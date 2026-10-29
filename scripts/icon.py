"""saltFlow's icon: a salt-white plate over the navy ground, the motif cut out of it as salt grains so the ground
shows through, flat. The motif is a flow: two steps whose moves join on a third, the step under review, cut as one
solid shape. Grains are deterministic (seed 3), so the icon rebuilds the same. Needs Pillow (pip install pillow).

  python3 scripts/icon.py      writes src/saltflow/icon.svg (the plate) and src/saltflow/icon.png (512, for the iPad)
"""
import math
import os
import random

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "src", "saltflow")
S, NAVY, SALT = 1024, "#1d2b3e", "#fbfaf5"
rng = random.Random(3)
grains = []                                 # (cx, cy, size, angle)


K = 1.24                                    # how far the motif fills the plate


def at(v):
    return 512 + (v - 512) * K


def grain(cx, cy, lo=9, hi=20):
    grains.append((at(cx), at(cy), rng.uniform(lo, hi) * K, rng.uniform(0, 90)))


def step_box(x0, y0, x1, y1, n):            # a step: a rounded box filled with grains, ragged at its edge like salt
    r = 40
    for _ in range(n):
        x, y = rng.uniform(x0 - 8, x1 + 8), rng.uniform(y0 - 8, y1 + 8)
        cx, cy = min(max(x, x0 + r), x1 - r), min(max(y, y0 + r), y1 - r)
        if math.hypot(x - cx, y - cy) <= r + rng.uniform(-6, 10):
            grain(x, y, 10, 22)


def move(p0, p1, p2, n, w=26):              # a move: a band of grains along a curve
    for i in range(n):
        t = rng.random() * 0.86              # a margin of salt before the step under review
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
        grain(x + rng.uniform(-w / 2, w / 2), y + rng.uniform(-w / 2, w / 2), 10, 22)


step_box(176, 236, 420, 420, 420)
step_box(176, 604, 420, 788, 420)
move((410, 328), (575, 328), (640, 470), 120)
move((410, 696), (575, 696), (640, 554), 120)
here = tuple(at(v) for v in (624, 420, 860, 604))   # the step under review: one solid cut

with open(os.path.join(OUT, "icon.svg"), "w") as f:
    f.write('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d"><defs><mask id="k" '
            'maskUnits="userSpaceOnUse" x="0" y="0" width="%d" height="%d"><rect width="%d" height="%d" fill="#fff"/>'
            '<g fill="#000">' % ((S,) * 8))
    for cx, cy, s, a in grains:
        f.write('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" transform="rotate(%.1f %.1f %.1f)"/>'
                % (cx - s / 2, cy - s / 2, s, s, s * 0.12, a, cx, cy))
    f.write('<rect x="%.0f" y="%.0f" width="%.0f" height="%.0f" rx="44"/></g></mask></defs>' % (here[0], here[1], here[2] - here[0], here[3] - here[1]))
    f.write('<rect width="%d" height="%d" fill="%s"/><rect width="%d" height="%d" fill="%s" mask="url(#k)"/></svg>\n' % (S, S, NAVY, S, S, SALT))

big = Image.new("RGB", (S * 2, S * 2), SALT)  # drawn at twice the size, then halved twice: clean edges at 512
d = ImageDraw.Draw(big)
for cx, cy, s, a in grains:
    r = s, math.radians(a)
    pts = [(cx + dx * math.cos(r[1]) - dy * math.sin(r[1]), cy + dx * math.sin(r[1]) + dy * math.cos(r[1]))
           for dx, dy in ((-s / 2, -s / 2), (s / 2, -s / 2), (s / 2, s / 2), (-s / 2, s / 2))]
    d.polygon([(x * 2, y * 2) for x, y in pts], fill=NAVY)
d.rounded_rectangle([v * 2 for v in here], radius=88, fill=NAVY)
big.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "icon.png"))
print("%d grains; src/saltflow/icon.svg and icon.png" % len(grains))
