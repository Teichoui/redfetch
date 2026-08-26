# redfetch notes for AI agents, by AI agents.

redfetch installs and updates EverQuest resources (Very Vanilla MacroQuest,
scripts, plugins, maps) from RedGuides. If you're a clanker, you're probably 
here to diagnose an update problem, add an emu server, or change a setting 
the UI doesn't surface. redfetch is an open source python script, so you can
reference the source code from pypi or github.

## Ground rules

- If the user has a redfetch TUI that might be open, say so and stop: it 
  rewrites the settings file on save and will clobber your edits.

## Understanding the manifest.

Users will mention resource *names*; but settings are keyed by resource *id*. 
Look ids up in the public manifest (no auth, one request, every resource):

    https://www.redguides.com/community/resources-manifest

Resources are nested under the top-level `resources` key, keyed by id, each
carrying a `title`. Example: `resources["4"].title` is "KissAssist".

Each resource's `parent_category_id` says what it is: **8** macros (`.mac`
files, run with `/mac <name>`), **11** plugins (C++ DLLs, loaded with
`/plugin <name> load`), **25** lua scripts (`.lua` files, run with
`/lua run <name>`), and **2** other software such as MacroQuest, maps,
MySEQ. Categories 8, 11, and 25 install to the matching subfolder of
the MQ folder; 2 uses `SPECIAL_RESOURCES`. Most new scripts are Lua.

One name can be several ids — Very Vanilla MQ is a different id per client
(see "What syncs and why").

## Where config lives

- The file is `settings.local.toml` in the user's chosen config directory. To
  find it, read the `first_run_complete` file in the platformdirs config dir —
  its contents are the chosen config dir's path (often
  `C:\Users\Public\redfetch`; don't assume). platformdirs config dir:
  - Windows: `%LOCALAPPDATA%\RedGuides\redfetch`
  - Linux: `~/.config/redfetch`
  - macOS: `~/Library/Application Support/redfetch`
- The `REDFETCH_CONFIG_DIR` environment variable is NOT an override.
- Sections are per-client: `[LIVE]`, `[TEST]`, `[EMU]`, plus `[DEFAULT]` for
  all clients and `[EMU.SERVERS.<slug>]` per emu server. `[DEFAULT]` is
  hand-edit only — `redfetch config` writes per-client sections
  (`--client` rejects DEFAULT).
- redfetch regenerates the file on every save, keeping only deltas from the
  shipped defaults (comments are dropped, default-equal values removed) —
  close redfetch before hand-editing, and prefer `redfetch config` (below),
  which handles types and regeneration for you.

## Reading and writing settings

    redfetch config <PATH>                       # print the current value
    redfetch config <PATH> <VALUE>...            # set it
    redfetch config <PATH> --add X --remove Y    # edit a list setting
    redfetch config <PATH> <VALUE> --client EMU  # target a specific client

`<PATH>` is dot-separated and never includes the client section — pick the
client with `--client LIVE|TEST|EMU` (default: the user's active client).
Reading an unset path prints `<PATH> is not set for <client>` and exits 1 —
that means "no value", not a broken command.

`<VALUE>` is typed by its TOML spelling (`true` → bool, `["a.ini"]` → list,
anything that isn't valid TOML stays a string) and checked against the
setting's current value: bool settings only accept `true`/`false`, and a bare
entry given to a list setting becomes a one-element list. Quote a value
(`'"42"'`) to force a literal string.

## The three per-resource knobs

Get these right; they are commonly confused.

1. **Protect specific files inside a resource** — the resource keeps updating,
   the named files are never overwritten:

       redfetch config PROTECTED_FILES_BY_RESOURCE.1974 --add MyFile.ini

   The value is a list of filenames. Setting it outright takes multiple
   values (`redfetch config PROTECTED_FILES_BY_RESOURCE.1974 CharSelect.cfg
   Zoned.cfg`). Never write the list as one quoted string of filenames.

2. **Stop downloading a resource altogether** — works for any id, including
   staff picks and watched/licensed resources:

       redfetch config SPECIAL_RESOURCES.4.opt_in false

3. **Install a special resource somewhere else**:

       redfetch config SPECIAL_RESOURCES.151.custom_path "D:/wherever"
       redfetch config SPECIAL_RESOURCES.151.opt_in true

   Only ids with a `SPECIAL_RESOURCES` entry have this knob; dependencies
   follow their parent. 151 is MySEQ's client-specific offsets for LIVE
   (164 for TEST); the MySEQ program itself (1865) installs as a dependency
   of it and follows its path. 151 ships `opt_in = false`, so users who
   relocate may want that flipped to true.

"Don't update X" is ambiguous between 1 and 2 — if the user named a file in the zip
they want to protect (1); a whole resource, opting out (2). Confirm when unsure.

## Other settings the UI doesn't surface

- Run your own program after updates (`targets` is a list; the built-ins
  `eqbcs` and `myseq` can join it):

      redfetch config POST_UPDATE_LAUNCH.targets --add custom
      redfetch config POST_UPDATE_LAUNCH.command "C:/Tools/after-update.exe --flag"

- Install a whole category (`lua`, `macros`, `plugins`) to a shared folder;
  absolute paths are used as-is, relative paths join to `DOWNLOAD_FOLDER`:

      redfetch config CATEGORY_PATHS.lua D:/shared/lua

## What syncs and why

`redfetch update` covers: watched resources, licensed resources, and special
resources with `opt_in = true` (staff picks ship that way). A
`SPECIAL_RESOURCES.<id>` entry with `opt_in = false` blocks the resource even
if watched or licensed. Very Vanilla MQ is a different id per client — 1974
(LIVE), 2218 (TEST), 60 (EMU). MySEQ's `SPECIAL_RESOURCES` entries are its
client-specific offset resources — 151 (LIVE), 164 (TEST) — and each ships
MySEQ itself (1865) as a dependency. Configure 151/164 (with `--client`),
never 1865 directly.

## Diagnosis toolkit

- `redfetch status` — active client/server plus resolved paths; add
  `--client EMU` for another client. Only opted-in special resources are
  listed — an `opt_in = false` resource (e.g. MySEQ's 151) won't appear.
- `redfetch list` — the local cache: downloaded resources with ids and titles.
- `redfetch check` — non-interactive update check; prints nothing. Writes
  `update_status.json` into the platformdirs config dir (above): `auth_state`
  (`ok` | `needs_login` | `not_configured`) plus pending updates in
  `updates.items`, populated only when `auth_state` is `ok`.
- Blocked resources: `redfetch update` and `redfetch download` print the
  reason per resource in their plan summary — e.g. "Requires Level 2
  membership", "You don't hold a license", "category is not mapped to an
  install location".
- Auth is fixed in a browser, never by you: on `needs_login` or
  `not_configured`, have the user run `redfetch` interactively. Level 2 and
  licenses are bought at redguides.com — nothing to fix locally.
- `redfetch client LIVE|TEST|EMU` — switch the active client persistently
  (`--client` on other commands is per-run).
- Clear the cache (usual fix for stale/stuck updates): `redfetch update
  --force` clears and re-downloads everything (ask first); `redfetch reset`
  only clears, active client only (no `--client`). The cache is the download
  record, not the files. `logout` clears tokens, not this.
- `redfetch download <id|url>` — download one resource.
- `redfetch open <shortcut>` / `redfetch run <shortcut>` — open folders/files
  or launch programs; bare `redfetch open` or `redfetch run` lists shortcuts.
- `redfetch version` — installed version.

There are no log files. Errors print to the terminal (stderr) — rerun the
failing command and read its output. A crashing `redfetch.exe` also shows the
traceback in a Windows dialog.

## Adding an emu server

When the user pastes emu server info, translate it to:

    redfetch server add <name> --eqpath <EverQuest folder>
        [--label "Display Name"] [--patcher-url <zip url>] [--patcher-exe <exe>]
        [--guide <getting-started url>] [--shortname <name EQ uses>]

The folder must contain `eqgame.exe`. `--patcher-url` needs `--patcher-exe` (the
name the download is saved as, or picked out of the zip); `--patcher-exe` alone is
fine for a patcher the user already has. Switch to it with `redfetch server <name>`.

Per-server settings are just the EverQuest folder plus the two map packs —
Brewall's (153) and Good's (303), each `opt_in`/`custom_path`; everything
else in the EMU client is shared across servers. Maps install under that
server's EQ folder (`<eqpath>/maps`); a server with no EQ folder gets its
maps turned off. Plugins don't install on TEST or EMU.

## Provisioning a server's EverQuest folder

Emu servers run the 2013 "Rain of Fear 2" (RoF2) client, so each server a user plays
on needs its own untouched copy. If the user doesn't have a folder for the server
yet, redfetch can create one from their clean RoF2 copy (details below):

    redfetch provision <server> [--source <zip|iso|folder>] [--destination <folder>]

It copies the source into the new folder, downloads the server's patcher into
it (if the server has one), turns on eqgame.exe's 4GB allowance, and registers
the server. Switch to it afterwards with `redfetch server <server>`. For a custom 
server, add the server first.

Before running it:

- **Ask first.** It copies several GB and the user should know it takes awhile.
- The default destination is `<EMU DOWNLOAD_FOLDER>/EverQuest_<server>`. It
  must be absent or empty, and can't sit inside the source (or vice versa).

### The user's local clean RoF2 copy

`--source` is optional once redfetch has remembered one, so check first:

    redfetch config CLEAN_SOURCE --client EMU

If that prints a path, use it. Otherwise ask the user, most know where they
put their own archive. It can be a `.zip`, an `.iso`, optical drive or a folder that 
itself contains `eqgame.exe` which hasn't been used for another server.

Remember that a modern copy of EverQuest will not work with RoF2 servers, 
it must be the old RoF2 client.

The first `--source` you pass is remembered as `CLEAN_SOURCE` for next time.
A later `--source` is used for that run only. To replace the remembered one,
`redfetch config CLEAN_SOURCE <path> --client EMU`.

## MacroQuest usage

In-game, MacroQuest is driven by chat commands. The basics:

    /mac kissassist         run a macro (.mac file); /endmacro stops it
    /lua run rgmercs        run a lua script (.lua file); /lua stop <name>
    /lua gui                open the Lua window to pick scripts, see output
    /plugin mq2melee        load a plugin DLL; /plugin <name> unload

Users may ask about usage as often as installation, and will confuse scripts with
MacroQuest itself.

## More information

Docs, repos, membership, setup guides, and support channels are indexed here,
<https://www.redguides.com/llms.txt>.

