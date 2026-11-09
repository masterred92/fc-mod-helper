"""Runs src/fcmh/lua/fcmh_scout_preview.lua against a mock of the Live Editor API.

Proves the script's logic (read-only, pcall-wrapped, CSV shape, fallback dump),
not that the real game stores scouted players exactly like this.
"""

import csv
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")
try:
    from lupa import lua54 as lua_module
except ImportError:  # pragma: no cover
    lua_module = lupa

from fcmh import scouting
from test_lua_export import MOCK as BASE_MOCK

SCRIPT = Path(__file__).resolve().parents[1] / "src" / "fcmh" / "lua" / "fcmh_scout_preview.lua"

SCOUT_MOCK = r"""
local function make_table(rows)
    local t = { rows = rows, cursor = 0, writes = 0 }
    function t:GetFirstRecord() self.cursor = 1; return (#self.rows > 0) and 1 or 0 end
    function t:GetNextValidRecord()
        self.cursor = self.cursor + 1
        if self.cursor <= #self.rows then return self.cursor end
        return 0
    end
    function t:GetRecordFieldValue(rec, name)
        local v = self.rows[rec][name]
        if v == nil then error("no field " .. name) end
        return v
    end
    function t:SetRecordFieldValue() WRITES = (WRITES or 0) + 1 end
    return t
end

local P = 1048576 -- Technical bit in the FC 26 layout
local T = {
    players = make_table({
        { playerid = 460001, birthdate = 20110315, overallrating = 55, potential = 88, nationality = 54,
          preferredposition1 = 25, preferredposition2 = 27, preferredposition3 = -1, preferredposition4 = -1,
          trait1 = 1 | P, icontrait1 = 1 | 2, trait2 = 64, icontrait2 = 0 },
        { playerid = 460002, birthdate = 20090101, overallrating = 62, potential = 79, nationality = 14,
          preferredposition1 = 5, preferredposition2 = -1, preferredposition3 = -1, preferredposition4 = -1,
          trait1 = 0, icontrait1 = 0, trait2 = 0, icontrait2 = 0 },
        { playerid = 460003, birthdate = 20100601, overallrating = 58, potential = 71, nationality = 54,
          preferredposition1 = 14, preferredposition2 = -1, preferredposition3 = -1, preferredposition4 = -1,
          trait1 = 1 << 30, icontrait1 = 0, trait2 = 0, icontrait2 = 0 },
        { playerid = 1001, birthdate = 20000101, overallrating = 80, potential = 82, nationality = 14,
          preferredposition1 = 25, preferredposition2 = -1, preferredposition3 = -1, preferredposition4 = -1,
          trait1 = 0, icontrait1 = 0, trait2 = 0, icontrait2 = 0 },
    }),
    career_youthplayers = make_table(MOCK_YOUTH_ROWS),
    teamplayerlinks = make_table({ { playerid = 460003, teamid = 9001 }, { playerid = 1001, teamid = 10 } }),
    nations = make_table({ { nationid = 54, nationname = "Brazil" }, { nationid = 14, nationname = "England" } }),
    career_scouts = make_table({ { scoutid = 7, firstname = "Ana", lastname = "Silva" } }),
    career_scoutmission = make_table({ { scoutid = 7, nationality = 54, playertype = 1 } }),
}
function LE.db:GetTable(name)
    local t = T[name]
    if t == nil then error("unknown table " .. name) end
    return t
end
function GetTeamIdFromPlayerId(id) return 0 end
function GetPlayerPrimaryPositionName(p)
    local names = { [25] = "ST", [27] = "LW", [14] = "CM", [5] = "CB" }
    return names[p] or "INVALID"
end
package.preload["imports/other/playstyles_enum"] = function()
    ENUM_PLAYSTYLE1_FINESSE_SHOT = 1
    ENUM_PLAYSTYLE1_CHIP_SHOT = 2
    ENUM_PLAYSTYLE1_TECHNICAL = 1048576
    ENUM_PLAYSTYLE2_CAREER_SOLID_PLAYER = 64
    return true
end
"""

DEFAULT_YOUTH = """{
    { playerid = 460001, playertier = 3, potentialvariance = 4, swinglowpotential = -3, monthsinsquad = 0, playertype = 1 },
    { playerid = 460001, playertier = 2, potentialvariance = 6, swinglowpotential = 2, monthsinsquad = 0, playertype = 1 },
    { playerid = 460002, playertier = 1, potentialvariance = 2, swinglowpotential = 0, monthsinsquad = 0, playertype = 2 },
    { playerid = 460003, playertier = 1, potentialvariance = 1, swinglowpotential = 0, monthsinsquad = 5, playertype = 1 },
}"""


def run(tmp_path, *, in_cm=True, youth=DEFAULT_YOUTH, extra=""):
    runtime = lua_module.LuaRuntime()
    g = runtime.globals()
    g.MOCK_IN_CM = in_cm
    g.MOCK_HAS_YOUTH = False
    g.FCMH_OUTPUT_DIR = str(tmp_path)
    runtime.execute(BASE_MOCK)
    runtime.execute("MOCK_YOUTH_ROWS = " + youth)
    runtime.execute(SCOUT_MOCK + extra)
    runtime.execute(SCRIPT.read_text(encoding="utf-8"))
    logs = [g.LOGS[i] for i in range(1, len(g.LOGS) + 1)]
    return g.FCMH_LAST_RESULT, logs, g.LAST_BOX, g.WRITES


def rows_of(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return {r["playerid"]: r for r in csv.DictReader(handle)}


def test_exports_scouted_players(tmp_path):
    result, logs, box, writes = run(tmp_path)
    assert result.ok, result.error
    assert writes is None  # read-only: never called SetRecordFieldValue
    path = Path(result.path)
    assert path.name == "scout_2026-08-01.csv"
    rows = rows_of(path)
    assert set(rows) == {"460001", "460002", "460003"}
    star = rows["460001"]
    assert star["age"] == "15" and star["potential"] == "88" and star["ovr"] == "55"
    assert star["positions"] == "ST LW" and star["nationality"] == "Brazil"
    assert star["playstyles_plus"] == "Chip Shot; Finesse Shot"
    assert star["playstyles"] == "Technical"
    assert star["traits"] == "Solid Player"
    assert star["pot_swing_low"] == "-3" and star["pot_variance"] == "6"  # widest view of 2 rows
    assert star["status"] == "not signed (guess)"
    assert star["scout_report"] == "Ana Silva in Brazil"
    assert rows["460003"]["status"] == "signed (guess)"
    assert rows["460003"]["playstyles"] == "Style 1.30"  # unknown bit kept as a raw id
    assert result.pending == 2
    assert box == "FC Mod Helper: Scout preview"


def test_csv_loads_in_the_app(tmp_path):
    result, *_ = run(tmp_path)
    players = scouting.load_csv(Path(result.path))
    assert [p.name for p in players][0] == "Player 460001"
    assert players[0].potential == 88 and players[0].stars == 5.0


def test_old_playstyle_names_fall_back_to_raw_ids(tmp_path):
    extra = """
package.preload["imports/other/playstyles_enum"] = function()
    ENUM_PLAYSTYLE1_FINESSE_SHOT = 1
    ENUM_PLAYSTYLE1_TECHNICAL = 65536
    return true
end
"""
    result, logs, *_ = run(tmp_path, extra=extra)
    assert result.ok
    assert rows_of(result.path)["460001"]["playstyles_plus"] == "Style 1.0; Style 1.1"
    assert any("older game" in line for line in logs)


def test_empty_youth_table_writes_table_list(tmp_path):
    result, logs, box, _ = run(tmp_path, youth="{}")
    assert not result.ok
    assert "couldn't find your scouted youth players" in result.error
    assert "traceback" not in result.error.lower()
    dump = tmp_path / "scout_2026-08-01_tables.txt"
    text = dump.read_text()
    assert "career_youthplayers" in text and "career_scoutmission" in text
    assert box == "FC Mod Helper: Scout preview didn't work"
    assert not list(tmp_path.glob("*.csv"))


def test_missing_youth_table_with_legacy_table_list(tmp_path):
    extra = """
T.career_youthplayers = nil
function GetDBTablesNames() return { "players", "career_youthplayers_v2", "teams" } end
function GetDBTableFields(name) return { { name = "playerid" }, { name = "pot" } } end
"""
    result, *_ = run(tmp_path, extra=extra)
    assert not result.ok
    text = (tmp_path / "scout_2026-08-01_tables.txt").read_text()
    assert "career_youthplayers_v2 columns: playerid, pot" in text
    assert "teams columns" not in text


def test_not_in_career_mode(tmp_path):
    result, _, box, _ = run(tmp_path, in_cm=False)
    assert not result.ok and "Career save" in result.error
    assert not list(tmp_path.iterdir())


def test_script_crash_is_caught(tmp_path):
    extra = """
function GetCurrentDate() error("boom") end
T.players = nil
"""
    result, *_ = run(tmp_path, extra=extra)
    assert not result.ok
    assert "players" in result.error


def test_lua_folder_copy_matches_the_app_copy():
    copy = Path(__file__).resolve().parents[1] / "lua" / "fcmh_scout_preview.lua"
    assert copy.read_text(encoding="utf-8") == SCRIPT.read_text(encoding="utf-8")


def test_months_in_academy_counts_as_signed(tmp_path):
    youth = """{
    { playerid = 460001, playertier = 3, potentialvariance = 4, swinglowpotential = -3, monthsinsquad = 0, playertype = 1 },
    { playerid = 460002, playertier = 1, potentialvariance = 2, swinglowpotential = 0, monthsinsquad = 3, playertype = 2 },
}"""
    result, *_ = run(tmp_path, youth=youth)
    rows = rows_of(result.path)
    assert rows["460002"]["status"] == "signed (guess)"
    assert rows["460001"]["status"] == "not signed (guess)"
    assert result.pending == 1
