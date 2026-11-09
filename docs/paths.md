# Default folders (and how to change them)

The app's first-run screen finds these for you and lets you pick any it can't find
(**More > Run setup again** to redo it). It stores its own files in `Documents\FC Mod Helper`
(`Mods`, `Backups`, `Academy`).

How the app looks for things:

- **Game:** the EA Sports registry keys, Windows "installed apps" entries, `Program Files\EA Games`,
  Steam libraries (from Steam's registry entry and `libraryfolders.vdf`), Epic manifests and
  `Epic Games` folders. A folder counts only if it contains `FC26.exe` / `FC27.exe`.
- **FIFA Mod Manager:** searches Downloads, Desktop, Documents (4 folders deep) and Program Files
  (2 deep) for `FIFA Mod Manager.exe`, newest first.
- **Live Editor:** `X:\FC 26 Live Editor` on each drive, or a folder named like "FC 26 Live Editor"
  with a `lua` folder inside, in Downloads/Desktop/Documents.

Every folder fcmh uses can be overridden in the ledger with `fcmh paths --set KEY PATH`.
Run `fcmh paths` to see what fcmh is using and whether each folder exists.

| Key | Default (FC 26) | Used for | Confidence |
|---|---|---|---|
| `settings_dir` | `%LOCALAPPDATA%\EA SPORTS FC 26\settings` | Career saves (files starting `Cm…`), squads, profile settings. Backed up as `saves`. | Several current guides and EA forum posts agree. Some older guides say `Documents\FC 26\settings`; if your saves are there, set it. |
| `fifamoddata_dir` | `<install_path>\FIFAModData` | Mod Manager's generated output. Deleted by `post-patch`, optional `moddata` backup. | Matches Mod Manager logs and tutorials (`-dataPath FIFAModData`). |
| `temp_dir` | `%LOCALAPPDATA%\Temp\EA SPORTS FC26` | Game temp/cache folder cleared after a patch. | Community advice; **please confirm the exact folder name** on your PC. fcmh only deletes it if the folder is inside a `Temp` folder and its name starts with `EA SPORTS FC`. |
| `editor_cache_file` | `%LOCALAPPDATA%\FIFA Editor Tool\Caches\fc26-modding.cache` | Only deleted with `post-patch --include-editor-cache`. | From community troubleshooting posts. |
| `fmm_dir` | *(not set)* | FIFA Mod Manager's folder (its profiles and config live next to the program). Backed up as `fmm`. | FIFA Mod Manager is portable, so set this to wherever you unzipped it. |
| `fmm_exe` | *(not set)* | Started by `fcmh launch`. | Set to the Mod Manager `.exe`. |
| `backup_dir` | `%LOCALAPPDATA%\fc-mod-helper\backups` | Where backup zips go. | Your choice; another drive is safer. |
| `academy_dir` | `%USERPROFILE%\Desktop` (app: `Documents\FC Mod Helper\Academy`) | Where academy CSVs are read from. | The app points the Lua script here. |
| `mods_dir` | `Documents\FC Mod Helper\Mods` | Folder the app watches for new and updated mod files. | Your choice. |
| `live_editor_dir` | *(found by the app)* | Live Editor folder; the academy script goes in its `lua` folder. | Unverified folder layout. |

The default install path is `C:\Program Files\EA Games\EA SPORTS FC 26` (EA app default) and the
executable is `FC26.exe`. If you installed elsewhere, pass `--install` to `fcmh init`.

FC 27 uses the same patterns with `27` (for example `%LOCALAPPDATA%\EA SPORTS FC 27\settings` and
`FC27.exe`). These are **unconfirmed** until FC 27 installs are checked; override them if needed.

Values in the ledger may use environment variables, e.g. `%LOCALAPPDATA%\...` (expanded on Windows).
