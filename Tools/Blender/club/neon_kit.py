"""Neon street kit: shop signs and street dressing for the night maps (Velvet Club street, Nightjar Garage).

    python neon_kit.py -- [AssetId ...] [--res 4096|2048|1024] [--no-render] [--lineup] [--list]
    blender -b -P neon_kit.py -- ...

Builds every asset below with the club propkit pipeline (Tools/Blender/common/propkit.py, CONVENTIONS.md):
one FBX per piece under SourceAssets/Props/<AssetId>/, baked BC/N/ORM/M textures, a 1920x1080 product shot
(Docs/Renders/PropsNeon/<AssetId>.jpg, PNG master in Saved/Renders/PropsNeon) and the asset's entry in
Content/Airsoft/Data/PropsNeon.json (the editor importer reads every Props*.json).

Signs are original designs (invented shop names, generic words, no brands):
    Neon_BladeRamen     vertical red lightbox, "ラーメン" (ramen) + NOODLES, amber border tube
    Neon_BladeHotel     vertical black blade, H-O-T-E-L in magenta outline tubes, cyan border
    Neon_BladeIzakaya   vertical cream lightbox, "居酒屋" (tavern) in red, magenta border
    Neon_BladeGames     vertical blade, G-A-M-E-S, one colour per letter
    Neon_BladeVelvet    the club's own blade: V-E-L-V-E-T in magenta and pink tubes, violet border
    Neon_BoxPawn        wall box: "質" (pawn) roundel + PAWN / & LOANS green and amber tubes
    Neon_PharmacyCross  projecting double-sided green LED cross with a bright tube outline
    Neon_Cocktails      cocktail glass icon + COCKTAILS on a raceway
    Neon_ArrowBar       chaser-bulb arrow with BAR in red tube
    Neon_OpenSign       small window sign: OPEN in a blue oval
    Neon_Karaoke        horizontal violet lightbox "カラオケ" + KARAOKE 24H, cyan border
Street dressing:
    Street_Shutter, Street_Shopfront, Street_ACUnit, Street_Awning (tintable), Street_Vending,
    Street_Cables (20 m overhead wires), Street_SteamVent (AirsoftEffects puffs steam from it),
    Street_FireBarrel (AirsoftEffects: embers + flicker), Street_FacadeBay_A.._D (storey modules, lit windows)

Wall-mounted assets have their origin on the wall plane (x = 0, front +X), bottom-centre; blade signs
project along +X from the wall and show their faces to +Y and -Y. Emissive pieces carry their colours in the
baked BC (materials.py uses BC x Intensity as the emissive), so one sign can mix tube colours.
Japanese glyphs come from a system CJK font (IPAGothic); without one the CJK signs fall back to English text.
Deterministic: fixed seeds, no time-dependent input.
"""

import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector as V  # noqa: E402

import propkit as pk  # noqa: E402
import propkit_mats as pkm  # noqa: E402
from propkit import catmull, circle_pts, round_poly, rrect_pts  # noqa: E402
from club_registry import font  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT, "SourceAssets", "Props")
RENDERS = os.path.join(ROOT, "Docs", "Renders", "PropsNeon")
PNG_RENDERS = os.path.join(ROOT, "Saved", "Renders", "PropsNeon")
JSON_PATH = os.path.join(ROOT, "Content", "Airsoft", "Data", "PropsNeon.json")
CACHE = os.environ.get("NEON_CACHE", os.path.join(os.environ.get("TMPDIR", "/tmp"), "neon_cache"))

DISPLAY = font("BigShoulders-Bold.ttf")
SERIF = font("LibreBaskerville-Regular.ttf")
CJK_CANDIDATES = ["/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]
CJK = next((p for p in CJK_CANDIDATES if os.path.exists(p)), None)

NEON = {}       # asset id -> {"fn", "kw"}
LINEUP = [   # front row first (rows step back, away from the camera)
    ["Street_FireBarrel", "Street_SteamVent", "Neon_OpenSign", "Street_ACUnit", "Street_Vending"],
    ["Neon_Cocktails", "Neon_ArrowBar", "Neon_PharmacyCross", "Neon_Karaoke", "Neon_BoxPawn"],
    ["Neon_BladeVelvet", "Neon_BladeHotel", "Neon_BladeGames", "Neon_BladeRamen", "Neon_BladeIzakaya"],
    ["Street_Shopfront", "Street_Shutter", "Street_Awning"],
    ["Street_FacadeBay_A", "Street_FacadeBay_B", "Street_FacadeBay_C", "Street_FacadeBay_D"],
]


def asset(aid, **kw):
    def deco(fn):
        NEON[aid] = {"fn": fn, "kw": dict(group="Neon", **kw)}
        return fn
    return deco


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------------------
# Colours (linear) and recipes registered into propkit_mats.MATS
# --------------------------------------------------------------------------------------

TUBE = {
    "magenta": (1.0, 0.10, 0.55), "pink": (1.0, 0.30, 0.62), "cyan": (0.10, 0.80, 1.0), "teal": (0.06, 0.95, 0.72),
    "green": (0.20, 1.0, 0.30), "red": (1.0, 0.08, 0.05), "amber": (1.0, 0.45, 0.07), "yellow": (1.0, 0.80, 0.22),
    "violet": (0.55, 0.20, 1.0), "blue": (0.16, 0.36, 1.0), "white": (0.95, 0.93, 1.0), "warm": (1.0, 0.70, 0.42),
}


def r_neon(nb, c, col=(1, 1, 1)):
    """Lit tube: flat colour, a touch hotter (whiter) where the glass faces the viewer is left to bloom."""
    return pkm._out(col, 0.3, 0.0, None)


def r_lightbox(nb, c, image="", bg=(0.4, 0.02, 0.02), ink1=(0.9, 0.85, 0.75), ink2=(0.05, 0.05, 0.05), hot=0.3):
    """Backlit acrylic face: image R = ink1, G = ink2 over bg (luv = face u, v), brighter in the middle."""
    u, v, _ = nb.sep(c.luv)
    col = bg
    im = bpy.data.images.get(image)
    if im is not None:
        t, _a = nb.img(im, nb.combine(u, v, 0.0), ext="EXTEND")
        r, g, _b = nb.sep(t)
        col = nb.mixc(r, bg, ink1)
        col = nb.mixc(g, col, ink2)
    fu = nb.math("SINE", nb.mul(nb.clamp(u), math.pi))
    fv = nb.math("SINE", nb.mul(nb.clamp(v), math.pi))
    f = nb.add(1.0 - hot, nb.mul(nb.pw(nb.mul(fu, fv), 0.35), hot))
    return pkm._out(nb.cmul(col, f), 0.3, 0.0, None)


def r_ledgrid(nb, c, col=(0.1, 1.0, 0.3), dark=(0.004, 0.02, 0.008), pitch=55.0):
    """LED matrix in the object XZ plane (pharmacy cross faces)."""
    x, _y, z = nb.sep(c.P)
    d, _, _ = nb.vor(nb.combine(x, z, 0.0), pitch, "F1", 0.0, dims="2D")
    dots = nb.ss(0.36, 0.24, d)
    return pkm._out(nb.mixc(dots, dark, col), 0.3, 0.0, None)


def r_flame(nb, c):
    """Flame tongues: white-yellow at the root, orange, deep red at the tips (object Z)."""
    _x, _y, z = nb.sep(c.P)
    n, _ = nb.noise(c.P, 9.0, 3.0, 0.6)
    t = nb.clamp(nb.add(nb.mul(nb.sub(z, 0.86), 2.6), nb.mul(nb.sub(n, 0.5), 0.35)))
    col = nb.ramp(t, [(0.0, (1.0, 0.86, 0.45)), (0.3, (1.0, 0.52, 0.10)), (0.65, (0.85, 0.20, 0.03)), (1.0, (0.35, 0.05, 0.01))])
    return pkm._out(col, 0.5, 0.0, None)


def r_ember(nb, c):
    """Glowing coals / punched holes: orange with dark crust."""
    n, _ = nb.noise(c.P, 40.0, 4.0, 0.6)
    col = nb.mixc(nb.ss(0.45, 0.65, n), (0.25, 0.04, 0.005), (1.0, 0.42, 0.08))
    return pkm._out(col, 0.6, 0.0, None)


def r_window(nb, c):
    """Lit interiors seen through a window, luv = (u, v, state/8): 0 dark, 1 warm curtains, 2 cool blinds,
    3 TV-blue room, 4 warm blinds, 5 pink lamp, 6 bare bulb, 7 green-white office."""
    u, v, lid = nb.sep(c.luv)
    state = nb.mul(lid, 8.0)
    blinds = nb.ss(0.35, 0.55, nb.math("SINE", nb.mul(v, 2 * math.pi * 16)))
    folds = nb.add(0.65, nb.mul(nb.math("SINE", nb.mul(u, 2 * math.pi * 7.0)), 0.35))
    room, _ = nb.noise(nb.combine(nb.mul(u, 3.0), nb.mul(v, 2.0), lid), 1.0, 2.0, 0.5)
    glow = nb.add(0.45, nb.mul(nb.pw(nb.mul(nb.math("SINE", nb.mul(nb.clamp(u), math.pi)), nb.math("SINE", nb.mul(nb.clamp(v), math.pi))), 0.5), 0.55))

    def pick(k):
        return nb.mul(nb.math("GREATER_THAN", state, k - 0.5), nb.math("LESS_THAN", state, k + 0.5))
    warm = nb.cmul((0.55, 0.30, 0.12), nb.mul(folds, glow))
    cool = nb.cmul((0.32, 0.42, 0.55), nb.mul(nb.add(0.35, nb.mul(blinds, 0.65)), glow))
    tv = nb.cmul((0.10, 0.22, 0.55), nb.mul(nb.add(0.4, nb.mul(room, 0.8)), glow))
    wblind = nb.cmul((0.60, 0.36, 0.14), nb.mul(nb.add(0.25, nb.mul(blinds, 0.75)), glow))
    pink = nb.cmul((0.55, 0.12, 0.30), nb.mul(nb.add(0.6, nb.mul(room, 0.4)), glow))
    bulb = nb.cmul((0.65, 0.48, 0.25), nb.pw(glow, 2.5))
    office = nb.cmul((0.30, 0.42, 0.34), nb.add(0.55, nb.mul(blinds, 0.45)))
    col = (0.004, 0.004, 0.005)
    for k, layer in ((1, warm), (2, cool), (3, tv), (4, wblind), (5, pink), (6, bulb), (7, office)):
        col = nb.mixc(pick(k), col, layer)
    return pkm._out(col, 0.4, 0.0, None)


def r_vend(nb, c):
    """Vending machine display: rows of drink cans / bottles, backlit (luv over the display)."""
    u, v, _ = nb.sep(c.luv)
    cu = nb.math("FRACT", nb.mul(u, 8.0))
    cv = nb.math("FRACT", nb.mul(v, 5.0))
    cell = nb.combine(nb.math("FLOOR", nb.mul(u, 8.0)), nb.math("FLOOR", nb.mul(v, 5.0)), 0.0)
    rnd, _ = nb.noise(cell, 1.7, 0.0, 0.5)
    can = nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(cu, 0.5)), 0.3), nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(cv, 0.55)), 0.33))
    pal = nb.ramp(rnd, [(0.0, (0.75, 0.05, 0.04)), (0.25, (0.05, 0.25, 0.75)), (0.42, (0.85, 0.65, 0.08)), (0.55, (0.08, 0.55, 0.15)),
                        (0.7, (0.85, 0.85, 0.85)), (0.85, (0.55, 0.08, 0.40))], interp="CONSTANT")
    shelf = nb.math("LESS_THAN", cv, 0.12)
    col = nb.mixc(can, (0.80, 0.82, 0.85), pal)
    col = nb.mixc(shelf, col, (0.15, 0.15, 0.16))
    return pkm._out(col, 0.3, 0.0, None)


def r_shop(nb, c, tint=(0.75, 0.62, 0.42)):
    """Shop interior back wall seen through glass: shelves of goods, bright ceiling band (luv)."""
    u, v, _ = nb.sep(c.luv)
    rows = nb.math("FRACT", nb.mul(v, 4.0))
    shelf = nb.math("LESS_THAN", rows, 0.08)
    cell = nb.combine(nb.math("FLOOR", nb.mul(u, 22.0)), nb.math("FLOOR", nb.mul(v, 4.0)), 0.0)
    rnd, _ = nb.noise(cell, 2.3, 0.0, 0.5)
    goods = nb.ramp(rnd, [(0.0, (0.55, 0.12, 0.08)), (0.3, (0.75, 0.70, 0.55)), (0.5, (0.12, 0.30, 0.55)), (0.7, (0.70, 0.50, 0.12)),
                          (0.85, (0.20, 0.45, 0.25))], interp="CONSTANT")
    gap = nb.math("GREATER_THAN", nb.math("FRACT", nb.mul(u, 22.0)), 0.85)
    col = nb.mixc(gap, goods, nb.cmul(tint, 0.6))
    col = nb.mixc(nb.math("GREATER_THAN", rows, 0.8), col, nb.cmul(tint, 0.8))
    col = nb.mixc(shelf, col, (0.05, 0.05, 0.05))
    top = nb.math("GREATER_THAN", v, 0.9)
    col = nb.mixc(top, col, (0.95, 0.92, 0.85))
    return pkm._out(nb.cmul(col, nb.add(0.55, nb.mul(v, 0.45))), 0.3, 0.0, None)


def r_canvas_tint(nb, c, col=(0.75, 0.75, 0.75), rough=0.8):
    """Awning canvas: neutral 0.75 grey with the role mask set (paint variants tint it), rain streaks."""
    o = pkm.fabric(nb, c, col=col, rough=rough, weave=500.0)
    st, _ = nb.noise(nb.vmath("MULTIPLY", c.P, (14.0, 14.0, 0.8)), 1.0, 4.0, 0.6)
    o["col"] = nb.cmul(o["col"], nb.sub(1.0, nb.mul(nb.ss(0.55, 0.8, st), 0.35)))
    o["rough"] = nb.sub(rough, nb.mul(nb.ss(0.5, 0.8, st), 0.35))
    o["mask"] = 1.0
    return o


def r_shutter(nb, c, col=(0.75, 0.75, 0.75)):
    """Roll-up shutter slats: neutral paint (tinted per placement) with rain streaks, grime and rust runs."""
    o = pkm.paint(nb, c, col=col, rough=0.38, mask=1.0, peel=0.6, grime=0.65, chip=0.5, rust=0.45, streak=0.9)
    return o


def r_facade(nb, c, col=(0.08, 0.08, 0.08), tiles=False):
    """Rain-stained city facade: render or small tiles, dark run-off streaks below sills, damp (glossier) patches."""
    o = pkm.concrete(nb, c, col=col, rough=0.7)
    st, _ = nb.noise(nb.vmath("MULTIPLY", c.P, (10.0, 10.0, 0.5)), 1.0, 5.0, 0.65)
    streak = nb.ss(0.5, 0.78, st)
    o["col"] = nb.cmul(o["col"], nb.sub(1.0, nb.mul(streak, 0.45)))
    o["rough"] = nb.sub(o["rough"], nb.mul(streak, 0.35))
    if tiles:
        _x, y, z = nb.sep(c.P)
        gy = nb.math("LESS_THAN", nb.math("FRACT", nb.mul(y, 10.0)), 0.06)
        gz = nb.math("LESS_THAN", nb.math("FRACT", nb.mul(z, 20.0)), 0.1)
        grout = nb.clamp(nb.add(gy, gz))
        o["col"] = nb.mixc(grout, o["col"], (0.03, 0.03, 0.03))
        o["rough"] = nb.mix(grout, nb.sub(o["rough"], 0.3), 0.85)
        o["h"] = nb.mul(grout, -1.0)
        o["bs"] = 0.6
    return o


def r_cable(nb, c):
    return pkm._out((0.012, 0.012, 0.013), 0.42, 0.0, None)


def r_rust(nb, c):
    o = pkm.paint(nb, c, col=(0.10, 0.045, 0.02), rough=0.75, peel=1.0, grime=0.8, rust=1.0, chip=0.8, chip_col=(0.15, 0.06, 0.02), streak=0.5)
    return o


def register_recipes():
    for k, col in TUBE.items():
        pkm.MATS["neon_" + k] = (r_neon, dict(col=col))
    pkm.MATS.update({
        "lb_ramen": (r_lightbox, dict(image="LB_RAMEN", bg=(0.36, 0.012, 0.010), ink1=(0.95, 0.88, 0.70), ink2=(0.95, 0.62, 0.15))),
        "lb_izakaya": (r_lightbox, dict(image="LB_IZAKAYA", bg=(0.78, 0.68, 0.45), ink1=(0.42, 0.015, 0.02), ink2=(0.03, 0.04, 0.12))),
        "lb_karaoke": (r_lightbox, dict(image="LB_KARAOKE", bg=(0.20, 0.04, 0.45), ink1=(0.95, 0.92, 1.0), ink2=(0.10, 0.85, 1.0))),
        "lb_pawn": (r_lightbox, dict(image="LB_PAWN", bg=(0.85, 0.82, 0.74), ink1=(0.55, 0.015, 0.01), ink2=(0.02, 0.02, 0.02), hot=0.2)),
        "led_green": (r_ledgrid, dict()),
        "flame": (r_flame, dict()),
        "ember": (r_ember, dict()),
        "window_lit": (r_window, dict()),
        "vend_display": (r_vend, dict()),
        "shop_warm": (r_shop, dict(tint=(0.80, 0.62, 0.40))),
        "shop_cool": (r_shop, dict(tint=(0.55, 0.70, 0.80))),
        "canvas_tint": (r_canvas_tint, dict()),
        "shutter_tint": (r_shutter, dict()),
        "cable": (r_cable, dict()),
        "rust_drum": (r_rust, dict()),
        "paint_sign_red": (pkm.paint, dict(col=(0.18, 0.012, 0.01), rough=0.35, peel=0.6, grime=0.5, chip=0.4, streak=0.5)),
        "paint_sign_cream": (pkm.paint, dict(col=(0.45, 0.40, 0.30), rough=0.35, peel=0.6, grime=0.6, chip=0.4, streak=0.6)),
        "paint_amber": (pkm.paint, dict(col=(0.45, 0.20, 0.02), rough=0.35, peel=0.6, grime=0.5, chip=0.5, streak=0.5)),
        "paint_vend": (pkm.paint, dict(col=(0.06, 0.12, 0.30), rough=0.22, peel=0.4, grime=0.4, chip=0.3, streak=0.3)),
        "paint_ac": (pkm.paint, dict(col=(0.55, 0.55, 0.52), rough=0.4, peel=0.5, grime=0.8, chip=0.3, rust=0.4, streak=0.8)),
        "paint_frame": (pkm.paint, dict(col=(0.035, 0.035, 0.038), rough=0.4, peel=0.6, grime=0.5, chip=0.5, streak=0.6)),
        "stucco_dark": (pkm.concrete, dict(col=(0.07, 0.065, 0.062), rough=0.8)),
        "stucco_facade": (r_facade, dict(col=(0.085, 0.08, 0.078))),
        "stucco_brown": (r_facade, dict(col=(0.11, 0.055, 0.04))),
        "tile_teal": (r_facade, dict(col=(0.055, 0.08, 0.08), tiles=True)),
        "glass_shop": (pkm.glass, dict(col=(0.85, 0.9, 0.92), rough=0.02, dirt=0.25)),
    })


register_recipes()


# --------------------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------------------


def resample(pts, step, closed=True):
    P = [V((p[0], p[1])) for p in pts]
    if closed and (P[0] - P[-1]).length < 1e-6:
        P = P[:-1]
    segs = list(zip(P, P[1:] + ([P[0]] if closed else [])))
    total = sum((b - a).length for a, b in segs)
    if total < 1e-6:
        return [tuple(p) for p in P]
    n = max(6 if closed else 2, int(total / step))
    out = []
    acc = 0.0
    k = 0
    seg_len = [(b - a).length for a, b in segs]
    for i in range(n if closed else n + 1):
        d = total * i / n
        while k < len(segs) - 1 and acc + seg_len[k] < d:
            acc += seg_len[k]
            k += 1
        a, b = segs[k]
        t = 0.0 if seg_len[k] < 1e-9 else (d - acc) / seg_len[k]
        out.append(a.lerp(b, max(0.0, min(1.0, t))))
    return [(p.x, p.y) for p in out]


def smooth(pts, iters=2, w=0.5, closed=True):
    P = [V(p) for p in pts]
    n = len(P)
    for _ in range(iters):
        Q = []
        for i in range(n):
            if not closed and (i == 0 or i == n - 1):
                Q.append(P[i])
                continue
            Q.append(P[i] * (1 - w) + (P[i - 1] + P[(i + 1) % n]) * (w / 2))
        P = Q
    return [tuple(p) for p in P]


def text_loops(body, fontpath, size=1.0, res=4):
    """Outline loops of `body` (centred, x right, y up) in font units * size."""
    cu = bpy.data.curves.new("g", "FONT")
    cu.body = body
    cu.font = pk.load_font(fontpath)
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.fill_mode = "NONE"
    cu.resolution_u = res
    ob = bpy.data.objects.new("glyphs", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    adj = {i: [] for i in range(len(me.vertices))}
    for e in me.edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)
    seen, loops = set(), []
    for s in sorted(adj):
        if s in seen or not adj[s]:
            continue
        loop, prev, cur = [s], None, s
        seen.add(s)
        while True:
            nxt = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        if len(loop) > 2:
            loops.append([tuple(me.vertices[i].co[:2]) for i in loop])
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)
    return loops


def loops_bbox(loops):
    xs = [p[0] for l in loops for p in l]
    ys = [p[1] for l in loops for p in l]
    return min(xs), min(ys), max(xs), max(ys)


def place_loops(loops, w=None, h=None, cx=0.0, cy=0.0, scale=None):
    """Scale loops to fit w x h (keeping aspect) and centre them on (cx, cy)."""
    x0, y0, x1, y1 = loops_bbox(loops)
    s = scale
    if s is None:
        s = min((w / (x1 - x0)) if w else 1e9, (h / (y1 - y0)) if h else 1e9)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    return [[(cx + (p[0] - mx) * s, cy + (p[1] - my) * s) for p in l] for l in loops], s


def tube(A, pts2d, frame, r=0.008, mat="neon_magenta", closed=True, step=0.012, iters=2, piece="Emissive", n=10):
    """Neon tube along a 2D polyline in sign-plane coordinates (u right, v up); frame(u, v) -> 3D point."""
    p2 = smooth(resample(pts2d, step, closed), iters, 0.5, closed)
    if len(p2) < 3:
        return None
    path = [frame(u, v) for (u, v) in p2]
    return A.sweep(path, r=r, n=n, mat=mat, closed=closed, cap=not closed, piece=piece, smooth=180)


def supports(A, pts2d, frame_back, frame_tube, every=0.22, r=0.004):
    """Little clear standoffs from the backing to the tube (opaque, grey)."""
    acc = 0.0
    for i in range(1, len(pts2d)):
        acc += math.dist(pts2d[i], pts2d[i - 1])
        if acc >= every:
            acc = 0.0
            a, b = V(frame_back(*pts2d[i])), V(frame_tube(*pts2d[i]))
            d = b - a
            if d.length < 1e-4:
                continue
            ob = A.cyl(r, d.length, at=(0, 0, 0), mat="plastic_grey", n=8, bevel=None, piece="Body")
            q = V((0, 0, 1)).rotation_difference(d.normalized())
            ob.matrix_world = Matrix.Translation(a) @ q.to_matrix().to_4x4()


def face_quad(A, frame, w, h, mat, piece="Emissive", nu=1, nv=1, lid=1.0, uv=(0.0, 0.0, 1.0, 1.0)):
    """Single-sided quad facing the viewer of `frame` (u right, v up), luv = (u, v, lid) over it."""
    verts, faces, luv = [], [], []
    u0, v0, u1, v1 = uv
    for j in range(nv + 1):
        for i in range(nu + 1):
            fu, fv = i / nu, j / nv
            verts.append(frame(-w / 2 + w * fu, -h / 2 + h * fv))
            luv.append((u0 + (u1 - u0) * fu, v0 + (v1 - v0) * fv, lid))
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            faces.append((a, a + 1, a + nu + 2, a + nu + 1))
    ob = A.mesh(verts, faces, mat, recalc=False, piece=piece, smooth=0)
    at = ob.data.attributes.new("luv", "FLOAT_VECTOR", "POINT")
    at.data.foreach_set("vector", np.array(luv, np.float32).ravel())
    return ob


def disc_face(A, frame, r, mat, piece="Emissive", n=48, lid=1.0):
    verts = [frame(0.0, 0.0)] + [frame(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    luv = [(0.5, 0.5, lid)] + [(0.5 + 0.5 * math.cos(2 * math.pi * i / n), 0.5 + 0.5 * math.sin(2 * math.pi * i / n), lid) for i in range(n)]
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    ob = A.mesh(verts, faces, mat, recalc=False, piece=piece, smooth=0)
    at = ob.data.attributes.new("luv", "FLOAT_VECTOR", "POINT")
    at.data.foreach_set("vector", np.array(luv, np.float32).ravel())
    return ob


def wall_frame(x, zc, yc=0.0):
    """Wall sign face at depth x facing +X: u -> +Y (viewer's right), v -> +Z."""
    return lambda u, v: (x, yc + u, zc + v)


def blade_frame(side, y, xc, zc):
    """Blade face at y = side * y: side +1 faces +Y (viewer's right is -X), side -1 faces -Y (right is +X)."""
    return lambda u, v: (xc - side * u, side * y, zc + v)


def make_image(name, layers, w, h):
    """RGBA image from up to two float masks (R = ink1, G = ink2)."""
    a = np.zeros((h, w, 4), np.float32)
    for k, m in enumerate(layers[:3]):
        if m is not None:
            a[..., k] = m
    a[..., 3] = 1.0
    return pk.np_to_image(name, a)


def text_mask_at(canvas, text, fontpath, box, pad=0.04, lines_gap=1.1, spacing=1.0, bold=0):
    """Rasterise `text` fitted into box (x0, y0, x1, y1 in 0..1, y up) of the canvas mask (in place, max).
    bold > 0 dilates the strokes by that many pixels (sign-painter weight for thin CJK fonts)."""
    h, w = canvas.shape
    x0, y0, x1, y1 = box
    bw, bh = max(8, int((x1 - x0) * w)), max(8, int((y1 - y0) * h))
    m = pk.text_mask(text, fontpath, bw, bh, pad=pad, spacing=spacing, lines_gap=lines_gap)
    for _ in range(bold):
        g = m.copy()
        g[1:] = np.maximum(g[1:], m[:-1])
        g[:-1] = np.maximum(g[:-1], m[1:])
        g[:, 1:] = np.maximum(g[:, 1:], m[:, :-1])
        g[:, :-1] = np.maximum(g[:, :-1], m[:, 1:])
        m = g
    r0 = int(y0 * h)
    c0 = int(x0 * w)
    sub = canvas[r0:r0 + m.shape[0], c0:c0 + m.shape[1]]
    np.maximum(sub, m[:sub.shape[0], :sub.shape[1]], out=sub)
    return canvas


def rect_mask(canvas, box, border=None):
    """Filled (or border-only, width `border` in 0..1 of height) rectangle mask, y up."""
    h, w = canvas.shape
    x0, y0, x1, y1 = box
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = (xx + 0.5) / w, (yy + 0.5) / h
    inside = (u >= x0) & (u <= x1) & (v >= y0) & (v <= y1)
    if border:
        bu = border * h / w
        inner = (u >= x0 + bu) & (u <= x1 - bu) & (v >= y0 + border) & (v <= y1 - border)
        inside = inside & ~inner
    canvas[inside] = 1.0
    return canvas


def bracket(A, x0, x1, z, y=0.0, mat="powder_black", s=0.04):
    """Square tube arm from the wall (x = 0) to the sign + wall plate with bolts."""
    A.box((x1 - x0, s, s), at=((x0 + x1) / 2, y, z), mat=mat, bevel=0.004, piece="Body")
    A.box((0.012, 0.16, 0.16), at=(0.006, y, z), mat=mat, bevel=0.003, piece="Body")
    for dy in (-0.05, 0.05):
        for dz in (-0.05, 0.05):
            A.cyl(0.008, 0.012, at=(0.012, y + dy, z + dz), axis="X", mat="galvanized", n=6, bevel=0.0015, piece="Body")


def border_loop(w, h, r):
    return round_poly(rrect_pts(w, h, r, 6), r * 0.3)


def blade_box(A, W, H, T, z0, gap=0.28, frame_mat="powder_black", face_inset=0.035):
    """Blade housing from the wall: x gap..gap+W, z z0..z0+H, thickness T. Returns face centre (xc, zc)."""
    xc, zc = gap + W / 2, z0 + H / 2
    A.box((W, T, H), at=(xc, 0, zc), mat=frame_mat, bevel=0.012, segs=2, piece="Body")
    # top cap and drip edge
    A.box((W + 0.04, T + 0.04, 0.03), at=(xc, 0, z0 + H + 0.015), mat=frame_mat, bevel=0.006, piece="Body")
    for zz in (z0 + H * 0.82, z0 + H * 0.18):
        bracket(A, 0.0, gap + 0.02, zz, mat=frame_mat)
    # diagonal brace under the lower arm
    A.sweep([(0.01, 0, z0 + H * 0.18 - 0.35), (gap + 0.02, 0, z0 + H * 0.18 - 0.02)], r=0.012, n=8, mat=frame_mat, piece="Body")
    return xc, zc


# --------------------------------------------------------------------------------------
# Signs
# --------------------------------------------------------------------------------------


def cjk_or(text_cjk, text_en):
    return (text_cjk, CJK) if CJK else (text_en, DISPLAY)


@asset("Neon_BladeRamen", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def blade_ramen(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    W, H, T, z0 = 0.62, 2.3, 0.2, 0.0
    # image: vertical "ラーメン" (long vowel drawn upright) + NOODLES band at the bottom
    iw, ih = 256, 1024
    ink1 = np.zeros((ih, iw), np.float32)
    ink2 = np.zeros((ih, iw), np.float32)
    txt, f = cjk_or("ラ\n｜\nメ\nン", "R\nA\nM\nE\nN")
    text_mask_at(ink1, txt, f, (0.08, 0.17, 0.92, 0.98), pad=0.03, lines_gap=1.05, bold=6 if CJK else 0)
    # amber band at the bottom with NOODLES knocked out of it (the red face shows through)
    rect_mask(ink2, (0.06, 0.035, 0.94, 0.135))
    knock = np.zeros((ih, iw), np.float32)
    text_mask_at(knock, "NOODLES", DISPLAY, (0.1, 0.045, 0.9, 0.125), pad=0.05)
    ink2 = np.clip(ink2 - knock, 0, 1)
    make_image("LB_RAMEN", [ink1, ink2], iw, ih)
    xc, zc = blade_box(A, W, H, T, z0, frame_mat="paint_sign_red")
    for side in (1, -1):
        fr = blade_frame(side, T / 2 + 0.002, xc, zc)
        face_quad(A, fr, W - 0.07, H - 0.07, "lb_ramen")
        tube(A, border_loop(W - 0.03, H - 0.03, 0.05), blade_frame(side, T / 2 + 0.03, xc, zc), r=0.008, mat="neon_amber")
        supports(A, resample(border_loop(W - 0.03, H - 0.03, 0.05), 0.02), blade_frame(side, T / 2, xc, zc), blade_frame(side, T / 2 + 0.03, xc, zc), every=0.3)
    A.point("Light", (xc, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 6.0}
    A.view = (0.25, -1.0, 0.15)
    A.lens = 50


def blade_tube_letters(A, letters, colours, W, H, T, z0, border, frame_mat="powder_black", fontpath=None, letter_h=None, r=0.0085):
    fontpath = fontpath or DISPLAY
    xc, zc = blade_box(A, W, H, T, z0, frame_mat=frame_mat)
    n = len(letters)
    pitch = (H - 0.24) / n
    lh = letter_h or pitch * 0.78
    ref, s = place_loops(text_loops("H", fontpath), h=lh)
    for side in (1, -1):
        # dark face panel slightly proud of the housing
        A.box((W - 0.06, 0.006, H - 0.06), at=(xc, side * (T / 2 + 0.003), zc), mat="lacquer_black", bevel=0.002, piece="Body")
        for k, (ch, col) in enumerate(zip(letters, colours)):
            cy = H / 2 - 0.12 - pitch * (k + 0.5)
            loops, _ = place_loops(text_loops(ch, fontpath), cx=0.0, cy=cy, scale=s)
            for lp in loops:
                tube(A, lp, blade_frame(side, T / 2 + 0.032, xc, zc), r=r, mat="neon_" + col, step=0.01)
                supports(A, resample(lp, 0.02), blade_frame(side, T / 2 + 0.006, xc, zc), blade_frame(side, T / 2 + 0.032, xc, zc), every=0.35)
        if border:
            tube(A, border_loop(W - 0.03, H - 0.03, 0.06), blade_frame(side, T / 2 + 0.03, xc, zc), r=0.008, mat="neon_" + border)
    return xc, zc


@asset("Neon_BladeHotel", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def blade_hotel(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    xc, zc = blade_tube_letters(A, "HOTEL", ["magenta"] * 5, 0.78, 3.4, 0.22, 0.0, "cyan")
    A.point("Light", (xc, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 8.0}
    A.view = (0.25, -1.0, 0.15)
    A.lens = 50


@asset("Neon_BladeGames", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def blade_games(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    xc, zc = blade_tube_letters(A, "GAMES", ["cyan", "yellow", "pink", "green", "amber"], 0.66, 2.9, 0.2, 0.0, "violet",
                                frame_mat="paint_frame")
    A.point("Light", (xc, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 8.0}
    A.view = (0.25, -1.0, 0.15)
    A.lens = 50


@asset("Neon_BladeVelvet", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def blade_velvet(A):
    """The club's own blade over the queue: V-E-L-V-E-T in magenta / pink, violet border."""
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    xc, zc = blade_tube_letters(A, "VELVET", ["magenta", "pink", "magenta", "pink", "magenta", "pink"], 0.8, 3.9, 0.22, 0.0,
                                "violet", frame_mat="lacquer_black")
    A.point("Light", (xc, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 8.0}
    A.view = (0.25, -1.0, 0.15)
    A.lens = 50


@asset("Neon_BladeIzakaya", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def blade_izakaya(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    W, H, T, z0 = 0.58, 2.7, 0.18, 0.0
    iw, ih = 256, 1024
    ink1 = np.zeros((ih, iw), np.float32)
    ink2 = np.zeros((ih, iw), np.float32)
    txt, f = cjk_or("居\n酒\n屋", "S\nA\nK\nE")
    text_mask_at(ink1, txt, f, (0.1, 0.16, 0.9, 0.93), pad=0.03, lines_gap=1.08, bold=6 if CJK else 0)
    rect_mask(ink2, (0.05, 0.03, 0.95, 0.97), border=0.008)
    text_mask_at(ink2, "SAKE  BAR", DISPLAY, (0.12, 0.05, 0.88, 0.13), pad=0.06)
    make_image("LB_IZAKAYA", [ink1, ink2], iw, ih)
    xc, zc = blade_box(A, W, H, T, z0, frame_mat="paint_sign_cream")
    for side in (1, -1):
        face_quad(A, blade_frame(side, T / 2 + 0.002, xc, zc), W - 0.07, H - 0.07, "lb_izakaya")
        tube(A, border_loop(W - 0.03, H - 0.03, 0.05), blade_frame(side, T / 2 + 0.03, xc, zc), r=0.008, mat="neon_magenta")
        supports(A, resample(border_loop(W - 0.03, H - 0.03, 0.05), 0.02), blade_frame(side, T / 2, xc, zc), blade_frame(side, T / 2 + 0.03, xc, zc), every=0.3)
    A.point("Light", (xc, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 6.0}
    A.view = (0.25, -1.0, 0.15)
    A.lens = 50


@asset("Neon_Karaoke", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def karaoke(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    W, H, D = 2.8, 0.82, 0.2
    iw, ih = 1024, 300
    ink1 = np.zeros((ih, iw), np.float32)
    ink2 = np.zeros((ih, iw), np.float32)
    txt, f = cjk_or("カラオケ", "KARAOKE")
    text_mask_at(ink1, txt, f, (0.04, 0.3, 0.96, 0.97), pad=0.04, bold=5 if CJK else 0)
    text_mask_at(ink2, "KARAOKE  ·  PRIVATE ROOMS  ·  24H", DISPLAY, (0.12, 0.04, 0.88, 0.27), pad=0.08)
    make_image("LB_KARAOKE", [ink1, ink2], iw, ih)
    zc = H / 2
    A.box((D, W, H), at=(D / 2, 0, zc), mat="powder_black", bevel=0.012, piece="Body")
    for y in (-W / 2 + 0.3, W / 2 - 0.3):
        A.box((0.02, 0.12, 0.3), at=(0.01, y, zc), mat="galvanized", bevel=0.003, piece="Body")
    face_quad(A, wall_frame(D + 0.002, zc), W - 0.06, H - 0.06, "lb_karaoke")
    tube(A, border_loop(W - 0.02, H - 0.02, 0.06), wall_frame(D + 0.03, zc), r=0.008, mat="neon_cyan")
    supports(A, resample(border_loop(W - 0.02, H - 0.02, 0.06), 0.02), wall_frame(D, zc), wall_frame(D + 0.03, zc), every=0.35)
    A.point("Light", (D + 0.15, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 6.0}
    A.view = (1.0, -0.3, 0.1)
    A.lens = 50


@asset("Neon_BoxPawn", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def box_pawn(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    W, H, D = 2.6, 1.0, 0.18
    zc = H / 2
    A.box((D, W, H), at=(D / 2, 0, zc), mat="paint_frame", bevel=0.012, piece="Body")
    A.box((0.006, W - 0.06, H - 0.06), at=(D + 0.003, 0, zc), mat="lacquer_black", bevel=0.002, piece="Body")
    # roundel lightbox (white with a red pawn character) on the left
    iw = ih = 512
    ink1 = np.zeros((ih, iw), np.float32)
    ink2 = np.zeros((ih, iw), np.float32)
    txt, f = cjk_or("質", "$")
    text_mask_at(ink1, txt, f, (0.2, 0.2, 0.8, 0.8), pad=0.02, bold=5 if CJK else 0)
    yy, xx = np.mgrid[0:ih, 0:iw]
    rr = np.hypot((xx + 0.5) / iw - 0.5, (yy + 0.5) / ih - 0.5)
    ink1 = np.maximum(ink1, ((rr > 0.40) & (rr < 0.44)).astype(np.float32))
    make_image("LB_PAWN", [ink1, ink2], iw, ih)
    rc = 0.38
    cyl_y = -W / 2 + 0.5
    A.cyl(rc + 0.03, 0.06, at=(D, cyl_y, zc), axis="X", mat="paint_frame", n=48, bevel=0.006, piece="Body")
    disc_face(A, wall_frame(D + 0.062, zc, cyl_y), rc, "lb_pawn")
    tube(A, circle_pts(rc + 0.015, 64), wall_frame(D + 0.085, zc, cyl_y), r=0.008, mat="neon_red", iters=0)
    # PAWN (green) / & LOANS (amber)
    loops, _ = place_loops(text_loops("PAWN", DISPLAY), w=1.45, h=0.46, cx=0.32, cy=0.15)
    for lp in loops:
        tube(A, lp, wall_frame(D + 0.035, zc), r=0.0085, mat="neon_green", step=0.01)
        supports(A, resample(lp, 0.02), wall_frame(D + 0.006, zc), wall_frame(D + 0.035, zc), every=0.3)
    loops, _ = place_loops(text_loops("& LOANS", DISPLAY), w=1.3, h=0.2, cx=0.32, cy=-0.27)
    for lp in loops:
        tube(A, lp, wall_frame(D + 0.035, zc), r=0.006, mat="neon_amber", step=0.008)
    tube(A, border_loop(W - 0.04, H - 0.04, 0.08), wall_frame(D + 0.03, zc), r=0.008, mat="neon_green")
    A.point("Light", (D + 0.2, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 8.0}
    A.view = (1.0, -0.3, 0.1)
    A.lens = 50


@asset("Neon_PharmacyCross", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def pharmacy_cross(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    S, a, T, gap = 0.95, 0.32, 0.16, 0.3
    xc, zc = gap + S / 2, S / 2
    cross = [(-a / 2, -S / 2), (a / 2, -S / 2), (a / 2, -a / 2), (S / 2, -a / 2), (S / 2, a / 2), (a / 2, a / 2), (a / 2, S / 2),
             (-a / 2, S / 2), (-a / 2, a / 2), (-S / 2, a / 2), (-S / 2, -a / 2), (-a / 2, -a / 2)]
    # housing: cross prism (XZ plane, extruded along Y)
    A.prism([(xc + u, zc + v) for (u, v) in cross], T, mat="paint_frame", plane="XZ", bevel=0.01, piece="Body")
    for side in (1, -1):
        fr = blade_frame(side, T / 2 + 0.002, xc, zc)
        inner = [(u * 0.9, v * 0.9) for (u, v) in cross]
        pts = [fr(u, v) for (u, v) in (inner if side > 0 else list(reversed(inner)))]
        # flat LED face: triangulated as quads (centre + arms)
        verts = pts
        faces = [tuple(range(len(pts)))]
        ob = A.mesh(verts, faces, "led_green", recalc=False, piece="Emissive", smooth=0)
        tube(A, round_poly(cross, 0.02), blade_frame(side, T / 2 + 0.025, xc, zc), r=0.009, mat="neon_white", iters=1, step=0.01)
    bracket(A, 0.0, gap + 0.02, zc + 0.1)
    bracket(A, 0.0, gap + 0.02, zc - 0.1)
    A.point("Light", (xc, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 8.0}
    A.view = (0.3, -1.0, 0.15)
    A.lens = 50


@asset("Neon_Cocktails", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def cocktails(A):
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    W, H, D = 2.2, 1.35, 0.12
    zc = H / 2
    # raceways (black boxes the transformers sit in) behind the icon and the word
    A.box((0.1, 1.95, 0.12), at=(0.05, 0, 0.2), mat="paint_frame", bevel=0.008, piece="Body")
    A.box((0.1, 0.12, 0.85), at=(0.05, 0, 0.82), mat="paint_frame", bevel=0.008, piece="Body")
    fr = wall_frame(D + 0.02, 0.0)
    back = wall_frame(0.1, 0.0)
    # cocktail glass (cyan): bowl triangle, stem, foot; olive (pink) on a pick
    bowl = [(-0.32, 1.25), (0.32, 1.25), (0.0, 0.86)]
    tube(A, round_poly(bowl, 0.03), fr, r=0.009, mat="neon_cyan", iters=1)
    tube(A, [(0.0, 0.86), (0.0, 0.52)], fr, r=0.009, mat="neon_cyan", closed=False, iters=0)
    tube(A, [(-0.17, 0.5), (0.17, 0.5)], fr, r=0.009, mat="neon_cyan", closed=False, iters=0)
    tube(A, [(-0.18, 1.12), (0.0, 1.0), (0.16, 1.18)], fr, r=0.007, mat="neon_white", closed=False, iters=1)
    tube(A, circle_pts(0.055, 32), lambda u, v: fr(u - 0.06, v + 1.07), r=0.008, mat="neon_pink", iters=0)
    loops, _ = place_loops(text_loops("COCKTAILS", DISPLAY), w=1.9, h=0.3, cx=0.0, cy=0.22)
    for lp in loops:
        tube(A, lp, fr, r=0.0075, mat="neon_pink", step=0.009)
        supports(A, resample(lp, 0.02), back, fr, every=0.4)
    for p in ((0.0, 0.6), (0.0, 0.8), (-0.25, 1.22), (0.25, 1.22)):
        supports(A, [p, (p[0], p[1] + 0.001)], back, fr, every=0.0)
    A.point("Light", (0.3, 0, 0.7))
    A.point("WallMount", (0, 0, 0.7))
    A.preview["Emissive"] = {"emit_tex": 8.0}
    A.view = (1.0, -0.3, 0.1)
    A.lens = 50


@asset("Neon_ArrowBar", res=1024, collision="Box", edge=0.004, ao_dist=0.12)
def arrow_bar(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    D = 0.14
    # arrow pointing down and to the viewer's left (toward a door)
    arrow = [(-0.9, 0.45), (0.55, 0.45), (0.55, 0.75), (1.0, 0.2), (0.55, -0.35), (0.55, -0.05), (-0.9, -0.05)]
    zc = 0.45
    A.prism([(u, v) for (u, v) in arrow], D, mat="paint_amber", plane="YZ", at=(D / 2, 0, zc - 0.2), bevel=0.01, piece="Body")
    inner = [(u * 0.92, v * 0.92 + 0.016) for (u, v) in arrow]
    tube(A, round_poly(inner, 0.02), wall_frame(D + 0.02, zc - 0.2), r=0.008, mat="neon_red", iters=1)
    # chaser bulbs along the outline
    pts = resample(round_poly(arrow, 0.02), 0.1)
    for (u, v) in pts:
        p = V(wall_frame(D + 0.012, zc - 0.2)(u * 0.97, v * 0.97 + 0.008))
        A.cyl(0.018, 0.012, at=(D - 0.002, p.y, p.z), axis="X", mat="brass", n=12, bevel=0.002, piece="Body")
        A.sphere(0.022, at=(D + 0.02, p.y, p.z), mat="neon_warm", seg=12, rings=6, piece="Emissive")
    loops, _ = place_loops(text_loops("BAR", DISPLAY), w=0.9, h=0.32, cx=-0.12, cy=0.2)
    for lp in loops:
        tube(A, lp, wall_frame(D + 0.03, zc - 0.2), r=0.008, mat="neon_white", step=0.01)
    A.point("Light", (0.3, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 8.0}
    A.view = (1.0, -0.3, 0.1)
    A.lens = 50


@asset("Neon_OpenSign", res=512, collision="None", edge=0.003, ao_dist=0.08)
def open_sign(A):
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    zc = 0.18
    A.box((0.03, 0.62, 0.03), at=(0.015, 0, 0.0), mat="paint_frame", bevel=0.004, piece="Body")
    fr = wall_frame(0.05, zc)
    tube(A, [(0.29 * math.cos(2 * math.pi * i / 64), 0.15 * math.sin(2 * math.pi * i / 64)) for i in range(64)], fr, r=0.006, mat="neon_blue", iters=0)
    loops, _ = place_loops(text_loops("OPEN", DISPLAY), w=0.4, h=0.15)
    for lp in loops:
        tube(A, lp, fr, r=0.0045, mat="neon_red", step=0.006)
    for y in (-0.2, 0.2):
        A.cyl(0.002, 0.16, at=(0.03, y, 0.015), mat="steel", n=6, bevel=None, piece="Body")
    A.point("Light", (0.1, 0, zc))
    A.point("WallMount", (0, 0, zc))
    A.preview["Emissive"] = {"emit_tex": 8.0}
    A.view = (1.0, -0.3, 0.1)
    A.lens = 60


# --------------------------------------------------------------------------------------
# Street dressing
# --------------------------------------------------------------------------------------


def corrugated(A, W, z0, z1, x, mat, amp=0.008, pitch=0.075, piece="Body"):
    """Roll-up shutter curtain in the YZ plane at depth x (front +X), slats along Y."""
    nv = max(8, int((z1 - z0) / pitch * 6))

    def f(u, v):
        z = z0 + (z1 - z0) * v
        ph = (z - z0) / pitch * 2 * math.pi
        return (x + amp * (0.5 + 0.5 * math.cos(ph)) ** 1.5, -W / 2 + W * u, z)
    return A.grid(f, 4, nv, mat=mat, smooth=180, piece=piece)


def shutter_box(A, W, z, x=0.0):
    A.box((0.36, W + 0.12, 0.42), at=(x + 0.18, 0, z + 0.21), mat="shutter_tint", bevel=0.012, piece="Body")
    A.box((0.38, W + 0.14, 0.03), at=(x + 0.19, 0, z + 0.435), mat="galvanized", bevel=0.004, piece="Body")


@asset("Street_Shutter", res=2048, collision="Box", edge=0.004, ao_dist=0.25, mask=True)
def shutter(A):
    W, H = 3.8, 3.0
    corrugated(A, W, 0.04, H, 0.06, "shutter_tint")
    for s in (-1, 1):
        A.box((0.07, 0.06, H), at=(0.05, s * (W / 2 + 0.03), H / 2), mat="galvanized", bevel=0.004, piece="Body")
    A.box((0.08, W, 0.06), at=(0.07, 0, 0.05), mat="steel_dark", bevel=0.006, piece="Body")
    A.box((0.03, 0.18, 0.025), at=(0.12, 0.6, 0.12), mat="steel", bevel=0.004, piece="Body")
    A.box((0.03, 0.06, 0.08), at=(0.12, -0.9, 0.09), mat="brass_aged", bevel=0.004, piece="Body")
    shutter_box(A, W, H)
    # stickers / graffiti strip as darker paint patches (part of the slats' grime)
    A.point("Light", (0.4, 0, H + 0.3))
    A.view = (1.0, -0.5, 0.2)
    A.lens = 45


@asset("Street_Shopfront", res=2048, collision="Box", edge=0.004, ao_dist=0.25)
def shopfront(A):
    A.piece("Glass", "Glass", res=512, glass=True)
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    A.cur = "Body"
    W, H = 3.8, 3.0
    # stallriser, frames, door
    A.box((0.12, W, 0.45), at=(0.06, 0, 0.225), mat="stucco_dark", bevel=0.01, piece="Body")
    mullions = [-W / 2, -0.55, 0.55, W / 2]
    for y in mullions:
        A.box((0.1, 0.07, H - 0.45), at=(0.08, y, 0.45 + (H - 0.45) / 2), mat="paint_frame", bevel=0.006, piece="Body")
    for z in (0.45, 2.35, H):
        A.box((0.1, W + 0.07, 0.07), at=(0.08, 0, z), mat="paint_frame", bevel=0.006, piece="Body")
    # door (right bay, centre) with a push bar
    A.box((0.05, 1.0, 2.25), at=(0.03, 0.0, 1.125 + 0.02), mat="paint_frame", bevel=0.006, piece="Body")
    A.box((0.03, 0.8, 0.04), at=(0.09, 0.0, 1.05), mat="steel", bevel=0.006, piece="Body")
    # glass panes
    for (y0, y1, z0, z1) in ((-W / 2, -0.55, 0.45, 2.35), (0.55, W / 2, 0.45, 2.35), (-W / 2, W / 2, 2.35, H), (-0.45, 0.45, 0.25, 2.2)):
        A.box((0.008, y1 - y0 - 0.07, z1 - z0 - 0.07), at=(0.06 if (y0, y1) != (-0.45, 0.45) else 0.05, (y0 + y1) / 2, (z0 + z1) / 2),
              mat="glass_shop", bevel=None, piece="Glass")
    # interior: lit back wall 1.2 m behind, a counter, shelves (opaque) and a ceiling light panel
    face_quad(A, wall_frame(-1.2, 1.55), W - 0.1, 2.9, "shop_warm", lid=1.0)
    A.box((1.2, 0.04, 3.0), at=(-0.6, W / 2 - 0.02, 1.5), mat="stucco_dark", bevel=None, piece="Body")
    A.box((1.2, 0.04, 3.0), at=(-0.6, -W / 2 + 0.02, 1.5), mat="stucco_dark", bevel=None, piece="Body")
    A.box((1.2, W, 0.04), at=(-0.6, 0, 3.0), mat="stucco_dark", bevel=None, piece="Body")
    A.box((1.2, W, 0.04), at=(-0.6, 0, 0.02), mat="concrete_dark", bevel=None, piece="Body")
    A.box((0.5, 1.3, 1.0), at=(-0.65, -1.05, 0.5), mat="walnut_satin", bevel=0.01, piece="Body")
    for z in (0.8, 1.3, 1.8):
        A.box((0.3, 1.1, 0.03), at=(-0.95, 1.1, z), mat="steel_dark", bevel=0.003, piece="Body")
        for k in range(7):
            A.box((0.2, 0.1, 0.18 + 0.05 * (k % 3)), at=(-0.95, 0.65 + k * 0.14, z + 0.1 + 0.025 * (k % 3)), mat="magazines", bevel=0.003, piece="Body")
    face_quad(A, lambda u, v: (-0.6 + v, u, 2.97), 3.0, 0.5, "neon_white", lid=1.0)
    # rolled-up shutter in its box above
    shutter_box(A, W, H)
    A.point("Light", (-0.4, 0, 2.6))
    A.preview["Emissive"] = {"emit_tex": 3.0}
    A.preview["Glass"] = {"glass": {"trans": 1.0, "rough": 0.03}}
    A.view = (1.0, -0.45, 0.15)
    A.lens = 40


@asset("Street_ACUnit", res=1024, collision="Box", edge=0.004, ao_dist=0.15)
def ac_unit(A):
    W, H, D = 0.82, 0.58, 0.3
    x0 = 0.12
    A.box((D, W, H), at=(x0 + D / 2, 0, H / 2 + 0.03), mat="paint_ac", bevel=0.012, segs=2, piece="Body")
    # fan grille: rings + spokes on the front
    cy, cz, R = -0.12, H / 2 + 0.03, 0.22
    A.cyl(R + 0.01, 0.012, at=(x0 + D, cy, cz), axis="X", mat="steel_dark", n=48, bevel=0.002, piece="Body")
    for k in range(1, 6):
        A.sweep([(x0 + D + 0.016, cy + R * k / 6 * math.cos(2 * math.pi * i / 40), cz + R * k / 6 * math.sin(2 * math.pi * i / 40)) for i in range(40)],
                r=0.0025, n=6, mat="paint_ac", closed=True, piece="Body")
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        A.sweep([(x0 + D + 0.016, cy, cz), (x0 + D + 0.016, cy + R * math.cos(a), cz + R * math.sin(a))], r=0.004, n=6, mat="paint_ac", piece="Body")
    for i in range(10):    # side fins (louvres) on the right panel
        A.box((0.004, 0.18, 0.012), at=(x0 + D + 0.002, 0.27, 0.12 + i * 0.04), rot=(-25, 0, 0), mat="paint_ac", bevel=None, piece="Body")
    # wall brackets (L angles) under the unit, pipes into the wall, drip hose
    for y in (-0.3, 0.3):
        A.box((x0 + D + 0.05, 0.04, 0.04), at=((x0 + D + 0.05) / 2, y, 0.01), mat="galvanized", bevel=0.003, piece="Body")
        A.sweep([(0.01, y, -0.3), (x0 + D, y, 0.0)], r=0.012, n=6, mat="galvanized", piece="Body")
    A.sweep([(x0, 0.32, 0.2), (0.05, 0.36, 0.2), (0.0, 0.36, 0.2)], r=0.012, n=8, mat="copper" if "copper" in pkm.MATS else "brass_aged", piece="Body")
    A.sweep([(x0 + 0.1, 0.3, 0.03), (x0 + 0.1, 0.32, -0.15), (x0 + 0.08, 0.33, -0.6)], r=0.008, n=6, mat="plastic_black", piece="Body")
    A.view = (1.0, -0.6, 0.25)
    A.lens = 50


@asset("Street_Awning", res=2048, collision="None", edge=0.004, ao_dist=0.2, mask=True)
def awning(A):
    W, P, drop = 3.2, 1.15, 0.55
    z0 = 0.0  # top attachment at the wall = origin

    def canvas(u, v):
        y = -W / 2 + W * u
        x = P * v
        z = z0 - drop * v + 0.025 * math.sin(math.pi * v) - 0.012 * math.sin(math.pi * u * 6) * v
        return (x, y, z)
    A.grid(canvas, 48, 12, mat="canvas_tint", smooth=180, piece="Body")
    # scalloped valance hanging at the front
    nsc = 9

    def valance(u, v):
        y = -W / 2 + W * u
        ph = (u * nsc) % 1.0
        depth = 0.22 + 0.06 * math.sin(math.pi * ph)
        return (P + 0.005, y, z0 - drop - depth * v)
    A.grid(valance, nsc * 8, 4, mat="canvas_tint", smooth=180, piece="Body")
    # frame: top bar, front bar, arms
    A.sweep([(0.03, -W / 2, z0), (0.03, W / 2, z0)], r=0.018, n=10, mat="paint_frame", piece="Body")
    A.sweep([(P, -W / 2, z0 - drop - 0.01), (P, W / 2, z0 - drop - 0.01)], r=0.016, n=10, mat="paint_frame", piece="Body")
    for y in (-W / 2 + 0.05, 0.0, W / 2 - 0.05):
        A.sweep([(0.02, y, z0 - 0.85), (P - 0.02, y, z0 - drop - 0.02)], r=0.012, n=8, mat="paint_frame", piece="Body")
        A.box((0.012, 0.08, 0.1), at=(0.006, y, z0 - 0.85), mat="paint_frame", bevel=0.002, piece="Body")
    A.view = (1.0, -0.6, 0.2)
    A.lens = 45


@asset("Street_Vending", res=2048, collision="Box", edge=0.004, ao_dist=0.2)
def vending(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    A.piece("Glass", "Glass", res=512, glass=True)
    A.cur = "Body"
    W, D, H = 1.0, 0.72, 1.86
    A.box((D, W, H - 0.06), at=(-D / 2 + 0.04, 0, 0.06 + (H - 0.06) / 2), mat="paint_vend", bevel=0.02, segs=3, piece="Body")
    A.box((D - 0.04, W - 0.04, 0.06), at=(-D / 2 + 0.04, 0, 0.03), mat="rubber", bevel=0.01, piece="Body")
    # display window (glass over a lit product panel), button strip, coin panel, delivery flap
    face_quad(A, wall_frame(0.042, 1.22, -0.08), 0.74, 1.05, "vend_display", lid=1.0)
    A.box((0.006, 0.76, 1.07), at=(0.052, -0.08, 1.22), mat="glass_shop", bevel=None, piece="Glass")
    A.box((0.03, 0.8, 0.05), at=(0.055, -0.08, 1.77), mat="steel_dark", bevel=0.004, piece="Body")
    face_quad(A, wall_frame(0.071, 1.77, -0.08), 0.74, 0.03, "neon_white", lid=1.0)
    for k in range(8):
        A.box((0.012, 0.05, 0.02), at=(0.05, -0.43 + k * 0.1, 0.66), mat="plastic_black", bevel=0.003, piece="Body")
        A.box((0.004, 0.03, 0.008), at=(0.058, -0.43 + k * 0.1, 0.66), mat="neon_green" if k % 3 else "neon_red", bevel=None, piece="Emissive")
    A.box((0.03, 0.16, 0.5), at=(0.05, 0.4, 1.15), mat="steel", bevel=0.005, piece="Body")
    A.box((0.006, 0.05, 0.08), at=(0.066, 0.4, 1.3), mat="neon_amber", bevel=None, piece="Emissive")
    A.box((0.05, 0.7, 0.22), at=(0.04, -0.08, 0.33), mat="plastic_black", bevel=0.01, piece="Body")
    A.view = (1.0, -0.55, 0.2)
    A.lens = 45
    A.point("Light", (0.4, -0.08, 1.2))
    A.preview["Emissive"] = {"emit_tex": 4.0}
    A.preview["Glass"] = {"glass": {"trans": 1.0, "rough": 0.03}}


@asset("Street_Cables", res=1024, collision="None", edge=0.003, ao_dist=0.05)
def cables(A):
    span = 20.2
    rng = random.Random(9)
    for k in range(6):
        z0 = rng.uniform(-0.6, 0.6)
        z1 = rng.uniform(-0.6, 0.6)
        x0 = rng.uniform(-0.5, 0.5)
        x1 = x0 + rng.uniform(-0.8, 0.8)
        sag = rng.uniform(0.6, 1.4)
        pts = []
        n = 80
        for i in range(n + 1):
            t = i / n
            pts.append((x0 + (x1 - x0) * t, -span / 2 + span * t, z0 + (z1 - z0) * t - sag * 4 * t * (1 - t)))
        A.sweep(pts, r=rng.choice((0.008, 0.01, 0.014)), n=6, mat="cable", piece="Body")
    # wall insulators / clamps at both ends
    for s in (-1, 1):
        for k in range(3):
            A.box((0.08, 0.06, 0.06), at=(0.0, s * span / 2, -0.4 + 0.4 * k), mat="galvanized", bevel=0.005, piece="Body")
    # a junction box hanging mid-span and a dangling drop line
    A.box((0.14, 0.2, 0.26), at=(0.1, 1.5, -1.45), mat="paint_frame", bevel=0.01, piece="Body")
    A.sweep([(0.1, 1.5, -1.32), (0.1, 1.5, -1.0)], r=0.008, n=6, mat="cable", piece="Body")
    A.view = (0.6, -1.0, 0.2)
    A.lens = 35


@asset("Street_SteamVent", res=1024, collision="None", edge=0.003, ao_dist=0.1)
def steam_vent(A):
    W, L = 0.62, 0.92
    A.box((L + 0.08, W + 0.08, 0.03), at=(0, 0, 0.0), mat="cast_iron", bevel=0.006, piece="Body")
    for i in range(14):
        y = -W / 2 + 0.03 + i * (W - 0.06) / 13
        A.box((L - 0.04, 0.018, 0.035), at=(0, y, 0.012), mat="cast_iron", bevel=0.003, piece="Body")
    A.box((L - 0.1, W - 0.1, 0.01), at=(0, 0, -0.05), mat="rust_drum", bevel=None, piece="Body")
    A.view = (1.0, -0.6, 0.8)
    A.lens = 50


@asset("Street_FireBarrel", res=1024, collision="Convex", edge=0.004, ao_dist=0.2)
def fire_barrel(A):
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    A.cur = "Body"
    r, h = 0.29, 0.88
    prof = [(0, 0.0), (r - 0.01, 0.0), (r, 0.015), (r, h - 0.015), (r - 0.012, h), (r - 0.022, h)]
    A.lathe(prof, mat="rust_drum", n=48, smooth=50, cap=False)
    A.lathe([(r - 0.022, h - 0.002), (r - 0.024, 0.02), (0, 0.02)], mat="rust_drum", n=48, smooth=50, cap=False)
    for z in (h * 0.33, h * 0.66):
        A.lathe([(r + 0.006, z - 0.012), (r + 0.012, z), (r + 0.006, z + 0.012)], mat="rust_drum", n=48, smooth=50, cap=False)
    # punched air holes glowing from the fire inside
    rng = random.Random(4)
    for k in range(14):
        a = rng.uniform(0, 2 * math.pi)
        z = rng.uniform(0.12, 0.3)
        A.cyl(0.022, 0.008, at=((r + 0.001) * math.cos(a), (r + 0.001) * math.sin(a), z), axis="X", rot=(0, 0, math.degrees(a)),
              mat="ember", n=10, bevel=None, piece="Emissive")
    # coals and burning wood at the top, flame tongues
    A.cyl(r - 0.03, 0.04, at=(0, 0, h - 0.12), mat="ember", n=32, bevel=0.01, piece="Emissive")
    for k in range(6):
        a = k * 1.1
        A.box((0.42, 0.05, 0.05), at=(0.05 * math.cos(a), 0.05 * math.sin(a), h - 0.06 + 0.02 * k), rot=(0, rng.uniform(-15, 15), math.degrees(a)),
              mat="pine", bevel=0.01, piece="Body")
    for k in range(9):
        a = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(0.0, 0.16)
        fh = rng.uniform(0.10, 0.24)
        cx, cy = rr * math.cos(a), rr * math.sin(a)
        prof_f = [(0, h - 0.06), (0.05, h - 0.05), (0.045, h - 0.02 + fh * 0.35), (0.025, h + fh * 0.7), (0.0, h + fh)]
        ob = A.lathe(prof_f, at=(cx, cy, 0), mat="flame", n=12, smooth=180, piece="Emissive")
        ob.scale = (1.0, rng.uniform(0.35, 0.6), 1.0)
        ob.rotation_euler = (rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), a)
    A.point("Light", (0, 0, h + 0.25))
    A.point("Embers", (0, 0, h + 0.1))
    A.preview["Emissive"] = {"emit_tex": 10.0}
    A.view = (1.0, -0.6, 0.35)
    A.lens = 50


def facade_bay(A, states, ac=False, seed=1, skin="stucco_facade"):
    """4 m x 3.4 m storey module: its own wall skin (x = -0.04..0) with two window openings, frames, sills,
    lintels and lit interiors 0.25 m back. Mount it 0.26 m in front of a backdrop wall (origin = skin plane)."""
    A.piece("Emissive", "Emissive", res=1024, emissive=True)
    A.cur = "Body"
    W, H = 4.0, 3.4
    rng = random.Random(seed)
    ww, wh, zc = 1.15, 1.55, 1.75
    hw, hh = ww / 2 + 0.07, wh / 2 + 0.07
    st_ = 0.04
    for (y0, y1, z0, z1) in ((-W / 2, W / 2, 0.0, zc - hh), (-W / 2, W / 2, zc + hh, H), (-W / 2, -1.0 - hw, zc - hh, zc + hh),
                             (-1.0 + hw, 1.0 - hw, zc - hh, zc + hh), (1.0 + hw, W / 2, zc - hh, zc + hh)):
        A.box((st_, y1 - y0, z1 - z0), at=(-st_ / 2, (y0 + y1) / 2, (z0 + z1) / 2), mat=skin, bevel=None, piece="Body")
    for k, st in enumerate(states):
        yc = -1.0 + 2.0 * k
        # frame + mullion + transom
        for s in (-1, 1):
            A.box((0.1, 0.07, wh + 0.07), at=(0.05, yc + s * (ww / 2 + 0.035), zc), mat="paint_frame", bevel=0.005, piece="Body")
        for z in (zc - wh / 2 - 0.035, zc + wh / 2 + 0.035):
            A.box((0.1, ww + 0.14, 0.07), at=(0.05, yc, z), mat="paint_frame", bevel=0.005, piece="Body")
        A.box((0.06, 0.04, wh), at=(0.03, yc, zc), mat="paint_frame", bevel=0.003, piece="Body")
        A.box((0.06, ww, 0.04), at=(0.03, yc, zc + wh * 0.22), mat="paint_frame", bevel=0.003, piece="Body")
        A.box((0.2, ww + 0.3, 0.06), at=(0.1, yc, zc - wh / 2 - 0.09), mat="concrete", bevel=0.008, piece="Body")
        A.box((0.08, ww + 0.36, 0.16), at=(0.04, yc, zc + wh / 2 + 0.15), mat="concrete_dark", bevel=0.008, piece="Body")
        # lit interior plane 0.25 m behind the glass line (recessed reveal)
        face_quad(A, wall_frame(-0.25, zc, yc), ww, wh, "window_lit", lid=st / 8.0)
        for s in (-1, 1):
            A.box((0.25, 0.02, wh), at=(-0.125, yc + s * ww / 2, zc), mat="stucco_dark", bevel=None, piece="Body")
        for z in (zc - wh / 2, zc + wh / 2):
            A.box((0.25, ww, 0.02), at=(-0.125, yc, z), mat="stucco_dark", bevel=None, piece="Body")
        if st in (1, 5) and rng.random() < 0.9:   # a plant / bottle silhouette on the sill
            A.cyl(0.06, 0.16, at=(-0.18, yc + rng.uniform(-0.35, 0.35), zc - wh / 2 + 0.01), mat="plastic_black", n=12, bevel=0.005, piece="Body")
    # storey band and downpipe
    A.box((0.06, W, 0.12), at=(0.03, 0, 0.06), mat="concrete_dark", bevel=0.006, piece="Body")
    A.sweep([(0.08, W / 2 - 0.08, 0.0), (0.08, W / 2 - 0.08, H)], r=0.045, n=12, mat="galvanized", piece="Body")
    for z in (0.6, 1.8, 3.0):
        A.box((0.1, 0.02, 0.03), at=(0.05, W / 2 - 0.08, z), mat="galvanized", bevel=0.002, piece="Body")
    if ac:
        ox, oy, oz = 0.12, 1.0, 0.35
        A.box((0.3, 0.8, 0.56), at=(ox + 0.15, oy, oz + 0.28), mat="paint_ac", bevel=0.012, piece="Body")
        A.cyl(0.2, 0.012, at=(ox + 0.3, oy - 0.12, oz + 0.28), axis="X", mat="steel_dark", n=40, bevel=0.002, piece="Body")
        for y in (oy - 0.3, oy + 0.3):
            A.box((0.46, 0.04, 0.04), at=(0.23, y, oz), mat="galvanized", bevel=0.003, piece="Body")
    A.preview["Emissive"] = {"emit_tex": 4.0}
    A.view = (1.0, -0.35, 0.1)
    A.lens = 45


@asset("Street_FacadeBay_A", res=2048, collision="None", edge=0.004, ao_dist=0.2)
def facade_a(A):
    facade_bay(A, [1, 0], ac=False, seed=1, skin="stucco_facade")


@asset("Street_FacadeBay_B", res=2048, collision="None", edge=0.004, ao_dist=0.2)
def facade_b(A):
    facade_bay(A, [0, 0], ac=True, seed=2, skin="stucco_brown")


@asset("Street_FacadeBay_C", res=2048, collision="None", edge=0.004, ao_dist=0.2)
def facade_c(A):
    facade_bay(A, [3, 0], ac=True, seed=3, skin="tile_teal")


@asset("Street_FacadeBay_D", res=2048, collision="None", edge=0.004, ao_dist=0.2)
def facade_d(A):
    facade_bay(A, [0, 5], ac=False, seed=4, skin="stucco_facade")


# --------------------------------------------------------------------------------------
# Build (same pipeline as build_club.build, own JSON / render folders, BC-driven emissive previews)
# --------------------------------------------------------------------------------------


def emissive_preview(m, strength):
    """Product-shot material for an emissive piece: emission colour = baked BC (multi-colour signs)."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    tex = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage" and n.image and n.image.colorspace_settings.name == "sRGB")
    nt.links.new(tex.outputs[0], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = strength * 0.4
    bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
    for l in list(bsdf.inputs["Base Color"].links):
        nt.links.remove(l)


def build(aid, res_cap, do_render=True, render_res=(1920, 1080), samples=12):
    t0 = time.time()
    spec = NEON[aid]
    pk.reset_scene()
    A = pk.Asset(aid, **spec["kw"])
    spec["fn"](A)
    out_dir = os.path.join(OUT, aid)
    os.makedirs(out_dir, exist_ok=True)
    objs = A.finish(out_dir)
    pieces_json, tris, tex = [], {}, {}
    scale = res_cap / 4096.0
    for pname, ob in objs.items():
        pc = A.pieces[pname]
        res = max(256, int(pc.res * scale))
        paths = pk.bake_piece(ob, A, pc, res, out_dir, log=log)
        slot = pc.slot or f"M_{aid}_{pname}"
        pk.assign_single(ob, pk.textured_material(slot, paths))
        tex[pname] = res
        tris[pname] = pk.tri_count(ob)
        pk.export_fbx(ob, os.path.join(out_dir, f"SM_{aid}_{pname}.fbx"))
        pv = dict(A.preview.get(pname, {}))
        emit_tex = pv.pop("emit_tex", None)
        if pc.glass:
            pv.setdefault("glass", {})
        m = pk.textured_material(slot + "_PV", paths, pv)
        if pc.emissive and emit_tex:
            emissive_preview(m, emit_tex)
        pk.assign_single(ob, m)
        if pc.glass or pc.emissive:
            ob.visible_shadow = False
        pieces_json.append({"Name": pname, "Kind": pc.kind, "Slots": [slot]})
    lo, hi = pk.bbox_of(objs.values())
    entry = {
        "Group": A.group,
        "Pieces": pieces_json,
        "Points": {k: pk.ue(v) for k, v in A.points.items()},
        "Bounds": {"Min": pk.ue((lo.x, hi.y, lo.z)), "Max": pk.ue((hi.x, lo.y, hi.z))},
        "Collision": A.collision,
        "Triangles": tris,
        "TextureSize": tex,
    }
    if A.mask:
        entry["TintVariants"] = {}
    pk.update_json(JSON_PATH, aid, entry)
    os.makedirs(CACHE, exist_ok=True)
    for o in objs.values():
        o["pv_view"] = list(A.view or (1.0, -0.62, 0.38))
        o["pv_lens"] = A.lens
        o["pv_margin"] = A.margin
    bpy.data.libraries.write(os.path.join(CACHE, aid + ".blend"), set(objs.values()), fake_user=True, path_remap="ABSOLUTE")
    log(f"  {aid}: tris {tris} tex {tex} build {time.time() - t0:.0f}s")
    if do_render:
        st = pk.setup_studio(back=(0.02, 0.02, 0.024))
        pk.frame(st, lo, hi, view=A.view or (1.0, -0.62, 0.38), lens=A.lens, margin=A.margin, key_scale=0.35)
        png = os.path.join(PNG_RENDERS, aid + ".png")
        t1 = time.time()
        pk.render(png, render_res, samples)
        to_jpg(png, os.path.join(RENDERS, aid + ".jpg"))
        log(f"  {aid}: render {time.time() - t1:.0f}s")
    return entry


def to_jpg(png, jpg, quality=90):
    from PIL import Image
    os.makedirs(os.path.dirname(jpg), exist_ok=True)
    Image.open(png).convert("RGB").save(jpg, quality=quality, subsampling=0, optimize=True)


def lineup(res=(3840, 2160), samples=24):
    pk.reset_scene()
    placed = []
    x_cursor = 0.0
    for row in LINEUP:
        items = []
        for aid in row:
            path = os.path.join(CACHE, aid + ".blend")
            if not os.path.exists(path):
                continue
            with bpy.data.libraries.load(path, link=False) as (src, dst):
                dst.objects = list(src.objects)
            objs = [o for o in dst.objects if o is not None]
            for o in objs:
                bpy.context.scene.collection.objects.link(o)
                for s in o.material_slots:
                    for n in (s.material.node_tree.nodes if s.material else []):
                        if n.bl_idname == "ShaderNodeTexImage" and n.image is not None and n.image.size[0] > 1024:
                            n.image.scale(1024, 1024)
            lo, hi = pk.bbox_of(objs)
            if abs(hi.y - lo.y) < 0.6 * abs(hi.x - lo.x):     # blade signs: turn the face to the camera
                R = Matrix.Rotation(math.radians(90), 4, "Z")
                for o in objs:
                    o.matrix_world = R @ o.matrix_world
                bpy.context.view_layer.update()
                lo, hi = pk.bbox_of(objs)
            items.append((aid, objs, lo, hi))
        if not items:
            continue
        depth = max(hi.x - lo.x for _, _, lo, hi in items)
        total = sum(hi.y - lo.y for _, _, lo, hi in items) + 0.5 * (len(items) - 1)
        y = total / 2
        for aid, objs, lo, hi in items:
            w = hi.y - lo.y
            off = V((x_cursor + depth / 2 - (lo.x + hi.x) / 2, y - w / 2 - (lo.y + hi.y) / 2, -lo.z))
            for o in objs:
                o.location += off
            placed.extend(objs)
            y -= w + 0.5
        x_cursor -= depth + 1.2
    bpy.context.view_layer.update()
    st = pk.setup_studio(back=(0.02, 0.02, 0.024))
    lo, hi = pk.bbox_of(placed)
    pk.frame(st, lo, hi, view=(1.0, -0.15, 0.6), lens=50, margin=1.03, key_scale=0.35)
    png = os.path.join(PNG_RENDERS, "_Lineup_4K.png")
    pk.render(png, res, samples)
    to_jpg(png, os.path.join(RENDERS, "_Lineup_4K.jpg"))


def main(argv):
    res = 4096
    if "--res" in argv:
        res = int(argv[argv.index("--res") + 1])
    flags = set(a for a in argv if a.startswith("--"))
    ids = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--res", "--samples"))]
    if "--list" in flags:
        for k in NEON:
            print(k)
        return
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 12
    rr = (1920, 1080) if res >= 2048 or "--full-render" in flags else (960, 540)
    if "--lineup-only" not in flags:
        for aid in ids or list(NEON):
            if aid not in NEON:
                log("unknown asset", aid)
                continue
            log(f"== {aid}")
            build(aid, res, "--no-render" not in flags, rr, samples)
    if "--lineup" in flags or "--lineup-only" in flags:
        lineup((3840, 2160) if res >= 2048 else (1280, 720), max(samples, 16))


if __name__ == "__main__":
    argv = sys.argv[1:]
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv
    main(argv)
