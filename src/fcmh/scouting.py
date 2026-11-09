"""Scout preview: read the scout CSV, give stars, pick who to sign, make a web page.

The CSV comes from lua/fcmh_scout_preview.lua (run inside Live Editor). Nothing here
talks to the game. Words on screen are plain on purpose: "not signed yet", "stars",
"Sign him".
"""

from __future__ import annotations

import copy
import csv
import html
import json
import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

GRADES_NAME = "scout-grades.json"
CSV_GLOB = "scout_*.csv"


# ------------------------------------------------------------------ settings
def default_grades() -> dict:
    return json.loads(resources.files("fcmh.data").joinpath(GRADES_NAME).read_text(encoding="utf-8"))


def load_grades(folder: Path | None = None) -> dict:
    """Default settings, overridden by Scouting/scout-grades.json if the player edited one."""
    grades = default_grades()
    if folder is None:
        return grades
    path = Path(folder) / GRADES_NAME
    if not path.exists():
        return grades
    try:
        user = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return grades
    merged = copy.deepcopy(grades)
    if isinstance(user.get("stars"), list) and user["stars"]:
        merged["stars"] = user["stars"]
    if isinstance(user.get("screen_range_percent"), list):
        merged["screen_range_percent"] = user["screen_range_percent"]
    if isinstance(user.get("sign_him"), dict):
        merged["sign_him"].update(user["sign_him"])
    return merged


def ensure_grades_file(folder: Path) -> Path:
    """Puts an editable copy of the settings next to the scout files (never overwrites)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / GRADES_NAME
    if not path.exists():
        path.write_text(json.dumps(default_grades(), indent=2) + "\n", encoding="utf-8")
    return path


def stars_for(potential: int | None, grades: dict) -> float:
    if potential is None:
        return 0.0
    for step in sorted(grades["stars"], key=lambda s: s["min_potential"], reverse=True):
        if potential >= step["min_potential"]:
            return float(step["stars"])
    return 0.0


def range_guess(potential: int | None, variance: int | None, grades: dict) -> tuple[int, int] | None:
    """GUESS at the potential range the game shows on screen.

    FIFA 18's scout.ini had POTENTIAL_VARIANCE_PERC_0..5 ("only for the screens") and the
    cheat table's 'Reveal Ovr & Pot' zeroes that list to show the exact number. We assume
    career_youthplayers.potentialvariance picks the entry. FC 26 values are not known.
    """
    table = grades.get("screen_range_percent") or []
    if potential is None or variance is None or not table:
        return None
    perc = table[min(max(variance, 0), len(table) - 1)]
    width = round(potential * perc / 100)
    low = max(potential - width // 2, 1)
    return (low, min(low + width, 99))


def star_text(stars: float) -> str:
    full = int(stars)
    half = stars - full >= 0.5
    empty = 5 - full - (1 if half else 0)
    return "\u2605" * full + ("\u00bd" if half else "") + "\u2606" * max(empty, 0)


# ------------------------------------------------------------------ players
def _int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _list(value) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


@dataclass
class ScoutPlayer:
    playerid: int
    name: str
    age: int | None
    positions: str
    nationality: str
    ovr: int | None
    potential: int | None
    swing_low: int | None = None
    variance: int | None = None
    playstyles: list[str] = field(default_factory=list)
    playstyles_plus: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    signed: bool = False
    scout_report: str = ""
    stars: float = 0.0
    score: float = 0.0
    sign_him: bool = False
    reason: str = ""

    range_guess: tuple[int, int] | None = None  # GUESS at the in-game range, see docs/scout-preview.md

    @property
    def stars_text(self) -> str:
        return star_text(self.stars)


def parse_rows(rows: list[dict]) -> list[ScoutPlayer]:
    players = []
    for row in rows:
        pid = _int(row.get("playerid"))
        if pid is None:
            continue
        status = (row.get("status") or "").lower()
        players.append(ScoutPlayer(
            playerid=pid,
            name=(row.get("name") or f"Player {pid}").strip(),
            age=_int(row.get("age")),
            positions=(row.get("positions") or "").strip(),
            nationality=(row.get("nationality") or "").strip(),
            ovr=_int(row.get("ovr")),
            potential=_int(row.get("potential")),
            swing_low=_int(row.get("pot_swing_low")),
            variance=_int(row.get("pot_variance")),
            playstyles=_list(row.get("playstyles")),
            playstyles_plus=_list(row.get("playstyles_plus")),
            traits=_list(row.get("traits")),
            signed=status.startswith("signed"),
            scout_report=(row.get("scout_report") or "").strip(),
        ))
    return players


def grade(players: list[ScoutPlayer], grades: dict) -> list[ScoutPlayer]:
    """Adds stars, a score, the 'Sign him' badge and a one-line reason. Best first."""
    rules = grades["sign_him"]
    for p in players:
        p.stars = stars_for(p.potential, grades)
        p.range_guess = range_guess(p.potential, p.variance, grades)
        young = max(rules["young_age"] - p.age, 0) if p.age is not None else 0
        p.score = ((p.potential or 0) + young * rules["bonus_per_year_younger"]
                   + len(p.playstyles_plus) * rules["bonus_per_playstyle_plus"])
        p.sign_him = False
        p.reason = reason_line(p)
    ranked = sorted(players, key=lambda p: (-p.score, -(p.potential or 0), p.age or 99, p.name))
    picked = 0
    for p in ranked:
        if picked >= rules["how_many"]:
            break
        if not p.signed and (p.potential or 0) >= rules["min_potential"]:
            p.sign_him = True
            picked += 1
    return ranked


def reason_line(p: ScoutPlayer) -> str:
    parts = [f"Potential {p.potential if p.potential is not None else '?'}"]
    if p.age is not None:
        parts.append(f"age {p.age}")
    if p.playstyles_plus:
        n = len(p.playstyles_plus)
        parts.append(f"{n} PlayStyle+" if n == 1 else f"{n} PlayStyles+")
    return ", ".join(parts)


def load_csv(path: Path, grades: dict | None = None) -> list[ScoutPlayer]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return grade(parse_rows(rows), grades or default_grades())


def newest_csv(folders: list[Path]) -> Path | None:
    files = []
    for folder in folders:
        if folder and Path(folder).is_dir():
            files += [f for f in Path(folder).glob(CSV_GLOB) if f.is_file()]
    if not files:
        return None
    return max(files, key=lambda f: (f.stat().st_mtime_ns, f.name))


def newest_table_dump(folder: Path) -> Path | None:
    files = list(Path(folder).glob("scout_*_tables.txt")) if Path(folder).is_dir() else []
    return max(files, key=lambda f: f.stat().st_mtime_ns) if files else None


# ------------------------------------------------------------------ web page
def write_html(players: list[ScoutPlayer], path: Path, *, source: str = "", game: str = "FC 26") -> Path:
    def chips(items, cls):
        return "".join(f'<span class="chip {cls}">{html.escape(i)}</span>' for i in items)

    cards = []
    for p in players:
        rng = p.range_guess
        badge = '<span class="badge">SIGN HIM</span>' if p.sign_him else ""
        signed = '<span class="signed">Already signed</span>' if p.signed else ""
        cards.append(f"""
<div class="card{' best' if p.sign_him else ''}{' done' if p.signed else ''}">
  <div class="top"><div><div class="name">{html.escape(p.name)} {badge}{signed}</div>
  <div class="meta">Age {p.age if p.age is not None else '?'} &middot; {html.escape(p.positions or '?')} &middot; {html.escape(p.nationality or '?')}</div></div>
  <div class="pot"><div class="num">{p.potential if p.potential is not None else '?'}</div><div class="lbl">potential</div></div></div>
  <div class="stars">{p.stars_text}</div>
  <div class="row">Now: <b>{p.ovr if p.ovr is not None else '?'}</b>{f' &middot; Range (guess): {rng[0]}-{rng[1]}' if rng else ''}</div>
  <div class="row">{chips(p.playstyles_plus, 'plus')}{chips(p.playstyles, 'ps')}{chips(p.traits, 'trait')}</div>
  <div class="why">{html.escape(p.reason)}</div>
  {f'<div class="from">Found by {html.escape(p.scout_report)}</div>' if p.scout_report else ''}
</div>""")
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Scout preview</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f6fb;color:#1d2433;margin:24px}}
h1{{margin:0}} .sub{{color:#5b6475;margin:4px 0 18px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
.card{{background:#fff;border-radius:12px;padding:14px 16px;border:2px solid #e3e7ef}}
.card.best{{border-color:#1f9d55;background:#f3fbf6}} .card.done{{opacity:.6}}
.top{{display:flex;justify-content:space-between;gap:8px}} .name{{font-size:18px;font-weight:700}}
.meta{{color:#5b6475}} .pot .num{{font-size:30px;font-weight:800;color:#3554d1;text-align:right}}
.pot .lbl{{font-size:11px;color:#5b6475;text-align:right}}
.stars{{color:#e0a800;font-size:22px;letter-spacing:2px}}
.chip{{display:inline-block;border-radius:10px;padding:2px 8px;margin:2px;font-size:12px}}
.chip.plus{{background:#ffe08a;color:#6b4b00;font-weight:700}} .chip.plus::after{{content:" +"}}
.chip.ps{{background:#e6e9f0}} .chip.trait{{background:#efe6fb;color:#5b4bc4}}
.badge{{background:#1f9d55;color:#fff;border-radius:8px;padding:2px 8px;font-size:12px;margin-left:6px}}
.signed{{background:#cfd5e1;border-radius:8px;padding:2px 8px;font-size:12px;margin-left:6px}}
.why{{margin-top:6px;font-weight:600}} .from{{color:#5b6475;font-size:12px;margin-top:4px}} .row{{margin-top:4px}}
</style></head><body>
<h1>Scout preview &middot; {html.escape(game)}</h1>
<div class="sub">{len([p for p in players if not p.signed])} players not signed yet{(' &middot; from ' + html.escape(source)) if source else ''}. Gold chips are PlayStyles+. "Range" is a guess.</div>
<div class="grid">{''.join(cards)}</div>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path


def desktop_csvs() -> list[Path]:
    profile = os.environ.get("USERPROFILE") or str(Path.home())
    desktop = Path(profile) / "Desktop"
    return sorted(desktop.glob(CSV_GLOB)) if desktop.is_dir() else []
