"""Merge the Live Editor academy CSV exports into a growth report.

Input: any number of CSVs written by lua/fcmh_academy_export.lua.
Output: a merged long CSV, a per-prospect growth CSV, plus Markdown and HTML tables.
"""

from __future__ import annotations

import csv
import html
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED = ("export_date", "playerid", "name", "age", "ovr", "pot")
OPTIONAL = ("season", "source", "team", "position", "playstyles_count", "playstyles_plus_count")


class AcademyError(Exception):
    pass


@dataclass
class Snapshot:
    export_date: str
    season: str
    playerid: str
    name: str
    team: str
    position: str
    source: str
    age: int | None
    ovr: int | None
    pot: int | None
    playstyles: int | None
    playstyles_plus: int | None
    origin: str


@dataclass
class Prospect:
    playerid: str
    snapshots: list[Snapshot] = field(default_factory=list)

    @property
    def latest(self) -> Snapshot:
        return self.snapshots[-1]

    @property
    def first(self) -> Snapshot:
        return self.snapshots[0]

    def growth(self) -> int | None:
        if self.first.ovr is None or self.latest.ovr is None:
            return None
        return self.latest.ovr - self.first.ovr

    def pot_change(self) -> int | None:
        if self.first.pot is None or self.latest.pot is None:
            return None
        return self.latest.pot - self.first.pot

    def by_season(self) -> dict[str, Snapshot]:
        result: dict[str, Snapshot] = {}
        for snap in self.snapshots:
            result[snap.season or snap.export_date[:4]] = snap  # last snapshot of each season wins
        return result


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in ("nil", "none", "nan"):
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def read_csv(path: Path) -> list[Snapshot]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in REQUIRED if c not in header]
        if missing:
            raise AcademyError(f"{path.name}: missing column(s) {', '.join(missing)}. "
                               "Was it written by lua/fcmh_academy_export.lua?")
        rows = []
        for raw in reader:
            row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
            if not row.get("playerid"):
                continue
            rows.append(Snapshot(
                export_date=row["export_date"], season=row.get("season", ""), playerid=row["playerid"],
                name=row.get("name", ""), team=row.get("team", ""), position=row.get("position", ""),
                source=row.get("source", ""), age=_int(row.get("age")), ovr=_int(row.get("ovr")),
                pot=_int(row.get("pot")), playstyles=_int(row.get("playstyles_count")),
                playstyles_plus=_int(row.get("playstyles_plus_count")), origin=path.name,
            ))
        return rows


def collect(inputs: list[Path], pattern: str = "fcmh_academy_*.csv") -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_dir():
            files.extend(sorted(item.glob(pattern)))
        elif item.is_file():
            files.append(item)
        else:
            raise AcademyError(f"Not found: {item}")
    return sorted(set(files))


def merge(files: list[Path]) -> dict[str, Prospect]:
    if not files:
        raise AcademyError("No academy CSVs found. Run lua/fcmh_academy_export.lua in Live Editor first.")
    seen: dict[tuple[str, str], Snapshot] = {}
    for path in files:
        for snap in read_csv(path):
            seen[(snap.playerid, snap.export_date)] = snap  # same player + same in-game date = duplicate run
    prospects: dict[str, Prospect] = {}
    for snap in sorted(seen.values(), key=lambda s: (s.export_date, s.playerid)):
        prospects.setdefault(snap.playerid, Prospect(snap.playerid)).snapshots.append(snap)
    return prospects


def seasons_of(prospects: dict[str, Prospect]) -> list[str]:
    return sorted({season for p in prospects.values() for season in p.by_season()})


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return str(value)


def _signed(value: int | None) -> str:
    return "" if value is None else f"{value:+d}"


def ordered(prospects: dict[str, Prospect]) -> list[Prospect]:
    def key(p: Prospect):
        growth = p.growth()
        return (-(growth if growth is not None else -999), -(p.latest.pot or 0), p.latest.name)

    return sorted(prospects.values(), key=key)


def write_report(prospects: dict[str, Prospect], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    seasons = seasons_of(prospects)
    paths = {
        "merged": out_dir / "academy-merged.csv",
        "growth": out_dir / "academy-growth.csv",
        "markdown": out_dir / "academy-growth.md",
        "html": out_dir / "academy-growth.html",
    }

    with open(paths["merged"], "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["export_date", "season", "playerid", "name", "team", "position", "source",
                         "age", "ovr", "pot", "playstyles_count", "playstyles_plus_count", "from_file"])
        for p in sorted(prospects.values(), key=lambda p: p.playerid):
            for s in p.snapshots:
                writer.writerow([s.export_date, s.season, s.playerid, s.name, s.team, s.position, s.source,
                                 _fmt(s.age), _fmt(s.ovr), _fmt(s.pot), _fmt(s.playstyles),
                                 _fmt(s.playstyles_plus), s.origin])

    header = ["playerid", "name", "position", "age_now", "ovr_first", "ovr_now", "ovr_growth",
              "pot_first", "pot_now", "pot_change", "first_seen", "last_seen", "snapshots"]
    header += [f"ovr_{season}" for season in seasons]
    rows = []
    for p in ordered(prospects):
        f, l = p.first, p.latest
        per_season = p.by_season()
        row = [p.playerid, l.name, l.position, _fmt(l.age), _fmt(f.ovr), _fmt(l.ovr), _signed(p.growth()),
               _fmt(f.pot), _fmt(l.pot), _signed(p.pot_change()), f.export_date, l.export_date,
               str(len(p.snapshots))]
        row += [_fmt(per_season[s].ovr) if s in per_season else "" for s in seasons]
        rows.append(row)

    with open(paths["growth"], "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)

    def md_cell(text: str) -> str:
        return text.replace("|", "\\|")

    md = ["# Academy growth report", "",
          f"{len(prospects)} prospects, {sum(len(p.snapshots) for p in prospects.values())} snapshots, "
          f"seasons: {', '.join(seasons) or '-'}.", "",
          "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    md += ["| " + " | ".join(md_cell(c) for c in row) + " |" for row in rows]
    paths["markdown"].write_text("\n".join(md) + "\n", encoding="utf-8")

    def cell(tag: str, text: str, cls: str = "") -> str:
        attr = f' class="{cls}"' if cls else ""
        return f"<{tag}{attr}>{html.escape(text)}</{tag}>"

    growth_idx = header.index("ovr_growth")
    body = []
    for row in rows:
        cells = []
        for i, value in enumerate(row):
            cls = ""
            if i == growth_idx and value:
                cls = "up" if value.startswith("+") and value != "+0" else ("down" if value.startswith("-") else "")
            cells.append(cell("td", value, cls))
        body.append("<tr>" + "".join(cells) + "</tr>")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Academy growth report</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,sans-serif;margin:1.5rem;color:#1d1d1f}}
table{{border-collapse:collapse;font-size:14px}}th,td{{border:1px solid #ccc;padding:4px 8px;text-align:left}}
th{{background:#f2f2f2;position:sticky;top:0}}td.up{{color:#0a7a2f;font-weight:600}}td.down{{color:#b00020}}
</style></head><body>
<h1>Academy growth report</h1>
<p>{len(prospects)} prospects &middot; seasons: {html.escape(', '.join(seasons) or '-')}. Sorted by OVR growth.</p>
<table><thead><tr>{''.join(cell('th', h) for h in header)}</tr></thead>
<tbody>
{chr(10).join(body)}
</tbody></table>
</body></html>
"""
    paths["html"].write_text(page, encoding="utf-8")
    return paths
