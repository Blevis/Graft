"""Builds the final Graft "Reach" mark and every delivery file from one geometry.

The mark: a small twig that leans forward and reaches up and out, with three leaves that alternate and grow towards
the tip. Construction (raw units, before fitting to the 256 canvas):
- stem: quadratic curve (84,230) -> control (92,150) -> (160,96), round ends;
- leaf: two mirrored cubic curves; controls at 22% length / 66% width and 80% length / 34% width (pointed tip);
- leaf 1 at 38% of the stem heading -160 deg, leaf 2 at 60% heading -92 deg, leaf 3 continues the stem 12 deg
  steeper (reaching), with the stem end tucked a quarter of the way into it so no round cap shows.
Run from the repo root: python docs/brand/build_logo.py"""
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend" / "public" / "orchid"
GREEN = "#2E9E5E"   # leaf green: 3.1:1 on #F6F5FA, 5.4:1 on the #160E2E sidebar
INK = "#211B35"
WHITE = "#FFFFFF"
WORDMARK = (ROOT / "docs" / "brand" / "concepts" / "wordmark.d").read_text(encoding="utf-8").strip()

P0, C, P1 = (84.0, 230.0), (92.0, 150.0), (160.0, 96.0)


def qp(t):
    return tuple((1 - t) ** 2 * P0[i] + 2 * (1 - t) * t * C[i] + t * t * P1[i] for i in range(2))


def qa(t):
    dx = 2 * (1 - t) * (C[0] - P0[0]) + 2 * t * (P1[0] - C[0])
    dy = 2 * (1 - t) * (C[1] - P0[1]) + 2 * t * (P1[1] - C[1])
    return math.degrees(math.atan2(dy, dx))


class Mark:
    """Geometry for one cut of the mark (regular or small), in raw units."""

    def __init__(self, stem_w, leaf_scale=1.0):
        self.w = stem_w
        s = leaf_scale
        self.leaves = [
            self._leaf(qp(0.38), -160, 58 * s, 30 * s),
            self._leaf(qp(0.60), -92, 62 * s, 32 * s),
            self._tip_leaf(qa(1.0) - 12, 80 * s, 40 * s),
        ]

    @staticmethod
    def _leaf(base, angle, length, width):
        a = math.radians(angle)
        d, p = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))

        def pt(t, s):
            return (base[0] + d[0] * length * t + p[0] * width * s, base[1] + d[1] * length * t + p[1] * width * s)

        return {"base": base, "pts": [base, pt(0.22, 0.66), pt(0.80, 0.34), pt(1, 0), pt(0.80, -0.34),
                                      pt(0.22, -0.66), base]}

    def _tip_leaf(self, angle, length, width):
        a = math.radians(angle)
        base = (P1[0] - math.cos(a) * length * 0.25, P1[1] - math.sin(a) * length * 0.25)
        return self._leaf(base, angle, length, width)

    def stem_outline(self):
        """The stroked stem as a filled outline: offset control polygon (Tiller-Hanson) plus two round caps."""
        r = self.w / 2

        def normal(a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            n = math.hypot(dx, dy)
            return (-dy / n, dx / n)

        def side(sign):
            n1, n2 = normal(P0, C), normal(C, P1)
            a0 = (P0[0] + sign * r * n1[0], P0[1] + sign * r * n1[1])
            a1 = (C[0] + sign * r * n1[0], C[1] + sign * r * n1[1])
            b0 = (C[0] + sign * r * n2[0], C[1] + sign * r * n2[1])
            b1 = (P1[0] + sign * r * n2[0], P1[1] + sign * r * n2[1])
            # intersection of line a0-a1 with line b0-b1 is the offset control point
            d1, d2 = (a1[0] - a0[0], a1[1] - a0[1]), (b1[0] - b0[0], b1[1] - b0[1])
            den = d1[0] * d2[1] - d1[1] * d2[0]
            t = ((b0[0] - a0[0]) * d2[1] - (b0[1] - a0[1]) * d2[0]) / den
            return a0, (a0[0] + d1[0] * t, a0[1] + d1[1] * t), b1

        return side(1), side(-1), r

    def points(self):
        pts = []
        for i in range(33):
            x, y = qp(i / 32)
            pts += [(x - self.w / 2, y - self.w / 2), (x + self.w / 2, y + self.w / 2)]
        for lf in self.leaves:
            b, c1, c2, tip, c3, c4, _ = lf["pts"]
            for i in range(21):
                t = i / 20
                for seg in ((b, c1, c2, tip), (tip, c3, c4, b)):
                    pts.append(tuple((1 - t) ** 3 * seg[0][k] + 3 * (1 - t) ** 2 * t * seg[1][k]
                                     + 3 * (1 - t) * t * t * seg[2][k] + t ** 3 * seg[3][k] for k in range(2)))
        return pts


def fit(mark, box, size=256, lift=0.0):
    """Scale + translate so the mark's bounds fill `box` inside a `size` square, nudged up by `lift` (optical centre)."""
    pts = mark.points()
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    k = box / max(w, h)
    tx = size / 2 - k * (min(xs) + w / 2)
    ty = size / 2 - lift * size - k * (min(ys) + h / 2)
    return lambda p: (round(p[0] * k + tx, 2), round(p[1] * k + ty, 2)), k


def f(p):
    return f"{p[0]:g} {p[1]:g}"


def leaf_d(lf, T):
    b, c1, c2, tip, c3, c4, _ = [T(p) for p in lf["pts"]]
    return f"M{f(b)}C{f(c1)} {f(c2)} {f(tip)}C{f(c3)} {f(c4)} {f(b)}Z"


def stem_d(mark, T, k):
    (l0, lc, l1), (r0, rc, r1), r = mark.stem_outline()
    rr = round(r * k, 2)
    return (f"M{f(T(l0))}Q{f(T(lc))} {f(T(l1))}A{rr:g} {rr:g} 0 0 0 {f(T(r1))}"
            f"Q{f(T(rc))} {f(T(r0))}A{rr:g} {rr:g} 0 0 0 {f(T(l0))}Z")


def symbol_body(mark, T, k, color):
    paths = [stem_d(mark, T, k)] + [leaf_d(lf, T) for lf in mark.leaves]
    return f'<path fill="{color}" d="{"".join(paths)}"/>'


def svg(body, w=256, h=256, title="Graft"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" viewBox="0 0 {w:g} {h:g}" '
            f'role="img" aria-label="{title}"><title>{title}</title>{body}</svg>\n')


def animated(mark, T, k):
    """Same geometry, kept as parts: the stem as a centre-line stroke (draw-on) and three leaves that grow from where
    they join the stem. Pure CSS; respects prefers-reduced-motion. Ids: stem, leaf-1..3."""
    p0, c, p1 = T(P0), T(C), T(P1)
    leaves = "".join(
        f'<path id="leaf-{i}" class="leaf" style="transform-origin:{T(lf["base"])[0]}px {T(lf["base"])[1]}px;'
        f'animation-delay:{0.45 + 0.18 * i:.2f}s" d="{leaf_d(lf, T)}"/>'
        for i, lf in enumerate(mark.leaves, 1))
    css = ("#stem{stroke-dasharray:1;stroke-dashoffset:1;animation:draw .7s cubic-bezier(.4,0,.2,1) forwards}"
           ".leaf{transform-box:view-box;transform:scale(0);animation:grow .45s cubic-bezier(.34,1.56,.64,1) forwards}"
           "@keyframes draw{to{stroke-dashoffset:0}}@keyframes grow{to{transform:scale(1)}}"
           "@media (prefers-reduced-motion:reduce){#stem,.leaf{animation:none;stroke-dashoffset:0;transform:none}}")
    return svg(f"<style>{css}</style>"
               f'<path id="stem" pathLength="1" fill="none" stroke="{GREEN}" stroke-width="{mark.w * k:.2f}" '
               f'stroke-linecap="round" d="M{f(p0)}Q{f(c)} {f(p1)}"/>'
               f'<g fill="{GREEN}">{leaves}</g>', title="Graft (animated)")


def lockup(symbol_svg_body, word_color, word_k=5.6, gap=18, size=256):
    """Horizontal lockup: twig at 256 high, wordmark cap-centred, gap measured from the twig's right edge."""
    x0 = 214 + gap - 48 * word_k
    width = round(214 + gap + (106 - 48) * word_k + 6)
    return svg(f'<g transform="translate(-20 0)">{symbol_svg_body}</g>'
               f'<g transform="translate({x0:.1f} {size / 2 - 16 * word_k:.1f}) scale({word_k})">'
               f'<path fill="{word_color}" d="{WORDMARK}"/></g>', w=width, h=size)


def stacked(symbol_svg_body, word_color, word_k=4.2):
    width = round(58 * word_k + 24)
    sym_x = (width - 256) / 2
    return svg(f'<g transform="translate({sym_x:.1f} 0)">{symbol_svg_body}</g>'
               f'<g transform="translate({width / 2 - 77 * word_k:.1f} {256 - 2 * word_k:.1f}) scale({word_k})">'
               f'<path fill="{word_color}" d="{WORDMARK}"/></g>', w=width, h=256 + 30 * word_k)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reg, small = Mark(14), Mark(24, leaf_scale=1.1)
    T, k = fit(reg, 212, lift=0.01)
    Ts, ks = fit(small, 236, lift=0.0)
    files = {
        "graft-mark.svg": svg(symbol_body(reg, T, k, GREEN)),
        "graft-mark-small.svg": svg(symbol_body(small, Ts, ks, GREEN)),
        "graft-mark-white.svg": svg(symbol_body(reg, T, k, WHITE)),
        "graft-mark-ink.svg": svg(symbol_body(reg, T, k, INK)),
        "graft-mark-current.svg": svg(symbol_body(reg, T, k, "currentColor")),
        "graft-animated.svg": animated(reg, T, k),
        "graft-lockup-light.svg": lockup(symbol_body(reg, T, k, GREEN), INK),
        "graft-lockup-dark.svg": lockup(symbol_body(reg, T, k, GREEN), WHITE),
        "graft-lockup-stacked.svg": stacked(symbol_body(reg, T, k, GREEN), INK),
    }
    # UI icon (sidebar 40 px, header 32 px): the regular cut cropped tight (no inner clear space), so it matches the
    # wordmark's height; the layout's gap supplies the clear space. Favicon: the small cut.
    Tu, ku = fit(reg, 254)
    files["graft.svg"] = svg(symbol_body(reg, Tu, ku, GREEN))
    files["graft-favicon.svg"] = files["graft-mark-small.svg"]
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8")
    print("\n".join(sorted(files)))


if __name__ == "__main__":
    main()
