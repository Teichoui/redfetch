"""Tests for the non-interactive loader update check."""

from __future__ import annotations

import sys
import types

import pytest
from typer.testing import CliRunner

about_module = types.ModuleType("redfetch.__about__")
about_module.__version__ = "0+test"
sys.modules.setdefault("redfetch.__about__", about_module)

from redfetch.config_firstrun import is_configured
from redfetch.sync_types import LocalInstallState, LocalSnapshot, UpdateCheckResult
from redfetch.update_check import _count_outdated


@pytest.fixture
def make_state():
    def _make(
        resource_id,
        *,
        version_local=10,
        target_kind="root",
        parent_id=None,
        root_resource_id=None,
    ):
        if target_kind == "root":
            target_key = f"/{resource_id}/"
        else:
            target_key = f"/{parent_id}/{resource_id}/"
        return LocalInstallState(
            target_key=target_key,
            resource_id=resource_id,
            parent_id=parent_id,
            parent_target_key=f"/{parent_id}/" if parent_id else None,
            root_resource_id=root_resource_id or resource_id,
            target_kind=target_kind,
            version_local=version_local,
        )

    return _make


def test_counts_outdated_and_skips_none_version(make_state):
    states = [
        make_state("100", version_local=10),
        make_state("200", version_local=20),
        make_state("300", version_local=None),
    ]
    snapshot = LocalSnapshot(install_targets={s.target_key: s for s in states})
    manifest = {
        "resources": {
            "100": {"version_id": 11},
            "200": {"version_id": 20},
            "300": {"version_id": 99},
        }
    }
    result = _count_outdated(snapshot, manifest)
    assert result.updates_available == 1


def test_caller_as_dependency_not_tracked(make_state):
    dep = make_state(
        "1974",
        version_local=5,
        target_kind="dependency",
        parent_id="100",
        root_resource_id="100",
    )
    snapshot = LocalSnapshot(install_targets={dep.target_key: dep})
    manifest = {"resources": {"1974": {"version_id": 10}}}
    result = _count_outdated(snapshot, manifest, caller_resource_id="1974")
    assert result.updates_available == 1
    assert result.caller_update_available is None


def test_is_configured_false_when_flag_but_no_env(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (tmp_path / "first_run_complete").write_text(str(config_dir))
    assert is_configured(str(tmp_path)) is False


def test_check_command_returns_machine_readable_stdout(monkeypatch):
    from redfetch import main

    async def fake_check_command_async(db_path, caller_resource_id):
        return UpdateCheckResult(
            updates_available=0,
            caller_update_available=False,
            caller_resource_id=caller_resource_id,
        )

    monkeypatch.setattr(main, "_has_auth_credentials", lambda: True)
    monkeypatch.setattr("redfetch.config_firstrun.is_configured", lambda: True)
    monkeypatch.setattr(main.config, "initialize_config", lambda: None)
    monkeypatch.setattr(main.config, "settings", types.SimpleNamespace(ENV="LIVE"))
    monkeypatch.setattr(main.auth, "initialize_keyring", lambda: None)
    monkeypatch.setattr(main.store, "initialize_db", lambda db_name: None)
    monkeypatch.setattr(main.store, "get_db_path", lambda db_name: "test.db")
    monkeypatch.setattr(main, "_check_command_async", fake_check_command_async)

    result = CliRunner().invoke(main.app, ["check", "--caller-resource-id", "1974"])

    assert result.exit_code == 0
    assert result.stdout == "0\n"
