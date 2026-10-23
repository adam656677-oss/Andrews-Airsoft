"""The Armory props (walnut + brass hotel gun room)."""

import math
import random
from mathutils import Vector as V, Matrix

import bpy
import numpy as np
import propkit as pk
from propkit import round_poly, circle_pts, rrect_pts, catmull
from club_registry import asset, font
from club_assets import raised_panel_x, ring_path, catenary, tufted_panel_x


# ======================================================================================
# Gun display bay: recessed walnut case, brass frame, leather back, LED halo, plaque
# ======================================================================================


@asset("GunDisplayBay", group="Armory", res=4096, collision="Box", edge=0.004, ao_dist=0.25)
def gun_display_bay(A):
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.piece("Plaque", "Static", res=1024)
    A.cur = "Body"
    W, H, D = 1.40, 1.20, 0.26
    xb = -D / 2  # back (wall) plane
    xf = D / 2
    t = 0.07
    # carcass boards (top/bottom/sides) with moulded fronts
    A.box((D, W, t), at=(0, 0, H - t / 2), mat="walnut", bevel=0.004, gax=1)
    A.box((D, W, t + 0.03), at=(0, 0, (t + 0.03) / 2), mat="walnut", bevel=0.004, gax=1)
    for s in (-1, 1):
        A.box((D, t, H), at=(0, s * (W / 2 - t / 2), H / 2), mat="walnut", bevel=0.004, gax=2)
    # cornice + base moulding
    cor = round_poly([(0.0, 0.0), (0.03, 0.0), (0.045, 0.015), (0.045, 0.035), (0.03, 0.05), (0.0, 0.06)], 0.005)
    A.prism([(xf - 0.01 + p[0], H - 0.06 + p[1]) for p in cor], W + 0.06, mat="walnut", plane="XZ", bevel=0.003, smooth=35, gax=1)
    for s in (-1, 1):
        A.prism([(-(p[0]) , H - 0.06 + p[1]) for p in cor], 0.0, mat="walnut") if False else None
    A.prism([(xf - 0.01 + p[0], -0.0 + p[1] * 0.8) for p in cor], W + 0.04, mat="walnut", plane="XZ", bevel=0.003, smooth=35, gax=1)
    for s in (-1, 1):
        for k in range(5):
            A.cyl(0.0045, H - 0.2, at=(xf + 0.0005, s * (W / 2 - 0.016 - k * 0.0095), 0.11), mat="walnut", n=10, bevel=0.0, gax=2)
    A.box((0.02, W + 0.08, 0.012), at=(xf + 0.03, 0, H + 0.004), mat="brass", bevel=0.003, gax=1)
    # back + leather panel with stitched welt
    A.box((0.02, W - 2 * t, H - 2 * t), at=(xb + 0.01, 0, H / 2), mat="walnut_satin", bevel=0.002, gax=2)
    A.box((0.012, W - 2 * t - 0.01, H - 2 * t - 0.04), at=(xb + 0.026, 0, H / 2 + 0.01), mat="leather_cognac", bevel=0.004, segs=2)
    tufted_panel_x(A, xb + 0.032, -(W / 2 - t) + 0.02, (W / 2 - t) - 0.02, t + 0.05, H - t - 0.02, "leather_cognac", su=0.07, sz=0.09, puff=0.028, res=0.005, button_mat="brass_aged")
    # inner recess lining (side/top/bottom inner faces)
    # brass frame bezel (L-section) around the opening
    ow, oh = W - 2 * t, H - 2 * t - 0.03
    zc = t + 0.03 + oh / 2
    bez = [(xf + 0.004, ow / 2 + 0.03, zc - oh / 2 - 0.03), (xf + 0.004, -ow / 2 - 0.03, zc - oh / 2 - 0.03), (xf + 0.004, -ow / 2 - 0.03, zc + oh / 2 + 0.03), (xf + 0.004, ow / 2 + 0.03, zc + oh / 2 + 0.03)]
    A.sweep(bez, prof=round_poly([(-0.008, -0.022), (0.004, -0.022), (0.004, 0.022), (-0.008, 0.022)], 0.003), mat="brass", closed=True, gax=1)
    inner = [(xf - 0.03, ow / 2 - 0.004, zc - oh / 2 + 0.004), (xf - 0.03, -ow / 2 + 0.004, zc - oh / 2 + 0.004), (xf - 0.03, -ow / 2 + 0.004, zc + oh / 2 - 0.004), (xf - 0.03, ow / 2 - 0.004, zc + oh / 2 - 0.004)]
    A.sweep(inner, prof=round_poly([(-0.03, -0.004), (0.03, -0.004), (0.03, 0.004), (-0.03, 0.004)], 0.002), mat="brass_aged", closed=True, gax=1)
    # LED halo: strips tucked behind the bezel, aimed at the leather
    for (y0, z0_, y1, z1_) in ((ow / 2 - 0.012, zc - oh / 2 + 0.012, -ow / 2 + 0.012, zc - oh / 2 + 0.012), (-ow / 2 + 0.012, zc + oh / 2 - 0.012, ow / 2 - 0.012, zc + oh / 2 - 0.012)):
        A.box((0.014, abs(y1 - y0), 0.004), at=(xf - 0.065, 0, z0_), mat="emit", bevel=0.0, piece="Emissive")
        A.box((0.02, abs(y1 - y0), 0.012), at=(xf - 0.065, 0, z0_ + (0.008 if z0_ < zc else -0.008)), mat="aluminium", bevel=0.002, gax=1)
    for s in (-1, 1):
        A.box((0.014, 0.004, oh - 0.03), at=(xf - 0.065, s * (ow / 2 - 0.012), zc), mat="emit", bevel=0.0, piece="Emissive")
        A.box((0.02, 0.012, oh - 0.03), at=(xf - 0.065, s * (ow / 2 - 0.004), zc), mat="aluminium", bevel=0.002, gax=2)
    # brass gun pegs with leather saddles
    zg = zc - 0.075  # pegs sit under the gun, whose centre is the recess centre (GunMount)
    for s in (-1, 1):
        y = s * 0.36
        A.lathe(round_poly([(0, 0), (0.03, 0), (0.03, 0.008), (0.012, 0.016), (0, 0.016)], 0.002, closed=False), at=(xb + 0.045, y, zg), axis="X", mat="brass_polished", n=32)
        A.cyl(0.009, 0.10, at=(xb + 0.05, y, zg), axis="X", mat="brass_polished", n=24, bevel=0.002)
        A.box((0.05, 0.04, 0.02), at=(xb + 0.12, y, zg + 0.012), mat="leather_black", bevel=0.008, segs=3)
        A.sphere(0.014, at=(xb + 0.155, y, zg + 0.02), mat="brass_polished", seg=20, rings=10)
    # plaque on the bottom rail
    A.cur = "Plaque"
    pw, ph = 0.22, 0.055
    pl = A.box((0.004, pw, ph), at=(xf + 0.003, 0, 0.05), mat="plaque_brass", bevel=0.0012, segs=2)
    A.vattr(pl, "luv", lambda co: (0.5 + co.y / pw, co.z / ph + 0.5, 1.0))
    for y in (-pw / 2 + 0.008, pw / 2 - 0.008):
        for z in (0.05 - ph / 2 + 0.008, 0.05 + ph / 2 - 0.008):
            A.sphere(0.0028, at=(xf + 0.005, y, z), mat="brass_polished", seg=10, rings=6, scale=(0.5, 1, 1))
    A.point("GunMount", (xb + 0.10, 0.0, zc))
    A.point("Plaque", (xf + 0.005, 0.0, 0.05))
    A.point("WallMount", (xb, 0.0, H / 2))
    A.preview["Emissive"] = {"emit": (1.0, 0.8, 0.55, 80.0)}
    A.view = (1.0, -0.55, 0.15)
    A.lens = 55


# ======================================================================================
# Armory counter: walnut with green leather inlay top and brass details
# ======================================================================================


@asset("ArmoryCounter", group="Armory", res=4096, collision="Box", edge=0.004, ao_dist=0.3)
def armory_counter(A):
    L, Dp, H = 2.4, 0.72, 1.0
    xf, xb = 0.30, -0.36
    A.box((0.56, L - 0.06, 0.10), at=((xf + xb) / 2 - 0.02, 0, 0.05), mat="powder_black", bevel=0.003)
    A.box((0.004, L - 0.06, 0.09), at=(xf - 0.045, 0, 0.05), mat="brass", bevel=0.0015, gax=1)
    A.box((xf - xb - 0.03, L - 0.02, H - 0.14), at=((xf + xb) / 2 - 0.015, 0, 0.10 + (H - 0.14) / 2), mat="walnut_satin", bevel=0.004, gax=2)
    nb = 3
    bw = (L - 0.02) / nb
    for i in range(nb):
        y0 = -L / 2 + 0.01 + i * bw
        raised_panel_x(A, y0 + 0.012, y0 + bw - 0.012, 0.14, H - 0.12, xf - 0.022, mat="walnut", frame=0.08)
    for s in (-1, 1):
        A.box((0.05, 0.05, H - 0.12), at=(xf - 0.0, s * (L / 2 - 0.015), 0.10 + (H - 0.12) / 2 - 0.0), mat="walnut", bevel=0.006, gax=2)
        A.box((0.054, 0.054, 0.05), at=(xf, s * (L / 2 - 0.015), 0.125), mat="brass", bevel=0.004)
    # fluted pilasters with brass capitals between the panels
    for i in range(1, nb):
        y = -L / 2 + 0.01 + i * bw
        A.box((0.03, 0.06, H - 0.26), at=(xf - 0.005, y, 0.13 + (H - 0.26) / 2), mat="walnut", bevel=0.004, gax=2)
        for k in range(4):
            A.cyl(0.0045, H - 0.34, at=(xf + 0.0095, y - 0.018 + k * 0.012, 0.17), mat="walnut", n=10, bevel=0.0, gax=2)
        A.box((0.04, 0.07, 0.03), at=(xf, y, H - 0.13), mat="brass_polished", bevel=0.004, segs=2)
        A.box((0.04, 0.07, 0.03), at=(xf, y, 0.14), mat="brass_polished", bevel=0.004, segs=2)
    # apron moulding under the top
    prof = round_poly([(0, 0), (0.0, -0.06), (0.015, -0.06), (0.025, -0.04), (0.035, -0.02), (0.04, 0)], 0.005, closed=True)
    A.prism([(xf - 0.02 + p[0], H + p[1]) for p in reversed(prof)], L, mat="walnut", plane="XZ", bevel=0.002, smooth=35, gax=1)
    # top: walnut border, inset leather, brass inlay line, brass corner guards
    zt = H
    top_prof = round_poly([(xb - 0.02, 0), (xf + 0.06, 0), (xf + 0.075, 0.01), (xf + 0.07, 0.025), (xf + 0.075, 0.035), (xf + 0.065, 0.045), (xb - 0.02, 0.045)], 0.004)
    A.prism(top_prof, L + 0.04, at=(0, 0, zt), mat="walnut", plane="XZ", bevel=0.003, smooth=35, gax=1)
    A.box((Dp - 0.14, L - 0.16, 0.004), at=((xf + xb) / 2 + 0.03, 0, zt + 0.0455), mat="leather_green", bevel=0.0015)
    for (sx, sy) in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        cx = (xf + 0.075) if sx > 0 else (xb - 0.02)
        cy = sy * (L + 0.04) / 2
        A.box((0.05, 0.05, 0.05), at=(cx - sx * 0.022, cy - sy * 0.022, zt + 0.0225), mat="brass_polished", bevel=0.006, segs=2)
    r = [(xf + xb) / 2 + 0.03 + (Dp - 0.10) / 2, (xf + xb) / 2 + 0.03 - (Dp - 0.10) / 2]
    path = [(r[0], L / 2 - 0.06, zt + 0.0452), (r[1], L / 2 - 0.06, zt + 0.0452), (r[1], -L / 2 + 0.06, zt + 0.0452), (r[0], -L / 2 + 0.06, zt + 0.0452)]
    A.sweep(path, prof=round_poly([(-0.0015, -0.003), (0.0015, -0.003), (0.0015, 0.003), (-0.0015, 0.003)], 0.0008), mat="brass_polished", closed=True)
    # staff side: drawers with brass cup pulls
    for i in range(4):
        y = -L / 2 + 0.31 + i * (L - 0.62) / 3
        A.box((0.02, 0.52, 0.18), at=(xb - 0.0, y, 0.84), mat="walnut", bevel=0.004, gax=1)
        A.box((0.02, 0.52, 0.52), at=(xb - 0.0, y, 0.44), mat="walnut", bevel=0.004, gax=2)
        A.lathe([(0, 0), (0.012, 0), (0.012, 0.01), (0.03, 0.022), (0, 0.022)], at=(xb - 0.01, y, 0.86), axis="X", rot=(0, 0, 180), mat="brass_polished", n=24) if False else None
        A.box((0.02, 0.10, 0.02), at=(xb - 0.02, y, 0.86), mat="brass_polished", bevel=0.006, segs=3)
        A.box((0.02, 0.10, 0.02), at=(xb - 0.02, y, 0.62), mat="brass_polished", bevel=0.006, segs=3)
    A.point("Top", (0.0, 0.0, H + 0.045))
    A.view = (1.0, -0.6, 0.45)


# ======================================================================================
# Banker's lamp
# ======================================================================================


@asset("BankersLamp", group="Armory", res=2048, collision="Convex", edge=0.002, ao_dist=0.08)
def bankers_lamp(A):
    A.piece("Glass", "Glass", res=1024, glass=True)
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    A.lathe(round_poly([(0, 0), (0.095, 0), (0.098, 0.006), (0.09, 0.016), (0.06, 0.03), (0.03, 0.04), (0, 0.04)], 0.004, closed=False), mat="brass_polished", n=64, gax=2)
    A.cyl(0.092, 0.003, at=(0, 0, -0.002), mat="leather_green", n=48, bevel=0.0)
    A.lathe(round_poly([(0, 0.04), (0.012, 0.04), (0.010, 0.30), (0.016, 0.31), (0.016, 0.33), (0, 0.33)], 0.002, closed=False), mat="brass", n=32, gax=2)
    # harp arm forward + shade holder
    A.sweep(catmull([(0, 0, 0.32), (0.02, 0, 0.36), (0.06, 0, 0.375), (0.09, 0, 0.37)], 6), r=0.006, mat="brass")
    for s in (-1, 1):
        A.sweep(catmull([(0.09, 0, 0.37), (0.09, s * 0.08, 0.37), (0.09, s * 0.12, 0.385)], 5), r=0.004, mat="brass")
    # bulb
    A.lathe([(0, 0), (0.012, 0.0), (0.02, 0.03), (0.022, 0.06), (0.012, 0.085), (0, 0.09)], at=(0.09, 0, 0.36), axis="Y", rot=(0, 0, 0), mat="emit", n=16, piece="Emissive", smooth=180) if False else None
    b = A.lathe([(0, -0.08), (0.016, -0.08), (0.016, 0.08), (0, 0.08)], mat="emit", n=16, piece="Emissive", smooth=60)
    b.matrix_world = Matrix.Translation((0.09, 0, 0.385)) @ Matrix.Rotation(math.pi / 2, 4, "X")
    # cased green shade: trough with a curved section, closed ends
    def shade(u, v):
        y = (u - 0.5) * 0.27
        a = math.radians(-100 + 200 * v)
        rr = 0.075
        x = 0.09 + rr * 1.05 * math.sin(a) * (1 - 0.15 * (2 * u - 1) ** 4)
        z = 0.39 + rr * 0.85 * math.cos(a) * (1 - 0.15 * (2 * u - 1) ** 4)
        return (x, y, z)
    A.grid(shade, 40, 24, mat="glass_green", piece="Glass", smooth=180, recalc=False)
    for u, sgn in ((0.0, -1), (1.0, 1)):
        pts = [shade(u, v / 24) for v in range(25)]
        c = (0.09, (u - 0.5) * 0.27, 0.39)
        verts = [c] + pts
        faces = [(0, i + 1, i + 2) if sgn > 0 else (0, i + 2, i + 1) for i in range(24)]
        A.mesh(verts, faces, "glass_green", piece="Glass", smooth=0, recalc=False)
    # pull chain
    for i in range(14):
        A.sphere(0.0022, at=(0.11, 0.05, 0.36 - i * 0.006), mat="brass_polished", seg=8, rings=4)
    A.lathe([(0, 0), (0.005, 0.002), (0.005, 0.016), (0, 0.02)], at=(0.11, 0.05, 0.26), mat="brass_polished", n=12, smooth=180)
    A.point("Light", (0.09, 0, 0.385))
    A.preview["Glass"] = {"glass": {"trans": 0.2, "rough": 0.05, "emit": 0.6}}
    A.preview["Emissive"] = {"emit": (1.0, 0.8, 0.5, 15.0)}
    A.view = (1.0, -0.8, 0.35)


# ======================================================================================
# Wooden ammo crate with stencils, rope handles, steel corners
# ======================================================================================


@asset("AmmoCrate_Wood", group="Armory", res=2048, collision="Box", edge=0.004, ao_dist=0.15)
def ammo_crate(A):
    Lc, Dc, Hc = 0.80, 0.42, 0.30
    pt = 0.018
    rng = random.Random(3)
    # side planks (front/back = +-X), two per side with a small gap
    for s in (-1, 1):
        for k, (z0, z1) in enumerate(((0.012, 0.150), (0.154, Hc - 0.006))):
            p = A.box((pt, Lc - 2 * pt, z1 - z0), at=(s * (Dc / 2 - pt / 2), 0, (z0 + z1) / 2), mat="stencil_wood" if s > 0 else "pine", bevel=0.0025, gax=1)
            if s > 0:
                A.vattr(p, "luv", lambda co, z0=z0, z1=z1: (0.5 + co.y / (Lc - 0.12), ((co.z + (z0 + z1) / 2) - 0.03) / (Hc - 0.06), 1.0))
    # end panels (+-Y) with battens and rope handle cleats
    for s in (-1, 1):
        A.box((Dc, pt, Hc - 0.012), at=(0, s * (Lc / 2 - pt / 2), (Hc - 0.012) / 2 + 0.006), mat="pine", bevel=0.0025, gax=2)
        for z in (0.05, Hc - 0.06):
            A.box((Dc - 0.03, 0.022, 0.05), at=(0, s * (Lc / 2 + 0.011), z), mat="pine", bevel=0.003, gax=0)
        for x in (-0.11, 0.11):
            A.box((0.04, 0.03, 0.07), at=(x, s * (Lc / 2 + 0.015), 0.16), mat="pine", bevel=0.004, gax=2)
        rope = catmull([(-0.11, s * (Lc / 2 + 0.03), 0.16), (-0.06, s * (Lc / 2 + 0.06), 0.13), (0.0, s * (Lc / 2 + 0.07), 0.12), (0.06, s * (Lc / 2 + 0.06), 0.13), (0.11, s * (Lc / 2 + 0.03), 0.16)], 6)
        A.sweep(rope, r=0.009, n=10, mat="linen", twist=12.0, smooth=180)
    # bottom
    A.box((Dc, Lc, 0.014), at=(0, 0, 0.007), mat="pine", bevel=0.002, gax=1)
    for y in (-0.3, 0.0, 0.3):
        A.box((Dc - 0.02, 0.05, 0.02), at=(0, y, -0.002), mat="pine", bevel=0.003, gax=0)
    # lid: two planks + battens
    for k, x in enumerate((-Dc / 4, Dc / 4)):
        A.box((Dc / 2 - 0.004, Lc + 0.01, 0.02), at=(x, 0, Hc + 0.01), mat="pine", bevel=0.0025, gax=1)
    for y in (-Lc / 2 + 0.07, Lc / 2 - 0.07):
        A.box((Dc + 0.004, 0.06, 0.018), at=(0, y, Hc + 0.029), mat="pine", bevel=0.003, gax=0)
    # steel corner brackets + hasps + nails
    for sx in (-1, 1):
        for sy in (-1, 1):
            for z in (0.03, Hc - 0.02):
                A.box((0.045, 0.045, 0.04), at=(sx * (Dc / 2 - 0.018), sy * (Lc / 2 - 0.018), z), mat="steel_dark", bevel=0.004)
    for y in (-0.22, 0.22):
        A.box((0.004, 0.04, 0.09), at=(Dc / 2 + 0.002, y, Hc - 0.02), mat="steel_dark", bevel=0.0015)
        A.cyl(0.006, 0.012, at=(Dc / 2 + 0.004, y, Hc - 0.05), axis="X", mat="steel", n=12, bevel=0.001)
    for sx in (-1, 1):
        for y in [(-Lc / 2 + 0.04) + i * (Lc - 0.08) / 7 for i in range(8)]:
            for z in (0.06, 0.22):
                A.cyl(0.0035, 0.002, at=(sx * (Dc / 2 + 0.0), y, z), axis="X", rot=(0, 0, 0 if sx > 0 else 180), mat="steel_dark", n=8, bevel=0.0)
    A.view = (1.0, -0.6, 0.45)


# ======================================================================================
# Hard rifle case (open) with pick-and-pluck foam
# ======================================================================================


RIFLE_SIL = [(-0.52, 0.02), (-0.50, -0.04), (-0.36, -0.03), (-0.28, -0.075), (-0.22, -0.075), (-0.20, -0.02), (-0.12, -0.02), (-0.10, -0.09), (-0.06, -0.09), (-0.06, -0.02),
             (0.10, -0.02), (0.12, -0.035), (0.30, -0.03), (0.30, -0.008), (0.48, -0.008), (0.48, 0.01), (0.30, 0.012), (0.28, 0.03), (-0.10, 0.04), (-0.16, 0.055), (-0.36, 0.05), (-0.48, 0.06)]


def _inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
            c = not c
    return c


@asset("GunCase_Hard", group="Armory", res=2048, collision="Box", edge=0.003, ao_dist=0.12)
def gun_case(A):
    Lc, Dc, Hb, Hl = 1.22, 0.40, 0.11, 0.06
    # base shell
    A.box((Dc, Lc, Hb), at=(0, 0, Hb / 2), mat="plastic_case", bevel=0.03, segs=4)
    A.box((Dc - 0.02, Lc - 0.02, 0.012), at=(0, 0, Hb - 0.004), mat="powder_black", bevel=0.004)
    # pick-and-pluck foam (one mesh of cubes), rifle cut-out
    cell = 0.0155
    nx, ny = int((Dc - 0.03) / cell), int((Lc - 0.03) / cell)
    verts, faces = [], []
    ztop, zcut = Hb + 0.004, Hb - 0.035
    for i in range(nx):
        for j in range(ny):
            x = -(Dc - 0.03) / 2 + (i + 0.5) * cell
            y = -(Lc - 0.03) / 2 + (j + 0.5) * cell
            inside = _inside(RIFLE_SIL, y * 0.95, x * 1.9) or _inside([(p[0], p[1] - 0.12) for p in [(-0.08, -0.05), (0.08, -0.05), (0.08, 0.05), (-0.08, 0.05)]], y - 0.25, x)
            zt = zcut if inside else ztop
            h = cell * 0.47
            k = len(verts)
            for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h)):
                verts.append((x + dx, y + dy, zt - 0.03))
            for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h)):
                verts.append((x + dx, y + dy, zt))
            faces += [(k + 4, k + 5, k + 6, k + 7), (k, k + 1, k + 5, k + 4), (k + 1, k + 2, k + 6, k + 5), (k + 2, k + 3, k + 7, k + 6), (k + 3, k, k + 4, k + 7)]
    A.mesh(verts, faces, "foam", recalc=False, smooth=0, bevel=0.0012, segs=1)
    A.box((Dc - 0.03, Lc - 0.03, 0.04), at=(0, 0, Hb - 0.06), mat="foam", bevel=0.002)
    # latches + handle on the front (+X)
    for y in (-0.42, -0.14, 0.14, 0.42):
        A.box((0.02, 0.06, 0.05), at=(Dc / 2 + 0.006, y, Hb - 0.012), mat="plastic_black", bevel=0.006, segs=2)
        A.box((0.008, 0.03, 0.02), at=(Dc / 2 + 0.018, y, Hb - 0.002), mat="steel", bevel=0.002)
    A.sweep(catmull([(Dc / 2, -0.08, Hb - 0.035), (Dc / 2 + 0.05, -0.07, Hb - 0.04), (Dc / 2 + 0.055, 0.0, Hb - 0.042), (Dc / 2 + 0.05, 0.07, Hb - 0.04), (Dc / 2, 0.08, Hb - 0.035)], 6),
            prof=round_poly(rrect_pts(0.03, 0.016, 0.007), 0.002), mat="rubber", smooth=60)
    # lid: hinged on the back edge (-X), opened ~100 degrees
    lid = []
    lid.append(A.box((Dc, Lc, Hl), at=(Dc / 2, 0, Hl / 2), mat="plastic_case", bevel=0.025, segs=4))
    for k in range(5):
        lid.append(A.box((Dc - 0.08, 0.035, 0.008), at=(Dc / 2, -0.4 + k * 0.2, Hl + 0.002), mat="plastic_case", bevel=0.004))
    # convoluted (egg-crate) foam inside the lid
    def egg(u, v):
        x = 0.015 + (Dc - 0.03) * u
        y = -(Lc - 0.03) / 2 + (Lc - 0.03) * v
        z = 0.012 + 0.012 * (0.5 + 0.5 * math.sin(u * 2 * math.pi * 8) * math.sin(v * 2 * math.pi * 24))
        return (x, y, -z)
    lid.append(A.grid(egg, 64, 192, mat="foam", recalc=False, smooth=180))
    M = Matrix.Translation((-Dc / 2, 0, Hb)) @ Matrix.Rotation(math.radians(-100), 4, "Y")
    for o in lid:
        o.matrix_world = M @ o.matrix_world
    for y in (-0.45, 0.0, 0.45):
        A.cyl(0.008, 0.10, at=(-Dc / 2 - 0.004, y - 0.05, Hb), axis="Y", mat="steel", n=12, bevel=0.002)
    A.view = (1.0, -0.65, 0.6)


# ======================================================================================
# Tailor's dummy torso on a walnut tripod
# ======================================================================================


@asset("Mannequin_Torso", group="Armory", res=2048, collision="Convex", edge=0.004, ao_dist=0.2)
def mannequin(A):
    # tripod
    hub_z = 0.32
    A.lathe(round_poly([(0, hub_z - 0.05), (0.05, hub_z - 0.05), (0.05, hub_z + 0.05), (0, hub_z + 0.05)], 0.008, closed=False), mat="walnut_dark", n=32, gax=2)
    for i in range(3):
        a = 2 * math.pi * i / 3
        foot = (0.33 * math.cos(a), 0.33 * math.sin(a), 0.04)
        A.sweep(catmull([(0.03 * math.cos(a), 0.03 * math.sin(a), hub_z), (0.15 * math.cos(a), 0.15 * math.sin(a), hub_z - 0.12), foot], 8), r=0.018, n=16, mat="walnut", scales=[1.2 - 0.4 * k / 16 for k in range(17)], gax=0)
        A.lathe(round_poly([(0, 0.0), (0.022, 0.0), (0.02, 0.05), (0, 0.05)], 0.003, closed=False), at=(foot[0], foot[1], 0.0), mat="brass_polished", n=20)
    # pole + height collar
    A.lathe([(0, hub_z), (0.014, hub_z), (0.014, 0.98), (0, 0.98)], mat="brass", n=24, gax=2)
    A.lathe(round_poly([(0, 0.62), (0.03, 0.62), (0.03, 0.68), (0, 0.68)], 0.006, closed=False), mat="brass_polished", n=32)
    A.sweep([(0.03, 0, 0.65), (0.07, 0, 0.65)], r=0.006, mat="brass_polished")
    A.sphere(0.014, at=(0.075, 0, 0.65), mat="walnut_dark", seg=16, rings=8)
    # torso loft
    table = [(0.95, 0.165, 0.125), (0.98, 0.17, 0.13), (1.05, 0.155, 0.115), (1.12, 0.143, 0.105), (1.20, 0.155, 0.112), (1.30, 0.175, 0.124), (1.38, 0.185, 0.122), (1.44, 0.20, 0.11), (1.49, 0.18, 0.095), (1.53, 0.10, 0.075), (1.56, 0.06, 0.055), (1.60, 0.055, 0.05)]
    rings = []
    for (z, w, d) in table:
        ring = []
        for i in range(56):
            a = 2 * math.pi * i / 56
            ca, sa = math.cos(a), math.sin(a)
            # superellipse section, flatter back (-X), fuller chest (+X)
            ex = 2.25
            r = 1.0 / ((abs(ca) ** ex + abs(sa) ** ex) ** (1 / ex))
            dd = d * (1.08 if ca > 0 else 0.9)
            bust = 1.0 + (0.06 * max(0, ca) ** 2 * math.exp(-((z - 1.33) / 0.06) ** 2) * (abs(sa) > 0.25))
            ring.append((dd * r * ca * bust, w * r * sa, z))
        rings.append(ring)
    A.loft(rings, mat="linen", closed=True, cap=True, smooth=180)
    A.sweep([(0.0, 0.0, 0.0)] and [(rings[i][0][0] + 0.002, 0.0, table[i][0]) for i in range(len(table))], r=0.003, mat="linen", smooth=180)
    A.lathe(round_poly([(0, 0.93), (0.15, 0.93), (0.17, 0.95), (0, 0.955)], 0.006, closed=False), mat="walnut_dark", n=48) if False else None
    A.cyl(0.165, 0.025, at=(0, 0, 0.93), mat="walnut_dark", n=48, bevel=0.006) if False else None
    # neck cap
    A.lathe(round_poly([(0, 1.595), (0.058, 1.595), (0.06, 1.61), (0.045, 1.635), (0.02, 1.645), (0.022, 1.665), (0, 1.675)], 0.004, closed=False), mat="walnut_dark", n=40, gax=2)
    A.lathe([(0.0545, 1.585), (0.0575, 1.585), (0.0575, 1.598), (0.0545, 1.598)], mat="brass_polished", n=40, cap=False)
    A.view = (1.0, -0.6, 0.2)
    A.lens = 55


# ======================================================================================
# Persian rug 3 x 2 m
# ======================================================================================


@asset("RugPersian", group="Armory", res=4096, collision="Box", edge=0.002, ao_dist=0.05)
def rug(A):
    Lx, Ly, T = 3.0, 2.0, 0.012

    def top(u, v):
        x = (u - 0.5) * Lx
        y = (v - 0.5) * Ly
        z = T + 0.004 * math.sin(x * 2.1 + 0.3) * math.sin(y * 1.7) + 0.002 * math.sin(x * 5.3 + y * 3.1)
        return (x, y, z)

    A.grid(top, 150, 100, mat="rug", recalc=False, smooth=180)
    # edges (binding) + underside
    path = [(-Lx / 2, -Ly / 2, T * 0.5), (Lx / 2, -Ly / 2, T * 0.5), (Lx / 2, Ly / 2, T * 0.5), (-Lx / 2, Ly / 2, T * 0.5)]
    A.sweep(path, r=0.0075, n=10, mat="rug", closed=True, smooth=180)
    A.mesh([(-Lx / 2, -Ly / 2, 0.001), (-Lx / 2, Ly / 2, 0.001), (Lx / 2, Ly / 2, 0.001), (Lx / 2, -Ly / 2, 0.001)], [(0, 1, 2, 3)], "rug", recalc=False, smooth=0)
    rng = random.Random(9)
    for s in (-1, 1):
        for i in range(110):
            y = -Ly / 2 + 0.02 + (Ly - 0.04) * i / 109
            ln = 0.07 + rng.uniform(-0.008, 0.008)
            curl = rng.uniform(-0.015, 0.015)
            pts = [(s * (Lx / 2 - 0.005), y, 0.006), (s * (Lx / 2 + ln * 0.4), y + curl * 0.3, 0.004), (s * (Lx / 2 + ln * 0.8), y + curl * 0.8, 0.0025), (s * (Lx / 2 + ln), y + curl, 0.0025)]
            A.sweep(catmull(pts, 3), r=0.0028, n=6, mat="linen", smooth=180)
    A.view = (1.0, -0.6, 0.75)
    A.lens = 50


# ======================================================================================
# Walnut wainscot wall panel 4 x 3 m (architecture: tileable MI_ slots)
# ======================================================================================


@asset("WallPanel_Walnut_4m", group="Armory", res=2048, collision="Box", edge=0.004, ao_dist=0.2)
def wall_panel(A):
    A.pieces["Body"].tileable = True
    L, H = 4.0, 3.0
    xb = -0.03
    A.box((0.02, L, H), at=(xb + 0.01, 0, H / 2), mat="walnut", bevel=0.002, gax=2)
    # baseboard
    A.prism(round_poly([(xb, 0), (xb + 0.035, 0), (xb + 0.035, 0.15), (xb + 0.025, 0.17), (xb + 0.02, 0.18), (xb, 0.18)], 0.004), L, mat="walnut", plane="XZ", bevel=0.002, smooth=35, gax=1)
    nb = 5
    bw = L / nb
    for i in range(nb):
        y0 = -L / 2 + i * bw
        raised_panel_x(A, y0 + 0.01, y0 + bw - 0.01, 0.20, 0.92, xb + 0.02, mat="walnut", frame=0.085)
        raised_panel_x(A, y0 + 0.01, y0 + bw - 0.01, 1.06, 2.74, xb + 0.02, mat="walnut", frame=0.095)
    # chair rail with brass inlay
    A.prism(round_poly([(xb, 0.92), (xb + 0.05, 0.93), (xb + 0.06, 0.96), (xb + 0.06, 1.02), (xb + 0.045, 1.05), (xb, 1.06)], 0.006), L, mat="walnut", plane="XZ", bevel=0.002, smooth=35, gax=1)
    A.box((0.006, L, 0.012), at=(xb + 0.062, 0, 0.99), mat="brass", bevel=0.002, gax=1)
    # crown moulding
    A.prism(round_poly([(xb, 2.74), (xb + 0.04, 2.74), (xb + 0.05, 2.78), (xb + 0.09, 2.86), (xb + 0.12, 2.95), (xb + 0.12, 3.0), (xb, 3.0)], 0.008), L, mat="walnut", plane="XZ", bevel=0.002, smooth=35, gax=1)
    A.box((0.006, L, 0.01), at=(xb + 0.122, 0, 2.975), mat="brass", bevel=0.002, gax=1)
    A.view = (1.0, -0.45, 0.1)
    A.lens = 45


# ======================================================================================
# Brass ceiling light (semi-flush, frosted bowl)
# ======================================================================================


@asset("CeilingLight_Brass", group="Armory", res=2048, collision="Convex", edge=0.002, ao_dist=0.1)
def ceiling_light(A):
    A.piece("Glass", "Glass", res=1024, glass=True)
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    top = 0.36
    A.lathe(round_poly([(0, top), (0.12, top), (0.12, top - 0.012), (0.10, top - 0.03), (0.03, top - 0.045), (0, top - 0.045)], 0.004, closed=False), mat="brass", n=64, gax=2)
    A.lathe([(0, top - 0.045), (0.012, top - 0.045), (0.012, top - 0.16), (0, top - 0.16)], mat="brass_polished", n=24)
    A.lathe(round_poly([(0, top - 0.17), (0.03, top - 0.17), (0.045, top - 0.155), (0.045, top - 0.145), (0, top - 0.145)], 0.003, closed=False), mat="brass_polished", n=32)
    # gallery ring + three arms
    zr = top - 0.19
    A.sweep(ring_path(0.205, zr, 96), prof=round_poly(rrect_pts(0.012, 0.03, 0.004), 0.002), mat="brass", closed=True, up=(0, 0, 1))
    for i in range(3):
        a = 2 * math.pi * i / 3
        A.sweep(catmull([(0.03 * math.cos(a), 0.03 * math.sin(a), top - 0.16), (0.12 * math.cos(a), 0.12 * math.sin(a), top - 0.17), (0.205 * math.cos(a), 0.205 * math.sin(a), zr)], 6), r=0.006, mat="brass_polished")
    for i in range(24):
        a = 2 * math.pi * i / 24
        A.sphere(0.006, at=(0.212 * math.cos(a), 0.212 * math.sin(a), zr), mat="brass_polished", seg=10, rings=6)
    # frosted bowl
    prof = []
    for i in range(14):
        t = i / 13
        a = math.radians(90 * t)
        prof.append((0.20 * math.cos(a) * (1 - 0.05 * t), zr - 0.005 - 0.14 * math.sin(a)))
    prof.append((0.0, zr - 0.15))
    A.lathe(list(reversed(prof)), mat="glass_frosted", n=48, piece="Glass", cap=False, smooth=60)
    # bulbs
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.5
        A.sphere(0.03, at=(0.06 * math.cos(a), 0.06 * math.sin(a), zr - 0.03), mat="emit", seg=16, rings=8, piece="Emissive")
    # finial
    A.lathe(round_poly([(0, 0.0), (0.008, 0.005), (0.02, 0.025), (0.016, 0.045), (0.006, 0.05), (0.0, 0.05)], 0.003, closed=False), at=(0, 0, zr - 0.20), mat="brass_polished", n=24, smooth=180)
    A.lathe([(0, 0.0), (0.005, 0.0), (0.005, 0.03), (0, 0.03)], at=(0, 0, zr - 0.17), mat="brass_polished", n=12)
    A.point("CeilingMount", (0, 0, top))
    A.point("Light", (0, 0, zr - 0.04))
    A.preview["Glass"] = {"glass": {"trans": 0.4, "rough": 0.5, "emit": 2.5}}
    A.preview["Emissive"] = {"emit": (1.0, 0.8, 0.55, 25.0)}
    A.view = (1.0, -0.6, -0.15)


# ======================================================================================
# Armory sign: brass letters on a routed walnut board
# ======================================================================================


@asset("ArmorySign", group="Armory", res=2048, collision="Box", edge=0.003, ao_dist=0.08)
def armory_sign(A):
    A.piece("Brass", "Static", res=2048)
    A.cur = "Body"
    W, H, T = 1.90, 0.46, 0.045
    xb = -0.03
    A.box((T, W, H), at=(xb + T / 2, 0, H / 2), mat="walnut", bevel=0.012, segs=3, gax=1)
    path = [(xb + T + 0.0005, W / 2 - 0.04, 0.04), (xb + T + 0.0005, -W / 2 + 0.04, 0.04), (xb + T + 0.0005, -W / 2 + 0.04, H - 0.04), (xb + T + 0.0005, W / 2 - 0.04, H - 0.04)]
    A.sweep(path, prof=round_poly(rrect_pts(0.004, 0.006, 0.0015), 0.001), mat="brass_aged", closed=True)
    for s in (-1, 1):
        A.lathe(round_poly([(0, 0), (0.025, 0), (0.025, 0.004), (0.012, 0.012), (0, 0.014)], 0.002, closed=False), at=(xb + T, s * (W / 2 - 0.085), H / 2), axis="X", mat="brass_polished", n=32)
    A.cur = "Brass"
    A.text("THE ARMORY", font("LibreBaskerville-Regular.ttf"), 0.205, 0.012, at=(xb + T + 0.006, 0, H / 2 - 0.075), rot=(90, 0, 90), mat="brass_unbrushed", spacing=1.18, bevel=0.0012)
    A.point("WallMount", (xb, 0, H / 2))
    A.view = (1.0, -0.3, 0.12)
    A.lens = 70
