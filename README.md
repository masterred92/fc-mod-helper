# fc-mod-helper (`fcmh`)

A small open-source helper for **EA SPORTS FC 26 / FC 27 on PC (EA app)** players who mod
**offline Career Mode**, especially the **youth academy**. It does three things:

1. **Patch-safety**: keeps a ledger of your mods and the game Title Update (TU) each one was built
   for, warns you before launch when the game has updated, and walks you through the post-patch
   clean-up. It also checks for mods that are known to clash.
2. **Backups**: one-command, timestamped zip snapshots of your Career saves, your FIFA Mod Manager
   folder and (optionally) FIFAModData, with restore that always backs up the current state first.
3. **Academy tracker**: a Live Editor Lua script that exports your young players to CSV, and a
   command that merges those CSVs into a growth report (CSV, Markdown and HTML).

It's a Python 3.11+ command-line tool (`fcmh`) with no required third-party packages, plus a
very small optional Tkinter window (`fcmh gui`).

---

## ⚠️ Read this first: risk warning

- **EA's rules don't allow mods.** Using mods or Live Editor is **at your own risk**.
- Use mods **only in offline Career Mode** (and other offline modes).
- **Never** go into Ultimate Team, Clubs, Rush, Seasons or any online mode with mods, FIFAModData
  or Live Editor active. Run `fcmh online-checklist` for the steps to get back to vanilla.
- Back up your saves before changing anything (`fcmh backup create`).
- This project is not affiliated with or endorsed by EA, the FIFA Editor Tool / FIFA Mod Manager
  team, Live Editor's author, or any mod author.

## What it deliberately does **not** do

- It does **not** host, bundle, download or redistribute any mods, EA game files or assets, or
  Live Editor. You get mods from their authors' pages and Live Editor from its official source.
- It does **not** read, parse or write `.fifamod` files. Mod files are treated as opaque: fcmh only
  records the path, a SHA-256 checksum and the TU you tell it.
- It does **not** touch the game executable, inject anything, or bypass anything.
- It never deletes anything without asking (every delete has a confirmation and a `--dry-run`),
  and it refuses to delete folders that don't look like FIFAModData or the FC temp folder.
- The online checklist only prints steps; it changes nothing.

---

## Install (Windows)

1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/windows/)
   (tick "Add python.exe to PATH"; the python.org installer includes Tkinter for the GUI).
2. Download this repo (Code → Download ZIP, or `git clone`), open a terminal in the folder and run:

   ```powershell
   py -m pip install .
   fcmh --help
   ```

   No other packages are needed. (For development: `py -m pip install -e ".[dev]"` then `py -m pytest`.)

## Quick start: a beginner academy setup (FC 26)

The base tools come from their own authors:
[FIFA Mod Manager](https://fifaeditortool.com/download) (v2.1.1+ for FC 26, v2.2.0+ for FC 27) and,
optionally, [Live Editor](https://github.com/xAranaktu/FC-26-Live-Editor) (official Patreon only).
Put the EA app in **Offline** mode and launch through Mod Manager.

A simple academy-focused starting set (pick **one** academy mod; they clash):

| Purpose | Mod | Note |
|---|---|---|
| Academy (pick one) | [Youth Academy Redux](https://www.nexusmods.com/easportsfc26/mods/92) **or** [Youth Academy Re-adjusted](https://www.nexusmods.com/easportsfc26/mods/1508) **or** the youth part of [KIARIKA Career Mode Overhaul](https://www.nexusmods.com/easportsfc26/mods/77) | `fcmh conflicts` flags two together |
| Development | [Complete Player Development](https://www.nexusmods.com/easportsfc26/mods/119) | |
| Regen faces | [Better Regen Minifaces](https://www.nexusmods.com/easportsfc26/mods/49) | |
| Performance | [KIARIKA Optimization Overhaul](https://www.nexusmods.com/easportsfc26/mods/79) | |

Then:

```powershell
# 1. Create your ledger and record the current game build
fcmh init --game fc26 --install "C:\Program Files\EA Games\EA SPORTS FC 26"
fcmh detect --save            # or: fcmh set-build 1.6.6
fcmh paths --set fmm_dir "D:\Modding\FIFA Mod Manager"   # the folder Mod Manager runs from
fcmh paths                    # check every folder; fix any that say (not found)

# 2. Record each mod you downloaded, with the TU from its mod page
fcmh mod add --name "Youth Academy Redux" --file "D:\Modding\mods\YouthAcademyRedux.fifamod" `
  --tu 1.6.6 --url "https://www.nexusmods.com/easportsfc26/mods/92" --tag academy-overhaul

# 3. Back up, then check before every session
fcmh backup create --label first-setup
fcmh check                    # exit code 2 means "don't launch with this mod set"
fcmh launch                   # same check, then starts Mod Manager if fmm_exe is set

# 4. When the game updates
fcmh post-patch --dry-run     # see what it would do
fcmh post-patch               # clears FIFAModData + temp (asks first), opens mod pages
fcmh rescan                   # after you download updated mods: spots new files, re-pins them

# 5. Academy tracking (in game, with Live Editor): run lua/fcmh_academy_export.lua each season
fcmh academy report           # merges the CSVs on your Desktop into a growth report
```

`fcmh gui` opens a small window with buttons for the read-only and dry-run actions.

## Commands

| Command | What it does |
|---|---|
| `fcmh init` | Create the ledger (default `%APPDATA%\fc-mod-helper\ledger.json`, or `--ledger` / `FCMH_LEDGER`) |
| `fcmh show`, `fcmh paths` | Show the ledger and every folder fcmh uses (`--set KEY PATH` / `--unset KEY`) |
| `fcmh detect [--save]` | Read the game exe's file version and map it to a TU |
| `fcmh set-build <TU>` | Enter the TU by hand (fallback when detection can't work) |
| `fcmh mod add/list/pin/enable/disable/remove` | Maintain the mod list |
| `fcmh check` | Pre-launch check: build vs pinned TUs, missing/changed files, clashes |
| `fcmh conflicts [--rules FILE]` | Clash check only |
| `fcmh launch [--force]` | Check, then start Mod Manager (`fmm_exe` path) |
| `fcmh post-patch [--dry-run] [--yes] [--no-open] [--tu X] [--include-editor-cache]` | Post-patch wizard |
| `fcmh rescan [--dry-run] [--yes]` | Re-hash mod files, re-pin updated ones |
| `fcmh backup create/list/verify/restore` | Zip backups with a manifest; restore takes a safety backup first |
| `fcmh academy report [--input DIR] [--out DIR]` | Growth report from the Lua CSVs |
| `fcmh online-checklist` | Steps to play online vanilla (prints only) |
| `fcmh gui` | Simple Tkinter window |

## How each part works

### Patch-safety

- **Ledger** (`examples/ledger.example.json` shows the format, with fake data): game (`fc26`/`fc27`),
  install path, current build (TU), exe version, folder overrides, and per mod: name, author page,
  local file path, sha256, pinned TU, enabled flag and tags.
- **Build detection**: reads the file version of `FC26.exe` / `FC27.exe` through the Windows version
  API (via `ctypes`, falling back to PowerShell) and maps it to a TU with `src/fcmh/data/tu_builds.json`.
  The FC 26 table comes from the public compatibility list in the Live Editor repository. If the
  version isn't in the table (new patch, or FC 27), fcmh tells you and you enter it with
  `fcmh set-build`. Detection also notices when the exe version changes even if the TU is unknown.
- **Post-patch wizard**: (1) records the new TU, (2) deletes `FIFAModData` and the FC temp folder after
  a confirmation each (optionally the FIFA Editor Tool `fcXX-modding.cache` file), (3) lists and opens
  the pages of mods pinned to an older TU, (4) re-hashes your mod files to spot updated downloads and
  offers to re-pin them. Your Career saves are never touched.
- **Conflict rules**: `src/fcmh/data/known-clashes.json` is a small, editable rules file. Each rule
  has members matched by regex against the mod name, file name or `tag:<tag>`, and a `max_enabled`.
  The bundled rules cover the three academy overhauls (KIARIKA's youth section, Youth Academy Redux,
  Youth Academy Re-adjusted) and gameplay overhauls (Anth James, TrueFoot). Copy it and use
  `--rules my-rules.json` to add your own.

### Backups

Components: `saves` (`%LOCALAPPDATA%\EA SPORTS FC 26\settings`), `fmm` (your Mod Manager folder) and
`moddata` (FIFAModData, large, off by default). `fcmh backup create` writes
`fcmh-backup-YYYYMMDD-HHMMSS[-label].zip` with a `manifest.json` listing every file and its sha256.
`restore` verifies the zip, takes a `pre-restore` backup of what's there now, then replaces the
folder. Close the game, the EA app and Mod Manager first. See [docs/paths.md](docs/paths.md) for the
default locations and how to change them.

> EA app cloud saves can overwrite a restored save. If that happens, choose the local copy when the
> EA app asks, or turn cloud saves off while you restore.

### Academy tracker

See [docs/academy-tracker.md](docs/academy-tracker.md). In short: `lua/fcmh_academy_export.lua`
(run from Live Editor's Lua Engine) writes `fcmh_academy_YYYY-MM-DD.csv` with age, OVR, POT,
position and PlayStyles counts for your young players. `fcmh academy report` merges every export into
`academy-growth.csv/.md/.html`, sorted by OVR growth, with one OVR column per season.

**The Lua script is untested in-game.** It uses only the functions the official Live Editor example
scripts use, is read-only, and is tested here against a mock of the API. Please try it on a spare
save first and report problems.

## Status and what needs checking in-game

| Item | Status |
|---|---|
| Python CLI, backups, report | Unit-tested on Windows and Linux in CI |
| Exe version detection | Uses the standard Windows version API; needs a real install to confirm |
| Default folders | From community guides; confirm with `fcmh paths` (see docs/paths.md) |
| Lua exporter | **Untested in-game**; field names follow the official examples |
| FC 27 | Same design; TU table and default paths are guesses until confirmed |

## Contributing

Issues and pull requests are welcome. Please never attach save files, mod files, game files or
anything personal. Run `python -m pytest` before opening a PR.

## License

[MIT](LICENSE). Copyright (c) 2026 fc-mod-helper contributors.
