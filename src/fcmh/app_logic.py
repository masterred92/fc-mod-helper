"""Plain-language logic behind every button in the app.

Nothing in here imports Tkinter, so it is all unit-tested. The window (app.py)
only shows what these functions return and asks the Yes/No questions they need.
Words used on purpose: "game update" (not TU), "mods" (not .fifamod).
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Callable

from fcmh import academy, backup, checks, conflicts, detect, patch
from fcmh import version as version_mod
from fcmh.ledger import Ledger, Mod, default_ledger_path, sha256_file
from fcmh.paths import GAMES
from fcmh.ui import UI

MOD_EXTENSIONS = (".fifamod", ".fbmod")
BACKUP_MAX_AGE = dt.timedelta(hours=24)
GREEN, YELLOW, RED = "green", "yellow", "red"
Confirm = Callable[[str, str], bool]  # (title, question) -> yes?

RISK_WARNING = (
    "Mods are not allowed by EA's rules, so you use them at your own risk.\n\n"
    "Only use mods in offline Career Mode. Never play Ultimate Team, Clubs, Rush, Seasons "
    "or anything online while mods or Live Editor are on.\n\n"
    "This app never downloads or shares mods or game files. It keeps backups of your "
    "Career saves and only replaces them when you press Restore."
)

ONLINE_STEPS = [
    "Save, quit Career Mode and close the game.",
    "Close Mod Manager and Live Editor.",
    "In the EA app: FC > Manage > Properties, remove \"-dataPath FIFAModData\".",
    "Switch the EA app back to Online.",
    "Start the game from the EA app, not from Mod Manager.",
]


def app_home() -> Path:
    profile = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(profile) / "Documents" / "FC Mod Helper"


def friendly_update(tu: str | None) -> str:
    return f"game update {tu}" if tu else "an unknown game update"


# ------------------------------------------------------------------ setup
@dataclass
class SetupItem:
    key: str
    label: str
    value: Path | str | None
    ok: bool
    optional: bool = False
    note: str = ""


def setup_items(found: detect.Detection, version_info: dict | None) -> list[SetupItem]:
    game = found.games[0] if found.games else None
    items = [
        SetupItem("game", "Your FC game", game.path if game else None, game is not None,
                  note=f"{GAMES[game.game]['title']} ({game.source})" if game else "Please pick your game folder"),
    ]
    tu = (version_info or {}).get("tu")
    exe_version = (version_info or {}).get("exe_version")
    items.append(SetupItem("version", "Game version", tu or exe_version, bool(tu),
                           note=friendly_update(tu) if tu else
                           ("Found the game, but please type the game update number" if game else "Needs the game first")))
    items.append(SetupItem("mod_manager", "FIFA Mod Manager", found.mod_manager_exe, found.mod_manager_exe is not None,
                           note="" if found.mod_manager_exe else "Please pick FIFA Mod Manager.exe"))
    items.append(SetupItem("saves", "Career saves", found.settings_dir, found.settings_dir is not None,
                           note="" if found.settings_dir else "Start a Career once, or pick the 'settings' folder"))
    items.append(SetupItem("temp", "Game temp folder", found.temp_dir, found.temp_dir is not None, optional=True,
                           note="Cleaned after game updates"))
    items.append(SetupItem("live_editor", "Live Editor (optional)", found.live_editor_dir,
                           found.live_editor_dir is not None, optional=True,
                           note="" if found.live_editor_dir else "Only needed for My academy"))
    return items


def run_detection(probe: detect.Probe | None = None, detector=None) -> tuple[detect.Detection, dict | None, list[SetupItem]]:
    detector = detector or version_mod.detect
    found = detect.detect_all(probe)
    info = detector(found.games[0].game, found.games[0].path) if found.games else None
    return found, info, setup_items(found, info)


def save_setup(ledger_path: Path, game: str, install: Path, *, tu: str | None, exe_version: str | None,
               mod_manager_exe: Path | None, settings_dir: Path | None, temp_dir: Path | None,
               live_editor_dir: Path | None, home: Path | None = None) -> Ledger:
    home = home or app_home()
    try:
        ledger = Ledger.load(ledger_path)
    except Exception:  # noqa: BLE001 - no ledger yet (or unreadable): start fresh
        ledger = Ledger()
    ledger.game = game
    ledger.install_path = str(install)
    ledger.current_build = tu or ledger.current_build
    ledger.exe_version = exe_version or ledger.exe_version
    values = {
        "fmm_exe": mod_manager_exe,
        "fmm_dir": mod_manager_exe.parent if mod_manager_exe else None,
        "settings_dir": settings_dir,
        "temp_dir": temp_dir,
        "live_editor_dir": live_editor_dir,
        "backup_dir": home / "Backups",
        "academy_dir": home / "Academy",
        "mods_dir": home / "Mods",
    }
    for key, value in values.items():
        if value is not None:
            ledger.paths[key] = str(value)
    for folder in ("Backups", "Academy", "Mods"):
        (home / folder).mkdir(parents=True, exist_ok=True)
    ledger.app["setup_done"] = True
    ledger.app["accepted_warning"] = True
    ledger.save(ledger_path)
    return ledger


def load_ledger(path: Path | None = None) -> Ledger | None:
    path = path or default_ledger_path()
    try:
        ledger = Ledger.load(path)
    except Exception:  # noqa: BLE001
        return None
    return ledger if ledger.app.get("setup_done") else None


# ------------------------------------------------------------------ status
@dataclass
class Status:
    level: str
    sentence: str
    fix: str = ""        # id of the fix action the UI should offer
    fix_label: str = ""
    detail: list[str] = field(default_factory=list)


def _clash_names(clash: conflicts.Clash) -> str:
    return " and ".join(clash.mods) if len(clash.mods) == 2 else ", ".join(clash.mods)


def status(ledger: Ledger, detector=None) -> Status:
    detector = detector or version_mod.detect
    if ledger.install_path:
        info = detector(ledger.game, ledger.install_path)
        tu, exe_version = info.get("tu"), info.get("exe_version")
        updated = (tu and ledger.current_build and tu != ledger.current_build) or \
                  (exe_version and ledger.exe_version and exe_version != ledger.exe_version)
        if updated:
            return Status(RED, "The game has updated. Press 'Game updated? Fix my mods' before you play.",
                          "game_updated", "Fix my mods")
    enabled = [m for m in ledger.mods if m.enabled]
    missing = [m for m in enabled if not ledger.mod_path(m).exists()]
    if missing:
        return Status(RED, f"I can't find the mod '{missing[0].name}' any more.", "remove_missing",
                      "Remove missing mods from my list", [m.name for m in missing])
    clashes = conflicts.find_clashes(ledger.mods, conflicts.load_rules())
    if clashes:
        return Status(RED, f"{_clash_names(clashes[0])} change the same thing. Keep only one.",
                      "choose_clash", "Choose one", clashes[0].mods)
    old = [m for m in enabled if m.pinned_tu and ledger.current_build and m.pinned_tu != ledger.current_build]
    if old:
        names = ", ".join(m.name for m in old)
        return Status(RED, f"{len(old)} mod(s) aren't ready for this game update yet: {names}.",
                      "game_updated", "Fix my mods", [m.name for m in old])
    if not ledger.resolved_paths().get("fmm_exe") or not Path(ledger.resolved_paths().get("fmm_exe")).exists():
        return Status(YELLOW, "I couldn't find FIFA Mod Manager. Please show me where it is.",
                      "pick_mod_manager", "Find Mod Manager")
    if not ledger.current_build:
        return Status(YELLOW, "I don't know which game update you have yet.", "set_update", "Tell me the game update")
    if not enabled:
        return Status(GREEN, "All good. You have no mods added yet.")
    return Status(GREEN, f"All good. {len(enabled)} mod(s) ready for {friendly_update(ledger.current_build)}.")


# ------------------------------------------------------------------ backups
def last_backup_time(ledger: Ledger) -> dt.datetime | None:
    folder = ledger.resolved_paths().get("backup_dir")
    infos = backup.list_backups(Path(folder)) if folder else []
    times = []
    for info in infos:
        try:
            times.append(dt.datetime.fromisoformat(info.created))
        except ValueError:
            continue
    return max(times) if times else None


def _backup_sources(ledger: Ledger) -> dict[str, Path]:
    resolved = ledger.resolved_paths()
    sources = {}
    if resolved.get("settings_dir"):
        sources["saves"] = Path(resolved.get("settings_dir"))
    if resolved.get("fmm_dir"):
        sources["fmm"] = Path(resolved.get("fmm_dir"))
    return sources


def backup_now(ledger: Ledger, label: str = "", now: dt.datetime | None = None) -> Path:
    dest = ledger.resolved_paths().require("backup_dir")
    return backup.create_backup(_backup_sources(ledger), Path(dest), label=label, game=ledger.game,
                                build=ledger.current_build, now=now)


def backup_if_old(ledger: Ledger, now: dt.datetime | None = None) -> Path | None:
    now = now or dt.datetime.now()
    last = last_backup_time(ledger)
    if last is not None and now - last < BACKUP_MAX_AGE:
        return None
    return backup_now(ledger, label="auto", now=now)


@dataclass
class RestorePoint:
    path: Path
    text: str


def friendly_date(when: dt.datetime) -> str:
    return when.strftime("%A %d %B %Y, %I:%M %p").replace(" 0", " ")


def restore_points(ledger: Ledger) -> list[RestorePoint]:
    folder = ledger.resolved_paths().get("backup_dir")
    points = []
    for info in reversed(backup.list_backups(Path(folder)) if folder else []):
        try:
            when = friendly_date(dt.datetime.fromisoformat(info.created))
        except ValueError:
            when = info.created
        kind = {"auto": " (automatic)", "pre-restore": " (made before a restore)", "": ""}.get(info.label, f" ({info.label})")
        points.append(RestorePoint(info.path, when + kind))
    return points


def restore(ledger: Ledger, point: Path, confirm: Confirm) -> str:
    if not confirm("Restore this backup?",
                   "Your saves and Mod Manager settings will go back to this backup.\n\n"
                   "I'll back up what you have now first, so you can undo this."):
        return "Nothing changed."
    manifest = backup.read_manifest(point)
    available = [c for c, e in manifest["components"].items() if e.get("status") == "ok"]
    resolved = ledger.resolved_paths()
    targets = {}
    for comp in available:
        key = backup.COMPONENTS[comp][0]
        if resolved.get(key):
            targets[comp] = Path(resolved.get(key))
    comps = [c for c in available if c in targets]
    if not comps:
        return "This backup has nothing I can put back."
    ui = UI(out=lambda _t: None, ask=lambda _p: "y", open_url=lambda _u: None, assume_yes=True)
    backup.restore_backup(point, targets, Path(resolved.require("backup_dir")), ui, components=comps,
                          game=ledger.game, build=ledger.current_build)
    return "Done. Your backup is back, and what you had before is saved too."


# ------------------------------------------------------------------ play safely
@dataclass
class PlayResult:
    ok: bool
    status: Status
    backed_up: Path | None = None
    launched: bool = False


def launch_mod_manager(exe: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(exe))  # type: ignore[attr-defined]
    else:
        subprocess.Popen([str(exe)])


def play_safely(ledger: Ledger, *, detector=None, now: dt.datetime | None = None,
                launcher: Callable[[Path], None] = launch_mod_manager) -> PlayResult:
    current = status(ledger, detector)
    backed_up = None
    if _backup_sources(ledger):
        backed_up = backup_if_old(ledger, now)
    if current.level != GREEN:
        return PlayResult(False, current, backed_up)
    exe = Path(ledger.resolved_paths().require("fmm_exe"))
    launcher(exe)
    sentence = "Starting Mod Manager. Make sure the EA app is in Offline mode. Have fun!"
    return PlayResult(True, Status(GREEN, sentence), backed_up, True)


def remove_missing(ledger: Ledger) -> list[str]:
    gone = [m for m in ledger.mods if not ledger.mod_path(m).exists()]
    for mod in gone:
        ledger.mods.remove(mod)
    ledger.save()
    return [m.name for m in gone]


# ------------------------------------------------------------------ add mods
TAG_GUESSES = [
    (re.compile(r"kiarika.*career|career.*kiarika", re.I), ["academy-overhaul"]),
    (re.compile(r"redux", re.I), ["academy-overhaul"]),
    (re.compile(r"re-?adjusted", re.I), ["academy-overhaul"]),
    (re.compile(r"youth|academy", re.I), ["academy"]),
    (re.compile(r"anth\s*james", re.I), ["gameplay-overhaul"]),
    (re.compile(r"true\s*foot", re.I), ["gameplay-overhaul"]),
    (re.compile(r"optimi[sz]|performance|fps", re.I), ["performance"]),
]
_VERSIONISH = re.compile(r"(?i)\b(v?\d+(?:[._]\d+)+|v\d+|tu\s*\d+(?:[._]\d+)*|fc\s*2[67]|final|update)\b")


def guess_name(filename: str) -> str:
    stem = Path(filename.replace("\\", "/")).stem
    text = re.sub(r"[_\-]+", " ", stem)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = _VERSIONISH.sub(" ", text)
    text = re.sub(r"[.()\[\]]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return stem
    words = " ".join(w if w.isupper() and len(w) > 1 else w[:1].upper() + w[1:] for w in text.split(" "))
    return re.sub(r"\bRe ([A-Za-z])", lambda m: "Re-" + m.group(1).lower(), words)


def match_key(name: str) -> str:
    return re.sub(r"[^a-z]", "", _VERSIONISH.sub(" ", guess_name(name)).lower())


def guess_tags(name: str) -> list[str]:
    text = f"{name} {guess_name(name)}"
    for pattern, tags in TAG_GUESSES:
        if pattern.search(text):
            return list(tags)
    return []


@dataclass
class ClashChoice:
    description: str
    mods: list[str]


@dataclass
class AddResult:
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    clashes: list[ClashChoice] = field(default_factory=list)

    @property
    def sentence(self) -> str:
        parts = []
        if self.added:
            parts.append(f"Added {len(self.added)} mod(s): {', '.join(self.added)}.")
        if self.skipped:
            parts.append(f"Skipped {len(self.skipped)} file(s) that aren't mods or are already added.")
        if self.clashes:
            parts.append("Some mods change the same thing - please choose which to keep.")
        return " ".join(parts) or "No mods added."


def _unique_name(ledger: Ledger, name: str) -> str:
    existing = {m.name.lower() for m in ledger.mods}
    if name.lower() not in existing:
        return name
    n = 2
    while f"{name} ({n})".lower() in existing:
        n += 1
    return f"{name} ({n})"


def add_mod_files(ledger: Ledger, files: list[Path], *, copy_to_mods_folder: bool = True,
                  url: str = "") -> AddResult:
    result = AddResult()
    mods_dir = ledger.resolved_paths().get("mods_dir")
    known = {sha for sha in (m.sha256 for m in ledger.mods) if sha}
    for source in files:
        source = Path(source)
        if source.suffix.lower() not in MOD_EXTENSIONS or not source.is_file():
            result.skipped.append(source.name)
            continue
        digest = sha256_file(source)
        if digest in known:
            result.skipped.append(source.name)
            continue
        target = source
        if copy_to_mods_folder and mods_dir:
            Path(mods_dir).mkdir(parents=True, exist_ok=True)
            target = Path(mods_dir) / source.name
            if os.path.normcase(os.path.abspath(target)) != os.path.normcase(os.path.abspath(source)):
                shutil.copy2(source, target)
        if mods_dir and Path(target).parent == Path(mods_dir):
            mark_seen(ledger, Path(target))
        name = _unique_name(ledger, guess_name(source.name))
        ledger.add_mod(Mod(name=name, file=str(target), pinned_tu=ledger.current_build, author_url=url,
                           sha256=digest, tags=guess_tags(source.name)))
        known.add(digest)
        result.added.append(name)
    for clash in conflicts.find_clashes(ledger.mods, conflicts.load_rules()):
        result.clashes.append(ClashChoice(clash.description, clash.mods))
    ledger.save()
    return result


def keep_only(ledger: Ledger, keep: str, among: list[str]) -> list[str]:
    """Turns off every mod in `among` except `keep`. Returns the names turned off."""
    off = []
    for name in among:
        mod = ledger.find_mod(name)
        if mod.name != keep and mod.enabled:
            mod.enabled = False
            off.append(mod.name)
    ledger.save()
    return off


def set_mod_link(ledger: Ledger, name: str, url: str) -> None:
    ledger.find_mod(name).author_url = url.strip()
    ledger.save()


# ------------------------------------------------------------------ game updated
@dataclass
class UpdateResult:
    sentence: str
    new_update: str
    cleaned: list[str] = field(default_factory=list)
    needs_update: list[str] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)


def game_updated(ledger: Ledger, confirm: Confirm, *, open_url: Callable[[str], object],
                 ask_update: Callable[[], str | None] = lambda: None, detector=None) -> UpdateResult:
    detector = detector or version_mod.detect
    info = detector(ledger.game, ledger.install_path) if ledger.install_path else {}
    new = info.get("tu") or ask_update() or ledger.current_build
    if new:
        try:
            from fcmh.ledger import normalize_tu
            new = normalize_tu(new) or ledger.current_build
        except Exception:  # noqa: BLE001
            new = ledger.current_build
    ledger.current_build = new
    if info.get("exe_version"):
        ledger.exe_version = info["exe_version"]

    cleaned = []
    paths = ledger.resolved_paths()
    targets = [(k, paths.get(k)) for k in ("fifamoddata_dir", "temp_dir")]
    targets = [(k, Path(p)) for k, p in targets if p and Path(p).exists()]
    if targets and confirm("Clean up old mod files?",
                           "After a game update, Mod Manager needs to rebuild its files.\n\n"
                           "Can I delete the old ones now? Your Career saves are NOT touched.\n"
                           "(Close the game and Mod Manager first.)"):
        for key, path in targets:
            try:
                patch.check_safe_target(key, path)
            except patch.UnsafeDeleteError:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            cleaned.append(key)

    # Updated files already sitting in the Mods folder get picked up now.
    watch_mods_folder(ledger, save=False)
    for result in patch.rescan(ledger):
        mod = ledger.find_mod(result.name)
        if result.status == "changed":
            mod.sha256, mod.pinned_tu = result.new, new

    needs = [m for m in ledger.mods if m.enabled and m.pinned_tu and new and m.pinned_tu != new]
    opened = []
    with_links = [m for m in needs if m.author_url]
    if with_links and confirm("Open the mod pages?",
                              f"{len(needs)} mod(s) need a new version for {friendly_update(new)}.\n\n"
                              "Open their pages so you can download the updates?"):
        for mod in with_links:
            open_url(mod.author_url)
            opened.append(mod.name)
    ledger.save()
    if needs:
        sentence = (f"Now on {friendly_update(new)}. {len(needs)} mod(s) need updates: "
                    f"{', '.join(m.name for m in needs)}. Put the new files in your Mods folder and I'll "
                    "spot them. Until then, untick those mods in Mod Manager.")
    else:
        sentence = f"All done. Every mod is ready for {friendly_update(new)}."
    return UpdateResult(sentence, new, cleaned, [m.name for m in needs], opened)


@dataclass
class WatchResult:
    updated: list[str] = field(default_factory=list)
    new_files: list[Path] = field(default_factory=list)


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _signature(path: Path) -> list[int]:
    info = path.stat()
    return [info.st_size, info.st_mtime_ns]


def mark_seen(ledger: Ledger, path: Path) -> None:
    ledger.app.setdefault("seen_files", {})[_norm(path)] = _signature(path)


def watch_mods_folder(ledger: Ledger, save: bool = True) -> WatchResult:
    """Looks in the Mods folder. A new file whose name matches a known mod (ignoring version
    numbers) is treated as that mod's update: the ledger points at it and re-pins it to the
    current game update. Other new files are returned so the app can offer to add them."""
    result = WatchResult()
    folder = ledger.resolved_paths().get("mods_dir")
    if not folder or not Path(folder).is_dir():
        return result
    files = sorted((p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in MOD_EXTENSIONS),
                   key=lambda p: p.stat().st_mtime)
    seen = ledger.app.setdefault("seen_files", {})
    by_key: dict[str, Mod] = {}
    for m in ledger.mods:
        by_key.setdefault(match_key(Path(m.file.replace("\\", "/")).name), m)
        by_key.setdefault(match_key(m.name), m)
    changed = False
    for path in files:
        here = _norm(path)
        signature = _signature(path)
        if seen.get(here) == signature:
            continue  # nothing new about this file
        seen[here] = signature
        changed = True
        current = next((m for m in ledger.mods if _norm(ledger.mod_path(m)) == here), None)
        if current is not None:
            digest = sha256_file(path)
            if current.sha256 and digest != current.sha256:
                current.sha256, current.pinned_tu = digest, ledger.current_build
                result.updated.append(current.name)
            continue
        mod = by_key.get(match_key(path.name))
        if mod is not None:
            digest = sha256_file(path)
            if digest != mod.sha256:
                mod.file, mod.sha256, mod.pinned_tu = str(path), digest, ledger.current_build
                if mod.name not in result.updated:
                    result.updated.append(mod.name)
            continue
        result.new_files.append(path)
    if changed and save:
        ledger.save()
    return result


# ------------------------------------------------------------------ academy
LUA_NAME = "fcmh_academy_export.lua"


def lua_source() -> str:
    return resources.files("fcmh.lua").joinpath(LUA_NAME).read_text(encoding="utf-8")


def lua_with_output_dir(folder: Path) -> str:
    escaped = str(folder).replace("\\", "\\\\").replace('"', '\\"')
    text = lua_source()
    return text.replace("local OUTPUT_DIR = nil\n", f'local OUTPUT_DIR = "{escaped}"\n', 1)


@dataclass
class AcademyResult:
    sentence: str
    script_path: Path | None = None
    report: Path | None = None
    imported: int = 0


def academy_setup(ledger: Ledger) -> AcademyResult:
    resolved = ledger.resolved_paths()
    folder = Path(resolved.require("academy_dir"))
    folder.mkdir(parents=True, exist_ok=True)
    le = resolved.get("live_editor_dir")
    if not le or not (Path(le) / "lua").is_dir():
        return AcademyResult("I couldn't find Live Editor. Get it from its official page, then show me its folder "
                             "(More > Find Live Editor).")
    target = Path(le) / "lua" / LUA_NAME
    target.write_text(lua_with_output_dir(folder), encoding="utf-8")
    return AcademyResult("In Career Mode press F9, then Features > Lua Engine, open "
                         f"'{LUA_NAME}' and press Execute. Do it once a season.", target)


def import_academy_csvs(ledger: Ledger) -> int:
    """Copies any exports left on the Desktop into the Academy folder."""
    folder = Path(ledger.resolved_paths().require("academy_dir"))
    folder.mkdir(parents=True, exist_ok=True)
    profile = os.environ.get("USERPROFILE") or str(Path.home())
    count = 0
    for source in sorted((Path(profile) / "Desktop").glob("fcmh_academy_*.csv")):
        target = folder / source.name
        if not target.exists() or source.stat().st_mtime > target.stat().st_mtime:
            shutil.copy2(source, target)
            count += 1
    return count


def academy_report(ledger: Ledger) -> AcademyResult:
    imported = import_academy_csvs(ledger)
    folder = Path(ledger.resolved_paths().require("academy_dir"))
    files = academy.collect([folder])
    if not files:
        setup = academy_setup(ledger)
        return AcademyResult("No academy data yet. " + setup.sentence, setup.script_path, None, imported)
    prospects = academy.merge(files)
    paths = academy.write_report(prospects, folder / "report")
    return AcademyResult(f"Your academy report has {len(prospects)} players.", None, paths["html"], imported)
