"""Draws the app's icons (no third-party artwork). Run: python tools/make_icons.py (needs Pillow)."""

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src" / "fcmh" / "assets"
S = 128
W = (255, 255, 255, 255)


def canvas():
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def play(d):
    d.polygon([(40, 26), (40, 102), (104, 64)], fill=W)


def plus(d):
    d.rounded_rectangle((54, 18, 74, 110), 8, fill=W)
    d.rounded_rectangle((18, 54, 110, 74), 8, fill=W)


def arc_arrow(d, start, end, clockwise=True):
    d.arc((22, 22, 106, 106), start, end, fill=W, width=14)
    ang = math.radians(end if clockwise else start)
    cx, cy = 64 + 42 * math.cos(ang), 64 + 42 * math.sin(ang)
    tangent = ang + (math.pi / 2 if clockwise else -math.pi / 2)
    tip = (cx + 22 * math.cos(tangent), cy + 22 * math.sin(tangent))
    left = (cx + 16 * math.cos(ang), cy + 16 * math.sin(ang))
    right = (cx - 16 * math.cos(ang), cy - 16 * math.sin(ang))
    d.polygon([tip, left, right], fill=W)


def update(d):
    arc_arrow(d, 200, 340)
    arc_arrow(d, 20, 160)


def backup(d):
    d.rounded_rectangle((22, 22, 106, 106), 12, fill=W)
    d.rectangle((38, 22, 90, 52), fill=(0, 0, 0, 0))
    d.rectangle((74, 28, 84, 46), fill=W)
    d.rounded_rectangle((36, 66, 92, 98), 6, fill=(0, 0, 0, 0))


def restore(d):
    arc_arrow(d, -60, 200, clockwise=False)
    d.rounded_rectangle((60, 40, 70, 68), 4, fill=W)
    d.rounded_rectangle((60, 60, 84, 70), 4, fill=W)


def star(d):
    pts = []
    for i in range(10):
        r = 50 if i % 2 == 0 else 21
        a = math.radians(-90 + i * 36)
        pts.append((64 + r * math.cos(a), 68 + r * math.sin(a)))
    d.polygon(pts, fill=W)


def globe(d):
    d.ellipse((18, 18, 110, 110), outline=W, width=10)
    d.ellipse((44, 18, 84, 110), outline=W, width=8)
    d.line((20, 64, 108, 64), fill=W, width=8)


def dots(d):
    for x in (34, 64, 94):
        d.ellipse((x - 10, 54, x + 10, 74), fill=W)


ICONS = {"play": play, "add": plus, "update": update, "backup": backup, "restore": restore,
         "academy": star, "online": globe, "more": dots}


def app_icon():
    img = canvas()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, 124, 124), 28, fill=(31, 122, 77, 255))
    d.ellipse((24, 24, 104, 104), fill=W)
    d.polygon([(54, 44), (54, 84), (86, 64)], fill=(31, 122, 77, 255))
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, draw in ICONS.items():
        img = canvas()
        draw(ImageDraw.Draw(img))
        img.save(OUT / f"{name}.png")
    icon = app_icon()
    icon.save(OUT / "app.png")
    icon.save(OUT / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128)])
    print("icons written to", OUT)
