import datetime as dt
import os
from pathlib import Path

import pytest
from conftest import FIXTURES, no_detect

from fcmh import app_logic as logic
from fcmh import backup
from fcmh.ledger import Ledger


@pytest.fixture
def app_env(fake_env, tmp_path):
    """fake_env plus a finished first-run setup."""
    home = tmp_path / "Profile" / "Documents" / "FC Mod Helper"
    exe = fake_env.fmm / "FIFA Mod Manager.exe"
    exe.write_bytes(b"x")
    ledger = logic.save_setup(fake_env.ledger_path, "fc26", fake_env.install, tu="1.6.6", exe_version=None,
                              mod_manager_exe=exe, settings_dir=fake_env.settings, temp_dir=fake_env.temp,
                              live_editor_dir=None, home=home)
    fake_env.home, fake_env.exe = home, exe
    fake_env.ledger = Ledger.load(fake_env.ledger_path)
    assert ledger.app["setup_done"]
    return fake_env


def yes(*_a):
    return True


def no(*_a):
    return False


# ---------------------------------------------------------------- setup
def test_setup_items_flags_missing():
    found = logic.detect.Detection()
    items = {i.key: i for i in logic.setup_items(found, None)}
    assert not items["game"].ok and not items["mod_manager"].ok
    assert items["live_editor"].optional


def test_setup_keeps_existing_mods_and_creates_folders(app_env):
    assert len(app_env.ledger.mods) == 2
    for sub in ("Backups", "Academy", "Mods"):
        assert (app_env.home / sub).is_dir()
    assert logic.load_ledger(app_env.ledger_path) is not None


def test_load_ledger_needs_setup(fake_env):
    assert logic.load_ledger(fake_env.ledger_path) is None  # ledger exists but setup never finished


# ---------------------------------------------------------------- status / play
def test_status_green(app_env):
    status = logic.status(app_env.ledger, no_detect)
    assert status.level == logic.GREEN and "2 mod(s) ready" in status.sentence
    assert "TU" not in status.sentence


def test_status_game_updated(app_env):
    detector = lambda g, i: {"tu": "1.6.7", "exe_version": "x"}
    status = logic.status(app_env.ledger, detector)
    assert status.level == logic.RED and status.fix == "game_updated"


def test_status_clash(app_env):
    logic.add_mod_files(app_env.ledger, [app_env.mods / "kiarika-career-overhaul.fifamod"])
    status = logic.status(app_env.ledger, no_detect)
    assert status.fix == "choose_clash" and len(status.detail) == 2


def test_status_missing_mod_and_fix(app_env):
    (app_env.mods / "optimization.fifamod").unlink()
    status = logic.status(app_env.ledger, no_detect)
    assert status.fix == "remove_missing"
    assert logic.remove_missing(app_env.ledger) == ["Optimization Overhaul"]


def test_status_without_mod_manager(app_env):
    app_env.exe.unlink()
    assert logic.status(app_env.ledger, no_detect).fix == "pick_mod_manager"


def test_play_safely_launches_and_backs_up(app_env):
    launched = []
    result = logic.play_safely(app_env.ledger, detector=no_detect, launcher=launched.append)
    assert result.ok and launched == [app_env.exe]
    assert result.backed_up is not None and result.backed_up.exists()
    # second time within 24h: no new backup
    again = logic.play_safely(app_env.ledger, detector=no_detect, launcher=launched.append)
    assert again.backed_up is None
    later = dt.datetime.now() + dt.timedelta(hours=25)
    assert logic.play_safely(app_env.ledger, detector=no_detect, launcher=launched.append, now=later).backed_up


def test_play_safely_blocks_with_one_sentence(app_env):
    launched = []
    app_env.ledger.find_mod("Optimization Overhaul").pinned_tu = "1.6.5"
    result = logic.play_safely(app_env.ledger, detector=no_detect, launcher=launched.append)
    assert not result.ok and launched == []
    assert result.status.fix == "game_updated" and result.status.sentence.count(".") >= 1


# ---------------------------------------------------------------- add mods
@pytest.mark.parametrize("filename,name,tags", [
    ("YouthAcademyRedux_v1.2.fifamod", "Youth Academy Redux", ["academy-overhaul"]),
    ("KIARIKA_Career_Mode_Overhaul_TU1.6.6.fifamod", "KIARIKA Career Mode Overhaul", ["academy-overhaul"]),
    ("Youth-Academy-Re-adjusted v3.fifamod", "Youth Academy Re-adjusted", ["academy-overhaul"]),
    ("anth_james_gameplay_fc26.fifamod", "Anth James Gameplay", ["gameplay-overhaul"]),
    ("TrueFoot.fifamod", "True Foot", ["gameplay-overhaul"]),
    ("KIARIKA Optimization Overhaul 1.6.6.fifamod", "KIARIKA Optimization Overhaul", ["performance"]),
    ("BetterRegenMinifaces.fifamod", "Better Regen Minifaces", []),
])
def test_guess_name_and_tags(filename, name, tags):
    assert logic.guess_name(filename) == name
    assert logic.guess_tags(filename) == tags


def test_add_many_files_with_clash_and_keep_one(app_env, tmp_path):
    downloads = tmp_path / "dl"
    downloads.mkdir()
    a = downloads / "Youth-Academy-Re-adjusted v3.fifamod"
    a.write_bytes(b"readj")
    b = downloads / "readme.txt"
    b.write_text("hi")
    result = logic.add_mod_files(app_env.ledger, [a, b, app_env.mods / "youth-academy-redux.fifamod"])
    assert result.added == ["Youth Academy Re-adjusted"]
    assert "readme.txt" in result.skipped and "youth-academy-redux.fifamod" in result.skipped
    assert (app_env.home / "Mods" / a.name).exists()  # copied into the watched Mods folder
    mod = app_env.ledger.find_mod("Youth Academy Re-adjusted")
    assert mod.pinned_tu == "1.6.6" and mod.tags == ["academy-overhaul"] and mod.author_url == ""
    assert result.clashes and set(result.clashes[0].mods) == {"Youth Academy Redux", "Youth Academy Re-adjusted"}
    off = logic.keep_only(app_env.ledger, "Youth Academy Redux", result.clashes[0].mods)
    assert off == ["Youth Academy Re-adjusted"]
    assert logic.status(app_env.ledger, no_detect).level == logic.GREEN


def test_set_mod_link(app_env):
    logic.set_mod_link(app_env.ledger, "Optimization Overhaul", " https://example.invalid/new ")
    assert Ledger.load(app_env.ledger_path).find_mod("Optimization Overhaul").author_url == "https://example.invalid/new"


# ---------------------------------------------------------------- game updated
def test_game_updated_flow(app_env):
    opened = []
    detector = lambda g, i: {"tu": "1.6.7", "exe_version": "1.0.140.1"}
    result = logic.game_updated(app_env.ledger, yes, open_url=opened.append, detector=detector)
    assert result.new_update == "1.6.7"
    assert set(result.cleaned) == {"fifamoddata_dir", "temp_dir"}
    assert not (app_env.install / "FIFAModData").exists()
    assert (app_env.settings / "CmMgrTest01").exists()  # never touches saves
    assert len(opened) == 2 and set(result.needs_update) == {"Youth Academy Redux", "Optimization Overhaul"}
    assert "game update 1.6.7" in result.sentence and "TU" not in result.sentence


def test_game_updated_no_means_nothing_deleted(app_env):
    opened = []
    result = logic.game_updated(app_env.ledger, no, open_url=opened.append, ask_update=lambda: "1.6.7",
                                detector=no_detect)
    assert result.cleaned == [] and opened == []
    assert (app_env.install / "FIFAModData").exists()
    assert result.new_update == "1.6.7"


def test_watch_mods_folder_repins_updates(app_env):
    ledger = app_env.ledger
    mods_dir = app_env.home / "Mods"
    first = logic.add_mod_files(ledger, [app_env.mods / "kiarika-career-overhaul.fifamod"])
    assert first.added
    ledger.current_build = "1.6.7"
    newer = mods_dir / "kiarika-career-overhaul_v2.fifamod"
    newer.write_bytes(b"kiarika-v2")
    unknown = mods_dir / "Brand New Kits.fifamod"
    unknown.write_bytes(b"kits")
    result = logic.watch_mods_folder(ledger)
    mod = ledger.find_mod(first.added[0])
    assert result.updated == [mod.name]
    assert mod.file == str(newer) and mod.pinned_tu == "1.6.7"
    assert result.new_files == [unknown]
    # nothing new the second time
    assert logic.watch_mods_folder(ledger).updated == []


def test_watch_same_file_overwritten(app_env):
    ledger = app_env.ledger
    added = logic.add_mod_files(ledger, [app_env.mods / "kiarika-career-overhaul.fifamod"]).added[0]
    ledger.current_build = "1.6.8"
    target = Path(ledger.find_mod(added).file)
    target.write_bytes(b"kiarika-v3")
    os.utime(target, (target.stat().st_atime + 5, target.stat().st_mtime + 5))  # a later download
    assert logic.watch_mods_folder(ledger).updated == [added]
    assert ledger.find_mod(added).pinned_tu == "1.6.8"


# ---------------------------------------------------------------- backups
def test_backup_and_restore_points(app_env):
    first = logic.backup_now(app_env.ledger, now=dt.datetime(2026, 11, 1, 9, 5))
    points = logic.restore_points(app_env.ledger)
    assert points[0].path == first and "1 November 2026" in points[0].text
    (app_env.settings / "CmMgrTest01").write_bytes(b"changed")
    assert logic.restore(app_env.ledger, first, no) == "Nothing changed."
    assert (app_env.settings / "CmMgrTest01").read_bytes() == b"changed"
    message = logic.restore(app_env.ledger, first, yes)
    assert "Done" in message
    assert (app_env.settings / "CmMgrTest01").read_bytes() == b"career-save-v1"
    labels = [p.text for p in logic.restore_points(app_env.ledger)]
    assert any("before a restore" in text for text in labels)


def test_backup_if_old(app_env):
    now = dt.datetime(2026, 11, 9, 12, 0)
    assert logic.backup_if_old(app_env.ledger, now) is not None
    assert logic.backup_if_old(app_env.ledger, now + dt.timedelta(hours=23)) is None
    assert logic.backup_if_old(app_env.ledger, now + dt.timedelta(hours=24, minutes=1)) is not None


# ---------------------------------------------------------------- academy
def test_academy_without_live_editor(app_env):
    result = logic.academy_setup(app_env.ledger)
    assert result.script_path is None and "Live Editor" in result.sentence


def test_academy_installs_script_and_builds_report(app_env, tmp_path):
    le = tmp_path / "FC 26 Live Editor"
    (le / "lua").mkdir(parents=True)
    app_env.ledger.paths["live_editor_dir"] = str(le)
    setup = logic.academy_setup(app_env.ledger)
    script = (le / "lua" / logic.LUA_NAME).read_text(encoding="utf-8")
    academy_dir = str(app_env.home / "Academy").replace("\\", "\\\\")
    assert f'local OUTPUT_DIR = "{academy_dir}"' in script
    assert "F9" in setup.sentence and "Lua Engine" in setup.sentence
    empty = logic.academy_report(app_env.ledger)
    assert empty.report is None and "No academy data yet" in empty.sentence
    # exports left on the Desktop are imported automatically
    desktop = app_env.profile / "Desktop"
    desktop.mkdir()
    for csv_file in (FIXTURES / "academy").glob("*.csv"):
        (desktop / csv_file.name).write_bytes(csv_file.read_bytes())
    report = logic.academy_report(app_env.ledger)
    assert report.imported == 3 and report.report.exists()
    html = report.report.read_text(encoding="utf-8")
    assert "&#9650; +11" in html and "<svg" in html and "<polyline" in html


def test_lua_copy_matches_packaged_source():
    text = logic.lua_source()
    assert "local OUTPUT_DIR = nil\n" in text
    assert logic.lua_with_output_dir(Path("D:/FC/academy")) != text


def test_risk_warning_and_online_steps_are_plain():
    assert "offline" in logic.RISK_WARNING.lower() and "Ultimate Team" in logic.RISK_WARNING
    assert 3 <= len(logic.ONLINE_STEPS) <= 6
    for text in [logic.RISK_WARNING, *logic.ONLINE_STEPS]:
        assert ".fifamod" not in text and " TU" not in text
