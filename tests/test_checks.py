from conftest import no_detect

from fcmh import checks
from fcmh.ledger import Mod


def levels(findings):
    return [f.level for f in findings]


def test_clean_setup_is_ok(fake_env):
    findings = checks.run_checks(fake_env.load(), detector=no_detect)
    assert checks.worst(findings) == checks.OK, checks.format_findings(findings)


def test_pinned_tu_mismatch_blocks(fake_env):
    ledger = fake_env.load()
    ledger.find_mod("Optimization Overhaul").pinned_tu = "1.6.5"
    findings = checks.run_checks(ledger, detector=no_detect)
    assert checks.worst(findings) == checks.ERROR
    assert any("1.6.5" in f.message and f.mod == "Optimization Overhaul" for f in findings)


def test_disabled_mod_not_checked(fake_env):
    ledger = fake_env.load()
    mod = ledger.find_mod("Optimization Overhaul")
    mod.pinned_tu, mod.enabled = "1.0.0", False
    assert checks.worst(checks.run_checks(ledger, detector=no_detect)) == checks.OK


def test_detected_update_blocks(fake_env):
    detector = lambda g, i: {"tu": "1.6.7", "exe_version": "1.0.140.1", "message": ""}
    findings = checks.run_checks(fake_env.load(), detector=detector)
    assert any("post-patch" in f.message for f in findings)
    assert checks.worst(findings) == checks.ERROR


def test_exe_change_blocks_even_without_tu(fake_env):
    ledger = fake_env.load()
    ledger.exe_version = "1.0.139.20381"
    detector = lambda g, i: {"tu": None, "exe_version": "1.0.140.5", "message": ""}
    assert checks.worst(checks.run_checks(ledger, detector=detector)) == checks.ERROR


def test_missing_and_changed_files(fake_env):
    ledger = fake_env.load()
    (fake_env.mods / "optimization.fifamod").write_bytes(b"opt-v2")
    ledger.add_mod(Mod(name="Ghost", file=str(fake_env.mods / "ghost.fifamod"), pinned_tu="1.6.6"))
    findings = checks.run_checks(ledger, detector=no_detect)
    assert any(f.mod == "Ghost" and f.level == checks.ERROR for f in findings)
    assert any(f.mod == "Optimization Overhaul" and "changed" in f.message for f in findings)


def test_clash_blocks(fake_env):
    ledger = fake_env.load()
    ledger.add_mod(Mod(name="KIARIKA Career Mode Overhaul", file=str(fake_env.mods / "kiarika-career-overhaul.fifamod"),
                       pinned_tu="1.6.6"))
    findings = checks.run_checks(ledger, detector=no_detect)
    assert any("youth-academy-overhaul" in f.message for f in findings)


def test_unknown_build_warns(fake_env):
    ledger = fake_env.load()
    ledger.current_build = ""
    findings = checks.run_checks(ledger, detector=no_detect)
    assert checks.WARN in levels(findings)
