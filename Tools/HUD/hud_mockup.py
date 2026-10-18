"""Andrew's Airsoft - neon HUD mockup.

Paints an approximation of the Slate HUD (Source/AndrewsAirsoft/Private/UI/SAirsoftHUD.cpp,
SAirsoftHUDCanvas.cpp, SAirsoftNeon.cpp) over a game still, using the same 1080p layout units,
sizes, colours, chamfers, glow passes, bar segments and weapon glyph shapes. For checking the look
without the editor; it is not pixel exact (Liberation Sans stands in for Roboto).

    python3 Tools/HUD/hud_mockup.py                 # both mockups into Docs/Screens
    python3 Tools/HUD/hud_mockup.py story OUT.jpg   # one variant
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SS = 2  # supersampling

FONT_DIRS = ["/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/dejavu", "C:/Windows/Fonts"]
FONT_FILES = {
    "Bold": ["LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"],
    "Regular": ["LiberationSans-Regular.ttf", "DejaVuSans.ttf", "arial.ttf"],
}


def find_font(weight):
    for d in FONT_DIRS:
        for f in FONT_FILES[weight]:
            p = os.path.join(d, f)
            if os.path.exists(p):
                return p
    raise SystemExit("no font found")


def srgb(r, g, b, a=1.0):
    return (r / 255.0, g / 255.0, b / 255.0, a)


# --- Palette (SAirsoftNeon.cpp) ---------------------------------------------------------------
CYAN = srgb(0, 229, 255)
CYAN_DEEP = srgb(0, 120, 190)
ORANGE = srgb(255, 128, 32)
AMBER = srgb(255, 196, 64)
RED = srgb(255, 40, 72)
MAGENTA = srgb(255, 48, 170)
GLASS = (0.04, 0.07, 0.10, 0.62)  # linear (0.0015, 0.004, 0.009) shown in sRGB
TRACK = (0.62, 0.88, 1.0, 0.08)
WHITE = (1.0, 1.0, 1.0, 1.0)
BLUE_TEAM = srgb(70, 140, 255)
RED_TEAM = srgb(255, 72, 64)

DIAGONAL, DIAGONAL_ALT, LEFT, RIGHT, BOTTOM, ALL = 5, 10, 9, 6, 12, 15
TL, TR, BR, BL = 1, 2, 4, 8


def alpha(c, a):
    return (c[0], c[1], c[2], c[3] * a)


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


class Painter:
    def __init__(self, background):
        self.bg = background.convert("RGBA")
        self.W, self.H = self.bg.size
        self.u = self.W / 1920.0  # HUD units -> output pixels
        self.s = self.u * SS
        self.img = self.bg.resize((self.W * SS, self.H * SS), Image.BICUBIC)
        self.fonts = {}

    # Coordinates are in 1080p HUD units.
    def P(self, x, y):
        return (x * self.s, y * self.s)

    def _col(self, c):
        return tuple(int(round(max(0.0, min(1.0, v)) * 255)) for v in c)

    def _layer(self, draw_fn, bbox):
        x0, y0, x1, y1 = [int(v) for v in bbox]
        x0, y0 = max(0, x0 - 2), max(0, y0 - 2)
        x1, y1 = min(self.img.width, x1 + 2), min(self.img.height, y1 + 2)
        if x1 <= x0 or y1 <= y0:
            return
        lay = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        draw_fn(d, x0, y0)
        self.img.alpha_composite(lay, dest=(x0, y0))

    def poly(self, pts, color):
        if color[3] <= 0 or len(pts) < 3:
            return
        sp = [self.P(*p) for p in pts]
        xs = [p[0] for p in sp]
        ys = [p[1] for p in sp]
        self._layer(lambda d, ox, oy: d.polygon([(x - ox, y - oy) for x, y in sp], fill=self._col(color)),
                    (min(xs), min(ys), max(xs) + 1, max(ys) + 1))

    def rect(self, x, y, w, h, color):
        if w > 0 and h > 0:
            self.poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], color)

    def polyline(self, pts, color, thick, closed):
        if color[3] <= 0 or len(pts) < 2:
            return
        sp = [self.P(*p) for p in pts]
        if closed:
            sp = sp + [sp[0]]
        w = max(1, int(round(thick * self.s)))
        xs = [p[0] for p in sp]
        ys = [p[1] for p in sp]
        pad = w
        col = self._col(color)

        def draw(d, ox, oy):
            pts2 = [(x - ox, y - oy) for x, y in sp]
            # Slate draws each segment on its own: no joins.
            for a, b in zip(pts2, pts2[1:]):
                d.line([a, b], fill=col, width=w)

        self._layer(draw, (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad))

    def glow_polyline(self, pts, color, thick, glow, closed):
        if glow > 0:
            self.polyline(pts, alpha(color, 0.06 * glow), thick + 12, closed)
            self.polyline(pts, alpha(color, 0.13 * glow), thick + 6, closed)
            self.polyline(pts, alpha(color, 0.30 * glow), thick + 2.5, closed)
        self.polyline(pts, color, thick, closed)
        core = lerp(color, WHITE, 0.5)
        core = (core[0], core[1], core[2], color[3] * 0.8)
        self.polyline(pts, core, max(thick * 0.45, 0.6), closed)

    def font(self, weight, size):
        key = (weight, size)
        if key not in self.fonts:
            # Slate sizes are points at 96 dpi.
            self.fonts[key] = ImageFont.truetype(find_font(weight), max(1, int(round(size * 4.0 / 3.0 * self.s))))
        return self.fonts[key]

    def measure(self, text, weight, size, spacing=0):
        f = self.font(weight, size)
        em = size * 4.0 / 3.0
        w = sum(f.getlength(ch) for ch in text) / self.s + spacing / 1000.0 * em * max(0, len(text) - 1)
        return w, em * 1.17

    def text(self, x, y, text, weight, size, color, spacing=0, shadow=False):
        f = self.font(weight, size)
        em = size * 4.0 / 3.0
        tw, th = self.measure(text, weight, size, spacing)

        def draw(d, ox, oy):
            cx = x * self.s - ox
            for ch in text:
                if shadow:
                    d.text((cx + self.s, y * self.s - oy + self.s + em * 0.08 * self.s), ch, font=f, fill=(0, 0, 0, int(190 * color[3])))
                d.text((cx, y * self.s - oy + em * 0.08 * self.s), ch, font=f, fill=self._col(color))
                cx += f.getlength(ch) + spacing / 1000.0 * em * self.s

        self._layer(draw, (x * self.s, y * self.s, (x + tw + 4) * self.s, (y + th + 4) * self.s))
        return tw, th

    def text_centered(self, cx, cy, text, weight, size, color, spacing=0, shadow=False):
        tw, th = self.measure(text, weight, size, spacing)
        return self.text(cx - tw / 2, cy - th / 2, text, weight, size, color, spacing, shadow)

    def finish(self):
        return self.img.resize((self.W, self.H), Image.LANCZOS).convert("RGB")


# --- SAirsoftNeon.cpp equivalents --------------------------------------------------------------

def chamfer_points(x, y, w, h, c, corners):
    c = max(0.0, min(c, min(w, h) * 0.5))
    x1, y1 = x + w, y + h
    p = []
    p += [(x, y + c), (x + c, y)] if corners & TL and c > 0 else [(x, y)]
    p += [(x1 - c, y), (x1, y + c)] if corners & TR and c > 0 else [(x1, y)]
    p += [(x1, y1 - c), (x1 - c, y1)] if corners & BR and c > 0 else [(x1, y1)]
    p += [(x + c, y1), (x, y1 - c)] if corners & BL and c > 0 else [(x, y1)]
    return p


def panel(pt, x, y, w, h, chamfer=12, corners=DIAGONAL, line=CYAN, fill=GLASS, glow=1.0, accent=None):
    pt.poly(chamfer_points(x, y, w, h, chamfer, corners), fill)
    pt.rect(x + chamfer, y + 1, max(0, w - 2 * chamfer), min(h * 0.35, 18), alpha(line, 0.035))
    pt.glow_polyline(chamfer_points(x + 0.5, y + 0.5, w - 1, h - 1, chamfer, corners), line, 1.25, glow, True)
    if accent and chamfer >= 4:
        c = min(chamfer, min(w, h) * 0.5)
        x0, y0, x1, y1 = x + 0.5, y + 0.5, x + w - 0.5, y + h - 0.5
        cuts = {TL: [(x0, y0 + c), (x0 + c, y0)], TR: [(x1 - c, y0), (x1, y0 + c)],
                BR: [(x1, y1 - c), (x1 - c, y1)], BL: [(x0 + c, y1), (x0, y1 - c)]}
        for k, seg in cuts.items():
            if corners & k:
                pt.glow_polyline(seg, accent, 3.0, glow, False)


def slant_points(x, y, w, h, slant, frac):
    s = max(0.0, min(slant, w * 0.5))
    l = (w - s) * max(0.0, min(1.0, frac))
    return [(x + s, y), (x + s + l, y), (x + l, y + h), (x, y + h)]


def slant_bar(pt, x, y, w, h, slant, frac, c_from, c_to, segments=1, gap=3, ghost=-1.0, frame=True, glow=1.0):
    s = max(0.0, min(slant, w * 0.5))
    base = w - s
    n = max(1, segments)
    g = gap if n > 1 else 0
    seg_w = (base - g * (n - 1)) / n
    fill_end = base * frac
    ghost_end = base * ghost if ghost > frac else fill_end
    sub = 24 if n == 1 else 1
    slice_w = seg_w / sub

    def piece(a0, a1, col):
        if a1 > a0:
            pt.poly([(x + s + a0, y), (x + s + a1, y), (x + a1, y + h), (x + a0, y + h)], col)

    for k in range(n):
        for j in range(sub):
            a0 = k * (seg_w + g) + j * slice_w
            a1 = a0 + slice_w
            col = lerp(c_from, c_to, min(1, max(0, (a0 + a1) * 0.5 / base)))
            piece(a0, min(a1, fill_end), col)
            piece(max(a0, fill_end), min(a1, ghost_end), (1, 0.95, 0.9, 0.55))
            piece(max(a0, fill_end, ghost_end), a1, TRACK)
    if frac > 0.005 and glow > 0:
        halo = lerp(c_from, c_to, 0.6)
        halo = (halo[0], halo[1], halo[2], halo[3] * 0.55)
        pts = slant_points(x, y, w, h, slant, frac)
        pt.polyline(pts, alpha(halo, 0.18 * glow), 7, True)
        pt.polyline(pts, alpha(halo, 0.30 * glow), 3, True)
    if frame:
        pt.polyline(slant_points(x - 3, y - 3, w + 6, h + 6, slant + 3 * slant / max(h, 1), 1), alpha(CYAN, 0.45), 1, True)


GLYPHS = {  # SAirsoftWeaponGlyph::GetShapes, 100 x 40 design box
    "Rifle": [[2, 13, 16, 11, 24, 13, 30, 13, 31, 9, 58, 9, 59, 11, 82, 11, 82, 13.5, 97, 13.5, 97, 16.5, 82, 16.5, 82, 19, 58, 19,
               56, 20, 52, 20, 50, 33, 43, 32, 45, 20, 38, 20, 35, 30, 30, 30, 32, 20, 24, 20, 16, 23, 2, 25]],
    "Pistol": [[24, 11, 84, 11, 84, 19, 56, 19, 54, 24, 47, 24, 46, 21, 43, 34, 32, 34, 35, 20, 24, 19]],
    "SMG": [[6, 12, 18, 12, 20, 10, 60, 10, 62, 12, 76, 12, 76, 14, 90, 14, 90, 17, 76, 17, 76, 19, 58, 19, 58, 33, 51, 33, 51, 19,
             42, 19, 38, 30, 32, 30, 34, 19, 20, 19, 18, 21, 6, 22]],
    "Grenade": [[44, 12, 56, 12, 62, 18, 62, 30, 56, 36, 44, 36, 38, 30, 38, 18], [46, 6, 54, 6, 54, 12, 46, 12]],
}


def scan_fill(pt, pts, color, step, row_h):
    ys = [p[1] for p in pts]
    y = min(ys)
    while y < max(ys):
        yc = y + row_h * 0.5
        xs = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            if (a[1] <= yc < b[1]) or (b[1] <= yc < a[1]):
                t = (yc - a[1]) / (b[1] - a[1])
                xs.append(a[0] + t * (b[0] - a[0]))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            pt.rect(xs[k], y, xs[k + 1] - xs[k], min(row_h, max(ys) - y), color)
        y += step


def glyph(pt, x, y, w, h, cls, color):
    shapes = GLYPHS.get(cls, GLYPHS["Rifle"])
    xs = [f[i] for f in shapes for i in range(0, len(f), 2)]
    ys = [f[i] for f in shapes for i in range(1, len(f), 2)]
    ex, ey = max(xs) - min(xs), max(ys) - min(ys)
    scale = min(w / ex, h / ey)
    ox, oy = x + (w - ex * scale) / 2 - min(xs) * scale, y + (h - ey * scale) / 2 - min(ys) * scale
    for flat in shapes:
        shape = [(ox + flat[i] * scale, oy + flat[i + 1] * scale) for i in range(0, len(flat), 2)]
        scan_fill(pt, shape, alpha(color, 0.55), 2.0, 1.3)
        pt.glow_polyline(shape, color, 1.2, 0.9, True)


def emblem(pt, x, y, size, text, color):
    cut = size * 0.29
    pt.poly(chamfer_points(x, y, size, size, cut, ALL), (0.02, 0.05, 0.08, 0.8))
    inner = chamfer_points(x + 6, y + 6, size - 12, size - 12, cut - 2.5, ALL)
    scan_fill(pt, inner, alpha(color, 0.07), 3, 1)
    pt.polyline(inner, alpha(color, 0.35), 1, True)
    pt.glow_polyline(chamfer_points(x + 0.5, y + 0.5, size - 1, size - 1, cut, ALL), color, 1.75, 1, True)
    pt.glow_polyline([(x + 0.5, y + cut + 0.5), (x + cut + 0.5, y + 0.5)], ORANGE, 2.5, 0.8, False)
    pt.glow_polyline([(x + size - 0.5, y + size - cut - 0.5), (x + size - cut - 0.5, y + size - 0.5)], ORANGE, 2.5, 0.8, False)
    pt.text_centered(x + size / 2, y + size / 2, text, "Bold", round(size * 0.27), lerp(color, WHITE, 0.45), 80)


def target_icon(pt, x, y, size, color):
    panel(pt, x, y, size, size, size * 0.22, DIAGONAL, color, GLASS, 0.8)
    import math
    cx, cy, r = x + size / 2, y + size / 2, size * 0.26
    ring = [(cx + math.cos(2 * math.pi * i / 12) * r, cy + math.sin(2 * math.pi * i / 12) * r) for i in range(12)]
    pt.glow_polyline(ring, color, 1.25, 0.8, True)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pt.glow_polyline([(cx + dx * r * 0.55, cy + dy * r * 0.55), (cx + dx * r * 1.45, cy + dy * r * 1.45)], color, 1.25, 0.6, False)
    pt.rect(cx - 1.5, cy - 1.5, 3, 3, ORANGE)


def mag_pips(pt, x, y, w, h, mag, cap):
    per = -(-cap // 50)
    pips = -(-cap // per)
    lit = -(-mag // per)
    gap = 1.5 if pips > 30 else 2.5
    pw = (w - gap * (pips - 1)) / pips
    on = RED if mag <= 0 else (ORANGE if mag * 4 <= cap else CYAN)
    for i in range(pips):
        pt.rect(x + i * (pw + gap), y, pw, h, on if i >= pips - lit else (0.62, 0.88, 1.0, 0.12))
    if lit:
        x0 = x + (pips - lit) * (pw + gap)
        pt.polyline([(x0, y + h / 2), (x + w, y + h / 2)], alpha(on, 0.14), h + 6, False)


def chip(pt, x, y, text, color):
    tw, th = pt.measure(text, "Bold", 8, 220)
    w, h = tw + 14, th + 2
    panel(pt, x, y, w, h, 4, DIAGONAL, color, GLASS, 0.6)
    pt.text(x + 7, y + 1, text, "Bold", 8, color, 220)
    return w, h


# --- The HUD (SAirsoftHUD.cpp layout) ---------------------------------------------------------

def crosshair(pt):
    cx, cy = 960, 540
    gap, ln, th = 8, 9, 2
    for (x, y, w, h) in ((cx - gap - ln, cy - 1, ln, th), (cx + gap, cy - 1, ln, th), (cx - 1, cy - gap - ln, th, ln), (cx - 1, cy + gap, th, ln), (cx - 1, cy - 1, 2, 2)):
        pt.rect(x - 1, y - 1, w + 2, h + 2, (0, 0, 0, 0.45))
        pt.rect(x, y, w, h, (1, 1, 1, 0.92))


def status_story(pt, health=0.62, ghost=0.74, regen=0.55):
    x, y = 28, 24
    w, h = 12 + 58 + 14 + 250 + 20, 10 + 64 + 12
    panel(pt, x, y, w, h, 14, DIAGONAL, CYAN, GLASS, 1.0, ORANGE)
    emblem(pt, x + 12, y + 10 + 2, 58, "AH", CYAN)
    cx, cy = x + 12 + 58 + 14, y + 10
    pt.text(cx, cy + 9, "HEALTH", "Bold", 9, CYAN, 300)
    vw, vh = pt.measure("/ 100", "Regular", 9, 40)
    pt.text(cx + 250 - vw, cy + 11, "/ 100", "Regular", 9, alpha(CYAN, 0.6), 40)
    nw, _ = pt.measure("62", "Bold", 17, 20)
    pt.text(cx + 250 - vw - 3 - nw, cy - 1, "62", "Bold", 17, WHITE, 20)
    slant_bar(pt, cx, cy + 28, 250, 14, 8, health, RED, AMBER, 10, 3, ghost)
    slant_bar(pt, cx, cy + 51, 186, 5, 4, regen, CYAN_DEEP, CYAN, 1, frame=False)
    pt.text(cx + 196, cy + 47, "REGEN", "Bold", 7, alpha(CYAN, 0.75), 300)


def status_match(pt, team_col=BLUE_TEAM):
    x, y = 28, 24
    w, h = 12 + 58 + 14 + 210 + 20, 10 + 58 + 12
    panel(pt, x, y, w, h, 14, DIAGONAL, team_col, GLASS, 1.0, ORANGE)
    emblem(pt, x + 12, y + 10, 58, "GH", team_col)
    cx, cy = x + 12 + 58 + 14, y + 12
    tw, th = pt.text(cx, cy, "Ghost_Hale", "Bold", 14, WHITE, 60)
    chip(pt, cx + tw + 10, cy + 4, "BLUE", team_col)
    pt.text(cx, cy + th + 6, "RANK 4 \u00b7 SERGEANT", "Bold", 8, alpha(CYAN, 0.8), 260)
    slant_bar(pt, cx, cy + th + 26, 210, 4, 3, 0.38, CYAN_DEEP, CYAN, frame=False)


def top_center_story(pt, boss=True):
    cap = "MISSION 2 \u00b7 NEON DEBT"
    tw, th = pt.measure(cap, "Regular", 8, 220)
    w = max(170, tw + 44)
    h = 5 + th + 9
    x, y = 960 - w / 2, 22
    panel(pt, x, y, w, h, 14, BOTTOM, CYAN, GLASS, 1.0, ORANGE)
    pt.text_centered(960, y + 5 + th / 2, cap, "Regular", 8, alpha(CYAN, 0.8), 220)
    y += h + 8
    _, lh = pt.text_centered(960, y + 9, "LAST CONTRACT", "Regular", 9, (0.9, 0.88, 0.85, 1), 220, True)
    y += lh + 14
    if boss:
        bw, bh = 460, 7 + 19 + 7 + 10 + 13
        bx = 960 - bw / 2
        panel(pt, bx, y, bw, bh, 12, DIAGONAL, RED, GLASS, 1.0, ORANGE)
        pt.text(bx + 20, y + 7, "VICTOR VARGA", "Bold", 12, WHITE, 260)
        tw2, _ = pt.measure("TARGET", "Bold", 8, 300)
        pt.text(bx + bw - 20 - tw2, y + 11, "TARGET", "Bold", 8, RED, 300)
        slant_bar(pt, bx + 20, y + 33, 420, 10, 7, 0.58, MAGENTA, RED, 20, 2, 0.66)


def top_center_match(pt):
    tw, th = pt.measure("03:41", "Bold", 26, 60)
    cw, ch = pt.measure("FIRST TO 40", "Regular", 8, 220)
    w = max(170, tw + 44)
    h = 5 + th + ch + 9
    x, y = 960 - w / 2, 22
    for team, col, sx, corners, score, label in ((0, BLUE_TEAM, x - 4 - 112, LEFT, "2", "BLUE \u00b7 YOU"), (1, RED_TEAM, x + w + 4, RIGHT, "1", "RED")):
        panel(pt, sx, y, 112, h, 12, corners, col, GLASS, 1.0)
        pt.text_centered(sx + 56, y + 5 + 18, score, "Bold", 26, WHITE)
        pt.text_centered(sx + 56, y + h - 12, label, "Regular", 8, col, 220)
    panel(pt, x, y, w, h, 14, BOTTOM, CYAN, GLASS, 1.0, ORANGE)
    pt.text_centered(960, y + 5 + th / 2, "03:41", "Bold", 26, WHITE, 60)
    pt.text_centered(960, y + 5 + th + ch / 2, "FIRST TO 40", "Regular", 8, alpha(CYAN, 0.8), 220)
    y += h + 8
    _, lh = pt.text_centered(960, y + 9, "DOMINATION  \u00b7  VELVET CLUB", "Regular", 9, (0.9, 0.88, 0.85, 1), 220, True)
    y += lh + 8
    # A / B / C badges
    for i, (letter, col) in enumerate((("A", BLUE_TEAM), ("B", None), ("C", RED_TEAM))):
        bx = 960 - 3 * 48 / 2 + i * 48 + 7
        line = col if col else (1, 1, 1, 0.3)
        pt.poly(chamfer_points(bx, y, 34, 34, 7, DIAGONAL), GLASS)
        if col:
            pt.rect(bx + 1, y + 1, 32, 32, alpha(col, 0.22))
        pt.glow_polyline(chamfer_points(bx + 0.5, y + 0.5, 33, 33, 7, DIAGONAL), line, 1.4, 1.0 if col else 0.4, True)
        pt.text_centered(bx + 17, y + 17, letter, "Bold", 14, col if col else (0.9, 0.88, 0.85, 1))
        pt.rect(bx, y + 39, 34, 3, (1, 1, 1, 0.12))


def kill_feed(pt, rows):
    y = 24
    for shooter, scol, weapon, victim, vcol, mine in rows:
        nw, nh = pt.measure(shooter, "Bold", 11, 40)
        ww, _ = pt.measure(weapon, "Bold", 7, 240)
        vw, _ = pt.measure(victim, "Bold", 11, 40)
        w = 14 + nw + 10 + ww + 10 + vw + 14
        h = 5 + nh + 5
        x = 1920 - 28 - w
        panel(pt, x, y, w, h, 8, DIAGONAL_ALT, ORANGE if mine else alpha(CYAN, 0.45), GLASS, 0.7, AMBER if mine else None)
        pt.text(x + 14, y + 5, shooter, "Bold", 11, scol, 40)
        pt.text(x + 14 + nw + 10, y + 5 + nh / 2 - 6, weapon, "Bold", 7, alpha(CYAN, 0.75), 240)
        pt.text(x + 14 + nw + 10 + ww + 10, y + 5, victim, "Bold", 11, vcol, 40)
        y += h + 4


def ammo_panel(pt, mag=27, reserve=180, cap=30, cls="Rifle", name="M4A1 CARBINE", grenades=1, light=False, mode="AUTO"):
    w = 340
    dw, dh = pt.measure(str(mag), "Bold", 38)
    _, nh = pt.measure(name, "Bold", 8, 260)
    h = 8 + dh + nh + 8 + 6 + 13
    x, y = 1920 - 28 - w, 1080 - 28 - h
    panel(pt, x, y, w, h, 16, DIAGONAL, CYAN, GLASS, 1.0, ORANGE)
    col = RED if mag * 4 <= cap else ORANGE
    pt.text(x + 20, y + 8, str(mag), "Bold", 38, col)
    rw, rh = pt.measure("/%d" % reserve, "Regular", 16, 40)
    pt.text(x + 20 + dw + 6, y + 8 + dh - rh - 7 + 4, "/%d" % reserve, "Regular", 16, alpha(AMBER, 0.85), 40)
    glyph(pt, x + w - 18 - 140, y + 8 + (dh - 44) / 2 + 2, 140, 44, cls, CYAN)
    pt.text(x + 20, y + 8 + dh, name, "Bold", 8, alpha(CYAN, 0.8), 260)
    mag_pips(pt, x + 20, y + 8 + dh + nh + 8, 300, 6, mag, cap)
    # Row above the frame: light, fire mode, grenade count.
    gx = x + w - 10
    gw, gh = pt.measure("x%d" % grenades, "Bold", 11, 40)
    gy = y - 6 - 20
    pt.text(gx - gw, gy + 1, "x%d" % grenades, "Bold", 11, CYAN, 40)
    glyph(pt, gx - gw - 2 - 16, gy, 16, 20, "Grenade", CYAN)
    cw, _ = pt.measure(mode, "Bold", 8, 220)
    chip(pt, gx - gw - 2 - 16 - 12 - (cw + 14), gy + 2, mode, CYAN)
    if light:
        lw, _ = pt.measure("LIGHT", "Bold", 8, 220)
        chip(pt, gx - gw - 2 - 16 - 12 - (cw + 14) - 8 - (lw + 14), gy + 2, "LIGHT", AMBER)


def objective_panel(pt, text="CLEAR THE CLUB", left=3, total=8, boss=False):
    tw, th = pt.measure(text, "Bold", 12, 80)
    col_w = max(tw, 220 + 12 + pt.measure("%d LEFT" % left, "Bold", 9, 200)[0])
    w = 10 + 46 + 14 + col_w + 20
    h = 10 + 13 + 2 + th + 7 + 6 + 12
    x, y = 28, 1080 - 30 - h
    panel(pt, x, y, w, h, 12, DIAGONAL, CYAN, GLASS, 1.0, ORANGE)
    target_icon(pt, x + 10, y + (h - 46) / 2, 46, CYAN)
    cx, cy = x + 10 + 46 + 14, y + 10
    pt.text(cx, cy, "OBJECTIVE \u00b7 M2", "Bold", 8, CYAN, 300)
    pt.text(cx, cy + 15, text, "Bold", 12, WHITE, 80)
    by = cy + 15 + th + 7
    slant_bar(pt, cx, by, 220, 6, 4, 1 - left / total, CYAN_DEEP, CYAN)
    pt.text(cx + 232, by - 4, "BOSS" if boss else "%d LEFT" % left, "Bold", 9, ORANGE, 200)


def xp_popup(pt, amount, reason, slot=0):
    y = 540 + 64 + slot * 28
    aw, ah = pt.measure(amount, "Bold", 13, 40)
    rw, rh = pt.measure(reason, "Regular", 9, 220)
    total = aw + 8 + rw
    x = 960 - total / 2
    panel(pt, x - 12, y - 11, total + 24, 22, 7, DIAGONAL, alpha(ORANGE, 0.9), GLASS, 0.7)
    pt.text(x, y - ah / 2, amount, "Bold", 13, ORANGE, 40)
    pt.text(x + aw + 8, y - rh / 2, reason, "Regular", 9, CYAN, 220)


def render(variant, out):
    bg_name = "01_VelvetClub_Street.jpg" if variant == "story" else "04_VelvetClub_FirstPerson.jpg"
    pt = Painter(Image.open(os.path.join(ROOT, "Docs", "Screens", bg_name)))
    if variant == "story":
        status_story(pt)
        top_center_story(pt)
        kill_feed(pt, [("Andrew", BLUE_TEAM, "G17 GAS BLOWBACK", "Varga's Driver", RED_TEAM, True),
                       ("Andrew", BLUE_TEAM, "M4A1 CARBINE", "Doorman", RED_TEAM, True)])
        objective_panel(pt, "TAKE DOWN VICTOR VARGA", 0, 8, boss=True)
        ammo_panel(pt, mag=22, reserve=96, cap=30, light=True)
        crosshair(pt)
        xp_popup(pt, "+100", "TAKEDOWN")
    else:
        status_match(pt)
        top_center_match(pt)
        kill_feed(pt, [("Ghost_Hale", BLUE_TEAM, "M4A1 CARBINE", "Rook", RED_TEAM, True),
                       ("Mara", RED_TEAM, "MP5 SD", "Tex", BLUE_TEAM, False),
                       ("Juno", BLUE_TEAM, "VSR-10 BOLT ACTION", "Brick", RED_TEAM, False)])
        ammo_panel(pt, mag=7, reserve=180, cap=30)
        crosshair(pt)
        xp_popup(pt, "+50", "TAG")
    img = pt.finish()
    img.save(out, quality=92)
    print("wrote", out)


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        render(sys.argv[1], sys.argv[2])
    else:
        render("story", os.path.join(ROOT, "Docs", "Screens", "HUD_Mockup.jpg"))
        render("match", os.path.join(ROOT, "Docs", "Screens", "HUD_Mockup_Match.jpg"))
