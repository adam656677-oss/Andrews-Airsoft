"""Modular CQB / field architecture kit -> SourceAssets/Architecture/<Id>/

usage: python architecture.py [--res 4096|2048|1024] [--no-render] [-- Id ...]

Kit modules use shared tileable materials (slots MI_<MaterialId>) with UVs at
real-world scale (1 UV = 2 m; tile with ArchUVScale from Materials.json).
The container body is a unique baked set (M_Container_20ft_Body) with a role
mask (R = paint, tintable). Origin = floor centre, front = +X.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from envlib import bake, bl, geo, shapes  # noqa: E402
from envlib.geo import Builder, box_bm, cyl_bm, mtx  # noqa: E402

CAT = 'Architecture'
OUT = os.path.join(bl.SA, CAT)


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def screws(B, pts, axis_x=True, r=0.0045, mat='MI_CorrodedMetal'):
    for p in pts:
        B.cyl(mat, r, 0.003, p, rot=(0, math.pi / 2, 0) if axis_x else (0, 0, 0), n=8, bevel=0.001, segs=1)


def ply_wall(B, width, openings=(), H=3.0, T=0.12):
    st = 0.018
    xs = T / 2 - st / 2
    n = max(1, round(width / 1.3))
    sw = width / n
    rects = []
    for i in range(n):
        y0 = -width / 2 + i * sw
        rects += [(y0 + 0.0015, 0.0, y0 + sw - 0.0015, 2.44 - 0.0015), (y0 + 0.0015, 2.44 + 0.0015, y0 + sw - 0.0015, H)]
    for o in openings:
        rects = shapes.rect_sub(rects, o)
    for r in rects:
        B.box('MI_Plywood', (st, r[2] - r[0], r[3] - r[1]), (xs, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2), bevel=0.002,
              segs=1, uvoff=(random.random(), random.random()))
    # framing on the back
    sd = T - st - 0.002
    sx = -T / 2 + sd / 2
    sw_ = 0.038
    segs = [(-width / 2, width / 2)]
    for o in openings:
        if o[1] < 0.01:  # doorway: cut the bottom plate
            segs = [(a, b) for (a, b) in segs for (a, b) in ((a, min(b, o[0])), (max(a, o[2]), b)) if b - a > 0.01]
    for (a, b) in segs:
        B.box('MI_Timber', (sd, b - a, 0.038), (sx, (a + b) / 2, 0.019), bevel=0.003, grain='y')
    B.box('MI_Timber', (sd, width, 0.038), (sx, 0, H - 0.019), bevel=0.003, grain='y')
    B.box('MI_Timber', (sd, width, 0.038), (sx, 0, H - 0.057), bevel=0.003, grain='y')
    ys = []
    k = 0
    while True:
        y = -width / 2 + sw_ / 2 + k * 0.6
        if y > width / 2 - sw_ / 2 + 1e-6:
            break
        ys.append(y)
        k += 1
    if abs(ys[-1] - (width / 2 - sw_ / 2)) > 0.05:
        ys.append(width / 2 - sw_ / 2)
    for y in ys:
        blocked = [o for o in openings if o[0] - 0.02 < y < o[2] + 0.02]
        if not blocked:
            B.box('MI_Timber', (sd, sw_, H - 0.114), (sx, y, (H - 0.114) / 2 + 0.038), bevel=0.003, grain='z')
            screws(B, [(T / 2 + 0.0005, y, z) for z in [0.15 + i * 0.3 for i in range(10)]])
        else:
            o = blocked[0]
            if o[1] > 0.05:  # cripple below window
                B.box('MI_Timber', (sd, sw_, o[1] - 0.076), (sx, y, (o[1] - 0.076) / 2 + 0.038), bevel=0.003, grain='z')
            top = o[3] + 0.2
            if top < H - 0.114:
                B.box('MI_Timber', (sd, sw_, H - 0.076 - top), (sx, y, (H - 0.076 + top) / 2), bevel=0.003, grain='z')
    for o in openings:
        y0, z0, y1, z1 = o
        for y in (y0 - sw_ / 2, y1 + sw_ / 2, y0 - sw_ * 1.5, y1 + sw_ * 1.5):  # jack + king studs
            zt = z1 if abs(y - y0) < sw_ or abs(y - y1) < sw_ else H - 0.076
            B.box('MI_Timber', (sd, sw_, zt - 0.038), (sx, y, (zt + 0.038) / 2), bevel=0.003, grain='z')
        B.box('MI_Timber', (sd, y1 - y0 + 2 * sw_, 0.19), (sx, (y0 + y1) / 2, z1 + 0.095), bevel=0.003, grain='y')
        if z0 > 0.05:
            B.box('MI_Timber', (sd, y1 - y0, 0.038), (sx, (y0 + y1) / 2, z0 - 0.019), bevel=0.003, grain='y')
            # trim / sill board on the front
            B.box('MI_Timber', (0.03, y1 - y0 + 0.1, 0.03), (T / 2 + 0.012, (y0 + y1) / 2, z0 - 0.012), bevel=0.004,
                  grain='y')
    # noggins at 1.2 m between full-height members
    members = [y for y in ys if not [o for o in openings if o[0] - 0.02 < y < o[2] + 0.02]]
    for o in openings:
        members += [o[0] - sw_ * 1.5, o[2] + sw_ * 1.5]
    members = sorted(members)
    for a, b2 in zip(members[:-1], members[1:]):
        mid = (a + b2) / 2
        if b2 - a < 0.1 or any(o[0] - 0.1 < mid < o[2] + 0.1 for o in openings):
            continue
        B.box('MI_Timber', (sd, b2 - a - sw_, 0.038), (sx, mid, 1.2 + random.uniform(-0.03, 0.03)), bevel=0.003,
              grain='y')


def finish_arch(B, name):
    o = B.finish(name)
    return o


def corr_sheet(B, mat, length, width, M, pitch=0.076, depth=0.018, profile='sine', thick=0.0012):
    bm = shapes.corrugated_bm(length, width, pitch, depth, thick, profile=profile)
    B.add(bm, mat, M, grain='x')


def ladder_rungs(B, x, ys, z0, z1, step, r, mat, axis='y'):
    z = z0
    while z <= z1 + 1e-6:
        B.between(mat, (x, ys[0], z), (x, ys[1], z), r, n=12, bevel=0.001)
        z += step


# ----------------------------------------------------------------------------
# kit modules
# ----------------------------------------------------------------------------
def a_Wall_Plywood_4m():
    random.seed(1)
    B = Builder(arch=True)
    ply_wall(B, 4.0)
    return [('Body', 'Body', B.finish('Wall_Plywood_4m_Body'))], 50


def a_Wall_Plywood_Door_4m():
    random.seed(2)
    B = Builder(arch=True)
    ply_wall(B, 4.0, [(-0.6, 0.0, 0.6, 2.1)])
    return [('Body', 'Body', B.finish('Wall_Plywood_Door_4m_Body'))], 50


def a_Wall_Plywood_Window_4m():
    random.seed(3)
    B = Builder(arch=True)
    ply_wall(B, 4.0, [(-0.6, 1.2, 0.6, 1.8)])
    return [('Body', 'Body', B.finish('Wall_Plywood_Window_4m_Body'))], 50


def a_Wall_Plywood_2m():
    random.seed(4)
    B = Builder(arch=True)
    ply_wall(B, 2.0)
    return [('Body', 'Body', B.finish('Wall_Plywood_2m_Body'))], 50


def a_Wall_Concrete_4m():
    B = Builder(arch=True)
    T = 0.2
    bm = box_bm((T, 4.0, 3.0), bevel=0.025, segs=3, subdiv=24)
    B.add(bm, 'MI_Concrete', mtx((0, 0, 1.5)))
    # lifting anchors (recessed pockets) and a cast-in drainage notch
    for y in (-1.2, 1.2):
        B.box('MI_CorrodedMetal', (0.05, 0.05, 0.03), (0, y, 3.0 - 0.012), bevel=0.006)
        B.cyl('MI_CorrodedMetal', 0.012, 0.03, (0, y, 3.0 + 0.004), n=12, bevel=0.003)
    # chamfered kicker / plinth
    B.box('MI_Concrete', (T + 0.06, 4.0, 0.12), (0, 0, 0.06), bevel=0.02, segs=2)
    o = B.finish('Wall_Concrete_4m_Body')
    return [('Body', 'Body', o)], 50


def a_Roof_Corrugated_4m():
    B = Builder(arch=True)
    for x in (-1.85, -0.62, 0.62, 1.85):
        B.box('MI_Timber', (0.05, 4.0, 0.1), (x, 0, 0.05), bevel=0.004, grain='y')
    widths = [1.1] * 4
    y = -2.0
    random.seed(5)
    for i, w in enumerate(widths):
        yc = y + w / 2
        z = 0.1 + 0.009 + 0.0013 * i
        M = mtx((0, yc, z), (0, 0, 0))
        corr_sheet(B, 'MI_CorrodedMetal', 4.0, w, M)
        for x in (-1.85, -0.62, 0.62, 1.85):
            for k in range(7):
                yy = yc - w / 2 + 0.076 * (2 * k + 1) * 1.0 + 0.019
                if yy > yc + w / 2 - 0.02:
                    continue
                B.cyl('MI_PaintedSteel', 0.011, 0.003, (x, yy, z + 0.0105), n=10, bevel=0.0012, segs=1)
                B.cyl('MI_PaintedSteel', 0.005, 0.008, (x, yy, z + 0.015), n=6, bevel=0.001, segs=1)
        y += w - 0.1 * (4 * 1.1 - 4.0) / 0.3 if False else w - (4 * 1.1 - 4.0) / 3
    return [('Body', 'Body', B.finish('Roof_Corrugated_4m_Body'))], 50


def a_Post_Timber():
    B = Builder(arch=True)
    B.box('MI_Timber', (0.15, 0.15, 3.0), (0, 0, 1.5), bevel=0.01, segs=2, grain='z')
    # galvanised post base
    B.box('MI_PaintedSteel', (0.25, 0.25, 0.008), (0, 0, 0.004), bevel=0.003)
    for sx in (-1, 1):
        B.box('MI_PaintedSteel', (0.006, 0.16, 0.12), (sx * 0.078, 0, 0.068), bevel=0.002)
        for z in (0.04, 0.10):
            B.cyl('MI_CorrodedMetal', 0.008, 0.012, (sx * 0.084, 0, z), rot=(0, math.pi / 2, 0), n=6, bevel=0.002)
    return [('Body', 'Body', B.finish('Post_Timber_Body'))], 25


def deck(B, sx, sy, z0, gap_rect=None, seed=0):
    rnd = random.Random(seed)
    jd = 0.2
    for x in (-sx / 2 + 0.03, sx / 2 - 0.03, 0.0) if sx > 1.0 else (-sx / 2 + 0.03, sx / 2 - 0.03):
        B.box('MI_Timber', (0.05, sy, jd), (x, 0, z0 + jd / 2), bevel=0.004, grain='y')
    for y in (-sy / 2 + 0.025, sy / 2 - 0.025):
        B.box('MI_Timber', (sx, 0.05, jd), (0, y, z0 + jd / 2), bevel=0.004, grain='x')
    bw, g = 0.14, 0.006
    n = int(sy / (bw + g))
    off = (sy - n * (bw + g) + g) / 2
    for i in range(n):
        y = -sy / 2 + off + i * (bw + g) + bw / 2
        if gap_rect and gap_rect[0] < y < gap_rect[1]:
            x0, x1 = -sx / 2, gap_rect[2]
            L = x1 - x0
            B.box('MI_Timber', (L, bw, 0.028), ((x0 + x1) / 2, y, z0 + jd + 0.014 + rnd.uniform(-0.002, 0.002)),
                  rot=(rnd.uniform(-0.01, 0.01), 0, 0), bevel=0.004, grain='x')
            continue
        B.box('MI_Timber', (sx + rnd.uniform(-0.01, 0.01), bw, 0.028),
              (rnd.uniform(-0.005, 0.005), y, z0 + jd + 0.014 + rnd.uniform(-0.002, 0.002)),
              rot=(rnd.uniform(-0.01, 0.01), 0, rnd.uniform(-0.004, 0.004)), bevel=0.004, grain='x')
        for x in (-sx / 2 + 0.03, sx / 2 - 0.03):
            for dy in (-0.04, 0.04):
                B.cyl('MI_CorrodedMetal', 0.004, 0.002, (x, y + dy, z0 + jd + 0.0285), n=6, bevel=0.0, segs=1)


def a_Platform_Timber_4m():
    B = Builder(arch=True)
    deck(B, 1.2, 4.0, 0.0, seed=7)
    return [('Body', 'Body', B.finish('Platform_Timber_4m_Body'))], 50


def a_Ladder_Metal_4m():
    B = Builder(arch=True)
    for y in (-0.24, 0.24):
        B.box('MI_PaintedSteel', (0.065, 0.028, 4.0), (0, y, 2.0), bevel=0.004, segs=3, grain='z')
        B.box('MI_Rubber', (0.09, 0.05, 0.05), (0, y, 0.025), bevel=0.01)
        # top hooks
        B.box('MI_PaintedSteel', (0.18, 0.028, 0.04), (-0.07, y, 3.98), bevel=0.006)
        B.box('MI_PaintedSteel', (0.04, 0.028, 0.14), (-0.15, y, 3.92), bevel=0.006)
    z = 0.3
    while z < 3.9:
        B.between('MI_DiamondPlate', (0, -0.226, z), (0, 0.226, z), 0.017, n=28, bevel=0.002)
        for y in (-0.222, 0.222):
            B.between('MI_PaintedSteel', (0, y - 0.006, z), (0, y + 0.006, z), 0.024, n=28, bevel=0.002)
        z += 0.3
    return [('Body', 'Body', B.finish('Ladder_Metal_4m_Body'))], 50


# ----------------------------------------------------------------------------
# field structures
# ----------------------------------------------------------------------------
def a_Watchtower():
    rnd = random.Random(11)
    B = Builder(arch=True)
    D = 5.0  # deck top
    g, t = 1.55, 1.2
    legs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p0 = Vector((sx * g, sy * g, 0.0))
            p1 = Vector((sx * t, sy * t, D - 0.23))
            B.between('MI_Timber', p0, p1, 0, kind='box', w=(0.2, 0.2), bevel=0.012)
            legs.append((p0, p1))
            B.box('MI_Concrete', (0.45, 0.45, 0.25), (sx * g, sy * g, 0.02), bevel=0.03)
            # roof posts
            B.box('MI_Timber', (0.14, 0.14, 2.35), (sx * t, sy * t, D + 1.175), bevel=0.01, grain='z')

    def leg_at(sx, sy, z):
        p0 = Vector((sx * g, sy * g, 0.0))
        p1 = Vector((sx * t, sy * t, D - 0.23))
        return p0 + (p1 - p0) * (z / (D - 0.23))
    # girts + X braces on 4 sides
    for z in (0.5, 2.6, 4.6):
        for (a, b2) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            pa = leg_at(*a, z)
            pb = leg_at(*b2, z)
            n_ = Vector((pa.x + pb.x, pa.y + pb.y, 0)).normalized() * 0.13
            B.between('MI_Timber', pa + n_, pb + n_, 0, kind='box', w=(0.05, 0.15), bevel=0.005)
    for (z0, z1) in ((0.5, 2.6), (2.6, 4.6)):
        for (a, b2) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            for flip in (0, 1):
                pa = leg_at(*a, z0 if not flip else z1)
                pb = leg_at(*b2, z1 if not flip else z0)
                n_ = Vector((pa.x + pb.x, pa.y + pb.y, 0)).normalized() * (0.17 + 0.05 * flip)
                B.between('MI_Timber', pa + n_, pb + n_, 0, kind='box', w=(0.04, 0.12), bevel=0.004)
                for p in (pa + n_ * 1.25, pb + n_ * 1.25):
                    B.cyl('MI_PaintedSteel', 0.014, 0.02, p, n=6, bevel=0.003)
    # deck with hatch at the back
    deck(B, 2.7, 2.7, D - 0.228, gap_rect=(-0.35, 0.35, -0.55), seed=12)
    # half walls (plywood on timber rails)
    hw = 1.05
    for side in range(4):
        ang = side * math.pi / 2
        R = Matrix.Rotation(ang, 4, 'Z')
        if side == 2:  # back: opening above the hatch
            segs = [(-1.35, -0.45), (0.45, 1.35)]
        else:
            segs = [(-1.35, 1.35)]
        for (y0, y1) in segs:
            c = (y0 + y1) / 2
            w = y1 - y0
            loc = R @ Vector((1.34, c, D + hw / 2))
            B.add(box_bm((0.018, w, hw), 0.002, 1), 'MI_Plywood', Matrix.Translation(loc) @ R)
            loc = R @ Vector((1.37, c, D + hw + 0.025))
            B.add(box_bm((0.09, w + 0.04, 0.05), 0.006, 2), 'MI_Timber', Matrix.Translation(loc) @ R, grain='y')
        if side == 0:  # shooting slot frame
            pass
    # roof: pitched corrugated, ridge along Y
    rz = D + 2.35
    for sx in (-1, 1):
        B.box('MI_Timber', (0.1, 3.0, 0.15), (sx * t, 0, rz - 0.05), bevel=0.008, grain='y')
    B.box('MI_Timber', (0.08, 3.0, 0.15), (0, 0, rz + 0.45), bevel=0.008, grain='y')
    for y in (-1.2, 0, 1.2):
        for sx in (-1, 1):
            p0 = Vector((sx * 1.75, y, rz - 0.15))
            p1 = Vector((0, y, rz + 0.5))
            B.between('MI_Timber', p0, p1, 0, kind='box', w=(0.05, 0.12), bevel=0.004)
    for sx in (-1, 1):
        ang = math.atan2(0.62, 1.75)
        M = mtx((sx * 0.9, 0, rz + 0.25 + 0.02), (0, sx * ang, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Z')
        corr_sheet(B, 'MI_CorrodedMetal', 3.2, 1.95, M)
    # timber ladder at the back
    lx0, lx1 = -2.6, -0.55
    for y in (-0.28, 0.28):
        B.between('MI_Timber', (lx0, y, 0.0), (lx1, y, D + 0.9), 0, kind='box', w=(0.05, 0.12), bevel=0.005,
                  roll=0.0)
    n = 16
    for i in range(1, n):
        f = i / n
        x = lx0 + (lx1 - lx0) * f
        z = (D + 0.9) * f
        B.box('MI_Timber', (0.1, 0.62, 0.035), (x, 0, z), rot=(0, 0, 0), bevel=0.005, grain='y')
    return [('Body', 'Body', B.finish('Watchtower_Body'))], 100


def a_FloodlightTower():
    B = Builder(arch=True)
    B.box('MI_Concrete', (1.0, 1.0, 0.45), (0, 0, 0.075), bevel=0.04, segs=3)
    B.box('MI_PaintedSteel', (0.5, 0.5, 0.025), (0, 0, 0.3125), bevel=0.006)
    for sx in (-1, 1):
        for sy in (-1, 1):
            B.cyl('MI_CorrodedMetal', 0.012, 0.12, (sx * 0.19, sy * 0.19, 0.36), n=10, bevel=0.002)
            B.cyl('MI_CorrodedMetal', 0.022, 0.02, (sx * 0.19, sy * 0.19, 0.335), n=6, bevel=0.003)
    for a in range(4):
        R = Matrix.Rotation(a * math.pi / 2 + math.pi / 4, 4, 'Z')
        bm = box_bm((0.18, 0.012, 0.22), 0.003, 1)
        B.add(bm, 'MI_PaintedSteel', Matrix.Translation(R @ Vector((0.17, 0, 0.435))) @ R)
    # tapered pole
    B.add(cyl_bm(0.11, 9.7, 64, 0.01, 3, r2=0.07), 'MI_PaintedSteel', mtx((0, 0, 0.325 + 4.85)), grain='z')
    B.box('MI_PaintedSteel', (0.02, 0.12, 0.35), (-0.112, 0, 1.0), bevel=0.004)  # access door
    # step bolts
    for i in range(18):
        z = 2.6 + i * 0.38
        a = (i % 2) * math.pi
        rr = 0.11 - (z - 0.3) / 9.7 * 0.04
        d = Vector((math.cos(a + math.pi / 2), math.sin(a + math.pi / 2), 0))
        B.between('MI_CorrodedMetal', d * rr, d * (rr + 0.17), 0.009, n=8, bevel=0.0)
        B.between('MI_CorrodedMetal', d * (rr + 0.16), d * (rr + 0.16) + Vector((0, 0, 0.05)), 0.009, n=8, bevel=0.0)
    # conduit + junction box
    B.cyl('MI_PaintedSteel', 0.016, 8.3, (-0.12, 0.0, 1.5 + 4.15), n=10, bevel=0.0)
    B.box('MI_PaintedSteel', (0.12, 0.25, 0.35), (-0.16, 0, 1.35), bevel=0.015)
    # head
    hz = 9.75
    B.box('MI_PaintedSteel', (0.08, 1.9, 0.08), (0.08, 0, hz), bevel=0.006, grain='y')
    B.box('MI_PaintedSteel', (0.08, 1.9, 0.08), (0.08, 0, hz + 0.55), bevel=0.006, grain='y')
    B.box('MI_PaintedSteel', (0.12, 0.2, 0.7), (0.0, 0, hz + 0.2), bevel=0.01)
    glass = Builder(arch=True)
    for i, y in enumerate((-0.68, -0.23, 0.23, 0.68)):
        z = hz + 0.28
        tilt = math.radians(28)
        M = mtx((0.32, y, z), (0, tilt, 0))
        # housing: deep box with cooling fins at back
        B.add(box_bm((0.16, 0.4, 0.36), 0.02, 3), 'MI_PaintedSteel', M @ mtx((0, 0, 0)))
        for k in range(7):
            B.add(box_bm((0.06, 0.006, 0.32), 0.001, 1), 'MI_PaintedSteel', M @ mtx((-0.1, -0.15 + k * 0.05, 0)))
        # bezel
        B.add(box_bm((0.03, 0.42, 0.38), 0.008, 2), 'MI_PaintedSteel', M @ mtx((0.085, 0, 0)))
        # reflector inside (recessed), lens in the Glass piece
        B.add(box_bm((0.005, 0.34, 0.3), 0.0, 1), 'MI_Brass', M @ mtx((0.07, 0, 0)))
        glass.add(box_bm((0.008, 0.35, 0.31), 0.002, 1), 'M_FloodlightTower_Lamp', M @ mtx((0.098, 0, 0)))
        # yoke
        for sy in (-1, 1):
            B.add(box_bm((0.04, 0.012, 0.3), 0.002, 1), 'MI_PaintedSteel', mtx((0.26, y + sy * 0.215, z + 0.0)))
        B.add(box_bm((0.25, 0.04, 0.04), 0.005, 1), 'MI_PaintedSteel', mtx((0.17, y, hz + 0.05)))
    body = B.finish('FloodlightTower_Body')
    g = glass.finish('FloodlightTower_Glass')
    return [('Body', 'Body', body), ('Glass', 'Glass', g)], 100


def grid_panel(B, mat, fn, nu, nv, thick=0.004):
    """Build a cloth panel from fn(u,v)->Vector over a grid, solidified."""
    bm = bmesh.new()
    vs = [[bm.verts.new(fn(i / nu, j / nv)) for j in range(nv + 1)] for i in range(nu + 1)]
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    bm.normal_update()
    if thick:
        res = bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=thick)
    B.add(bm, mat, None, grain='x')


def a_SpawnTent():
    import numpy as np
    B = Builder(arch=True)
    L, Wd, eave, ridge = 6.0, 4.0, 1.6, 2.9
    rng = np.random.default_rng(5)

    def wr(p, amp=0.012, f=1.6, seed=0):
        n = geo.fbm3(np.array([p]) * f, 1.0, 3, 0.5, seed)[0]
        return n * amp

    poles_x = (-3.0, 0.0, 3.0)

    def sag_x(x):
        # sag between poles along the ridge / eaves
        d = min(abs(x - px) for px in poles_x)
        return math.sin(min(d / 3.0, 1.0) * math.pi / 2) * 0.12

    for sy in (-1, 1):
        def roof(u, v, sy=sy):
            x = (u - 0.5) * (L + 0.2)
            y = sy * (Wd / 2 + 0.08) * (1 - v)
            z = eave + (ridge - eave) * v
            z -= sag_x(x) * math.sin(v * math.pi) * 1.3 + 0.04 * math.sin(v * math.pi)
            p = Vector((x, y, z))
            p.z += wr(p, 0.03, 2.0, 1) + wr(p, 0.008, 7.0, 5)
            return p
        grid_panel(B, 'MI_Canvas', roof, 120, 40)

        def wall(u, v, sy=sy):
            x = (u - 0.5) * L
            z = eave * v
            y = sy * (Wd / 2 + 0.05 * (1 - v) ** 3)
            y += sy * (-sag_x(x) * 0.5 * math.sin(v * math.pi))
            p = Vector((x, y, z))
            p.y += wr(p, 0.03, 2.2, 2) + wr(p, 0.008, 7.0, 6)
            return p
        grid_panel(B, 'MI_Canvas', wall, 120, 28)
    for sx in (-1, 1):
        def end(u, v, sx=sx):
            y = (u - 0.5) * Wd
            ztop = eave + (ridge - eave) * (1 - abs(y) / (Wd / 2))
            z = ztop * v
            x = sx * (L / 2 + 0.02 * math.sin(v * math.pi))
            p = Vector((x, y, z))
            p.x += wr(p, 0.025, 2.5, 3) + wr(p, 0.006, 7.0, 7)
            return p
        bm = bmesh.new()
        nu, nv = 60, 40
        vs = [[bm.verts.new(end(i / nu, j / nv)) for j in range(nv + 1)] for i in range(nu + 1)]
        for i in range(nu):
            for j in range(nv):
                c = (vs[i][j].co + vs[i + 1][j + 1].co) / 2
                if sx > 0 and abs(c.y) < 0.65 and c.z < 1.95:
                    continue  # door opening
                bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
        bm.normal_update()
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
        bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.004)
        B.add(bm, 'MI_Canvas', None)
    # rolled door flap
    B.add(cyl_bm(0.075, 1.5, 16, 0.0, 1), 'MI_Canvas', mtx((L / 2 + 0.09, 0, 2.02), (math.pi / 2, 0, 0)), grain='z')
    for sy in (-0.6, 0.6):
        B.between('MI_Burlap', (L / 2 + 0.09, sy, 2.1), (L / 2 + 0.17, sy, 1.95), 0.006, n=6, bevel=0)
    # poles
    for x in poles_x:
        B.cyl('MI_Timber', 0.035, ridge - 0.02, (x * 0.98, 0, (ridge - 0.02) / 2), n=12, bevel=0.005)
    B.cyl('MI_Timber', 0.03, L, (0, 0, ridge - 0.05), rot=(0, math.pi / 2, 0), n=12, bevel=0.005)
    for x in (-3.0, -1.5, 0.0, 1.5, 3.0):
        for sy in (-1, 1):
            B.cyl('MI_Timber', 0.025, eave, (x * 0.99, sy * (Wd / 2 - 0.02), eave / 2), n=10, bevel=0.004)
            # guy rope + stake
            top = Vector((x, sy * (Wd / 2 + 0.1), eave + 0.05))
            stake = Vector((x * 1.05, sy * (Wd / 2 + 1.4), 0.08))
            B.between('MI_Burlap', top, stake, 0.005, n=6, bevel=0)
            B.between('MI_PaintedSteel', stake + Vector((0, 0, -0.1)), stake + Vector((0, sy * -0.02, 0.18)), 0.012,
                      n=8, bevel=0.002)
    # sod cloth on the ground
    for sy in (-1, 1):
        B.box('MI_Canvas', (L, 0.25, 0.006), (0, sy * (Wd / 2 + 0.12), 0.003), bevel=0.002)
    return [('Body', 'Body', B.finish('SpawnTent_Body'))], 100


def a_NettingFence_4m():
    import numpy as np
    B = Builder(arch=True)
    H = 3.3
    for y in (-2.0, 2.0):
        B.cyl('MI_PaintedSteel', 0.045, H, (0, y, H / 2), n=20, bevel=0.004)
        B.cyl('MI_PaintedSteel', 0.05, 0.03, (0, y, H + 0.01), n=20, bevel=0.008)
        B.cyl('MI_Concrete', 0.16, 0.08, (0, y, 0.02), n=24, bevel=0.02, r2=0.12)
        for z in (0.1, 3.0):
            B.cyl('MI_CorrodedMetal', 0.052, 0.04, (0, y, z), n=16, bevel=0.004)
    for z in (0.1, 3.0):
        B.between('MI_CorrodedMetal', (0.05, -2.0, z), (0.05, 2.0, z - 0.0), 0.004, n=6, bevel=0)
    body = B.finish('NettingFence_4m_Body')
    N = Builder(arch=True)
    nu, nv = 48, 36
    bm = bmesh.new()
    vs = []
    for i in range(nu + 1):
        row = []
        for j in range(nv + 1):
            y = -1.96 + 3.92 * i / nu
            z = 0.1 + 2.9 * j / nv
            sag = math.sin(i / nu * math.pi) * 0.06 * math.sin(j / nv * math.pi)
            p = Vector((0.06 + sag, y, z - 0.02 * math.sin(i / nu * math.pi) * (j / nv)))
            p.x += geo.fbm3(np.array([[y, z, 0.0]]) * 1.3, 1.0, 3, 0.5, 4)[0] * 0.05
            row.append(bm.verts.new(p))
        vs.append(row)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    N.add(bm, 'MI_Netting', None)
    net = N.finish('NettingFence_4m_Net')
    return [('Body', 'Body', body), ('Net', 'Static', net)], 400


def a_Bunker_Logs():
    B = Builder(arch=True)
    rnd = random.Random(21)
    S = 6.0
    r = 0.15
    h = 2 * r * 0.88
    courses = 5
    for c in range(courses):
        z = r + c * h
        for side in range(4):
            along_x = side % 2 == 0
            ext = 0.25 if (c + side) % 2 == 0 else -0.05
            L = S + ext
            pos = (S / 2 - r)
            if along_x:
                y = pos * (1 if side == 0 else -1)
                if side == 2 and c < 4:  # entrance in back (-Y side? use -X) handled below
                    pass
                segs = [(-L / 2, L / 2)]
                cx, cy, rot = 0, y, (0, 0, 0)
            else:
                x = pos * (1 if side == 1 else -1)
                segs = [(-L / 2, L / 2)]
                cx, cy, rot = x, 0, (0, 0, math.pi / 2)
            # front wall (+X) firing slit at course 3
            if side == 1 and c == 3:
                segs = [(-L / 2, -1.6), (1.6, L / 2)]
            # entrance in back wall (-X)
            if side == 3 and c < 4:
                segs = [(-L / 2, -0.55), (0.55, L / 2)]
            for (a, b2) in segs:
                ln = b2 - a
                mid = (a + b2) / 2
                bm = shapes.log_bm(ln, r * rnd.uniform(0.9, 1.08), rnd.randint(0, 10000), n=18)
                if along_x:
                    M = mtx((mid, cy, z), (rnd.uniform(-0.02, 0.02), 0, rnd.uniform(-0.01, 0.01)))
                else:
                    M = mtx((cx, mid, z), (0, 0, math.pi / 2 + rnd.uniform(-0.01, 0.01)))
                B.add(bm, 'MI_Bark', M, grain='x', cap_mat='MI_Timber', cap_axis=0)
    # door frame posts
    for y in (-0.6, 0.6):
        B.box('MI_Timber', (0.2, 0.15, 1.4), (-S / 2 + r, y, 0.7), bevel=0.01, grain='z')
    # roof logs across
    zr = 2 * r + (courses - 1) * h + 0.105
    n = 22
    for i in range(n):
        y = -S / 2 + 0.1 + i * (S - 0.2) / (n - 1)
        bm = shapes.log_bm(S + 0.4 + rnd.uniform(-0.2, 0.2), 0.12 * rnd.uniform(0.9, 1.1), rnd.randint(0, 9999), n=16)
        B.add(bm, 'MI_Bark', mtx((rnd.uniform(-0.1, 0.1), y, zr), (0, 0, rnd.uniform(-0.03, 0.03))), grain='x',
              cap_mat='MI_Timber', cap_axis=0)
    # sandbags on the roof (two layers) and along the front base
    k = 0
    ztop = zr + 0.11
    for layer in range(2):
        for i in range(10):
            for j in range(9):
                if layer == 1 and (i in (0, 9) or j in (0, 8)):
                    continue
                x = -S / 2 + 0.35 + i * 0.58 + (0.29 if (j + layer) % 2 else 0) - 0.15
                y = -S / 2 + 0.35 + j * 0.66
                if abs(x) > S / 2 or abs(y) > S / 2:
                    continue
                bm = shapes.sandbag_bm(1000 + k, cuts=9)
                B.add(bm, 'MI_Burlap', mtx((x, y, ztop + layer * 0.11), (0, 0, rnd.uniform(-0.15, 0.15) + (math.pi / 2 if layer else 0))))
                k += 1
    for c in range(3):
        for i in range(11):
            y = -S / 2 + 0.3 + i * 0.55 + (0.27 if c % 2 else 0)
            if y > S / 2 - 0.2:
                continue
            if c == 2 and abs(y) < 1.8:
                continue
            bm = shapes.sandbag_bm(3000 + k, cuts=9)
            B.add(bm, 'MI_Burlap', mtx((S / 2 + 0.22, y, c * 0.11), (0, 0, math.pi / 2 + rnd.uniform(-0.1, 0.1))))
            k += 1
    return [('Body', 'Body', B.finish('Bunker_Logs_Body'))], 100


# ----------------------------------------------------------------------------
# container (baked unique)
# ----------------------------------------------------------------------------
CONT_RECIPES = {
    'paint': dict(base='PaintedSteel', paint=(0.88, 0.88, 0.88), chip=0.55, chip_scale=7.0, under='CorrodedMetal',
                  paint_rough=0.5, edge=0.25, dirt=0.6, ground=0.5, streak=0.55, streak_col=(0.3, 0.14, 0.06),
                  mask=(1, 0, 0), mask_paint_only=True, edge_r=0.01),
    'steel': dict(base='PaintedSteel', tint=(0.35, 0.35, 0.35), edge=0.5, dirt=0.7, ground=0.4, streak=0.3,
                  hue=(0.2, 0.6)),
    'rust': dict(base='CorrodedMetal', edge=0.2, dirt=0.6),
    'wood': dict(base='Timber', tint=(0.55, 0.45, 0.35), dirt=0.8),
    'rubber': dict(base='Rubber', dirt=0.4),
}


# corrugated sheet local axes (X ribs, Y waves, Z normal) -> wall orientations
SIDE = Matrix(((0, 1, 0), (0, 0, 1), (1, 0, 0))).to_4x4()   # ribs vertical, waves along X, normal Y
END = Matrix(((0, 0, -1), (0, 1, 0), (1, 0, 0))).to_4x4()   # ribs vertical, waves along Y, normal X


def a_Container_20ft():
    B = Builder(uvtex=True)
    L, W, H = 6.058, 2.438, 2.591
    cc = (0.178, 0.162, 0.118)
    # corner castings with apertures
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (0, 1):
                bm = box_bm(cc, 0.006, 2)
                faces = [f for f in bm.faces if abs(f.normal.x) > 0.9 or abs(f.normal.y) > 0.9 or abs(f.normal.z) > 0.9]
                outs = [f for f in faces if (f.normal.x * sx > 0.9) or (f.normal.y * sy > 0.9) or
                        (f.normal.z * (1 if sz else -1) > 0.9)]
                outs = [f for f in outs if f.calc_area() > 0.01]
                for f in outs:
                    rr = bmesh.ops.inset_region(bm, faces=[f], thickness=0.03, depth=-0.025)
                B.add(bm, 'steel', mtx((sx * (L / 2 - cc[0] / 2), sy * (W / 2 - cc[1] / 2), cc[2] / 2 if sz == 0 else H - cc[2] / 2)))
            # corner posts
            B.box('steel', (0.15, 0.15, H - 2 * cc[2]), (sx * (L / 2 - 0.08), sy * (W / 2 - 0.08), H / 2), bevel=0.008,
                  grain='z')
    # rails
    for sy in (-1, 1):
        B.box('steel', (L - 2 * cc[0], 0.08, 0.16), (0, sy * (W / 2 - 0.04), 0.08), bevel=0.008)
        B.box('steel', (L - 2 * cc[0], 0.1, 0.06), (0, sy * (W / 2 - 0.05), H - 0.03), bevel=0.008)
    for sx in (-1, 1):
        B.box('steel', (0.12, W - 2 * cc[1], 0.16), (sx * (L / 2 - 0.06), 0, 0.08), bevel=0.008, grain='y')
        B.box('steel', (0.12, W - 2 * cc[1], 0.12), (sx * (L / 2 - 0.06), 0, H - 0.06), bevel=0.008, grain='y')
    # side walls: trapezoid corrugation, ribs vertical
    wh = H - 0.16 - 0.06
    for sy in (-1, 1):
        bm = shapes.corrugated_bm(wh, L - 0.32, pitch=0.278, depth=0.036, thick=0.002, nl=6, profile='trap')
        M = mtx((0, sy * (W / 2 - 0.03), 0.16 + wh / 2)) @ SIDE
        B.add(bm, 'paint', M, grain='x')
    # back end wall (-X)
    bm = shapes.corrugated_bm(wh, W - 0.32, pitch=0.278, depth=0.036, thick=0.002, nl=6, profile='trap')
    M = mtx((-L / 2 + 0.05, 0, 0.16 + wh / 2)) @ END
    B.add(bm, 'paint', M, grain='x')
    # roof (shallow corrugation across X)
    bm = shapes.corrugated_bm(W - 0.2, L - 0.3, pitch=0.25, depth=0.015, thick=0.002, nl=4, profile='sine')
    B.add(bm, 'paint', mtx((0, 0, H - 0.02), (0, 0, math.pi / 2)), grain='x')
    # floor plate
    B.box('wood', (L - 0.2, W - 0.2, 0.03), (0, 0, 0.13), bevel=0.003)
    # doors (+X)
    dw = (W - 0.3) / 2
    dh = H - 0.28
    for sy in (-1, 1):
        yc = sy * dw / 2
        x = L / 2 - 0.05
        B.box('paint', (0.04, dw - 0.02, dh), (x, yc, 0.14 + dh / 2), bevel=0.012)
        # door panel corrugation (inset, vertical ribs)
        bm = shapes.corrugated_bm(dh - 0.24, dw - 0.2, pitch=0.24, depth=0.03, thick=0.002, nl=4, profile='trap')
        M = mtx((x + 0.028, yc, 0.14 + dh / 2)) @ END
        B.add(bm, 'paint', M, grain='x')
        # frame rails on the door leaf
        for z in (0.2, 0.14 + dh - 0.06):
            B.box('paint', (0.05, dw - 0.02, 0.1), (x + 0.03, yc, z), bevel=0.01, grain='y')
        for yy in (yc - sy * (dw / 2 - 0.05), yc + sy * (dw / 2 - 0.05)):
            B.box('paint', (0.05, 0.09, dh - 0.1), (x + 0.03, yy, 0.14 + dh / 2), bevel=0.01, grain='z')
        # locking bars (2 per leaf)
        for k, yy in enumerate((yc - sy * 0.18, yc + sy * 0.25)):
            B.cyl('steel', 0.016, dh + 0.12, (x + 0.085, yy, 0.14 + dh / 2), n=14, bevel=0.003, grain='z')
            for z in (0.12, 0.14 + dh + 0.0):
                B.box('steel', (0.07, 0.07, 0.08), (x + 0.07, yy, z), bevel=0.008)
            for z in (0.6, 1.4, 2.1):
                B.box('steel', (0.03, 0.06, 0.04), (x + 0.07, yy, z), bevel=0.005)
            # handle
            B.box('steel', (0.03, 0.035, 0.36), (x + 0.11, yy - sy * 0.12, 1.15), rot=(0.3 * sy, 0, 0), bevel=0.008)
            B.box('steel', (0.06, 0.03, 0.04), (x + 0.1, yy, 1.32), bevel=0.006)
        # hinges
        for z in (0.35, 1.0, 1.65, 2.25):
            B.cyl('steel', 0.022, 0.13, (x + 0.04, sy * (W / 2 - 0.16), z), n=12, bevel=0.003)
        # gasket
        B.box('rubber', (0.02, 0.02, dh), (x - 0.01, sy * 0.012, 0.14 + dh / 2), bevel=0.005, grain='z')
    # CSC plate
    B.box('steel', (0.006, 0.3, 0.2), (L / 2 - 0.0, -dw / 2, 1.8), bevel=0.002)
    # forklift pockets on the sides
    for sy in (-1, 1):
        for xx in (-1.0, 1.0):
            B.box('steel', (0.36, 0.02, 0.12), (xx, sy * (W / 2 - 0.0), 0.08), bevel=0.004)
    body = B.finish('Container_20ft_Body')
    return [('Body', 'Body', body)], 10, {'Body': CONT_RECIPES}


ASSETS = ['Wall_Plywood_4m', 'Wall_Plywood_Door_4m', 'Wall_Plywood_Window_4m', 'Wall_Plywood_2m',
          'Wall_Concrete_4m', 'Roof_Corrugated_4m', 'Post_Timber', 'Platform_Timber_4m', 'Ladder_Metal_4m',
          'Container_20ft', 'Watchtower', 'FloodlightTower', 'SpawnTent', 'NettingFence_4m', 'Bunker_Logs']


def setup_lib_materials(obj):
    """Assign library render materials (MI_<Id>, UVs in 2 m units)."""
    me = obj.data
    for i, m in enumerate(me.materials):
        if m.name.startswith('MI_'):
            mid = m.name[3:]
            nm = bl.lib_material(mid, uv_scale=2.0 / bl.lib_tile(mid), name=m.name + '_R')
            me.materials[i] = nm
        elif m.name == 'M_FloodlightTower_Lamp':
            me.materials[i] = bl.simple_material('M_FloodlightTower_Lamp_R', (0.9, 0.92, 0.95), 0.05, 0.0,
                                                 transmission=0.9, emission=(1.0, 0.92, 0.75, 8.0))


def rename_slots_for_export(obj):
    me = obj.data
    for i, m in enumerate(me.materials):
        if m.name.endswith('_R'):
            base = m.name[:-2]
            mm = bpy.data.materials.get(base) or bpy.data.materials.new(base)
            me.materials[i] = mm


def build(aid, res, opts):
    bl.reset()
    fn = globals()['a_' + aid]
    r = fn()
    pieces, snap = r[0], r[1]
    recipes = r[2] if len(r) > 2 else {}
    out = bl.ensure(os.path.join(OUT, aid))
    entry = {'Pieces': [], 'Snap': snap}
    objs = []
    tris = 0
    for (pname, kind, obj) in pieces:
        if pname in recipes:
            rec = recipes[pname]
            for i, m in enumerate(obj.data.materials):
                obj.data.materials[i] = bake.recipe_material('%s_%s_%s' % (aid, pname, m.name), rec[m.name])
            geo.smart_uv(obj, margin=0.003)
            prefix = os.path.join(out, 'T_%s_%s' % (aid, pname))
            want_m = any(rec[s].get('mask') for s in rec)
            bake.bake_piece(obj, prefix, res, mask_res=min(1024, res), want_mask=want_m)
            slot = 'M_%s_%s' % (aid, pname)
            bake.finalize_piece(obj, slot, prefix, has_mask=want_m, tint=(0.05, 0.13, 0.22) if want_m else None)
            slots = [slot]
        else:
            slots = [m.name for m in obj.data.materials]
        if opts['export']:
            rename_slots_for_export(obj) if pname not in recipes else None
            if pname in recipes:
                # export with the bare slot name (material named exactly M_<Id>_<Piece>)
                m = obj.data.materials[0]
                keep = m.name
            bl.export_fbx(obj, os.path.join(out, 'SM_%s_%s.fbx' % (aid, pname)))
        if pname not in recipes:
            setup_lib_materials(obj)
        t = bl.tri_count(obj)
        tris += t
        pe = {'Name': pname, 'Kind': kind, 'Slots': slots, 'Triangles': t}
        if pname in recipes:
            pe['Textures'] = {k: 'Architecture/%s/T_%s_%s_%s.png' % (aid, aid, pname, k)
                              for k in ('BC', 'N', 'ORM', 'M') if os.path.exists(os.path.join(out, 'T_%s_%s_%s.png' % (aid, pname, k)))}
        entry['Pieces'].append(pe)
        objs.append(obj)
    entry['Bounds'] = bl.bounds_ue(objs)
    print('  %-24s tris=%d' % (aid, tris), flush=True)
    import json
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(bl.ensure(SCRATCH), aid + '.blend'), compress=False)
    json.dump(entry, open(os.path.join(SCRATCH, aid + '.json'), 'w'))
    return render_asset(aid, objs, entry, opts)


def resume(aid, opts):
    import json
    import time
    b = os.path.join(SCRATCH, aid + '.blend')
    j = os.path.join(SCRATCH, aid + '.json')
    if not (os.path.exists(b) and os.path.exists(j) and time.time() - os.path.getmtime(j) < 3 * 3600):
        return None
    bpy.ops.wm.open_mainfile(filepath=b)
    objs = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.name.startswith('Cyc')]
    return render_asset(aid, objs, json.load(open(j)), opts)


def render_asset(aid, objs, entry, opts):
    if opts['render']:
        az = -40.0
        el = 14.0
        if aid.startswith('Wall') or aid in ('Ladder_Metal_4m', 'NettingFence_4m'):
            az, el = -32.0, 10.0
        if aid == 'Roof_Corrugated_4m' or aid == 'Platform_Timber_4m':
            el = 28.0
        bl.product_shot(objs, os.path.join(bl.RENDERS, CAT, aid + '.png'), az=az, el=el, samples=opts['samples'] or 7,
                        margin=1.12)
        if aid == 'Wall_Plywood_Door_4m' and not opts['preview']:
            bl.clear_scene_extras()
            bl.product_shot(objs, os.path.join(bl.RENDERS, CAT, aid + '_Back.png'), az=180 - 35.0, el=10.0,
                            samples=opts['samples'] or 16, margin=1.12)
    return entry


SCRATCH = os.environ.get('ENV_SCRATCH', os.path.join(__import__('tempfile').gettempdir(), 'airsoft_env_cache'))


def lineup(ids, cat, out_name='_Lineup_4K.png', cols=5, spacing=1.0):
    bl.reset()
    objs = []
    x = 0.0
    rows = [ids[i:i + cols] for i in range(0, len(ids), cols)]
    yrow = 0.0
    from mathutils import Vector
    placed = []
    row_depth = 0
    for r, row in enumerate(rows):
        y = 0.0
        maxd = 0
        for aid in row:
            path = os.path.join(SCRATCH, aid + '.blend')
            if not os.path.exists(path):
                continue
            with bpy.data.libraries.load(path, link=False) as (src, dst):
                dst.objects = [n for n in src.objects if not (n.startswith('Cam') or n in ('Key', 'Fill', 'Rim', 'Cyc'))]
            group = [o for o in dst.objects if o is not None and o.type == 'MESH']
            for o in group:
                bpy.context.scene.collection.objects.link(o)
            pts = bl.bbox_world(group)
            lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
            hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
            w = hi.y - lo.y
            d = hi.x - lo.x
            off = Vector((-yrow - (lo.x + hi.x) / 2, -(y + w / 2) - (lo.y + hi.y) / 2, 0))
            for o in group:
                o.location = o.location + off
            y += w + spacing
            maxd = max(maxd, d)
            objs += group
        yrow += maxd + spacing * 1.5
    # recentre
    bpy.context.view_layer.update()
    pts = bl.bbox_world(objs)
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2
    for o in objs:
        o.location.x -= c.x
        o.location.y -= c.y
    bpy.context.view_layer.update()
    bl.product_shot(objs, os.path.join(bl.RENDERS, cat, out_name), az=-35.0, el=22.0, lens=50, samples=12, margin=1.03,
                    w=3840, h=2160, tex_limit='1024')


def main():
    o = bl.parse_args()
    ids = o['ids'] or ASSETS
    if not o['lineup_only']:
        for aid in ids:
            e = resume(aid, o) if '--resume' in sys.argv else None
            e = e or build(aid, o['res'], o)
            bl.json_update('Architecture.json', 'Assets', {aid: e},
                       extra={'Notes': 'Unreal cm. Origin = floor centre, front +X. MI_* slots use Materials.json '
                                       '(UVs: 1 UV = 2 m -> tiling ArchUVScale). Snap = grid size in cm.'})
    if o['lineup'] and o['render']:
        lineup(['Post_Timber', 'Ladder_Metal_4m', 'Wall_Plywood_2m', 'Wall_Plywood_4m', 'Wall_Plywood_Door_4m',
                'Wall_Plywood_Window_4m', 'Wall_Concrete_4m', 'Platform_Timber_4m', 'Roof_Corrugated_4m',
                'NettingFence_4m', 'Container_20ft', 'SpawnTent', 'Bunker_Logs', 'Watchtower', 'FloodlightTower'],
               CAT, cols=5, spacing=1.0)


if __name__ == '__main__':
    main()
