"""
bakekit: UV unwrapping and PBR texture baking for the Blender -> Unreal generators.

A piece is one mesh object whose material slots are "zones" (anodised receiver,
polymer furniture, steel pins, wood, team tape, ...).  Every zone has a procedural
recipe and an optional tint role (P = Primary, S = Secondary, A = Accent).  One call
bakes the whole piece into a single texture set (see Tools/Blender/CONVENTIONS.md):

    T_<Asset>_<Piece>_BC.png    base colour (sRGB).  Tinted zones are neutral grey
                                (0.75 linear) with luminance-only wear and grime.
    T_<Asset>_<Piece>_N.png     tangent-space normal, DirectX (green = -Y)
    T_<Asset>_<Piece>_ORM.png   R = AO, G = roughness, B = metallic (linear)
    T_<Asset>_<Piece>_M.png     role mask R/G/B = Primary/Secondary/Accent (<= 1024)

Passes: a half-resolution mask pass (bevel-shader curvature + AO) feeds the colour,
ORM and normal passes, which are evaluated at the target resolution with one
sample per texel (pure emission bakes, so there is no noise to denoise).
Normal detail = bevel-shader edge rounding + procedural micro height
(stipple, grain, machining marks, wood grain, weave, knurl).
"""

import hashlib
import json
import math
import os
import tempfile

import bpy  # noqa: I001
import numpy as np

BAKE_VERSION = 3
TINT_GREY = 0.75
HASH_DIR = os.path.join(tempfile.gettempdir(), "airsoft_bake_hashes")

# colour/rough/metal: clean surface.  wear_*: bare material on worn convex edges.
# micro: (kind, scale per unit, strength).  grime: cavity dirt.  var: mottling.
RECIPES = {
    "anodized": dict(color=(0.026, 0.026, 0.028), rough=0.5, metal=0.08, wear_color=(0.62, 0.62, 0.64), wear_rough=0.26, wear_metal=1.0, wear=1.0, micro=("grain", 900.0, 0.08), grime=0.55, var=0.25, scratches=0.6),
    "polymer": dict(color=(0.024, 0.024, 0.026), rough=0.62, metal=0.0, wear_color=(0.05, 0.05, 0.052), wear_rough=0.38, wear_metal=0.0, wear=0.6, micro=("stipple", 420.0, 0.22), grime=0.6, var=0.3, scratches=0.25),
    "polymer_dark": dict(color=(0.014, 0.014, 0.015), rough=0.66, metal=0.0, wear_color=(0.035, 0.035, 0.037), wear_rough=0.4, wear_metal=0.0, wear=0.5, micro=("stipple", 420.0, 0.22), grime=0.6, var=0.3, scratches=0.2),
    "grip": dict(color=(0.022, 0.022, 0.024), rough=0.7, metal=0.0, wear_color=(0.05, 0.05, 0.052), wear_rough=0.45, wear_metal=0.0, wear=0.5, micro=("stipple", 260.0, 0.6), grime=0.6, var=0.3, scratches=0.15),
    "fde": dict(color=(0.25, 0.18, 0.105), rough=0.62, metal=0.0, wear_color=(0.33, 0.25, 0.16), wear_rough=0.42, wear_metal=0.0, wear=0.6, micro=("stipple", 420.0, 0.22), grime=0.7, var=0.35, scratches=0.25),
    "od": dict(color=(0.085, 0.09, 0.05), rough=0.62, metal=0.0, wear_color=(0.13, 0.135, 0.085), wear_rough=0.42, wear_metal=0.0, wear=0.6, micro=("stipple", 420.0, 0.22), grime=0.7, var=0.35, scratches=0.25),
    "plum": dict(color=(0.11, 0.035, 0.03), rough=0.5, metal=0.0, wear_color=(0.17, 0.06, 0.05), wear_rough=0.35, wear_metal=0.0, wear=0.6, micro=("grain", 600.0, 0.1), grime=0.6, var=0.4, scratches=0.3),
    "smoke": dict(color=(0.085, 0.08, 0.068), rough=0.2, metal=0.0, wear_color=(0.12, 0.115, 0.1), wear_rough=0.32, wear_metal=0.0, wear=0.5, micro=("grain", 700.0, 0.04), grime=0.5, var=0.2, scratches=0.5),
    "parkerized": dict(color=(0.055, 0.06, 0.056), rough=0.64, metal=0.55, wear_color=(0.42, 0.42, 0.43), wear_rough=0.24, wear_metal=1.0, wear=1.2, micro=("grain", 1100.0, 0.16), grime=0.6, var=0.35, scratches=0.5),
    "gunmetal": dict(color=(0.05, 0.053, 0.058), rough=0.34, metal=0.9, wear_color=(0.5, 0.5, 0.52), wear_rough=0.2, wear_metal=1.0, wear=1.0, micro=("brushed", 500.0, 0.05), grime=0.5, var=0.25, scratches=0.6),
    "steel": dict(color=(0.3, 0.3, 0.31), rough=0.3, metal=1.0, wear_color=(0.62, 0.62, 0.63), wear_rough=0.16, wear_metal=1.0, wear=0.9, micro=("brushed", 500.0, 0.05), grime=0.5, var=0.3, scratches=0.7),
    "chrome": dict(color=(0.55, 0.56, 0.58), rough=0.15, metal=1.0, wear_color=(0.7, 0.7, 0.72), wear_rough=0.1, wear_metal=1.0, wear=0.5, micro=("brushed", 500.0, 0.03), grime=0.4, var=0.2, scratches=0.5),
    "aluminium": dict(color=(0.5, 0.5, 0.52), rough=0.35, metal=1.0, wear_color=(0.75, 0.75, 0.77), wear_rough=0.2, wear_metal=1.0, wear=0.6, micro=("knurl", 120.0, 0.5), grime=0.6, var=0.25, scratches=0.4),
    "wood": dict(color=(0.15, 0.06, 0.022), rough=0.4, metal=0.0, wear_color=(0.3, 0.15, 0.065), wear_rough=0.62, wear_metal=0.0, wear=0.8, micro=("wood", 1.0, 0.12), grime=0.5, var=0.5, scratches=0.4, grain=True),
    "wood_light": dict(color=(0.24, 0.11, 0.045), rough=0.45, metal=0.0, wear_color=(0.4, 0.22, 0.1), wear_rough=0.62, wear_metal=0.0, wear=0.8, micro=("wood", 1.0, 0.12), grime=0.5, var=0.5, scratches=0.4, grain=True),
    "tape": dict(color=(0.62, 0.62, 0.6), rough=0.82, metal=0.0, wear_color=(0.7, 0.7, 0.68), wear_rough=0.9, wear_metal=0.0, wear=0.4, micro=("weave", 260.0, 0.35), grime=0.8, var=0.5, scratches=0.0),
    "rubber": dict(color=(0.016, 0.016, 0.016), rough=0.88, metal=0.0, wear_color=(0.03, 0.03, 0.03), wear_rough=0.7, wear_metal=0.0, wear=0.3, micro=("stipple", 300.0, 0.3), grime=0.5, var=0.2, scratches=0.0),
    "glass": dict(color=(0.05, 0.11, 0.13), rough=0.04, metal=0.0, wear_color=(0.05, 0.11, 0.13), wear_rough=0.04, wear_metal=0.0, wear=0.0, micro=("none", 1.0, 0.0), grime=0.0, var=0.0, scratches=0.0),
    "reticle": dict(color=(1.0, 0.05, 0.03), rough=0.4, metal=0.0, wear_color=(1.0, 0.05, 0.03), wear_rough=0.4, wear_metal=0.0, wear=0.0, micro=("none", 1.0, 0.0), grime=0.0, var=0.0, scratches=0.0),
    "brass": dict(color=(0.55, 0.38, 0.12), rough=0.3, metal=1.0, wear_color=(0.75, 0.6, 0.3), wear_rough=0.2, wear_metal=1.0, wear=0.6, micro=("grain", 900.0, 0.03), grime=0.6, var=0.4, scratches=0.3),
    "fabric": dict(color=(0.09, 0.095, 0.06), rough=0.9, metal=0.0, wear_color=(0.13, 0.135, 0.09), wear_rough=0.95, wear_metal=0.0, wear=0.5, micro=("weave", 180.0, 0.5), grime=0.8, var=0.5, scratches=0.0),
    "emitter": dict(color=(0.02, 0.02, 0.025), rough=0.08, metal=0.0, wear_color=(0.02, 0.02, 0.025), wear_rough=0.08, wear_metal=0.0, wear=0.0, micro=("none", 1.0, 0.0), grime=0.0, var=0.05, scratches=0.0),
}

RECIPES["anod_od"] = dict(RECIPES["anodized"], color=(0.07, 0.08, 0.045))

# --------------------------------------------------------------------------------------
# Node-graph builder
# --------------------------------------------------------------------------------------


def sid(coll, identifier):
    for s in coll:
        if s.identifier == identifier:
            return s
    raise KeyError(identifier)


class NB:
    def __init__(self, nt):
        self.nt = nt

    def node(self, kind, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
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
        self._in(sid(n.inputs, "Factor_Float"), f)
        self._in(sid(n.inputs, "A_Float"), a)
        self._in(sid(n.inputs, "B_Float"), b)
        return sid(n.outputs, "Result_Float")

    def mixc(self, f, a, b, blend="MIX"):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_factor=True)
        self._in(sid(n.inputs, "Factor_Float"), f)
        self._in(sid(n.inputs, "A_Color"), a if isinstance(a, bpy.types.NodeSocket) else (*a, 1.0))
        self._in(sid(n.inputs, "B_Color"), b if isinstance(b, bpy.types.NodeSocket) else (*b, 1.0))
        return sid(n.outputs, "Result_Color")

    def vscale(self, v, s):
        n = self.node("ShaderNodeVectorMath", operation="MULTIPLY")
        self._in(n.inputs[0], v)
        self._in(n.inputs[1], s)
        return n.outputs["Vector"]

    def vadd(self, v, s):
        n = self.node("ShaderNodeVectorMath", operation="ADD")
        self._in(n.inputs[0], v)
        self._in(n.inputs[1], s)
        return n.outputs["Vector"]

    def noise(self, vec, scale, detail=3.0, rough=0.55, dist=0.0):
        n = self.node("ShaderNodeTexNoise", noise_dimensions="3D")
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

    def wave(self, vec, scale, direction="X", profile="SIN", dist=0.0, detail=0.0):
        n = self.node("ShaderNodeTexWave", wave_type="BANDS", wave_profile=profile, bands_direction=direction)
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


def fresh_material(name):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    out = m.node_tree.nodes.new("ShaderNodeOutputMaterial")
    out.target = "ALL"
    return m


# --------------------------------------------------------------------------------------
# Procedural surface graph (one per zone)
# --------------------------------------------------------------------------------------


def _wood_grain(nb, p):
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
    return f, nb.add(nb.mul(f, 0.4), nb.mul(pores, 0.6))


def _height(nb, p, r):
    kind, scale, _ = r["micro"]
    if kind == "stipple":
        d = nb.voronoi(p, scale, "F1")
        h = nb.maprange(d, 0.0, 0.6, 1.0, 0.0, smooth=True)
        return nb.add(nb.mul(h, 0.8), nb.mul(nb.noise(p, scale * 2.5, 2.0), 0.2))
    if kind == "grain":
        return nb.noise(p, scale, 4.0, 0.6)
    if kind == "brushed":
        return nb.noise(nb.vscale(p, (1.0, 0.03, 1.0)), scale, 3.0, 0.6)
    if kind == "wood":
        return _wood_grain(nb, p)[1]
    if kind == "weave":
        a = nb.wave(p, scale, "X")
        b = nb.wave(p, scale, "Y")
        c = nb.wave(p, scale, "Z")
        return nb.math("MAXIMUM", nb.math("MAXIMUM", a, b), c)
    if kind == "knurl":
        a = nb.wave(nb.vadd(nb.vscale(p, (1, 1, 1)), (0, 0, 0)), scale, "DIAGONAL", "TRI")
        sw = nb.vscale(p, (-1.0, 1.0, 1.0))
        b = nb.wave(sw, scale, "DIAGONAL", "TRI")
        return nb.math("MINIMUM", a, b)
    return 0.0


def build_zone_graph(mat, r, role, mask_img, seed, edge_radius):
    """Builds every pass for one zone; returns {pass: socket}."""
    nt = mat.node_tree
    nb = NB(nt)
    geo = nb.node("ShaderNodeNewGeometry")
    pos = nb.vadd(geo.outputs["Position"], (seed * 3.17, seed * 1.91, seed * 2.53))
    outs = {}
    tint = role is not None

    # mask pass: R = edge (convex + concave), G = AO, B = convex edge
    bev = nb.node("ShaderNodeBevel", samples=6)
    bev.inputs["Radius"].default_value = edge_radius * 2.5
    dot = nb.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nb._in(dot.inputs[0], bev.outputs["Normal"])
    nb._in(dot.inputs[1], geo.outputs["Normal"])
    edge = nb.maprange(dot.outputs["Value"], 0.995, 0.75, 0.0, 1.0)
    ao = nb.node("ShaderNodeAmbientOcclusion", samples=10, only_local=True)
    ao.inputs["Distance"].default_value = edge_radius * 12
    ao_v = ao.outputs["AO"]
    convex = nb.mul(edge, nb.maprange(ao_v, 0.55, 0.9, 0.0, 1.0))
    outs["mask"] = nb.emit(nb.combine(edge, ao_v, convex))

    # role mask
    outs["role"] = nb.emit((1.0 if role == "P" else 0.0, 1.0 if role == "S" else 0.0, 1.0 if role == "A" else 0.0, 1.0))

    # normal pass: bevel-shader rounding + micro height
    bev2 = nb.node("ShaderNodeBevel", samples=5)
    bev2.inputs["Radius"].default_value = edge_radius
    kind, _scale, strength = r["micro"]
    bsdf = nb.node("ShaderNodeBsdfDiffuse")
    if strength > 0 and kind != "none":
        bump = nb.node("ShaderNodeBump")
        bump.inputs["Strength"].default_value = min(1.0, strength)
        bump.inputs["Distance"].default_value = 0.0015
        nb._in(bump.inputs["Height"], _height(nb, pos, r))
        nb._in(bump.inputs["Normal"], bev2.outputs["Normal"])
        nb._in(bsdf.inputs["Normal"], bump.outputs["Normal"])
    else:
        nb._in(bsdf.inputs["Normal"], bev2.outputs["Normal"])
    outs["normal"] = bsdf.outputs[0]

    if mask_img is not None:
        uv = nb.node("ShaderNodeUVMap", uv_map="UVMap")
        img = nb.node("ShaderNodeTexImage", image=mask_img, interpolation="Linear")
        nb._in(img.inputs["Vector"], uv.outputs["UV"])
        m_edge, m_ao, m_convex = nb.separate(img.outputs["Color"])
    else:
        m_edge, m_ao, m_convex = 0.0, 1.0, 0.0
    p = nb.vadd(geo.outputs["Position"], (seed * 7.1, seed * 3.3, seed * 5.7))

    # curvature-driven edge wear, broken up by noise, plus sparse scratches
    wn = nb.noise(p, 38.0, 4.0, 0.7)
    wear_raw = nb.sub(nb.mul(m_convex, 1.25 * r["wear"]), nb.mul(nb.maprange(wn, 0.35, 0.65, 0.0, 1.0), 0.75))
    wear = nb.maprange(wear_raw, 0.05, 0.35, 0.0, 1.0, smooth=True)
    if r["scratches"] > 0:
        sc = nb.noise(nb.vscale(p, (1.0, 0.04, 1.0)), 60.0, 3.0, 0.7, dist=0.4)
        sc2 = nb.noise(nb.vscale(p, (0.05, 1.0, 1.0)), 45.0, 3.0, 0.7, dist=0.4)
        sline = nb.math("MAXIMUM", nb.maprange(sc, 0.71, 0.74, 0.0, 1.0), nb.maprange(sc2, 0.72, 0.745, 0.0, 1.0))
        spots = nb.maprange(nb.noise(p, 4.0, 2.0), 0.45, 0.7, 0.0, 1.0)
        wear = nb.math("MAXIMUM", wear, nb.mul(nb.mul(sline, spots), 0.55 * r["scratches"]))
    # AO cavity grime
    gn = nb.noise(p, 12.0, 2.0, 0.6)
    grime = nb.mul(nb.maprange(m_ao, 0.95, 0.35, 0.0, 1.0), nb.add(0.5, nb.mul(gn, 0.8)))
    grime = nb.mul(grime, r["grime"], clamp=True)
    mot = nb.noise(p, 2.5, 3.0, 0.5)
    mot2 = nb.noise(p, 30.0, 2.0, 0.5)
    var = nb.mul(nb.add(nb.sub(mot, 0.5), nb.mul(nb.sub(mot2, 0.5), 0.5)), r["var"])

    if tint:
        base_v = nb.add(TINT_GREY, nb.mul(var, 0.25))
        cval = nb.lerp(wear, base_v, min(1.0, TINT_GREY * 1.3))
        cval = nb.mul(cval, nb.sub(1.0, nb.mul(grime, 0.55)))
        col = nb.combine(cval, cval, cval)
    else:
        if r.get("grain"):
            gf, _ = _wood_grain(nb, geo.outputs["Position"])
            base = nb.mixc(nb.maprange(gf, 0.2, 0.9, 0.0, 1.0), r["color"], tuple(c * 0.55 for c in r["color"]))
        else:
            base = r["color"]
        g = nb.add(1.0, nb.mul(var, 2.0))
        col = nb.mixc(1.0, base, nb.combine(g, g, g), "MULTIPLY")
        col = nb.mixc(wear, col, r["wear_color"])
        col = nb.mixc(nb.mul(grime, 0.6), col, (0.0, 0.0, 0.0))
    outs["color"] = nb.emit(col)

    rv = nb.add(r["rough"], nb.mul(var, 0.35))
    rv = nb.add(rv, nb.mul(nb.sub(nb.noise(p, 160.0, 3.0), 0.5), 0.12))
    rough = nb.lerp(wear, rv, r["wear_rough"])
    rough = nb.lerp(nb.mul(grime, 0.7), rough, min(1.0, r["rough"] + 0.3))
    rough = nb.math("MAXIMUM", nb.math("MINIMUM", rough, 1.0), 0.03)
    metal = nb.lerp(wear, r["metal"], r["wear_metal"])
    ao_o = nb.maprange(m_ao, 0.0, 1.0, 0.15, 1.0)
    outs["orm"] = nb.emit(nb.combine(ao_o, rough, metal))
    return outs


# --------------------------------------------------------------------------------------
# UVs
# --------------------------------------------------------------------------------------


def deselect_all():
    bpy.context.view_layer.update()
    for o in bpy.context.scene.objects:
        if o is not None:
            o.select_set(False)


def uv_unwrap(ob, res=4096, angle=62.0, margin_px=4):
    deselect_all()
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    me = ob.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")
    margin = max(0.0015, margin_px * 1.5 / 4096.0)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=margin, shape_method="CONVEX")
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)


# --------------------------------------------------------------------------------------
# Baking
# --------------------------------------------------------------------------------------


def setup_bake_engine():
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.cycles.samples = 1
    scn.cycles.use_adaptive_sampling = False
    scn.cycles.use_denoising = False
    scn.render.bake.margin_type = "EXTEND"
    scn.render.bake.use_clear = True
    scn.render.image_settings.compression = 40


def _hash(ob, zones, extra):
    me = ob.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    uv = np.empty(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    mi = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", mi)
    h = hashlib.sha1()
    for a in (np.round(co, 5), np.round(uv, 5), mi):
        h.update(a.tobytes())
    h.update(json.dumps([zones, extra, BAKE_VERSION], sort_keys=True, default=str).encode())
    return h.hexdigest()


def _float_image(name, res):
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


def _srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def save_png(arr, path, srgb):
    """Saves an (h, w, 4) float array as an 8-bit PNG.  Modifies arr in place."""
    h, w, _ = arr.shape
    im = bpy.data.images.new("__save", w, h, alpha=False, float_buffer=False)
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    out = arr
    out[..., 3] = 1.0
    if srgb:
        out[..., :3] = _srgb(out[..., :3])
    np.clip(out, 0, 1, out=out)
    out *= 255.0
    np.round(out, out=out)
    out /= 255.0
    im.pixels.foreach_set(out.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save(filepath=path)
    bpy.data.images.remove(im)


def _bake(ob, mats, sockets, img, kind, margin):
    for mat, sock in zip(mats, sockets):
        nt = mat.node_tree
        out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        nt.links.new(sock, out.inputs["Surface"])
        tex = nt.nodes.get("__bake_target") or nt.nodes.new("ShaderNodeTexImage")
        tex.name = "__bake_target"
        tex.image = img
        for n in nt.nodes:
            n.select = False
        tex.select = True
        nt.nodes.active = tex
    deselect_all()
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    if kind == "NORMAL":
        bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", normal_r="POS_X", normal_g="NEG_Y", normal_b="POS_Z", margin=margin, use_clear=True)
    else:
        bpy.ops.object.bake(type="EMIT", margin=margin, use_clear=True)
    ob.select_set(False)


def _denoise_inplace(img, passes=2):
    """Light separable [1 2 1] blur: removes AO / bevel sampling noise from the mask."""
    a = _pixels(img).copy()
    for _ in range(passes):
        for ax in (0, 1):
            a = (np.roll(a, 1, axis=ax) + 2 * a + np.roll(a, -1, axis=ax)) * 0.25
    a[..., 3] = 1.0
    img.pixels.foreach_set(a.ravel())
    img.update()


PROXY_RES = 2048


def proxy_path(path, res=None):
    return os.path.join(HASH_DIR, "proxy", f"{res or PROXY_RES}_{os.path.basename(path)}")


def _save_proxy(a, path, srgb, res=None):
    """Preview renders use <= 2K copies of the textures (keeps memory low)."""
    res = res or PROXY_RES
    os.makedirs(os.path.join(HASH_DIR, "proxy"), exist_ok=True)
    f = max(1, a.shape[0] // res)
    if f > 1:
        h, w, c = a.shape
        p = a.reshape(h // f, f, w // f, f, c).mean(axis=(1, 3))
    else:
        p = a.copy()
    save_png(p, proxy_path(path, res), srgb)


def ensure_proxies(paths, res=None):
    res = res or PROXY_RES
    for k, path in paths.items():
        if not os.path.exists(proxy_path(path, res)) or os.path.getmtime(proxy_path(path, res)) < os.path.getmtime(path) - 120:
            im = bpy.data.images.load(path)
            im.colorspace_settings.name = "Non-Color"
            a = _pixels(im)
            bpy.data.images.remove(im)
            if k == "BC":  # stored sRGB bytes; keep them as-is (no re-encode)
                f = max(1, a.shape[0] // res)
                h, w, c = a.shape
                p = a.reshape(h // f, f, w // f, f, c).mean(axis=(1, 3)) if f > 1 else a
                save_png(p, proxy_path(path, res), srgb=False)
            else:
                _save_proxy(a, path, False, res)


def texture_paths(out_dir, asset, piece):
    base = os.path.join(out_dir, f"T_{asset}_{piece}")
    return {"BC": base + "_BC.png", "N": base + "_N.png", "ORM": base + "_ORM.png", "M": base + "_M.png"}


def bake_piece(ob, zones, res, out_dir, asset, piece, seed=0.0, edge_radius=0.006, force=False):
    """zones: list of (recipe_name, role) indexed by material slot.  Writes the four
    textures into out_dir and returns their paths."""
    paths = texture_paths(out_dir, asset, piece)
    key = _hash(ob, zones, [res, seed, edge_radius, [RECIPES[z[0]] for z in zones]])
    os.makedirs(HASH_DIR, exist_ok=True)
    hash_file = os.path.join(HASH_DIR, f"{asset}_{piece}.sha1")
    if not force and all(os.path.exists(p) for p in paths.values()) and os.path.exists(hash_file) and open(hash_file).read() == key:
        return paths, True
    os.makedirs(out_dir, exist_ok=True)
    saved = list(ob.data.materials)
    mats = []
    for i, (recipe, role) in enumerate(zones):
        m = fresh_material(f"__bake_{asset}_{piece}_{i}")
        mats.append(m)
    for i, m in enumerate(mats):  # replace slots in place (clear() would reset material indices)
        if i < len(ob.data.materials):
            ob.data.materials[i] = m
        else:
            ob.data.materials.append(m)
    margin = max(4, res // 256)
    mask_res = max(512, res // 4 if res >= 4096 else res // 2)
    mask = _float_image(f"__mask_{asset}_{piece}", mask_res)
    outs = [build_zone_graph(m, RECIPES[z[0]], z[1], None, seed, edge_radius) for m, z in zip(mats, zones)]
    _bake(ob, mats, [o["mask"] for o in outs], mask, "EMIT", max(2, margin // 2))
    _denoise_inplace(mask)
    role_res = min(1024, res)
    role = _float_image(f"__role_{asset}_{piece}", role_res)
    _bake(ob, mats, [o["role"] for o in outs], role, "EMIT", max(2, margin // 2))
    ra = _pixels(role)
    _save_proxy(ra, paths["M"], False)
    save_png(ra, paths["M"], srgb=False)
    bpy.data.images.remove(role)
    for m in mats:
        m.node_tree.nodes.clear()
        out = m.node_tree.nodes.new("ShaderNodeOutputMaterial")
        out.target = "ALL"
    outs = [build_zone_graph(m, RECIPES[z[0]], z[1], mask, seed, edge_radius) for m, z in zip(mats, zones)]
    for passname, kind, srgb in (("color", "EMIT", True), ("orm", "EMIT", False), ("normal", "NORMAL", False)):
        img = _float_image(f"__{passname}_{asset}_{piece}", res)
        _bake(ob, mats, [o[passname] for o in outs], img, kind, margin)
        a = _pixels(img)
        bpy.data.images.remove(img)
        if passname == "normal":
            v = a[..., :3] * 2.0 - 1.0
            v /= np.maximum(np.linalg.norm(v, axis=2, keepdims=True), 1e-6)
            a[..., :3] = v * 0.5 + 0.5
            del v
        key = {"color": "BC", "orm": "ORM", "normal": "N"}[passname]
        _save_proxy(a, paths[key], srgb)
        save_png(a, paths[key], srgb=srgb)
        del a
    bpy.data.images.remove(mask)
    for i, m in enumerate(saved):
        ob.data.materials[i] = m
    for m in mats:
        bpy.data.materials.remove(m)
    with open(hash_file, "w") as f:
        f.write(key)
    return paths, False


# --------------------------------------------------------------------------------------
# Materials using the baked maps
# --------------------------------------------------------------------------------------


def _load(path, colorspace):
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = colorspace
    return im


def plain_material(name, rgb=(0.5, 0.5, 0.5), rough=0.5, metal=0.0, alpha=1.0, emission=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        b.inputs["Transmission Weight"].default_value = 0.0
    if emission:
        b.inputs["Emission Color"].default_value = (*emission, 1.0)
        b.inputs["Emission Strength"].default_value = 8.0
    return m


def preview_material(name, paths, tints=None, proxy_res=None):
    """Material for Blender preview renders: BC * role-mask tints, ORM, DirectX normal."""
    m = fresh_material(name)
    nt = m.node_tree
    nb = NB(nt)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    bsdf = nb.node("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    uv = nb.node("ShaderNodeUVMap", uv_map="UVMap")
    imgs = {}
    ensure_proxies(paths, proxy_res)
    for k, cs in (("BC", "sRGB"), ("ORM", "Non-Color"), ("N", "Non-Color"), ("M", "Non-Color")):
        t = nb.node("ShaderNodeTexImage", image=_load(proxy_path(paths[k], proxy_res), cs))
        nt.links.new(uv.outputs["UV"], t.inputs["Vector"])
        imgs[k] = t
    col = imgs["BC"].outputs["Color"]
    if tints:
        mr, mg, mb = nb.separate(imgs["M"].outputs["Color"])
        for msk, key in ((mr, "P"), (mg, "S"), (mb, "A")):
            if key in tints:
                tinted = nb.mixc(1.0, col, tuple(tints[key]), "MULTIPLY")
                col = nb.mixc(msk, col, tinted)
    nt.links.new(col, bsdf.inputs["Base Color"])
    ao, rough, metal = nb.separate(imgs["ORM"].outputs["Color"])
    nt.links.new(rough, bsdf.inputs["Roughness"])
    nt.links.new(metal, bsdf.inputs["Metallic"])
    nx, ny, nz = nb.separate(imgs["N"].outputs["Color"])
    flipped = nb.combine(nx, nb.sub(1.0, ny), nz)  # DirectX -> OpenGL for Blender
    nm = nb.node("ShaderNodeNormalMap")
    nt.links.new(flipped, nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return m
