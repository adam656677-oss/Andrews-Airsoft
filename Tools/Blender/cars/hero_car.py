"""Andrew's car: Car_Hero, display name "'69 Fastback".

A 1969 American fastback (SportsRoof body) built on the luxury-car surface model (club/luxury_cars.py):
published proportions (wheelbase 108 in = 2.743 m, length 187.4 in = 4.76 m, width 71.3 in = 1.81 m,
height 50.4 in = 1.28 m), long hood with a centre scoop, hood pins and a matte black hood panel, quad round
headlights (inner pair in the grille ends, outer pair in the fender bezels), sweeping fastback roofline with
small quarter glass and wide sail panels, simulated rear-quarter scoops, ducktail deck, triple-lens tail lamps,
chrome blade bumpers, 5-spoke chrome wheels, black vinyl high-back buckets.

No trademarks anywhere: the grille centre, stripes, gas cap, wheel caps, steering-wheel hub and dash are plain
(no oval, no running-horse / tri-bar emblem, no model or maker lettering).

Pieces: Body (4K, paint mask R primary; stripes / hood panel are satin black, never tinted), Wheels (2K),
Interior (2K), Glass, Emissive (lamps, lit on the night maps). Build + renders: build_hero_car.py.
"""

import math
import numpy as np
from mathutils import Vector as V, Matrix

import propkit as pk
from propkit import round_poly, rrect_pts
from propkit_mats import paint
from club_registry import asset
from luxury_cars import (Car, interp, lerp, reg, lux_paint, lux_metal, lux_leather, lux_fabric, lux_plate, plate_image,
                         build_lower, build_greenhouse, dlo_loop, frame_sweep, fan_patch, bar_across, grid_mesh,
                         surf_front, surf_rear, surf_side, surf_top, chrome_strip_side, number_plate, mirror_poly, slit)

DISPLAY_NAME = "'69 Fastback"

# Panel gaps (see luxury_cars.gap_field): doors, hood, deck lid
HERO_GAPS = [
    ("XZ", [(0.21, 0.27), (0.21, 0.60), (0.18, 0.83)], 0.45),
    ("XZ", [(-0.97, 0.27), (-0.98, 0.60), (-1.0, 0.86)], 0.45),
    ("XZ", [(0.21, 0.27), (-0.97, 0.27)], 0.6, 0.0016),
    ("XY", [(0.50, 0.0), (0.50, 0.71), (2.27, 0.71), (2.27, 0.0)], 0.5),
    ("XY", [(-1.90, 0.0), (-1.90, 0.69), (-2.30, 0.69), (-2.30, 0.0)], 0.5),
]


def hero_spec():
    return Car(
        x0=-2.38, x1=2.38, wf=1.45, wr=-1.293, track=1.49, r_tire=0.335, tire_w=0.225, tire_wr=0.235, rim_r=0.19, arch_r=0.385,
        plan_rf=0.10, plan_rr=0.10,
        width=[(-2.38, 0.86), (-2.2, 0.895), (-1.6, 0.905), (-1.29, 0.905), (-0.8, 0.89), (-0.2, 0.876), (0.5, 0.873),
               (1.45, 0.882), (2.1, 0.878), (2.38, 0.86)],
        zbot=[(-2.38, 0.34), (-2.2, 0.22), (-1.9, 0.16), (1.95, 0.16), (2.2, 0.19), (2.38, 0.235)],
        zsill=[(-2.38, 0.40), (-2.0, 0.27), (1.95, 0.27), (2.38, 0.30)],
        zsh=[(-2.38, 0.76), (-1.6, 0.80), (-1.05, 0.765), (-0.6, 0.705), (0.5, 0.69), (1.5, 0.705), (2.38, 0.72)],
        belt_t=[(-2.38, 0.93), (-2.2, 0.955), (-1.86, 0.945), (-1.3, 0.905), (-0.8, 0.872), (0.0, 0.852), (0.8, 0.848),
                (1.6, 0.846), (2.2, 0.838), (2.38, 0.80)],
        deck_t=[(-2.38, 0.93), (-2.31, 0.988), (-2.2, 0.99), (-1.86, 0.968), (-1.0, 0.93), (-0.3, 0.9), (0.42, 0.878),
                (0.7, 0.878), (1.3, 0.868), (1.9, 0.856), (2.25, 0.84), (2.38, 0.80)],
        tuck_t=[(-2.38, 0.03), (-1.5, 0.085), (-0.6, 0.07), (0.6, 0.05), (1.6, 0.04), (2.38, 0.03)],
        x_ws=0.42, x_bl=-1.86,
        roof_t=[(-1.86, 0.968), (-1.4, 1.09), (-1.05, 1.19), (-0.78, 1.255), (-0.55, 1.28), (-0.3, 1.276), (-0.12, 1.245),
                (0.05, 1.16), (0.25, 1.0), (0.42, 0.878)],
        lean_t=[(-1.9, 0.17), (0.4, 0.14)], n_exp=3.6,
        s_g0=0.035, s_g1=0.36, s_rail=0.41, s_w0=0.44,
        side_breaks=[0.42, (0.26, -0.08), -0.86, -0.89, (-1.38, -0.98), -1.86],
        roof_breaks=[0.42, -0.14, -0.86, -0.89, -1.02, -1.86],
        col_counts=[10, 16, 2, 10, 16],
        seat_x=[-0.55, -1.30],
    )


# --------------------------------------------------------------------------------------
# Wheels: 5 broad chrome spokes, dark windows, chrome trim ring, plain centre cap
# --------------------------------------------------------------------------------------


def five_spoke_wheel(A, at, side, r_t, wdt, rim_r, piece="Wheels"):
    x, y, z = at
    attrs = {"wcx": x, "wcz": z, "wcy": y, "wrt": r_t, "wrd": rim_r * 0.86, "wny": float(side)}
    sw = wdt / 2
    M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(-side * math.pi / 2, 4, "X")   # local Z -> world side
    parts = []
    # tyre: tall period sidewall, rounded shoulders, plain sidewall (no lettering), simple tread grooves
    sh = 0.03
    prof = [(rim_r + 0.010, -sw * 0.86), (rim_r + 0.025, -sw * 0.95), (rim_r + 0.05, -sw * 1.0), ((rim_r + r_t) / 2, -sw * 1.03),
            (r_t - sh * 1.5, -sw * 1.0), (r_t - sh * 0.5, -sw * 0.94), (r_t - 0.004, -sw * 0.84), (r_t, -sw * 0.72)]
    crown = []
    for g in (-0.45, -0.15, 0.15, 0.45):
        crown += [(r_t, sw * (g - 0.06)), (r_t - 0.007, sw * (g - 0.04)), (r_t - 0.007, sw * (g + 0.04)), (r_t, sw * (g + 0.06))]
    full = prof + crown + [(p[0], -p[1]) for p in reversed(prof)]
    parts.append(A.lathe(full, mat="lx_tyre", n=56, cap=False, smooth=40, piece=piece, attrs=attrs))
    face = sw * 0.9
    # rim barrel (dark) + polished trim ring
    parts.append(A.lathe([(rim_r - 0.004, -sw * 0.84), (rim_r - 0.012, -sw * 0.74), (rim_r - 0.016, sw * 0.6), (rim_r - 0.006, face - 0.012)],
                         mat="lx_rim_dark", n=48, cap=False, smooth=50, piece=piece, attrs=attrs))
    parts.append(A.lathe([(rim_r - 0.03, face - 0.022), (rim_r - 0.012, face - 0.004), (rim_r + 0.004, face - 0.001), (rim_r + 0.012, face - 0.010),
                          (rim_r + 0.012, face - 0.02)], mat="lx_chrome", n=64, cap=False, smooth=40, piece=piece, attrs=attrs))
    # recessed dark dish (the "windows" between the spokes)
    hub_r = rim_r * 0.30
    parts.append(A.lathe([(hub_r * 0.95, face - 0.035), (rim_r * 0.72, face - 0.05), (rim_r - 0.028, face - 0.026)],
                         mat="lx_rim_gun", n=48, cap=False, smooth=50, piece=piece, attrs=attrs))
    # five broad flat spokes: wide at the hub, slightly narrower at the ring, gently domed
    for i in range(5):
        a = 2 * math.pi * i / 5 + math.pi / 2
        pts = []
        for j in range(7):
            t_ = j / 6
            rr = lerp(hub_r * 0.9, rim_r - 0.026, t_)
            zz = face - 0.012 - 0.022 * (1 - t_) ** 1.4
            pts.append((rr * math.cos(a), rr * math.sin(a), zz))
        wroot, wtip = 0.078, 0.056
        scales = [lerp(1.0, wtip / wroot, (j / 6) ** 0.9) for j in range(7)]
        prof_s = round_poly([(-wroot / 2, -0.008), (wroot / 2, -0.008), (wroot * 0.44, 0.007), (-wroot * 0.44, 0.007)], 0.004, iters=1)
        parts.append(A.sweep(pts, prof=prof_s, mat="lx_chrome", scales=scales, smooth=45, piece=piece, attrs=attrs, up=(0, 0, 1)))
    # hub, five lug nuts, small plain domed cap
    parts.append(A.lathe(round_poly([(0.0, face - 0.010), (hub_r, face - 0.012), (hub_r * 1.02, face - 0.04), (0.0, face - 0.04)], 0.004, closed=False),
                         mat="lx_chrome", n=48, smooth=40, piece=piece, attrs=attrs))
    for i in range(5):
        aa = 2 * math.pi * i / 5 + math.pi / 2 + math.pi / 5
        parts.append(A.cyl(0.0095, 0.018, at=(hub_r * 0.66 * math.cos(aa), hub_r * 0.66 * math.sin(aa), face - 0.006), mat="lx_chrome", n=6,
                           bevel=0.0015, piece=piece, attrs=attrs))
    parts.append(A.sphere(1.0, at=(0, 0, face - 0.004), mat="lx_chrome", seg=28, rings=10, scale=(0.032, 0.032, 0.014), piece=piece, attrs=attrs))
    for p in parts:
        p.matrix_world = M @ p.matrix_world
    # drum brake backing plate behind the spokes
    M2 = Matrix.Translation((x, y + side * (face - 0.10), z)) @ Matrix.Rotation(-side * math.pi / 2, 4, "X")
    d = A.lathe([(0.0, -0.02), (rim_r * 0.8, -0.02), (rim_r * 0.84, 0.02), (0.0, 0.02)], mat="lx_rim_dark", n=48, cap=False, smooth=40, piece=piece, attrs=attrs)
    d.matrix_world = M2 @ d.matrix_world


# --------------------------------------------------------------------------------------
# Interior: black vinyl high-back buckets, console + shifter, twin-cowl dash, 3-spoke wheel
# --------------------------------------------------------------------------------------


def bucket(A, x, y, z, P, mat, insert):
    w, depth, back_h = 0.52, 0.52, 0.56
    A.box((depth, w, 0.11), at=(x, y, z + 0.055), mat=mat, bevel=0.035, segs=3, piece=P)
    A.box((depth * 0.8, w * 0.66, 0.03), at=(x + 0.01, y, z + 0.12), mat=insert, bevel=0.012, segs=3, piece=P)
    bx, bz = x - depth / 2 + 0.06, z + 0.12
    R = pk.rot_matrix((0, -18, 0))

    def place(o, local):
        o.matrix_world = Matrix.Translation((bx, y, bz)) @ R @ Matrix.Translation(local) @ o.matrix_world
    o = A.box((0.11, w, back_h), mat=mat, bevel=0.045, segs=3, piece=P)
    place(o, (-0.02, 0, back_h / 2))
    o = A.box((0.025, w * 0.62, back_h * 0.62), mat=insert, bevel=0.01, segs=3, piece=P)
    place(o, (0.04, 0, back_h * 0.42))
    # integrated headrest: the high back narrows at the top
    o = A.box((0.11, w * 0.6, 0.15), mat=mat, bevel=0.05, segs=3, piece=P)
    place(o, (-0.02, 0, back_h + 0.06))


def period_steering_wheel(A, at, r, P):
    parts = []
    path = [(r * math.cos(2 * math.pi * i / 48), r * math.sin(2 * math.pi * i / 48), 0) for i in range(48)]
    parts.append(A.sweep(path, r=0.014, n=12, mat="lx_dash_hero", closed=True, piece=P))
    for a in (0, 120, 240):
        aa = math.radians(a - 90)
        parts.append(A.box((r * 0.9, 0.03, 0.006), at=(r * 0.45 * math.cos(aa), r * 0.45 * math.sin(aa), -0.01), rot=(0, 0, a - 90),
                           mat="lx_satin", bevel=0.002, piece=P))
    parts.append(A.cyl(0.055, 0.035, at=(0, 0, -0.03), mat="lx_black", n=28, bevel=0.008, piece=P))       # plain hub pad
    parts.append(A.cyl(0.028, 0.32, at=(0, 0, -0.35), mat="lx_satin_black", n=14, piece=P))
    M = Matrix.Translation(at) @ Matrix.Rotation(math.radians(-90 + 28), 4, "Y") @ Matrix.Rotation(math.radians(-90), 4, "Z")
    for p in parts:
        p.matrix_world = M @ p.matrix_world


def period_cabin(A, cs, vinyl, insert, dash):
    P = "Interior"
    x_front, x_back = cs.x_ws - 0.05, cs.x_bl + 0.05
    zf = interp(cs.zbot, 0.0) + 0.12
    A.box((x_front - x_back + 0.1, 2 * (cs.yb(0.0) - 0.02), 0.03), at=((x_front + x_back) / 2, 0, zf), mat="lx_carpet", bevel=0.005, piece=P)
    belt = cs.belt
    for s in (-1, 1):
        xs_ = np.linspace(x_back + 0.02, x_front - 0.02, 28)
        top = [(x, s * (cs.yb(x) - 0.035), belt(x) - 0.006) for x in xs_]

        def zbot_(x):
            z_ = zf
            for wx in (cs.wf, cs.wr):
                if abs(x - wx) < cs.arch_r + 0.06:
                    z_ = max(z_, cs.r_tire + cs.arch_r + 0.04)
            return min(z_, belt(x) - 0.12)
        bot = [(x, s * (cs.yb(x) - 0.06), zbot_(x)) for x in xs_]
        grid_mesh(A, [bot, top], vinyl, flip=(s < 0), piece=P, smooth=60)
        cap_in = [(x, s * (cs.yb(x) - 0.07), belt(x) - 0.012) for x in xs_]
        cap_out = [(x, s * (cs.yb(x) + 0.004), belt(x) - 0.012) for x in xs_]
        grid_mesh(A, [cap_in, cap_out] if s > 0 else [cap_out, cap_in], dash, piece=P, smooth=60)
        A.box((0.36, 0.07, 0.05), at=(cs.seat_x[0] - 0.02, s * (cs.yb(cs.seat_x[0]) - 0.09), belt(cs.seat_x[0]) - 0.26), mat=vinyl, bevel=0.02,
              segs=3, piece=P)
    # dash: padded top, twin cowls over the driver, round gauges, plain centre panel
    xd = cs.x_ws
    dz = belt(xd)
    yb = cs.yb(xd - 0.3) - 0.03
    A.box((0.46, 2 * yb, 0.15), at=(xd - 0.14, 0, dz - 0.04), mat=dash, bevel=0.05, segs=3, piece=P)
    A.box((0.26, 2 * yb - 0.04, 0.28), at=(xd - 0.2, 0, dz - 0.27), mat=dash, bevel=0.05, segs=3, piece=P)
    for yy in (0.27, 0.47):
        A.cyl(0.085, 0.12, at=(xd - 0.36, yy, dz + 0.0), axis="X", rot=(0, 0, 180), mat=dash, n=28, bevel=0.01, piece=P)
        A.cyl(0.066, 0.02, at=(xd - 0.415, yy, dz - 0.005), axis="X", rot=(0, 0, 180), mat="lx_black", n=28, bevel=0.002, piece=P)
        A.cyl(0.07, 0.012, at=(xd - 0.418, yy, dz - 0.005), axis="X", rot=(0, 0, 180), mat="lx_chrome", n=28, bevel=0.002, piece=P)
        A.box((0.004, 0.05, 0.006), at=(xd - 0.43, yy - 0.01, dz + 0.005), rot=(35, 0, 0), mat="lx_emit_warm", piece=P, bevel=0.001)
    for yy in (-0.05, 0.07):
        A.cyl(0.032, 0.012, at=(xd - 0.40, yy, dz - 0.09), axis="X", rot=(0, 0, 180), mat="lx_chrome", n=20, bevel=0.002, piece=P)
    A.box((0.012, 0.36, 0.06), at=(xd - 0.40, -0.35, dz - 0.10), mat="lx_satin", bevel=0.004, piece=P)   # plain glovebox trim
    # console + T-handle shifter
    xs0, xs1 = cs.seat_x[0] - 0.3, xd - 0.32
    A.box((xs1 - xs0, 0.22, 0.2), at=((xs0 + xs1) / 2, 0, zf + 0.12), mat=vinyl, bevel=0.035, segs=3, piece=P)
    A.box((xs1 - xs0 - 0.08, 0.15, 0.012), at=((xs0 + xs1) / 2, 0, zf + 0.225), mat="lx_satin_black", bevel=0.004, piece=P)
    gx = (xs0 + xs1) / 2 + 0.08
    A.cyl(0.008, 0.2, at=(gx, 0, zf + 0.225), mat="lx_chrome", n=10, piece=P)
    A.box((0.03, 0.09, 0.03), at=(gx, 0, zf + 0.43), mat="lx_black", bevel=0.01, segs=2, piece=P)
    period_steering_wheel(A, (xd - 0.58, 0.37, dz - 0.03), 0.19, P)
    zs = zf + 0.04
    for s in (-1, 1):
        bucket(A, cs.seat_x[0], s * 0.36, zs, P, vinyl, insert)
    # fold-down rear seat (low cushions) + parcel area under the fastback
    for s in (-1, 1):
        A.box((0.42, 0.5, 0.1), at=(cs.seat_x[1], s * 0.34, zs + 0.08), mat=vinyl, bevel=0.035, segs=3, piece=P)
        A.box((0.1, 0.5, 0.4), at=(cs.seat_x[1] - 0.26, s * 0.34, zs + 0.3), rot=(0, -24, 0), mat=insert, bevel=0.035, segs=3, piece=P)
    A.box((0.4, 2 * (cs.yb(x_back + 0.2) - 0.05), 0.03), at=(x_back + 0.2, 0, belt(x_back + 0.2) - 0.02), mat="lx_carpet", bevel=0.005, piece=P)


# --------------------------------------------------------------------------------------
# Exterior details
# --------------------------------------------------------------------------------------


def round_lamp(A, surf, u, v, r, front=True, point=None):
    """Round sealed-beam lamp: chrome bezel, reflector, Body lens (shows when parked), Emissive face."""
    p, n = surf(u, v)
    n = V(n)
    ax = 1.0 if front else -1.0
    rot = (0, 0, 0) if front else (0, 0, 180)

    def at(d):
        return tuple(p + n * d)
    # cylinders grow from their base along the lamp axis (outward): bezel -10..+12 mm, lens dome 4..16 mm,
    # emissive face just proud of the lens (16.5..18.5 mm)
    A.cyl(r + 0.016, 0.022, at=at(-0.010), axis="X", rot=rot, mat="lx_chrome", n=40, bevel=0.005, segs=2)
    A.cyl(r, 0.012, at=at(0.004), axis="X", rot=rot, mat="lx_lens", n=40, bevel=0.004, segs=2)
    A.cyl(r * 0.88, 0.002, at=at(0.0165), axis="X", rot=rot, mat="lx_emit_white", n=36, bevel=0.0005, piece="Emissive")
    if point:
        A.point(point, at(0.02))


def hood_pin(A, T, x, y):
    p, n = T(x, y)
    A.cyl(0.013, 0.008, at=tuple(p - V(n) * 0.002), mat="lx_chrome", n=16, bevel=0.003)
    A.cyl(0.004, 0.016, at=tuple(p + V(n) * 0.005), mat="lx_chrome", n=8, bevel=0.001)
    # lanyard loop to a clip a little further back
    q, m = T(x - 0.07, y)
    path = [tuple(p + V(n) * 0.012), tuple((p + q) / 2 + V(n) * 0.022), tuple(q + V(m) * 0.006)]
    A.sweep(path, r=0.0018, n=6, mat="lx_satin", smooth=50)


def quarter_scoop(A, cs, side, P1):
    """Simulated scoop on the rear quarter just behind the door: body-colour fairing with a dark rear mouth."""
    S = surf_side(cs, side)
    out = round_poly([(-1.0, 0.655), (-1.05, 0.705), (-1.29, 0.75), (-1.33, 0.70), (-1.30, 0.64)], 0.015)
    fan_patch(A, out if side > 0 else list(reversed(out)), S, 0.028, P1, rings=4, smooth=40)
    mouth = round_poly([(-1.27, 0.655), (-1.29, 0.725), (-1.322, 0.715), (-1.312, 0.652)], 0.006)
    fan_patch(A, mouth if side > 0 else list(reversed(mouth)), S, 0.031, "lx_satin_black", rings=2)


def stripe_side(A, cs, side):
    """Body-side stripe along the crease from behind the front wheel to the quarter scoop (plain, no lettering)."""
    S = surf_side(cs, side)
    upper = [(1.02, 0.712), (0.5, 0.705), (-0.2, 0.708), (-0.85, 0.727), (-1.0, 0.70)]
    lower = [(-0.97, 0.672), (-0.85, 0.687), (-0.2, 0.668), (0.5, 0.665), (1.06, 0.674)]
    out = upper + lower
    fan_patch(A, out if side > 0 else list(reversed(out)), S, 0.003, "lx_matte_black", rings=2, smooth=30)
    # pinstripe below the band
    lo2 = [(1.06, 0.662), (0.5, 0.654), (-0.2, 0.657), (-0.9, 0.676), (-0.9, 0.669), (-0.2, 0.650), (0.5, 0.647), (1.08, 0.655)]
    fan_patch(A, lo2 if side > 0 else list(reversed(lo2)), S, 0.003, "lx_matte_black", rings=1, smooth=30)


def windscreen_trim(A, cs, x_a, x_b, s0, off=0.005, n=24, mat="lx_chrome"):
    """Closed chrome reveal around a greenhouse glass span x_a..x_b (s >= s0, both sides)."""
    path = []
    for i in range(n + 1):                                  # right side, along s0
        path.append((lerp(x_a, x_b, i / n), s0, 1))
    for i in range(1, n + 1):                               # across the far edge, right half up to the centre
        path.append((x_b, lerp(s0, 1.0, i / n), 1))
    for i in range(1, n + 1):
        path.append((x_b, lerp(1.0, s0, i / n), -1))
    for i in range(1, n + 1):
        path.append((lerp(x_b, x_a, i / n), s0, -1))
    for i in range(1, n):
        path.append((x_a, lerp(s0, 1.0, i / n), -1))
    path.append((x_a, 1.0, 1))
    for i in range(1, n):
        path.append((x_a, lerp(1.0, s0, i / n), 1))
    pts = [cs.gh(x, s, sd) + cs.gh_normal(x, s, sd) * off for (x, s, sd) in path]
    frame_sweep(A, pts, 0.006, 0.016, mat, closed=True, smooth=60)


def plain_mirror(A, cs, x, z, side, P1):
    """Bullet-style door mirror on a short stalk."""
    zb_ = cs.belt(x)
    y0 = cs.yb(x) + 0.004
    s = side
    A.sweep([(x, s * (y0 - 0.01), zb_ + 0.005), (x - 0.01, s * (y0 + 0.05), zb_ + 0.07)], r=0.011, n=10, mat=P1, smooth=50)
    A.sphere(1.0, at=(x - 0.02, s * (y0 + 0.08), zb_ + 0.1), mat=P1, seg=24, rings=12, scale=(0.09, 0.055, 0.045))
    A.box((0.004, 0.09, 0.07), at=(x - 0.095, s * (y0 + 0.08), zb_ + 0.1), mat="lx_mirror", bevel=0.002)


@asset("Car_Hero", group="Cars", res=4096, collision="Convex", edge=0.003, ao_dist=0.45, mask=True)
def car_hero(A):
    cs = hero_spec()
    A.piece("Wheels", "Static", res=2048)
    A.piece("Interior", "Static", res=2048)
    A.piece("Glass", "Glass", res=256, glass=True)
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    P1 = reg("lx_paint_hero", lux_paint, gaps=HERO_GAPS, mask=1.0, rough=0.07)
    reg("lx_vinyl_hero", lux_leather, col=(0.012, 0.012, 0.013), rough=0.32)
    reg("lx_vinyl_weave", lux_leather, col=(0.014, 0.014, 0.015), rough=0.4, quilt=0.35, k=60.0)
    reg("lx_dash_hero", lux_leather, col=(0.01, 0.01, 0.011), rough=0.45)
    reg("lx_headliner_hero", lux_fabric, col=(0.018, 0.018, 0.019), rough=0.95)
    reg("lx_carpet", lux_fabric, col=(0.012, 0.012, 0.013), rough=0.95)
    reg("lx_plate_hero", lux_plate, image=plate_image("PLATE_HERO", "NJR 429"))
    reg("lx_matte_black", paint, col=(0.008, 0.008, 0.009), rough=0.62, peel=0.0, grime=0.03)   # hood panel, stripes

    def mats(c, n):
        if n.z < -0.5 and c.z < interp(cs.zbot, c.x) + 0.04:
            return "lx_under"
        return P1

    cut = [("arch", (cs.wf, cs.r_tire + 0.015, cs.arch_r, cs.track / 2 - 0.2)), ("arch", (cs.wr, cs.r_tire + 0.015, cs.arch_r, cs.track / 2 - 0.2))]
    build_lower(A, cs, mats, cut, nst=120)

    def tagmat(rk, k, s):
        if rk == "side":
            return "glass" if k in (1, 3) else ("lx_black" if k == 2 else P1)
        if rk in ("belt", "frame", "rail"):
            return P1
        if k in (0, 4):
            return "glass" if s >= cs.s_w0 else P1
        return P1

    build_greenhouse(A, cs, tagmat, headliner="lx_headliner_hero")
    # chrome reveals: side glass, windscreen, backlight
    for side in (1, -1):
        loop = dlo_loop(cs, (0.26, -0.08), (-1.38, -0.98), cs.s_g0, cs.s_g1, side, off=0.004)
        frame_sweep(A, loop, 0.004, 0.012, "lx_chrome", closed=True, smooth=60)
    windscreen_trim(A, cs, 0.42, -0.14, cs.s_w0)
    windscreen_trim(A, cs, -1.02, -1.86, cs.s_w0)
    # ---- sides ------------------------------------------------------------------------------
    for side in (1, -1):
        stripe_side(A, cs, side)
        quarter_scoop(A, cs, side, P1)
        S = surf_side(cs, side)
        h = round_poly(rrect_pts(0.13, 0.026, 0.008, 3), 0.003)
        h = [(-0.84 + p[0], 0.795 + p[1]) for p in h]
        fan_patch(A, h if side > 0 else list(reversed(h)), S, 0.007, "lx_chrome", rings=2)
        for (mx, mz, mm) in ((2.05, 0.60, "lx_emit_amber"), (-2.18, 0.64, "lx_emit_red")):
            m = round_poly(rrect_pts(0.09, 0.03, 0.01, 3), 0.003)
            m = [(mx + p[0], mz + p[1]) for p in m]
            fan_patch(A, m if side > 0 else list(reversed(m)), S, 0.004, "lx_redlens" if mz > 0.62 else "lx_smoke", rings=2)
            fan_patch(A, m if side > 0 else list(reversed(m)), S, 0.006, mm, rings=1, piece="Emissive", smooth=180)
        chrome_strip_side(A, cs, 1.02, -0.98, 0.285, side, w=0.026, t=0.005, mat="lx_chrome")     # rocker moulding
    plain_mirror(A, cs, 0.14, 0.0, 1, P1)
    plain_mirror(A, cs, 0.14, 0.0, -1, P1)
    pa, na = surf_side(cs, -1)(1.30, 0.80)
    A.cyl(0.0035, 0.62, at=tuple(pa + V(na) * 0.012 - V((0, 0, 0.01))), mat="lx_chrome", n=8, bevel=0.0)        # antenna
    # ---- hood: matte black centre panel, scoop, pins, wipers ----------------------------------
    T = surf_top(cs)
    hp = round_poly([(0.56, 0.36), (2.16, 0.40), (2.16, -0.40), (0.56, -0.36)], 0.04)
    fan_patch(A, hp, T, 0.003, "lx_matte_black", rings=3, smooth=30)
    sc = round_poly([(0.95, 0.17), (1.62, 0.23), (1.64, -0.23), (0.95, -0.17)], 0.05)
    fan_patch(A, sc, T, 0.055, "lx_matte_black", rings=4, smooth=40)
    pm, nm = T(1.66, 0.0)
    A.box((0.03, 0.40, 0.04), at=tuple(pm + V(nm) * 0.026), mat="lx_black", bevel=0.008, segs=2)          # scoop mouth
    for yy in (0.56, -0.56):
        hood_pin(A, T, 2.13, yy)
    for yy in (0.28, -0.32):
        pw, nw = T(0.47, yy)
        A.box((0.02, 0.42, 0.012), at=tuple(pw + V(nw) * 0.01), rot=(0, 0, -12), mat="lx_satin_black", bevel=0.003)
    # ---- front: recessed grille with the inner lamps at its ends, outer lamps in the fenders, blade bumper
    F = surf_front(cs)
    gr = round_poly([(0.565, 0.50), (0.565, 0.71), (-0.565, 0.71), (-0.565, 0.50)], 0.035)
    fan_patch(A, gr, F, 0.002, "lx_satin_black", rings=3)
    gr2 = round_poly([(0.33, 0.52), (0.33, 0.69), (-0.33, 0.69), (-0.33, 0.52)], 0.025)
    fan_patch(A, gr2, F, 0.004, "lx_mesh", rings=3)                     # plain centre: no emblem
    path = []
    for (u, v) in gr:
        p, n = F(u, v)
        path.append(p + n * 0.006)
    frame_sweep(A, path, 0.008, 0.01, "lx_chrome", closed=True, smooth=50)
    for s in (1, -1):
        round_lamp(A, F, s * 0.455, 0.605, 0.086, True)
        round_lamp(A, F, s * 0.685, 0.605, 0.086, True, point="Headlight" + ("L" if s > 0 else "R"))
        ts = round_poly(rrect_pts(0.14, 0.035, 0.012, 3), 0.003)
        ts = [(s * 0.56 + p[0], 0.335 + p[1]) for p in ts]
        fan_patch(A, ts, F, 0.004, "lx_smoke", rings=2)
        fan_patch(A, ts, F, 0.006, "lx_emit_amber", rings=1, piece="Emissive", smooth=180)
    bar_across(A, F, -0.84, 0.84, 0.425, 0.07, 0.03, "lx_chrome", off=0.035, n=36)
    number_plate(A, cs, "lx_plate_hero", 0.318, True, w=0.305, h=0.152)
    # ---- rear: black tail panel, triple-lens lamps, plain gas cap, blade bumper, twin tips ----
    R = surf_rear(cs)
    tp = round_poly([(0.79, 0.585), (0.79, 0.81), (-0.79, 0.81), (-0.79, 0.585)], 0.02)
    fan_patch(A, list(reversed(tp)), R, 0.004, "lx_satin_black", rings=2)
    for s in (1, -1):
        for k, yy in enumerate((0.36, 0.51, 0.66)):
            bz = round_poly(rrect_pts(0.125, 0.18, 0.012, 3), 0.003)
            bz = [(s * yy + p[0], 0.70 + p[1]) for p in bz]
            fan_patch(A, list(reversed(bz)), R, 0.008, "lx_chrome", rings=2)
            ln = round_poly(rrect_pts(0.105, 0.16, 0.01, 3), 0.003)
            ln = [(s * yy + p[0], 0.70 + p[1]) for p in ln]
            fan_patch(A, list(reversed(ln)), R, 0.012, "lx_redlens", rings=2)
            em = [(s * yy + p[0], 0.70 + p[1]) for p in round_poly(rrect_pts(0.09, 0.14, 0.01, 3), 0.003)]
            fan_patch(A, list(reversed(em)), R, 0.014, "lx_emit_red", rings=1, piece="Emissive", smooth=180)
        A.point("Taillight" + ("L" if s > 0 else "R"), tuple(R(s * 0.51, 0.70)[0]))
    pg, ng = R(0.0, 0.70)
    A.cyl(0.07, 0.02, at=tuple(pg + V(ng) * 0.01), axis="X", rot=(0, 0, 180), mat="lx_chrome", n=40, bevel=0.006, segs=2)  # plain cap
    bar_across(A, R, -0.84, 0.84, 0.50, 0.07, 0.03, "lx_chrome", off=0.035, n=36)
    number_plate(A, cs, "lx_plate_hero", 0.385, False, w=0.305, h=0.152)
    for s in (1, -1):
        A.cyl(0.032, 0.16, at=(cs.x0 + 0.01, s * 0.52, 0.27), axis="X", mat="lx_chrome", n=24, bevel=0.003)
        A.cyl(0.025, 0.162, at=(cs.x0 + 0.008, s * 0.52, 0.27), axis="X", mat="lx_black", n=20, bevel=0.002)
    # plain stripe across the ducktail
    dk = round_poly([(-2.08, 0.66), (-2.26, 0.66), (-2.26, -0.66), (-2.08, -0.66)], 0.02)
    fan_patch(A, dk, T, 0.003, "lx_matte_black", rings=2, smooth=30)
    # ---- wheels + interior ---------------------------------------------------------------------
    for wx, tw in ((cs.wf, cs.tire_w), (cs.wr, cs.tire_wr)):
        for s in (1, -1):
            five_spoke_wheel(A, (wx, s * cs.track / 2, cs.r_tire), s, cs.r_tire, tw, cs.rim_r)
    period_cabin(A, cs, "lx_vinyl_hero", "lx_vinyl_weave", "lx_dash_hero")
    A.cur = "Body"
    A.preview["Body"] = {"tint": (0.045, 0.048, 0.052), "coat": True}
    A.view = (1.0, -0.75, 0.2)
    A.lens = 55
