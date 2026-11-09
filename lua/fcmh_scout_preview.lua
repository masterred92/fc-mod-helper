--[[
fc-mod-helper: SCOUT PREVIEW for FC 26 Live Editor (Lua API v2, Lua 5.4)

STATUS: UNTESTED IN-GAME. Written from the public Live Editor docs, the official
example scripts and community notes (see docs/scout-preview.md), and tested only
against a mock of the API. Please run it once and compare it with your in-game
youth scout report before you trust it.

What it does (READ-ONLY, it never changes the game or your save):
  * reads the youth players your scouts found (table career_youthplayers)
  * for each one: name, age, positions, nationality, OVR, real potential,
    PlayStyles, PlayStyles+ and hidden traits, and which scout trip found him
  * guesses who is NOT signed yet (scout report) and who is already in your academy
    (signed = has a team link or months in the academy; the game has no clear "signed" field)
  * writes scout_<in-game date>.csv for the FC Mod Helper app
  * if the youth table can't be read, writes scout_<date>_tables.txt listing the
    tables and columns that DO exist, so the guess can be fixed

How to run: in Career Mode press F9 > Features > Lua Engine, open this file, Execute.

Uses (as in the official example scripts): LE.db:GetTable, GetFirstRecord,
GetNextValidRecord, GetRecordFieldValue, IsInCM, GetCurrentDate, DATE:FromGregorianDays,
GetUserTeamID, GetPlayerName, GetTeamIdFromPlayerId, GetPlayerPrimaryPositionName,
LOGGER, MessageBox, and the optional 'imports/other/playstyles_enum'.
Only for the "what tables exist" fallback it also tries the older GetDBTablesNames /
GetDBTableFields if Live Editor still has them. Every call is wrapped in pcall.
]]

---------------------------------------------------------------- settings
-- Folder for the CSV. nil = Documents\FC Mod Helper\Scouting (or your Desktop).
local OUTPUT_DIR = nil

-- GUESS: the table that holds youth players found by your scouts (plus your academy).
local YOUTH_TABLES = { "career_youthplayers" }

-- Only trust the PlayStyle names file if its "Technical" bit matches FC 26.
-- Set to true to always use it (names may then be wrong after a game update).
local TRUST_PLAYSTYLE_NAMES_ANYWAY = false
---------------------------------------------------------------- end of settings

local SCRIPT = "fcmh_scout_preview"
local SEP = package.config:sub(1, 1)
local NOTES = {}

local function log(level, msg)
    local text = "[" .. SCRIPT .. "] " .. tostring(msg)
    if level ~= "info" then NOTES[#NOTES + 1] = tostring(msg) end
    if LOGGER then
        if level == "error" then pcall(LOGGER.LogError, LOGGER, text)
        elseif level == "warn" then pcall(LOGGER.LogWarn, LOGGER, text)
        else pcall(LOGGER.LogInfo, LOGGER, text) end
    else
        print(text)
    end
end

-- A plain-words error for the message box (no Lua stack trace).
local function fail(msg) error({ fcmh = msg }, 0) end

local function popup(title, msg)
    if type(MessageBox) == "function" then pcall(MessageBox, title, msg) end
end

local function call(fn_name, ...)
    local fn = _G[fn_name]
    if type(fn) ~= "function" then return nil end
    local ok, value = pcall(fn, ...)
    if ok then return value end
    return nil
end

local function csv_escape(value)
    if value == nil then return "" end
    local s = tostring(value)
    if math.type and math.type(value) == "float" and value == math.floor(value) then
        s = string.format("%d", value)
    end
    if s:find('[,"\r\n]') then s = '"' .. (s:gsub('"', '""')) .. '"' end
    return s
end

local function num(value)
    if value == nil then return nil end
    local n = tonumber(value)
    if n == nil then return nil end
    return math.tointeger(n) or n
end

local function open_table(name)
    local ok, tbl = pcall(function() return LE.db:GetTable(name) end)
    if ok and tbl ~= nil then return tbl end
    return nil, tostring(tbl)
end

-- Reads every row of a table into a list of {field = value}. Never writes.
local function read_rows(name, fields, limit)
    local tbl, err = open_table(name)
    if tbl == nil then return nil, "can't open table '" .. name .. "' (" .. tostring(err) .. ")" end
    local rows, missing = {}, {}
    local ok, loop_err = pcall(function()
        local record = tbl:GetFirstRecord()
        while record and record > 0 do
            local row = {}
            for _, f in ipairs(fields) do
                local fok, v = pcall(function() return tbl:GetRecordFieldValue(record, f) end)
                if fok then row[f] = v else missing[f] = true end
            end
            rows[#rows + 1] = row
            if limit and #rows >= limit then break end
            record = tbl:GetNextValidRecord()
        end
    end)
    if not ok then return nil, "reading '" .. name .. "' failed: " .. tostring(loop_err) end
    return rows, nil, missing
end

---------------------------------------------------------------- dates
local function age_on(birthdate_days, today)
    birthdate_days = num(birthdate_days)
    if birthdate_days == nil or birthdate_days <= 0 or today == nil or DATE == nil then return nil end
    local ok, born = pcall(function() local d = DATE:new(); d:FromGregorianDays(birthdate_days); return d end)
    if not ok or born == nil or not born.year then return nil end
    local age = today.year - born.year
    if today.month < born.month or (today.month == born.month and today.day < born.day) then age = age - 1 end
    return age
end

---------------------------------------------------------------- PlayStyles
-- Names come from Live Editor's own enum file, ENUM_PLAYSTYLE1_* / ENUM_PLAYSTYLE2_*.
-- trait1/trait2 = PlayStyles, icontrait1/icontrait2 = PlayStyles+ (as in the official
-- pap_all_playstyles.lua example). CPUAI_* and CAREER_* names are hidden traits.
local STYLE_NAMES = nil

local function pretty(name)
    name = name:gsub("^GK_", "GK "):gsub("^CPUAI_", ""):gsub("^CAREER_", "")
    return (name:lower():gsub("_", " "):gsub("(%a)([%w]*)", function(a, b) return a:upper() .. b end))
end

local function load_style_names()
    local ok = pcall(require, "imports/other/playstyles_enum")
    if not ok then log("warn", "PlayStyle names file not found; writing raw numbers instead.") return nil end
    local technical = rawget(_G, "ENUM_PLAYSTYLE1_TECHNICAL")
    if technical ~= 1048576 and not TRUST_PLAYSTYLE_NAMES_ANYWAY then
        log("warn", "PlayStyle names file looks like an older game (Technical=" .. tostring(technical) ..
            "); writing raw numbers instead.")
        return nil
    end
    local names = { [1] = {}, [2] = {} }
    for key, mask in pairs(_G) do
        if type(key) == "string" and math.type(mask) == "integer" and mask > 0 and (mask & (mask - 1)) == 0 then
            local group, raw = key:match("^ENUM_PLAYSTYLE([12])_(.+)$")
            if group then
                local hidden = raw:match("^CPUAI_") ~= nil or raw:match("^CAREER_") ~= nil
                names[tonumber(group)][mask] = { name = pretty(raw), hidden = hidden }
            end
        end
    end
    return names
end

local function bits_of(value)
    local out, n, bit = {}, math.tointeger(num(value) or 0) or 0, 0
    n = n & 0xFFFFFFFFFFFF
    while n ~= 0 do
        if n & 1 == 1 then out[#out + 1] = bit end
        n = n >> 1
        bit = bit + 1
    end
    return out
end

-- returns playstyles, playstyles_plus, hidden traits (each a list of strings)
local function decode_styles(p)
    local normal, plus, hidden = {}, {}, {}
    for group = 1, 2 do
        local t = math.tointeger(num(p["trait" .. group]) or 0) or 0
        local it = math.tointeger(num(p["icontrait" .. group]) or 0) or 0
        for _, bit in ipairs(bits_of(t | it)) do
            local mask = 1 << bit
            local info = STYLE_NAMES and STYLE_NAMES[group][mask]
            local label = info and info.name or string.format("Style %d.%d", group, bit)
            if info and info.hidden then
                hidden[#hidden + 1] = label
            elseif it & mask ~= 0 then
                plus[#plus + 1] = label
            else
                normal[#normal + 1] = label
            end
        end
    end
    table.sort(normal); table.sort(plus); table.sort(hidden)
    return normal, plus, hidden
end

---------------------------------------------------------------- fallback dump
local function dump_tables(path, reason)
    local f = io.open(path, "w")
    if f == nil then return false end
    f:write("FC Mod Helper scout preview: table check\n")
    f:write("Reason: " .. tostring(reason) .. "\n")
    f:write("Live Editor: " .. tostring(rawget(_G, "LE_VERSION")) .. "\n\n")
    local names = call("GetDBTablesNames")
    local wanted = {}
    if type(names) == "table" then
        for _, n in pairs(names) do
            local s = type(n) == "table" and (n.name or n[1]) or n
            if type(s) == "string" then wanted[#wanted + 1] = s end
        end
        table.sort(wanted)
        f:write("All tables (" .. #wanted .. "): " .. table.concat(wanted, ", ") .. "\n\n")
    else
        f:write("GetDBTablesNames is not available; checking a list of likely tables.\n\n")
        wanted = { "career_youthplayers", "career_youthplayerattributes", "career_youthplayerposattributes",
                   "career_youthplayerhistory", "career_scoutmission", "career_scouts", "career_users",
                   "players", "teamplayerlinks", "nations" }
    end
    for _, name in ipairs(wanted) do
        local lname = name:lower()
        if lname:find("youth") or lname:find("scout") or lname:find("academy") or lname == "players"
            or lname == "teamplayerlinks" or lname == "career_users" then
            local cols = {}
            local fields = call("GetDBTableFields", name)
            if type(fields) == "table" then
                for _, fd in pairs(fields) do
                    local s = type(fd) == "table" and (fd.name or fd[1]) or fd
                    if type(s) == "string" then cols[#cols + 1] = s end
                end
            else
                local tbl = open_table(name)
                if tbl ~= nil and type(tbl.fields) == "table" then
                    for k in pairs(tbl.fields) do cols[#cols + 1] = tostring(k) end
                end
                local rows = read_rows(name, { "playerid" }, 100000)
                f:write(string.format("%s: %s rows\n", name, rows and tostring(#rows) or "can't open"))
            end
            table.sort(cols)
            f:write(name .. " columns: " .. (#cols > 0 and table.concat(cols, ", ") or "(unknown)") .. "\n")
        end
    end
    f:close()
    return true
end

---------------------------------------------------------------- output folder
local function can_write(dir)
    if dir == nil or dir == "" then return false end
    local probe = dir .. SEP .. "fcmh_write_test.tmp"
    local f = io.open(probe, "w")
    if f == nil then return false end
    f:write("ok"); f:close(); os.remove(probe)
    return true
end

local function output_dir()
    local candidates = {}
    local function add(dir)
        if type(dir) == "string" and dir ~= "" then candidates[#candidates + 1] = dir end
    end
    add(OUTPUT_DIR)
    add(rawget(_G, "FCMH_OUTPUT_DIR"))
    local profile = os.getenv("USERPROFILE")
    if profile then
        add(profile .. SEP .. "Documents" .. SEP .. "FC Mod Helper" .. SEP .. "Scouting")
        add(profile .. SEP .. "Desktop")
    end
    for _, dir in ipairs(candidates) do
        if can_write(dir) then return dir end
    end
    fail("Can't find a folder to write to. Open FC Mod Helper, press Scout preview once, then try again.")
end

---------------------------------------------------------------- main
local COLUMNS = {
    "game", "export_date", "playerid", "name", "age", "positions", "nationality", "ovr", "potential",
    "pot_swing_low", "pot_variance", "tier", "playstyles", "playstyles_plus", "traits", "status",
    "scout_report", "months_in_squad", "raw_styles", "le_version",
}

local function main()
    pcall(require, "imports/career_mode/helpers")
    pcall(require, "imports/other/helpers")
    if type(LE) ~= "table" or type(IsInCM) ~= "function" then
        fail("This Live Editor is too old or not running. Update Live Editor and try again.")
    end
    if not IsInCM() then fail("Load your Career save first, then run this script again.") end

    local today = call("GetCurrentDate")
    local date_str = today and today.year and string.format("%04d-%02d-%02d", today.year, today.month, today.day)
        or os.date("%Y-%m-%d")
    local dir = output_dir()
    local csv_path = dir .. SEP .. "scout_" .. date_str .. ".csv"
    local dump_path = dir .. SEP .. "scout_" .. date_str .. "_tables.txt"

    -- 1. youth players (GUESS: table and columns, see docs/scout-preview.md)
    local youth_fields = { "playerid", "playertier", "potentialvariance", "swinglowpotential", "monthsinsquad", "playertype" }
    local youth_rows, youth_err, used_table, youth_missing
    for _, name in ipairs(YOUTH_TABLES) do
        youth_rows, youth_err, youth_missing = read_rows(name, youth_fields)
        if youth_rows and youth_missing and youth_missing.playerid then
            youth_err = "table '" .. name .. "' has no 'playerid' column"
            youth_rows = nil
        end
        if youth_rows then used_table = name break end
    end
    if youth_rows == nil or #youth_rows == 0 then
        local why = youth_err or ("table '" .. tostring(used_table) .. "' is empty (no scout report yet?)")
        log("warn", why)
        local dumped = dump_tables(dump_path, why)
        fail("I couldn't find your scouted youth players: " .. why .. ".\n\n" ..
              (dumped and ("I wrote the list of tables I can see to:\n" .. dump_path ..
              "\nPlease send that file to the FC Mod Helper page so this can be fixed.")
              or "I couldn't write the table list either."))
    end

    local youth = {}
    for _, r in ipairs(youth_rows) do
        local pid = num(r.playerid)
        if pid and pid > 0 then
            local y = youth[pid] or { rows = 0 }
            y.rows = y.rows + 1
            -- the same player can appear more than once; keep the widest view
            local swing, var, months = num(r.swinglowpotential), num(r.potentialvariance), num(r.monthsinsquad)
            if swing and (y.swing == nil or swing < y.swing) then y.swing = swing end
            if var and (y.var == nil or var > y.var) then y.var = var end
            if months and (y.months == nil or months > y.months) then y.months = months end
            y.tier = y.tier or num(r.playertier)
            youth[pid] = y
        end
    end

    -- 2. who is already on a team (GUESS: a scout-report player has no team yet)
    local on_team = {}
    local links = read_rows("teamplayerlinks", { "playerid", "teamid" })
    if links then
        for _, l in ipairs(links) do
            local pid = num(l.playerid)
            if pid and youth[pid] then on_team[pid] = num(l.teamid) end
        end
    else
        log("warn", "Couldn't read teamplayerlinks; 'signed' guesses use GetTeamIdFromPlayerId only.")
    end

    -- 3. nations and scout trips (best effort, GUESS)
    local nations = {}
    for _, n in ipairs(read_rows("nations", { "nationid", "nationname" }) or {}) do
        if num(n.nationid) then nations[num(n.nationid)] = n.nationname end
    end
    local scouts = {}
    for _, s in ipairs(read_rows("career_scouts", { "scoutid", "firstname", "lastname" }) or {}) do
        local sid = num(s.scoutid)
        if sid then
            local name = ((type(s.firstname) == "string" and s.firstname or "") .. " " ..
                          (type(s.lastname) == "string" and s.lastname or "")):gsub("^%s+", ""):gsub("%s+$", "")
            scouts[sid] = name ~= "" and name or ("Scout " .. sid)
        end
    end
    local missions = read_rows("career_scoutmission", { "scoutid", "nationality", "playertype" }) or {}
    local function mission_for(nat)
        local hits = {}
        for _, m in ipairs(missions) do
            if num(m.nationality) == nat then hits[#hits + 1] = m end
        end
        if #hits == 0 and #missions == 1 then hits = missions end
        if #hits == 0 then return "" end
        local m = hits[1]
        local who = scouts[num(m.scoutid)] or ("Scout " .. tostring(m.scoutid))
        local where = nations[num(m.nationality)] or ("country " .. tostring(m.nationality))
        return who .. " in " .. where
    end

    -- 4. player details from the players table
    STYLE_NAMES = load_style_names()
    local pfields = { "playerid", "birthdate", "overallrating", "potential", "nationality",
                      "preferredposition1", "preferredposition2", "preferredposition3", "preferredposition4",
                      "trait1", "trait2", "icontrait1", "icontrait2" }
    local ptbl = open_table("players")
    if ptbl == nil then fail("Could not open the 'players' table.") end
    local found = {}
    local ok, err = pcall(function()
        local record = ptbl:GetFirstRecord()
        while record and record > 0 do
            local pidok, pid = pcall(function() return ptbl:GetRecordFieldValue(record, "playerid") end)
            pid = pidok and num(pid) or nil
            if pid and youth[pid] and not found[pid] then
                local p = {}
                for _, f in ipairs(pfields) do
                    local fok, v = pcall(function() return ptbl:GetRecordFieldValue(record, f) end)
                    if fok then p[f] = v end
                end
                found[pid] = p
            end
            record = ptbl:GetNextValidRecord()
        end
    end)
    if not ok then log("warn", "Reading players stopped early: " .. tostring(err)) end

    local out, pending = {}, 0
    for pid, y in pairs(youth) do
        local p = found[pid] or {}
        local positions = {}
        for i = 1, 4 do
            local pos = num(p["preferredposition" .. i])
            if pos and pos >= 0 then
                local nm = call("GetPlayerPrimaryPositionName", pos)
                positions[#positions + 1] = (nm and nm ~= "INVALID") and nm or tostring(pos)
            end
        end
        local team = on_team[pid]
        if team == nil then
            local t = num(call("GetTeamIdFromPlayerId", pid))
            if t and t > 0 then team = t end
        end
        -- GUESS: signed if he is on a team, or has already spent months in the academy.
        -- (One community save reader says academy players have no team link, so months helps.)
        local signed = team ~= nil or (y.months ~= nil and y.months > 0)
        local status = signed and "signed (guess)" or "not signed (guess)"
        if not signed then pending = pending + 1 end
        local nat = num(p.nationality)
        local normal, plus, hidden = decode_styles(p)
        out[#out + 1] = {
            "FC 26", date_str, pid,
            call("GetPlayerName", pid) or ("Player " .. pid),
            age_on(p.birthdate, today),
            table.concat(positions, " "),
            (nat and nations[nat]) or nat,
            num(p.overallrating), num(p.potential),
            y.swing, y.var, y.tier,
            table.concat(normal, "; "), table.concat(plus, "; "), table.concat(hidden, "; "),
            status, nat and mission_for(nat) or "", y.months,
            string.format("t1=%s it1=%s t2=%s it2=%s", tostring(p.trait1), tostring(p.icontrait1),
                          tostring(p.trait2), tostring(p.icontrait2)),
            tostring(rawget(_G, "LE_VERSION") or ""),
        }
    end
    table.sort(out, function(a, b) return (a[9] or 0) > (b[9] or 0) end)
    if pending > 15 then
        log("warn", string.format("%d players look unsigned, but a scout report holds at most 15. " ..
            "The 'signed' guess may be wrong; please compare with the game.", pending))
    end

    local file, open_err = io.open(csv_path, "w")
    if file == nil then fail("Can't write " .. csv_path .. ": " .. tostring(open_err)) end
    file:write(table.concat(COLUMNS, ","), "\n")
    for _, row in ipairs(out) do
        local cells = {}
        for i = 1, #COLUMNS do cells[i] = csv_escape(row[i]) end
        file:write(table.concat(cells, ","), "\n")
    end
    file:close()
    return csv_path, #out, pending
end

local ok, path, count, pending = xpcall(main, function(err)
    if type(err) == "table" and err.fcmh then return err.fcmh end
    local msg = tostring(err)
    if debug and debug.traceback then msg = debug.traceback(msg, 2) end
    return "Something went wrong inside the script:\n" .. msg
end)
if ok then
    local text = string.format("Found %d youth players (%d not signed yet).\nSaved to:\n%s\n\n" ..
        "Now look at FC Mod Helper - it shows them by itself.", count, pending, path)
    if #NOTES > 0 then text = text .. "\n\nNotes:\n- " .. table.concat(NOTES, "\n- ") end
    log("info", string.format("Exported %d youth players to %s", count, path))
    popup("FC Mod Helper: Scout preview", text)
else
    log("error", "Scout preview failed: " .. tostring(path))
    popup("FC Mod Helper: Scout preview didn't work", tostring(path))
end
FCMH_LAST_RESULT = {
    ok = ok, path = ok and path or nil, count = ok and count or 0,
    pending = ok and pending or 0, error = (not ok) and tostring(path) or nil,
}
