"""Builds the twig concepts. Every mark is one stem (a stroked path, so it can be drawn on with stroke-dashoffset)
plus three leaves (separate filled paths with ids; data-origin is the point where each leaf joins the stem, so it can
grow from there). Canvas 256x256, scaled to fit and centred optically. Run: python build.py v3"""
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
INK = "#000"
GREEN = "#2E9E5E"
POINTS: list = []  # sampled outline points of the mark being built, for fitting and optical centring


def stroke_points(fn, w, n=32):
    for i in range(n + 1):
        x, y = fn(i / n)
        POINTS.extend([(x - w / 2, y - w / 2), (x + w / 2, y + w / 2)])


def leaf(base, angle_deg, length, width, ident, belly=0.66, tip=0.34):
    """A pointed leaf: two mirrored cubic curves from `base` to the tip, heading `angle_deg` (0 = right, -90 = up)."""
    a = math.radians(angle_deg)
    d = (math.cos(a), math.sin(a))
    p = (-d[1], d[0])
    bx, by = base

    def pt(t, s):
        return (bx + d[0] * length * t + p[0] * width * s, by + d[1] * length * t + p[1] * width * s)

    end = pt(1, 0)
    c1, c2, c3, c4 = pt(0.22, belly), pt(0.80, tip), pt(0.80, -tip), pt(0.22, -belly)
    for i in range(21):  # approximate outline for the bounding box
        t = i / 20
        for s in (1, -1):
            POINTS.append(pt(t, s * 0.5 * math.sin(math.pi * t ** 0.8)))
    f = lambda q: f"{q[0]:.2f} {q[1]:.2f}"
    return (f'<path id="{ident}" data-origin="{bx:.1f} {by:.1f}" '
            f'd="M{f(base)}C{f(c1)} {f(c2)} {f(end)}C{f(c3)} {f(c4)} {f(base)}Z"/>')


def qp(p0, c, p1, t):
    return tuple((1 - t) ** 2 * p0[i] + 2 * (1 - t) * t * c[i] + t * t * p1[i] for i in range(2))


def qa(p0, c, p1, t):
    dx = 2 * (1 - t) * (c[0] - p0[0]) + 2 * t * (p1[0] - c[0])
    dy = 2 * (1 - t) * (c[1] - p0[1]) + 2 * t * (p1[1] - c[1])
    return math.degrees(math.atan2(dy, dx))


def svg(body, color, box=200, centre=(128, 131)):
    xs, ys = [q[0] for q in POINTS], [q[1] for q in POINTS]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    k = box / max(w, h)
    tx, ty = centre[0] - k * (min(xs) + w / 2), centre[1] - k * (min(ys) + h / 2)
    POINTS.clear()
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'
            f'<g transform="translate({tx:.2f} {ty:.2f}) scale({k:.4f})" fill="{color}" stroke="{color}" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>\n')


def stem_path(p0, c, p1, w, ident="stem"):
    stroke_points(lambda t: qp(p0, c, p1, t), w)
    return (f'<path id="{ident}" fill="none" stroke-width="{w}" '
            f'd="M{p0[0]} {p0[1]}Q{c[0]} {c[1]} {p1[0]} {p1[1]}"/>')


def tip_leaf(end, angle, length, width, ident="leaf-3"):
    """The stem's end is tucked a quarter of the way into the tip leaf, so no round cap shows beside its base."""
    a = math.radians(angle)
    base = (end[0] - math.cos(a) * length * 0.25, end[1] - math.sin(a) * length * 0.25)
    return leaf(base, angle, length, width, ident)


W = 14  # stem weight (one weight for every concept)


def concept_a(color=INK):
    """Reach: the shoot leans forward and its tip leaf points up and out; leaves alternate and grow towards the tip."""
    p0, c, p1 = (84, 230), (92, 150), (160, 96)
    stem = stem_path(p0, c, p1, W)
    l1 = leaf(qp(p0, c, p1, 0.38), -160, 58, 30, "leaf-1")
    l2 = leaf(qp(p0, c, p1, 0.60), -92, 62, 32, "leaf-2")
    l3 = tip_leaf(p1, qa(p0, c, p1, 1.0) - 12, 80, 40)
    return svg(stem + f'<g stroke="none">{l1}{l2}{l3}</g>', color)


def concept_b(color=INK):
    """Sprig: a gently bowed shoot; side leaves stepping up in size like onboarding stages, the tip leaf largest."""
    p0, c, p1 = (70, 224), (110, 176), (162, 104)
    stem = stem_path(p0, c, p1, W)
    l1 = leaf(qp(p0, c, p1, 0.34), -100, 50, 26, "leaf-1")
    l2 = leaf(qp(p0, c, p1, 0.66), -8, 62, 32, "leaf-2")
    l3 = tip_leaf(p1, -66, 82, 42)
    return svg(stem + f'<g stroke="none">{l1}{l2}{l3}</g>', color)


def concept_c(color=INK):
    """Taken: the reaching shoot grows from a short cut stock across a small gap, the graft union."""
    stroke_points(lambda t: (82 + 12 * t, 238 - 21 * t), 18)
    stock = '<path id="stock" fill="none" stroke-width="18" d="M82 238L94 217"/>'
    p0, c, p1 = (104, 199), (114, 148), (166, 100)
    stem = stem_path(p0, c, p1, W - 1)
    l1 = leaf(qp(p0, c, p1, 0.34), -165, 54, 28, "leaf-1")
    l2 = leaf(qp(p0, c, p1, 0.67), -82, 60, 31, "leaf-2")
    l3 = tip_leaf(p1, qa(p0, c, p1, 1.0) - 12, 76, 38)
    return svg(stock + stem + f'<g stroke="none">{l1}{l2}{l3}</g>', color)


if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    for name, fn in (("a-reach", concept_a), ("b-sprig", concept_b), ("c-taken", concept_c)):
        (OUT / f"{name}-{version}.svg").write_text(fn(), encoding="utf-8")
        (OUT / f"{name}-{version}-green.svg").write_text(fn(GREEN), encoding="utf-8")
    print("written", version)
