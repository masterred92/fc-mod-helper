import json

from fcmh.conflicts import find_clashes, load_rules
from fcmh.ledger import Mod


def mod(name, enabled=True, tags=(), file="x.fifamod"):
    return Mod(name=name, file=file, pinned_tu="1.6.6", enabled=enabled, tags=list(tags))


def test_bundled_rules_load():
    ids = {r["id"] for r in load_rules()}
    assert {"youth-academy-overhaul", "gameplay-overhaul"} <= ids


def test_academy_clash():
    clashes = find_clashes([mod("Youth Academy Redux"), mod("Youth Academy Re-adjusted"), mod("Kits")], load_rules())
    assert len(clashes) == 1
    assert clashes[0].rule_id == "youth-academy-overhaul"
    assert set(clashes[0].mods) == {"Youth Academy Redux", "Youth Academy Re-adjusted"}


def test_kiarika_and_redux_clash_by_filename():
    mods = [mod("Career overhaul", file=r"D:\mods\KIARIKA_Career_Mode_Overhaul_v3.fifamod"), mod("Youth Academy Redux")]
    assert [c.rule_id for c in find_clashes(mods, load_rules())] == ["youth-academy-overhaul"]


def test_gameplay_clash_and_disabled_ignored():
    rules = load_rules()
    assert find_clashes([mod("Anth James Gameplay"), mod("TrueFoot")], rules)[0].rule_id == "gameplay-overhaul"
    assert find_clashes([mod("Anth James Gameplay"), mod("TrueFoot", enabled=False)], rules) == []


def test_tags_match():
    clashes = find_clashes([mod("My academy A", tags=["academy-overhaul"]), mod("Youth Academy Redux")], load_rules())
    assert len(clashes) == 1


def test_custom_rules_file(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"rules": [{"id": "faces", "max_enabled": 1, "severity": "warning",
                                           "members": [{"patterns": ["face"]}]}]}))
    clashes = find_clashes([mod("Faces A"), mod("Faces B")], load_rules(path))
    assert clashes[0].rule_id == "faces" and clashes[0].severity == "warning"
