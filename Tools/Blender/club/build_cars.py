"""Builds the AVERNE luxury cars (luxury_cars.py) and renders their product shots.

    python build_cars.py -- [Car_Limousine ...] [--res 4096|2048|1024] [--samples N]
    python build_cars.py -- --render-only [ids]       # re-render from the build cache (no bake)
    python build_cars.py -- --lineup                  # 3840x2160 lineup of all four cars
    python build_cars.py -- --preview [ids] [--out DIR]   # geometry check: procedural materials, no bake

Builds go through build_club.build (one FBX per piece under SourceAssets/Props/<Id>/, baked BC/N/ORM/M,
entry in Content/Airsoft/Data/PropsClub.json). Product renders use a car studio (long softbox strips for
the flank / roof highlights, glossy floor, clear-coated flake paint like M_CarPaint) and are written as
JPG to Docs/Renders/Cars/<Id>.jpg and Docs/Renders/Cars/_Lineup_4K.jpg.
"""

import os
import sys
import math
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector as V, Matrix  # noqa: E402
import propkit as pk  # noqa: E402
from club_registry import ASSETS  # noqa: E402
import luxury_cars  # noqa: F401,E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT_DIR = os.path.join(ROOT, "Docs", "Renders", "Cars")
SRC = os.path.join(ROOT, "SourceAssets", "Props")
VIEWS = []
CARS = ["Car_Limousine", "Car_GrandTourer", "Car_Hypercar", "Car_SUV"]

# Product-shot colourways (linear): primary, secondary (two-tone upper body), caliper accent is baked
SHOT_PAINT = {
    "Car_Limousine": ((0.075, 0.004, 0.012), (0.004, 0.004, 0.005)),     # deep burgundy over obsidian
    "Car_GrandTourer": ((0.006, 0.014, 0.045), None),                    # midnight blue
    "Car_Hypercar": ((0.03, 0.032, 0.036), None),                       # dark gunmetal
    "Car_SUV": ((0.70, 0.69, 0.66), None),                              # pearl white
}
FLAKE = {"Car_SUV": 0.25}
METALLIC = {"Car_SUV": 0.25}


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------------------
# Materials for renders
# --------------------------------------------------------------------------------------


def car_paint_nodes(nt, nb, bsdf, col_sock, mask_r, mask_g, prim, sec, flake=0.6, metallic=0.55):
    """Clear-coat metallic paint on the masked areas (mirrors M_CarPaint): base = tint (R primary, G secondary),
    metallic flake sparkle from a fine voronoi in object space, coat weight 1 / roughness 0.02."""
    sec = sec or prim
    tinted = nb.mixc_op("MULTIPLY", 1.0, col_sock, (*[c / 0.75 for c in prim], 1))
    tinted2 = nb.mixc_op("MULTIPLY", 1.0, col_sock, (*[c / 0.75 for c in sec], 1))
    col = nb.mixc(mask_r, col_sock, tinted)
    col = nb.mixc(mask_g, col, tinted2)
    msum = nb.clamp(nb.add(mask_r, mask_g))
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 2200.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    fl = nb.maprange(vor.outputs["Color"], 0.0, 1.0, 1.0 - 0.35 * flake, 1.0 + 0.6 * flake)
    col = nb.mixc(msum, col, nb.mixc_op("MULTIPLY", 1.0, col, nb.combine(fl, fl, fl)))
    return col, msum


def render_material(aid, piece, paths, prim, sec, kind):
    m = bpy.data.materials.new(f"RM_{aid}_{piece}")
    nt = m.node_tree
    nt.nodes.clear()
    nb = pk.NB(nt)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])

    def tex(path, cs):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        n.image.colorspace_settings.name = cs
        return n

    if kind == "glass":
        priv = piece == "GlassPrivacy"
        bsdf.inputs["Base Color"].default_value = (0.02, 0.022, 0.025, 1) if priv else (0.05, 0.055, 0.06, 1)
        bsdf.inputs["Roughness"].default_value = 0.01
        bsdf.inputs["Transmission Weight"].default_value = 0.0
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        tr.inputs["Color"].default_value = (0.08, 0.09, 0.09, 1) if priv else (0.55, 0.6, 0.6, 1)
        mix = nt.nodes.new("ShaderNodeMixShader")
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.25
        f = nb.add(0.18 if not priv else 0.5, nb.mul(lw.outputs["Fresnel"], 0.8))
        nt.links.new(f, mix.inputs[0])
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(bsdf.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        return m
    bc = tex(paths["BC"], "sRGB")
    if kind == "emissive":
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(bc.outputs[0], em.inputs["Color"])
        em.inputs["Strength"].default_value = 12.0
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        return m
    orm = tex(paths["ORM"], "Non-Color")
    nm = tex(paths["N"], "Non-Color")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(orm.outputs[0], sep.inputs[0])
    col = bc.outputs[0]
    rough = sep.outputs[1]
    metal = sep.outputs[2]
    if os.path.exists(paths.get("M", "")) and prim is not None:
        mk = tex(paths["M"], "Non-Color")
        ms = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(mk.outputs[0], ms.inputs[0])
        col, msum = car_paint_nodes(nt, nb, bsdf, col, ms.outputs[0], ms.outputs[1], prim, sec, FLAKE.get(aid, 0.6))
        metal = nb.mix(msum, metal, METALLIC.get(aid, 0.55))
        rough = nb.mix(msum, rough, 0.32)
        nt.links.new(msum, bsdf.inputs["Coat Weight"])
        bsdf.inputs["Coat Roughness"].default_value = 0.02
    ao = nb.mixc_op("MULTIPLY", 0.5, col, nb.combine(sep.outputs[0], sep.outputs[0], sep.outputs[0]))
    nt.links.new(ao, bsdf.inputs["Base Color"])
    nt.links.new(rough, bsdf.inputs["Roughness"])
    nt.links.new(metal, bsdf.inputs["Metallic"])
    sn = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(nm.outputs[0], sn.inputs[0])
    cn = nt.nodes.new("ShaderNodeCombineColor")
    nt.links.new(sn.outputs[0], cn.inputs[0])
    nt.links.new(nb.sub(1.0, sn.outputs[1]), cn.inputs[1])
    nt.links.new(sn.outputs[2], cn.inputs[2])
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(cn.outputs[0], nmap.inputs["Color"])
    nt.links.new(nmap.outputs[0], bsdf.inputs["Normal"])
    return m


def import_car(aid, prim=None, sec=None, at=(0, 0, 0), yaw=0.0):
    """FBX pieces from SourceAssets with render materials; returns the objects."""
    import json
    d = os.path.join(SRC, aid)
    data = json.load(open(os.path.join(ROOT, "Content", "Airsoft", "Data", "PropsClub.json")))["Assets"][aid]
    if prim is None:
        prim, sec = SHOT_PAINT[aid]
    objs = []
    for pc in data["Pieces"]:
        pn = pc["Name"]
        f = os.path.join(d, f"SM_{aid}_{pn}.fbx")
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=f, axis_forward="X", axis_up="Z", global_scale=1.0)
        new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        kind = "glass" if pc["Kind"] == "Glass" else ("emissive" if pc["Kind"] == "Emissive" else "opaque")
        paths = {k: os.path.join(d, f"T_{aid}_{pn}_{k}.png") for k in ("BC", "N", "ORM", "M")}
        mat = render_material(aid, pn, paths, prim if pn == "Body" else None, sec, kind)
        for o in new:
            o.data.materials.clear()
            o.data.materials.append(mat)
            o.matrix_world = Matrix.Translation(at) @ Matrix.Rotation(math.radians(yaw), 4, "Z") @ o.matrix_world
            if kind in ("glass", "emissive"):
                o.visible_shadow = False
            objs.append(o)
    return objs


# --------------------------------------------------------------------------------------
# Car studio
# --------------------------------------------------------------------------------------


def car_studio(lo, hi, view=(1.0, -0.75, 0.22), lens=50, margin=1.08, res=(1920, 1080), floor_col=0.012, key=1.0):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    world = bpy.data.worlds.new("CarStudio")
    scn.world = world
    nt = world.node_tree
    nt.nodes.clear()
    nb = pk.NB(nt)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    z = sep.outputs[2]
    # dark studio with a soft bright horizon band (gives the body sides a clean gradient reflection)
    # studio "HDRI": dark floor, soft bright horizon band, a cool grey dome with a brighter zenith
    band = nb.maprange(nb.math("ABSOLUTE", nb.sub(z, 0.05)), 0.0, 0.16, 1.0, 0.0, smooth=True)
    dome = nb.maprange(z, 0.0, 1.0, 0.0, 1.0, smooth=True)
    v = nb.add(nb.add(0.003, nb.mul(band, 0.5)), nb.mul(dome, 0.12))
    col = nb.combine(nb.mul(v, 0.92), nb.mul(v, 0.96), v)
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(col, bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    lo, hi = V(lo), V(hi)
    c = (lo + hi) / 2
    L = hi.x - lo.x
    # floor: dark, semi-gloss
    bpy.ops.mesh.primitive_plane_add(size=1, location=(c.x, c.y, lo.z))
    fl = bpy.context.active_object
    fl.scale = (60, 60, 1)
    fm = bpy.data.materials.new("Floor")
    b = fm.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (floor_col, floor_col, floor_col * 1.05, 1)
    b.inputs["Roughness"].default_value = 0.22
    fl.data.materials.append(fm)

    def area(name, loc, size, energy, col=(1, 1, 1), target=None, shape="RECTANGLE"):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = shape
        ld.size, ld.size_y = size
        ld.energy = energy * key
        ld.color = col
        o = bpy.data.objects.new(name, ld)
        scn.collection.objects.link(o)
        o.location = loc
        pk.look_at(o, target if target is not None else c)
        return o

    H = hi.z - lo.z
    for dy in (-0.9, 0.9):
        area("Top", (c.x, c.y + dy, hi.z + 2.6), (L * 1.2, 0.45), 700, (1.0, 0.98, 0.95), target=(c.x, c.y + dy, lo.z))
    area("TopFill", (c.x, c.y, hi.z + 6.0), (L * 2.2, 6.0), 120, (0.85, 0.9, 1.0), target=(c.x, c.y, lo.z))
    area("StripL", (c.x, c.y + 4.2, lo.z + H * 0.9), (L * 1.3, 0.35), 900, (0.95, 0.97, 1.0))
    area("StripR", (c.x, c.y - 4.2, lo.z + H * 0.9), (L * 1.3, 0.35), 900, (0.95, 0.97, 1.0))
    area("Front", (c.x + L * 1.1, c.y - 1.0, lo.z + 1.6), (2.5, 1.2), 500, (1.0, 0.95, 0.9))
    area("Rim", (c.x - L * 0.9, c.y + 2.5, lo.z + 2.4), (3.0, 1.0), 900, (0.9, 0.95, 1.0))
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scn.collection.objects.link(cam)
    scn.camera = cam
    cam.data.sensor_width = 36
    _frame(cam, lo, hi, view, lens, res[0] / res[1], margin)
    return cam


def _frame(cam, lo, hi, view, lens, aspect, margin):
    lo, hi = V(lo), V(hi)
    center = (lo + hi) / 2
    vd = V(view).normalized()
    cam.data.lens = lens
    fov_x = 2 * math.atan(cam.data.sensor_width / 2 / lens)
    tx = math.tan(fov_x / 2)
    ty = tx / aspect
    corners = [V((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    dist = (hi - lo).length * 2.0
    shift = V((0, 0, 0))
    for _ in range(10):
        cam.location = center + shift + vd * dist
        pk.look_at(cam, center + shift)
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
    pk.look_at(cam, center + shift)
    cam.data.clip_start = 0.05
    cam.data.clip_end = 500


def render_jpg(path, res, samples):
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.cycles.samples = samples
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.05
    scn.cycles.max_bounces = 8
    scn.cycles.glossy_bounces = 4
    scn.cycles.transmission_bounces = 6
    scn.cycles.transparent_max_bounces = 8
    scn.cycles.diffuse_bounces = 2
    scn.cycles.caustics_reflective = False
    scn.cycles.caustics_refractive = False
    scn.cycles.blur_glossy = 0.5
    scn.cycles.use_denoising = True
    scn.cycles.denoiser = "OPENIMAGEDENOISE"
    scn.render.image_settings.file_format = "JPEG"
    scn.render.image_settings.quality = 92
    scn.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    t = time.time()
    bpy.ops.render.render(write_still=True)
    log(f"  render {os.path.basename(path)} {time.time() - t:.0f}s")


# --------------------------------------------------------------------------------------
# Preview (geometry check without baking)
# --------------------------------------------------------------------------------------


def preview(aid, out_dir, views=None, res=(960, 540), samples=24):
    pk.reset_scene()
    spec = ASSETS[aid]
    A = pk.Asset(aid, **spec["kw"])
    spec["fn"](A)
    prim, sec = SHOT_PAINT.get(aid, ((0.05, 0.05, 0.05), None))
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        nt = m.node_tree
        for n in nt.nodes:
            if n.bl_idname == "ShaderNodeOutputMaterial":
                n.is_active_output = n.name == "OUT_PV"
        if m.name.startswith("R_lx_paint"):
            pv = [n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"]
            out = nt.nodes.get("OUT_PV")
            b = out.inputs["Surface"].links[0].from_node if out and out.inputs["Surface"].links else pv[-1]
            colr = sec if ("paint2" in m.name and sec) else prim
            for l in list(b.inputs["Base Color"].links):
                nt.links.remove(l)
            b.inputs["Base Color"].default_value = (*colr, 1)
            for l in list(b.inputs["Metallic"].links):
                nt.links.remove(l)
            b.inputs["Metallic"].default_value = 0.5
            for l in list(b.inputs["Roughness"].links):
                nt.links.remove(l)
            b.inputs["Roughness"].default_value = 0.3
            b.inputs["Coat Weight"].default_value = 1.0
            b.inputs["Coat Roughness"].default_value = 0.02
        if m.name.startswith("R_lx_emit"):
            out = nt.nodes.get("OUT_PV")
            b = out.inputs["Surface"].links[0].from_node
            b.inputs["Emission Strength"].default_value = 10.0
            for l in list(b.inputs["Emission Color"].links):
                nt.links.remove(l)
            col = (1, 0.03, 0.02, 1) if "red" in m.name else ((1, 0.4, 0.05, 1) if "amber" in m.name else (0.9, 0.95, 1, 1))
            b.inputs["Emission Color"].default_value = col
        if m.name.startswith("R_lx_glass"):
            out = nt.nodes.get("OUT_PV")
            b = out.inputs["Surface"].links[0].from_node
            b.inputs["Transmission Weight"].default_value = 0.85
            for l in list(b.inputs["Roughness"].links):
                nt.links.remove(l)
            b.inputs["Roughness"].default_value = 0.0
            for l in list(b.inputs["Base Color"].links):
                nt.links.remove(l)
            b.inputs["Base Color"].default_value = (0.3, 0.32, 0.33, 1)
    objs = [o for o in bpy.data.objects if o.type == "MESH"]
    lo, hi = pk.bbox_of(objs)
    if VIEWS:
        allv = {"34f": (1.0, -0.75, 0.22), "side": (0.0, -1.0, 0.05), "34r": (-1.0, -0.7, 0.25), "front": (1.0, -0.12, 0.12), "top": (0.25, -0.35, 1.0),
                "low": (1.0, -0.55, 0.06), "rear": (-1.0, -0.1, 0.15), "wheel": (0.25, -1.0, 0.02)}
        views = {k: allv[k] for k in VIEWS}
    views = views or {"34f": (1.0, -0.75, 0.22), "side": (0.0, -1.0, 0.05), "34r": (-1.0, -0.7, 0.25), "front": (1.0, -0.12, 0.12), "top": (0.25, -0.35, 1.0)}
    cam = car_studio(lo, hi, res=res)
    for k, v in views.items():
        _frame(cam, lo, hi, v, 50, res[0] / res[1], 1.06)
        render_jpg(os.path.join(out_dir, f"{aid}_{k}.jpg"), res, samples)
    tris = {}
    dg = bpy.context.evaluated_depsgraph_get()
    big = []
    for o in objs:
        me = o.evaluated_get(dg).to_mesh()
        me.calc_loop_triangles()
        n = len(me.loop_triangles)
        o.evaluated_get(dg).to_mesh_clear()
        pc = o.get("piece", "?")
        tris[pc] = tris.get(pc, 0) + n
        big.append((n, pc, o.data.materials[0].name if o.data.materials else "", len(o.modifiers)))
    big.sort(reverse=True)
    log(f"  {aid}: preview tris {tris} total {sum(tris.values())}")
    for b in big[:25]:
        log("     ", b)


# --------------------------------------------------------------------------------------
# Product shots + lineup
# --------------------------------------------------------------------------------------


SHOT_VIEW = {"Car_Limousine": ((1.0, -0.8, 0.2), 50), "Car_GrandTourer": ((1.0, -0.85, 0.15), 45),
             "Car_Hypercar": ((1.0, -0.85, 0.13), 42), "Car_SUV": ((1.0, -0.8, 0.18), 45)}


def product_shot(aid, res=(1920, 1080), samples=96, view=None, name=None):
    pk.reset_scene()
    objs = import_car(aid)
    lo, hi = pk.bbox_of(objs)
    v, lens = SHOT_VIEW.get(aid, ((1.0, -0.78, 0.2), 50))
    cam = car_studio(lo, hi, view=view or v, lens=lens, res=res)
    render_jpg(os.path.join(OUT_DIR, (name or aid) + ".jpg"), res, samples)


def lineup(res=(3840, 2160), samples=64):
    pk.reset_scene()
    allo = []
    # staggered diagonal row, each car at a 3/4 angle
    place = {"Car_Limousine": (0.0, 3.9, -28), "Car_GrandTourer": (-0.7, 1.3, -28), "Car_Hypercar": (-1.4, -1.25, -28), "Car_SUV": (-2.1, -3.85, -28)}
    for aid in CARS:
        x, y, yaw = place[aid]
        allo += import_car(aid, at=(x, y, 0), yaw=yaw)
    lo, hi = pk.bbox_of(allo)
    car_studio(lo, hi, view=(1.0, -0.42, 0.24), lens=45, res=res, margin=1.04)
    render_jpg(os.path.join(OUT_DIR, "_Lineup_4K.jpg"), res, samples)


def main(argv):
    res = 4096
    if "--res" in argv:
        res = int(argv[argv.index("--res") + 1])
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else None
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(OUT_DIR, "_preview")
    flags = set(a for a in argv if a.startswith("--"))
    ids = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--res", "--samples", "--out", "--views"))]
    ids = ids or CARS
    if "--views" in argv:
        VIEWS.extend(argv[argv.index("--views") + 1].split(","))
    if "--preview" in flags:
        for aid in ids:
            preview(aid, out, samples=samples or 24)
        return
    if "--lineup" in flags:
        lineup(samples=samples or 64)
        return
    if "--render-only" not in flags:
        import build_club
        for aid in ids:
            log(f"== {aid}")
            build_club.build(aid, res, do_render=False)
    for aid in ids:
        product_shot(aid, samples=samples or 96)


if __name__ == "__main__":
    argv = sys.argv[1:]
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv
    main(argv)
