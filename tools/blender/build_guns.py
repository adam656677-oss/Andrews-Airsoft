"""
Procedural airsoft gun meshes for Andrew's Airsoft.

Run with a Python that has the `bpy` module (Blender 5.2 as a module):

    python tools/blender/build_guns.py            # build everything
    python tools/blender/build_guns.py M4 G17     # build only some ids (no lineup / lua)

Outputs
    assets/meshes/<ID>.glb        one GLB per gun / attachment
    src/shared/GunMeshData.lua    piece + attachment-point metadata (game coordinates)
    docs/renders/<ID>.png         preview renders, plus lineup.png / attachments.png

Modelling convention (Blender): barrel along +Y, up +Z, right +X, 1 unit = 1 stud,
pistol-grip centre at the origin.  Game coordinates = (bx, bz, -by).
Attachments use the same axes with the origin at their mount point.

Everything is deterministic: no randomness, fixed build order.
"""

import math
import os
import sys
from collections import OrderedDict

import bpy  # noqa: I001  (bpy must be imported before bmesh)
import bmesh
from mathutils import Matrix, Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MESH_DIR = os.path.join(ROOT, "assets", "meshes")
RENDER_DIR = os.path.join(ROOT, "docs", "renders")
LUA_PATH = os.path.join(ROOT, "src", "shared", "GunMeshData.lua")

TRI_LIMIT_OBJECT = 8000
TRI_LIMIT_GUN = 25000

# --------------------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------------------

PALETTE = {
    # name: (rgb, metallic, roughness)
    "polymer": ((0.022, 0.022, 0.024), 0.0, 0.55),
    "polymer_dark": ((0.012, 0.012, 0.013), 0.0, 0.6),
    "anodized": ((0.028, 0.028, 0.030), 0.35, 0.45),
    "gunmetal": ((0.055, 0.058, 0.062), 0.85, 0.35),
    "steel": ((0.16, 0.16, 0.165), 0.9, 0.3),
    "parkerized": ((0.07, 0.072, 0.07), 0.6, 0.55),
    "fde": ((0.25, 0.18, 0.105), 0.0, 0.6),
    "od": ((0.085, 0.09, 0.05), 0.0, 0.6),
    "wood": ((0.15, 0.06, 0.022), 0.0, 0.42),
    "wood_light": ((0.24, 0.11, 0.045), 0.0, 0.45),
    "plum": ((0.11, 0.035, 0.03), 0.0, 0.5),
    "tape": ((0.62, 0.62, 0.60), 0.0, 0.85),
    "rubber": ((0.015, 0.015, 0.015), 0.0, 0.9),
    "glass": ((0.05, 0.12, 0.14), 0.0, 0.05),
    "reticle": ((1.0, 0.05, 0.03), 0.0, 0.4),
    "chrome": ((0.55, 0.56, 0.58), 1.0, 0.18),
    "smoke": ((0.09, 0.085, 0.07), 0.0, 0.15),
}

_mat_cache = {}


def material(name):
    if name in _mat_cache and _mat_cache[name].name in bpy.data.materials:
        return _mat_cache[name]
    rgb, metal, rough = PALETTE[name]
    m = bpy.data.materials.new("M_" + name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    if name == "glass":
        bsdf.inputs["Alpha"].default_value = 0.45
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
    if name == "reticle":
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.05, 0.02, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 6.0
    m.diffuse_color = (*rgb, 1.0)
    _mat_cache[name] = m
    return m


# --------------------------------------------------------------------------------------
# Low level mesh helpers (all geometry is built directly in world space)
# --------------------------------------------------------------------------------------

V = Vector
_work = {"coll": None}


def _link(ob):
    coll = _work["coll"] or bpy.context.scene.collection
    coll.objects.link(ob)
    return ob


def obj_from_bm(bm, name="part"):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _link(bpy.data.objects.new(name, me))


def apply_mods(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=False, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)
    return ob


def delete(ob):
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if me and me.users == 0:
        bpy.data.meshes.remove(me)


def bevel(ob, w, seg=1, angle=40.0):
    if w and w > 0:
        m = ob.modifiers.new("bev", "BEVEL")
        m.width = w
        m.segments = seg
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(angle)
        m.use_clamp_overlap = True
        m.miter_outer = "MITER_ARC" if seg > 1 else "MITER_SHARP"
        apply_mods(ob)
    return ob


def join(objs, name="joined"):
    objs = [o for o in objs if o is not None]
    bm = bmesh.new()
    for o in objs:
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    for o in objs:
        delete(o)
    return obj_from_bm(bm, name)


def xform(ob, M):
    ob.data.transform(M)
    ob.data.update()
    return ob


def move(ob, d):
    return xform(ob, Matrix.Translation(V(d)))


def rotate(ob, deg, axis="X", pivot=(0, 0, 0)):
    p = V(pivot)
    M = Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-p)
    return xform(ob, M)


def scale(ob, s, pivot=(0, 0, 0)):
    p = V(pivot)
    if isinstance(s, (int, float)):
        s = (s, s, s)
    S = Matrix.Diagonal((s[0], s[1], s[2], 1.0))
    return xform(ob, Matrix.Translation(p) @ S @ Matrix.Translation(-p))


def flip_normals(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def mirror_x(ob, keep=True):
    """Return a mirrored (x -> -x) copy (and keep the original)."""
    me = ob.data.copy()
    cp = _link(bpy.data.objects.new(ob.name + "_m", me))
    xform(cp, Matrix.Diagonal((-1, 1, 1, 1)))
    flip_normals(cp)
    if keep:
        return cp
    delete(ob)
    return cp


def duplicate(ob):
    return _link(bpy.data.objects.new(ob.name + "_d", ob.data.copy()))


def boolean(ob, cutters, op="DIFFERENCE", solver="EXACT", self_check=True):
    if not isinstance(cutters, (list, tuple)):
        cutters = [cutters]
    cutters = [c for c in cutters if c is not None]
    if not cutters:
        return ob
    c = join(cutters, "cutter") if len(cutters) > 1 else cutters[0]
    m = ob.modifiers.new("bool", "BOOLEAN")
    m.operation = op
    m.object = c
    m.solver = solver
    if solver == "EXACT":
        m.use_self = self_check
        m.use_hole_tolerant = False
    c.hide_set(True)
    apply_mods(ob)
    delete(c)
    return ob


def cut(ob, *cutters, **kw):
    flat = []
    for c in cutters:
        if isinstance(c, (list, tuple)):
            flat.extend(c)
        else:
            flat.append(c)
    return boolean(ob, flat, "DIFFERENCE", **kw)


def union(ob, *others, **kw):
    return boolean(ob, list(others), "UNION", **kw)


def intersect(ob, other, **kw):
    return boolean(ob, [other], "INTERSECT", **kw)


def serrations(y0, y1, n, z0, z1, w, depth=0.01, groove=0.014, slant=0.0, x=0.0):
    """Vertical grooves on both sides of a slide/receiver of width w -> cutters."""
    cs = []
    for i in range(n):
        y = y0 + (y1 - y0) * i / max(1, n - 1)
        for sx in (-1, 1):
            b = box((x + sx * (w / 2 + 0.02 - depth), y, (z0 + z1) / 2), (0.04, groove, z1 - z0), bev=0)
            if slant:
                rotate(b, slant, "X", (0, y, (z0 + z1) / 2))
            cs.append(b)
    return cs


# --------------------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------------------


def box(center, size, bev=0.01, seg=1, angle=40.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=V(size), verts=bm.verts)
    bmesh.ops.translate(bm, vec=V(center), verts=bm.verts)
    ob = obj_from_bm(bm, "box")
    return bevel(ob, min(bev, min(size) * 0.45) if bev else 0, seg, angle)


def box2(p0, p1, **kw):
    """Box from two opposite corners."""
    c = [(a + b) / 2 for a, b in zip(p0, p1)]
    s = [abs(b - a) for a, b in zip(p0, p1)]
    return box(c, s, **kw)


def _clean_pts(pts):
    out = []
    for p in pts:
        if not out or (abs(p[0] - out[-1][0]) > 1e-6 or abs(p[1] - out[-1][1]) > 1e-6):
            out.append((float(p[0]), float(p[1])))
    if len(out) > 2 and abs(out[0][0] - out[-1][0]) < 1e-6 and abs(out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def _plane_point(axis, u, v, a):
    if axis == "x":
        return V((a, u, v))
    if axis == "y":
        return V((u, a, v))
    return V((u, v, a))


def prism(pts, axis="x", a0=-0.1, a1=0.1, bev=0.01, seg=1, angle=40.0):
    """Extrude a closed 2D polygon.

    axis='x': pts are (y, z), extruded from x=a0..a1   (side profiles)
    axis='y': pts are (x, z), extruded from y=a0..a1   (cross sections along the bore)
    axis='z': pts are (x, y), extruded from z=a0..a1   (top views)
    """
    pts = _clean_pts(pts)
    bm = bmesh.new()
    r0 = [bm.verts.new(_plane_point(axis, u, v, a0)) for u, v in pts]
    r1 = [bm.verts.new(_plane_point(axis, u, v, a1)) for u, v in pts]
    bm.faces.new(r0)
    bm.faces.new(list(reversed(r1)))
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([r0[i], r0[j], r1[j], r1[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = obj_from_bm(bm, "prism")
    return bevel(ob, bev, seg, angle)


def side(pts, w, x=0.0, **kw):
    """Side-profile prism of width w centred on x."""
    return prism(pts, "x", x - w / 2, x + w / 2, **kw)


def section(pts, y0, y1, **kw):
    """Cross-section (x, z) extruded along the bore from y0 to y1."""
    return prism(pts, "y", y0, y1, **kw)


def offset_polyline(pts, thick):
    """Thick 2D polyline -> closed polygon (mitred)."""
    pts = [V((p[0], p[1])) for p in _clean_pts(pts)]
    n = len(pts)
    left, right = [], []
    for i in range(n):
        if i == 0:
            d = (pts[1] - pts[0]).normalized()
            nrm = V((-d.y, d.x))
            k = 1.0
        elif i == n - 1:
            d = (pts[-1] - pts[-2]).normalized()
            nrm = V((-d.y, d.x))
            k = 1.0
        else:
            d0 = (pts[i] - pts[i - 1]).normalized()
            d1 = (pts[i + 1] - pts[i]).normalized()
            n0 = V((-d0.y, d0.x))
            n1 = V((-d1.y, d1.x))
            nrm = (n0 + n1)
            if nrm.length < 1e-6:
                nrm = n0
            nrm.normalize()
            k = 1.0 / max(0.35, nrm.dot(n0))
        left.append(pts[i] + nrm * thick / 2 * k)
        right.append(pts[i] - nrm * thick / 2 * k)
    return [tuple(p) for p in left] + [tuple(p) for p in reversed(right)]


def bar(pts, thick, w, x=0.0, axis="x", **kw):
    """A thick polyline (trigger guards, handles) extruded to width w."""
    poly = offset_polyline(pts, thick)
    return prism(poly, axis, x - w / 2, x + w / 2, **kw)


def _basis(d):
    d = V(d).normalized()
    up = V((0, 0, 1)) if abs(d.z) < 0.9 else V((1, 0, 0))
    u = up.cross(d).normalized()
    v = d.cross(u).normalized()
    return d, u, v


def lathe(p0, direction, prof, seg=20, closed=False, rot=0.0, bev=0.0, bseg=1, angle=40.0):
    """Solid of revolution. prof = [(t, r), ...] along `direction` starting at p0.
    Points with r == 0 collapse to the axis (caps)."""
    p0 = V(p0)
    d, u, v = _basis(direction)
    bm = bmesh.new()
    rings = []
    for t, r in prof:
        c = p0 + d * t
        if r < 1e-7:
            rings.append([bm.verts.new(c)])
        else:
            ring = []
            for i in range(seg):
                a = rot + 2 * math.pi * i / seg + math.pi / seg
                ring.append(bm.verts.new(c + (u * math.cos(a) + v * math.sin(a)) * r))
            rings.append(ring)
    pairs = list(zip(rings[:-1], rings[1:]))
    if closed:
        pairs.append((rings[-1], rings[0]))
    for A, B in pairs:
        if len(A) == 1 and len(B) == 1:
            continue
        if len(A) == 1:
            for i in range(seg):
                bm.faces.new([A[0], B[i], B[(i + 1) % seg]])
        elif len(B) == 1:
            for i in range(seg):
                bm.faces.new([A[i], A[(i + 1) % seg], B[0]])
        else:
            for i in range(seg):
                j = (i + 1) % seg
                bm.faces.new([A[i], A[j], B[j], B[i]])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = obj_from_bm(bm, "lathe")
    return bevel(ob, bev, bseg, angle)


def cyl(p0, p1, r, r1=None, seg=20, bev=0.0, bseg=1, rot=0.0):
    p0, p1 = V(p0), V(p1)
    L = (p1 - p0).length
    r1 = r if r1 is None else r1
    return lathe(p0, p1 - p0, [(0, 0), (0, r), (L, r1), (L, 0)], seg=seg, rot=rot, bev=bev, bseg=bseg)


def cyl_y(y0, y1, r, x=0.0, z=0.0, **kw):
    return cyl((x, y0, z), (x, y1, z), r, **kw)


def cyl_x(x0, x1, r, y=0.0, z=0.0, **kw):
    return cyl((x0, y, z), (x1, y, z), r, **kw)


def cyl_z(z0, z1, r, x=0.0, y=0.0, **kw):
    return cyl((x, y, z0), (x, y, z1), r, **kw)


def tube(p0, p1, ro, ri, seg=20, bev=0.0):
    p0, p1 = V(p0), V(p1)
    L = (p1 - p0).length
    return lathe(p0, p1 - p0, [(0, ri), (0, ro), (L, ro), (L, ri)], seg=seg, closed=True, bev=bev)


# 2D shape helpers ----------------------------------------------------------------------


def arc(cx, cy, r, a0, a1, n=8):
    """Points along an arc (degrees, inclusive)."""
    return [
        (cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
        for i in range(n + 1)
    ]


def rrect(cx, cy, w, h, r, n=3):
    r = min(r, w / 2 - 1e-4, h / 2 - 1e-4)
    x0, x1, y0, y1 = cx - w / 2 + r, cx + w / 2 - r, cy - h / 2 + r, cy + h / 2 - r
    pts = []
    pts += arc(x1, y0, r, -90, 0, n)
    pts += arc(x1, y1, r, 0, 90, n)
    pts += arc(x0, y1, r, 90, 180, n)
    pts += arc(x0, y0, r, 180, 270, n)
    return pts


def octagon(cx, cy, w, h, ch):
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    return [(x0 + ch, y0), (x1 - ch, y0), (x1, y0 + ch), (x1, y1 - ch), (x1 - ch, y1), (x0 + ch, y1), (x0, y1 - ch), (x0, y0 + ch)]


def clip_half(pts, nx, ny, d):
    """Clip a 2D polygon to the half-plane nx*u + ny*v >= d (Sutherland-Hodgman)."""
    out = []
    n = len(pts)
    for i in range(n):
        P, Q = pts[i], pts[(i + 1) % n]
        fp = nx * P[0] + ny * P[1] - d
        fq = nx * Q[0] + ny * Q[1] - d
        if fp >= 0:
            out.append(P)
        if (fp >= 0) != (fq >= 0):
            t = fp / (fp - fq)
            out.append((P[0] + (Q[0] - P[0]) * t, P[1] + (Q[1] - P[1]) * t))
    return out


def clip_box(pts, u0=None, u1=None, v0=None, v1=None):
    if u0 is not None:
        pts = clip_half(pts, 1, 0, u0)
    if u1 is not None:
        pts = clip_half(pts, -1, 0, -u1)
    if v0 is not None:
        pts = clip_half(pts, 0, 1, v0)
    if v1 is not None:
        pts = clip_half(pts, 0, -1, -v1)
    return pts


def axis_band(pts, top, a, L, t0, t1):
    """Part of a grip profile between fractions t0..t1 along its axis."""
    a, top = V(a), V(top)
    base = a.dot(top)
    pts = clip_half(pts, a.x, a.y, base + t0 * L)
    return clip_half(pts, -a.x, -a.y, -(base + t1 * L))


def axis_rrect(top, a, nf, L, t0, t1, f0, f1, r=0.03, n=3):
    """Rounded rectangle laid out in grip-local coordinates (t along the axis, f forward)."""
    top, a, nf = V(top), V(a), V(nf)
    loc = rrect((f0 + f1) / 2, -(t0 + t1) / 2 * L, f1 - f0, (t1 - t0) * L, r, n)
    return [tuple(top + nf * u - a * v) for u, v in loc]


def bezier(p0, p1, p2, p3, n=8):
    out = []
    for i in range(n + 1):
        t = i / n
        a = (1 - t) ** 3
        b = 3 * (1 - t) ** 2 * t
        c = 3 * (1 - t) * t * t
        d = t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def stadium_cutter(center, length, width, depth, normal="x", along="y", seg=3):
    """Rounded slot cutter (M-LOK style)."""
    cx, cy, cz = center
    if normal == "x":
        pts = rrect(cy, cz, length, width, width / 2 - 1e-3, seg) if along == "y" else rrect(cy, cz, width, length, width / 2 - 1e-3, seg)
        return prism(pts, "x", cx - depth / 2, cx + depth / 2, bev=0)
    if normal == "z":
        pts = rrect(cx, cy, width, length, width / 2 - 1e-3, seg) if along == "y" else rrect(cx, cy, length, width, width / 2 - 1e-3, seg)
        return prism(pts, "z", cz - depth / 2, cz + depth / 2, bev=0)
    pts = rrect(cx, cz, width, length, width / 2 - 1e-3, seg)
    return prism(pts, "y", cy - depth / 2, cy + depth / 2, bev=0)


# --------------------------------------------------------------------------------------
# Gun build context
# --------------------------------------------------------------------------------------

ROLE_OF_PIECE = {
    "Body": "Primary",
    "Furniture": "Secondary",
    "Metal": "Metal",
    "Wood": "Wood",
    "Tape": "Accent",
    "Glass": "Glass",
    "Reticle": "Reticle",
}

PIECE_ORDER = ["Body", "Furniture", "Wood", "Metal", "Mag", "Slide", "Pump", "Bolt", "Tape", "Glass", "Reticle"]


class Gun:
    def __init__(self, gid, kind):
        self.id = gid
        self.kind = kind  # "Primary" | "Secondary" | "Attachment"
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
            "Glass": "glass",
            "Reticle": "reticle",
        }
        self.roles = dict(ROLE_OF_PIECE)
        self.roles.update({"Mag": "Primary", "Slide": "Metal", "Pump": "Wood", "Bolt": "Metal"})
        self.points = OrderedDict()

    def add(self, piece, *objs):
        for o in objs:
            if isinstance(o, (list, tuple)):
                self.add(piece, *o)
            elif o is not None:
                self.parts.setdefault(piece, []).append(o)
        return objs[0] if len(objs) == 1 else objs

    # convenience aliases
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
        """Merge parts by piece name, set materials/shading/origins. Returns ordered objects."""
        out = []
        for piece in PIECE_ORDER + [p for p in self.parts if p not in PIECE_ORDER]:
            objs = self.parts.get(piece)
            if not objs:
                continue
            ob = join(objs, piece)
            ob.name = piece
            ob.data.name = f"{self.id}_{piece}"
            me = ob.data
            # tidy
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
            bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
            bm.to_mesh(me)
            bm.free()
            me.validate(clean_customdata=False)
            me.materials.clear()
            me.materials.append(material(self.mats[piece]))
            for p in me.polygons:
                p.use_smooth = True
            me.set_sharp_from_angle(angle=math.radians(32))
            # origin to bounding box centre
            xs = [v.co for v in me.vertices]
            lo = V((min(c.x for c in xs), min(c.y for c in xs), min(c.z for c in xs)))
            hi = V((max(c.x for c in xs), max(c.y for c in xs), max(c.z for c in xs)))
            cen = (lo + hi) / 2
            me.transform(Matrix.Translation(-cen))
            ob.location = cen
            ob["bbox_size"] = list(hi - lo)
            out.append(ob)
        return out


def tri_count(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


# --------------------------------------------------------------------------------------
# Shared sub-assemblies
# --------------------------------------------------------------------------------------


def picatinny(y0, y1, z, w=0.15, h=0.06, pitch=0.062, x=0.0, axis="top", slots=True):
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


def ar_lower(g, y_rear=-0.34, y_front=0.95, w=0.2, mw_front=0.9, mw_rear=0.5, mw_bot=0.06, top=0.42):
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
    # bolt catch
    g.metal(box((-w / 2 - 0.006, mw_rear - 0.02, 0.36), (0.014, 0.08, 0.05), bev=0.004))


def ar_grip(g, piece="Furniture"):
    pts, nf, a, L = grip_profile((0.1, 0.27), (-0.09, -0.27), 0.2, 0.22, nub=0.02, beaver=0.06)
    grip = side(pts, 0.15, bev=0.03, seg=2)
    cut(grip, grip_texture((0.1, 0.27), a, nf, L, 0.15, 0.22, n=8))
    g.add(piece, grip)


def ar_upper(g, y_rear=-0.34, y_front=0.95, w=0.22, top=0.62, bot=0.42, port=(0.05, 0.42)):
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
    g.body(box((w / 2 + 0.012, (port[0] + port[1]) / 2, BORE - 0.07), (0.012, port[1] - port[0] + 0.02, 0.06), bev=0.004))
    g.body(side([(port[0] - 0.12, BORE + 0.08), (port[0] - 0.01, BORE + 0.08), (port[0] - 0.01, BORE - 0.02), (port[0] - 0.05, BORE - 0.02)], 0.05, x=w / 2 + 0.01, bev=0.008))
    g.body(cyl((w / 2 - 0.02, -0.02, BORE + 0.04), (w / 2 + 0.03, -0.26, BORE + 0.04), 0.038, seg=16, bev=0.006))
    g.metal(cyl((w / 2 + 0.035, -0.29, BORE + 0.04), (w / 2 + 0.02, -0.24, BORE + 0.04), 0.03, seg=16, bev=0.006))
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
    g.metal(cyl_z(-0.03, 0.12, 0.03, y=y_back + 0.35, seg=12, bev=0.006))  # monopod


@register("SR25", "Primary")
def build_sr25(g):
    g.mats.update(Body="fde", Furniture="polymer", Mag="polymer")
    g.roles["Mag"] = "Secondary"
    ar_lower(g, y_front=0.98, mw_front=0.94, mw_rear=0.5, w=0.21)
    ar_grip(g)
    ar_upper(g, y_front=0.98, w=0.23)
    buffer_tube(g, -0.34, -1.25)
    prs_stock(g, -1.6)
    mlok_handguard(g, 0.98, 3.05, w=0.26, h=0.28, tape_at=(1.4, 1.52))
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
    rec = side(side_p, 0.21, bev=0.0)
    intersect(rec, section(rounded_section(0.21, -0.1, 0.4, 0.07), yr - 0.1, yf + 0.1, bev=0))
    bevel(rec, 0.012, 2)
    cut(rec, box((0.12, 0.78, 0.2), (0.08, 0.44, 0.17), bev=0.01), box((0, 1.02, -0.07), (0.15, 0.52, 0.06), bev=0.01))
    g.body(rec)
    g.metal(box((0.08, 0.78, 0.2), (0.02, 0.4, 0.14), bev=0.004))  # bolt in port
    g.body(picatinny(yr + 0.12, yf - 0.05, 0.38, w=0.14, h=0.05))
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
    g.metal(cyl_z(B + 0.05, B + 0.085, 0.012, y=3.44, seg=10))
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
    tp = lathe((0, 1.37, B - 0.105), (0, 1, 0), [(0, 0), (0, 0.098), (0.055, 0.098), (0.055, 0)], seg=20)
    scale(tp, (0.97, 1, 1.22), (0, 1.43, B - 0.105))
    g.tape(tp)
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
    cut(fh, [box((0, 1.25, B + 0.03), (0.014, 0.1, 0.03), bev=0), box((sx * 0.03, 1.25, B), (0.03, 0.1, 0.014), bev=0)] if False else [box((0, 1.25, B + 0.03), (0.014, 0.1, 0.03), bev=0)] + [box((sx * 0.03, 1.25, B), (0.03, 0.1, 0.014), bev=0) for sx in (-1, 1)])
    g.metal(fh)
    # folding foregrip (deployed)
    g.furn(box((0, 0.74, 0.24), (0.1, 0.18, 0.05), bev=0.012))
    fg = side([(0.66, 0.24), (0.82, 0.24), (0.83, -0.18), (0.8, -0.22), (0.7, -0.22), (0.67, -0.18)], 0.1, bev=0.03, seg=2)
    cut(fg, [box((0, 0.74, -0.02 - i * 0.07), (0.2, 0.24, 0.012), bev=0) if False else box((sx * 0.06, 0.745, -0.02 - i * 0.06), (0.03, 0.2, 0.014), bev=0) for i in range(3) for sx in (-1, 1)])
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
    bevel(body, 0.035, 2)
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


@register("ATT_RedDot", "Attachment")
def build_reddot(g):
    g.mats.update(Body="anodized")
    Z = 0.2
    rail_clamp(g, -0.11, 0.11, w=0.15)
    g.body(side([(-0.1, 0.05), (0.1, 0.05), (0.08, Z - 0.03), (-0.08, Z - 0.03)], 0.1, bev=0.012))
    g.body(lathe((0, -0.13, Z), (0, 1, 0), [(0, 0.05), (0, 0.068), (0.26, 0.068), (0.26, 0.05)], seg=24, closed=True, bev=0.006))
    g.body(lathe((0, -0.13, Z), (0, 1, 0), [(0, 0.05), (0, 0.072), (0.03, 0.072), (0.03, 0.05)], seg=24, closed=True))
    g.body(lathe((0, 0.1, Z), (0, 1, 0), [(0, 0.05), (0, 0.072), (0.03, 0.072), (0.03, 0.05)], seg=24, closed=True))
    g.body(cyl_z(Z + 0.06, Z + 0.1, 0.028, y=0.0, seg=14, bev=0.005))
    g.body(cyl_x(0.06, 0.1, 0.028, y=0.0, z=Z, seg=14, bev=0.005))
    g.add("Glass", cyl_y(0.095, 0.1, 0.05, z=Z, seg=24))
    g.add("Reticle", cyl_y(0.092, 0.094, 0.006, z=Z, seg=8))
    g.points.update(Aim=(0, -0.55, Z))


@register("ATT_Holo", "Attachment")
def build_holo(g):
    g.mats.update(Body="anodized")
    Z = 0.17
    rail_clamp(g, -0.12, 0.12, w=0.17, knob="right")
    g.body(box((0, -0.04, 0.085), (0.16, 0.36, 0.07), bev=0.015, seg=2))
    g.body(box((0, -0.18, 0.14), (0.14, 0.08, 0.14), bev=0.015, seg=2))  # rear controls
    hood = side(rrect(0.05, Z, 0.24, 0.0001 + 0.24, 0.02), 0.18, bev=0) if False else box((0, 0.05, Z), (0.18, 0.22, 0.2), bev=0.02, seg=2)
    cut(hood, box((0, 0.05, Z + 0.01), (0.14, 0.4, 0.15), bev=0.0))
    g.body(hood)
    for i in range(3):
        g.body(box((0, -0.2, 0.17 + i * 0.03 - 0.03), (0.06, 0.015, 0.018), bev=0.005))
    g.add("Glass", box((0, 0.14, Z + 0.01), (0.14, 0.006, 0.15), bev=0))
    g.add("Glass", box((0, -0.03, Z + 0.01), (0.14, 0.006, 0.15), bev=0))
    g.add("Reticle", tube((0, 0.13, Z), (0, 0.133, Z), 0.032, 0.027, seg=24))
    g.add("Reticle", cyl_y(0.13, 0.133, 0.004, z=Z, seg=8))
    g.points.update(Aim=(0, -0.55, Z))


@register("ATT_Scope4x", "Attachment")
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


@register("ATT_ScopeLong", "Attachment")
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


@register("ATT_Suppressor", "Attachment")
def build_suppressor(g):
    g.mats.update(Body="anodized")
    L = 0.85
    s = lathe((0, 0, 0), (0, 1, 0), [(0, 0), (0, 0.05), (0.05, 0.05), (0.08, 0.07), (L - 0.03, 0.07), (L, 0.06), (L, 0.016), (L - 0.02, 0)], seg=24, bev=0.005)
    cut(s, [tube((0, y, 0), (0, y + 0.012, 0), 0.08, 0.064, seg=24) for y in (0.12, 0.16, 0.2, L - 0.1)])
    cut(s, [box((sx * 0.07, 0.06, 0), (0.02, 0.05, 0.04), bev=0) for sx in (-1, 1)])
    g.body(s)
    g.points.update(MuzzleOffset=(0, L, 0))


@register("ATT_Compensator", "Attachment")
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


@register("ATT_VerticalGrip", "Attachment")
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


@register("ATT_AngledGrip", "Attachment")
def build_afg(g):
    g.mats.update(Body="polymer")
    under_clamp(g, -0.2, 0.2)
    pts = [(-0.26, -0.04), (0.22, -0.04), (0.2, -0.08)] + bezier((0.2, -0.08), (0.12, -0.12), (0.05, -0.2), (0.0, -0.24), 6)[1:] + [(-0.06, -0.24)] + bezier((-0.06, -0.24), (-0.12, -0.16), (-0.2, -0.08), (-0.26, -0.06), 6)[1:]
    afg = side(pts, 0.12, bev=0.03, seg=2)
    cut(afg, [box((sx * 0.06, 0.08 - i * 0.05, -0.1 - i * 0.02), (0.02, 0.02, 0.2), bev=0) for i in range(4) for sx in (-1, 1)])
    g.body(afg)


@register("ATT_Laser", "Attachment")
def build_laser(g):
    g.mats.update(Body="fde")
    # side-mounted: mount face at x=0, extends to +X (right side rail)
    g.body(prism([(-0.12, -0.065), (0.12, -0.065), (0.12, 0.065), (-0.12, 0.065)], "x", 0.0, 0.035, bev=0.008) if False else box((0.018, 0, 0), (0.036, 0.24, 0.13), bev=0.008))
    g.body(cyl_z(-0.08, 0.08, 0.02, x=0.02, y=0.0, seg=10))
    lb = box((0.1, 0.0, 0.0), (0.13, 0.34, 0.15), bev=0.018, seg=2)
    cut(lb, [cyl_y(0.15, 0.2, 0.025, x=0.1, z=0.035, seg=14), cyl_y(0.15, 0.2, 0.03, x=0.1, z=-0.03, seg=14)])
    g.body(lb)
    for i, yy in enumerate((-0.06, 0.04)):
        g.body(box((0.1, yy, 0.08), (0.05, 0.05, 0.016), bev=0.006))
    g.add("Glass", cyl_y(0.158, 0.165, 0.024, x=0.1, z=0.035, seg=14))
    g.add("Glass", cyl_y(0.158, 0.165, 0.029, x=0.1, z=-0.03, seg=14))
    g.points.update(Beam=(0.1, 0.17, 0.035))


# ======================================================================================
# Pipeline: scene, export, metadata, render
# ======================================================================================


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mat_cache.clear()
    scn = bpy.context.scene
    scn.unit_settings.system = "NONE"
    work = bpy.data.collections.new("Work")
    scn.collection.children.link(work)
    lineup = bpy.data.collections.new("Lineup")
    scn.collection.children.link(lineup)
    _work["coll"] = work
    _work["lineup"] = lineup


def clear_work():
    for ob in list(_work["coll"].objects):
        delete(ob)


def g3(v):
    """Blender -> game coordinates."""
    return (v[0], v[2], -v[1])


def gsize(s):
    return (s[0], s[2], s[1])


def fmt(v):
    def f(x):
        x = round(x, 3)
        if x == 0:
            x = 0.0
        return f"{x:.3f}"

    return f"Vector3.new({f(v[0])}, {f(v[1])}, {f(v[2])})"


def export_glb(objs, path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_extras=False,
        export_animations=False,
        export_skins=False,
        export_morph=False,
        export_cameras=False,
        export_lights=False,
    )


def piece_meta(g, objs):
    rows = []
    for o in objs:
        s = o["bbox_size"]
        rows.append(
            {
                "Name": o.name,
                "Role": g.roles.get(o.name, "Primary"),
                "Center": g3(o.location),
                "Size": gsize(s),
                "Triangles": tri_count(o),
            }
        )
    return rows


def setup_render():
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 24
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.max_bounces = 4
    try:
        scn.cycles.use_denoising = True
        scn.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    scn.render.resolution_x = 900
    scn.render.resolution_y = 500
    scn.render.resolution_percentage = 100
    scn.render.film_transparent = False
    scn.render.image_settings.file_format = "PNG"
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.05, 0.05, 0.055, 1)
    bg.inputs["Strength"].default_value = 1.0
    scn.world = world

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("Cam", cam_data)
    scn.collection.objects.link(cam)
    scn.camera = cam

    def area(name, energy, size, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        scn.collection.objects.link(lo)
        return lo

    lights = {
        "key": area("Key", 900, 4.0),
        "fill": area("Fill", 300, 6.0, (0.85, 0.9, 1.0)),
        "rim": area("Rim", 700, 3.0, (1.0, 0.95, 0.9)),
        "top": area("Top", 350, 6.0),
    }
    return cam, lights


def look_at(ob, target):
    d = V(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def frame_camera(cam, lights, lo, hi, view_dir=(1.0, 0.42, 0.3), aspect=900 / 500, margin=1.1):
    lo, hi = V(lo), V(hi)
    center = (lo + hi) / 2
    vd = V(view_dir).normalized()
    radius = (hi - lo).length
    cam.location = center + vd * (radius * 3 + 5)
    look_at(cam, center)
    # fit ortho scale by projecting bbox corners on camera axes
    M = cam.rotation_euler.to_matrix()
    right, up = M @ V((1, 0, 0)), M @ V((0, 1, 0))
    xs, ys = [], []
    for cx in (lo.x, hi.x):
        for cy in (lo.y, hi.y):
            for cz in (lo.z, hi.z):
                p = V((cx, cy, cz)) - center
                xs.append(p.dot(right))
                ys.append(p.dot(up))
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    off = right * (max(xs) + min(xs)) / 2 + up * (max(ys) + min(ys)) / 2
    cam.location += off
    cam.data.ortho_scale = (max(w, h * aspect) if aspect >= 1 else max(h, w / aspect)) * margin
    cam.data.clip_end = radius * 10 + 50
    size = max(radius, 1.0)
    # studio lights relative to subject
    lights["key"].location = center + V((2.0, 1.2, 2.4)) * size
    lights["fill"].location = center + V((-1.5, 2.0, 0.8)) * size
    lights["rim"].location = center + V((-0.6, -2.4, 1.6)) * size
    lights["top"].location = center + V((0.3, 0.0, 3.0)) * size
    for k, lo_ in lights.items():
        look_at(lo_, center)
        lo_.data.size = size * (1.5 if k != "top" else 3)
        base = {"key": 420, "fill": 130, "rim": 260, "top": 160}[k]
        lo_.data.energy = base * size * size


def render_to(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def bbox_of(objs):
    lo = V((1e9, 1e9, 1e9))
    hi = V((-1e9, -1e9, -1e9))
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ V(c)
            lo = V((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = V((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return lo, hi


def archive(objs, gid, offset):
    for o in objs:
        o.name = f"{gid}_{o.name}"
        for c in list(o.users_collection):
            c.objects.unlink(o)
        _work["lineup"].objects.link(o)
        o.location += V(offset)


def add_label(text, loc, size=0.28):
    cu = bpy.data.curves.new("lbl_" + text, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new("lbl_" + text, cu)
    _work["lineup"].objects.link(ob)
    ob.location = V(loc)
    ob.rotation_euler = (math.radians(90), 0, math.radians(90))
    m = bpy.data.materials.new("lbl")
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
    b.inputs["Emission Color"].default_value = (1, 1, 1, 1)
    b.inputs["Emission Strength"].default_value = 0.6
    cu.materials.append(m)
    return ob


def lua_points(points, keys):
    lines = []
    for k in keys:
        v = points.get(k)
        if v is None:
            continue
        lines.append(f"\t\t\t\t{k} = {fmt(g3(v))},")
    return lines


GUN_POINT_KEYS = ["Muzzle", "Aim", "LeftHand", "Optic", "Underbarrel", "MuzzleMount", "Side", "MagWell"]
ATT_POINT_KEYS = ["Aim", "MuzzleOffset", "Beam"]


def write_lua(gun_meta, att_meta):
    L = ["-- Generated by tools/blender/build_guns.py. Do not edit by hand.", "-- All vectors are in game space (studs): +X right, +Y up, -Z forward (barrel), origin = pistol-grip centre.", "return {", "\tGuns = {"]
    for gid, m in gun_meta.items():
        L.append(f"\t\t{gid} = {{")
        L.append(f"\t\t\tLength = {m['Length']:.3f},")
        L.append("\t\t\tPieces = {")
        for p in m["Pieces"]:
            L.append(
                f'\t\t\t\t{{ Name = "{p["Name"]}", Role = "{p["Role"]}", Center = {fmt(p["Center"])}, Size = {fmt(p["Size"])}, Triangles = {p["Triangles"]} }},'
            )
        L.append("\t\t\t},")
        L.append("\t\t\tPoints = {")
        L += ["\t" + s[1:] if False else s for s in lua_points(m["Points"], GUN_POINT_KEYS)]
        L.append("\t\t\t},")
        L.append("\t\t},")
    L.append("\t},")
    L.append("\tAttachments = {")
    for gid, m in att_meta.items():
        L.append(f"\t\t{gid} = {{")
        L.append("\t\t\tPieces = {")
        for p in m["Pieces"]:
            L.append(
                f'\t\t\t\t{{ Name = "{p["Name"]}", Role = "{p["Role"]}", Center = {fmt(p["Center"])}, Size = {fmt(p["Size"])}, Triangles = {p["Triangles"]} }},'
            )
        L.append("\t\t\t},")
        L.append("\t\t\tPoints = {")
        L += lua_points(m["Points"], ATT_POINT_KEYS)
        L.append("\t\t\t},")
        L.append("\t\t},")
    L.append("\t},")
    L.append("}")
    with open(LUA_PATH, "w", newline="\n") as f:
        f.write("\n".join(L) + "\n")


def main(argv):
    only = [a for a in argv if not a.startswith("-")]
    os.makedirs(MESH_DIR, exist_ok=True)
    os.makedirs(RENDER_DIR, exist_ok=True)
    reset_scene()
    cam, lights = setup_render()
    gun_meta, att_meta = OrderedDict(), OrderedDict()
    summary = []
    gi = ai = 0
    for gid, (kind, fn) in BUILDERS.items():
        if only and gid not in only:
            continue
        g = Gun(gid, kind)
        fn(g)
        objs = g.finish()
        clear_work_except(objs)
        tris = {o.name: tri_count(o) for o in objs}
        total = sum(tris.values())
        summary.append((gid, total, tris))
        for n, t in tris.items():
            if t > TRI_LIMIT_OBJECT:
                print(f"WARNING {gid}.{n} has {t} triangles (> {TRI_LIMIT_OBJECT})")
        if total > TRI_LIMIT_GUN:
            print(f"WARNING {gid} has {total} triangles (> {TRI_LIMIT_GUN})")
        export_glb(objs, os.path.join(MESH_DIR, gid + ".glb"))
        lo, hi = bbox_of(objs)
        meta = {"Pieces": piece_meta(g, objs), "Points": g.points}
        if kind == "Attachment":
            att_meta[gid] = meta
            offset = (0, (ai % 3) * 3.0, -(ai // 3) * 1.6)
            off = V((0, 30 + (ai % 3) * 2.6, -(ai // 3) * 1.5)) - V((0, (lo.y + hi.y) / 2, (lo.z + hi.z) / 2))
            archive(objs, gid, off)
            add_label(gid.replace("ATT_", ""), V((0.6, 30 + (ai % 3) * 2.6, -(ai // 3) * 1.5 - 0.62)), 0.16)
            ai += 1
        else:
            meta["Length"] = hi.y - lo.y
            gun_meta[gid] = meta
            _work["lineup"].hide_render = True
            frame_camera(cam, lights, lo, hi)
            render_to(os.path.join(RENDER_DIR, gid + ".png"))
            _work["lineup"].hide_render = False
            col, row = gi % 2, gi // 2
            target = V((0, col * 6.2, -row * 1.9))
            off = target - V((0, (lo.y + hi.y) / 2, (lo.z + hi.z) / 2))
            archive(objs, gid, off)
            add_label(gid, target + V((0.5, 0, -0.78)), 0.24)
            gi += 1
        print(f"built {gid}: {total} tris {tris}")
    # lineup renders
    if not only or "--lineup" in argv:
        coll = _work["lineup"]
        guns = [o for o in coll.objects if o.type == "MESH" and o.location.y < 25]
        if guns:
            lo, hi = bbox_of(guns)
            lo.z -= 0.6
            scn = bpy.context.scene
            scn.render.resolution_x, scn.render.resolution_y = 1800, 2000
            frame_camera(cam, lights, lo, hi, view_dir=(1.0, 0.0, 0.12), aspect=1800 / 2000, margin=1.04)
            for o in coll.objects:
                o.hide_render = o.location.y > 25
            render_to(os.path.join(RENDER_DIR, "lineup.png"))
        atts = [o for o in coll.objects if o.type == "MESH" and o.location.y > 25]
        if atts:
            lo, hi = bbox_of(atts)
            lo.z -= 0.4
            scn = bpy.context.scene
            scn.render.resolution_x, scn.render.resolution_y = 1200, 900
            frame_camera(cam, lights, lo, hi, view_dir=(1.0, 0.35, 0.3), aspect=1200 / 900, margin=1.08)
            for o in coll.objects:
                o.hide_render = o.location.y < 25
            render_to(os.path.join(RENDER_DIR, "attachments.png"))
    if not only:
        write_lua(gun_meta, att_meta)
    print("\nSUMMARY")
    for gid, total, tris in summary:
        print(f"  {gid:16s} {total:6d}  " + ", ".join(f"{k}={v}" for k, v in tris.items()))


def clear_work_except(keep):
    keep = set(o.name for o in keep)
    for ob in list(_work["coll"].objects):
        if ob.name not in keep:
            delete(ob)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    main(argv)
