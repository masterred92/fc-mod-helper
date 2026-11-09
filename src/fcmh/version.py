"""Detect the installed game build from the executable's file version (Windows only).

Order of attempts:
1. Win32 version resources via ctypes (version.dll) - no extra packages.
2. PowerShell: (Get-Item <exe>).VersionInfo.FileVersion
3. Give up and ask the user to type the TU with `fcmh set-build 1.6.6`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import resources
from pathlib import Path

from fcmh.paths import GAMES


def load_tu_table() -> dict[str, dict[str, str]]:
    text = resources.files("fcmh.data").joinpath("tu_builds.json").read_text(encoding="utf-8")
    data = json.loads(text)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def exe_path(game: str, install_path: str | Path) -> Path:
    return Path(install_path) / GAMES[game]["exe"]


def _version_via_ctypes(path: Path) -> str | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    version = ctypes.WinDLL("version")
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    pointer = ctypes.c_void_p()
    length = wintypes.UINT()
    if not version.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        return None

    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [(name, wintypes.DWORD) for name in (
            "dwSignature", "dwStrucVersion", "dwFileVersionMS", "dwFileVersionLS",
            "dwProductVersionMS", "dwProductVersionLS", "dwFileFlagsMask", "dwFileFlags",
            "dwFileOS", "dwFileType", "dwFileSubtype", "dwFileDateMS", "dwFileDateLS")]

    info = ctypes.cast(pointer, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    ms, ls = info.dwFileVersionMS, info.dwFileVersionLS
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def _version_via_powershell(path: Path) -> str | None:
    if sys.platform != "win32":
        return None
    literal = str(path).replace("'", "''")
    command = f"(Get-Item -LiteralPath '{literal}').VersionInfo.FileVersion"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value.replace(", ", ".").replace(",", ".") or None


def read_exe_version(path: Path) -> str | None:
    if not path.exists():
        return None
    for reader in (_version_via_ctypes, _version_via_powershell):
        try:
            value = reader(path)
        except Exception:  # noqa: BLE001 - any failure just means "try the next way"
            value = None
        if value:
            return value
    return None


def tu_for_exe_version(game: str, exe_version: str | None, table: dict | None = None) -> str | None:
    if not exe_version:
        return None
    table = table if table is not None else load_tu_table()
    return table.get(game, {}).get(exe_version.strip())


def detect(game: str, install_path: str | Path) -> dict:
    """Returns {'exe': path, 'exe_version': str|None, 'tu': str|None, 'message': str}."""
    exe = exe_path(game, install_path)
    if not exe.exists():
        return {"exe": str(exe), "exe_version": None, "tu": None,
                "message": f"Game executable not found at {exe}. Check install_path, or enter the TU by hand: fcmh set-build 1.6.6"}
    exe_version = read_exe_version(exe)
    if not exe_version:
        return {"exe": str(exe), "exe_version": None, "tu": None,
                "message": "Couldn't read the executable's version on this system. Enter the TU by hand: fcmh set-build 1.6.6"}
    tu = tu_for_exe_version(game, exe_version)
    if tu:
        message = f"{exe.name} file version {exe_version} = Title Update {tu}"
    else:
        message = (f"{exe.name} file version {exe_version} isn't in the built-in TU table. "
                   "Check the patch notes and enter it by hand: fcmh set-build <TU>")
    return {"exe": str(exe), "exe_version": exe_version, "tu": tu, "message": message}
