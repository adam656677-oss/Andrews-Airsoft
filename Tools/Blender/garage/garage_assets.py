"""Nightjar Garage kit: modular parking-garage pieces and props (Blender, propkit).

Every asset is registered with @asset and built by build_garage.py. Authoring space follows
Tools/Blender/CONVENTIONS.md: metres, +X = front, +Z = up, Blender +Y = Unreal -Y, origin =
floor centre of the footprint. Ceiling / wall fixtures put their origin at the bottom centre and
carry CeilingMount / WallMount points.

Extra per-asset data written to PropsGarage.json:
    Layout        hints for Tools/Unreal/check_layouts.py (multi-level checker):
                  Core [[x0,y0],[x1,y1]] cm (solid footprint smaller than the bounds),
                  Los / Cover / Solid booleans, Ramp {X0,X1,Y0,Y1,Z0,Z1,Wall} cm (walkable slope).
    TintVariants  named paint colours for the role mask (names must exist in layouts.TINTS).
Everything is original: no real brands, logos or signage from real companies.
"""

import math
import os
import random

import numpy as np
from mathutils import Matrix, Vector as V

import propkit as pk
import propkit_mats as pm
from propkit import catmull, circle_pts, round_poly, rrect_pts

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "..", "club", "fonts")
ASSETS = {}

# Lineup sheet (rows back to front)
LINEUP = [
    ["Garage_Ramp"],
    ["Garage_PipeRun", "Garage_Scaffold", "Garage_MaintCage", "Garage_ElevatorDoors", "Garage_RoofHVAC"],
    ["Garage_TicketBooth", "Garage_BarrierArm", "Garage_HeightBar", "Garage_Pillar", "Garage_Railing_3m"],
    ["Garage_JerseyBarrier", "Garage_BlockPallet", "Garage_PayMachine", "Garage_LightFluo", "Garage_LightSodium",
     "Garage_ExitSign", "Garage_Cone", "Garage_WheelStop", "Garage_Drain"],
]

LEVEL_TINTS = {"Teal": [0.0, 0.2, 0.22], "Orange": [0.72, 0.24, 0.02], "Red": [0.48, 0.03, 0.02],
               "Blue": [0.03, 0.12, 0.42], "Green": [0.05, 0.28, 0.08]}


def asset(aid, **kw):
    def deco(fn):
        ASSETS[aid] = {"fn": fn, "kw": dict(group="Garage", **kw)}
        return fn
    return deco


def font(name="BigShoulders-Bold.ttf"):
    p = os.path.abspath(os.path.join(FONT_DIR, name))
    return p if os.path.exists(p) else None


# ======================================================================================
# Recipes (registered into propkit_mats.MATS so propkit.get_mat can build them)
# ======================================================================================
_out = pm._out


def _wear(nb, c, scale=18.0, edge=0.9, amt=0.8, lo=0.62, hi=0.75):
    n1, _ = nb.noise(c.P, scale, 5.0, 0.65)
    return nb.clamp(nb.add(nb.mul(c.edge, edge), nb.mul(nb.ss(lo, hi, n1), amt)))


def r_pillar(nb, c, base=(0.30, 0.292, 0.276)):
    """Cast column: concrete, yellow/black hazard band at the base (0-0.9 m), tintable level band
    (1.55-2.25 m, role mask R) for the painted level colour, chipped at the arrises."""
    o = pm.concrete(nb, c, col=base, rough=0.86)
    x, y, z = nb.sep(c.P)
    haz = nb.math("LESS_THAN", z, 0.9)
    s = nb.math("FRACT", nb.mul(nb.add(nb.add(z, x), y), 1.0 / 0.3))
    stripe = nb.math("GREATER_THAN", s, 0.5)
    hz_col = nb.mixc(stripe, (0.70, 0.43, 0.02), (0.014, 0.014, 0.014))
    wear = _wear(nb, c, 16.0, 0.9, 0.75)
    wear = nb.clamp(nb.add(wear, nb.mul(nb.ss(0.14, 0.0, z), 0.7)))
    pmk = nb.mul(haz, nb.sub(1.0, wear))
    col = nb.mixc(pmk, o["col"], hz_col)
    band = nb.mul(nb.math("GREATER_THAN", z, 1.55), nb.math("LESS_THAN", z, 2.25))
    bw = _wear(nb, c, 22.0, 0.8, 0.6, 0.66, 0.78)
    bm = nb.mul(band, nb.sub(1.0, bw))
    col = nb.mixc(bm, col, (0.75, 0.75, 0.75))
    # thin white pinstripes framing the band
    ps = nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(z, 1.5)), 0.02),
                nb.sub(1.0, bw))
    ps = nb.add(ps, nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(z, 2.3)), 0.02), nb.sub(1.0, bw)))
    col = nb.mixc(nb.clamp(ps), col, (0.62, 0.62, 0.6))
    rough = nb.mix(pmk, o["rough"], 0.42)
    rough = nb.mix(bm, rough, 0.38)
    h = nb.add(o["h"], nb.mul(nb.add(pmk, bm), 0.4))
    return _out(col, rough, 0.0, h, 0.4, 0.0008, mask=bm)


def r_hazard(nb, c, period=0.2, yellow=(0.70, 0.43, 0.02), black=(0.014, 0.014, 0.014), rough=0.42, chip=0.6):
    x, y, z = nb.sep(c.P)
    s = nb.math("FRACT", nb.mul(nb.add(nb.add(z, x), y), 1.0 / period))
    stripe = nb.math("GREATER_THAN", s, 0.5)
    col = nb.mixc(stripe, yellow, black)
    o = pm.paint(nb, c, col=(0.5, 0.5, 0.5), rough=rough, peel=0.6, grime=0.45, chip=chip, chip_col=(0.18, 0.18, 0.18))
    sm, _ = nb.noise(c.P, 5.0, 5.0, 0.6)
    col = nb.cmul(col, nb.add(0.92, nb.mul(sm, 0.16)))
    col = nb.cmul(col, nb.mix(nb.mul(c.cav, 1.4), 1.0, 0.5))
    return _out(col, o["rough"], 0.0, o["h"], 0.08, 0.0004)


def r_boom(nb, c, period=0.5):
    """Barrier boom: white with red reflective bands along the arm (local Y)."""
    x, y, z = nb.sep(c.P)
    s = nb.math("FRACT", nb.mul(y, 1.0 / period))
    band = nb.math("GREATER_THAN", s, 0.5)
    col = nb.mixc(band, (0.78, 0.78, 0.76), (0.55, 0.02, 0.015))
    sm, _ = nb.noise(c.P, 6.0, 4.0, 0.6)
    g = nb.clamp(nb.add(nb.mul(c.cav, 1.4), nb.mul(nb.ss(0.6, 0.85, sm), 0.35)))
    col = nb.cmul(col, nb.sub(1.0, nb.mul(g, 0.35)))
    r = nb.add(0.3, nb.add(nb.mul(band, -0.05), nb.mul(g, 0.2)))
    op, _ = nb.noise(c.P, 260.0, 2.0, 0.5)
    return _out(col, r, 0.0, op, 0.05, 0.0003)


def r_wheelstop(nb, c):
    """Precast wheel stop with two worn yellow paint bands (by local X)."""
    o = pm.concrete(nb, c, col=(0.33, 0.32, 0.30), rough=0.88)
    x, y, z = nb.sep(c.P)
    ax = nb.math("ABSOLUTE", x)
    band = nb.mul(nb.math("GREATER_THAN", ax, 0.25), nb.math("LESS_THAN", ax, 0.6))
    band = nb.mul(band, nb.math("GREATER_THAN", z, 0.03))
    wear = _wear(nb, c, 20.0, 1.0, 0.9, 0.58, 0.7)
    m = nb.mul(band, nb.sub(1.0, wear))
    col = nb.mixc(m, o["col"], (0.68, 0.44, 0.03))
    return _out(col, nb.mix(m, o["rough"], 0.5), 0.0, nb.add(o["h"], nb.mul(m, 0.3)), 0.4, 0.0008)


def r_picto(nb, c, image="EXIT_PICTO", bg=(0.0, 0.32, 0.07), ink=(0.9, 0.92, 0.88), rough=0.3):
    """Flat printed panel: image (luv u/v) as ink over a background colour (no breakup: crisp)."""
    u, v, lid = nb.sep(c.luv)
    import bpy
    im = bpy.data.images.get(image)
    m = 0.0
    if im is not None:
        s, _ = nb.img(im, nb.combine(u, v, 0.0))
        m = nb.mul(nb.lum(s), nb.math("GREATER_THAN", lid, 0.5))
    col = nb.mixc(m, bg, ink)
    n, _ = nb.noise(c.P, 30.0, 2.0, 0.5)
    col = nb.cmul(col, nb.add(0.97, nb.mul(n, 0.06)))
    return _out(col, rough, 0.0, None)


def r_screen(nb, c, image="PAY_SCREEN"):
    """LCD: image through luv (already coloured: use RGB directly)."""
    u, v, lid = nb.sep(c.luv)
    import bpy
    im = bpy.data.images.get(image)
    col = (0.01, 0.015, 0.03)
    if im is not None:
        s, _ = nb.img(im, nb.combine(u, v, 0.0))
        col = nb.mixc(nb.math("GREATER_THAN", lid, 0.5), (0.01, 0.015, 0.03), s)
    return _out(col, 0.15, 0.0, None)


def r_wallpaint(nb, c, lower=(0.05, 0.11, 0.12), upper=(0.52, 0.52, 0.50), split=1.2):
    """Painted lobby wall: dark dado below `split`, light paint above, scuffs and grime."""
    x, y, z = nb.sep(c.P)
    lo = nb.math("LESS_THAN", z, split)
    col = nb.mixc(lo, upper, lower)
    o = pm.paint(nb, c, col=(0.5, 0.5, 0.5), rough=0.55, peel=0.4, grime=0.5, streak=0.25)
    sm, _ = nb.noise(c.P, 4.0, 5.0, 0.6)
    col = nb.cmul(col, nb.add(0.93, nb.mul(sm, 0.12)))
    sc, _ = nb.noise(nb.vmath("MULTIPLY", c.P, (1.0, 6.0, 1.0)), 10.0, 4.0, 0.6)
    scuff = nb.mul(nb.ss(0.62, 0.72, sc), nb.ss(0.8, 0.1, z))
    col = nb.mixc(nb.mul(scuff, 0.5), col, (0.06, 0.06, 0.06))
    col = nb.cmul(col, nb.mix(nb.mul(c.cav, 1.5), 1.0, 0.5))
    return _out(col, o["rough"], 0.0, o["h"], 0.08, 0.0004)


def r_cmu(nb, c):
    """Concrete masonry unit: coarse open texture."""
    o = pm.concrete(nb, c, col=(0.2, 0.195, 0.185), rough=0.92)
    v, _, _ = nb.vor(c.P, 260.0, "F1", 1.0)
    pits = nb.ss(0.0, 0.18, v)
    col = nb.cmul(o["col"], nb.add(0.78, nb.mul(pits, 0.25)))
    return _out(col, o["rough"], 0.0, nb.add(o["h"], nb.mul(pits, 1.2)), 0.6, 0.001)


def _reg():
    M = pm.MATS
    M["g_pillar"] = (r_pillar, {})
    M["g_hazard"] = (r_hazard, {})
    M["g_hazard_big"] = (r_hazard, dict(period=0.3))
    M["g_boom"] = (r_boom, {})
    M["g_wheelstop"] = (r_wheelstop, {})
    M["g_precast"] = (pm.concrete, dict(col=(0.36, 0.35, 0.33), rough=0.86))
    M["g_cmu"] = (r_cmu, {})
    M["g_exit_face"] = (r_picto, dict(image="EXIT_PICTO"))
    M["g_pay_screen"] = (r_screen, dict(image="PAY_SCREEN"))
    M["g_monitor"] = (r_screen, dict(image="BOOTH_SCREEN"))
    M["g_hall_lantern"] = (r_screen, dict(image="LANTERN"))
    M["g_sign_p"] = (r_picto, dict(image="SIGN_P", bg=(0.02, 0.08, 0.32), ink=(0.85, 0.86, 0.86), rough=0.35))
    M["g_opal"] = (pm.emissive, dict(col=(0.80, 0.86, 0.92)))
    M["g_sodium"] = (pm.emissive, dict(col=(1.0, 0.56, 0.20)))
    M["g_led_amber"] = (pm.emissive, dict(col=(1.0, 0.42, 0.06)))
    M["g_led_green"] = (pm.emissive, dict(col=(0.15, 0.95, 0.3)))
    M["g_warm_panel"] = (pm.emissive, dict(col=(1.0, 0.86, 0.66)))
    M["g_wallpaint"] = (r_wallpaint, {})
    M["g_booth"] = (pm.paint, dict(col=(0.30, 0.31, 0.30), rough=0.38, peel=0.6, grime=0.5, chip=0.4, streak=0.3))
    M["g_pay_body"] = (pm.paint, dict(col=(0.03, 0.045, 0.07), rough=0.32, peel=0.6, grime=0.35, chip=0.35, chip_col=(0.4, 0.4, 0.4)))
    M["g_hvac"] = (pm.paint, dict(col=(0.40, 0.41, 0.40), rough=0.42, peel=0.6, grime=0.6, streak=0.7, rust=0.2))
    M["g_cabinet_yellow"] = (pm.paint, dict(col=(0.70, 0.46, 0.02), rough=0.35, peel=0.6, grime=0.5, chip=0.6, streak=0.35))
    M["g_cone"] = (pm.plastic, dict(col=(0.80, 0.13, 0.008), rough=0.42, grain=300.0, gstr=0.3))
    M["g_reflect"] = (pm.paint, dict(col=(0.78, 0.78, 0.76), rough=0.25, peel=0.2, grime=0.45))
    M["g_shelf"] = (pm.paint, dict(col=(0.22, 0.23, 0.24), rough=0.4, peel=0.5, grime=0.5, chip=0.5))
    M["g_tarp"] = (pm.fabric, dict(col=(0.03, 0.10, 0.26), rough=0.7, weave=500.0))
    M["g_copper"] = (pm.metal, dict(col=(0.75, 0.42, 0.28), rough=0.35, dirt=0.5))
    M["g_insul"] = (pm.rubber, dict(col=(0.012, 0.012, 0.012), rough=0.9))
    M["g_strap"] = (pm.plastic, dict(col=(0.25, 0.09, 0.02), rough=0.5))
    M["g_pipe_red"] = (pm.paint, dict(col=(0.38, 0.015, 0.012), rough=0.35, peel=0.5, grime=0.6, chip=0.3, streak=0.3))
    M["g_conduit"] = (pm.paint, dict(col=(0.32, 0.33, 0.34), rough=0.4, peel=0.3, grime=0.5))
    # tileable slots (MI_<Name>): names chosen so build_garage maps "R_concreteGarage" -> MI_ConcreteGarage
    M["concreteGarage"] = (pm.concrete, dict(col=(0.25, 0.245, 0.23)))
    M["paintLineYellow"] = (pm.paint, dict(col=(0.7, 0.45, 0.03), rough=0.5))
    M["paintLineWhite"] = (pm.paint, dict(col=(0.7, 0.7, 0.68), rough=0.5))
    M["diamondPlate"] = (pm.metal, dict(col=(0.5, 0.5, 0.52), rough=0.4))
    M["corrodedMetal"] = (pm.paint, dict(col=(0.2, 0.1, 0.05), rough=0.7, rust=1.0))


_reg()


# ======================================================================================
# Decal images (numpy rasteriser, row 0 = bottom like Blender images)
# ======================================================================================
def _seg_dist(X, Y, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy + 1e-12
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
    return np.hypot(X - (ax + t * dx), Y - (ay + t * dy))


def _poly_mask(X, Y, pts):
    """Even-odd fill of a polygon (pixel centres)."""
    inside = np.zeros(X.shape, bool)
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        cond = ((y0 > Y) != (y1 > Y)) & (X < (x1 - x0) * (Y - y0) / (y1 - y0 + 1e-12) + x0)
        inside ^= cond
    return inside


def _aa(d, w, px):
    return np.clip((w - d) / px + 0.5, 0, 1)


def img_exit(w=1024, h=512):
    """Original emergency-exit pictogram: arrow, running figure, doorway (white on green)."""
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    X, Y = X / h, Y / h            # units: image height = 1
    px = 1.0 / h
    m = np.zeros((h, w), np.float32)
    # border
    W = w / h
    bd = np.minimum(np.minimum(X, W - X), np.minimum(Y, 1 - Y))
    m = np.maximum(m, _aa(np.abs(bd - 0.045), 0.012, px))
    # arrow (left, pointing left)
    m = np.maximum(m, _aa(_seg_dist(X, Y, (0.18, 0.5), (0.52, 0.5)), 0.055, px))
    head = _poly_mask(X, Y, [(0.10, 0.5), (0.30, 0.70), (0.30, 0.30)])
    m = np.maximum(m, head.astype(np.float32))
    # doorway (right): frame with an opening
    dx0, dx1, dy0, dy1 = 1.36, 1.74, 0.14, 0.86
    frame = np.minimum(np.minimum(np.abs(X - dx0), np.abs(X - dx1)), np.abs(Y - dy1))
    inbox = (X > dx0 - 0.05) & (X < dx1 + 0.05) & (Y > dy0) & (Y < dy1 + 0.05)
    m = np.maximum(m, _aa(frame, 0.035, px) * inbox)
    # running figure (heading toward the doorway)
    cx, cy = 0.98, 0.5
    head_c = (cx + 0.12, cy + 0.27)
    m = np.maximum(m, _aa(np.hypot(X - head_c[0], Y - head_c[1]), 0.07, px))
    hip = (cx - 0.02, cy - 0.06)
    neck = (cx + 0.08, cy + 0.16)
    limbs = [(neck, hip, 0.055),
             (neck, (cx - 0.12, cy + 0.10), 0.04), ((cx - 0.12, cy + 0.10), (cx - 0.22, cy - 0.02), 0.035),
             (neck, (cx + 0.2, cy + 0.06), 0.04), ((cx + 0.2, cy + 0.06), (cx + 0.3, cy + 0.17), 0.035),
             (hip, (cx + 0.14, cy - 0.16), 0.045), ((cx + 0.14, cy - 0.16), (cx + 0.12, cy - 0.36), 0.04),
             ((cx + 0.12, cy - 0.36), (cx + 0.2, cy - 0.37), 0.03),
             (hip, (cx - 0.12, cy - 0.2), 0.045), ((cx - 0.12, cy - 0.2), (cx - 0.3, cy - 0.28), 0.04)]
    for a, b, wd in limbs:
        m = np.maximum(m, _aa(_seg_dist(X, Y, a, b), wd, px))
    out = np.zeros((h, w, 4), np.float32)
    out[..., 0] = out[..., 1] = out[..., 2] = m
    out[..., 3] = 1
    return out


def img_sign_p(w=512, h=512):
    """Generic parking 'P' symbol (rounded square frame + letter shape from strokes)."""
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    X, Y = X / h, Y / h
    px = 1.0 / h
    bd = np.minimum(np.minimum(X, 1 - X), np.minimum(Y, 1 - Y))
    m = _aa(np.abs(bd - 0.06), 0.018, px)
    # letter: stem + bowl (a stroke-drawn P)
    m = np.maximum(m, _aa(_seg_dist(X, Y, (0.36, 0.2), (0.36, 0.8)), 0.075, px))
    bowl_c = (0.5, 0.62)
    r = np.hypot(X - bowl_c[0], Y - bowl_c[1])
    bowl = _aa(np.abs(r - 0.15), 0.07, px) * (X > 0.36)
    m = np.maximum(m, bowl)
    m = np.maximum(m, _aa(_seg_dist(X, Y, (0.36, 0.77), (0.5, 0.77)), 0.07, px))
    m = np.maximum(m, _aa(_seg_dist(X, Y, (0.36, 0.47), (0.5, 0.47)), 0.07, px))
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = m[..., None]
    out[..., 3] = 1
    return out


def _rect(X, Y, x0, y0, x1, y1):
    return ((X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)).astype(np.float32)


def img_pay_screen(w=512, h=384):
    """Pay-station LCD UI: header bar, a big 'P' tile, amount bars and two soft buttons (no text)."""
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    X, Y = X / w, Y / h
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.01, 0.03, 0.09)
    img += (Y[..., None] * 0.05) * np.array([0.2, 0.4, 1.0], np.float32)
    hdr = _rect(X, Y, 0.0, 0.84, 1.0, 1.0)
    img = img * (1 - hdr[..., None]) + hdr[..., None] * np.array([0.02, 0.18, 0.45], np.float32)
    tile = _rect(X, Y, 0.07, 0.38, 0.33, 0.76)
    img = img * (1 - tile[..., None]) + tile[..., None] * np.array([0.05, 0.25, 0.75], np.float32)
    pp = img_sign_p(128, 128)[..., 0]
    xs = ((X - 0.09) / 0.22 * 128).astype(int)
    ys = ((Y - 0.41) / 0.32 * 128).astype(int)
    ok = (xs >= 0) & (xs < 128) & (ys >= 0) & (ys < 128)
    pm_ = np.zeros_like(X)
    pm_[ok] = pp[ys[ok], xs[ok]]
    img = img * (1 - pm_[..., None]) + pm_[..., None] * np.array([0.9, 0.92, 0.95], np.float32)
    for i, (y0, wd) in enumerate(((0.64, 0.5), (0.52, 0.38), (0.42, 0.44))):
        b = _rect(X, Y, 0.40, y0, 0.40 + wd, y0 + 0.06)
        img = img * (1 - b[..., None]) + b[..., None] * np.array([0.7, 0.78, 0.9], np.float32) * (1.0 - 0.25 * i)
    for x0, col in ((0.07, (0.05, 0.6, 0.2)), (0.55, (0.7, 0.12, 0.05))):
        b = _rect(X, Y, x0, 0.08, x0 + 0.38, 0.26)
        img = img * (1 - b[..., None]) + b[..., None] * np.array(col, np.float32)
    out = np.ones((h, w, 4), np.float32)
    out[..., :3] = img
    return out


def img_booth_screen(w=512, h=320):
    """Attendant monitor: four camera tiles of an empty deck (grey gradients, noise)."""
    rng = np.random.default_rng(3)
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    X, Y = X / w, Y / h
    img = np.zeros((h, w, 3), np.float32)
    for i in range(2):
        for j in range(2):
            t = _rect(X, Y, 0.02 + i * 0.49, 0.03 + j * 0.49, 0.49 + i * 0.49, 0.48 + j * 0.49)
            g = 0.08 + 0.22 * (1 - np.abs(Y - (0.25 + j * 0.49)) * 3) + 0.03 * rng.standard_normal(X.shape)
            img += t[..., None] * np.clip(g, 0, 1)[..., None] * np.array([0.6, 0.75, 0.7], np.float32)
    out = np.ones((h, w, 4), np.float32)
    out[..., :3] = np.clip(img, 0, 1)
    return out


def img_lantern(w=256, h=128):
    """Elevator hall lantern: up/down arrows (down lit amber, up dim) on black glass."""
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    X, Y = X / h, Y / h
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.008, 0.008, 0.01)
    up = _poly_mask(X, Y, [(0.55, 0.30), (0.95, 0.30), (0.75, 0.72)]).astype(np.float32)
    dn = _poly_mask(X, Y, [(1.05, 0.72), (1.45, 0.72), (1.25, 0.30)]).astype(np.float32)
    img = img * (1 - up[..., None]) + up[..., None] * np.array([0.12, 0.05, 0.01], np.float32)
    img = img * (1 - dn[..., None]) + dn[..., None] * np.array([1.0, 0.45, 0.05], np.float32)
    out = np.ones((h, w, 4), np.float32)
    out[..., :3] = img
    return out


def make_images():
    for name, fn in (("EXIT_PICTO", img_exit), ("SIGN_P", img_sign_p), ("PAY_SCREEN", img_pay_screen),
                     ("BOOTH_SCREEN", img_booth_screen), ("LANTERN", img_lantern)):
        pk.np_to_image(name, fn())


def face_quad(A, mat, center, size, normal="+X", piece=None, luv=True):
    """Flat quad (decal / screen / sign face) with luv = (u right, v up, 1)."""
    cx, cy, cz = center
    w, h = size
    if normal == "+X":
        vs = [(cx, cy - w / 2, cz - h / 2), (cx, cy + w / 2, cz - h / 2), (cx, cy + w / 2, cz + h / 2), (cx, cy - w / 2, cz + h / 2)]
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]   # a viewer facing the +X side has Blender +Y on the right
    elif normal == "-X":
        vs = [(cx, cy + w / 2, cz - h / 2), (cx, cy - w / 2, cz - h / 2), (cx, cy - w / 2, cz + h / 2), (cx, cy + w / 2, cz + h / 2)]
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    elif normal == "-Y":
        vs = [(cx - w / 2, cy, cz - h / 2), (cx + w / 2, cy, cz - h / 2), (cx + w / 2, cy, cz + h / 2), (cx - w / 2, cy, cz + h / 2)]
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    else:  # +Y
        vs = [(cx + w / 2, cy, cz - h / 2), (cx - w / 2, cy, cz - h / 2), (cx - w / 2, cy, cz + h / 2), (cx + w / 2, cy, cz + h / 2)]
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    ob = A.mesh(vs, [(0, 1, 2, 3)], mat, recalc=False, smooth=0, piece=piece)
    me = ob.data
    nrm = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0)}[normal]
    if me.polygons[0].normal.dot(V(nrm)) < 0:
        me.flip_normals()
    if luv:
        at = me.attributes.new("luv", "FLOAT_VECTOR", "POINT")
        at.data.foreach_set("vector", np.array([(u, v, 1.0) for (u, v) in uv], np.float32).ravel())
    return ob


def chain(A, p0, p1, link=0.035, wire=0.0045, mat="galvanized"):
    """Chain of alternating oval links between two points."""
    p0, p1 = V(p0), V(p1)
    d = p1 - p0
    L = d.length
    n = max(2, int(L / (link * 0.8)))
    q = d.normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()
    prof = circle_pts(wire, 6)
    for i in range(n):
        c = p0 + d * ((i + 0.5) / n)
        ring = [V((0.012 * math.cos(a), 0.0, (link * 0.5) * math.sin(a))) for a in np.linspace(0, 2 * math.pi, 13)[:-1]]
        rot = Matrix.Rotation(math.pi / 2 * (i % 2), 4, "Z")
        A.sweep([tuple(p) for p in ring], prof=prof, mat=mat, closed=True, rot=q @ rot, at=tuple(c), smooth=180)


# ======================================================================================
# Structure
# ======================================================================================
@asset("Garage_Pillar", res=2048, collision="Box", edge=0.006, ao_dist=0.25, mask=True)
def pillar(A):
    """0.6 x 0.6 x 3.0 m cast column (floor to slab soffit): chamfered arrises, painted hazard base and
    level band (tint), a conduit with a junction box on the back face, cast-in lifting socket."""
    S, H = 0.6, 3.0
    A.box((S, S, H), at=(0, 0, H / 2), mat="g_pillar", bevel=0.022, segs=1)
    # capital chamfer strip where the column meets the soffit (shadow gap)
    A.box((S + 0.02, S + 0.02, 0.04), at=(0, 0, H - 0.02), mat="g_precast", bevel=0.008, segs=1)
    # conduit on the -X face: floor box -> ceiling, with saddles and a junction box
    x = -S / 2 - 0.018
    A.cyl(0.011, H - 0.25, at=(x, 0.17, 0.25), mat="galvanized", n=12, bevel=0.0)
    for z in (0.6, 1.4, 2.2, 2.85):
        A.box((0.02, 0.05, 0.018), at=(x + 0.004, 0.17, z), mat="galvanized", bevel=0.003)
    A.box((0.06, 0.12, 0.16), at=(-S / 2 - 0.03, 0.17, 1.15), mat="g_conduit", bevel=0.008)
    A.box((0.012, 0.07, 0.07), at=(-S / 2 - 0.066, 0.17, 1.15), mat="plastic_grey", bevel=0.004)
    A.box((0.05, 0.1, 0.12), at=(-S / 2 - 0.025, 0.17, 0.18), mat="g_conduit", bevel=0.006)
    # rubber corner protectors on the two front arrises (cars clip them)
    for sy in (-1, 1):
        for ax, ay, sx_, sy_ in ((S / 2 + 0.006, sy * (S / 2 - 0.03), 0.012, 0.072), (S / 2 - 0.03, sy * (S / 2 + 0.006), 0.072, 0.012)):
            A.box((sx_, sy_, 0.8), at=(ax, ay, 0.5), mat="rubber", bevel=0.003)
    A.layout = {"Cover": True}
    A.tint_variants = LEVEL_TINTS
    A.view = (1.0, -0.75, 0.35)
    A.lens = 50
    A.preview["Body"] = {"tint": (0.0, 0.2, 0.22)}


@asset("Garage_Ramp", res=1024, collision="Complex", edge=0.01, ao_dist=0.3)
def ramp(A):
    """Car ramp, one storey: 22 m run, 3.3 m rise (15 %), 4.0 m deck between 0.25 m upstand walls that
    stand 1.0 m above the slope; painted curbs, direction arrows, trench drain at the foot and an
    expansion plate at the head. Shared tileable materials (no bake)."""
    A.pieces["Body"] = pk.Piece("Body", "Body", 1024, tileable=True)
    X0, X1, RISE, HW, WT, WH = -11.0, 11.0, 3.3, 2.0, 0.25, 1.0
    k = RISE / (X1 - X0)
    ang = math.degrees(math.atan(k))

    def zs(x):
        return (x - X0) * k
    # solid wedge (concrete) under a 4 cm wearing course (deck concrete)
    xl = X0 + 0.04 / k
    A.prism([(xl, 0.0), (X1, 0.0), (X1, RISE - 0.04)], 2 * HW, at=(0, 0, 0), plane="XZ", mat="concrete", bevel=0.0)
    A.prism([(X0, 0.0), (xl, 0.0), (X1, RISE - 0.04), (X1, RISE)], 2 * HW, at=(0, 0, 0), plane="XZ",
            mat="concreteGarage", bevel=0.0)
    # upstand walls (constant 1.0 m above the slope) with a chamfered cap
    for sy in (-1, 1):
        y = sy * (HW + WT / 2)
        A.prism([(X0, 0.0), (X1, 0.0), (X1, RISE + WH - 0.03), (X0, WH - 0.03)], WT, at=(0, y, 0), plane="XZ",
                mat="concrete", bevel=0.012, segs=1)
        A.prism([(X0, WH - 0.03), (X1, RISE + WH - 0.03), (X1, RISE + WH), (X0, WH)], WT + 0.03, at=(0, y, 0),
                plane="XZ", mat="concrete", bevel=0.01, segs=1)
        # painted wheel-guard curb inside the wall
        yc = sy * (HW - 0.11)
        xa = X0 + 0.3
        A.prism([(xa, zs(xa) - 0.02), (X1, RISE - 0.02), (X1, RISE + 0.15), (xa, zs(xa) + 0.15)], 0.22, at=(0, yc, 0),
                plane="XZ", mat="paintLineYellow", bevel=0.02, segs=1)
    # direction arrows (thermoplastic, 4 mm) lying on the slope, pointing up the ramp (+X)
    arrow = [(-1.2, -0.12), (0.3, -0.12), (0.3, -0.32), (1.0, 0.0), (0.3, 0.32), (0.3, 0.12), (-1.2, 0.12)]
    for xa in (-6.0, 4.0):
        M = Matrix.Translation((xa, 0, zs(xa) + 0.001)) @ Matrix.Rotation(-math.atan(k), 4, "Y")
        o = A.prism(arrow, 0.004, at=(0, 0, 0), plane="XY", mat="paintLineWhite", bevel=0.0)
        o.matrix_world = M @ o.matrix_world
    # expansion plate at the head (lies on the slope) and anti-skid steel strips near the foot
    for xp, wx, mat in ((X1 - 0.17, 0.3, "diamondPlate"), (X0 + 1.2, 0.08, "diamondPlate"), (X0 + 1.6, 0.08, "diamondPlate")):
        o = A.box((wx, 2 * HW - 0.5, 0.006), at=(0, 0, 0.003), mat=mat, bevel=0.0015)
        o.matrix_world = Matrix.Translation((xp, 0, zs(xp))) @ Matrix.Rotation(-math.atan(k), 4, "Y") @ o.matrix_world
    # steel nosing angle on the wall ends (impact protection at the foot)
    for sy in (-1, 1):
        y = sy * (HW + WT / 2)
        A.box((0.02, WT + 0.04, WH), at=(X0 - 0.01, y, WH / 2), mat="paintLineYellow", bevel=0.004)
    A.layout = {"Ramp": {"X0": -1100.0, "X1": 1100.0, "Y0": -200.0, "Y1": 200.0, "Z0": 0.0, "Z1": 330.0,
                         "Wall": 100.0, "WallT": 25.0}}
    A.view = (0.55, -1.0, 0.42)
    A.lens = 35


@asset("Garage_JerseyBarrier", res=2048, collision="Box", edge=0.008, ao_dist=0.3)
def jersey_barrier(A):
    """3.0 m precast safety-shape barrier (New Jersey profile, 0.81 m), lifting loops, pin joints,
    a reflector strip; scuffed and chipped."""
    L = 3.0
    prof = [(-0.305, 0.0), (0.305, 0.0), (0.305, 0.076), (0.127, 0.33), (0.077, 0.81), (-0.077, 0.81),
            (-0.127, 0.33), (-0.305, 0.076)]
    prof = round_poly(prof, 0.012)
    A.prism([(p[0], p[1]) for p in prof], L, at=(0, 0, 0), plane="YZ", mat="g_precast", bevel=0.0, smooth=35)
    # end faces slightly chamfered caps
    # lifting loops (rebar) on top
    for x in (-0.8, 0.8):
        A.sweep(catmull([(x - 0.07, 0, 0.80), (x - 0.06, 0, 0.86), (x, 0, 0.885), (x + 0.06, 0, 0.86), (x + 0.07, 0, 0.80)], 6),
                r=0.011, n=10, mat="cast_iron")
    # pin-and-loop joints at both ends
    for sx in (-1, 1):
        for z in (0.2, 0.6):
            A.sweep(catmull([(sx * L / 2 - sx * 0.02, -0.06, z), (sx * L / 2 + sx * 0.06, -0.05, z), (sx * L / 2 + sx * 0.08, 0, z),
                             (sx * L / 2 + sx * 0.06, 0.05, z), (sx * L / 2 - sx * 0.02, 0.06, z)], 5), r=0.012, n=10, mat="cast_iron")
        A.cyl(0.016, 0.75, at=(sx * (L / 2 + 0.07), 0, 0.05), mat="cast_iron", n=12, bevel=0.003)
    for x in (-0.75, 0.75):      # forklift / drainage toe slots (dark recess plates)
        for sy in (-1, 1):
            A.box((0.3, 0.004, 0.07), at=(x, sy * 0.306, 0.04), mat="rubber", bevel=0.0)
    # reflector buttons (amber) on both sides
    for x in (-1.0, 0.0, 1.0):
        for sy in (-1, 1):
            A.cyl(0.022, 0.012, at=(x, sy * 0.105, 0.58), axis="Y", rot=(0, 0, 0) if sy < 0 else (0, 0, 180),
                  mat="plastic_amber", n=16, bevel=0.002)
    A.view = (1.0, -0.8, 0.4)
    A.lens = 50


@asset("Garage_WheelStop", res=1024, collision="Box", edge=0.006, ao_dist=0.12)
def wheel_stop(A):
    """1.8 m precast wheel stop with tapered ends, yellow paint bands and two anchor pins."""
    L = 1.8
    prof = round_poly([(-0.08, 0.0), (0.08, 0.0), (0.055, 0.1), (-0.055, 0.1)], 0.012)
    A.prism([(p[0], p[1]) for p in prof], L, plane="YZ", mat="g_wheelstop", bevel=0.0, smooth=35)
    for x in (-0.6, 0.6):
        A.cyl(0.03, 0.012, at=(x, 0, 0.092), mat="rubber", n=16, bevel=0.0)
        A.cyl(0.011, 0.016, at=(x, 0, 0.094), mat="cast_iron", n=10, bevel=0.002)
    A.view = (1.0, -0.6, 0.45)
    A.lens = 60


@asset("Garage_Railing_3m", res=1024, collision="Complex", edge=0.003, ao_dist=0.12)
def railing(A):
    """3.0 m galvanised pipe guard rail (1.07 m): three posts on base plates, top + mid rail."""
    L, H, r = 3.0, 1.07, 0.024
    for y in (-1.45, 0.0, 1.45):
        A.cyl(r, H - 0.02, at=(0, y, 0.012), mat="galvanized", n=16, bevel=0.0)
        A.box((0.14, 0.14, 0.012), at=(0, y, 0.006), mat="galvanized", bevel=0.003)
        for sx in (-1, 1):
            for sy in (-1, 1):
                A.cyl(0.008, 0.012, at=(sx * 0.05, y + sy * 0.05, 0.012), mat="steel", n=6, bevel=0.002)
        A.lathe([(0, H - 0.04), (r + 0.006, H - 0.04), (r + 0.006, H - 0.0), (0, H)], at=(0, y, 0), mat="galvanized", n=16)
    A.sweep([(0, -L / 2, H - 0.02), (0, L / 2, H - 0.02)], r=r, n=16, mat="galvanized")
    A.sweep([(0, -L / 2 + 0.03, 0.55), (0, L / 2 - 0.03, 0.55)], r=0.02, n=14, mat="galvanized")
    for y in (-1.45, 0.0, 1.45):
        A.cyl(r + 0.004, 0.05, at=(0, y, 0.525), mat="galvanized", n=16, bevel=0.002)
    A.layout = {"Los": False, "Cover": False}
    A.view = (1.0, -0.55, 0.3)
    A.lens = 45


@asset("Garage_ElevatorDoors", res=2048, collision="Box", edge=0.003, ao_dist=0.2)
def elevator_doors(A):
    """Elevator landing: 3.0 x 3.0 m painted wall module (0.3 m) with a stainless portal, closed
    two-panel centre-opening doors, call buttons and an amber hall lantern above."""
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    T, W, H = 0.3, 3.0, 3.0
    ow, oh = 1.1, 2.15
    fx = T / 2
    # wall around the opening (painted, dark dado)
    side = (W - ow) / 2 - 0.08
    for sy in (-1, 1):
        A.box((T, side, H), at=(0, sy * (W / 2 - side / 2), H / 2), mat="g_wallpaint", bevel=0.004)
    A.box((T, ow + 0.16, H - oh - 0.08), at=(0, 0, oh + 0.08 + (H - oh - 0.08) / 2), mat="g_wallpaint", bevel=0.004)
    # stainless portal (jambs + head, slight projection)
    for sy in (-1, 1):
        A.box((T + 0.04, 0.08, oh + 0.08), at=(0.02, sy * (ow / 2 + 0.04), (oh + 0.08) / 2), mat="steel", bevel=0.004)
    A.box((T + 0.04, ow + 0.16, 0.08), at=(0.02, 0, oh + 0.04), mat="steel", bevel=0.004)
    # door panels (recessed 6 cm), centre meeting line, rubber edges
    for sy in (-1, 1):
        A.box((0.04, ow / 2 - 0.004, oh), at=(fx - 0.06, sy * (ow / 4 + 0.001), oh / 2), mat="steel", bevel=0.002)
        A.box((0.006, 0.006, oh), at=(fx - 0.038, sy * 0.004, oh / 2), mat="rubber", bevel=0.0)
    A.box((0.06, ow, 0.03), at=(fx - 0.06, 0, 0.015), mat="aluminium", bevel=0.002)  # sill
    A.box((0.12, ow + 0.1, 0.012), at=(fx + 0.06, 0, 0.006), mat="aluminium", bevel=0.002)
    # call panel (stainless plate with two buttons) right of the door
    py = -(ow / 2 + 0.32)
    A.box((0.012, 0.12, 0.3), at=(fx + 0.006, py, 1.1), mat="steel", bevel=0.003)
    for z, mat in ((1.17, "g_led_amber"), (1.03, "g_led_amber")):
        A.cyl(0.026, 0.008, at=(fx + 0.012, py, z), axis="X", mat="chrome", n=24, bevel=0.002)
        A.cyl(0.017, 0.006, at=(fx + 0.018, py, z), axis="X", mat=mat, n=24, bevel=0.001, piece="Emissive")
    # hall lantern above the portal
    A.box((0.03, 0.5, 0.16), at=(fx + 0.015, 0, oh + 0.3), mat="steel", bevel=0.004)
    face_quad(A, "g_hall_lantern", (fx + 0.031, 0, oh + 0.3), (0.44, 0.12), "+X", piece="Emissive")
    # floor number plate (blank tintless steel) and a small braille-ish plate
    A.box((0.006, 0.09, 0.09), at=(fx + 0.003, ow / 2 + 0.17, 1.55), mat="steel", bevel=0.002)
    A.view = (1.0, -0.45, 0.2)
    A.lens = 45
    A.preview["Emissive"] = {"glass": {"trans": 0.0, "emit": 10.0, "rough": 0.3}}


# ======================================================================================
# Lighting fixtures
# ======================================================================================
@asset("Garage_LightFluo", res=1024, collision="None", edge=0.002, ao_dist=0.08)
def light_fluo(A):
    """Twin-tube vapour-proof batten, 1.56 m: grey polycarbonate body, stainless clips, opal diffuser
    (the Emissive piece), hung 0.5 m below the soffit on two threaded rods with ceiling plates so the rows
    clear the downstand beams (CeilingMount on the plates)."""
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    L = 1.56
    A.box((L, 0.11, 0.045), at=(0, 0, 0.1), mat="plastic_grey", bevel=0.012, segs=3)
    A.box((L - 0.04, 0.09, 0.03), at=(0, 0, 0.135), mat="plastic_grey", bevel=0.008)
    for sx in (-1, 1):
        A.box((0.03, 0.124, 0.06), at=(sx * (L / 2 - 0.02), 0, 0.075), mat="plastic_grey", bevel=0.01)
    for x in np.linspace(-0.6, 0.6, 5):
        A.box((0.02, 0.13, 0.008), at=(x, 0, 0.078), mat="steel", bevel=0.002)
        for sy in (-1, 1):
            A.box((0.02, 0.006, 0.05), at=(x, sy * 0.064, 0.058), mat="steel", bevel=0.001)
    # opal diffuser: half-round section along X
    prof = [(0.055 * math.cos(a), 0.06 + 0.055 * math.sin(a) - 0.0) for a in np.linspace(math.pi, 2 * math.pi, 17)]
    prof = [(p[0], max(0.006, p[1])) for p in prof]
    pts = prof + [(0.055, 0.075), (-0.055, 0.075)]
    A.prism([(y, z) for (y, z) in pts], L - 0.07, plane="YZ", at=(0, 0, 0), mat="g_opal", bevel=0.0, piece="Emissive", smooth=60)
    # pendant: threaded rods on the end clips, round ceiling plates
    for sx in (-1, 1):
        A.cyl(0.005, 0.49, at=(sx * 0.6, 0, 0.15), mat="steel", n=8, bevel=0.0)
        A.cyl(0.032, 0.012, at=(sx * 0.6, 0, 0.638), mat="steel", n=16, bevel=0.002)
    A.point("CeilingMount", (0, 0, 0.65))
    A.point("Light", (0, 0, -0.02))
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (0.6, -1.0, 0.45)
    A.lens = 50
    A.preview["Emissive"] = {"glass": {"trans": 0.0, "emit": 18.0, "rough": 0.3}}
    A.pv_flip = True


@asset("Garage_LightSodium", res=1024, collision="None", edge=0.003, ao_dist=0.1)
def light_sodium(A):
    """High-pressure-sodium wallpack: dark-bronze die-cast housing on a back plate with a hinged
    cast door frame holding a prismatic refractor (Emissive piece) angled forward and down. Back on the
    wall (WallMount), light thrown forward and down."""
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    W = 0.40
    # back plate + housing (trapezoid side profile: deep at the top, sloping front)
    A.box((0.025, W - 0.04, 0.34), at=(-0.17, 0, 0.19), mat="powder_black", bevel=0.006)
    side = [(-0.16, 0.06), (0.06, 0.06), (0.15, 0.2), (0.12, 0.36), (-0.16, 0.36)]
    A.prism(round_poly(side, 0.02), W, plane="XZ", mat="powder_black", bevel=0.006)
    A.prism(round_poly([(-0.17, 0.355), (0.13, 0.355), (0.12, 0.385), (-0.17, 0.385)], 0.01), W + 0.02, plane="XZ",
            mat="powder_black", bevel=0.005)
    # door frame on the sloped front + refractor
    ax, az = 0.105, 0.13
    tilt = math.degrees(math.atan2(0.14, 0.09))
    fr = A.box((0.03, W - 0.03, 0.2), at=(0, 0, 0), mat="powder_black", bevel=0.006)
    fr.matrix_world = Matrix.Translation((ax, 0, az)) @ Matrix.Rotation(math.radians(tilt - 90), 4, "Y") @ fr.matrix_world
    lens = A.box((0.02, W - 0.07, 0.165), at=(0, 0, 0), mat="g_sodium", bevel=0.004, piece="Emissive")
    lens.matrix_world = Matrix.Translation((ax + 0.012, 0, az)) @ Matrix.Rotation(math.radians(tilt - 90), 4, "Y") @ lens.matrix_world
    for i in range(6):     # prism ribs across the refractor
        rib = A.box((0.008, W - 0.08, 0.008), at=(0, 0, 0), mat="g_sodium", bevel=0.002, piece="Emissive")
        rib.matrix_world = (Matrix.Translation((ax + 0.024, 0, az)) @ Matrix.Rotation(math.radians(tilt - 90), 4, "Y")
                            @ Matrix.Translation((0, 0, -0.065 + i * 0.026)) @ rib.matrix_world)
    # latch, conduit entry on top, photocell
    A.box((0.03, 0.05, 0.02), at=(0.14, 0, 0.065), mat="steel", bevel=0.004)
    A.cyl(0.016, 0.05, at=(-0.12, 0.0, 0.385), mat="galvanized", n=12, bevel=0.002)
    A.cyl(0.02, 0.03, at=(0.02, 0.0, 0.385), mat="plastic_black", n=12, bevel=0.004)
    A.point("WallMount", (-0.183, 0, 0.19))
    A.point("Light", (0.16, 0, 0.1))
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (1.0, -0.8, 0.15)
    A.lens = 60
    A.preview["Emissive"] = {"glass": {"trans": 0.0, "emit": 14.0, "rough": 0.3}}


@asset("Garage_ExitSign", res=1024, collision="None", edge=0.002, ao_dist=0.06)
def exit_sign(A):
    """Double-sided suspended emergency-exit box sign (generic pictogram: arrow, running figure,
    doorway) on a stem; the faces are the Emissive piece."""
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    W, H, D = 0.42, 0.21, 0.06
    A.box((D, W, H), at=(0, 0, H / 2), mat="aluminium", bevel=0.006)
    for sx in (-1, 1):
        A.box((0.004, W - 0.024, H - 0.024), at=(sx * (D / 2 + 0.001), 0, H / 2), mat="plastic_black", bevel=0.0)
        face_quad(A, "g_exit_face", (sx * (D / 2 + 0.0035), 0, H / 2), (W - 0.03, H - 0.03), "+X" if sx > 0 else "-X",
                  piece="Emissive")
    A.cyl(0.012, 0.13, at=(0, 0, H), mat="aluminium", n=12, bevel=0.002)
    A.cyl(0.045, 0.012, at=(0, 0, H + 0.13), mat="aluminium", n=24, bevel=0.003)
    A.point("CeilingMount", (0, 0, H + 0.142))
    A.point("Light", (0.12, 0, H / 2))
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (1.0, -0.6, 0.1)
    A.lens = 70
    A.preview["Emissive"] = {"glass": {"trans": 0.0, "emit": 5.0, "rough": 0.3}}


# ======================================================================================
# Entrance / pedestrian
# ======================================================================================
@asset("Garage_BarrierArm", res=2048, collision="Box", edge=0.004, ao_dist=0.2)
def barrier_arm(A):
    """Automatic parking barrier: yellow steel cabinet with access door and status lamp; 3.6 m white
    boom with red bands (the 'Arm' piece, no collision) pointing to Unreal +Y."""
    A.piece("Arm", "Static", res=1024)
    A.piece("Emissive", "Emissive", res=128, emissive=True)
    A.cur = "Body"
    w, h = 0.36, 1.05
    A.box((w + 0.06, w + 0.06, 0.02), at=(0, 0, 0.01), mat="galvanized", bevel=0.004)
    A.box((w, w, h - 0.06), at=(0, 0, 0.02 + (h - 0.06) / 2), mat="g_cabinet_yellow", bevel=0.01)
    A.box((w + 0.03, w + 0.03, 0.05), at=(0, 0, h - 0.015), mat="g_cabinet_yellow", bevel=0.012)
    A.box((0.008, w - 0.08, h - 0.3), at=(w / 2 + 0.004, 0, 0.5), mat="g_cabinet_yellow", bevel=0.004)
    A.cyl(0.012, 0.01, at=(w / 2 + 0.008, 0.11, 0.6), axis="X", mat="chrome", n=12, bevel=0.002)
    for i in range(5):
        A.box((0.006, 0.12, 0.012), at=(-w / 2 - 0.003, 0, 0.25 + i * 0.03), mat="powder_black", bevel=0.0)
    # status lamp (green, top)
    A.cyl(0.03, 0.02, at=(0.1, 0.1, h + 0.01), mat="powder_black", n=16, bevel=0.003)
    A.sphere(0.024, at=(0.1, 0.1, h + 0.03), mat="g_led_green", seg=16, rings=8, piece="Emissive")
    # hub and boom (Unreal +Y = Blender -Y)
    hz = 0.9
    A.cyl(0.08, 0.06, at=(0.0, -w / 2 - 0.06, hz), axis="Y", mat="steel_dark", n=24, bevel=0.006)
    A.cur = "Arm"
    L = 3.6
    A.box((0.05, 0.3, 0.12), at=(0, -w / 2 - 0.18, hz), mat="steel_dark", bevel=0.006)
    A.box((0.045, L, 0.095), at=(0, -w / 2 - 0.1 - L / 2, hz), mat="g_boom", bevel=0.008)
    A.box((0.06, 0.08, 0.11), at=(0, -w / 2 - 0.1 - L, hz), mat="rubber", bevel=0.015)
    A.box((0.006, L - 0.2, 0.02), at=(0.024, -w / 2 - 0.1 - L / 2, hz - 0.03), mat="rubber", bevel=0.0)
    A.cur = "Body"
    A.point("ArmTip", (0, -w / 2 - 0.1 - L, hz))
    A.layout = {"Core": [[-21.0, -21.0], [21.0, 21.0]]}
    A.view = (1.0, -0.45, 0.35)
    A.lens = 40


@asset("Garage_TicketBooth", res=2048, collision="Box", edge=0.004, ao_dist=0.3)
def ticket_booth(A):
    """Cashier booth for the entrance island: steel frame, grey panels, glazing on all sides with a
    sliding hatch, door at the back (-X), roof with fascia sign, interior counter, stool and monitor."""
    A.piece("Glass", "Glass", res=512, glass=True)
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    D, W, H = 1.6, 1.4, 2.45
    A.box((D + 0.1, W + 0.1, 0.1), at=(0, 0, 0.05), mat="concrete_dark", bevel=0.01)
    z0, zw0, zw1 = 0.1, 1.0, 2.1
    # posts
    for sx in (-1, 1):
        for sy in (-1, 1):
            A.box((0.06, 0.06, H - z0), at=(sx * (D / 2 - 0.03), sy * (W / 2 - 0.03), z0 + (H - z0) / 2), mat="g_booth", bevel=0.006)
    # lower panels (all sides except the door)
    A.box((D - 0.12, 0.04, zw0 - z0), at=(0, W / 2 - 0.02, (z0 + zw0) / 2), mat="g_booth", bevel=0.004)
    A.box((D - 0.12, 0.04, zw0 - z0), at=(0, -W / 2 + 0.02, (z0 + zw0) / 2), mat="g_booth", bevel=0.004)
    A.box((0.04, W - 0.12, zw0 - z0), at=(D / 2 - 0.02, 0, (z0 + zw0) / 2), mat="g_booth", bevel=0.004)
    # door at the back (-X): full-height panel with a small window
    A.box((0.04, W - 0.12, zw1 - z0 - 0.05), at=(-D / 2 + 0.02, 0, z0 + (zw1 - z0 - 0.05) / 2), mat="g_booth", bevel=0.004)
    A.box((0.02, 0.03, 0.12), at=(-D / 2 - 0.01, -0.45, 1.05), mat="steel", bevel=0.003)
    # sill rails + head rails
    for z in (zw0, zw1):
        A.box((D - 0.08, 0.07, 0.04), at=(0, W / 2 - 0.03, z), mat="g_booth", bevel=0.004)
        A.box((D - 0.08, 0.07, 0.04), at=(0, -W / 2 + 0.03, z), mat="g_booth", bevel=0.004)
        A.box((0.07, W - 0.08, 0.04), at=(D / 2 - 0.03, 0, z), mat="g_booth", bevel=0.004)
    # closed frieze between the head rail and the roof
    fz = (zw1 + 0.02 + H) / 2
    fh = H - zw1 - 0.02
    for sy in (-1, 1):
        A.box((D - 0.12, 0.04, fh), at=(0, sy * (W / 2 - 0.02), fz), mat="g_booth", bevel=0.004)
    for sx in (-1, 1):
        A.box((0.04, W - 0.12, fh), at=(sx * (D / 2 - 0.02), 0, fz), mat="g_booth", bevel=0.004)
    # mullions
    for y in (-0.2, 0.25):
        A.box((0.04, 0.04, zw1 - zw0), at=(D / 2 - 0.02, y, (zw0 + zw1) / 2), mat="g_booth", bevel=0.003)
    # glazing (sides + front), a sliding hatch pane on each side, offset
    gz = (zw0 + zw1) / 2
    gh = zw1 - zw0 - 0.04
    for sy in (-1, 1):
        A.box((D - 0.14, 0.008, gh), at=(0.02, sy * (W / 2 - 0.035), gz), mat="glass", bevel=0.0, piece="Glass")
        A.box((0.5, 0.008, 0.6), at=(0.25, sy * (W / 2 - 0.015), zw0 + 0.35), mat="glass", bevel=0.0, piece="Glass")
        A.box((0.5, 0.025, 0.02), at=(0.25, sy * (W / 2 - 0.015), zw0 + 0.66), mat="aluminium", bevel=0.002)
    A.box((0.008, W - 0.14, gh), at=(D / 2 - 0.035, 0, gz), mat="glass", bevel=0.0, piece="Glass")
    # transaction trays
    for sy in (-1, 1):
        A.box((0.3, 0.18, 0.04), at=(0.25, sy * (W / 2 + 0.06), zw0 - 0.02), mat="steel", bevel=0.004)
    # roof + fascia + sign text
    A.box((D + 0.4, W + 0.4, 0.08), at=(0, 0, H + 0.04), mat="g_booth", bevel=0.008)
    A.box((D + 0.44, W + 0.44, 0.03), at=(0, 0, H + 0.095), mat="powder_black", bevel=0.006)
    for sy in (-1, 1):
        A.box((D + 0.42, 0.03, 0.24), at=(0, sy * (W / 2 + 0.21), H - 0.04), mat="powder_black", bevel=0.004)
        A.text("CASHIER", font(), 0.19, 0.006, at=(0.0, sy * (W / 2 + 0.226), H - 0.135),
               rot=(90, 0, 0 if sy < 0 else 180), mat="g_warm_panel", piece="Emissive")
    for sx in (-1, 1):
        A.box((0.03, W + 0.42, 0.24), at=(sx * (D / 2 + 0.21), 0, H - 0.04), mat="powder_black", bevel=0.004)
    # ceiling light panel (Emissive)
    A.box((0.5, 0.3, 0.01), at=(0, 0, H - 0.005), mat="g_warm_panel", bevel=0.0, piece="Emissive")
    # interior: counter, monitor, stool, heater, ticket rolls
    A.box((0.5, W - 0.2, 0.04), at=(D / 2 - 0.3, 0, 0.95), mat="walnut_satin", bevel=0.006)
    A.box((0.12, 0.42, 0.28), at=(D / 2 - 0.42, -0.15, 1.12), mat="plastic_black", bevel=0.01)
    face_quad(A, "g_monitor", (D / 2 - 0.359, -0.15, 1.13), (0.38, 0.22), "+X", piece="Emissive")
    A.cyl(0.02, 0.1, at=(D / 2 - 0.47, -0.15, 0.97), mat="plastic_black", n=12)
    A.cyl(0.18, 0.04, at=(-0.1, 0.1, 0.62), mat="leather_black", n=24, bevel=0.01)
    A.cyl(0.025, 0.55, at=(-0.1, 0.1, 0.1), mat="chrome", n=12)
    A.cyl(0.2, 0.02, at=(-0.1, 0.1, 0.1), mat="chrome", n=24, bevel=0.004)
    A.box((0.25, 0.15, 0.35), at=(-0.5, -0.45, 0.28), mat="paint_white", bevel=0.01)
    A.point("Light", (0, 0, H - 0.2))
    A.view = (1.0, -0.7, 0.32)
    A.lens = 45
    A.preview["Emissive"] = {"glass": {"trans": 0.0, "emit": 6.0, "rough": 0.3}}
    A.preview["Glass"] = {"glass": {"trans": 1.0, "rough": 0.02, "ior": 1.05}}


@asset("Garage_PayMachine", res=2048, collision="Box", edge=0.003, ao_dist=0.2)
def pay_machine(A):
    """Pay-on-foot station: dark blue-grey steel cabinet on a plinth, stainless fascia with LCD,
    keypad, card reader, coin and ticket slots, rain hood. Generic 'P' pictogram, no brand."""
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    D, W, H = 0.42, 0.56, 1.7
    A.box((D + 0.06, W + 0.06, 0.1), at=(0, 0, 0.05), mat="steel_dark", bevel=0.008)
    A.box((D, W, H - 0.1), at=(0, 0, 0.1 + (H - 0.1) / 2), mat="g_pay_body", bevel=0.012)
    # hood
    A.box((D + 0.16, W + 0.08, 0.05), at=(0.06, 0, H + 0.02), mat="g_pay_body", bevel=0.012)
    A.box((0.03, W + 0.08, 0.12), at=(D / 2 + 0.13, 0, H - 0.03), mat="g_pay_body", bevel=0.008)
    # sign panel above the screen (P pictogram)
    face_quad(A, "g_sign_p", (D / 2 + 0.003, 0, 1.52), (0.18, 0.18), "+X", piece="Body")
    # stainless fascia
    A.box((0.012, W - 0.08, 0.85), at=(D / 2 + 0.006, 0, 0.95), mat="steel", bevel=0.004)
    A.box((0.03, 0.3, 0.22), at=(D / 2 + 0.02, 0.06, 1.24), mat="plastic_black", bevel=0.008)
    face_quad(A, "g_pay_screen", (D / 2 + 0.036, 0.06, 1.24), (0.26, 0.19), "+X", piece="Emissive")
    # keypad 3x4
    for i in range(3):
        for j in range(4):
            A.box((0.012, 0.03, 0.026), at=(D / 2 + 0.016, -0.17 + i * 0.038, 1.32 - j * 0.034), mat="steel", bevel=0.003)
    # card reader with green LED, coin slot, ticket slot, receipt + change cup
    A.box((0.05, 0.1, 0.05), at=(D / 2 + 0.03, -0.13, 1.06), mat="plastic_black", bevel=0.008)
    A.box((0.01, 0.02, 0.008), at=(D / 2 + 0.056, -0.1, 1.08), mat="g_led_green", bevel=0.0, piece="Emissive")
    A.box((0.02, 0.012, 0.05), at=(D / 2 + 0.018, 0.12, 1.02), mat="plastic_black", bevel=0.002)
    A.box((0.03, 0.12, 0.02), at=(D / 2 + 0.022, 0.0, 0.92), mat="plastic_black", bevel=0.004)
    A.box((0.04, 0.12, 0.08), at=(D / 2 + 0.03, 0.05, 0.72), mat="steel_dark", bevel=0.01)
    A.box((0.03, 0.1, 0.012), at=(D / 2 + 0.022, -0.12, 0.82), mat="plastic_black", bevel=0.002)
    # yellow help button
    A.cyl(0.022, 0.015, at=(D / 2 + 0.012, 0.19, 1.05), axis="X", mat="paint_yellow", n=20, bevel=0.003)
    # service lock + vents
    A.cyl(0.012, 0.008, at=(D / 2 + 0.003, 0.2, 0.4), axis="X", mat="chrome", n=12)
    for i in range(6):
        A.box((0.006, W - 0.2, 0.01), at=(-D / 2 - 0.003, 0, 0.3 + i * 0.03), mat="powder_black", bevel=0.0)
    A.view = (1.0, -0.7, 0.25)
    A.lens = 50
    A.preview["Emissive"] = {"glass": {"trans": 0.0, "emit": 4.0, "rough": 0.2}}


@asset("Garage_HeightBar", res=1024, collision="None", edge=0.003, ao_dist=0.1)
def height_bar(A):
    """Clearance bar hung on chains across the entrance: striped square tube with a headroom sign."""
    L = 4.0
    A.box((0.1, L, 0.1), at=(0, 0, 0.05), mat="g_hazard_big", bevel=0.008)
    for sy in (-1, 1):
        A.box((0.12, 0.012, 0.12), at=(0, sy * (L / 2 + 0.006), 0.05), mat="g_hazard_big", bevel=0.003)
        y = sy * (L / 2 - 0.25)
        A.box((0.03, 0.03, 0.04), at=(0, y, 0.115), mat="galvanized", bevel=0.004)
        chain(A, (0, y, 0.13), (0, y, 0.72))
        A.cyl(0.035, 0.012, at=(0, y, 0.72), mat="galvanized", n=16, bevel=0.003)
    # sign plate on both faces
    A.box((0.02, 1.6, 0.16), at=(0, 0, 0.05), mat="powder_black", bevel=0.006)
    for sx in (-1, 1):
        A.text("MAX HEADROOM  2.20 m", font(), 0.085, 0.004, at=(sx * 0.0115, 0, 0.012),
               rot=(90, 0, 90 if sx > 0 else -90), mat="paint_white", spacing=1.05)
    A.point("CeilingMount", (0, 0, 0.732))
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (1.0, -0.5, 0.15)
    A.lens = 40


# ======================================================================================
# Cover / dressing
# ======================================================================================
@asset("Garage_BlockPallet", res=2048, collision="Box", edge=0.004, ao_dist=0.25)
def block_pallet(A):
    """Timber pallet stacked with concrete masonry units (five courses, interlocked), two straps."""
    rng = random.Random(17)
    # pallet
    for y in (-0.45, 0.0, 0.45):
        A.box((1.2, 0.1, 0.1), at=(0, y, 0.05), mat="pine", bevel=0.004, gax=0)
    for i in range(7):
        x = -0.55 + i * (1.1 / 6)
        A.box((0.12, 1.0, 0.022), at=(x, 0, 0.111), mat="pine", bevel=0.003, gax=1)
    z = 0.122
    bl, bw, bh = 0.39, 0.19, 0.19
    for c in range(5):
        along_x = c % 2 == 0
        for i in range(3 if along_x else 6):
            for j in range(5 if along_x else 2):
                if along_x:
                    cx, cy, sx, sy = -0.39 + i * 0.395, -0.4 + j * 0.2, bl, bw
                else:
                    cx, cy, sx, sy = -0.5 + i * 0.2, -0.2 + j * 0.395, bw, bl
                if c == 4 and rng.random() < 0.25:
                    continue
                ox, oy = cx + rng.uniform(-0.006, 0.006), cy + rng.uniform(-0.006, 0.006)
                A.box((sx - 0.004, sy - 0.004, bh - 0.002), at=(ox, oy, z + bh / 2),
                      rot=(0, 0, rng.uniform(-1.2, 1.2)), mat="g_cmu", bevel=0.006, segs=1)
                if c == 4:   # hollow cores visible on the top course
                    for k in (-1, 1):
                        hx, hy = (k * 0.095, 0.0) if along_x else (0.0, k * 0.095)
                        A.box((0.13 if along_x else 0.11, 0.11 if along_x else 0.13, 0.004), at=(ox + hx, oy + hy, z + bh - 0.0005),
                              mat="rubber", bevel=0.0)
        z += bh
    # straps over the top
    zt = z
    for x in (-0.3, 0.3):
        A.sweep([(x, -0.53, 0.12), (x, -0.53, zt + 0.004), (x, 0.53, zt + 0.004), (x, 0.53, 0.12)],
                prof=rrect_pts(0.03, 0.0025, 0.0008), mat="g_strap", smooth=30)
    A.view = (1.0, -0.65, 0.42)
    A.lens = 50


@asset("Garage_Cone", res=1024, collision="None", edge=0.003, ao_dist=0.1)
def cone(A):
    """Traffic cone, 0.7 m: square base, two retro-reflective collars."""
    A.box((0.36, 0.36, 0.035), at=(0, 0, 0.0175), mat="rubber", bevel=0.012, segs=2)
    prof = [(0, 0.03), (0.155, 0.03), (0.15, 0.06), (0.03, 0.68), (0.024, 0.7), (0, 0.7)]
    A.lathe(prof, mat="g_cone", n=40, smooth=50)
    for z0, z1 in ((0.3, 0.42), (0.5, 0.58)):
        r0 = 0.15 - (z0 - 0.06) * (0.12 / 0.62)
        r1 = 0.15 - (z1 - 0.06) * (0.12 / 0.62)
        A.lathe([(r0 + 0.002, z0), (r1 + 0.002, z1)], mat="g_reflect", n=40, cap=False, smooth=50)
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (1.0, -0.6, 0.35)
    A.lens = 70


@asset("Garage_Drain", res=1024, collision="None", edge=0.002, ao_dist=0.05)
def drain(A):
    """Floor-flush trench drain, 1.5 m: cast frame with a slotted grate (top at floor level)."""
    L, W = 1.5, 0.22
    A.box((L, W, 0.02), at=(0, 0, -0.008), mat="cast_iron", bevel=0.003)
    A.box((L - 0.04, W - 0.05, 0.004), at=(0, 0, 0.0005), mat="rubber", bevel=0.0)
    for i in range(30):
        x = -L / 2 + 0.04 + i * (L - 0.08) / 29
        A.box((0.022, W - 0.05, 0.006), at=(x, 0, 0.0), mat="cast_iron", bevel=0.001)
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (0.8, -0.8, 0.9)
    A.lens = 60


@asset("Garage_PipeRun", res=2048, collision="None", edge=0.003, ao_dist=0.15)
def pipe_run(A):
    """6 m soffit services run (tiles end to end): red sprinkler main with grooved couplings, a branch
    line with two pendant heads, three grey conduits on strut, galvanised ladder tray with cables,
    threaded-rod hangers. CeilingMount on top."""
    L, Ht = 6.0, 0.55
    # hangers every 3 m
    for x in (-1.5, 1.5):
        A.cyl(0.006, Ht - 0.18, at=(x, 0.0, 0.18), mat="galvanized", n=8, bevel=0.0)
        A.box((0.04, 1.0, 0.04), at=(x, 0.0, 0.33), mat="galvanized", bevel=0.003)          # strut channel
        for y in (-0.42, 0.42):
            A.cyl(0.006, Ht - 0.33, at=(x, y, 0.33), mat="galvanized", n=8, bevel=0.0)
        A.sweep([(x, 0.0 + 0.056 * math.cos(a), 0.24 - 0.056 * math.sin(a)) for a in np.linspace(0, math.pi, 12)],
                r=0.005, n=6, mat="galvanized")
        A.cyl(0.03, 0.01, at=(x, 0.0, Ht - 0.01), mat="galvanized", n=12, bevel=0.002)
    # sprinkler main (Unreal-Y centred), couplings at the ends and mid
    A.cyl(0.055, L, at=(-L / 2, 0.0, 0.24), axis="X", mat="g_pipe_red", n=28, bevel=0.0)
    for x in (-L / 2 + 0.03, 0.0, L / 2 - 0.03):
        A.cyl(0.065, 0.06, at=(x - 0.03, 0.0, 0.24), axis="X", mat="g_pipe_red", n=28, bevel=0.006)
        for a in (0, math.pi):
            A.cyl(0.008, 0.04, at=(x, 0.07 * math.cos(a), 0.24 + 0.07 * math.sin(a)), axis="Y", mat="steel", n=6)
    # branch tee + pendant heads
    A.cyl(0.03, 0.7, at=(0.6, 0.0, 0.24), axis="Y", mat="g_pipe_red", n=16, bevel=0.0)
    for y in (0.35, 0.68):
        A.cyl(0.018, 0.14, at=(0.6, y, 0.1), mat="g_pipe_red", n=12)
        A.cyl(0.012, 0.03, at=(0.6, y, 0.07), mat="brass", n=12)
        A.cyl(0.028, 0.004, at=(0.6, y, 0.066), mat="brass", n=16)
    # conduits on the strut
    for k in range(3):
        A.cyl(0.013, L, at=(-L / 2, -0.25 - k * 0.035, 0.36), axis="X", mat="g_conduit", n=12, bevel=0.0)
    # ladder tray with cables
    yt = 0.3
    for sy in (-1, 1):
        A.box((L, 0.004, 0.08), at=(0, yt + sy * 0.15, 0.39), mat="galvanized", bevel=0.0)
    for i in range(20):
        A.box((0.025, 0.3, 0.012), at=(-L / 2 + 0.15 + i * (L - 0.3) / 19, yt, 0.356), mat="galvanized", bevel=0.0)
    rng = random.Random(4)
    for k in range(7):
        y = yt - 0.12 + k * 0.04
        pts = [(-L / 2, y, 0.375 + rng.uniform(0, 0.01))]
        for x in np.linspace(-L / 2 + 0.75, L / 2 - 0.75, 5):
            pts.append((x, y + rng.uniform(-0.012, 0.012), 0.376 + rng.uniform(0, 0.02)))
        pts.append((L / 2, y, 0.375))
        A.sweep(catmull(pts, 4), r=0.009 + 0.004 * (k % 3), n=8, mat="plastic_black" if k % 3 else "g_insul")
    A.point("CeilingMount", (0, 0, Ht))
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (0.9, -0.8, 0.45)
    A.lens = 35
    A.pv_flip = True


@asset("Garage_Scaffold", res=2048, collision="Complex", edge=0.003, ao_dist=0.2)
def scaffold(A):
    """One bay of frame scaffold for soffit repairs (fits under a 3.0 m slab): two H-frames on base
    jacks and sole boards, cross braces, timber deck at 1.8 m with toe boards, guard rail at 2.8 m,
    a blue tarp tied on the back."""
    Lx, Wy, Hd = 2.5, 1.0, 1.8
    r = 0.024
    rng = random.Random(8)
    for sx in (-1, 1):
        x = sx * Lx / 2
        A.box((0.3, Wy + 0.25, 0.04), at=(x, 0, 0.02), mat="pine", bevel=0.004, gax=1)
        for sy in (-1, 1):
            y = sy * Wy / 2
            A.box((0.15, 0.15, 0.006), at=(x, y, 0.043), mat="galvanized", bevel=0.002)
            A.cyl(0.017, 0.2, at=(x, y, 0.046), mat="steel_dark", n=10)
            A.cyl(r, Hd + 1.0 - 0.25, at=(x, y, 0.25), mat="galvanized", n=14, bevel=0.0)
        for z in (0.3, 1.0, Hd - 0.05, Hd + 1.0 - 0.02):
            A.sweep([(x, -Wy / 2, z), (x, Wy / 2, z)], r=r * 0.85, n=12, mat="galvanized")
        A.sweep([(x, -Wy / 2, 0.35), (x, Wy / 2, 1.0)], r=0.016, n=10, mat="galvanized")
    # cross braces (both long sides)
    for sy in (-1, 1):
        y = sy * (Wy / 2 + 0.03)
        A.sweep([(-Lx / 2, y, 0.3), (Lx / 2, y, Hd - 0.1)], r=0.014, n=10, mat="galvanized")
        A.sweep([(-Lx / 2, y, Hd - 0.1), (Lx / 2, y, 0.3)], r=0.014, n=10, mat="galvanized")
        # guard rails above the deck
        for z in (Hd + 0.5, Hd + 1.0 - 0.02):
            A.sweep([(-Lx / 2, y, z), (Lx / 2, y, z)], r=0.02, n=12, mat="galvanized")
    # deck boards + toe boards
    for i in range(4):
        y = -Wy / 2 + 0.13 + i * 0.245
        A.box((Lx + 0.25, 0.225, 0.038), at=(rng.uniform(-0.03, 0.03), y, Hd + 0.02), mat="pine", bevel=0.004, gax=0)
    for sy in (-1, 1):
        A.box((Lx, 0.025, 0.15), at=(0, sy * (Wy / 2 + 0.06), Hd + 0.11), mat="pine", bevel=0.003, gax=0)
    # tarp on the back side (tied at the rails, sagging)
    def tarp(u, v):
        x = -Lx / 2 + Lx * u
        z = 0.35 + (Hd + 0.95 - 0.35) * v
        y = Wy / 2 + 0.07 + 0.05 * math.sin(math.pi * u) * math.sin(math.pi * v) + 0.01 * math.sin(u * 23 + v * 7)
        return (x, y, z)
    A.grid(tarp, 24, 16, mat="g_tarp")
    # buckets / tools on the deck
    A.cyl(0.14, 0.28, at=(0.6, -0.15, Hd + 0.04), mat="plastic_black", n=24, r2=0.16, bevel=0.004)
    A.box((0.45, 0.2, 0.12), at=(-0.5, 0.1, Hd + 0.1), mat="paint_red", bevel=0.01)
    A.layout = {"Los": False, "Cover": False}
    A.view = (1.0, -0.75, 0.3)
    A.lens = 40


@asset("Garage_MaintCage", res=2048, collision="Complex", edge=0.003, ao_dist=0.25)
def maint_cage(A):
    """Welded-mesh maintenance cage (3.0 x 2.0 x 2.4 m) with a padlocked door: shelving with paint
    tins, spare cones, a mop bucket, a folded step ladder and a box of fluorescent tubes inside."""
    Lx, Wy, H = 3.0, 2.0, 2.4
    t = 0.04
    for sx in (-1, 1):
        for sy in (-1, 1):
            A.box((t, t, H), at=(sx * (Lx / 2 - t / 2), sy * (Wy / 2 - t / 2), H / 2), mat="g_shelf", bevel=0.004)
    for z in (0.05, H - 0.02):
        for sy in (-1, 1):
            A.box((Lx, t, t), at=(0, sy * (Wy / 2 - t / 2), z), mat="g_shelf", bevel=0.004)
        for sx in (-1, 1):
            A.box((t, Wy, t), at=(sx * (Lx / 2 - t / 2), 0, z), mat="g_shelf", bevel=0.004)

    def mesh_panel(axis, fixed, a0, a1, z0, z1, pitch_a=0.05, pitch_z=0.1, skip=None):
        w = 0.004
        n_a = int((a1 - a0) / pitch_a)
        for i in range(1, n_a):
            a = a0 + i * pitch_a
            if skip and skip[0] < a < skip[1]:
                continue
            if axis == "x":
                A.box((w, w, z1 - z0), at=(a, fixed, (z0 + z1) / 2), mat="galvanized", bevel=0)
            else:
                A.box((w, w, z1 - z0), at=(fixed, a, (z0 + z1) / 2), mat="galvanized", bevel=0)
        n_z = int((z1 - z0) / pitch_z)
        for j in range(1, n_z):
            z = z0 + j * pitch_z
            if axis == "x":
                A.box((a1 - a0, w, w), at=((a0 + a1) / 2, fixed + 0.004, z), mat="galvanized", bevel=0)
            else:
                A.box((w, a1 - a0, w), at=(fixed + 0.004, (a0 + a1) / 2, z), mat="galvanized", bevel=0)
    # long sides (+/-Y), back (-X) and the front (+X) with a door opening in the middle
    for sy in (-1, 1):
        mesh_panel("x", sy * (Wy / 2 - t / 2), -Lx / 2 + t, Lx / 2 - t, 0.07, H - 0.04)
    mesh_panel("y", -Lx / 2 + t / 2, -Wy / 2 + t, Wy / 2 - t, 0.07, H - 0.04)
    dw = 0.9
    mesh_panel("y", Lx / 2 - t / 2, -Wy / 2 + t, -dw / 2 - 0.03, 0.07, H - 0.04)
    mesh_panel("y", Lx / 2 - t / 2, dw / 2 + 0.03, Wy / 2 - t, 0.07, H - 0.04)
    # door (slightly ajar? closed, padlocked)
    for y in (-dw / 2, dw / 2):
        A.box((t, t, H - 0.1), at=(Lx / 2 - t / 2, y, (H - 0.1) / 2 + 0.05), mat="g_shelf", bevel=0.004)
    for z in (0.12, 1.1, H - 0.2):
        A.box((t * 0.8, dw, t * 0.8), at=(Lx / 2 + 0.02, 0, z), mat="g_shelf", bevel=0.003)
    mesh_panel("y", Lx / 2 + 0.02, -dw / 2 + 0.02, dw / 2 - 0.02, 0.14, H - 0.22)
    A.box((0.02, 0.05, 0.06), at=(Lx / 2 + 0.05, dw / 2 - 0.05, 1.1), mat="brass_aged", bevel=0.005)
    A.sweep(catmull([(Lx / 2 + 0.05, dw / 2 - 0.065, 1.13), (Lx / 2 + 0.05, dw / 2 - 0.05, 1.16), (Lx / 2 + 0.05, dw / 2 - 0.035, 1.13)], 4),
            r=0.004, n=8, mat="steel")
    # shelving along the back
    for z in (0.3, 0.9, 1.5):
        A.box((0.5, 1.7, 0.025), at=(-Lx / 2 + 0.32, 0, z), mat="g_shelf", bevel=0.004)
    for sy in (-1, 1):
        for sx in (0.08, 0.56):
            A.box((0.03, 0.03, 1.8), at=(-Lx / 2 + sx, sy * 0.83, 0.9), mat="g_shelf", bevel=0.003)
    rng = random.Random(21)
    cols = ["paint_white", "paint_yellow", "paint_red", "g_shelf", "paint_white"]
    for z in (0.3125, 0.9125, 1.5125):
        for k in range(7):
            if rng.random() < 0.2:
                continue
            y = -0.75 + k * 0.24 + rng.uniform(-0.03, 0.03)
            A.cyl(0.085, 0.2, at=(-Lx / 2 + 0.3 + rng.uniform(-0.06, 0.06), y, z), mat=cols[k % 5], n=24, bevel=0.004)
    # spare cones stacked, mop bucket, step ladder, tube box
    for k in range(3):
        A.lathe([(0, 0.03 + k * 0.05), (0.155, 0.03 + k * 0.05), (0.03, 0.68 + k * 0.05), (0, 0.7 + k * 0.05)],
                at=(0.9, -0.55, 0), mat="g_cone", n=32, smooth=50)
    A.box((0.36, 0.36, 0.035), at=(0.9, -0.55, 0.0175), mat="rubber", bevel=0.01)
    A.cyl(0.18, 0.3, at=(0.4, 0.55, 0.06), mat="paint_yellow", n=28, r2=0.2, bevel=0.006)
    for x in (0.25, 0.55):
        A.cyl(0.04, 0.06, at=(x, 0.55, 0.0), mat="plastic_black", n=12)
    A.cyl(0.012, 1.2, at=(0.45, 0.6, 0.1), mat="aluminium", n=8, rot=(12, 0, 0))
    for sy in (-1, 1):
        A.box((0.04, 0.02, 1.6), at=(1.2, 0.2 + sy * 0.22, 0.85), rot=(0, -8, 0), mat="aluminium", bevel=0.003)
    for i in range(5):
        A.box((0.04, 0.44, 0.02), at=(1.2 - 0.035 * (i - 2) * 0.3, 0.2, 0.3 + i * 0.3), mat="aluminium", bevel=0.002)
    A.box((1.6, 0.18, 0.12), at=(-0.2, -0.8, 0.06), mat="g_booth", bevel=0.01)
    A.layout = {"Los": False, "Cover": False}
    A.view = (1.0, -0.65, 0.35)
    A.lens = 40


@asset("Garage_RoofHVAC", res=2048, collision="Box", edge=0.005, ao_dist=0.3)
def roof_hvac(A):
    """Rooftop condensing unit, 2.4 x 1.4 x 1.75 m: galvanised base rails, weathered grey casing with
    louvred coil sides, two top fan guards with blades, insulated copper lines and a disconnect box."""
    Lx, Wy, H = 2.4, 1.4, 1.75
    for sy in (-1, 1):
        A.box((Lx + 0.1, 0.1, 0.12), at=(0, sy * (Wy / 2 - 0.1), 0.06), mat="galvanized", bevel=0.006)
    A.box((Lx, Wy, H - 0.25), at=(0, 0, 0.12 + (H - 0.25) / 2), mat="g_hvac", bevel=0.014)
    A.box((Lx + 0.03, Wy + 0.03, 0.08), at=(0, 0, H - 0.09), mat="g_hvac", bevel=0.012)
    # louvres on the long sides
    for sy in (-1, 1):
        for i in range(22):
            z = 0.28 + i * 0.05
            A.box((Lx - 0.3, 0.03, 0.012), at=(0, sy * (Wy / 2 + 0.008), z), rot=(sy * 35, 0, 0), mat="g_hvac", bevel=0.0)
        A.box((Lx - 0.28, 0.006, 1.12), at=(0, sy * (Wy / 2 - 0.004), 0.83), mat="powder_black", bevel=0.0)
    # fan guards + blades on top
    for x in (-0.6, 0.6):
        A.cyl(0.5, 0.06, at=(x, 0, H - 0.05), mat="powder_black", n=40, bevel=0.006)
        for rr in (0.15, 0.27, 0.39, 0.49):
            A.sweep([(x + rr * math.cos(a), rr * math.sin(a), H + 0.02) for a in np.linspace(0, 2 * math.pi, 41)[:-1]],
                    r=0.004, n=6, mat="steel_dark", closed=True)
        for k in range(8):
            a = k * math.pi / 4
            A.sweep([(x, 0, H + 0.02), (x + 0.49 * math.cos(a), 0.49 * math.sin(a), H + 0.02)], r=0.004, n=6, mat="steel_dark")
        for k in range(4):
            a = k * math.pi / 2 + 0.3
            A.box((0.36, 0.12, 0.008), at=(x + 0.2 * math.cos(a), 0.2 * math.sin(a), H - 0.03), rot=(25, 0, math.degrees(a)),
                  mat="steel_dark", bevel=0.003)
        A.cyl(0.07, 0.06, at=(x, 0, H - 0.06), mat="steel_dark", n=20)
    # service panel, disconnect, refrigerant lines
    A.box((0.01, 0.5, 0.7), at=(Lx / 2 + 0.005, -0.2, 0.75), mat="g_hvac", bevel=0.004)
    for z in (0.5, 1.0):
        for y in (-0.42, 0.02):
            A.cyl(0.008, 0.008, at=(Lx / 2 + 0.01, y, z), axis="X", mat="steel", n=8)
    A.box((0.12, 0.22, 0.3), at=(Lx / 2 + 0.07, 0.42, 1.0), mat="g_shelf", bevel=0.01)
    A.cyl(0.015, 0.75, at=(Lx / 2 + 0.07, 0.42, 0.12), mat="g_conduit", n=10)
    for k, r_ in enumerate((0.028, 0.018)):
        y = 0.25 + k * 0.08
        A.sweep(catmull([(Lx / 2 - 0.05, y, 0.55), (Lx / 2 + 0.15, y, 0.55), (Lx / 2 + 0.3, y, 0.3), (Lx / 2 + 0.3, y, 0.0)], 6),
                r=r_, n=12, mat="g_insul" if k == 0 else "g_copper")
    A.view = (1.0, -0.7, 0.45)
    A.lens = 45
