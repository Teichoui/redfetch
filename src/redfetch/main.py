# standard imports
import json
import sys
import os
import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated
import asyncio

# third-party imports
from rich.prompt import Prompt
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
import typer

# local imports
from redfetch import api
from redfetch import auth
from redfetch import config
from redfetch import detecteq
from redfetch import meta
from redfetch import net
from redfetch import post_update
from redfetch import processes
from redfetch import provision
from redfetch import servers
from redfetch import utils
from redfetch import push
from redfetch import sync
from redfetch import store
from redfetch import shortcuts
from redfetch import update_status
from redfetch.runtime_errors import exit_with_fatal_error
from redfetch.sync_types import SyncOutcome


app = typer.Typer(
    help="[bold red]redfetch[/bold red] - RedGuides resource management tool. Run without arguments to launch the [italic]Terminal User Interface[/italic].",
    rich_markup_mode="rich"
)

console = Console()


# ===== CLI helpers =====

class Env(str, Enum):
    LIVE = "LIVE"
    TEST = "TEST"
    EMU = "EMU"



_CLIENT_COLORS = ("green", "yellow", "cyan", "magenta", "blue")


def _client_choices(conjunction: str = "or") -> str:
    """Help-text list of clients from config.ENVS."""
    colored = [
        f"[{_CLIENT_COLORS[i % len(_CLIENT_COLORS)]}]{token}[/]"
        + ("" if label.casefold() == token.casefold() else f" ({label})")
        for i, (token, label) in enumerate(config.ENVS.items())
    ]
    return f"{', '.join(colored[:-1])}, {conjunction} {colored[-1]}"


def _client_option(help_text: str = "Use this client for this run only, without changing your active client."):
    return typer.Option("--client", "--server", "-s", case_sensitive=False, help=help_text)


_Client = Annotated[Env | None, _client_option()]


@contextmanager
def _usage_errors():
    """When libraries throw a ValueError, convert it to BadParameter."""
    try:
        yield
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _require_eq_folder(folder: str) -> None:
    if not folder:
        raise typer.BadParameter("An EverQuest folder is required.")
    if not detecteq.is_valid_eq_dir(folder):
        raise typer.BadParameter(f"No eqgame.exe in {folder}, so it isn't an EverQuest folder.")


def _apply_server_override(server: Env | None = None) -> None:
    if server is not None and server.value != config.settings.ENV:
        config.select_environment_in_memory(server.value)


def _initialize_auth():
    """Initialize configuration, update check, and auth (no DB, no network)."""
    config.initialize_config()
    if os.environ.get('CI') != 'true':
        _ = meta.check_for_update()
    auth.initialize_keyring()
    auth.authorize()


def initialize_db_only(server: Env | None = None):
    """Initialize configuration, auth, and local cache database (no network)."""
    _initialize_auth()
    _apply_server_override(server)
    db_name = store.db_name(config.settings.ENV)
    store.initialize_db(db_name)
    db_path = store.get_db_path(db_name)
    return db_name, db_path


class _CliPostUpdate:
    """CLI adapter for post_update.execute: rich prompts, console output."""

    def notify(self, message: str, *, error: bool = False) -> None:
        console.print(message)

    async def confirm_restart(self) -> bool:
        try:
            choice = Prompt.ask(
                "Restart MacroQuest to apply the update now?",
                choices=["yes", "no"],
                default="yes",
            )
        except (KeyboardInterrupt, EOFError):
            return False  # headless/no-stdin: skip the restart, update applies next launch
        return choice == "yes"

    async def ask_cold_start(self) -> post_update.ColdStartChoice:
        try:
            return Prompt.ask(
                "Do you want to start MacroQuest now?",
                choices=["yes", "no", "always", "never"],
                default="yes",
            )
        except (KeyboardInterrupt, EOFError):
            return "no"  # headless/no-stdin: don't start MacroQuest

    def auto_run_persisted(self, value: str) -> None:
        pass  # the policy notifies; nothing to sync in the CLI

    async def wait_for_eq_close(self) -> bool:
        while processes.get_eqgame_process_pids():
            try:
                Prompt.ask(
                "[yellow]EverQuest is still running.[/yellow] Close it, then press "
                "[bold]Enter[/bold] to restart MacroQuest, or [bold]Ctrl-C[/bold] to "
                "skip (update applies next MacroQuest launch)"
            )
            except (KeyboardInterrupt, EOFError):
                return False
        return True


async def handle_download_watched_async(db_path: str, headers: dict) -> bool:
    """Run the main 'update watched' flow using async network calls."""
    if await net.is_mq_down():
        console.print(
            "[bold yellow]Warning:[/bold yellow] [blink bold red]MQ appears to be down[/blink bold red] for a patch, so it's not likely to work."
        )

    outcome = await sync.run_sync(db_path, headers)
    # offer regardless of overall success:
    await post_update.offer(outcome, _CliPostUpdate())
    return outcome.success


async def update_command_async(db_name: str, db_path: str, force: bool) -> None:
    await asyncio.to_thread(utils.sweep_stale_update_debris)
    headers = await auth.get_api_headers()
    if not (await api.get_sync_info(headers)).is_level_2:
        console.print(
            "[bold yellow]Warning:[/bold yellow] You're not level 2 on RedGuides, so some resources will not be downloadable."
        )
    if force:
        with store.get_db_connection(db_name) as conn:
            cursor = conn.cursor()
            console.print(
                "Force download requested. All watched resources will be re-downloaded."
            )
            store.reset_download_dates(cursor)
    await handle_download_watched_async(db_path, headers)


async def download_command_async(db_name: str, db_path: str, id_or_url: str, force: bool) -> None:
    headers = await auth.get_api_headers()
    rid = parse_resource_id_or_fail(id_or_url)
    if force:
        with store.get_db_connection(db_name) as conn:
            cursor = conn.cursor()
            store.reset_versions_for_resource(
                cursor, rid, servers.active_server_slug(config.settings.ENV)
            )
    console.print(f"Downloading resource {rid}.")
    await sync.run_sync(db_path, headers, [rid])


@app.command(
    "update",
    help="Update all [italic]watched[/italic] and special resources.",
    rich_help_panel="📦 Resource Management"
)
def update_command(
    force: Annotated[bool, typer.Option("--force", "-f", help="Force re-download of all watched resources.")] = False,
    server: _Client = None,
    headless: Annotated[bool, typer.Option("--headless", hidden=True, help="MQ silent update: no prompts, no browser, no dialogs. writes update_status.json.")] = False,
):
    if headless:
        _headless_update(server=server, force=force)
        return
    db_name, db_path = initialize_db_only(server=server)
    asyncio.run(update_command_async(db_name=db_name, db_path=db_path, force=force))


@contextmanager
def _exit_silently_on_error():
    """Anything unexpected for headless commands becomes a silent exit 1."""
    try:
        yield
    except typer.Exit:
        raise
    except Exception:
        raise typer.Exit(1)


@dataclass(frozen=True, slots=True)
class _HeadlessSession:
    """What `check` and `update --headless` share once the env is settled."""
    env: str
    managed_path: str | None  # MQ matches this against its own root to ignore stray copies.
    auto_update: bool
    db_name: str
    db_path: str

    def write_status(self, **fields) -> None:
        update_status.write_update_status(
            env=self.env, managed_path=self.managed_path, auto_update=self.auto_update, **fields,
        )


def _headless_session(server: Env | None, *, require_auto_update: bool = False) -> _HeadlessSession:
    """Settle the env and open the DB. With no config or no login, write status and exit 0."""
    from redfetch.config_firstrun import is_configured

    requested_env = server.value if server else None
    if not is_configured():
        update_status.write_update_status(
            env=requested_env or config.DEFAULT_ENV, auth_state="not_configured",
        )
        raise typer.Exit(0)

    config.initialize_config()
    if requested_env:
        config.select_environment_in_memory(requested_env)
    env = config.settings.ENV
    auth.initialize_keyring()

    auto_update = utils.is_auto_update_enabled()
    if require_auto_update and not auto_update:
        raise typer.Exit(1)
    managed_path = utils.get_vvmq_path()
    if not auth.has_stored_credentials():
        update_status.write_update_status(
            env=env, auth_state="needs_login", managed_path=managed_path, auto_update=auto_update,
        )
        raise typer.Exit(0)

    db_name = store.db_name(env)
    store.initialize_db(db_name)
    return _HeadlessSession(env, managed_path, auto_update, db_name, store.get_db_path(db_name))


def _headless_update(server: Env | None, force: bool) -> None:
    with _exit_silently_on_error():
        session = _headless_session(server, require_auto_update=True)
        if force:
            with store.get_db_connection(session.db_name) as conn:
                store.reset_download_dates(conn.cursor())

        outcome = asyncio.run(_headless_update_async(session.db_path))

        if outcome is None:
            # Mid-run silent-refresh failure handling
            session.write_status(auth_state="needs_login")
            raise typer.Exit(0)

        if outcome.execution_plan is None or outcome.execution_result is None:
            raise typer.Exit(1)  # busy or cancelled: nothing ran, nothing fresh

        installed, remaining = update_status.split_items_by_outcome(
            outcome.execution_plan, outcome.execution_result
        )
        vvmq_version = None
        if outcome.vvmq_updated:
            vvmq_id = utils.get_current_vvmq_id(session.env)
            vvmq_version = next(
                (item["version"] for item in installed if item["resource_id"] == vvmq_id), None
            )
        session.write_status(
            auth_state="ok",
            items=remaining,
            installed=installed,
            pending_restart=outcome.vvmq_updated,
            pending_restart_version=vvmq_version,
        )

        # the swap starts only when this run has nothing left to do.
        meta.spawn_silent_self_update()
        raise typer.Exit(0)


async def _headless_update_async(db_path: str) -> SyncOutcome | None:
    """Returns the SyncOutcome or needs_login."""
    await asyncio.to_thread(utils.sweep_stale_update_debris)
    try:
        headers = await auth.get_api_headers()
    except RuntimeError:
        return None
    return await sync.run_sync(db_path, headers)


def parse_resource_id_or_fail(value: str) -> str:
    """Accept either an integer ID or a RedGuides URL that includes a recognizable ID."""
    with _usage_errors():
        return utils.parse_resource_id(value.strip())


@app.command(
    "download",
    help="Download a specific resource by ID or URL.",
    rich_help_panel="📦 Resource Management"
)
def download(
    id_or_url: Annotated[str, typer.Argument(metavar="ID_OR_URL", help="RedGuides resource ID or URL")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Force re-download by resetting this resource's download date.")] = False,
    server: _Client = None,
):
    db_name, db_path = initialize_db_only(server=server)
    asyncio.run(download_command_async(db_name=db_name, db_path=db_path, id_or_url=id_or_url, force=force))


@app.command(
    "check",
    help=(
        "Non-interactive update check (for automation.)"
    ),
    rich_help_panel="📦 Resource Management",
)
def check_command(server: _Client = None):
    with _exit_silently_on_error():
        session = _headless_session(server)
        auth_state, items = asyncio.run(_check_command_async(session.db_path))
        session.write_status(auth_state=auth_state, items=items)
        raise typer.Exit(0)


async def _check_command_async(db_path: str) -> tuple[str, list[dict] | None]:
    try:
        headers = await auth.get_api_headers()
    except RuntimeError:
        # Silent refresh failed / expired / logged out -> a gentle re-login nudge
        return "needs_login", None

    prepared = await sync.prepare_sync(db_path, headers)
    return "ok", update_status.build_items_from_plan(prepared.execution_plan)


@app.command(
    "ui",
    help="Launch the [italic]Terminal User Interface[/italic].",
    rich_help_panel="🔧 System & Utilities"
)
def run_tui():
    """Initialize configuration and launch the Terminal User Interface."""
    _initialize_auth()
    utils.sweep_stale_update_debris()
    from redfetch.tui import run_textual_ui
    run_textual_ui()


def _print_shortcut_table(entries, available, describe) -> None:
    """List shortcuts (key, aliases, availability) for the bare `run`/`open` verb."""
    from rich.table import Table
    from rich.text import Text

    # ASCII-only content for legacy Windows consoles
    table = Table(show_header=True, header_style="bold")
    table.add_column("shortcut")
    table.add_column("aliases", style="dim")
    table.add_column("available", justify="center")
    table.add_column("description", style="dim")
    for entry in entries:
        mark = "[green]yes[/green]" if available(entry) else "[dim]no[/dim]"
        table.add_row(entry.key, ", ".join(entry.aliases) or "-", mark, Text(describe(entry)))
    console.print(table)


@app.command(
    "run",
    help="Run a shortcut (e.g. [bold]vvmq[/bold], [bold]eqbcs[/bold], [bold]myseq[/bold]). [bold]run[/bold] by itself will show a full list.",
    rich_help_panel="🔧 System & Utilities",
)
def run_shortcut_command(
    target: Annotated[str | None, typer.Argument(metavar="SHORTCUT", help="Shortcut to run: vvmq, eqbcs, eq, eqgame, etc.")] = None,
    server: _Client = None,
):
    config.initialize_config()
    _apply_server_override(server)
    if target is None:
        _print_shortcut_table(shortcuts.RUNNABLES, shortcuts.runnable_available,
                              shortcuts.runnable_tooltip)
        return
    runnable = shortcuts.find_runnable(target)
    if runnable is None:
        valid = ", ".join(r.key for r in shortcuts.RUNNABLES)
        raise typer.BadParameter(f"Unknown shortcut '{target}'. Try: {valid}")
    if runnable.startup:
        try:
            result = runnable.startup()
        except (ValueError, TypeError, RuntimeError, OSError) as exc:
            console.print(f"[red]Couldn't run {runnable.key}:[/red] {exc}")
            raise typer.Exit(1)
        for message, is_error in result.messages:
            console.print(message, style="red" if is_error else None, markup=False)
        if not result.mq_up:
            raise typer.Exit(1)
        return
    try:
        shortcuts.run(runnable)
        console.print(f"Started [bold]{escape(shortcuts.runnable_executable(runnable))}[/bold].")
    except (ValueError, RuntimeError, OSError) as exc:
        console.print(f"[red]Couldn't run {runnable.key}:[/red] {exc}")
        raise typer.Exit(1)


@app.command(
    "open",
    help="Open a folder or file (e.g. [bold]downloads[/bold], [bold]mqini[/bold]). [bold]open[/bold] by itself will show a full list.",
    rich_help_panel="🔧 System & Utilities",
)
def open_shortcut_command(
    target: Annotated[str | None, typer.Argument(metavar="SHORTCUT", help="Folder/file to open: downloads, vvmq, eq, etc.")] = None,
    server: _Client = None,
):
    config.initialize_config()
    _apply_server_override(server)
    if target is None:
        _print_shortcut_table(shortcuts.OPENABLES, shortcuts.openable_available,
                              shortcuts.openable_tooltip)
        return
    openable = shortcuts.find_openable(target)
    if openable is None:
        valid = ", ".join(o.key for o in shortcuts.OPENABLES)
        raise typer.BadParameter(f"Unknown shortcut '{target}'. Try: {valid}")
    try:
        detail = shortcuts.open_target(openable)
        console.print(f"Opened [bold]{openable.key}[/bold]{(' ' + detail) if detail else ''}.")
    except (ValueError, OSError) as exc:
        console.print(f"[red]Couldn't open {openable.key}:[/red] {exc}")
        raise typer.Exit(1)


@app.command(
    "web",
    help="Launch the [bold]RedGuides.com[/bold] web interface.",
    rich_help_panel="🔧 System & Utilities"
)
def web_command():
    db_name, _db_path = initialize_db_only()
    try:
        asyncio.run(web_command_async(db_name=db_name))
    except KeyboardInterrupt:
        console.print("\nServer stopped by user (Ctrl+C).")


async def web_command_async(db_name: str) -> None:
    headers = await auth.get_api_headers()
    from .listener import run_server_async
    await run_server_async(db_name, headers, config.CATEGORY_MAP)


@app.command(
    "list",
    help="List resources and dependencies in your local cache.",
    rich_help_panel="📦 Resource Management"
)
def resources_list_command():
    db_name, _db_path = initialize_db_only()
    with store.get_db_connection(db_name) as conn:
        cursor = conn.cursor()
        resources = store.list_resources(cursor)
        console.print("Resources:")
        for resource_id, title in resources:
            console.print(f"ID: {resource_id}, Title: {title}")
        dependencies = store.list_dependencies(cursor)
        console.print("Dependencies:")
        for resource_id, title in dependencies:
            console.print(f"ID: {resource_id}, Title: {title}")


@app.command(
    "reset",
    help="Reset download dates for [italic]watched resources[/italic] in the database.",
    rich_help_panel="📦 Resource Management"
)
def resources_reset_command():
    db_name, _db_path = initialize_db_only()
    with store.get_db_connection(db_name) as conn:
        cursor = conn.cursor()
        store.reset_download_dates(cursor)
    console.print("Reset download dates for watched resources.")


@app.command(
    "config",
    help="Read or update a setting by path. Give no value to print the current one.",
    rich_help_panel="🍔 Configuration"
)
def config_command(
    path: Annotated[str, typer.Argument(metavar="SETTING_PATH", help="Dot-separated setting path (e.g., SPECIAL_RESOURCES.1974.opt_in)")],
    values: Annotated[list[str], typer.Argument(help="New value. List settings take multiple values (e.g. a.ini b.ini). Omit to print the current value.")] = [],
    add_entries: Annotated[list[str], typer.Option("--add", metavar="ENTRY", help="Append an entry to a list setting (e.g. a protected file).")] = [],
    remove_entries: Annotated[list[str], typer.Option("--remove", metavar="ENTRY", help="Remove an entry from a list setting.")] = [],
    server: Annotated[Env | None, _client_option("Client to apply the change in.")] = None,
):
    list_edits = bool(add_entries or remove_entries)

    config.initialize_config()
    setting_path = path.split('.')
    env = server.value if server else None

    # Three modes, same order as the help text: read, set, edit a list.
    if values and list_edits:
        raise typer.BadParameter("Use either VALUE arguments or --add/--remove, not both.")
    with _usage_errors():
        if not values and not list_edits:
            _print_setting(setting_path, env or config.settings.ENV)
            return
        if list_edits:
            new_value = config.apply_list_edits(setting_path, add_entries, remove_entries, env=env)
        else:
            new_value = config.coerce_setting_value(setting_path, values, env=env)

    config.update_setting(setting_path, new_value, env)
    console.print(f"Updated setting {path} to {new_value!r}{' for client ' + config.ENVS[env] if env else ''}.")


def _print_setting(setting_path: list[str], settings_env: str) -> None:
    """The read half of read-modify-write: the effective value, JSON for non-strings."""
    value = config.read_setting(setting_path, env=settings_env)
    if value is config.MISSING:
        console.print(
            f"[yellow]{'.'.join(setting_path)} is not set for "
            f"{config.ENVS[settings_env]}.[/yellow]"
        )
        raise typer.Exit(1)
    typer.echo(value if isinstance(value, str) else json.dumps(value))


def _switch_client(token: str) -> None:
    """Persist the client switch; its active server (if any) resumes untouched."""
    config.switch_environment(token)
    console.print(f"Client: {config.ENVS[token]}")
    if servers.is_multi_server(token):
        active = servers.get_active_server(token)
        label = servers.server_label(active, token) if active else config.BARE_SERVER_LABEL
        console.print(f"Server: {escape(label)}")


@app.command(
    "client",
    help=f"Switch the game client: {_client_choices()}.",
    rich_help_panel="🍔 Configuration"
)
def client_command(
    env: Annotated[Env, typer.Argument(metavar="CLIENT", case_sensitive=False, help=_client_choices())],
):
    config.initialize_config()
    _switch_client(env.value)


@app.command(
    "server",
    help="Switch the active emu server: a name like [cyan]lazarus[/cyan], [cyan]none[/cyan] to use any emu server, or [cyan]add[/cyan] to add a new server.",
    rich_help_panel="🍔 Configuration"
)
def server_command(
    server: Annotated[str, typer.Argument(metavar="SERVER", help="An emu server name (e.g. [cyan]lazarus[/cyan]), [cyan]none[/cyan] to use any emu server, or [cyan]add[/cyan] to add a new server")],
    slug: Annotated[str | None, typer.Argument(metavar="NAME", help="With [cyan]add[/cyan]: the new server's name (e.g. [cyan]myserver[/cyan])")] = None,
    eqpath: Annotated[Path | None, typer.Option("--eqpath", exists=True, file_okay=False, resolve_path=True, help="With [cyan]add[/cyan]: the server's EverQuest folder.")] = None,
    label: Annotated[str | None, typer.Option("--label", help="With [cyan]add[/cyan]: display name for a custom server.")] = None,
    patcher_url: Annotated[str | None, typer.Option("--patcher-url", help="With [cyan]add[/cyan]: download link for the server's patcher (zip or exe); needs --patcher-exe.")] = None,
    patcher_exe: Annotated[str | None, typer.Option("--patcher-exe", help="With [cyan]add[/cyan]: patcher file name, e.g. ThePatcher.exe (inside the zip, if any).")] = None,
    guide: Annotated[str | None, typer.Option("--guide", help="With [cyan]add[/cyan]: URL of the server's getting-started guide.")] = None,
    shortname: Annotated[str | None, typer.Option("--shortname", help="With [cyan]add[/cyan]: the server's short name as EverQuest knows it.")] = None,
):
    config.initialize_config()

    # Exit codes: 0 switched, 1 a guard blocked the switch, 2 bad input (typer usage error).
    value = server.strip()
    add_details = {"eqpath": eqpath, "label": label, "patcher_url": patcher_url,
                   "patcher_exe": patcher_exe, "guide": guide, "shortname": shortname}
    if value.lower() == "add":
        _server_add(slug, **add_details)
        return
    if slug is not None or any(add_details.values()):
        raise typer.BadParameter(
            "NAME and --eqpath/--label/--patcher-* only apply to 'redfetch server add'."
        )
    token = value.upper()
    if token in config.ENVS:
        # a client token still switches the client, no nag.
        _switch_client(token)
        return

    if value.lower() == servers.BARE_SETUP_TOKEN:
        current = config.settings.ENV
        if not servers.is_multi_server(current):
            raise typer.BadParameter(
                f"{config.ENVS[current]} doesn't have switchable servers — "
                "switch to an emu client first (e.g. 'redfetch client emu')."
            )
        if servers.get_active_server(current):
            try:
                notices = servers.switch_to_generic(current)
            except servers.ServerSwitchError as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(1)
            for notice in notices:
                console.print(f"[yellow]{escape(notice)}[/yellow]")
        console.print(f"Server: {config.BARE_SERVER_LABEL}")
        return

    with _usage_errors():
        slug = servers.validate_server_slug(value.lower())
        server_env = servers.env_for_slug(slug)

    if server_env is None:
        known = {s for e in config.MULTI_SERVER_ENVS for s in servers.list_servers(e)}
        valid = ", ".join([servers.BARE_SETUP_TOKEN, *sorted(known)])
        raise typer.BadParameter(
            f"Unknown server '{slug}'. Valid servers: {valid}. "
            f"To switch clients ({', '.join(config.ENVS)}), use 'redfetch client'."
        )

    if not servers.is_server_configured(slug, server_env):
        label = servers.server_label(slug, server_env)
        try:
            folder = Prompt.ask(f"EverQuest folder for [bold]{escape(label)}[/bold]").strip()
        except (KeyboardInterrupt, EOFError):
            # headless/no-stdin: can't configure interactively
            console.print(f"[red]'{slug}' isn't set up; it needs an EverQuest folder.[/red]")
            raise typer.Exit(1)
        _require_eq_folder(folder)
        with _usage_errors():
            servers.add_server(slug, env=server_env, eqpath=folder)
        console.print(f"Server '{slug}' added.")

    # never persist a server slug as REDFETCH_ENV.
    if config.settings.ENV != server_env:
        config.switch_environment(server_env)
        # The client changed too (durably) — say so, matching _switch_client.
        console.print(f"Client: {config.ENVS[server_env]}")

    try:
        notices = servers.switch_server(slug)
    except servers.ServerSwitchError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    for notice in notices:
        console.print(f"[yellow]{escape(notice)}[/yellow]")
    console.print(f"Server: {escape(servers.server_label(slug, server_env))}")


def _server_add(slug: str | None, *, eqpath: Path | None, label: str | None,
                patcher_url: str | None, patcher_exe: str | None,
                guide: str | None, shortname: str | None) -> None:
    """`redfetch server add <name> --eqpath <folder>`: the paste-an-info-block flow.
    add_server validates everything else (name, patcher pair, guide link)."""
    if not slug or eqpath is None:
        raise typer.BadParameter(
            "Usage: redfetch server add <name> --eqpath <EverQuest folder>"
        )
    _require_eq_folder(str(eqpath))
    slug = slug.strip().lower()
    with _usage_errors():
        # A known slug belongs to its bundled env; new customs go to the first (only) emu env.
        server_env = servers.env_for_slug(slug) or config.MULTI_SERVER_ENVS[0]
        servers.add_server(slug, env=server_env, eqpath=str(eqpath), label=label,
                           patcher_url=patcher_url, patcher_exe=patcher_exe,
                           guide=guide, shortname=shortname)
    console.print(f"Server '{slug}' added. Switch to it with: redfetch server {slug}")


@app.command(
    "provision",
    help="Create a server's EverQuest folder from a clean RoF2 copy, then set it up.",
    rich_help_panel="🍔 Configuration",
)
def provision_command(
    server: Annotated[str, typer.Argument(metavar="SERVER", help="An emu server name (e.g. [cyan]lazarus[/cyan])")],
    source: Annotated[str | None, typer.Option("--source", help="A clean RoF2 zip, iso, or folder.")] = None,
    destination: Annotated[str | None, typer.Option("--destination", help="Where to create the new EverQuest folder.")] = None,
):
    config.initialize_config()

    slug, server_env = _resolve_known_emu_server(server)
    if servers.is_server_configured(slug, server_env):
        console.print(
            f"[red]'{slug}' already has an EverQuest folder. Reset it on the "
            f"Servers tab to set it up again.[/red]"
        )
        raise typer.Exit(1)

    cli_source = (source or "").strip()
    remembered = provision.clean_source()
    chosen_source = cli_source or remembered
    if not chosen_source:
        console.print(f"[red]{provision.NO_SOURCE_MESSAGE}[/red]")
        console.print("Point redfetch at yours with --source.")
        raise typer.Exit(1)
    if cli_source and not remembered:
        try:
            provision.set_clean_source(cli_source)  # lazy write, so next time needs no flag
        except provision.ProvisionError as exc:
            console.print(f"[red]{escape(str(exc))}[/red]")
            raise typer.Exit(1)

    target = (destination or "").strip() or provision.default_destination(slug)
    console.print(f"Creating {escape(target)} from {escape(chosen_source)}")

    try:
        with (
            _sigint_cancellation() as stop,
            Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as bar,
        ):
            task = bar.add_task("Starting", total=1.0)

            def report(label, fraction):
                # Called from the copy thread.
                if fraction is None:
                    bar.update(task, description=escape(label))
                else:
                    bar.update(task, description=escape(label), completed=fraction)

            result = asyncio.run(provision.provision(
                slug, env=server_env, source=chosen_source, destination=target,
                progress=report, cancelled=stop.is_set,
            ))
    except provision.ProvisionCancelled as exc:
        console.print(f"[yellow]{escape(str(exc))}[/yellow]")
        raise typer.Exit(1)
    except provision.ProvisionError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(1)

    for notice in result.notices:
        console.print(f"[yellow]{escape(notice)}[/yellow]")
    console.print(f"Created {escape(str(result.destination))}")
    console.print(f"Server '{slug}' added. Switch to it with: redfetch server {slug}")


@contextmanager
def _sigint_cancellation():
    """A stop flag Ctrl+C sets; a second Ctrl+C gives up on stopping cleanly."""
    stop = threading.Event()
    previous_handler = signal.getsignal(signal.SIGINT)

    def on_interrupt(_signum, _frame):
        if stop.is_set():
            signal.signal(signal.SIGINT, previous_handler)
            raise KeyboardInterrupt
        stop.set()
        console.print("[yellow]Cancelling…[/yellow]")

    # Ctrl+C has to reach the copy loop, cancelling the await isn't enough
    signal.signal(signal.SIGINT, on_interrupt)
    try:
        yield stop
    finally:
        signal.signal(signal.SIGINT, previous_handler)


def _resolve_known_emu_server(server: str) -> tuple[str, str]:
    """A bundled emu slug and its env; custom servers arrive with the Add dialog."""
    with _usage_errors():
        slug = servers.validate_server_slug(server.strip().lower())
        server_env = servers.env_for_slug(slug)
    if server_env is None or not servers.is_known_server(slug, server_env):
        known = sorted(
            slug_
            for env in config.MULTI_SERVER_ENVS
            for slug_ in servers.list_servers(env)
            if servers.is_known_server(slug_, env)
        )
        raise typer.BadParameter(
            f"'{slug}' isn't a known emu server. Valid servers: {', '.join(known)}."
        )
    return slug, server_env


@app.command("show", hidden=True)
@app.command(
    "status",
    help="Show the configuration for the current or specified client.",
    rich_help_panel="🍔 Configuration"
)
def config_show_command(server: Annotated[Env | None, _client_option("Client to show (defaults to current)")] = None):
    from rich.panel import Panel

    config.initialize_config()
    current_env = server.value if server else getattr(config.settings, "ENV", "UNKNOWN")
    env_settings = config.settings.from_env(current_env)

    # Core paths for this environment
    download_folder = env_settings.get("DOWNLOAD_FOLDER") or ""
    eq_path = env_settings.get("EQPATH") or ""

    panel_lines: list[str] = []

    # Only show top-level paths that are actually set
    if download_folder:
        panel_lines.append(f"[bold yellow]DOWNLOAD_FOLDER:[/bold yellow] {download_folder}")
    if eq_path:
        panel_lines.append(f"[bold yellow]EQPATH:[/bold yellow] {eq_path}")

    # Opted-in special resources with resolved paths, keyed by resource ID
    special_resources = env_settings.get("SPECIAL_RESOURCES", {})

    for resource_id, resource_info in special_resources.items():
        # Only show if opted in
        if not resource_info.get("opt_in"):
            continue

        # Get the resolved path
        custom_path = resource_info.get("custom_path", "")
        default_path = resource_info.get("default_path", "")

        if custom_path:
            resource_path = custom_path
        elif default_path:
            # If default_path is absolute, use it as-is
            if download_folder and not os.path.isabs(default_path):
                resource_path = os.path.join(download_folder, default_path)
            else:
                resource_path = default_path
        else:
            continue

        # Label only by resource ID
        panel_lines.append(f"[bold yellow]Resource {resource_id}:[/bold yellow] {resource_path}")

    # If nothing to show, still render an empty-but-clear panel
    if not panel_lines:
        panel_lines.append("[dim]No paths are currently configured or opted in for this client.[/dim]")

    # Lead with both levels so users always know where they are.
    if servers.is_multi_server(current_env):
        active = servers.get_active_server(current_env)
        if active:
            label = servers.server_label(active, current_env)
            shown = label if label == active else f"{label} ({active})"
        else:
            shown = config.BARE_SERVER_LABEL
        panel_lines.insert(0, f"[bold yellow]Server:[/bold yellow] {escape(shown)}")
    panel_lines.insert(0, f"[bold yellow]Client:[/bold yellow] {config.ENVS[current_env]}")

    console.print(Panel("\n".join(panel_lines), expand=False))

    # Optional: Show full settings dict with a label
    console.print("\n[dim][italic]Full configuration (for debugging):[/italic][/dim]")
    typer.echo(env_settings.as_dict())


@app.command("push", hidden=True, rich_help_panel="📤 Publishing")
@app.command(
    "publish",
    help="Publish updates to a [bold]RedGuides[/bold] resource.",
    rich_help_panel="📤 Publishing"
)
def publish_command(
    ctx: typer.Context,
    resource_id: Annotated[int, typer.Argument(metavar="RESOURCE_ID", help="Existing RedGuides resource ID")],
    description: Annotated[Path | None, typer.Option("--description", "-d", metavar="README.md", help="Path to a description file (e.g. README.md) to become the overview description.", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True)] = None,
    version: Annotated[str | None, typer.Option("--version", "-v", help="New version string (e.g., v1.0.1)")] = None,
    message: Annotated[Path | None, typer.Option("--message", "-m", metavar="CHANGELOG.md | MESSAGE", help="Path to [italic]CHANGELOG.md[/italic] (keep a changelog), other message file, or a direct message string.", exists=False)] = None,
    file: Annotated[Path | None, typer.Option("--file", "-f", metavar="FILE.zip", help="Path to your zipped release file", exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True)] = None,
    domain: Annotated[str | None, typer.Option("--domain", help="If description or message is a .md file with relative URLs, resolve them to this domain (e.g., https://raw.githubusercontent.com/your/repo/main/)")] = None,
):
    if ctx.info_name == "push":
        console.print("[yellow]Warning:[/yellow] 'push' is deprecated. Use 'redfetch publish' instead.")
    push.handle_cli(
        resource_id,
        description=description,
        version=version,
        message=message,
        file=file,
        domain=domain,
    )


def load_agent_docs() -> str:
    """Included notes for clankers."""
    from importlib.resources import files
    return files("redfetch").joinpath("agent_docs.md").read_text(encoding="utf-8")


@app.command(
    "agent",
    help="Print setup and configuration slop for llm agents.",
    rich_help_panel="🔧 System & Utilities"
)
def agent_command():
    typer.echo(load_agent_docs())


@app.command(
    "version",
    help="Show version and exit.",
    rich_help_panel="🔧 System & Utilities"
)
def version_command():
    console.print(f"redfetch {meta.get_current_version()}")


@app.command(
    "uninstall",
    help="Uninstall [bold]redfetch[/bold] and clean up data.",
    rich_help_panel="🔧 System & Utilities"
)
def uninstall_command():
    meta.uninstall()


@app.command(
    "logout",
    help="Log out and clear cached token and API cache.",
    rich_help_panel="🔧 System & Utilities"
)
def auth_logout():
    config.initialize_config()
    api_key = os.environ.get('REDGUIDES_API_KEY')
    if not api_key:
        auth.initialize_keyring()
        auth.logout()
        console.print("Logged out successfully.")
    else:
        console.print("Cannot logout when using API key from environment variable.")


# ============================================================================
# LEGACY/DEPRECATED COMMAND ALIASES
# ============================================================================


def legacy_callback_factory(new_command: str, invoke_func=None, **invoke_kwargs):
    """Factory to create deprecation callbacks that forward to new commands."""
    def callback(ctx: typer.Context, value):
        if ctx.resilient_parsing or not value:
            return value
        console.print(f"[bold yellow blink]Warning:[/bold yellow blink] This flag is deprecated! Use 'redfetch {new_command}' instead.")
        if invoke_func:
            ctx.invoke(invoke_func, **invoke_kwargs)
        raise typer.Exit()
    return callback


def legacy_switch_env_callback(ctx: typer.Context, value: Env | None):
    """Deprecated --switch-env handler that forwards to the 'client' subcommand."""
    if ctx.resilient_parsing or value is None:
        return value
    console.print("[yellow]Warning:[/yellow] --switch-env is deprecated. Use 'redfetch client' instead.")
    ctx.invoke(client_command, env=value)
    raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    # Legacy: --switch-env ENV
    switch_env: Annotated[Env | None, typer.Option(
        "--switch-env", is_eager=True, case_sensitive=False, hidden=True,
        callback=legacy_switch_env_callback,
        metavar="CLIENT", help="(Deprecated) Use 'client' subcommand instead.",
    )] = None,
    # Legacy: --download-watched
    download_watched: Annotated[bool, typer.Option(
        "--download-watched", is_eager=True, hidden=True,
        callback=legacy_callback_factory("update", update_command),
        help="(Deprecated) Use 'update' subcommand instead.",
    )] = False,
    # Legacy: --force-download
    force_download: Annotated[bool, typer.Option(
        "--force-download", is_eager=True, hidden=True,
        callback=legacy_callback_factory("update --force", update_command, force=True),
        help="(Deprecated) Use 'update --force' instead.",
    )] = False,
    # Legacy: --serve
    serve: Annotated[bool, typer.Option(
        "--serve", is_eager=True, hidden=True,
        callback=legacy_callback_factory("web", web_command),
        help="(Deprecated) Use 'web' subcommand instead.",
    )] = False,
    # Legacy: --version
    show_version: Annotated[bool, typer.Option(
        "--version", is_eager=True, hidden=True,
        callback=legacy_callback_factory("version", version_command),
        help="(Deprecated) Use 'version' subcommand instead.",
    )] = False,
    # Legacy: --logout
    do_logout: Annotated[bool, typer.Option(
        "--logout", is_eager=True, hidden=True,
        callback=legacy_callback_factory("logout", auth_logout),
        help="(Deprecated) Use 'logout' subcommand instead.",
    )] = False,
    # Legacy: --uninstall
    do_uninstall: Annotated[bool, typer.Option(
        "--uninstall", is_eager=True, hidden=True,
        callback=legacy_callback_factory("uninstall", uninstall_command),
        help="(Deprecated) Use 'uninstall' subcommand instead.",
    )] = False,
):
    """redfetch - RedGuides resource management tool."""
    pass


# ============================================================================
# END LEGACY/DEPRECATED COMMANDS
# ============================================================================


# ===== Entry point =====

def _reconfigure_console_streams() -> None:
    """Piped output on Win crashes from help-panel emoji. Drop once Python 3.15 (UTF-8 default) is the floor."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding=None if stream.isatty() else "utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def main():
    try:
        _reconfigure_console_streams()
        utils.ensure_cooked_console()
        # Launch TUI when no arguments are provided
        if len(sys.argv) == 1:
            run_tui()
            return
        # `redfetch help` → show top-level help 
        if len(sys.argv) == 2 and sys.argv[1] == "help":
            sys.argv[1] = "--help"
        app()
    except typer.Exit:
        raise
    except Exception as exc:
        exit_with_fatal_error(exc)


if __name__ == "__main__":
    main()
