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


def _spark(prospect: Prospect, width: int = 240, height: int = 70) -> str:
    points = [(s.ovr, s.pot) for s in prospect.snapshots]
    values = [v for pair in points for v in pair if v is not None]
    if not values:
        return ""
    low, high = min(values) - 2, max(values) + 2
    span = max(high - low, 1)
    step = (width - 16) / max(len(points) - 1, 1)

    def xy(i: int, v: int) -> tuple[float, float]:
        return 8 + i * step, height - 8 - (v - low) / span * (height - 16)

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="growth chart">']
    for idx, (color, dash) in enumerate((("#1f9d55", ""), ("#3554d1", ' stroke-dasharray="5 4"'))):
        coords = [xy(i, p[idx]) for i, p in enumerate(points) if p[idx] is not None]
        if len(coords) > 1:
            line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="3"{dash} points="{line}"/>')
        for x, y in coords:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>')
    parts.append("</svg>")
    return "".join(parts)


def _card(prospect: Prospect) -> str:
    latest, growth = prospect.latest, prospect.growth()
    if growth is None or growth == 0:
        arrow, cls = "&#9654; 0", "flat"
    elif growth > 0:
        arrow, cls = f"&#9650; +{growth}", "up"
    else:
        arrow, cls = f"&#9660; {growth}", "down"
    meta = " &middot; ".join(html.escape(x) for x in (latest.position, f"age {latest.age}" if latest.age is not None else "", latest.team) if x)
    return (f'<div class="card"><h2>{html.escape(latest.name or prospect.playerid)}</h2>'
            f'<div class="meta">{meta}</div>'
            f'<div class="nums"><span class="big">{_fmt(latest.ovr)}</span>'
            f'<span class="arrow {cls}">{arrow}</span>'
            f'<span class="pot">potential {_fmt(latest.pot)}</span></div>'
            f'{_spark(prospect)}'
            f'<div class="meta">{len(prospect.snapshots)} exports, since {html.escape(prospect.first.export_date)}</div></div>')


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

    cards = "\n".join(_card(p) for p in ordered(prospects))
    table_rows = []
    growth_idx = header.index("ovr_growth")
    for row in rows:
        cells = []
        for i, value in enumerate(row):
            cls = ""
            if i == growth_idx and value:
                cls = "up" if value.startswith("+") and value != "+0" else ("down" if value.startswith("-") else "")
            cells.append(cell("td", value, cls))
        table_rows.append("<tr>" + "".join(cells) + "</tr>")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>My academy</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:"Segoe UI",system-ui,sans-serif;margin:0;background:#f4f6fb;color:#1d2433}}
header{{background:#1f7a4d;color:#fff;padding:24px 32px}}header h1{{margin:0;font-size:30px}}
header p{{margin:6px 0 0;font-size:17px;opacity:.9}}
main{{padding:24px 32px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:16px}}
.card{{background:#fff;border-radius:14px;padding:16px 18px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.card h2{{margin:0 0 2px;font-size:19px}}.meta{{color:#5b6475;font-size:14px}}
.nums{{display:flex;gap:18px;align-items:baseline;margin:10px 0 6px}}
.big{{font-size:34px;font-weight:700}}.arrow{{font-size:20px;font-weight:700}}
.up{{color:#1f9d55}}.down{{color:#c62828}}.flat{{color:#8a93a6}}
.pot{{font-size:15px;color:#3554d1}}
svg{{width:100%;height:70px}}
.legend{{font-size:12px;color:#5b6475}}
details{{margin-top:28px}}summary{{cursor:pointer;font-size:17px}}
table{{border-collapse:collapse;font-size:14px;background:#fff;margin-top:10px}}
th,td{{border:1px solid #d6dbe6;padding:4px 8px;text-align:left}}th{{background:#eef1f7}}
td.up{{font-weight:600}}
</style></head><body>
<header><h1>My academy</h1>
<p>{len(prospects)} players &middot; seasons: {html.escape(', '.join(seasons) or '-')} &middot; biggest growth first</p></header>
<main>
<div class="grid">
{cards}
</div>
<p class="legend">Green line = overall rating, dashed blue line = potential, one dot per export.</p>
<details><summary>Show the full table</summary>
<table><thead><tr>{''.join(cell('th', h) for h in header)}</tr></thead>
<tbody>
{chr(10).join(table_rows)}
</tbody></table></details>
</main>
</body></html>
"""
    paths["html"].write_text(page, encoding="utf-8")
    return paths
