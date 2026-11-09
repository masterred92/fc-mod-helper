"""Takes the README screenshots with fake demo data (no real game, no personal paths).

Linux:  xvfb-run -s "-screen 0 1280x1000x24" python tools/screenshots.py
Needs Tkinter and Pillow; the academy page also needs google-chrome or chromium.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "screenshots"

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from fcmh import app as app_mod  # noqa: E402
from fcmh import app_logic as logic  # noqa: E402
from fcmh import detect  # noqa: E402


def build_demo(base: Path) -> dict:
    c = base / "C"
    profile = c / "Users" / "Player"
    for sub in ("Downloads", "Desktop", "Documents"):
        (profile / sub).mkdir(parents=True)
    lad = profile / "AppData" / "Local"
    game = c / "Program Files" / "EA Games" / "EA SPORTS FC 26"
    (game / "FIFAModData").mkdir(parents=True)
    (game / "FC26.exe").write_bytes(b"demo")
    (lad / "EA SPORTS FC 26" / "settings").mkdir(parents=True)
    (lad / "EA SPORTS FC 26" / "settings" / "CmMgrDemo").write_bytes(b"demo save")
    (lad / "Temp" / "EA SPORTS FC26").mkdir(parents=True)
    fmm = profile / "Downloads" / "FIFA Mod Manager v2.1.1"
    fmm.mkdir(parents=True)
    (fmm / "FIFA Mod Manager.exe").write_bytes(b"demo")
    env = {"USERPROFILE": str(profile), "LOCALAPPDATA": str(lad), "APPDATA": str(profile / "AppData" / "Roaming"),
           "ProgramFiles": str(c / "Program Files"), "ProgramFiles(x86)": str(c / "Program Files (x86)"),
           "ProgramData": str(c / "ProgramData")}
    return {"c": c, "profile": profile, "env": env}


class DemoProbe(detect.Probe):
    def __init__(self, env):
        self._env = env

    def env(self, name):
        return self._env.get(name)

    def drives(self):
        return []

    def registry_values(self):
        return []


def detector(game, install):
    return {"tu": "1.6.6", "exe_version": "1.0.139.20381", "message": ""}


def grab(root: tk.Misc, name: str, pad: int = 0) -> None:
    root.update()
    root.after(250)
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    image = ImageGrab.grab(bbox=(x - pad, y - pad, x + w + pad, y + h + pad), xdisplay=os.environ.get("DISPLAY"))
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(OUT / name)
    print("saved", OUT / name)


def make_mod(folder: Path, name: str, data: bytes) -> Path:
    path = folder / name
    path.write_bytes(data)
    return path


def write_academy(folder: Path) -> None:
    players = [("460101", "Leo Hartmann", "ST", [(16, 58, 84), (16, 63, 85), (17, 69, 86)]),
               ("460102", "Tomas Okafor", "CB", [(17, 61, 79), (17, 64, 80), (18, 68, 81)]),
               ("460103", "Rui Mendes", "CAM", [(19, 66, 81), (19, 67, 81), (20, 70, 82)]),
               ("460104", "Sam Novak", "GK", [(15, 48, 88), (16, 52, 88), (16, 57, 89)]),
               ("460105", "Ali Haddad", "RW", [(17, 63, 77), (17, 63, 76), (18, 62, 74)])]
    dates = [("2026-08-01", "2026/27"), ("2027-01-15", "2026/27"), ("2027-08-01", "2027/28")]
    for i, (date, season) in enumerate(dates):
        with open(folder / f"fcmh_academy_{date}.csv", "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["export_date", "season", "source", "playerid", "name", "team", "age", "ovr", "pot",
                             "position", "playstyles_bits", "playstyles_plus_bits", "playstyles_count",
                             "playstyles_plus_count", "le_version"])
            for pid, name, pos, snaps in players:
                age, ovr, pot = snaps[i]
                writer.writerow([date, season, "academy", pid, name, "Demo Town FC", age, ovr, pot, pos, 3, 0, 2, 0, "demo"])


def write_scouting(folder: Path) -> None:
    head = ["game", "export_date", "playerid", "name", "age", "positions", "nationality", "ovr", "potential",
            "pot_swing_low", "pot_variance", "tier", "playstyles", "playstyles_plus", "traits", "status",
            "scout_report", "months_in_squad", "raw_styles", "le_version"]
    rows = [
        (460201, "Mateus Rocha", 15, "ST LW", "Brazil", 57, 88, "Technical; Rapid", "Finesse Shot; Chip Shot", "", 2),
        (460202, "Kofi Mensah", 14, "CM CDM", "Ghana", 52, 83, "Intercept; Tiki Taka", "Incisive Pass", "Team Player", 3),
        (460203, "Jonas Berg", 16, "GK", "Norway", 58, 81, "GK Far Reach", "", "", 2),
        (460204, "Diego Lopez", 17, "CB", "Spain", 63, 78, "Block; Anticipate", "", "", 1),
        (460205, "Yuto Sato", 16, "RW", "Japan", 59, 76, "Trickster; Quick Step", "", "", 3),
        (460206, "Liam Walsh", 17, "LB", "Ireland", 56, 69, "Relentless", "", "", 4),
        (460207, "Noah Klein", 16, "CAM", "Germany", 61, 86, "Technical", "Incisive Pass", "", 1),
    ]
    with open(folder / "scout_2026-09-01.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(head)
        for pid, name, age, pos, nat, ovr, pot, ps, psp, traits, var in rows:
            signed = "signed (guess)" if pid == 460207 else "not signed (guess)"
            writer.writerow(["FC 26", "2026-09-01", pid, name, age, pos, nat, ovr, pot, 0, var, 2, ps, psp, traits,
                             signed, "Scout A. Demo in Brazil" if nat == "Brazil" else "", 0, "", "demo"])


def main() -> None:
    base = Path(tempfile.mkdtemp(prefix="fcmh-demo-"))
    demo = build_demo(base)
    os.environ.update(demo["env"])
    prefix = str(demo["c"])

    def show(path) -> str:
        text = str(path)
        if text.startswith(prefix):
            text = "C:" + text[len(prefix):]
        return text.replace("/", "\\")

    ledger_path = Path(demo["env"]["APPDATA"]) / "fc-mod-helper" / "ledger.json"
    root = tk.Tk()
    root.geometry("940x780+0+0")
    app = app_mod.App(root, ledger_path, probe=DemoProbe(demo["env"]), detector=detector, no_wait=True)
    app.display_path = show
    app.keep_dialogs = True
    app.start()
    grab(root, "01-welcome.png")

    app.show_setup()
    grab(root, "02-setup.png")
    app.finish_setup()

    downloads = demo["profile"] / "Downloads"
    files = [make_mod(downloads, "YouthAcademyRedux_v1.2.fifamod", b"redux"),
             make_mod(downloads, "KIARIKA_Optimization_Overhaul.fifamod", b"opt"),
             make_mod(downloads, "Complete_Player_Development.fifamod", b"cpd"),
             make_mod(downloads, "Better-Regen-Minifaces.fifamod", b"faces")]
    logic.add_mod_files(app.ledger, files)
    app.show_main()
    logic.backup_now(app.ledger, now=dt.datetime.now() - dt.timedelta(days=3))
    logic.backup_now(app.ledger, label="auto", now=dt.datetime.now() - dt.timedelta(hours=2))
    grab(root, "03-main.png")

    clash = make_mod(downloads, "Youth Academy Re-adjusted v3.fifamod", b"readj")
    logic.add_mod_files(app.ledger, [clash])
    app.refresh_status()
    grab(root, "04-needs-a-fix.png")

    app.auto_answers = [None]
    app.on_play()
    grab(root, "05-play-safely.png")
    if app.open_dialog:
        app.open_dialog.close(None)

    app.auto_answers = [None]
    app.on_restore()
    grab(root, "06-restore.png")
    if app.open_dialog:
        app.open_dialog.close(None)

    app.auto_answers = [None]
    app.on_online()
    grab(root, "07-online.png")
    if app.open_dialog:
        app.open_dialog.close(None)

    write_scouting(logic.scouting_dir(app.ledger))
    app.scout_show_signed = True
    app.on_scout()
    grab(root, "09-scout-preview.png")
    root.destroy()

    academy_dir = Path(app.ledger.resolved_paths().get("academy_dir"))
    write_academy(academy_dir)
    from fcmh import academy
    report = academy.write_report(academy.merge(academy.collect([academy_dir])), academy_dir / "report")["html"]
    browser = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if browser:
        subprocess.run([browser, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--screenshot={OUT / '08-academy-report.png'}", "--window-size=1100,760",
                        report.as_uri()], check=False, capture_output=True, timeout=60)
        print("saved", OUT / "08-academy-report.png")
    shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    main()
