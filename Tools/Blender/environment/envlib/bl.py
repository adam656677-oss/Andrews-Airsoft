"""Blender-side helpers: scene/Cycles setup, studio renders, library
materials, FBX export, JSON IO, CLI parsing."""
import json
import math
import os
import sys

import bpy  # noqa: F401  (must precede addon_utils)
import addon_utils
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
SA = os.path.join(ROOT, 'SourceAssets')
DATA = os.path.join(ROOT, 'Content', 'Airsoft', 'Data')
RENDERS = os.path.join(ROOT, 'Docs', 'Renders')
MATDIR = os.path.join(SA, 'Materials')


PREVIEW = [False]


def parse_args(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--' in argv:
        i = argv.index('--')
        flags, ids = argv[:i], argv[i + 1:]
        # allow flags after -- as well
        rest = [a for a in ids if a.startswith('--')]
        ids = [a for a in ids if not a.startswith('--')]
        flags += rest
    else:
        flags = argv
        ids = []
    opts = {'res': 4096, 'ids': [], 'render': True, 'export': True, 'lineup': True, 'samples': None,
            'lineup_only': False, 'preview': False}
    i = 0
    toks = flags
    while i < len(toks):
        t = toks[i]
        if t == '--res':
            opts['res'] = int(toks[i + 1]); i += 2; continue
        if t.startswith('--res='):
            opts['res'] = int(t.split('=')[1]); i += 1; continue
        if t == '--samples':
            opts['samples'] = int(toks[i + 1]); i += 2; continue
        if t == '--no-render':
            opts['render'] = False
        elif t == '--no-lineup':
            opts['lineup'] = False
        elif t == '--preview':
            opts['preview'] = True
            PREVIEW[0] = True
        elif t == '--lineup-only':
            opts['lineup_only'] = True
        elif t == '--no-export':
            opts['export'] = False
        elif not t.startswith('--'):
            ids.append(t)
        i += 1
    opts['ids'] = ids
    return opts


def ensure(p):
    os.makedirs(p, exist_ok=True)
    return p


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable('cycles', default_set=True)
    addon_utils.enable('io_scene_fbx', default_set=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.unit_settings.system = 'METRIC'
    return sc


def cycles_setup(samples=24, w=1920, h=1080, tex_limit='2048'):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.05
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    try:
        sc.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
        sc.cycles.denoising_prefilter = 'ACCURATE'
    except Exception:
        pass
    sc.cycles.max_bounces = 6
    sc.cycles.diffuse_bounces = 3
    sc.cycles.glossy_bounces = 3
    sc.cycles.transparent_max_bounces = 16
    sc.cycles.transmission_bounces = 4
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.use_simplify = True
    sc.cycles.texture_limit_render = tex_limit
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass
    sc.view_settings.exposure = 0.0
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    sc.render.image_settings.color_depth = '8'
    sc.render.threads_mode = 'AUTO'
    return sc


# ----------------------------------------------------------------------------
# images / library materials
# ----------------------------------------------------------------------------
def load_image(path, noncolor=False):
    name = os.path.basename(path)
    img = bpy.data.images.get(name)
    if img is None or img.filepath != path:
        img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = 'Non-Color' if noncolor else 'sRGB'
    return img


def lib_paths(mat_id):
    d = os.path.join(MATDIR, mat_id)
    p = {k: os.path.join(d, 'T_%s_%s.png' % (mat_id, k)) for k in ('BC', 'N', 'ORM', 'H', 'Opacity')}
    return p


def lib_tile(mat_id):
    from mat_defs import SPECS
    return SPECS[mat_id][0]


def dx_normal_node(nt, img_node, uv_map=None, strength=1.0):
    """Image(DX normal) -> flip G -> Normal Map node. Returns normal socket."""
    sep = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(img_node.outputs['Color'], sep.inputs['Color'])
    inv = nt.nodes.new('ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    nt.links.new(sep.outputs[1], inv.inputs[1])
    comb = nt.nodes.new('ShaderNodeCombineColor')
    nt.links.new(sep.outputs[0], comb.inputs[0])
    nt.links.new(inv.outputs[0], comb.inputs[1])
    nt.links.new(sep.outputs[2], comb.inputs[2])
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nm.inputs['Strength'].default_value = strength
    if uv_map:
        nm.uv_map = uv_map
    nt.links.new(comb.outputs[0], nm.inputs['Color'])
    return nm.outputs['Normal']


def lib_material(mat_id, uv_scale=None, uv_map='UVMap', name=None, tint=None):
    """MI_<Id> render material using the library textures.

    uv_scale: multiply UVs by this (architecture: 2/TileMeters)."""
    name = name or 'MI_' + mat_id
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(bsdf.outputs[0], out.inputs['Surface'])
    p = lib_paths(mat_id)
    uv = nt.nodes.new('ShaderNodeUVMap')
    uv.uv_map = uv_map
    vec = uv.outputs['UV']
    if uv_scale is None:
        uv_scale = 2.0 / lib_tile(mat_id)
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (uv_scale, uv_scale, 1)
    nt.links.new(vec, mp.inputs['Vector'])
    vec = mp.outputs['Vector']

    def tex(path, nc):
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = load_image(path, nc)
        t.interpolation = 'Linear'
        nt.links.new(vec, t.inputs['Vector'])
        return t
    bc = tex(p['BC'], False)
    if tint is not None:
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        nt.links.new(bc.outputs['Color'], mix.inputs[6])
        mix.inputs[7].default_value = tuple(tint) + (1,)
        nt.links.new(mix.outputs[2], bsdf.inputs['Base Color'])
    else:
        nt.links.new(bc.outputs['Color'], bsdf.inputs['Base Color'])
    orm = tex(p['ORM'], True)
    sep = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(orm.outputs['Color'], sep.inputs['Color'])
    nt.links.new(sep.outputs[1], bsdf.inputs['Roughness'])
    nt.links.new(sep.outputs[2], bsdf.inputs['Metallic'])
    n = tex(p['N'], True)
    nt.links.new(dx_normal_node(nt, n, uv_map), bsdf.inputs['Normal'])
    if os.path.exists(p['Opacity']):
        op = tex(p['Opacity'], True)
        nt.links.new(op.outputs['Color'], bsdf.inputs['Alpha'])
    if mat_id == 'Velvet':
        bsdf.inputs['Sheen Weight'].default_value = 1.0
        bsdf.inputs['Sheen Roughness'].default_value = 0.35
    if mat_id in ('Burlap', 'Carpet'):
        bsdf.inputs['Sheen Weight'].default_value = 0.3
    return m


def baked_material(name, prefix, has_mask=False, tint=None, opacity=False, emissive=None):
    """Render material from a baked set T_<prefix>_BC/N/ORM(/M)."""
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(bsdf.outputs[0], out.inputs['Surface'])
    uv = nt.nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'UVMap'

    def tex(path, nc):
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = load_image(path, nc)
        nt.links.new(uv.outputs['UV'], t.inputs['Vector'])
        return t
    bc = tex(prefix + '_BC.png', False)
    col_out = bc.outputs['Color']
    if has_mask and tint is not None:
        mk = tex(prefix + '_M.png', True)
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(mk.outputs['Color'], sep.inputs['Color'])
        mul = nt.nodes.new('ShaderNodeMix')
        mul.data_type = 'RGBA'
        mul.blend_type = 'MULTIPLY'
        nt.links.new(sep.outputs[0], mul.inputs['Factor'])
        nt.links.new(col_out, mul.inputs[6])
        mul.inputs[7].default_value = tuple(tint) + (1,)
        col_out = mul.outputs[2]
    nt.links.new(col_out, bsdf.inputs['Base Color'])
    orm = tex(prefix + '_ORM.png', True)
    sep = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(orm.outputs['Color'], sep.inputs['Color'])
    nt.links.new(sep.outputs[1], bsdf.inputs['Roughness'])
    nt.links.new(sep.outputs[2], bsdf.inputs['Metallic'])
    n = tex(prefix + '_N.png', True)
    nt.links.new(dx_normal_node(nt, n, 'UVMap'), bsdf.inputs['Normal'])
    if opacity:
        op = tex(prefix + '_Opacity.png', True)
        nt.links.new(op.outputs['Color'], bsdf.inputs['Alpha'])
    if emissive is not None:
        bsdf.inputs['Emission Color'].default_value = tuple(emissive) + (1,)
        bsdf.inputs['Emission Strength'].default_value = 1.0
    return m


def simple_material(name, color, rough=0.5, metal=0.0, transmission=0.0, emission=None, alpha=1.0, ior=1.5):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = tuple(color) + (1,)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    b.inputs['Transmission Weight'].default_value = transmission
    b.inputs['IOR'].default_value = ior
    b.inputs['Alpha'].default_value = alpha
    if emission is not None:
        b.inputs['Emission Color'].default_value = tuple(emission[:3]) + (1,)
        b.inputs['Emission Strength'].default_value = emission[3] if len(emission) > 3 else 1.0
    return m


# ----------------------------------------------------------------------------
# studio
# ----------------------------------------------------------------------------
def _area(name, loc, target, size, power, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.shape = 'DISK'
    ld.size = size
    ld.energy = power
    ld.color = color
    o = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    d = Vector(target) - Vector(loc)
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return o


def studio(center, radius, az_deg=-38.0, floor_z=0.0, key=1.0, cyc_color=(0.36, 0.36, 0.35), dark=False):
    """Soft three-point studio, gradient world and a cyclorama behind the
    subject (relative to the camera azimuth)."""
    sc = bpy.context.scene
    w = bpy.data.worlds.new('Studio')
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.32, 0.33, 0.35, 1) if not dark else (0.05, 0.05, 0.06, 1)
    ramp.color_ramp.elements[1].position = 0.6
    ramp.color_ramp.elements[1].color = (0.12, 0.13, 0.15, 1) if not dark else (0.02, 0.02, 0.025, 1)
    nt.links.new(sep.outputs['Z'], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 0.45
    nt.links.new(bg.outputs[0], out.inputs[0])

    r = max(radius, 0.3)
    c = Vector(center)
    az = math.radians(az_deg)
    fwd = Vector((math.cos(az), math.sin(az), 0))  # camera side direction
    side = Vector((-fwd.y, fwd.x, 0))
    # key: front-left high; fill: right low; rim: back
    kd = r * 3.2
    _area('Key', c + (fwd * 0.6 + side * 0.8).normalized() * kd + Vector((0, 0, kd * 0.85)), c, r * 2.2,
          420 * key * (kd / 3.2) ** 2, (1.0, 0.95, 0.88))
    fd = r * 3.5
    _area('Fill', c + (fwd * 0.8 - side * 0.7).normalized() * fd + Vector((0, 0, fd * 0.25)), c, r * 3.0,
          110 * key * (fd / 3.5) ** 2, (0.82, 0.9, 1.0))
    rd = r * 3.0
    _area('Rim', c + (-fwd * 0.9 + side * 0.3).normalized() * rd + Vector((0, 0, rd * 0.9)), c, r * 1.6,
          520 * key * (rd / 3.0) ** 2, (1.0, 1.0, 1.0))

    # cyclorama
    import bmesh
    bm = bmesh.new()
    R = r * 2.0
    back = r * 3.0
    width = r * 14.0
    prof = []
    front = r * 12.0
    prof.append((front, 0.0))
    prof.append((-back + R, 0.0))
    for k in range(1, 13):
        a = k / 12 * math.pi / 2
        prof.append((-back + R - math.sin(a) * R, R - math.cos(a) * R))
    prof.append((-back, r * 10.0))
    rows = []
    for (d, z) in prof:
        row = []
        for s in (-width, width):
            p = c * 0 + Vector((c.x, c.y, floor_z)) + fwd * d + side * s
            p.z = floor_z + z
            row.append(bm.verts.new(p))
        rows.append(row)
    for a, b in zip(rows[:-1], rows[1:]):
        bm.faces.new((a[0], a[1], b[1], b[0]))
    me = bpy.data.meshes.new('Cyc')
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new('Cyc', me)
    sc.collection.objects.link(o)
    mat = bpy.data.materials.new('CycMat')
    mat.use_nodes = True
    b = mat.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = tuple(cyc_color) + (1,)
    b.inputs['Roughness'].default_value = 0.75
    me.materials.append(mat)
    return o


def camera_fit(corners, az_deg=-38.0, el_deg=18.0, lens=60.0, margin=1.08, target=None, shift_z=0.0):
    """Place a camera looking from (az, el) so all corners fit the frame."""
    sc = bpy.context.scene
    cd = bpy.data.cameras.new('Cam')
    cd.lens = lens
    cd.sensor_fit = 'HORIZONTAL'
    cd.sensor_width = 36.0
    cam = bpy.data.objects.new('Cam', cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    pts = [Vector(p) for p in corners]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    tgt = Vector(target) if target else (lo + hi) / 2
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    back = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
    fwd = -back
    right = fwd.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(fwd).normalized()
    W = sc.render.resolution_x
    H = sc.render.resolution_y
    th = 18.0 / lens  # tan(hfov/2)
    tv = th * H / W
    th /= margin
    tv /= margin
    d = 0.0
    for _ in range(2):
        need = 0
        for p in pts:
            q = p - tgt
            a = q.dot(right)
            b = q.dot(up)
            f = q.dot(fwd)
            need = max(need, abs(a) / th + f, abs(b) / tv + f)
        d = need
    cam.location = tgt - fwd * d
    cam.rotation_euler = fwd.to_track_quat('-Z', 'Y').to_euler()
    cd.clip_start = max(0.01, d * 0.01)
    cd.clip_end = d * 50
    return cam, tgt, d


def bbox_world(objs):
    pts = []
    for o in objs:
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    return pts


def render_to(path, samples=None):
    sc = bpy.context.scene
    if samples:
        sc.cycles.samples = samples
    ensure(os.path.dirname(path))
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def product_shot(objs, path, az=-38.0, el=16.0, lens=60.0, samples=24, margin=1.1, key=1.0, w=1920, h=1080,
                 tex_limit='2048', target=None):
    if PREVIEW[0]:
        w, h, samples, tex_limit = w // 2, h // 2, 8, '1024'
        path = path.replace('Docs/Renders', 'Docs/Renders/_preview')
    cycles_setup(samples, w, h, tex_limit)
    pts = bbox_world(objs)
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2
    r = (hi - lo).length / 2
    camera_fit(pts, az, el, lens, margin, target=target)
    studio(c, r, az_deg=az, floor_z=lo.z, key=key)
    render_to(path)


def clear_scene_extras():
    """Remove cameras, lights, cyc from a scene (keep meshes)."""
    for o in list(bpy.data.objects):
        if o.type in ('CAMERA', 'LIGHT') or o.name.startswith('Cyc') or o.name.startswith('Label'):
            bpy.data.objects.remove(o, do_unlink=True)


# ----------------------------------------------------------------------------
# export / json
# ----------------------------------------------------------------------------
def export_fbx(obj, path):
    ensure(os.path.dirname(path))
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'},
                             axis_forward='X', axis_up='Z', apply_unit_scale=True, global_scale=1.0,
                             apply_scale_options='FBX_SCALE_ALL', use_tspace=True, mesh_smooth_type='FACE',
                             add_leaf_bones=False, use_mesh_modifiers=True, bake_anim=False,
                             path_mode='STRIP', embed_textures=False)


def ue(v):
    return [round(v[0] * 100, 1), round(-v[1] * 100, 1), round(v[2] * 100, 1)]


def bounds_ue(objs):
    pts = bbox_world(objs)
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    a = ue(lo)
    b = ue(hi)
    return {'Min': [min(a[i], b[i]) for i in range(3)], 'Max': [max(a[i], b[i]) for i in range(3)]}


def json_update(name, key, entries, extra=None):
    path = os.path.join(DATA, name)
    ensure(DATA)
    d = {'Version': 1, key: {}}
    if os.path.exists(path):
        try:
            d = json.load(open(path))
        except Exception:
            pass
    d.setdefault(key, {})
    d[key].update(entries)
    d[key] = dict(sorted(d[key].items()))
    if extra:
        d.update(extra)
    with open(path, 'w') as f:
        json.dump(d, f, indent=2)
        f.write('\n')


def tri_count(obj):
    me = obj.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)
