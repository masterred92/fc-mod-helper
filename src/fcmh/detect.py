"""Auto-detection for the first-run wizard.

Everything goes through a `Probe`, so tests can swap in fake drives, a fake
registry and fake environment variables and run on any OS.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fcmh.paths import GAMES

MOD_MANAGER_EXES = ("fifa mod manager.exe", "fifamodmanager.exe")
MAX_SEARCH_DEPTH = 4


class Probe:
    """Real system access. Subclass or replace pieces for tests."""

    def env(self, name: str) -> str | None:
        return os.environ.get(name) or None

    def drives(self) -> list[Path]:
        if sys.platform != "win32":
            return []
        import string
        return [Path(f"{letter}:\\") for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]

    def registry_values(self) -> list[tuple[str, str, str]]:
        """(key path, value name, value) for keys that can hold a game or Steam location."""
        if sys.platform != "win32":
            return []
        import winreg

        found: list[tuple[str, str, str]] = []
        roots = [(winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")]

        def read_key(hive, path, label, names):
            try:
                with winreg.OpenKey(hive, path) as key:
                    for name in names:
                        try:
                            value, _ = winreg.QueryValueEx(key, name)
                            found.append((f"{label}\\{path}", name, str(value)))
                        except OSError:
                            pass
            except OSError:
                pass

        for hive, label in roots:
            for game in GAMES.values():
                for base in ("SOFTWARE\\EA Sports", "SOFTWARE\\WOW6432Node\\EA Sports"):
                    read_key(hive, f"{base}\\{game['title']}", label, ("Install Dir", "InstallDir"))
            read_key(hive, "SOFTWARE\\Valve\\Steam", label, ("SteamPath", "InstallPath"))
            read_key(hive, "SOFTWARE\\WOW6432Node\\Valve\\Steam", label, ("InstallPath",))
            for base in ("SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
                         "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"):
                try:
                    with winreg.OpenKey(hive, base) as key:
                        index = 0
                        while True:
                            try:
                                sub = winreg.EnumKey(key, index)
                            except OSError:
                                break
                            index += 1
                            try:
                                with winreg.OpenKey(key, sub) as subkey:
                                    name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                    if "EA SPORTS FC" in str(name).upper():
                                        location, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                                        found.append((f"{label}\\{base}\\{sub}", str(name), str(location)))
                            except OSError:
                                pass
                except OSError:
                    pass
        return found


@dataclass
class GameInstall:
    game: str
    path: Path
    source: str


@dataclass
class Detection:
    games: list[GameInstall] = field(default_factory=list)
    mod_manager_exe: Path | None = None
    live_editor_dir: Path | None = None
    settings_dir: Path | None = None
    temp_dir: Path | None = None


def _program_roots(probe: Probe) -> list[Path]:
    roots = []
    for name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        value = probe.env(name)
        if value:
            roots.append(Path(value))
    roots += probe.drives()
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def _user_folders(probe: Probe) -> list[Path]:
    profile = probe.env("USERPROFILE")
    if not profile:
        return []
    base = Path(profile)
    return [base / "Downloads", base / "Desktop", base / "Documents", base / "OneDrive" / "Desktop",
            base / "OneDrive" / "Documents"]


def is_game_dir(game: str, path: Path) -> bool:
    try:
        return (path / GAMES[game]["exe"]).is_file()
    except OSError:
        return False


def steam_libraries(probe: Probe) -> list[Path]:
    libraries: list[Path] = []
    steam_roots = [Path(v) for _k, n, v in probe.registry_values() if n in ("SteamPath", "InstallPath") and v]
    steam_roots += [root / "Steam" for root in _program_roots(probe)]
    for root in steam_roots:
        if root not in libraries:
            libraries.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            lib = Path(match.group(1).replace("\\\\", "\\"))
            if lib not in libraries:
                libraries.append(lib)
    for drive in probe.drives():
        libraries.append(drive / "SteamLibrary")
    return libraries


def epic_installs(probe: Probe) -> list[tuple[str, Path]]:
    program_data = probe.env("ProgramData")
    if not program_data:
        return []
    manifests = Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    found = []
    try:
        items = sorted(manifests.glob("*.item"))
    except OSError:
        return []
    for item in items:
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name, location = str(data.get("DisplayName", "")), data.get("InstallLocation")
        if location:
            found.append((name, Path(location)))
    return found


def find_games(probe: Probe) -> list[GameInstall]:
    candidates: list[tuple[str, Path, str]] = []
    registry = probe.registry_values()
    for game, info in GAMES.items():
        title = info["title"]
        for key, name, value in registry:
            if title.upper() in key.upper() or title.upper() in name.upper():
                if name not in ("SteamPath", "InstallPath") or title.upper() in key.upper():
                    candidates.append((game, Path(value), "registry"))
        for root in _program_roots(probe):
            candidates.append((game, root / "EA Games" / title, "EA app"))
            candidates.append((game, root / "Epic Games" / title.replace(" ", ""), "Epic"))
            candidates.append((game, root / "Epic Games" / title, "Epic"))
        for lib in steam_libraries(probe):
            candidates.append((game, lib / "steamapps" / "common" / title, "Steam"))
        for name, location in epic_installs(probe):
            if title.upper() in name.upper() or title.replace(" ", "").upper() in name.upper().replace(" ", ""):
                candidates.append((game, location, "Epic"))

    results: list[GameInstall] = []
    seen: set[str] = set()
    for game, path, source in candidates:
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        if is_game_dir(game, path):
            seen.add(key)
            results.append(GameInstall(game, path, source))
    # newest game first
    results.sort(key=lambda g: g.game, reverse=True)
    return results


def _walk_limited(root: Path, depth: int):
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for entry in entries:
        yield entry
        if depth > 0:
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            if is_dir and not entry.name.startswith((".", "$")) and entry.name.lower() not in ("windows", "node_modules"):
                yield from _walk_limited(Path(entry.path), depth - 1)


def find_mod_manager(probe: Probe) -> Path | None:
    roots = [(r, MAX_SEARCH_DEPTH) for r in _user_folders(probe)]
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        value = probe.env(name)
        if value:
            roots.append((Path(value), 2))
    hits: list[Path] = []
    for root, depth in roots:
        for entry in _walk_limited(root, depth):
            if entry.name.lower() in MOD_MANAGER_EXES:
                try:
                    if entry.is_file():
                        hits.append(Path(entry.path))
                except OSError:
                    pass
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime)


def is_live_editor_dir(path: Path, game: str | None = None) -> bool:
    name = path.name.lower()
    if "live editor" not in name and "liveeditor" not in name:
        return False
    if game and GAMES[game]["number"] not in name:
        return False
    return (path / "lua").is_dir()


def find_live_editor(probe: Probe, game: str) -> Path | None:
    number = GAMES[game]["number"]
    candidates = [drive / f"FC {number} Live Editor" for drive in probe.drives()]
    for path in candidates:
        if is_live_editor_dir(path, game):
            return path
    for root in _user_folders(probe):
        for entry in _walk_limited(root, 2):
            path = Path(entry.path)
            try:
                if entry.is_dir() and is_live_editor_dir(path, game):
                    return path
            except OSError:
                continue
    return None


def find_settings_dir(probe: Probe, game: str) -> Path | None:
    title, number = GAMES[game]["title"], GAMES[game]["number"]
    options = []
    lad = probe.env("LOCALAPPDATA")
    if lad:
        options.append(Path(lad) / title / "settings")
    profile = probe.env("USERPROFILE")
    if profile:
        options.append(Path(profile) / "Documents" / f"FC {number}" / "settings")
    for option in options:
        if option.is_dir():
            return option
    return None


def find_temp_dir(probe: Probe, game: str) -> Path | None:
    number = GAMES[game]["number"]
    lad = probe.env("LOCALAPPDATA")
    if not lad:
        return None
    return Path(lad) / "Temp" / f"EA SPORTS FC{number}"


def detect_all(probe: Probe | None = None, game: str | None = None) -> Detection:
    probe = probe or Probe()
    result = Detection()
    result.games = find_games(probe)
    chosen = game or (result.games[0].game if result.games else "fc26")
    result.mod_manager_exe = find_mod_manager(probe)
    result.live_editor_dir = find_live_editor(probe, chosen)
    result.settings_dir = find_settings_dir(probe, chosen)
    result.temp_dir = find_temp_dir(probe, chosen)
    return result
