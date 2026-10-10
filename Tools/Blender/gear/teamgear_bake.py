"""
teamgear_bake: surface zones and the PBR bake for the third-person team gear.

A piece is one mesh whose material slots are zones (cordura, webbing, loop field, team
patch, polymer, steel mesh ...).  Each zone is a procedural graph driven by object-space
position and the geometry attributes written by teamgear_geo (sd / ss / puv): weave,
stitch rows and edge binding, embroidered emblem, perforated mesh, rail slots, zipper
teeth.  One call bakes the whole piece into a texture set (Tools/Blender/CONVENTIONS.md):

    T_<Id>_<Piece>_BC.png   base colour (sRGB); tinted zones are neutral grey with
                            luminance-only wear, grime, thread and emblem shading
    T_<Id>_<Piece>_N.png    tangent-space normal, DirectX (green = -Y)
    T_<Id>_<Piece>_ORM.png  AO / roughness / metallic (linear)
    T_<Id>_<Piece>_M.png    role mask: R = Primary (colourway), G = Secondary, B = Accent (team)

Pattern periods adapt to the piece's texel size so the 1-sample emission bakes never alias.
"""

import os
import time

import bpy  # noqa: I001
import numpy as np

import bakekit as bk

# role: None (real colour) / "P" primary colourway / "S" secondary colourway / "A" team accent.
# lum: neutral grey of a tinted zone.  col: real colour (linear) of an untinted zone.
ZONES = {
    "cordura": dict(role="P", lum=0.75, rough=0.86, kind="cordura", wear=0.55, grime=0.65, var=0.30, stitch=True, bump=0.55),
    "cordura_pad": dict(role="P", lum=0.72, rough=0.88, kind="cordura", wear=0.45, grime=0.6, var=0.30, stitch=True, bump=0.5),
    "webbing": dict(role="P", lum=0.64, rough=0.80, kind="webbing", wear=0.6, grime=0.6, var=0.25, stitch=True, bump=0.6),
    "loop": dict(role="P", lum=0.58, rough=0.96, kind="loop", wear=0.3, grime=0.5, var=0.35, stitch=True, bump=0.7),
    "binding": dict(role="P", lum=0.62, rough=0.82, kind="webbing", wear=0.6, grime=0.6, var=0.25, stitch=False, bump=0.5),
    "patch": dict(role="A", lum=0.66, rough=0.80, kind="patch", wear=0.35, grime=0.35, var=0.15, stitch=False, bump=0.7),
    "armband": dict(role="A", lum=0.74, rough=0.84, kind="cordura", wear=0.4, grime=0.35, var=0.20, stitch=True, bump=0.5),
    "teamband": dict(role="A", lum=0.74, rough=0.80, kind="elastic", wear=0.35, grime=0.35, var=0.18, stitch=False, bump=0.6),
    "strap_kit": dict(role="S", lum=0.70, rough=0.82, kind="elastic", wear=0.4, grime=0.5, var=0.25, stitch=False, bump=0.6),
    "shell": dict(role="P", lum=0.75, rough=0.60, kind="grit", wear=0.85, grime=0.5, var=0.22, stitch=False, bump=0.3),
    "twill": dict(role="P", lum=0.75, rough=0.86, kind="twill", wear=0.45, grime=0.55, var=0.28, stitch=True, bump=0.5),
    "twill_brim": dict(role="P", lum=0.72, rough=0.86, kind="twill", wear=0.55, grime=0.55, var=0.28, stitch=True, rows=6, bump=0.5),
    "glass": dict(role=None, col=(0.03, 0.032, 0.036), rough=0.05, kind="satin", wear=0.0, grime=0.0, var=0.0, stitch=False, bump=0.0),
    "elastic": dict(role=None, col=(0.020, 0.020, 0.022), rough=0.84, kind="elastic", wear=0.35, grime=0.4, var=0.25, stitch=False, bump=0.6),
    "webbing_black": dict(role=None, col=(0.022, 0.022, 0.024), rough=0.80, kind="webbing", wear=0.5, grime=0.5, var=0.2, stitch=True, bump=0.6),
    "polymer": dict(role=None, col=(0.024, 0.024, 0.026), rough=0.56, kind="stipple", wear=0.6, grime=0.5, var=0.25, stitch=False, bump=0.35,
                    wear_col=(0.07, 0.07, 0.072)),
    "polymer_mag": dict(role=None, col=(0.030, 0.030, 0.032), rough=0.48, kind="stipple", wear=0.7, grime=0.6, var=0.25, stitch=False, bump=0.3,
                        wear_col=(0.08, 0.08, 0.082)),
    "tpu": dict(role=None, col=(0.020, 0.020, 0.022), rough=0.42, kind="satin", wear=0.4, grime=0.45, var=0.2, stitch=False, bump=0.2,
                wear_col=(0.05, 0.05, 0.052)),
    "rubber": dict(role=None, col=(0.016, 0.016, 0.017), rough=0.82, kind="rubber", wear=0.3, grime=0.4, var=0.2, stitch=False, bump=0.4),
    "foam": dict(role=None, col=(0.012, 0.012, 0.013), rough=0.95, kind="foam", wear=0.0, grime=0.3, var=0.15, stitch=False, bump=0.8),
    "anod": dict(role=None, col=(0.030, 0.031, 0.034), rough=0.40, metal=0.85, kind="brushed", wear=1.0, grime=0.5, var=0.2, stitch=False, bump=0.15,
                 wear_col=(0.55, 0.55, 0.57), wear_metal=1.0, wear_rough=0.25),
    "steel": dict(role=None, col=(0.30, 0.30, 0.31), rough=0.32, metal=1.0, kind="brushed", wear=0.5, grime=0.5, var=0.2, stitch=False, bump=0.1,
                  wear_col=(0.6, 0.6, 0.62), wear_metal=1.0, wear_rough=0.2),
    "rail": dict(role=None, col=(0.022, 0.022, 0.024), rough=0.5, kind="rail", wear=0.6, grime=0.6, var=0.2, stitch=False, bump=0.6,
                 wear_col=(0.07, 0.07, 0.072)),
    "mesh": dict(role=None, col=(0.028, 0.028, 0.030), rough=0.42, kind="mesh", wear=0.6, grime=0.4, var=0.2, stitch=False, bump=0.9,
                 wear_col=(0.12, 0.12, 0.125), wear_metal=0.6, wear_rough=0.3),
    "zipper": dict(role=None, col=(0.020, 0.020, 0.022), rough=0.5, kind="zipper", wear=0.5, grime=0.5, var=0.2, stitch=False, bump=0.8),
    "vent": dict(role=None, col=(0.012, 0.012, 0.013), rough=0.7, kind="vent", wear=0.0, grime=0.4, var=0.1, stitch=False, bump=0.8),
    "label": dict(role=None, col=(0.05, 0.05, 0.052), rough=0.7, kind="cordura", wear=0.2, grime=0.3, var=0.1, stitch=True, bump=0.3),
}

# design periods (metres) of the finest pattern features
PERIODS = {"weave": 0.0011, "fiber": 0.0005, "webbing": 0.0010, "loop": 0.0009, "elastic": 0.0012, "stipple": 0.0016, "twill": 0.0011,
           "stitch": 0.0032, "grit": 0.0012, "foam": 0.0012, "mesh": 0.0028}

# strength of the baked low-frequency wrinkles per pattern kind (soft goods only)
WRINKLE = {"cordura": 0.9, "webbing": 0.45, "loop": 0.5, "elastic": 0.45, "twill": 0.8, "patch": 0.25}

WAVE_K = 2 * np.pi / 20.0  # Blender wave texture: period = 2*pi / (20 * scale)


def wave_scale(period):
    return WAVE_K / period


class G:
    """Per-material graph context."""

    def __init__(self, mat, seed, tex_m):
        self.nt = mat.node_tree
        self.nb = bk.NB(self.nt)
        nb = self.nb
        geo = nb.node("ShaderNodeNewGeometry")
        self.geo = geo
        self.pos = geo.outputs["Position"]
        self.p = nb.vadd(self.pos, (seed * 3.17, seed * 1.91, seed * 2.53))
        self.tex_m = tex_m
        self.sd = self.attr("sd")
        self.ss = self.attr("ss")
        pv = nb.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name="puv")
        sep = nb.node("ShaderNodeSeparateXYZ")
        nb._in(sep.inputs[0], pv.outputs["Vector"])
        self.pu, self.pv, self.pw = sep.outputs[0], sep.outputs[1], sep.outputs[2]

    def attr(self, name):
        n = self.nb.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=name)
        return n.outputs["Fac"]

    def per(self, design):
        """Pattern period clamped to >= 3.6 texels."""
        return max(design, 3.6 * self.tex_m)

    # small math helpers
    def m(self, op, a, b=None, clamp=False):
        return self.nb.math(op, a, b, clamp)

    def mr(self, x, a, b, c=0.0, d=1.0, smooth=False):
        """Map range whose bounds may be sockets."""
        n = self.nb.node("ShaderNodeMapRange", clamp=True, interpolation_type="SMOOTHSTEP" if smooth else "LINEAR")
        for key, val in (("Value", x), ("From Min", a), ("From Max", b), ("To Min", c), ("To Max", d)):
            self.nb._in(n.inputs[key], val)
        return n.outputs["Result"]

    def mx(self, a, b):
        return self.m("MAXIMUM", a, b)

    def mn(self, a, b):
        return self.m("MINIMUM", a, b)

    def absd(self, a, b):
        return self.m("ABSOLUTE", self.nb.sub(a, b))


def _weave(g, period):
    nb = g.nb
    s = wave_scale(period)
    wx = nb.wave(g.p, s, "X")
    wy = nb.wave(g.p, s, "Y")
    wz = nb.wave(g.p, s, "Z")
    return g.mx(g.mx(wx, wy), wz)


def pattern(g, Z):
    """Returns dict(h height 0..1, dark 0..1 (holes / slots), light 0..1 (emblem), rough_add)."""
    nb = g.nb
    kind = Z["kind"]
    p = g.p
    out = dict(h=0.0, dark=0.0, light=0.0, rough_add=0.0, metal_mask=None)
    fiber_s = 1.0 / g.per(PERIODS["fiber"])
    if kind == "cordura":
        w = _weave(g, g.per(PERIODS["weave"]))
        fib = nb.noise(p, fiber_s * 0.6, 2.0, 0.5)
        slub = nb.noise(nb.vscale(p, (1.0, 1.0, 1.0)), 90.0, 3.0, 0.6)
        out["h"] = nb.add(nb.add(nb.mul(w, 0.55), nb.mul(fib, 0.3)), nb.mul(slub, 0.15))
    elif kind == "webbing":
        d = nb.wave(g.p, wave_scale(g.per(PERIODS["webbing"])), "DIAGONAL")
        w = _weave(g, g.per(PERIODS["webbing"]) * 1.3)
        fib = nb.noise(p, fiber_s * 0.5, 2.0, 0.5)
        out["h"] = nb.add(nb.add(nb.mul(d, 0.5), nb.mul(w, 0.3)), nb.mul(fib, 0.2))
    elif kind == "loop":
        per = g.per(PERIODS["loop"])
        v = nb.voronoi(p, 1.0 / per, "F1")
        fz = nb.noise(p, 1.0 / per * 0.7, 5.0, 0.75)
        out["h"] = nb.add(nb.mul(g.mr(v, 0.0, 0.7, 1.0, 0.0, True), 0.45), nb.mul(fz, 0.55))
        out["rough_add"] = 0.0
    elif kind == "elastic":
        per = g.per(PERIODS["elastic"])
        w = _weave(g, per)
        n = nb.noise(p, 1.0 / per * 0.8, 3.0, 0.6)
        out["h"] = nb.add(nb.mul(w, 0.6), nb.mul(n, 0.4))
    elif kind == "twill":
        per = g.per(PERIODS["twill"])
        d = nb.wave(g.p, wave_scale(per), "DIAGONAL")
        n = nb.noise(p, fiber_s * 0.5, 2.0, 0.5)
        out["h"] = nb.add(nb.mul(d, 0.65), nb.mul(n, 0.35))
    elif kind == "stipple":
        per = g.per(PERIODS["stipple"])
        v = nb.voronoi(p, 1.0 / per, "F1")
        out["h"] = nb.add(nb.mul(g.mr(v, 0.0, 0.6, 1.0, 0.0, True), 0.8), nb.mul(nb.noise(p, 2.5 / per, 2.0), 0.2))
    elif kind == "satin":
        out["h"] = nb.mul(nb.noise(p, 1.0 / g.per(0.002), 3.0, 0.5), 0.6)
    elif kind == "grit":
        per = g.per(PERIODS["grit"])
        v = nb.voronoi(p, 1.0 / per, "F1")
        out["h"] = nb.add(nb.mul(g.mr(v, 0.0, 0.7, 1.0, 0.0, True), 0.5), nb.mul(nb.noise(p, 0.6 / per, 3.0, 0.6), 0.5))
    elif kind == "rubber":
        out["h"] = nb.noise(p, 1.0 / g.per(0.0015), 3.0, 0.6)
    elif kind == "foam":
        per = g.per(PERIODS["foam"])
        v = nb.voronoi(p, 1.0 / per, "F1")
        out["h"] = g.mr(v, 0.0, 0.55, 0.0, 1.0, True)
    elif kind == "brushed":
        out["h"] = nb.noise(nb.vscale(p, (1.0, 0.04, 1.0)), 1.0 / g.per(0.0015), 3.0, 0.6)
    elif kind == "mesh":
        pitch = max(PERIODS["mesh"], 4.5 * g.tex_m)
        u = nb.math("DIVIDE", g.pu, pitch)
        v = nb.math("DIVIDE", g.pv, pitch)
        row = g.m("FLOOR", v)
        odd = g.m("MODULO", g.m("ABSOLUTE", row), 2.0)
        uo = nb.add(u, nb.mul(odd, 0.5))
        du = nb.sub(g.m("FRACT", uo), 0.5)
        dv = nb.sub(g.m("FRACT", v), 0.5)
        r = g.m("SQRT", nb.add(nb.mul(du, du), nb.mul(dv, dv)))
        hole = g.mr(r, 0.355, 0.30, 0.0, 1.0, True)
        out["dark"] = hole
        out["h"] = nb.sub(1.0, hole)
        out["rough_add"] = nb.mul(hole, 0.4)
    elif kind == "rail":
        s, y = g.pu, g.pv
        cell = g.m("FRACT", nb.math("DIVIDE", s, 0.016))
        along = g.mr(g.m("ABSOLUTE", nb.sub(cell, 0.5)), 0.30, 0.26, 1.0, 0.0, True)
        across = g.mr(g.m("ABSOLUTE", y), 0.0042, 0.0034, 0.0, 1.0, True)
        slot = nb.mul(nb.sub(1.0, along), across)
        st = nb.voronoi(p, 1.0 / g.per(PERIODS["stipple"]), "F1")
        out["dark"] = slot
        out["h"] = nb.sub(nb.mul(g.mr(st, 0.0, 0.6, 1.0, 0.0, True), 0.25), nb.mul(slot, 1.0))
    elif kind == "zipper":
        s, y = g.pu, g.pv
        ay = g.m("ABSOLUTE", y)
        teeth_zone = g.mr(ay, 0.0030, 0.0024, 0.0, 1.0, True)
        t = g.m("FRACT", nb.math("DIVIDE", s, max(0.0022, 3.6 * g.tex_m)))
        tooth = g.mr(g.m("ABSOLUTE", nb.sub(t, 0.5)), 0.32, 0.22, 0.0, 1.0, True)
        w = nb.wave(g.p, wave_scale(g.per(PERIODS["webbing"])), "DIAGONAL")
        out["h"] = nb.add(nb.mul(teeth_zone, nb.add(0.4, nb.mul(tooth, 0.6))), nb.mul(nb.sub(1.0, teeth_zone), nb.mul(w, 0.3)))
        out["dark"] = nb.mul(teeth_zone, nb.sub(1.0, tooth))
        out["rough_add"] = nb.mul(teeth_zone, -0.15)
    elif kind == "vent":
        s, y = g.pu, g.pv
        cell = g.m("FRACT", nb.math("DIVIDE", s, 0.0045))
        slot = nb.mul(g.mr(g.m("ABSOLUTE", nb.sub(cell, 0.5)), 0.30, 0.22, 0.0, 1.0, True), g.mr(g.m("ABSOLUTE", y), 0.0048, 0.0040, 0.0, 1.0, True))
        out["dark"] = slot
        out["h"] = nb.sub(1.0, slot)
    elif kind == "patch":
        # puv = (u, v, aspect) with v in [-1, 1], u in [-aspect, aspect]
        u, v, asp = g.pu, g.pv, g.pw
        au = g.m("ABSOLUTE", u)
        # double chevron (pointing up)
        def chevron(c):
            line = nb.sub(c, nb.mul(au, 0.95))
            band = g.mr(g.absd(v, line), 0.15, 0.115, 0.0, 1.0, True)
            return nb.mul(band, g.mr(au, 0.66, 0.60, 0.0, 1.0, True))
        emb = g.mx(chevron(0.50), chevron(-0.02))
        # inner border line
        bu = g.mr(g.absd(au, nb.sub(asp, 0.20)), 0.045, 0.028, 0.0, 1.0, True)
        bv = g.mr(g.absd(g.m("ABSOLUTE", v), 0.80), 0.045, 0.028, 0.0, 1.0, True)
        inside_u = g.mr(au, nb.sub(asp, 0.17), nb.sub(asp, 0.20), 0.0, 1.0)
        inside_v = g.mr(g.m("ABSOLUTE", v), 0.83, 0.80, 0.0, 1.0)
        border = g.mx(nb.mul(bu, inside_v), nb.mul(bv, inside_u))
        light = g.mx(emb, border)
        # satin stitches in the emblem, twill weave elsewhere, merrowed rope edge
        satin = nb.wave(g.p, wave_scale(g.per(0.0009)), "DIAGONAL")
        tw = _weave(g, g.per(PERIODS["weave"]))
        rope_zone = g.mr(g.sd, 0.0042, 0.0032, 0.0, 1.0, True)
        rope = g.m("PINGPONG", nb.math("DIVIDE", g.ss, max(0.0014, 3.6 * g.tex_m)), 0.5)
        h = nb.add(nb.mul(light, nb.add(0.55, nb.mul(satin, 0.45))), nb.mul(nb.sub(1.0, light), nb.mul(tw, 0.35)))
        h = nb.add(nb.mul(h, nb.sub(1.0, rope_zone)), nb.mul(rope_zone, nb.add(0.5, nb.mul(rope, 1.0))))
        out["h"] = h
        out["light"] = nb.add(nb.mul(light, nb.sub(1.0, rope_zone)), nb.mul(rope_zone, 0.55))
    return out


def stitches(g, Z, h):
    """Edge binding band + one stitch row; returns (h, stitch, binding)."""
    nb = g.nb
    if not Z.get("stitch"):
        return h, 0.0, 0.0
    sd, ss = g.sd, g.ss
    pitch = max(PERIODS["stitch"], 5.0 * g.tex_m)
    row = g.mr(g.absd(sd, 0.0042), 0.00065, 0.00030, 0.0, 1.0, True)
    for k in range(1, Z.get("rows", 1)):
        row = g.mx(row, g.mr(g.absd(sd, 0.0042 + 0.0058 * k), 0.00065, 0.00030, 0.0, 1.0, True))
    dash = g.mr(g.m("PINGPONG", nb.math("DIVIDE", ss, pitch), 0.5), 0.10, 0.17, 0.0, 1.0, True)
    stitch = nb.mul(row, dash)
    binding = g.mr(sd, 0.0072, 0.0064, 0.0, 1.0, True)
    crease = g.mr(g.absd(sd, 0.0068), 0.0007, 0.0, 0.0, 1.0, True)
    h = nb.add(h, nb.mul(stitch, 0.9))
    h = nb.sub(h, nb.mul(row, 0.25))
    h = nb.sub(h, nb.mul(crease, 0.7))
    return h, stitch, binding


def zone_graph(mat, zname, mask_img, seed, tex_m, edge_radius=0.0015):
    Z = ZONES[zname]
    g = G(mat, seed, tex_m)
    nb = g.nb
    geo = g.geo
    outs = {}
    # mask pass: R = edge, G = AO, B = convex edge
    bev = nb.node("ShaderNodeBevel", samples=6)
    bev.inputs["Radius"].default_value = edge_radius * 2.5
    dot = nb.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nb._in(dot.inputs[0], bev.outputs["Normal"])
    nb._in(dot.inputs[1], geo.outputs["Normal"])
    edge = nb.maprange(dot.outputs["Value"], 0.995, 0.75, 0.0, 1.0)
    ao = nb.node("ShaderNodeAmbientOcclusion", samples=12, only_local=True)
    ao.inputs["Distance"].default_value = 0.035
    convex = nb.mul(edge, nb.maprange(ao.outputs["AO"], 0.55, 0.9, 0.0, 1.0))
    outs["mask"] = nb.emit(nb.combine(edge, ao.outputs["AO"], convex))
    role = Z["role"]
    outs["role"] = nb.emit((1.0 if role == "P" else 0.0, 1.0 if role == "S" else 0.0, 1.0 if role == "A" else 0.0, 1.0))
    if mask_img is not None:
        uv = nb.node("ShaderNodeUVMap", uv_map="UVMap")
        img = nb.node("ShaderNodeTexImage", image=mask_img, interpolation="Linear")
        nb._in(img.inputs["Vector"], uv.outputs["UV"])
        _m_edge, m_ao, m_convex = nb.separate(img.outputs["Color"])
    else:
        m_ao, m_convex = 1.0, 0.0
    pt = pattern(g, Z)
    h, stitch, binding = stitches(g, Z, pt["h"])
    # soft goods: low-frequency wrinkles / padding undulation (a few cm), baked into the normal map
    wrinkle = Z.get("wrinkle", WRINKLE.get(Z["kind"], 0.0))
    macro = 0.5
    if wrinkle:
        m1 = nb.noise(g.p, 24.0, 3.0, 0.55, 0.5)
        m2 = nb.noise(g.p, 70.0, 2.0, 0.5)
        macro = nb.add(nb.mul(m1, 0.75), nb.mul(m2, 0.25))
    if Z.get("stitch"):
        # binding tape near the edge: finer webbing texture
        bw = nb.wave(g.p, wave_scale(g.per(PERIODS["webbing"])), "DIAGONAL")
        h = nb.lerp(binding, h, nb.add(nb.mul(bw, 0.5), nb.mul(stitch, 0.9)))
    p = g.p
    # wear / grime / mottling
    wn = nb.noise(p, 38.0, 4.0, 0.7)
    wear_raw = nb.sub(nb.mul(m_convex, 1.25 * Z["wear"]), nb.mul(nb.maprange(wn, 0.35, 0.65, 0.0, 1.0), 0.75))
    wear = nb.maprange(wear_raw, 0.05, 0.35, 0.0, 1.0, smooth=True)
    gn = nb.noise(p, 12.0, 2.0, 0.6)
    grime = nb.mul(nb.maprange(m_ao, 0.95, 0.35, 0.0, 1.0), nb.add(0.5, nb.mul(gn, 0.8)))
    grime = nb.mul(grime, Z["grime"], clamp=True)
    mot = nb.noise(p, 2.5, 3.0, 0.5)
    mot2 = nb.noise(p, 30.0, 2.0, 0.5)
    var = nb.mul(nb.add(nb.sub(mot, 0.5), nb.mul(nb.sub(mot2, 0.5), 0.5)), Z["var"])
    dust = nb.mul(nb.maprange(nb.noise(p, 9.0, 3.0), 0.58, 0.8, 0.0, 1.0), 0.18)
    dark = pt["dark"]
    light = pt["light"]
    if role:
        lum = Z["lum"]
        cv = nb.mul(lum, nb.add(1.0, nb.mul(var, 0.8)))
        if wrinkle:
            cv = nb.mul(cv, nb.add(0.88, nb.mul(macro, 0.24)))
        cv = nb.add(cv, nb.mul(nb.sub(h, 0.5), 0.06))  # weave shading
        if not isinstance(light, float) or light:
            cv = nb.lerp(light, cv, 0.97)
        if Z.get("stitch"):
            cv = nb.lerp(nb.mul(binding, 0.9), cv, lum * 0.9)
            cv = nb.lerp(nb.mul(stitch, 0.85), cv, min(1.0, lum * 1.12))
        cv = nb.lerp(nb.mul(wear, 0.5), cv, min(1.0, lum * 1.25))
        cv = nb.mul(cv, nb.sub(1.0, nb.mul(grime, 0.5)))
        cv = nb.lerp(dust, cv, lum * 1.1)
        col = nb.combine(cv, cv, cv)
    else:
        base = Z["col"]
        gm = nb.add(1.0, nb.mul(var, 2.0))
        col = nb.mixc(1.0, base, nb.combine(gm, gm, gm), "MULTIPLY")
        if wrinkle:
            mg = nb.add(0.88, nb.mul(macro, 0.24))
            col = nb.mixc(1.0, col, nb.combine(mg, mg, mg), "MULTIPLY")
        col = nb.mixc(nb.mul(nb.sub(h, 0.5), 0.12), col, tuple(c * 1.6 for c in base))
        if Z.get("stitch"):
            col = nb.mixc(nb.mul(stitch, 0.8), col, tuple(min(1.0, c * 2.2) for c in base))
        wc = Z.get("wear_col", tuple(min(1.0, c * 2.0 + 0.02) for c in base))
        col = nb.mixc(wear, col, wc)
        col = nb.mixc(nb.mul(grime, 0.6), col, (0.0, 0.0, 0.0))
        col = nb.mixc(dust, col, (0.12, 0.11, 0.095))
        if not isinstance(dark, float) or dark:
            col = nb.mixc(dark, col, tuple(c * 0.12 for c in base))
    outs["color"] = nb.emit(col)
    rv = nb.add(Z["rough"], nb.mul(var, 0.3))
    rv = nb.add(rv, nb.mul(nb.sub(nb.noise(p, 160.0, 3.0), 0.5), 0.10))
    if not isinstance(pt["rough_add"], float) or pt["rough_add"]:
        rv = nb.add(rv, pt["rough_add"])
    rough = nb.lerp(wear, rv, Z.get("wear_rough", max(0.2, Z["rough"] - 0.18)))
    rough = nb.lerp(nb.mul(grime, 0.7), rough, min(1.0, Z["rough"] + 0.25))
    if Z.get("stitch"):
        rough = nb.lerp(nb.mul(stitch, 0.8), rough, 0.72)
    rough = nb.math("MAXIMUM", nb.math("MINIMUM", rough, 1.0), 0.04)
    metal = nb.lerp(wear, Z.get("metal", 0.0), Z.get("wear_metal", Z.get("metal", 0.0)))
    if not isinstance(dark, float) or dark:
        metal = nb.lerp(dark, metal, 0.0)
    ao_o = nb.maprange(m_ao, 0.0, 1.0, 0.22, 1.0)
    if not isinstance(dark, float) or dark:
        ao_o = nb.mul(ao_o, nb.sub(1.0, nb.mul(dark, 0.55)))
    outs["orm"] = nb.emit(nb.combine(ao_o, rough, metal))
    # normal: bevel rounding + micro height
    bev2 = nb.node("ShaderNodeBevel", samples=5)
    bev2.inputs["Radius"].default_value = edge_radius
    base_n = bev2.outputs["Normal"]
    if wrinkle:
        bm = nb.node("ShaderNodeBump")
        bm.inputs["Strength"].default_value = wrinkle
        bm.inputs["Distance"].default_value = 0.006
        nb._in(bm.inputs["Height"], macro)
        nb._in(bm.inputs["Normal"], base_n)
        base_n = bm.outputs["Normal"]
    bump = nb.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = min(1.0, Z.get("bump", 0.5))
    bump.inputs["Distance"].default_value = max(0.00025, 0.6 * g.tex_m)
    nb._in(bump.inputs["Height"], h)
    nb._in(bump.inputs["Normal"], base_n)
    bsdf = nb.node("ShaderNodeBsdfDiffuse")
    nb._in(bsdf.inputs["Normal"], bump.outputs["Normal"])
    outs["normal"] = bsdf.outputs[0]
    outs["raw"] = (col, rough, metal, bump.outputs["Normal"])
    return outs


# --------------------------------------------------------------------------------------
# Texel size
# --------------------------------------------------------------------------------------


def texel_size(ob, res):
    me = ob.data
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    vi = np.empty(n * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", vi)
    li = np.empty(n * 3, np.int64)
    me.loop_triangles.foreach_get("loops", li)
    w = co[vi.reshape(-1, 3)]
    a3 = np.linalg.norm(np.cross(w[:, 1] - w[:, 0], w[:, 2] - w[:, 0]), axis=1).sum() * 0.5
    if not me.uv_layers:
        return 0.0003
    uv = np.empty(len(me.loops) * 2, np.float64)
    me.uv_layers.active.data.foreach_get("uv", uv)
    u = uv.reshape(-1, 2)[li.reshape(-1, 3)]
    e1, e2 = u[:, 1] - u[:, 0], u[:, 2] - u[:, 0]
    a2 = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() * 0.5
    return float(np.sqrt(a3 / max(a2 * res * res, 1e-12)))


# --------------------------------------------------------------------------------------
# Bake
# --------------------------------------------------------------------------------------


def zones_of(ob):
    return [s.material.name[2:] if s.material and s.material.name.startswith("Z_") else "polymer" for s in ob.material_slots]


def bake_piece(ob, out_dir, asset, piece, res, seed=0.0, log=print):
    """Bakes BC / N / ORM / M for a joined piece whose slots are Z_<zone> materials."""
    paths = bk.texture_paths(out_dir, asset, piece)
    os.makedirs(out_dir, exist_ok=True)
    bk.setup_bake_engine()
    zones = zones_of(ob)
    tex_m = texel_size(ob, res)
    log(f"    {asset}.{piece}: texel {tex_m * 1000:.3f} mm, zones {zones}")
    saved = list(ob.data.materials)
    mats = [bk.fresh_material(f"__tg_{asset}_{piece}_{i}") for i in range(len(zones))]
    for i, m in enumerate(mats):
        ob.data.materials[i] = m
    margin = max(4, res // 256)
    mask_res = max(512, res // 4 if res >= 4096 else res // 2)
    mask = bk._float_image(f"__tgmask_{asset}_{piece}", mask_res)
    outs = [zone_graph(m, z, None, seed, tex_m) for m, z in zip(mats, zones)]
    t0 = time.time()
    bk._bake(ob, mats, [o["mask"] for o in outs], mask, "EMIT", max(2, margin // 2))
    bk._denoise_inplace(mask)
    log(f"      mask {time.time() - t0:.0f}s")
    # role mask: baked at up to 2x and box-filtered to <= 1024 (anti-aliased tint edges)
    role_res = min(1024, res)
    rb = min(res, role_res * 2)
    role = bk._float_image(f"__tgrole_{asset}_{piece}", rb)
    bk._bake(ob, mats, [o["role"] for o in outs], role, "EMIT", max(2, margin))
    ra = bk._pixels(role)
    bpy.data.images.remove(role)
    f = rb // role_res
    if f > 1:
        ra = ra.reshape(role_res, f, role_res, f, 4).mean(axis=(1, 3))
    bk._save_proxy(ra.copy(), paths["M"], False)
    bk.save_png(ra, paths["M"], srgb=False)
    for m in mats:
        m.node_tree.nodes.clear()
        o = m.node_tree.nodes.new("ShaderNodeOutputMaterial")
        o.target = "ALL"
    outs = [zone_graph(m, z, mask, seed, tex_m) for m, z in zip(mats, zones)]
    for passname, kind, srgb in (("color", "EMIT", True), ("orm", "EMIT", False), ("normal", "NORMAL", False)):
        t0 = time.time()
        img = bk._float_image(f"__tg{passname}_{asset}_{piece}", res)
        bk._bake(ob, mats, [o[passname] for o in outs], img, kind, margin)
        a = bk._pixels(img)
        bpy.data.images.remove(img)
        if passname == "normal":
            v = a[..., :3] * 2.0 - 1.0
            v /= np.maximum(np.linalg.norm(v, axis=2, keepdims=True), 1e-6)
            a[..., :3] = v * 0.5 + 0.5
            del v
        key = {"color": "BC", "orm": "ORM", "normal": "N"}[passname]
        bk._save_proxy(a.copy(), paths[key], srgb)
        bk.save_png(a, paths[key], srgb=srgb)
        del a
        log(f"      {key} {time.time() - t0:.0f}s")
    bpy.data.images.remove(mask)
    for i, m in enumerate(saved):
        ob.data.materials[i] = m
    for m in mats:
        bpy.data.materials.remove(m)
    return paths


def lookdev_material(name, zname, seed=0.0, tex_m=0.0003, tints=None):
    """Unbaked preview material straight from a zone graph (fast look-dev renders)."""
    m = bk.fresh_material(name)
    outs = zone_graph(m, zname, None, seed, tex_m)
    nt = m.node_tree
    col, rough, metal, nrm = outs["raw"]
    nb = bk.NB(nt)
    role = ZONES[zname]["role"]
    if tints and role in tints:
        col = nb.mixc(1.0, col, tuple(tints[role]), "MULTIPLY")
    outn = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(col, b.inputs["Base Color"])
    nb._in(b.inputs["Roughness"], rough)
    nb._in(b.inputs["Metallic"], metal)
    nt.links.new(nrm, b.inputs["Normal"])
    nt.links.new(b.outputs[0], outn.inputs["Surface"])
    return m


def glass_material(name, tint=(0.03, 0.032, 0.036), rough=0.04):
    m = bk.fresh_material(name)
    nt = m.node_tree
    outn = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*tint, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["IOR"].default_value = 1.5
    b.inputs["Specular IOR Level"].default_value = 0.12
    nt.links.new(b.outputs[0], outn.inputs["Surface"])
    return m
