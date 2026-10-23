"""
studio: product-shot rendering for the Blender generators (Cycles, AgX).

Soft three-point area-light studio, an HDR-ish gradient world for reflections, a
shadow-catcher floor for a subtle contact shadow, and a neutral gradient backdrop
composited behind the transparent render.  Framing is automatic (perspective lens,
fits the asset bounding box).
"""

import math
import os

import bpy  # noqa: I001
import numpy as np
from mathutils import Vector

V = Vector


def setup_studio():
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.render.film_transparent = True
    scn.render.image_settings.file_format = "PNG"
    scn.render.image_settings.color_mode = "RGBA"
    scn.render.image_settings.color_depth = "8"
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    scn.view_settings.exposure = -1.3
    world = bpy.data.worlds.new("Studio")
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])

    def mr(sock, a, b, c, d):
        n = nt.nodes.new("ShaderNodeMapRange")
        n.interpolation_type = "SMOOTHSTEP"
        nt.links.new(sock, n.inputs["Value"])
        n.inputs["From Min"].default_value = a
        n.inputs["From Max"].default_value = b
        n.inputs["To Min"].default_value = c
        n.inputs["To Max"].default_value = d
        return n.outputs["Result"]

    def op(o, a, b):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = o
        for i, v in enumerate((a, b)):
            if isinstance(v, bpy.types.NodeSocket):
                nt.links.new(v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        return n.outputs[0]

    top = mr(sep.outputs["Z"], 0.3, 0.85, 0.0, 1.0)
    band = op("MULTIPLY", mr(sep.outputs["Z"], -0.05, 0.12, 0.0, 1.0), mr(sep.outputs["Z"], 0.22, 0.35, 1.0, 0.0))
    side = mr(sep.outputs["Y"], -0.2, -0.75, 0.0, 1.0)  # brighter on the camera side (-Y)
    ground = mr(sep.outputs["Z"], -0.4, 0.0, 0.0, 1.0)
    v = op("ADD", op("ADD", 0.01, op("MULTIPLY", top, 0.9)), op("MULTIPLY", op("MULTIPLY", band, side), 1.4))
    v = op("ADD", v, op("MULTIPLY", ground, 0.04))
    bg = nt.nodes.new("ShaderNodeBackground")
    comb = nt.nodes.new("ShaderNodeCombineColor")
    for k in ("Red", "Green", "Blue"):
        nt.links.new(v, comb.inputs[k])
    nt.links.new(comb.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    scn.world = world

    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 85
    cam.data.sensor_width = 36
    cam.data.dof.use_dof = False
    scn.collection.objects.link(cam)
    scn.camera = cam

    def area(name, color):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "RECTANGLE"
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        scn.collection.objects.link(lo)
        return lo

    lights = {"key": area("Key", (1.0, 0.97, 0.93)), "fill": area("Fill", (0.86, 0.91, 1.0)), "rim": area("Rim", (1.0, 1.0, 1.0)), "kick": area("Kick", (0.92, 0.96, 1.0))}

    floor = bpy.data.objects.new("Floor", bpy.data.meshes.new("Floor"))
    floor.data.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    floor.is_shadow_catcher = True
    scn.collection.objects.link(floor)
    return {"cam": cam, "lights": lights, "floor": floor}


def look_at(ob, target):
    d = V(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def frame(rig, lo, hi, view_dir=(0.5, -1.0, 0.32), aspect=16 / 9, margin=1.12, lens=85, light_scale=1.0):
    cam, lights, floor = rig["cam"], rig["lights"], rig["floor"]
    lo, hi = V(lo), V(hi)
    center = (lo + hi) / 2
    vd = V(view_dir).normalized()
    cam.data.lens = lens
    fov_x = 2 * math.atan(cam.data.sensor_width / 2 / lens)
    tx = math.tan(fov_x / 2)
    ty = tx / aspect
    corners = [V((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    size = max((hi - lo).length, 0.05)
    dist = size * 2.5
    shift = V((0, 0, 0))
    for _ in range(8):
        cam.location = center + shift + vd * dist
        look_at(cam, center + shift)
        M = cam.rotation_euler.to_matrix()
        right, up, fwd = M @ V((1, 0, 0)), M @ V((0, 1, 0)), M @ V((0, 0, -1))
        xs, ys = [], []
        for c in corners:
            p = c - cam.location
            depth = p.dot(fwd)
            xs.append(p.dot(right) / depth / tx)
            ys.append(p.dot(up) / depth / ty)
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        shift += right * cx * tx * dist + up * cy * ty * dist
        ext = max((max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2)
        dist *= ext * margin
    cam.location = center + shift + vd * dist
    look_at(cam, center + shift)
    cam.data.clip_start = max(0.001, dist * 0.01)
    cam.data.clip_end = dist * 20 + 10
    place = {
        "key": (V((0.55, -1.0, 1.9)), 1.4, 110),
        "fill": (V((-1.3, -1.2, 0.3)), 1.5, 22),
        "rim": (V((-0.7, 1.5, 1.1)), 0.7, 110),
        "kick": (V((1.5, 0.7, 0.15)), 0.8, 35),
    }
    for k, (offs, sz, energy) in place.items():
        L = lights[k]
        L.location = center + offs * size
        look_at(L, center)
        L.data.size = sz * size
        L.data.size_y = sz * size * (0.35 if k in ("rim", "kick") else 0.7)
        L.data.energy = energy * size * size * light_scale
        L.data.use_shadow = k == "key"
    floor.location = (center.x, center.y, lo.z - size * 0.002)
    floor.scale = (size * 6, size * 6, 1)


def render(path, res, samples=64):
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.cycles.samples = samples
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.04
    scn.render.use_simplify = True
    try:
        scn.cycles.texture_limit_render = "2048"
    except Exception:
        pass
    scn.cycles.adaptive_min_samples = 4
    scn.cycles.max_bounces = 5
    scn.cycles.diffuse_bounces = 2
    scn.cycles.glossy_bounces = 3
    scn.cycles.transmission_bounces = 4
    scn.cycles.transparent_max_bounces = 8
    scn.cycles.caustics_reflective = False
    scn.cycles.caustics_refractive = False
    scn.render.use_persistent_data = True
    scn.cycles.use_denoising = True
    try:
        scn.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    tmp = path + ".tmp.png"
    scn.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    composite_backdrop(tmp, path)
    os.remove(tmp)


def _backdrop(w, h):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (x / w - 0.5) * (w / h)
    v = y / h  # 0 = bottom row in Blender pixel order
    r = np.sqrt(u * u * 0.55 + (v - 0.55) ** 2 * 1.2)
    vig = np.clip(1.0 - r / 0.95, 0, 1)
    vig = vig * vig * (3 - 2 * vig)
    base = 0.07 + 0.2 * vig + 0.04 * v
    rgb = np.stack([base * 0.98, base * 0.99, base * 1.03], axis=-1)
    return np.clip(rgb, 0, 1)


def composite_backdrop(src, dst):
    im = bpy.data.images.load(src)
    w, h = im.size
    a = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    bg = _backdrop(w, h)
    alpha = a[..., 3:4]
    rgb = a[..., :3] * alpha + bg * (1 - alpha)
    # gentle film grain to avoid banding in the gradient
    rng = np.random.default_rng(1234)
    rgb += (rng.random((h, w, 1), dtype=np.float32) - 0.5) / 255.0
    out = np.concatenate([np.clip(rgb, 0, 1), np.ones((h, w, 1), np.float32)], axis=-1)
    o = bpy.data.images.new("__comp", w, h, alpha=False)
    o.pixels.foreach_set(out.ravel())
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(o)
    bpy.data.images.remove(im)


def add_label(coll, text, loc, size):
    cu = bpy.data.curves.new("lbl_" + text, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new("lbl_" + text, cu)
    coll.objects.link(ob)
    ob.location = V(loc)
    ob.rotation_euler = (math.radians(90), 0, 0)  # faces -Y (the camera side)
    m = bpy.data.materials.new("lbl")
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1)
    b.inputs["Emission Color"].default_value = (1, 1, 1, 1)
    b.inputs["Emission Strength"].default_value = 0.4
    cu.materials.append(m)
    ob.visible_shadow = False
    return ob


def bbox(objs):
    lo = V((1e9, 1e9, 1e9))
    hi = V((-1e9, -1e9, -1e9))
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ V(c)
            lo = V((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = V((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    return lo, hi


def layout_rows(groups, rows, row_gap, col_gap, label_coll=None, label_size=0.02):
    """groups: {id: [objects]} (in place).  Lays rows along +X, stacked down in Z, facing -Y.
    Returns the list of moved objects (plus labels)."""
    shown = []
    z = 0.0
    for row in rows:
        row = [i for i in row if i in groups]
        if not row:
            continue
        spans = [(i, *bbox(groups[i])) for i in row]
        height = max(hi.z - lo.z for _, lo, hi in spans)
        total = sum(hi.x - lo.x for _, lo, hi in spans) + col_gap * (len(spans) - 1)
        x = -total / 2
        for i, lo, hi in spans:
            L = hi.x - lo.x
            target = V((x + L / 2, 0, z - height / 2))
            off = target - V(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, (lo.z + hi.z) / 2))
            for o in groups[i]:
                o.location += off
                o.hide_render = False
                shown.append(o)
            if label_coll is not None:
                shown.append(add_label(label_coll, i, (target.x, -0.3 * row_gap, z - height - label_size * 1.8), label_size))
            x += L + col_gap
        z -= height + row_gap
    return shown
