import datetime as dt
import json
import zipfile

import pytest
from conftest import Recorder

from fcmh import backup


def sources(env):
    return {"saves": env.settings, "fmm": env.fmm}


def test_create_list_verify(fake_env, tmp_path):
    dest = tmp_path / "backups"
    path = backup.create_backup(sources(fake_env), dest, label="before TU 1.6.7!", game="fc26", build="1.6.6",
                                now=dt.datetime(2026, 11, 9, 12, 0, 0))
    assert path.name == "fcmh-backup-20261109-120000-before-TU-1-6-7.zip"
    manifest = backup.read_manifest(path)
    assert manifest["components"]["saves"]["status"] == "ok"
    assert {f["path"] for f in manifest["components"]["saves"]["files"]} == {"CmMgrTest01", "Squads_test"}
    assert backup.verify_backup(path) == []
    infos = backup.list_backups(dest)
    assert len(infos) == 1 and set(infos[0].components) == {"saves", "fmm"}


def test_same_second_does_not_overwrite(fake_env, tmp_path):
    now = dt.datetime(2026, 1, 1)
    a = backup.create_backup(sources(fake_env), tmp_path, now=now)
    b = backup.create_backup(sources(fake_env), tmp_path, now=now)
    assert a != b and a.exists() and b.exists()


def test_missing_component_recorded(fake_env, tmp_path):
    path = backup.create_backup({"moddata": tmp_path / "nope"}, tmp_path / "b")
    assert backup.read_manifest(path)["components"]["moddata"]["status"] == "missing"


def test_restore_takes_safety_backup_first(fake_env, tmp_path):
    dest = tmp_path / "backups"
    original = backup.create_backup(sources(fake_env), dest, now=dt.datetime(2026, 1, 1))
    # the save changes after the backup
    (fake_env.settings / "CmMgrTest01").write_bytes(b"career-save-v2")
    (fake_env.settings / "NewFile").write_bytes(b"new")
    rec = Recorder(assume_yes=True)
    result = backup.restore_backup(original, sources(fake_env), dest, rec.ui)
    assert (fake_env.settings / "CmMgrTest01").read_bytes() == b"career-save-v1"
    assert not (fake_env.settings / "NewFile").exists()
    safety = result["safety_backup"]
    with zipfile.ZipFile(safety) as z:
        assert z.read("saves/CmMgrTest01") == b"career-save-v2"
    assert "pre-restore" in safety.name


def test_restore_dry_run_and_cancel(fake_env, tmp_path):
    dest = tmp_path / "backups"
    path = backup.create_backup(sources(fake_env), dest)
    (fake_env.settings / "CmMgrTest01").write_bytes(b"changed")
    backup.restore_backup(path, sources(fake_env), dest, Recorder().ui, dry_run=True)
    backup.restore_backup(path, sources(fake_env), dest, Recorder(answers=["n"]).ui)
    assert (fake_env.settings / "CmMgrTest01").read_bytes() == b"changed"
    assert len(backup.list_backups(dest)) == 1


def test_tampered_backup_refused(fake_env, tmp_path):
    dest = tmp_path / "b"
    path = backup.create_backup(sources(fake_env), dest)
    tampered = dest / "fcmh-backup-20000101-000000.zip"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tampered, "w") as out:
        for item in src.infolist():
            data = src.read(item)
            out.writestr(item, b"evil" if item.filename == "saves/CmMgrTest01" else data)
    assert backup.verify_backup(tampered)
    with pytest.raises(backup.BackupError, match="verification"):
        backup.restore_backup(tampered, sources(fake_env), dest, Recorder(assume_yes=True).ui)


def test_zip_slip_rejected(tmp_path):
    evil = tmp_path / "fcmh-backup-20000101-000000.zip"
    manifest = {"components": {"saves": {"status": "ok", "files": [], "source": "x"}}}
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("saves/../../escape.txt", "boom")
    target = tmp_path / "restore" / "settings"
    with pytest.raises(backup.BackupError, match="Unsafe"):
        backup.restore_backup(evil, {"saves": target}, tmp_path / "b", Recorder(assume_yes=True).ui)
    assert not (tmp_path / "escape.txt").exists()


def test_not_a_backup(tmp_path):
    bogus = tmp_path / "fcmh-backup-20000101-000000.zip"
    bogus.write_bytes(b"not a zip")
    with pytest.raises(backup.BackupError):
        backup.read_manifest(bogus)
    assert backup.list_backups(tmp_path) == []
