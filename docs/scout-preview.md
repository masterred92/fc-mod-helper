# Scout preview (FC 26)

See the youth players your scouts found **before** you sign them: real potential (number and stars),
PlayStyles, PlayStyles+, hidden traits, and a **Sign him** badge on the best ones.

> **Status: untested in-game.** The script was written from the sources below and tested against a
> mock of Live Editor only. Compare it with your in-game scout report the first time
> ([what to check](#what-to-check-in-game)). FC 27 is coming soon.

## How to use it

1. Install [Live Editor](https://github.com/xAranaktu/FC-26-Live-Editor) from its official source
   (this project never ships it).
2. In FC Mod Helper press **Scout preview** once. It copies `fcmh_scout_preview.lua` into Live
   Editor's `lua` folder and tells you the one step to do in the game.
3. In Career Mode: **F9 > Features > Lua Engine**, open `fcmh_scout_preview.lua`, press **Execute**.
4. A message box says how many players it found. The app picks up the new file by itself
   (`Documents\FC Mod Helper\Scouting\scout_<in-game date>.csv`) and shows the cards.
5. **Make a web page** saves the same cards as an HTML page next to the CSV.

The script is **read-only**: it only reads database tables and never calls any "set" function.
Every call is wrapped in `pcall`, so a missing table or function shows a message box instead of
breaking anything.

## Stars and "Sign him"

Settings live in `Documents\FC Mod Helper\Scouting\scout-grades.json` (made on first use; edit the
numbers and press **Scout preview** again).

| Potential | Stars |
|---|---|
| 85+ | 5 |
| 80-84 | 4.5 |
| 75-79 | 4 |
| 70-74 | 3.5 |
| 65-69 | 3 |
| 60-64 | 2.5 |
| 55-59 | 2 |
| 50-54 | 1.5 |
| below 50 | 1 |

**Sign him** goes to the 3 best players who are **not signed yet** and have potential 75 or more.
Score = potential + 2 for every year younger than 17 + 3 for every PlayStyle+. Each card shows one
plain line, for example "Potential 88, age 15, 2 PlayStyles+".

## How other mods and tools do it

Nobody has a public "show the scout report" API for FC 26. Here is what each tool does, and what we
copied.

| Tool / source | How it gets youth scout data | Table, column or API it uses | What we copied |
|---|---|---|---|
| **Live Editor FC 26** (xAranaktu) - [README](https://github.com/xAranaktu/FC-26-Live-Editor#features), [changelog](https://github.com/xAranaktu/FC-26-Live-Editor/blob/main/changelog.txt) | Built-in features: "Generate youth scout academy reports" (README), "Youth Academy" in Miscellaneous Features (v26.1.3), "Scouts tab" and "Make every scout perfect" (v26.1.4), "Reveal Player Data" (v26.1.4). Its youth academy is a team you can open in the Team Editor (v26.1.1 fix). | Closed source (C++). No Lua function for the scout report is documented in the [Lua API v2 wiki](https://github.com/xAranaktu/FC-26-Live-Editor/wiki/LUA-API-v2). | Nothing directly; it confirms the data is in the career database/managers. |
| **Live Editor official Lua examples** - [pap_all_playstyles.lua](https://github.com/xAranaktu/FC-26-Live-Editor/blob/main/lua/pap_all_playstyles.lua), [delete_generated_players.lua](https://github.com/xAranaktu/FC-26-Live-Editor/blob/main/lua/delete_generated_players.lua) | Walk the `players` table record by record. | `LE.db:GetTable("players")`, `GetFirstRecord`, `GetNextValidRecord`, `GetRecordFieldValue`; PlayStyles in `trait1`/`trait2`, PlayStyles+ in `icontrait1`/`icontrait2`; names via `imports/other/playstyles_enum`; generated players have `playerid >= 460000`. | **Confirmed approach**, used for all reads. |
| **Live Editor FC 25 Lua library** - [career_mode/enums.lua](https://github.com/xAranaktu/FC-25-Live-Editor/blob/main/lua/libs/v2/imports/career_mode/enums.lua), [playstyles_enum.lua](https://github.com/xAranaktu/FC-25-Live-Editor/blob/main/lua/libs/v2/imports/other/playstyles_enum.lua), [other/helpers.lua](https://github.com/xAranaktu/FC-25-Live-Editor/blob/main/lua/libs/v2/imports/other/helpers.lua) | Game-mode managers and events exist for youth scouting. | `ENUM_CM_EVENT_MSG_YOUTH_SCOUT_REPORT_IS_AVAILABLE`, `..._YOUTH_PLAYER_ADDED_TO_YOUTH_ACADEMY`, managers `FCECareerModeYouthPlayerManager`, `FCECareerModeYouthPlayerUtil`, `FCECareerModeScoutManager`; `ENUM_PLAYSTYLE1_*`/`ENUM_PLAYSTYLE2_*` bit names (`CPUAI_*`, `CAREER_*` = hidden traits); `GetUserTeamID()` reads `career_users.clubteamid`. | Enum-based PlayStyle names and the hidden-trait split. Manager memory layouts are undocumented, so we don't read them. |
| **Aranaktu's CM Cheat Table** - [FC 25 wiki: Youth Academy](https://github.com/xAranaktu/FC-25-CM-Cheat-Table/wiki/Youth-Academy), [FIFA 22 helpers.lua `ya_reveal_data`](https://github.com/xAranaktu/FIFA-22-CM-Cheat-Table/blob/main/lua/helpers.lua), [consts.lua](https://github.com/xAranaktu/FIFA-22-CM-Cheat-Table/blob/main/lua/consts.lua) | "Reveal Ovr & Pot" **writes memory** so the game's own screens show the exact numbers. "Generate new report", "15 Players Per Report" (a report holds at most 15), "Force Player Tier", "Potential Range". | `YouthPlayerUtil` manager, settings pointer at `+0x18`; zeroes the 6x2 potential-variance list at `+0x798`; sets "max display value" at `+0x7CC` to 99. `ScoutManager` for mission cost and players per report. | The idea that the **true potential is stored** and only the on-screen range is blurred. We read it instead of patching memory (read-only, and those offsets are for older games). The 15-per-report limit is used as a sanity warning. |
| **scout.ini (FIFA 17/18 career settings)** - [FIFA 18 scout.ini](https://github.com/xAranaktu/FIFA-18---iniToCT/blob/master/ORG_INIFILES/scout.ini) | Game settings file that generates youth players. | `[YOUTH_SCOUT]`, `TIER_n_POTENTIAL_RANGE_0/1`, `POTENTIAL_VARIANCE_PERC_0..5` and `POTENTIAL_SWING_VARIANCE_0..5` ("only for the screens"), `POTENTIAL_MAX_DISPLAY_VALUE = 94`. | Explains `potentialvariance`/`swinglowpotential` and the "Game may show X-Y (guess)" line (FIFA 18 percentages, editable in `scout-grades.json`). |
| **Youth Academy Redux** (RobGrant) - [Nexus](https://www.nexusmods.com/easportsfc26/mods/92) | Changes how scouts **generate** players (Platinum tier everywhere, 70-80 OVR, 7-8 PlayStyles, earlier PlayStyle+ upgrades at 65/75 OVR, promotion from 15). | Career settings inside a `.fifamod` (not readable without the mod tools; we treat mods as opaque). | Nothing to copy for reading; it explains why a Redux player can have many PlayStyles+. |
| **Youth Academy Re-adjusted** (zxbnzlol2) - [Nexus](https://www.nexusmods.com/easportsfc26/mods/1508) | Generation tweaks: more Platinum prospects, more PlayStyles, scout age 12, academy max age 19. | Career settings in a `.fifamod`. | Ages can be 12-19 with this mod, so the app doesn't assume 15-17. |
| **KIARIKA Career Mode Overhaul** - [Nexus](https://www.nexusmods.com/easportsfc26/mods/77) | Generation tweaks; Platinum potential 75-94, 5-7 PlayStyles; "The visual variability range of youth academy player potential has been reduced... up to 10 potential" in the UI. | Career settings in a `.fifamod`. | Confirms FC 26 still blurs potential **only on screen**, like scout.ini did. |
| **CM Tweaks (FIFA 23)** - [Nexus](https://www.nexusmods.com/fifa23/mods/202) | "Reduced the potential range displayed... Increased max potential displayed from 94 to 99." | Career settings. | Same "display only" idea. |
| **FC 26 database field list** - [FC-Universe `db_meta.json`](https://github.com/Arnax308/FC-Universe/blob/main/backend/db_meta.json) (field codes match the FC 26 save notes in [hang-rua](https://github.com/hungntv210/hang-rua)) | Field names for the career tables. | `career_youthplayers`: `playerid, monthsinsquad, playertype, potentialvariance, swinglowpotential, playertier`; `career_youthplayerhistory`: `playerid, appearances, goals`; `career_scoutmission`: `scoutid, nationality, playertype, preferredposition1-4, preferredrole1-3, durationid, returningdate, missioncost`; `career_scouts`: `scoutid, firstname, lastname, knowledge, experience, nationality, regionid, state`; `career_youthplayerattributes` (templates by `playertype`/`playertier`); `nations`: `nationid, nationname`. | The table and column names the script reads. |
| **FC 26 save readers** - [fc26-career-analyzer report](https://github.com/solon07/fc26-career-analyzer/blob/main/docs/investigation_report.md), [touchline_os parser](https://github.com/ianmadez/touchline_os/blob/main/src/lib/parser/feasibility-parser.ts), [hang-rua youth.ts](https://github.com/hungntv210/hang-rua/blob/main/lib/fc26/youth.ts) | Read the saved database. | Real FC 26 saves contain `career_youthplayers` (15 rows), `career_scoutmission` (3), `career_scouts` (3). Join `career_youthplayers.playerid` to `players`. One player can have **several rows** that disagree. hang-rua: the table holds **signed and scouted** players together (25 = 16 signed + 9 scouted) and **no field says who is signed**. touchline: academy players have no `teamplayerlinks` row. | Join by `playerid`; merge repeated rows (widest range); "signed" is only a guess. |
| **Community Live Editor scripts** - [hang-rua fc26-dump-career.lua](https://github.com/hungntv210/hang-rua/blob/main/scripts/fc26-dump-career.lua), [FC-Career-Top client-script.lua](https://github.com/VeejaLiu/FC-Career-Top/blob/main/apps/frontend/lua-scripts/client-script.lua) | Export career tables to CSV from inside Live Editor. | hang-rua uses the older `GetDBTablesNames` / `GetDBTableFields` / `GetDBTableRows` and reports the pointer API crashed the game for them in an earlier full dump of **all 322 tables**. FC-Career-Top uses the pointer API and decodes PlayStyles from the runtime enum only if `ENUM_PLAYSTYLE1_TECHNICAL == 1048576` (FC 26 layout). | Same enum check. We only read ~7 tables with the official pointer API, and use the older functions only for the "what tables exist" fallback. |

## What the script reads

Confirmed means: seen in an official Live Editor example or in at least two independent community
sources for FC 26. Guess means: our best reading, please check in-game.

| What | Where | Confirmed or guess |
|---|---|---|
| Who the youth players are | `career_youthplayers.playerid` | **Confirmed** table and column (FC 26 field list + three save readers). That the table includes the not-yet-signed scout report is **confirmed by one** reader (hang-rua). |
| Name | `GetPlayerName(playerid)` | Confirmed function (Lua API docs); untested for youth players. |
| Age | `players.birthdate` + `GetCurrentDate()` + `DATE:FromGregorianDays` | Confirmed (official examples). |
| Positions | `players.preferredposition1..4` + `GetPlayerPrimaryPositionName` | Confirmed fields and helper; `-1` = none. |
| Nationality | `players.nationality` -> `nations.nationname` | Fields confirmed in the FC 26 field list; reading `nations` from Lua is a guess (falls back to the id). |
| OVR, exact potential | `players.overallrating`, `players.potential` | **Confirmed** (official examples). The real potential is stored; only the screen range is blurred (cheat table + KIARIKA + scout.ini). |
| Potential range | `career_youthplayers.potentialvariance`, `swinglowpotential` | Columns confirmed; their meaning is a **guess** (index into the screen-only variance list). The app shows "Game may show X-Y (guess)". |
| Tier | `career_youthplayers.playertier` | Column confirmed; 0-3 = Bronze..Platinum is a guess. |
| PlayStyles / PlayStyles+ / hidden traits | `players.trait1/2` (PlayStyles), `icontrait1/2` (PlayStyles+); names from `ENUM_PLAYSTYLE1_*`/`ENUM_PLAYSTYLE2_*` | **Confirmed** fields and enum (official example). Names are used only if the enum matches the FC 26 layout; otherwise raw ids like "Style 1.20" are written. |
| Signed or not | team link in `teamplayerlinks`, `GetTeamIdFromPlayerId`, or `career_youthplayers.monthsinsquad > 0` | **Guess.** The game has no known "signed" field. The app lets you show everyone. If more than 15 look unsigned, the script warns (a report holds at most 15). |
| Which scout trip | `career_scoutmission.nationality` matched to the player's nationality, scout name from `career_scouts` | **Guess** (there is no player-to-mission link in the field list). |

If `career_youthplayers` can't be read or is empty, the script writes
`scout_<date>_tables.txt` with every table and column it can see (via `GetDBTablesNames`/
`GetDBTableFields` if Live Editor still has them, otherwise a list of likely tables), and the app
asks you to send that file.

## What to check in-game

1. Open your youth scout report in the game and run the script. Do the **names** in the app match
   the report? Is the **count** of "not signed yet" players the same (at most 15)?
2. Pick one player: do age, positions and nationality match?
3. Is his potential **inside** the range the game shows for him? (It should be; the game shows a
   range around the real number.)
4. Do his PlayStyles and PlayStyles+ match his in-game player page (if the game shows them before
   signing)? If they show as "Style 1.20", tell us; the names file didn't match.
5. Sign one player, run the script again: does he move to "signed" (tick **Show players I already
   signed** to see him)?
6. If the script shows "couldn't find your scouted youth players", send the `scout_*_tables.txt` file
   from `Documents\FC Mod Helper\Scouting`.
