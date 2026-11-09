import json

import pytest
from conftest import FIXTURES, Recorder

from fcmh import cli, version
from fcmh.ledger import Ledger


@pytest.fixture(autouse=True)
def _no_real_detection(monkeypatch):
    monkeypatch.setattr(version, "read_exe_version", lambda path: None)


def run(args, rec=None):
    rec = rec or Recorder()
    code = cli.main(args, ui=rec.ui)
    return code, rec.text


def test_init_and_show(tmp_path):
    ledger = tmp_path / "l.json"
    code, _ = run(["--ledger", str(ledger), "init", "--game", "fc27", "--install", str(tmp_path), "--build", "1.0.1"])
    assert code == 0
    assert json.loads(ledger.read_text())["game"] == "fc27"
    code, out = run(["--ledger", str(ledger), "init"])
    assert code == 1 and "--force" in out
    code, out = run(["--ledger", str(ledger), "show"])
    assert "EA SPORTS FC 27" in out and "1.0.1" in out


def test_missing_ledger_message(tmp_path):
    code, out = run(["--ledger", str(tmp_path / "none.json"), "check"])
    assert code == 1 and "fcmh init" in out


def test_mod_add_warns_about_clash_and_check_blocks(fake_env):
    L = ["--ledger", str(fake_env.ledger_path)]
    code, out = run(L + ["mod", "add", "--name", "Youth Academy Re-adjusted",
                         "--file", str(fake_env.mods / "kiarika-career-overhaul.fifamod"),
                         "--tu", "1.6.6", "--url", "https://example.invalid/x"])
    assert code == 0 and "clash" in out
    mod = Ledger.load(fake_env.ledger_path).find_mod("Youth Academy Re-adjusted")
    assert len(mod.sha256) == 64
    code, out = run(L + ["check"])
    assert code == 2 and "NOT SAFE" in out
    code, _ = run(L + ["conflicts"])
    assert code == 2
    run(L + ["mod", "disable", "Youth Academy Re-adjusted"])
    code, out = run(L + ["check"])
    assert code == 0, out


def test_set_build_then_check_flags_old_pins(fake_env):
    L = ["--ledger", str(fake_env.ledger_path)]
    assert run(L + ["set-build", "v1.6.7"])[0] == 0
    code, out = run(L + ["check"])
    assert code == 2 and "TU 1.6.6" in out


def test_mod_list_pin_remove(fake_env):
    L = ["--ledger", str(fake_env.ledger_path)]
    assert "Youth Academy Redux" in run(L + ["mod", "list"])[1]
    run(L + ["mod", "pin", "Youth Academy Redux", "--tu", "1.6.7"])
    assert Ledger.load(fake_env.ledger_path).find_mod("Youth Academy Redux").pinned_tu == "1.6.7"
    run(L + ["mod", "remove", "Youth Academy Redux"])
    assert len(Ledger.load(fake_env.ledger_path).mods) == 1
    assert (fake_env.mods / "youth-academy-redux.fifamod").exists()


def test_paths_set_and_unset(fake_env):
    L = ["--ledger", str(fake_env.ledger_path)]
    code, out = run(L + ["paths", "--set", "backup_dir", str(fake_env.root / "bk")])
    assert code == 0 and "[ledger]" in out
    assert run(L + ["paths", "--set", "bogus", "x"])[0] == 1
    run(L + ["paths", "--unset", "backup_dir"])
    assert "backup_dir" not in Ledger.load(fake_env.ledger_path).paths


def test_post_patch_dry_run_cli(fake_env):
    code, out = run(["--ledger", str(fake_env.ledger_path), "post-patch", "--tu", "1.6.7", "--dry-run"])
    assert code == 0 and "DRY RUN" in out
    assert (fake_env.install / "FIFAModData").exists()


def test_backup_cli_roundtrip(fake_env):
    L = ["--ledger", str(fake_env.ledger_path)]
    code, out = run(L + ["backup", "create", "--label", "test"])
    assert code == 0 and "saves: ok" in out and "fmm: ok" in out
    code, out = run(L + ["backup", "list"])
    name = out.split()[0]
    assert name.startswith("fcmh-backup-")
    assert run(L + ["backup", "verify", name])[0] == 0
    (fake_env.settings / "CmMgrTest01").write_bytes(b"oops")
    code, out = run(L + ["backup", "restore", name, "--components", "saves", "--yes"])
    assert code == 0, out
    assert (fake_env.settings / "CmMgrTest01").read_bytes() == b"career-save-v1"
    assert run(L + ["backup", "create", "--components", "nope"])[0] == 1


def test_backup_without_fmm_dir_skips_it(fake_env):
    L = ["--ledger", str(fake_env.ledger_path)]
    run(L + ["paths", "--unset", "fmm_dir"])
    code, out = run(L + ["backup", "create"])
    assert code == 0 and "Skipping 'fmm'" in out


def test_academy_report_cli(tmp_path):
    out_dir = tmp_path / "report"
    code, out = run(["--ledger", str(tmp_path / "none.json"), "academy", "report",
                     "--input", str(FIXTURES / "academy"), "--out", str(out_dir)])
    assert code == 0 and "4 prospects" in out
    assert (out_dir / "academy-growth.html").exists()


def test_online_checklist_changes_nothing(fake_env):
    before = sorted(p.as_posix() for p in fake_env.root.rglob("*"))
    code, out = run(["online-checklist"])
    assert code == 0 and "Ultimate Team" in out and "-dataPath" in out
    assert sorted(p.as_posix() for p in fake_env.root.rglob("*")) == before


def test_launch_without_fmm_exe(fake_env):
    code, out = run(["--ledger", str(fake_env.ledger_path), "launch"])
    assert code == 0 and "fmm_exe" in out


def test_rescan_cli(fake_env):
    (fake_env.mods / "optimization.fifamod").write_bytes(b"opt-v2")
    code, out = run(["--ledger", str(fake_env.ledger_path), "rescan", "--dry-run"])
    assert code == 0 and "FILE CHANGED" in out
