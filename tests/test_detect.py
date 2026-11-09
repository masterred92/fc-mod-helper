import json
import os
from pathlib import Path

from fcmh import detect


class FakeProbe(detect.Probe):
    """Fake drives, registry and environment rooted in a temp folder."""

    def __init__(self, root: Path, registry=None, drives=None, env=None):
        self.root = root
        self._registry = registry or []
        self._drives = drives or []
        self._env = env or {}

    def env(self, name):
        return self._env.get(name)

    def drives(self):
        return list(self._drives)

    def registry_values(self):
        return list(self._registry)


def make_game(folder: Path, exe="FC26.exe") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / exe).write_bytes(b"fake")
    return folder


def base_env(tmp_path):
    profile = tmp_path / "Users" / "player"
    for sub in ("Downloads", "Desktop", "Documents"):
        (profile / sub).mkdir(parents=True)
    pf = tmp_path / "Program Files"
    pf86 = tmp_path / "Program Files (x86)"
    pf.mkdir()
    pf86.mkdir()
    lad = profile / "AppData" / "Local"
    lad.mkdir(parents=True)
    return {"USERPROFILE": str(profile), "ProgramFiles": str(pf), "ProgramFiles(x86)": str(pf86),
            "LOCALAPPDATA": str(lad), "ProgramData": str(tmp_path / "ProgramData")}


def test_finds_ea_app_install(tmp_path):
    env = base_env(tmp_path)
    game = make_game(Path(env["ProgramFiles"]) / "EA Games" / "EA SPORTS FC 26")
    found = detect.find_games(FakeProbe(tmp_path, env=env))
    assert [(g.game, g.path, g.source) for g in found] == [("fc26", game, "EA app")]


def test_finds_registry_install_on_other_drive(tmp_path):
    env = base_env(tmp_path)
    game = make_game(tmp_path / "D" / "Games" / "FC27", exe="FC27.exe")
    registry = [(r"HKLM\SOFTWARE\WOW6432Node\EA Sports\EA SPORTS FC 27", "Install Dir", str(game))]
    found = detect.find_games(FakeProbe(tmp_path, registry=registry, env=env))
    assert found[0].game == "fc27" and found[0].path == game and found[0].source == "registry"


def test_uninstall_entry_and_bad_registry_value(tmp_path):
    env = base_env(tmp_path)
    game = make_game(tmp_path / "E" / "FC")
    registry = [
        (r"HKLM\...\Uninstall\{x}", "EA SPORTS FC 26", str(game)),
        (r"HKLM\SOFTWARE\EA Sports\EA SPORTS FC 26", "Install Dir", str(tmp_path / "gone")),
    ]
    found = detect.find_games(FakeProbe(tmp_path, registry=registry, env=env))
    assert [g.path for g in found] == [game]


def test_steam_library_from_vdf(tmp_path):
    env = base_env(tmp_path)
    steam = tmp_path / "Steam"
    library = tmp_path / "G" / "SteamLibrary"
    (steam / "steamapps").mkdir(parents=True)
    escaped = str(library).replace("\\", "\\\\")
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n "0"\n {\n  "path"  "%s"\n }\n}\n' % escaped)
    game = make_game(library / "steamapps" / "common" / "EA SPORTS FC 26")
    registry = [(r"HKCU\SOFTWARE\Valve\Steam", "SteamPath", str(steam))]
    found = detect.find_games(FakeProbe(tmp_path, registry=registry, env=env))
    assert found and found[0].path == game and found[0].source == "Steam"


def test_epic_manifest(tmp_path):
    env = base_env(tmp_path)
    game = make_game(tmp_path / "Epic" / "EASPORTSFC26")
    manifests = Path(env["ProgramData"]) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    manifests.mkdir(parents=True)
    (manifests / "abc.item").write_text(json.dumps({"DisplayName": "EA SPORTS FC 26", "InstallLocation": str(game)}))
    (manifests / "broken.item").write_text("{nope")
    found = detect.find_games(FakeProbe(tmp_path, env=env))
    assert found[0].path == game and found[0].source == "Epic"


def test_no_games(tmp_path):
    assert detect.find_games(FakeProbe(tmp_path, env=base_env(tmp_path))) == []


def test_finds_newest_mod_manager(tmp_path):
    env = base_env(tmp_path)
    old = Path(env["USERPROFILE"]) / "Desktop" / "FMM old" / "FIFA Mod Manager.exe"
    new = Path(env["USERPROFILE"]) / "Downloads" / "FIFA Mod Manager v2.2.0" / "FIFA Mod Manager.exe"
    for exe in (old, new):
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"x")
    os.utime(old, (1_000_000, 1_000_000))
    assert detect.find_mod_manager(FakeProbe(tmp_path, env=env)) == new


def test_mod_manager_missing(tmp_path):
    assert detect.find_mod_manager(FakeProbe(tmp_path, env=base_env(tmp_path))) is None


def test_live_editor_on_drive_and_in_downloads(tmp_path):
    env = base_env(tmp_path)
    drive = tmp_path / "C"
    le = drive / "FC 26 Live Editor"
    (le / "lua").mkdir(parents=True)
    assert detect.find_live_editor(FakeProbe(tmp_path, env=env, drives=[drive]), "fc26") == le
    other = Path(env["USERPROFILE"]) / "Downloads" / "FC 26 Live Editor v26.3.6"
    (other / "lua").mkdir(parents=True)
    assert detect.find_live_editor(FakeProbe(tmp_path, env=env), "fc26") == other
    assert detect.find_live_editor(FakeProbe(tmp_path, env=env), "fc27") is None


def test_settings_and_temp(tmp_path):
    env = base_env(tmp_path)
    probe = FakeProbe(tmp_path, env=env)
    assert detect.find_settings_dir(probe, "fc26") is None
    docs = Path(env["USERPROFILE"]) / "Documents" / "FC 26" / "settings"
    docs.mkdir(parents=True)
    assert detect.find_settings_dir(probe, "fc26") == docs
    local = Path(env["LOCALAPPDATA"]) / "EA SPORTS FC 26" / "settings"
    local.mkdir(parents=True)
    assert detect.find_settings_dir(probe, "fc26") == local  # AppData wins
    assert detect.find_temp_dir(probe, "fc26") == Path(env["LOCALAPPDATA"]) / "Temp" / "EA SPORTS FC26"


def test_detect_all(tmp_path):
    env = base_env(tmp_path)
    make_game(Path(env["ProgramFiles"]) / "EA Games" / "EA SPORTS FC 26")
    result = detect.detect_all(FakeProbe(tmp_path, env=env))
    assert result.games[0].game == "fc26"
    assert result.mod_manager_exe is None and result.temp_dir is not None


def test_real_probe_is_harmless_off_windows():
    probe = detect.Probe()
    if os.name != "nt":
        assert probe.registry_values() == [] and probe.drives() == []
