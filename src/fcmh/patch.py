"""Post-patch wizard and the `rescan` command.

After a Title Update the community routine is:
1. note the new TU,
2. delete FIFAModData and the game's temp folder (Mod Manager rebuilds them),
3. check every mod's page for an update built for the new TU,
4. swap in the updated files and re-pin them.
fcmh walks through that, asking before anything is deleted, with a --dry-run mode.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from fcmh import version as version_mod
from fcmh.ledger import Ledger, LedgerError, normalize_tu, sha256_file
from fcmh.ui import UI


class UnsafeDeleteError(Exception):
    pass


# Folder/file names we are willing to delete. Anything else is refused.
_ALLOWED = {
    "fifamoddata_dir": lambda p: p.name.lower() == "fifamoddata",
    "temp_dir": lambda p: p.name.lower().startswith("ea sports fc") and p.parent.name.lower() == "temp",
    "editor_cache_file": lambda p: p.suffix.lower() == ".cache" and "modding" in p.name.lower(),
}


def check_safe_target(key: str, path: Path) -> None:
    resolved = Path(os.path.abspath(path))
    if resolved == Path(resolved.anchor) or resolved == Path(os.path.abspath(Path.home())):
        raise UnsafeDeleteError(f"Refusing to delete {resolved}: it is a drive root or home folder")
    allowed = _ALLOWED.get(key)
    if allowed is None or not allowed(resolved):
        raise UnsafeDeleteError(
            f"Refusing to delete {resolved}: it doesn't look like the expected '{key}' location. "
            "Fix the path in the ledger (fcmh paths) if it is wrong.")


def describe(path: Path) -> tuple[int, int]:
    """(file_count, total_bytes) for a file or folder; (0, 0) if missing."""
    if path.is_file():
        return 1, path.stat().st_size
    count = size = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            count += 1
            try:
                size += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return count, size


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def delete_target(key: str, path: Path, ui: UI, dry_run: bool) -> bool:
    if not path.exists():
        ui.out(f"  - {key}: {path} (not present, nothing to do)")
        return False
    check_safe_target(key, path)
    files, size = describe(path)
    label = f"{path} ({files} files, {human(size)})"
    if dry_run:
        ui.out(f"  - would delete {key}: {label}")
        return False
    if not ui.confirm(f"  Delete {key}: {label}?"):
        ui.out("    skipped")
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    ui.out("    deleted")
    return True


@dataclass
class RescanResult:
    name: str
    status: str  # unchanged | changed | missing | recorded
    old: str
    new: str


def rescan(ledger: Ledger) -> list[RescanResult]:
    results = []
    for mod in ledger.mods:
        path = ledger.mod_path(mod)
        if not path.exists():
            results.append(RescanResult(mod.name, "missing", mod.sha256, ""))
            continue
        digest = sha256_file(path)
        if not mod.sha256:
            status = "recorded"
        elif digest == mod.sha256:
            status = "unchanged"
        else:
            status = "changed"
        results.append(RescanResult(mod.name, status, mod.sha256, digest))
    return results


def apply_rescan(ledger: Ledger, results: list[RescanResult], ui: UI, dry_run: bool) -> int:
    """Records new checksums; offers to re-pin changed files to the current build."""
    updated = 0
    for result in results:
        mod = ledger.find_mod(result.name)
        if result.status == "missing":
            ui.out(f"  {mod.name}: file missing at {ledger.mod_path(mod)}")
        elif result.status == "unchanged":
            ui.out(f"  {mod.name}: unchanged (pinned TU {mod.pinned_tu or '?'})")
        elif result.status == "recorded":
            ui.out(f"  {mod.name}: checksum recorded for the first time")
            if not dry_run:
                mod.sha256 = result.new
                updated += 1
        else:
            ui.out(f"  {mod.name}: FILE CHANGED (looks like an updated download)")
            if dry_run:
                continue
            build = ledger.current_build
            if build and mod.pinned_tu != build and ui.confirm(
                    f"    Is this the update built for TU {build}? Re-pin {mod.name} to {build}"):
                mod.pinned_tu = build
            mod.sha256 = result.new
            updated += 1
    return updated


def post_patch(ledger: Ledger, ui: UI, *, new_tu: str | None = None, dry_run: bool = False,
               open_pages: bool = True, include_editor_cache: bool = False, detector=None) -> dict:
    detector = detector or version_mod.detect
    paths = ledger.resolved_paths()
    ui.out("== fcmh post-patch wizard" + (" (DRY RUN: nothing is changed)" if dry_run else ""))

    # Step 1: which build are we on now?
    ui.out("\nStep 1/4  New game build")
    old_build = ledger.current_build
    info = {}
    if not new_tu and ledger.install_path:
        info = detector(ledger.game, ledger.install_path)
        ui.out(f"  {info.get('message', '')}")
        new_tu = info.get("tu")
    if not new_tu:
        typed = ui.ask("  Enter the new Title Update (e.g. 1.6.6), or leave empty to keep the current value: ").strip()
        new_tu = typed or old_build
    try:
        new_tu = normalize_tu(new_tu) or ""
    except LedgerError as exc:
        ui.out(f"  {exc}")
        new_tu = old_build
    ui.out(f"  Build: {old_build or '?'} -> {new_tu or '?'}")
    if not dry_run:
        ledger.current_build = new_tu
        if info.get("exe_version"):
            ledger.exe_version = info["exe_version"]

    # Step 2: clear generated mod data and temp
    ui.out("\nStep 2/4  Clear generated mod data (close the game and Mod Manager first)")
    keys = ["fifamoddata_dir", "temp_dir"] + (["editor_cache_file"] if include_editor_cache else [])
    deleted = []
    for key in keys:
        target = paths.get(key)
        if target is None:
            continue
        try:
            if delete_target(key, target, ui, dry_run):
                deleted.append(key)
        except UnsafeDeleteError as exc:
            ui.out(f"  ! {exc}")

    # Step 3: mods that need an update
    ui.out("\nStep 3/4  Mods pinned to a different TU")
    outdated = [m for m in ledger.mods if m.enabled and m.pinned_tu and new_tu and m.pinned_tu != new_tu]
    if not outdated:
        ui.out("  None. Every enabled mod is pinned to the current build.")
    for mod in outdated:
        ui.out(f"  - {mod.name}: pinned {mod.pinned_tu} -> needs a {new_tu} build  {mod.author_url}")
        if open_pages and not dry_run and mod.author_url:
            ui.open_url(mod.author_url)
    if outdated:
        ui.out("  Download only from the author's own page. Keep a mod disabled until its author ships a build for this TU.")

    # Step 4: look for updated files already on disk
    ui.out("\nStep 4/4  Check local mod files for updates")
    results = rescan(ledger)
    changed = apply_rescan(ledger, results, ui, dry_run)
    if not dry_run:
        ledger.save()
        ui.out(f"\nLedger saved to {ledger.location}.")
    ui.out("After you download updated mods, replace the files listed in the ledger and run `fcmh rescan`, then `fcmh check`.")
    return {"old_build": old_build, "new_build": new_tu, "deleted": deleted,
            "outdated": [m.name for m in outdated], "updated": changed}
