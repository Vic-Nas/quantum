"""Render the 1200x630 share image with Pillow. Returns False (no image) if Pillow is unavailable."""
from pathlib import Path

from .present import TARGET_NAMES, TARGET_ORDER, date_label, headline, short_count

W, H = 1200, 630
INK, DIM, PAPER, ACCENT, RULE = (26, 24, 19), (98, 93, 80), (244, 241, 234), (194, 87, 12), (214, 210, 200)


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=font) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


def render(rows, as_of, out, fonts=Path("web/fonts"), domain=""):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    bold = ImageFont.truetype(str(fonts / "Geist-SemiBold.ttf"), 46)
    big = ImageFont.truetype(str(fonts / "Geist-SemiBold.ttf"), 76)
    mid = ImageFont.truetype(str(fonts / "Geist-SemiBold.ttf"), 26)
    small = ImageFont.truetype(str(fonts / "Geist-Regular.ttf"), 24)
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((60, 54, 96, 90), 8, fill=INK)
    d.line([(68, 64), (78, 64), (78, 73), (86, 73), (86, 82)], fill=(232, 119, 46), width=3, joint="curve")
    d.text((110, 58), "Quantum threat tracker", font=mid, fill=INK)
    y = 120
    for line in _wrap(d, "How close is quantum computing to breaking encryption?", bold, 1000):
        d.text((60, y), line, font=bold, fill=INK)
        y += 56
    col = 60
    for t in TARGET_ORDER:
        h = headline(rows, t)
        if not h:
            continue
        name, tech = TARGET_NAMES[t]
        x, base = col, 300
        d.line([(x, base - 20), (x + 520, base - 20)], fill=RULE, width=2)
        d.text((x, base), name, font=mid, fill=INK)
        d.text((x, base + 34), tech, font=small, fill=DIM)
        now = short_count(h["best"]["y"])
        if h["first"] is not h["best"]:
            was = short_count(h["first"]["y"])
            d.text((x, base + 84), was, font=mid, fill=DIM)
            wx = x + d.textlength(was, font=mid)
            d.line([(x, base + 99), (wx, base + 99)], fill=DIM, width=2)
            d.text((x, base + 120), now, font=big, fill=ACCENT)
            cap = f"qubits needed, {date_label(h['first']['date'], True)} to {date_label(h['best']['date'], True)}"
        else:
            d.text((x, base + 100), now, font=big, fill=ACCENT)
            cap = f"qubits needed, {date_label(h['best']['date'], True)}"
        d.text((x, base + 214), cap, font=small, fill=DIM)
        col += 580
    foot = ("Updated " + date_label(as_of) + "  |  " if as_of else "") + (domain or "Published estimates, each with its source")
    d.text((60, H - 46), foot, font=small, fill=DIM)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return True
