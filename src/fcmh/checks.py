"""Pre-launch check: build vs pinned TUs, missing/changed files and known clashes."""

from __future__ import annotations

from dataclasses import dataclass

from fcmh.conflicts import find_clashes, load_rules
from fcmh.ledger import Ledger, sha256_file
from fcmh import version as version_mod

OK, WARN, ERROR = "ok", "warn", "error"


@dataclass
class Finding:
    level: str
    message: str
    mod: str = ""


def run_checks(ledger: Ledger, rules_path=None, detect_build: bool = True, detector=None) -> list[Finding]:
    findings: list[Finding] = []
    detector = detector or version_mod.detect

    build = ledger.current_build
    if detect_build and ledger.install_path:
        info = detector(ledger.game, ledger.install_path)
        detected_tu = info.get("tu")
        exe_version = info.get("exe_version")
        if detected_tu and build and detected_tu != build:
            findings.append(Finding(ERROR, f"The game is now on TU {detected_tu} but the ledger says {build}. "
                                           "The game probably updated: run `fcmh post-patch`."))
            build = detected_tu
        elif exe_version and ledger.exe_version and exe_version != ledger.exe_version:
            findings.append(Finding(ERROR, f"The game executable changed ({ledger.exe_version} -> {exe_version}). "
                                           "The game probably updated: run `fcmh post-patch`."))
        elif detected_tu and not build:
            build = detected_tu
            findings.append(Finding(WARN, f"Ledger has no current build; detected TU {detected_tu}. Save it with `fcmh detect --save`."))

    if not build:
        findings.append(Finding(WARN, "Current game build is unknown. Run `fcmh detect --save` or `fcmh set-build <TU>`."))

    enabled = [m for m in ledger.mods if m.enabled]
    if not enabled:
        findings.append(Finding(OK, "No enabled mods in the ledger."))

    for mod in enabled:
        path = ledger.mod_path(mod)
        if not path.exists():
            findings.append(Finding(ERROR, f"Mod file is missing: {path}", mod.name))
            continue
        if not mod.pinned_tu:
            findings.append(Finding(WARN, "No pinned TU recorded for this mod.", mod.name))
        elif build and mod.pinned_tu != build:
            findings.append(Finding(ERROR, f"Built for TU {mod.pinned_tu}, game is on TU {build}. "
                                           "Wait for / download an update before launching with this mod.", mod.name))
        else:
            findings.append(Finding(OK, f"Pinned to TU {mod.pinned_tu}.", mod.name))
        if mod.sha256:
            current = sha256_file(path)
            if current != mod.sha256:
                findings.append(Finding(WARN, "The file changed since it was recorded (maybe an update). "
                                              "Run `fcmh rescan` to confirm and re-pin it.", mod.name))
        else:
            findings.append(Finding(WARN, "No checksum recorded. Run `fcmh rescan` to record one.", mod.name))

    for clash in find_clashes(ledger.mods, load_rules(rules_path)):
        level = ERROR if clash.severity == "error" else WARN
        findings.append(Finding(level, f"Clash '{clash.rule_id}': {', '.join(clash.mods)}. {clash.description} {clash.advice}".strip()))
    return findings


def worst(findings: list[Finding]) -> str:
    levels = {f.level for f in findings}
    if ERROR in levels:
        return ERROR
    if WARN in levels:
        return WARN
    return OK


def format_findings(findings: list[Finding]) -> str:
    tag = {OK: "[ OK ]", WARN: "[WARN]", ERROR: "[FAIL]"}
    lines = []
    for f in findings:
        who = f"{f.mod}: " if f.mod else ""
        lines.append(f"{tag[f.level]} {who}{f.message}")
    return "\n".join(lines)
