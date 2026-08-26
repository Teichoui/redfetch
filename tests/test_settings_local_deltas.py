"""settings.local.toml is machine-managed: redfetch regenerates it deterministically
and stores only the user's deltas from the bundled settings.toml defaults."""

import tomllib

from dynaconf import Dynaconf

from conftest import _install_settings
from redfetch import config


def _render(tmp_path, data, monkeypatch):
    # base defaults include an @format DOWNLOAD_FOLDER that resolves against this
    monkeypatch.setenv("REDFETCH_DATA_DIR", str(tmp_path))
    out = tmp_path / "settings.local.toml"
    config.save_config(str(out), data)
    return out.read_text(encoding="utf-8")


def test_drops_values_equal_to_defaults(tmp_path, monkeypatch):
    # KissAssist (4) defaults to opt_in=true, so storing it again is redundant.
    # MySEQ (151) defaults to opt_in=false, so opt_in=true is a real change.
    data = {"LIVE": {"SPECIAL_RESOURCES": {
        "4": {"opt_in": True},
        "151": {"opt_in": True},
    }}}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    sr = parsed["LIVE"]["SPECIAL_RESOURCES"]
    assert "4" not in sr
    assert sr["151"] == {"opt_in": True}


def test_keeps_opt_out_that_differs_from_default(tmp_path, monkeypatch):
    # Opting out of a staff pick (default true) writes false, which is a real delta.
    data = {"LIVE": {"SPECIAL_RESOURCES": {"4": {"opt_in": False}}}}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    assert parsed["LIVE"]["SPECIAL_RESOURCES"]["4"] == {"opt_in": False}


def test_emit_is_idempotent(tmp_path, monkeypatch):
    data = {"LIVE": {"EQPATH": "C:/EQ", "SPECIAL_RESOURCES": {"151": {"opt_in": True}}}}
    first = _render(tmp_path, data, monkeypatch)
    second = _render(tmp_path, tomllib.loads(first), monkeypatch)
    assert first == second


def test_accepts_tomlkit_document(tmp_path, monkeypatch):
    import tomlkit
    doc = tomlkit.parse('[LIVE.SPECIAL_RESOURCES.151]\nopt_in = true\n')
    parsed = tomllib.loads(_render(tmp_path, doc, monkeypatch))
    assert parsed["LIVE"]["SPECIAL_RESOURCES"]["151"] == {"opt_in": True}


# --- emu multipath: SERVERS / ACTIVE_SERVER vs the delta-prune ---------------

def _fixture_base(tmp_path, monkeypatch, bundle_toml):
    """Swap the prune's bundled-defaults view for a fixture bundle."""
    bundle = tmp_path / "bundle.toml"
    bundle.write_text(bundle_toml, encoding="utf-8")
    fixture = Dynaconf(
        settings_files=[str(bundle)],
        environments=True,
        merge_enabled=True,
        env_switcher="REDFETCH_ENV",
    )
    monkeypatch.setattr(config, "_base_settings_cache", fixture)


_KNOWN_BUNDLE = """
[EMU.SERVERS.thegrind]
label = "The Grind"
opt_in = false
patcher_url = "https://thegrind.example/patcher.zip"
patcher_exe = "patcher.exe"
"""


def test_active_server_survives_prune(tmp_path, monkeypatch):
    """ACTIVE_SERVER has no bundled default; the MISSING rule must keep it."""
    data = {"EMU": {"ACTIVE_SERVER": "thegrind"}}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    assert parsed["EMU"]["ACTIVE_SERVER"] == "thegrind"


def test_novel_server_leaves_survive_prune(tmp_path, monkeypatch):
    """A hand-added custom server (no bundled counterpart) is kept verbatim."""
    entry = {"label": "My Server", "opt_in": True, "eqpath": "D:/Games/EQ-Mine"}
    data = {"EMU": {"SERVERS": {"myserver": dict(entry)}}}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    assert parsed["EMU"]["SERVERS"]["myserver"] == entry


def test_server_leaves_prune_against_known_bundle(tmp_path, monkeypatch):
    """Leaf-wise vs known defaults: equal leaves drop, deltas and overrides stay."""
    _fixture_base(tmp_path, monkeypatch, _KNOWN_BUNDLE)
    data = {"EMU": {"ACTIVE_SERVER": "thegrind", "SERVERS": {"thegrind": {
        "label": "The Grind",                                   # equals bundle -> pruned
        "opt_in": True,                                         # differs from bundled false -> kept
        "eqpath": "C:/Games/EQ-TheGrind",                       # novel local leaf -> kept
        "patcher_url": "https://mymirror.example/p.zip",        # local override -> kept
    }}}}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    server = parsed["EMU"]["SERVERS"]["thegrind"]
    assert "label" not in server
    assert server["opt_in"] is True
    assert server["eqpath"] == "C:/Games/EQ-TheGrind"
    assert server["patcher_url"] == "https://mymirror.example/p.zip"
    assert parsed["EMU"]["ACTIVE_SERVER"] == "thegrind"


def test_reverted_known_server_prunes_to_nothing(tmp_path, monkeypatch):
    """Delete-known = clear local leaves; the emptied table must vanish entirely."""
    _fixture_base(tmp_path, monkeypatch, _KNOWN_BUNDLE)
    data = {"EMU": {"SERVERS": {"thegrind": {"label": "The Grind", "opt_in": False}}}}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    assert "SERVERS" not in parsed.get("EMU", {})


def test_migrate_renames_navmesh_opt_in(tmp_path, monkeypatch):
    """NAVMESH_OPT_IN carries forward as NAVMESH_DOWNLOADS; reruns are no-ops."""
    monkeypatch.setenv("REDFETCH_DATA_DIR", str(tmp_path))
    local = tmp_path / "settings.local.toml"
    local.write_text("[LIVE]\nNAVMESH_OPT_IN = false\n", encoding="utf-8")

    config._migrate_local_settings(str(tmp_path))
    first = local.read_text(encoding="utf-8")
    parsed = tomllib.loads(first)
    assert parsed["LIVE"]["NAVMESH_DOWNLOADS"] is False
    assert "NAVMESH_OPT_IN" not in parsed["LIVE"]

    config._migrate_local_settings(str(tmp_path))  # second run: no-op
    assert local.read_text(encoding="utf-8") == first


def test_migrate_retypes_bool_auto_run_vvmq(tmp_path, monkeypatch):
    """Legacy bools become the "always"/"never" strings; reruns are no-ops."""
    monkeypatch.setenv("REDFETCH_DATA_DIR", str(tmp_path))
    local = tmp_path / "settings.local.toml"
    local.write_text(
        "[LIVE]\nAUTO_RUN_VVMQ = true\n[EMU]\nAUTO_RUN_VVMQ = false\n",
        encoding="utf-8",
    )

    config._migrate_local_settings(str(tmp_path))
    first = local.read_text(encoding="utf-8")
    parsed = tomllib.loads(first)
    assert parsed["LIVE"]["AUTO_RUN_VVMQ"] == "always"
    assert parsed["EMU"]["AUTO_RUN_VVMQ"] == "never"

    config._migrate_local_settings(str(tmp_path))  # second run: no-op
    assert local.read_text(encoding="utf-8") == first


# ---- key casing -------------------------------------------------------------
# dynaconf reads keys case-insensitively (last spelling wins, and a later env
# table replaces an earlier one wholesale), so save_config merges spellings
# and pruning respells them the bundled way. Older files that forked heal on their next save.


def test_merges_case_duplicate_leaves_last_wins(tmp_path, monkeypatch):
    data = {"LIVE": {"eqpath": "C:/hand", "EQPATH": "C:/cli"}}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    assert parsed["LIVE"] == {"EQPATH": "C:/cli"}


def test_merges_case_duplicate_env_tables(tmp_path, monkeypatch):
    """A hand-written [live] beside redfetch's own [LIVE]: dynaconf would drop
    everything under [live]; merged, both survive."""
    data = {"live": {"EQPATH": "C:/hand"}, "LIVE": {"THEME": "dracula"}}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    assert parsed == {"LIVE": {"EQPATH": "C:/hand", "THEME": "dracula"}}


def test_merges_nested_tables_into_bundled_spelling(tmp_path, monkeypatch):
    data = {"LIVE": {
        "special_resources": {"1974": {"Opt_In": False}},
        "SPECIAL_RESOURCES": {"151": {"opt_in": True}},
    }}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    assert parsed["LIVE"]["SPECIAL_RESOURCES"] == {
        "1974": {"opt_in": False}, "151": {"opt_in": True}}


def test_unknown_keys_keep_their_spelling(tmp_path, monkeypatch):
    data = {"LIVE": {"SERVERS": {"MyServer": {"label": "x"}}}}
    parsed = tomllib.loads(_render(tmp_path, data, monkeypatch))
    assert parsed["LIVE"]["SERVERS"] == {"MyServer": {"label": "x"}}


def test_path_like_compare_survives_odd_casing(tmp_path, monkeypatch):
    """Download_Folder equal to the default apart from slashes prunes like
    DOWNLOAD_FOLDER does: the path-aware compare keys on the bundled spelling."""
    data = {"LIVE": {"Download_Folder": str(tmp_path / "Downloads")}}
    assert "LIVE" not in tomllib.loads(_render(tmp_path, data, monkeypatch))


def test_update_setting_replaces_other_spelling(tmp_path, monkeypatch):
    _install_settings(tmp_path, monkeypatch, env="LIVE", current_env="LIVE",
                      local_toml='[LIVE]\neqpath = "C:/hand"\n')
    config.update_setting(["EQPATH"], "C:/cli", env="LIVE")
    parsed = tomllib.loads((tmp_path / "settings.local.toml").read_text(encoding="utf-8"))
    assert parsed["LIVE"] == {"EQPATH": "C:/cli"}


def test_update_setting_unsets_other_spelling(tmp_path, monkeypatch):
    _install_settings(tmp_path, monkeypatch, env="LIVE", current_env="LIVE",
                      local_toml='[LIVE]\neqpath = "C:/hand"\n')
    config.update_setting(["EQPATH"], None, env="LIVE")
    assert "LIVE" not in tomllib.loads((tmp_path / "settings.local.toml").read_text(encoding="utf-8"))
