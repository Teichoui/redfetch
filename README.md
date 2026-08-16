![six wizards levitating a package, the word redfetch underneath](https://www.redguides.com/images/redfetchlogo.png)

redfetch is for updating software and scripts for EverQuest that RedGuides recommends, as well as those you "[watch](https://www.redguides.com/community/watched/resources)". It's also open source, how nice.

## Installation

On Windows the easiest way to install redfetch is to [download](https://www.redguides.com/community/resources/redfetch.3177/download) and run [`redfetch.exe`](https://www.redguides.com/community/resources/redfetch.3177/download). (*optional: If you're still on Windows 10 and want a more modern appearance, follow [this guide](https://www.redguides.com/community/threads/redfetch.92998/post-634938) to set [Windows Terminal](https://www.redguides.com/community/threads/redfetch.92998/post-634938) as your default terminal.*)

<details>
<summary>Terminal / Python / Linux</summary>


Make sure you have a recent version of [Python](https://www.python.org/downloads/)

1) **Install pipx**
```bash
python -m pip install --user pipx
```

2) **Make it so you can run packages without having to type "python -m"**
```bash
python -m pipx ensurepath
```

3) **Install redfetch**
```bash
pipx install redfetch
```

When you open a new terminal window you'll be able to run redfetch by typing `redfetch` from the command line. 

</details>

## Usage


### 1) Double-click [`redfetch.exe`](https://www.redguides.com/community/resources/redfetch.3177/download) to run the script. 
Take a moment to consider your configuration and the settings tab.

### 2) Click the big blue "Easy Update" button, and then "Yes" or "Always" on the popup. 
![a screenshot showing the easy update button](https://www.redguides.com/images/redfetchupdate.gif)  
(It's updating *Very Vanilla MQ* and any of its scripts or plugins you have [watched on RedGuides](https://www.redguides.com/community/watched/resources), your licensed resources, and scripts recommended by staff. You can customize this if you like.)

Now you're ready to play EQ with the big boys.

## Add more MQ Scripts
To add more MacroQuest scripts, "watch" them on [www.redguides.com/community/resources](https://www.redguides.com/community/resources), and then click the *Easy Update* button again.

![a screenshot showing the watch button on a resource page](https://www.redguides.com/images/clickwatch.gif)

If there are non-MQ resources you'd like to keep in sync with redfetch, you can add them as a "special resource" in the local settings file, as shown in settings section.

## Command Line
To run redfetch from the command line:

| .exe file | python |
|---------|-----------|
| `.\redfetch.exe update` | `redfetch update` |

![a screenshot showing the command line interface](https://www.redguides.com/images/redfetchcliupdate.gif)

## Command Line Reference

<!-- to update: hatch run dev:check-docs -->
<!-- BEGIN GENERATED CLI REFERENCE -->
> Run `redfetch --help` for the current list, or `redfetch <COMMAND> --help` for a command's options. It looks like:
>
> ### 📦 Resource Management
> - `update` - Update all *watched* and special resources.
>   - `--force` / `-f` - Force re-download of all watched resources.
>   - `--client` / `--server` / `-s` - Update this client for this run only, without changing your active client (LIVE, TEST, EMU).
> - `download <ID_OR_URL>` - Download a specific resource by ID or URL.
>   - `ID_OR_URL` - RedGuides resource ID or URL
>   - `--force` / `-f` - Force re-download by resetting this resource's download date.
>   - `--client` / `--server` / `-s` - Download for this client for this run only, without changing your active client (LIVE, TEST, EMU).
> - `check` - Non-interactive update check (for automation.)
>   - `--client` / `--server` / `-s` - Check this client for this run only, without changing your active client (LIVE, TEST, EMU).
> - `list` - List resources and dependencies in your local cache.
> - `reset` - Reset download dates for *watched resources* in the database.
>
> ### 🔧 System & Utilities
> - `ui` - Launch the *Terminal User Interface*.
> - `run [SHORTCUT]` - Run a shortcut (e.g. **vvmq**, **eqbcs**, **myseq**). **run** by itself will show a full list.
>   - `SHORTCUT` - Shortcut to run: vvmq, eqbcs, eq, eqgame, etc.
>   - `--client` / `--server` / `-s` - Run for this client this run only, without changing your active client (LIVE, TEST, EMU).
> - `open [SHORTCUT]` - Open a folder or file (e.g. **downloads**, **mqini**). **open** by itself will show a full list.
>   - `SHORTCUT` - Folder/file to open: downloads, vvmq, eq, etc.
>   - `--client` / `--server` / `-s` - Resolve paths for this client this run only, without changing your active client (LIVE, TEST, EMU).
> - `web` - Launch the **RedGuides.com** web interface.
> - `version` - Show version and exit.
> - `uninstall` - Uninstall **redfetch** and clean up data.
> - `logout` - Log out and clear cached token and API cache.
>
> ### 🍔 Configuration
> - `config <SETTING_PATH> <VALUE>` - Update a setting by path and value.
>   - `SETTING_PATH` - Dot-separated setting path (e.g., SPECIAL_RESOURCES.1974.opt_in)
>   - `VALUE` - New value for the setting
>   - `--client` / `--server` / `-s` - Client to apply the change in (LIVE, TEST, EMU)
> - `client <CLIENT>` - Switch the game client: LIVE, TEST, or EMU (RoF2).
>   - `CLIENT` - LIVE, TEST, or EMU
> - `server <SERVER>` - Switch the active emu server: a name like lazarus, or none to use any emu server.
>   - `SERVER` - An emu server name (e.g. lazarus), or none to use any emu server
> - `provision <SERVER>` - Create a server's EverQuest folder from a clean RoF2 copy, then set it up.
>   - `SERVER` - An emu server name (e.g. lazarus)
>   - `--source` - A clean RoF2 zip, iso, or folder.
>   - `--destination` - Where to create the new EverQuest folder.
> - `status` - Show the configuration for the current or specified client.
>   - `--client` / `--server` / `-s` - Client to show (defaults to current)
>
> ### 📤 Publishing
> - `publish <RESOURCE_ID>` - Publish updates to a **RedGuides** resource.
>   - `RESOURCE_ID` - Existing RedGuides resource ID
>   - `--description <README.md>` / `-d` - Path to a description file (e.g. README.md) to become the overview description.
>   - `--version` / `-v` - New version string (e.g., v1.0.1)
>   - `--message <CHANGELOG.md | MESSAGE>` / `-m` - Path to *CHANGELOG.md* (keep a changelog), other message file, or a direct message string.
>   - `--file <FILE.zip>` / `-f` - Path to your zipped release file
>   - `--domain` - If description or message is a .md file with relative URLs, resolve them to this domain (e.g., https://raw.githubusercontent.com/your/repo/main/)
<!-- END GENERATED CLI REFERENCE -->

The `publish` command also has a [GitHub Action](https://github.com/marketplace/actions/redguides-publish).

## Settings

`settings.local.toml` is found in your configuration directory, which by default is `c:\Users\Public\redfetch\settings.local.toml`. Any keys you add will override their default values in [`settings.toml`](./src/redfetch/settings.toml).

All settings are prefixed with the environment,

- `[DEFAULT]` - encompasses all clients that are not explicitly defined.
- `[LIVE]` - EverQuest Live
- `[TEST]` - EverQuest Test
- `[EMU]` - EQEmulator (see [Emu servers](#emu-servers))

### General settings reference

These can all be managed from the settings tab in the TUI, or directly in `settings.local.toml`:

```toml
[DEFAULT]                  # These settings will be used on all clients, unless overriden.
DOWNLOAD_FOLDER = 'D:\dl'  # where resources land unless they have a path of their own

[LIVE]                     # These settings are only in effect for the Live client
EQPATH = 'C:\EverQuest'    # the live client's EverQuest folder
THEME = "dracula"          # interface theme, ctrl+t to cycle
AUTO_UPDATE = true         # silent update when MacroQuest launches
AUTO_RUN_VVMQ = true       # start MQ after updates; false = never, unset = ask
NAVMESH_DOWNLOADS = true   # pre-made meshes for the Nav plugin

[EMU]
ACTIVE_SERVER = "lazarus"  # your active server slug name
```

### Adding a special resource
To add a "special resource" (a non-MQ resource that you want to keep updated), open `settings.local.toml` and add an entry. You'll need the [resource ID (numbers at the end of the url)](https://www.redguides.com/community/resources/brewalls-everquest-maps.153/) and a target directory. Example:

```toml
[LIVE.SPECIAL_RESOURCES.153]
custom_path = 'C:\Users\Public\Daybreak Game Company\Installed Games\EverQuest\maps\Brewall_Maps'
opt_in = true
```
* Note the use of single quotes around the path, which are required for windows paths.

The above will install Brewall's maps to the EQ maps directory the next time `redfetch update` is run for the `LIVE` client.

Key reference for special resources:

```toml
[LIVE.SPECIAL_RESOURCES.151] # for resource 151 (MySEQ) when on the live client
opt_in = true                # whether redfetch updates this resource
custom_path = 'C:\MySEQ'     # exact install folder, overrides all defaults

[LIVE.SPECIAL_RESOURCES.151.dependencies.153]  # installs inside the parent resource
subfolder = "maps"           # relative to the parent's folder
flatten = true               # discard the zip's own folder structure
opt_in = true
```

### Emu servers

redfetch can track more than one emulator server, each with its own EverQuest folder and maps choice. 

You can also switch from the command line:

```powershell
redfetch client emu
redfetch server lazarus
redfetch server none    # back to "Any emu server"
```

To add a server redfetch doesn't know about, use the Servers tab, or hand-add an entry to `settings.local.toml`:

```toml
[EMU.SERVERS.myserver]
label = "My Server"
opt_in = true
eqpath = 'D:\Games\EQ-MyServer'
```

### Opt out of a staff pick, watched, or default resource
You can opt out of any resource, including a staff pick. To opt out of downloading KissAssist (resource id 4) across all clients, 

```toml
[DEFAULT.SPECIAL_RESOURCES.4]
opt_in = false
``` 
This will stop all updates even if you watch or have a license for the resource. In the very rare case where it's a dependency for a parent resource, you can opt out under the dependency's category.

#### Self compiling or alternate source MacroQuest
If you self-compile MacroQuest or use a discord friend's copy, you can still keep your scripts and plugins in sync with redfetch by opting out of Very Vanilla. You can edit the `settings.local.toml` as shown above, or do it quickly via CLI,

```powershell
redfetch.exe config SPECIAL_RESOURCES.1974.opt_in false --client LIVE
redfetch.exe config SPECIAL_RESOURCES.60.opt_in false --client EMU
redfetch.exe config SPECIAL_RESOURCES.2218.opt_in false --client TEST
```

Then assign the *Very Vanilla MQ* path to your self-compiled MacroQuest.

### Overwrite protection

If there are specific files within a resource you don't want overwritten, you can add them to the `PROTECTED_FILES_BY_RESOURCE` setting. Include the resource ID and files you want to protect. e.g.,

```toml
[LIVE.PROTECTED_FILES_BY_RESOURCE]
1974 = ["CharSelect.cfg", "Zoned.cfg", "MQ2Map.ini", "MQ2MoveUtils.ini"]
153 = ["citymist.txt", "innothule.txt", "oasis.txt"]
navmesh = ["befallen.navmesh", "innothuleb.navmesh"]
```

### Custom category directories

If you share `lua`, `macros`, or `plugins` directories across multiple MQ environments, you can override where an entire category is installed. Add a `CATEGORY_PATHS` section to your `settings.local.toml`:

```toml
[DEFAULT.CATEGORY_PATHS]
lua = 'D:\\shared\\lua'
macros = 'D:\\shared\\macros'
```

Absolute paths are used as-is. Relative paths are joined to `DOWNLOAD_FOLDER`. You can set this globally in `[DEFAULT]` or per-environment (`[LIVE.CATEGORY_PATHS]`, `[TEST.CATEGORY_PATHS]`, etc.).

### Custom post-update launch

redfetch can launch extra programs after an update completes. Aside from the normal UI toggles, you can add `custom` to `POST_UPDATE_LAUNCH.targets` in `settings.local.toml`, then set `command` to whatever redfetch should run:

```toml
[LIVE.POST_UPDATE_LAUNCH]
targets = ["custom"]
command = ['C:\Tools\AfterRedfetch\after-update.exe', '--server', 'LIVE']
```

You can also combine it with the built-in targets, `eqbcs` and `myseq`. For example, to start EQBCS and MySEQ and run your own Python script:

```toml
[LIVE.POST_UPDATE_LAUNCH]
targets = ["myseq", "custom", "eqbcs"]
command = ["C:\\Users\\Public\\Python\\python.exe", "C:\\Users\\Public\\redfetch\\after_update.py"]
```

You can set these per-client, e.g. `[TEST.POST_UPDATE_LAUNCH]`, or global `[DEFAULT.POST_UPDATE_LAUNCH]`.

![Watchers on RedGuides](https://www.redguides.com/community/resources/redfetch.3177/watchers-sparkline?months=12&w=500&h=180)

## Contributing

I'd love help, conceptually and technically. I'm not a developer and this is my first big python script. 

> [!NOTE]
> This project is built with LLM assistance. (derogatory)

To set up a [development environment](https://hatch.pypa.io/latest/environment/),

```bash
git clone https://github.com/RedGuides/redfetch
cd redfetch
pip install hatch
hatch env create dev
hatch shell dev
```
You can then run your dev version with,

`redfetch`

Or if the issue is ui-specific, run the [terminal UI in debug mode](https://textual.textualize.io/guide/devtools/#live-editing),

`textual run --dev .\src\redfetch\main.py`

When you're done, type `exit` to leave the shell.

---

*Not affiliated with or endorsed by EverQuest or its owners.*
