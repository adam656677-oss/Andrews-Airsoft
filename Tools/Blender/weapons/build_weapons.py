"""
Procedural airsoft weapons + attachments for Andrew's Airsoft (Unreal Engine 5).

    python Tools/Blender/weapons/build_weapons.py                  # everything, 4K textures
    python Tools/Blender/weapons/build_weapons.py -- --res 1024    # quick preview bake
    python Tools/Blender/weapons/build_weapons.py -- M4 G17        # only some assets
    flags: --res 4096|2048|1024, --no-bake, --no-render, --preview (small quick renders),
           --lineup (force lineup renders on a partial run), --lineups-only,
           --each (one child process per asset, then the lineups; low memory)

Outputs (see Tools/Blender/CONVENTIONS.md):
    SourceAssets/Weapons/<ID>/SM_<ID>_<Piece>.fbx + T_<ID>_<Piece>_{BC,N,ORM,M}.png
    SourceAssets/Attachments/<ID>/...
    Content/Airsoft/Data/Weapons.json, Content/Airsoft/Data/Attachments.json
    Docs/Renders/Weapons/<ID>.png + _Lineup_4K.png, Docs/Renders/Attachments/...

How it works
    Every asset is modelled procedurally in "design space" (forward = +Y, up = +Z,
    right = +X, 1 design unit = DESIGN_SCALE metres, pistol-grip centre at the origin);
    that is the space the original Roblox generator used, so all the hand-tuned
    profiles carry over.  Parts are merged into pieces (Body / Mag / Slide / Bolt /
    Pump / Glass) whose material slots are bake "zones" (anodised receiver, polymer
    furniture, steel pins, wood, team tape ...).  Each piece is UV-unwrapped and baked
    (common/bakekit.py), then transformed to the Unreal convention (barrel +X, up +Z,
    right -Y, metres; origin stays at the asset origin) and exported as its own FBX.
"""

import math
import os
import sys
import time
import zlib
from collections import OrderedDict

import bpy  # noqa: I001  (bpy must be imported before bmesh)
import bmesh
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))

import bakekit as bk  # noqa: E402
import meshkit  # noqa: E402
import studio  # noqa: E402
from meshkit import *  # noqa: E402,F401,F403
from meshkit import QUALITY, WORK  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SOURCE_DIR = os.path.join(ROOT, "SourceAssets")
DATA_DIR = os.path.join(ROOT, "Content", "Airsoft", "Data")
RENDER_DIR = os.path.join(ROOT, "Docs", "Renders")

# design units -> metres.  Rifles were designed relative to an M4 of 4.445 units
# (real M4A1, stock extended: 0.838 m); pistols relative to a 1.3 unit Glock 17 (0.202 m).
RIFLE_SCALE = 0.838 / 4.445
PISTOL_SCALE = 0.202 / 1.3
TRI_LIMIT_GLASS = 5000

V = Vector

# --------------------------------------------------------------------------------------
# Palette (preview colours for tinted zones = default finish)
# --------------------------------------------------------------------------------------

PALETTE = {
    "polymer": (0.022, 0.022, 0.024),
    "polymer_dark": (0.012, 0.012, 0.013),
    "grip": (0.02, 0.02, 0.022),
    "anodized": (0.026, 0.026, 0.028),
    "anod_od": (0.07, 0.08, 0.045),
    "gunmetal": (0.055, 0.058, 0.062),
    "steel": (0.3, 0.3, 0.31),
    "parkerized": (0.055, 0.06, 0.056),
    "fde": (0.25, 0.18, 0.105),
    "od": (0.085, 0.09, 0.05),
    "wood": (0.15, 0.06, 0.022),
    "wood_light": (0.24, 0.11, 0.045),
    "plum": (0.11, 0.035, 0.03),
    "tape": (0.62, 0.62, 0.6),
    "rubber": (0.015, 0.015, 0.015),
    "glass": (0.05, 0.12, 0.14),
    "reticle": (1.0, 0.05, 0.03),
    "chrome": (0.55, 0.56, 0.58),
    "smoke": (0.085, 0.08, 0.068),
    "aluminium": (0.5, 0.5, 0.52),
    "brass": (0.55, 0.38, 0.12),
    "emitter": (0.02, 0.02, 0.025),
}

# design "parts groups" -> exported piece
PIECE_OF_GROUP = {
    "Body": "Body",
    "Furniture": "Body",
    "Metal": "Body",
    "Wood": "Body",
    "Tape": "Body",
    "Grip": "Body",
    "Rubber": "Body",
    "Mag": "Mag",
    "Slide": "Slide",
    "Pump": "Pump",
    "Bolt": "Bolt",
    "Glass": "Glass",
    "Reticle": "Reticle",
    "PumpTape": "Pump",
}
PIECE_ORDER = ["Body", "Mag", "Slide", "Bolt", "Pump", "Glass", "Reticle"]
KIND_OF_PIECE = {"Body": "Body", "Mag": "Mag", "Slide": "Slide", "Bolt": "Bolt", "Pump": "Pump", "Glass": "Glass", "Reticle": "Static"}
UNBAKED = {"Glass", "Reticle"}


class Gun:
    def __init__(self, gid, kind):
        self.id = gid
        self.kind = kind  # "Primary" | "Secondary" | "Throwable" | "Attachment"
        self.parts = OrderedDict()
        self.mats = {
            "Body": "anodized",
            "Furniture": "polymer",
            "Metal": "gunmetal",
            "Wood": "wood",
            "Mag": "polymer",
            "Slide": "gunmetal",
            "Pump": "wood",
            "Bolt": "steel",
            "Tape": "tape",
            "Grip": "grip",
            "Rubber": "rubber",
            "PumpTape": "tape",
            "Glass": "glass",
            "Reticle": "reticle",
        }
        # tint role of each group (P/S/A); None = real colour
        self.tints = {"Body": "P", "Furniture": "S", "Tape": "A", "Slide": "P", "PumpTape": "A"}
        self.points = OrderedDict()
        self.roles = {}  # legacy (Roblox) role names; unused
        self.scale = RIFLE_SCALE if kind in ("Primary", "Attachment") else PISTOL_SCALE
        self.edge_radius = 0.006
        self.category = "Attachments" if kind == "Attachment" else "Weapons"

    def add(self, group, *objs):
        for o in objs:
            if isinstance(o, (list, tuple)):
                self.add(group, *o)
            elif o is not None:
                self.parts.setdefault(group, []).append(o)
        return objs[0] if len(objs) == 1 else objs

    def body(self, *o):
        return self.add("Body", *o)

    def furn(self, *o):
        return self.add("Furniture", *o)

    def metal(self, *o):
        return self.add("Metal", *o)

    def wood(self, *o):
        return self.add("Wood", *o)

    def mag(self, *o):
        return self.add("Mag", *o)

    def tape(self, *o):
        return self.add("Tape", *o)

    def finish(self):
        """Merge groups into pieces.  Each group becomes a material slot (bake zone).
        Returns [(piece_name, object, zones)] with zones = [(recipe, role)]."""
        pieces = OrderedDict()
        for group, objs in self.parts.items():
            piece = PIECE_OF_GROUP.get(group, group)
            pieces.setdefault(piece, []).append((group, objs))
        out = []
        for piece in PIECE_ORDER + [p for p in pieces if p not in PIECE_ORDER]:
            if piece not in pieces:
                continue
            bm = bmesh.new()
            zones = []
            for zi, (group, objs) in enumerate(pieces[piece]):
                recipe = self.mats[group]
                zones.append((recipe, self.tints.get(group)))
                for o in objs:
                    me = o.data.copy()
                    me.transform(o.matrix_world)
                    n0 = len(bm.faces)
                    bm.from_mesh(me)
                    bm.faces.ensure_lookup_table()
                    for f in bm.faces[n0:]:
                        f.material_index = zi
                    bpy.data.meshes.remove(me)
                for o in objs:
                    delete(o)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
            bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
            # triangulate now so the baked tangent space matches the exported FBX exactly
            bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
            me = bpy.data.meshes.new(f"SM_{self.id}_{piece}")
            bm.to_mesh(me)
            bm.free()
            me.validate(clean_customdata=False)
            ob = bpy.data.objects.new(piece, me)
            WORK["coll"].objects.link(ob)
            for zi, z in enumerate(zones):
                me.materials.append(bpy.data.materials.get(f"__zone_{zi}") or bpy.data.materials.new(f"__zone_{zi}"))
            for p in me.polygons:
                p.use_smooth = True
            me.set_sharp_from_angle(angle=math.radians(32))
            out.append((piece, ob, zones))
        return out

    def to_unreal(self, ob):
        ob.data.transform(self.design_matrix())
        ob.data.update()

    def design_matrix(self):
        """design space (Y fwd, X right, units) -> Blender-for-Unreal (X fwd, -Y right, metres)."""
        return Matrix.Scale(self.scale, 4) @ Matrix.Rotation(math.radians(-90), 4, "Z")

    def point_ue(self, p):
        """Design-space point -> Unreal cm (x fwd, y right, z up)."""
        q = self.design_matrix() @ V(p)
        return [round(q.x * 100, 1) + 0.0, round(-q.y * 100, 1) + 0.0, round(q.z * 100, 1) + 0.0]


def tri_count(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


# --------------------------------------------------------------------------------------
# Shared sub-assemblies
# --------------------------------------------------------------------------------------


def picatinny(y0, y1, z, w=0.118, h=0.058, pitch=0.053, x=0.0, axis="top", slots=True):
    """Picatinny rail, base at height z (top rail). axis='side_r'/'side_l'/'bottom' rotate it."""
    hw = w / 2
    prof = [
        (x - hw * 0.8, z),
        (x + hw * 0.8, z),
        (x + hw * 0.8, z + h * 0.35),
        (x + hw * 1.12, z + h * 0.62),
        (x + hw * 0.92, z + h),
        (x - hw * 0.92, z + h),
        (x - hw * 1.12, z + h * 0.62),
        (x - hw * 0.8, z + h * 0.35),
    ]
    rail = section(prof, y0, y1, bev=0.004)
    if slots:
        cs = []
        n = int((y1 - y0 - 0.03) / pitch)
        start = (y0 + y1) / 2 - (n - 1) * pitch / 2
        for i in range(n):
            yy = start + i * pitch
            cs.append(box((x, yy, z + h * 0.78), (w * 1.6, pitch * 0.48, h * 0.6), bev=0))
        cut(rail, cs)
    return rail


def orient(ob, kind, pivot):
    """Rotate a top-built part around the bore so it faces side/bottom."""
    if kind == "side_r":
        rotate(ob, 90, "Y", pivot)
    elif kind == "side_l":
        rotate(ob, -90, "Y", pivot)
    elif kind == "bottom":
        rotate(ob, 180, "Y", pivot)
    return ob


def grip_profile(top, bot, d_top, d_bot, nub=0.0, swell=0.012, beaver=0.0, n=10, waves=0):
    """Pistol-grip side profile between top centre and bottom centre (y, z)."""
    n = int(round(n * QUALITY["seg"]))
    top, bot = V(top), V(bot)
    a = bot - top
    L = a.length
    a.normalize()
    nf = V((-a.y, a.x))  # forward normal
    if nf.x < 0:
        nf = -nf
    front, rear = [], []
    for i in range(n + 1):
        t = i / n
        d = d_top + (d_bot - d_top) * t
        f = d / 2
        if nub and waves:
            if 0.12 < t < 0.92:
                f += nub * abs(math.sin(waves * math.pi * (t - 0.12) / 0.8))
        elif nub and 0.3 < t < 0.75:
            f += nub * math.sin(math.pi * (t - 0.3) / 0.45)
        r = d / 2 + swell * math.sin(math.pi * t)
        c = top + a * L * t
        front.append(tuple(c + nf * f))
        rear.append(tuple(c - nf * r))
    c = top + a * L
    dbot = d_bot / 2
    bottom = []
    for i in range(1, 6):
        s = i / 6
        p = c + nf * (dbot * (1 - 2 * s)) + a * (0.025 * math.sin(math.pi * s))
        bottom.append(tuple(p))
    pts = front + bottom + list(reversed(rear))
    if beaver:
        r0 = top - nf * (d_top / 2)
        pts.append((r0.x - beaver, r0.y + 0.01))
        pts.append((r0.x - beaver * 0.6, r0.y + 0.04))
    return pts, nf, a, L


def grip_texture(top, a, nf, L, w, d, t0=0.25, t1=0.85, n=7, depth=0.006, groove=0.012):
    """Side grooves across a pistol grip -> list of cutters."""
    top, a, nf = V(top), V(a), V(nf)
    cs = []
    for i in range(n):
        t = t0 + (t1 - t0) * i / max(1, n - 1)
        c = top + a * L * t
        ang = math.degrees(math.atan2(a.x, -a.y))  # tilt of grip axis from vertical (in y,z)
        for sx in (-1, 1):
            b = box((sx * (w / 2 + 0.03 - depth), c.x - nf.x * 0.0, c.y), (0.06, d * 1.3, groove), bev=0)
            rotate(b, ang, "X", (0, c.x, c.y))
            cs.append(b)
    return cs


def curved_mag(top, length, depth, width, bend_deg, n=10, lip=0.0, bev=0.012):
    """Curved box magazine side profile, top centre at `top` (y,z), going down and
    curving forward by bend_deg over its length. Returns (pts, centreline)."""
    n = int(round(n * QUALITY["seg"]))
    y0, z0 = top
    front, rear, cl = [], [], []
    for i in range(n + 1):
        t = i / n
        ang = math.radians(bend_deg * t)
        # integrate centreline (arc)
        if abs(bend_deg) < 1e-3:
            cy, cz = y0, z0 - length * t
        else:
            R = length / math.radians(bend_deg)
            cy = y0 + R * (1 - math.cos(ang))
            cz = z0 - R * math.sin(ang)
        tan = V((math.sin(ang), -math.cos(ang)))
        nf = V((-tan.y, tan.x))  # forward
        if nf.x < 0:
            nf = -nf
        c = V((cy, cz))
        cl.append((c, tan, nf))
        front.append(tuple(c + nf * depth / 2))
        rear.append(tuple(c - nf * depth / 2))
    pts = front + list(reversed(rear))
    return pts, cl


def mag_segment(cl, depth, width, t0, t1, extra=0.012, x=0.0, bev=0.006):
    """A band of a curved mag (ribs / base plate) between fractions t0..t1."""
    n = len(cl) - 1

    def at(t):
        f = t * n
        i = min(int(f), n - 1)
        k = f - i
        c = cl[i][0].lerp(cl[i + 1][0], k)
        nf = cl[i][2].lerp(cl[i + 1][2], k).normalized()
        return c, nf

    c0, n0 = at(t0)
    c1, n1 = at(t1)
    d = depth / 2 + extra
    pts = [tuple(c0 + n0 * d), tuple(c1 + n1 * d), tuple(c1 - n1 * d), tuple(c0 - n0 * d)]
    return side(pts, width + 2 * extra, x, bev=bev)


def trigger(y, z, h=0.11, w=0.035, curl=0.03, thick=0.022):
    pts = bezier((y, z), (y + 0.005, z - h * 0.45), (y + curl * 0.6, z - h * 0.85), (y + curl + 0.02, z - h), n=6)
    return bar(pts, thick, w, bev=0.006)


def ring_cut_y(y, r_in, r_out, w):
    """Annular groove cutter around the Y axis (for barrels / suppressors)."""
    return tube((0, y - w / 2, 0), (0, y + w / 2, 0), r_out, r_in, seg=20)


# --------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------

BUILDERS = OrderedDict()


def register(gid, kind):
    def deco(fn):
        BUILDERS[gid] = (kind, fn)
        return fn

    return deco


# ======================================================================================
# PRIMARIES
# ======================================================================================

BORE = 0.5  # rifle bore height


def ar_lower(g, y_rear=-0.34, y_front=0.95, w=0.165, mw_front=0.9, mw_rear=0.5, mw_bot=0.06, top=0.42):
    """AR-15 style lower receiver incl. magwell, trigger guard and pistol grip."""
    pts = [
        (y_rear, top),
        (y_front, top),
        (y_front, top - 0.06),
        (mw_front + 0.02, top - 0.07),
        (mw_front, mw_bot + 0.05),
        (mw_front - 0.03, mw_bot),
        (mw_rear + 0.02, mw_bot),
        (mw_rear, mw_bot + 0.04),
        (mw_rear - 0.02, 0.25),
        (0.12, 0.25),
        (-0.06, 0.26),
        (-0.2, 0.28),
        (y_rear + 0.04, 0.31),
        (y_rear, 0.35),
    ]
    lower = side(pts, w, bev=0.012)
    # magwell opening and side recesses
    lower = cut(
        lower,
        box(((0, (mw_front + mw_rear) / 2 - 0.005, mw_bot + 0.01)), (w - 0.05, mw_front - mw_rear - 0.06, 0.08), bev=0),
        box((w / 2 + 0.01, (mw_front + mw_rear) / 2, 0.24), (0.03, 0.26, 0.2), bev=0.01),
        box((-w / 2 - 0.01, (mw_front + mw_rear) / 2, 0.24), (0.03, 0.26, 0.2), bev=0.01),
    )
    g.body(lower)
    g.body(side([(mw_rear - 0.015, mw_bot + 0.07), (mw_front + 0.012, mw_bot + 0.07), (mw_front - 0.01, mw_bot - 0.005), (mw_rear + 0.0, mw_bot - 0.005)], w + 0.024, bev=0.01))
    # pivot / takedown pins
    for yy in (y_front - 0.04, y_rear + 0.12):
        g.metal(cyl_x(-w / 2 - 0.008, w / 2 + 0.008, 0.022, y=yy, z=top - 0.03, seg=12))
    # trigger guard
    g.body(bar([(0.12, 0.27), (0.13, 0.15), (0.2, 0.125), (mw_rear - 0.04, 0.125), (mw_rear - 0.02, 0.15), (mw_rear - 0.02, 0.24)], 0.03, 0.08, bev=0.008))
    g.metal(trigger(0.25, 0.28))
    # selector, mag release
    g.metal(cyl_x(-w / 2 - 0.02, -w / 2, 0.03, y=0.02, z=0.36, seg=12))
    g.metal(box((-w / 2 - 0.025, 0.02, 0.36), (0.012, 0.09, 0.02), bev=0.004))
    g.metal(cyl_x(w / 2, w / 2 + 0.015, 0.025, y=mw_rear + 0.05, z=0.32, seg=12))
    # bolt catch paddle
    g.metal(side([(mw_rear - 0.07, 0.4), (mw_rear + 0.02, 0.4), (mw_rear + 0.03, 0.33), (mw_rear - 0.01, 0.31), (mw_rear - 0.06, 0.35)], 0.014, x=-w / 2 - 0.006, bev=0.004))
    # mag release fence (raised half ring around the button)
    fence = tube((w / 2 - 0.004, mw_rear + 0.05, 0.32), (w / 2 + 0.014, mw_rear + 0.05, 0.32), 0.05, 0.036, seg=20)
    cut(fence, box((w / 2, mw_rear + 0.05, 0.25), (0.1, 0.2, 0.1), bev=0))
    g.body(fence)
    # trigger guard roll pin + lower receiver part line
    g.metal(cyl_x(-0.045, 0.045, 0.008, y=mw_rear - 0.03, z=0.2, seg=10))
    ar_details(g, y_rear=y_rear, w_low=w)


def ar_grip(g, piece="Furniture"):
    pts, nf, a, L = grip_profile((0.1, 0.27), (-0.09, -0.27), 0.2, 0.22, nub=0.02, beaver=0.06)
    grip = side(pts, 0.15, bev=0.03, seg=2)
    cut(grip, grip_texture((0.1, 0.27), a, nf, L, 0.15, 0.22, n=8))
    g.add(piece, grip)


def ar_upper(g, y_rear=-0.34, y_front=0.95, w=0.175, top=0.62, bot=0.42, port=(0.05, 0.42)):
    up = side([(y_rear, bot), (y_rear, top - 0.04), (y_rear + 0.04, top), (y_front, top), (y_front, bot)], w, bev=0)
    sec = [(-w / 2, bot), (w / 2, bot), (w / 2, top - 0.055), (w / 2 - 0.04, top), (-w / 2 + 0.04, top), (-w / 2, top - 0.055)]
    intersect(up, section(sec, y_rear - 0.1, y_front + 0.1, bev=0))
    bevel(up, 0.012, 2)
    port_c = box((w / 2, (port[0] + port[1]) / 2, BORE + 0.01), (0.07, port[1] - port[0], 0.1), bev=0.008)
    cs = [port_c]
    for sx in (-1, 1):  # shallow fluting along the front of the upper
        cs.append(box((sx * w / 2, (port[1] + y_front) / 2 + 0.03, BORE + 0.03), (0.016, y_front - port[1] - 0.14, 0.03), bev=0.008))
    up = cut(up, cs)
    g.body(up)
    g.metal(box((w / 2 - 0.03, (port[0] + port[1]) / 2, BORE + 0.01), (0.03, port[1] - port[0] - 0.02, 0.08), bev=0.005))
    g.metal(cyl_x(w / 2 - 0.03, w / 2 - 0.012, 0.022, y=(port[0] + port[1]) / 2 + 0.06, z=BORE + 0.01, seg=10))
    dc = section([(w / 2 + 0.004, BORE - 0.1), (w / 2 + 0.016, BORE - 0.1), (w / 2 + 0.02, BORE - 0.06), (w / 2 + 0.014, BORE - 0.035), (w / 2 + 0.004, BORE - 0.035)], port[0] - 0.01, port[1] + 0.01, bev=0.003)
    cut(dc, [box((w / 2 + 0.022, (port[0] + port[1]) / 2, BORE - 0.06 + dz), (0.01, port[1] - port[0] - 0.06, 0.008), bev=0) for dz in (-0.018, 0.0)])
    g.body(dc)
    g.metal(cyl_y(port[0] - 0.02, port[1] + 0.02, 0.008, x=w / 2 + 0.008, z=BORE - 0.1, seg=10))
    g.metal(box((w / 2 + 0.02, port[0] + 0.06, BORE - 0.055), (0.012, 0.03, 0.022), bev=0.004))
    g.body(side([(port[0] - 0.12, BORE + 0.08), (port[0] - 0.01, BORE + 0.08), (port[0] - 0.01, BORE - 0.02), (port[0] - 0.05, BORE - 0.02)], 0.05, x=w / 2 + 0.01, bev=0.008))
    g.body(cyl((w / 2 - 0.02, -0.02, BORE + 0.04), (w / 2 + 0.03, -0.26, BORE + 0.04), 0.038, seg=16, bev=0.006))
    fa = cyl((w / 2 + 0.035, -0.29, BORE + 0.04), (w / 2 + 0.02, -0.24, BORE + 0.04), 0.03, seg=16, bev=0.006)
    cut(fa, [tube((w / 2 + 0.034 - k * 0.003, -0.283 + k * 0.01, BORE + 0.04), (w / 2 + 0.033 - k * 0.003, -0.279 + k * 0.01, BORE + 0.04), 0.04, 0.027, seg=16) for k in range(3)])
    g.metal(fa)
    g.metal(box((0, y_rear - 0.03, top - 0.03), (0.08, 0.1, 0.035), bev=0.008))
    g.metal(box((0, y_rear - 0.06, top - 0.03), (0.2, 0.035, 0.035), bev=0.01, seg=2))
    return up


def buffer_tube(g, y0, y1, z=0.52, r=0.07, piece="Metal"):
    t = lathe((0, y0, z), (0, -1, 0), [(0, 0), (0, r * 1.25), (0.04, r * 1.25), (0.04, r), (y0 - y1, r), (y0 - y1, 0)], seg=24, bev=0.006)
    g.add(piece, t)
    # castle nut notches
    return t


def m4_stock(g, y_back=-1.4, z_tube=0.52, piece="Furniture"):
    """CTR-style collapsible stock: tube housing, open triangular brace, tall butt."""
    z = z_tube
    yb = y_back
    pts = [
        (yb, z + 0.16), (yb + 0.32, z + 0.15), (-0.86, z + 0.11), (-0.64, z + 0.1), (-0.62, z + 0.07),
        (-0.62, z - 0.08), (-0.66, z - 0.1), (-0.8, z - 0.11), (yb + 0.13, 0.04), (yb + 0.1, 0.0), (yb, 0.0),
    ]
    st = side(pts, 0.16, bev=0.0)
    win = [(yb + 0.12, z - 0.12), (-0.93, z - 0.12), (yb + 0.12, 0.14)]
    st = cut(st, side(win, 0.4, bev=0))
    # lightening pocket on the tube housing
    cut(st, [side(rrect(-0.95 + (yb + 0.95) * 0.35, z + 0.03, 0.26, 0.07, 0.03), 0.03, x=sx * 0.08, bev=0) for sx in (-1, 1)])
    bevel(st, 0.02, 2)
    g.add(piece, st)
    g.add(piece, side([(yb - 0.035, z + 0.165), (yb + 0.005, z + 0.165), (yb + 0.005, -0.005), (yb - 0.035, -0.005)], 0.17, bev=0.014, seg=2))
    g.metal(box((0, -0.82, z - 0.115), (0.04, 0.18, 0.03), bev=0.008))
    g.metal(cyl_x(-0.09, 0.09, 0.02, y=yb + 0.06, z=z + 0.02, seg=10))


def mlok_handguard(g, y0, y1, cz=BORE - 0.01, w=0.25, h=0.27, ch=0.06, slot_ys=None, piece="Body", tape_at=None):
    oct_pts = octagon(0, cz, w, h, ch)
    hg = section(oct_pts, y0, y1, bev=0.01)
    if slot_ys is None:
        slot_ys = []
        n = int((y1 - y0 - 0.12) / 0.24)
        for i in range(n):
            slot_ys.append(y0 + 0.16 + i * 0.24)
    cs = []
    for yy in slot_ys:
        for sx in (-1, 1):
            cs.append(stadium_cutter((sx * w / 2, yy, cz), 0.16, 0.042, 0.05, normal="x"))
            d = stadium_cutter((0, yy, 0), 0.12, 0.04, 0.05, normal="z")
            # diagonal faces
            rotate(d, sx * -45, "Y")
            k = (w / 2 - ch / 2) * 0.98
            move(d, (sx * (w / 2 - ch / 2), 0, cz - h / 2 + ch / 2))
            cs.append(d)
        cs.append(stadium_cutter((0, yy, cz - h / 2), 0.16, 0.042, 0.05, normal="z"))
    cut(hg, cs)
    g.add(piece, hg)
    # end cap ring
    g.add(piece, section(octagon(0, cz, w + 0.012, h + 0.012, ch), y1 - 0.03, y1, bev=0.006))
    if tape_at:
        ty0, ty1 = tape_at
        g.tape(section(octagon(0, cz, w + 0.014, h + 0.014, ch + 0.004), ty0, ty1, bev=0.004))
    return hg


def ar_rear_sight(g, y, z):
    g.metal(box((0, y, z + 0.02), (0.13, 0.13, 0.04), bev=0.008))
    g.metal(side([(y - 0.05, z + 0.03), (y + 0.04, z + 0.03), (y + 0.0, z + 0.15), (y - 0.04, z + 0.15)], 0.11, bev=0.008))
    ring = cyl_x(-0.03, 0.03, 0.035, y=y - 0.02, z=z + 0.15, seg=16)
    cut(ring, cyl_x(-0.1, 0.1, 0.014, y=y - 0.02, z=z + 0.15, seg=10))
    g.metal(ring)


def ar_front_sight(g, y, z, flip=True):
    g.metal(box((0, y, z + 0.02), (0.13, 0.12, 0.04), bev=0.008))
    wing = side([(y - 0.05, z + 0.03), (y + 0.05, z + 0.03), (y + 0.02, z + 0.2), (y - 0.02, z + 0.2)], 0.1, bev=0.008)
    cut(wing, side([(y - 0.04, z + 0.09), (y + 0.04, z + 0.09), (y + 0.02, z + 0.18), (y - 0.02, z + 0.18)], 0.05, bev=0))
    g.metal(wing)
    g.metal(cyl_z(z + 0.08, z + 0.17, 0.008, y=y, seg=8))


def birdcage(g, y0, length=0.15, r=0.042, z=BORE):
    fh = cyl_y(y0, y0 + length, r, z=z, seg=20, bev=0.006)
    cs = []
    for a in (-90, -45, 0, 45, 90):
        s = box((0, y0 + length * 0.6, z + r), (0.018, length * 0.62, 0.05), bev=0)
        rotate(s, a, "Y", (0, 0, z))
        cs.append(s)
    cut(fh, cs)
    cut(fh, cyl_y(y0 + length * 0.35, y0 + length + 0.01, r * 0.62, z=z, seg=14))
    g.metal(fh)
    return fh


def pmag(g, top, length=0.95, depth=0.36, width=0.13, bend=14, piece="Mag"):
    pts, cl = curved_mag(top, length, depth, width, bend, n=10)
    body = side(pts, width, bev=0.014, seg=2)
    g.add(piece, body)
    # texture ribs, base plate
    for t0, t1 in ((0.52, 0.56), (0.6, 0.64), (0.68, 0.72)):
        g.add(piece, mag_segment(cl, depth, width, t0, t1, extra=0.006))
    g.add(piece, mag_segment(cl, depth, width, 0.95, 1.02, extra=0.014, bev=0.01))
    g.add(piece, mag_segment(cl, depth, width, 0.2, 0.26, extra=0.004))
    return cl


def straight_mag(g, top, length, depth, width, tilt=0.0, piece="Mag", base=0.016, ribs=(), bev=0.01):
    """Straight box magazine hanging from `top` (y,z), tilted by `tilt` deg (positive = bottom forward)."""
    pts, cl = curved_mag(top, length, depth, width, 0.001, n=2)
    parts = [side(pts, width, bev=bev, seg=2)]
    parts.append(mag_segment(cl, depth, width, 0.97, 1.0 + base / length, extra=0.012, bev=0.008))
    for t0, t1 in ribs:
        parts.append(mag_segment(cl, depth, width, t0, t1, extra=0.005))
    if tilt:
        for p_ in parts:
            rotate(p_, tilt, "X", (0, top[0], top[1]))
    g.add(piece, parts)
    return parts


def rounded_section(w, z0, z1, r, cx=0.0, n=4):
    return rrect(cx, (z0 + z1) / 2, w, z1 - z0, r, n)


def muzzle_brake_ak(g, y0, length=0.3, r=0.044, z=BORE):
    br = cyl_y(y0, y0 + length, r, z=z, seg=20, bev=0.006)
    cs = [cyl_y(y0 + length * 0.3, y0 + length + 0.02, r * 0.55, z=z, seg=14)]
    # two big side windows and a front notch
    for sx in (-1, 1):
        cs.append(box((sx * r, y0 + length * 0.55, z), (r * 1.2, length * 0.22, r * 1.1), bev=0))
    cs.append(box((0, y0 + length * 0.92, z - r), (r * 0.9, length * 0.2, r * 1.0), bev=0))
    for i in range(3):
        cs.append(cyl_z(z, z + r * 2, 0.008, y=y0 + length * (0.25 + 0.12 * i), x=0.0, seg=8))
    cut(br, cs)
    g.metal(br)


def ported_brake(g, y0, length=0.18, r=0.05, z=BORE):
    br = cyl_y(y0, y0 + length, r, z=z, seg=16, bev=0.008, rot=math.pi / 16)
    cs = [cyl_y(y0 + 0.02, y0 + length + 0.02, r * 0.5, z=z, seg=12)]
    for i in range(3):
        cs.append(box((0, y0 + 0.04 + i * (length - 0.06) / 2.6, z), (r * 3, 0.026, r * 0.9), bev=0))
    cut(br, cs)
    g.metal(br)


# --------------------------------------------------------------------------------------
# M4A1
# --------------------------------------------------------------------------------------


@register("M4", "Primary")
def build_m4(g):
    g.mats.update(Body="anodized", Furniture="fde", Mag="fde")
    g.roles["Mag"] = "Secondary"
    ar_lower(g)
    ar_grip(g)
    ar_upper(g)
    buffer_tube(g, -0.34, -1.2)
    m4_stock(g)
    mlok_handguard(g, 0.95, 2.48, tape_at=(1.27, 1.39))
    handguard_hardware(g, 0.95)
    g.body(picatinny(-0.34, 2.48, 0.62))
    g.metal(lathe((0, 2.48, BORE), (0, 1, 0), [(0, 0), (0, 0.04), (0.2, 0.04), (0.22, 0.034), (0.4, 0.034), (0.4, 0)], seg=20))
    birdcage(g, 2.86, 0.15)
    ar_rear_sight(g, -0.18, 0.68)
    ar_front_sight(g, 2.38, 0.68)
    pmag(g, (0.695, 0.44))
    g.points.update(
        Muzzle=(0, 3.01, BORE),
        Aim=(0, -0.18 - 0.55, 0.83),
        LeftHand=(0, 1.75, BORE - 0.145),
        Optic=(0, 0.35, 0.68),
        Underbarrel=(0, 1.8, BORE - 0.145),
        MuzzleMount=(0, 2.88, BORE),
        Side=(0.125, 2.0, BORE - 0.01),
        MagWell=(0, 0.695, 0.44),
    )


# --------------------------------------------------------------------------------------
# MP5SD
# --------------------------------------------------------------------------------------


@register("MP5", "Primary")
def build_mp5(g):
    B = 0.47
    g.mats.update(Body="anodized", Furniture="polymer", Mag="gunmetal")
    g.roles["Mag"] = "Metal"
    yr, yf = -0.55, 0.98
    # stamped receiver: flat sides, round top
    sec = [(-0.1, 0.33), (0.1, 0.33), (0.1, 0.53)] + arc(0, 0.53, 0.1, 0, 180, 10)[1:-1] + [(-0.1, 0.53)]
    rec = section(sec, yr, yf, bev=0.012, seg=2)
    cs = [box((0.12, 0.42, B + 0.0), (0.06, 0.26, 0.1), bev=0.006)]  # ejection port
    for sx in (-1, 1):  # pressed side channels
        cs.append(box((sx * 0.11, -0.05, 0.395), (0.03, 0.8, 0.025), bev=0.006))
        cs.append(box((sx * 0.11, 0.12, 0.5), (0.03, 0.42, 0.018), bev=0.006))
    cut(rec, cs)
    g.body(rec)
    g.metal(box((0.08, 0.42, B), (0.02, 0.24, 0.08), bev=0.004))
    # cocking tube front + handle (left, angled forward)
    g.body(cyl_y(yf - 0.05, yf + 0.06, 0.07, z=0.55, seg=18, bev=0.006))
    ch = cyl((-0.07, 0.86, 0.56), (-0.2, 0.93, 0.6), 0.02, seg=10, bev=0.004)
    g.metal(ch)
    g.metal(cyl((-0.2, 0.93, 0.6), (-0.215, 0.94, 0.605), 0.032, seg=12, bev=0.005))
    # end cap
    g.metal(box((0, yr - 0.02, 0.48), (0.2, 0.05, 0.3), bev=0.012, seg=2))
    # magwell
    mw = side([(0.47, 0.34), (0.83, 0.34), (0.83, 0.22), (0.8, 0.18), (0.5, 0.18), (0.47, 0.22)], 0.15, bev=0.01)
    g.body(mw)
    g.metal(side([(0.4, 0.22), (0.47, 0.22), (0.47, 0.13), (0.42, 0.13)], 0.06, bev=0.006))  # paddle release
    # trigger housing + grip (polymer "Navy" group)
    hous = side([(-0.32, 0.34), (0.47, 0.34), (0.47, 0.26), (0.42, 0.22), (0.1, 0.22), (-0.32, 0.26)], 0.17, bev=0.014, seg=2)
    g.furn(hous)
    pts, nf, a, L = grip_profile((0.07, 0.25), (-0.09, -0.28), 0.2, 0.215, nub=0.018, waves=3, n=24, beaver=0.0)
    grip = side(pts, 0.16, bev=0.03, seg=2)
    cut(grip, grip_texture((0.07, 0.25), a, nf, L, 0.16, 0.2, n=7))
    g.furn(grip)
    g.furn(bar([(0.1, 0.24), (0.12, 0.08), (0.2, 0.05), (0.38, 0.05), (0.44, 0.1), (0.45, 0.22)], 0.028, 0.08, bev=0.007))
    g.metal(trigger(0.24, 0.23, h=0.1))
    for yy in (-0.24, 0.38):
        g.metal(cyl_x(-0.1, 0.1, 0.02, y=yy, z=0.3, seg=10))
    g.metal(box((-0.092, -0.12, 0.29), (0.012, 0.12, 0.03), bev=0.004))  # selector
    # suppressor
    sup = lathe((0, yf, B), (0, 1, 0), [(0, 0), (0, 0.07), (0.05, 0.1), (1.56, 0.1), (1.6, 0.085), (1.6, 0.03), (1.58, 0.0)], seg=24, bev=0.008)
    cut(sup, [tube((0, yf + y, B), (0, yf + y + 0.014, B), 0.12, 0.094, seg=24) for y in (0.75, 0.8, 0.85, 1.4)])
    g.metal(sup)
    # SD handguard (open-top shell around the rear of the suppressor)
    hg = tube((0, 1.0, B), (0, 1.66, B), 0.135, 0.1, seg=24)
    hg = cut(hg, box((0, 1.33, B + 0.1), (0.4, 0.8, 0.16), bev=0))
    cut(hg, [box((sx * 0.135, 1.33, B - 0.03 + dz), (0.03, 0.48, 0.022), bev=0.01) for sx in (-1, 1) for dz in (0.0, -0.05)])
    bevel(hg, 0.008, 1)
    g.furn(hg)
    tp = tube((0, 1.5, B), (0, 1.6, B), 0.14, 0.125, seg=24)
    g.tape(cut(tp, box((0, 1.55, B + 0.1), (0.4, 0.2, 0.16), bev=0)))
    # A2 fixed stock
    st = side([(yr, 0.36), (yr, 0.6), (-0.8, 0.6), (-1.4, 0.57), (-1.5, 0.6), (-1.56, 0.6), (-1.56, 0.06), (-1.5, 0.03), (-1.42, 0.05), (-1.2, 0.2), (-0.8, 0.33), (-0.62, 0.35)], 0.15, bev=0.035, seg=2)
    cut(st, side([(-1.42, 0.24), (-1.42, 0.49), (-0.95, 0.5), (-1.2, 0.33)], 0.4, bev=0))
    g.furn(st)
    g.furn(side([(-1.6, 0.61), (-1.555, 0.61), (-1.555, 0.05), (-1.6, 0.05)], 0.16, bev=0.014, seg=2))
    # rear drum sight + hooded front sight
    g.metal(box((0, -0.36, 0.64), (0.12, 0.14, 0.04), bev=0.008))
    drum = cyl_x(-0.055, 0.055, 0.06, y=-0.36, z=0.72, seg=8)
    cut(drum, cyl((0, -0.5, 0.75), (0, -0.2, 0.75), 0.012, seg=8))
    g.metal(drum)
    g.metal(side([(0.82, 0.62), (0.94, 0.62), (0.92, 0.68), (0.84, 0.68)], 0.06, bev=0.006))
    hood = tube((0, 0.83, 0.74), (0, 0.93, 0.74), 0.06, 0.048, seg=16)
    g.metal(hood)
    g.metal(cyl_z(0.66, 0.75, 0.007, y=0.88, seg=8))
    # claw mount with short rail
    g.metal(section([(-0.075, 0.6), (0.075, 0.6), (0.06, 0.64), (-0.06, 0.64)], -0.12, 0.42, bev=0.006))
    g.metal(picatinny(-0.12, 0.42, 0.635, h=0.05))
    for yy in (-0.08, 0.38):
        g.metal(box((0, yy, 0.6), (0.21, 0.05, 0.05), bev=0.01))
    pts, cl = curved_mag((0.65, 0.33), 0.86, 0.22, 0.1, 30, n=12)
    g.mag(side(pts, 0.1, bev=0.012, seg=2))
    for t0, t1 in ((0.18, 0.86),):
        g.mag(mag_segment(cl, 0.08, 0.1, t0, t1, extra=0.006, bev=0.004))
    g.mag(mag_segment(cl, 0.22, 0.1, 0.97, 1.03, extra=0.01))
    g.points.update(
        Muzzle=(0, yf + 1.6, B),
        Aim=(0, -0.36 - 0.55, 0.75),
        LeftHand=(0, 1.33, B - 0.135),
        Optic=(0, 0.15, 0.685),
        MagWell=(0, 0.65, 0.33),
    )


# --------------------------------------------------------------------------------------
# SR-25
# --------------------------------------------------------------------------------------


def prs_stock(g, y_back, z_tube=0.52, piece="Furniture"):
    pts = [
        (y_back, z_tube + 0.2),
        (-0.68, z_tube + 0.16),
        (-0.62, z_tube + 0.1),
        (-0.6, z_tube - 0.1),
        (-0.95, z_tube - 0.12),
        (-1.05, z_tube - 0.2),
        (y_back + 0.12, 0.05),
        (y_back, 0.0),
    ]
    st = side(pts, 0.17, bev=0.022, seg=2)
    st = cut(st, side(rrect(-0.95 + (y_back + 0.9) / 2 + 0.25, 0.26, 0.36, 0.12, 0.05), 0.4, bev=0))
    g.add(piece, st)
    g.add(piece, side([(y_back + 0.1, z_tube + 0.27), (-0.72, z_tube + 0.24), (-0.74, z_tube + 0.17), (y_back + 0.1, z_tube + 0.18)], 0.15, bev=0.025, seg=2))
    g.add(piece, side([(y_back - 0.05, z_tube + 0.22), (y_back + 0.01, z_tube + 0.22), (y_back + 0.01, -0.02), (y_back - 0.05, -0.02)], 0.18, bev=0.015, seg=2))
    for yy in (-0.95, y_back + 0.2):
        knob = cyl_x(-0.1, 0.1, 0.05, y=yy, z=z_tube + 0.12 if yy > -1 else 0.25, seg=16, bev=0.006)
        g.metal(knob)
    g.metal(cyl_z(0.04, 0.22, 0.03, y=y_back + 0.35, seg=12, bev=0.006))  # monopod


@register("SR25", "Primary")
def build_sr25(g):
    g.mats.update(Body="fde", Furniture="polymer", Mag="polymer")
    g.roles["Mag"] = "Secondary"
    ar_lower(g, y_front=0.98, mw_front=0.94, mw_rear=0.5, w=0.18)
    ar_grip(g)
    ar_upper(g, y_front=0.98, w=0.19)
    buffer_tube(g, -0.34, -1.25)
    prs_stock(g, -1.6)
    mlok_handguard(g, 0.98, 3.05, w=0.26, h=0.28, tape_at=(1.4, 1.52))
    handguard_hardware(g, 0.98, w=0.26, h=0.28)
    g.body(picatinny(-0.34, 3.05, 0.62))
    g.metal(lathe((0, 3.05, BORE), (0, 1, 0), [(0, 0), (0, 0.048), (0.3, 0.045), (0.46, 0.042), (0.46, 0)], seg=20))
    ported_brake(g, 3.5, 0.19, 0.052)
    ar_rear_sight(g, -0.18, 0.68)
    ar_front_sight(g, 2.95, 0.68)
    straight_mag(g, (0.72, 0.44), 0.62, 0.42, 0.14, tilt=4, ribs=((0.55, 0.6), (0.65, 0.7), (0.75, 0.8)))
    # bipod stud / sling QD
    g.metal(cyl_z(0.3, 0.36, 0.025, y=2.8, seg=12))
    g.points.update(
        Muzzle=(0, 3.7, BORE),
        Aim=(0, -0.18 - 0.55, 0.83),
        LeftHand=(0, 1.9, BORE - 0.15),
        Optic=(0, 0.4, 0.68),
        Underbarrel=(0, 2.2, BORE - 0.15),
        MuzzleMount=(0, 3.5, BORE),
        Side=(0.13, 2.4, BORE - 0.01),
        MagWell=(0, 0.72, 0.44),
    )


# --------------------------------------------------------------------------------------
# VSR-10
# --------------------------------------------------------------------------------------


@register("VSR", "Primary")
def build_vsr(g):
    B = 0.48
    g.mats.update(Body="od", Metal="gunmetal", Mag="polymer", Bolt="steel")
    g.roles["Mag"] = "Metal"
    # one-piece synthetic stock (this is the "frame" of a bolt gun -> Body)
    top = [(2.32, 0.4), (1.0, 0.42), (0.95, 0.44), (-0.3, 0.44), (-0.42, 0.38), (-0.58, 0.44), (-1.15, 0.5), (-1.72, 0.5)]
    butt = [(-1.75, 0.48), (-1.75, -0.16)]
    bottom = [(-1.7, -0.17), (-0.62, 0.08), (-0.38, 0.06), (-0.33, -0.08), (-0.3, -0.24), (-0.25, -0.29), (-0.12, -0.28)]
    gripf = [(-0.06, -0.2), (0.0, 0.0), (0.04, 0.14), (0.08, 0.2), (0.62, 0.21), (2.2, 0.26), (2.32, 0.3)]
    pts = top + butt + bottom + gripf
    stock = side(pts, 0.16, bev=0.04, seg=3)
    cs = []
    for sx in (-1, 1):  # forend panels + inlet
        cs.append(side(rrect(1.45, 0.32, 1.1, 0.08, 0.035), 0.03, x=sx * 0.085, bev=0))
    cs.append(side([(-0.22, 0.38), (0.9, 0.38), (0.9, 0.5), (-0.22, 0.5)], 0.13, bev=0))  # action inlet
    cs.append(side(rrect(0.25, 0.14, 0.42, 0.18, 0.06), 0.4, bev=0))  # trigger guard opening area recess
    cut(stock, cs)
    # stippled grip
    a = V((-0.12, -0.27)) - V((0.02, 0.18))
    L = a.length
    a.normalize()
    nf = V((-a.y, a.x))
    if nf.x < 0:
        nf = -nf
    cut(stock, grip_texture((0.02, 0.18), a, nf, L, 0.16, 0.24, t0=0.25, t1=0.8, n=7))
    g.body(stock)
    g.add("Furniture", side([(-1.81, 0.5), (-1.745, 0.5), (-1.745, -0.18), (-1.81, -0.18)], 0.17, bev=0.018, seg=2))
    g.mats["Furniture"] = "rubber"
    # action / barrel / suppressor
    act = lathe((0, -0.42, B), (0, 1, 0), [(0, 0), (0, 0.07), (0.03, 0.085), (1.35, 0.085), (1.37, 0.07), (1.37, 0)], seg=24, bev=0.004)
    cut(act, box((0.08, 0.32, B + 0.03), (0.08, 0.36, 0.08), bev=0.01))
    g.metal(act)
    g.metal(lathe((0, 0.95, B), (0, 1, 0), [(0, 0), (0, 0.064), (0.15, 0.058), (1.95, 0.052), (1.95, 0)], seg=20))
    sup = lathe((0, 2.9, B), (0, 1, 0), [(0, 0), (0, 0.06), (0.04, 0.088), (1.12, 0.088), (1.16, 0.075), (1.16, 0.02), (1.15, 0)], seg=24, bev=0.006)
    cut(sup, [tube((0, 2.9 + y, B), (0, 2.9 + y + 0.016, B), 0.1, 0.082, seg=24) for y in (0.12, 0.17, 0.22, 1.02)])
    g.metal(sup)
    g.metal(picatinny(-0.36, 0.9, B + 0.075, w=0.15))
    # bolt (separate for animation)
    g.add("Bolt", cyl_y(0.2, 0.46, 0.05, x=0.0, z=B + 0.02, seg=16))  # bolt body seen in port
    g.add("Bolt", lathe((0, -0.42, B), (0, -1, 0), [(0, 0), (0, 0.065), (0.12, 0.06), (0.16, 0.045), (0.16, 0)], seg=20, bev=0.004))
    g.add("Bolt", cyl((0.07, -0.18, B + 0.02), (0.22, -0.26, B - 0.1), 0.02, seg=12))
    g.add("Bolt", lathe((0.22, -0.26, B - 0.1), (0.55, -0.4, -0.6), [(0, 0), (0, 0.03), (0.02, 0.045), (0.07, 0.045), (0.09, 0.03), (0.1, 0)], seg=14))
    # trigger guard + trigger + mag
    g.metal(bar([(0.02, 0.24), (0.03, 0.08), (0.1, 0.03), (0.36, 0.03), (0.44, 0.1), (0.46, 0.22)], 0.03, 0.07, bev=0.008))
    g.metal(trigger(0.22, 0.25, h=0.11))
    for yy in (-0.02, 0.5):  # guard / action screws
        g.metal(socket_screw((0, yy, 0.06 if yy < 0.2 else 0.18), "z", -1, 0.018, 0.006))
    g.mag(box((0, 0.6, 0.27), (0.1, 0.24, 0.18), bev=0.01))
    g.mag(box((0, 0.6, 0.18), (0.12, 0.28, 0.025), bev=0.008))
    # sling studs
    for p_ in ((0, -1.45, -0.07), (0, 1.95, 0.24)):
        g.metal(cyl_z(p_[2] - 0.05, p_[2] + 0.02, 0.018, y=p_[1], seg=10))
        g.metal(tube((-0.006, p_[1], p_[2] - 0.07), (0.006, p_[1], p_[2] - 0.07), 0.035, 0.022, seg=12))
    g.tape(section(rounded_section(0.168, 0.19, 0.43, 0.06), 1.62, 1.74, bev=0.004))
    g.points.update(
        Muzzle=(0, 4.07, B),
        Aim=(0, -0.36 - 0.55, B + 0.2),
        LeftHand=(0, 1.55, 0.23),
        Optic=(0, 0.25, B + 0.135),
        Underbarrel=(0, 2.0, 0.255),
        MagWell=(0, 0.6, 0.36),
    )


# --------------------------------------------------------------------------------------
# Remington 870
# --------------------------------------------------------------------------------------


@register("M870", "Primary")
def build_m870(g):
    B = 0.25
    g.mats.update(Body="parkerized", Furniture="rubber", Wood="wood", Pump="wood")
    yr, yf = 0.15, 1.33
    side_p = [(yr, -0.04), (yr, 0.3), (yr + 0.1, 0.38), (yf, 0.38), (yf, -0.06), (0.8, -0.06), (0.75, -0.04)]
    RW = 0.17
    rec = side(side_p, RW, bev=0.0)
    intersect(rec, section(rounded_section(RW, -0.1, 0.4, 0.06), yr - 0.1, yf + 0.1, bev=0))
    bevel(rec, 0.012, 2)
    cut(rec, box((RW / 2 + 0.02, 0.8, 0.2), (0.08, 0.34, 0.13), bev=0.012), box((0, 1.02, -0.07), (0.13, 0.5, 0.06), bev=0.01))
    cut(rec, [box((sx * RW / 2, 0.75, -0.0), (0.012, 0.9, 0.01), bev=0) for sx in (-1, 1)])  # action-bar groove line
    g.body(rec)
    g.metal(box((RW / 2 - 0.03, 0.8, 0.2), (0.02, 0.32, 0.11), bev=0.004))  # bolt in port
    g.metal(cyl_x(RW / 2 - 0.04, RW / 2 - 0.02, 0.025, y=0.88, z=0.2, seg=16))  # extractor
    g.metal(box((0, 1.0, -0.035), (0.09, 0.42, 0.012), bev=0.004))  # shell lifter
    g.metal(side([(0.72, -0.1), (0.8, -0.1), (0.82, -0.06), (0.73, -0.06)], 0.012, x=-RW / 2 + 0.03, bev=0.003))  # action release
    for yy in (0.3, 0.62):
        for sx in (-1, 1):
            g.metal(pin_head((sx * (RW / 2 + 0.001), yy, 0.02), "x", sx, 0.018, 0.004))
    g.body(picatinny(yr + 0.12, yf - 0.05, 0.38, h=0.05))
    # trigger plate + guard
    g.body(side([(yr, -0.04), (0.75, -0.04), (0.72, -0.12), (yr + 0.05, -0.12)], 0.17, bev=0.01))
    g.body(bar([(0.22, -0.1), (0.24, -0.22), (0.32, -0.26), (0.56, -0.26), (0.64, -0.2), (0.66, -0.1)], 0.03, 0.08, bev=0.008))
    g.metal(trigger(0.38, -0.1, h=0.12))
    g.metal(cyl_x(-0.1, 0.1, 0.02, y=0.24, z=-0.08, seg=10))  # safety
    g.metal(cyl_x(-0.09, 0.09, 0.015, y=0.5, z=-0.05, seg=10))
    # stock
    top = [(yr + 0.01, 0.34), (0.0, 0.25), (-0.25, 0.17), (-0.55, 0.22), (-1.4, 0.27)]
    pts = top + [(-1.46, 0.28), (-1.46, -0.42), (-1.38, -0.43), (-0.45, -0.16), (-0.15, -0.12), (0.05, -0.1), (yr + 0.01, -0.05)]
    stock = side(pts, 0.16, bev=0.04, seg=3)
    a = V((-0.4, -0.17)) - V((0.05, 0.25))
    g.wood(stock)
    g.add("Furniture", side([(-1.54, 0.29), (-1.455, 0.29), (-1.455, -0.44), (-1.54, -0.44)], 0.17, bev=0.02, seg=2))
    # barrel, magazine tube, bead
    g.metal(lathe((0, yf, B), (0, 1, 0), [(0, 0), (0, 0.062), (0.12, 0.062), (0.16, 0.054), (2.17, 0.052), (2.17, 0.035), (2.16, 0)], seg=24))
    g.metal(cyl_y(yf, 3.12, 0.046, z=B - 0.112, seg=20))
    g.metal(lathe((0, 3.12, B - 0.112), (0, 1, 0), [(0, 0), (0, 0.05), (0.14, 0.05), (0.16, 0.04), (0.16, 0)], seg=20, bev=0.004))
    g.metal(side([(3.0, B - 0.16), (3.08, B - 0.16), (3.08, B + 0.03), (3.0, B + 0.03)], 0.06, bev=0.008))
    g.metal(cyl_z(B + 0.08, B + 0.11, 0.012, y=3.44, seg=10))
    # ventilated rib on the barrel
    g.metal(box((0, 2.4, B + 0.075), (0.045, 2.08, 0.016), bev=0.004))
    for k in range(17):
        g.metal(box((0, 1.42 + k * 0.12, B + 0.06), (0.03, 0.035, 0.03), bev=0.004))
    # action bars
    for sx in (-1, 1):
        g.metal(box((sx * 0.052, 1.38, B - 0.07), (0.012, 0.3, 0.035), bev=0.004))
    # pump (ribbed)
    prof = [(0, 0), (0, 0.075)]
    n = 10
    for i in range(n):
        y0 = 0.08 + i * 0.075
        prof += [(y0, 0.098), (y0 + 0.05, 0.098), (y0 + 0.06, 0.086), (y0 + 0.075, 0.086)]
    prof += [(0.86, 0.09), (0.9, 0.075), (0.9, 0)]
    pump = lathe((0, 1.43, B - 0.105), (0, 1, 0), prof, seg=20)
    scale(pump, (0.95, 1, 1.2), (0, 1.43, B - 0.105))
    g.add("Pump", pump)
    tp = lathe((0, 2.15, B - 0.105), (0, 1, 0), [(0, 0.085), (0, 0.101), (0.09, 0.101), (0.09, 0.085)], seg=20, closed=True)
    scale(tp, (0.95, 1, 1.2), (0, 1.43, B - 0.105))
    g.add("PumpTape", tp)
    g.points.update(
        Muzzle=(0, 3.5, B),
        Aim=(0, -0.45, 0.47),
        LeftHand=(0, 1.88, B - 0.105 - 0.11),
        Optic=(0, 0.75, 0.43),
        MagWell=(0, 1.02, -0.06),
    )


# --------------------------------------------------------------------------------------
# AK-74
# --------------------------------------------------------------------------------------


@register("AK74", "Primary")
def build_ak74(g):
    B = 0.48
    g.mats.update(Body="parkerized", Wood="wood", Mag="plum", Metal="gunmetal")
    g.roles["Mag"] = "Secondary"
    yr, yf = -0.48, 1.02
    rec = side([(yr, 0.3), (yr, 0.56), (yf, 0.56), (yf, 0.3)], 0.2, bev=0.008)
    cs = [box((0, 0.64, 0.3), (0.13, 0.33, 0.04), bev=0)]
    for sx in (-1, 1):  # mag-well dimples
        cs.append(box((sx * 0.105, 0.64, 0.42), (0.02, 0.14, 0.05), bev=0.01))
    cut(rec, cs)
    g.body(rec)
    # dust cover (round top), rear tang
    dc = section([(0.095, 0.55)] + arc(0, 0.56, 0.095, 0, 180, 10)[1:-1] + [(-0.095, 0.55)], yr + 0.06, yf - 0.06, bev=0.006)
    cut(dc, [box((0, y, 0.66), (0.22, 0.01, 0.03), bev=0) for y in (0.1, 0.16, 0.22)])
    g.body(dc)
    g.body(side([(yr - 0.04, 0.4), (yr + 0.08, 0.4), (yr + 0.08, 0.58), (yr, 0.58)], 0.19, bev=0.01))
    # rivets
    for p_ in ((0.88, 0.36), (0.95, 0.36), (0.88, 0.44), (-0.05, 0.34), (0.05, 0.34), (-0.3, 0.36)):
        for sx in (-1, 1):
            g.metal(cyl_x(sx * 0.1, sx * 0.106, 0.012, y=p_[0], z=p_[1], seg=8))
    # selector lever (right side) + charging handle on the bolt carrier
    g.metal(side([(-0.36, 0.555), (0.55, 0.555), (0.55, 0.5), (0.5, 0.42), (0.44, 0.42), (0.42, 0.5), (-0.36, 0.52)], 0.012, x=0.106, bev=0.003))
    g.metal(cyl_x(0.1, 0.12, 0.03, y=-0.36, z=0.535, seg=12))
    g.metal(cyl_x(0.08, 0.2, 0.018, y=0.86, z=0.53, seg=10))
    g.metal(lathe((0.2, 0.86, 0.53), (1, 0, 0), [(0, 0), (0, 0.03), (0.04, 0.03), (0.05, 0), ], seg=12))
    # trigger guard + mag catch
    g.metal(bar([(0.1, 0.31), (0.12, 0.17), (0.2, 0.14), (0.42, 0.14), (0.46, 0.2), (0.47, 0.31)], 0.022, 0.06, bev=0.005))
    g.metal(trigger(0.25, 0.31, h=0.11))
    g.metal(side([(0.47, 0.32), (0.5, 0.32), (0.5, 0.22), (0.47, 0.22)], 0.07, bev=0.006))
    # rear sight block + leaf
    g.metal(side([(yf, 0.55), (1.25, 0.55), (1.25, 0.64), (1.06, 0.67), (yf, 0.67)], 0.14, bev=0.008))
    g.metal(side([(1.04, 0.665), (1.24, 0.66), (1.24, 0.685), (1.04, 0.685)], 0.07, bev=0.004))
    # wood: stock, grip, handguards
    st = side([(yr, 0.55), (yr - 0.05, 0.55), (-1.62, 0.46), (-1.62, -0.06), (-1.54, -0.08), (yr - 0.05, 0.31), (yr, 0.31)], 0.15, bev=0.03, seg=2)
    cut(st, [side(rrect(-1.1, 0.33, 0.5, 0.07, 0.03), 0.03, x=sx * 0.076, bev=0) for sx in (-1, 1)])
    g.wood(st)
    g.metal(side([(-1.68, 0.47), (-1.615, 0.47), (-1.615, -0.08), (-1.68, -0.08)], 0.16, bev=0.012, seg=2))
    pts, nf, a, L = grip_profile((0.08, 0.3), (-0.12, -0.25), 0.17, 0.17, swell=0.01)
    grip = side(pts, 0.12, bev=0.025, seg=2)
    cut(grip, grip_texture((0.08, 0.3), a, nf, L, 0.12, 0.17, n=8))
    g.wood(grip)
    lhg = side([(yf, 0.33), (yf, 0.53), (1.86, 0.53), (1.86, 0.36), (1.8, 0.33), (1.5, 0.31), (1.2, 0.31)], 0.2, bev=0.0)
    intersect(lhg, section(rounded_section(0.2, 0.28, 0.56, 0.07), yf - 0.1, 1.95, bev=0))
    bevel(lhg, 0.012, 2)
    cut(lhg, [box((sx * 0.1, 1.45, 0.43), (0.03, 0.55, 0.035), bev=0.015) for sx in (-1, 1)])
    g.wood(lhg)
    uhg = lathe((0, 1.12, 0.65), (0, 1, 0), [(0, 0), (0, 0.055), (0.05, 0.072), (0.62, 0.072), (0.68, 0.06), (0.68, 0)], seg=20)
    scale(uhg, (1.0, 1, 0.85), (0, 1.12, 0.65))
    g.wood(uhg)
    g.tape(section(rounded_section(0.212, 0.29, 0.545, 0.075), 1.56, 1.68, bev=0.004))
    # barrel, gas block/tube, front sight, brake, cleaning rod
    g.metal(cyl_y(yf, 3.02, 0.034, z=B, seg=18))
    g.metal(side([(1.86, 0.53), (1.89, 0.53), (1.89, 0.3), (1.86, 0.3)], 0.21, bev=0.006))  # retainer
    g.metal(cyl_y(1.8, 2.06, 0.045, z=0.65, seg=16))
    g.metal(side([(2.0, 0.44), (2.18, 0.44), (2.18, 0.62), (2.14, 0.7), (2.0, 0.7)], 0.1, bev=0.01))
    fs = side([(2.68, 0.43), (2.86, 0.43), (2.86, 0.52), (2.82, 0.56), (2.82, 0.72), (2.74, 0.72), (2.74, 0.56), (2.68, 0.52)], 0.1, bev=0.008)
    cut(fs, box((0, 2.78, 0.66), (0.06, 0.2, 0.1), bev=0))
    g.metal(fs)
    g.metal(cyl_z(0.55, 0.7, 0.008, y=2.78, seg=8))
    g.metal(box((0, 2.75, 0.39), (0.05, 0.12, 0.06), bev=0.006))  # bayonet lug
    g.metal(tube((-0.004, 2.1, 0.4), (0.004, 2.1, 0.4), 0.045, 0.032, seg=16))  # front sling loop
    g.metal(tube((-0.004, -1.35, -0.02), (0.004, -1.35, -0.02), 0.04, 0.028, seg=16))  # rear sling loop
    g.metal(cyl_y(1.92, 2.98, 0.011, z=0.405, seg=8))
    muzzle_brake_ak(g, 3.02, 0.3, 0.044, B)
    # side optic rail (dovetail) on the left
    g.metal(side([(-0.1, 0.4), (0.45, 0.4), (0.45, 0.5), (-0.1, 0.5)], 0.02, x=-0.11, bev=0.004))
    # mag: built from angled segments (polygon arcs) with a centre rib
    pts, cl = curved_mag((0.64, 0.33), 0.98, 0.32, 0.11, 32, n=12)
    m = side(pts, 0.11, bev=0.012, seg=2)
    g.mag(m)
    g.mag(mag_segment(cl, 0.06, 0.11, 0.08, 0.95, extra=0.007, bev=0.004))
    g.mag(mag_segment(cl, 0.32, 0.11, 0.97, 1.02, extra=0.008))
    g.mag(mag_segment(cl, 0.32, 0.11, 0.02, 0.1, extra=0.004))
    g.mag(side([(0.8, 0.33), (0.86, 0.33), (0.85, 0.27), (0.8, 0.27)], 0.06, bev=0.006))  # front lug
    g.points.update(
        Muzzle=(0, 3.33, B),
        Aim=(0, 1.15 - 0.55, 0.72),
        LeftHand=(0, 1.5, 0.31),
        Optic=(0, 0.2, 0.69),
        MuzzleMount=(0, 3.02, B),
        MagWell=(0, 0.64, 0.33),
    )


# --------------------------------------------------------------------------------------
# KRISS Vector
# --------------------------------------------------------------------------------------


@register("VECTOR", "Primary")
def build_vector(g):
    B = 0.36
    g.mats.update(Body="fde", Furniture="polymer", Mag="polymer", Metal="gunmetal")
    g.roles["Mag"] = "Secondary"
    W = 0.24
    pts = [
        (-0.42, 0.62), (0.98, 0.62), (1.18, 0.5), (1.18, 0.24), (1.06, 0.08), (0.8, 0.03),
        (0.79, -0.06), (0.47, -0.06), (0.44, 0.08), (0.42, 0.24), (0.12, 0.27), (-0.3, 0.3), (-0.42, 0.38),
    ]
    rec = side(pts, W, bev=0.014, seg=1)
    cs = [box((0, 0.63, -0.04), (0.14, 0.24, 0.1), bev=0)]  # mag opening
    for sx in (-1, 1):
        cs.append(side([(0.84, 0.1), (1.04, 0.13), (1.12, 0.24), (1.12, 0.42), (0.84, 0.42)], 0.03, x=sx * W / 2, bev=0.006))
        cs.append(side([(0.48, 0.02), (0.76, 0.02), (0.76, 0.2), (0.5, 0.2)], 0.024, x=sx * W / 2, bev=0.006))
        cs.append(side([(-0.3, 0.36), (0.1, 0.36), (0.1, 0.42), (-0.3, 0.42)], 0.016, x=sx * W / 2, bev=0.004))
        cs.append(side([(0.86, 0.46), (1.0, 0.46), (1.12, 0.52), (0.98, 0.56), (0.86, 0.56)], 0.02, x=sx * W / 2, bev=0.004))  # nose facet
        cs.append(side([(0.2, 0.44), (0.42, 0.56), (0.7, 0.56), (0.7, 0.44)], 0.012, x=sx * W / 2, bev=0.003))  # upper facet
    cs.append(box((W / 2, 0.32, 0.5), (0.06, 0.26, 0.1), bev=0.008))  # ejection port
    cut(rec, cs)
    g.body(rec)
    g.metal(box((W / 2 - 0.03, 0.32, 0.5), (0.02, 0.24, 0.08), bev=0.004))
    g.body(bar([(0.13, 0.27), (0.17, 0.08), (0.4, 0.08), (0.43, 0.2)], 0.035, 0.09, bev=0.008))
    g.metal(trigger(0.26, 0.27, h=0.1))
    # charging handle (left)
    g.metal(box((-W / 2 - 0.02, 0.75, 0.52), (0.04, 0.08, 0.05), bev=0.01))
    g.metal(box((-W / 2 - 0.003, 0.55, 0.52), (0.01, 0.5, 0.02), bev=0.003))
    # selector
    g.metal(cyl_x(-W / 2 - 0.015, -W / 2, 0.03, y=0.02, z=0.45, seg=12))
    g.metal(box((-W / 2 - 0.02, 0.06, 0.45), (0.012, 0.09, 0.02), bev=0.004))
    pts, nf, a, L = grip_profile((0.07, 0.28), (-0.06, -0.28), 0.2, 0.2, nub=0.0, swell=0.006)
    grip = side(pts, 0.16, bev=0.022, seg=2)
    cut(grip, grip_texture((0.07, 0.28), a, nf, L, 0.16, 0.2, n=8))
    g.furn(grip)
    # shroud + rails + barrel
    sh = box((0, 1.33, B), (0.16, 0.32, 0.22), bev=0.012, seg=2)
    cut(sh, [cyl_x(-0.2, 0.2, 0.03, y=1.25 + i * 0.1, z=B + 0.01, seg=12) for i in range(2)])
    g.body(sh)
    g.body(picatinny(1.2, 1.47, B + 0.11, w=0.13, h=0.045))
    g.body(orient(picatinny(1.2, 1.47, B + 0.08, w=0.12, h=0.04), "side_r", (0, 0, B)))
    g.body(orient(picatinny(1.2, 1.47, B + 0.11, w=0.12, h=0.04), "bottom", (0, 0, B)))
    g.metal(cyl_y(1.48, 1.52, 0.032, z=B, seg=16))
    g.metal(lathe((0, 1.52, B), (0, 1, 0), [(0, 0), (0, 0.04), (0.08, 0.04), (0.09, 0.03), (0.09, 0)], seg=16, bev=0.004))
    g.body(picatinny(-0.42, 0.98, 0.62))
    # flip sights
    g.metal(box((0, -0.3, 0.7), (0.12, 0.1, 0.04), bev=0.008))
    g.metal(side([(-0.34, 0.71), (-0.26, 0.71), (-0.29, 0.81), (-0.32, 0.81)], 0.09, bev=0.006))
    g.metal(box((0, 0.9, 0.7), (0.12, 0.1, 0.04), bev=0.008))
    g.metal(side([(0.86, 0.71), (0.94, 0.71), (0.91, 0.82), (0.89, 0.82)], 0.08, bev=0.006))
    # stock adapter + folding stock
    g.body(box((0, -0.47, 0.5), (0.16, 0.1, 0.18), bev=0.02, seg=2))
    buffer_tube(g, -0.5, -1.05, z=0.5, r=0.065)
    m4_stock(g, y_back=-1.42, z_tube=0.5)
    straight_mag(g, (0.63, 0.27), 0.86, 0.2, 0.11, tilt=0, base=0.03)
    g.tape(side(axis_band(pts, (0.07, 0.28), a, L, 0.66, 0.8), 0.172, bev=0.004))
    g.points.update(
        Muzzle=(0, 1.61, B),
        Aim=(0, -0.3 - 0.55, 0.8),
        LeftHand=(0, 0.92, 0.05),
        Optic=(0, 0.3, 0.68),
        Underbarrel=(0, 1.34, B - 0.155),
        MuzzleMount=(0, 1.52, B),
        Side=(0.125, 1.34, B),
        MagWell=(0, 0.63, 0.27),
    )


# --------------------------------------------------------------------------------------
# MP7A1
# --------------------------------------------------------------------------------------


@register("MP7", "Primary")
def build_mp7(g):
    B = 0.42
    g.mats.update(Body="polymer", Furniture="polymer_dark", Mag="polymer", Metal="gunmetal")
    g.roles["Mag"] = "Secondary"
    W = 0.2
    pts = [(-0.44, 0.62), (0.92, 0.62), (1.06, 0.52), (1.08, 0.34), (0.98, 0.26), (0.45, 0.26), (0.12, 0.24), (-0.3, 0.27), (-0.44, 0.34)]
    rec = side(pts, W, bev=0.014, seg=1)
    cs = [box((W / 2, 0.42, 0.5), (0.05, 0.22, 0.09), bev=0.008)]
    for sx in (-1, 1):
        cs.append(side([(0.5, 0.3), (0.95, 0.3), (1.0, 0.36), (1.0, 0.44), (0.5, 0.44)], 0.024, x=sx * W / 2, bev=0.005))
        cs.append(side([(-0.36, 0.33), (0.1, 0.33), (0.1, 0.4), (-0.36, 0.4)], 0.016, x=sx * W / 2, bev=0.004))
    cut(rec, cs)
    g.body(rec)
    g.metal(box((W / 2 - 0.025, 0.42, 0.5), (0.02, 0.2, 0.07), bev=0.004))
    pts, nf, a, L = grip_profile((0.06, 0.26), (-0.09, -0.3), 0.2, 0.19, nub=0.012, waves=3, n=24)
    grip = side(pts, 0.15, bev=0.025, seg=2)
    cut(grip, box((0, -0.1, -0.33), (0.1, 0.17, 0.1), bev=0))  # mag opening
    cut(grip, grip_texture((0.06, 0.26), a, nf, L, 0.15, 0.2, n=7))
    g.body(grip)
    g.body(bar([(0.12, 0.25), (0.15, 0.1), (0.22, 0.08), (0.4, 0.08), (0.45, 0.14), (0.46, 0.26)], 0.03, 0.08, bev=0.008))
    g.metal(trigger(0.25, 0.25, h=0.1))
    g.body(picatinny(-0.44, 0.92, 0.62, w=0.14, h=0.05))
    for sx in ("side_r", "side_l"):
        g.body(orient(picatinny(0.55, 0.95, B + 0.1, w=0.1, h=0.035), sx, (0, 0, B)))
    g.metal(box((0, -0.5, 0.58), (0.16, 0.06, 0.03), bev=0.008))  # charging handle
    g.metal(box((0, -0.47, 0.58), (0.06, 0.06, 0.03), bev=0.008))
    for sx in (-1, 1):
        g.metal(cyl_x(sx * W / 2, sx * (W / 2 + 0.015), 0.028, y=-0.15, z=0.42, seg=12))
    # sights folded up on the rail
    g.metal(side([(-0.36, 0.67), (-0.26, 0.67), (-0.28, 0.76), (-0.34, 0.76)], 0.1, bev=0.006))
    g.metal(side([(0.8, 0.67), (0.88, 0.67), (0.86, 0.77), (0.82, 0.77)], 0.07, bev=0.006))
    # barrel + flash hider
    g.metal(cyl_y(1.06, 1.14, 0.03, z=B, seg=16))
    fh = lathe((0, 1.12, B), (0, 1, 0), [(0, 0), (0, 0.036), (0.2, 0.036), (0.2, 0.02), (0.19, 0)], seg=16, bev=0.004)
    cut(fh, [box((0, 1.25, B + 0.03), (0.014, 0.1, 0.03), bev=0)] + [box((sx * 0.03, 1.25, B), (0.03, 0.1, 0.014), bev=0) for sx in (-1, 1)])
    g.metal(fh)
    # folding foregrip (deployed)
    g.furn(box((0, 0.74, 0.24), (0.1, 0.18, 0.05), bev=0.012))
    fg = side([(0.66, 0.24), (0.82, 0.24), (0.83, -0.18), (0.8, -0.22), (0.7, -0.22), (0.67, -0.18)], 0.1, bev=0.03, seg=2)
    cut(fg, [box((sx * 0.06, 0.745, -0.02 - i * 0.06), (0.03, 0.2, 0.014), bev=0) for i in range(3) for sx in (-1, 1)])
    g.furn(fg)
    # telescoping stock: twin rods + butt plate
    for sx in (-1, 1):
        g.metal(cyl_y(-1.12, -0.44, 0.018, x=sx * 0.06, z=0.44, seg=10))
    g.furn(side([(-1.2, 0.6), (-1.1, 0.6), (-1.1, 0.27), (-1.13, 0.22), (-1.2, 0.22)], 0.18, bev=0.025, seg=2))
    g.furn(box((0, -1.1, 0.44), (0.18, 0.06, 0.08), bev=0.015))
    # mag in the grip
    mp = straight_mag(g, (0.0, 0.24), 0.7, 0.14, 0.09, tilt=0, base=0.035)
    for p_ in mp:
        rotate(p_, -math.degrees(math.atan2(0.15, 0.56)), "X", (0, 0.0, 0.24))
        move(p_, (0, 0.045, 0))
    g.tape(box((0, 0.745, -0.05), (0.112, 0.2, 0.08), bev=0.012))
    g.points.update(
        Muzzle=(0, 1.32, B),
        Aim=(0, -0.31 - 0.55, 0.78),
        LeftHand=(0, 0.745, 0.0),
        Optic=(0, 0.25, 0.67),
        MuzzleMount=(0, 1.14, B),
        Side=(0.135, 0.75, B),
        MagWell=(0, 0.045, 0.24),
    )


# --------------------------------------------------------------------------------------
# FN P90
# --------------------------------------------------------------------------------------


@register("P90", "Primary")
def build_p90(g):
    dz = 0.1
    B = 0.36 + dz
    g.mats.update(Body="polymer", Furniture="polymer_dark", Mag="smoke", Metal="gunmetal")
    g.roles["Mag"] = "Secondary"
    W = 0.26
    top_z = 0.49 + dz
    outline = (
        [(-1.08, -0.16 + dz), (-1.14, 0.0 + dz), (-1.16, 0.36 + dz), (-1.12, top_z - 0.02), (-1.04, top_z), (0.98, top_z)]
        + bezier((0.98, top_z), (1.14, top_z - 0.02), (1.24, 0.44 + dz), (1.26, 0.36 + dz), 5)[1:]
        + bezier((1.26, 0.36 + dz), (1.27, 0.27 + dz), (1.1, 0.22 + dz), (0.96, 0.13 + dz), 5)[1:]
        + bezier((0.96, 0.13 + dz), (0.86, 0.04 + dz), (0.86, -0.26 + dz), (0.62, -0.31 + dz), 6)[1:]
        + [(0.4, -0.32 + dz), (0.12, -0.3 + dz), (-0.1, -0.31 + dz), (-0.4, -0.3 + dz), (-0.8, -0.25 + dz)]
    )
    body = side(outline, W, bev=0.0)
    front_hole = rrect(0.33, -0.03 + dz, 0.44, 0.22, 0.1, 4)
    thumb_hole = rrect(-0.29, 0.0 + dz, 0.23, 0.3, 0.1, 4)
    cut(body, side(front_hole, 0.6, bev=0), side(thumb_hole, 0.6, bev=0))
    bevel(body, 0.085, 4)
    cs = []
    for sx in (-1, 1):
        cs.append(box((sx * W / 2, 0.0, 0.34 + dz), (0.02, 1.9, 0.012), bev=0))
        cs.append(box((sx * W / 2, -0.75, 0.2 + dz), (0.02, 0.5, 0.012), bev=0))
    cut(body, cs)
    g.body(body)
    g.furn(side([(-1.2, top_z - 0.03), (-1.13, top_z - 0.03), (-1.11, -0.15 + dz), (-1.06, -0.2 + dz), (-1.2, -0.2 + dz)], W - 0.02, bev=0.02, seg=2))
    g.metal(trigger(0.17, 0.09 + dz, h=0.1))
    g.metal(cyl_z(-0.32 + dz, -0.29 + dz, 0.04, y=0.2, seg=14))
    g.mag(box((0, -0.2, top_z + 0.065), (0.24, 1.56, 0.13), bev=0.025, seg=2))
    for sx in (-1, 1):
        g.body(side([(0.15, top_z - 0.02), (0.98, top_z - 0.02), (0.95, top_z + 0.2), (0.18, top_z + 0.2)], 0.025, x=sx * 0.13, bev=0.006))
    g.body(box((0, 0.57, top_z + 0.2), (0.285, 0.8, 0.03), bev=0.006))
    g.body(picatinny(0.18, 0.96, top_z + 0.215, w=0.14, h=0.05))
    for sx in ("side_r", "side_l"):
        g.body(orient(picatinny(0.72, 1.06, B + W / 2 - 0.005, w=0.1, h=0.035), sx, (0, 0, B)))
    g.metal(cyl_y(1.24, 1.32, 0.04, z=B, seg=16))
    fh = lathe((0, 1.3, B), (0, 1, 0), [(0, 0), (0, 0.035), (0.16, 0.035), (0.16, 0.02), (0.15, 0)], seg=16, bev=0.004)
    cut(fh, [box((sx * 0.03, 1.4, B), (0.03, 0.08, 0.014), bev=0) for sx in (-1, 1)])
    g.metal(fh)
    for sx in (-1, 1):
        g.metal(cyl_x(sx * W / 2, sx * (W / 2 + 0.04), 0.022, y=0.98, z=0.26 + dz, seg=10))
    band = clip_box(outline, u0=0.44, u1=0.62, v1=-0.15 + dz)
    g.tape(side(band, W + 0.014, bev=0.006))
    g.points.update(
        Muzzle=(0, 1.46, B),
        Aim=(0, 0.2 - 0.55, top_z + 0.33),
        LeftHand=(0, 0.56, -0.24 + dz),
        Optic=(0, 0.55, top_z + 0.265),
        MuzzleMount=(0, 1.32, B),
        Side=(0.165, 0.9, B),
        MagWell=(0, -0.2, top_z + 0.13),
    )


# --------------------------------------------------------------------------------------
# M249 SAW
# --------------------------------------------------------------------------------------


@register("M249", "Primary")
def build_m249(g):
    B = 0.55
    g.mats.update(Body="anodized", Furniture="polymer", Mag="od", Metal="gunmetal")
    g.roles["Mag"] = "Secondary"
    W = 0.26
    yr, yf = -0.48, 1.12
    rec = side([(yr, 0.3), (yr, 0.7), (yf, 0.7), (yf, 0.36), (1.0, 0.3)], W, bev=0.012)
    cs = [
        box((-W / 2, 0.45, 0.56), (0.08, 0.38, 0.12), bev=0.01),  # feed tray opening (left)
        box((0, 0.5, 0.3), (0.12, 0.3, 0.06), bev=0),  # ejection port bottom
    ]
    for sx in (-1, 1):
        cs.append(box((sx * W / 2, 0.75, 0.42), (0.02, 0.6, 0.03), bev=0.008))
        cs.append(box((sx * W / 2, -0.2, 0.42), (0.02, 0.4, 0.03), bev=0.008))
    cut(rec, cs)
    g.body(rec)
    # feed cover with rail
    fc = side([(yr + 0.38, 0.69), (0.98, 0.69), (0.98, 0.8), (yr + 0.46, 0.8)], W - 0.02, bev=0.014, seg=2)
    g.body(fc)
    g.body(picatinny(yr + 0.5, 0.96, 0.8, w=0.15, h=0.055))
    g.metal(side([(yr + 0.34, 0.7), (yr + 0.46, 0.7), (yr + 0.44, 0.9), (yr + 0.38, 0.9)], 0.1, bev=0.008))  # rear sight
    rs = cyl_x(-0.03, 0.03, 0.03, y=yr + 0.41, z=0.9, seg=12)
    cut(rs, cyl_x(-0.1, 0.1, 0.012, y=yr + 0.41, z=0.9, seg=8))
    g.metal(rs)
    g.metal(box((0, yr - 0.03, 0.5), (0.22, 0.07, 0.36), bev=0.015, seg=2))  # buttplate housing
    for sx in (-1, 1):  # receiver rivets
        for yy in (-0.38, -0.1, 0.2, 0.62, 0.95, 1.06):
            for zz in (0.36, 0.64):
                g.metal(pin_head((sx * (W / 2 + 0.001), yy, zz), "x", sx, 0.014, 0.004))
    g.metal(box((W / 2 + 0.03, 0.85, 0.5), (0.05, 0.12, 0.05), bev=0.012))  # charging handle
    # trigger group + grip
    g.furn(side([(-0.3, 0.31), (0.45, 0.31), (0.42, 0.22), (-0.28, 0.24)], 0.18, bev=0.012))
    ar_grip(g)
    g.body(bar([(0.12, 0.27), (0.13, 0.12), (0.2, 0.09), (0.44, 0.09), (0.48, 0.16), (0.48, 0.24)], 0.03, 0.09, bev=0.008))
    g.metal(trigger(0.26, 0.26, h=0.11))
    # stock
    st = side([(yr - 0.06, 0.66), (-1.75, 0.62), (-1.8, 0.66), (-1.84, 0.64), (-1.84, 0.02), (-1.78, -0.02), (-1.66, -0.02), (-0.9, 0.24), (yr - 0.06, 0.34)], 0.18, bev=0.03, seg=2)
    cut(st, side([(-1.6, 0.52), (-0.75, 0.55), (-0.75, 0.42), (-1.0, 0.31), (-1.6, 0.18)], 0.4, bev=0))
    g.furn(st)
    g.furn(side([(-1.9, 0.66), (-1.835, 0.66), (-1.835, 0.0), (-1.9, 0.0)], 0.19, bev=0.015, seg=2))
    # handguard (polymer, ribbed) + heat shield + rails
    hg = section(rounded_section(0.24, 0.31, 0.52, 0.06), yf, 1.9, bev=0.01)
    cut(hg, [box((0, 1.2 + i * 0.1, 0.31), (0.3, 0.035, 0.04), bev=0) for i in range(7)])
    g.furn(hg)
    g.body(orient(picatinny(1.2, 1.85, B - 0.1 + 0.18, w=0.11, h=0.04), "side_r", (0, 0, B - 0.1)))
    hs = tube((0, 1.15, B), (0, 1.95, B), 0.085, 0.072, seg=20)
    cut(hs, box((0, 1.55, B - 0.08), (0.3, 1.0, 0.16), bev=0))
    cut(hs, [cyl_z(B, B + 0.2, 0.022, y=1.25 + i * 0.12, seg=10) for i in range(6)])
    g.metal(hs)
    g.metal(cyl_y(yf, 3.32, 0.046, z=B, seg=20))
    g.metal(cyl_y(1.88, 2.62, 0.038, z=B - 0.12, seg=16))  # gas cylinder
    g.metal(side([(2.5, B - 0.17), (2.66, B - 0.17), (2.66, B + 0.04), (2.5, B + 0.04)], 0.1, bev=0.012))
    # carry handle
    g.metal(box((0, 1.98, B + 0.06), (0.1, 0.12, 0.05), bev=0.01))
    g.metal(bar([(1.9, B + 0.08), (1.92, B + 0.3), (2.18, B + 0.32), (2.2, B + 0.1)], 0.03, 0.06, bev=0.01))
    # front sight
    g.metal(side([(3.0, B + 0.02), (3.1, B + 0.02), (3.08, B + 0.22), (3.03, B + 0.22)], 0.05, bev=0.006))
    g.metal(tube((0, 2.98, B), (0, 3.12, B), 0.06, 0.044, seg=16))
    birdcage(g, 3.32, 0.18, 0.048, z=B)
    # bipod (deployed)
    g.metal(box((0, 2.68, B - 0.14), (0.12, 0.1, 0.07), bev=0.012))
    for sx in (-1, 1):
        top = V((sx * 0.05, 2.68, B - 0.16))
        foot = V((sx * 0.24, 2.76, -0.44))
        mid = top.lerp(foot, 0.55)
        g.metal(cyl(top, mid, 0.024, seg=12))
        g.metal(cyl(top.lerp(foot, 0.5), foot, 0.017, seg=10))
        g.metal(box(tuple(foot + V((0, 0, -0.01))), (0.05, 0.08, 0.025), bev=0.01))
    # 200 rd box + belt
    bx = box((-0.08, 0.52, -0.04), (0.28, 0.62, 0.62), bev=0.05, seg=3)
    cut(bx, [box((-0.08 + sx * 0.14, 0.52, -0.04), (0.02, 0.5, 0.5), bev=0.02) for sx in (-1, 1)])
    g.mag(bx)
    g.mag(box((-0.08, 0.52, 0.28), (0.3, 0.64, 0.04), bev=0.015))
    for i in range(6):
        t = i / 5
        x = -0.2 + 0.08 * t
        z = 0.3 + 0.26 * math.sin(t * math.pi / 2)
        g.mag(cyl_y(0.36, 0.6, 0.02, x=x - 0.03 * (1 - t), z=z, seg=10))
        g.mag(box((x - 0.03 * (1 - t), 0.48, z), (0.03, 0.26, 0.045), bev=0.006))
    g.tape(section(rounded_section(0.252, 0.3, 0.53, 0.065), 1.55, 1.67, bev=0.004))
    g.points.update(
        Muzzle=(0, 3.51, B),
        Aim=(0, yr + 0.41 - 0.55, 0.9),
        LeftHand=(0, 1.5, 0.31),
        Optic=(0, 0.45, 0.855),
        Underbarrel=(0, 1.55, 0.31),
        MuzzleMount=(0, 3.33, B),
        Side=(0.12 + 0.03, 1.52, B - 0.1),
        MagWell=(-0.08, 0.52, 0.3),
    )


# ======================================================================================
# SECONDARIES
# ======================================================================================

PB = 0.38  # pistol bore height


def glock(g, gid):
    g.mats.update(Body="polymer", Slide="gunmetal", Mag="polymer", Metal="gunmetal")
    g.roles["Mag"] = "Primary"
    W = 0.16
    y0, y1, z0, z1 = -0.1, 1.2, 0.29, 0.49
    sec = [(-W / 2, z0), (W / 2, z0), (W / 2, z1 - 0.045), (W / 2 - 0.03, z1), (-W / 2 + 0.03, z1), (-W / 2, z1 - 0.045)]
    sl = section(sec, y0, y1, bev=0.01, seg=2)
    cs = serrations(y0 + 0.05, y0 + 0.2, 7, z0 + 0.02, z1 - 0.03, W, depth=0.012, groove=0.014)
    cs.append(box((0.045, 0.47, z1), (0.12, 0.3, 0.09), bev=0.006))  # ejection port
    cs.append(cyl_y(y1 - 0.02, y1 + 0.02, 0.035, z=PB, seg=16))
    cs.append(side([(y1 - 0.1, z0 - 0.01), (y1 + 0.02, z0 - 0.01), (y1 + 0.02, z0 + 0.05)], 0.3, bev=0))  # nose
    if gid == "G18":
        cs += [box((0, y1 - 0.08 - i * 0.07, z1), (0.04, 0.035, 0.1), bev=0.008) for i in range(3)]
    cut(sl, cs)
    g.add("Slide", sl)
    rs = box((0, y0 + 0.06, z1 + 0.025), (0.11, 0.06, 0.05), bev=0.008)
    cut(rs, box((0, y0 + 0.06, z1 + 0.05), (0.025, 0.1, 0.04), bev=0))
    g.add("Slide", rs)
    g.add("Slide", box((0, y1 - 0.06, z1 + 0.02), (0.03, 0.05, 0.04), bev=0.006))
    if gid == "G18":
        g.add("Slide", box((-W / 2 - 0.006, y0 + 0.08, z0 + 0.1), (0.014, 0.05, 0.03), bev=0.004))
    g.metal(box((0, 0.47, z1 - 0.04), (0.09, 0.3, 0.06), bev=0.006))
    g.metal(tube((0, y1 - 0.05, PB), (0, y1 - 0.015, PB), 0.034, 0.015, seg=16))
    # frame: dust cover with rail, square trigger guard, angled grip
    fr = side([(y0 + 0.02, z0 + 0.01), (y1 - 0.02, z0 + 0.01), (y1 - 0.02, 0.25), (y1 - 0.06, 0.21), (0.62, 0.21), (0.24, 0.2), (0.0, 0.22), (y0 + 0.02, 0.25)], W - 0.006, bev=0.01)
    cut(fr, [box((0, 0.86 + i * 0.08, 0.205), (0.2, 0.028, 0.02), bev=0) for i in range(3)])
    cut(fr, [box((sx * W / 2, 0.92, 0.235), (0.02, 0.4, 0.015), bev=0) for sx in (-1, 1)])
    g.body(fr)
    g.body(bar([(0.23, 0.22), (0.25, 0.09), (0.32, 0.055), (0.58, 0.055), (0.64, 0.11), (0.64, 0.21)], 0.035, 0.1, bev=0.008))
    top, bot = (0.07, 0.24), (-0.08, -0.31)
    pts, nf, a, L = grip_profile(top, bot, 0.3, 0.27, nub=0.012, waves=3, n=24, beaver=0.05, swell=0.008)
    grip = side(pts, 0.17, bev=0.03, seg=2)
    cut(grip, grip_texture(top, a, nf, L, 0.17, 0.3, t0=0.22, t1=0.62, n=6))
    g.body(grip)
    g.metal(trigger(0.36, 0.22, h=0.1, w=0.04))
    g.metal(box((0, 0.365, 0.17), (0.012, 0.02, 0.05), bev=0.003))
    g.metal(box((-W / 2 - 0.004, 0.36, z0 - 0.02), (0.01, 0.16, 0.025), bev=0.003))
    for sx in (-1, 1):
        g.metal(box((sx * (W / 2 - 0.002), 0.58, z0 - 0.025), (0.012, 0.04, 0.02), bev=0.003))
    g.metal(box((-W / 2 + 0.01, 0.22, 0.17), (0.02, 0.05, 0.04), bev=0.006))
    for yy, zz in ((0.0, 0.265), (0.33, 0.25), (0.55, 0.265)):  # trigger housing / trigger / locking block pins
        for sx in (-1, 1):
            g.metal(pin_head((sx * (W / 2 - 0.003), yy, zz), "x", sx, 0.012, 0.004))
    ext = 0.55 if gid == "G18" else 0.0
    mp = straight_mag(g, (0, 0.23), 0.6 + ext, 0.22, 0.12, base=0.03, bev=0.008)
    ang = -math.degrees(math.atan2(-(bot[0] - top[0]), -(bot[1] - top[1])))
    for p_ in mp:
        rotate(p_, ang, "X", (0, 0, 0.23))
        move(p_, (0, top[0], 0))
    g.tape(side(axis_band(pts, top, a, L, 0.72, 0.86), 0.178, bev=0.004))
    g.points.update(
        Muzzle=(0, y1 + 0.005, PB),
        Aim=(0, y0 + 0.06 - 0.55, z1 + 0.045),
        LeftHand=(-0.07, -0.02, -0.04),
        Underbarrel=(0, 0.95, 0.21),
        MuzzleMount=(0, y1, PB),
        MagWell=(0, top[0], 0.23),
    )


@register("G17", "Secondary")
def build_g17(g):
    glock(g, "G17")


@register("M1911", "Secondary")
def build_m1911(g):
    B = 0.37
    g.mats.update(Body="parkerized", Slide="parkerized", Wood="wood", Mag="gunmetal", Metal="steel")
    g.roles.update(Mag="Metal", Slide="Metal")
    W = 0.13
    y0, y1, z0 = -0.12, 1.27, 0.29
    sec = [(-W / 2, z0), (W / 2, z0), (W / 2, 0.41)] + arc(0, 0.41, W / 2, 0, 180, 8)[1:-1] + [(-W / 2, 0.41)]
    sl = section(sec, y0, y1, bev=0.008, seg=2)
    cs = serrations(y0 + 0.05, y0 + 0.2, 8, z0 + 0.02, 0.43, W, depth=0.01, groove=0.012, slant=-8)
    cs.append(box((W / 2, 0.5, 0.39), (0.06, 0.26, 0.09), bev=0.006))
    cs.append(cyl_y(y1 - 0.03, y1 + 0.02, 0.05, z=B, seg=18))
    cut(sl, cs)
    g.add("Slide", sl)
    rs = box((0, y0 + 0.06, 0.48), (0.09, 0.06, 0.04), bev=0.006)
    cut(rs, box((0, y0 + 0.06, 0.5), (0.02, 0.1, 0.03), bev=0))
    g.add("Slide", rs)
    g.add("Slide", box((0, y1 - 0.08, 0.485), (0.02, 0.06, 0.03), bev=0.005))
    g.metal(box((W / 2 - 0.03, 0.5, 0.39), (0.02, 0.24, 0.07), bev=0.004))
    g.metal(tube((0, y1 - 0.025, B), (0, y1 + 0.005, B), 0.048, 0.03, seg=18))
    g.metal(tube((0, y1 - 0.02, B), (0, y1 + 0.0, B), 0.03, 0.017, seg=14))
    g.metal(cyl_y(y1 - 0.05, y1 - 0.0, 0.035, z=0.31, seg=14))
    fr = side([(y0 + 0.02, z0 + 0.005), (y1 - 0.04, z0 + 0.005), (y1 - 0.04, 0.24), (0.6, 0.23), (0.22, 0.22), (0.0, 0.24), (y0 + 0.02, 0.27)], W - 0.006, bev=0.008)
    g.body(fr)
    g.body(bar([(0.21, 0.23), (0.23, 0.1), (0.31, 0.075), (0.5, 0.075), (0.57, 0.12), (0.58, 0.22)], 0.028, 0.08, bev=0.008))
    top, bot = (0.05, 0.25), (-0.06, -0.31)
    pts, nf, a, L = grip_profile(top, bot, 0.27, 0.26, swell=0.0)
    g.body(side(pts, W - 0.006, bev=0.014))
    # wood panels with diamond checkering
    for sx in (-1, 1):
        xp = sx * (W / 2 + 0.006)
        pn = side(axis_rrect(top, a, nf, L, 0.14, 0.9, -0.1, 0.105, 0.04), 0.024, x=xp, bev=0.01, seg=2)
        ccs = []
        for i in range(-6, 7):
            for d in (-1, 1):
                c = box((sx * (W / 2 + 0.02), -0.02 + i * 0.04, -0.03), (0.014, 0.008, 0.7), bev=0)
                rotate(c, d * 35, "X", (0, -0.02 + i * 0.04, -0.03))
                ccs.append(c)
        cutter = join(ccs, "chk")
        intersect(cutter, side(axis_rrect(top, a, nf, L, 0.22, 0.82, -0.075, 0.08, 0.02), 0.03, x=sx * (W / 2 + 0.02), bev=0))
        cut(pn, cutter)
        g.wood(pn)
        for t in (0.28, 0.78):
            c = V(top) + V(a) * L * t
            g.metal(cyl_x(sx * (W / 2 + 0.016), sx * (W / 2 + 0.022), 0.016, y=c.x, z=c.y, seg=10))
    # hammer, beavertail grip safety, thumb safety, slide stop, trigger, mag release
    g.metal(side([(y0 + 0.01, 0.31), (y0 + 0.05, 0.34), (y0 - 0.02, 0.44), (y0 - 0.07, 0.45), (y0 - 0.06, 0.41), (y0 - 0.03, 0.4)], 0.045, bev=0.006))
    g.metal(side([(y0 + 0.06, 0.285), (y0 - 0.04, 0.29), (y0 - 0.1, 0.27), (y0 - 0.09, 0.245), (y0 - 0.02, 0.235), (y0 + 0.04, 0.17), (y0 + 0.08, 0.18)], 0.11, bev=0.014, seg=2))
    g.metal(box((-W / 2 - 0.01, y0 + 0.16, 0.29), (0.014, 0.12, 0.03), bev=0.004))
    g.metal(box((-W / 2 - 0.008, 0.36, 0.28), (0.012, 0.18, 0.03), bev=0.004))
    g.metal(cyl_x(-W / 2 - 0.012, W / 2, 0.018, y=0.36, z=0.28, seg=10))
    g.metal(side([(0.29, 0.24), (0.34, 0.24), (0.34, 0.13), (0.3, 0.13)], 0.04, bev=0.006))
    g.metal(cyl_x(-W / 2 - 0.01, -W / 2, 0.022, y=0.2, z=0.18, seg=10))
    mp = straight_mag(g, (0, 0.23), 0.62, 0.16, 0.1, base=0.03, bev=0.006)
    ang = -math.degrees(math.atan2(-(bot[0] - top[0]), -(bot[1] - top[1])))
    for p_ in mp:
        rotate(p_, ang, "X", (0, 0, 0.23))
        move(p_, (0, top[0], 0))
    g.tape(side(axis_band(pts, top, a, L, 0.9, 0.98), W + 0.012, bev=0.004))
    g.points.update(
        Muzzle=(0, y1 + 0.005, B),
        Aim=(0, y0 + 0.06 - 0.55, 0.51),
        LeftHand=(-0.06, -0.02, -0.04),
        MuzzleMount=(0, y1, B),
        MagWell=(0, top[0], 0.23),
    )


@register("DEAGLE", "Secondary")
def build_deagle(g):
    B = 0.42
    g.mats.update(Body="anodized", Slide="steel", Metal="steel", Furniture="rubber", Mag="gunmetal")
    g.roles.update(Mag="Metal", Slide="Metal")
    W = 0.17
    y0 = -0.14
    yb0, yb1 = 0.56, 1.62
    # fixed barrel: triangular top with integral rail and side flutes
    bsec = [(-0.08, 0.3), (0.08, 0.3), (0.08, 0.47), (0.03, 0.56), (-0.03, 0.56), (-0.08, 0.47)]
    br = section(bsec, yb0, yb1, bev=0.01, seg=2)
    cut(br, [cyl_y(yb1 - 0.02, yb1 + 0.02, 0.04, z=B, seg=16)] + [side(rrect(1.2, 0.39, 0.55, 0.055, 0.027), 0.02, x=sx * 0.08, bev=0) for sx in (-1, 1)])
    g.metal(br)
    g.metal(picatinny(yb0 + 0.04, yb1 - 0.12, 0.56, w=0.08, h=0.035, pitch=0.06))
    g.metal(box((0, yb1 - 0.05, 0.58), (0.03, 0.05, 0.04), bev=0.006))
    g.metal(tube((0, yb1 - 0.03, B), (0, yb1 - 0.01, B), 0.036, 0.022, seg=16))
    # slide (rear half, wraps the bolt)
    ssec = [(-W / 2, 0.29), (W / 2, 0.29), (W / 2, 0.47), (0.05, 0.545), (-0.05, 0.545), (-W / 2, 0.47)]
    sl = section(ssec, y0, yb0 + 0.02, bev=0.012, seg=2)
    cs = serrations(y0 + 0.05, y0 + 0.22, 8, 0.31, 0.46, W, depth=0.012, groove=0.016, slant=-10)
    cs.append(box((W / 2, 0.36, 0.46), (0.08, 0.22, 0.08), bev=0.006))
    cut(sl, cs)
    g.add("Slide", sl)
    rs = box((0, y0 + 0.06, 0.57), (0.11, 0.06, 0.05), bev=0.008)
    cut(rs, box((0, y0 + 0.06, 0.6), (0.025, 0.1, 0.04), bev=0))
    g.add("Slide", rs)
    for sx in (-1, 1):  # ambi safety levers
        g.add("Slide", box((sx * (W / 2 + 0.01), y0 + 0.1, 0.43), (0.025, 0.08, 0.04), bev=0.008))
    g.metal(box((0.05, 0.36, 0.44), (0.02, 0.2, 0.06), bev=0.004))
    # frame
    fr = side([(y0 + 0.02, 0.3), (yb1 - 0.02, 0.3), (yb1 - 0.02, 0.26), (yb1 - 0.08, 0.2), (0.74, 0.19), (0.26, 0.2), (0.0, 0.22), (y0 + 0.02, 0.26)], W - 0.006, bev=0.012)
    g.body(fr)
    g.body(bar([(0.25, 0.21), (0.27, 0.08), (0.37, 0.035), (0.63, 0.035), (0.71, 0.1), (0.72, 0.2)], 0.04, 0.1, bev=0.01))
    top, bot = (0.08, 0.24), (-0.09, -0.34)
    pts, nf, a, L = grip_profile(top, bot, 0.33, 0.3, swell=0.008, beaver=0.04)
    g.body(side(pts, W - 0.01, bev=0.02, seg=2))
    wrap = axis_band(pts, top, a, L, 0.12, 0.97)
    gw = side(wrap, W + 0.016, bev=0.025, seg=2)
    cut(gw, grip_texture(top, a, nf, L, W + 0.016, 0.34, t0=0.2, t1=0.62, n=6))
    g.furn(gw)
    g.metal(side([(y0 + 0.0, 0.33), (y0 + 0.05, 0.36), (y0 - 0.01, 0.46), (y0 - 0.07, 0.465), (y0 - 0.05, 0.42)], 0.05, bev=0.006))
    g.metal(trigger(0.4, 0.2, h=0.1, w=0.04))
    g.metal(box((-W / 2 - 0.004, 0.42, 0.26), (0.012, 0.16, 0.03), bev=0.004))
    g.metal(cyl_x(-W / 2 - 0.012, -W / 2, 0.024, y=0.24, z=0.16, seg=10))
    mp = straight_mag(g, (0, 0.22), 0.66, 0.21, 0.11, base=0.035, bev=0.008)
    ang = -math.degrees(math.atan2(-(bot[0] - top[0]), -(bot[1] - top[1])))
    for p_ in mp:
        rotate(p_, ang, "X", (0, 0, 0.22))
        move(p_, (0, top[0], 0))
    g.tape(side(axis_band(pts, top, a, L, 0.7, 0.82), W + 0.032, bev=0.004))
    g.points.update(
        Muzzle=(0, yb1 + 0.005, B),
        Aim=(0, y0 + 0.06 - 0.55, 0.6),
        LeftHand=(-0.07, -0.03, -0.05),
        Optic=(0, 1.05, 0.595),
        MagWell=(0, top[0], 0.22),
    )


@register("G18", "Secondary")
def build_g18(g):
    glock(g, "G18")


# ======================================================================================
# ATTACHMENTS (origin = mount point)
# ======================================================================================


def rail_clamp(g, y0, y1, w=0.17, h=0.05, z=0.0, knob="left"):
    g.body(section([(-w / 2, z), (w / 2, z), (w / 2, z + h), (-w / 2, z + h)], y0, y1, bev=0.01))
    for sx in (-1, 1):
        g.body(section([(sx * w / 2, z), (sx * (w / 2 - 0.02), z - 0.02), (sx * (w / 2 - 0.035), z - 0.02), (sx * (w / 2 - 0.015), z)], y0, y1, bev=0.0))
    if knob:
        sx = -1 if knob == "left" else 1
        g.body(cyl_x(sx * w / 2, sx * (w / 2 + 0.035), 0.03, y=(y0 + y1) / 2, z=z + 0.02, seg=12, bev=0.006))


@register("RedDot", "Attachment")
def build_reddot(g):
    g.mats.update(Body="anodized")
    Z = 0.2
    rail_clamp(g, -0.11, 0.11, w=0.15)
    g.body(side([(-0.1, 0.05), (0.1, 0.05), (0.08, Z - 0.03), (-0.08, Z - 0.03)], 0.1, bev=0.012))
    g.body(lathe((0, -0.13, Z), (0, 1, 0), [(0, 0.05), (0, 0.068), (0.26, 0.068), (0.26, 0.05)], seg=24, closed=True, bev=0.006))
    g.body(lathe((0, -0.13, Z), (0, 1, 0), [(0, 0.05), (0, 0.072), (0.03, 0.072), (0.03, 0.05)], seg=24, closed=True))
    g.body(lathe((0, 0.1, Z), (0, 1, 0), [(0, 0.05), (0, 0.072), (0.03, 0.072), (0.03, 0.05)], seg=24, closed=True))
    tur = cyl_z(Z + 0.06, Z + 0.1, 0.028, y=0.0, seg=14, bev=0.005)
    cut(tur, box((0, 0, Z + 0.1), (0.07, 0.008, 0.012), bev=0))  # coin slot
    g.body(tur)
    tur = cyl_x(0.06, 0.1, 0.028, y=0.0, z=Z, seg=14, bev=0.005)
    cut(tur, box((0.1, 0, Z), (0.012, 0.008, 0.07), bev=0))
    g.body(tur)
    # turret guard wings (T-2 style) and battery cap on the left
    for sx in (-1, 1):
        g.body(side([(-0.06, Z + 0.03), (0.06, Z + 0.03), (0.04, Z + 0.105), (-0.04, Z + 0.105)], 0.012, x=sx * 0.04, bev=0.004))
    g.body(cyl_x(-0.1, -0.06, 0.03, y=0.0, z=Z, seg=16, bev=0.006))
    # front flip-up lens cover (open), cross bolt nut. No rear cover: open, it stood ~7 cm from the eye and
    # filled the top of the aim-down-sights view.
    g.add("Rubber", side([(0.14, Z + 0.06), (0.17, Z + 0.06), (0.2, Z + 0.17), (0.17, Z + 0.18)], 0.12, bev=0.012, seg=2))
    g.mats["Rubber"] = "rubber"
    g.metal(cyl_x(0.075, 0.105, 0.025, y=0.0, z=0.025, seg=6, bev=0.003))
    g.add("Glass", cyl_y(0.095, 0.1, 0.05, z=Z, seg=24))
    g.add("Reticle", cyl_y(0.092, 0.094, 0.006, z=Z, seg=8))
    g.points.update(Aim=(0, -0.55, Z))


@register("Holo", "Attachment")
def build_holo(g):
    g.mats.update(Body="anodized")
    Z = 0.17
    rail_clamp(g, -0.12, 0.12, w=0.17, knob="right")
    g.body(box((0, -0.04, 0.085), (0.16, 0.36, 0.07), bev=0.015, seg=2))
    g.body(box((0, -0.18, 0.14), (0.14, 0.08, 0.14), bev=0.015, seg=2))  # rear controls
    hood = side([(-0.06, 0.07), (0.16, 0.07), (0.16, Z + 0.1), (0.13, Z + 0.115), (-0.03, Z + 0.115), (-0.06, Z + 0.09)], 0.18, bev=0.02, seg=2)
    cut(hood, side(rrect(0.05, Z + 0.01, 0.4, 0.15, 0.025), 0.14, bev=0.0))
    cut(hood, [side(rrect(0.05, Z + 0.02, 0.12, 0.08, 0.02), 0.03, x=sx * 0.09, bev=0) for sx in (-1, 1)])  # side windows
    g.body(hood)
    # rear control buttons (rubber), QD lever and cross bolts
    for i in range(2):
        g.add("Rubber", box((0, -0.222, 0.15 + i * 0.045), (0.07, 0.012, 0.03), bev=0.006, seg=2))
    g.mats["Rubber"] = "rubber"
    g.metal(side([(-0.06, 0.02), (0.06, 0.02), (0.08, 0.05), (-0.04, 0.05)], 0.012, x=0.095, bev=0.004))
    for yy in (-0.08, 0.06):
        g.metal(cyl_x(-0.09, -0.085, 0.014, y=yy, z=0.1, seg=12, bev=0.002))
    g.body(cyl_x(0.08, 0.1, 0.035, y=-0.12, z=0.085, seg=20, bev=0.005))  # battery cap
    g.add("Glass", box((0, 0.14, Z + 0.01), (0.14, 0.006, 0.15), bev=0))
    g.add("Glass", box((0, -0.03, Z + 0.01), (0.14, 0.006, 0.15), bev=0))
    g.add("Reticle", tube((0, 0.13, Z), (0, 0.133, Z), 0.032, 0.027, seg=24))
    g.add("Reticle", cyl_y(0.13, 0.133, 0.004, z=Z, seg=8))
    g.points.update(Aim=(0, -0.55, Z))


@register("Scope4x", "Attachment")
def build_acog(g):
    g.mats.update(Body="anodized")
    Z = 0.19
    rail_clamp(g, -0.12, 0.14, w=0.16)
    for sx in (-1, 1):
        g.body(cyl_x(sx * 0.08, sx * 0.11, 0.025, y=0.07 if sx > 0 else -0.05, z=0.025, seg=12))
    g.body(side([(-0.14, 0.05), (0.16, 0.05), (0.18, 0.1), (0.2, Z + 0.06), (-0.16, Z + 0.07), (-0.16, 0.1)], 0.12, bev=0.02, seg=2))
    g.body(lathe((0, -0.36, Z), (0, 1, 0), [(0, 0.04), (0, 0.055), (0.1, 0.055), (0.24, 0.045), (0.24, 0.0), (0.0, 0.0)], seg=24, bev=0.004))
    g.body(lathe((0, 0.14, Z), (0, 1, 0), [(0, 0), (0, 0.055), (0.12, 0.072), (0.22, 0.072), (0.22, 0.058), (0.2, 0.0)], seg=24, bev=0.004))
    g.body(cyl_y(-0.12, 0.14, 0.008, z=Z + 0.075, seg=8))
    g.body(cyl_z(Z + 0.06, Z + 0.09, 0.022, y=0.0, seg=12, bev=0.004))
    g.body(cyl_x(0.06, 0.09, 0.022, y=0.0, z=Z, seg=12, bev=0.004))
    g.add("Glass", cyl_y(0.345, 0.355, 0.058, z=Z, seg=24))
    g.add("Glass", cyl_y(-0.37, -0.36, 0.04, z=Z, seg=20))
    g.points.update(Aim=(0, -0.36 - 0.25, Z))


@register("ScopeLong", "Attachment")
def build_scope_long(g):
    g.mats.update(Body="anodized")
    Z = 0.24
    for yy in (-0.24, 0.22):
        rail_clamp(g, yy - 0.05, yy + 0.05, w=0.15, knob="left")
        g.body(side([(yy - 0.04, 0.05), (yy + 0.04, 0.05), (yy + 0.04, Z), (yy - 0.04, Z)], 0.07, bev=0.008))
        g.body(tube((0, yy - 0.035, Z), (0, yy + 0.035, Z), 0.065, 0.045, seg=20, bev=0.004))
    prof = [(0, 0), (0, 0.06), (0.06, 0.066), (0.2, 0.066), (0.3, 0.05), (0.39, 0.05)]
    for i in range(4):
        prof += [(0.4 + i * 0.022, 0.058), (0.41 + i * 0.022, 0.058), (0.42 + i * 0.022, 0.052)]
    prof += [(0.5, 0.046), (1.08, 0.046), (1.28, 0.088), (1.5, 0.09), (1.52, 0.082), (1.52, 0)]
    g.body(lathe((0, -0.78, Z), (0, 1, 0), prof, seg=24, bev=0.003))
    g.body(box((0, 0.0, Z), (0.11, 0.16, 0.11), bev=0.03, seg=2))
    g.body(lathe((0, 0, Z + 0.05), (0, 0, 1), [(0, 0), (0, 0.04), (0.06, 0.04), (0.06, 0.044), (0.11, 0.044), (0.11, 0)], seg=20, bev=0.004))
    g.body(lathe((0.05, 0, Z), (1, 0, 0), [(0, 0), (0, 0.035), (0.05, 0.035), (0.05, 0.04), (0.09, 0.04), (0.09, 0)], seg=20, bev=0.004))
    g.body(lathe((-0.05, 0, Z), (-1, 0, 0), [(0, 0), (0, 0.04), (0.06, 0.04), (0.06, 0)], seg=20, bev=0.004))
    g.add("Glass", cyl_y(0.735, 0.742, 0.08, z=Z, seg=24))
    g.add("Glass", cyl_y(-0.785, -0.778, 0.052, z=Z, seg=24))
    g.points.update(Aim=(0, -0.78 - 0.4, Z))


@register("Suppressor", "Attachment")
def build_suppressor(g):
    g.mats.update(Body="anodized")
    L = 0.85
    s = lathe((0, 0, 0), (0, 1, 0), [(0, 0), (0, 0.05), (0.05, 0.05), (0.08, 0.07), (L - 0.03, 0.07), (L, 0.06), (L, 0.016), (L - 0.02, 0)], seg=24, bev=0.005)
    cut(s, [tube((0, y, 0), (0, y + 0.012, 0), 0.08, 0.064, seg=24) for y in (0.12, 0.16, 0.2, L - 0.1)])
    cut(s, [box((sx * 0.07, 0.06, 0), (0.02, 0.05, 0.04), bev=0) for sx in (-1, 1)])
    # front cap vent holes + wrench flats near the muzzle
    vents = []
    for a_ in range(0, 360, 45):
        cx, cz = 0.036 * math.cos(math.radians(a_)), 0.036 * math.sin(math.radians(a_))
        vents.append(cyl((cx, L - 0.01, cz), (cx, L + 0.05, cz), 0.007, seg=8))
    cut(s, vents)
    g.body(s)
    # knurled grip band (aluminium recipe has a knurl normal pattern)
    g.add("Grip", tube((0, 0.3, 0), (0, 0.6, 0), 0.0712, 0.066, seg=24))
    g.mats["Grip"] = "aluminium"
    g.tints["Grip"] = "P"
    g.points.update(MuzzleOffset=(0, L, 0))


@register("Compensator", "Attachment")
def build_comp(g):
    g.mats.update(Body="gunmetal")
    L = 0.2
    c = lathe((0, 0, 0), (0, 1, 0), [(0, 0), (0, 0.04), (0.02, 0.046), (L - 0.01, 0.046), (L, 0.04), (L, 0.016), (L - 0.01, 0)], seg=20, bev=0.003)
    cs = [cyl_y(0.03, L + 0.02, 0.018, seg=12)]
    for i in range(3):
        cs.append(box((0, 0.06 + i * 0.045, 0.045), (0.02, 0.025, 0.04), bev=0))
        for sx in (-1, 1):
            cs.append(box((sx * 0.045, 0.06 + i * 0.045, 0.015), (0.04, 0.025, 0.02), bev=0))
    cut(c, cs)
    g.body(c)
    g.points.update(MuzzleOffset=(0, L, 0))


def under_clamp(g, y0, y1, w=0.15):
    g.body(section([(-w / 2, 0), (w / 2, 0), (w / 2, -0.05), (-w / 2, -0.05)], y0, y1, bev=0.01))
    for sx in (-1, 1):
        g.body(section([(sx * w / 2, 0), (sx * (w / 2 - 0.02), 0.02), (sx * (w / 2 - 0.035), 0.02), (sx * (w / 2 - 0.015), 0)], y0, y1, bev=0))


@register("VerticalGrip", "Attachment")
def build_vgrip(g):
    g.mats.update(Body="polymer")
    under_clamp(g, -0.12, 0.12)
    prof = [(0, 0.06), (0.04, 0.065)]
    for i in range(4):
        zz = 0.1 + i * 0.1
        prof += [(zz, 0.068), (zz + 0.04, 0.06), (zz + 0.08, 0.068)]
    prof += [(0.5, 0.07), (0.53, 0.072), (0.56, 0.06), (0.57, 0)]
    gr = lathe((0, 0, -0.04), (0, 0, -1), [(0, 0)] + prof, seg=20, bev=0.004)
    g.body(gr)
    g.body(cyl_z(-0.08, -0.04, 0.05, seg=16, bev=0.004))


@register("AngledGrip", "Attachment")
def build_afg(g):
    g.mats.update(Body="polymer")
    under_clamp(g, -0.2, 0.2)
    pts = [(-0.26, -0.04), (0.22, -0.04), (0.2, -0.08)] + bezier((0.2, -0.08), (0.12, -0.12), (0.05, -0.2), (0.0, -0.24), 6)[1:] + [(-0.06, -0.24)] + bezier((-0.06, -0.24), (-0.12, -0.16), (-0.2, -0.08), (-0.26, -0.06), 6)[1:]
    afg = side(pts, 0.12, bev=0.03, seg=2)
    cut(afg, [box((sx * 0.06, 0.08 - i * 0.05, -0.1 - i * 0.02), (0.02, 0.02, 0.2), bev=0) for i in range(4) for sx in (-1, 1)])
    g.body(afg)


@register("Laser", "Attachment")
def build_laser(g):
    """PEQ-15 style aiming laser / illuminator box.  Mounts like an optic: origin at the
    bottom-centre of the clamp, box above it (roll it 90 degrees for a side rail)."""
    g.mats.update(Body="fde", Metal="gunmetal", Rubber="rubber")
    rail_clamp(g, -0.2, 0.2, w=0.15, knob="left")
    W, L, H, z0 = 0.34, 0.56, 0.19, 0.05
    bx = box((0, 0.0, z0 + H / 2), (W, L, H), bev=0.03, seg=3)
    cs = [
        cyl_y(L / 2 - 0.03, L / 2 + 0.05, 0.03, x=-0.09, z=z0 + 0.12, seg=20),
        cyl_y(L / 2 - 0.03, L / 2 + 0.05, 0.03, x=-0.02, z=z0 + 0.12, seg=20),
        cyl_y(L / 2 - 0.04, L / 2 + 0.05, 0.055, x=0.08, z=z0 + 0.095, seg=28),
    ]
    for sx in (-1, 1):  # side grooves
        for k in range(3):
            cs.append(box((sx * W / 2, -0.05, z0 + 0.05 + k * 0.04), (0.02, 0.3, 0.012), bev=0))
    cut(bx, cs)
    g.body(bx)
    # emitter bezels, adjusters, buttons, battery cap
    g.add("Rubber", tube((0.08, L / 2 - 0.02, z0 + 0.095), (0.08, L / 2 + 0.014, z0 + 0.095), 0.066, 0.05, seg=28, bev=0.004))
    for x in (-0.09, -0.02):
        g.metal(tube((x, L / 2 - 0.01, z0 + 0.12), (x, L / 2 + 0.008, z0 + 0.12), 0.036, 0.026, seg=20))
    for p_ in ((W / 2, 0.08, z0 + 0.1), (0, 0.08, z0 + H)):
        ax = "x" if p_[0] else "z"
        g.metal(cyl(p_, (p_[0] + (0.02 if ax == "x" else 0), p_[1], p_[2] + (0.02 if ax == "z" else 0)), 0.03, seg=24, bev=0.005))
    for yy in (-0.12, -0.04):
        g.add("Rubber", box((-0.06, yy, z0 + H + 0.008), (0.07, 0.06, 0.02), bev=0.008, seg=2))
    g.add("Rubber", box((0.07, -0.08, z0 + H + 0.012), (0.06, 0.12, 0.03), bev=0.012, seg=2))
    g.body(cyl_y(-L / 2 - 0.04, -L / 2 + 0.01, 0.05, x=0.06, z=z0 + 0.09, seg=24, bev=0.006))
    g.add("Glass", cyl_y(L / 2 - 0.025, L / 2 - 0.015, 0.027, x=-0.09, z=z0 + 0.12, seg=16))
    g.add("Glass", cyl_y(L / 2 - 0.025, L / 2 - 0.015, 0.027, x=-0.02, z=z0 + 0.12, seg=16))
    g.add("Glass", cyl_y(L / 2 - 0.035, L / 2 - 0.025, 0.052, x=0.08, z=z0 + 0.095, seg=24))
    g.points.update(Beam=(-0.09, L / 2, z0 + 0.12))


# --------------------------------------------------------------------------------------
# Small hardware: screws, pins, QD sockets (design units)
# --------------------------------------------------------------------------------------


def socket_screw(p, axis="x", sign=1, r=0.018, h=0.008):
    """Socket-head cap screw head sitting on a surface; axis = surface normal axis."""
    p = V(p)
    d = {"x": V((1, 0, 0)), "y": V((0, 1, 0)), "z": V((0, 0, 1))}[axis] * sign
    head = cyl(p, p + d * h, r, seg=16, bev=r * 0.25)
    hexr = lathe(p + d * (h * 0.35), d, [(0, 0), (0, r * 0.5), (h * 1.2, r * 0.5), (h * 1.2, 0)], seg=6)
    cut(head, hexr)
    return head


def pin_head(p, axis="x", sign=1, r=0.02, h=0.006):
    p = V(p)
    d = {"x": V((1, 0, 0)), "y": V((0, 1, 0)), "z": V((0, 0, 1))}[axis] * sign
    return cyl(p - d * 0.002, p + d * h, r, seg=16, bev=r * 0.3)


def qd_socket(p, axis="x", sign=1, r=0.035):
    p = V(p)
    d = {"x": V((1, 0, 0)), "y": V((0, 1, 0)), "z": V((0, 0, 1))}[axis] * sign
    cup = cyl(p - d * 0.01, p + d * 0.018, r, seg=20, bev=0.005)
    cut(cup, cyl(p + d * 0.004, p + d * 0.05, r * 0.55, seg=16))
    return cup


def ar_details(g, y_rear=-0.34, w_low=0.16, w_up=0.17, tube_z=0.52, tube_y1=-1.2):
    """Extra AR-15 hardware: castle nut + end plate with QD, takedown pins, bolt catch roll pin."""
    # castle nut with notches
    cn = cyl_y(y_rear - 0.07, y_rear - 0.015, 0.088, z=tube_z, seg=24, bev=0.006)
    cs = []
    for i in range(6):
        b = box((0, y_rear - 0.04, tube_z + 0.088), (0.03, 0.07, 0.03), bev=0)
        rotate(b, i * 60 + 30, "Y", (0, 0, tube_z))
        cs.append(b)
    cut(cn, cs)
    g.metal(cn)
    # end plate with sling QD socket (left)
    g.metal(side([(y_rear - 0.015, tube_z + 0.1), (y_rear - 0.005, tube_z + 0.1), (y_rear - 0.005, tube_z - 0.11), (y_rear - 0.015, tube_z - 0.11)], w_low + 0.01, bev=0.003))
    g.metal(qd_socket((-w_low / 2 - 0.02, y_rear - 0.05, tube_z - 0.02), "x", -1, 0.03))
    # takedown/pivot pin heads with detent dimples on the right side
    for yy in (0.92, y_rear + 0.12):
        g.metal(pin_head((w_low / 2 + 0.003, yy, 0.39), "x", 1, 0.024, 0.006))
        g.metal(pin_head((-w_low / 2 - 0.003, yy, 0.39), "x", -1, 0.02, 0.004))
    # trigger/hammer pins
    for yy in (0.17, 0.33):
        for sx in (-1, 1):
            g.metal(pin_head((sx * (w_low / 2 + 0.002), yy, 0.33), "x", sx, 0.014, 0.003))
    # bolt catch roll pin + plunger
    g.metal(cyl_z(0.3, 0.42, 0.008, x=-w_low / 2 - 0.004, y=0.47, seg=10))


def handguard_hardware(g, y0, cz=BORE - 0.01, w=0.25, h=0.27):
    """Clamp screws at the rear of a free-float handguard + QD cups."""
    for sx in (-1, 1):
        for dz in (-0.05, 0.03):
            g.metal(socket_screw((sx * (w / 2), y0 + 0.07, cz + dz), "x", sx, 0.016, 0.007))
        g.metal(qd_socket((sx * w / 2, y0 + 0.2, cz + 0.07), "x", sx, 0.026))


# --------------------------------------------------------------------------------------
# Thunder-B style gas grenade
# --------------------------------------------------------------------------------------


@register("GRENADE", "Throwable")
def build_grenade(g):
    g.scale = RIFLE_SCALE
    g.mats.update(Body="anod_od", Furniture="polymer", Metal="steel")
    R = 0.119  # 45 mm diameter
    z0, z1 = -0.29, 0.25
    prof = [(0, 0), (0, R * 0.86), (0.012, R * 0.95), (0.03, R)]
    # grip rings: alternate ridges along the body
    zz = 0.06
    while zz < (z1 - z0) - 0.07:
        prof += [(zz, R), (zz + 0.008, R * 0.955), (zz + 0.03, R * 0.955), (zz + 0.038, R)]
        zz += 0.06
    prof += [(z1 - z0 - 0.02, R), (z1 - z0, R * 0.9), (z1 - z0, 0)]
    body = lathe((0, 0, z0), (0, 0, 1), prof, seg=40, bev=0.002)
    # gas vent ports around the shoulder
    cut(body, [cyl((0, 0, z1 - 0.06), (math.cos(math.radians(a)) * (R + 0.05), math.sin(math.radians(a)) * (R + 0.05), z1 - 0.06), 0.014, seg=12) for a in range(0, 360, 45)])
    g.body(body)
    # base with fill valve
    g.metal(lathe((0, 0, z0 - 0.012), (0, 0, 1), [(0, 0), (0, R * 0.8), (0.012, R * 0.84), (0.012, 0)], seg=40, bev=0.002))
    g.metal(cyl_z(z0 - 0.024, z0 - 0.008, 0.018, seg=16, bev=0.003))
    # top cap (polymer) with grip flutes
    cap = lathe((0, 0, z1), (0, 0, 1), [(0, 0), (0, R * 0.92), (0.06, R * 0.88), (0.085, R * 0.7), (0.095, R * 0.35), (0.095, 0)], seg=40, bev=0.003)
    cut(cap, [box((math.cos(math.radians(a)) * R * 0.92, math.sin(math.radians(a)) * R * 0.92, z1 + 0.035), (0.02, 0.02, 0.07), bev=0) for a in range(0, 360, 20)])
    g.furn(cap)
    # striker housing + pin + ring
    g.metal(cyl_z(z1 + 0.09, z1 + 0.13, 0.035, seg=24, bev=0.004))
    g.metal(cyl((-0.06, 0, z1 + 0.115), (0.07, 0, z1 + 0.115), 0.008, seg=12))
    ring = lathe((0.11, 0, z1 + 0.115), (0, 1, 0), [(-0.004, 0.034), (-0.004, 0.042), (0.004, 0.042), (0.004, 0.034)], seg=28, closed=True)
    rotate(ring, 70, "X", (0.11, 0, z1 + 0.115))
    g.metal(ring)
    g.tape(lathe((0, 0, -0.05), (0, 0, 1), [(0, R + 0.0015), (0.07, R + 0.0015), (0.07, R - 0.01), (0, R - 0.01)], seg=40, closed=True))
    g.points.update()


# --------------------------------------------------------------------------------------
# New attachments
# --------------------------------------------------------------------------------------


@register("Magnifier", "Attachment")
def build_magnifier(g):
    """3x flip-to-side magnifier (G33 style) on a flip mount, shown deployed."""
    g.mats.update(Body="anodized", Metal="gunmetal", Rubber="rubber")
    Z = 0.17
    rail_clamp(g, -0.12, 0.08, w=0.15, knob="right")
    # flip mount: base, pivot on the left, arm up to the tube
    g.body(side([(-0.12, 0.05), (0.08, 0.05), (0.06, 0.09), (-0.1, 0.09)], 0.13, bev=0.012))
    g.body(cyl_y(-0.11, 0.07, 0.022, x=-0.075, z=0.075, seg=16, bev=0.004))
    g.body(side([(-0.1, 0.07), (0.06, 0.07), (0.05, Z - 0.05), (-0.09, Z - 0.05)], 0.035, x=-0.06, bev=0.008))
    g.metal(socket_screw((-0.085, -0.02, 0.075), "x", -1, 0.014, 0.006))
    g.body(box((0, -0.02, Z - 0.055), (0.12, 0.17, 0.035), bev=0.01, seg=2))
    # tube: objective bell, body with ribs, eyepiece with rubber cup
    prof = [(0, 0), (0, 0.072), (0.03, 0.078), (0.07, 0.072), (0.09, 0.066)]
    for i in range(4):
        y0 = 0.1 + i * 0.05
        prof += [(y0, 0.066), (y0 + 0.01, 0.071), (y0 + 0.03, 0.071), (y0 + 0.04, 0.066)]
    prof += [(0.33, 0.066), (0.36, 0.074), (0.42, 0.074), (0.42, 0)]
    tube = lathe((0, -0.24, Z), (0, 1, 0), prof, seg=36, bev=0.002)
    cut(tube, cyl_y(-0.25, -0.2, 0.052, z=Z, seg=32), cyl_y(0.15, 0.2, 0.06, z=Z, seg=32))
    g.body(tube)
    g.add("Rubber", lathe((0, -0.3, Z), (0, 1, 0), [(0, 0.052), (0, 0.07), (0.06, 0.074), (0.06, 0.052)], seg=36, closed=True, bev=0.004))
    g.body(cyl_z(Z + 0.06, Z + 0.09, 0.022, y=-0.02, seg=16, bev=0.004))
    g.body(cyl_x(0.06, 0.09, 0.022, y=-0.02, z=Z, seg=16, bev=0.004))
    g.add("Glass", cyl_y(-0.215, -0.205, 0.052, z=Z, seg=24))
    g.add("Glass", cyl_y(0.165, 0.175, 0.06, z=Z, seg=24))
    g.points.update(Aim=(0, -0.3 - 0.35, Z))


@register("Bipod", "Attachment")
def build_bipod(g):
    """Harris-style bipod with picatinny adapter, legs folded forward."""
    g.mats.update(Body="anodized", Metal="steel", Rubber="rubber")
    under_clamp(g, -0.1, 0.1, w=0.14)
    g.body(box((0, 0, -0.08), (0.1, 0.16, 0.06), bev=0.012, seg=2))
    g.metal(cyl_z(-0.14, -0.05, 0.02, seg=16))
    g.metal(socket_screw((0.05, 0, -0.08), "x", 1, 0.02, 0.012))
    # yoke
    yk = side([(-0.09, -0.12), (0.09, -0.12), (0.11, -0.19), (0.06, -0.24), (-0.06, -0.24), (-0.11, -0.19)], 0.26, bev=0.015, seg=2)
    cut(yk, box((0, 0, -0.2), (0.16, 0.3, 0.07), bev=0.01))
    g.body(yk)
    for sx in (-1, 1):
        x = sx * 0.1
        # leg: upper tube + lower extension + rubber foot, folded forward along +Y
        g.body(cyl((x, -0.03, -0.2), (x, 0.9, -0.21), 0.03, seg=20, bev=0.004))
        g.metal(cyl((x, 0.88, -0.21), (x, 1.24, -0.215), 0.021, seg=18))
        g.add("Rubber", lathe((x, 1.24, -0.215), (0, 1, 0), [(0, 0), (0, 0.03), (0.06, 0.034), (0.1, 0.026), (0.11, 0)], seg=20))
        g.metal(cyl_x(x - sx * 0.02, x + sx * 0.03, 0.026, y=0.86, z=-0.21, seg=16, bev=0.004))  # leg lock collar
        g.metal(cyl_x(x - 0.04, x + 0.04, 0.025, y=-0.03, z=-0.2, seg=16, bev=0.004))  # pivot
        # coil spring alongside the leg
        pts = []
        for i in range(48):
            t = i / 47
            a = t * math.pi * 2 * 12
            pts.append((x - sx * 0.045 + 0.012 * math.cos(a), 0.05 + 0.35 * t, -0.16 + 0.012 * math.sin(a)))
        for a_, b_ in zip(pts[:-1], pts[1:]):
            g.metal(cyl(a_, b_, 0.0045, seg=6))
    g.metal(cyl_z(-0.17, -0.14, 0.035, y=0.0, x=0.0, seg=20, bev=0.004))  # swivel knob
    g.points.update()


def _ar_mag_profile(g, length, bend, piece="Mag", ribs=True):
    pts, cl = curved_mag((0.0, 0.0), length, 0.36, 0.13, bend, n=16)
    g.add(piece, side(pts, 0.13, bev=0.014, seg=2))
    if ribs:
        for t0 in (0.55, 0.61, 0.67, 0.73, 0.79):
            g.add(piece, mag_segment(cl, 0.36, 0.13, t0, t0 + 0.03, extra=0.006))
    g.add(piece, mag_segment(cl, 0.36, 0.13, 0.96, 1.03, extra=0.014, bev=0.01))
    g.add(piece, mag_segment(cl, 0.36, 0.13, 0.12, 0.17, extra=0.004))
    # feed lips + follower window
    g.add(piece, box((0, 0.0, 0.01), (0.1, 0.3, 0.03), bev=0.006))
    return cl


@register("ExtMag", "Attachment")
def build_extmag(g):
    """40-round AR polymer magazine.  Origin = top-centre where it seats in the mag well."""
    g.mats.update(Mag="polymer")
    _ar_mag_profile(g, 1.3, 16)
    g.points.update()


@register("DrumMag", "Attachment")
def build_drummag(g):
    """60-round AR drum (D-60 style): feed tower + drum.  Origin = mag-well top-centre."""
    g.mats.update(Mag="polymer", Metal="steel")
    pts, cl = curved_mag((0.0, 0.0), 0.5, 0.36, 0.13, 6, n=6)
    g.mag(side(pts, 0.13, bev=0.014, seg=2))
    g.mag(box((0, 0.0, 0.01), (0.1, 0.3, 0.03), bev=0.006))
    cy, cz, R, W = 0.06, -0.82, 0.42, 0.48
    drum = lathe((-W / 2, cy, cz), (1, 0, 0), [(0, 0), (0, R - 0.03), (0.03, R), (W - 0.03, R), (W, R - 0.03), (W, 0)], seg=56, bev=0.004)
    cs = []
    for sx in (-1, 1):  # recessed faces with a raised rim + strengthening ribs
        cs.append(cyl_x(sx * (W / 2 + 0.02), sx * (W / 2 - 0.012), R - 0.06, y=cy, z=cz, seg=48))
    for i in range(12):
        b = box((0, cy, cz + R), (W + 0.1, 0.035, 0.03), bev=0)
        rotate(b, i * 30, "X", (0, cy, cz))
        cs.append(b)
    cut(drum, cs)
    g.mag(drum)
    for sx in (-1, 1):
        g.mag(cyl_x(sx * (W / 2 - 0.012), sx * (W / 2 + 0.01), 0.1, y=cy, z=cz, seg=32, bev=0.006))  # winding knob hub
        g.mag(side([(cy - 0.02, cz - 0.02), (cy + 0.02, cz - 0.02), (cy + 0.02, cz + 0.16), (cy - 0.02, cz + 0.16)], 0.04, x=sx * (W / 2 + 0.02), bev=0.006))
    # neck between tower and drum
    g.mag(side([(-0.18, -0.42), (0.2, -0.42), (0.24, -0.55), (-0.2, -0.55)], 0.2, bev=0.02, seg=2))
    g.points.update()


# ======================================================================================
# Pipeline: bake, export (FBX per piece), JSON, renders
# ======================================================================================

WEAPON_ROWS = [
    ["M4", "SR25", "VSR"],
    ["AK74", "M870", "M249"],
    ["MP5", "VECTOR", "MP7", "P90"],
    ["G17", "G18", "M1911", "DEAGLE", "GRENADE"],
]


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 1.0
    for name in ("Work", "Lineup", "Labels"):
        c = bpy.data.collections.new(name)
        scn.collection.children.link(c)
        WORK[name.lower() if name != "Work" else "coll"] = c


def clear_work_except(keep):
    keep = set(o.name for o in keep)
    for ob in list(WORK["coll"].objects):
        if ob.name not in keep:
            delete(ob)


def export_fbx(ob, path):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=True,
        object_types={"MESH"},
        axis_forward="X",
        axis_up="Z",
        apply_unit_scale=True,
        global_scale=1.0,
        apply_scale_options="FBX_SCALE_ALL",
        use_tspace=True,
        mesh_smooth_type="FACE",
        add_leaf_bones=False,
        use_mesh_modifiers=True,
        path_mode="STRIP",
        embed_textures=False,
        bake_anim=False,
    )
    ob.select_set(False)


def tints_for(g):
    """Preview tint colours (default finish) for the role mask channels."""
    t = {}
    for group, role in g.tints.items():
        if role and group in g.parts:
            t.setdefault(role, tuple(c / bk.TINT_GREY for c in PALETTE[g.mats[group]]))
    return t


def process(g, res, do_bake, rig, do_render):
    QUALITY.update(seg=GEO_SEG, bevel=GEO_BEVEL, min_seg=16)
    fn = BUILDERS[g.id][1]
    t0 = time.time()
    fn(g)
    pieces = g.finish()
    print(f"  {g.id}: modelled in {time.time() - t0:.0f}s", flush=True)
    clear_work_except([ob for _, ob, _ in pieces])
    out_dir = os.path.join(SOURCE_DIR, g.category, g.id)
    os.makedirs(out_dir, exist_ok=True)
    seed = (zlib.crc32(g.id.encode()) % 997) / 7.0
    info = []
    tints = tints_for(g)
    for piece, ob, zones in pieces:
        tris = tri_count(ob)
        slot = f"M_{g.id}_{piece}"
        textured = False
        if piece in UNBAKED:
            if piece == "Glass":
                mat = bk.plain_material(slot, PALETTE["glass"], 0.03, 0.0, alpha=0.25)
                if tris > TRI_LIMIT_GLASS:
                    print(f"WARNING {g.id}.Glass has {tris} triangles (> {TRI_LIMIT_GLASS})")
            else:
                mat = bk.plain_material(slot, (1.0, 0.05, 0.03), 0.4, 0.0, emission=(1.0, 0.05, 0.02))
            ob.data.materials.clear()
            ob.data.materials.append(mat)
            for p in ob.data.polygons:
                p.material_index = 0
            bk.uv_unwrap(ob, res, cache_key=f"{g.id}_{piece}")
        else:
            res_piece = res if piece == "Body" and g.kind != "Attachment" else max(512, res // 2)
            bk.uv_unwrap(ob, res_piece, cache_key=f"{g.id}_{piece}")
            if do_bake:
                t0 = time.time()
                bk.setup_bake_engine()
                paths, cached = bk.bake_piece(ob, zones, res_piece, out_dir, g.id, piece, seed=seed, edge_radius=g.edge_radius)
                textured = True
                print(f"    {g.id}.{piece}: {tris} tris, baked {res_piece}px in {time.time() - t0:.0f}s {'(cached)' if cached else ''}", flush=True)
            # export material: one slot named per the conventions
            ob.data.materials.clear()
            mat = bpy.data.materials.get(slot) or bpy.data.materials.new(slot)
            ob.data.materials.append(mat)
            for p in ob.data.polygons:
                p.material_index = 0
        g.to_unreal(ob)
        ob.name = f"SM_{g.id}_{piece}"
        export_fbx(ob, os.path.join(out_dir, f"SM_{g.id}_{piece}.fbx"))
        ob.name = piece
        if textured:
            prev = bk.preview_material(f"PV_{g.id}_{piece}", bk.texture_paths(out_dir, g.id, piece), tints, proxy_res=1024 if not do_render else 2048)
            ob.data.materials.clear()
            ob.data.materials.append(prev)
        info.append({"Name": piece, "Kind": KIND_OF_PIECE.get(piece, "Static"), "Slots": [slot], "Triangles": tris, "Textured": textured, "Object": ob})
    objs = [i["Object"] for i in info]
    lo, hi = studio.bbox(objs)
    ue_lo = [round(lo.x * 100, 1), round(-hi.y * 100, 1), round(lo.z * 100, 1)]
    ue_hi = [round(hi.x * 100, 1), round(-lo.y * 100, 1), round(hi.z * 100, 1)]
    entry = OrderedDict()
    entry["Pieces"] = [OrderedDict((k, i[k]) for k in ("Name", "Kind", "Slots")) for i in info]
    pts = OrderedDict()
    keys = ["Muzzle", "Aim", "LeftHand", "MagWell", "Optic", "Underbarrel", "MuzzleMount", "Side", "Beam"]
    for k in keys:
        if g.points.get(k) is not None:
            pts[k] = g.point_ue(g.points[k])
    if g.kind == "Attachment":
        if "Aim" in pts:
            entry["AimOffset"] = pts.pop("Aim")
        if g.points.get("MuzzleOffset") is not None:
            entry["MuzzleOffset"] = g.point_ue(g.points["MuzzleOffset"])
    entry["Points"] = pts
    entry["Bounds"] = {"Min": ue_lo, "Max": ue_hi}
    if do_render:
        rdir = os.path.join(RENDER_DIR, g.category)
        os.makedirs(rdir, exist_ok=True)
        for o in WORK["lineup"].objects:
            o.hide_render = True
        rig["floor"].hide_render = False
        studio.frame(rig, lo, hi, view_dir=(0.5, -1.0, 0.3) if g.kind != "Attachment" else (0.6, -1.0, 0.45), lens=85)
        t0 = time.time()
        studio.render(os.path.join(rdir, f"{g.id}.png"), RENDER_RES, samples=RENDER_SAMPLES)
        print(f"    {g.id}: render {time.time() - t0:.0f}s", flush=True)
    for o in objs:
        o.name = f"{g.id}_{o.name}"
        for c in list(o.users_collection):
            c.objects.unlink(o)
        WORK["lineup"].objects.link(o)
        o.hide_render = True
        o["asset"] = g.id
    return entry, info


RENDER_SAMPLES = 10
GEO_SEG = 3.5  # round-segment multiplier (Nanite: dense curvature is cheap)
GEO_BEVEL = 2  # extra bevel segments on every chamfer
RENDER_RES = (1920, 1080)
LINEUP_RES = (3840, 2160)


def write_json(path, assets):
    import json

    data = OrderedDict()
    if os.path.exists(path):
        try:
            data = json.load(open(path), object_pairs_hook=OrderedDict)
        except Exception:
            data = OrderedDict()
    data["Version"] = 1
    old = data.get("Assets", OrderedDict())
    for k, v in assets.items():
        old[k] = v
    order = list(BUILDERS.keys())
    data["Assets"] = OrderedDict((k, old[k]) for k in sorted(old, key=lambda k: order.index(k) if k in order else 999))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def lineup(rig, category, rows, row_gap, col_gap, label_size, view_dir, lens, path):
    groups = {}
    for o in WORK["lineup"].objects:
        a = o.get("asset")
        if a and BUILDERS.get(a, ("", None))[0] != "" and (BUILDERS[a][0] == "Attachment") == (category == "Attachments"):
            groups.setdefault(a, []).append(o)
    if not groups:
        return
    shown = studio.layout_rows(groups, rows, row_gap, col_gap, WORK["labels"], label_size)
    meshes = [o for o in shown if o.type == "MESH"]
    lo, hi = studio.bbox(shown)
    rig["floor"].hide_render = True
    studio.frame(rig, lo, hi, view_dir=view_dir, margin=1.05, lens=lens)
    studio.render(path, LINEUP_RES, samples=RENDER_SAMPLES)
    for o in shown:
        o.hide_render = True
    del meshes


def run_each(argv, only, res):
    """Driver: one child process per asset (frees memory between assets, retries a
    crashed child once), optionally several at a time (--jobs N), then one child that
    renders the lineups from the cached bakes."""
    import subprocess
    from concurrent.futures import ThreadPoolExecutor

    jobs = 1
    if "--jobs" in argv:
        jobs = int(argv[argv.index("--jobs") + 1])
    passthru = [a for a in argv if a.startswith("--") and a not in ("--each", "--res", "--jobs")]
    ids = [i for i in BUILDERS if not only or i in only]

    def one(gid):
        for attempt in range(2):
            cmd = [sys.executable, os.path.abspath(__file__), "--", gid, "--res", str(res)] + passthru
            print(f"[each] {gid} (attempt {attempt + 1})", flush=True)
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            log = [ln for ln in r.stdout.splitlines() if ln.startswith(("  ", "built", "WARNING", "Traceback")) or "Error" in ln]
            print("\n".join(log), flush=True)
            if r.returncode == 0:
                return None
        return gid

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        failed = [f for f in ex.map(one, ids) if f]
    if "--no-render" not in passthru:
        subprocess.run([sys.executable, os.path.abspath(__file__), "--", "--res", str(res), "--lineups-only"] + passthru)
    print(f"[each] done; failed: {failed}", flush=True)


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    res = 4096
    if "--res" in argv:
        res = int(argv[argv.index("--res") + 1])
    only = [a for a in argv if not a.startswith("--") and not a.isdigit()]
    if "--each" in flags:
        return run_each(argv, only, res)
    do_bake = "--no-bake" not in flags
    do_render = "--no-render" not in flags
    lineups_only = "--lineups-only" in flags  # rebuild (cached bakes) and render only the lineups
    if "--preview" in flags:  # quick look renders while iterating
        global RENDER_SAMPLES, RENDER_RES, LINEUP_RES
        RENDER_SAMPLES, RENDER_RES, LINEUP_RES = 16, (960, 540), (1920, 1080)
    reset_scene()
    rig = studio.setup_studio()
    results = {"Weapons": OrderedDict(), "Attachments": OrderedDict()}
    summary = []
    for gid, (kind, fn) in BUILDERS.items():
        if only and gid not in only:
            continue
        g = Gun(gid, kind)
        entry, info = process(g, res, do_bake, rig, do_render and not lineups_only)
        results[g.category][gid] = entry
        summary.append((gid, {i["Name"]: i["Triangles"] for i in info}))
        print(f"built {gid}: " + ", ".join(f"{i['Name']}={i['Triangles']}" for i in info), flush=True)
    for cat, assets in results.items():
        if assets:
            write_json(os.path.join(DATA_DIR, f"{cat}.json"), assets)
    if do_render and (not only or "--lineup" in flags):
        lineup(rig, "Weapons", WEAPON_ROWS, 0.07, 0.07, 0.022, (0.1, -1.0, 0.12), 135, os.path.join(RENDER_DIR, "Weapons", "_Lineup_4K.png"))
        att = [gid for gid, (k, _) in BUILDERS.items() if k == "Attachment"]
        rows = [att[0:5], att[5:9], att[9:13], att[13:]]
        lineup(rig, "Attachments", rows, 0.05, 0.06, 0.012, (0.35, -1.0, 0.3), 100, os.path.join(RENDER_DIR, "Attachments", "_Lineup_4K.png"))
    print("\nSUMMARY (triangles)")
    for gid, t in summary:
        print(f"  {gid:14s} total {sum(t.values()):8d}  " + ", ".join(f"{k}={v}" for k, v in t.items()))


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    main(argv)
