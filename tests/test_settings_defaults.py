"""Where setting defaults live.

Defaults ship in settings.toml [DEFAULT] so delta-pruning and `config show`
can see them.
"""
import pytest

from conftest import _install_settings
from redfetch import config, navmesh, utils

ENVS = ("LIVE", "TEST", "EMU")


@pytest.mark.parametrize("env", ENVS)
def test_auto_run_vvmq_defaults_to_ask(tmp_path, monkeypatch, env):
    """The "ask" default shows post_update's Always/Once/Never dialog after each
    update; "always"/"never" skip it. A bool default here would make the dialog
    unreachable — this test turns that into a CI failure instead."""
    _install_settings(tmp_path, monkeypatch, env=env)
    assert config.read_setting(["AUTO_RUN_VVMQ"], env=env) == "ask"


@pytest.mark.parametrize("env", ENVS)
def test_bool_defaults_ship_in_settings_toml(tmp_path, monkeypatch, env):
    """AUTO_UPDATE / NAVMESH_DOWNLOADS default true from [DEFAULT], visible
    in every env view rather than hidden in their consumers."""
    settings = _install_settings(tmp_path, monkeypatch, env=env)
    assert settings.from_env(env).get("AUTO_UPDATE") is True
    assert settings.from_env(env).get("NAVMESH_DOWNLOADS") is True


def test_readers_default_on_when_unset(tmp_path, monkeypatch):
    _install_settings(tmp_path, monkeypatch, env="LIVE")
    assert utils.is_auto_update_enabled() is True
    assert navmesh.is_navmesh_enabled() is True
