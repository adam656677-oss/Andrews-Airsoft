"""
meshkit: procedural hard-surface modelling helpers for the Blender generators.

All geometry is built directly in world space as separate mesh objects; modifiers
(bevel, boolean) are applied immediately so every helper returns a plain mesh.

Quality knobs (set by the generator before building):
    QUALITY["seg"]   multiplier for round segment counts (cylinders, lathes)
    QUALITY["bevel"] extra bevel segments added to every bevel
"""

import math

import bpy  # noqa: I001
import bmesh
from mathutils import Matrix, Vector

QUALITY = {"seg": 1.0, "bevel": 0, "min_seg": 8}
# --------------------------------------------------------------------------------------
# Low level mesh helpers (all geometry is built directly in world space)
# --------------------------------------------------------------------------------------

V = Vector
WORK = {"coll": None, "lineup": None}


def _link(ob):
    coll = WORK["coll"] or bpy.context.scene.collection
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
        seg = seg + QUALITY["bevel"]
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
    if seg > 6:  # 6 or fewer segments = intentional polygon (hex recess etc.)
        seg = max(QUALITY["min_seg"], int(round(seg * QUALITY["seg"])))
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
    n = max(1, int(round(n * QUALITY["seg"])))
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
    n = max(2, int(round(n * QUALITY["seg"])))
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

