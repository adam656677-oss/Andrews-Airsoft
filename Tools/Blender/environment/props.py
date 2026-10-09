"""Field props -> SourceAssets/Props/<Id>/  (baked unique texture sets)

usage: python props.py [--res 4096|2048|1024] [--no-render] [-- Id ...]

Hero props bake at --res, small props at --res/2. Each piece's slots are
layered recipe shaders over the tileable library (real-world 'UVTex'),
with curvature edge wear, cavity dirt and ground grime, baked to
T_<Id>_<Piece>_BC/N/ORM(/M).png on a smart-UV layout. Trees use MI_Bark for
trunks (1 UV = 2 m) and a generated alpha-masked leaf atlas.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from envlib import bake, bl, geo, shapes, tex  # noqa: E402
from envlib.geo import Builder, box_bm, cyl_bm, mtx  # noqa: E402

CAT = 'Props'
OUT = os.path.join(bl.SA, CAT)
SCRATCH = os.environ.get('ENV_SCRATCH', os.path.join(__import__('tempfile').gettempdir(), 'airsoft_env_cache'))

# ----------------------------------------------------------------------------
# recipes
# ----------------------------------------------------------------------------
R = {
    'burlap': dict(base='Burlap', dirt=0.8, ground=0.3, ground_col=(0.22, 0.17, 0.11), breakup=0.4, breakup_scale=2.5,
                   bump=0.25, bump_scale=10.0, bump_dist=0.004, ao_dist=0.15, edge=0.15),
    'rubber': dict(base='Rubber', dirt=0.6, ground=0.25, edge=0.35, edge_col=(0.16, 0.16, 0.15), ao_dist=0.1),
    'timber': dict(base='Timber', dirt=0.8, edge=0.3, ground=0.2, breakup=0.3),
    'timber_new': dict(base='Timber', tint=(1.25, 1.12, 0.95), hue=(0.8, 1.05), dirt=0.6, edge=0.3, ground=0.12),
    'ply': dict(base='Plywood', dirt=0.6, edge=0.35, ground=0.35, streak=0.2, streak_col=(0.22, 0.17, 0.11)),
    'ply_od': dict(base='PlywoodPainted', dirt=0.6, edge=0.25, ground=0.35, streak=0.25,
                   streak_col=(0.2, 0.17, 0.1), edge_col=(0.55, 0.45, 0.3)),
    'steel': dict(base='PaintedSteel', dirt=0.6, edge=0.45, ground=0.2, streak=0.25),
    'steel_dark': dict(base='PaintedSteel', tint=(0.45, 0.45, 0.45), hue=(0.3, 0.8), dirt=0.6, edge=0.5, ground=0.2),
    'galv': dict(base='Brass', hue=(0.0, 0.85), metal=1.0, dirt=0.6, edge=0.2, rough_add=0.15),
    'rust': dict(base='CorrodedMetal', dirt=0.6, edge=0.25, ground=0.3),
    'straw': dict(base='Straw', tint=(0.82, 0.74, 0.56), dirt=0.85, ground=0.3, ground_col=(0.2, 0.16, 0.1),
                  breakup=0.45, breakup_scale=2.0, bump=0.3, bump_scale=40.0),
    'granite': dict(base='Granite', tint=(0.8, 0.78, 0.74), dirt=0.9, edge=0.45, ground=0.3, moss=1.0, ao_dist=0.4,
                    breakup=0.5, breakup_scale=1.5, streak=0.35, streak_col=(0.1, 0.095, 0.085), streak_scale=2.0,
                    bump=0.25, bump_scale=6.0, bump_dist=0.01),
    'concrete': dict(base='Concrete', dirt=0.7, edge=0.35, ground=0.2),
}


def drum_paint():
    return dict(base='PaintedSteel', paint=(0.88, 0.88, 0.87), chip=0.9, chip_scale=7.0, chip_global=0.22,
                under='CorrodedMetal', paint_rough=0.5, edge=0.25, dirt=0.9, ground=0.3, streak=0.8,
                streak_col=(0.28, 0.13, 0.05), mask=(1, 0, 0), mask_paint_only=True, bump=0.15, bump_scale=6.0,
                bump_dist=0.003, edge_r=0.012)


def ammo_paint():
    return dict(base='Timber', paint=(0.27, 0.29, 0.17), chip=0.6, chip_scale=10.0, paint_rough=0.65, edge=0.25,
                dirt=0.7, ground=0.2, under='Timber')


# ----------------------------------------------------------------------------
# geometry helpers
# ----------------------------------------------------------------------------
def lathe(profile, n=64, axis='z'):
    """Revolve [(r, z), ...] around Z."""
    bm = bmesh.new()
    rings = []
    for j in range(n):
        a = j / n * math.tau
        rings.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z)) for (r, z) in profile])
    for j in range(n):
        A = rings[j]
        Bv = rings[(j + 1) % n]
        for i in range(len(profile) - 1):
            try:
                bm.faces.new((A[i], Bv[i], Bv[i + 1], A[i + 1]))
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def extrude_poly(pts, thick, bevel=0.004):
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, -thick / 2)) for x, y in pts]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, thick), verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    geo._bevel(bm, bevel, 2, angle=0.6)
    return bm


def displace_obj(obj, amp, freq, oct=4, seed=0, mask=None):
    me = obj.data
    P = geo.verts_np(me)
    N = geo.normals_np(me)
    d = geo.fbm3(P * freq, 1.0, oct, 0.5, seed) * amp
    if mask is not None:
        d = d * mask(P)
    geo.set_verts(me, P + N * d[:, None])


# ----------------------------------------------------------------------------
# sandbags
# ----------------------------------------------------------------------------
def sandbag_run(B, rng, y0, y1, x, z, rot, k0, bagL=0.56, slump=0.0):
    """Bags laid along Y, tightly butted (step ~0.5 m, ends overlap)."""
    step = 0.5
    n = max(1, int(round((y1 - y0) / step)))
    step = (y1 - y0) / n
    k = k0
    for i in range(n):
        y = y0 + step * (i + 0.5)
        bm = shapes.sandbag_bm(rng.integers(1e6), cuts=11, slump=slump + rng.uniform(-0.005, 0.01))
        flip = rng.random() < 0.5
        M = mtx((x + rng.uniform(-0.015, 0.015), y, z),
                (rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03), rot + math.pi / 2 + (math.pi if flip else 0) + rng.uniform(-0.05, 0.05)))
        B.add(bm, 'burlap', M)
        k += 1
    return k


def p_SandbagWall_3m():
    rng = np.random.default_rng(31)
    B = Builder()
    k = 0
    zc = 0.0
    for c in range(8):
        off = 0.25 if c % 2 else 0.0
        sl = 0.022 if c > 0 else 0.0
        if c < 6:
            for x in (-0.165, 0.165):
                k = sandbag_run(B, rng, -1.5 + off, 1.5 - off, x, zc, 0, k, slump=sl)
        else:
            k = sandbag_run(B, rng, -1.4 + off, 1.4 - off, rng.uniform(-0.03, 0.03), zc, 0, k, slump=sl)
        zc += 0.112
    return [('Body', 'Body', B.finish('SandbagWall_3m_Body'), {'burlap': R['burlap']})], 'hero', 'Complex'


def sandbag_run_x(B, rng, x0, x1, y, z, bagL=0.56, slump=0.02):
    n = max(1, int(round((x1 - x0) / 0.5)))
    step = (x1 - x0) / n
    for i in range(n):
        x = x0 + step * (i + 0.5)
        bm = shapes.sandbag_bm(rng.integers(1e6), cuts=11, slump=(slump if z > 0.01 else 0) + rng.uniform(-0.005, 0.01))
        flip = rng.random() < 0.5
        M = mtx((x, y + rng.uniform(-0.015, 0.015), z),
                (rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03), (math.pi if flip else 0) + rng.uniform(-0.06, 0.06)))
        B.add(bm, 'burlap', M)


def p_SandbagCorner():
    rng = np.random.default_rng(32)
    B = Builder()
    zc = 0.0
    for c in range(8):
        two = c < 6
        rows = (0.435, 0.765) if two else (0.6,)
        if c % 2 == 0:
            for x in rows:
                sandbag_run(B, rng, -0.9, 0.95, x, zc, 0, 0, slump=0.022 if c else 0)
            for y in rows:
                sandbag_run_x(B, rng, -0.9, 0.27, y, zc)
        else:
            for y in rows:
                sandbag_run_x(B, rng, -0.9 + 0.25, 0.95, y, zc)
            for x in rows:
                sandbag_run(B, rng, -0.9 + 0.25, 0.27, x, zc, 0, 0, slump=0.022)
        zc += 0.112
    return [('Body', 'Body', B.finish('SandbagCorner_Body'), {'burlap': R['burlap']})], 'hero', 'Complex'


# ----------------------------------------------------------------------------
# tyres
# ----------------------------------------------------------------------------
def tire_bm(seed=0, R0=0.33, w=0.21, rim=0.2, nseg=256, nprof=44):
    rng = np.random.default_rng(seed)
    prof = []
    # cross-section (r, z) from inner bead over the tread to the other bead
    for i in range(nprof + 1):
        t = i / nprof
        a = (t - 0.5) * math.pi * 1.15
        rr = rim + (R0 - rim) * (0.5 + 0.5 * math.cos(a) ** 0.6 * (1 if abs(a) < math.pi / 2 else -0.0))
        z = w / 2 * math.sin(a) * 1.05
        if abs(a) > math.pi / 2:
            rr = rim + (R0 - rim) * 0.02 * (1 - (abs(a) - math.pi / 2) * 2)
        prof.append((max(rim, rr), z))
    bm = lathe(prof, nseg)
    # tread grooves: push outer verts in by a pattern
    for v in bm.verts:
        r = math.hypot(v.co.x, v.co.y)
        if r > R0 - 0.02:
            ang = math.atan2(v.co.y, v.co.x)
            z = v.co.z
            blk = (math.sin(ang * 40 + (z / w) * 6.0 * (1 if z > 0 else -1)) > 0.55)
            groove = abs(z) < 0.012 or abs(abs(z) - w * 0.28) < 0.008 or blk
            if groove:
                s = (r - 0.008) / r
                v.co.x *= s
                v.co.y *= s
    bm.normal_update()
    return bm


def p_Tire():
    B = Builder()
    B.add(tire_bm(1), 'rubber', mtx((0, 0, 0.105)), grain='x')
    return [('Body', 'Body', B.finish('Tire_Body'), {'rubber': R['rubber']})], 'small', 'Convex'


def p_TireStack():
    rng = random.Random(3)
    B = Builder()
    for i in range(3):
        B.add(tire_bm(i + 1), 'rubber', mtx((rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03), 0.105 + i * 0.205),
                                            (rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02), rng.uniform(0, 6))))
    return [('Body', 'Body', B.finish('TireStack_Body'), {'rubber': R['rubber']})], 'small', 'Convex'


# ----------------------------------------------------------------------------
# wood
# ----------------------------------------------------------------------------
def p_CableSpool():
    rng = random.Random(5)
    B = Builder()
    Rf = 1.0
    th = 0.055
    hub = 0.4
    span = 1.0
    # flanges made of planks clipped to the circle, standing (axis along Y)
    for sy in (-1, 1):
        y = sy * (span / 2 + th / 2)
        n = 7
        pw = 2 * Rf / n
        for i in range(n):
            x0 = -Rf + i * pw + 0.004
            x1 = x0 + pw - 0.008
            pts = []
            for k in range(9):
                x = x0 + (x1 - x0) * k / 8
                pts.append((x, math.sqrt(max(Rf * Rf - x * x, 1e-6))))
            for k in range(9):
                x = x1 - (x1 - x0) * k / 8
                pts.append((x, -math.sqrt(max(Rf * Rf - x * x, 1e-6))))
            bm = extrude_poly(pts, th, 0.006)
            M = mtx((0, y, Rf), (math.pi / 2, 0, 0))
            B.add(bm, 'timber', M, grain='y')
        # cross battens on the outside
        for a in (0.0, math.pi / 2):
            B.add(box_bm((2 * Rf * 0.92, 0.12, 0.05), 0.006, 2), 'timber',
                  mtx((0, y + sy * (th / 2 + 0.025), Rf), (0, a, 0)), grain='x')
        # tie-rod nuts
        for k in range(4):
            a = k * math.pi / 2 + math.pi / 4
            p = (math.cos(a) * 0.55, y + sy * (th / 2 + 0.01), Rf + math.sin(a) * 0.55)
            B.add(cyl_bm(0.03, 0.025, 6, 0.004, 1), 'steel_dark', mtx(p, (math.pi / 2, 0, 0)))
        B.add(cyl_bm(0.06, 0.03, 24, 0.004, 1), 'steel_dark', mtx((0, y + sy * (th / 2 + 0.012), Rf), (math.pi / 2, 0, 0)))
    # hub lagging (staves)
    n = 22
    for i in range(n):
        a = i / n * math.tau
        p = (math.cos(a) * hub, 0, Rf + math.sin(a) * hub)
        B.add(box_bm((0.05, span, 2 * hub * math.sin(math.pi / n) * 0.96), 0.006, 2), 'timber',
              mtx(p, (0, -a, 0)), grain='y')
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        B.between('steel_dark', (math.cos(a) * 0.55, -span / 2 - th - 0.02, Rf + math.sin(a) * 0.55),
                  (math.cos(a) * 0.55, span / 2 + th + 0.02, Rf + math.sin(a) * 0.55), 0.012, n=8)
    return [('Body', 'Body', B.finish('CableSpool_Body'), {'timber': R['timber'], 'steel_dark': R['steel_dark']})], \
        'hero', 'Convex'


def pallet(B, M0, rng):
    def bx(size, loc, grain='x'):
        B.add(box_bm(size, 0.005, 2), 'pal', M0 @ mtx((loc[0] + rng.uniform(-0.004, 0.004), loc[1] + rng.uniform(-0.004, 0.004), loc[2]),
                                                   (0, 0, rng.uniform(-0.01, 0.01))), grain=grain)
    L, W = 1.2, 0.8
    for y in (-0.3275, 0.0, 0.3275):  # bottom boards
        bx((L, 0.145 if y == 0 else 0.1, 0.022), (0, y, 0.011))
    for x in (-0.5275, 0.0, 0.5275):
        for y in (-0.3275, 0.0, 0.3275):
            bx((0.145, 0.145 if y == 0 else 0.1, 0.078), (x, y, 0.022 + 0.039), grain='z')
    for x in (-0.5275, 0.0, 0.5275):
        bx((0.145, W, 0.022), (x, 0, 0.1 + 0.011), grain='y')
    for i, y in enumerate((-0.3275, -0.16, 0.0, 0.16, 0.3275)):
        wb = 0.145 if i in (0, 2, 4) else 0.1
        bx((L, wb, 0.022), (0, y, 0.122 + 0.011))
        for x in (-0.5275, 0.0, 0.5275):
            for dy in (-wb / 3, wb / 3):
                B.add(cyl_bm(0.0045, 0.002, 6, 0, 1), 'nail', M0 @ mtx((x + rng.uniform(-0.03, 0.03), y + dy, 0.1445)))


PAL = {'pal': dict(base='Timber', tint=(1.2, 1.1, 0.92), hue=(0.85, 1.0), dirt=0.8, edge=0.3, ground=0.1,
                   breakup=0.35),
       'nail': dict(base='CorrodedMetal', dirt=0.3)}


def p_Pallet():
    B = Builder()
    pallet(B, Matrix.Identity(4), random.Random(1))
    return [('Body', 'Body', B.finish('Pallet_Body'), PAL)], 'small', 'Box'


def p_PalletStack():
    B = Builder()
    rng = random.Random(2)
    for i in range(4):
        pallet(B, mtx((rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03), i * 0.1445), (0, 0, rng.uniform(-0.04, 0.04))), rng)
    return [('Body', 'Body', B.finish('PalletStack_Body'), PAL)], 'small', 'Box'


def p_HayBale_Round():
    B = Builder()
    bm = cyl_bm(0.75, 1.2, 64, 0.12, 4)
    # subdivide side faces for displacement
    bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges], cuts=3, use_grid_fill=True)
    B.add(bm, 'straw', mtx((0, 0, 0.75), (math.pi / 2, 0, 0)), grain='x')
    o = B.finish('HayBale_Round_Body')
    geo.subdivide_obj(o, 1)
    P = geo.verts_np(o.data)
    displace_obj(o, 0.025, 2.5, 4, 3)
    displace_obj(o, 0.006, 14.0, 3, 4)
    # sag / flatten on the ground
    P = geo.verts_np(o.data)
    P[:, 2] = np.maximum(P[:, 2], 0.0) - np.clip(0.06 - P[:, 2], 0, 0.06) * 0.5
    P[:, 2] -= P[:, 2].min()
    geo.set_verts(o.data, P)
    rec = dict(R['straw'])
    return [('Body', 'Body', o, {'straw': rec})], 'hero', 'Convex'


def p_HayBale_Square():
    B = Builder()
    L, W, H = 1.0, 0.48, 0.38
    bm = box_bm((L, W, H), 0.05, 3, subdiv=0)
    B.add(bm, 'straw', mtx((0, 0, H / 2)), grain='x')
    o = B.finish('HayBale_Square_Body')
    geo.subdivide_obj(o, 3, simple=True)
    me = o.data
    P = geo.verts_np(me)
    N = geo.normals_np(me)
    d = geo.fbm3(P * 3.0, 1.0, 4, 0.5, 7) * 0.02 + geo.fbm3(P * 18.0, 1.0, 3, 0.5, 8) * 0.006
    tw = np.exp(-((np.abs(P[:, 0]) - 0.25) / 0.015) ** 2) * 0.014  # twine cuts in
    geo.set_verts(me, P + N * (d - tw)[:, None])
    T = Builder()
    for x in (-0.25, 0.25):
        pts = []
        for k in range(41):
            a = k / 40 * math.tau
            y = math.cos(a) * (W / 2 + 0.005)
            z = H / 2 + math.sin(a) * (H / 2 + 0.005)
            # rounded-rectangle loop hugging the bale
            y = max(-W / 2 + 0.01, min(W / 2 - 0.01, y * 1.25))
            z = max(0.01, min(H - 0.005, (z - H / 2) * 1.25 + H / 2))
            pts.append(Vector((x, y, z)))
        for a_, b_ in zip(pts[:-1], pts[1:]):
            if (b_ - a_).length > 1e-4:
                T.between('twine', a_, b_, 0.0035, n=6, bevel=0)
    t = T.finish('HayBale_Square_Twine')
    o = geo.join([o, t], 'HayBale_Square_Body')
    return [('Body', 'Body', o, {'straw': R['straw'], 'twine': dict(base='Burlap', tint=(0.9, 0.75, 0.45), dirt=0.3)})], \
        'small', 'Box'


def barricade(B, width, window=None, H=2.0):
    st = 0.018
    n = max(1, round(width / 1.22))
    sw = width / n
    rects = []
    for i in range(n):
        y0 = -width / 2 + i * sw
        rects.append((y0 + 0.0015, 0.0, y0 + sw - 0.0015, H))
    if window:
        rects = shapes.rect_sub(rects, window)
    for r in rects:
        B.box('ply', (st, r[2] - r[0], r[3] - r[1]), (0.03, (r[0] + r[2]) / 2, 0.06 + (r[1] + r[3]) / 2), bevel=0.003,
              uvoff=(random.random() * 2, random.random() * 2))
    # frame on the back
    B.box('frame', (0.09, width, 0.038), (-0.026, 0, 0.06 + 0.019), bevel=0.004, grain='y')
    B.box('frame', (0.09, width, 0.038), (-0.026, 0, 0.06 + H - 0.019), bevel=0.004, grain='y')
    ys = [-width / 2 + 0.019 + i * (width - 0.038) / round(width / 0.6) for i in range(int(round(width / 0.6)) + 1)]
    for y in ys:
        if window and window[0] < y < window[2]:
            B.box('frame', (0.09, 0.038, window[1] - 0.04), (-0.026, y, 0.06 + 0.038 + (window[1] - 0.04) / 2 - 0.0), bevel=0.004, grain='z')
            continue
        B.box('frame', (0.09, 0.038, H - 0.076), (-0.026, y, 0.06 + H / 2), bevel=0.004, grain='z')
        for z in np.arange(0.2, H, 0.3):
            B.add(cyl_bm(0.0045, 0.003, 8, 0, 1), 'screw', mtx((0.04, y, 0.06 + z), (0, math.pi / 2, 0)))
    if window:
        y0, z0, y1, z1 = window
        for y in (y0 - 0.019, y1 + 0.019):
            B.box('frame', (0.09, 0.038, H - 0.076), (-0.026, y, 0.06 + H / 2), bevel=0.004, grain='z')
        for z in (z0 - 0.019, z1 + 0.019):
            B.box('frame', (0.09, y1 - y0, 0.038), (-0.026, (y0 + y1) / 2, 0.06 + z), bevel=0.004, grain='y')
    # A-frame braces + skids
    for y in ([-width / 2 + 0.1, 0.0, width / 2 - 0.1] if width > 3.5 else [-width / 2 + 0.1, width / 2 - 0.1]):
        B.box('frame', (1.3, 0.09, 0.06), (-0.55, y, 0.03), bevel=0.006)
        B.between('frame', (-1.15, y, 0.06), (-0.075, y, 0.06 + H * 0.85), 0, kind='box', w=(0.09, 0.038), bevel=0.004)
        B.between('frame', (-0.6, y, 0.06), (-0.075, y, 0.06 + H * 0.45), 0, kind='box', w=(0.07, 0.038), bevel=0.004)
        for p in ((-0.075, y, 0.06 + H * 0.85), (-1.1, y, 0.08)):
            B.add(cyl_bm(0.012, 0.11, 6, 0.002, 1), 'screw', mtx(p, (math.pi / 2, 0, 0)))


BAR = {'ply': R['ply_od'], 'frame': R['timber'], 'screw': dict(base='CorrodedMetal', dirt=0.2)}


def p_Barricade_Plywood_3m():
    B = Builder()
    barricade(B, 3.0, window=(-0.4, 1.1, 0.4, 1.5))
    return [('Body', 'Body', B.finish('Barricade_Plywood_3m_Body'), BAR)], 'hero', 'Complex'


def p_Barricade_Plywood_4m():
    B = Builder()
    barricade(B, 4.0)
    rec = dict(BAR)
    rec['ply'] = R['ply']
    return [('Body', 'Body', B.finish('Barricade_Plywood_4m_Body'), rec)], 'hero', 'Box'


def p_OilDrum():
    B = Builder()
    r = 0.286
    prof = [(0.0, 0.012), (0.255, 0.012), (0.262, 0.004), (0.282, 0.0), (0.296, 0.008), (0.298, 0.022), (0.29, 0.03),
            (r, 0.036)]
    for zc in (0.29, 0.59):
        prof += [(r, zc - 0.03), (r + 0.006, zc - 0.018), (r + 0.011, zc), (r + 0.006, zc + 0.018), (r, zc + 0.03)]
    prof += [(r, 0.85), (0.29, 0.856), (0.298, 0.866), (0.296, 0.88), (0.282, 0.884), (0.262, 0.878), (0.256, 0.866),
             (0.0, 0.866)]
    fine = []
    for (a, b2) in zip(prof[:-1], prof[1:]):
        for k in range(3):
            t = k / 3
            fine.append((a[0] + (b2[0] - a[0]) * t, a[1] + (b2[1] - a[1]) * t))
    fine.append(prof[-1])
    bm = lathe(fine, 128)
    B.add(bm, 'drum', None, grain='z')
    for (x, y, rr) in ((0.17, 0.0, 0.032), (-0.17, 0.05, 0.022)):
        B.add(cyl_bm(rr, 0.016, 16, 0.004, 2), 'drum', mtx((x, y, 0.874)))
        B.add(cyl_bm(rr * 0.5, 0.01, 6, 0.002, 1), 'drum', mtx((x, y, 0.884)))
    o = B.finish('OilDrum_Body')
    # dents
    me = o.data
    P = geo.verts_np(me)
    rr_ = np.hypot(P[:, 0], P[:, 1])
    side = (rr_ > 0.27) & (P[:, 2] > 0.04) & (P[:, 2] < 0.84)
    d = geo.fbm3(P * 3.5, 1.0, 3, 0.5, 2) * 0.02
    dent = np.exp(-(((np.arctan2(P[:, 1], P[:, 0]) - 0.6) / 0.35) ** 2 + ((P[:, 2] - 0.7) / 0.08) ** 2)) * 0.04
    dent += np.exp(-(((np.arctan2(P[:, 1], P[:, 0]) + 2.2) / 0.25) ** 2 + ((P[:, 2] - 0.2) / 0.06) ** 2)) * 0.03
    k = np.where(side, 1 - (d + dent) / np.maximum(rr_, 1e-3), 1.0)
    P[:, 0] *= k
    P[:, 1] *= k
    geo.set_verts(me, P)
    return [('Body', 'Body', o, {'drum': drum_paint()})], 'small', 'Convex', {'TintVariants': {'Blue': [0.02, 0.07, 0.26], 'Red': [0.42, 0.03, 0.02]}}


def p_Crate_Wood():
    B = Builder()
    rng = random.Random(9)
    L, W, H = 1.0, 0.7, 0.6
    # slatted sides
    for sy in (-1, 1):
        for i in range(4):
            z = 0.04 + i * 0.145 + 0.06
            B.box('wood', (L, 0.02, 0.12), (rng.uniform(-0.003, 0.003), sy * (W / 2 - 0.01), z), bevel=0.004)
    for sx in (-1, 1):
        for i in range(4):
            z = 0.04 + i * 0.145 + 0.06
            B.box('wood', (0.02, W - 0.04, 0.12), (sx * (L / 2 - 0.01), 0, z), bevel=0.004, grain='y')
    # frame battens
    for sx in (-1, 1):
        for sy in (-1, 1):
            B.box('wood', (0.07, 0.025, H), (sx * (L / 2 - 0.05), sy * (W / 2 + 0.012), H / 2), bevel=0.005, grain='z')
            B.box('wood', (0.025, 0.07, H), (sx * (L / 2 + 0.012), sy * (W / 2 - 0.05), H / 2), bevel=0.005, grain='z')
            B.box('metal', (0.1, 0.1, 0.003), (sx * (L / 2 - 0.03), sy * (W / 2 - 0.03), H + 0.0015), bevel=0.001)
    # lid boards
    for i in range(5):
        y = -W / 2 + 0.07 + i * (W - 0.14) / 4
        B.box('wood', (L + 0.01, 0.13, 0.022), (0, y, H - 0.011), bevel=0.004)
    for x in (-0.38, 0.38):
        B.box('wood', (0.08, W - 0.02, 0.02), (x, 0, H + 0.01), bevel=0.004, grain='y')
    # skids
    for y in (-0.25, 0.25):
        B.box('wood', (L, 0.08, 0.04), (0, y, 0.02), bevel=0.005)
    rec = {'wood': R['timber_new'], 'metal': R['steel_dark']}
    return [('Body', 'Body', B.finish('Crate_Wood_Body'), rec)], 'small', 'Box'


def p_Crate_Ammo():
    B = Builder()
    L, W, H = 0.9, 0.45, 0.36
    B.box('box', (L - 0.04, W - 0.04, H - 0.06), (0, 0, (H - 0.06) / 2 + 0.03), bevel=0.006)
    # end cleats + lid
    for sx in (-1, 1):
        B.box('box', (0.03, W, H), (sx * (L / 2 - 0.015), 0, H / 2), bevel=0.008, grain='y')
        # rope handle
        pts = [Vector((sx * (L / 2 + 0.01), y, 0.22 + 0.04 * math.cos(y / 0.1 * math.pi / 2))) for y in np.linspace(-0.1, 0.1, 7)]
        for a, b2 in zip(pts[:-1], pts[1:]):
            B.between('rope', a, b2, 0.008, n=8, bevel=0)
        for y in (-0.1, 0.1):
            B.add(box_bm((0.02, 0.04, 0.05), 0.004, 1), 'metal', mtx((sx * (L / 2 + 0.004), y, 0.22)))
    B.box('box', (L - 0.06, W + 0.01, 0.05), (0, 0, H - 0.025), bevel=0.008)
    for y in (-0.12, 0.12):
        B.box('box', (L - 0.1, 0.06, 0.02), (0, y, H + 0.01), bevel=0.005)
    # hinges + latches
    for x in (-0.25, 0.25):
        B.add(box_bm((0.08, 0.006, 0.07), 0.002, 1), 'metal', mtx((x, -W / 2 - 0.004, H - 0.05)))
        B.add(cyl_bm(0.008, 0.08, 10, 0.001, 1), 'metal', mtx((x, -W / 2 - 0.008, H - 0.05), (0, math.pi / 2, 0)))
        B.add(box_bm((0.05, 0.012, 0.09), 0.003, 1), 'metal', mtx((x, W / 2 + 0.006, H - 0.06)))
        B.add(box_bm((0.03, 0.02, 0.025), 0.003, 1), 'metal', mtx((x, W / 2 + 0.014, H - 0.1)))
    rec = {'box': ammo_paint(), 'metal': R['steel_dark'], 'rope': dict(base='Burlap', tint=(0.75, 0.68, 0.5), dirt=0.6)}
    return [('Body', 'Body', B.finish('Crate_Ammo_Body'), rec)], 'small', 'Box'


# ----------------------------------------------------------------------------
# wrecked car
# ----------------------------------------------------------------------------
def p_WreckedCar():
    import numpy as np
    L, Wd = 4.6, 1.76

    def ztop(x):
        xs = [-2.3, -2.22, -1.6, -1.0, -0.85, 0.25, 0.95, 2.05, 2.25, 2.3]
        zs = [0.62, 0.95, 1.0, 1.36, 1.41, 1.40, 0.96, 0.84, 0.72, 0.55]
        return float(np.interp(x, xs, zs))
    zbelt = lambda x: min(ztop(x), 0.97 + 0.02 * (x / 2.3))
    zbot = 0.22
    nx, ns = 200, 96
    bm = bmesh.new()
    grid = []
    tags = []
    for i in range(nx + 1):
        x = -L / 2 + L * i / nx
        zt, zb_ = ztop(x), zbelt(x)
        end = max(0.0, (abs(x) - 1.9) / 0.4)
        wb = Wd / 2 * (1 - 0.18 * end ** 2)
        wt = 0.66 * (1 - 0.1 * end)
        row = []
        trow = []
        for j in range(ns + 1):
            s = j / ns  # 0 left bottom -> 1 right bottom
            side = -1 if s < 0.5 else 1
            q = s * 2 if s < 0.5 else (1 - s) * 2  # 0 bottom .. 1 top centre
            if zt - zb_ > 0.08:
                if q < 0.45:
                    t = q / 0.45
                    z = zbot + (zb_ - zbot) * t
                    y = wb * (0.94 + 0.06 * math.sin(t * math.pi * 0.9))
                    seg = 0
                elif q < 0.75:
                    t = (q - 0.45) / 0.3
                    z = zb_ + (zt - 0.06 - zb_) * t
                    y = wb + (wt - wb) * t
                    seg = 1
                else:
                    t = (q - 0.75) / 0.25
                    z = zt - 0.06 * (1 - t) ** 2
                    y = wt * (1 - t)
                    seg = 2
            else:
                if q < 0.6:
                    t = q / 0.6
                    z = zbot + (zt - 0.04 - zbot) * t
                    y = wb * (0.94 + 0.06 * math.sin(t * math.pi * 0.9))
                    seg = 0
                else:
                    t = (q - 0.6) / 0.4
                    z = zt - 0.04 * (1 - t) ** 2
                    y = wb * (1 - t) * (1 - 0.1 * t)
                    seg = 3
            row.append(bm.verts.new((x, side * y, z)))
            trow.append((seg, t, side))
        grid.append(row)
        tags.append(trow)
    faces = []
    for i in range(nx):
        x = -L / 2 + L * (i + 0.5) / nx
        for j in range(ns):
            seg, t, side = tags[i][j]
            c = (grid[i][j].co + grid[i + 1][j + 1].co) / 2
            cut = False
            # wheel arches
            for xw in (-1.38, 1.36):
                if (c.x - xw) ** 2 + (c.z - 0.3) ** 2 < 0.4 ** 2 and seg == 0:
                    cut = True
            # side windows (keep A/B/C pillars)
            if seg == 1:
                if -1.45 < c.x < 0.8 and not (-0.32 < c.x < -0.2) and 0.08 < (c.z - zbelt(c.x)) < (ztop(c.x) - zbelt(c.x) - 0.1):
                    cut = True
            # windshield / rear window on the top
            if seg in (1, 2):
                if 0.33 < c.x < 0.88 and abs(c.y) < 0.55:
                    cut = True
                if -1.55 < c.x < -0.95 and abs(c.y) < 0.55:
                    cut = True
            if not cut:
                faces.append(bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1])))
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    # snap the wheel-arch cut to a clean (slightly ragged) circle
    for v in bm.verts:
        if not v.is_boundary:
            continue
        for xw in (-1.38, 1.36):
            dx, dz = v.co.x - xw, v.co.z - 0.3
            d = math.hypot(dx, dz)
            if d < 0.47 and v.co.z < 0.8:
                rr = 0.4 + 0.012 * math.sin(math.atan2(dz, dx) * 7 + xw)
                v.co.x = xw + dx / max(d, 1e-6) * rr
                v.co.z = 0.3 + dz / max(d, 1e-6) * rr
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.018)
    B = Builder()
    B.add(bm, 'body', None, grain='x')
    # floor pan, bumpers, grille, lamps sockets, hubs, seats frames, steering
    B.box('rust', (3.9, 1.6, 0.02), (0, 0, 0.24), bevel=0.005)
    for sx in (-1, 1):
        B.add(box_bm((0.12, 1.75, 0.16), 0.04, 3), 'rust', mtx((sx * 2.32, 0, 0.42), (0, 0, 0)))
    B.box('rust', (0.04, 1.0, 0.18), (2.29, 0, 0.66), bevel=0.01, grain='y')
    for k in range(6):
        B.box('rust', (0.05, 0.98, 0.012), (2.3, 0, 0.6 + k * 0.026), bevel=0.003, grain='y')
    for sy in (-1, 1):
        B.add(cyl_bm(0.09, 0.08, 16, 0.01, 2), 'rust', mtx((2.24, sy * 0.66, 0.72), (0, math.pi / 2, 0)))
        B.add(cyl_bm(0.07, 0.06, 16, 0.01, 2), 'rust', mtx((-2.26, sy * 0.68, 0.78), (0, math.pi / 2, 0)))
        for xw in (-1.38, 1.36):
            B.add(cyl_bm(0.16, 0.12, 24, 0.012, 2), 'rust', mtx((xw, sy * 0.72, 0.26), (math.pi / 2, 0, 0)))
            B.add(cyl_bm(0.09, 0.05, 10, 0.006, 1), 'rust', mtx((xw, sy * 0.79, 0.26), (math.pi / 2, 0, 0)))
            B.between('rust', (xw, sy * 0.3, 0.26), (xw, sy * 0.7, 0.26), 0.03, n=10)
        # mirror stubs
        B.add(box_bm((0.1, 0.06, 0.08), 0.015, 2), 'body', mtx((0.78, sy * 0.86, 1.02)))
    # one flattened tyre (front left) lying in the arch
    B.add(tire_bm(7, R0=0.31, w=0.19, rim=0.19, nseg=96, nprof=20), 'tyre', mtx((1.36, 0.73, 0.2), (math.pi / 2, 0, 0.0),
                                                                                  scale=(1.0, 1.0, 0.82)))
    # seats (frames + springs)
    for x in (0.0, -1.0):
        for sy in ((-1, 1) if x == 0.0 else (0,)):
            w = 0.5 if x == 0.0 else 1.3
            B.box('rust', (0.5, w, 0.08), (x, sy * 0.38, 0.42), bevel=0.02)
            B.between('rust', (x - 0.24, sy * 0.38 - w / 2, 0.45), (x - 0.34, sy * 0.38 - w / 2, 1.0), 0.015, n=8)
            B.between('rust', (x - 0.24, sy * 0.38 + w / 2, 0.45), (x - 0.34, sy * 0.38 + w / 2, 1.0), 0.015, n=8)
            B.between('rust', (x - 0.34, sy * 0.38 - w / 2, 1.0), (x - 0.34, sy * 0.38 + w / 2, 1.0), 0.015, n=8)
            for k in range(4):
                B.between('rust', (x - 0.26 - k * 0.02, sy * 0.38 - w / 2, 0.55 + k * 0.12),
                          (x - 0.26 - k * 0.02, sy * 0.38 + w / 2, 0.55 + k * 0.12), 0.006, n=6)
    # dashboard + steering wheel
    B.box('rust', (0.25, 1.5, 0.2), (0.75, 0, 0.88), bevel=0.04, grain='y')
    B.between('rust', (0.7, 0.38, 0.85), (0.45, 0.38, 0.95), 0.02, n=8)
    tor = bmesh.new()
    bmesh.ops.create_circle(tor, segments=24, radius=0.18)
    sw = Builder()
    B.add(lathe([(0.17, -0.012), (0.185, 0.0), (0.17, 0.012), (0.155, 0.0), (0.17, -0.012)], 32), 'rust',
          mtx((0.45, 0.38, 0.97), (0, -1.1, 0)))
    o = B.finish('WreckedCar_Body')
    # dents + crushed front corner
    me = o.data
    P = geo.verts_np(me)
    d = geo.fbm3(P * 1.6, 1.0, 3, 0.5, 11) * 0.03
    N = geo.normals_np(me)
    body_mask = (P[:, 2] > 0.3).astype(float)
    crush = np.clip((P[:, 0] - 1.6) / 0.7, 0, 1) * np.clip((P[:, 1] + 0.2) / 0.7, 0, 1)
    P[:, 0] -= crush * 0.18
    P[:, 2] -= crush * 0.08 * np.clip((P[:, 2] - 0.4), 0, 1)
    P = P + N * (d * body_mask)[:, None]
    P[:, 2] = np.maximum(P[:, 2], 0.0)
    # sag (sits low on the left)
    P[:, 2] -= 0.03 * (P[:, 1] + 0.9)
    P[:, 2] -= P[:, 2].min()
    geo.set_verts(me, P)
    rec = {
        'body': dict(base='CorrodedMetal', paint=(0.36, 0.13, 0.1), chip=0.9, chip_scale=3.0, chip_global=0.62,
                     under='CorrodedMetal', paint_rough=0.75, edge=0.2, dirt=0.8, ground=0.45, streak=0.6,
                     streak_col=(0.22, 0.09, 0.03)),
        'rust': dict(base='CorrodedMetal', dirt=0.8, edge=0.2, ground=0.4),
        'tyre': dict(base='Rubber', dirt=0.8, ground=0.3, hue=(0.6, 1.4)),
    }
    return [('Body', 'Body', o, rec)], 'hero', 'Convex'


# ----------------------------------------------------------------------------
# vegetation
# ----------------------------------------------------------------------------
def leaf_atlas(asset, res, seed, palette):
    """2x2 atlas of twig clusters with oak leaves -> T_<asset>_Leaves_*."""
    n = res
    rg = np.random.default_rng(seed)
    bc = np.zeros((n, n, 3), np.float32)
    op = np.zeros((n, n), np.float32)
    hh = np.zeros((n, n), np.float32)
    half = n // 2
    for cy in range(2):
        for cx in range(2):
            ox, oy = cx * half, cy * half
            # twig
            pts = [(0.5, 0.97)]
            ang = -math.pi / 2 + rg.uniform(-0.2, 0.2)
            for k in range(6):
                ang += rg.uniform(-0.25, 0.25)
                pts.append((pts[-1][0] + math.cos(ang) * 0.14, pts[-1][1] + math.sin(ang) * 0.14))
            leaves = []
            for k in range(1, len(pts)):
                for side in (-1, 1):
                    if rg.random() < 0.85:
                        leaves.append((pts[k], ang + side * rg.uniform(0.5, 1.2)))
            for _ in range(5):
                k = rg.integers(2, len(pts))
                leaves.append((pts[k], -math.pi / 2 + rg.uniform(-1.4, 1.4)))
            canvas = np.zeros((half, half, 3), np.float32)
            a_ = np.zeros((half, half), np.float32)
            h_ = np.zeros((half, half), np.float32)
            twig = np.zeros((half, half), np.float32)
            polys = [np.array(pts)]
            cov, _ = tex.draw_polylines(half, polys, widths=[np.array([3.0, 1.0])])
            twig = np.clip(tex.blur(cov, half / 400.0) * 2, 0, 1)
            for (p, a) in leaves:
                size = int(half * rg.uniform(0.28, 0.42))
                y, x = np.mgrid[0:size, 0:size].astype(np.float32)
                x = (x + 0.5) / size - 0.5
                y = (y + 0.5) / size - 0.5
                xr = x * math.cos(a) + y * math.sin(a)
                yr = -x * math.sin(a) + y * math.cos(a)
                t = xr / 0.46 + 0.45
                lob = 6
                w = np.clip(np.sin(np.clip(t, 0, 1) * math.pi), 0, 1) ** 0.7 * (0.1 + 0.06 * np.abs(np.sin(t * math.pi * lob)))
                inside = (t > 0) & (t < 1)
                al = tex.sstep(0.006, -0.006, np.abs(yr) - w) * inside
                vein = np.exp(-(yr / 0.006) ** 2) + 0.5 * np.exp(-((np.abs(yr) * 1.4 - (t * 0.6 % 0.12)) / 0.008) ** 2) * (np.abs(yr) < w)
                hue = rg.random()
                base = tex.ramp(np.array(hue, np.float32), palette)
                shade = 0.8 + 0.35 * (1 - np.abs(yr) / np.maximum(w, 1e-3)).clip(0, 1)
                rgb = np.broadcast_to(base, (size, size, 3)) * (shade * (1 - 0.25 * vein.clip(0, 1)))[..., None]
                px = int(p[0] * half - size / 2)
                py = int(p[1] * half - size / 2)
                ys = np.clip(np.arange(size) + py, 0, half - 1)
                xs = np.clip(np.arange(size) + px, 0, half - 1)
                ix = np.ix_(ys, xs)
                m = al > 0.5
                canvas[ix] = np.where(m[..., None], rgb, canvas[ix])
                a_[ix] = np.maximum(a_[ix], al)
                h_[ix] = np.where(m, 0.5 + 0.5 * (1 - (np.abs(yr) / np.maximum(w, 1e-3)) ** 2).clip(0, 1) - vein.clip(0, 1) * 0.1, h_[ix])
            canvas = np.where((twig > 0.3)[..., None] & (a_ < 0.5)[..., None], np.array([0.25, 0.18, 0.12], np.float32), canvas)
            a_ = np.maximum(a_, twig)
            bc[oy:oy + half, ox:ox + half] = canvas
            op[oy:oy + half, ox:ox + half] = a_
            hh[oy:oy + half, ox:ox + half] = h_
    # dilate colour into transparent areas to avoid dark fringes
    for _ in range(6):
        m = op > 0.5
        b2 = tex.blur(bc * m[..., None], 2.0)
        w2 = tex.blur(m.astype(np.float32), 2.0)
        fill = b2 / np.maximum(w2, 1e-4)[..., None]
        bc = np.where(m[..., None], bc, fill)
    out = bl.ensure(os.path.join(OUT, asset))
    pre = os.path.join(out, 'T_%s_Leaves_' % asset)
    tex.save_png(pre + 'BC.png', bc)
    tex.save_png(pre + 'Opacity.png', op)
    tex.save_png(pre + 'N.png', tex.height_to_normal(hh * 0.004, 0.6, 1.0))
    ao = 0.6 + 0.4 * hh
    tex.save_png(pre + 'ORM.png', np.stack([ao, np.full_like(op, 0.55), np.zeros_like(op)], -1))
    return pre


GREEN = [(0, tex.col('#2f4a1a')), (0.35, tex.col('#3f5e22')), (0.6, tex.col('#56722c')), (0.85, tex.col('#6d7f35')),
         (1, tex.col('#7a6a2c'))]


def tree_build(name, seed, height, spread, levels=4, leaf_density=1.0, bush=False):
    rnd = random.Random(seed)
    branches = []

    def rv():
        return Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)))

    def grow(p, d, length, r0, level):
        k = max(3, int(length / 0.25))
        pts = [p.copy()]
        rads = [r0]
        dirv = d.normalized()
        wob = 0.05 if level == 0 else 0.16
        grav = 0.05 if level < 2 else -0.05 * (level - 1)
        for i in range(k):
            dirv = (dirv + rv() * wob + Vector((0, 0, grav))).normalized()
            p = p + dirv * (length / k)
            pts.append(p.copy())
            rads.append(max(0.006, r0 * (1 - 0.72 * (i + 1) / k)))
        branches.append((pts, rads, level))
        if level >= levels:
            return
        nchild = rnd.randint(4, 6) if level == 0 else (rnd.randint(4, 6) if level == 1 else rnd.randint(3, 5))
        for c in range(nchild):
            t = rnd.uniform(0.8, 0.98) if level == 0 else rnd.uniform(0.25, 0.97)
            idx = min(len(pts) - 2, int(t * k))
            perp = dirv.cross(rv()).normalized()
            ang = rnd.uniform(0.5, 1.0)
            cd = (dirv * math.cos(ang) + perp * math.sin(ang)).normalized()
            if level == 0:
                a = c / nchild * math.tau + rnd.uniform(-0.3, 0.3)
                cd = Vector((math.cos(a) * spread, math.sin(a) * spread, 0.9 + rnd.uniform(-0.3, 0.3))).normalized()
            cl = length * (rnd.uniform(1.1, 1.35) if level == 0 else rnd.uniform(0.5, 0.7))
            grow(pts[idx], cd, cl, rads[idx] * (0.6 if level == 0 else 0.62), level + 1)
    if bush:
        for s_ in range(7):
            a = s_ / 7 * math.tau
            grow(Vector((math.cos(a) * 0.1, math.sin(a) * 0.1, 0)), Vector((math.cos(a) * 0.5, math.sin(a) * 0.5, 1)),
                 height * 0.55, 0.03, 2)
    else:
        grow(Vector((0, 0, -0.1)), Vector((0, 0, 1)), height * 0.3, height * 0.034, 0)
    # trunk mesh
    B = Builder(arch=True)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new('UVMap')
    for (pts, rads, level) in branches:
        nsd = max(5, min(28, int(rads[0] * 110)))
        rings = []
        acc = 0.0
        prev = pts[0]
        for i, (p, r) in enumerate(zip(pts, rads)):
            d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            q = d.to_track_quat('Z', 'Y')
            acc += (p - prev).length
            prev = p
            ring = []
            for j in range(nsd + 1):
                a = j / nsd * math.tau
                rr = r
                if level == 0 and not bush:
                    flare = math.exp(-max(p.z, 0) / 0.6)
                    rr = r * (1 + 0.7 * flare * (1 + 0.35 * math.sin(a * 5)))
                    rr *= 1 + 0.05 * math.sin(a * 3 + p.z * 2)
                off = q @ Vector((math.cos(a) * rr, math.sin(a) * rr, 0))
                ring.append((bm.verts.new(p + off), acc, a / math.tau * math.tau * rads[0]))
            rings.append(ring)
        for i in range(len(rings) - 1):
            for j in range(nsd):
                vs = (rings[i][j][0], rings[i][j + 1][0], rings[i + 1][j + 1][0], rings[i + 1][j][0])
                f = bm.faces.new(vs)
                for lp, (ri, rj) in zip(f.loops, ((i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j))):
                    lp[uvl].uv = (rings[ri][rj][1] * 0.5, rings[ri][rj][2] * 0.5)
    bm.normal_update()
    me = bpy.data.meshes.new(name + '_Body')
    bm.to_mesh(me)
    bm.free()
    me.materials.append(bpy.data.materials.get('MI_Bark') or bpy.data.materials.new('MI_Bark'))
    for p in me.polygons:
        p.use_smooth = True
    trunk = bpy.data.objects.new(name + '_Body', me)
    bpy.context.scene.collection.objects.link(trunk)
    # leaf cards along terminal branches
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new('UVMap')
    centre = Vector((0, 0, height * 0.6))
    ncard = 0
    for (pts, rads, level) in branches:
        if level < levels - 2 or rads[0] > 0.12:
            continue
        L = sum((b - a).length for a, b in zip(pts[:-1], pts[1:]))
        k = max(1, int(L / (0.075 if not bush else 0.06) * leaf_density))
        for c in range(k):
            t = rnd.uniform(0.3, 1.0)
            idx = min(len(pts) - 1, int(t * (len(pts) - 1)))
            p = pts[idx] + rv() * 0.3
            out = (p - centre)
            out.z *= 0.5
            out = (out.normalized() + rv() * 0.8 + Vector((0, 0, 0.4))).normalized()
            size = rnd.uniform(0.8, 1.25) * (0.55 if bush else 1.0)
            up = Vector((0, 0, 1))
            xa = out.cross(up)
            if xa.length < 1e-3:
                xa = Vector((1, 0, 0))
            xa.normalize()
            ya = xa.cross(out).normalized()
            rot = rnd.uniform(0, math.tau)
            xa, ya = xa * math.cos(rot) + ya * math.sin(rot), -xa * math.sin(rot) + ya * math.cos(rot)
            cell = rnd.randint(0, 3)
            u0, v0 = (cell % 2) * 0.5, (cell // 2) * 0.5
            vv = []
            for (a, b2) in ((-0.5, 0), (0.5, 0), (0.5, 1), (-0.5, 1), (-0.5, 0.5), (0.5, 0.5)):
                pass
            grid = []
            for gi in range(3):
                row = []
                for gj in range(2):
                    a = gj - 0.5
                    b2 = gi / 2
                    bend = (b2 ** 2) * 0.25 * size
                    pos = p + xa * a * size + ya * b2 * size - out * bend
                    row.append((bm.verts.new(pos), (u0 + 0.5 * (gj), v0 + 0.5 * (1 - b2) * 1.0)))
                grid.append(row)
            for gi in range(2):
                vs = [grid[gi][0], grid[gi][1], grid[gi + 1][1], grid[gi + 1][0]]
                f = bm.faces.new([v[0] for v in vs])
                for lp, v in zip(f.loops, vs):
                    lp[uvl].uv = (v[1][0], 1 - (v[1][1]))
            ncard += 1
    me = bpy.data.meshes.new(name + '_Leaves')
    bm.to_mesh(me)
    bm.free()
    me.materials.append(bpy.data.materials.new('M_%s_Leaves' % name))
    leaves = bpy.data.objects.new(name + '_Leaves', me)
    bpy.context.scene.collection.objects.link(leaves)
    return trunk, leaves


def veg(name, seed, height, spread, levels, density=1.0, bush=False, res=2048):
    trunk, leaves = tree_build(name, seed, height, spread, levels, density, bush)
    pre = leaf_atlas(name, min(2048, res), seed + 5, GREEN)
    leaves.data.materials[0] = bl.baked_material('M_%s_Leaves' % name, pre[:-1], opacity=True)
    m = leaves.data.materials[0]
    try:
        bsdf = [n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'][0]
        bsdf.inputs['Subsurface Weight'].default_value = 0.0
        bsdf.inputs['Transmission Weight'].default_value = 0.0
    except Exception:
        pass
    return [('Body', 'Body', trunk, None), ('Leaves', 'Static', leaves, None)], 'veg', 'Convex'


def p_Tree_Oak_A():
    return veg('Tree_Oak_A', 101, 13.0, 0.9, 4)


def p_Tree_Oak_B():
    return veg('Tree_Oak_B', 202, 11.0, 1.2, 4)


def p_Tree_Oak_C():
    return veg('Tree_Oak_C', 303, 14.5, 0.7, 4, 0.9)


def p_Bush_A():
    return veg('Bush_A', 404, 1.8, 1.0, 4, 1.4, bush=True)


def rock(name, seed, size, flat=0.6):
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=6, radius=1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    P = geo.verts_np(me)
    P = P * np.array(size)
    P = P * (1 + 0.25 * geo.fbm3(P * 0.6, 1.0, 3, 0.5, seed))[:, None]
    for k in range(9):
        n = rng.normal(size=3)
        n[2] = abs(n[2]) * 0.5 + (0.6 if k == 0 else 0)
        n /= np.linalg.norm(n)
        d = np.percentile(P @ n, rng.uniform(80, 93))
        over = np.clip(P @ n - d, 0, None)
        P = P - np.outer(over * 0.85, n)
    P = P + P / np.linalg.norm(P, axis=1, keepdims=True) * (geo.fbm3(P * 3.0, 1.0, 4, 0.55, seed + 1) * 0.05 * max(size))[:, None]
    P = P + P / np.linalg.norm(P, axis=1, keepdims=True) * (geo.fbm3(P * 25.0, 1.0, 2, 0.5, seed + 3) * 0.004 * max(size))[:, None]
    P = P + P / np.linalg.norm(P, axis=1, keepdims=True) * (geo.fbm3(P * 12.0, 1.0, 3, 0.5, seed + 2) * 0.008 * max(size))[:, None]
    zmin = P[:, 2].min()
    P[:, 2] = np.maximum(P[:, 2], zmin + size[2] * 0.25 * flat)
    P[:, 2] -= P[:, 2].min() + 0.06
    geo.set_verts(me, P)
    for p in me.polygons:
        p.use_smooth = True
    uvl = me.uv_layers.new(name='UVMap')
    me.uv_layers.new(name='UVTex')
    o = bpy.data.objects.new(name + '_Body', me)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(bpy.data.materials.new('granite'))
    # world box UV into UVTex
    bmx = bmesh.new()
    bmx.from_mesh(me)
    geo.box_uv(bmx, bmx.loops.layers.uv['UVTex'], 1.0, 'x')
    bmx.to_mesh(me)
    bmx.free()
    return o


def p_Rock_A():
    o = rock('Rock_A', 51, (1.0, 0.8, 0.75))
    return [('Body', 'Body', o, {'granite': R['granite']})], 'hero', 'Convex'


def p_Rock_B():
    o = rock('Rock_B', 52, (0.7, 0.55, 0.38), flat=0.8)
    return [('Body', 'Body', o, {'granite': R['granite']})], 'small', 'Convex'


# ----------------------------------------------------------------------------
# objective / range props
# ----------------------------------------------------------------------------
def p_FlagPole_Objective():
    B = Builder()
    # weighted base: tyre filled with concrete
    B.add(tire_bm(3), 'tyre', mtx((0, 0, 0.105)))
    B.add(cyl_bm(0.215, 0.16, 32, 0.01, 2), 'conc', mtx((0, 0, 0.09)))
    B.add(cyl_bm(0.032, 6.0, 20, 0.004, 2, r2=0.022), 'pole', mtx((0, 0, 3.15)), grain='z')
    B.add(cyl_bm(0.045, 0.06, 20, 0.008, 2), 'pole', mtx((0, 0, 6.18)))
    bmb = bmesh.new()
    bmesh.ops.create_uvsphere(bmb, u_segments=20, v_segments=12, radius=0.05)
    B.add(bmb, 'pole', mtx((0, 0, 6.25)))
    B.box('pole', (0.04, 0.12, 0.025), (0.04, 0, 1.4), bevel=0.006)  # cleat
    B.between('rope', (0.04, 0, 1.4), (0.035, 0, 6.12), 0.003, n=6, bevel=0)
    body = B.finish('FlagPole_Objective_Body')
    F = Builder()
    fw, fh = 1.2, 0.8
    nu, nv = 48, 32
    bm = bmesh.new()
    vs = []
    for i in range(nu + 1):
        row = []
        for j in range(nv + 1):
            u = i / nu
            v = j / nv
            x = 0.04 + u * fw * (1 - 0.04 * u)
            amp = 0.09 * u ** 1.2
            y = amp * math.sin(u * 7.0 - 0.6 + v * 0.8) + 0.02 * math.sin(u * 19 + v * 5) * u
            z = 6.05 - fh + v * fh - 0.06 * u ** 2 * (1 - v)
            row.append(bm.verts.new((x, y, z)))
        vs.append(row)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    bm.normal_update()
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.003)
    F.add(bm, 'flag', None, grain='x')
    for z in (6.05 - fh + 0.02, 6.03):
        F.add(cyl_bm(0.04, 0.03, 16, 0.004, 1), 'clip', mtx((0, 0, z)))
    flag = F.finish('FlagPole_Objective_Flag')
    rb = {'pole': R['galv'], 'tyre': R['rubber'], 'conc': R['concrete'],
          'rope': dict(base='Burlap', tint=(0.95, 0.95, 0.9), hue=(0.1, 1.3), dirt=0.3)}
    rf = {'flag': dict(base='Canvas', paint=(0.88, 0.88, 0.88), chip=0.0, chip_global=-0.6, paint_rough=0.8,
                       mask=(1, 0, 0), dirt=0.35, breakup=0.15, edge=0.0, bump=0.15, bump_scale=8.0),
          'clip': dict(base='PaintedSteel', tint=(0.3, 0.3, 0.3), mask=(0, 0, 0))}
    return [('Body', 'Body', body, rb), ('Flag', 'Static', flag, rf)], 'small', 'Convex', \
        {'TintVariants': {'Red': [0.6, 0.05, 0.04], 'Blue': [0.04, 0.15, 0.6]},
         'Points': {'FlagTop': bl.ue((0.0, 0.0, 6.30))}}


def p_SteelTarget():
    B = Builder()
    # square-tube stand: two splayed legs, crossbar, hanger arm
    for sy in (-1, 1):
        B.between('stand', (0.35, sy * 0.45, 0.0), (0.0, sy * 0.3, 1.25), 0, kind='box', w=(0.04, 0.04), bevel=0.003)
        B.between('stand', (-0.35, sy * 0.45, 0.0), (0.0, sy * 0.3, 1.25), 0, kind='box', w=(0.04, 0.04), bevel=0.003)
        B.box('stand', (0.8, 0.05, 0.01), (0, sy * 0.45, 0.005), bevel=0.002)
    B.box('stand', (0.05, 0.7, 0.05), (0, 0, 1.27), bevel=0.004, grain='y')
    for sy in (-0.09, 0.09):
        B.box('stand', (0.04, 0.008, 0.12), (0.03, sy, 1.2), bevel=0.002)
        B.add(cyl_bm(0.008, 0.03, 10, 0.002, 1), 'stand', mtx((0.03, sy, 1.15), (math.pi / 2, 0, 0)))
    body = B.finish('SteelTarget_Body')
    P = Builder()
    # hanger links swing with the plate (pivot = Points.Hinge at the top of the links)
    for sy in (-0.09, 0.09):
        P.between('chain', (0.03, sy, 1.15), (0.06, sy, 1.06), 0.006, n=8)
    pts = []
    for k in range(48):
        a = k / 48 * math.tau
        pts.append((math.cos(a) * 0.2, math.sin(a) * 0.2))
    bm = extrude_poly(pts, 0.0095, 0.002)
    P.add(bm, 'plate', mtx((0.06, 0, 0.84), (0, math.pi / 2, 0)), grain='x')
    for sy in (-0.09, 0.09):
        P.box('plate', (0.0095, 0.03, 0.06), (0.06, sy, 1.05), bevel=0.002)
    plate = P.finish('SteelTarget_Plate')
    rb = {'stand': R['steel_dark']}
    rp = {'chain': R['galv'], 'plate': dict(base='PaintedSteel', paint=(0.85, 0.84, 0.8), chip=0.5, chip_scale=40.0, chip_global=0.1,
                        under='CorrodedMetal', paint_rough=0.5, edge=0.3, dirt=0.4, streak=0.3,
                        streak_col=(0.3, 0.2, 0.12))}
    return [('Body', 'Body', body, rb), ('Plate', 'Static', plate, rp)], 'small', 'Convex', \
        {'Points': {'Hinge': bl.ue((0.03, 0.0, 1.15))}, 'HingeAxis': [0.0, 1.0, 0.0]}


def p_ChronoTable():
    B = Builder()
    L, W, H = 1.83, 0.76, 0.74
    B.box('top', (W, L, 0.045), (0, 0, H - 0.0225), bevel=0.012, grain='y')
    B.box('frame', (W - 0.06, 0.03, 0.05), (0, L / 2 - 0.12, H - 0.07), bevel=0.004)
    B.box('frame', (W - 0.06, 0.03, 0.05), (0, -L / 2 + 0.12, H - 0.07), bevel=0.004)
    for sy in (-1, 1):
        y = sy * (L / 2 - 0.2)
        for sx in (-1, 1):
            B.between('frame', (sx * 0.32, y, 0.0), (sx * 0.3, y, H - 0.05), 0.014, n=12)
            B.add(cyl_bm(0.02, 0.025, 12, 0.005, 1), 'feet', mtx((sx * 0.32, y, 0.012)))
        B.between('frame', (-0.31, y, 0.12), (0.31, y, 0.12), 0.011, n=10)
        B.between('frame', (0, y, 0.12), (0, y * 0.4, H - 0.06), 0.009, n=8)
    # chronograph (sky screens on rods)
    cx, cy, cz = 0.0, -0.2, H
    B.box('chrono', (0.12, 0.42, 0.06), (cx, cy, cz + 0.03), bevel=0.01, grain='y')
    B.box('display', (0.004, 0.08, 0.035), (cx + 0.061, cy, cz + 0.035), bevel=0.002)
    for dy in (-0.18, 0.18):
        for dx in (-0.05, 0.05):
            B.between('frame', (cx + dx, cy + dy, cz + 0.06), (cx + dx * 2.6, cy + dy, cz + 0.33), 0.003, n=6, bevel=0)
        sc = bmesh.new()
        vs = [sc.verts.new(v) for v in ((-0.13, -0.035, 0.0), (0.13, -0.035, 0.0), (0.13, -0.035, 0.0), (-0.13, -0.035, 0.0))]
        B.add(box_bm((0.27, 0.07, 0.002), 0.0005, 1), 'screen', mtx((cx, cy + dy, cz + 0.335), (0.0, 0.0, 0)))
    # gun rest pad + bb bottle + clipboard
    B.box('feet', (0.25, 0.35, 0.05), (0.1, 0.45, H + 0.025), bevel=0.015, grain='y')
    B.add(cyl_bm(0.04, 0.16, 20, 0.008, 2), 'bottle', mtx((-0.22, 0.25, H + 0.08)))
    B.add(cyl_bm(0.022, 0.025, 16, 0.004, 1), 'chrono', mtx((-0.22, 0.25, H + 0.172)))
    B.box('clip', (0.23, 0.32, 0.004), (-0.15, 0.6, H + 0.002), bevel=0.001)
    body = B.finish('ChronoTable_Body')
    rec = {'top': R['ply'], 'frame': R['steel_dark'], 'feet': R['rubber'],
           'chrono': dict(base='Rubber', tint=(0.9, 0.9, 0.9), dirt=0.3, edge=0.4, metal=0.0),
           'display': dict(base='MarbleBlack', tint=(0.3, 0.45, 0.35), rough_add=-0.05),
           'screen': dict(base='Canvas', paint=(0.92, 0.92, 0.9), chip=0.0, chip_global=-0.6, paint_rough=0.6, dirt=0.2),
           'bottle': dict(base='Rubber', paint=(0.9, 0.9, 0.92), chip=0.0, chip_global=-0.6, paint_rough=0.3, dirt=0.2),
           'clip': dict(base='OSB', dirt=0.2)}
    return [('Body', 'Body', body, rec)], 'small', 'Box'


ASSETS = ['SandbagWall_3m', 'SandbagCorner', 'Tire', 'TireStack', 'CableSpool', 'Pallet', 'PalletStack',
          'HayBale_Round', 'HayBale_Square', 'Barricade_Plywood_3m', 'Barricade_Plywood_4m', 'OilDrum', 'Crate_Wood',
          'Crate_Ammo', 'WreckedCar', 'Tree_Oak_A', 'Tree_Oak_B', 'Tree_Oak_C', 'Bush_A', 'Rock_A', 'Rock_B',
          'FlagPole_Objective', 'SteelTarget', 'ChronoTable']


def build(aid, res, opts):
    bl.reset()
    r = globals()['p_' + aid]()
    pieces, klass, coll = r[0], r[1], r[2]
    extra = r[3] if len(r) > 3 else {}
    tres = res if klass == 'hero' else max(512, res // 2)
    out = bl.ensure(os.path.join(OUT, aid))
    entry = {'Pieces': [], 'Collision': coll}
    entry.update(extra)
    objs = []
    tint = None
    if extra.get('TintVariants'):
        tint = list(extra['TintVariants'].values())[0]
    for (pname, kind, obj, rec) in pieces:
        slots = []
        if rec:
            for i, m in enumerate(obj.data.materials):
                obj.data.materials[i] = bake.recipe_material('%s_%s_%s' % (aid, pname, m.name), rec[m.name])
            geo.smart_uv(obj, margin=0.003 if tres >= 2048 else 0.006)
            prefix = os.path.join(out, 'T_%s_%s' % (aid, pname))
            want_m = any(rec[s].get('mask') for s in rec)
            bake.bake_piece(obj, prefix, tres, mask_res=min(1024, tres), want_mask=want_m)
            slot = 'M_%s_%s' % (aid, pname)
            bake.finalize_piece(obj, slot, prefix, has_mask=want_m, tint=tint if want_m else None)
            slots = [slot]
            texd = {k: '%s/%s/T_%s_%s_%s.png' % (CAT, aid, aid, pname, k) for k in ('BC', 'N', 'ORM', 'M')
                    if os.path.exists(prefix + '_%s.png' % k)}
            texres = tres
        else:
            slots = [m.name for m in obj.data.materials]
            texd = {}
            if pname == 'Leaves':
                texd = {k: '%s/%s/T_%s_Leaves_%s.png' % (CAT, aid, aid, k) for k in ('BC', 'N', 'ORM', 'Opacity')}
            texres = None
        if opts['export']:
            # export material slot names exactly (strip render-only suffixes)
            mats = list(obj.data.materials)
            bl.export_fbx(obj, os.path.join(out, 'SM_%s_%s.fbx' % (aid, pname)))
        if not rec and pname == 'Body':
            m = obj.data.materials[0]
            obj.data.materials[0] = bl.lib_material('Bark', uv_scale=2.0 / bl.lib_tile('Bark'), name='MI_Bark_R')
        t = bl.tri_count(obj)
        pe = {'Name': pname, 'Kind': kind, 'Slots': slots, 'Triangles': t}
        if texd:
            pe['Textures'] = texd
        if texres:
            pe['TextureSize'] = texres
        if pname == 'Leaves' or pname == 'Net':
            pe['BlendMode'] = 'Masked'
        entry['Pieces'].append(pe)
        objs.append(obj)
    entry['Bounds'] = bl.bounds_ue(objs)
    print('  %-22s tris=%s' % (aid, [p['Triangles'] for p in entry['Pieces']]), flush=True)
    checkpoint(aid, 'P_', entry)
    return render_asset(aid, objs, entry, opts)


def checkpoint(aid, pre, entry):
    import json
    bl.ensure(SCRATCH)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(SCRATCH, pre + aid + '.blend'), compress=False)
    json.dump(entry, open(os.path.join(SCRATCH, pre + aid + '.json'), 'w'))


def resume(aid, opts):
    """Render-only from a checkpoint written by a build that was killed while rendering."""
    import json
    import time
    b = os.path.join(SCRATCH, 'P_' + aid + '.blend')
    j = os.path.join(SCRATCH, 'P_' + aid + '.json')
    if not (os.path.exists(b) and os.path.exists(j) and time.time() - os.path.getmtime(j) < 3 * 3600):
        return None
    bpy.ops.wm.open_mainfile(filepath=b)
    objs = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.name.startswith('Cyc')]
    return render_asset(aid, objs, json.load(open(j)), opts)


def render_asset(aid, objs, entry, opts):
    if opts['render']:
        az, el = -38.0, 16.0
        if aid.startswith('Tree'):
            el = 6.0
        if aid in ('Tire',):
            el = 30.0
        bl.product_shot(objs, os.path.join(bl.RENDERS, CAT, aid + '.png'), az=az, el=el,
                        samples=opts['samples'] or 10, margin=1.1)
        if aid == 'OilDrum':
            pass
    return entry


def main():
    o = bl.parse_args()
    ids = o['ids'] or ASSETS
    if not o['lineup_only']:
        for aid in ids:
            try:
                e = resume(aid, o) if '--resume' in sys.argv else None
                e = e or build(aid, o['res'], o)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                print('FAILED', aid, ex, flush=True)
                continue
            bl.json_update('Props.json', 'Assets', {aid: e},
                       extra={'Notes': 'Unreal cm. Origin = floor centre, front +X. M_* slots = unique baked sets '
                                       '(T_<Id>_<Piece>_BC/N/ORM, _M role mask R = tint). MI_Bark uses Materials.json '
                                       '(1 UV = 2 m). Leaves/Net are Masked with _Opacity.'})  # per asset
    if o['lineup'] and o['render']:
        import architecture
        architecture.SCRATCH = SCRATCH
        order = ['Tire', 'TireStack', 'OilDrum', 'Crate_Ammo', 'Crate_Wood', 'Pallet', 'PalletStack', 'HayBale_Square',
                 'SteelTarget', 'ChronoTable', 'Rock_B', 'HayBale_Round', 'CableSpool', 'Rock_A', 'SandbagCorner',
                 'SandbagWall_3m', 'Barricade_Plywood_3m', 'Barricade_Plywood_4m', 'WreckedCar', 'FlagPole_Objective',
                 'Bush_A', 'Tree_Oak_B', 'Tree_Oak_A', 'Tree_Oak_C']
        architecture.lineup(['P_' + a for a in order], CAT, cols=7, spacing=0.5)


if __name__ == '__main__':
    main()
