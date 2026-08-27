"""spawn_silent_self_update: hidden, spawn-then-exit, fire-and-forget — and never
for dev builds or when nothing is newer. Also config.own_pyapp_exe, which decides
whether the exe named by PYAPP is really the one that launched us."""

import os
import subprocess
from types import SimpleNamespace

import pytest

from redfetch import config, meta

REAL_PYPI = "https://pypi.org/pypi/redfetch/json"

_HIDDEN_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


@pytest.fixture
def pyapp_install(tmp_path, monkeypatch):
    """Launched by the PyApp redfetch.exe: PYAPP names it and it is our parent process."""
    exe = tmp_path / "redfetch.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("PYAPP", str(exe))
    monkeypatch.setattr(config, "_launcher_exe", lambda: str(exe))
    return str(exe)


@pytest.fixture
def inherited_pyapp(tmp_path, monkeypatch):
    """A pipx redfetch started under hatch.exe (a PyApp binary), so PYAPP=hatch.exe leaked in."""
    hatch = tmp_path / "hatch.exe"
    hatch.write_bytes(b"")
    shell = tmp_path / "cmd.exe"
    shell.write_bytes(b"")
    monkeypatch.setenv("PYAPP", str(hatch))
    monkeypatch.setattr(config, "_launcher_exe", lambda: str(shell))
    return str(hatch)


def _fake_process_tree(monkeypatch, *exes):
    """psutil.Process() whose ancestry is `exes`: our own image first, then each parent."""
    class Proc:
        def __init__(self, chain):
            self.chain = chain

        def exe(self):
            return self.chain[0]

        def parent(self):
            return Proc(self.chain[1:]) if len(self.chain) > 1 else None

    monkeypatch.setattr(config.psutil, "Process", lambda: Proc(list(exes)))


def test_launcher_looks_past_venv_python_stub(monkeypatch, tmp_path):
    stub = tmp_path / "python.exe"
    stub.write_bytes(b"")
    exe = tmp_path / "redfetch.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(config.sys, "executable", str(stub))
    _fake_process_tree(monkeypatch, "base-python.exe", str(stub), str(exe))

    assert config._launcher_exe() == str(exe)


def test_launcher_is_direct_parent_without_stub(monkeypatch, tmp_path):
    exe = tmp_path / "redfetch.exe"
    exe.write_bytes(b"")
    _fake_process_tree(monkeypatch, "python.exe", str(exe))

    assert config._launcher_exe() == str(exe)


@pytest.fixture
def spawn_env(monkeypatch):
    """Newer version on real PyPI; Popen captured; site-packages sweep neutered."""
    monkeypatch.setattr(meta, "PYPI_URL", REAL_PYPI)
    monkeypatch.setattr(meta, "fetch_latest_version_cached", lambda: "99.0.0")
    monkeypatch.setattr(meta, "get_current_version", lambda: "1.0.0")
    monkeypatch.setattr(meta, "_sweep_pip_stash_debris", lambda: None)
    monkeypatch.delenv("PYAPP", raising=False)

    calls = []

    def _popen(command, **kwargs):
        calls.append(SimpleNamespace(command=command, kwargs=kwargs))
        return SimpleNamespace(pid=4242)

    monkeypatch.setattr(meta.subprocess, "Popen", _popen)
    return SimpleNamespace(calls=calls, monkeypatch=monkeypatch)


def test_pyapp_spawns_self_update_hidden(spawn_env, pyapp_install):
    assert meta.spawn_silent_self_update() is True
    (call,) = spawn_env.calls
    assert call.command == [pyapp_install, "self", "update"]
    assert call.kwargs["creationflags"] == _HIDDEN_FLAGS
    assert call.kwargs["stdin"] is subprocess.DEVNULL
    assert call.kwargs["stdout"] is subprocess.DEVNULL
    assert call.kwargs["stderr"] is subprocess.DEVNULL


def test_inherited_pyapp_from_another_app_is_ignored(spawn_env, inherited_pyapp):
    # It must upgrade itself, not run `hatch.exe self update`.
    assert meta.spawn_silent_self_update() is True
    (call,) = spawn_env.calls
    assert inherited_pyapp not in call.command
    assert call.command[-1] == "redfetch"


def test_pipx_spawns_upgrade_command(spawn_env):
    spawn_env.monkeypatch.setattr(meta, "detect_installation_method", lambda: "pipx")

    assert meta.spawn_silent_self_update() is True
    (call,) = spawn_env.calls
    assert call.command == ["pipx", "upgrade", "redfetch"]
    assert call.kwargs["creationflags"] == _HIDDEN_FLAGS


def test_pip_sweeps_stash_debris_before_spawn(spawn_env):
    events = []
    commands = []
    spawn_env.monkeypatch.setattr(meta, "detect_installation_method", lambda: "pip")
    spawn_env.monkeypatch.setattr(meta, "_sweep_pip_stash_debris", lambda: events.append("sweep"))

    def _popen(command, **kwargs):
        events.append("spawn")
        commands.append(command)
        return SimpleNamespace(pid=4242)

    spawn_env.monkeypatch.setattr(meta.subprocess, "Popen", _popen)

    assert meta.spawn_silent_self_update() is True
    # Order matters: sweeping ~edfetch debris after pip starts would race it.
    assert events == ["sweep", "spawn"]
    assert commands[0][-4:] == ["pip", "install", "--upgrade", "redfetch"]


def test_no_spawn_when_already_current(spawn_env):
    spawn_env.monkeypatch.setattr(meta, "fetch_latest_version_cached", lambda: "1.0.0")

    assert meta.spawn_silent_self_update() is False
    assert spawn_env.calls == []


def test_dev_builds_never_auto_update(spawn_env):
    spawn_env.monkeypatch.setattr(meta, "PYPI_URL", "https://test.pypi.org/pypi/redfetch/json")
    spawn_env.monkeypatch.setattr(
        meta, "fetch_latest_version_cached",
        lambda: pytest.fail("dev builds must not even check for updates"),
    )

    assert meta.spawn_silent_self_update() is False
    assert spawn_env.calls == []


def test_spawn_failure_is_swallowed(spawn_env):
    def _no_pipx(*a, **k):
        raise FileNotFoundError("pipx not on MQ's PATH")

    spawn_env.monkeypatch.setattr(meta.subprocess, "Popen", _no_pipx)
    spawn_env.monkeypatch.setattr(meta, "detect_installation_method", lambda: "pipx")

    # The sync already succeeded; a failed spawn must not fail the headless run.
    assert meta.spawn_silent_self_update() is False
