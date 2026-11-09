import json
from pathlib import Path

import pytest

from fcmh.ledger import Ledger, LedgerError, Mod, normalize_tu

ROOT = Path(__file__).resolve().parents[1]


def test_normalize_tu():
    assert normalize_tu("v1.6.6") == "1.6.6"
    assert normalize_tu(" 1.6 ") == "1.6"
    assert normalize_tu("") is None
    assert normalize_tu(None) is None
    with pytest.raises(LedgerError):
        normalize_tu("latest")


def test_roundtrip(tmp_path):
    path = tmp_path / "l.json"
    ledger = Ledger(game="fc27", install_path="X", current_build="v1.0.1")
    ledger.add_mod(Mod(name="A", file="a.fifamod", pinned_tu="1.0.1", tags=["t"]))
    ledger.save(path)
    loaded = Ledger.load(path)
    assert loaded.game == "fc27"
    assert loaded.mods[0].name == "A" and loaded.mods[0].tags == ["t"]
    assert json.loads(path.read_text())["schema"] == 1


def test_duplicate_and_unknowns(tmp_path):
    with pytest.raises(LedgerError):
        Ledger.from_dict({"game": "fifa23"})
    with pytest.raises(LedgerError):
        Ledger.from_dict({"mods": [{"name": "A", "file": "a"}, {"name": "a", "file": "b"}]})
    with pytest.raises(LedgerError):
        Ledger.from_dict({"paths": {"nope": "x"}})
    ledger = Ledger()
    ledger.add_mod(Mod(name="A", file="a", pinned_tu=""))
    with pytest.raises(LedgerError):
        ledger.add_mod(Mod(name="a", file="b", pinned_tu=""))


def test_missing_and_bad_json(tmp_path):
    with pytest.raises(LedgerError, match="fcmh init"):
        Ledger.load(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    with pytest.raises(LedgerError, match="not valid JSON"):
        Ledger.load(bad)


def test_example_ledger_is_valid():
    ledger = Ledger.load(ROOT / "examples" / "ledger.example.json")
    assert ledger.game == "fc26"
    assert len(ledger.mods) == 2


def test_relative_mod_path(tmp_path):
    ledger = Ledger(location=tmp_path / "ledger.json")
    mod = Mod(name="A", file="mods/a.fifamod", pinned_tu="")
    assert ledger.mod_path(mod) == tmp_path / "mods" / "a.fifamod"
