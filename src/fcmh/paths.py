"""Default Windows locations and how to override them.

Every path here is a *default* taken from community sources (see docs/paths.md).
Any of them can be overridden in the ledger's "paths" section, because installs differ.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

GAMES = {
    "fc26": {
        "title": "EA SPORTS FC 26",
        "number": "26",
        "exe": "FC26.exe",
    },
    "fc27": {
        "title": "EA SPORTS FC 27",
        "number": "27",
        "exe": "FC27.exe",
    },
}

PATH_KEYS = (
    "settings_dir",      # Career saves, squads, profile settings
    "fifamoddata_dir",   # Mod Manager's generated output inside the game folder
    "temp_dir",          # Game temp/shader cache folder cleared after a patch
    "fmm_dir",           # FIFA Mod Manager folder (profiles, config). No safe default: set it.
    "fmm_exe",           # Optional: FIFA Mod Manager executable, for `fcmh launch`
    "editor_cache_file", # Optional: FIFA Editor Tool modding cache, cleared after a patch
    "backup_dir",        # Where fcmh writes backup zips
    "academy_dir",       # Where the Lua academy exporter writes CSVs
    "mods_dir",          # Folder the app watches for new/updated mod files
    "live_editor_dir",   # Live Editor folder (the app copies the academy script into its lua folder)
)


def _env(name: str, fallback: str) -> str:
    value = os.environ.get(name)
    return value if value else fallback


def local_appdata() -> Path:
    return Path(_env("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))


def user_profile() -> Path:
    return Path(_env("USERPROFILE", str(Path.home())))


def default_install_path(game: str) -> Path:
    return Path(r"C:\Program Files\EA Games") / GAMES[game]["title"]


def default_paths(game: str, install_path: str | os.PathLike | None) -> dict[str, Path | None]:
    if game not in GAMES:
        raise ValueError(f"Unknown game {game!r}; expected one of {', '.join(GAMES)}")
    info = GAMES[game]
    lad = local_appdata()
    install = Path(install_path) if install_path else default_install_path(game)
    return {
        "settings_dir": lad / info["title"] / "settings",
        "fifamoddata_dir": install / "FIFAModData",
        "temp_dir": lad / "Temp" / f"EA SPORTS FC{info['number']}",
        "fmm_dir": None,
        "fmm_exe": None,
        "editor_cache_file": lad / "FIFA Editor Tool" / "Caches" / f"fc{info['number']}-modding.cache",
        "backup_dir": lad / "fc-mod-helper" / "backups",
        "academy_dir": user_profile() / "Desktop",
        "mods_dir": user_profile() / "Documents" / "FC Mod Helper" / "Mods",
        "live_editor_dir": None,
    }


@dataclass
class ResolvedPaths:
    values: dict[str, Path | None]

    def get(self, key: str) -> Path | None:
        return self.values.get(key)

    def require(self, key: str) -> Path:
        value = self.values.get(key)
        if value is None:
            raise KeyError(
                f"Path '{key}' is not set. Add it to the ledger with: fcmh paths --set {key} <folder>"
            )
        return value


def resolve_paths(game: str, install_path: str | None, overrides: dict | None) -> ResolvedPaths:
    values = default_paths(game, install_path)
    for key, value in (overrides or {}).items():
        if key not in PATH_KEYS:
            continue
        values[key] = Path(os.path.expandvars(str(value))) if value else None
    return ResolvedPaths(values)
