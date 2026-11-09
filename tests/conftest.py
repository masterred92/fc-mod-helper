import json
from pathlib import Path

import pytest

from fcmh.ledger import Ledger, Mod, sha256_file
from fcmh.ui import UI

FIXTURES = Path(__file__).parent / "fixtures"


class Recorder:
    """A UI that records output and answers prompts from a list."""

    def __init__(self, answers=None, assume_yes=False):
        self.lines = []
        self.opened = []
        self.answers = list(answers or [])
        self.ui = UI(out=self.lines.append, ask=self._ask, open_url=self.opened.append, assume_yes=assume_yes)

    def _ask(self, prompt):
        self.lines.append(prompt)
        return self.answers.pop(0) if self.answers else ""

    @property
    def text(self):
        return "\n".join(self.lines)


@pytest.fixture
def recorder():
    return Recorder()


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """A fake Windows-like layout under tmp_path. Nothing real is touched."""
    lad = tmp_path / "LocalAppData"
    profile = tmp_path / "Profile"
    roaming = tmp_path / "Roaming"
    for p in (lad, profile, roaming):
        p.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(lad))
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.delenv("FCMH_LEDGER", raising=False)

    install = tmp_path / "Games" / "EA SPORTS FC 26"
    (install / "FIFAModData" / "Data").mkdir(parents=True)
    (install / "FIFAModData" / "Data" / "generated.bin").write_bytes(b"x" * 100)
    (install / "FC26.exe").write_bytes(b"not a real exe")

    temp = lad / "Temp" / "EA SPORTS FC26"
    temp.mkdir(parents=True)
    (temp / "shadercache.tmp").write_text("cache")

    settings = lad / "EA SPORTS FC 26" / "settings"
    settings.mkdir(parents=True)
    (settings / "CmMgrTest01").write_bytes(b"career-save-v1")
    (settings / "Squads_test").write_bytes(b"squads")

    fmm = tmp_path / "Modding" / "FIFA Mod Manager"
    (fmm / "Profiles").mkdir(parents=True)
    (fmm / "Profiles" / "Career.json").write_text(json.dumps({"mods": ["a", "b"]}))

    mods = tmp_path / "Modding" / "mods"
    mods.mkdir()
    (mods / "youth-academy-redux.fifamod").write_bytes(b"redux-v1")
    (mods / "kiarika-career-overhaul.fifamod").write_bytes(b"kiarika-v1")
    (mods / "optimization.fifamod").write_bytes(b"opt-v1")

    ledger_path = roaming / "fc-mod-helper" / "ledger.json"
    ledger = Ledger(game="fc26", install_path=str(install), current_build="1.6.6",
                    paths={"fmm_dir": str(fmm)})
    ledger.mods = [
        Mod(name="Youth Academy Redux", file=str(mods / "youth-academy-redux.fifamod"), pinned_tu="1.6.6",
            author_url="https://example.invalid/redux", sha256=sha256_file(mods / "youth-academy-redux.fifamod")),
        Mod(name="Optimization Overhaul", file=str(mods / "optimization.fifamod"), pinned_tu="1.6.6",
            author_url="https://example.invalid/opt", sha256=sha256_file(mods / "optimization.fifamod")),
    ]
    ledger.save(ledger_path)

    class Env:
        pass

    env = Env()
    env.root, env.lad, env.profile, env.install, env.temp = tmp_path, lad, profile, install, temp
    env.settings, env.fmm, env.mods, env.ledger_path = settings, fmm, mods, ledger_path
    env.load = lambda: Ledger.load(ledger_path)
    return env


def no_detect(game, install):
    return {"exe": "", "exe_version": None, "tu": None, "message": "detection skipped in tests"}
