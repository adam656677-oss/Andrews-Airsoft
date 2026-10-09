"""propkit_mats: procedural material recipes used for baking unique prop texture sets.

Each recipe returns colour / roughness / metallic / height / mask sockets. The material gets
three outputs (OUT_BC, OUT_ORM, OUT_N) that the baker switches between:
  OUT_BC  = emission(base colour)
  OUT_ORM = emission(mask, roughness, metallic)   (AO is baked separately)
  OUT_N   = principled with the bump normal        (tangent-space normal bake)
Recipes may read the per-piece AUX image (R = convex edges, G = ambient occlusion) through
the bake UVs, `Random Per Island`, face attribute `gax` (grain axis 0/1/2 = X/Y/Z) and
point attribute `luv` (decal/label coordinates u, v, id).
All colours are linear.
"""

import bpy
import math

# --------------------------------------------------------------------------------------
# Node builder
# --------------------------------------------------------------------------------------


class NB:
    def __init__(self, nt):
        self.nt = nt

    def n(self, t, **kw):
        node = self.nt.nodes.new(t)
        for k, v in kw.items():
            setattr(node, k, v)
        return node

    def s(self, x, sock):
        if isinstance(x, bpy.types.NodeSocket):
            self.nt.links.new(x, sock)
        elif isinstance(x, (tuple, list)):
            dv = sock.default_value
            n = len(dv)
            vals = list(x) + [1.0] * (n - len(x))
            sock.default_value = vals[:n]
        else:
            try:
                sock.default_value = x
            except TypeError:
                sock.default_value = (x,) * len(sock.default_value)

    def math(self, op, a, b=0.0, c=0.0, clamp=False):
        nd = self.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.s(a, nd.inputs[0])
        self.s(b, nd.inputs[1])
        self.s(c, nd.inputs[2])
        return nd.outputs[0]

    def add(self, a, b):
        return self.math("ADD", a, b)

    def sub(self, a, b):
        return self.math("SUBTRACT", a, b)

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def div(self, a, b):
        return self.math("DIVIDE", a, b)

    def pw(self, a, b):
        return self.math("POWER", a, b)

    def mn(self, a, b):
        return self.math("MINIMUM", a, b)

    def mx(self, a, b):
        return self.math("MAXIMUM", a, b)

    def clamp(self, a):
        return self.math("ADD", a, 0.0, clamp=True)

    def inv(self, a):
        return self.math("SUBTRACT", 1.0, a)

    def maprange(self, x, a, b, c=0.0, d=1.0, clamp=True, smooth=False):
        nd = self.n("ShaderNodeMapRange", clamp=clamp, interpolation_type="SMOOTHSTEP" if smooth else "LINEAR")
        for i, v in enumerate((x, a, b, c, d)):
            self.s(v, nd.inputs[i])
        return nd.outputs[0]

    def ss(self, a, b, x):
        return self.maprange(x, a, b, 0.0, 1.0, smooth=True)

    def mix(self, f, a, b):
        nd = self.n("ShaderNodeMix", data_type="FLOAT", clamp_factor=True)
        self.s(f, nd.inputs[0])
        self.s(a, nd.inputs[2])
        self.s(b, nd.inputs[3])
        return nd.outputs[0]

    def mixc(self, f, a, b):
        nd = self.n("ShaderNodeMix", data_type="RGBA", clamp_factor=True)
        self.s(f, nd.inputs[0])
        self.s(a, nd.inputs[6])
        self.s(b, nd.inputs[7])
        return nd.outputs[2]

    def mixc_op(self, blend, f, a, b):
        nd = self.n("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_factor=True)
        self.s(f, nd.inputs[0])
        self.s(a, nd.inputs[6])
        self.s(b, nd.inputs[7])
        return nd.outputs[2]

    def cmul(self, col, f):
        """colour * scalar (f may be a socket)."""
        if isinstance(f, bpy.types.NodeSocket):
            return self.mixc_op("MULTIPLY", 1.0, col, self.combine(f, f, f))
        return self.mixc_op("MULTIPLY", 1.0, col, (f, f, f, 1))

    def vmath(self, op, a, b=(0, 0, 0)):
        nd = self.n("ShaderNodeVectorMath", operation=op)
        self.s(a, nd.inputs[0])
        self.s(b, nd.inputs[1])
        return nd.outputs[1] if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else nd.outputs[0]

    def vscale(self, a, f):
        nd = self.n("ShaderNodeVectorMath", operation="SCALE")
        self.s(a, nd.inputs[0])
        self.s(f, nd.inputs[3])
        return nd.outputs[0]

    def combine(self, x, y, z):
        nd = self.n("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self.s(v, nd.inputs[i])
        return nd.outputs[0]

    def sep(self, v):
        nd = self.n("ShaderNodeSeparateXYZ")
        self.s(v, nd.inputs[0])
        return nd.outputs[0], nd.outputs[1], nd.outputs[2]

    def noise(self, v, scale=1.0, detail=2.0, rough=0.5, dist=0.0, lac=2.0, dims="3D", w=None):
        nd = self.n("ShaderNodeTexNoise", noise_dimensions=dims)
        if v is not None:
            self.s(v, nd.inputs["Vector"])
        if w is not None:
            self.s(w, nd.inputs["W"])
        self.s(scale, nd.inputs["Scale"])
        self.s(detail, nd.inputs["Detail"])
        self.s(rough, nd.inputs["Roughness"])
        self.s(lac, nd.inputs["Lacunarity"])
        self.s(dist, nd.inputs["Distortion"])
        return nd.outputs[0], nd.outputs[1]

    def vor(self, v, scale=1.0, feature="F1", rand=1.0, dims="3D", metric="EUCLIDEAN", smooth=0.0):
        nd = self.n("ShaderNodeTexVoronoi", feature=feature, voronoi_dimensions=dims, distance=metric)
        if v is not None:
            self.s(v, nd.inputs["Vector"])
        self.s(scale, nd.inputs["Scale"])
        self.s(rand, nd.inputs["Randomness"])
        if feature == "SMOOTH_F1":
            self.s(smooth, nd.inputs["Smoothness"])
        return nd.outputs[0], nd.outputs[1], nd.outputs[2]

    def wave(self, v, scale=1.0, dist=0.0, detail=2.0, typ="BANDS", axis="X", prof="SIN", dscale=1.0):
        nd = self.n("ShaderNodeTexWave", wave_type=typ, wave_profile=prof)
        if typ == "BANDS":
            nd.bands_direction = axis
        else:
            nd.rings_direction = axis
        self.s(v, nd.inputs["Vector"])
        self.s(scale, nd.inputs["Scale"])
        self.s(dist, nd.inputs["Distortion"])
        self.s(detail, nd.inputs["Detail"])
        self.s(dscale, nd.inputs["Detail Scale"])
        return nd.outputs[1]

    def ramp(self, f, stops, interp="LINEAR"):
        nd = self.n("ShaderNodeValToRGB")
        cr = nd.color_ramp
        cr.interpolation = interp
        while len(cr.elements) > 1:
            cr.elements.remove(cr.elements[-1])
        cr.elements[0].position = stops[0][0]
        cr.elements[0].color = (*stops[0][1][:3], 1)
        for p, c in stops[1:]:
            e = cr.elements.new(p)
            e.color = (*c[:3], 1)
        self.s(f, nd.inputs[0])
        return nd.outputs[0]

    def attr(self, name, out="Factor"):
        nd = self.n("ShaderNodeAttribute", attribute_name=name)
        return nd.outputs[out]

    def img(self, image, vec, ext="CLIP", interp="Linear"):
        nd = self.n("ShaderNodeTexImage", extension=ext, interpolation=interp)
        nd.image = image
        if vec is not None:
            self.s(vec, nd.inputs[0])
        return nd.outputs[0], nd.outputs[1]

    def bump(self, h, strength=1.0, dist=0.001, normal=None):
        nd = self.n("ShaderNodeBump")
        self.s(h, nd.inputs["Height"])
        self.s(strength, nd.inputs["Strength"])
        self.s(dist, nd.inputs["Distance"])
        if normal is not None:
            self.s(normal, nd.inputs["Normal"])
        return nd.outputs[0]

    def lum(self, col):
        nd = self.n("ShaderNodeRGBToBW")
        self.s(col, nd.inputs[0])
        return nd.outputs[0]


# --------------------------------------------------------------------------------------
# Context available to every recipe
# --------------------------------------------------------------------------------------


class Ctx:
    def __init__(self, nb):
        self.nb = nb
        tc = nb.n("ShaderNodeTexCoord")
        self.P = tc.outputs["Object"]
        self.Nobj = tc.outputs["Normal"]
        geo = nb.n("ShaderNodeNewGeometry")
        self.rnd = geo.outputs["Random Per Island"]
        uvn = nb.n("ShaderNodeUVMap", uv_map="UVMap")
        aux_img = bpy.data.images.get("AUX")
        if aux_img is None:
            aux_img = bpy.data.images.new("AUX", 4, 4, float_buffer=True)
            aux_img.colorspace_settings.name = "Non-Color"
            aux_img.generated_color = (0, 1, 0, 1)
        col, _ = nb.img(aux_img, uvn.outputs[0], ext="EXTEND")
        r, g, b = nb.sep(col)
        self.edge = r
        self.ao = g
        self.cav = nb.inv(g)
        self._gp = None
        self._luv = None

    @property
    def gP(self):
        """Position swizzled so that the grain / brushing direction is local X."""
        if self._gp is None:
            nb = self.nb
            x, y, z = nb.sep(self.P)
            g = nb.attr("gax")
            a = nb.math("LESS_THAN", g, 0.5)
            c = nb.math("GREATER_THAN", g, 1.5)
            b = nb.sub(nb.sub(1.0, a), c)

            def pick(p, q, r):
                return nb.add(nb.add(nb.mul(p, a), nb.mul(q, b)), nb.mul(r, c))

            self._gp = nb.combine(pick(x, y, z), pick(y, z, x), pick(z, x, y))
        return self._gp

    @property
    def luv(self):
        if self._luv is None:
            self._luv = self.nb.attr("luv", "Vector")
        return self._luv


# --------------------------------------------------------------------------------------
# Recipes
# --------------------------------------------------------------------------------------


def _out(col, rough, metal=0.0, h=None, bs=0.3, bd=0.001, mask=0.0):
    return dict(col=col, rough=rough, metal=metal, h=h, bs=bs, bd=bd, mask=mask)


def wood(nb, c, dark, light, rough=0.32, ring=38.0, pore=1.0, lacquer=True, figure=0.5, worn=0.25):
    q = nb.vmath("ADD", c.gP, nb.vscale(nb.combine(c.rnd, nb.mul(c.rnd, 3.7), nb.mul(c.rnd, 1.3)), 11.0))
    qx, qy, qz = nb.sep(q)
    warp, _ = nb.noise(nb.vmath("MULTIPLY", q, (0.35, 3.0, 3.0)), 1.0, 3.0, 0.55)
    rr = nb.math("SQRT", nb.add(nb.mul(nb.add(qy, 0.37), nb.add(qy, 0.37)), nb.mul(nb.add(qz, 0.81), nb.add(qz, 0.81))))
    rings = nb.math("FRACT", nb.add(nb.mul(rr, ring), nb.mul(warp, 4.0)))
    late = nb.ss(0.55, 0.95, rings)
    fig, _ = nb.noise(nb.vmath("MULTIPLY", q, (1.2, 22.0, 22.0)), 1.0, 5.0, 0.6)
    t = nb.clamp(nb.add(nb.mul(late, 0.75), nb.mul(nb.sub(fig, 0.5), figure)))
    col = nb.ramp(t, [(0.0, light), (0.55, tuple(0.5 * (a + b) for a, b in zip(light, dark))), (1.0, dark)])
    pores, _ = nb.noise(nb.vmath("MULTIPLY", q, (6.0, 420.0, 420.0)), 1.0, 2.0, 0.5)
    pm = nb.mul(nb.ss(0.58, 0.75, pores), pore)
    col = nb.cmul(col, nb.sub(1.0, nb.mul(pm, 0.45)))
    blot, _ = nb.noise(c.P, 3.0, 3.0, 0.5)
    col = nb.cmul(col, nb.add(0.85, nb.mul(blot, 0.3)))
    col = nb.cmul(col, nb.mix(nb.mul(c.cav, 1.4), 1.0, 0.55))
    col = nb.mixc(nb.mul(c.edge, worn), col, nb.cmul(col, 1.55))
    scr, _ = nb.noise(nb.vmath("MULTIPLY", c.P, (60.0, 3.0, 60.0)), 1.0, 2.0, 0.5)
    r = nb.add(rough, nb.add(nb.mul(pm, 0.18), nb.mul(nb.ss(0.6, 0.8, scr), 0.08)))
    r = nb.add(r, nb.mul(c.cav, 0.15))
    if not lacquer:
        r = nb.add(r, 0.25)
    h = nb.add(nb.mul(pm, -1.0), nb.mul(late, 0.15))
    return _out(col, r, 0.0, h, 0.35, 0.0006)


def brass(nb, c, polish=0.22, tarnish=0.55, base=(0.80, 0.58, 0.27), brushed=1.0):
    br, _ = nb.noise(nb.vmath("MULTIPLY", c.gP, (3.0, 900.0, 900.0)), 1.0, 2.0, 0.6)
    big, _ = nb.noise(c.P, 4.0, 4.0, 0.6)
    tm = nb.clamp(nb.add(nb.mul(c.cav, 1.6 * tarnish), nb.mul(nb.ss(0.5, 0.75, big), 0.5 * tarnish)))
    tm = nb.mul(tm, nb.sub(1.0, nb.mul(c.edge, 0.8)))
    dull = tuple(x * 0.55 for x in base)
    col = nb.mixc(tm, base, dull)
    patina = nb.ss(0.55, 0.9, nb.mul(c.cav, 1.3))
    col = nb.mixc(nb.mul(patina, tarnish * 0.6), col, (0.10, 0.11, 0.06))
    col = nb.mixc(nb.mul(c.edge, 0.6), col, tuple(min(1, x * 1.12) for x in base))
    col = nb.cmul(col, nb.add(0.93, nb.mul(br, 0.14 * brushed)))
    r = nb.add(polish, nb.add(nb.mul(br, 0.10 * brushed), nb.mul(tm, 0.28)))
    r = nb.sub(r, nb.mul(c.edge, 0.1))
    metal = nb.sub(1.0, nb.mul(patina, tarnish * 0.5))
    fine, _ = nb.noise(c.P, 900.0, 2.0, 0.5)
    h = nb.add(nb.mul(br, brushed), nb.mul(fine, 0.2))
    return _out(col, r, metal, h, 0.15, 0.0003)


def marble(nb, c, base=(0.010, 0.010, 0.011), vein=(0.62, 0.60, 0.56), rough=0.06, scale=1.0, base2=None):
    p = nb.vscale(c.P, scale)
    n1, _ = nb.noise(p, 0.7, 7.0, 0.58, dist=0.9)
    v1 = nb.pw(nb.clamp(nb.sub(1.0, nb.mul(nb.math("ABSOLUTE", nb.sub(n1, 0.5)), 38.0))), 2.0)
    zone, _ = nb.noise(p, 0.45, 2.0, 0.5)
    v1 = nb.mul(v1, nb.ss(0.42, 0.6, zone))
    n2, _ = nb.noise(p, 1.8, 7.0, 0.6, dist=1.4)
    v2 = nb.pw(nb.clamp(nb.sub(1.0, nb.mul(nb.math("ABSOLUTE", nb.sub(n2, 0.5)), 70.0))), 2.0)
    v2 = nb.mul(v2, nb.ss(0.5, 0.7, zone))
    n3, _ = nb.noise(p, 6.0, 6.0, 0.6, dist=1.0)
    v3 = nb.pw(nb.clamp(nb.sub(1.0, nb.mul(nb.math("ABSOLUTE", nb.sub(n3, 0.5)), 90.0))), 2.0)
    cloud, _ = nb.noise(p, 3.0, 6.0, 0.7)
    b2 = base2 or tuple(x * 2.5 for x in base)
    col = nb.mixc(nb.ss(0.35, 0.8, cloud), base, b2)
    v = nb.clamp(nb.add(nb.add(v1, nb.mul(v2, 0.6)), nb.mul(v3, 0.18)))
    col = nb.mixc(v, col, vein)
    sc, _ = nb.noise(nb.vmath("MULTIPLY", c.P, (80.0, 2.0, 80.0)), 1.0, 1.0, 0.5)
    r = nb.add(rough, nb.add(nb.mul(v, 0.05), nb.mul(nb.ss(0.62, 0.7, sc), 0.05)))
    r = nb.add(r, nb.mul(c.cav, 0.1))
    return _out(col, r, 0.0, nb.mul(v, -0.3), 0.1, 0.0003)


def leather(nb, c, col=(0.10, 0.02, 0.012), rough=0.42, crease=1.0, worn=0.6):
    g, _, _ = nb.vor(c.P, 380.0, "F1", 1.0)
    g2, _, _ = nb.vor(c.P, 150.0, "DISTANCE_TO_EDGE", 1.0)
    cr, _ = nb.noise(nb.vmath("MULTIPLY", c.P, (1.0, 1.0, 2.5)), 22.0, 8.0, 0.65, dist=0.4)
    crl = nb.pw(nb.clamp(nb.sub(1.0, nb.mul(nb.math("ABSOLUTE", nb.sub(cr, 0.5)), 9.0))), 3.0)
    crl = nb.mul(crl, crease)
    mot, _ = nb.noise(c.P, 5.0, 4.0, 0.6)
    col_s = nb.cmul(col, nb.add(0.75, nb.mul(mot, 0.5)))
    col_s = nb.cmul(col_s, nb.sub(1.0, nb.mul(crl, 0.45)))
    col_s = nb.cmul(col_s, nb.mix(nb.mul(c.cav, 1.5), 1.0, 0.45))
    worn_c = tuple(min(1, x * 2.4 + 0.02) for x in col)
    col_s = nb.mixc(nb.mul(c.edge, worn), col_s, worn_c)
    r = nb.add(rough, nb.add(nb.mul(mot, 0.12), nb.mul(crl, 0.12)))
    r = nb.sub(r, nb.mul(c.edge, 0.15))
    h = nb.add(nb.add(nb.mul(g, 0.5), nb.mul(nb.ss(0.0, 0.08, g2), 0.3)), nb.mul(crl, -1.2))
    return _out(col_s, r, 0.0, h, 0.35, 0.0006)


def velvet(nb, c, col=(0.16, 0.012, 0.025), rough=0.82):
    cr, _ = nb.noise(c.P, 9.0, 6.0, 0.65, dist=0.6)
    pile, _ = nb.noise(c.P, 1400.0, 1.0, 0.5)
    col_s = nb.cmul(col, nb.add(0.65, nb.mul(cr, 0.75)))
    col_s = nb.cmul(col_s, nb.mix(nb.mul(c.cav, 1.3), 1.0, 0.45))
    sheen = tuple(min(1, x * 1.9 + 0.01) for x in col)
    col_s = nb.mixc(nb.mul(c.edge, 0.55), col_s, sheen)
    r = nb.add(rough, nb.mul(cr, 0.1))
    h = nb.add(nb.mul(pile, 0.4), nb.mul(cr, 0.6))
    return _out(col_s, r, 0.0, h, 0.2, 0.0006)


def metal(nb, c, col=(0.6, 0.6, 0.62), rough=0.08, brushed=0.0, dirt=0.3):
    br, _ = nb.noise(nb.vmath("MULTIPLY", c.gP, (3.0, 700.0, 700.0)), 1.0, 2.0, 0.6)
    sm, _ = nb.noise(c.P, 6.0, 4.0, 0.6)
    col_s = nb.cmul(col, nb.add(0.92, nb.mul(br, 0.16 * brushed)))
    col_s = nb.cmul(col_s, nb.mix(nb.mul(c.cav, dirt * 2), 1.0, 0.5))
    r = nb.add(rough, nb.add(nb.mul(br, 0.12 * brushed), nb.mul(nb.ss(0.5, 0.8, sm), 0.05)))
    r = nb.add(r, nb.mul(c.cav, dirt * 0.4))
    return _out(col_s, r, 1.0, nb.mul(br, brushed), 0.1, 0.0003)


def paint(nb, c, col=(0.75, 0.75, 0.75), rough=0.2, mask=0.0, peel=0.5, chip=0.0, chip_col=(0.08, 0.075, 0.07), grime=0.4, rust=0.0, streak=0.0, metal_v=0.0):
    op, _ = nb.noise(c.P, 260.0, 2.0, 0.5)
    sm, _ = nb.noise(c.P, 5.0, 5.0, 0.6)
    col_s = nb.cmul(col, nb.add(0.97, nb.mul(sm, 0.06)))
    g = nb.clamp(nb.add(nb.mul(c.cav, 1.5), nb.mul(nb.ss(0.55, 0.85, sm), 0.3)))
    if streak:
        x, y, z = nb.sep(c.P)
        st, _ = nb.noise(nb.vmath("MULTIPLY", c.P, (25.0, 25.0, 0.6)), 1.0, 4.0, 0.6)
        g = nb.clamp(nb.add(g, nb.mul(nb.ss(0.5, 0.75, st), streak)))
    col_s = nb.cmul(col_s, nb.sub(1.0, nb.mul(g, grime)))
    if rust:
        rn, _ = nb.noise(c.P, 14.0, 6.0, 0.7)
        rm = nb.clamp(nb.mul(nb.add(c.cav, nb.mul(nb.ss(0.6, 0.8, rn), 0.6)), rust))
        col_s = nb.mixc(nb.ss(0.35, 0.7, rm), col_s, (0.13, 0.05, 0.02))
    r = nb.add(rough, nb.add(nb.mul(op, 0.04), nb.mul(g, 0.35 * grime)))
    m = metal_v
    if chip:
        ch, _ = nb.noise(c.P, 30.0, 6.0, 0.7)
        cm = nb.ss(0.55, 0.62, nb.add(nb.mul(c.edge, 0.9 * chip), nb.mul(ch, 0.6)))
        col_s = nb.mixc(cm, col_s, chip_col)
        r = nb.mix(cm, r, 0.45)
        m = nb.mix(cm, metal_v, 0.8)
    h = nb.mul(op, peel)
    return _out(col_s, r, m, h, 0.08, 0.0004, mask)


def plastic(nb, c, col=(0.02, 0.02, 0.02), rough=0.5, grain=600.0, gstr=0.6, dirt=0.4):
    g, _, _ = nb.vor(c.P, grain, "F1", 1.0)
    sm, _ = nb.noise(c.P, 6.0, 4.0, 0.6)
    col_s = nb.cmul(col, nb.add(0.9, nb.mul(sm, 0.2)))
    col_s = nb.mixc(nb.mul(c.edge, 0.5), col_s, tuple(min(1, x * 2.0 + 0.02) for x in col))
    col_s = nb.cmul(col_s, nb.mix(nb.mul(c.cav, dirt * 2), 1.0, 0.6))
    r = nb.add(rough, nb.sub(nb.mul(sm, 0.08), nb.mul(c.edge, 0.15)))
    return _out(col_s, r, 0.0, nb.mul(g, gstr), 0.25, 0.0004)


def rubber(nb, c, col=(0.022, 0.022, 0.022), rough=0.85):
    n, _ = nb.noise(c.P, 300.0, 3.0, 0.6)
    sm, _ = nb.noise(c.P, 8.0, 4.0, 0.6)
    col_s = nb.cmul(col, nb.add(0.8, nb.mul(sm, 0.4)))
    col_s = nb.mixc(nb.mul(c.edge, 0.4), col_s, (0.06, 0.058, 0.055))
    return _out(col_s, nb.add(rough, nb.mul(sm, 0.1)), 0.0, n, 0.3, 0.0004)


def concrete(nb, c, col=(0.33, 0.32, 0.30), rough=0.85):
    pores, _, _ = nb.vor(c.P, 90.0, "F1", 1.0)
    pm = nb.ss(0.0, 0.12, pores)
    sm, _ = nb.noise(c.P, 3.0, 6.0, 0.65)
    st, _ = nb.noise(nb.vmath("MULTIPLY", c.P, (8.0, 8.0, 0.8)), 1.0, 5.0, 0.6)
    col_s = nb.cmul(col, nb.add(0.75, nb.mul(sm, 0.5)))
    col_s = nb.cmul(col_s, nb.sub(1.0, nb.mul(nb.ss(0.55, 0.8, st), 0.35)))
    col_s = nb.cmul(col_s, nb.add(0.7, nb.mul(pm, 0.3)))
    col_s = nb.cmul(col_s, nb.mix(nb.mul(c.cav, 1.5), 1.0, 0.5))
    col_s = nb.mixc(nb.mul(c.edge, 0.4), col_s, tuple(min(1, x * 1.3) for x in col))
    fine, _ = nb.noise(c.P, 500.0, 3.0, 0.6)
    h = nb.add(nb.mul(pm, 1.0), nb.mul(fine, 0.3))
    return _out(col_s, nb.add(rough, nb.mul(sm, 0.1)), 0.0, h, 0.4, 0.0008)


def leaves(nb, c):
    pal = nb.ramp(c.rnd, [(0.0, (0.020, 0.055, 0.012)), (0.35, (0.035, 0.085, 0.018)), (0.7, (0.055, 0.11, 0.022)), (1.0, (0.09, 0.13, 0.03))])
    n, _ = nb.noise(c.P, 40.0, 3.0, 0.5)
    col = nb.cmul(pal, nb.add(0.75, nb.mul(n, 0.5)))
    col = nb.cmul(col, nb.mix(nb.mul(c.cav, 1.6), 1.0, 0.25))
    vein, _ = nb.noise(c.P, 600.0, 2.0, 0.5)
    return _out(col, nb.add(0.45, nb.mul(n, 0.15)), 0.0, vein, 0.2, 0.0003)


def soil(nb, c):
    v, _, _ = nb.vor(c.P, 160.0, "F1", 1.0)
    n, _ = nb.noise(c.P, 30.0, 6.0, 0.7)
    col = nb.mixc(nb.ss(0.3, 0.7, n), (0.025, 0.018, 0.012), (0.06, 0.045, 0.03))
    bark = nb.ss(0.6, 0.7, n)
    col = nb.mixc(nb.mul(bark, 0.6), col, (0.12, 0.07, 0.035))
    return _out(col, 0.92, 0.0, nb.add(v, n), 0.6, 0.002)


def fabric(nb, c, col=(0.5, 0.43, 0.33), rough=0.88, weave=900.0):
    x, y, z = nb.sep(c.P)
    w1 = nb.math("SINE", nb.mul(nb.add(x, y), weave))
    w2 = nb.math("SINE", nb.mul(z, weave))
    wv = nb.mul(nb.add(w1, w2), 0.5)
    sl, _ = nb.noise(c.P, 30.0, 4.0, 0.6)
    col_s = nb.cmul(col, nb.add(0.85, nb.mul(sl, 0.3)))
    col_s = nb.cmul(col_s, nb.add(0.92, nb.mul(wv, 0.08)))
    col_s = nb.cmul(col_s, nb.mix(nb.mul(c.cav, 1.5), 1.0, 0.5))
    return _out(col_s, rough, 0.0, wv, 0.25, 0.0003)


def glass(nb, c, col=(0.9, 0.92, 0.92), rough=0.03, dirt=0.15):
    sm, _ = nb.noise(c.P, 6.0, 4.0, 0.6)
    r = nb.add(rough, nb.mul(nb.ss(0.55, 0.8, sm), dirt))
    return _out(col, r, 0.0, None)


def glass_bottles(nb, c):
    col = nb.ramp(c.rnd, [(0.0, (0.80, 0.42, 0.10)), (0.18, (0.30, 0.55, 0.22)), (0.36, (0.92, 0.93, 0.92)), (0.52, (0.85, 0.55, 0.16)),
                          (0.68, (0.35, 0.50, 0.75)), (0.82, (0.60, 0.25, 0.08)), (0.93, (0.90, 0.75, 0.35))], interp="CONSTANT")
    return _out(col, 0.04, 0.0, None)


def emissive(nb, c, col=(0.86, 0.86, 0.84)):
    n, _ = nb.noise(c.P, 30.0, 2.0, 0.5)
    return _out(nb.cmul(col, nb.add(0.96, nb.mul(n, 0.06))), 0.35, 0.0, None)


def label(nb, c):
    """Bottle labels: luv = (u around 0..1, v up 0..1, id)."""
    u, v, lid = nb.sep(c.luv)
    key = nb.math("FRACT", nb.add(nb.mul(c.rnd, 7.31), 0.13))
    bg = nb.ramp(key, [(0.0, (0.75, 0.68, 0.52)), (0.2, (0.02, 0.02, 0.02)), (0.4, (0.78, 0.78, 0.76)), (0.55, (0.20, 0.02, 0.02)),
                       (0.7, (0.02, 0.05, 0.12)), (0.85, (0.55, 0.42, 0.25))], interp="CONSTANT")
    ink = nb.ramp(key, [(0.0, (0.08, 0.05, 0.03)), (0.2, (0.70, 0.52, 0.20)), (0.4, (0.05, 0.05, 0.08)), (0.55, (0.75, 0.62, 0.35)),
                        (0.7, (0.70, 0.55, 0.25)), (0.85, (0.06, 0.03, 0.02))], interp="CONSTANT")
    foil = nb.math("GREATER_THAN", nb.math("FRACT", nb.mul(key, 5.0)), 0.5)
    # border lines
    b1 = nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(v, 0.08)), 0.02), 1.0)
    b2 = nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(v, 0.92)), 0.02)
    # front emblem (u around 0.25 faces +X after builder rotation)
    du = nb.mul(nb.sub(nb.math("FRACT", nb.add(u, 0.0)), 0.5), 2.6)
    dv = nb.sub(v, 0.6)
    ell = nb.math("SQRT", nb.add(nb.mul(du, du), nb.mul(nb.mul(dv, dv), 4.0)))
    emb = nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(ell, 0.42)), 0.04), 1.0)
    # faux text rows
    tn, _ = nb.noise(nb.combine(nb.mul(u, 90.0), nb.mul(v, 6.0), lid), 1.0, 0.0, 0.5)
    rowmask = nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", nb.mul(v, 6.5)), 0.5)), 0.18), nb.math("LESS_THAN", nb.math("ABSOLUTE", du), 0.9))
    rowmask = nb.mul(rowmask, nb.math("LESS_THAN", v, 0.42))
    txt = nb.mul(nb.math("GREATER_THAN", tn, 0.52), rowmask)
    big = nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(v, 0.62)), 0.07), nb.math("LESS_THAN", nb.math("ABSOLUTE", du), 0.6))
    tn2, _ = nb.noise(nb.combine(nb.mul(u, 40.0), v, lid), 1.0, 0.0, 0.5)
    big = nb.mul(big, nb.math("GREATER_THAN", tn2, 0.45))
    inkm = nb.clamp(nb.add(nb.add(nb.add(b1, b2), emb), nb.add(txt, big)))
    col = nb.mixc(inkm, bg, ink)
    age, _ = nb.noise(c.P, 20.0, 4.0, 0.6)
    col = nb.cmul(col, nb.add(0.85, nb.mul(age, 0.2)))
    met = nb.mul(inkm, foil)
    r = nb.mix(met, 0.55, 0.25)
    return _out(col, r, met, nb.mul(inkm, 0.4), 0.1, 0.0002)


def decal(nb, c, base_fn, image, ink=(0.85, 0.85, 0.82), ink_rough=0.6, ink_metal=0.0, engrave=0.0, **kw):
    """Base recipe plus an image decal (mask) sampled through the `luv` attribute."""
    o = base_fn(nb, c, **kw)
    u, v, lid = nb.sep(c.luv)
    im = bpy.data.images.get(image)
    m, _ = nb.img(im, nb.combine(u, v, 0.0)) if im else (0.0, None)
    if im:
        m = nb.mul(nb.lum(m), nb.math("GREATER_THAN", lid, 0.5))
        br, _ = nb.noise(c.P, 120.0, 4.0, 0.6)
        m = nb.mul(m, nb.ss(0.2, 0.45, nb.add(br, 0.25))) if not engrave else m
    o["col"] = nb.mixc(m, o["col"], ink)
    o["rough"] = nb.mix(m, o["rough"], ink_rough)
    o["metal"] = nb.mix(m, o["metal"], ink_metal)
    if engrave:
        o["h"] = nb.add(o["h"] if o["h"] is not None else 0.0, nb.mul(m, -engrave))
        o["bs"] = 0.8
        o["bd"] = 0.0008
    return o


def rug(nb, c):
    """Persian rug pattern in object XY (rug spans X 3 m, Y 2 m)."""
    x, y, z = nb.sep(c.P)
    ax = nb.math("ABSOLUTE", x)
    ay = nb.math("ABSOLUTE", y)
    # distance to the rug edge (box), metres
    dx = nb.sub(1.42, ax)
    dy = nb.sub(0.97, ay)
    de = nb.mn(dx, dy)
    navy, red, ivory, gold, dred, teal = (0.006, 0.010, 0.032), (0.115, 0.009, 0.008), (0.42, 0.34, 0.22), (0.28, 0.15, 0.035), (0.045, 0.005, 0.005), (0.01, 0.04, 0.04)
    # border bands
    band = nb.ramp(de, [(0.0, dred), (0.035, ivory), (0.045, navy), (0.20, ivory), (0.21, dred), (0.24, gold), (0.25, red)], interp="CONSTANT")
    # border motif: vine/rosettes along the edges
    along = nb.mix(nb.math("LESS_THAN", dx, dy), x, y)
    rose_u = nb.math("FRACT", nb.mul(along, 5.0))
    rose_v = nb.mul(nb.sub(de, 0.125), 8.0)
    rd = nb.math("SQRT", nb.add(nb.mul(nb.sub(rose_u, 0.5), nb.sub(rose_u, 0.5)), nb.mul(rose_v, rose_v)))
    rose = nb.mul(nb.math("LESS_THAN", rd, 0.33), nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(de, 0.125)), 0.07))
    petal = nb.math("SINE", nb.mul(nb.math("ARCTAN2", rose_v, nb.sub(rose_u, 0.5)), 8.0))
    rose_col = nb.mixc(nb.math("GREATER_THAN", petal, 0.0), red, gold)
    vine = nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(nb.add(nb.mul(nb.math("SINE", nb.mul(along, 31.4)), 0.035), 0.125), de)), 0.008),
                  nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(de, 0.125)), 0.07))
    border = nb.mixc(vine, band, gold)
    border = nb.mixc(rose, border, rose_col)
    # field: lattice of small motifs (herati-like)
    fu = nb.math("FRACT", nb.mul(x, 6.0))
    fv = nb.math("FRACT", nb.mul(y, 6.0))
    du = nb.sub(fu, 0.5)
    dv = nb.sub(fv, 0.5)
    diam = nb.add(nb.math("ABSOLUTE", du), nb.math("ABSOLUTE", dv))
    lattice = nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(diam, 0.42)), 0.035)
    dot = nb.math("LESS_THAN", diam, 0.12)
    leaf = nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(diam, 0.25)), 0.05), nb.math("GREATER_THAN", nb.math("SINE", nb.mul(nb.math("ARCTAN2", dv, du), 4.0)), 0.3))
    field = nb.mixc(lattice, red, navy)
    field = nb.mixc(leaf, field, ivory)
    field = nb.mixc(dot, field, gold)
    # central medallion (lobed ellipse) + corner spandrels
    ex = nb.div(x, 0.75)
    ey = nb.div(y, 0.5)
    er = nb.math("SQRT", nb.add(nb.mul(ex, ex), nb.mul(ey, ey)))
    ang = nb.math("ARCTAN2", ey, ex)
    lob = nb.add(1.0, nb.mul(nb.math("SINE", nb.mul(ang, 16.0)), 0.06))
    erl = nb.div(er, lob)
    med = nb.ramp(erl, [(0.0, gold), (0.10, navy), (0.14, ivory), (0.18, navy), (0.38, teal), (0.42, ivory), (0.47, dred), (0.80, navy), (0.86, ivory), (0.90, gold), (0.94, (0, 0, 0))], interp="CONSTANT")
    petals = nb.mul(nb.math("GREATER_THAN", nb.math("SINE", nb.mul(ang, 12.0)), 0.55), nb.mul(nb.math("GREATER_THAN", erl, 0.2), nb.math("LESS_THAN", erl, 0.36)))
    med = nb.mixc(petals, med, red)
    inmed = nb.math("LESS_THAN", erl, 0.93)
    field = nb.mixc(inmed, field, med)
    cx = nb.div(nb.sub(ax, 1.17), 0.55)
    cy = nb.div(nb.sub(ay, 0.72), 0.42)
    cr = nb.math("SQRT", nb.add(nb.mul(cx, cx), nb.mul(cy, cy)))
    corner = nb.math("LESS_THAN", cr, 1.0)
    cring = nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(cr, 0.95)), 0.05)
    field = nb.mixc(corner, field, navy)
    field = nb.mixc(nb.mul(corner, leaf), field, ivory)
    field = nb.mixc(cring, field, ivory)
    col = nb.mixc(nb.math("LESS_THAN", de, 0.25), field, border)
    # wool: abrash colour banding, pile, wear in centre
    ab, _ = nb.noise(nb.combine(nb.mul(x, 0.6), nb.mul(y, 12.0), 0.0), 1.0, 2.0, 0.5)
    col = nb.cmul(col, nb.add(0.88, nb.mul(ab, 0.24)))
    pile, _ = nb.noise(c.P, 900.0, 3.0, 0.7)
    knots = nb.mul(nb.math("SINE", nb.mul(x, 1300.0)), nb.math("SINE", nb.mul(y, 1300.0)))
    col = nb.cmul(col, nb.add(0.85, nb.mul(pile, 0.3)))
    wear, _ = nb.noise(c.P, 1.5, 3.0, 0.5)
    wm = nb.mul(nb.ss(0.5, 0.75, wear), nb.ss(0.4, 0.1, nb.div(er, 2.5)))
    col = nb.mixc(nb.mul(wm, 0.12), col, ivory)
    col = nb.cmul(col, nb.mix(nb.mul(c.cav, 1.5), 1.0, 0.5))
    h = nb.add(nb.mul(pile, 1.0), nb.mul(knots, 0.15))
    return _out(col, nb.add(0.88, nb.mul(pile, 0.08)), 0.0, h, 0.6, 0.0008)


def foam(nb, c, col=(0.035, 0.035, 0.037)):
    d, _, _ = nb.vor(c.P, 700.0, "F1", 1.0)
    n, _ = nb.noise(c.P, 10.0, 3.0, 0.5)
    col_s = nb.cmul(col, nb.add(0.85, nb.mul(n, 0.3)))
    col_s = nb.cmul(col_s, nb.mix(nb.mul(c.cav, 2.0), 1.0, 0.3))
    return _out(col_s, 0.95, 0.0, nb.mul(d, 1.0), 0.8, 0.001)


def perforated(nb, c, col=(0.02, 0.02, 0.022), pitch=180.0):
    """Speaker grille: hex-ish hole pattern in the plane facing +X (Y/Z coords)."""
    x, y, z = nb.sep(c.P)
    v, _, _ = nb.vor(nb.combine(y, z, 0.0), pitch, "F1", 0.0, dims="2D")
    holes = nb.ss(0.27, 0.22, v)
    col_s = nb.cmul(col, nb.sub(1.0, nb.mul(holes, 0.85)))
    return _out(col_s, nb.add(0.45, nb.mul(holes, 0.4)), nb.mul(nb.sub(1.0, holes), 0.0), nb.mul(holes, -1.0), 0.8, 0.0015)


def vinyl(nb, c):
    x, y, z = nb.sep(c.P)
    return _out((0.012, 0.012, 0.012), 0.22, 0.0, None)


def mirror(nb, c):
    n, _ = nb.noise(c.P, 3.0, 6.0, 0.7)
    sp, _ = nb.noise(c.P, 40.0, 6.0, 0.7)
    spots = nb.ss(0.68, 0.75, sp)
    col = nb.mixc(nb.ss(0.3, 0.8, n), (0.32, 0.28, 0.24), (0.38, 0.33, 0.27))
    col = nb.mixc(spots, col, (0.05, 0.04, 0.03))
    r = nb.add(0.03, nb.mul(spots, 0.5))
    return _out(col, r, nb.sub(1.0, spots), None)


def magazines(nb, c):
    col = nb.ramp(c.rnd, [(0.0, (0.6, 0.05, 0.03)), (0.15, (0.75, 0.72, 0.65)), (0.3, (0.05, 0.08, 0.3)), (0.45, (0.7, 0.55, 0.05)),
                          (0.6, (0.03, 0.03, 0.03)), (0.75, (0.55, 0.57, 0.55)), (0.9, (0.1, 0.35, 0.15))], interp="CONSTANT")
    x, y, z = nb.sep(c.P)
    tn, _ = nb.noise(nb.combine(nb.mul(y, 120.0), nb.mul(z, 25.0), nb.mul(c.rnd, 50.0)), 1.0, 0.0, 0.5)
    rows = nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", nb.mul(z, 60.0)), 0.5)), 0.25)
    txt = nb.mul(nb.math("GREATER_THAN", tn, 0.55), rows)
    col = nb.mixc(nb.mul(txt, 0.6), col, (0.05, 0.05, 0.05))
    col = nb.cmul(col, nb.mix(nb.mul(c.cav, 1.5), 1.0, 0.5))
    return _out(col, 0.45, 0.0, None)


def trashbag(nb, c):
    n, _ = nb.noise(c.P, 18.0, 6.0, 0.65, dist=0.5)
    cr = nb.pw(nb.clamp(nb.sub(1.0, nb.mul(nb.math("ABSOLUTE", nb.sub(n, 0.5)), 10.0))), 2.0)
    col = nb.cmul((0.012, 0.013, 0.014), nb.add(0.8, nb.mul(cr, 0.8)))
    dust, _ = nb.noise(c.P, 6.0, 4.0, 0.6)
    col = nb.mixc(nb.mul(nb.ss(0.6, 0.8, dust), 0.5), col, (0.05, 0.045, 0.04))
    r = nb.add(0.33, nb.add(nb.mul(cr, 0.15), nb.mul(nb.ss(0.6, 0.8, dust), 0.35)))
    return _out(col, r, 0.0, nb.mul(cr, -1.0), 0.5, 0.001)


def tire(nb, c):
    o = rubber(nb, c, (0.018, 0.018, 0.018), 0.8)
    return o


def stencil_wood(nb, c, image="STENCIL"):
    return decal(nb, c, lambda nb_, c_: wood(nb_, c_, (0.07, 0.045, 0.022), (0.19, 0.125, 0.06), rough=0.8, ring=10.0, pore=0.6, lacquer=False, worn=0.5),
                 image, ink=(0.62, 0.58, 0.42), ink_rough=0.75)


def ao_only(nb, c):
    return _out((0.5, 0.5, 0.5), 0.5, 0.0, None)


# Recipe table: name -> (fn, kwargs)
WALNUT_D, WALNUT_L = (0.020, 0.0085, 0.0042), (0.088, 0.042, 0.021)
MATS = {
    "walnut": (wood, dict(dark=WALNUT_D, light=WALNUT_L)),
    "walnut_satin": (wood, dict(dark=WALNUT_D, light=WALNUT_L, rough=0.42)),
    "walnut_dark": (wood, dict(dark=(0.025, 0.010, 0.005), light=(0.10, 0.045, 0.02), rough=0.3)),
    "pine": (wood, dict(dark=(0.07, 0.045, 0.022), light=(0.19, 0.125, 0.06), rough=0.8, ring=10.0, pore=0.6, lacquer=False, worn=0.5)),
    "oak_turned": (wood, dict(dark=(0.10, 0.05, 0.02), light=(0.30, 0.17, 0.08), rough=0.4)),
    "brass": (brass, dict()),
    "brass_polished": (brass, dict(polish=0.10, tarnish=0.25)),
    "brass_aged": (brass, dict(polish=0.32, tarnish=1.0, base=(0.70, 0.50, 0.22))),
    "brass_unbrushed": (brass, dict(polish=0.14, tarnish=0.35, brushed=0.15)),
    "marble_black": (marble, dict()),
    "marble_white": (marble, dict(base=(0.62, 0.60, 0.57), vein=(0.18, 0.17, 0.16), base2=(0.75, 0.74, 0.71), rough=0.07)),
    "leather_oxblood": (leather, dict(col=(0.085, 0.014, 0.010))),
    "leather_black": (leather, dict(col=(0.016, 0.014, 0.013), rough=0.38)),
    "leather_cognac": (leather, dict(col=(0.20, 0.075, 0.025), rough=0.45)),
    "leather_green": (leather, dict(col=(0.006, 0.026, 0.014), rough=0.62, crease=0.3, worn=0.3)),
    "velvet_burgundy": (velvet, dict()),
    "velvet_emerald": (velvet, dict(col=(0.008, 0.055, 0.032))),
    "chrome": (metal, dict(col=(0.62, 0.62, 0.64), rough=0.05, dirt=0.2)),
    "steel": (metal, dict(col=(0.55, 0.55, 0.56), rough=0.25, brushed=0.6)),
    "steel_dark": (metal, dict(col=(0.10, 0.10, 0.11), rough=0.35, brushed=0.4)),
    "aluminium": (metal, dict(col=(0.80, 0.80, 0.81), rough=0.28, brushed=1.0)),
    "galvanized": (metal, dict(col=(0.45, 0.46, 0.46), rough=0.45, brushed=0.2, dirt=0.6)),
    "cast_iron": (paint, dict(col=(0.018, 0.018, 0.019), rough=0.45, peel=1.0, grime=0.5, rust=0.6, chip=0.5, chip_col=(0.08, 0.04, 0.02))),
    "powder_black": (paint, dict(col=(0.022, 0.022, 0.024), rough=0.48, peel=1.0, grime=0.3)),
    "lacquer_black": (paint, dict(col=(0.008, 0.008, 0.009), rough=0.07, peel=0.3, grime=0.15)),
    "paint_car": (paint, dict(col=(0.75, 0.75, 0.75), rough=0.10, mask=1.0, peel=0.5, grime=0.07)),
    "paint_truck": (paint, dict(col=(0.75, 0.75, 0.75), rough=0.3, mask=1.0, peel=0.8, grime=0.55, streak=0.4)),
    "paint_box_white": (paint, dict(col=(0.62, 0.62, 0.60), rough=0.4, peel=0.4, grime=0.7, streak=0.6)),
    "paint_dumpster": (paint, dict(col=(0.025, 0.075, 0.04), rough=0.5, peel=1.0, grime=0.7, chip=1.0, chip_col=(0.10, 0.05, 0.025), rust=0.8, streak=0.6)),
    "paint_kiosk": (paint, dict(col=(0.012, 0.045, 0.03), rough=0.3, peel=0.6, grime=0.5, chip=0.6, streak=0.3)),
    "paint_yellow": (paint, dict(col=(0.75, 0.48, 0.02), rough=0.4, peel=0.6, grime=0.5, chip=0.7)),
    "paint_white": (paint, dict(col=(0.7, 0.7, 0.68), rough=0.35, peel=0.6, grime=0.4)),
    "paint_red": (paint, dict(col=(0.40, 0.02, 0.015), rough=0.3, peel=0.6, grime=0.4)),
    "duratex": (plastic, dict(col=(0.018, 0.018, 0.019), rough=0.75, grain=250.0, gstr=1.0)),
    "plastic_black": (plastic, dict()),
    "plastic_grey": (plastic, dict(col=(0.10, 0.10, 0.105), rough=0.45)),
    "plastic_case": (plastic, dict(col=(0.016, 0.016, 0.017), rough=0.6, grain=180.0, gstr=1.0)),
    "plastic_amber": (plastic, dict(col=(0.6, 0.18, 0.01), rough=0.2, grain=100, gstr=0.1)),
    "plastic_redlens": (plastic, dict(col=(0.35, 0.01, 0.01), rough=0.15, grain=100, gstr=0.1)),
    "rubber": (rubber, dict()),
    "tire": (tire, dict()),
    "concrete": (concrete, dict(col=(0.105, 0.10, 0.093))),
    "concrete_dark": (concrete, dict(col=(0.06, 0.058, 0.055))),
    "leaves": (leaves, dict()),
    "soil": (soil, dict()),
    "linen": (fabric, dict(col=(0.36, 0.30, 0.22))),
    "canvas_black": (fabric, dict(col=(0.03, 0.03, 0.03), weave=700.0)),
    "glass": (glass, dict()),
    "glass_bottles": (glass_bottles, dict()),
    "glass_frosted": (glass, dict(col=(0.92, 0.90, 0.86), rough=0.45, dirt=0.05)),
    "glass_green": (glass, dict(col=(0.008, 0.11, 0.035), rough=0.04)),
    "glass_car": (glass, dict(col=(0.22, 0.25, 0.25), rough=0.02, dirt=0.1)),
    "glass_lamp": (glass, dict(col=(0.92, 0.88, 0.80), rough=0.08, dirt=0.25)),
    "glass_lens": (glass, dict(col=(0.85, 0.88, 0.92), rough=0.01, dirt=0.0)),
    "crystal": (glass, dict(col=(0.97, 0.97, 0.98), rough=0.0, dirt=0.02)),
    "emit": (emissive, dict()),
    "label": (label, dict()),
    "rug": (rug, dict()),
    "foam": (foam, dict()),
    "grille": (perforated, dict()),
    "vinyl": (vinyl, dict()),
    "mirror": (mirror, dict()),
    "magazines": (magazines, dict()),
    "trashbag": (trashbag, dict()),
    "stencil_wood": (stencil_wood, dict()),
    "plaque_brass": (decal, dict(base_fn=brass, image="PLAQUE", ink=(0.03, 0.025, 0.02), ink_rough=0.7, ink_metal=0.0, engrave=1.0, polish=0.12, tarnish=0.3)),
    "plate": (decal, dict(base_fn=paint, image="PLATE", ink=(0.02, 0.03, 0.08), ink_rough=0.4, engrave=0.0, col=(0.72, 0.72, 0.70), rough=0.3, grime=0.6)),
}


def build_recipe_material(name):
    fn, kw = MATS[name]
    m = bpy.data.materials.new("R_" + name)
    nt = m.node_tree
    nt.nodes.clear()
    nb = NB(nt)
    c = Ctx(nb)
    o = fn(nb, c, **kw)
    # outputs
    ob = nb.n("ShaderNodeOutputMaterial", target="CYCLES")
    ob.name = "OUT_BC"
    em = nb.n("ShaderNodeEmission")
    nb.s(o["col"], em.inputs["Color"])
    nb.s(1.0, em.inputs["Strength"])
    nt.links.new(em.outputs[0], ob.inputs["Surface"])
    oo = nb.n("ShaderNodeOutputMaterial", target="CYCLES")
    oo.name = "OUT_ORM"
    em2 = nb.n("ShaderNodeEmission")
    nb.s(nb.combine(o["mask"], nb.clamp(o["rough"]), nb.clamp(o["metal"]) if isinstance(o["metal"], bpy.types.NodeSocket) else o["metal"]), em2.inputs["Color"])
    nt.links.new(em2.outputs[0], oo.inputs["Surface"])
    on = nb.n("ShaderNodeOutputMaterial", target="CYCLES")
    on.name = "OUT_N"
    pb = nb.n("ShaderNodeBsdfPrincipled")
    if o["h"] is not None:
        nb.s(nb.bump(o["h"], o["bs"], o["bd"]), pb.inputs["Normal"])
    nt.links.new(pb.outputs[0], on.inputs["Surface"])
    # procedural preview (used for tileable MI_ slots, which are not baked)
    op = nb.n("ShaderNodeOutputMaterial", target="CYCLES")
    op.name = "OUT_PV"
    pp = nb.n("ShaderNodeBsdfPrincipled")
    nb.s(o["col"], pp.inputs["Base Color"])
    nb.s(nb.clamp(o["rough"]), pp.inputs["Roughness"])
    nb.s(o["metal"], pp.inputs["Metallic"])
    if o["h"] is not None:
        nb.s(nb.bump(o["h"], o["bs"], o["bd"]), pp.inputs["Normal"])
    nt.links.new(pp.outputs[0], op.inputs["Surface"])
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeOutputMaterial":
            n.is_active_output = n.name == "OUT_BC"
    return m


def aux_material(edge_r=0.004, ao_dist=0.25):
    name = f"AUX_{edge_r:.4f}_{ao_dist:.3f}"
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    nb = NB(nt)
    geo = nb.n("ShaderNodeNewGeometry")
    bev = nb.n("ShaderNodeBevel", samples=16)
    nb.s(edge_r, bev.inputs["Radius"])
    d = nb.vmath("DOT_PRODUCT", bev.outputs[0], geo.outputs["Normal"])
    e = nb.maprange(nb.sub(1.0, d), 0.02, 0.16, 0.0, 1.0)
    ao = nb.n("ShaderNodeAmbientOcclusion", samples=16, only_local=False)
    nb.s(ao_dist, ao.inputs["Distance"])
    em = nb.n("ShaderNodeEmission")
    nb.s(nb.combine(e, ao.outputs["AO"], 0.0), em.inputs["Color"])
    out = nb.n("ShaderNodeOutputMaterial", target="CYCLES")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m
