"""Street vehicles for the Velvet Club exterior: luxury sedan, 1970s muscle coupe, box truck.

Bodies are lofted from feature-aligned cross-sections (rocker, door bulge, shoulder, belt,
glass, roof), wheel arches are cut with booleans, window faces are split off into dark trim
and offset outward to make the `Glass` piece. Paint is baked neutral grey with role-mask R
so the game can tint it.
"""

import math
import random
import bpy
import bmesh
import numpy as np
from mathutils import Vector as V, Matrix

import propkit as pk
from propkit import round_poly, circle_pts, rrect_pts, catmull
from club_registry import asset, font


def ss(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def interp(table, x):
    """Piecewise-smooth interpolation through (x, y) knots (Catmull-Rom in y)."""
    xs = [p[0] for p in table]
    if x <= xs[0]:
        return table[0][1]
    if x >= xs[-1]:
        return table[-1][1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            y0 = table[max(i - 1, 0)][1]
            y1 = table[i][1]
            y2 = table[i + 1][1]
            y3 = table[min(i + 2, len(xs) - 1)][1]
            t2, t3 = t * t, t * t * t
            v = 0.5 * ((2 * y1) + (-y0 + y2) * t + (2 * y0 - 5 * y1 + 4 * y2 - y3) * t2 + (-y0 + 3 * y1 - 3 * y2 + y3) * t3)
            lo, hi = min(y1, y2), max(y1, y2)
            return min(max(v, lo - 0.03), hi + 0.03)
    return table[-1][1]


def resample(pts, n):
    """Resample a polyline to n points by arc length."""
    P = [V(p) for p in pts]
    d = [0.0]
    for a, b in zip(P[:-1], P[1:]):
        d.append(d[-1] + (b - a).length)
    L = d[-1] if d[-1] > 1e-9 else 1.0
    out = []
    j = 0
    for i in range(n):
        s = L * i / (n - 1)
        while j < len(d) - 2 and d[j + 1] < s:
            j += 1
        seg = d[j + 1] - d[j]
        t = (s - d[j]) / seg if seg > 1e-9 else 0.0
        out.append(P[j].lerp(P[j + 1], t))
    return out


def plan_round(half_len, half_w, r):
    """Plan-view rounded-rectangle factor: 1 along the sides, rounding off over radius r at the ends."""
    def f(x):
        d = abs(x) - (half_len - r)
        if d <= 0:
            return 1.0
        d = min(d, r * 0.999)
        return max(0.25, (half_w - r + math.sqrt(r * r - d * d)) / half_w)
    return f


class CarSpec:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def section(cs, x):
    """Right-half (y >= 0) section keys at station x, returned as list of (y, z) segments."""
    zb = interp(cs.zbot, x)
    deck = interp(cs.deck, x)
    roof = interp(cs.roof, x)
    yb = interp(cs.width, x) * cs.plan(x)
    yr = interp(cs.roofw, x)
    zbelt = min(interp(cs.belt, x), deck + 0.02)
    ztop = max(deck, roof)
    c = ss(0.02, 0.16, roof - deck)
    h = ztop - zbelt
    keys = [(0.0, zb), (yb * 0.80, zb), (yb * 0.965, zb + 0.07), (yb, zb + cs.bulge_z), (yb * 0.995, zbelt - cs.shoulder), (yb * 0.955, zbelt)]
    hood = [(yb * 0.93, deck - 0.004), (yb * 0.80, deck + 0.010), (yb * 0.62, deck + 0.016), (yb * 0.32, deck + 0.022), (0.0, deck + 0.025)]
    yg = yb * 0.94
    cab = [(yg + (yr - yg) * 0.22, zbelt + h * 0.25), (yg + (yr - yg) * 0.62, zbelt + h * 0.66), (yr, ztop - 0.035), (yr * 0.55, ztop - 0.004), (0.0, ztop)]
    top = [(a[0] + (b[0] - a[0]) * c, a[1] + (b[1] - a[1]) * c) for a, b in zip(hood, cab)]
    return keys + top, (zb, zbelt, ztop, yb, yr, c, deck)


def build_body_mesh(cs, nst=180):
    counts = [5, 4, 6, 7, 3, 4, 7, 7, 3, 4]  # points per key segment
    xs = [cs.x0 + (cs.x1 - cs.x0) * (0.5 - 0.5 * math.cos(math.pi * i / (nst - 1))) for i in range(nst)]
    rings = []
    info = []
    for x in xs:
        keys, inf = section(cs, x)
        half = []
        for k in range(len(keys) - 1):
            seg = resample([keys[k], keys[k + 1]], counts[k] + 1)
            half.extend(seg[:-1])
        half.append(V(keys[-1]))
        # full loop: right side (y>0) bottom->top, then left side top->bottom (excluding shared centre points)
        loop = [(x, p.x, p.y) for p in half] + [(x, -p.x, p.y) for p in reversed(half[1:-1])]
        rings.append(loop)
        info.append(inf)
    return rings, xs, info


def side_y(cs, x, z):
    keys, _ = section(cs, x)
    best = keys[0][0]
    for a, b in zip(keys[:-1], keys[1:]):
        if (a[1] - z) * (b[1] - z) <= 0 and abs(b[1] - a[1]) > 1e-6:
            t = (z - a[1]) / (b[1] - a[1])
            y = a[0] + (b[0] - a[0]) * t
            best = max(best, y)
    return best


def wheel(A, at, r_tire, width, rim_r, style="multi", side=1, rim_mat="aluminium"):
    """Tyre + rim + brake. at = wheel centre; side = +1 (left, +Y) / -1."""
    x, y, z = at
    sw = width / 2
    # tyre profile (r, y_local) revolved around the axle (local Z -> world Y)
    prof = [(rim_r - 0.01, -sw * 0.78), (rim_r + 0.015, -sw * 0.92), (r_tire - 0.05, -sw), (r_tire - 0.012, -sw * 0.86), (r_tire, -sw * 0.6), (r_tire, -sw * 0.25), (r_tire - 0.008, -sw * 0.22), (r_tire - 0.008, -sw * 0.12),
            (r_tire, -sw * 0.08), (r_tire, sw * 0.08), (r_tire - 0.008, sw * 0.12), (r_tire - 0.008, sw * 0.22), (r_tire, sw * 0.25), (r_tire, sw * 0.6), (r_tire - 0.012, sw * 0.86), (r_tire - 0.05, sw), (rim_r + 0.015, sw * 0.92), (rim_r - 0.01, sw * 0.78)]
    t = A.lathe([(r, zz) for r, zz in prof], mat="tire", n=72, cap=False, smooth=50)
    t.matrix_world = Matrix.Translation(at) @ Matrix.Rotation(-math.pi / 2, 4, "X")
    face = side * sw * 0.82
    # rim barrel + dish
    barrel = A.lathe([(rim_r - 0.005, -sw * 0.8), (rim_r - 0.012, -sw * 0.75), (rim_r - 0.012, sw * 0.7), (rim_r - 0.002, sw * 0.8)], mat=rim_mat, n=64, cap=False, smooth=50)
    barrel.matrix_world = Matrix.Translation(at) @ Matrix.Rotation(-math.pi / 2, 4, "X")
    parts = []
    lip = A.lathe(round_poly([(rim_r * 0.86, 0.0), (rim_r + 0.008, 0.0), (rim_r + 0.008, 0.012), (rim_r * 0.86, 0.016)], 0.003, closed=False), mat=rim_mat, n=64, cap=False, smooth=40)
    parts.append(lip)
    hub = A.lathe(round_poly([(0, 0.03), (0.06, 0.03), (0.075, 0.02), (0.085, 0.0), (0.0, 0.0)], 0.004, closed=False), mat=rim_mat, n=48)
    parts.append(hub)
    parts.append(A.cyl(0.035, 0.034, at=(0, 0, 0.0), mat="chrome", n=32, bevel=0.003))
    if style == "multi":
        ns = 10
        for i in range(ns):
            a = 2 * math.pi * i / ns
            sp = A.sweep([(0.07 * math.cos(a), 0.07 * math.sin(a), 0.022), (rim_r * 0.55 * math.cos(a + 0.05), rim_r * 0.55 * math.sin(a + 0.05), 0.016), (rim_r * 0.88 * math.cos(a + 0.09), rim_r * 0.88 * math.sin(a + 0.09), 0.006)],
                         prof=round_poly([(-0.013, -0.009), (0.013, -0.009), (0.009, 0.009), (-0.009, 0.009)], 0.003), mat=rim_mat, smooth=40)
            parts.append(sp)
    else:  # classic 5-slot mag / rally wheel
        parts.append(A.lathe([(0.085, 0.0), (rim_r * 0.86, -0.012), (rim_r * 0.86, -0.004), (0.085, 0.008)], mat="steel_dark", n=64, cap=False, smooth=40))
        for i in range(5):
            a = 2 * math.pi * i / 5
            sp = A.box((rim_r * 0.5, 0.06, 0.02), at=(rim_r * 0.5 * math.cos(a), rim_r * 0.5 * math.sin(a), 0.006), rot=(0, 0, math.degrees(a)), mat="chrome", bevel=0.008, segs=3)
            parts.append(sp)
        for i in range(5):
            a = 2 * math.pi * (i + 0.5) / 5
            parts.append(A.cyl(0.008, 0.02, at=(0.06 * math.cos(a), 0.06 * math.sin(a), 0.02), mat="chrome", n=6, bevel=0.002))
    # lug nuts
    for i in range(5):
        a = 2 * math.pi * i / 5 + 0.3
        parts.append(A.cyl(0.0085, 0.02, at=(0.055 * math.cos(a), 0.055 * math.sin(a), 0.026), mat="chrome", n=6, bevel=0.0015))
    M = Matrix.Translation((x, y + face, z)) @ Matrix.Rotation(-side * math.pi / 2, 4, "X")
    for p in parts:
        p.matrix_world = M @ p.matrix_world
    # brake disc + caliper
    d = A.cyl(rim_r * 0.78, 0.028, at=(0, 0, -0.014), mat="steel", n=48, bevel=0.002)
    cal = A.box((0.09, 0.14, 0.05), at=(0, rim_r * 0.68, 0), mat="paint_red", bevel=0.012, segs=3)
    M2 = Matrix.Translation((x, y + side * sw * 0.35, z)) @ Matrix.Rotation(-side * math.pi / 2, 4, "X")
    d.matrix_world = M2 @ d.matrix_world
    cal.matrix_world = Matrix.Translation((x, y + side * sw * 0.42, z)) @ Matrix.Rotation(math.radians(-40), 4, "Y") @ Matrix.Rotation(-side * math.pi / 2, 4, "X") @ cal.matrix_world


def make_car(A, cs, paint="paint_car", rim_style="multi", rim_mat="aluminium"):
    A.piece("Glass", "Glass", res=1024, glass=True)
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    rings, xs, info = build_body_mesh(cs)
    k = len(rings[0])
    verts = [p for ring in rings for p in ring]
    faces = []
    for i in range(len(rings) - 1):
        for j in range(k):
            j2 = (j + 1) % k
            faces.append((i * k + j, i * k + j2, (i + 1) * k + j2, (i + 1) * k + j))
    faces.append(tuple(range(k - 1, -1, -1)))
    faces.append(tuple((len(rings) - 1) * k + j for j in range(k)))
    body = A.mesh(verts, faces, paint, smooth=55)
    # wheel arch cutters (booleans on the sides only)
    cutters = []
    for wx in (cs.wf, cs.wr):
        for s in (-1, 1):
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=64, radius1=cs.arch_r, radius2=cs.arch_r, depth=0.9)
            me = bpy.data.meshes.new("cut")
            bm.to_mesh(me)
            bm.free()
            co = bpy.data.objects.new("cut", me)
            pk.link(co)
            co.matrix_world = Matrix.Translation((wx, s * (cs.track / 2 + 0.36), cs.r_tire + 0.012)) @ Matrix.Rotation(math.pi / 2, 4, "X")
            co.hide_render = True
            cutters.append(co)
            m = body.modifiers.new("arch", "BOOLEAN")
            m.object = co
            m.operation = "DIFFERENCE"
            m.solver = "EXACT"
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(body.evaluated_get(dg))
    body.modifiers.clear()
    old = body.data
    body.data = me2
    bpy.data.meshes.remove(old)
    pk.delete_objects(cutters)
    m_ = body.modifiers.new("bev", "BEVEL")
    m_.width = 0.006
    m_.segments = 2
    m_.limit_method = "ANGLE"
    m_.angle_limit = math.radians(50)
    m_.harden_normals = False
    # split window faces into dark trim + build glass from them
    me = body.data
    me.materials.append(pk.get_mat("lacquer_black"))
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    win = []
    for f in bm.faces:
        c = f.calc_center_median()
        n = f.normal
        if cs.is_window(c, n):
            f.material_index = 1
            win.append(f)
    # glass: duplicate window faces, offset outward
    gverts, gfaces, vmap = [], [], {}
    for f in win:
        idx = []
        for v in f.verts:
            if v.index not in vmap:
                vmap[v.index] = len(gverts)
                gverts.append(tuple(v.co + v.normal * 0.004))
            idx.append(vmap[v.index])
        gfaces.append(idx)
    bm.to_mesh(me)
    bm.free()
    g = A.mesh(gverts, gfaces, "glass_car", piece="Glass", smooth=180, recalc=False)
    dec = g.modifiers.new("dec", "DECIMATE")
    dec.ratio = min(1.0, 4500.0 / max(1, 2 * len(gfaces)))
    # wheel well liners
    for wx in (cs.wf, cs.wr):
        for s in (-1, 1):
            pts = []
            for i in range(25):
                a = math.radians(-15 + 210 * i / 24)
                pts.append((wx + (cs.arch_r - 0.015) * math.cos(a), (cs.r_tire + 0.012) + (cs.arch_r - 0.015) * math.sin(a)))
            verts2, faces2 = [], []
            ywall = interp(cs.width, wx) * cs.plan(wx) - 0.035
            for yy in (s * (cs.track / 2 - 0.30), s * ywall):
                for (px, pz) in pts:
                    verts2.append((px, yy, pz))
            n = len(pts)
            for i in range(n - 1):
                faces2.append((i, i + 1, n + i + 1, n + i))
            A.mesh(verts2, faces2, "plastic_case", smooth=60, recalc=False)
    # wheels
    for wx in (cs.wf, cs.wr):
        for s in (-1, 1):
            wheel(A, (wx, s * cs.track / 2, cs.r_tire), cs.r_tire, cs.tire_w, cs.rim_r, rim_style, side=s, rim_mat=rim_mat)
    # underbody pan
    A.box((cs.wf - cs.wr + 0.9, cs.track - 0.35, 0.03), at=((cs.wf + cs.wr) / 2, 0, interp(cs.zbot, 0.0) + 0.02), mat="plastic_case", bevel=0.01)
    # simple interior seen through the glass
    zs = interp(cs.zbot, 0) + 0.25
    for sx in (cs.seat_front, cs.seat_rear):
        for s in ((-1, 1) if sx == cs.seat_front else (0,)):
            wseat = 0.52 if s else cs.track - 0.3
            A.box((0.52, wseat, 0.16), at=(sx, s * 0.38, zs + 0.08), mat="leather_black", bevel=0.04, segs=3)
            A.box((0.14, wseat, 0.62), at=(sx - 0.26, s * 0.38, zs + 0.44), rot=(0, -12, 0), mat="leather_black", bevel=0.04, segs=3)
    A.box((0.35, cs.track - 0.1, 0.25), at=(cs.dash_x, 0, interp(cs.belt, cs.dash_x) - 0.08), mat="leather_black", bevel=0.04, segs=3)
    sw_ = A.sweep([(0.17 * math.cos(2 * math.pi * i / 32), 0.17 * math.sin(2 * math.pi * i / 32), 0) for i in range(32)], r=0.016, mat="leather_black", closed=True)
    sw_.matrix_world = Matrix.Translation((cs.dash_x - 0.3, 0.38, interp(cs.belt, cs.dash_x) - 0.05)) @ Matrix.Rotation(math.radians(-62), 4, "Y")
    return body


def door_lines(A, cs, xs_list, z0, z1, mat="lacquer_black"):
    for x in xs_list:
        for s in (-1, 1):
            pts = []
            for i in range(12):
                z = z0 + (z1 - z0) * i / 11
                y = side_y(cs, x, z) + 0.0008
                pts.append((x, s * y, z))
            A.sweep(pts, r=0.0022, n=6, mat=mat, smooth=60)


def lamp(A, poly_yz, x, depth, piece="Emissive", mat="emit", rot=None, at=None):
    p = A.prism(poly_yz, depth, mat=mat, plane="YZ", piece=piece, bevel=0.003, segs=2)
    p.matrix_world = Matrix.Translation(at or (x, 0, 0)) @ pk.rot_matrix(rot)
    return p


# ======================================================================================
# Modern luxury sedan
# ======================================================================================


@asset("Car_Sedan", res=4096, collision="Convex", edge=0.004, ao_dist=0.5, mask=True)
def car_sedan(A):
    L = 5.10
    cs = CarSpec(
        x0=-2.55, x1=2.55, wf=1.55, wr=-1.50, track=1.63, r_tire=0.355, tire_w=0.255, rim_r=0.245, arch_r=0.40,
        zbot=[(-2.55, 0.34), (-2.3, 0.22), (-1.9, 0.19), (1.95, 0.19), (2.35, 0.22), (2.55, 0.32)],
        deck=[(-2.55, 0.80), (-2.45, 0.96), (-2.25, 1.03), (-1.85, 1.05), (0.95, 0.99), (1.4, 0.93), (2.1, 0.85), (2.45, 0.76), (2.55, 0.62)],
        roof=[(-2.3, 0.6), (-1.95, 1.04), (-1.55, 1.30), (-1.1, 1.43), (-0.5, 1.465), (0.15, 1.44), (0.55, 1.32), (0.95, 1.07), (1.15, 0.85), (1.5, 0.5)],
        width=[(-2.55, 0.88), (-2.2, 0.94), (-1.5, 0.955), (0.0, 0.95), (1.5, 0.95), (2.2, 0.93), (2.55, 0.86)],
        roofw=[(-2.0, 0.66), (-0.5, 0.70), (0.6, 0.68), (1.0, 0.70)],
        belt=[(-2.55, 1.0), (-1.9, 1.04), (0.9, 1.0), (2.55, 0.9)],
        bulge_z=0.30, shoulder=0.13,
        seat_front=-0.05, seat_rear=-1.05, dash_x=0.62,
    )
    cs.plan = plan_round(2.55, 0.95, 0.45)

    def is_window(c, n):
        x, y, z = c
        belt = interp(cs.belt, x)
        roof = interp(cs.roof, x)
        if z < belt + 0.035 or z > roof - 0.04:
            return False
        if abs(n.z) > 0.93:
            return False
        if -1.88 < x < 0.92 and abs(n.y) > 0.45:
            if -0.12 < x < -0.04:  # B pillar
                return False
            if x > 0.80 or x < -1.80:
                return False
            return True
        if 0.70 < x < 1.12 and n.x > 0.25 and abs(y) < interp(cs.roofw, x) * 0.88 + (x - 0.7) * 0.4:
            return True
        if -2.05 < x < -1.30 and n.x < -0.25 and abs(y) < interp(cs.roofw, x) * 0.86:
            return True
        return False

    cs.is_window = is_window
    make_car(A, cs, "paint_car", "multi", "aluminium")
    door_lines(A, cs, [0.88, -0.08, -1.12], 0.32, 0.98)
    # door handles (chrome, flush)
    for x in (0.25, -0.78):
        for s in (-1, 1):
            y = side_y(cs, x, 0.93) + 0.004
            A.box((0.16, 0.012, 0.022), at=(x, s * y, 0.93), mat="chrome", bevel=0.005, segs=3)
    # mirrors
    for s in (-1, 1):
        y = side_y(cs, 0.72, 1.02)
        A.box((0.10, 0.06, 0.04), at=(0.72, s * (y + 0.03), 1.02), mat="paint_car", bevel=0.01)
        A.box((0.12, 0.16, 0.10), at=(0.70, s * (y + 0.12), 1.07), rot=(0, 0, s * 8), mat="paint_car", bevel=0.03, segs=3)
        A.box((0.004, 0.14, 0.08), at=(0.641, s * (y + 0.12), 1.07), rot=(0, 0, s * 8), mat="mirror", bevel=0.002)
    # chrome window surround line
    pts = []
    for i in range(40):
        x = 0.85 - 2.65 * i / 39
        pts.append(x)
    for s in (-1, 1):
        path = [(x, s * (side_y(cs, x, interp(cs.belt, x) + 0.01) + 0.002), interp(cs.belt, x) + 0.012) for x in pts]
        A.sweep(path, r=0.006, n=8, mat="chrome", smooth=60)
    # brushed sill strip between the wheel arches
    for s in (-1, 1):
        xs_ = [cs.wf - 0.47 - (cs.wf - cs.wr - 0.94) * i / 39 for i in range(40)]
        path = [(x, s * (side_y(cs, x, 0.30) + 0.003), 0.30) for x in xs_]
        A.sweep(path, prof=round_poly(rrect_pts(0.004, 0.035, 0.0015), 0.001), mat="chrome", smooth=60, up=(0, 0, 1))
    # front: grille + LED headlights + lower intake
    xf = 2.55
    A.prism(round_poly(rrect_pts(0.60, 0.26, 0.06, 6), 0.004), 0.06, mat="chrome", plane="YZ", at=(xf - 0.035, 0, 0.62), bevel=0.006)
    A.prism(round_poly(rrect_pts(0.54, 0.21, 0.05, 6), 0.004), 0.06, mat="grille", plane="YZ", at=(xf - 0.02, 0, 0.62), bevel=0.003)
    for i in range(9):
        A.box((0.02, 0.008, 0.20), at=(xf + 0.005, -0.24 + i * 0.06, 0.62), mat="chrome", bevel=0.002)
    A.prism(round_poly(rrect_pts(1.10, 0.12, 0.04, 6), 0.004), 0.06, mat="grille", plane="YZ", at=(xf - 0.12, 0, 0.36), bevel=0.003)
    for s in (-1, 1):
        hl = round_poly([(0.0, 0.0), (0.38, 0.03), (0.40, 0.09), (0.05, 0.08)], 0.02)
        hl = [(s * (0.33 + p[0]), p[1]) for p in hl]
        if s < 0:
            hl = list(reversed(hl))
        lamp(A, hl, 0, 0.05, at=(xf - 0.16, 0, 0.70), rot=(0, -28, 0))
        lamp(A, round_poly(rrect_pts(0.34, 0.014, 0.006, 3), 0.002), 0, 0.03, at=(xf - 0.11, s * 0.52, 0.665), rot=(0, -15, 0))
    # rear: full-width light bar + plate + exhausts
    xr = -2.55
    lamp(A, round_poly(rrect_pts(1.55, 0.05, 0.02, 4), 0.003), 0, 0.04, at=(xr + 0.02, 0, 0.93), rot=(0, 20, 0))
    for s in (-1, 1):
        tl = round_poly([(0.45, 0.0), (0.80, 0.02), (0.80, 0.10), (0.48, 0.09)], 0.02)
        tl = [(s * p[0], p[1]) for p in tl]
        if s < 0:
            tl = list(reversed(tl))
        lamp(A, tl, 0, 0.05, at=(xr + 0.06, 0, 0.86), rot=(0, 22, 0))
    plate = A.box((0.006, 0.52, 0.11), at=(xr + 0.025, 0, 0.62), mat="plate", bevel=0.003)
    A.vattr(plate, "luv", lambda co: (0.5 - co.y / 0.52, co.z / 0.11 + 0.5, 1.0))
    for s in (-1, 1):
        A.prism(round_poly(rrect_pts(0.20, 0.07, 0.03, 4), 0.003), 0.08, mat="chrome", plane="YZ", at=(xr + 0.03, s * 0.55, 0.30), bevel=0.003)
    fplate = A.box((0.006, 0.52, 0.11), at=(xf - 0.03, 0, 0.45), mat="plate", bevel=0.003)
    A.vattr(fplate, "luv", lambda co: (0.5 + co.y / 0.52, co.z / 0.11 + 0.5, 1.0))
    A.preview["Body"] = {"tint": (0.035, 0.045, 0.07), "coat": True}
    A.preview["Emissive"] = {"emit": (1.0, 0.95, 0.9, 8.0)}
    A.preview["Glass"] = {"glass": {"trans": 0.9, "rough": 0.02, "thin": True}}
    A.view = (1.0, -0.75, 0.32)
    A.lens = 50


# ======================================================================================
# 1970s muscle coupe (black, chrome bumpers, long hood, fastback)
# ======================================================================================


@asset("Car_Coupe", res=4096, collision="Convex", edge=0.004, ao_dist=0.5, mask=True)
def car_coupe(A):
    cs = CarSpec(
        x0=-2.62, x1=2.62, wf=1.48, wr=-1.49, track=1.56, r_tire=0.345, tire_w=0.24, rim_r=0.19, arch_r=0.40,
        zbot=[(-2.62, 0.36), (-2.4, 0.26), (-2.0, 0.21), (1.9, 0.21), (2.4, 0.27), (2.62, 0.38)],
        deck=[(-2.62, 0.88), (-2.55, 0.93), (-2.3, 0.95), (-1.6, 0.96), (0.55, 0.92), (1.5, 0.90), (2.45, 0.87), (2.62, 0.80)],
        roof=[(-2.25, 0.55), (-2.05, 0.95), (-1.5, 1.16), (-0.9, 1.30), (-0.45, 1.34), (0.05, 1.33), (0.38, 1.22), (0.72, 0.97), (0.9, 0.80), (1.2, 0.5)],
        width=[(-2.62, 0.90), (-2.3, 0.955), (-1.5, 0.975), (-0.6, 0.94), (0.5, 0.955), (1.6, 0.965), (2.3, 0.95), (2.62, 0.90)],
        roofw=[(-2.0, 0.60), (-0.6, 0.66), (0.4, 0.65), (0.8, 0.66)],
        belt=[(-2.62, 0.93), (-1.5, 0.96), (0.6, 0.92), (2.62, 0.87)],
        bulge_z=0.26, shoulder=0.10,
        seat_front=-0.25, seat_rear=-1.15, dash_x=0.40,
    )
    cs.plan = plan_round(2.62, 0.97, 0.30)

    def is_window(c, n):
        x, y, z = c
        belt = interp(cs.belt, x)
        roof = interp(cs.roof, x)
        if z < belt + 0.03 or z > roof - 0.035:
            return False
        if abs(n.z) > 0.94:
            return False
        if -1.75 < x < 0.62 and abs(n.y) > 0.45:
            if x > 0.52 or x < -1.6:
                return False
            if -0.62 < x < -0.55:
                return False
            return True
        if 0.50 < x < 0.92 and n.x > 0.25 and abs(y) < interp(cs.roofw, x) * 0.88 + (x - 0.5) * 0.4:
            return True
        if -2.15 < x < -1.20 and n.x < -0.2 and abs(y) < interp(cs.roofw, x) * 0.84:
            return True
        return False

    cs.is_window = is_window
    make_car(A, cs, "paint_car", "rally", "chrome")
    door_lines(A, cs, [0.70, -0.75], 0.30, 0.90)
    for s in (-1, 1):
        y = side_y(cs, -0.62, 0.86) + 0.004
        A.box((0.14, 0.014, 0.03), at=(-0.62, s * y, 0.86), mat="chrome", bevel=0.006, segs=3)
        y = side_y(cs, 0.52, 0.95)
        A.lathe(round_poly([(0, 0), (0.05, 0), (0.06, 0.02), (0.05, 0.05), (0, 0.06)], 0.01, closed=False), at=(0.52, s * (y + 0.02), 0.95), axis="Y", rot=(0, 0, 0 if s > 0 else 180), mat="chrome", n=24, smooth=60)
    # chrome drip rail + belt molding
    for s in (-1, 1):
        xs_ = [0.85 - 2.6 * i / 49 for i in range(50)]
        path = [(x, s * (side_y(cs, x, interp(cs.belt, x) + 0.01) + 0.002), interp(cs.belt, x) + 0.012) for x in xs_]
        A.sweep(path, r=0.006, n=8, mat="chrome", smooth=60)
        path2 = [(x, s * (side_y(cs, x, 0.62) + 0.002), 0.62) for x in [2.5 - 5.0 * i / 59 for i in range(60)]]
        A.sweep(path2, r=0.004, n=8, mat="chrome", smooth=60)
    # chrome bumpers
    for xb_, sgn in ((2.64, 1), (-2.64, -1)):
        prof = round_poly([(-0.04, -0.06), (0.03, -0.05), (0.045, 0.0), (0.03, 0.05), (-0.04, 0.06)], 0.012)
        path = []
        for i in range(31):
            t = i / 30
            yy = -0.98 + 1.96 * t
            xx = xb_ - sgn * 0.10 * (abs(yy) / 0.98) ** 4
            path.append((xx, yy, 0.47 if sgn > 0 else 0.52))
        bp = A.sweep(path, prof=[(p[1], -sgn * p[0]) for p in prof] if False else prof, mat="chrome", up=(0, 0, 1), smooth=50)
    # full-width black grille with quad round headlights
    xf = 2.62
    A.prism(round_poly(rrect_pts(1.62, 0.26, 0.03, 4), 0.004), 0.06, mat="grille", plane="YZ", at=(xf - 0.03, 0, 0.67), bevel=0.003)
    A.prism(round_poly(rrect_pts(1.66, 0.30, 0.04, 4), 0.004), 0.03, mat="chrome", plane="YZ", at=(xf - 0.05, 0, 0.67), bevel=0.004)
    for y in (-0.62, -0.42, 0.42, 0.62):
        A.lathe([(0.0, 0.0), (0.085, 0.0), (0.085, 0.02), (0.07, 0.03), (0, 0.032)], at=(xf - 0.02, y, 0.67), axis="X", mat="chrome", n=40)
        A.lathe([(0.0, 0.0), (0.07, 0.0), (0.066, 0.012), (0.04, 0.02), (0, 0.022)], at=(xf - 0.005, y, 0.67), axis="X", mat="emit", n=32, piece="Emissive", smooth=180)
    for i in range(12):
        A.box((0.015, 0.006, 0.24), at=(xf + 0.002, -0.3 + i * 0.055, 0.67), mat="powder_black", bevel=0.001)
    # rear: wide tail light panel + plate
    xr = -2.62
    A.prism(round_poly(rrect_pts(1.55, 0.18, 0.03, 4), 0.004), 0.04, mat="chrome", plane="YZ", at=(xr + 0.015, 0, 0.76), bevel=0.004)
    lamp(A, round_poly(rrect_pts(1.48, 0.13, 0.025, 4), 0.003), 0, 0.03, at=(xr + 0.01, 0, 0.76))
    plate = A.box((0.006, 0.31, 0.155), at=(xr - 0.035, 0, 0.53), mat="plate", bevel=0.003)
    A.vattr(plate, "luv", lambda co: (0.5 - co.y / 0.31, co.z / 0.155 + 0.5, 1.0))
    for s in (-1, 1):
        A.cyl(0.035, 0.12, at=(xr + 0.05, s * 0.55, 0.30), axis="X", rot=(0, 0, 180), mat="chrome", n=24, bevel=0.003)
    # hood scoop / power bulge
    A.prism(round_poly([(0.0, 0.0), (0.9, 0.0), (0.9, 0.03), (0.15, 0.06), (0.0, 0.06)], 0.02), 0.62, mat="paint_car", plane="XZ", at=(1.2, 0, interp(cs.deck, 1.6) + 0.005), bevel=0.01, segs=3)
    A.preview["Body"] = {"tint": (0.012, 0.012, 0.013), "coat": True}
    A.preview["Emissive"] = {"emit": (1.0, 0.92, 0.8, 8.0)}
    A.preview["Glass"] = {"glass": {"trans": 0.9, "rough": 0.02, "thin": True}}
    A.view = (1.0, -0.75, 0.3)
    A.lens = 50


# ======================================================================================
# Box truck (cab-over delivery truck)
# ======================================================================================


@asset("BoxTruck", res=2048, collision="Convex", edge=0.005, ao_dist=0.5, mask=True)
def box_truck(A):
    A.piece("Glass", "Glass", res=1024, glass=True)
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    L, W = 7.4, 2.35
    xf = L / 2
    r_t = 0.43
    wf, wr = xf - 0.85, xf - 0.85 - 3.8
    # chassis rails + bumper
    for s in (-1, 1):
        A.box((L - 0.5, 0.08, 0.24), at=(-0.1, s * 0.45, 0.72), mat="powder_black", bevel=0.006)
    A.box((0.14, W - 0.1, 0.22), at=(xf - 0.05, 0, 0.55), mat="powder_black", bevel=0.02, segs=3)
    # cab: rounded box with slanted windscreen
    cab_x0 = xf - 1.95
    side = round_poly([(cab_x0, 0.62), (xf - 0.08, 0.62), (xf - 0.02, 1.2), (xf - 0.10, 1.55), (xf - 0.32, 2.62), (cab_x0, 2.72)], 0.08)
    A.prism(side, W - 0.05, mat="paint_truck", plane="XZ", bevel=0.05, segs=4)
    # windscreen + side windows (glass) and dark frames
    ws = [(xf - 0.11, 1.62), (xf - 0.31, 2.52), (xf - 0.31, 2.52)]
    g = A.mesh([(xf - 0.095, -1.02, 1.62), (xf - 0.095, 1.02, 1.62), (xf - 0.295, 1.0, 2.52), (xf - 0.295, -1.0, 2.52)], [(0, 1, 2, 3)], "glass_car", piece="Glass", smooth=0, recalc=False)
    A.mesh([(xf - 0.09, -1.06, 1.58), (xf - 0.09, 1.06, 1.58), (xf - 0.29, 1.04, 2.56), (xf - 0.29, -1.04, 2.56)], [(0, 1, 2, 3)], "lacquer_black", smooth=0, recalc=False)
    for s in (-1, 1):
        y = s * ((W - 0.05) / 2 + 0.004)
        quad = [(xf - 1.05, y, 1.62), (xf - 0.18, y, 1.62), (xf - 0.36, y, 2.45), (xf - 1.05, y, 2.45)]
        A.mesh(quad if s > 0 else list(reversed(quad)), [(0, 1, 2, 3)], "glass_car", piece="Glass", smooth=0, recalc=False)
        A.box((0.9, 0.006, 0.86), at=(xf - 0.62, s * ((W - 0.05) / 2 + 0.001), 2.03), mat="lacquer_black", bevel=0.002)
        A.box((0.12, 0.05, 0.03), at=(xf - 1.1, s * ((W - 0.05) / 2 + 0.03), 1.45), mat="plastic_black", bevel=0.008)
        # mirrors on arms
        A.sweep([(xf - 0.25, s * (W / 2 - 0.02), 2.0), (xf - 0.1, s * (W / 2 + 0.2), 2.05)], r=0.015, mat="powder_black")
        A.box((0.08, 0.20, 0.36), at=(xf - 0.12, s * (W / 2 + 0.26), 1.95), mat="plastic_black", bevel=0.02, segs=3)
        # steps
        A.box((0.35, 0.18, 0.04), at=(xf - 0.75, s * (W / 2 - 0.07), 0.48), mat="aluminium", bevel=0.006)
        door_x = xf - 1.12
        A.box((0.004, 0.004, 1.9), at=(door_x, s * ((W - 0.05) / 2 + 0.002), 1.6), mat="lacquer_black", bevel=0.0)
    # grille + headlights + amber markers
    A.prism(round_poly(rrect_pts(1.3, 0.38, 0.04, 4), 0.004), 0.04, mat="grille", plane="YZ", at=(xf - 0.03, 0, 0.98), bevel=0.003)
    for s in (-1, 1):
        lamp(A, round_poly(rrect_pts(0.30, 0.18, 0.04, 4), 0.004), 0, 0.04, at=(xf - 0.03, s * 0.88, 0.95))
        A.prism(round_poly(rrect_pts(0.34, 0.22, 0.05, 4), 0.004), 0.03, mat="chrome", plane="YZ", at=(xf - 0.05, s * 0.88, 0.95), bevel=0.003)
        A.box((0.03, 0.12, 0.05), at=(xf - 0.12, s * 1.0, 2.66), mat="plastic_amber", bevel=0.01)
    # cargo box
    bx0, bx1 = cab_x0 - 0.08, -L / 2
    A.box((bx0 - bx1, W, 2.45), at=((bx0 + bx1) / 2, 0, 0.88 + 1.225), mat="paint_box_white", bevel=0.02, segs=3)
    for i in range(14):
        x = bx1 + 0.05 + i * (bx0 - bx1 - 0.1) / 13
        for s in (-1, 1):
            A.box((0.05, 0.03, 2.40), at=(x, s * (W / 2 + 0.012), 2.1), mat="aluminium", bevel=0.006)
    for z in (0.90, 3.31):
        for s in (-1, 1):
            A.box((bx0 - bx1, 0.05, 0.08), at=((bx0 + bx1) / 2, s * (W / 2 + 0.02), z), mat="aluminium", bevel=0.008, gax=0)
    # roll-up rear door
    A.box((0.04, W - 0.2, 2.25), at=(bx1 - 0.015, 0, 2.08), mat="paint_box_white", bevel=0.006)
    for k in range(22):
        A.box((0.012, W - 0.22, 0.008), at=(bx1 - 0.036, 0, 0.98 + k * 0.1), mat="paint_box_white", bevel=0.002)
    A.box((0.04, 0.4, 0.04), at=(bx1 - 0.05, 0, 1.05), mat="aluminium", bevel=0.008)
    # rear lights + bumper/step
    A.box((0.25, W - 0.15, 0.1), at=(bx1 + 0.05, 0, 0.62), mat="powder_black", bevel=0.01)
    for s in (-1, 1):
        lamp(A, round_poly(rrect_pts(0.12, 0.22, 0.03, 4), 0.003), 0, 0.03, at=(bx1 - 0.04, s * 1.0, 1.15), rot=(0, 0, 180))
    plate = A.box((0.006, 0.52, 0.11), at=(bx1 - 0.08, 0, 0.75), mat="plate", bevel=0.003)
    A.vattr(plate, "luv", lambda co: (0.5 - co.y / 0.52, co.z / 0.11 + 0.5, 1.0))
    # fuel tank, side skirts
    A.cyl(0.25, 0.9, at=(-0.2, -0.85, 0.65), axis="X", mat="aluminium", n=32, bevel=0.01)
    # wheels: single front, dual rear
    for s in (-1, 1):
        wheel(A, (wf, s * 0.98, r_t), r_t, 0.24, 0.22, "rally", side=s, rim_mat="steel")
        wheel(A, (wr, s * 0.84, r_t), r_t, 0.24, 0.22, "rally", side=s, rim_mat="steel")
        wheel(A, (wr, s * 1.08, r_t), r_t, 0.24, 0.22, "rally", side=s, rim_mat="steel")
        A.box((0.85, 0.30, 0.04), at=(wr, s * 1.0, 0.92), mat="plastic_case", bevel=0.01)
        A.box((0.02, 0.30, 0.45), at=(wr - 0.5, s * 1.0, 0.65), mat="rubber", bevel=0.004)
    A.preview["Body"] = {"tint": (0.55, 0.08, 0.05), "coat": False}
    A.preview["Emissive"] = {"emit": (1.0, 0.95, 0.85, 8.0)}
    A.preview["Glass"] = {"glass": {"trans": 0.9, "rough": 0.03, "thin": True}}
    A.view = (1.0, -0.7, 0.3)
    A.lens = 45
