"""propkit: shared helpers for procedural prop generators (geometry, bake, export, renders).

Used by Tools/Blender/club/build_club.py. Follows Tools/Blender/CONVENTIONS.md:
front = +X, up = +Z, metres; one FBX per piece with its origin at the asset origin
(floor-centre of the footprint); DirectX normal maps; ORM = AO/Roughness/Metallic.

Everything is built in asset space. Parts are separate objects tagged with a piece name;
`Asset.finish()` applies modifiers, joins each piece, unwraps, bakes and exports it.
"""

import bpy
import bmesh
import math
import os
import json
import time
import zlib
import numpy as np
from mathutils import Vector as V, Matrix, Euler

from propkit_mats import MATS, build_recipe_material, aux_material, NB  # noqa: E402

# --------------------------------------------------------------------------------------
# Scene
# --------------------------------------------------------------------------------------

STATE = {"coll": None}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 1.0
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    coll = bpy.data.collections.new("Build")
    scn.collection.children.link(coll)
    STATE["coll"] = coll
    return scn


def link(ob, coll=None):
    (coll or STATE["coll"]).objects.link(ob)
    return ob


def delete_objects(objs):
    for o in list(objs):
        me = o.data if o.type == "MESH" else None
        bpy.data.objects.remove(o, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


# --------------------------------------------------------------------------------------
# 2D helpers
# --------------------------------------------------------------------------------------


def round_poly(pts, r, closed=True, iters=2):
    """Corner-cutting fillet for 2D/3D polylines: rounds every corner with radius ~r."""
    P = [V(p) for p in pts]
    for it in range(iters):
        rr = r / (2 ** it) * (1.0 if it == 0 else 0.9)
        out = []
        n = len(P)
        rng = range(n) if closed else range(n)
        for i in rng:
            if not closed and (i == 0 or i == n - 1):
                out.append(P[i])
                continue
            a, p, c = P[i - 1], P[i], P[(i + 1) % n]
            da, dc = (a - p), (c - p)
            la, lc = da.length, dc.length
            if la < 1e-9 or lc < 1e-9:
                out.append(p)
                continue
            k = min(rr, la * 0.45, lc * 0.45)
            out.append(p + da / la * k)
            out.append(p + dc / lc * k)
        P = out
    return [tuple(p) for p in P]


def circle_pts(r, n=16, rx=None, start=0.0):
    rx = r if rx is None else rx
    return [(rx * math.cos(start + 2 * math.pi * i / n), r * math.sin(start + 2 * math.pi * i / n)) for i in range(n)]


def rrect_pts(w, h, r, n=4):
    """Rounded rectangle centred at origin, CCW."""
    r = min(r, w / 2 - 1e-5, h / 2 - 1e-5)
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def catmull(pts, n=8, closed=False):
    """Catmull-Rom spline through points (2D or 3D)."""
    P = [V(p) if len(p) == 3 else V((p[0], p[1], 0)) for p in pts]
    out = []
    m = len(P)
    segs = m if closed else m - 1
    for i in range(segs):
        p0 = P[(i - 1) % m] if closed else P[max(i - 1, 0)]
        p1 = P[i % m]
        p2 = P[(i + 1) % m]
        p3 = P[(i + 2) % m] if closed else P[min(i + 2, m - 1)]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1])
    return [tuple(p) for p in out]


def rot_matrix(rot):
    if rot is None:
        return Matrix.Identity(4)
    if isinstance(rot, Matrix):
        return rot.to_4x4()
    return Euler([math.radians(a) for a in rot], "XYZ").to_matrix().to_4x4()


# --------------------------------------------------------------------------------------
# Asset builder
# --------------------------------------------------------------------------------------


class Piece:
    def __init__(self, name, kind="Static", res=2048, slot=None, glass=False, emissive=False, tileable=False, bake=True):
        self.name = name
        self.kind = kind
        self.res = res
        self.slot = slot
        self.glass = glass
        self.emissive = emissive
        self.tileable = tileable
        self.bake = bake


class Asset:
    def __init__(self, aid, res=2048, collision="Box", edge=0.004, ao_dist=0.25, group="Club", mask=False):
        self.id = aid
        self.res = res
        self.collision = collision
        self.edge = edge
        self.ao_dist = ao_dist
        self.group = group
        self.mask = mask
        self.parts = []
        self.points = {}
        self.pieces = {"Body": Piece("Body", "Body", res)}
        self.cur = "Body"
        self.preview = {}  # piece -> dict(tint=(r,g,b), emit=(r,g,b,strength), glass=dict)
        self.lights = []  # callables(scene) adding practical lights for the product render
        self.view = None
        self.lens = 60
        self.margin = 1.10

    # -- pieces ---------------------------------------------------------------------
    def piece(self, name, kind="Static", res=None, **kw):
        if name not in self.pieces:
            self.pieces[name] = Piece(name, kind, res or self.res, **kw)
        self.cur = name
        return self

    def point(self, name, p):
        self.points[name] = tuple(p)

    # -- object creation ------------------------------------------------------------
    def _obj(self, me, mat, at=(0, 0, 0), rot=None, piece=None, smooth=40, bevel=None, segs=2, gax=None, attrs=None, sub=0, wn=False):
        ob = bpy.data.objects.new(f"{self.id}_part", me)
        link(ob)
        ob.matrix_world = Matrix.Translation(V(at)) @ rot_matrix(rot)
        ob["piece"] = piece or self.cur
        if mat:
            me.materials.append(get_mat(mat))
        if smooth:
            me.shade_smooth()
            if smooth < 180:
                me.set_sharp_from_angle(angle=math.radians(smooth))
        if sub:
            m = ob.modifiers.new("sub", "SUBSURF")
            m.levels = sub
            m.render_levels = sub
        if bevel:
            m = ob.modifiers.new("bev", "BEVEL")
            m.width = bevel
            m.segments = segs
            m.limit_method = "ANGLE"
            m.angle_limit = math.radians(35)
            m.use_clamp_overlap = True
            m.harden_normals = True
            m.miter_outer = "MITER_ARC"
        if wn:
            m = ob.modifiers.new("wn", "WEIGHTED_NORMAL")
            m.keep_sharp = True
        if gax is not None:
            ob["a_gax"] = float(gax)
        if attrs:
            for k, v in attrs.items():
                ob["a_" + k] = float(v)
        self.parts.append(ob)
        return ob

    def dup(self, ob, at=(0, 0, 0), rot=None, piece=None, attrs=None, mirror_y=False):
        o2 = ob.copy()
        link(o2)
        if mirror_y:
            o2.data = ob.data.copy()
            o2.data.transform(Matrix.Scale(-1, 4, (0, 1, 0)))
            o2.data.flip_normals()
        o2.matrix_world = Matrix.Translation(V(at)) @ rot_matrix(rot) @ ob.matrix_world
        if piece:
            o2["piece"] = piece
        if attrs:
            for k, v in attrs.items():
                o2["a_" + k] = float(v)
        self.parts.append(o2)
        return o2

    def mesh(self, verts, faces, mat, recalc=True, **kw):
        me = bpy.data.meshes.new("m")
        me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
        me.validate()
        if recalc:
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
            bm.free()
        return self._obj(me, mat, **kw)

    def _bm_obj(self, bm, mat, **kw):
        me = bpy.data.meshes.new("m")
        bm.to_mesh(me)
        bm.free()
        return self._obj(me, mat, **kw)

    def box(self, size, at=(0, 0, 0), mat="steel", bevel=0.004, segs=2, rot=None, **kw):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=V(size), verts=bm.verts)
        return self._bm_obj(bm, mat, at=at, rot=rot, bevel=bevel, segs=segs, **kw)

    def cyl(self, r, h, at=(0, 0, 0), mat="steel", n=32, r2=None, axis="Z", bevel=0.003, segs=2, rot=None, caps=True, **kw):
        """Cylinder whose base sits at `at` (extends +h along axis)."""
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=n, radius1=r, radius2=(r if r2 is None else r2), depth=h)
        bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
        R = {"Z": Matrix.Identity(4), "X": Matrix.Rotation(math.pi / 2, 4, "Y"), "Y": Matrix.Rotation(-math.pi / 2, 4, "X")}[axis]
        bmesh.ops.transform(bm, matrix=R, verts=bm.verts)
        return self._bm_obj(bm, mat, at=at, rot=rot, bevel=bevel, segs=segs, **kw)

    def sphere(self, r, at=(0, 0, 0), mat="steel", seg=24, rings=12, scale=(1, 1, 1), rot=None, **kw):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
        bmesh.ops.scale(bm, vec=V(scale), verts=bm.verts)
        kw.setdefault("smooth", 180)
        return self._bm_obj(bm, mat, at=at, rot=rot, **kw)

    def lathe(self, prof, at=(0, 0, 0), mat="steel", n=32, axis="Z", rot=None, cap=True, smooth=40, **kw):
        """Revolve a (r, z) profile around the local Z axis. r==0 endpoints close to a pole."""
        verts, faces = [], []
        rings = []
        for (r, z) in prof:
            if r <= 1e-7:
                verts.append((0, 0, z))
                rings.append([len(verts) - 1])
            else:
                idx = []
                for i in range(n):
                    a = 2 * math.pi * i / n
                    verts.append((r * math.cos(a), r * math.sin(a), z))
                    idx.append(len(verts) - 1)
                rings.append(idx)
        for a, b in zip(rings[:-1], rings[1:]):
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                for i in range(n):
                    faces.append((a[0], b[(i + 1) % n], b[i]))
            elif len(b) == 1:
                for i in range(n):
                    faces.append((a[i], a[(i + 1) % n], b[0]))
            else:
                for i in range(n):
                    faces.append((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
        if cap:
            if len(rings[0]) > 1:
                faces.append(tuple(reversed(rings[0])))
            if len(rings[-1]) > 1:
                faces.append(tuple(rings[-1]))
        R = {"Z": Matrix.Identity(3), "X": Matrix.Rotation(math.pi / 2, 3, "Y"), "Y": Matrix.Rotation(-math.pi / 2, 3, "X")}[axis]
        verts = [R @ V(v) for v in verts]
        return self.mesh(verts, faces, mat, at=at, rot=rot, smooth=smooth, **kw)

    def sweep(self, path, prof=None, r=0.01, n=12, mat="steel", closed=False, cap=True, scales=None, at=(0, 0, 0), rot=None, up=None, twist=0.0, smooth=60, **kw):
        """Sweep a closed 2D profile along a 3D path with parallel-transport frames."""
        P = [V(p) for p in path]
        m = len(P)
        prof = prof or circle_pts(r, n)
        T = []
        for i in range(m):
            if closed:
                t = P[(i + 1) % m] - P[i - 1]
            else:
                t = P[min(i + 1, m - 1)] - P[max(i - 1, 0)]
            T.append(t.normalized() if t.length > 1e-12 else V((1, 0, 0)))
        ref = V(up) if up else (V((0, 0, 1)) if abs(T[0].z) < 0.9 else V((1, 0, 0)))
        N = (ref - T[0] * ref.dot(T[0])).normalized()
        frames = []
        for i in range(m):
            if i > 0:
                q = T[i - 1].rotation_difference(T[i])
                N = q @ N
                N = (N - T[i] * N.dot(T[i])).normalized()
            B = T[i].cross(N)
            frames.append((N, B))
        verts, faces = [], []
        k = len(prof)
        for i in range(m):
            Nn, Bb = frames[i]
            s = scales[i] if scales else 1.0
            a = twist * i / max(m - 1, 1)
            ca, sa = math.cos(a), math.sin(a)
            for (x, y) in prof:
                xr, yr = x * ca - y * sa, x * sa + y * ca
                verts.append(P[i] + (Nn * xr + Bb * yr) * s)
        rows = m if closed else m - 1
        for i in range(rows):
            i2 = (i + 1) % m
            for j in range(k):
                faces.append((i * k + j, i * k + (j + 1) % k, i2 * k + (j + 1) % k, i2 * k + j))
        if cap and not closed:
            faces.append(tuple(range(k - 1, -1, -1)))
            faces.append(tuple((m - 1) * k + j for j in range(k)))
        return self.mesh(verts, faces, mat, at=at, rot=rot, smooth=smooth, **kw)

    def prism(self, poly, depth, at=(0, 0, 0), mat="steel", plane="XY", rot=None, bevel=0.003, segs=2, z0=0.0, **kw):
        """Extrude a CCW 2D polygon by depth.
        XY: poly (x, y), extruded along +Z from z0.  XZ: poly (x, z), extruded along Y, centred.
        YZ: poly (y, z), extruded along X, centred."""
        k = len(poly)
        loc = []
        for d in (0.0, depth):
            for (u, v) in poly:
                loc.append((u, v, d))
        faces = [tuple(range(k - 1, -1, -1)), tuple(range(k, 2 * k))]
        for j in range(k):
            faces.append((j, (j + 1) % k, k + (j + 1) % k, k + j))
        if plane == "XY":
            verts = [(u, v, d + z0) for (u, v, d) in loc]
        elif plane == "XZ":
            verts = [(u, depth / 2 - d, v) for (u, v, d) in loc]
        else:
            verts = [(d - depth / 2, u, v) for (u, v, d) in loc]
        return self.mesh(verts, faces, mat, at=at, rot=rot, bevel=bevel, segs=segs, **kw)

    def vattr(self, ob, name, fn):
        """Per-vertex FLOAT_VECTOR attribute from fn(local_co) -> (a, b, c) (used for decals/labels)."""
        me = ob.data
        at = me.attributes.get(name) or me.attributes.new(name, "FLOAT_VECTOR", "POINT")
        vals = np.array([fn(v.co) for v in me.vertices], dtype=np.float32).ravel()
        at.data.foreach_set("vector", vals)
        return ob

    def loft(self, rings, mat="steel", closed=True, cap=True, at=(0, 0, 0), rot=None, smooth=180, **kw):
        verts, faces = [], []
        k = len(rings[0])
        for ring in rings:
            verts.extend(tuple(p) for p in ring)
        for i in range(len(rings) - 1):
            for j in range(k if closed else k - 1):
                j2 = (j + 1) % k
                faces.append((i * k + j, i * k + j2, (i + 1) * k + j2, (i + 1) * k + j))
        if cap and closed:
            faces.append(tuple(range(k - 1, -1, -1)))
            faces.append(tuple((len(rings) - 1) * k + j for j in range(k)))
        return self.mesh(verts, faces, mat, at=at, rot=rot, smooth=smooth, **kw)

    def grid(self, fn, nu, nv, mat="steel", closed_u=False, at=(0, 0, 0), rot=None, smooth=180, **kw):
        """Parametric surface fn(u, v) -> xyz, u,v in [0,1]."""
        verts, faces = [], []
        cu = nu if closed_u else nu + 1
        for j in range(nv + 1):
            for i in range(cu):
                verts.append(fn(i / nu, j / nv))
        for j in range(nv):
            for i in range(nu):
                i2 = (i + 1) % cu if closed_u else i + 1
                faces.append((j * cu + i, j * cu + i2, (j + 1) * cu + i2, (j + 1) * cu + i))
        return self.mesh(verts, faces, mat, at=at, rot=rot, smooth=smooth, **kw)

    def text(self, body, font, size, depth, at=(0, 0, 0), rot=None, mat="brass", bevel=0.0, align="CENTER", spacing=1.0, res=4, **kw):
        cu = bpy.data.curves.new("txt", "FONT")
        cu.body = body
        cu.font = load_font(font)
        cu.size = size
        cu.extrude = depth / 2
        cu.bevel_depth = bevel
        cu.bevel_resolution = 2
        cu.resolution_u = res
        cu.align_x = align
        cu.align_y = "BOTTOM"
        cu.space_character = spacing
        tob = bpy.data.objects.new("txt", cu)
        link(tob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(tob.evaluated_get(dg))
        bpy.data.objects.remove(tob)
        bpy.data.curves.remove(cu)
        me.transform(Matrix.Translation((0, 0, depth / 2)))
        return self._obj(me, mat, at=at, rot=rot, **kw)

    # -- finishing ----------------------------------------------------------------------
    def finish(self, out_dir, res_scale=1.0, do_bake=True, log=print):
        """Apply modifiers, join parts per piece, unwrap, bake, export. Returns {piece: object}."""
        os.makedirs(out_dir, exist_ok=True)
        result = {}
        attr_names = sorted({k[2:] for o in self.parts for k in o.keys() if k.startswith("a_")})
        for o in self.parts:
            m = o.modifiers.new("tri", "TRIANGULATE")
            m.quad_method = "SHORTEST_DIAGONAL"
            m.ngon_method = "BEAUTY"
            m.keep_custom_normals = True
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        by_piece = {}
        for o in self.parts:
            by_piece.setdefault(o["piece"], []).append(o)
        for pname, objs in by_piece.items():
            pc = self.pieces[pname]
            temps = []
            for o in objs:
                me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
                nf = len(me.polygons)
                for an in attr_names:
                    at = me.attributes.new(an, "FLOAT", "FACE")
                    at.data.foreach_set("value", np.full(nf, float(o.get("a_" + an, 0.0)), dtype=np.float32))
                t = bpy.data.objects.new("t", me)
                link(t)
                t.matrix_world = o.matrix_world.copy()
                temps.append(t)
            delete_objects(objs)
            target = bpy.data.objects.new(f"SM_{self.id}_{pname}", bpy.data.meshes.new(f"SM_{self.id}_{pname}"))
            link(target)
            bpy.ops.object.select_all(action="DESELECT")
            for t in temps:
                t.select_set(True)
            target.select_set(True)
            bpy.context.view_layer.objects.active = target
            bpy.ops.object.join()
            ob = bpy.context.view_layer.objects.active
            for i in reversed(range(len(ob.material_slots))):
                if ob.material_slots[i].material is None:
                    ob.active_material_index = i
                    bpy.ops.object.material_slot_remove()
            ob.name = f"SM_{self.id}_{pname}"
            ob["piece"] = pname
            ob["asset"] = self.id
            result[pname] = ob
        self.parts = []
        self.objects = result
        return result


# --------------------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------------------

_mat_cache = {}


def get_mat(name):
    m = bpy.data.materials.get("R_" + name)
    if m is None:
        m = build_recipe_material(name)
    return m


_fonts = {}


def load_font(path):
    f = _fonts.get(path)
    try:
        if f is not None and f.name in bpy.data.fonts:
            return f
    except ReferenceError:
        pass
    f = bpy.data.fonts.load(path if path and os.path.exists(path) else "<builtin>", check_existing=True)
    _fonts[path] = f
    return f


# --------------------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------------------


def new_image(name, w, h, float_buf=True, alpha=True, color=(0, 0, 0, 0)):
    im = bpy.data.images.get(name)
    if im is not None:
        bpy.data.images.remove(im)
    im = bpy.data.images.new(name, w, h, alpha=alpha, float_buffer=float_buf)
    im.colorspace_settings.name = "Non-Color"
    im.generated_color = color
    return im


def img_np(im):
    w, h = im.size
    a = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def np_to_image(name, arr):
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones((h, w, 1), np.float32)], axis=2)
    im = new_image(name, w, h, float_buf=True)
    im.pixels.foreach_set(np.ascontiguousarray(arr, dtype=np.float32).ravel())
    im.pack() if False else None
    return im


def save_png(arr, path, srgb=False):
    """Writes an (h, w, 3|4) float array (linear) to an 8-bit PNG. srgb applies the sRGB OETF."""
    h, w = arr.shape[:2]
    a = np.clip(arr[..., :3], 0, 1).astype(np.float32)
    if srgb:
        a = np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)
    out = np.ones((h, w, 4), np.float32)
    out[..., :3] = a
    im = bpy.data.images.new("save_tmp", w, h, alpha=False, float_buffer=False)
    im.colorspace_settings.name = "Non-Color"
    im.pixels.foreach_set(out.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    sc = bpy.context.scene.render.image_settings
    im.save()
    bpy.data.images.remove(im)


def blur(a, r):
    """Separable box blur (applied twice ~ gaussian) on HxWxC float array."""
    if r < 1:
        return a
    for _ in range(2):
        for ax in (0, 1):
            c = np.cumsum(np.pad(a, [(r + 1, r) if i == ax else (0, 0) for i in range(a.ndim)], mode="edge"), axis=ax, dtype=np.float32)
            if ax == 0:
                a = (c[2 * r + 1 :] - c[: -2 * r - 1]) / (2 * r + 1)
            else:
                a = (c[:, 2 * r + 1 :] - c[:, : -2 * r - 1]) / (2 * r + 1)
    return a


def upsample(a, f):
    if f == 1:
        return a
    a = np.repeat(np.repeat(a, f, axis=0), f, axis=1)
    return blur(a, max(1, f // 2))


def downsample(a, f):
    if f == 1:
        return a
    h, w = a.shape[:2]
    return a.reshape(h // f, f, w // f, f, -1).mean(axis=(1, 3))


# --------------------------------------------------------------------------------------
# Text masks (rasterised from font outlines, no PIL needed)
# --------------------------------------------------------------------------------------


def text_mask(text, font, w, h, pad=0.06, spacing=1.0, ss=2, lines_gap=1.25):
    """Returns an (h, w) float mask with `text` (may contain \\n) fitted and centred."""
    cu = bpy.data.curves.new("tm", "FONT")
    cu.body = text
    cu.font = load_font(font)
    cu.size = 1.0
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.space_character = spacing
    cu.space_line = lines_gap
    cu.resolution_u = 6
    cu.fill_mode = "BOTH"
    tob = bpy.data.objects.new("tm", cu)
    link(tob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tob.evaluated_get(dg))
    bpy.data.objects.remove(tob)
    bpy.data.curves.remove(cu)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    tris = np.array([[(l.vert.co.x, l.vert.co.y) for l in f.loops] for f in bm.faces], dtype=np.float64)
    bm.free()
    bpy.data.meshes.remove(me)
    W, H = w * ss, h * ss
    mask = np.zeros((H, W), np.float32)
    if len(tris) == 0:
        return np.zeros((h, w), np.float32)
    mn = tris.reshape(-1, 2).min(0)
    mx = tris.reshape(-1, 2).max(0)
    sz = mx - mn
    s = min(W * (1 - 2 * pad) / sz[0], H * (1 - 2 * pad) / sz[1])
    c = (mn + mx) / 2
    T = (tris - c) * s + np.array([W / 2, H / 2])
    for t in T:
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs = np.arange(x0, x1 + 1) + 0.5
        ys = np.arange(y0, y1 + 1) + 0.5
        X, Y = np.meshgrid(xs, ys)
        (ax, ay), (bx, by), (cx, cy) = t
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / d
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / d
        inside = (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
        mask[y0 : y1 + 1, x0 : x1 + 1] = np.maximum(mask[y0 : y1 + 1, x0 : x1 + 1], inside.astype(np.float32))
    return downsample(mask[..., None], ss)[..., 0]


# --------------------------------------------------------------------------------------
# UV + bake
# --------------------------------------------------------------------------------------


def unwrap(ob, res, angle=60, world_scale=None):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    if world_scale:
        # architecture: box-project at real-world scale (1 UV unit = world_scale metres)
        bm = bmesh.new()
        bm.from_mesh(me)
        uvl = bm.loops.layers.uv.active
        for f in bm.faces:
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            for l in f.loops:
                co = l.vert.co
                if ax == 0:
                    u, v = -co.y * math.copysign(1, n.x), co.z
                elif ax == 1:
                    u, v = co.x * math.copysign(1, n.y), co.z
                else:
                    u, v = co.x, co.y * math.copysign(1, n.z)
                l[uvl].uv = (u / world_scale, v / world_scale)
        bm.to_mesh(me)
        bm.free()
        return
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    margin = min(4.0 / res, 0.004)
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.0, correct_aspect=True, scale_to_bounds=False, margin_method="FRACTION")
    try:
        bpy.ops.uv.pack_islands(rotate=True, margin=margin, margin_method="FRACTION", shape_method="AABB")
    except Exception as e:  # pragma: no cover
        print("pack failed", e)
    bpy.ops.object.mode_set(mode="OBJECT")
    # guard: the packer occasionally leaves islands outside 0..1 -> refit uniformly
    uvl = me.uv_layers.active.data
    uv = np.empty(len(uvl) * 2, np.float32)
    uvl.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    lo, hi = uv.min(0), uv.max(0)
    if lo.min() < -1e-4 or hi.max() > 1.0 + 1e-4 or os.environ.get("PK_FORCE_REFIT"):
        m = margin * 0.5
        span = float((hi - lo).max())
        uv = ((uv - lo) / span * (1 - 2 * m) + m).astype(np.float32)
        bm = bmesh.new()
        bm.from_mesh(me)
        lay = bm.loops.layers.uv.active
        k = 0
        for f in bm.faces:
            for l in f.loops:
                l[lay].uv = (float(uv[l.index][0]), float(uv[l.index][1]))
        bm.to_mesh(me)
        bm.free()
        me.update()
        print(f"    uv refit: range {lo} {hi}")


def _set_bake_target(ob, im):
    for slot in ob.material_slots:
        m = slot.material
        if m is None:
            continue
        nt = m.node_tree
        n = nt.nodes.get("BAKE_TARGET")
        if n is None:
            n = nt.nodes.new("ShaderNodeTexImage")
            n.name = "BAKE_TARGET"
        n.image = im
        for x in nt.nodes:
            x.select = False
        n.select = True
        nt.nodes.active = n


def _set_output(ob, which):
    for slot in ob.material_slots:
        m = slot.material
        if m is None:
            continue
        for n in m.node_tree.nodes:
            if n.bl_idname == "ShaderNodeOutputMaterial":
                n.is_active_output = n.name == "OUT_" + which


def _bake(ob, typ, im, margin):
    scn = bpy.context.scene
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    _set_bake_target(ob, im)
    kw = dict(type=typ, margin=margin, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    if typ == "NORMAL":
        kw.update(normal_space="TANGENT", normal_r="POS_X", normal_g="NEG_Y", normal_b="POS_Z")
    bpy.ops.object.bake(**kw)


def bake_piece(ob, asset, piece, res, out_dir, log=print):
    """Bakes BC / N / ORM (+M) for a joined piece. Returns dict of file paths."""
    scn = bpy.context.scene
    scn.cycles.samples = 1
    scn.cycles.use_denoising = False
    scn.render.bake.margin = 0
    t0 = time.time()
    unwrap(ob, res)
    t_uv = time.time() - t0
    margin = max(2, int(round(8 * res / 4096)))
    aid, pn = asset.id, piece.name
    paths = {}
    # --- aux pass (edge + AO) at half resolution -------------------------------------
    ares = max(256, res // 2) if not (piece.glass or piece.emissive) else max(128, res // 4)
    aux_tgt = new_image("AUX_BAKE", ares, ares)
    saved = [s.material for s in ob.material_slots]
    am = aux_material(asset.edge, asset.ao_dist)
    for s in ob.material_slots:
        s.material = am
    _bake(ob, "EMIT", aux_tgt, max(2, margin // 2))
    for s, m in zip(ob.material_slots, saved):
        s.material = m
    aux = img_np(aux_tgt)
    cover = aux[..., 3:4].copy()
    rgb = aux[..., :3] * cover
    rb = max(1, ares // 512)
    sm = blur(rgb, rb) / np.maximum(blur(cover, rb), 1e-4)
    aux_s = np.where(cover > 0.5, sm, aux[..., :3])
    aux_full = upsample(aux_s, res // ares)
    if os.environ.get("PK_DEBUG_AUX"):
        save_png(aux_s, os.path.join(out_dir, f"_aux_{piece.name}.png"))
    auximg = bpy.data.images.get("AUX")
    if auximg is None:
        auximg = new_image("AUX", res, res)
    elif tuple(auximg.size) != (res, res):
        auximg.scale(res, res)
    a4 = np.ones((res, res, 4), np.float32)
    a4[..., :3] = aux_full
    auximg.pixels.foreach_set(a4.ravel())
    auximg.update()
    del a4, aux, sm, rgb
    bpy.data.images.remove(aux_tgt)
    # --- colour / data / normal passes ----------------------------------------------
    tgt = new_image("BAKE_TGT", res, res)
    t1 = time.time()
    _set_output(ob, "BC")
    _bake(ob, "EMIT", tgt, margin)
    bc = img_np(tgt)[..., :3].copy()
    _set_output(ob, "ORM")
    _bake(ob, "EMIT", tgt, margin)
    data = img_np(tgt)[..., :3].copy()
    _set_output(ob, "N")
    _bake(ob, "NORMAL", tgt, margin)
    nrm = img_np(tgt)[..., :3].copy()
    _set_output(ob, "BC")
    t_bake = time.time() - t1
    base = os.path.join(out_dir, f"T_{aid}_{pn}")
    save_png(bc, base + "_BC.png", srgb=True)
    ao = 1.0 - (1.0 - aux_full[..., 1]) * 0.9
    orm = np.stack([ao, np.clip(data[..., 1], 0.02, 1), data[..., 2]], axis=-1)
    save_png(orm, base + "_ORM.png")
    save_png(nrm, base + "_N.png")
    mres = min(1024, res)
    msk = downsample(data[..., 0:1], res // mres)[..., 0]
    if asset.mask and msk.max() > 0.01:
        m3 = np.stack([msk, np.zeros_like(msk), np.zeros_like(msk)], -1)
    else:
        m3 = np.zeros((mres, mres, 3), np.float32)
    save_png(m3, base + "_M.png")
    paths = {k: base + f"_{k}.png" for k in ("BC", "N", "ORM", "M")}
    bpy.data.images.remove(tgt)
    log(f"    bake {aid}.{pn}: {res}px uv {t_uv:.1f}s bake {t_bake:.1f}s total {time.time() - t0:.1f}s")
    return paths


# --------------------------------------------------------------------------------------
# Final + preview materials
# --------------------------------------------------------------------------------------


def textured_material(slot, paths, preview=None):
    preview = preview or {}
    m = bpy.data.materials.get(slot)
    if m is not None:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(slot)
    nt = m.node_tree
    nt.nodes.clear()
    nb = NB(nt)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])

    def tex(path, cs):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        n.image.colorspace_settings.name = cs
        return n

    bc = tex(paths["BC"], "sRGB")
    orm = tex(paths["ORM"], "Non-Color")
    nm = tex(paths["N"], "Non-Color")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(orm.outputs[0], sep.inputs[0])
    col = bc.outputs[0]
    if preview.get("tint") and os.path.exists(paths.get("M", "")):
        mk = tex(paths["M"], "Non-Color")
        ms = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(mk.outputs[0], ms.inputs[0])
        tint = [c / 0.75 for c in preview["tint"]]
        tinted = nb.mixc_op("MULTIPLY", 1.0, col, (*tint, 1))
        col = nb.mixc(ms.outputs[0], col, tinted)
        if preview.get("coat"):
            nt.links.new(ms.outputs[0], bsdf.inputs["Coat Weight"])
            bsdf.inputs["Coat Roughness"].default_value = 0.03
    ao_mul = nb.mixc_op("MULTIPLY", 0.6, col, nb.combine(sep.outputs[0], sep.outputs[0], sep.outputs[0]))
    nt.links.new(ao_mul, bsdf.inputs["Base Color"])
    nt.links.new(sep.outputs[1], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs[2], bsdf.inputs["Metallic"])
    # DirectX normal -> flip green for Blender (OpenGL)
    sn = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(nm.outputs[0], sn.inputs[0])
    inv = nb.sub(1.0, sn.outputs[1])
    cn = nt.nodes.new("ShaderNodeCombineColor")
    nt.links.new(sn.outputs[0], cn.inputs[0])
    nt.links.new(inv, cn.inputs[1])
    nt.links.new(sn.outputs[2], cn.inputs[2])
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(cn.outputs[0], nmap.inputs["Color"])
    nt.links.new(nmap.outputs[0], bsdf.inputs["Normal"])
    if preview.get("glass"):
        g = preview["glass"]
        bsdf.inputs["Transmission Weight"].default_value = g.get("trans", 1.0)
        bsdf.inputs["IOR"].default_value = g.get("ior", 1.45)
        if g.get("thin", True):
            try:
                bsdf.inputs["Thin Wall"].default_value = True
            except Exception:
                pass
        if g.get("rough") is not None:
            for l in list(bsdf.inputs["Roughness"].links):
                nt.links.remove(l)
            bsdf.inputs["Roughness"].default_value = g["rough"]
        if g.get("emit"):
            e = g["emit"]
            nt.links.new(ao_mul, bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = e
    if preview.get("emit"):
        r, gg, b, s = preview["emit"]
        bsdf.inputs["Emission Color"].default_value = (r, gg, b, 1)
        bsdf.inputs["Emission Strength"].default_value = s
    return m


def assign_single(ob, m):
    me = ob.data
    me.materials.clear()
    me.materials.append(m)
    for p in me.polygons:
        p.material_index = 0


# --------------------------------------------------------------------------------------
# Export + data
# --------------------------------------------------------------------------------------


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


def tri_count(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def bbox_of(objs):
    lo = V((1e9, 1e9, 1e9))
    hi = V((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ V(c)
            lo = V((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = V((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return lo, hi


def ue(v):
    return [round(v[0] * 100, 1) + 0.0, round(-v[1] * 100, 1) + 0.0, round(v[2] * 100, 1) + 0.0]


def update_json(path, aid, entry):
    data = {"Version": 1, "Assets": {}}
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    data.setdefault("Assets", {})[aid] = entry
    data["Assets"] = dict(sorted(data["Assets"].items()))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


# --------------------------------------------------------------------------------------
# Studio renders
# --------------------------------------------------------------------------------------


def setup_studio(back=(0.045, 0.045, 0.05)):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.render.image_settings.file_format = "PNG"
    scn.render.image_settings.color_depth = "8"
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    world = bpy.data.worlds.new("Studio")
    scn.world = world
    nt = world.node_tree
    nt.nodes.clear()
    nb = NB(nt)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    z = sep.outputs[2]
    top = nb.maprange(z, -0.1, 0.9, 0.0, 1.0, smooth=True)
    v = nb.add(0.008, nb.mul(top, 0.12))
    col = nb.combine(nb.mul(v, 0.95), nb.mul(v, 0.98), v)
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(col, bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scn.collection.objects.link(cam)
    scn.camera = cam
    cam.data.sensor_width = 36
    lights = {}
    for name, col_, shape in (("Key", (1.0, 0.95, 0.88), "RECTANGLE"), ("Fill", (0.82, 0.88, 1.0), "RECTANGLE"), ("Rim", (1.0, 0.98, 0.95), "RECTANGLE")):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = shape
        ld.color = col_
        lo = bpy.data.objects.new(name, ld)
        scn.collection.objects.link(lo)
        lights[name] = lo
    # cyclorama (floor curving up behind)
    prof = [(-1.0, 0.0)]
    for i in range(13):
        a = math.radians(90 * i / 12)
        prof.append((0.55 + 0.45 * math.sin(a) - 0.0, 0.45 - 0.45 * math.cos(a)))
    prof.append((1.0, 1.6))
    verts, faces = [], []
    for j, (x, z) in enumerate(prof):
        for y in (-1.0, 1.0):
            verts.append((-x, y, z))
    for j in range(len(prof) - 1):
        a, b = j * 2, (j + 1) * 2
        faces.append((a, a + 1, b + 1, b))
    me = bpy.data.meshes.new("cyc")
    me.from_pydata(verts, [], faces)
    me.shade_smooth()
    cyc = bpy.data.objects.new("Cyc", me)
    scn.collection.objects.link(cyc)
    cm = bpy.data.materials.new("Cyc")
    b = cm.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*back, 1)
    b.inputs["Roughness"].default_value = 0.55
    b.inputs["Specular IOR Level"].default_value = 0.3
    me.materials.append(cm)
    return {"cam": cam, "lights": lights, "cyc": cyc}


def look_at(ob, target):
    d = V(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def frame(st, lo, hi, view=(1.0, -0.62, 0.38), lens=70, aspect=16 / 9, margin=1.10, key_scale=1.0, cyc_rot=None):
    cam, L, cyc = st["cam"], st["lights"], st["cyc"]
    lo, hi = V(lo), V(hi)
    center = (lo + hi) / 2
    vd = V(view).normalized()
    cam.data.lens = lens
    fov_x = 2 * math.atan(cam.data.sensor_width / 2 / lens)
    tx = math.tan(fov_x / 2)
    ty = tx / aspect
    corners = [V((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    size = max((hi - lo).length, 0.3)
    dist = size * 2.0
    shift = V((0, 0, 0))
    for _ in range(8):
        cam.location = center + shift + vd * dist
        look_at(cam, center + shift)
        M = cam.rotation_euler.to_matrix()
        right, up, fwd = M @ V((1, 0, 0)), M @ V((0, 1, 0)), M @ V((0, 0, -1))
        xs, ys = [], []
        for c in corners:
            p = c - cam.location
            d = p.dot(fwd)
            xs.append(p.dot(right) / d / tx)
            ys.append(p.dot(up) / d / ty)
        cx = (max(xs) + min(xs)) / 2
        cy = (max(ys) + min(ys)) / 2
        shift += right * cx * tx * dist + up * cy * ty * dist
        ext = max((max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2)
        dist *= ext * margin
    cam.location = center + shift + vd * dist
    look_at(cam, center + shift)
    cam.data.clip_start = max(0.01, dist * 0.01)
    cam.data.clip_end = dist * 20 + 100
    # cyclorama: scaled to the asset, opening towards the camera
    s = max(size * 2.2, 3.0, dist * 1.4)
    cyc.scale = (s, s * 1.6, s)
    cyc.location = (center.x, center.y, lo.z)
    ang = math.atan2(vd.y, vd.x)
    cyc.rotation_euler = (0, 0, ang)
    hz = hi.z - lo.z
    spots = {
        "Key": (V((0.55, -1.0, 1.05)), 1.4, 160 * key_scale),
        "Fill": (V((1.0, 0.85, 0.35)), 2.0, 40 * key_scale),
        "Rim": (V((-1.1, 0.45, 1.0)), 1.0, 200 * key_scale),
    }
    R = Matrix.Rotation(ang, 3, "Z")
    for k, (off, sz, e) in spots.items():
        lo_ = L[k]
        lo_.location = center + (R @ V((off.x, off.y, 0))) * size * 1.1 + V((0, 0, off.z * size * 1.1))
        look_at(lo_, center)
        lo_.data.size = sz * size * 0.6
        lo_.data.size_y = sz * size * 0.35
        lo_.data.energy = e * size * size * 0.55


def render(path, res=(1920, 1080), samples=48):
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.cycles.samples = samples
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.04
    scn.cycles.max_bounces = 6
    scn.cycles.diffuse_bounces = 3
    scn.cycles.glossy_bounces = 3
    scn.cycles.transmission_bounces = 6
    scn.cycles.transparent_max_bounces = 6
    scn.cycles.caustics_reflective = False
    scn.cycles.caustics_refractive = False
    scn.cycles.blur_glossy = 1.0
    scn.cycles.use_denoising = True
    scn.cycles.denoiser = "OPENIMAGEDENOISE"
    scn.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
