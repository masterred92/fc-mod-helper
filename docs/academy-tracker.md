# Academy tracker

> **Untested in-game.** The Lua script has only been run against a mock of the Live Editor API in
> this repo's tests. Try it on a spare Career save first. It is read-only: it never writes to the
> game database.

## 1. Export a snapshot (in game)

1. Get Live Editor for your game build from its official source and start Career Mode with it.
2. In the app, press **My academy** once. It copies `fcmh_academy_export.lua` into Live Editor's
   `lua` folder and points it at `Documents\FC Mod Helper\Academy`.
3. In Career Mode press **F9 → Features → Lua Engine**, open `fcmh_academy_export.lua` and press **Execute**.
4. A message box says how many players were exported and where the CSV went
   (`fcmh_academy_YYYY-MM-DD.csv`, using the **in-game** date). Without the app, the script writes to your Desktop.
5. Press **My academy** again to see the report. CSVs left on the Desktop are imported automatically.

The script's source is `src/fcmh/lua/fcmh_academy_export.lua`.

Run it whenever you want a data point, e.g. at the start of each season, at the January window and
at the end of the season. Running it twice on the same in-game day just overwrites that day's file.

Settings at the top of the script:

| Setting | Default | Meaning |
|---|---|---|
| `MAX_AGE` | `21` | Senior-squad players at or under this age are exported |
| `OUTPUT_DIR` | `nil` (Desktop) | Folder for the CSVs, e.g. `"D:\\FC\\academy"` (must exist) |
| `YOUTH_TABLE` | `"career_youthplayers"` | **Experimental**: database table read for academy players. If it doesn't exist, the script logs a warning and exports the senior squad only. Set `nil` to switch off. |

## 2. Build the growth report

The **My academy** button does this. From the command line:

```powershell
fcmh academy report                       # reads academy_dir (Desktop by default)
fcmh academy report --input D:\FC\academy --out D:\FC\academy\report
```

Outputs:

- `academy-merged.csv`: every snapshot, one row per player per export.
- `academy-growth.csv`: one row per prospect: first/latest OVR and POT, growth, and one
  `ovr_<season>` column per season (the last snapshot of that season).
- `academy-growth.md`: the same table, sorted by OVR growth.
- `academy-growth.html`: one card per player with a growth arrow and a small OVR/potential chart, plus the full table.

## CSV columns

`export_date, season, source, playerid, name, team, age, ovr, pot, position, playstyles_bits,
playstyles_plus_bits, playstyles_count, playstyles_plus_count, le_version`

- `source` is `senior` (from your senior squad) or `academy` (from the youth table).
- `season` is derived from the in-game date (July starts a new season), e.g. `2026/27`.
- PlayStyles are exported as the raw bitmask plus a count of set bits; names aren't decoded.

## What needs checking in-game

| Item | Source used | Please confirm |
|---|---|---|
| `LE.db:GetTable`, `GetFirstRecord`, `GetNextValidRecord`, `GetRecordFieldValue` | official example scripts | Script runs without "missing helper" errors |
| `GetUserSeniorTeamPlayerIDs`, `GetCurrentDate`, `DATE:FromGregorianDays`, `IsInCM` | official example scripts (`1ovr_99pot.lua`, `mass_edit_age.lua`) | Ages look right |
| `players` fields `playerid`, `birthdate`, `overallrating`, `potential`, `preferredposition1` | official example scripts | OVR/POT match the in-game squad screen |
| `trait1` / `icontrait1` as PlayStyles / PlayStyles+ | `pap_all_playstyles.lua` | Counts match what the player card shows |
| `GetPlayerPrimaryPositionName`, `GetPlayerName`, `GetTeamName`, `GetTeamIdFromPlayerId` | official example scripts | Names and positions look right |
| `career_youthplayers` table for academy players | **not documented**, a guess | Whether academy (not yet promoted) players appear with `source=academy` |

If something fails, the script shows the error in a message box and in the Live Editor log
(lines start with `[fcmh_academy_export]`). Please include that text when reporting an issue,
but never attach your save files.
