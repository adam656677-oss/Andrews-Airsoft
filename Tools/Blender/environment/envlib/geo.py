"""Procedural mesh building: chamfered primitives merged into one bmesh with
material indices, world-scale box UVs and numpy vertex noise."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector


def _bevel(bm, w, segs, angle=0.5):
    if w <= 0:
        return
    edges = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > angle]
    if edges:
        bmesh.ops.bevel(bm, geom=edges, offset=w, offset_type='OFFSET', segments=segs, profile=0.5,
                        affect='EDGES', clamp_overlap=True)


def box_bm(size, bevel=0.0, segs=2, subdiv=0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    if subdiv:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=subdiv, use_grid_fill=True)
    _bevel(bm, min(bevel, min(size) * 0.45), segs)
    return bm


def cyl_bm(r, h, n=24, bevel=0.0, segs=2, r2=None, cap=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=n, radius1=r,
                          radius2=r if r2 is None else r2, depth=h)
    _bevel(bm, min(bevel, r * 0.4, h * 0.4), segs, angle=0.6)
    return bm


class Builder:
    """Accumulates parts into one mesh. Each part: bmesh in local space,
    a 4x4 matrix, a material slot name. UVTex (1 UV = 1 m, grain along
    local X) is computed per part before transforming."""

    def __init__(self, uvtex=True, arch=False):
        self.bm = bmesh.new()
        self.arch = arch
        self.uvl = self.bm.loops.layers.uv.new('UVMap')
        self.uvt = self.bm.loops.layers.uv.new('UVTex') if (uvtex and not arch) else None
        self.slots = []

    def slot(self, name):
        if name not in self.slots:
            self.slots.append(name)
        return self.slots.index(name)

    def add(self, part, mat, M=None, uvscale=1.0, grain='x', cap_mat=None, cap_axis=0, uvoff=None):
        """Merge a part. UVs: architecture -> UVMap at 1 UV = 2 m; props ->
        UVTex at 1 UV = 1 m. Unrotated parts are projected in world space so
        the texture is continuous across parts."""
        idx = self.slot(mat)
        lname = 'UVMap' if self.arch else 'UVTex'
        sc = 0.5 * uvscale if self.arch else uvscale
        l = part.loops.layers.uv.get(lname) or part.loops.layers.uv.new(lname)
        for nm in ('UVMap', 'UVTex'):
            if (nm == 'UVTex' and self.uvt is None):
                continue
            part.loops.layers.uv.get(nm) or part.loops.layers.uv.new(nm)
        rotated = M is not None and any(abs(M[i][j] - (1.0 if i == j else 0.0)) > 1e-6
                                        for i in range(3) for j in range(3))
        if M is not None and not rotated:
            bmesh.ops.transform(part, matrix=M, verts=part.verts[:])
            part.normal_update()
            box_uv(part, l, sc, grain)
        else:
            part.normal_update()
            box_uv(part, l, sc, grain)
            if M is not None:
                bmesh.ops.transform(part, matrix=M, verts=part.verts[:])
        if uvoff is not None:
            for f in part.faces:
                for lp in f.loops:
                    uv = lp[l].uv
                    lp[l].uv = (uv[0] + uvoff[0], uv[1] + uvoff[1])
        cidx = self.slot(cap_mat) if cap_mat else None
        part.normal_update()
        for f in part.faces:
            f.material_index = idx
            if cidx is not None:
                ax = Vector((0, 0, 0))
                ax[cap_axis] = 1
                if M is not None:
                    ax = (M.to_3x3() @ ax).normalized()
                if abs(f.normal.dot(ax)) > 0.85:
                    f.material_index = cidx
        me = bpy.data.meshes.new('_tmp')
        part.to_mesh(me)
        part.free()
        self.bm.from_mesh(me)
        bpy.data.meshes.remove(me)

    def box(self, mat, size, loc, rot=(0, 0, 0), bevel=0.01, segs=2, grain='x', subdiv=0, uvoff=None):
        self.add(box_bm(size, bevel, segs, subdiv), mat, mtx(loc, rot), grain=grain, uvoff=uvoff)

    def cyl(self, mat, r, h, loc, rot=(0, 0, 0), n=24, bevel=0.005, segs=2, r2=None, cap=True, grain='z'):
        self.add(cyl_bm(r, h, n, bevel, segs, r2, cap), mat, mtx(loc, rot), grain=grain)

    def between(self, mat, p0, p1, r, n=16, bevel=0.003, kind='cyl', w=None, roll=0.0):
        """Cylinder (or box of section w=(a,b)) from p0 to p1."""
        p0 = Vector(p0)
        p1 = Vector(p1)
        d = p1 - p0
        L = d.length
        q = d.normalized().to_track_quat('Z', 'Y')
        M = Matrix.Translation((p0 + p1) / 2) @ q.to_matrix().to_4x4() @ Matrix.Rotation(roll, 4, 'Z')
        if kind == 'cyl':
            self.add(cyl_bm(r, L, n, bevel), mat, M, grain='z')
        else:
            self.add(box_bm((w[0], w[1], L), bevel), mat, M, grain='z')

    def finish(self, name, collection=None, smooth_angle=32.0):
        me = bpy.data.meshes.new(name)
        ngons = [f for f in self.bm.faces if len(f.verts) > 4]
        if ngons:  # FBX tangent export needs tris/quads
            bmesh.ops.triangulate(self.bm, faces=ngons, quad_method='BEAUTY', ngon_method='BEAUTY')
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        for s in self.slots:
            m = bpy.data.materials.get(s) or bpy.data.materials.new(s)
            me.materials.append(m)
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        o = bpy.data.objects.new(name, me)
        (collection or bpy.context.scene.collection).objects.link(o)
        return o


def mtx(loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    from mathutils import Euler
    M = Matrix.Translation(loc) @ Euler(rot, 'XYZ').to_matrix().to_4x4()
    if scale is not None:
        M = M @ Matrix.Diagonal(Vector(tuple(scale) + (1,)))
    return M


def box_uv(bm, layer, scale=1.0, grain='x'):
    """Per-face dominant-axis projection. Grain runs along U and follows the
    given local axis on faces that contain it."""
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            co = lp.vert.co
            x, y, z = co.x, co.y, co.z
            if grain == 'z':
                x, z = z, x
                axg = {0: 2, 2: 0, 1: 1}[ax]
                sgn = n[ax]
            else:
                axg = ax
                sgn = n[ax]
            if grain == 'y':
                x, y = y, x
                axg = {0: 1, 1: 0, 2: 2}[ax]
            if axg == 2:
                u, v = x, y
            elif axg == 1:
                u, v = x, z
            else:
                u, v = y, z
            lp[layer].uv = (u * scale, v * scale)


def world_uv(obj, scale=0.5, layer='UVMap'):
    """Architecture: real-world box projection (1 UV = 1/scale m) in object
    space, U pointing to the viewer's right on every face."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.get(layer) or bm.loops.layers.uv.new(layer)
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        s = 1.0 if n[ax] >= 0 else -1.0
        for lp in f.loops:
            c = lp.vert.co
            if ax == 0:      # faces +X/-X : right is -Y for +X
                u, v = -c.y * s, c.z
            elif ax == 1:    # faces +Y/-Y : viewer at +Y, right is +X
                u, v = c.x * s, c.z
            else:
                u, v = c.x, c.y * s
            lp[uvl].uv = (u * scale, v * scale)
    bm.to_mesh(me)
    bm.free()


def smart_uv(obj, margin=0.004, angle=60.0, layer='UVMap'):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    me = obj.data
    me.uv_layers.active = me.uv_layers[layer]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    try:
        bpy.ops.uv.average_islands_scale()
        bpy.ops.uv.pack_islands(rotate=True, rotate_method='ANY', shape_method='CONCAVE',
                                margin_method='FRACTION', margin=margin)
    except Exception as e:
        print('pack failed', e)
    bpy.ops.object.mode_set(mode='OBJECT')


# ----------------------------------------------------------------------------
# numpy vertex noise
# ----------------------------------------------------------------------------
def _hash(ix, iy, iz, seed):
    n = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    n = n & 0xffffffff
    n = ((n ^ (n >> 13)) * 1274126177) & 0xffffffff
    n = n ^ (n >> 16)
    return (n & 0xffff).astype(np.float64) / 65535.0 * 2 - 1


def vnoise3(P, seed=0):
    P = np.asarray(P, np.float64)
    Pi = np.floor(P).astype(np.int64)
    f = P - Pi
    w = f * f * (3 - 2 * f)
    out = 0
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                h = _hash(Pi[:, 0] + dx, Pi[:, 1] + dy, Pi[:, 2] + dz, seed)
                wx = w[:, 0] if dx else 1 - w[:, 0]
                wy = w[:, 1] if dy else 1 - w[:, 1]
                wz = w[:, 2] if dz else 1 - w[:, 2]
                out = out + h * wx * wy * wz
    return out


def fbm3(P, freq=1.0, oct=4, rough=0.5, seed=0):
    P = np.asarray(P, np.float64)
    out = np.zeros(len(P))
    a = 1.0
    f = freq
    tot = 0
    for i in range(oct):
        out += vnoise3(P * f + i * 17.31, seed + i) * a
        tot += a
        a *= rough
        f *= 2.03
    return out / tot


def verts_np(me):
    a = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get('co', a)
    return a.reshape(-1, 3)


def set_verts(me, a):
    me.vertices.foreach_set('co', np.asarray(a, np.float64).ravel())
    me.update()


def normals_np(me):
    a = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get('normal', a)
    return a.reshape(-1, 3)


def subdivide_obj(obj, levels=2, simple=False):
    m = obj.modifiers.new('sub', 'SUBSURF')
    m.levels = levels
    m.render_levels = levels
    if simple:
        m.subdivision_type = 'SIMPLE'
    apply_mods(obj)


def apply_mods(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    bpy.data.meshes.remove(old)


def join(objs, name):
    """Join objects (keeps materials by name)."""
    bm = bmesh.new()
    slots = []
    for o in objs:
        me = o.data.copy()
        me.transform(o.matrix_world)
        remap = []
        for m in o.data.materials:
            if m.name not in slots:
                slots.append(m.name)
            remap.append(slots.index(m.name))
        for p in me.polygons:
            p.material_index = remap[p.material_index] if remap else 0
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for s in slots:
        me.materials.append(bpy.data.materials[s])
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o
