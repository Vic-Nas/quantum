"""Render the 1200x630 share image with Pillow. Returns False (no image) if Pillow is unavailable."""
from pathlib import Path

from .breakdate import earliest_path
from .present import TARGET_NAMES, TARGET_ORDER, date_label, headline, short_count, year_label

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


def render(rows, hw_rows, as_of, out, fonts=Path("web/fonts"), domain=""):
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
        path = earliest_path(rows, hw_rows, t)
        if path.get("year"):
            d.text((x, base + 78), year_label(path["year"], path.get("month")), font=big, fill=ACCENT)
            d.text((x, base + 172), "earliest announced path to break it", font=small, fill=DIM)
            d.text((x, base + 204), f"needs {short_count(path['need'])} qubits; {path['supply']['actor']} plans {short_count(path['supply'][path['metric']])}",
                   font=small, fill=DIM)
        else:
            d.text((x, base + 90), "No date yet", font=big, fill=DIM)
            d.text((x, base + 188), path["reason"], font=small, fill=DIM)
        col += 580
    foot = ("Updated " + date_label(as_of) + "  |  " if as_of else "") + (domain or "Published estimates, each with its source")
    d.text((60, H - 46), foot, font=small, fill=DIM)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return True
