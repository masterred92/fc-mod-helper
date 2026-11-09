import json
import os
import time
from pathlib import Path

from fcmh import app_logic as logic
from fcmh import scouting
from conftest import FIXTURES

CSV = FIXTURES / "scouting" / "scout_2026-09-01.csv"


def by_id(players):
    return {p.playerid: p for p in players}


def test_star_thresholds():
    g = scouting.default_grades()
    expected = {99: 5, 85: 5, 84: 4.5, 80: 4.5, 79: 4, 75: 4, 74: 3.5, 70: 3.5, 69: 3, 65: 3,
                64: 2.5, 60: 2.5, 59: 2, 55: 2, 54: 1.5, 50: 1.5, 49: 1, 30: 1}
    for pot, stars in expected.items():
        assert scouting.stars_for(pot, g) == stars, pot
    assert scouting.stars_for(None, g) == 0
    assert scouting.star_text(4.5) == "\u2605\u2605\u2605\u2605\u00bd"
    assert scouting.star_text(3) == "\u2605\u2605\u2605\u2606\u2606"


def test_load_and_flag():
    players = scouting.load_csv(CSV)
    assert players[0].name == "Example Striker"  # best score first
    p = by_id(players)
    star = p[460101]
    assert star.sign_him and star.stars == 5
    assert star.reason == "Potential 88, age 15, 2 PlayStyles+"
    assert star.playstyles_plus == ["Finesse Shot", "Chip Shot"]
    assert star.traits == ["Solid Player"]
    # signed players never get the badge, even with the best potential
    assert p[460105].signed and not p[460105].sign_him
    # young + PlayStyle+ beats an older player with similar potential
    assert p[460103].sign_him and p[460103].reason == "Potential 82, age 14, 1 PlayStyle+"
    assert sum(x.sign_him for x in players) == 3
    assert not p[460104].sign_him
    assert p[460106].name == 'Comma, Quote "Kid"'


def test_min_potential_blocks_badge():
    g = scouting.default_grades()
    g["sign_him"]["min_potential"] = 86
    players = scouting.load_csv(CSV, g)
    assert [x.playerid for x in players if x.sign_him] == [460101]


def test_edited_grades_file(tmp_path):
    path = scouting.ensure_grades_file(tmp_path)
    data = json.loads(path.read_text())
    data["stars"] = [{"min_potential": 90, "stars": 5}, {"min_potential": 0, "stars": 2}]
    data["sign_him"]["how_many"] = 1
    path.write_text(json.dumps(data))
    g = scouting.load_grades(tmp_path)
    players = scouting.load_csv(CSV, g)
    assert by_id(players)[460101].stars == 2
    assert sum(x.sign_him for x in players) == 1
    # a broken file falls back to the defaults
    path.write_text("{not json")
    assert scouting.load_grades(tmp_path)["sign_him"]["how_many"] == 3
    # never overwrites an edited file
    path.write_text('{"stars": []}')
    scouting.ensure_grades_file(tmp_path)
    assert path.read_text() == '{"stars": []}'


def test_range_guess():
    g = scouting.default_grades()
    assert scouting.range_guess(88, 3, g) == (84, 92)
    assert scouting.range_guess(88, 9, g) == (86, 90)  # clamps to the last entry
    assert scouting.range_guess(88, None, g) is None


def test_newest_csv(tmp_path):
    old = tmp_path / "scout_2026-08-01.csv"
    new = tmp_path / "scout_2026-07-01.csv"
    old.write_text("x")
    new.write_text("y")
    os.utime(old, (time.time() - 100, time.time() - 100))
    assert scouting.newest_csv([tmp_path]) == new
    assert scouting.newest_csv([tmp_path / "missing"]) is None


def test_html_export(tmp_path):
    players = scouting.load_csv(CSV)
    page = scouting.write_html(players, tmp_path / "out.html", source=CSV.name).read_text()
    assert "SIGN HIM" in page and "Example Striker" in page
    assert "Comma, Quote &quot;Kid&quot;" in page
    assert "7 players not signed yet" in page
    assert 'class="chip plus"' in page


def test_scout_preview_flow(fake_env):
    ledger = fake_env.load()
    le = fake_env.root / "FC 26 Live Editor"
    (le / "lua").mkdir(parents=True)
    ledger.paths["live_editor_dir"] = str(le)
    ledger.save()

    result = logic.scout_preview(ledger)
    assert "No scout report yet" in result.sentence
    script = le / "lua" / logic.SCOUT_LUA_NAME
    assert script.exists()
    folder = logic.scouting_dir(ledger)
    assert folder == fake_env.profile / "Documents" / "FC Mod Helper" / "Scouting"
    assert f'local OUTPUT_DIR = "{str(folder).replace(chr(92), chr(92) * 2)}"' in script.read_text()
    assert (folder / "scout-grades.json").exists()

    # the script left its file on the Desktop: it gets picked up
    desktop = fake_env.profile / "Desktop"
    desktop.mkdir()
    (desktop / CSV.name).write_bytes(CSV.read_bytes())
    result = logic.scout_preview(ledger)
    assert result.csv == folder / CSV.name
    assert result.sentence == "7 players are waiting to be signed. 3 marked 'Sign him'."
    html = logic.scout_export_html(ledger, result)
    assert html.name == "scout_2026-09-01.html" and html.exists()


def test_table_dump_is_reported(fake_env):
    ledger = fake_env.load()
    folder = logic.scouting_dir(ledger)
    (folder / "scout_2026-09-02_tables.txt").write_text("tables")
    result = logic.scout_preview(ledger)
    assert result.table_dump is not None and "send that file" in result.sentence


def test_fc27_is_coming_soon(fake_env):
    ledger = fake_env.load()
    ledger.game = "fc27"
    assert "coming soon" in logic.scout_setup(ledger).sentence
