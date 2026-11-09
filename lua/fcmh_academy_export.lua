--[[
fc-mod-helper: academy exporter for FC Live Editor (Lua API v2, Lua 5.4)

STATUS: UNTESTED IN-GAME. It was written against the public Live Editor docs and
the official example scripts, and tested only against a mock of the API. Please
run it once on a throwaway save first and check the CSV.

What it does (read-only, it never writes to the game database):
  * finds young players in your senior squad (age <= MAX_AGE)
  * optionally also reads the youth academy table (experimental, see YOUTH_TABLE)
  * writes one CSV per in-game date: fcmh_academy_YYYY-MM-DD.csv
Then run `fcmh academy report` to merge every CSV into a growth report.

How to run: start Career Mode with Live Editor, press F9 > Features > Lua Engine,
open this file and press Execute. Run it again whenever you want a snapshot
(for example at the start of each season and before each transfer window).

Uses only: LE.db:GetTable / GetFirstRecord / GetNextValidRecord / GetRecordFieldValue,
IsInCM, GetCurrentDate, DATE:new():FromGregorianDays, GetUserSeniorTeamPlayerIDs,
GetPlayerName, GetTeamIdFromPlayerId, GetTeamName, GetPlayerPrimaryPositionName,
LOGGER and MessageBox, as used by the official example scripts.
]]

---------------------------------------------------------------- settings
-- Players in your senior squad at or under this age are exported.
local MAX_AGE = 21

-- Folder for the CSVs. nil = your Desktop (same place the official export scripts use).
-- Example: local OUTPUT_DIR = "D:\\FC\\academy"
local OUTPUT_DIR = nil

-- EXPERIMENTAL: also read academy players from this database table, if it exists.
-- If the table name is wrong the script logs a warning and carries on.
-- Set to nil to switch it off.
local YOUTH_TABLE = "career_youthplayers"
---------------------------------------------------------------- end of settings

local SCRIPT = "fcmh_academy_export"
local SEP = package.config:sub(1, 1)

local function log(level, msg)
    local text = "[" .. SCRIPT .. "] " .. tostring(msg)
    if LOGGER then
        if level == "error" then LOGGER:LogError(text)
        elseif level == "warn" then LOGGER:LogWarn(text)
        else LOGGER:LogInfo(text) end
    else
        print(text)
    end
end

local function popup(title, msg)
    if type(MessageBox) == "function" then
        pcall(MessageBox, title, msg)
    end
end

local function try_require(name)
    local ok, err = pcall(require, name)
    if not ok then
        log("warn", "Could not load '" .. name .. "': " .. tostring(err))
    end
    return ok
end

local function need(name)
    if type(_G[name]) ~= "function" and type(_G[name]) ~= "table" then
        error("Live Editor helper '" .. name .. "' is missing. Is this Live Editor up to date, and are you in Career Mode?", 0)
    end
end

local function optional_call(fn_name, ...)
    local fn = _G[fn_name]
    if type(fn) ~= "function" then return nil end
    local ok, value = pcall(fn, ...)
    if ok then return value end
    return nil
end

local function csv_escape(value)
    if value == nil then return "" end
    local s = tostring(value)
    if s:find('[,"\r\n]') then
        s = '"' .. (s:gsub('"', '""')) .. '"'
    end
    return s
end

local function bit_count(value)
    local n = math.tointeger(value)
    if n == nil then return nil end
    n = n & 0xFFFFFFFF
    local count = 0
    while n ~= 0 do
        n = n & (n - 1)
        count = count + 1
    end
    return count
end

local function season_label(date)
    local start_year = date.year
    if date.month < 7 then start_year = date.year - 1 end
    return string.format("%d/%02d", start_year, (start_year + 1) % 100)
end

local function age_on(birthdate_days, today)
    if birthdate_days == nil or birthdate_days <= 0 then return nil end
    local born = DATE:new()
    born:FromGregorianDays(birthdate_days)
    local age = today.year - born.year
    if today.month < born.month or (today.month == born.month and today.day < born.day) then
        age = age - 1
    end
    return age
end

local function field(tbl, record, name)
    local ok, value = pcall(function() return tbl:GetRecordFieldValue(record, name) end)
    if ok then return value end
    return nil
end

local function read_youth_ids()
    local ids = {}
    if YOUTH_TABLE == nil then return ids, 0 end
    local ok, tbl = pcall(function() return LE.db:GetTable(YOUTH_TABLE) end)
    if not ok or tbl == nil then
        log("warn", "Youth table '" .. YOUTH_TABLE .. "' not available (" .. tostring(tbl) .. "). Exporting senior squad only.")
        return ids, 0
    end
    local count = 0
    local ok2, err = pcall(function()
        local record = tbl:GetFirstRecord()
        while record > 0 do
            local pid = field(tbl, record, "playerid")
            if pid and pid > 0 then
                ids[pid] = true
                count = count + 1
            end
            record = tbl:GetNextValidRecord()
        end
    end)
    if not ok2 then
        log("warn", "Reading youth table '" .. YOUTH_TABLE .. "' failed: " .. tostring(err))
    end
    return ids, count
end

local COLUMNS = {
    "export_date", "season", "source", "playerid", "name", "team", "age", "ovr", "pot",
    "position", "playstyles_bits", "playstyles_plus_bits", "playstyles_count", "playstyles_plus_count",
    "le_version",
}

local function main()
    try_require("imports/career_mode/helpers")
    try_require("imports/other/helpers")

    need("LE")
    need("IsInCM")
    if not IsInCM() then
        error("Load your Career save first, then run this script again.", 0)
    end
    need("GetCurrentDate")
    need("DATE")
    need("GetUserSeniorTeamPlayerIDs")

    local today = GetCurrentDate()
    local export_date = string.format("%04d-%02d-%02d", today.year, today.month, today.day)
    local season = season_label(today)

    local senior = GetUserSeniorTeamPlayerIDs() or {}
    local youth, youth_count = read_youth_ids()
    log("info", string.format("Youth table rows: %d", youth_count))

    local players = LE.db:GetTable("players")
    if players == nil then error("Could not open the 'players' table.", 0) end

    local rows = {}
    local record = players:GetFirstRecord()
    while record > 0 do
        local pid = field(players, record, "playerid")
        local source = nil
        if pid and youth[pid] then source = "academy"
        elseif pid and senior[pid] then source = "senior" end
        if source then
            local age = age_on(field(players, record, "birthdate"), today)
            if source == "academy" or (age ~= nil and age <= MAX_AGE) then
                local pos_id = field(players, record, "preferredposition1")
                local position = optional_call("GetPlayerPrimaryPositionName", pos_id) or pos_id
                local team_id = optional_call("GetTeamIdFromPlayerId", pid)
                local team = team_id and optional_call("GetTeamName", team_id) or ""
                local ps = field(players, record, "trait1")
                local psplus = field(players, record, "icontrait1")
                rows[#rows + 1] = {
                    export_date, season, source, pid,
                    optional_call("GetPlayerName", pid) or "",
                    team, age,
                    field(players, record, "overallrating"),
                    field(players, record, "potential"),
                    position, ps, psplus, bit_count(ps), bit_count(psplus),
                    LE_VERSION or "",
                }
            end
        end
        record = players:GetNextValidRecord()
    end

    local dir = OUTPUT_DIR or FCMH_OUTPUT_DIR
    if dir == nil then
        local profile = os.getenv("USERPROFILE")
        if profile == nil then error("USERPROFILE is not set; put a folder in OUTPUT_DIR at the top of the script.", 0) end
        dir = profile .. SEP .. "Desktop"
    end
    local path = dir .. SEP .. "fcmh_academy_" .. export_date .. ".csv"
    local file, open_err = io.open(path, "w")
    if file == nil then
        error("Can't write " .. path .. ": " .. tostring(open_err) .. ". Check OUTPUT_DIR exists.", 0)
    end
    file:write(table.concat(COLUMNS, ","), "\n")
    for _, row in ipairs(rows) do
        local cells = {}
        for i = 1, #COLUMNS do cells[i] = csv_escape(row[i]) end
        file:write(table.concat(cells, ","), "\n")
    end
    file:close()
    return path, #rows
end

local ok, path, count = xpcall(main, function(err)
    return debug and debug.traceback and debug.traceback(tostring(err), 2) or tostring(err)
end)
if ok then
    log("info", string.format("Exported %d players to %s", count, path))
    popup("fcmh academy export", string.format("Exported %d players to\n%s", count, path))
else
    log("error", "Export failed: " .. tostring(path))
    popup("fcmh academy export failed", tostring(path))
end
FCMH_LAST_RESULT = { ok = ok, path = ok and path or nil, count = ok and count or 0, error = (not ok) and tostring(path) or nil }
