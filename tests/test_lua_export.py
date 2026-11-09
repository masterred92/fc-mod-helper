"""Runs lua/fcmh_academy_export.lua against a small mock of the Live Editor API.

This proves the script's logic and error handling, not that the real Live Editor
exposes these exact fields. Needs the optional `lupa` package (pip install lupa).
"""

import csv
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")
try:
    from lupa import lua54 as lua_module
except ImportError:  # pragma: no cover
    lua_module = lupa

SCRIPT = Path(__file__).resolve().parents[1] / "lua" / "fcmh_academy_export.lua"

MOCK = r"""
-- Minimal Live Editor mock, shaped like the official example scripts use it.
local function make_table(rows)
    local t = { rows = rows, cursor = 0 }
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
    return t
end

DATE = {}
DATE.__index = DATE
function DATE:new() return setmetatable({ day = 0, month = 0, year = 0 }, DATE) end
-- test-only encoding: days = year*10000 + month*100 + day
function DATE:FromGregorianDays(d) self.year = d // 10000; self.month = (d // 100) % 100; self.day = d % 100 end

local tables = {
    players = make_table({
        { playerid = 1001, birthdate = 20100315, overallrating = 58, potential = 84, preferredposition1 = 25, trait1 = 5, icontrait1 = 0 },
        { playerid = 1002, birthdate = 19950101, overallrating = 80, potential = 81, preferredposition1 = 5, trait1 = 1, icontrait1 = 1 },
        { playerid = 1003, birthdate = 20050901, overallrating = 70, potential = 85, preferredposition1 = 14, trait1 = 0, icontrait1 = 0 },
        { playerid = 1004, birthdate = 20110101, overallrating = 50, potential = 90, preferredposition1 = 0, trait1 = 3, icontrait1 = 2 },
        { playerid = 9999, birthdate = 20090101, overallrating = 60, potential = 70, preferredposition1 = 3 },
    }),
}
if MOCK_HAS_YOUTH then
    tables.career_youthplayers = make_table({ { playerid = 1004 } })
end

LE = { db = {} }
function LE.db:GetTable(name)
    local t = tables[name]
    if t == nil then error("unknown table " .. name) end
    return t
end
LE_VERSION = "mock"
LOGS = {}
LOGGER = {}
function LOGGER:LogInfo(t) LOGS[#LOGS + 1] = "INFO " .. t end
function LOGGER:LogWarn(t) LOGS[#LOGS + 1] = "WARN " .. t end
function LOGGER:LogError(t) LOGS[#LOGS + 1] = "ERROR " .. t end
function MessageBox(title, text) LAST_BOX = title end
function IsInCM() return MOCK_IN_CM end
function GetCurrentDate() local d = DATE:new(); d.year = 2026; d.month = 8; d.day = 1; return d end
function GetUserSeniorTeamPlayerIDs() return { [1001] = true, [1002] = true, [1003] = true } end
function GetPlayerName(id) if id == 1003 then return 'Comma, "Quote"' end return "Player " .. id end
function GetTeamIdFromPlayerId(id) return 1 end
function GetTeamName(id) return "Example FC" end
function GetPlayerPrimaryPositionName(p) local names = { [25] = "ST", [14] = "CM", [5] = "CB", [0] = "GK" }; return names[p] end
package.preload["imports/career_mode/helpers"] = function() return true end
package.preload["imports/other/helpers"] = function() return true end
"""


def run_script(tmp_path, in_cm=True, has_youth=True):
    runtime = lua_module.LuaRuntime()
    g = runtime.globals()
    g.MOCK_IN_CM = in_cm
    g.MOCK_HAS_YOUTH = has_youth
    g.FCMH_OUTPUT_DIR = str(tmp_path)
    runtime.execute(MOCK)
    runtime.execute(SCRIPT.read_text(encoding="utf-8"))
    result = g.FCMH_LAST_RESULT
    logs = [g.LOGS[i] for i in range(1, len(g.LOGS) + 1)]
    return result, logs, g.LAST_BOX


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_export_with_youth_table(tmp_path):
    result, logs, box = run_script(tmp_path)
    assert result.ok, result.error
    path = Path(result.path)
    assert path.name == "fcmh_academy_2026-08-01.csv"
    rows = {r["playerid"]: r for r in read_rows(path)}
    assert set(rows) == {"1001", "1003", "1004"}  # 1002 is 31, 9999 isn't ours
    assert rows["1001"]["age"] == "16" and rows["1001"]["season"] == "2026/27"
    assert rows["1001"]["position"] == "ST" and rows["1001"]["playstyles_count"] == "2"
    assert rows["1003"]["age"] == "20" and rows["1003"]["name"] == 'Comma, "Quote"'
    assert rows["1004"]["source"] == "academy" and rows["1004"]["playstyles_plus_count"] == "1"
    assert box == "fcmh academy export"


def test_csv_feeds_growth_report(tmp_path):
    from fcmh import academy
    run_script(tmp_path)
    prospects = academy.merge(academy.collect([tmp_path]))
    assert len(prospects) == 3


def test_missing_youth_table_is_a_warning(tmp_path):
    result, logs, _ = run_script(tmp_path, has_youth=False)
    assert result.ok
    assert any(l.startswith("WARN") and "career_youthplayers" in l for l in logs)
    assert {r["playerid"] for r in read_rows(result.path)} == {"1001", "1003"}


def test_not_in_career_mode(tmp_path):
    result, logs, box = run_script(tmp_path, in_cm=False)
    assert not result.ok
    assert "Career save" in result.error
    assert box == "fcmh academy export failed"
    assert list(tmp_path.glob("*.csv")) == []
