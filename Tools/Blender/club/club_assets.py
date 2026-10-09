"""Velvet Club props (bar, lounge, DJ, lighting, street)."""

import math
import random
from mathutils import Vector as V, Matrix

import bpy
import propkit as pk
from propkit import round_poly, circle_pts, rrect_pts, catmull
from club_registry import asset, font


def ring_path(r, z, n=48, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n), z) for i in range(n)]


def warm_point(loc, energy=30.0, color=(1.0, 0.75, 0.45), radius=0.03):
    def f(scn):
        ld = bpy.data.lights.new("prac", "POINT")
        ld.energy = energy
        ld.color = color
        ld.shadow_soft_size = radius
        o = bpy.data.objects.new("prac", ld)
        o.location = loc
        scn.collection.objects.link(o)
    return f


# ======================================================================================
# Bar stool: brass pedestal, foot ring, swivel, leather seat with welt and low back
# ======================================================================================


@asset("BarStool", res=2048, collision="Convex", edge=0.003, ao_dist=0.15)
def bar_stool(A):
    # weighted base: stepped brass disc
    A.lathe(round_poly([(0, 0), (0.235, 0), (0.24, 0.006), (0.236, 0.016), (0.20, 0.026), (0.07, 0.034), (0.045, 0.05), (0, 0.05)], 0.004, closed=False), mat="brass", n=64)
    A.cyl(0.229, 0.004, at=(0, 0, -0.002), mat="rubber", n=64, bevel=0.0015)
    # column with collar
    A.lathe([(0, 0.045), (0.032, 0.045), (0.032, 0.60), (0.034, 0.605), (0.034, 0.62), (0, 0.62)], mat="brass_polished", n=40)
    A.lathe(round_poly([(0, 0.27), (0.045, 0.27), (0.045, 0.31), (0, 0.31)], 0.004, closed=False), mat="brass", n=40)
    # foot ring + 4 struts
    A.sweep(ring_path(0.21, 0.29, 72), r=0.0125, n=16, mat="brass_polished", closed=True)
    for i in range(4):
        a = math.radians(45 + 90 * i)
        p0 = (0.04 * math.cos(a), 0.04 * math.sin(a), 0.29)
        p1 = (0.20 * math.cos(a), 0.20 * math.sin(a), 0.29)
        A.sweep([p0, p1], r=0.008, n=12, mat="brass")
    # swivel housing
    A.cyl(0.09, 0.035, at=(0, 0, 0.62), mat="powder_black", n=40, bevel=0.004)
    A.cyl(0.17, 0.012, at=(0, 0, 0.655), mat="steel_dark", n=48, bevel=0.003)
    # seat pan (brass skirt) + cushion
    A.lathe(round_poly([(0, 0.665), (0.205, 0.665), (0.215, 0.672), (0.215, 0.70), (0, 0.70)], 0.004, closed=False), mat="brass", n=64)
    prof = [(0, 0.698), (0.212, 0.698)]
    for i in range(10):
        a = math.radians(-90 + 180 * i / 9)
        prof.append((0.212 + 0.018 * math.cos(a) * 0.55, 0.722 + 0.022 * math.sin(a)))
    prof += [(0.18, 0.758), (0.12, 0.766), (0.0, 0.770)]
    A.lathe(prof, mat="leather_oxblood", n=72, smooth=180)
    A.sweep(ring_path(0.2225, 0.722, 96), r=0.0045, n=10, mat="leather_oxblood", closed=True)
    # low curved back: two brass posts + padded band
    back = []
    for i in range(25):
        a = math.radians(115 + 130 * i / 24)
        back.append((0.205 * math.cos(a), 0.205 * math.sin(a)))
    for side in (0, 24):
        bx, by = back[side]
        A.sweep(catmull([(bx * 0.9, by * 0.9, 0.70), (bx * 1.0, by * 1.0, 0.80), (bx * 1.05, by * 1.05, 0.90)], 6), r=0.011, n=14, mat="brass_polished")
    pad_prof = round_poly([(-0.006, -0.055), (0.03, -0.055), (0.034, 0.055), (-0.006, 0.055)], 0.012)
    path = [(x * 1.07, y * 1.07, 0.93) for (x, y) in back]
    A.sweep(path, prof=[(p[0], p[1]) for p in pad_prof], mat="leather_oxblood", up=(0, 0, 1), smooth=180, sub=1)
    A.sweep([(x * 1.07, y * 1.07, 0.872) for (x, y) in back], r=0.006, n=10, mat="brass_polished")
    A.point("Seat", (0, 0, 0.77))


# ======================================================================================
# Shared joinery helpers
# ======================================================================================


def raised_panel_x(A, y0, y1, z0, z1, x, mat="walnut", frame=0.07, t=0.022, field_t=0.012, gax_v=2):
    """Frame-and-panel facing +X with its back at x. Returns nothing."""
    w, h = y1 - y0, z1 - z0
    cy, cz = (y0 + y1) / 2, (z0 + z1) / 2
    # stiles + rails
    A.box((t, frame, h), at=(x + t / 2, y0 + frame / 2, cz), mat=mat, bevel=0.003, gax=2)
    A.box((t, frame, h), at=(x + t / 2, y1 - frame / 2, cz), mat=mat, bevel=0.003, gax=2)
    A.box((t, w - 2 * frame, frame), at=(x + t / 2, cy, z1 - frame / 2), mat=mat, bevel=0.003, gax=1)
    A.box((t, w - 2 * frame, frame), at=(x + t / 2, cy, z0 + frame / 2), mat=mat, bevel=0.003, gax=1)
    # recessed board + raised field (wide single-segment chamfer = fielded panel)
    A.box((t * 0.5, w - 2 * frame + 0.01, h - 2 * frame + 0.01), at=(x + t * 0.25, cy, cz), mat=mat, bevel=0.001, gax=gax_v)
    A.box((field_t, w - 2 * frame - 0.03, h - 2 * frame - 0.03), at=(x + t * 0.5 + field_t / 2 - 0.004, cy, cz), mat=mat, bevel=0.016, segs=1, gax=gax_v)
    # small ovolo moulding inside the frame
    m = 0.008
    pts = [(x + t, y0 + frame, z0 + frame), (x + t, y1 - frame, z0 + frame), (x + t, y1 - frame, z1 - frame), (x + t, y0 + frame, z1 - frame)]
    A.sweep(pts, r=m * 0.6, n=8, mat=mat, closed=True, gax=1)


def tufted_panel_x(A, x0, y0, y1, z0, z1, mat, su=0.075, sz=0.085, puff=0.03, res=0.006, button_mat=None):
    """Diamond-tufted upholstery facing +X (back plane at x0), with buttons at the tuft points."""
    W, H = y1 - y0, z1 - z0
    nbu = max(1, int(round(W / (2 * su))))
    su = W / (2 * nbu)
    nbz = max(1, int(round(H / sz)))
    sz = H / nbz

    def f(u, v):
        y = y0 + W * u
        z = z0 + H * v
        a_ = (y - y0) / su
        b_ = (z - z0) / sz
        d1 = abs(((a_ - b_) / 2.0) - round((a_ - b_) / 2.0)) * 2.0
        d2 = abs(((a_ + b_) / 2.0) - round((a_ + b_) / 2.0)) * 2.0
        dl = min(d1, d2) * 0.5 * math.hypot(su, sz)
        best = 9.0
        bj = round(b_)
        for jj in (bj - 1, bj, bj + 1):
            ai = round((a_ - jj) / 2.0) * 2 + jj
            for ii in (ai - 2, ai, ai + 2):
                best = min(best, math.hypot((a_ - ii) * su, (b_ - jj) * sz))
        dimple = math.exp(-(best / (0.3 * min(su, sz))) ** 2)
        crease = math.exp(-(dl / 0.006) ** 2) * (1.0 - dimple)
        edge = min(1.0, (y - y0) / 0.03, (y1 - y) / 0.03, (z - z0) / 0.03, (z1 - z) / 0.03)
        off = puff * max(edge, 0.0) ** 0.6 - 0.75 * puff * dimple * max(edge, 0) - 0.3 * puff * crease * max(edge, 0)
        return (x0 + off, y, z)

    A.grid(f, int(W / res), int(H / res), mat=mat, recalc=False)
    for j in range(1, nbz):
        for i in range(0, 2 * nbu + 1):
            if (i + j) % 2:
                continue
            y = y0 + i * su
            z = z0 + j * sz
            if y0 + 0.02 < y < y1 - 0.02:
                A.sphere(0.007, at=(x0 + 0.25 * puff + 0.002, y, z), mat=button_mat or mat, seg=10, rings=6, scale=(0.5, 1, 1))


def bottle_profile(kind, h):
    """(r, z) profile for a few spirits bottle shapes, base at z=0."""
    if kind == 0:  # whisky / bourbon: straight body, short neck
        return [(0, 0), (0.036, 0), (0.04, 0.006), (0.04, h * 0.62), (0.036, h * 0.70), (0.016, h * 0.80), (0.014, h * 0.94), (0.016, h * 0.95), (0, h * 0.95)]
    if kind == 1:  # wine/gin tall shoulder
        return [(0, 0), (0.034, 0), (0.037, 0.008), (0.037, h * 0.56), (0.030, h * 0.68), (0.014, h * 0.78), (0.012, h * 0.96), (0, h * 0.96)]
    if kind == 2:  # squat decanter
        return [(0, 0), (0.05, 0), (0.056, h * 0.12), (0.058, h * 0.40), (0.045, h * 0.62), (0.018, h * 0.72), (0.017, h * 0.95), (0, h * 0.95)]
    if kind == 3:  # vodka slim
        return [(0, 0), (0.031, 0), (0.033, 0.006), (0.033, h * 0.70), (0.022, h * 0.82), (0.012, h * 0.88), (0.012, h * 0.96), (0, h * 0.96)]
    return [(0, 0), (0.042, 0), (0.045, 0.01), (0.043, h * 0.5), (0.03, h * 0.66), (0.015, h * 0.74), (0.015, h * 0.95), (0, h * 0.95)]


def add_bottle(A, at, kind, h, rng, glass_piece="Glass", body_piece="Body"):
    prof = bottle_profile(kind, h)
    n = 4 if kind == 4 else 8
    rot = (0, 0, 45) if n == 4 else (0, 0, rng.uniform(0, 360))
    if n == 4:
        prof = [(r * 1.25, z) for r, z in prof]
    A.lathe(prof, at=at, mat="glass_bottles", n=n, piece=glass_piece, rot=rot, smooth=50 if n == 4 else 180)
    rmax = max(r for r, z in prof) * (1.0 if n != 4 else 0.92)
    # label band (opaque, on the body piece)
    z0, z1 = h * rng.uniform(0.18, 0.25), h * rng.uniform(0.45, 0.55)
    lid = rng.randint(1, 7)
    rl = rmax + 0.0012
    if n == 4:
        # square bottle: flat front label
        lab = A.box((0.002, rmax * 1.25, z1 - z0), at=(at[0] + rmax * 0.93 + 0.001, at[1], at[2] + (z0 + z1) / 2), mat="label", bevel=0, piece=body_piece)
        A.vattr(lab, "luv", lambda co: (0.25 + co.y / (rmax * 1.25) * 0.5, co.z / (z1 - z0) + 0.5, lid))
    else:
        segs = 16
        prf = [(rl, z0), (rl, z1)]
        verts, faces = [], []
        span = 0.7  # wraps 70% around
        for j, z in enumerate((z0, z1)):
            for i in range(segs + 1):
                a = -math.pi * span + 2 * math.pi * span * i / segs
                verts.append((rl * math.cos(a), rl * math.sin(a), z))
        for i in range(segs):
            faces.append((i, i + 1, segs + 1 + i + 1, segs + 1 + i))
        lab = A.mesh(verts, faces, "label", at=at, piece=body_piece, smooth=180, recalc=False)
        A.vattr(lab, "luv", lambda co: ((math.atan2(co.y, co.x) / (2 * math.pi * span) + 0.5), (co.z - z0) / (z1 - z0), lid))
    # cap / cork
    ztop = prof[-1][1]
    rn = prof[-2][0]
    cap = rng.choice(["cork", "metal", "wax"])
    if cap == "cork":
        A.lathe(round_poly([(0, ztop), (rn * 1.5, ztop), (rn * 1.5, ztop + 0.022), (0, ztop + 0.022)], 0.003, closed=False), at=at, mat="walnut_dark", n=12, piece=body_piece)
    elif cap == "metal":
        A.cyl(rn * 1.15, 0.03, at=(at[0], at[1], at[2] + ztop - 0.018), mat=rng.choice(["brass_polished", "chrome", "powder_black"]), n=14, bevel=0.0015, piece=body_piece)
    else:
        A.lathe([(0, ztop - 0.03), (rn * 1.25, ztop - 0.03), (rn * 1.3, ztop + 0.005), (rn * 0.9, ztop + 0.012), (0, ztop + 0.012)], at=at, mat="paint_red", n=12, piece=body_piece, smooth=180)


# ======================================================================================
# Bar counter 4 m: walnut raised panels, brass footrail, black marble top
# ======================================================================================


@asset("BarCounter_4m", res=4096, collision="Box", edge=0.004, ao_dist=0.35)
def bar_counter(A):
    L = 4.0
    H = 1.08
    xf = 0.17  # front panel face
    xb = -0.33  # back face
    # plinth: recessed black kick + brass kick plate
    A.box((0.44, L - 0.04, 0.10), at=((xf - 0.06 + xb) / 2, 0, 0.05), mat="powder_black", bevel=0.003)
    A.box((0.004, L - 0.04, 0.09), at=(xf - 0.06 + 0.0, 0, 0.05), mat="brass", bevel=0.0015, gax=1)
    # carcass
    A.box((xf - xb - 0.03, L - 0.02, H - 0.15), at=((xf + xb) / 2 - 0.015, 0, 0.10 + (H - 0.15) / 2), mat="walnut_satin", bevel=0.004, gax=2)
    # base moulding (plinth cap) along the front
    prof = round_poly([(0, 0), (0.035, 0), (0.035, 0.03), (0.018, 0.05), (0.0, 0.06)], 0.006, closed=True)
    A.prism([(xf - 0.005 + p[0], 0.10 + p[1]) for p in prof], L - 0.01, mat="walnut", plane="XZ", bevel=0.002, smooth=35, gax=1)
    # five raised-panel bays + brass reveal pilasters between them
    nb = 5
    bw = (L - 0.02) / nb
    for i in range(nb):
        y0 = -L / 2 + 0.01 + i * bw
        raised_panel_x(A, y0 + 0.012, y0 + bw - 0.012, 0.17, H - 0.17, xf - 0.022, mat="walnut", frame=0.075)
    for i in range(nb + 1):
        y = -L / 2 + 0.01 + i * bw
        A.box((0.03, 0.022, H - 0.32), at=(xf - 0.005, y, 0.16 + (H - 0.32) / 2), mat="walnut", bevel=0.003, gax=2)
        A.box((0.006, 0.008, H - 0.36), at=(xf + 0.011, y, 0.16 + (H - 0.32) / 2), mat="brass_polished", bevel=0.002, gax=2)
    # upper apron / crown under the top
    prof = round_poly([(0, 0), (0.0, -0.09), (0.02, -0.09), (0.03, -0.06), (0.045, -0.035), (0.06, -0.02), (0.06, 0)], 0.006, closed=True)
    A.prism([(xf - 0.02 + p[0], H - 0.045 + p[1]) for p in reversed(prof)], L, mat="walnut", plane="XZ", bevel=0.002, smooth=35, gax=1)
    # end panels
    for s in (-1, 1):
        A.box((xf - xb + 0.01, 0.03, H - 0.12), at=((xf + xb) / 2, s * (L / 2 - 0.0), 0.06 + (H - 0.12) / 2), mat="walnut", bevel=0.004, gax=2)
    # black marble top: ogee-ish front edge, square back
    top_prof = round_poly([(xb - 0.02, 0), (0.33, 0), (0.355, 0.006), (0.37, 0.02), (0.365, 0.034), (0.35, 0.045), (xb - 0.02, 0.045)], 0.004, closed=True)
    A.prism([(p[0], p[1]) for p in top_prof], L + 0.04, at=(0, 0, H - 0.045), mat="marble_black", plane="XZ", bevel=0.002, smooth=35)
    # brass footrail on brackets
    zr, xr = 0.21, xf + 0.19
    A.sweep([(xr, L / 2 - 0.06, zr), (xr, -L / 2 + 0.06, zr)], r=0.0254, n=32, mat="brass_polished", gax=1, cap=False)
    for s in (-1, 1):
        A.sphere(0.0254, at=(xr, s * (L / 2 - 0.06), zr), mat="brass_polished", seg=32, rings=16)
        A.lathe([(0.0, 0.0), (0.03, 0.0), (0.03, 0.006), (0.0256, 0.012), (0.0256, 0.02), (0, 0.02)], at=(xr, s * (L / 2 - 0.06), zr), axis="Y", rot=(0, 0, 0) if s > 0 else (180, 0, 0), mat="brass_polished", n=32)
    for i in range(6):
        y = -L / 2 + 0.2 + i * (L - 0.4) / 5
        path = catmull([(xf + 0.002, y, zr + 0.11), (xf + 0.08, y, zr + 0.09), (xr - 0.02, y, zr + 0.035), (xr, y, zr)], 6)
        A.sweep(path, r=0.011, n=16, mat="brass", scales=[1.25, 1.1, 1.0, 1.0, 0.95, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9][: len(path)])
        A.lathe(round_poly([(0, 0), (0.035, 0), (0.035, 0.008), (0.02, 0.016), (0, 0.016)], 0.002, closed=False), at=(xf - 0.003, y, zr + 0.11), axis="X", mat="brass", n=32)
        A.lathe([(0, -0.03), (0.031, -0.03), (0.031, 0.03), (0, 0.03)], at=(xr, y, zr), axis="Y", mat="brass", n=32)
    # bartender side: stainless work shelf + speed rail + cabinet fronts
    A.box((0.30, L - 0.1, 0.02), at=(xb - 0.12, 0, 0.84), mat="steel", bevel=0.003, gax=1)
    A.box((0.012, L - 0.1, 0.16), at=(xb - 0.27, 0, 0.77), mat="steel", bevel=0.002, gax=1)
    A.sweep([(xb - 0.27, L / 2 - 0.1, 0.62), (xb - 0.27, -L / 2 + 0.1, 0.62)], r=0.008, mat="steel", gax=1)
    for i in range(4):
        y = -L / 2 + 0.55 + i * 0.98
        A.box((0.02, 0.86, 0.62), at=(xb - 0.01, y, 0.45), mat="walnut_satin", bevel=0.004, gax=2)
        A.box((0.02, 0.14, 0.012), at=(xb - 0.03, y, 0.68), mat="brass", bevel=0.003, gax=1)
    A.point("BarTop", (0.0, 0.0, H))
    A.point("Footrail", (xr, 0.0, zr))
    A.view = (1.0, -0.75, 0.35)


# ======================================================================================
# Back bar 4 m: walnut cabinetry, antique mirror, glass shelves, ~40 bottles, LED channels
# ======================================================================================


@asset("BackBar_4m", res=4096, collision="Box", edge=0.004, ao_dist=0.3)
def back_bar(A):
    A.piece("Glass", "Glass", res=1024, glass=True)
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    L, D = 4.0, 0.52
    xb = -0.26
    # lower cabinet
    A.box((0.40, L - 0.06, 0.10), at=(xb + 0.20 - 0.04, 0, 0.05), mat="powder_black", bevel=0.003)
    A.box((0.48, L, 0.82), at=(xb + 0.24, 0, 0.10 + 0.41), mat="walnut_satin", bevel=0.004, gax=2)
    nd = 4
    dw = (L - 0.04) / nd
    for i in range(nd):
        y0 = -L / 2 + 0.02 + i * dw
        raised_panel_x(A, y0 + 0.008, y0 + dw - 0.008, 0.14, 0.88, xb + 0.48, mat="walnut", frame=0.07)
        A.box((0.02, 0.012, 0.16), at=(xb + 0.515, y0 + (dw - 0.06 if i % 2 == 0 else 0.06), 0.64), mat="brass_polished", bevel=0.004, gax=2)
    A.prism(round_poly([(xb - 0.01, 0), (xb + 0.53, 0), (xb + 0.545, 0.012), (xb + 0.54, 0.03), (xb - 0.01, 0.03)], 0.004), L + 0.02, at=(0, 0, 0.92), mat="marble_black", plane="XZ", bevel=0.002, smooth=35)
    # upper: mirror back in walnut frame, three bays
    z0, z1 = 0.95, 2.48
    A.box((0.03, L, z1 - z0), at=(xb + 0.015, 0, (z0 + z1) / 2), mat="walnut", bevel=0.003, gax=2)
    bays = 3
    bw = L / bays
    for i in range(bays):
        y0 = -L / 2 + i * bw
        A.box((0.006, bw - 0.08, z1 - z0 - 0.12), at=(xb + 0.033, y0 + bw / 2, (z0 + z1) / 2), mat="mirror", bevel=0.0015, gax=2)
    for i in range(bays + 1):
        y = -L / 2 + i * bw
        y = min(max(y, -L / 2 + 0.04), L / 2 - 0.04)
        A.box((0.30, 0.08, z1 - z0), at=(xb + 0.15, y, (z0 + z1) / 2), mat="walnut", bevel=0.004, gax=2)
        # fluted face with brass inlay
        A.box((0.006, 0.012, z1 - z0 - 0.1), at=(xb + 0.302, y, (z0 + z1) / 2), mat="brass_polished", bevel=0.002, gax=2)
    # cornice + LED channel under it
    prof = round_poly([(0, 0), (0.34, 0), (0.37, 0.02), (0.36, 0.05), (0.33, 0.07), (0.33, 0.12), (0, 0.12)], 0.006)
    A.prism(prof, L + 0.06, at=(xb, 0, z1), mat="walnut", plane="XZ", bevel=0.002, smooth=35, gax=1)
    A.box((0.02, L - 0.1, 0.012), at=(xb + 0.28, 0, z1 - 0.004), mat="aluminium", bevel=0.002, gax=1)
    A.box((0.012, L - 0.12, 0.004), at=(xb + 0.28, 0, z1 - 0.011), mat="emit", bevel=0.0, piece="Emissive")
    # glass shelves on brass brackets + LED strips under the front edge
    shelves = [1.30, 1.68, 2.06]
    rng = random.Random(7)
    count = 0
    for zi, zs in enumerate(shelves):
        for i in range(bays):
            yc = -L / 2 + (i + 0.5) * bw
            sw = bw - 0.10
            A.box((0.26, sw, 0.010), at=(xb + 0.165, yc, zs), mat="glass", bevel=0.0015, piece="Glass")
            A.box((0.014, sw, 0.022), at=(xb + 0.29, yc, zs - 0.004), mat="brass_polished", bevel=0.002, gax=1)
            A.box((0.006, sw - 0.02, 0.003), at=(xb + 0.285, yc, zs - 0.0165), mat="emit", bevel=0.0, piece="Emissive")
            for s in (-1, 1):
                A.box((0.24, 0.012, 0.03), at=(xb + 0.15, yc + s * (sw / 2 - 0.05), zs - 0.02), mat="brass", bevel=0.003, gax=0)
    # bottles: 3 shelves x 3 bays x 4 + counter row = 42
    kinds_h = {0: 0.30, 1: 0.32, 2: 0.24, 3: 0.33, 4: 0.27}
    for zi, zs in enumerate(shelves + [0.95]):
        for i in range(bays):
            yc = -L / 2 + (i + 0.5) * bw
            nbt = 4 if zi < 3 else (2 if i != 1 else 0)
            if nbt == 0:
                continue
            for k in range(nbt):
                kind = rng.choice([0, 0, 1, 2, 3, 4])
                h = kinds_h[kind] * rng.uniform(0.92, 1.08)
                y = yc + (k - (nbt - 1) / 2) * (bw - 0.25) / max(nbt - 1, 1) + rng.uniform(-0.03, 0.03)
                x = xb + (0.16 if zi < 3 else 0.20) + rng.uniform(-0.03, 0.03)
                add_bottle(A, (x, y, zs + (0.005 if zi < 3 else 0.0)), kind, h, rng)
                count += 1
    A.point("LEDTop", (xb + 0.28, 0, z1 - 0.011))
    A.view = (1.0, -0.6, 0.18)
    A.preview["Emissive"] = {"emit": (1.0, 0.62, 0.32, 18.0)}
    A.preview["Glass"] = {"glass": {"trans": 1.0, "thin": False, "ior": 1.5}}


# ======================================================================================
# Booth table + high table
# ======================================================================================


@asset("BoothTable", res=2048, collision="Convex", edge=0.003, ao_dist=0.2)
def booth_table(A):
    H = 0.74
    A.lathe(round_poly([(0, H - 0.035), (0.44, H - 0.035), (0.452, H - 0.028), (0.456, H - 0.015), (0.45, H - 0.004), (0.44, H), (0, H)], 0.004, closed=False), mat="marble_black", n=128, smooth=35)
    A.lathe(round_poly([(0, H - 0.06), (0.30, H - 0.06), (0.30, H - 0.035), (0, H - 0.035)], 0.004, closed=False), mat="powder_black", n=64)
    # trumpet base
    prof = [(0, 0.0), (0.30, 0.0), (0.302, 0.008), (0.29, 0.018)]
    for i in range(1, 13):
        t = i / 12
        prof.append((0.29 * (1 - t) ** 2.6 + 0.045, 0.018 + t * 0.30))
    prof += [(0.045, H - 0.12), (0.06, H - 0.11), (0.08, H - 0.075), (0.11, H - 0.06), (0, H - 0.06)]
    A.lathe(round_poly(prof, 0.004, closed=False), mat="brass", n=96, smooth=50, gax=2)
    A.lathe(round_poly([(0, 0.20), (0.068, 0.20), (0.072, 0.21), (0.068, 0.22), (0, 0.22)], 0.002, closed=False), mat="brass_polished", n=64)
    A.cyl(0.29, 0.004, at=(0, 0, -0.003), mat="rubber", n=64, bevel=0.0015)
    A.point("TableTop", (0, 0, H))


@asset("HighTable", res=2048, collision="Convex", edge=0.003, ao_dist=0.2)
def high_table(A):
    H = 1.07
    A.lathe(round_poly([(0, H - 0.04), (0.35, H - 0.04), (0.35, H), (0, H)], 0.005, closed=False), mat="walnut", n=128, gax=0)
    A.sweep(ring_path(0.353, H - 0.02, 160), prof=round_poly([(-0.004, -0.021), (0.004, -0.021), (0.004, 0.021), (-0.004, 0.021)], 0.002), mat="brass_polished", closed=True, up=(0, 0, 1))
    A.lathe(round_poly([(0, H - 0.07), (0.16, H - 0.07), (0.16, H - 0.04), (0, H - 0.04)], 0.004, closed=False), mat="powder_black", n=48)
    A.lathe([(0, 0.04), (0.04, 0.04), (0.04, H - 0.07), (0, H - 0.07)], mat="powder_black", n=40)
    for z in (0.32, H - 0.12):
        A.lathe(round_poly([(0, z), (0.05, z), (0.05, z + 0.03), (0, z + 0.03)], 0.004, closed=False), mat="brass_polished", n=48)
    A.lathe(round_poly([(0, 0), (0.28, 0), (0.28, 0.02), (0.22, 0.035), (0.06, 0.05), (0, 0.05)], 0.005, closed=False), mat="cast_iron", n=96)
    A.sweep(ring_path(0.26, 0.024, 120), r=0.006, mat="brass_polished", closed=True)
    A.point("TableTop", (0, 0, H))


# ======================================================================================
# Curved booth sofa: diamond-tufted velvet back, welted seat cushions, walnut shell, brass
# ======================================================================================


def arc_pts(cx, r, a0, a1, n, z=0.0):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), r * math.sin(a0 + (a1 - a0) * i / n), z) for i in range(n + 1)]


def annular_sector(A, cx, r0, r1, z0, z1, a0, a1, n, mat, bevel=0.004, **kw):
    prof = [(r0, z0), (r1, z0), (r1, z1), (r0, z1)]
    rings = []
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        ca, sa = math.cos(a), math.sin(a)
        rings.append([(cx + r * ca, r * sa, z) for r, z in prof])
    return A.loft(rings, mat=mat, closed=True, cap=True, bevel=bevel, smooth=40, **kw)


@asset("BoothSofa_Curved", res=2048, collision="Complex", edge=0.004, ao_dist=0.3)
def booth_sofa(A):
    cx = 0.39
    a0, a1 = math.radians(62), math.radians(298)
    n = 120
    # plinth + brass kick
    annular_sector(A, cx, 1.00, 1.47, 0.0, 0.10, a0, a1, n, "powder_black")
    A.sweep(arc_pts(cx, 0.999, a0, a1, n, 0.05), prof=round_poly([(-0.035, -0.002), (0.035, -0.002), (0.035, 0.002), (-0.035, 0.002)], 0.0015), mat="brass_polished", up=(0, 0, 1), gax=1)
    # velvet seat base (skirt)
    annular_sector(A, cx, 0.97, 1.40, 0.10, 0.33, a0, a1, n, "velvet_burgundy", bevel=0.012)
    # seat cushions (5), welted front edge
    ncush = 5
    gap = math.radians(0.6)
    prof = round_poly([(-0.07, -0.215), (0.06, -0.215), (0.075, -0.15), (0.072, 0.20), (0.0, 0.215), (-0.07, 0.215)], 0.03)
    for k in range(ncush):
        b0 = a0 + (a1 - a0) * k / ncush + gap
        b1 = a0 + (a1 - a0) * (k + 1) / ncush - gap
        path = arc_pts(cx, 1.185, b0, b1, 28, 0.40)
        A.sweep(path, prof=prof, mat="velvet_burgundy", up=(0, 0, 1), bevel=0.02, segs=3, smooth=180)
        A.sweep(arc_pts(cx, 0.968, b0 + 0.01, b1 - 0.01, 28, 0.472), r=0.0055, n=10, mat="velvet_burgundy", smooth=180)
        A.sweep(arc_pts(cx, 0.968, b0 + 0.01, b1 - 0.01, 28, 0.333), r=0.0055, n=10, mat="velvet_burgundy", smooth=180)
    # tufted back (diamond pattern) as a dense parametric surface
    rb0, z0, z1 = 1.345, 0.47, 1.06
    su, sz = 0.11, 0.125  # half pitch along the arc / row pitch
    length = rb0 * (a1 - a0)
    buttons = []

    def surf(u, v):
        u = 1.0 - u  # wind faces so normals point at the sitter
        a = a0 + (a1 - a0) * u
        z = z0 + (z1 - z0) * v
        s = u * length
        A_ = s / su
        B_ = (z - (z0 + 0.06)) / sz
        # distance to diamond crease lines (a +- b = 2k) in metres (approx)
        d1 = abs(((A_ - B_) / 2.0) - round((A_ - B_) / 2.0)) * 2.0
        d2 = abs(((A_ + B_) / 2.0) - round((A_ + B_) / 2.0)) * 2.0
        dl = min(d1, d2) * 0.5 * math.hypot(su, sz)
        # nearest button
        bj = round(B_)
        best = 9.0
        for jj in (bj - 1, bj, bj + 1):
            if jj < 0 or jj > 4:
                continue
            ai = round((A_ - jj) / 2.0) * 2 + jj
            for ii in (ai - 2, ai, ai + 2):
                d = math.hypot((A_ - ii) * su, (B_ - jj) * sz)
                best = min(best, d)
        dimple = math.exp(-(best / 0.032) ** 2)
        crease = math.exp(-(dl / 0.010) ** 2) * (1.0 - dimple)
        edge = min(1.0, v / 0.06, (1 - v) / 0.08, u * length / 0.05, (1 - u) * length / 0.05)
        puff = 0.045 * max(edge, 0.0) ** 0.5
        off = puff - 0.032 * dimple - 0.012 * crease
        r = rb0 + (z - z0) * 0.10 - off
        return (cx + r * math.cos(a), r * math.sin(a), z)

    nv = int((z1 - z0) / 0.011)
    npatch = 7
    for k in range(npatch):
        ua, ub = k / npatch, (k + 1) / npatch
        nu = int(length / npatch / 0.011)
        A.grid(lambda u, v, ua=ua, ub=ub: surf(ua + (ub - ua) * u, v), nu, nv, mat="velvet_burgundy", recalc=False)
    for jj in range(0, 5):
        B_ = jj
        z = z0 + 0.06 + B_ * sz
        if z > z1 - 0.06:
            continue
        ii = jj % 2
        while ii * su < length:
            s = ii * su
            if 0.06 < s < length - 0.06:
                a = a0 + s / rb0
                r = rb0 + (z - z0) * 0.10 - 0.045 + 0.034
                A.sphere(0.011, at=(cx + r * math.cos(a), r * math.sin(a), z), mat="velvet_burgundy", seg=10, rings=6, scale=(1, 1, 0.55), rot=(0, 90, math.degrees(a) + 180))
            ii += 2
    # top roll + backing + walnut outer shell + brass cap rail
    A.sweep(arc_pts(cx, 1.40, a0, a1, n, 1.075), r=0.045, n=16, mat="velvet_burgundy", smooth=180)
    annular_sector(A, cx, 1.40, 1.47, 0.33, 1.06, a0, a1, n, "velvet_burgundy", bevel=0.008)
    annular_sector(A, cx, 1.47, 1.51, 0.02, 1.13, a0, a1, n, "walnut", bevel=0.004, gax=2)
    A.sweep(arc_pts(cx, 1.49, a0, a1, n, 1.137), prof=round_poly([(-0.006, -0.03), (0.006, -0.03), (0.006, 0.03), (-0.006, 0.03)], 0.003), mat="brass_polished", up=(0, 0, 1), gax=1)
    # end panels (walnut) with brass edge
    for a, sgn in ((a0, -1), (a1, 1)):
        poly = round_poly([(0.94, 0.0), (1.52, 0.0), (1.52, 1.14), (1.30, 1.14), (1.05, 0.72), (0.94, 0.72)], 0.02)
        ang = math.degrees(a)
        off = sgn * 0.026
        p = A.prism(poly, 0.05, mat="walnut", plane="XZ", bevel=0.004, gax=2)
        p.matrix_world = Matrix.Translation((cx, 0, 0)) @ Matrix.Rotation(a, 4, "Z") @ Matrix.Translation((0, off, 0))
        cap = A.sweep([(0.94, 0, 0.725), (1.05, 0, 0.725), (1.30, 0, 1.145), (1.52, 0, 1.145)], r=0.008, mat="brass_polished", gax=0)
        cap.matrix_world = Matrix.Translation((cx, 0, 0)) @ Matrix.Rotation(a, 4, "Z") @ Matrix.Translation((0, off, 0))
    A.point("SeatCentre", (cx - 1.18, 0, 0.47))
    A.view = (1.0, -0.55, 0.45)
    A.lens = 50


# ======================================================================================
# Leather club armchair
# ======================================================================================


@asset("Armchair_Leather", res=2048, collision="Convex", edge=0.005, ao_dist=0.25)
def armchair(A):
    lm = "leather_oxblood"
    W, D = 0.88, 0.92
    # bun feet
    for x in (-0.36, 0.36):
        for y in (-0.36, 0.36):
            A.lathe(round_poly([(0, 0), (0.03, 0), (0.042, 0.03), (0.038, 0.07), (0.045, 0.085), (0.045, 0.10), (0, 0.10)], 0.004, closed=False), at=(x, y, 0), mat="walnut_dark", n=24, gax=2)
    # base
    A.box((D - 0.02, W - 0.04, 0.24), at=(0, 0, 0.10 + 0.12), mat=lm, bevel=0.035, segs=4)
    # arms: upright + roll
    for s in (-1, 1):
        y = s * (W / 2 - 0.085)
        A.box((D - 0.04, 0.15, 0.40), at=(0.0, y, 0.12 + 0.20), mat=lm, bevel=0.04, segs=4)
        A.sweep([(D / 2 - 0.01, y + s * 0.02, 0.60), (-D / 2 + 0.06, y + s * 0.02, 0.60)], prof=circle_pts(0.085, 28, rx=0.075), mat=lm, bevel=0.03, segs=4, smooth=180, cap=True)
        # scroll front panel + nailhead trim
        A.lathe([(0, 0), (0.07, 0), (0.08, 0.008), (0.0, 0.016)], at=(D / 2 - 0.012, y + s * 0.02, 0.60), axis="X", mat=lm, n=32, smooth=180)
        for i in range(22):
            t = i / 21
            if t < 0.6:
                py = y + s * 0.02 + 0.072 * math.cos(math.pi * (0.5 + t / 0.6 * 1.5))
                pz = 0.60 + 0.072 * math.sin(math.pi * (0.5 + t / 0.6 * 1.5))
            else:
                py = y + s * 0.062
                pz = 0.60 - (t - 0.6) / 0.4 * 0.42
            px = D / 2 - 0.004 if t < 0.6 else D / 2 - 0.018
            A.sphere(0.0065, at=(px, py, pz), mat="brass_aged", seg=10, rings=5, scale=(0.6, 1, 1))
    # back with top roll, raked
    A.box((0.20, W - 0.30, 0.48), at=(-D / 2 + 0.14, 0, 0.56), rot=(0, -9, 0), mat=lm, bevel=0.05, segs=4)
    A.sweep([(-D / 2 + 0.17, -(W / 2 - 0.12), 0.80), (-D / 2 + 0.17, (W / 2 - 0.12), 0.80)], prof=circle_pts(0.06, 24, rx=0.085), mat=lm, bevel=0.03, segs=3, smooth=180)
    # seat cushion
    A.box((0.66, W - 0.30, 0.14), at=(0.07, 0, 0.405), mat=lm, bevel=0.04, segs=4)
    A.sweep([(0.40, -(W / 2 - 0.16), 0.468), (0.40, (W / 2 - 0.16), 0.468)], r=0.006, mat=lm, smooth=180)
    # front base nailhead row
    for i in range(40):
        y = -(W / 2 - 0.06) + (W - 0.12) * i / 39
        A.sphere(0.0065, at=(D / 2 - 0.006, y, 0.14), mat="brass_aged", seg=10, rings=5, scale=(0.6, 1, 1))
    A.point("Seat", (0.05, 0, 0.47))
    A.view = (1.0, -0.8, 0.45)


# ======================================================================================
# DJ booth: fluted walnut front with LED channels, lacquer top, turntables + mixer
# ======================================================================================


def turntable(A, at):
    x, y, z = at
    A.box((0.353, 0.453, 0.11), at=(x, y, z + 0.055), mat="aluminium", bevel=0.006, segs=3, gax=1)
    A.box((0.36, 0.46, 0.03), at=(x, y, z + 0.015), mat="rubber", bevel=0.006)
    for fx in (-0.13, 0.13):
        for fy in (-0.18, 0.18):
            A.cyl(0.03, 0.02, at=(x + fx, y + fy, z - 0.02), mat="rubber", n=20, bevel=0.003)
    px, py = x + 0.01, y + 0.05
    A.cyl(0.16, 0.02, at=(px, py, z + 0.11), mat="aluminium", n=96, bevel=0.002)
    for i in range(48):
        a = 2 * math.pi * i / 48
        A.box((0.004, 0.006, 0.004), at=(px + 0.161 * math.cos(a), py + 0.161 * math.sin(a), z + 0.12), rot=(0, 0, math.degrees(a)), mat="steel", bevel=0.0)
    A.cyl(0.152, 0.003, at=(px, py, z + 0.13), mat="rubber", n=96, bevel=0.001)
    A.cyl(0.150, 0.0015, at=(px, py, z + 0.133), mat="vinyl", n=96, bevel=0.0)
    A.cyl(0.05, 0.0005, at=(px, py, z + 0.1345), mat="paint_red", n=48, bevel=0.0)
    A.cyl(0.0036, 0.016, at=(px, py, z + 0.133), mat="chrome", n=12, bevel=0.0005)
    # tonearm
    tx, ty = x + 0.12, y - 0.18
    A.cyl(0.03, 0.03, at=(tx, ty, z + 0.11), mat="chrome", n=32, bevel=0.002)
    A.sweep(catmull([(tx, ty, z + 0.15), (tx - 0.06, ty + 0.06, z + 0.152), (tx - 0.12, ty + 0.17, z + 0.150), (tx - 0.14, ty + 0.21, z + 0.148)], 8), r=0.0045, mat="chrome")
    A.box((0.03, 0.05, 0.008), at=(tx - 0.145, ty + 0.225, z + 0.146), rot=(0, 0, 25), mat="powder_black", bevel=0.002)
    A.cyl(0.018, 0.04, at=(tx + 0.03, ty - 0.03, z + 0.14), axis="X", mat="chrome", n=24, bevel=0.002)
    A.box((0.08, 0.012, 0.006), at=(x - 0.1, y - 0.19, z + 0.112), mat="plastic_black", bevel=0.002)
    A.box((0.012, 0.03, 0.01), at=(x - 0.1, y - 0.19, z + 0.118), mat="steel", bevel=0.002)
    A.cyl(0.02, 0.008, at=(x + 0.13, y + 0.19, z + 0.11), mat="steel", n=24, bevel=0.002)


def mixer(A, at):
    x, y, z = at
    A.box((0.40, 0.33, 0.10), at=(x, y, z + 0.05), mat="steel_dark", bevel=0.006, segs=3)
    A.box((0.38, 0.31, 0.004), at=(x, y, z + 0.1), mat="powder_black", bevel=0.001)
    for ch in range(4):
        cy = y - 0.11 + ch * 0.0733
        for k in range(5):
            A.cyl(0.011, 0.018, at=(x + 0.15 - k * 0.045, cy, z + 0.1), mat="rubber", n=16, bevel=0.002)
            A.cyl(0.0015, 0.003, at=(x + 0.15 - k * 0.045 + 0.007, cy, z + 0.118), mat="paint_white", n=6, bevel=0.0)
        A.box((0.07, 0.004, 0.002), at=(x - 0.10, cy, z + 0.101), mat="steel", bevel=0.0)
        A.box((0.014, 0.018, 0.016), at=(x - 0.10 + 0.01 * ch, cy, z + 0.108), mat="plastic_grey", bevel=0.002)
    A.box((0.004, 0.10, 0.002), at=(x - 0.165, y, z + 0.101), mat="steel", bevel=0.0)
    A.box((0.018, 0.016, 0.016), at=(x - 0.165, y + 0.01, z + 0.108), mat="plastic_grey", bevel=0.002)


@asset("DJBooth", res=4096, collision="Box", edge=0.004, ao_dist=0.3)
def dj_booth(A):
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    W, D, H = 2.4, 0.8, 1.0
    xf = D / 2
    A.box((D - 0.1, W - 0.1, 0.10), at=(-0.05, 0, 0.05), mat="powder_black", bevel=0.003)
    A.box((D - 0.06, W - 0.04, H - 0.14), at=(-0.03, 0, 0.10 + (H - 0.14) / 2), mat="lacquer_black", bevel=0.004)
    # fluted walnut front between two LED channels
    nfl = 64
    for i in range(nfl):
        y = -W / 2 + 0.06 + (W - 0.12) * (i + 0.5) / nfl
        A.box((0.022, (W - 0.12) / nfl - 0.003, 0.70), at=(xf - 0.02, y, 0.52), mat="walnut", bevel=0.009, segs=3, gax=2)
    A.box((0.03, W - 0.04, 0.03), at=(xf - 0.03, 0, 0.155), mat="brass", bevel=0.003, gax=1)
    A.box((0.03, W - 0.04, 0.03), at=(xf - 0.03, 0, 0.885), mat="brass", bevel=0.003, gax=1)
    for s in (-1, 1):
        A.box((0.06, 0.05, H - 0.12), at=(xf - 0.03, s * (W / 2 - 0.025), 0.10 + (H - 0.12) / 2), mat="brass", bevel=0.004, gax=2)
    # LED channels (aluminium U + diffuser = emissive)
    for zc in (0.125, 0.915):
        A.box((0.02, W - 0.14, 0.022), at=(xf - 0.02, 0, zc), mat="aluminium", bevel=0.002, gax=1)
        A.box((0.004, W - 0.16, 0.012), at=(xf - 0.008, 0, zc), mat="emit", bevel=0.0, piece="Emissive")
    # lacquer top with brass nosing
    A.box((D + 0.06, W + 0.04, 0.05), at=(0.0, 0, H + 0.025), mat="lacquer_black", bevel=0.006, segs=3)
    A.sweep([(xf + 0.03, W / 2 + 0.02, H + 0.025), (xf + 0.03, -W / 2 - 0.02, H + 0.025)], prof=round_poly([(-0.004, -0.026), (0.006, -0.026), (0.006, 0.026), (-0.004, 0.026)], 0.003), mat="brass_polished", up=(0, 0, 1), gax=1)
    # equipment
    turntable(A, (-0.02, 0.66, H + 0.05))
    turntable(A, (-0.02, -0.66, H + 0.05))
    mixer(A, (-0.02, 0.0, H + 0.05))
    # DJ-side shelf + cable tray
    A.box((0.36, W - 0.2, 0.02), at=(-D / 2 + 0.16, 0, 0.55), mat="walnut", bevel=0.003, gax=1)
    A.box((0.02, W - 0.2, 0.28), at=(-D / 2 + 0.0, 0, 0.70), mat="lacquer_black", bevel=0.003)
    A.point("DJ", (-0.75, 0, 0))
    A.preview["Emissive"] = {"emit": (0.85, 0.15, 1.0, 25.0)}
    A.view = (1.0, -0.55, 0.42)


# ======================================================================================
# Speaker stack: two subs + four splayed line-array modules on a rigging frame
# ======================================================================================


def speaker_box(A, w, h_front, h_back, d, at, tilt=0.0, grille_mat="grille"):
    """Trapezoid line-array module, front face at local +X. at = front-bottom centre."""
    poly = round_poly([(0.0, 0.0), (0.0, h_front), (-d, h_front - (h_front - h_back) / 2), (-d, (h_front - h_back) / 2)], 0.008)
    poly = list(reversed(poly))
    ob = A.prism(poly, w, mat="duratex", plane="XZ", bevel=0.004)
    gr = A.box((0.012, w - 0.03, h_front - 0.03), at=(0.004, 0, h_front / 2), mat=grille_mat, bevel=0.003)
    plates = []
    for s in (-1, 1):
        plates.append(A.box((d * 0.75, 0.008, h_front * 0.8), at=(-d * 0.45, s * (w / 2 + 0.004), h_front * 0.5), mat="steel_dark", bevel=0.002, gax=0))
        plates.append(A.cyl(0.012, 0.02, at=(-0.06, s * (w / 2 + 0.008), h_front * 0.85), axis="Y", mat="steel", n=16, bevel=0.002))
        plates.append(A.cyl(0.012, 0.02, at=(-d + 0.08, s * (w / 2 + 0.008), h_front * 0.5), axis="Y", mat="steel", n=16, bevel=0.002))
    hd = A.box((0.03, 0.18, 0.02), at=(-d - 0.005, 0, h_back * 0.5 + (h_front - h_back) / 2), mat="plastic_black", bevel=0.006)
    M = Matrix.Translation(at) @ Matrix.Rotation(math.radians(tilt), 4, "Y")
    for o in [ob, gr, hd] + plates:
        o.matrix_world = M @ o.matrix_world
    return M


@asset("SpeakerStack", res=2048, collision="Box", edge=0.004, ao_dist=0.25)
def speaker_stack(A):
    w, d = 1.10, 0.72
    z = 0.0
    for k in range(2):
        A.box((d, w, 0.56), at=(-d / 2 + 0.01, 0, z + 0.28), mat="duratex", bevel=0.008, segs=3)
        A.box((0.014, w - 0.04, 0.52), at=(0.012, 0, z + 0.28), mat="grille", bevel=0.003)
        for s in (-1, 1):
            A.box((0.15, 0.02, 0.04), at=(-d / 2, s * (w / 2 + 0.01), z + 0.38), mat="plastic_black", bevel=0.008)
            A.box((d - 0.05, 0.006, 0.06), at=(-d / 2, s * (w / 2 + 0.003), z + 0.05), mat="steel_dark", bevel=0.002, gax=0)
        for fx in (-d + 0.08, -0.06):
            for fy in (-w / 2 + 0.08, w / 2 - 0.08):
                A.cyl(0.03, 0.012, at=(fx, fy, z - 0.012 if k == 0 else z - 0.006), mat="rubber", n=16, bevel=0.002)
        z += 0.565
    # fly frame / rigging bumper on top of the subs
    A.box((0.70, w + 0.06, 0.05), at=(-0.33, 0, z + 0.025), mat="steel_dark", bevel=0.004, gax=1)
    for s in (-1, 1):
        A.box((0.60, 0.012, 0.10), at=(-0.32, s * (w / 2 + 0.03), z + 0.07), mat="steel_dark", bevel=0.003, gax=0)
    z += 0.05
    splay = [0.0, 2.0, 5.0, 9.0]
    M = Matrix.Translation((0.0, 0, z))
    tilt = 0.0
    hf, hb, md = 0.30, 0.27, 0.55
    for i, sp in enumerate(splay):
        tilt += sp
        base = M @ V((0, 0, 0))
        speaker_box(A, w - 0.06, hf, hb, md, tuple(base), tilt=-tilt)
        M = Matrix.Translation(base) @ Matrix.Rotation(math.radians(-tilt), 4, "Y") @ Matrix.Translation((0, 0, hf + 0.004)) @ Matrix.Rotation(math.radians(tilt), 4, "Y")
    A.view = (1.0, -0.6, 0.25)


# ======================================================================================
# Moving head stage light
# ======================================================================================


@asset("MovingHeadLight", res=2048, collision="Box", edge=0.003, ao_dist=0.15)
def moving_head(A):
    A.piece("Glass", "Glass", res=1024, glass=True)
    A.cur = "Body"
    # base
    A.box((0.32, 0.40, 0.15), at=(0, 0, 0.075), mat="plastic_black", bevel=0.02, segs=3)
    A.box((0.004, 0.10, 0.05), at=(0.161, 0.08, 0.08), mat="glass_car", bevel=0.002)
    for i in range(4):
        A.cyl(0.006, 0.006, at=(0.16, -0.05 - i * 0.025, 0.07), axis="X", mat="rubber", n=12, bevel=0.001)
    for s in (-1, 1):
        A.sweep([(-0.08, s * 0.205, 0.04), (-0.08, s * 0.225, 0.06), (0.08, s * 0.225, 0.06), (0.08, s * 0.205, 0.04)], r=0.008, mat="plastic_black")
    for x in (-0.12, 0.12):
        for y in (-0.16, 0.16):
            A.cyl(0.018, 0.01, at=(x, y, -0.008), mat="rubber", n=16, bevel=0.002)
    # pan bearing + yoke
    A.cyl(0.11, 0.03, at=(0, 0, 0.15), mat="plastic_black", n=48, bevel=0.004)
    A.box((0.12, 0.40, 0.06), at=(0, 0, 0.21), mat="plastic_black", bevel=0.02, segs=3)
    for s in (-1, 1):
        poly = round_poly([(-0.06, 0.0), (0.06, 0.0), (0.05, 0.30), (-0.05, 0.30)], 0.02)
        arm = A.prism(poly, 0.05, mat="plastic_black", plane="XZ", bevel=0.006)
        arm.matrix_world = Matrix.Translation((0, s * 0.175, 0.22)) @ arm.matrix_world
        A.cyl(0.05, 0.012, at=(0, s * 0.20, 0.47), axis="Y", rot=(0, 0, 0 if s > 0 else 180), mat="plastic_grey", n=32, bevel=0.002)
    # head (tilted up 25 deg)
    head = []
    prof = round_poly([(0, -0.20), (0.11, -0.20), (0.13, -0.12), (0.135, 0.10), (0.125, 0.16), (0.118, 0.17), (0, 0.17)], 0.01, closed=False)
    head.append(A.lathe(prof, axis="X", mat="plastic_black", n=48))
    head.append(A.lathe([(0.112, 0.168), (0.118, 0.168), (0.118, 0.19), (0.10, 0.19), (0.098, 0.18)], axis="X", mat="powder_black", n=48, cap=False))
    for i in range(10):
        a = 2 * math.pi * i / 10
        head.append(A.box((0.10, 0.01, 0.012), at=(-0.06, 0.134 * math.cos(a), 0.134 * math.sin(a)), rot=(math.degrees(a), 0, 0), mat="plastic_grey", bevel=0.003))
    head.append(A.cyl(0.08, 0.004, at=(-0.20, 0, 0), axis="X", rot=(0, 0, 180), mat="grille", n=40, bevel=0.001))
    lens = A.lathe([(0, 0.175), (0.098, 0.175), (0.09, 0.183), (0.05, 0.188), (0, 0.19)], axis="X", mat="glass_lens", n=32, piece="Glass", smooth=180)
    head.append(lens)
    M = Matrix.Translation((0, 0, 0.47)) @ Matrix.Rotation(math.radians(-25), 4, "Y")
    for o in head:
        o.matrix_world = M @ o.matrix_world
    A.point("Beam", tuple(M @ V((0.19, 0, 0))))
    A.preview["Glass"] = {"glass": {"trans": 0.6, "rough": 0.02, "emit": 6.0}}
    A.view = (1.0, -0.7, 0.3)


# ======================================================================================
# Crystal chandelier
# ======================================================================================


def octa_bead(A, at, r, h, mat="crystal", piece="Glass", rot=None):
    """Faceted bead: octagonal bipyramid (16 tris)."""
    verts = [(0, 0, h / 2), (0, 0, -h / 2)] + [(r * math.cos(2 * math.pi * i / 8), r * math.sin(2 * math.pi * i / 8), 0) for i in range(8)]
    faces = []
    for i in range(8):
        faces.append((0, 2 + i, 2 + (i + 1) % 8))
        faces.append((1, 2 + (i + 1) % 8, 2 + i))
    return A.mesh(verts, faces, mat, at=at, rot=rot, piece=piece, smooth=0)


def pendalogue(A, at, s=1.0, piece="Glass"):
    """Teardrop prism drop (24 tris), hanging below `at`."""
    r = 0.016 * s
    pts = []
    rings = [(0.0, 0.0), (0.6, -0.012), (1.0, -0.03), (0.8, -0.05), (0.0, -0.075)]
    verts, faces = [], []
    for k, (f, z) in enumerate(rings):
        if f == 0:
            verts.append((0, 0, z * s))
        else:
            for i in range(6):
                a = 2 * math.pi * i / 6
                verts.append((r * f * math.cos(a), r * f * 0.45 * math.sin(a), z * s))
    # top pole 0, rings 1..3 (6 each), bottom pole
    def ring(k):
        return [1 + (k - 1) * 6 + i for i in range(6)]
    for i in range(6):
        faces.append((0, ring(1)[(i + 1) % 6], ring(1)[i]))
    for k in (1, 2):
        a, b = ring(k), ring(k + 1)
        for i in range(6):
            faces.append((a[i], a[(i + 1) % 6], b[(i + 1) % 6], b[i]))
    bot = len(verts) - 1
    for i in range(6):
        faces.append((ring(3)[i], ring(3)[(i + 1) % 6], bot))
    return A.mesh(verts, faces, "crystal", at=at, piece=piece, smooth=0)


def catenary(p0, p1, sag, n):
    p0, p1 = V(p0), V(p1)
    out = []
    for i in range(n + 1):
        t = i / n
        p = p0.lerp(p1, t)
        p.z -= sag * 4 * t * (1 - t)
        out.append(tuple(p))
    return out


@asset("Chandelier", res=4096, collision="Convex", edge=0.003, ao_dist=0.15)
def chandelier(A):
    A.piece("Glass", "Glass", res=1024, glass=True)
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    zb = 0.10
    # central column (turned brass, urn + bulbs)
    prof = [(0, zb), (0.03, zb), (0.05, zb + 0.03), (0.055, zb + 0.07), (0.03, zb + 0.11), (0.022, zb + 0.15), (0.035, zb + 0.20), (0.07, zb + 0.24), (0.075, zb + 0.27),
            (0.03, zb + 0.30), (0.02, zb + 0.36), (0.028, zb + 0.40), (0.045, zb + 0.45), (0.03, zb + 0.50), (0.018, zb + 0.55), (0.02, zb + 0.65), (0.04, zb + 0.70), (0.045, zb + 0.73),
            (0.02, zb + 0.76), (0.014, zb + 0.82), (0.025, zb + 0.86), (0.012, zb + 0.90), (0.012, 1.18), (0.06, 1.18), (0.07, 1.20), (0.065, 1.22), (0, 1.23)]
    A.lathe(round_poly(prof, 0.006, closed=False), mat="brass_polished", n=48, smooth=50)
    A.lathe([(0, 0.0), (0.012, 0.0), (0.02, 0.03), (0.018, 0.06), (0.01, zb), (0, zb)], mat="brass_polished", n=24, smooth=180)
    tiers = [(8, 0.42, zb + 0.255, zb + 0.36), (6, 0.25, zb + 0.715, zb + 0.80)]
    tips = []
    for count, R, zarm, zcup in tiers:
        tier_tips = []
        for i in range(count):
            a = 2 * math.pi * (i + 0.5) / count
            ca, sa = math.cos(a), math.sin(a)
            pts2 = [(0.04, zarm), (R * 0.35, zarm - 0.05), (R * 0.75, zarm - 0.04), (R * 0.98, zarm + 0.01), (R, zcup - 0.04)]
            path = catmull([(r * ca, r * sa, z) for r, z in pts2], 8)
            A.sweep(path, r=0.0075, n=12, mat="brass_polished")
            # scroll curl under the arm
            curl = [(R * 0.35 + 0.03 * math.cos(t), 0, zarm - 0.08 + 0.03 * math.sin(t)) for t in [math.pi * 2 * k / 14 + math.pi / 2 for k in range(12)]]
            curl = [(p[0] * ca, p[0] * sa, p[2]) for p in curl]
            A.sweep(curl, r=0.004, n=8, mat="brass_polished")
            # bobeche (drip pan) + candle sleeve + bulb
            cx_, cy_ = R * ca, R * sa
            A.lathe(round_poly([(0, zcup - 0.045), (0.02, zcup - 0.045), (0.05, zcup - 0.01), (0.055, zcup), (0.015, zcup), (0, zcup)], 0.004, closed=False), at=(cx_, cy_, 0), mat="brass_polished", n=32)
            A.cyl(0.013, 0.09, at=(cx_, cy_, zcup), mat="paint_white", n=20, bevel=0.002)
            A.lathe([(0, 0), (0.006, 0.0), (0.014, 0.02), (0.016, 0.035), (0.01, 0.055), (0.0, 0.065)], at=(cx_, cy_, zcup + 0.09), mat="emit", n=16, piece="Emissive", smooth=180)
            pendalogue(A, (cx_, cy_, zcup - 0.05), s=1.1)
            tier_tips.append((cx_, cy_, zcup - 0.012))
        tips.append(tier_tips)
    # festoons of beads between neighbouring bobeches
    for ti, tier_tips in enumerate(tips):
        nbeads = 9 if ti == 0 else 7
        for i in range(len(tier_tips)):
            p0, p1 = tier_tips[i], tier_tips[(i + 1) % len(tier_tips)]
            path = catenary(p0, p1, 0.10 if ti == 0 else 0.07, nbeads + 1)
            for p in path[1:-1]:
                octa_bead(A, p, 0.011, 0.022)
    # crystal basket: strands from the lower ring down to the column bottom
    for i in range(12):
        a = 2 * math.pi * (i + 0.5) / 12
        p0 = (0.40 * math.cos(a), 0.40 * math.sin(a), zb + 0.30)
        p1 = (0.05 * math.cos(a), 0.05 * math.sin(a), zb + 0.03)
        path = catenary(p0, p1, 0.06, 8)
        for p in path[1:]:
            octa_bead(A, p, 0.010, 0.020)
    # crown ring of drops near the top
    for i in range(16):
        a = 2 * math.pi * i / 16
        pendalogue(A, (0.075 * math.cos(a), 0.075 * math.sin(a), zb + 0.73), s=0.8)
    pendalogue(A, (0, 0, 0.075), s=1.0)
    A.sweep(ring_path(0.40, zb + 0.30, 64), r=0.004, mat="brass_polished", closed=True)
    A.point("CeilingMount", (0, 0, 1.23))
    A.point("Light", (0, 0, zb + 0.45))
    A.preview["Emissive"] = {"emit": (1.0, 0.78, 0.5, 40.0)}
    A.preview["Glass"] = {"glass": {"trans": 1.0, "rough": 0.0, "thin": False, "ior": 1.6}}
    A.view = (1.0, -0.55, 0.12)


# ======================================================================================
# Wall sconce (brass backplate, curved arm, frosted shade)
# ======================================================================================


@asset("WallSconce", res=2048, collision="Box", edge=0.002, ao_dist=0.1)
def wall_sconce(A):
    A.piece("Glass", "Glass", res=1024, glass=True)
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    xw = -0.12  # wall plane
    poly = round_poly(rrect_pts(0.11, 0.26, 0.05, 6), 0.002)
    A.prism(poly, 0.012, mat="brass", plane="YZ", at=(xw + 0.006, 0, 0.13), bevel=0.003, segs=3, gax=2)
    A.prism(round_poly(rrect_pts(0.085, 0.235, 0.04, 6), 0.002), 0.006, mat="brass_polished", plane="YZ", at=(xw + 0.015, 0, 0.13), bevel=0.002, gax=2)
    A.lathe([(0, 0), (0.022, 0), (0.022, 0.012), (0.012, 0.022), (0, 0.024)], at=(xw + 0.018, 0, 0.10), axis="X", mat="brass_polished", n=32)
    arm = catmull([(xw + 0.03, 0, 0.10), (xw + 0.10, 0, 0.09), (xw + 0.17, 0, 0.13), (xw + 0.19, 0, 0.20)], 10)
    A.sweep(arm, r=0.008, mat="brass_polished", gax=0)
    A.lathe(round_poly([(0, 0.19), (0.03, 0.19), (0.04, 0.205), (0.034, 0.215), (0.012, 0.22), (0, 0.22)], 0.003, closed=False), at=(xw + 0.19, 0, 0.0), mat="brass_polished", n=40)
    A.cyl(0.016, 0.05, at=(xw + 0.19, 0, 0.22), mat="brass", n=24, bevel=0.002)
    A.sphere(0.022, at=(xw + 0.19, 0, 0.29), mat="emit", seg=16, rings=10, scale=(1, 1, 1.4), piece="Emissive")
    shade = [(0.045, 0.215), (0.05, 0.22), (0.07, 0.30), (0.075, 0.36), (0.072, 0.365), (0.067, 0.36), (0.062, 0.30), (0.043, 0.222)]
    A.lathe(shade, at=(xw + 0.19, 0, 0.0), mat="glass_frosted", n=32, piece="Glass", cap=False, smooth=60)
    A.point("WallMount", (xw, 0, 0.13))
    A.point("Light", (xw + 0.19, 0, 0.29))
    A.preview["Glass"] = {"glass": {"trans": 0.5, "rough": 0.5, "emit": 3.0}}
    A.preview["Emissive"] = {"emit": (1.0, 0.75, 0.45, 30.0)}
    A.view = (1.0, -0.9, 0.25)


# ======================================================================================
# Neon sign: cursive "Velvet" in single-stroke tubes on a black backplate
# ======================================================================================

# Hand-authored single-stroke script, (u, v) in sign units (u to the viewer's right, v up).
VELVET_STROKES = [
    [(0.00, 0.27), (0.02, 0.31), (0.05, 0.31), (0.075, 0.24), (0.10, 0.13), (0.12, 0.05), (0.135, 0.015), (0.155, 0.05), (0.18, 0.15), (0.205, 0.25), (0.23, 0.31), (0.255, 0.33), (0.275, 0.31)],
    [(0.235, 0.06), (0.27, 0.075), (0.30, 0.10), (0.325, 0.135), (0.322, 0.158), (0.30, 0.16), (0.282, 0.13), (0.28, 0.07), (0.295, 0.03), (0.32, 0.015), (0.35, 0.025),
     (0.375, 0.07), (0.395, 0.16), (0.408, 0.25), (0.41, 0.30), (0.398, 0.318), (0.383, 0.30), (0.38, 0.22), (0.382, 0.11), (0.39, 0.04), (0.41, 0.015), (0.435, 0.025),
     (0.452, 0.07), (0.462, 0.12), (0.466, 0.14), (0.475, 0.10), (0.488, 0.04), (0.50, 0.015), (0.515, 0.05), (0.528, 0.11), (0.536, 0.14), (0.548, 0.13), (0.562, 0.112),
     (0.585, 0.115), (0.61, 0.135), (0.606, 0.16), (0.585, 0.16), (0.568, 0.12), (0.57, 0.06), (0.585, 0.025), (0.61, 0.015), (0.64, 0.03), (0.665, 0.08), (0.678, 0.15),
     (0.686, 0.235), (0.678, 0.15), (0.68, 0.07), (0.692, 0.025), (0.715, 0.015), (0.745, 0.04)],
    [(0.652, 0.160), (0.69, 0.163), (0.725, 0.168)],
    [(0.06, -0.035), (0.25, -0.05), (0.48, -0.052), (0.66, -0.04), (0.76, -0.01)],
]


@asset("NeonSign_Velvet", res=2048, collision="Box", edge=0.003, ao_dist=0.1)
def neon_sign(A):
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    W, Hs = 1.25, 0.62
    xw = -0.04
    z0 = 0.0
    plate = A.prism(round_poly(rrect_pts(W, Hs, 0.06, 8), 0.003), 0.012, mat="powder_black", plane="YZ", at=(xw + 0.026, 0, z0 + Hs / 2), bevel=0.004, segs=3)
    A.prism(round_poly(rrect_pts(W - 0.03, Hs - 0.03, 0.05, 8), 0.002), 0.004, mat="brass_polished", plane="YZ", at=(xw + 0.034, 0, z0 + Hs / 2), bevel=0.0015)
    A.prism(round_poly(rrect_pts(W - 0.045, Hs - 0.045, 0.045, 8), 0.002), 0.006, mat="lacquer_black", plane="YZ", at=(xw + 0.036, 0, z0 + Hs / 2), bevel=0.0015)
    for y in (-W / 2 + 0.06, W / 2 - 0.06):
        for z in (0.06, Hs - 0.06):
            A.cyl(0.012, 0.022, at=(xw, y, z0 + z), axis="X", mat="brass", n=20, bevel=0.002)
            A.cyl(0.009, 0.004, at=(xw + 0.04, y, z0 + z), axis="X", mat="brass_polished", n=20, bevel=0.001)
    sc = 1.45
    u0, v0 = 0.37, 0.10
    xt = xw + 0.075
    for k, stroke in enumerate(VELVET_STROKES):
        pts = catmull(stroke, 6)
        path = [(xt, (p[0] - u0) * sc, z0 + Hs / 2 + (p[1] - v0) * sc - 0.08) for p in pts]
        A.sweep(path, r=0.0075, n=12, mat="emit", piece="Emissive", smooth=180)
        # electrodes: back-bends into black housings at both ends
        for end in (path[0], path[-1]):
            A.cyl(0.011, 0.034, at=(xw + 0.042, end[1], end[2]), axis="X", mat="powder_black", n=16, bevel=0.002)
        # tube supports every ~0.14 m
        acc = 0.0
        for i in range(1, len(path)):
            acc += (V(path[i]) - V(path[i - 1])).length
            if acc > 0.14 and 3 < i < len(path) - 3:
                acc = 0.0
                p = path[i]
                A.cyl(0.004, 0.034, at=(xw + 0.04, p[1], p[2]), axis="X", mat="plastic_grey", n=10, bevel=0.0008)
                A.cyl(0.0095, 0.008, at=(xt - 0.004, p[1], p[2]), axis="X", mat="plastic_grey", n=12, bevel=0.001)
    # transformer box under the sign
    A.box((0.05, 0.16, 0.05), at=(xw + 0.03, W / 2 - 0.2, z0 + 0.02), mat="powder_black", bevel=0.004)
    A.point("WallMount", (xw, 0, z0 + Hs / 2))
    A.point("Light", (xt + 0.1, 0, z0 + Hs / 2))
    A.preview["Emissive"] = {"emit": (1.0, 0.12, 0.45, 30.0)}
    A.view = (1.0, -0.35, 0.12)
    A.lens = 70


# ======================================================================================
# Concrete planter with a clipped boxwood ball
# ======================================================================================


@asset("Planter_Concrete", res=2048, collision="Convex", edge=0.006, ao_dist=0.2)
def planter(A):
    A.piece("Shrub", "Static", res=2048)
    A.cur = "Body"
    s2 = math.sqrt(2)
    prof = [(0, 0.04), (0.25 * s2, 0.04), (0.30 * s2, 0.70), (0.255 * s2, 0.70), (0.25 * s2, 0.64), (0, 0.64)]
    A.lathe(prof, mat="concrete", n=4, rot=(0, 0, 45), bevel=0.008, segs=3, smooth=30)
    A.box((0.44, 0.44, 0.04), at=(0, 0, 0.02), mat="concrete_dark", bevel=0.006, segs=2)
    # cast tie-holes and form lines on each face
    for sx, sy, rz in ((1, 0, 0), (-1, 0, 180), (0, 1, 90), (0, -1, -90)):
        for zz in (0.22, 0.46):
            for off in (-0.14, 0.14):
                r_at = 0.25 + 0.05 * zz / 0.70
                p = V((sx * r_at, sy * r_at, zz)) + V((-sy * off, sx * off, 0))
                A.cyl(0.011, 0.004, at=tuple(p - V((sx, sy, 0)) * 0.0035), axis="X", rot=(0, 0, rz), mat="concrete_dark", n=16, bevel=0.0015)
    # brass inlay band
    zb = 0.58
    rb = 0.25 + (0.30 - 0.25) * zb / 0.70
    A.lathe([(rb * s2 + 0.002, zb), (rb * s2 + 0.003, zb + 0.012), (0, zb + 0.012)], mat="brass", n=4, rot=(0, 0, 45), cap=False, smooth=30) if False else None
    for sx, sy, rz in ((1, 0, 0), (-1, 0, 180), (0, 1, 90), (0, -1, -90)):
        A.box((0.004, 2 * rb + 0.008, 0.012), at=(sx * (rb + 0.002), sy * (rb + 0.002), zb), rot=(0, -math.degrees(math.atan(0.05 / 0.70)) * 1, rz), mat="brass_polished", bevel=0.0015)
    A.box((0.505, 0.505, 0.02), at=(0, 0, 0.645), mat="soil", bevel=0.004)
    for i in range(5):
        a = i * 1.3
        A.cyl(0.015, 0.06, at=(0.015 * math.cos(a), 0.015 * math.sin(a), 0.64), mat="soil", n=8, r2=0.008, bevel=0.0)
    # boxwood: dark core + thousands of small leaves on a lumpy sphere
    A.cur = "Shrub"
    cz, R = 0.95, 0.31
    A.sphere(R - 0.02, at=(0, 0, cz), mat="leaves", seg=32, rings=16, piece="Body")
    rng = random.Random(11)
    verts, faces = [], []
    nleaves = 9000
    for i in range(nleaves):
        zz = rng.uniform(-0.75, 1.0)
        ph = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(max(0.0, 1 - zz * zz))
        nrm = V((rr * math.cos(ph), rr * math.sin(ph), zz))
        lump = 1.0 + 0.04 * math.sin(nrm.x * 9 + 1.3) * math.sin(nrm.y * 7 + 0.4) * math.sin(nrm.z * 8 + 2.0)
        c = V((0, 0, cz)) + nrm * (R * lump + rng.uniform(-0.012, 0.01))
        t = nrm.orthogonal().normalized()
        t.rotate(Matrix.Rotation(rng.uniform(0, math.pi * 2), 3, nrm))
        b = nrm.cross(t)
        tilt = rng.uniform(-0.6, 0.6)
        n2 = (nrm + t * tilt).normalized()
        L_, W_ = 0.011, 0.0065
        p0 = c - t * L_
        p1 = c + b * W_ + n2 * 0.002
        p2 = c + t * L_
        p3 = c - b * W_ + n2 * 0.002
        k = len(verts)
        verts += [tuple(p0), tuple(p1), tuple(p2), tuple(p3), tuple(c + n2 * 0.003)]
        faces += [(k, k + 1, k + 4), (k + 1, k + 2, k + 4), (k + 2, k + 3, k + 4), (k + 3, k, k + 4)]
    A.mesh(verts, faces, "leaves", recalc=False, smooth=0)
    A.view = (1.0, -0.7, 0.35)


# ======================================================================================
# Velvet rope post (brass stanchion) + rope piece hanging to the next post
# ======================================================================================


@asset("VelvetRopePost", res=2048, collision="Convex", edge=0.003, ao_dist=0.15)
def rope_post(A):
    A.piece("Rope", "Static", res=1024)
    A.cur = "Body"
    base = round_poly([(0, 0), (0.165, 0), (0.168, 0.008), (0.16, 0.02), (0.12, 0.04), (0.06, 0.06), (0.035, 0.075), (0, 0.075)], 0.006, closed=False)
    A.lathe(base, mat="brass_polished", n=64, smooth=50)
    A.cyl(0.155, 0.004, at=(0, 0, -0.003), mat="rubber", n=64, bevel=0.001)
    post = [(0, 0.07), (0.03, 0.07), (0.036, 0.09), (0.026, 0.11), (0.026, 0.86), (0.034, 0.875), (0.03, 0.89), (0, 0.89)]
    A.lathe(round_poly(post, 0.004, closed=False), mat="brass_polished", n=48, smooth=50, gax=2)
    A.lathe(round_poly([(0, 0.885), (0.02, 0.885), (0.012, 0.905), (0.0, 0.905)], 0.003, closed=False), mat="brass_polished", n=32)
    A.sphere(0.045, at=(0, 0, 0.945), mat="brass_polished", seg=48, rings=24)
    # rope ring (eye) on the -Y side
    A.sweep(ring_path(0.016, 0, 32), r=0.0045, mat="brass_polished", closed=True, rot=(90, 0, 0), at=(0, -0.045, 0.865)) if False else None
    eye = A.sweep([(0.016 * math.cos(2 * math.pi * i / 32), 0, 0.016 * math.sin(2 * math.pi * i / 32)) for i in range(32)], r=0.0045, mat="brass_polished", closed=True)
    eye.matrix_world = Matrix.Translation((0, -0.045, 0.86))
    A.box((0.012, 0.02, 0.012), at=(0, -0.031, 0.86), mat="brass_polished", bevel=0.003)
    # rope: velvet tube, brass end caps and snap hooks
    A.cur = "Rope"
    y0, y1, zr = -0.075, -1.425, 0.84
    path = catenary((0, y0 - 0.05, zr), (0, y1 + 0.05, zr), 0.24, 48)
    A.sweep(path, r=0.019, n=20, mat="velvet_burgundy", smooth=180, twist=6.0)
    for end, sgn in ((path[0], -1), (path[-1], 1)):
        e = V(end)
        A.lathe([(0, 0), (0.021, 0.0), (0.023, 0.01), (0.023, 0.05), (0.016, 0.06), (0, 0.065)], at=tuple(e), axis="Y", rot=(0, 0, 0) if sgn > 0 else (0, 0, 180), mat="brass_polished", n=32, smooth=50) if False else None
        cap = A.lathe(round_poly([(0, 0), (0.021, 0.0), (0.023, 0.012), (0.023, 0.05), (0.016, 0.062), (0, 0.066)], 0.003, closed=False), mat="brass_polished", n=32, smooth=50)
        d = (V(path[1]) - V(path[0])).normalized() if sgn < 0 else (V(path[-2]) - V(path[-1])).normalized()
        q = V((0, 0, 1)).rotation_difference(-d)
        cap.matrix_world = Matrix.Translation(e + d * 0.03) @ q.to_matrix().to_4x4()
        hook = A.sweep(catmull([(0, 0, 0), (0, 0, 0.02), (0.0, 0.0, 0.045), (0.0, 0.012, 0.055), (0.0, 0.022, 0.04)], 6), r=0.004, mat="brass_polished")
        hook.matrix_world = Matrix.Translation(e - d * 0.03) @ q.to_matrix().to_4x4()
    A.point("RopeStart", (0, -0.045, 0.86))
    A.point("RopeEnd", (0, y1 + 0.03, 0.86))
    A.view = (1.0, -0.9, 0.3)
    A.lens = 45


# ======================================================================================
# Street furniture
# ======================================================================================


@asset("StreetLamp", res=2048, collision="Convex", edge=0.004, ao_dist=0.2)
def street_lamp(A):
    A.piece("Glass", "Glass", res=1024, glass=True)
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    # fluted cast-iron base (octagonal plinth + bell)
    A.lathe(round_poly([(0, 0), (0.24, 0), (0.24, 0.05), (0.22, 0.07), (0.22, 0.10), (0, 0.10)], 0.006, closed=False), mat="cast_iron", n=8, rot=(0, 0, 22.5), smooth=30)
    bell = [(0, 0.10), (0.20, 0.10), (0.19, 0.16), (0.15, 0.28), (0.12, 0.50), (0.105, 0.70), (0.11, 0.74), (0.13, 0.76), (0.13, 0.80), (0.095, 0.83), (0.085, 0.86), (0, 0.86)]
    A.lathe(round_poly(bell, 0.008, closed=False), mat="cast_iron", n=48, smooth=50)
    # door panel on the base
    A.box((0.02, 0.10, 0.22), at=(0.14, 0, 0.40), rot=(0, -8, 0), mat="cast_iron", bevel=0.004)
    # fluted shaft
    A.lathe([(0, 0.86), (0.075, 0.86), (0.065, 3.20), (0, 3.20)], mat="cast_iron", n=48, smooth=50)
    for i in range(16):
        a = 2 * math.pi * i / 16
        A.sweep([(0.07 * math.cos(a), 0.07 * math.sin(a), 0.92), (0.0625 * math.cos(a), 0.0625 * math.sin(a), 3.12)], r=0.009, n=8, mat="cast_iron", smooth=60)
    for z in (0.90, 2.0, 3.15):
        A.lathe(round_poly([(0, z), (0.095, z), (0.10, z + 0.02), (0.095, z + 0.04), (0, z + 0.04)], 0.004, closed=False), mat="cast_iron", n=48)
    # ladder bar
    A.sweep([(0.0, -0.32, 3.0), (0.0, 0.32, 3.0)], r=0.014, mat="cast_iron")
    for s in (-1, 1):
        A.sphere(0.025, at=(0, s * 0.33, 3.0), mat="cast_iron", seg=16, rings=8)
    # lantern: 4 posts, cap, glass panes, bulb
    zl = 3.24
    A.lathe(round_poly([(0, zl - 0.04), (0.12, zl - 0.04), (0.16, zl), (0.16, zl + 0.03), (0, zl + 0.03)], 0.006, closed=False), mat="cast_iron", n=4, rot=(0, 0, 45), smooth=30)
    w0, w1, hl = 0.11, 0.17, 0.48
    for i in range(4):
        a = math.radians(45 + 90 * i)
        A.sweep([(w0 * math.sqrt(2) * math.cos(a), w0 * math.sqrt(2) * math.sin(a), zl + 0.03), (w1 * math.sqrt(2) * math.cos(a), w1 * math.sqrt(2) * math.sin(a), zl + 0.03 + hl)], r=0.012, n=8, mat="cast_iron")
    for i in range(4):
        a0_ = math.radians(45 + 90 * i)
        a1_ = math.radians(45 + 90 * (i + 1))
        p = [(w0 * math.sqrt(2) * math.cos(a0_), w0 * math.sqrt(2) * math.sin(a0_), zl + 0.035), (w0 * math.sqrt(2) * math.cos(a1_), w0 * math.sqrt(2) * math.sin(a1_), zl + 0.035),
             (w1 * math.sqrt(2) * math.cos(a1_), w1 * math.sqrt(2) * math.sin(a1_), zl + 0.025 + hl), (w1 * math.sqrt(2) * math.cos(a0_), w1 * math.sqrt(2) * math.sin(a0_), zl + 0.025 + hl)]
        A.mesh(p, [(0, 1, 2, 3)], "glass_lamp", piece="Glass", smooth=0, recalc=False)
    A.lathe([(0, zl + 0.03), (0.03, zl + 0.03), (0.03, zl + 0.10), (0, zl + 0.10)], mat="steel_dark", n=16)
    A.lathe([(0, zl + 0.10), (0.02, zl + 0.10), (0.045, zl + 0.16), (0.045, zl + 0.22), (0.03, zl + 0.27), (0, zl + 0.29)], mat="emit", n=24, piece="Emissive", smooth=180)
    zc = zl + 0.03 + hl
    cap = [(0, zc), (0.27, zc), (0.28, zc + 0.02), (0.22, zc + 0.06), (0.10, zc + 0.16), (0.06, zc + 0.20), (0.07, zc + 0.23), (0.03, zc + 0.27), (0.04, zc + 0.30), (0.0, zc + 0.36)]
    A.lathe(round_poly(cap, 0.006, closed=False), mat="cast_iron", n=4, rot=(0, 0, 45), smooth=30)
    A.sphere(0.035, at=(0, 0, zc + 0.36), mat="cast_iron", seg=16, rings=8)
    A.point("Light", (0, 0, zl + 0.2))
    A.preview["Emissive"] = {"emit": (1.0, 0.72, 0.4, 60.0)}
    A.preview["Glass"] = {"glass": {"trans": 1.0, "rough": 0.05}}
    A.view = (1.0, -0.6, 0.15)
    A.lens = 50


@asset("Bollard", res=2048, collision="Convex", edge=0.003, ao_dist=0.12)
def bollard(A):
    A.lathe(round_poly([(0, 0), (0.15, 0), (0.15, 0.015), (0.12, 0.03), (0, 0.03)], 0.004, closed=False), mat="galvanized", n=64)
    for i in range(4):
        a = math.radians(45 + 90 * i)
        A.cyl(0.012, 0.014, at=(0.12 * math.cos(a), 0.12 * math.sin(a), 0.03), mat="steel", n=6, bevel=0.002)
    A.lathe([(0, 0.03), (0.10, 0.03), (0.10, 0.86), (0, 0.86)], mat="powder_black", n=64, smooth=50)
    for z in (0.66, 0.74):
        A.lathe([(0.1005, z), (0.1015, z), (0.1015, z + 0.05), (0.1005, z + 0.05)], mat="paint_white", n=64, cap=False, smooth=60)
    A.lathe(round_poly([(0, 0.85), (0.105, 0.85), (0.105, 0.88), (0.09, 0.91), (0.05, 0.93), (0, 0.935)], 0.006, closed=False), mat="steel", n=64, smooth=50, gax=2)
    A.view = (1.0, -0.7, 0.3)


@asset("TrashBags", res=2048, collision="Convex", edge=0.004, ao_dist=0.2)
def trash_bags(A):
    rng = random.Random(5)
    bags = [((0.0, 0.0), 0.30, 0.62), ((0.42, 0.25), 0.27, 0.58), ((-0.36, 0.32), 0.28, 0.52), ((0.18, -0.40), 0.25, 0.55), ((-0.18, -0.24), 0.22, 0.40), ((0.05, 0.12), 0.22, 0.45)]
    for k, ((bx, by), r, h) in enumerate(bags):
        zbase = 0.0 if k < 4 else 0.28
        if k == 5:
            bx, by, zbase = 0.10, 0.08, 0.40
        seed = rng.uniform(0, 10)
        lumps = []
        for _ in range(7):
            d = V((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized() * rng.uniform(7, 16)
            lumps.append((d, rng.uniform(0, 6.28), rng.uniform(0.05, 0.10)))
        folds = [(rng.randint(5, 12), rng.uniform(0, 6.28), rng.uniform(0.04, 0.08)) for _ in range(3)]
        sq = (rng.uniform(0.85, 1.2), rng.uniform(0.85, 1.2))
        lean = V((rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), 0))

        def bag_fn(u, v, r=r, h=h, lumps=lumps, folds=folds, sq=sq, lean=lean):
            a = 2 * math.pi * u
            if v < 0.84:
                t = v / 0.84
                body = math.sin(math.pi * min(1.0, 0.06 + t * 0.96)) ** 0.5
                rad = r * body * (1.0 + 0.32 * (1 - t) ** 3)
                z = h * 0.86 * (t if t > 0.06 else 0.06 * (t / 0.06) ** 0.5)
            else:
                t = (v - 0.84) / 0.16
                rad = r * (0.14 * (1 - t) + 0.03)
                z = h * 0.86 + h * 0.16 * t
            p0 = V((rad * sq[0] * math.cos(a), rad * sq[1] * math.sin(a), z))
            w = 0.0
            for d, ph, amp in lumps:
                w += amp * math.sin(d.dot(p0) + ph)
            neck = max(0.0, min(1.0, (v - 0.55) / 0.29))
            for k, ph, amp in folds:
                w -= amp * neck * abs(math.sin(a * k + ph + v * 3.0))
            w *= min(1.0, v / 0.08)
            p = p0 * (1.0 + w) if v < 0.98 else p0
            return tuple(p + lean * (z / h) * h)

        ob = A.grid(bag_fn, 96, 56, mat="trashbag", closed_u=True, recalc=False)
        ob.matrix_world = Matrix.Translation((bx, by, zbase)) @ Matrix.Rotation(rng.uniform(-0.25, 0.25), 4, "X") @ Matrix.Rotation(rng.uniform(0, 6.28), 4, "Z")
        # knot ears
        for s in (-1, 1):
            e = A.sweep(catmull([(0, 0, h * 1.0), (s * 0.05, 0.01, h * 1.06), (s * 0.09, 0.02, h * 1.03), (s * 0.11, 0.0, h * 0.98)], 5), prof=circle_pts(0.014, 10, rx=0.004), mat="trashbag", smooth=180, scales=[1.0, 1.2, 1.4, 1.5, 1.6, 1.6, 1.5, 1.3, 1.1, 0.9, 0.7, 0.5, 0.4, 0.3, 0.2, 0.2][:16])
            e.matrix_world = ob.matrix_world.copy()
    A.view = (1.0, -0.6, 0.45)


@asset("Dumpster", res=2048, collision="Box", edge=0.006, ao_dist=0.3)
def dumpster(A):
    W, D = 1.85, 1.10
    # body: trapezoid side profile (front lower/sloped), x front
    side = [(-D / 2, 0.16), (D / 2 - 0.15, 0.16), (D / 2, 0.40), (D / 2, 1.10), (-D / 2, 1.20)]
    A.prism(list(reversed(side)) if False else side, W, mat="paint_dumpster", plane="XZ", bevel=0.012, segs=2)
    # top rim lip
    A.sweep([(D / 2 + 0.02, W / 2 + 0.02, 1.11), (-D / 2 - 0.02, W / 2 + 0.02, 1.21), (-D / 2 - 0.02, -W / 2 - 0.02, 1.21), (D / 2 + 0.02, -W / 2 - 0.02, 1.11)],
            prof=round_poly(rrect_pts(0.05, 0.04, 0.008), 0.003), mat="paint_dumpster", closed=True)
    # vertical ribs on the sides + front
    for s in (-1, 1):
        for x in (-0.3, 0.1):
            A.box((0.08, 0.04, 0.95), at=(x, s * (W / 2 + 0.02), 0.66), mat="paint_dumpster", bevel=0.008)
        # fork pockets
        A.box((0.9, 0.12, 0.14), at=(0.0, s * (W / 2 + 0.06), 0.80), mat="paint_dumpster", bevel=0.01) if False else None
    for y in (-0.6, 0.0, 0.6):
        A.box((0.04, 0.08, 0.68), at=(D / 2 + 0.02, y, 0.75), mat="paint_dumpster", bevel=0.008)
    for s in (-1, 1):
        A.box((0.16, 0.18, 0.12), at=(0.0, s * 0.6, 1.25), mat="paint_dumpster", bevel=0.01) if False else None
    # fork pockets on the sides
    for s in (-1, 1):
        A.box((0.95, 0.16, 0.13), at=(-0.02, s * (W / 2 + 0.07), 0.82), mat="paint_dumpster", bevel=0.012)
    # lids (black HDPE), slightly open
    for s in (-1, 1):
        lid = A.box((D + 0.08, W / 2 - 0.01, 0.05), at=(0, 0, 0), mat="plastic_case", bevel=0.015, segs=3)
        ribs = [A.box((D, 0.03, 0.025), at=(0, yy, 0.035), mat="plastic_case", bevel=0.008) for yy in (-0.25, 0.0, 0.25)]
        ang = math.degrees(math.atan2(0.10, D)) + (6 if s > 0 else 0)
        M = Matrix.Translation((-D / 2 - 0.03, s * (W / 4 + 0.0), 1.235)) @ Matrix.Rotation(math.radians(ang), 4, "Y") @ Matrix.Translation(((D + 0.08) / 2, 0, 0))
        for o in [lid] + ribs:
            o.matrix_world = M @ o.matrix_world
        A.box((0.06, 0.12, 0.06), at=(-D / 2 - 0.02, s * (W / 4), 1.20), mat="plastic_case", bevel=0.01)
    # casters
    for x in (-D / 2 + 0.14, D / 2 - 0.25):
        for y in (-W / 2 + 0.15, W / 2 - 0.15):
            A.box((0.14, 0.12, 0.02), at=(x, y, 0.155), mat="galvanized", bevel=0.003)
            A.box((0.02, 0.08, 0.08), at=(x - 0.03, y, 0.11), mat="galvanized", bevel=0.003)
            A.cyl(0.055, 0.045, at=(x - 0.03, y - 0.0225, 0.055), axis="Y", mat="rubber", n=24, bevel=0.006)
    A.view = (1.0, -0.7, 0.4)


@asset("Kiosk", res=2048, collision="Box", edge=0.005, ao_dist=0.3)
def kiosk(A):
    W, D, H = 2.4, 1.5, 2.45
    # plinth and box body (front opening with counter)
    A.box((D + 0.05, W + 0.05, 0.12), at=(0, 0, 0.06), mat="concrete_dark", bevel=0.01)
    for s in (-1, 1):
        A.box((D, 0.06, H - 0.12), at=(0, s * (W / 2 - 0.03), 0.12 + (H - 0.12) / 2), mat="paint_kiosk", bevel=0.008, gax=2)
    A.box((0.06, W, H - 0.12), at=(-D / 2 + 0.03, 0, 0.12 + (H - 0.12) / 2), mat="paint_kiosk", bevel=0.008, gax=2)
    # lower front: panelled counter
    A.box((0.06, W - 0.12, 0.95), at=(D / 2 - 0.03, 0, 0.12 + 0.475), mat="paint_kiosk", bevel=0.008)
    for i in range(3):
        y = -W / 2 + 0.06 + (i + 0.5) * (W - 0.12) / 3
        A.box((0.02, (W - 0.12) / 3 - 0.12, 0.70), at=(D / 2 + 0.005, y, 0.6), mat="paint_kiosk", bevel=0.012, segs=1)
    A.box((0.36, W + 0.04, 0.04), at=(D / 2 + 0.08, 0, 1.09), mat="walnut", bevel=0.006, gax=1)
    A.box((0.02, W + 0.04, 0.012), at=(D / 2 + 0.26, 0, 1.09), mat="brass", bevel=0.003, gax=1)
    # interior: magazine racks on the side walls + back shelves stacked with papers
    for tier in range(4):
        z = 1.25 + tier * 0.24
        A.box((0.22, W - 0.2, 0.02), at=(-D / 2 + 0.17, 0, z), mat="walnut", bevel=0.003, gax=1)
        for k in range(14):
            y = -W / 2 + 0.2 + k * (W - 0.4) / 13
            A.box((0.012, 0.15, 0.21), at=(-D / 2 + 0.15, y, z + 0.11), rot=(0, -12, 0), mat="magazines", bevel=0.001)
    for k in range(10):
        y = -W / 2 + 0.25 + k * (W - 0.5) / 9
        h = 0.04 + (k % 3) * 0.03
        A.box((0.30, 0.22, h), at=(D / 2 + 0.06, y * 0.98, 1.11 + h / 2), mat="magazines", bevel=0.002)
    # canopy roof with overhang + fascia sign band
    A.box((D + 0.5, W + 0.5, 0.06), at=(0.12, 0, H + 0.03), mat="paint_kiosk", bevel=0.01)
    A.box((0.06, W + 0.5, 0.28), at=(D / 2 + 0.37, 0, H - 0.08), mat="paint_kiosk", bevel=0.008)
    for s in (-1, 1):
        A.box((D + 0.5, 0.06, 0.28), at=(0.12, s * (W / 2 + 0.22), H - 0.08), mat="paint_kiosk", bevel=0.008)
    A.box((0.012, W, 0.16), at=(D / 2 + 0.405, 0, H - 0.08), mat="brass", bevel=0.003, gax=1)
    A.text("NEWS  &  TOBACCO", font("LibreBaskerville-Regular.ttf"), 0.12, 0.01, at=(D / 2 + 0.411, 0, H - 0.135), rot=(90, 0, 90), mat="paint_kiosk")
    A.lathe(round_poly([(0, H + 0.06), (0.9, H + 0.06), (0.15, H + 0.40), (0, H + 0.42)], 0.02, closed=False), at=(0.12, 0, 0), mat="paint_kiosk", n=4, rot=(0, 0, 45), smooth=30) if False else None
    roof = [(-D / 2 - 0.13, H + 0.06), (D / 2 + 0.37, H + 0.06), (D / 2 + 0.2, H + 0.16), (0.12, H + 0.36), (-D / 2, H + 0.16)]
    A.prism(roof, W + 0.5, mat="galvanized", plane="XZ", bevel=0.008)
    # rolling shutter box above the opening
    A.cyl(0.11, W - 0.14, at=(D / 2 - 0.06, -W / 2 + 0.07, H - 0.25), axis="Y", rot=(0, 0, 0), mat="paint_kiosk", n=32, bevel=0.006) if False else None
    A.box((0.20, W - 0.12, 0.22), at=(D / 2 - 0.10, 0, H - 0.23), mat="paint_kiosk", bevel=0.008)
    A.view = (1.0, -0.6, 0.3)
    A.lens = 45
