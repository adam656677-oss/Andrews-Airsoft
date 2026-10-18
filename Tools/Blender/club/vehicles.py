"""Work vehicles for the Velvet Club exterior and the Nightjar Garage: the cab-over box truck.

The street's passenger cars are the AVERNE luxury cars in luxury_cars.py (Car_Limousine,
Car_GrandTourer, Car_Hypercar, Car_SUV); they replaced the old Car_Sedan / Car_Coupe.
Paint is baked neutral grey with role-mask R so the game can tint it.
"""

import math
from mathutils import Matrix

import propkit as pk
from propkit import round_poly, rrect_pts
from club_registry import asset


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


def lamp(A, poly_yz, x, depth, piece="Emissive", mat="emit", rot=None, at=None):
    p = A.prism(poly_yz, depth, mat=mat, plane="YZ", piece=piece, bevel=0.003, segs=2)
    p.matrix_world = Matrix.Translation(at or (x, 0, 0)) @ pk.rot_matrix(rot)
    return p


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
