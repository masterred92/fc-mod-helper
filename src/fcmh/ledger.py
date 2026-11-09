"""The user-maintained JSON ledger: game, install path, current build and pinned mods.

fcmh treats mod files as opaque blobs. It records a path, a sha256 and the Title
Update (TU) the user says the mod was built for. It never reads mod internals.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fcmh.paths import GAMES, PATH_KEYS, ResolvedPaths, resolve_paths

SCHEMA = 1
LEDGER_ENV = "FCMH_LEDGER"


class LedgerError(Exception):
    pass


def default_ledger_path() -> Path:
    env = os.environ.get(LEDGER_ENV)
    if env:
        return Path(env)
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "fc-mod-helper" / "ledger.json"
    return Path.home() / ".config" / "fc-mod-helper" / "ledger.json"


_TU_RE = re.compile(r"^v?(\d+(?:\.\d+){1,3})$", re.IGNORECASE)


def normalize_tu(value: str | None) -> str | None:
    """'v1.6.6' -> '1.6.6'. Returns None for empty input; raises on garbage."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _TU_RE.match(text)
    if not match:
        raise LedgerError(f"'{value}' doesn't look like a Title Update such as 1.6.6")
    return match.group(1)


def sha256_file(path: str | os.PathLike, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


@dataclass
class Mod:
    name: str
    file: str
    pinned_tu: str
    author_url: str = ""
    sha256: str = ""
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Mod":
        if "name" not in data or "file" not in data:
            raise LedgerError(f"Mod entry needs at least 'name' and 'file': {data!r}")
        return cls(
            name=str(data["name"]),
            file=str(data["file"]),
            pinned_tu=normalize_tu(data.get("pinned_tu")) or "",
            author_url=str(data.get("author_url", "")),
            sha256=str(data.get("sha256", "")).lower(),
            enabled=bool(data.get("enabled", True)),
            tags=[str(t) for t in data.get("tags", [])],
            notes=str(data.get("notes", "")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Ledger:
    game: str = "fc26"
    install_path: str = ""
    current_build: str = ""
    exe_version: str = ""
    paths: dict = field(default_factory=dict)
    mods: list[Mod] = field(default_factory=list)
    location: Path | None = None

    # ---- loading / saving -------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict, location: Path | None = None) -> "Ledger":
        game = str(data.get("game", "fc26")).lower()
        if game not in GAMES:
            raise LedgerError(f"Unknown game '{game}'. Use one of: {', '.join(GAMES)}")
        paths = data.get("paths") or {}
        unknown = sorted(set(paths) - set(PATH_KEYS))
        if unknown:
            raise LedgerError(f"Unknown path keys in ledger: {', '.join(unknown)}")
        mods = [Mod.from_dict(m) for m in data.get("mods", [])]
        names = [m.name.lower() for m in mods]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise LedgerError(f"Duplicate mod names in ledger: {', '.join(dupes)}")
        return cls(
            game=game,
            install_path=str(data.get("install_path", "")),
            current_build=normalize_tu(data.get("current_build")) or "",
            exe_version=str(data.get("exe_version", "")),
            paths=dict(paths),
            mods=mods,
            location=location,
        )

    @classmethod
    def load(cls, path: str | os.PathLike) -> "Ledger":
        location = Path(path)
        if not location.exists():
            raise LedgerError(
                f"No ledger at {location}. Create one with: fcmh init --game fc26 --install \"<game folder>\""
            )
        try:
            data = json.loads(location.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LedgerError(f"Ledger {location} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LedgerError(f"Ledger {location} must contain a JSON object")
        return cls.from_dict(data, location)

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "game": self.game,
            "install_path": self.install_path,
            "current_build": self.current_build,
            "exe_version": self.exe_version,
            "paths": self.paths,
            "mods": [m.to_dict() for m in self.mods],
        }

    def save(self, path: str | os.PathLike | None = None) -> Path:
        target = Path(path) if path else self.location
        if target is None:
            raise LedgerError("No ledger path to save to")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        fd, tmp = tempfile.mkstemp(prefix=".ledger-", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, target)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        self.location = target
        return target

    # ---- helpers ----------------------------------------------------------
    def resolved_paths(self) -> ResolvedPaths:
        return resolve_paths(self.game, self.install_path or None, self.paths)

    def find_mod(self, name: str) -> Mod:
        for mod in self.mods:
            if mod.name.lower() == name.lower():
                return mod
        raise LedgerError(f"No mod named '{name}' in the ledger")

    def add_mod(self, mod: Mod) -> None:
        if any(m.name.lower() == mod.name.lower() for m in self.mods):
            raise LedgerError(f"A mod named '{mod.name}' is already in the ledger")
        self.mods.append(mod)

    def remove_mod(self, name: str) -> Mod:
        mod = self.find_mod(name)
        self.mods.remove(mod)
        return mod

    def mod_path(self, mod: Mod) -> Path:
        path = Path(os.path.expandvars(mod.file))
        if not path.is_absolute() and self.location is not None:
            path = self.location.parent / path
        return path
