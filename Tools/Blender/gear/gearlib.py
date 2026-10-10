"""
gearlib: Blender-side helpers for the glove generator (gun loading, obstacle fields,
mesh objects from the SDF, preview renders).
"""

import glob
import math
import os
import sys

import bpy  # noqa: I001
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
import bakekit as bk  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SOURCE_DIR = os.path.join(ROOT, "SourceAssets")
DATA_DIR = os.path.join(ROOT, "Content", "Airsoft", "Data")
RENDER_DIR = os.path.join(ROOT, "Docs", "Renders")

PALETTE_GLASS = (0.05, 0.12, 0.14)


def weapon_points(gid):
    import json

    d = json.load(open(os.path.join(DATA_DIR, "Weapons.json")))
    pts = d["Assets"][gid]["Points"]
    return {k: np.array([v[0] / 100.0, -v[1] / 100.0, v[2] / 100.0]) for k, v in pts.items()}


def weapon_tints(gid):
    sys.path.insert(0, os.path.join(HERE, ".."))
    import render_imported as ri

    return ri.tints_for(gid)


def load_gun(gid, coll=None, materials=True, offset=(0, 0, 0)):
    """Imports SourceAssets/Weapons/<gid>/*.fbx.  Returns (objects, bvh, verts, polys)."""
    coll = coll or bpy.context.scene.collection
    d = os.path.join(SOURCE_DIR, "Weapons", gid)
    tints = weapon_tints(gid) if materials else None
    objs = []
    allv, allp = [], []
    for f in sorted(glob.glob(os.path.join(d, f"SM_{gid}_*.fbx"))):
        piece = os.path.basename(f)[len(f"SM_{gid}_") : -4]
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=f, axis_forward="X", axis_up="Z")
        for o in [o for o in bpy.data.objects if o not in before]:
            if o.type != "MESH":
                bpy.data.objects.remove(o)
                continue
            for c in list(o.users_collection):
                c.objects.unlink(o)
            coll.objects.link(o)
            o.location = Vector(o.location) + Vector(offset)
            bpy.context.view_layer.update()
            if materials:
                if piece == "Glass":
                    mat = bk.plain_material(f"G_{gid}_Glass", PALETTE_GLASS, 0.03, 0.0, alpha=0.25)
                else:
                    mat = bk.preview_material(f"PV_{gid}_{piece}", bk.texture_paths(d, gid, piece), tints, proxy_res=2048)
                o.data.materials.clear()
                o.data.materials.append(mat)
            o.name = f"{gid}_{piece}"
            M = o.matrix_world
            base = sum(len(v) for v in allv)
            allv.append([tuple(M @ v.co) for v in o.data.vertices])
            allp.extend([tuple(i + base for i in p.vertices) for p in o.data.polygons])
            objs.append(o)
    verts = [v for vs in allv for v in vs]
    bvh = BVHTree.FromPolygons(verts, allp, epsilon=0.0)
    return objs, bvh


_RAYS = [Vector(d).normalized() for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1), (1, 1, 1), (-1, -1, 1), (1, -1, -1), (-1, 1, -1))]


def bvh_sdf(bvh, maxdist=0.2):
    """Signed distance from a mesh BVH made of overlapping closed shells.  The gun meshes
    are unions of separate closed parts, so the nearest-face normal is not a reliable
    inside test; instead a point is inside when at least 3 of 10 rays first hit a back
    face (it is then inside some shell)."""

    def f(P):
        out = np.empty(len(P))
        for i, p in enumerate(P):
            v = Vector(p)
            loc, nrm, idx, dist = bvh.find_nearest(v, maxdist)
            if loc is None:
                out[i] = maxdist
                continue
            back = 0
            for k, d in enumerate(_RAYS):
                hit, n, _, _ = bvh.ray_cast(v, d, 1.0)
                if hit is not None and n.dot(d) > 0:
                    back += 1
                if back >= 3 or (k >= 6 and back == 0):
                    break
            out[i] = -dist if back >= 3 else dist
        return out

    return f


def union_sdf(*fs):
    def f(P):
        return np.min(np.stack([g(P) for g in fs]), axis=0)

    return f


# --------------------------------------------------------------------------------------
# Mesh objects
# --------------------------------------------------------------------------------------


def mesh_object(name, verts, faces, coll=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(int(i) for i in f) for f in faces])
    me.validate(clean_customdata=False)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    return ob


def fix_winding(verts, faces, field):
    """Flips faces whose normal disagrees with the field gradient."""
    v = verts[faces]
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    if faces.shape[1] == 4:
        n += np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0])
    c = v.mean(axis=1)
    g = field.gradient(c, 3e-4)
    flip = np.einsum("ij,ij->i", n, g) < 0
    faces = faces.copy()
    faces[flip] = faces[flip][:, ::-1]
    return faces


def simple_mat(name, rgb, rough=0.6, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def look_at(ob, target, up=(0, 0, 1)):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def setup_preview_scene(threads=2):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    if threads:
        scn.render.threads_mode = "FIXED"
        scn.render.threads = threads
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.32, 0.33, 0.35, 1)
    bg.inputs["Strength"].default_value = 0.5
    scn.world = world
    cam = bpy.data.objects.new("PCam", bpy.data.cameras.new("PCam"))
    scn.collection.objects.link(cam)
    scn.camera = cam
    for name, loc, e in (("K", (0.2, -0.6, 0.9), 120.0), ("F", (-0.6, 0.5, 0.4), 50.0), ("R", (0.6, 0.6, 0.2), 40.0)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.size = 0.6
        ld.energy = e
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        scn.collection.objects.link(lo)
        look_at(lo, (0.05, 0, 0))
    return cam


def render_views(path, views, res=(560, 360), samples=8):
    """views: list of (cam_loc, target, lens or ('fov', deg)).  Writes a sheet PNG."""
    scn = bpy.context.scene
    cam = scn.camera
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.cycles.samples = samples
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 4
    scn.render.film_transparent = False
    scn.render.image_settings.file_format = "PNG"
    tiles = []
    tmp = path + ".v.png"
    for loc, tgt, lens in views:
        cam.location = loc
        look_at(cam, tgt)
        if isinstance(lens, tuple):
            cam.data.lens_unit = "FOV"
            cam.data.angle = math.radians(lens[1])
        else:
            cam.data.lens_unit = "MILLIMETERS"
            cam.data.lens = lens
        cam.data.clip_start = 0.005
        scn.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(tmp)
        a = np.empty(im.size[0] * im.size[1] * 4, np.float32)
        im.pixels.foreach_get(a)
        tiles.append(a.reshape(im.size[1], im.size[0], 4))
        bpy.data.images.remove(im)
    os.remove(tmp)
    cols = 2 if len(tiles) > 1 else 1
    rows = (len(tiles) + cols - 1) // cols
    h, w = tiles[0].shape[:2]
    sheet = np.zeros((rows * h, cols * w, 4), np.float32)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet[(rows - 1 - r) * h : (rows - r) * h, c * w : (c + 1) * w] = t
    sheet[..., 3] = 1
    im = bpy.data.images.new("sheet", cols * w, rows * h)
    im.pixels.foreach_set(sheet.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def penetration(ob, sdf, sample=1):
    """Vertices of ob inside the obstacle: returns (count, max depth m)."""
    M = ob.matrix_world
    P = np.array([tuple(M @ v.co) for v in ob.data.vertices[::sample]])
    d = sdf(P)
    ins = d < 0
    return int(ins.sum()), float(-d.min()) if ins.any() else 0.0, P[ins]
