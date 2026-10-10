"""
Shared UV + PBR texture baking helpers for the Blender asset generators.

Usage (from a generator, after its mesh objects are final):

    import common_bake as cb
    cb.setup_bake_engine()
    info = cb.bake_object(ob, recipe="anodized", tint=True, out_res=1024, tag="M4_Body")
    cb.apply_export_material(ob, info)       # glTF-friendly image material
    ...export...
    cb.apply_render_material(ob, info, tint_rgb=(0.03, 0.03, 0.03))   # preview renders only

What gets baked (per object, one texture set):
    colour      JPEG, sRGB.  Tintable roles are neutral light grey (~0.8 linear) with
                luminance-only wear/grime so the game can tint them per skin.
    normal      PNG, tangent space, OpenGL (+Y up).  Edge rounding (bevel shader) and
                procedural micro detail (stipple, grain, machining marks, wood grain, weave).
    metal/rough PNG packed the glTF way: G = roughness, B = metallic.

Procedural materials are evaluated at 2x the output resolution with one sample per
texel and box-filtered down to the output size (4x supersampling), which is far
faster on CPU than many-sample bakes.  Results are cached on disk keyed by a hash of
the mesh, its UVs and the recipe, so re-running a generator only re-bakes what changed.
"""

import hashlib
import json
import math
import os
import tempfile

import bpy  # noqa: I001
import bmesh  # noqa: F401
import numpy as np

BAKE_VERSION = 7
SUPERSAMPLE = 2  # bake at out_res * SUPERSAMPLE, then box-filter down
JPEG_QUALITY = 92
TINT_GREY = 0.8  # linear value tintable roles are baked at

CACHE_DIR = os.environ.get(
    "BAKE_CACHE_DIR",
    os.path.join(tempfile.gettempdir(), "andrews_airsoft_bake_cache"),
)

# --------------------------------------------------------------------------------------
# Material recipes
# --------------------------------------------------------------------------------------
# colour/rough/metal: clean surface.  wear_*: what shows on worn convex edges.
# micro: (kind, scale, strength) height detail for the normal map.
# grime: darkening/roughening in cavities (0..1).  var: large-scale mottling (0..1).

RECIPES = {
    "anodized": dict(color=(0.026, 0.026, 0.028), rough=0.42, metal=0.3, wear_color=(0.62, 0.62, 0.64), wear_rough=0.26, wear_metal=1.0, wear=1.0, micro=("grain", 900.0, 0.08), grime=0.55, var=0.25, scratches=0.6),
    "polymer": dict(color=(0.024, 0.024, 0.026), rough=0.62, metal=0.0, wear_color=(0.05, 0.05, 0.052), wear_rough=0.38, wear_metal=0.0, wear=0.6, micro=("stipple", 420.0, 0.22), grime=0.6, var=0.3, scratches=0.25),
    "polymer_dark": dict(color=(0.014, 0.014, 0.015), rough=0.66, metal=0.0, wear_color=(0.035, 0.035, 0.037), wear_rough=0.4, wear_metal=0.0, wear=0.5, micro=("stipple", 420.0, 0.22), grime=0.6, var=0.3, scratches=0.2),
    "fde": dict(color=(0.25, 0.18, 0.105), rough=0.62, metal=0.0, wear_color=(0.33, 0.25, 0.16), wear_rough=0.42, wear_metal=0.0, wear=0.6, micro=("stipple", 420.0, 0.22), grime=0.7, var=0.35, scratches=0.25),
    "od": dict(color=(0.085, 0.09, 0.05), rough=0.62, metal=0.0, wear_color=(0.13, 0.135, 0.085), wear_rough=0.42, wear_metal=0.0, wear=0.6, micro=("stipple", 420.0, 0.22), grime=0.7, var=0.35, scratches=0.25),
    "plum": dict(color=(0.11, 0.035, 0.03), rough=0.5, metal=0.0, wear_color=(0.17, 0.06, 0.05), wear_rough=0.35, wear_metal=0.0, wear=0.6, micro=("grain", 600.0, 0.1), grime=0.6, var=0.4, scratches=0.3),
    "smoke": dict(color=(0.085, 0.08, 0.068), rough=0.2, metal=0.0, wear_color=(0.12, 0.115, 0.1), wear_rough=0.32, wear_metal=0.0, wear=0.5, micro=("grain", 700.0, 0.04), grime=0.5, var=0.2, scratches=0.5),
    "parkerized": dict(color=(0.055, 0.06, 0.056), rough=0.64, metal=0.55, wear_color=(0.42, 0.42, 0.43), wear_rough=0.24, wear_metal=1.0, wear=1.2, micro=("grain", 1100.0, 0.16), grime=0.6, var=0.35, scratches=0.5),
    "gunmetal": dict(color=(0.05, 0.053, 0.058), rough=0.34, metal=0.9, wear_color=(0.5, 0.5, 0.52), wear_rough=0.2, wear_metal=1.0, wear=1.0, micro=("brushed", 500.0, 0.05), grime=0.5, var=0.25, scratches=0.6),
    "steel": dict(color=(0.3, 0.3, 0.31), rough=0.3, metal=1.0, wear_color=(0.62, 0.62, 0.63), wear_rough=0.16, wear_metal=1.0, wear=0.9, micro=("brushed", 500.0, 0.05), grime=0.5, var=0.3, scratches=0.7),
    "wood": dict(color=(0.15, 0.06, 0.022), rough=0.4, metal=0.0, wear_color=(0.3, 0.15, 0.065), wear_rough=0.62, wear_metal=0.0, wear=0.8, micro=("wood", 1.0, 0.12), grime=0.5, var=0.5, scratches=0.4, grain=True),
    "wood_light": dict(color=(0.24, 0.11, 0.045), rough=0.45, metal=0.0, wear_color=(0.4, 0.22, 0.1), wear_rough=0.62, wear_metal=0.0, wear=0.8, micro=("wood", 1.0, 0.12), grime=0.5, var=0.5, scratches=0.4, grain=True),
    "tape": dict(color=(0.62, 0.62, 0.6), rough=0.82, metal=0.0, wear_color=(0.7, 0.7, 0.68), wear_rough=0.9, wear_metal=0.0, wear=0.4, micro=("weave", 260.0, 0.35), grime=0.8, var=0.5, scratches=0.0),
    "rubber": dict(color=(0.016, 0.016, 0.016), rough=0.88, metal=0.0, wear_color=(0.03, 0.03, 0.03), wear_rough=0.7, wear_metal=0.0, wear=0.3, micro=("stipple", 300.0, 0.3), grime=0.5, var=0.2, scratches=0.0),
    "glass": dict(color=(0.05, 0.11, 0.13), rough=0.04, metal=0.0, wear_color=(0.05, 0.11, 0.13), wear_rough=0.04, wear_metal=0.0, wear=0.0, micro=("none", 1.0, 0.0), grime=0.0, var=0.0, scratches=0.0),
    "reticle": dict(color=(1.0, 0.05, 0.03), rough=0.4, metal=0.0, wear_color=(1.0, 0.05, 0.03), wear_rough=0.4, wear_metal=0.0, wear=0.0, micro=("none", 1.0, 0.0), grime=0.0, var=0.0, scratches=0.0),
    "brass": dict(color=(0.55, 0.38, 0.12), rough=0.3, metal=1.0, wear_color=(0.75, 0.6, 0.3), wear_rough=0.2, wear_metal=1.0, wear=0.6, micro=("grain", 900.0, 0.03), grime=0.6, var=0.4, scratches=0.3),
    "fabric": dict(color=(0.09, 0.095, 0.06), rough=0.9, metal=0.0, wear_color=(0.13, 0.135, 0.09), wear_rough=0.95, wear_metal=0.0, wear=0.5, micro=("weave", 180.0, 0.5), grime=0.8, var=0.5, scratches=0.0),
}

# --------------------------------------------------------------------------------------
# Small node-graph builder
# --------------------------------------------------------------------------------------


class NB:
    def __init__(self, nt):
        self.nt = nt
        self.x = 0

    def node(self, kind, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        n.location = (self.x, 0)
        self.x += 40
        return n

    def _in(self, sock, val):
        if val is None:
            return
        if isinstance(val, bpy.types.NodeSocket):
            self.nt.links.new(val, sock)
        else:
            sock.default_value = val

    def math(self, op, a, b=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._in(n.inputs[0], a)
        if b is not None:
            self._in(n.inputs[1], b)
        return n.outputs[0]

    def mul(self, a, b, clamp=False):
        return self.math("MULTIPLY", a, b, clamp)

    def add(self, a, b, clamp=False):
        return self.math("ADD", a, b, clamp)

    def sub(self, a, b, clamp=False):
        return self.math("SUBTRACT", a, b, clamp)

    def maprange(self, v, a, b, c=0.0, d=1.0, clamp=True, smooth=False):
        n = self.node("ShaderNodeMapRange", clamp=clamp, interpolation_type="SMOOTHSTEP" if smooth else "LINEAR")
        self._in(n.inputs["Value"], v)
        n.inputs["From Min"].default_value = a
        n.inputs["From Max"].default_value = b
        n.inputs["To Min"].default_value = c
        n.inputs["To Max"].default_value = d
        return n.outputs["Result"]

    def lerp(self, f, a, b):
        n = self.node("ShaderNodeMix", data_type="FLOAT", clamp_factor=True)
        self._in(n.inputs["Factor_Float"], f)
        self._in(n.inputs["A_Float"], a)
        self._in(n.inputs["B_Float"], b)
        return n.outputs["Result_Float"]

    def mixc(self, f, a, b, blend="MIX"):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_factor=True)
        self._in(n.inputs["Factor_Float"], f)
        self._in(n.inputs["A_Color"], a if isinstance(a, bpy.types.NodeSocket) else (*a, 1.0))
        self._in(n.inputs["B_Color"], b if isinstance(b, bpy.types.NodeSocket) else (*b, 1.0))
        return n.outputs["Result_Color"]

    def vscale(self, v, s):
        n = self.node("ShaderNodeVectorMath", operation="MULTIPLY")
        self._in(n.inputs[0], v)
        self._in(n.inputs[1], s)
        return n.outputs["Vector"]

    def noise(self, vec, scale, detail=3.0, rough=0.55, dist=0.0, dims="3D"):
        n = self.node("ShaderNodeTexNoise", noise_dimensions=dims)
        self._in(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        n.inputs["Distortion"].default_value = dist
        return n.outputs["Fac"]

    def voronoi(self, vec, scale, feature="F1", rand=1.0):
        n = self.node("ShaderNodeTexVoronoi", feature=feature)
        self._in(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        n.inputs["Randomness"].default_value = rand
        return n.outputs["Distance"]

    def wave(self, vec, scale, dist=0.0, detail=2.0, direction="X", kind="BANDS", profile="SIN"):
        n = self.node("ShaderNodeTexWave", wave_type=kind, wave_profile=profile)
        if kind == "BANDS":
            n.bands_direction = direction
        else:
            n.rings_direction = direction
        self._in(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        n.inputs["Distortion"].default_value = dist
        n.inputs["Detail"].default_value = detail
        return n.outputs["Fac"]

    def combine(self, r, g, b):
        n = self.node("ShaderNodeCombineColor")
        self._in(n.inputs["Red"], r)
        self._in(n.inputs["Green"], g)
        self._in(n.inputs["Blue"], b)
        return n.outputs["Color"]

    def separate(self, c):
        n = self.node("ShaderNodeSeparateColor")
        self._in(n.inputs["Color"], c)
        return n.outputs["Red"], n.outputs["Green"], n.outputs["Blue"]

    def emit(self, color):
        n = self.node("ShaderNodeEmission")
        self._in(n.inputs["Color"], color)
        n.inputs["Strength"].default_value = 1.0
        return n.outputs["Emission"]


def _output(nt):
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.target = "ALL"
    return out


def _fresh_material(name):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    return m


# --------------------------------------------------------------------------------------
# Procedural surface graph
# --------------------------------------------------------------------------------------


def _coords(nb):
    geo = nb.node("ShaderNodeNewGeometry")
    return geo


def _height(nb, pos, r, seed):
    """Micro-detail height field for the normal map (0..1-ish)."""
    kind, scale, _ = r["micro"]
    off = nb.node("ShaderNodeVectorMath", operation="ADD")
    nb._in(off.inputs[0], pos)
    off.inputs[1].default_value = (seed * 3.17, seed * 1.91, seed * 2.53)
    p = off.outputs["Vector"]
    if kind == "stipple":
        d = nb.voronoi(p, scale, "F1")
        h = nb.maprange(d, 0.0, 0.6, 1.0, 0.0, smooth=True)
        fine = nb.noise(p, scale * 2.5, 2.0)
        return nb.add(nb.mul(h, 0.8), nb.mul(fine, 0.2))
    if kind == "grain":
        return nb.noise(p, scale, 4.0, 0.6)
    if kind == "brushed":
        st = nb.vscale(p, (1.0, 0.03, 1.0))
        return nb.noise(st, scale, 3.0, 0.6)
    if kind == "wood":
        return _wood_grain(nb, p)[1]
    if kind == "weave":
        a = nb.wave(p, scale, 0.0, 0.0, "X")
        b = nb.wave(p, scale, 0.0, 0.0, "Y")
        c = nb.wave(p, scale, 0.0, 0.0, "Z")
        return nb.math("MAXIMUM", nb.math("MAXIMUM", a, b), c)
    return 0.0


def _wood_grain(nb, p):
    """Returns (colour factor, height) for wood grain running along the Y axis."""
    st = nb.vscale(p, (1.0, 0.12, 1.0))
    warp = nb.noise(st, 6.0, 3.0, 0.6)
    rings = nb.node("ShaderNodeTexWave", wave_type="RINGS", rings_direction="Y", wave_profile="SAW")
    nb._in(rings.inputs["Vector"], st)
    rings.inputs["Scale"].default_value = 9.0
    rings.inputs["Distortion"].default_value = 9.0
    rings.inputs["Detail"].default_value = 3.0
    rings.inputs["Detail Scale"].default_value = 1.5
    f = nb.add(nb.mul(rings.outputs["Fac"], 0.7), nb.mul(warp, 0.3))
    pores = nb.noise(nb.vscale(p, (1.0, 0.05, 1.0)), 260.0, 2.0)
    h = nb.add(nb.mul(f, 0.4), nb.mul(pores, 0.6))
    return f, h


def build_bake_graph(mat, r, tint, mask_img, seed, edge_radius):
    """Creates every node; returns dict of output sockets for each bake pass."""
    nt = mat.node_tree
    nb = NB(nt)
    geo = nb.node("ShaderNodeNewGeometry")
    pos = geo.outputs["Position"]
    outs = {}

    # ---- mask pass: R = edge (any), G = AO, B = convex edge
    bev = nb.node("ShaderNodeBevel", samples=8)
    bev.inputs["Radius"].default_value = edge_radius * 2.5
    dot = nb.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nb._in(dot.inputs[0], bev.outputs["Normal"])
    nb._in(dot.inputs[1], geo.outputs["Normal"])
    edge = nb.maprange(dot.outputs["Value"], 0.995, 0.75, 0.0, 1.0)
    ao = nb.node("ShaderNodeAmbientOcclusion", samples=12, only_local=True)
    ao.inputs["Distance"].default_value = 0.06
    ao_v = ao.outputs["AO"]
    convex = nb.mul(edge, nb.maprange(ao_v, 0.55, 0.9, 0.0, 1.0))
    outs["mask"] = nb.emit(nb.combine(edge, ao_v, convex))

    # ---- normal pass
    bev2 = nb.node("ShaderNodeBevel", samples=8)
    bev2.inputs["Radius"].default_value = edge_radius
    h = _height(nb, pos, r, seed)
    kind, scale, strength = r["micro"]
    principled = nb.node("ShaderNodePrincipledBSDF")
    if strength > 0 and kind != "none":
        bump = nb.node("ShaderNodeBump")
        bump.inputs["Strength"].default_value = min(1.0, strength)
        bump.inputs["Distance"].default_value = 0.0015 if kind != "wood" else 0.001
        nb._in(bump.inputs["Height"], h)
        nb._in(bump.inputs["Normal"], bev2.outputs["Normal"])
        nb._in(principled.inputs["Normal"], bump.outputs["Normal"])
    else:
        nb._in(principled.inputs["Normal"], bev2.outputs["Normal"])
    outs["normal"] = principled.outputs[0]

    # ---- shared masks for colour / roughness / metal (read back from the mask image)
    if mask_img is not None:
        uv = nb.node("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        img = nb.node("ShaderNodeTexImage", image=mask_img, interpolation="Linear")
        nb._in(img.inputs["Vector"], uv.outputs["UV"])
        m_edge, m_ao, m_convex = nb.separate(img.outputs["Color"])
    else:
        m_edge, m_ao, m_convex = 0.0, 1.0, 0.0

    off = nb.node("ShaderNodeVectorMath", operation="ADD")
    nb._in(off.inputs[0], pos)
    off.inputs[1].default_value = (seed * 7.1, seed * 3.3, seed * 5.7)
    p = off.outputs["Vector"]

    # edge wear: convex edges broken up by noise, plus sparse scratches
    wn = nb.noise(p, 38.0, 6.0, 0.7)
    wear_raw = nb.sub(nb.mul(m_convex, 1.25 * r["wear"]), nb.mul(nb.maprange(wn, 0.35, 0.65, 0.0, 1.0), 0.75))
    wear = nb.maprange(wear_raw, 0.05, 0.35, 0.0, 1.0, smooth=True)
    if r["scratches"] > 0:
        sc = nb.noise(nb.vscale(p, (1.0, 0.04, 1.0)), 60.0, 4.0, 0.7, dist=0.4)
        sc2 = nb.noise(nb.vscale(p, (0.05, 1.0, 1.0)), 45.0, 4.0, 0.7, dist=0.4)
        sline = nb.math("MAXIMUM", nb.maprange(sc, 0.71, 0.74, 0.0, 1.0), nb.maprange(sc2, 0.72, 0.745, 0.0, 1.0))
        spots = nb.maprange(nb.noise(p, 4.0, 2.0), 0.45, 0.7, 0.0, 1.0)
        wear = nb.math("MAXIMUM", wear, nb.mul(nb.mul(sline, spots), 0.55 * r["scratches"]))
    # grime in cavities
    gn = nb.noise(p, 12.0, 4.0, 0.6)
    grime = nb.mul(nb.maprange(m_ao, 0.95, 0.35, 0.0, 1.0), nb.add(0.5, nb.mul(gn, 0.8)))
    grime = nb.mul(grime, r["grime"], clamp=True)
    # large scale mottling
    mot = nb.noise(p, 2.5, 3.0, 0.5)
    mot2 = nb.noise(p, 30.0, 2.0, 0.5)
    var = nb.mul(nb.add(nb.sub(mot, 0.5), nb.mul(nb.sub(mot2, 0.5), 0.5)), r["var"])

    # colour
    if r.get("grain"):
        gf, _gh = _wood_grain(nb, pos)
        dark = tuple(c * 0.55 for c in r["color"])
        base = nb.mixc(nb.maprange(gf, 0.2, 0.9, 0.0, 1.0), r["color"], dark)
    else:
        base = r["color"]
    if tint:
        # luminance only: neutral grey with the same relative variation
        lum_wear = TINT_GREY * 1.22
        base_v = nb.add(TINT_GREY, nb.mul(var, 0.25))
        cval = nb.lerp(wear, base_v, lum_wear)
        cval = nb.mul(cval, nb.sub(1.0, nb.mul(grime, 0.55)))
        col = nb.combine(cval, cval, cval)
    else:
        c0 = nb.mixc(nb.add(0.5, var), (0, 0, 0), (1, 1, 1))  # 0.5 +- var as grey
        tinted = nb.mixc(1.0, base, c0, "MULTIPLY") if not isinstance(base, tuple) else nb.mixc(1.0, base, c0, "MULTIPLY")
        tinted = nb.mixc(1.0, tinted, (2.0, 2.0, 2.0), "MULTIPLY")
        col = nb.mixc(wear, tinted, r["wear_color"])
        col = nb.mixc(nb.mul(grime, 0.6), col, (0.0, 0.0, 0.0))
    outs["color"] = nb.emit(col)

    # roughness / metallic
    rv = nb.add(r["rough"], nb.mul(var, 0.35))
    rv = nb.add(rv, nb.mul(nb.sub(nb.noise(p, 160.0, 3.0), 0.5), 0.12))
    rough = nb.lerp(wear, rv, r["wear_rough"])
    rough = nb.lerp(nb.mul(grime, 0.7), rough, min(1.0, r["rough"] + 0.3))
    metal = nb.lerp(wear, r["metal"], r["wear_metal"])
    outs["mr"] = nb.emit(nb.combine(0.0, nb.math("MAXIMUM", nb.math("MINIMUM", rough, 1.0), 0.03), metal))
    return outs


# --------------------------------------------------------------------------------------
# UVs
# --------------------------------------------------------------------------------------


def uv_unwrap(ob, angle=62.0, margin=0.006):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    me = ob.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    try:
        bpy.ops.uv.pack_islands(rotate=True, margin=margin, shape_method="CONVEX")
    except TypeError:
        bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)


# --------------------------------------------------------------------------------------
# Baking
# --------------------------------------------------------------------------------------

_engine_state = {}


def setup_bake_engine():
    scn = bpy.context.scene
    _engine_state["engine"] = scn.render.engine
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    _engine_state["samples"] = scn.cycles.samples
    scn.cycles.samples = 1
    scn.cycles.use_adaptive_sampling = False
    scn.cycles.use_denoising = False
    scn.render.bake.margin = 8
    scn.render.bake.margin_type = "EXTEND"
    scn.render.bake.use_clear = True


def restore_render_engine(samples=None):
    scn = bpy.context.scene
    if samples is not None:
        scn.cycles.samples = samples


def _mesh_hash(ob, recipe_key, extra):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    uv = np.empty(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    idx = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", idx)
    h = hashlib.sha1()
    h.update(np.round(co, 5).tobytes())
    h.update(np.round(uv, 5).tobytes())
    h.update(idx.tobytes())
    h.update(np.round(np.array(ob.location, dtype=np.float32), 5).tobytes())
    h.update(json.dumps([recipe_key, extra, BAKE_VERSION], sort_keys=True, default=str).encode())
    return h.hexdigest()[:20]


def _new_float_image(name, res):
    im = bpy.data.images.get(name)
    if im:
        bpy.data.images.remove(im)
    im = bpy.data.images.new(name, res, res, alpha=False, float_buffer=True)
    im.colorspace_settings.name = "Non-Color"
    return im


def _pixels(im):
    a = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    return a.reshape(im.size[1], im.size[0], 4)


def _downscale(a, f):
    if f == 1:
        return a
    h, w, c = a.shape
    return a.reshape(h // f, f, w // f, f, c).mean(axis=(1, 3))


def _srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _save_byte(arr, path, fmt, srgb, quality=JPEG_QUALITY):
    h, w, _ = arr.shape
    name = "tmp_save"
    im = bpy.data.images.get(name)
    if im:
        bpy.data.images.remove(im)
    im = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    out = arr.copy()
    out[..., 3] = 1.0
    if srgb:
        out[..., :3] = _srgb(out[..., :3])
    out = np.clip(out, 0, 1)
    out = np.round(out * 255.0) / 255.0  # quantise exactly
    im.pixels.foreach_set(out.astype(np.float32).ravel())
    im.filepath_raw = path
    im.file_format = fmt
    if fmt == "JPEG":
        im.save(filepath=path, quality=quality)
    else:
        im.save(filepath=path)
    bpy.data.images.remove(im)


def _bake(ob, mat, socket, img, kind):
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    nt.links.new(socket, out.inputs["Surface"])
    tex = nt.nodes.get("__bake_target")
    if tex is None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.name = "__bake_target"
    tex.image = img
    for n in nt.nodes:
        n.select = False
    tex.select = True
    nt.nodes.active = tex
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    if kind == "NORMAL":
        bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y", normal_b="POS_Z", margin=8 * SUPERSAMPLE, use_clear=True)
    else:
        bpy.ops.object.bake(type="EMIT", margin=8 * SUPERSAMPLE, use_clear=True)
    ob.select_set(False)


def bake_object(ob, recipe, tint, out_res=1024, tag=None, seed=0, edge_radius=0.006, force=False):
    """UV-unwraps (if needed) and bakes colour / normal / metal-rough for one object.
    Returns a dict with file paths and settings."""
    if not ob.data.uv_layers:
        uv_unwrap(ob)
    r = dict(RECIPES[recipe])
    key = _mesh_hash(ob, recipe, [tint, out_res, seed, edge_radius, sorted(r.items())])
    tag = tag or ob.name
    folder = os.path.join(CACHE_DIR, f"{tag}_{key}")
    paths = {k: os.path.join(folder, f"{tag}_{k}.{ext}") for k, ext in (("color", "jpg"), ("normal", "png"), ("mr", "png"))}
    info = dict(paths=paths, recipe=recipe, tint=tint, res=out_res, tag=tag, cached=True)
    if not force and all(os.path.exists(p) for p in paths.values()):
        return info
    info["cached"] = False
    os.makedirs(folder, exist_ok=True)
    res = out_res * SUPERSAMPLE
    saved = list(ob.data.materials)
    mat = _fresh_material(f"__bake_{tag}")
    _output(mat.node_tree)
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    # pass 1: masks
    mask = _new_float_image(f"__mask_{tag}", res)
    outs = build_bake_graph(mat, r, tint, None, seed, edge_radius)
    _bake(ob, mat, outs["mask"], mask, "EMIT")
    # rebuild graph reading the mask
    mat.node_tree.nodes.clear()
    _output(mat.node_tree)
    outs = build_bake_graph(mat, r, tint, mask, seed, edge_radius)
    results = {}
    for passname, kind in (("color", "EMIT"), ("mr", "EMIT"), ("normal", "NORMAL")):
        img = _new_float_image(f"__{passname}_{tag}", res)
        _bake(ob, mat, outs[passname], img, kind)
        a = _downscale(_pixels(img), SUPERSAMPLE)
        if passname == "normal":
            v = a[..., :3] * 2.0 - 1.0
            v /= np.maximum(np.linalg.norm(v, axis=2, keepdims=True), 1e-6)
            a[..., :3] = v * 0.5 + 0.5
        results[passname] = a
        bpy.data.images.remove(img)
    bpy.data.images.remove(mask)
    _save_byte(results["color"], paths["color"], "JPEG", srgb=True)
    _save_byte(results["normal"], paths["normal"], "PNG", srgb=False)
    _save_byte(results["mr"], paths["mr"], "PNG", srgb=False)
    ob.data.materials.clear()
    for m in saved:
        ob.data.materials.append(m)
    bpy.data.materials.remove(mat)
    return info


# --------------------------------------------------------------------------------------
# Materials that use the baked maps
# --------------------------------------------------------------------------------------


def _load(path, colorspace):
    name = os.path.basename(path)
    im = bpy.data.images.get(name)
    if im is None or im.filepath != path:
        im = bpy.data.images.load(path, check_existing=False)
        im.name = name
    im.colorspace_settings.name = colorspace
    im.pack()
    return im


def textured_material(name, info, tint_rgb=None, glass=False, emissive=None):
    """Image-based Principled material.  tint_rgb multiplies the base colour (preview only;
    the exported material never has a tint so the glTF stays a plain metal-rough set)."""
    m = _fresh_material(name)
    nt = m.node_tree
    nb = NB(nt)
    out = _output(nt)
    bsdf = nb.node("ShaderNodePrincipledBSDF")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    uv = nb.node("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    col = nb.node("ShaderNodeTexImage", image=_load(info["paths"]["color"], "sRGB"))
    mr = nb.node("ShaderNodeTexImage", image=_load(info["paths"]["mr"], "Non-Color"))
    nrm = nb.node("ShaderNodeTexImage", image=_load(info["paths"]["normal"], "Non-Color"))
    for t in (col, mr, nrm):
        nt.links.new(uv.outputs["UV"], t.inputs["Vector"])
    if tint_rgb is not None:
        c = nb.mixc(1.0, col.outputs["Color"], tuple(tint_rgb), "MULTIPLY")
        nt.links.new(c, bsdf.inputs["Base Color"])
    else:
        nt.links.new(col.outputs["Color"], bsdf.inputs["Base Color"])
    sep = nb.node("ShaderNodeSeparateColor")
    nt.links.new(mr.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    nm = nb.node("ShaderNodeNormalMap")
    nt.links.new(nrm.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if glass:
        bsdf.inputs["Alpha"].default_value = 0.35
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
    if emissive is not None:
        bsdf.inputs["Emission Color"].default_value = (*emissive, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 6.0
    return m


def apply_material(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)
