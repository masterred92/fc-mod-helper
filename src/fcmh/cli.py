"""Command line interface: `fcmh <command>`. Run `fcmh --help` for the list."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from fcmh import __version__
from fcmh import academy, backup, checks, conflicts, patch
from fcmh import version as version_mod
from fcmh.checklist import ONLINE_CHECKLIST
from fcmh.ledger import Ledger, LedgerError, Mod, default_ledger_path, normalize_tu, sha256_file
from fcmh.paths import GAMES, PATH_KEYS
from fcmh.ui import UI

EXIT_OK, EXIT_ERROR, EXIT_BLOCKED = 0, 1, 2


def _ledger(args) -> Ledger:
    return Ledger.load(args.ledger)


# ---------------------------------------------------------------- ledger
def cmd_init(args, ui: UI) -> int:
    path = Path(args.ledger)
    if path.exists() and not args.force:
        ui.out(f"A ledger already exists at {path}. Use --force to replace it.")
        return EXIT_ERROR
    ledger = Ledger(game=args.game, install_path=args.install or "",
                    current_build=normalize_tu(args.build) or "")
    ledger.save(path)
    ui.out(f"Created ledger for {GAMES[args.game]['title']} at {path}")
    ui.out("Next: `fcmh detect --save`, then `fcmh paths --set fmm_dir <your Mod Manager folder>`.")
    return EXIT_OK


def cmd_show(args, ui: UI) -> int:
    ledger = _ledger(args)
    ui.out(f"Ledger:        {ledger.location}")
    ui.out(f"Game:          {GAMES[ledger.game]['title']} ({ledger.game})")
    ui.out(f"Install path:  {ledger.install_path or '(not set)'}")
    ui.out(f"Current TU:    {ledger.current_build or '(unknown)'}   exe version: {ledger.exe_version or '-'}")
    ui.out(f"Mods:          {len(ledger.mods)} ({sum(m.enabled for m in ledger.mods)} enabled)")
    return EXIT_OK


def cmd_paths(args, ui: UI) -> int:
    ledger = _ledger(args)
    if args.set:
        key, value = args.set
        if key not in PATH_KEYS:
            ui.out(f"Unknown path key {key}. Choose from: {', '.join(PATH_KEYS)}")
            return EXIT_ERROR
        ledger.paths[key] = value
        ledger.save()
        ui.out(f"Set {key} = {value}")
    if args.unset:
        ledger.paths.pop(args.unset, None)
        ledger.save()
        ui.out(f"Reset {args.unset} to its default")
    resolved = ledger.resolved_paths()
    for key in PATH_KEYS:
        value = resolved.get(key)
        origin = "ledger" if key in ledger.paths else "default"
        exists = "" if value is None else ("  (exists)" if Path(value).exists() else "  (not found)")
        ui.out(f"  {key:18} {value if value is not None else '(not set)'}  [{origin}]{exists}")
    return EXIT_OK


def cmd_detect(args, ui: UI) -> int:
    ledger = _ledger(args)
    if not ledger.install_path:
        ui.out("install_path is empty in the ledger. Re-run `fcmh init --install \"<game folder>\" --force` or edit the ledger.")
        return EXIT_ERROR
    info = version_mod.detect(ledger.game, ledger.install_path)
    ui.out(info["message"])
    if args.save and info.get("tu"):
        ledger.current_build = info["tu"]
        ledger.exe_version = info["exe_version"]
        ledger.save()
        ui.out(f"Saved current build {info['tu']} to the ledger.")
    elif args.save and info.get("exe_version"):
        ledger.exe_version = info["exe_version"]
        ledger.save()
        ui.out("Saved the exe version. Set the TU by hand with `fcmh set-build <TU>`.")
    return EXIT_OK if info.get("exe_version") else EXIT_ERROR


def cmd_set_build(args, ui: UI) -> int:
    ledger = _ledger(args)
    ledger.current_build = normalize_tu(args.tu) or ""
    ledger.save()
    ui.out(f"Current build set to TU {ledger.current_build}")
    return EXIT_OK


# ---------------------------------------------------------------- mods
def cmd_mod_add(args, ui: UI) -> int:
    ledger = _ledger(args)
    mod = Mod(name=args.name, file=args.file, pinned_tu=normalize_tu(args.tu) or "",
              author_url=args.url or "", tags=args.tag or [], enabled=not args.disabled, notes=args.notes or "")
    path = ledger.mod_path(mod)
    if path.exists():
        mod.sha256 = sha256_file(path)
    else:
        ui.out(f"Note: {path} doesn't exist yet; the checksum will be recorded by `fcmh rescan`.")
    ledger.add_mod(mod)
    ledger.save()
    ui.out(f"Added {mod.name} (TU {mod.pinned_tu or '?'})")
    clashes = conflicts.find_clashes(ledger.mods, conflicts.load_rules(args.rules))
    for clash in clashes:
        ui.out(f"Warning: clash '{clash.rule_id}' between {', '.join(clash.mods)}. {clash.advice}")
    return EXIT_OK


def cmd_mod_list(args, ui: UI) -> int:
    ledger = _ledger(args)
    if not ledger.mods:
        ui.out("No mods in the ledger. Add one with `fcmh mod add`.")
        return EXIT_OK
    for mod in ledger.mods:
        state = "on " if mod.enabled else "off"
        tags = f" [{', '.join(mod.tags)}]" if mod.tags else ""
        ui.out(f"[{state}] {mod.name}  TU {mod.pinned_tu or '?'}{tags}")
        ui.out(f"      file: {mod.file}")
        if mod.author_url:
            ui.out(f"      page: {mod.author_url}")
    return EXIT_OK


def cmd_mod_remove(args, ui: UI) -> int:
    ledger = _ledger(args)
    mod = ledger.remove_mod(args.name)
    ledger.save()
    ui.out(f"Removed {mod.name} from the ledger (the file itself was not touched).")
    return EXIT_OK


def cmd_mod_toggle(args, ui: UI) -> int:
    ledger = _ledger(args)
    mod = ledger.find_mod(args.name)
    mod.enabled = args.command_name == "enable"
    ledger.save()
    ui.out(f"{mod.name} is now {'enabled' if mod.enabled else 'disabled'} in the ledger. "
           "Mirror this in Mod Manager.")
    return EXIT_OK


def cmd_mod_pin(args, ui: UI) -> int:
    ledger = _ledger(args)
    mod = ledger.find_mod(args.name)
    mod.pinned_tu = normalize_tu(args.tu) or ""
    path = ledger.mod_path(mod)
    if path.exists():
        mod.sha256 = sha256_file(path)
    ledger.save()
    ui.out(f"{mod.name} pinned to TU {mod.pinned_tu}")
    return EXIT_OK


def cmd_rescan(args, ui: UI) -> int:
    ledger = _ledger(args)
    ui.assume_yes = args.yes
    results = patch.rescan(ledger)
    changed = patch.apply_rescan(ledger, results, ui, args.dry_run)
    if not args.dry_run and changed:
        ledger.save()
    ui.out(f"{changed} ledger entr{'y' if changed == 1 else 'ies'} updated." if not args.dry_run else "Dry run: ledger not changed.")
    return EXIT_OK


# ---------------------------------------------------------------- checks
def cmd_check(args, ui: UI) -> int:
    ledger = _ledger(args)
    findings = checks.run_checks(ledger, args.rules, detect_build=not args.no_detect)
    ui.out(checks.format_findings(findings))
    verdict = checks.worst(findings)
    if verdict == checks.ERROR:
        ui.out("\nNOT SAFE TO LAUNCH with this mod set. Fix the [FAIL] lines first.")
        return EXIT_BLOCKED
    ui.out("\nLooks OK to launch" + (" (see warnings)." if verdict == checks.WARN else "."))
    return EXIT_OK


def cmd_conflicts(args, ui: UI) -> int:
    ledger = _ledger(args)
    clashes = conflicts.find_clashes(ledger.mods, conflicts.load_rules(args.rules))
    if not clashes:
        ui.out("No known clashes between enabled mods.")
        return EXIT_OK
    for clash in clashes:
        ui.out(f"[{clash.severity.upper()}] {clash.rule_id}: {', '.join(clash.mods)}")
        ui.out(f"    {clash.description}")
        if clash.advice:
            ui.out(f"    {clash.advice}")
    return EXIT_BLOCKED


def cmd_launch(args, ui: UI) -> int:
    ledger = _ledger(args)
    findings = checks.run_checks(ledger, args.rules)
    ui.out(checks.format_findings(findings))
    if checks.worst(findings) == checks.ERROR and not args.force:
        ui.out("\nLaunch blocked. Fix the [FAIL] lines, or use --force if you are sure.")
        return EXIT_BLOCKED
    exe = ledger.resolved_paths().get("fmm_exe")
    if exe is None or not Path(exe).exists():
        ui.out("\nChecks done. Set `fcmh paths --set fmm_exe <path to Mod Manager exe>` to start it from here, "
               "or open Mod Manager yourself.")
        return EXIT_OK
    ui.out(f"\nStarting {exe} (EA app should be in Offline mode).")
    if sys.platform == "win32":
        os.startfile(str(exe))  # type: ignore[attr-defined]
    else:
        subprocess.Popen([str(exe)])
    return EXIT_OK


def cmd_post_patch(args, ui: UI) -> int:
    ledger = _ledger(args)
    ui.assume_yes = args.yes
    patch.post_patch(ledger, ui, new_tu=args.tu, dry_run=args.dry_run, open_pages=not args.no_open,
                     include_editor_cache=args.include_editor_cache)
    return EXIT_OK


def cmd_online_checklist(args, ui: UI) -> int:
    ui.out(ONLINE_CHECKLIST)
    return EXIT_OK


# ---------------------------------------------------------------- backups
def _backup_dir(ledger: Ledger, override: str | None) -> Path:
    return Path(override) if override else ledger.resolved_paths().require("backup_dir")


def _component_paths(ledger: Ledger, names: list[str]) -> dict[str, Path]:
    resolved = ledger.resolved_paths()
    result = {}
    for name in names:
        if name not in backup.COMPONENTS:
            raise backup.BackupError(f"Unknown component {name}. Choose from: {', '.join(backup.COMPONENTS)}")
        key = backup.COMPONENTS[name][0]
        value = resolved.get(key)
        if value is None:
            raise backup.BackupError(f"Component '{name}' needs a folder: fcmh paths --set {key} <folder>")
        result[name] = value
    return result


def _split(value: str | None, default) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else list(default)


def cmd_backup_create(args, ui: UI) -> int:
    ledger = _ledger(args)
    names = _split(args.components, backup.DEFAULT_COMPONENTS)
    resolved = ledger.resolved_paths()
    if args.components is None and resolved.get("fmm_dir") is None:
        names = [n for n in names if n != "fmm"]
        ui.out("Skipping 'fmm': fmm_dir is not set (fcmh paths --set fmm_dir <folder>).")
    sources = _component_paths(ledger, names)
    target = backup.create_backup(sources, _backup_dir(ledger, args.dest), label=args.label or "",
                                  game=ledger.game, build=ledger.current_build)
    manifest = backup.read_manifest(target)
    for comp, entry in manifest["components"].items():
        ui.out(f"  {comp}: {entry['status']} ({len(entry['files'])} files from {entry['source']})")
    ui.out(f"Backup written: {target}")
    return EXIT_OK


def cmd_backup_list(args, ui: UI) -> int:
    ledger = _ledger(args)
    infos = backup.list_backups(_backup_dir(ledger, args.dest))
    if not infos:
        ui.out("No backups yet. Make one with `fcmh backup create`.")
        return EXIT_OK
    for info in infos:
        label = f"  label={info.label}" if info.label else ""
        ui.out(f"{info.path.name}  {info.created}  [{', '.join(info.components)}]  "
               f"{info.files} files, {patch.human(info.size)}{label}")
    return EXIT_OK


def cmd_backup_verify(args, ui: UI) -> int:
    ledger = _ledger(args)
    path = backup.find_backup(_backup_dir(ledger, args.dest), args.name)
    problems = backup.verify_backup(path)
    if problems:
        for problem in problems:
            ui.out(f"  {problem}")
        return EXIT_ERROR
    ui.out(f"{path.name}: OK, every file matches the manifest.")
    return EXIT_OK


def cmd_backup_restore(args, ui: UI) -> int:
    ledger = _ledger(args)
    ui.assume_yes = args.yes
    dest = _backup_dir(ledger, args.dest)
    path = backup.find_backup(dest, args.name)
    manifest = backup.read_manifest(path)
    available = [c for c, e in manifest["components"].items() if e.get("status") == "ok"]
    names = _split(args.components, available)
    targets = _component_paths(ledger, names)
    backup.restore_backup(path, targets, dest, ui, components=names, dry_run=args.dry_run,
                          game=ledger.game, build=ledger.current_build)
    return EXIT_OK


# ---------------------------------------------------------------- academy
def cmd_academy_report(args, ui: UI) -> int:
    inputs = [Path(p) for p in args.input] if args.input else None
    if inputs is None:
        try:
            inputs = [_ledger(args).resolved_paths().require("academy_dir")]
        except LedgerError:
            ui.out("No --input given and no ledger found. Pass --input <folder with fcmh_academy_*.csv>.")
            return EXIT_ERROR
    files = academy.collect(inputs)
    prospects = academy.merge(files)
    if args.out:
        out = Path(args.out)
    else:
        base = inputs[0] if inputs[0].is_dir() else inputs[0].parent
        out = base / "fcmh-academy-report"
    written = academy.write_report(prospects, out)
    ui.out(f"Merged {len(files)} CSV file(s), {len(prospects)} prospects.")
    for kind, path in written.items():
        ui.out(f"  {kind:8} {path}")
    return EXIT_OK


def cmd_gui(args, ui: UI) -> int:
    from fcmh import gui
    return gui.run(args.ledger)


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fcmh", description="EA SPORTS FC mod helper: patch-safety, backups, academy tracker. Offline Career Mode only.")
    parser.add_argument("--version", action="version", version=f"fcmh {__version__}")
    parser.add_argument("--ledger", default=str(default_ledger_path()),
                        help="Ledger JSON file (default: %(default)s, or set FCMH_LEDGER)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def add(name, func, help_text, **kwargs):
        p = sub.add_parser(name, help=help_text, description=help_text, **kwargs)
        p.set_defaults(func=func, command_name=name)
        return p

    p = add("init", cmd_init, "Create a new ledger")
    p.add_argument("--game", choices=sorted(GAMES), default="fc26")
    p.add_argument("--install", help="Game folder, e.g. \"C:\\Program Files\\EA Games\\EA SPORTS FC 26\"")
    p.add_argument("--build", help="Current Title Update if you know it, e.g. 1.6.6")
    p.add_argument("--force", action="store_true", help="Replace an existing ledger")

    add("show", cmd_show, "Show a ledger summary")
    p = add("paths", cmd_paths, "Show or override the folders fcmh uses")
    p.add_argument("--set", nargs=2, metavar=("KEY", "PATH"))
    p.add_argument("--unset", metavar="KEY")
    p = add("detect", cmd_detect, "Read the game exe version and map it to a Title Update")
    p.add_argument("--save", action="store_true", help="Store the detected build in the ledger")
    p = add("set-build", cmd_set_build, "Enter the current Title Update by hand")
    p.add_argument("tu")

    mod = sub.add_parser("mod", help="Add, list, pin, enable/disable or remove mods in the ledger")
    msub = mod.add_subparsers(dest="mod_command", required=True, metavar="<action>")

    def madd(name, func, help_text):
        p = msub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func, command_name=name)
        return p

    p = madd("add", cmd_mod_add, "Record a mod file (opaque: path, sha256, pinned TU)")
    p.add_argument("--name", required=True)
    p.add_argument("--file", required=True, help="Path to the .fifamod file you downloaded")
    p.add_argument("--tu", required=True, help="Title Update the mod was built for, from its mod page")
    p.add_argument("--url", help="Author's mod page")
    p.add_argument("--tag", action="append", help="Tag, e.g. academy-overhaul (repeatable)")
    p.add_argument("--notes")
    p.add_argument("--disabled", action="store_true")
    p.add_argument("--rules", help="Custom known-clashes.json")
    madd("list", cmd_mod_list, "List mods in the ledger")
    for name, func, text in (("remove", cmd_mod_remove, "Remove a mod from the ledger (file is kept)"),
                             ("enable", cmd_mod_toggle, "Mark a mod enabled"),
                             ("disable", cmd_mod_toggle, "Mark a mod disabled")):
        p = madd(name, func, text)
        p.add_argument("name")
    p = madd("pin", cmd_mod_pin, "Set a mod's pinned TU and re-record its checksum")
    p.add_argument("name")
    p.add_argument("--tu", required=True)

    p = add("rescan", cmd_rescan, "Re-hash mod files to spot updated downloads")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true", help="Re-pin changed files to the current build without asking")
    p = add("check", cmd_check, "Pre-launch safety check (exit code 2 = not safe)")
    p.add_argument("--rules", help="Custom known-clashes.json")
    p.add_argument("--no-detect", action="store_true", help="Don't read the game exe version")
    p = add("conflicts", cmd_conflicts, "Check enabled mods against the known-clashes rules")
    p.add_argument("--rules", help="Custom known-clashes.json")
    p = add("launch", cmd_launch, "Run the check, then start Mod Manager if fmm_exe is set")
    p.add_argument("--rules")
    p.add_argument("--force", action="store_true")
    p = add("post-patch", cmd_post_patch, "Wizard to run after a game update")
    p.add_argument("--tu", help="New Title Update (skip detection)")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen, change nothing")
    p.add_argument("--yes", action="store_true", help="Answer yes to every prompt")
    p.add_argument("--no-open", action="store_true", help="Don't open mod pages in the browser")
    p.add_argument("--include-editor-cache", action="store_true",
                   help="Also delete the FIFA Editor Tool modding cache file")
    add("online-checklist", cmd_online_checklist, "Print the steps to play online vanilla (changes nothing)")

    bk = sub.add_parser("backup", help="Create, list, verify or restore backups")
    bsub = bk.add_subparsers(dest="backup_command", required=True, metavar="<action>")

    def badd(name, func, help_text):
        p = bsub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func, command_name=name)
        p.add_argument("--dest", help="Backup folder (default: backup_dir from fcmh paths)")
        return p

    p = badd("create", cmd_backup_create, "Zip the chosen folders with a manifest")
    p.add_argument("--components", help="Comma list of saves,fmm,moddata (default: saves,fmm)")
    p.add_argument("--label", help="Short label added to the file name")
    badd("list", cmd_backup_list, "List backups")
    p = badd("verify", cmd_backup_verify, "Check a backup zip against its manifest")
    p.add_argument("name")
    p = badd("restore", cmd_backup_restore, "Restore a backup (takes a safety backup first)")
    p.add_argument("name")
    p.add_argument("--components", help="Comma list to restore (default: all in the backup)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true")

    ac = sub.add_parser("academy", help="Academy tracker reports")
    asub = ac.add_subparsers(dest="academy_command", required=True, metavar="<action>")
    p = asub.add_parser("report", help="Merge academy CSVs into a growth report",
                        description="Merge fcmh_academy_*.csv files into CSV, Markdown and HTML growth tables")
    p.set_defaults(func=cmd_academy_report, command_name="report")
    p.add_argument("--input", action="append", help="CSV file or folder (repeatable; default: academy_dir)")
    p.add_argument("--out", help="Output folder (default: <input>/fcmh-academy-report)")

    add("gui", cmd_gui, "Open the simple Tkinter window")
    return parser


def main(argv: list[str] | None = None, ui: UI | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ui = ui or UI()
    try:
        return args.func(args, ui)
    except (LedgerError, backup.BackupError, academy.AcademyError, patch.UnsafeDeleteError, KeyError, ValueError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
        ui.out(f"fcmh: {message}")
        return EXIT_ERROR
    except KeyboardInterrupt:
        ui.out("\nCancelled.")
        return EXIT_ERROR
