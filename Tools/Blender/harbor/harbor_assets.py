"""Saltmarsh Terminal kit: container-port pieces and props (Blender, propkit).

Every asset is registered with @asset and built by build_harbor.py. Authoring space follows
Tools/Blender/CONVENTIONS.md: metres, +X = front, +Z = up, Blender +Y = Unreal -Y, origin =
floor centre of the footprint.

Extra per-asset data written to PropsHarbor.json:
    Layout        hints for Tools/Unreal/check_layouts.py (multi-level checker):
                  Core [[x0,y0],[x1,y1]] cm (solid footprint smaller than the bounds), Los / Cover / Solid booleans.
    TintVariants  named paint colours for the role mask (names must exist in layouts.TINTS).
Everything is original: the shipping line (ORSAVIK), terminal names and numbers are invented; no real
brands, logos or registered container owner codes.
"""

import math
import os

import numpy as np
from mathutils import Matrix, Vector as V

import propkit as pk
import propkit_mats as pm
from propkit import catmull, circle_pts, round_poly

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "..", "club", "fonts")
ASSETS = {}

# Lineup sheet (rows back to front)
LINEUP = [
    ["Harbor_FloodMast", "Harbor_ReachStacker", "Harbor_Container40", "Harbor_CladdingPanel_4m", "Harbor_RollerDoor"],
    ["Harbor_Gatehouse", "Harbor_PalletRack", "Harbor_Forklift", "Harbor_ChainFence_4m"],
    ["Harbor_MooringBollard", "Harbor_Fender"],
]

CONTAINER_TINTS = {"Red": [0.42, 0.04, 0.03], "Blue": [0.04, 0.13, 0.32], "Green": [0.07, 0.2, 0.09],
                   "Rust": [0.36, 0.13, 0.05], "Sand": [0.5, 0.4, 0.26], "Grey": [0.3, 0.31, 0.32],
                   "Teal": [0.02, 0.18, 0.2], "Orange": [0.7, 0.22, 0.03], "White": [0.8, 0.8, 0.78]}
CLADDING_TINTS = {"Teal": [0.02, 0.18, 0.2], "Grey": [0.3, 0.31, 0.32], "Gunmetal": [0.07, 0.075, 0.08],
                  "Rust": [0.36, 0.13, 0.05]}


def asset(aid, **kw):
    def deco(fn):
        ASSETS[aid] = {"fn": fn, "kw": dict(group="Harbor", **kw)}
        return fn
    return deco


def font(name="BigShoulders-Bold.ttf"):
    p = os.path.abspath(os.path.join(FONT_DIR, name))
    return p if os.path.exists(p) else None


# ======================================================================================
# Recipes (registered into propkit_mats.MATS so propkit.get_mat can build them)
# ======================================================================================
def _reg():
    M = pm.MATS
    # tintable corrugated steel (role mask R = 1): the game paints it per placement
    M["h_box_paint"] = (pm.paint, dict(col=(0.75, 0.75, 0.75), rough=0.42, mask=1.0, peel=0.7, grime=0.65, rust=0.45,
                                       streak=0.7, chip=0.5, chip_col=(0.16, 0.07, 0.03)))
    M["h_frame"] = (pm.paint, dict(col=(0.09, 0.085, 0.08), rough=0.5, peel=0.8, grime=0.6, rust=0.7, chip=0.8,
                                   chip_col=(0.2, 0.08, 0.03), streak=0.5))
    M["h_stencil"] = (pm.paint, dict(col=(0.72, 0.72, 0.70), rough=0.45, peel=0.9, grime=0.5, chip=0.6))
    M["h_floor_ply"] = (pm.wood, dict(dark=(0.05, 0.03, 0.015), light=(0.14, 0.08, 0.04), rough=0.8, ring=12.0, pore=0.5,
                                      lacquer=False, worn=0.7))
    M["h_crane"] = (pm.paint, dict(col=(0.50, 0.13, 0.035), rough=0.4, peel=0.8, grime=0.75, rust=0.55, streak=0.9,
                                   chip=0.6, chip_col=(0.17, 0.08, 0.04)))
    M["h_crane_white"] = (pm.paint, dict(col=(0.62, 0.62, 0.6), rough=0.4, peel=0.7, grime=0.7, rust=0.35, streak=0.8))
    M["h_machine_yellow"] = (pm.paint, dict(col=(0.72, 0.46, 0.02), rough=0.38, peel=0.7, grime=0.65, chip=0.7,
                                            streak=0.5, chip_col=(0.12, 0.1, 0.08)))
    M["h_primer"] = (pm.paint, dict(col=(0.16, 0.2, 0.18), rough=0.55, peel=0.6, grime=0.6, rust=0.5, streak=0.4))
    M["h_rack_blue"] = (pm.paint, dict(col=(0.03, 0.12, 0.34), rough=0.4, peel=0.6, grime=0.45, chip=0.6))
    M["h_rack_orange"] = (pm.paint, dict(col=(0.72, 0.22, 0.02), rough=0.4, peel=0.6, grime=0.45, chip=0.6))
    M["h_wrap"] = (pm.plastic, dict(col=(0.36, 0.38, 0.4), rough=0.18, grain=80.0, gstr=0.5, dirt=0.3))
    M["h_carton"] = (pm.fabric, dict(col=(0.36, 0.25, 0.14), rough=0.92, weave=60.0))
    M["h_sodium"] = (pm.emissive, dict(col=(1.0, 0.56, 0.20)))
    M["h_flood_white"] = (pm.emissive, dict(col=(0.86, 0.9, 1.0)))
    M["h_beacon_red"] = (pm.emissive, dict(col=(1.0, 0.04, 0.03)))
    M["h_beacon_white"] = (pm.emissive, dict(col=(1.0, 1.0, 1.0)))
    M["h_warm_panel"] = (pm.emissive, dict(col=(1.0, 0.82, 0.58)))
    M["h_signal_green"] = (pm.emissive, dict(col=(0.15, 0.95, 0.3)))
    M["h_signal_red"] = (pm.emissive, dict(col=(1.0, 0.05, 0.03)))
    M["h_cladding"] = (pm.paint, dict(col=(0.75, 0.75, 0.75), rough=0.45, mask=1.0, peel=0.6, grime=0.7, rust=0.5,
                                      streak=0.9, chip=0.3, chip_col=(0.18, 0.08, 0.04)))
    M["h_shutter"] = (pm.paint, dict(col=(0.32, 0.33, 0.34), rough=0.42, peel=0.6, grime=0.7, rust=0.45, streak=0.8))
    M["h_booth"] = (pm.paint, dict(col=(0.62, 0.62, 0.6), rough=0.4, peel=0.6, grime=0.6, streak=0.6, chip=0.3))
    M["h_hazard"] = (pm.paint, dict(col=(0.70, 0.43, 0.02), rough=0.42, peel=0.6, grime=0.5, chip=0.6))


_reg()


# ======================================================================================
# Shape helpers
# ======================================================================================
def corrugation(length, pitch=0.278, depth=0.036, plateau=0.3):
    """Trapezoid wave along u in [-length/2, length/2]: list of (u, d), d = 0 crest .. -depth trough."""
    pts = []
    n = max(1, int(round(length / pitch)))
    p = length / n
    s = (1.0 - 2 * plateau) / 2.0
    for i in range(n):
        u0 = -length / 2 + i * p
        pts += [(u0, 0.0), (u0 + plateau * p, 0.0), (u0 + (plateau + s) * p, -depth), (u0 + (2 * plateau + s) * p, -depth)]
    pts.append((length / 2, 0.0))
    return pts


def corr_sheet(A, length, height, axis, face, mat, pitch=0.278, depth=0.036, thick=0.004, z0=0.0, piece=None, out=1):
    """Corrugated sheet standing on z0, waves along `axis` ('x' or 'y'), crest plane at `face` on the other axis,
    outer side toward `out` (+1 / -1). Built as a closed prism: wave front + flat back behind the troughs."""
    w = corrugation(length, pitch, depth)
    front = [(u, face + out * d) for (u, d) in w]
    back = [(u, face - out * (depth + thick)) for (u, _) in reversed(w)]
    poly = front + back
    if axis == "y":
        poly = [(b, a) for (a, b) in poly]
    area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    if area < 0:
        poly = list(reversed(poly))
    return A.prism(poly, height, plane="XY", z0=z0, mat=mat, bevel=0.0, smooth=0, piece=piece)


def beam_between(A, p0, p1, w, h, mat, piece=None, bevel=0.01):
    """Box beam (w across, h up) from p0 to p1."""
    p0, p1 = V(p0), V(p1)
    d = p1 - p0
    L = d.length
    ob = A.box((L, w, h), at=(0, 0, 0), mat=mat, bevel=bevel, piece=piece)
    q = d.normalized().to_track_quat("X", "Z").to_matrix().to_4x4()
    ob.matrix_world = Matrix.Translation((p0 + p1) / 2) @ q @ ob.matrix_world
    return ob


def rod(A, p0, p1, r, mat, n=10, piece=None):
    return A.sweep([tuple(p0), tuple(p1)], r=r, n=n, mat=mat, piece=piece, smooth=60)


# ======================================================================================
# Containers
# ======================================================================================
@asset("Harbor_Container40", res=4096, collision="Box", edge=0.006, ao_dist=0.35, mask=True)
def container40(A):
    """40 ft dry box (12.19 x 2.44 x 2.59 m): corrugated side walls, roof and front wall, double cargo doors
    at +X with four locking bars each, corner posts and castings, bottom rails with forklift-free
    floor bearers, ORSAVIK line stencils and an invented unit number. Paint is the tint mask."""
    Lc, W, H = 12.19, 2.44, 2.59
    hx, hy = Lc / 2, W / 2
    post = 0.16
    # side walls (waves along X), crest on the outside
    for s in (-1, 1):
        corr_sheet(A, Lc - 2 * post, H - 0.32, "x", s * (hy - 0.012), "h_box_paint", depth=0.036, z0=0.16, out=s)
    # roof: shallow corrugation across the width (waves along X), slightly below the top rails
    roof = A.prism([(-hx + post, 0.0), (hx - post, 0.0), (hx - post, 0.02), (-hx + post, 0.02)], W - 0.12, plane="XZ",
                   mat="h_box_paint", bevel=0.0)
    roof.location.z = H - 0.06
    for i in range(int((Lc - 2 * post) / 0.46)):
        x = -hx + post + 0.23 + i * 0.46
        A.box((0.2, W - 0.14, 0.018), at=(x, 0, H - 0.035), mat="h_box_paint", bevel=0.004, segs=1)
    # front (closed) wall at -X: vertical waves along Y
    corr_sheet(A, W - 2 * post, H - 0.32, "y", -hx + 0.03, "h_box_paint", depth=0.04, z0=0.16, out=-1)
    # frame: corner posts, top / bottom side rails, end headers and sills, corner castings
    for sx in (-1, 1):
        for sy in (-1, 1):
            A.box((post, post, H), at=(sx * (hx - post / 2), sy * (hy - post / 2), H / 2), mat="h_frame", bevel=0.01)
            for z in (0.06, H - 0.06):
                A.box((0.178, 0.162, 0.118), at=(sx * (hx - 0.089), sy * (hy - 0.081), z), mat="h_frame", bevel=0.008)
    for sy in (-1, 1):
        A.box((Lc - 0.3, 0.1, 0.14), at=(0, sy * (hy - 0.05), H - 0.07), mat="h_frame", bevel=0.01)
        A.box((Lc - 0.3, 0.12, 0.16), at=(0, sy * (hy - 0.06), 0.08), mat="h_frame", bevel=0.01)
    for sx in (-1, 1):
        A.box((0.12, W - 0.3, 0.2), at=(sx * (hx - 0.06), 0, H - 0.1), mat="h_frame", bevel=0.01)
        A.box((0.14, W - 0.3, 0.16), at=(sx * (hx - 0.07), 0, 0.08), mat="h_frame", bevel=0.01)
    # floor (seen through nothing, but closes the box) and cross members underneath
    A.box((Lc - 0.3, W - 0.3, 0.03), at=(0, 0, 0.15), mat="h_floor_ply", bevel=0.0, segs=1)
    for i in range(14):
        A.box((0.06, W - 0.28, 0.12), at=(-hx + 0.5 + i * (Lc - 1.0) / 13, 0, 0.07), mat="h_frame", bevel=0.004, segs=1)
    # cargo doors at +X: two leaves with vertical corrugation, gasket gap, 4 locking bars, cams and handles
    dx = hx - 0.02
    for s in (-1, 1):
        yc = s * (W / 4 - 0.035)
        leaf = corr_sheet(A, W / 2 - 0.13, H - 0.36, "y", 0.0, "h_box_paint", depth=0.03, z0=0.18)
        leaf.matrix_world = Matrix.Translation((dx, yc, 0)) @ leaf.matrix_world
        A.box((0.03, W / 2 - 0.12, 0.08), at=(dx + 0.012, yc, H - 0.22), mat="h_box_paint", bevel=0.006)
        A.box((0.03, W / 2 - 0.12, 0.08), at=(dx + 0.012, yc, 0.22), mat="h_box_paint", bevel=0.006)
        for k in (-1, 1):
            by = yc + k * 0.27
            A.cyl(0.016, H - 0.3, at=(dx + 0.07, by, 0.12), mat="h_frame", n=10, bevel=0.0)
            for z in (0.15, H - 0.16):
                A.box((0.05, 0.07, 0.06), at=(dx + 0.065, by, z), mat="h_frame", bevel=0.006)
            for z in (0.62, 1.4, 2.1):
                A.box((0.03, 0.05, 0.03), at=(dx + 0.06, by, z), mat="h_frame", bevel=0.004)
            h = A.box((0.03, 0.04, 0.32), at=(dx + 0.1, by + 0.05 * k, 1.05), mat="h_frame", bevel=0.006)
            h.matrix_world = Matrix.Translation((dx + 0.1, by + 0.05 * k, 1.05)) @ Matrix.Rotation(math.radians(-12 * k), 4, "X") @ \
                Matrix.Translation((-dx - 0.1, -by - 0.05 * k, -1.05)) @ h.matrix_world
        # data plate
        A.box((0.008, 0.22, 0.14), at=(dx + 0.035, s * 0.42, 1.65), mat="aluminium", bevel=0.003)
    # stencils: line name on both sides, unit number on the doors and the right top corner
    f = font()
    if f:
        for s in (-1, 1):
            rot = (90, 0, 0) if s < 0 else (90, 0, 180)
            A.text("ORSAVIK", f, 0.56, 0.004, at=(-1.2, s * (hy + 0.002), 1.25), rot=rot, mat="h_stencil")
            A.text("SMT 418207-4", f, 0.14, 0.003, at=(4.6, s * (hy + 0.002), 2.15), rot=rot, mat="h_stencil")
        A.text("SMT 418207-4", f, 0.12, 0.003, at=(dx + 0.032, -0.6, 2.18), rot=(90, 0, 90), mat="h_stencil")
        A.text("45G1   MAX 30480 KG", f, 0.06, 0.003, at=(dx + 0.032, 0.6, 2.18), rot=(90, 0, 90), mat="h_stencil")
    A.layout = {"Cover": True}
    A.tint_variants = CONTAINER_TINTS
    A.view = (0.9, -0.85, 0.42)
    A.lens = 45
    A.preview["Body"] = {"tint": (0.02, 0.18, 0.2)}


# ======================================================================================
# Ship-to-shore gantry crane
# ======================================================================================
@asset("Harbor_STSCrane", res=4096, collision="Complex", edge=0.03, ao_dist=1.5)
def sts_crane(A):
    """Ship-to-shore container crane: portal of four box legs (16 m span across the quay along X, 16 m gauge
    along Y) on rail bogies, a main girder at 30 m running from a 14 m backreach (machinery house) to a
    boom 36 m out over the water (+X), an A-frame apex with fore- and backstays, a trolley with the
    operator cab and a spreader hanging on its ropes. Red aviation beacons, white strobe at the apex and
    floodlights under the girder (Emissive piece). Origin: centre of the four legs at rail level."""
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.piece("Glass", "Glass", res=256, glass=True)
    A.cur = "Body"
    S, G = 8.0, 8.0          # half span (X), half gauge (Y)
    ZP, ZG = 14.0, 30.0      # portal beam, girder underside
    LEG = 1.1
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * S, sy * G
            # leg (slight taper) and bogie
            A.box((LEG, LEG, ZP + 1.0), at=(x, y, 1.4 + (ZP + 1.0) / 2), mat="h_crane", bevel=0.04)
            A.box((3.4, 1.4, 1.2), at=(x, y, 0.75), mat="h_crane", bevel=0.05)
            for wx in (-1.1, 0.0, 1.1):
                A.cyl(0.38, 0.26, at=(x + wx, y - 0.13, 0.38), axis="Y", mat="steel_dark", n=20, bevel=0.01)
            A.box((3.6, 1.0, 0.25), at=(x, y, 1.45), mat="h_hazard", bevel=0.02)
            # upper legs to the girder (waterside legs straight, landside legs too)
            A.box((LEG * 0.9, LEG * 0.9, ZG - ZP - 1.0), at=(x, y, ZP + 1.0 + (ZG - ZP - 1.0) / 2), mat="h_crane", bevel=0.04)
    # portal beams along X / Y (the portal stays open at ground level: trucks drive through it)
    for sx in (-1, 1):
        A.box((1.4, 2 * G + LEG, 1.6), at=(sx * S, 0, ZP + 0.6), mat="h_crane", bevel=0.05)
    for sy in (-1, 1):
        A.box((2 * S + LEG, 1.4, 1.8), at=(0, sy * G, ZP + 0.4), mat="h_crane", bevel=0.05)
        # diagonal bracing in the leg planes above the portal
        beam_between(A, (-S, sy * G, ZP + 1.5), (S, sy * G, ZG - 0.5), 0.6, 0.6, "h_crane", bevel=0.03)
    # main girder (two box beams) from backreach to boom tip; boom part is a separate continuing span
    X0, X1 = -S - 14.0, S + 36.0
    for sy in (-1, 1):
        A.box((X1 - X0, 1.2, 2.2), at=((X0 + X1) / 2, sy * 2.6, ZG + 1.1), mat="h_crane", bevel=0.05)
        # walkway railing along the outside of each beam
        A.box((X1 - X0, 0.05, 0.05), at=((X0 + X1) / 2, sy * 3.4, ZG + 3.3), mat="h_crane_white", bevel=0.0)
        for i in range(int((X1 - X0) / 2.5)):
            A.box((0.05, 0.05, 1.1), at=(X0 + 0.5 + i * 2.5, sy * 3.4, ZG + 2.75), mat="h_crane_white", bevel=0.0)
    for i in range(int((X1 - X0) / 4.0)):
        A.box((0.4, 5.2, 0.4), at=(X0 + 1.0 + i * 4.0, 0, ZG + 0.2), mat="h_crane", bevel=0.02)
    # girder carried on the legs: cross heads
    for sx in (-1, 1):
        A.box((1.6, 2 * G + LEG, 1.2), at=(sx * S, 0, ZG - 0.4), mat="h_crane", bevel=0.04)
    # A-frame apex over the waterside legs and stays
    apex = V((S * 0.5, 0, ZG + 16.0))
    for sy in (-1, 1):
        beam_between(A, (S, sy * 2.6, ZG + 2.2), apex + V((0, sy * 1.2, 0)), 0.9, 0.9, "h_crane", bevel=0.03)
        beam_between(A, (-S + 2.0, sy * 2.6, ZG + 2.2), apex + V((0, sy * 1.2, 0)), 0.8, 0.8, "h_crane", bevel=0.03)
        rod(A, apex + V((0.5, sy * 1.2, 0)), (X1 - 2.0, sy * 2.6, ZG + 2.3), 0.12, "h_crane_white")
        rod(A, apex + V((0.5, sy * 1.2, -2.0)), (X1 - 16.0, sy * 2.6, ZG + 2.3), 0.12, "h_crane_white")
        rod(A, apex + V((-0.5, sy * 1.2, 0)), (X0 + 2.0, sy * 2.6, ZG + 2.3), 0.14, "h_crane_white")
    A.box((2.0, 3.6, 1.0), at=tuple(apex + V((0, 0, 0.3))), mat="h_crane", bevel=0.05)
    # machinery house on the backreach
    A.box((10.0, 6.6, 4.4), at=(X0 + 5.6, 0, ZG + 4.4), mat="h_crane_white", bevel=0.06)
    A.box((10.4, 7.0, 0.3), at=(X0 + 5.6, 0, ZG + 6.75), mat="h_crane", bevel=0.03)
    for i in range(4):
        A.box((0.06, 1.2, 0.8), at=(X0 + 0.58, -2.4 + i * 1.6, ZG + 4.6), mat="steel_dark", bevel=0.01)
    f = font()
    if f:
        for s in (-1, 1):
            A.text("SALTMARSH  07", f, 1.5, 0.02, at=(X0 + 5.6, s * 3.31, ZG + 3.7), rot=(90, 0, 0 if s < 0 else 180),
                   mat="h_crane")
    # trolley + operator cab (hanging under the waterside girder) + spreader on ropes
    tx = S + 6.0
    A.box((5.0, 6.4, 1.6), at=(tx, 0, ZG + 2.6), mat="h_crane_white", bevel=0.05)
    A.box((2.6, 2.4, 2.6), at=(tx + 0.6, -2.0, ZG - 1.9), mat="h_crane_white", bevel=0.05)
    A.cur = "Glass"
    A.box((0.06, 2.0, 1.6), at=(tx + 1.92, -2.0, ZG - 1.8), mat="glass", bevel=0.0)
    A.box((2.0, 2.0, 0.06), at=(tx + 0.6, -2.0, ZG - 3.22), mat="glass", bevel=0.0)
    A.cur = "Emissive"
    A.box((0.04, 1.8, 0.5), at=(tx + 0.0, -2.0, ZG - 1.3), mat="h_warm_panel", bevel=0.0)
    A.cur = "Body"
    zs = ZG - 11.0
    for sy in (-1, 1):
        for sx in (-1, 1):
            rod(A, (tx + sx * 1.6, sy * 1.6, ZG + 1.8), (tx + sx * 1.0, sy * 1.0, zs + 0.6), 0.03, "steel_dark", n=6)
    A.box((2.4, 12.0, 0.6), at=(tx, 0, zs + 0.3), mat="h_machine_yellow", bevel=0.03)
    A.box((2.6, 2.4, 1.2), at=(tx, 0, zs + 1.2), mat="h_machine_yellow", bevel=0.04)
    for sy in (-1, 1):
        for sx in (-1, 1):
            A.box((0.3, 0.3, 0.5), at=(tx + sx * 1.0, sy * 5.8, zs - 0.15), mat="steel_dark", bevel=0.02)
    # ladders / stair towers on two legs (simple cage)
    for (lx, ly) in ((-S - 0.9, -G), (S + 0.9, G)):
        for i in range(int((ZG - 2.0) / 3.0)):
            z = 2.0 + i * 3.0
            A.box((0.9, 1.2, 0.05), at=(lx, ly, z), mat="galvanized", bevel=0.0)
            A.box((0.05, 1.2, 1.0), at=(lx - 0.44 * (1 if lx > 0 else -1), ly, z + 0.5), mat="galvanized", bevel=0.0)
    # lights: floods under the girder, beacons on apex / tip / backreach, strobe on the apex
    A.cur = "Emissive"
    for x in (S - 4.0, S + 14.0, S + 26.0, -S + 2.0):
        for sy in (-1, 1):
            A.box((0.7, 0.5, 0.12), at=(x, sy * 2.6, ZG - 0.06), mat="h_flood_white", bevel=0.01)
    for p in (apex + V((0, 0, 1.0)), V((X1 - 0.5, 2.6, ZG + 2.5)), V((X1 - 0.5, -2.6, ZG + 2.5)), V((X0 + 0.5, 0, ZG + 7.2)),
              V((S, G, ZP + 1.6)), V((-S, -G, ZP + 1.6))):
        A.sphere(0.25, at=tuple(p), mat="h_beacon_red", seg=10, rings=6)
    A.sphere(0.22, at=tuple(apex + V((0.0, 0, 1.6))), mat="h_beacon_white", seg=10, rings=6)
    A.cur = "Body"
    A.point("FloodA", (S - 4.0, 0, ZG - 0.2))
    A.point("FloodB", (S + 14.0, 0, ZG - 0.2))
    A.point("Light", (S + 2.0, 0, ZG - 0.2))
    # checker: the portal is open between the legs; the layout adds a blocker at each leg / bogie instead
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (0.55, -1.0, 0.32)
    A.lens = 24
    A.margin = 1.04


# ======================================================================================
# Yard machines
# ======================================================================================
def _wheel(A, x, y, r, w, mat="tire"):
    A.cyl(r, w, at=(x, y - w / 2, r), axis="Y", mat=mat, n=28, bevel=0.03)
    A.cyl(r * 0.55, w + 0.02, at=(x, y - w / 2 - 0.01, r), axis="Y", mat="h_machine_yellow", n=20, bevel=0.01)


@asset("Harbor_ReachStacker", res=4096, collision="Complex", edge=0.012, ao_dist=0.6)
def reach_stacker(A):
    """Container reach stacker: long chassis on twin front / single rear tyres, counterweight at the rear,
    raised cab, telescopic boom pivoted at the rear rising over the cab toward the front and a 40 ft
    top-lift spreader across the front (points: SpreaderBottom). Work lights and beacon on the Emissive
    piece, cab glass on the Glass piece."""
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.piece("Glass", "Glass", res=512, glass=True)
    A.cur = "Body"
    # chassis
    A.box((8.6, 3.2, 1.1), at=(0.2, 0, 1.25), mat="h_machine_yellow", bevel=0.06)
    A.box((2.0, 3.4, 1.8), at=(-4.0, 0, 1.6), mat="h_machine_yellow", bevel=0.08)     # counterweight
    A.box((0.2, 3.5, 0.3), at=(-5.05, 0, 0.9), mat="h_hazard", bevel=0.02)
    A.box((1.4, 3.0, 0.9), at=(3.6, 0, 2.2), mat="h_machine_yellow", bevel=0.05)     # front axle housing
    for sy in (-1, 1):
        _wheel(A, 3.2, sy * 1.45, 0.82, 0.55)
        _wheel(A, 3.2, sy * 0.85, 0.82, 0.55)
        _wheel(A, -3.0, sy * 1.25, 0.72, 0.5)
        A.box((2.4, 0.4, 0.15), at=(3.2, sy * 1.65, 1.75), mat="h_frame", bevel=0.02)  # mudguard
    # cab (raised, mid-left) with glass
    A.box((2.0, 1.7, 0.4), at=(0.2, -0.75, 2.0), mat="h_machine_yellow", bevel=0.04)
    for (px, py) in ((-0.75, -1.55), (1.15, -1.55), (-0.75, 0.05), (1.15, 0.05)):
        A.box((0.1, 0.1, 1.8), at=(px, py, 3.1), mat="h_frame", bevel=0.01)
    A.box((2.1, 1.8, 0.12), at=(0.2, -0.75, 4.05), mat="h_machine_yellow", bevel=0.03)
    A.cur = "Glass"
    for (cx, cy, sx, sy) in ((0.2, -1.6, 1.8, 0.03), (0.2, 0.1, 1.8, 0.03), (-0.8, -0.75, 0.03, 1.6), (1.2, -0.75, 0.03, 1.6)):
        A.box((sx, sy, 1.7), at=(cx, cy, 3.1), mat="glass", bevel=0.0)
    A.cur = "Body"
    A.box((0.6, 0.6, 0.5), at=(-0.2, -0.75, 2.45), mat="leather_black", bevel=0.05)    # seat
    # boom: pivot on rear posts, telescopic sections rising forward
    piv = V((-3.2, 0.0, 3.0))
    ang = math.radians(24.0)
    d = V((math.cos(ang), 0.0, math.sin(ang)))
    for sy in (-1, 1):
        A.box((0.6, 0.5, 1.6), at=(-3.2, sy * 0.55, 2.4), mat="h_machine_yellow", bevel=0.04)
    for (l0, l1, w, h) in ((0.0, 7.0, 0.95, 1.1), (6.6, 11.6, 0.8, 0.9)):
        beam_between(A, piv + d * l0, piv + d * l1, w, h, "h_machine_yellow", bevel=0.03)
    # lift cylinder
    beam_between(A, (1.0, 0, 1.9), piv + d * 4.2 + V((0, 0, -0.5)), 0.32, 0.32, "steel_dark", bevel=0.02)
    rod(A, piv + d * 2.6 + V((0, 0, -0.6)), piv + d * 4.2 + V((0, 0, -0.5)), 0.09, "chrome")
    tip = piv + d * 11.6
    # spreader (12 m across Y) hanging under the boom tip
    sb = tip + V((0.4, 0, -1.0))
    A.box((1.2, 1.4, 1.0), at=tuple(sb + V((0, 0, 0.4))), mat="h_machine_yellow", bevel=0.04)
    A.box((0.7, 12.0, 0.45), at=tuple(sb + V((0, 0, -0.25))), mat="h_machine_yellow", bevel=0.03)
    for sy in (-1, 1):
        A.box((0.5, 0.5, 0.6), at=tuple(sb + V((0, sy * 5.9, -0.6))), mat="steel_dark", bevel=0.02)
        A.box((0.6, 0.2, 0.18), at=tuple(sb + V((0, sy * 6.08, -0.25))), mat="h_hazard", bevel=0.01)
    A.point("SpreaderBottom", tuple(sb + V((0, 0, -0.9))))
    # lights
    A.cur = "Emissive"
    for sy in (-1, 1):
        A.box((0.06, 0.3, 0.2), at=(1.33, -0.75 + sy * 0.6, 3.95), mat="h_flood_white", bevel=0.01)
        A.box((0.06, 0.25, 0.15), at=(4.32, sy * 1.2, 2.45), mat="h_flood_white", bevel=0.01)
        A.box((0.05, 0.2, 0.12), at=(-5.03, sy * 1.4, 2.3), mat="h_signal_red", bevel=0.01)
    A.cyl(0.11, 0.18, at=(0.2, -0.75, 4.11), mat="plastic_amber", n=12, bevel=0.01)
    A.cur = "Body"
    f = font()
    if f:
        for s in (-1, 1):
            A.text("RS-14", f, 0.42, 0.006, at=(-4.0, s * 1.71, 1.7), rot=(90, 0, 0 if s < 0 else 180), mat="h_frame")
    A.layout = {"Core": [[-520, -175], [440, 175]], "Cover": True}
    A.view = (0.75, -1.0, 0.35)
    A.lens = 35


@asset("Harbor_Forklift", res=2048, collision="Box", edge=0.006, ao_dist=0.3)
def forklift(A):
    """Counterbalance forklift (5 t): chassis, rear counterweight, overhead guard on four posts, upright
    mast with carriage and two forks lowered to the ground, seat and steering wheel, beacon."""
    A.piece("Emissive", "Emissive", res=128, emissive=True)
    A.cur = "Body"
    A.box((2.3, 1.3, 0.75), at=(0.0, 0, 0.75), mat="h_machine_yellow", bevel=0.05)
    A.box((0.7, 1.32, 1.05), at=(-1.05, 0, 1.0), mat="h_frame", bevel=0.08)
    for sy in (-1, 1):
        A.cyl(0.36, 0.3, at=(0.75, sy * 0.66 - 0.15, 0.36), axis="Y", mat="tire", n=24, bevel=0.02)
        A.cyl(0.3, 0.26, at=(-0.85, sy * 0.6 - 0.13, 0.3), axis="Y", mat="tire", n=24, bevel=0.02)
    for (px, py) in ((0.55, -0.55), (0.55, 0.55), (-0.75, -0.55), (-0.75, 0.55)):
        A.box((0.07, 0.07, 1.25), at=(px, py, 1.75), mat="h_frame", bevel=0.01)
    A.box((1.45, 1.2, 0.08), at=(-0.1, 0, 2.38), mat="h_frame", bevel=0.01)
    for i in range(5):
        A.box((1.4, 0.03, 0.03), at=(-0.1, -0.5 + i * 0.25, 2.43), mat="h_frame", bevel=0.0)
    A.box((0.5, 0.5, 0.45), at=(-0.35, 0, 1.35), mat="leather_black", bevel=0.05)
    A.cyl(0.17, 0.03, at=(0.3, 0, 1.6), mat="plastic_black", n=20, rot=(0, -35, 0), bevel=0.005)
    # mast, carriage, forks
    for sy in (-1, 1):
        A.box((0.1, 0.12, 2.6), at=(1.3, sy * 0.38, 1.4), mat="h_frame", bevel=0.01)
        A.box((1.2, 0.12, 0.05), at=(1.95, sy * 0.3, 0.06), mat="steel_dark", bevel=0.005)
        A.box((0.05, 0.12, 0.7), at=(1.37, sy * 0.3, 0.38), mat="steel_dark", bevel=0.005)
    A.box((0.08, 1.0, 0.5), at=(1.36, 0, 0.55), mat="h_frame", bevel=0.01)
    A.box((0.12, 0.9, 0.1), at=(1.3, 0, 2.7), mat="h_frame", bevel=0.01)
    A.cur = "Emissive"
    A.cyl(0.07, 0.12, at=(-0.75, 0, 2.42), mat="plastic_amber", n=10, bevel=0.005)
    for sy in (-1, 1):
        A.box((0.04, 0.12, 0.1), at=(0.6, sy * 0.55, 2.2), mat="h_flood_white", bevel=0.005)
    A.cur = "Body"
    A.layout = {"Cover": True}
    A.view = (0.9, -0.85, 0.35)
    A.lens = 50


# ======================================================================================
# Lighting
# ======================================================================================
@asset("Harbor_FloodMast", res=2048, collision="Box", edge=0.008, ao_dist=0.4)
def flood_mast(A):
    """24 m high-mast lighting column: concrete plinth, tapered galvanised shaft with door and access hatch,
    a head frame with four sodium floodlights aimed forward and down (+X), service platform with rail and
    a red obstruction lamp. Point Light at the head."""
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    A.box((1.4, 1.4, 0.6), at=(0, 0, 0.3), mat="concrete", bevel=0.03)
    A.box((1.0, 1.0, 0.05), at=(0, 0, 0.625), mat="galvanized", bevel=0.01)
    for sx in (-1, 1):
        for sy in (-1, 1):
            A.cyl(0.03, 0.12, at=(sx * 0.4, sy * 0.4, 0.65), mat="galvanized", n=8)
    Hm = 24.0
    A.cyl(0.32, Hm - 0.6, at=(0, 0, 0.65), r2=0.15, mat="galvanized", n=20, bevel=0.0)
    A.box((0.02, 0.22, 0.6), at=(0.31, 0, 1.4), mat="galvanized", bevel=0.005)
    # platform + rail
    zp = Hm - 1.2
    A.cyl(1.2, 0.08, at=(0, 0, zp), mat="galvanized", n=24, bevel=0.005)
    A.sweep(circle_pts(1.2, 24), r=0.025, n=6, mat="galvanized", closed=True, at=(0, 0, zp + 1.0))
    for i in range(8):
        a = i * math.pi / 4
        A.cyl(0.02, 1.0, at=(1.18 * math.cos(a), 1.18 * math.sin(a), zp), mat="galvanized", n=6)
    # head frame
    A.box((0.15, 2.0, 0.15), at=(0.35, 0, Hm), mat="galvanized", bevel=0.01)
    A.box((0.15, 2.0, 0.15), at=(0.35, 0, Hm - 0.9), mat="galvanized", bevel=0.01)
    for y in (-0.95, -0.32, 0.32, 0.95):
        hous = A.box((0.5, 0.55, 0.4), at=(0, 0, 0), mat="powder_black", bevel=0.03)
        lens = A.box((0.04, 0.48, 0.33), at=(0, 0, 0), mat="h_sodium", bevel=0.005, piece="Emissive")
        for ob, ox in ((hous, 0.0), (lens, 0.26)):
            ob.matrix_world = (Matrix.Translation((0.62, y, Hm - 0.45)) @ Matrix.Rotation(math.radians(55), 4, "Y")
                               @ Matrix.Translation((ox, 0, 0)) @ ob.matrix_world)
    A.cur = "Emissive"
    A.sphere(0.12, at=(0, 0, Hm + 0.25), mat="h_beacon_red", seg=10, rings=6)
    A.cur = "Body"
    A.point("Light", (0.9, 0, Hm - 0.6))
    A.layout = {"Core": [[-70, -70], [70, 70]], "Cover": True}
    A.view = (1.0, -0.6, 0.25)
    A.lens = 28
    A.margin = 1.04


# ======================================================================================
# Fences, quay furniture
# ======================================================================================
def _wire_mesh(A, y0, y1, z0, z1, x, pitch=0.065, r=0.0022, mat="galvanized"):
    """Chain-link as two families of diagonal wires (thin square strands) clipped to the panel."""
    verts, faces = [], []
    span = (y1 - y0) + (z1 - z0)
    n = int(span / pitch) + 1

    def strand(a, b):
        a, b = V(a), V(b)
        d = (b - a).normalized()
        nrm = V((1, 0, 0))
        side = d.cross(nrm).normalized()
        k = len(verts)
        for p in (a, b):
            for (u, w) in ((r, r), (-r, r), (-r, -r), (r, -r)):
                verts.append(tuple(p + nrm * u + side * w))
        for j in range(4):
            faces.append((k + j, k + (j + 1) % 4, k + 4 + (j + 1) % 4, k + 4 + j))

    hz = z1 - z0
    for fam in (1, -1):
        for i in range(n):
            if fam > 0:
                c = y0 - hz + i * pitch                       # y = c + (z - z0)
                za, zb = z0 + max(0.0, y0 - c), z0 + min(hz, y1 - c)
                ya, yb = c + (za - z0), c + (zb - z0)
            else:
                c = y0 + i * pitch                            # y = c - (z - z0)
                za, zb = z0 + max(0.0, c - y1), z0 + min(hz, c - y0)
                ya, yb = c - (za - z0), c - (zb - z0)
            if zb - za < 0.02:
                continue
            strand((x, ya, za), (x, yb, zb))
    return A.mesh(verts, faces, mat, recalc=True, smooth=0)


@asset("Harbor_ChainFence_4m", res=1024, collision="Box", edge=0.004, ao_dist=0.15)
def chain_fence(A):
    """4 m security fence panel along Y: galvanised posts, top and mid rails, chain-link mesh (2.4 m),
    45-degree outrigger arms with three strands of barbed wire. See-through (Los false)."""
    Hm = 2.4
    for y in (-2.0, 2.0):
        A.cyl(0.035, Hm + 0.1, at=(0, y, 0), mat="galvanized", n=10, bevel=0.0)
        A.cyl(0.04, 0.01, at=(0, y, Hm + 0.1), mat="galvanized", n=10, bevel=0.0)
        arm = A.box((0.03, 0.03, 0.55), at=(0, 0, 0), mat="galvanized", bevel=0.0)
        arm.matrix_world = Matrix.Translation((0.17, y, Hm + 0.28)) @ Matrix.Rotation(math.radians(45), 4, "Y") @ arm.matrix_world
    A.sweep([(0, -2.0, Hm), (0, 2.0, Hm)], r=0.021, n=10, mat="galvanized")
    A.sweep([(0, -2.0, 1.2), (0, 2.0, 1.2)], r=0.016, n=8, mat="galvanized")
    A.sweep([(0, -2.0, 0.05), (0, 2.0, 0.05)], r=0.004, n=6, mat="galvanized")
    _wire_mesh(A, -1.98, 1.98, 0.05, Hm - 0.02, 0.0)
    for k in range(3):
        x = 0.1 + k * 0.12
        z = Hm + 0.12 + k * 0.12
        pts = []
        for i in range(81):
            y = -2.0 + i * 0.05
            pts.append((x + 0.004 * math.sin(i * 2.1), y, z + 0.004 * math.cos(i * 1.7)))
        A.sweep(pts, r=0.0025, n=5, mat="steel_dark")
        for i in range(20):
            y = -1.9 + i * 0.2
            A.box((0.05, 0.004, 0.004), at=(x, y, z), mat="steel_dark", rot=(0, 0, 45 + 30 * (i % 3)), bevel=0.0)
    A.layout = {"Core": [[-6, -200], [6, 200]], "Los": False, "Cover": False}
    A.view = (1.0, -0.4, 0.2)
    A.lens = 50


@asset("Harbor_MooringBollard", res=1024, collision="Box", edge=0.006, ao_dist=0.15)
def mooring_bollard(A):
    """Cast-iron tee-head mooring bollard on a bolted base plate (0.8 m)."""
    prof = [(0.0, 0.0), (0.42, 0.0), (0.42, 0.06), (0.24, 0.08), (0.2, 0.12), (0.19, 0.55), (0.24, 0.62),
            (0.33, 0.66), (0.34, 0.74), (0.22, 0.78), (0.0, 0.79)]
    A.lathe(prof, mat="cast_iron", n=32)
    A.box((0.95, 0.18, 0.12), at=(0.0, 0, 0.66), mat="cast_iron", bevel=0.03)
    for i in range(6):
        a = i * math.pi / 3
        A.cyl(0.035, 0.05, at=(0.34 * math.cos(a), 0.34 * math.sin(a), 0.06), mat="steel_dark", n=6)
    A.view = (1.0, -0.6, 0.4)
    A.lens = 60


@asset("Harbor_Fender", res=1024, collision="None", edge=0.01, ao_dist=0.2)
def fender(A):
    """Cylindrical rubber quay fender (1.2 m dia x 2.0 m) hung on two chains from the cope edge. Origin at
    the hanging point on the quay top; the fender sits below it in front of the wall face (+X)."""
    A.cyl(0.6, 2.0, at=(0.62, -1.0, -1.0), axis="Y", mat="rubber", n=32, bevel=0.04)
    A.cyl(0.25, 2.04, at=(0.62, -1.02, -1.0), axis="Y", mat="steel_dark", n=16, bevel=0.01)
    for y in (-0.8, 0.8):
        pts = catmull([(0.05, y, 0.0), (0.3, y, -0.2), (0.6, y, -0.4)], 4)
        A.sweep(pts, r=0.025, n=6, mat="galvanized")
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (1.0, -0.6, 0.2)
    A.lens = 60


# ======================================================================================
# Warehouse pieces
# ======================================================================================
@asset("Harbor_PalletRack", res=2048, collision="Box", edge=0.005, ao_dist=0.35)
def pallet_rack(A):
    """Selective pallet racking, one 2.7 m bay (Y) x 1.1 m deep (X) x 4.6 m: blue uprights with bracing,
    orange beams at three levels, shrink-wrapped loads and carton stacks on pallets."""
    Hr, Dp, Wb = 4.6, 1.1, 2.7
    for sy in (-1, 1):
        for sx in (-1, 1):
            A.box((0.09, 0.08, Hr), at=(sx * Dp / 2, sy * Wb / 2, Hr / 2), mat="h_rack_blue", bevel=0.006)
        for i in range(7):
            z0 = 0.2 + i * 0.62
            beam_between(A, (-Dp / 2, sy * Wb / 2, z0), (Dp / 2, sy * Wb / 2, z0 + 0.55), 0.03, 0.03, "h_rack_blue", bevel=0.0)
    levels = (0.0, 1.55, 3.1)
    for z in levels[1:] + (4.45,):
        for sx in (-1, 1):
            A.box((0.06, Wb, 0.14), at=(sx * (Dp / 2 + 0.04), 0, z), mat="h_rack_orange", bevel=0.006)
    for k, z in enumerate(levels):
        zz = z + (0.07 if z > 0 else 0.0)
        for j, y in enumerate((-0.65, 0.65)):
            A.box((1.0, 1.1, 0.14), at=(0, y, zz + 0.07), mat="pine", bevel=0.008)
            if (k + j) % 3 == 2:
                continue
            if (k + j) % 2 == 0:
                A.box((0.98, 1.05, 1.15), at=(0, y, zz + 0.14 + 0.575), mat="h_wrap", bevel=0.05)
            else:
                for (cx, cy, cz) in ((-0.24, -0.26, 0), (0.24, -0.26, 0), (-0.24, 0.26, 0), (0.24, 0.26, 0), (0, 0, 1)):
                    A.box((0.46, 0.5, 0.42), at=(cx * (1 if cz == 0 else 0), y + cy, zz + 0.14 + 0.21 + cz * 0.42),
                          mat="h_carton", bevel=0.01)
    A.layout = {"Cover": True}
    A.view = (1.0, -0.7, 0.3)
    A.lens = 40


@asset("Harbor_CladdingPanel_4m", res=2048, collision="Box", edge=0.004, ao_dist=0.3, mask=True)
def cladding_panel(A):
    """Warehouse wall bay: 4 m wide (Y) x 8 m corrugated steel sheet (tint mask) on a 0.6 m concrete
    dwarf wall, with sheeting rails and a column flange behind it (the inside face, -X). Outside = +X."""
    A.box((0.25, 4.0, 0.6), at=(-0.06, 0, 0.3), mat="concrete", bevel=0.01)
    corr_sheet(A, 4.0, 7.4, "y", 0.07, "h_cladding", pitch=0.3, depth=0.045, z0=0.6)
    A.box((0.06, 4.02, 0.12), at=(0.05, 0, 7.98), mat="h_frame", bevel=0.01)       # flashing
    for z in (2.2, 4.4, 6.6):
        A.box((0.12, 4.0, 0.06), at=(-0.04, 0, z), mat="h_primer", bevel=0.005)
    A.box((0.25, 0.25, 7.4), at=(-0.18, -1.87, 4.3), mat="h_primer", bevel=0.01)
    A.tint_variants = CLADDING_TINTS
    A.layout = {"Cover": True}
    A.view = (1.0, -0.5, 0.2)
    A.lens = 35
    A.preview["Body"] = {"tint": (0.02, 0.18, 0.2)}


@asset("Harbor_RollerDoor", res=2048, collision="Complex", edge=0.004, ao_dist=0.3)
def roller_door(A):
    """Warehouse roller-shutter bay: 4 m wide (Y) x 8 m wall bay with a 3.6 m wide opening, the slatted
    curtain stopped half-raised (clear height 3.2 m), coil box and guides, hazard-striped jambs, cladding
    above. Walk-through (Solid false for the checker; complex collision in game)."""
    W, Hd = 3.6, 4.6
    A.box((0.25, 0.2, 0.6), at=(-0.06, -1.9, 0.3), mat="concrete", bevel=0.01)
    A.box((0.25, 0.2, 0.6), at=(-0.06, 1.9, 0.3), mat="concrete", bevel=0.01)
    corr_sheet(A, 4.0, 8.0 - Hd - 0.5, "y", 0.07, "h_shutter", pitch=0.3, depth=0.045, z0=Hd + 0.5)
    for sy in (-1, 1):
        A.box((0.2, 0.2, Hd + 0.5), at=(0.0, sy * (W / 2 + 0.1), (Hd + 0.5) / 2), mat="h_hazard", bevel=0.01)
        A.box((0.14, 0.1, Hd), at=(0.12, sy * (W / 2 - 0.02), Hd / 2), mat="steel_dark", bevel=0.005)
    A.box((0.7, W + 0.6, 0.7), at=(0.25, 0, Hd + 0.35), mat="h_shutter", bevel=0.02)
    # curtain: slats from 3.2 m up to the coil
    for i in range(int((Hd - 3.2) / 0.1)):
        z = 3.2 + i * 0.1 + 0.05
        A.box((0.03, W, 0.09), at=(0.14, 0, z), mat="h_shutter", bevel=0.01, segs=1)
    A.box((0.06, W, 0.08), at=(0.14, 0, 3.16), mat="rubber", bevel=0.01)
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (1.0, -0.5, 0.2)
    A.lens = 35


@asset("Harbor_RoofTruss_22m", res=1024, collision="None", edge=0.005, ao_dist=0.3)
def roof_truss(A):
    """Pratt roof truss spanning 22 m along X (bearing at x = +-11, z = 0): pitched top chord rising 1.6 m,
    flat bottom chord, verticals and diagonals in primed steel angles."""
    Lh = 11.0
    rise = 1.6

    def top(x):
        return 1.0 + rise * (1.0 - abs(x) / Lh)
    beam_between(A, (-Lh, 0, 0.0), (Lh, 0, 0.0), 0.18, 0.2, "h_primer", bevel=0.005)
    beam_between(A, (-Lh, 0, 0.0), (0, 0, top(0)), 0.2, 0.22, "h_primer", bevel=0.005)
    beam_between(A, (0, 0, top(0)), (Lh, 0, 0.0), 0.2, 0.22, "h_primer", bevel=0.005)
    n = 10
    for i in range(1, n):
        x = -Lh + i * 2 * Lh / n
        beam_between(A, (x, 0, 0.0), (x, 0, top(x) - 0.08), 0.1, 0.1, "h_primer", bevel=0.003)
        xn = -Lh + (i + 1) * 2 * Lh / n if x < 0 else -Lh + (i - 1) * 2 * Lh / n
        if abs(x) > 1.0:
            beam_between(A, (x, 0, top(x) - 0.08), (xn, 0, 0.0), 0.08, 0.08, "h_primer", bevel=0.003)
    for x in (-Lh, Lh):
        A.box((0.4, 0.3, 0.05), at=(x, 0, -0.12), mat="steel_dark", bevel=0.005)
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (0.3, -1.0, 0.2)
    A.lens = 35


# ======================================================================================
# Gatehouse
# ======================================================================================
@asset("Harbor_Gatehouse", res=2048, collision="Box", edge=0.006, ao_dist=0.35)
def gatehouse(A):
    """Terminal gate booth (4.2 x 3.0 x 3.1 m): plinth, painted steel walls with a ribbon of windows on
    three sides, door on -Y, flat roof with a deep overhang and a lit soffit, interior desk with
    monitors (warm lit panel), traffic signal heads on a post and the invented gate sign. Point Light
    under the canopy."""
    A.piece("Glass", "Glass", res=512, glass=True)
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    Lx, Wy, Hh = 4.2, 3.0, 3.1
    A.box((Lx + 0.4, Wy + 0.4, 0.25), at=(0, 0, 0.125), mat="concrete", bevel=0.02)
    z0 = 0.25
    # walls: lower band, window ribbon, upper band
    A.box((Lx, Wy, 1.0), at=(0, 0, z0 + 0.5), mat="h_booth", bevel=0.02)
    A.box((Lx, Wy, 0.55), at=(0, 0, Hh - 0.275), mat="h_booth", bevel=0.02)
    for (px, py) in ((Lx / 2 - 0.08, Wy / 2 - 0.08), (-Lx / 2 + 0.08, Wy / 2 - 0.08), (Lx / 2 - 0.08, -Wy / 2 + 0.08),
                     (-Lx / 2 + 0.08, -Wy / 2 + 0.08), (0.0, Wy / 2 - 0.08), (Lx / 2 - 0.08, 0.0)):
        A.box((0.16, 0.16, Hh - 1.25 - 0.55), at=(px, py, z0 + 1.0 + (Hh - z0 - 1.55) / 2), mat="h_booth", bevel=0.01)
    # back wall (-X) solid, door on -Y side
    A.box((0.16, Wy, Hh - z0 - 1.55), at=(-Lx / 2 + 0.08, 0, z0 + 1.0 + (Hh - z0 - 1.55) / 2), mat="h_booth", bevel=0.01)
    A.box((0.9, 0.06, 2.2), at=(-0.9, -Wy / 2 - 0.02, z0 + 1.1), mat="steel_dark", bevel=0.01)
    A.cur = "Glass"
    A.box((0.03, Wy - 0.3, Hh - z0 - 1.55), at=(Lx / 2 - 0.08, 0, z0 + 1.0 + (Hh - z0 - 1.55) / 2), mat="glass", bevel=0.0)
    A.box((Lx - 0.3, 0.03, Hh - z0 - 1.55), at=(0, Wy / 2 - 0.08, z0 + 1.0 + (Hh - z0 - 1.55) / 2), mat="glass", bevel=0.0)
    A.box((1.8, 0.03, Hh - z0 - 1.55), at=(0.9, -Wy / 2 + 0.08, z0 + 1.0 + (Hh - z0 - 1.55) / 2), mat="glass", bevel=0.0)
    A.cur = "Body"
    # interior: desk + monitors (seen through the glass)
    A.box((0.6, 2.4, 0.08), at=(Lx / 2 - 0.5, 0, z0 + 0.95), mat="pine", bevel=0.01)
    A.cur = "Emissive"
    for y in (-0.6, 0.2):
        A.box((0.04, 0.5, 0.32), at=(Lx / 2 - 0.62, y, z0 + 1.25), mat="h_flood_white", bevel=0.0)
    A.box((Lx - 0.6, Wy - 0.6, 0.03), at=(0, 0, Hh - 0.57), mat="h_warm_panel", bevel=0.0)
    A.cur = "Body"
    # roof with overhang and lit soffit
    A.box((Lx + 1.6, Wy + 1.4, 0.3), at=(0.3, 0, Hh + 0.15), mat="h_frame", bevel=0.03)
    A.cur = "Emissive"
    A.box((1.6, 0.12, 0.02), at=(Lx / 2 + 0.55, 0, Hh - 0.01), mat="h_warm_panel", bevel=0.0)
    A.cur = "Body"
    # signal post at the lane side (+X)
    A.cyl(0.06, 2.6, at=(Lx / 2 + 0.6, Wy / 2 + 0.4, 0.25), mat="galvanized", n=10)
    A.box((0.25, 0.25, 0.55), at=(Lx / 2 + 0.6, Wy / 2 + 0.4, 2.95), mat="powder_black", bevel=0.02)
    A.cur = "Emissive"
    A.sphere(0.07, at=(Lx / 2 + 0.73, Wy / 2 + 0.4, 3.08), mat="h_signal_red", seg=10, rings=6)
    A.sphere(0.07, at=(Lx / 2 + 0.73, Wy / 2 + 0.4, 2.85), mat="h_signal_green", seg=10, rings=6, scale=(0.4, 1, 1))
    A.cur = "Body"
    f = font()
    if f:
        A.box((0.05, 2.0, 0.42), at=(Lx / 2 + 1.12, 0, Hh + 0.15), mat="h_hazard", bevel=0.01)
        A.text("GATE 3  -  SALTMARSH", f, 0.24, 0.01, at=(Lx / 2 + 1.15, 0, Hh + 0.02), rot=(90, 0, 90), mat="h_frame")
    A.point("Light", (Lx / 2 + 0.6, 0, Hh - 0.1))
    A.layout = {"Core": [[-230, -170], [230, 170]], "Cover": True}
    A.view = (1.0, -0.8, 0.3)
    A.lens = 40


def make_images():
    """No decal images in this kit (stencils are modelled text)."""
    return None
