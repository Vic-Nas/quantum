"""Server-rendered timeline chart (inline SVG). Pure: points in, markup out."""
import html
import math

from .present import clean, dom_id, short_count

TICKS = [1e3, 1e4, 1e5, 1e6, 1e7, 1e8]


def _e(x):
    return html.escape(str(x), quote=True)


def timeline_svg(points, width, height, label, today=None):
    """One SVG sized to its box so text stays 1:1. Y is log scale (qubits), X is paper date."""
    if not points:
        return ""
    l, r, t, b = 62, 16, 16, 30
    xs = [p["x"] for p in points]
    now = max(xs) if today is None else max(today, max(xs))
    x0, x1 = math.floor(min(xs) - 0.4), math.ceil(now + 1.0)  # about a year of empty future on the right
    lo, hi = 3, 8
    ys = [math.log10(p["y"]) for p in points]
    lo, hi = min(lo, math.floor(min(ys))), max(hi, math.ceil(max(ys)))

    def px(x):
        return l + (x - x0) / (x1 - x0) * (width - l - r)

    def py(y):
        return t + (hi - math.log10(y)) / (hi - lo) * (height - t - b)

    out = [f'<svg class="tl" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{_e(label)}">']
    out.append(f'<rect class="future" x="{px(now):.1f}" y="{t}" width="{width - r - px(now):.1f}" height="{height - t - b}"/>'
               f'<line class="today" x1="{px(now):.1f}" x2="{px(now):.1f}" y1="{t}" y2="{height - b}"/>'
               f'<text class="ax" x="{px(now):.1f}" y="{t - 4}" text-anchor="middle">Today</text>')
    for tick in [10 ** k for k in range(lo, hi + 1)]:
        y = py(tick)
        out.append(f'<line class="grid" x1="{l}" x2="{width - r}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text class="ax" x="{l - 8}" y="{y + 4:.1f}" text-anchor="end">{_e(short_count(tick))}</text>')
    step = 1 if width > 500 else 2
    for yr in range(int(x0), int(x1) + 1, step):
        x = px(yr)
        out.append(f'<text class="ax" x="{x:.1f}" y="{height - 8}" text-anchor="middle">{yr}</text>')
    stair, best = [], None
    for p in points:
        if p["record"]:
            if best is not None:
                stair.append(f"H{px(p['x']):.1f}")
            stair.append(("M" if best is None else "V") + (f"{px(p['x']):.1f} {py(p['y']):.1f}" if best is None else f"{py(p['y']):.1f}"))
            best = p["y"]
    out.append(f'<path class="stair" d="{"".join(stair)}H{px(now):.1f}" fill="none"/>')  # ends today, never into the future
    for p in points:
        cx, cy = px(p["x"]), py(p["y"])
        rid = dom_id(p["row"]["id"])
        aria = f'{short_count(p["y"])} qubits, {p["date"]}, {clean(p["row"]["title"], 80)}'
        out.append(f'<a class="dot{" rec" if p["record"] else ""}" href="#{rid}" data-id="{rid}" aria-label="{_e(aria)}">'
                   f'<circle class="hit" cx="{cx:.1f}" cy="{cy:.1f}" r="15"/><circle class="pt" cx="{cx:.1f}" cy="{cy:.1f}" r="6.5"/></a>')
    first, last = points[0], [p for p in points if p["record"]][-1]
    if last is not first:  # label the current best beside its own dot, and the starting point above it
        out.append(f'<text class="lbl" x="{px(last["x"]) - 14:.1f}" y="{py(last["y"]) + 5:.1f}" text-anchor="end">{_e(short_count(last["y"]))}</text>')
    out.append(f'<text class="lbl" x="{px(first["x"]) + 12:.1f}" y="{py(first["y"]) - 12:.1f}" text-anchor="start">{_e(short_count(first["y"]))}</text>')
    out.append("</svg>")
    return "".join(out)
