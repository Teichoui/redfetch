# standard
import datetime
import json
import os
import platform
import re
import shutil
import tomllib
from contextlib import suppress
from pathlib import Path

# third-party
import tomlkit
from tomlkit.exceptions import TOMLKitError
from dynaconf import Dynaconf, Validator, ValidationError
from dynaconf.loaders import env_loader
from platformdirs import user_config_dir, user_data_dir
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

# Parent Category to folder
CATEGORY_MAP = {
    8: "macros",
    11: "plugins",
    25: "lua"
}

# MQ Client environments (dynaconf envs)
# Tokens are persisted (REDFETCH_ENV, DB names, [EMU] settings sections) and never change;
# they're also reserved against server slugs. Labels name the game build.
ENVS = {"LIVE": "Live", "TEST": "Test", "EMU": "RoF2"}
DEFAULT_ENV = next(iter(ENVS))  # first client is the default


def env_token(value: str) -> str | None:
    """The client token for text typed as a token or a label, any case; None if neither."""
    key = value.strip().casefold()
    for token, label in ENVS.items():
        if key in (token.casefold(), label.casefold()):
            return token
    return None


# Envs who have switchable servers (servers.py manages)
MULTI_SERVER_ENVS = ("EMU",)

# Display row for a multi-server client's bare setup (no named server active).
BARE_SERVER_LABEL = "Any emu server"

# Resource to MQ version
VANILLA_MAP = {
    1974: "LIVE",
    2218: "TEST",
    60: "EMU"
}

MYSEQ_MAP = {
    151: "LIVE",
    164: "TEST"
}

MAPS_MAP = {
    "brewall": "153",
    "good": "303",
}

# to make settings.local.toml easier to read, names are added in comments
RESOURCE_NAMES = {
    "1974": "Very Vanilla MQ Live",
    "2218": "Very Vanilla MQ Test",
    "60": "Very Vanilla MQ Emu",
    "4": "KissAssist",
    "2539": "Lua Event Manager",
    "151": "MySEQ Live",
    "164": "MySEQ Test",
    "153": "Brewall's EverQuest Maps",
    "303": "Good's EverQuest Maps",
    "2318": "guildclicky",
    "2174": "buttonmaster",
    "2062": "alertmaster",
    "3040": "rgmercs",
    "2196": "lootly",
    "2088": "boxhud",
    "2391": "scriber",
    "3001": "bazaar / auction helper",
    "2937": "skill skillup: spells and others",
    "2675": "lootnscoot",
    "973": "Ninjadvloot.inc",
}

BREADCRUMB_FILENAME = "last_command.json"
DEFAULT_CONFIG_DIR = user_config_dir("redfetch", "RedGuides")

script_dir = os.path.dirname(os.path.abspath(__file__))

# Populated by initialize_config()
config_dir = None
env_file_path = None
settings = None


def cache_dir() -> str:
    """Return the cache directory, creating it if needed."""
    base = config_dir or os.environ.get("REDFETCH_CONFIG_DIR") or os.getcwd()
    path = os.path.join(base, ".cache")
    os.makedirs(path, exist_ok=True)
    return path


def normalize_and_create_path(path):
    if not path:
        raise ValidationError("Path is not set.")
    normalized_path = os.path.normpath(path)
    if not os.path.exists(normalized_path):
        try:
            os.makedirs(normalized_path, exist_ok=True)
            print(f"Created directory: {normalized_path}")
        except OSError as e:
            raise ValidationError(f"Failed to create the directory '{normalized_path}': {e}")
    return normalized_path


def normalize_category_paths(data):
    """Normalize and validate absolute paths in CATEGORY_PATHS."""
    if not isinstance(data, dict):
        return data
    valid_names = set(CATEGORY_MAP.values())
    for key, value in list(data.items()):
        if key not in valid_names:
            raise ValidationError(
                f"Unknown category '{key}' in CATEGORY_PATHS. "
                f"Valid categories: {', '.join(sorted(valid_names))}"
            )
        if isinstance(value, str) and value:
            normalized = os.path.normpath(value)
            data[key] = normalized
    return data


def normalize_paths_in_dict(data):
    """Dynaconf validator for SPECIAL_RESOURCE paths."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                normalize_paths_in_dict(value)
            elif isinstance(value, list):
                for item in value:
                    normalize_paths_in_dict(item)
            elif key in ['default_path', 'custom_path'] and isinstance(value, str):
                normalized_value = os.path.normpath(value) if value else value
                data[key] = normalized_value
    elif isinstance(data, list):
        for item in data:
            normalize_paths_in_dict(item)
    return data


def initialize_config():
    """Initialize configuration settings."""
    from redfetch.config_firstrun import first_run_setup
    
    global config_dir, env_file_path, settings  # Declare globals to modify them

    # Perform first-run setup
    config_dir = first_run_setup()
    os.environ['REDFETCH_CONFIG_DIR'] = config_dir
    
    # Data dir: Linux default uses XDG data dir (~/.local/share), else same as config
    is_linux_default = platform.system() == "Linux" and config_dir == DEFAULT_CONFIG_DIR
    data_dir = user_data_dir("redfetch", "RedGuides") if is_linux_default else config_dir
    os.makedirs(data_dir, exist_ok=True)
    os.environ['REDFETCH_DATA_DIR'] = data_dir

    # Path to the .env file
    env_file_path = os.path.join(config_dir, '.env')

    # Check if the .env file exists
    if not os.path.exists(env_file_path):
        # If not, create it and set the default client
        atomic_write_text(env_file_path, f'REDFETCH_ENV={DEFAULT_ENV}\n')
        print(f".env file created at {env_file_path} (client: {ENVS[DEFAULT_ENV]})")

    # Migrate any settings.local.toml written by older versions
    _migrate_local_settings(config_dir)

    # Initialize Dynaconf settings
    settings = Dynaconf(
        envvar_prefix="REDFETCH",
        settings_files=[
            os.path.join(script_dir, 'settings.toml'),
            os.path.join(config_dir, 'settings.local.toml')
        ],
        load_dotenv=True,
        dotenv_path=env_file_path,
        dotenv_override=True,
        env_switcher="REDFETCH_ENV",
        merge_enabled=True,
        lazy_load=True,
        environments=True,
        validate_on_update=True,
        validators=[
            Validator("DOWNLOAD_FOLDER", cast=normalize_and_create_path),
            # Separate validator for EQPATH to avoid triggering eqgame.exe check
            Validator("EQPATH", default=None, cast=lambda x: os.path.normpath(x) if x else None),
            # An optional path to a zip, iso or folder. Not a directory we create, and an unset value shouldn't crash on boot.
            Validator("CLEAN_SOURCE", default=None, cast=lambda x: os.path.normpath(x) if x else None),
            Validator("SPECIAL_RESOURCES", cast=normalize_paths_in_dict),
            Validator("CATEGORY_PATHS", default={}, cast=normalize_category_paths)
        ]
    )

    self_heal_eqpath()
    write_breadcrumb()

    # Return the settings object for potential use
    return settings


def self_heal_eqpath() -> None:
    """Fill a blank or broken EQ PATH from autologin's login.db, per env."""
    from redfetch import utils, detecteq

    for env in ENVS:
        try:
            env_settings = settings.from_env(env)
            # Spelled inline: config must not import servers.
            if env in MULTI_SERVER_ENVS and env_settings.get("ACTIVE_SERVER"):
                continue  # AutoLogin's shared emu path isn't tied to the active server.
            stored = env_settings.get("EQPATH")
            if stored and detecteq.is_valid_eq_dir(stored):
                continue  # heal only when blank or broken

            vvmq_id = utils.get_current_vvmq_id(env)
            if not vvmq_id:
                continue
            vvmq = utils.resolve_special_destination(
                env_settings.SPECIAL_RESOURCES.get(vvmq_id), env_settings.DOWNLOAD_FOLDER
            )
            if not vvmq:
                continue

            detected = detecteq.read_autologin_eq_path(os.path.join(vvmq, "config"), env)
            if detected and detected != stored: 
                update_setting(["EQPATH"], detected, env=env)
        except Exception:
            continue  # we're not stopping for this


def _resolve_redfetch_executable():
    """PYAPP will give a path when built with PYAPP_PASS_LOCATION=1"""
    pyapp = os.environ.get("PYAPP")
    if pyapp and "redfetch" in os.path.basename(pyapp).lower() and os.path.exists(pyapp):
        return os.path.abspath(pyapp)

    cmd = shutil.which("redfetch")
    if cmd:
        return os.path.abspath(cmd)

    return None


@retry(
    retry=retry_if_exception_type(PermissionError),
    stop=stop_after_attempt(5),
    wait=wait_fixed(0.1),
    reraise=True,
)
def _replace_with_retry(src: str, dst: str) -> None:
    # MQ reads update_status.json
    os.replace(src, dst)


def atomic_write_text(path: str, text: str) -> None:
    """Write UTF-8 text to `path` via a temp file + os.replace() so readers never see a partial write."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text)
    _replace_with_retry(tmp_path, path)


def atomic_write_json(path: str, data) -> None:
    """Atomically write `data` as UTF-8 JSON (ensure_ascii=False keeps non-ASCII paths/titles verbatim)."""
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def write_breadcrumb() -> None:
    """A breadcrumb in the user config dir to track the most recently used redfetch binary's location."""
    try:
        program = _resolve_redfetch_executable()
        if program is None:
            return

        breadcrumb_path = os.path.join(DEFAULT_CONFIG_DIR, BREADCRUMB_FILENAME)
        atomic_write_json(breadcrumb_path, {"program": program})
    except Exception:
        pass


def remove_breadcrumb() -> None:
    Path(DEFAULT_CONFIG_DIR, BREADCRUMB_FILENAME).unlink(missing_ok=True)


def switch_environment(new_env):
    """Switch the environment and update the settings."""
    if settings is None:
        raise RuntimeError("Configuration has not been initialized.")

    # Update the .env file first
    write_env_to_file(new_env)

    # Set the Dynaconf environment so subsequent `from_env` calls use the new env
    settings.setenv(new_env)

    # Keep a simple attribute around for convenience (used throughout the app)
    settings.ENV = new_env

    # Re-validate settings after environment switch; callers own the confirmation.
    try:
        settings.validators.validate()
    except ValidationError as e:
        print(f"Validation error after switching to {new_env}: {e}")

    return settings


def select_environment_in_memory(new_env):
    """Select `new_env` for this process only, without persisting to the .env file."""
    if settings is None:
        raise RuntimeError("Configuration has not been initialized.")

    settings.setenv(new_env)
    settings.ENV = new_env

    try:
        settings.validators.validate()
    except ValidationError as e:
        print(f"Validation error after selecting {new_env}: {e}")

    return settings


def ensure_config_file_exists(file_path):
    """Ensure the configuration file exists."""
    if not os.path.exists(file_path):
        atomic_write_text(file_path, tomlkit.dumps({}))
        print(f"Created new configuration file: {file_path}")


def load_config(file_path):
    """Load the TOML configuration file, creating an empty document if it doesn't exist."""
    if not os.path.exists(file_path):
        return tomlkit.document()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return tomlkit.parse(f.read())
    except Exception as e:
        raise ValidationError(f"Error loading config file {file_path}: {e}")


def _descend_tables(table, keys):
    for key in keys:
        if key not in table:
            table[key] = tomlkit.table()
        table = table[key]
    return table


def _annotate_special_resource_comments(toml_text: str) -> str:
    """Add a `# friendly-name` comment above each known SPECIAL_RESOURCES section."""
    section_pattern = re.compile(
        r"^\[(?:DEFAULT|LIVE|TEST|EMU)"
        r"(?:\.SERVERS\.[A-Za-z0-9_-]+|\.GENERIC)?"
        r"\.SPECIAL_RESOURCES\.(\d+)\]\s*$"
    )

    new_lines = []
    for line in toml_text.splitlines():
        match = section_pattern.match(line)
        if match:
            friendly_name = RESOURCE_NAMES.get(match.group(1))
            if friendly_name and not (new_lines and new_lines[-1] == f"# {friendly_name}"):
                new_lines.append(f"# {friendly_name}")
        new_lines.append(line)

    ending = "\n" if toml_text.endswith("\n") else ""
    return "\n".join(new_lines) + ending


# Header for settings.local.toml, which redfetch rewrites on every save.
SETTINGS_LOCAL_HEADER = (
    "# Managed by redfetch: stores only your changes from settings.toml defaults.\n"
    "# Editable by hand, but redfetch rewrites on save, so comments may be dropped\n"
    "# and values matching a default are removed. See settings.toml for all options.\n"
)

# Path-valued keys, compared with path-aware equality (slash vs backslash).
_PATH_LIKE_KEYS = {"EQPATH", "DOWNLOAD_FOLDER", "custom_path", "default_path"}

MISSING = object()
_base_settings_cache = None


def _base_settings():
    """Cached Dynaconf view of the bundled settings.toml defaults (no overrides)."""
    global _base_settings_cache
    if _base_settings_cache is None:
        _base_settings_cache = Dynaconf(
            settings_files=[os.path.join(script_dir, "settings.toml")],
            environments=True,
            merge_enabled=True,
            env_switcher="REDFETCH_ENV",
        )
    return _base_settings_cache


def _to_plain(data):
    """Convert a tomlkit document/table (or any nested mapping) to plain dicts/lists."""
    if hasattr(data, "unwrap"):
        return data.unwrap()
    if isinstance(data, dict):
        return {k: _to_plain(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_to_plain(v) for v in data]
    return data


def _merge_case_variants(table, into=None):
    """merge together keys that only differ by cAsE."""
    into = {} if into is None else into
    for key, value in table.items():
        name = next((k for k in into if k.lower() == key.lower()), key)
        if isinstance(value, dict):
            nested = into.get(name)
            into[name] = _merge_case_variants(value, nested if isinstance(nested, dict) else {})
        else:
            into[name] = value
    return into


def _equals_default(value, default, key):
    """True if value matches the default (and can be dropped)."""
    if value == default:
        return True
    if (
        key in _PATH_LIKE_KEYS
        and isinstance(value, str) and value
        and isinstance(default, str) and default
    ):
        return os.path.normpath(value) == os.path.normpath(default)
    return False


def _prune_branch(local, base):
    """Drops any setting that matches the bundled default setting."""
    spelling = {k.lower(): k for k in base}
    for key, value in list(local.items()):
        del local[key]
        key = spelling.get(key.lower(), key)
        base_value = base.get(key, MISSING)
        if isinstance(value, dict):
            _prune_branch(value, base_value if isinstance(base_value, dict) else {})
            if not value:
                continue
        elif base_value is not MISSING and _equals_default(value, base_value, key):
            continue
        elif isinstance(value, list) and isinstance(base_value, list):
            bundled = {i.lower() for i in base_value}
            value = [i for i in value if i.lower() not in bundled]  # dynaconf merges the bundle back in on read
            if not value:
                continue
        local[key] = value


def _prune_to_deltas(data):
    """Builds a list of client defaults, hands it to _prune_branch."""
    base = _base_settings()
    base_tree = {}
    for env in data:
        try:
            base_tree[env.upper()] = base.from_env(env).as_dict()
        except Exception:
            pass  # defaults unresolvable; keep env verbatim
    _prune_branch(data, base_tree)


def save_config(file_path, config_data):
    """Writes settings.local.toml."""
    data = _merge_case_variants(_to_plain(config_data))
    _prune_to_deltas(data)

    body = _annotate_special_resource_comments(tomlkit.dumps(data)).strip("\n")

    if body:
        toml_text = f"{SETTINGS_LOCAL_HEADER}\n{body}\n"
    else:
        toml_text = SETTINGS_LOCAL_HEADER
    atomic_write_text(file_path, toml_text)


def _migrate_local_settings(config_dir):
    """Carry changed settings in an older settings.local.toml"""
    config_file = os.path.join(config_dir, 'settings.local.toml')
    if not os.path.exists(config_file):
        return
    try:
        with open(config_file, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return
    changed = False
    for env_table in data.values():
        if not isinstance(env_table, dict):
            continue
        # NAVMESH_OPT_IN became NAVMESH_DOWNLOADS
        if "NAVMESH_OPT_IN" in env_table:
            env_table.setdefault("NAVMESH_DOWNLOADS", env_table.pop("NAVMESH_OPT_IN"))
            changed = True
        # bool AUTO_RUN_VVMQ became tri-state "ask"/"always"/"never"
        if isinstance(env_table.get("AUTO_RUN_VVMQ"), bool):
            env_table["AUTO_RUN_VVMQ"] = "always" if env_table["AUTO_RUN_VVMQ"] else "never"
            changed = True
    if changed:
        save_config(config_file, data)


def active_settings():
    """Settings view for the active env.

    Use this instead of bare `settings.X` for env-scoped keys
    """
    return settings.from_env(settings.ENV)


def reload_settings():
    """Reload settings from disk and invalidate from_env() clones.

    useful until a future dynaconf's reload() clears env_cache
    """
    settings.reload()
    settings.__core__.config.env_cache.clear()


def normalize_tristate(value) -> str:
    """Interpreter for "ask"/"always"/"never"."""
    token = str(value).strip().lower()
    return token if token in ("always", "never") else "ask"


# CLI value typing (`redfetch config`).
# Why a bridge? Dynaconf reads, tomlkit writes, case issues because neither knows the other.

def read_setting(setting_path, env=None):
    """Effective value (after overrides) for the chosen client, with handling."""
    env = env or settings.ENV
    path_label = ".".join(setting_path)
    try:
        value = settings.from_env(env).get(path_label, MISSING)
    except (AttributeError, ValueError) as exc:
        # better to state a common config issue than raise an error
        raise ValueError(f"'{path_label}' isn't a valid setting path: {exc}") from exc
    return value if value is MISSING else _to_plain(value)


def _parse_toml_value(raw):
    """Type a CLI string for tomlkit, unknown is a string"""
    token = raw.strip().lower()
    if token in ("true", "false"):  # accept True/FALSE too; TOML itself is lowercase-only
        return token == "true"
    try:
        value = tomlkit.parse(f"v = {raw}")["v"].unwrap()
    except TOMLKitError:
        return raw
    # we don't have anything that needs a date at the moment
    if isinstance(value, (datetime.date, datetime.time)):
        return raw
    return value


def coerce_setting_value(setting_path, raw_values, env=None):
    """Coerce aka convert the CLI's string arguments into the correct type."""
    env = env or settings.ENV
    path_label = ".".join(setting_path)
    current = read_setting(setting_path, env=env)
    if current is MISSING and setting_path[0].upper() == "PROTECTED_FILES_BY_RESOURCE":
        current = []  # new ids are still filename lists
    if isinstance(current, dict):
        raise ValueError(f"'{path_label}' is a settings table, not a single setting.")
    if len(raw_values) != 1:
        if current is not MISSING and not isinstance(current, list):
            raise ValueError(f"'{path_label}' takes a single value, got {len(raw_values)}.")
        return list(raw_values)
    raw = raw_values[0]
    value = _parse_toml_value(raw)
    if isinstance(value, dict):
        raise ValueError(f"'{path_label}' can't be set to a table.")
    if isinstance(current, bool) and not isinstance(value, bool):
        raise ValueError(f"'{path_label}' expects true or false, got '{raw}'.")
    if isinstance(current, str) and not isinstance(value, (str, list)):
        return raw  # str settings stay str; only the array spelling may retype them
    if isinstance(current, list) and not isinstance(value, list):
        return [raw]  # a bare entry keeps list settings lists, matching --add
    return value


def apply_list_edits(setting_path, additions, removals, env=None):
    """cli --add/--remove on a list setting."""
    env = env or settings.ENV
    current = read_setting(setting_path, env=env)
    if current is not MISSING and not isinstance(current, list):
        raise ValueError(
            f"--add/--remove only work on list settings; "
            f"'{'.'.join(setting_path)}' isn't one."
        )
    items = {str(i).lower(): str(i) for i in current} if isinstance(current, list) else {}
    for entry in additions:
        items.setdefault(entry.lower(), entry)
    drop = {entry.lower() for entry in removals}
    bundled = {i.lower() for i in _base_settings().from_env(env).get(".".join(setting_path), [])}
    for entry in removals:
        if entry.lower() in bundled:
            raise ValueError(f"'{entry}' is a shipped default and can't be removed from '{'.'.join(setting_path)}'.")
    return [item for key, item in items.items() if key not in drop]


def update_setting(setting_path, setting_value, env=None):
    """Update a specific setting in the settings.local.toml file and in memory,
    optionally within a specific environment."""
    if settings is None or config_dir is None:
        raise RuntimeError("Configuration has not been initialized.")

    config_file = os.path.join(config_dir, 'settings.local.toml')
    ensure_config_file_exists(config_file)
    config_data = load_config(config_file)

    # Use the specified environment or, if None, the current environment
    env = env or settings.ENV

    # Ensure the environment exists in the configuration
    if env not in config_data:
        config_data[env] = tomlkit.table()

    # Navigate to the correct setting based on the path within the specified environment
    current_data = _descend_tables(config_data[env], setting_path[:-1])
    # dynaconf reads keys case-insensitively; use the file's spelling so an unset finds it
    leaf = next((k for k in current_data if k.lower() == setting_path[-1].lower()), setting_path[-1])

    # Debugging output
    print(f"Updating config key: {'.'.join(setting_path)}")
    print(f"Old Value: {current_data.get(leaf, 'Not set')}")

    # None means "unset", TOML can't store None, so remove the key
    if setting_value is None:
        current_data.pop(leaf, None)
    else:
        current_data[leaf] = setting_value

    print(f"New Value: {setting_value}")

    save_config(config_file, config_data)
    reload_settings()

    print("Configuration saved.")


def write_env_to_file(new_env):
    """Persist the selected environment to the .env file; dynaconf reads it back via env_switcher."""
    if env_file_path is None:
        raise RuntimeError("Configuration has not been initialized. Call initialize_config() first.")

    env_loader.write(env_file_path, {"REDFETCH_ENV": new_env})

    # Env changed -> re-shows client/config banner.
    with suppress(OSError):
        os.remove(os.path.join(os.path.dirname(env_file_path), ".banner_shown"))
