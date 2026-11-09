from fcmh import version


def test_tu_table_maps_known_build():
    assert version.tu_for_exe_version("fc26", "1.0.139.20381") == "1.6.6"
    assert version.tu_for_exe_version("fc26", "9.9.9.9") is None
    assert version.tu_for_exe_version("fc27", "1.0.139.20381") is None
    assert version.tu_for_exe_version("fc26", None) is None


def test_detect_missing_exe(tmp_path):
    info = version.detect("fc26", tmp_path)
    assert info["tu"] is None and "not found" in info["message"]


def test_detect_unreadable_exe(tmp_path, monkeypatch):
    (tmp_path / "FC26.exe").write_bytes(b"x")
    monkeypatch.setattr(version, "read_exe_version", lambda path: None)
    info = version.detect("fc26", tmp_path)
    assert "set-build" in info["message"]


def test_detect_maps_version(tmp_path, monkeypatch):
    (tmp_path / "FC26.exe").write_bytes(b"x")
    monkeypatch.setattr(version, "read_exe_version", lambda path: "1.0.138.57785")
    info = version.detect("fc26", tmp_path)
    assert info["tu"] == "1.6.5" and info["exe_version"] == "1.0.138.57785"
