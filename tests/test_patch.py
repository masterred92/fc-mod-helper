from pathlib import Path

import pytest
from conftest import Recorder, no_detect

from fcmh import patch


def test_dry_run_changes_nothing(fake_env):
    rec = Recorder()
    ledger = fake_env.load()
    before = fake_env.ledger_path.read_text()
    result = patch.post_patch(ledger, rec.ui, new_tu="1.6.7", dry_run=True, detector=no_detect)
    assert (fake_env.install / "FIFAModData").exists()
    assert fake_env.temp.exists()
    assert fake_env.ledger_path.read_text() == before
    assert rec.opened == []
    assert "would delete fifamoddata_dir" in rec.text
    assert result["new_build"] == "1.6.7"


def test_real_run_with_confirmation(fake_env):
    rec = Recorder(assume_yes=True)
    ledger = fake_env.load()
    result = patch.post_patch(ledger, rec.ui, new_tu="v1.6.7", detector=no_detect)
    assert not (fake_env.install / "FIFAModData").exists()
    assert not fake_env.temp.exists()
    assert set(result["deleted"]) == {"fifamoddata_dir", "temp_dir"}
    assert sorted(rec.opened) == ["https://example.invalid/opt", "https://example.invalid/redux"]
    assert fake_env.load().current_build == "1.6.7"
    # Career saves are never touched by the wizard
    assert (fake_env.settings / "CmMgrTest01").exists()


def test_declining_keeps_folders(fake_env):
    rec = Recorder(answers=["n", "n"])
    patch.post_patch(fake_env.load(), rec.ui, new_tu="1.6.7", open_pages=False, detector=no_detect)
    assert (fake_env.install / "FIFAModData").exists()
    assert fake_env.temp.exists()
    assert rec.opened == []


def test_asks_for_tu_when_detection_fails(fake_env):
    rec = Recorder(answers=["1.6.8"], assume_yes=False)
    rec.answers += ["n", "n"]
    result = patch.post_patch(fake_env.load(), rec.ui, dry_run=False, open_pages=False, detector=no_detect)
    assert result["new_build"] == "1.6.8"


@pytest.mark.parametrize("key,path", [
    ("fifamoddata_dir", "Games/EA SPORTS FC 26"),
    ("temp_dir", "Temp"),
    ("temp_dir", "Somewhere/EA SPORTS FC26"),
    ("editor_cache_file", "Caches/settings.json"),
    ("settings_dir", "LocalAppData/EA SPORTS FC 26/settings"),
])
def test_refuses_unexpected_targets(tmp_path, key, path):
    with pytest.raises(patch.UnsafeDeleteError):
        patch.check_safe_target(key, tmp_path / path)


def test_refuses_home_and_root():
    with pytest.raises(patch.UnsafeDeleteError):
        patch.check_safe_target("fifamoddata_dir", Path.home())
    with pytest.raises(patch.UnsafeDeleteError):
        patch.check_safe_target("fifamoddata_dir", Path(Path.home().anchor))


def test_misconfigured_path_is_skipped_not_deleted(fake_env):
    ledger = fake_env.load()
    ledger.paths["temp_dir"] = str(fake_env.settings)  # wrong on purpose
    rec = Recorder(assume_yes=True)
    patch.post_patch(ledger, rec.ui, new_tu="1.6.6", open_pages=False, detector=no_detect)
    assert (fake_env.settings / "CmMgrTest01").exists()
    assert "Refusing to delete" in rec.text


def test_rescan_detects_update_and_repins(fake_env):
    ledger = fake_env.load()
    ledger.current_build = "1.6.7"
    (fake_env.mods / "youth-academy-redux.fifamod").write_bytes(b"redux-v2")
    results = {r.name: r.status for r in patch.rescan(ledger)}
    assert results == {"Youth Academy Redux": "changed", "Optimization Overhaul": "unchanged"}
    rec = Recorder(answers=["y"])
    updated = patch.apply_rescan(ledger, patch.rescan(ledger), rec.ui, dry_run=False)
    assert updated == 1
    redux = ledger.find_mod("Youth Academy Redux")
    assert redux.pinned_tu == "1.6.7"
    assert ledger.find_mod("Optimization Overhaul").pinned_tu == "1.6.6"


def test_editor_cache_only_when_asked(fake_env):
    cache = fake_env.lad / "FIFA Editor Tool" / "Caches" / "fc26-modding.cache"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"c")
    patch.post_patch(fake_env.load(), Recorder(assume_yes=True).ui, new_tu="1.6.6", open_pages=False, detector=no_detect)
    assert cache.exists()
    patch.post_patch(fake_env.load(), Recorder(assume_yes=True).ui, new_tu="1.6.6", open_pages=False,
                     include_editor_cache=True, detector=no_detect)
    assert not cache.exists()
