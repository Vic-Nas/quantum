"""Server-rendered timeline chart (inline SVG). Pure: points in, markup out."""
import html
import math

from .present import clean, dom_id, short_count



def _e(x):
    return html.escape(str(x), quote=True)


def spread(ys, gap, lo, hi):
    """Move label positions apart so neighbours are at least `gap` apart, staying inside [lo, hi]. Keeps order."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    pos = [ys[i] for i in order]
    for _ in range(60):
        moved = False
        for k in range(1, len(pos)):
            if pos[k] - pos[k - 1] < gap - 1e-6:
                mid = (pos[k] + pos[k - 1]) / 2
                pos[k - 1], pos[k] = mid - gap / 2, mid + gap / 2
                moved = True
        pos = [min(max(p, lo), hi) for p in pos]
        if not moved:
            break
    out = [0.0] * len(ys)
    for i, p in zip(order, pos):
        out[i] = p
    return out


def overview_svg(lines, supply_phys, supply_log, width, height, label, today, narrow=False):
    """Everything on one chart. X is the year, Y is qubits (log).

    lines: [{'id','name','need','metric','year','practical','proxy','sub'}], one per attack.
    supply_*: announced machines as from breakdate.supply_points. Each attack line is read against the staircase of
    its own kind of qubit; a ring marks where that staircase first passes it.
    """
    if not lines:
        return ""
    l, t, b = 58, 24, 30
    r = 134 if narrow else 214
    xs = [p["year"] for p in supply_phys + supply_log] + [math.floor(today), math.floor(today) + 3]
    xs += [ln["year"] + 1 for ln in lines if ln.get("year")]
    x0, x1 = min(xs), max(xs) + 1
    vals = [ln["need"] for ln in lines] + [p["y"] for p in supply_phys + supply_log]
    lo, hi = math.floor(math.log10(min(vals))), math.ceil(math.log10(max(vals)))

    def px(x):
        return l + (x - x0) / (x1 - x0) * (width - l - r)

    def py(y):
        return t + (hi - math.log10(y)) / (hi - lo) * (height - t - b)

    out = [f'<svg class="tl ov" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{_e(label)}">']
    for k in range(lo, hi + 1):
        y = py(10 ** k)
        out.append(f'<line class="grid" x1="{l}" x2="{width - r}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text class="ax" x="{l - 8}" y="{y + 4:.1f}" text-anchor="end">{_e(short_count(10 ** k))}</text>')
    for yr in range(x0, x1, 1 if width - r - l > 330 else 2):
        out.append(f'<text class="ax" x="{px(yr + 0.5):.1f}" y="{height - 8}" text-anchor="middle">{yr}</text>')
    tx = px(today)
    out.append(f'<line class="today" x1="{tx:.1f}" x2="{tx:.1f}" y1="{t}" y2="{height - b}"/>'
               f'<text class="ax" x="{tx + 5:.1f}" y="{t + 12}" text-anchor="start">Today</text>')
    # the vendors' announced machines: one staircase per kind of qubit
    for pts, kind in ((supply_phys, "phys"), (supply_log, "log")):
        stair, top = [], None
        for p in pts:
            if p["record"]:
                if top is not None:
                    stair.append(f"H{px(p['year'] + 0.5):.1f}")
                stair.append(("M" if top is None else "V") + (f"{px(p['year'] + 0.5):.1f} {py(p['y']):.1f}" if top is None else f"{py(p['y']):.1f}"))
                top = p["y"]
        if stair:
            out.append(f'<path class="stair sup {kind}" d="{"".join(stair)}H{px(x1 - 0.2):.1f}" fill="none"/>')
    # attack lines with direct labels at the right edge
    xr = width - r
    want = [py(ln["need"]) for ln in lines]
    gap = 27 if narrow else 31
    placed = spread(want, gap, t + 8, height - b - 8)
    for ln, y, ly in zip(lines, want, placed):
        cls = ("need " + ln["metric"][:4]) + ("" if ln["practical"] else " weak")
        rid = ln["id"]
        out.append(f'<a class="atk" href="#{rid}" data-id="{rid}" aria-label="{_e(ln["name"] + ", " + ln["sub"])}">'
                   f'<line class="hit" x1="{l}" x2="{xr}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<line class="{cls}" x1="{l}" x2="{xr}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<path class="lead" d="M{xr:.1f} {y:.1f}L{xr + 8:.1f} {ly:.1f}" fill="none"/>'
                   f'<text class="nm" x="{xr + 12:.1f}" y="{ly - 1:.1f}">{_e(ln["name"])}</text>'
                   f'<text class="sb" x="{xr + 12:.1f}" y="{ly + 12:.1f}">{_e(ln["sub"])}</text></a>')
        if ln.get("year") and ln["practical"]:
            out.append(f'<circle class="cross" cx="{px(ln["year"] + 0.5):.1f}" cy="{y:.1f}" r="6.5"/>')
    for pts, kind in ((supply_phys, "phys"), (supply_log, "log")):
        for p in pts:
            hid = dom_id(p["row"]["id"])
            aria = f'{p["row"]["actor"]}, {short_count(p["y"])} {"physical" if kind == "phys" else "logical"} qubits by {p["year"]}'
            out.append(f'<a class="dot {kind}{" rec" if p["record"] else ""}" href="#{hid}" data-id="{hid}" aria-label="{_e(aria)}">'
                       f'<circle class="hit" cx="{px(p["year"] + 0.5):.1f}" cy="{py(p["y"]):.1f}" r="14"/>'
                       f'<circle class="pt" cx="{px(p["year"] + 0.5):.1f}" cy="{py(p["y"]):.1f}" r="6"/></a>')
    out.append("</svg>")
    return "".join(out)
