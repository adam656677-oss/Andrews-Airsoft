"""Master materials, material instances and slot assignment for Andrew's Airsoft."""

import unreal

from . import common as C
from . import layouts as L

MEL = unreal.MaterialEditingLibrary
MP = unreal.MaterialProperty
ST = unreal.MaterialSamplerType

MASTER_PBR = C.MAT_ROOT + "/M_AirsoftPBR"
MASTER_TILE = C.MAT_ROOT + "/M_Tileable"
MASTER_EMISSIVE = C.MAT_ROOT + "/M_Emissive"
MASTER_GLASS = C.MAT_ROOT + "/M_Glass"
MASTER_MASKED = C.MAT_ROOT + "/M_Masked"
MASTER_SIGN = C.MAT_ROOT + "/M_SignText"
DEF = C.TEX_ROOT + "/Defaults/"

# Flat colours for tileables whose textures are not generated yet (multiplied into a white texture).
FALLBACK_COLOR = {
    "Grass": (0.16, 0.24, 0.08), "Dirt": (0.25, 0.18, 0.11), "Gravel": (0.35, 0.33, 0.3), "Mud": (0.18, 0.13, 0.09),
    "ForestFloor": (0.15, 0.12, 0.08), "Asphalt": (0.08, 0.08, 0.085), "AsphaltWet": (0.035, 0.035, 0.04),
    "Concrete": (0.42, 0.41, 0.39), "ConcreteFloor": (0.38, 0.37, 0.35), "Plywood": (0.55, 0.4, 0.25),
    "PlywoodPainted": (0.3, 0.33, 0.3), "OSB": (0.5, 0.38, 0.22), "Timber": (0.35, 0.25, 0.15),
    "Walnut": (0.15, 0.08, 0.04), "Brick": (0.35, 0.15, 0.1), "BrickDark": (0.15, 0.08, 0.07),
    "PaintedSteel": (0.3, 0.32, 0.33), "CorrodedMetal": (0.3, 0.17, 0.09), "DiamondPlate": (0.45, 0.46, 0.47),
    "Rubber": (0.03, 0.03, 0.03), "Canvas": (0.38, 0.36, 0.28), "Burlap": (0.4, 0.32, 0.2),
    "Straw": (0.6, 0.48, 0.25), "Bark": (0.12, 0.09, 0.06), "Granite": (0.35, 0.34, 0.33),
    "MarbleBlack": (0.02, 0.02, 0.025), "Carpet": (0.2, 0.03, 0.05), "Velvet": (0.2, 0.01, 0.03),
    "Leather": (0.12, 0.05, 0.03), "Brass": (0.6, 0.42, 0.15), "Netting": (0.1, 0.12, 0.08),
}
METALLIC_TILE = {"Brass": 1.0, "DiamondPlate": 1.0, "CorrodedMetal": 0.6}

# Glass pieces: (tint, opacity, roughness, glow) keyed by asset id ("*" = default)
GLASS = {
    "*": ((0.08, 0.12, 0.13), 0.22, 0.04, 0.0),
    "Car_Sedan": ((0.03, 0.035, 0.04), 0.6, 0.03, 0.0), "Car_Coupe": ((0.03, 0.035, 0.04), 0.6, 0.03, 0.0),
    "BoxTruck": ((0.04, 0.045, 0.05), 0.55, 0.05, 0.0),
    "BackBar_4m": ((0.25, 0.16, 0.05), 0.45, 0.06, 0.6),        # bottles, lit by the LED shelf
    "StreetLamp": ((1.0, 0.62, 0.3), 0.5, 0.3, 12.0), "Chandelier": ((1.0, 0.85, 0.65), 0.35, 0.05, 4.0),
    "WallSconce": ((1.0, 0.8, 0.6), 0.6, 0.4, 8.0), "CeilingLight_Brass": ((1.0, 0.86, 0.68), 0.75, 0.6, 10.0),
    "FloodlightTower": ((1.0, 0.92, 0.8), 0.6, 0.2, 30.0), "MovingHeadLight": ((0.9, 0.9, 1.0), 0.5, 0.1, 6.0),
    "BankersLamp": ((0.05, 0.35, 0.12), 0.85, 0.15, 1.5), "Laser": ((0.6, 0.05, 0.05), 0.4, 0.05, 2.0),
}
# Emissive pieces: (colour override or None = use the baked BC, intensity)
EMISSIVE = {
    "*": (None, 12.0), "NeonSign_Velvet": (None, 45.0), "StreetLamp": (None, 30.0), "Chandelier": (None, 22.0),
    "WallSconce": (None, 16.0), "BackBar_4m": (None, 28.0), "DJBooth": (None, 18.0), "Car_Sedan": (None, 9.0),
    "Car_Coupe": (None, 9.0), "BoxTruck": (None, 8.0), "GunDisplayBay": (None, 6.0), "CeilingLight_Brass": (None, 14.0),
    "BankersLamp": (None, 10.0), "ArmorySign": (None, 8.0), "MovingHeadLight": (None, 20.0),
}
RETICLE = ((1.0, 0.05, 0.03), 30.0)

_cache = {}


# ---------------------------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------------------------
def _split(src):
    return src if isinstance(src, tuple) else (src, "")


def link(src, dst, inp=""):
    e, o = _split(src)
    try:
        MEL.connect_material_expressions(e, o, dst, inp)
    except Exception as ex:
        C.SUMMARY.once("link:%s:%s" % (type(dst).__name__, inp), "material link %s -> %s.%s failed: %s" %
                       (type(e).__name__, type(dst).__name__, inp, ex))


def out(src, prop):
    e, o = _split(src)
    try:
        MEL.connect_material_property(e, o, prop)
    except Exception as ex:
        C.SUMMARY.once("out:%s" % prop, "material output %s failed: %s" % (prop, ex))


class Graph(object):
    def __init__(self, mat):
        self.m = mat

    def e(self, cls, x, y, **props):
        n = MEL.create_material_expression(self.m, cls, x, y)
        for k, v in props.items():
            C.try_set(n, k, v)
        return n

    def tex(self, name, default, sampler, x, y, uv=None, group="Textures"):
        n = self.e(unreal.MaterialExpressionTextureSampleParameter2D, x, y)
        n.set_editor_property("parameter_name", name)
        t = C.load(DEF + default)
        if t:
            n.set_editor_property("texture", t)
        n.set_editor_property("sampler_type", sampler)
        C.try_set(n, "group", group, quiet=True)
        if uv is not None:
            link(uv, n, "UVs")
        return n

    def scalar(self, name, default, x, y, group="Params"):
        n = self.e(unreal.MaterialExpressionScalarParameter, x, y)
        n.set_editor_property("parameter_name", name)
        n.set_editor_property("default_value", float(default))
        C.try_set(n, "group", group, quiet=True)
        return n

    def vector(self, name, rgb, x, y, group="Params"):
        n = self.e(unreal.MaterialExpressionVectorParameter, x, y)
        n.set_editor_property("parameter_name", name)
        n.set_editor_property("default_value", C.lc(rgb))
        C.try_set(n, "group", group, quiet=True)
        return n

    def const(self, v, x, y):
        return self.e(unreal.MaterialExpressionConstant, x, y, r=float(v))

    def const3(self, rgb, x, y):
        return self.e(unreal.MaterialExpressionConstant3Vector, x, y, constant=C.lc(rgb))

    def op(self, cls, a, b, x, y, const_b=None):
        n = self.e(cls, x, y)
        if a is not None:
            link(a, n, "A")
        if b is not None:
            link(b, n, "B")
        elif const_b is not None:
            C.try_set(n, "const_b", float(const_b))
        return n

    def mul(self, a, b, x, y, const_b=None):
        return self.op(unreal.MaterialExpressionMultiply, a, b, x, y, const_b)

    def add(self, a, b, x, y, const_b=None):
        return self.op(unreal.MaterialExpressionAdd, a, b, x, y, const_b)

    def sub(self, a, b, x, y, const_b=None):
        return self.op(unreal.MaterialExpressionSubtract, a, b, x, y, const_b)

    def lerp(self, a, b, alpha, x, y, const_a=None):
        n = self.e(unreal.MaterialExpressionLinearInterpolate, x, y)
        if a is not None:
            link(a, n, "A")
        elif const_a is not None:
            C.try_set(n, "const_a", float(const_a))
        link(b, n, "B")
        link(alpha, n, "Alpha")
        return n

    def sat(self, a, x, y):
        n = self.e(unreal.MaterialExpressionSaturate, x, y)
        link(a, n, "")
        return n

    def mask(self, a, x, y, r=False, g=False, b=False, al=False):
        n = self.e(unreal.MaterialExpressionComponentMask, x, y, r=r, g=g, b=b, a=al)
        link(a, n, "")
        return n

    def switch(self, name, t, f, x, y, default=True):
        n = self.e(unreal.MaterialExpressionStaticSwitchParameter, x, y)
        n.set_editor_property("parameter_name", name)
        C.try_set(n, "default_value", bool(default))
        link(t, n, "True")
        link(f, n, "False")
        return n


def _new_material(path):
    folder, name = path.rsplit("/", 1)
    C.ensure_dir(folder)
    mat = C.load(path)
    if mat:
        try:
            MEL.delete_all_material_expressions(mat)
        except Exception as e:
            C.warn("could not clear %s (%s); rebuilding on top" % (path, e))
    else:
        mat = C.asset_tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())
    return mat


def _finish(mat, nanite=True):
    if nanite:
        C.try_set(mat, "used_with_nanite", True, quiet=True)
    try:
        MEL.layout_material_expressions(mat)
    except Exception:
        pass
    try:
        MEL.recompile_material(mat)
    except Exception as e:
        C.warn("recompile %s: %s" % (mat.get_name(), e))
    C.save_asset(mat)
    C.SUMMARY.inc("master materials built")
    return mat


# ---------------------------------------------------------------------------------------------
# Masters
# ---------------------------------------------------------------------------------------------
def build_pbr():
    m = _new_material(MASTER_PBR)
    C.try_set(m, "blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    C.try_set(m, "shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    g = Graph(m)
    bc = g.tex("BaseColor", "T_Default_BC", ST.SAMPLERTYPE_COLOR, -1600, -500)
    nrm = g.tex("Normal", "T_Default_N", ST.SAMPLERTYPE_NORMAL, -1600, 300)
    orm = g.tex("ORM", "T_Default_ORM", ST.SAMPLERTYPE_MASKS, -1600, 0)
    msk = g.tex("Mask", "T_Default_M", ST.SAMPLERTYPE_MASKS, -1600, -250)
    pt = g.vector("PrimaryTint", (1, 1, 1), -1300, -900, "Tint")
    st = g.vector("SecondaryTint", (1, 1, 1), -1300, -750, "Tint")
    at = g.vector("AccentTint", (1.0, 0.45, 0.08), -1300, -600, "Tint")
    bt = g.vector("BaseTint", (1, 1, 1), -1300, -1050, "Tint")
    tm = g.scalar("TintMetallic", 0.0, -1300, 150, "Tint")
    tr = g.scalar("TintRoughness", 0.55, -1300, 250, "Tint")
    rd = g.scalar("RoughnessDetail", 0.35, -1300, 350, "Tint")
    rs = g.scalar("RoughnessScale", 1.0, -500, 250)
    ns = g.scalar("NormalStrength", 1.0, -500, 450)
    one = g.const3((1, 1, 1), -1050, -1100)
    # role tints: BC * lerp(1, tint, mask) per channel
    lp = g.lerp(one, pt, (msk, "R"), -1000, -900)
    ls = g.lerp(one, st, (msk, "G"), -1000, -750)
    la = g.lerp(one, at, (msk, "B"), -1000, -600)
    tint = g.mul(g.mul(lp, ls, -800, -800), la, -650, -750)
    base_bt = g.mul((bc, "RGB"), bt, -800, -500)
    base_t = g.mul(base_bt, tint, -500, -650)
    rg = g.add((msk, "R"), (msk, "G"), -1000, -250)
    msum = g.sat(g.add(rg, (msk, "B"), -850, -250), -700, -250)
    metal_t = g.lerp((orm, "B"), tm, msum, -500, 0)
    rdet = g.add(tr, g.mul(g.sub((orm, "G"), None, -1000, 300, const_b=0.5), rd, -850, 300), -700, 250)
    rough_t = g.lerp((orm, "G"), rdet, msum, -500, 150)
    base = g.switch("UseMask", base_t, base_bt, -250, -600)
    metal = g.switch("UseMask", metal_t, (orm, "B"), -250, 0)
    rough = g.switch("UseMask", rough_t, (orm, "G"), -250, 150)
    rough = g.sat(g.mul(rough, rs, -100, 200), 50, 200)
    flat = g.const3((0, 0, 1), -500, 550)
    normal = g.lerp(flat, (nrm, "RGB"), ns, -250, 450)
    out(base, MP.MP_BASE_COLOR)
    out(metal, MP.MP_METALLIC)
    out(rough, MP.MP_ROUGHNESS)
    out(normal, MP.MP_NORMAL)
    out((orm, "R"), MP.MP_AMBIENT_OCCLUSION)
    return _finish(m)


def _world_uv(g, tm, x, y):
    """Dominant-axis planar projection of world position, tiled every TileMeters."""
    wp = g.e(unreal.MaterialExpressionWorldPosition, x, y)
    scale = g.mul(tm, None, x, y + 120, const_b=100.0)
    p = g.op(unreal.MaterialExpressionDivide, wp, scale, x + 150, y)
    pxy = g.mask(p, x + 300, y - 100, r=True, g=True)
    pyz = g.mask(p, x + 300, y, g=True, b=True)
    pxz = g.mask(p, x + 300, y + 100, r=True, b=True)
    nabs = g.e(unreal.MaterialExpressionAbs, x + 150, y + 250)
    link(g.e(unreal.MaterialExpressionVertexNormalWS, x, y + 250), nabs, "")
    nx = g.mask(nabs, x + 300, y + 220, r=True)
    ny = g.mask(nabs, x + 300, y + 300, g=True)
    nz = g.mask(nabs, x + 300, y + 380, b=True)
    sx = g.sat(g.mul(g.sub(nx, ny, x + 450, y + 240), None, x + 600, y + 240, const_b=1000.0), x + 750, y + 240)
    side = g.lerp(pxz, pyz, sx, x + 900, y + 50)
    mxy = g.op(unreal.MaterialExpressionMax, nx, ny, x + 450, y + 340)
    top = g.sat(g.mul(g.sub(nz, mxy, x + 600, y + 360), None, x + 750, y + 360, const_b=1000.0), x + 900, y + 360)
    return g.lerp(side, pxy, top, x + 1050, y)


def build_tileable():
    m = _new_material(MASTER_TILE)
    C.try_set(m, "blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    C.try_set(m, "shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    g = Graph(m)
    tm = g.scalar("TileMeters", 2.0, -2600, 0, "Tiling")
    wa = g.scalar("WorldAligned", 0.0, -2600, 200, "Tiling")
    tc = g.e(unreal.MaterialExpressionTextureCoordinate, -2600, -300)
    k = g.op(unreal.MaterialExpressionDivide, None, tm, -2450, -150)
    C.try_set(k, "const_a", 2.0)                       # architecture UVs: 1 UV = 2 m
    mesh_uv = g.mul(tc, k, -2300, -300)
    world_uv = _world_uv(g, tm, -2600, 400)
    uv = g.lerp(mesh_uv, world_uv, wa, -1300, 0)
    bc = g.tex("BaseColor", "T_Default_BC", ST.SAMPLERTYPE_COLOR, -1000, -600, uv)
    nrm = g.tex("Normal", "T_Default_N", ST.SAMPLERTYPE_NORMAL, -1000, 400, uv)
    orm = g.tex("ORM", "T_Default_ORM", ST.SAMPLERTYPE_MASKS, -1000, 0, uv)
    hgt = g.tex("Height", "T_Default_H", ST.SAMPLERTYPE_MASKS, -1000, 200, uv)
    macro_uv = g.mul(uv, None, -1150, -350, const_b=0.071)
    macro = g.tex("BaseColor", "T_Default_BC", ST.SAMPLERTYPE_COLOR, -1000, -300, macro_uv)
    dot = g.e(unreal.MaterialExpressionDotProduct, -750, -300)
    link((macro, "RGB"), dot, "A")
    link(g.const3((0.333, 0.333, 0.333), -900, -200), dot, "B")
    cv = g.scalar("ColorVariation", 0.3, -750, -150)
    var = g.lerp(None, g.mul(dot, None, -600, -300, const_b=2.2), cv, -450, -300, const_a=1.0)
    tint = g.vector("Tint", (1, 1, 1), -750, -750)
    base = g.mul(g.mul((bc, "RGB"), tint, -600, -650), var, -300, -500)
    rs = g.scalar("RoughnessScale", 1.0, -750, 50)
    ra = g.scalar("RoughnessAdd", 0.0, -750, 130)
    rough = g.sat(g.add(g.mul((orm, "G"), rs, -600, 50), ra, -450, 80), -300, 80)
    ms = g.scalar("MetallicScale", 1.0, -750, 250)
    metal = g.mul((orm, "B"), ms, -450, 220)
    hao = g.scalar("HeightAO", 0.25, -750, 330)
    ao = g.mul((orm, "R"), g.lerp(None, (hgt, "R"), hao, -600, 300, const_a=1.0), -450, 320)
    ns = g.scalar("NormalStrength", 1.0, -750, 520)
    normal = g.lerp(g.const3((0, 0, 1), -600, 560), (nrm, "RGB"), ns, -450, 480)
    out(base, MP.MP_BASE_COLOR)
    out(rough, MP.MP_ROUGHNESS)
    out(metal, MP.MP_METALLIC)
    out(ao, MP.MP_AMBIENT_OCCLUSION)
    out(normal, MP.MP_NORMAL)
    return _finish(m)


def build_emissive():
    m = _new_material(MASTER_EMISSIVE)
    C.try_set(m, "blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    C.try_set(m, "shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    g = Graph(m)
    t = g.tex("EmissiveMap", "T_Default_BC", ST.SAMPLERTYPE_COLOR, -800, 0)
    col = g.vector("Color", (1.0, 0.45, 0.1), -800, -250)
    inten = g.scalar("Intensity", 8.0, -800, 250)
    e = g.mul(g.mul((t, "RGB"), col, -500, -100), inten, -300, 0)
    out(e, MP.MP_EMISSIVE_COLOR)
    return _finish(m)


def build_glass():
    m = _new_material(MASTER_GLASS)
    C.try_set(m, "blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    C.try_set(m, "shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    C.try_set(m, "translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    for prop, val in (("refraction_method", "RM_INDEX_OF_REFRACTION"), ("refraction_mode", "RM_INDEX_OF_REFRACTION")):
        enum = getattr(unreal, "RefractionMode", None)
        if enum is not None and hasattr(enum, val) and C.try_set(m, prop, getattr(enum, val), quiet=True):
            break
    g = Graph(m)
    tint = g.vector("Tint", (0.08, 0.12, 0.13), -800, -300)
    rough = g.scalar("Roughness", 0.04, -800, 0)
    metal = g.scalar("Metallic", 0.0, -800, 80)
    spec = g.scalar("Specular", 0.6, -800, 160)
    opac = g.scalar("Opacity", 0.22, -800, 260)
    fres = g.e(unreal.MaterialExpressionFresnel, -800, 380, exponent=4.0, base_reflect_fraction=0.04)
    fo = g.scalar("FresnelOpacity", 0.5, -800, 500)
    opacity = g.sat(g.add(opac, g.mul(fres, fo, -600, 420), -450, 300), -300, 300)
    glow = g.scalar("Glow", 0.0, -800, -150)
    emis = g.mul(tint, glow, -500, -200)
    ior = g.scalar("IOR", 1.05, -800, 640)
    out(tint, MP.MP_BASE_COLOR)
    out(rough, MP.MP_ROUGHNESS)
    out(metal, MP.MP_METALLIC)
    out(spec, MP.MP_SPECULAR)
    out(opacity, MP.MP_OPACITY)
    out(emis, MP.MP_EMISSIVE_COLOR)
    out(ior, MP.MP_REFRACTION)
    return _finish(m, nanite=False)


def build_masked():
    m = _new_material(MASTER_MASKED)
    C.try_set(m, "blend_mode", unreal.BlendMode.BLEND_MASKED)
    C.try_set(m, "shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    C.try_set(m, "two_sided", True)
    C.try_set(m, "opacity_mask_clip_value", 0.4)
    g = Graph(m)
    tc = g.e(unreal.MaterialExpressionTextureCoordinate, -1500, 0)
    uv = g.mul(tc, g.scalar("UVScale", 1.0, -1500, 150, "Tiling"), -1300, 0)
    bc = g.tex("BaseColor", "T_Default_BC", ST.SAMPLERTYPE_COLOR, -1000, -500, uv)
    nrm = g.tex("Normal", "T_Default_N", ST.SAMPLERTYPE_NORMAL, -1000, 400, uv)
    orm = g.tex("ORM", "T_Default_ORM", ST.SAMPLERTYPE_MASKS, -1000, 0, uv)
    opa = g.tex("Opacity", "T_Default_Opacity", ST.SAMPLERTYPE_MASKS, -1000, 200, uv)
    tint = g.vector("Tint", (1, 1, 1), -800, -650)
    base = g.mul((bc, "RGB"), tint, -600, -500)
    sss = g.mul(g.mul(base, g.vector("SubsurfaceTint", (0.55, 0.7, 0.25), -800, -250), -450, -300),
                g.scalar("SubsurfaceStrength", 1.0, -800, -150), -300, -250)
    rough = g.sat(g.mul((orm, "G"), g.scalar("RoughnessScale", 1.0, -800, 80), -600, 50), -450, 50)
    normal = g.lerp(g.const3((0, 0, 1), -700, 560), (nrm, "RGB"), g.scalar("NormalStrength", 1.0, -800, 480), -450, 480)
    out(base, MP.MP_BASE_COLOR)
    out(rough, MP.MP_ROUGHNESS)
    out((orm, "R"), MP.MP_AMBIENT_OCCLUSION)
    out(normal, MP.MP_NORMAL)
    out((opa, "R"), MP.MP_OPACITY_MASK)
    out(sss, MP.MP_SUBSURFACE_COLOR)
    return _finish(m)


def build_sign():
    """Unlit masked text material for TextRenderActors (glowing sign letters)."""
    m = _new_material(MASTER_SIGN)
    C.try_set(m, "blend_mode", unreal.BlendMode.BLEND_MASKED)
    C.try_set(m, "shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    C.try_set(m, "opacity_mask_clip_value", 0.5)
    g = Graph(m)
    font = unreal.EditorAssetLibrary.load_asset("/Engine/EngineFonts/RobotoDistanceField.RobotoDistanceField")
    fs = g.e(unreal.MaterialExpressionFontSampleParameter, -800, 0)
    fs.set_editor_property("parameter_name", "Font")
    if font:
        C.try_set(fs, "font", font)
    C.try_set(fs, "font_texture_page", 0, quiet=True)
    vc = g.e(unreal.MaterialExpressionVertexColor, -800, -250)
    col = g.vector("Color", (1.0, 0.8, 0.45), -800, -400)
    inten = g.scalar("Intensity", 10.0, -800, 250)
    e = g.mul(g.mul((vc, ""), col, -500, -300), inten, -300, -200)
    out(e, MP.MP_EMISSIVE_COLOR)
    out((fs, "A"), MP.MP_OPACITY_MASK)
    return _finish(m, nanite=False)


def build_masters():
    built = {}
    for name, fn in (("M_AirsoftPBR", build_pbr), ("M_Tileable", build_tileable), ("M_Emissive", build_emissive),
                     ("M_Glass", build_glass), ("M_Masked", build_masked), ("M_SignText", build_sign)):
        try:
            built[name] = fn()
        except Exception as e:
            C.SUMMARY.note("building %s failed: %s" % (name, e))
    return built


# ---------------------------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------------------------
_switch_ok = [True]


def make_mi(path, parent, scalars=None, vectors=None, textures=None, switches=None, clear=True):
    if parent is None:
        return None
    if path in _cache and not clear:
        return _cache[path]
    folder, name = path.rsplit("/", 1)
    C.ensure_dir(folder)
    mi = C.load(path)
    if not mi:
        f = unreal.MaterialInstanceConstantFactoryNew()
        C.try_set(f, "initial_parent", parent, quiet=True)
        mi = C.asset_tools().create_asset(name, folder, unreal.MaterialInstanceConstant, f)
        C.SUMMARY.inc("material instances created")
    else:
        C.SUMMARY.inc("material instances updated")
    if mi is None:
        return None
    try:
        MEL.set_material_instance_parent(mi, parent)
    except Exception:
        C.try_set(mi, "parent", parent)
    if clear:
        try:
            MEL.clear_all_material_instance_parameters(mi)
        except Exception:
            pass
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(mi, k, C.lc(v[:3], v[3] if len(v) > 3 else 1.0))
    for k, v in (textures or {}).items():
        if v:
            MEL.set_material_instance_texture_parameter_value(mi, k, v)
    for k, v in (switches or {}).items():
        if not _switch_ok[0]:
            break
        try:
            MEL.set_material_instance_static_switch_parameter_value(mi, k, bool(v))
        except Exception as e:
            _switch_ok[0] = False
            C.SUMMARY.note("static switch parameters cannot be set from Python here (%s); UseMask stays on "
                           "(correct, one extra texture sample)" % e)
    try:
        MEL.update_material_instance(mi)
    except Exception:
        pass
    C.save_asset(mi)
    _cache[path] = mi
    return mi


def _tex(path):
    return C.load(path)


def tileable_path(mid):
    return "%s/Tileable/MI_%s" % (C.MI_ROOT, mid)


def build_tileable_instances(materials):
    """MI_<Material> for every Materials.json entry (and every fallback colour)."""
    tile, masked = C.load(MASTER_TILE), C.load(MASTER_MASKED)
    ids = sorted(set(materials) | set(FALLBACK_COLOR))
    for mid in ids:
        m = materials.get(mid, {})
        folder = "%s/Materials/%s" % (C.TEX_ROOT, mid)
        tx = {k: _tex("%s/T_%s_%s" % (folder, mid, k)) for k in ("BC", "N", "ORM", "H", "Opacity")}
        have = tx["BC"] is not None
        tm = float(m.get("TileMeters", 2.0))
        tint = (1, 1, 1) if have else FALLBACK_COLOR.get(mid, (0.5, 0.5, 0.5))
        if m.get("BlendMode") == "Masked" or mid == "Netting":
            make_mi(tileable_path(mid), masked,
                    scalars={"UVScale": float(m.get("ArchUVScale", 2.0 / tm)), "SubsurfaceStrength": 0.2},
                    vectors={"Tint": tint},
                    textures={"BaseColor": tx["BC"], "Normal": tx["N"], "ORM": tx["ORM"], "Opacity": tx["Opacity"]})
        else:
            sc = {"TileMeters": tm, "ColorVariation": 0.3 if have else 0.0, "MetallicScale": 1.0}
            if not have and mid in METALLIC_TILE:
                sc["MetallicScale"] = 1.0
            make_mi(tileable_path(mid), tile, scalars=sc, vectors={"Tint": tint},
                    textures={"BaseColor": tx["BC"], "Normal": tx["N"], "ORM": tx["ORM"], "Height": tx["H"]})
        if not have:
            C.SUMMARY.miss("tileable textures (flat colour used)", mid)
    # specials
    puddle_base = C.load(tileable_path("AsphaltWet")) or C.load(tileable_path("Asphalt"))
    make_mi("%s/Special/MI_Puddle" % C.MI_ROOT, puddle_base,
            scalars={"WorldAligned": 1.0, "RoughnessScale": 0.05, "RoughnessAdd": 0.0, "NormalStrength": 0.15,
                     "ColorVariation": 0.0}, vectors={"Tint": (0.45, 0.45, 0.5)})
    grass = C.load(tileable_path("Grass"))
    make_mi("%s/Special/MI_Foliage_World" % C.MI_ROOT, grass,
            scalars={"WorldAligned": 1.0, "TileMeters": 1.0}, vectors={"Tint": (0.45, 0.6, 0.3)})
    glass = C.load(MASTER_GLASS)
    make_mi("%s/Glass/MI_Glass_Clear" % C.MI_ROOT, glass)
    make_mi("%s/Glass/MI_Blocker" % C.MI_ROOT, glass,
            scalars={"Opacity": 0.12, "FresnelOpacity": 0.1, "Roughness": 0.5}, vectors={"Tint": (0.9, 0.1, 0.05)})
    make_mi("%s/Emissive/MI_Emissive_Warm_12" % C.MI_ROOT, C.load(MASTER_EMISSIVE),
            scalars={"Intensity": 12.0}, vectors={"Color": L.EMISSIVE_COLORS["Warm"]})
    make_mi("%s/Special/MI_Fallback_Grey" % C.MI_ROOT, tile, vectors={"Tint": (0.35, 0.35, 0.35)},
            scalars={"WorldAligned": 1.0})


def get_box_mi(mat, tint=None, world=True, tile=None):
    """Instance for procedural boxes / fallback shapes: world-aligned tileable, optional paint tint."""
    if mat.startswith("Emissive:"):
        return get_emissive_mi(mat.split(":", 1)[1], 20.0)
    if mat == "Puddle":
        return C.load("%s/Special/MI_Puddle" % C.MI_ROOT)
    if mat == "Foliage":
        return C.load("%s/Special/MI_Foliage_World" % C.MI_ROOT)
    if mat == "Blocker":
        return C.load("%s/Glass/MI_Blocker" % C.MI_ROOT)
    if mat == "Glass":
        return C.load("%s/Glass/MI_Glass_Clear" % C.MI_ROOT)
    base = C.load(tileable_path(mat))
    if base is None:
        base = make_mi(tileable_path(mat), C.load(MASTER_TILE), vectors={"Tint": FALLBACK_COLOR.get(mat, (0.5, 0.5, 0.5))})
    if mat == "Netting":
        return base
    name = "MI_%s" % mat + ("_%s" % tint if tint else "") + ("_World" if world else "") + \
           ("_T%s" % str(tile).replace(".", "p") if tile else "")
    if name == "MI_%s" % mat:
        return base
    path = "%s/Tileable/Variants/%s" % (C.MI_ROOT, name)
    if path in _cache:
        return _cache[path]
    sc = {"WorldAligned": 1.0 if world else 0.0}
    if tile:
        sc["TileMeters"] = float(tile)
    vec = {}
    if tint:
        col = L.TINTS.get(tint, (0.5, 0.5, 0.5))
        # tint the neutral texture: scale so a ~0.5 grey texture lands on the paint colour
        vec["Tint"] = tuple(min(4.0, c * 1.8) for c in col)
    return make_mi(path, base, scalars=sc, vectors=vec, clear=True)


def get_emissive_mi(color, glow):
    g = int(round(glow))
    path = "%s/Emissive/MI_Emissive_%s_%d" % (C.MI_ROOT, color, g)
    if path in _cache:
        return _cache[path]
    mi = C.load(path)
    if mi:
        _cache[path] = mi
        return mi
    return make_mi(path, C.load(MASTER_EMISSIVE), scalars={"Intensity": float(g)},
                   vectors={"Color": L.EMISSIVE_COLORS.get(color, (1, 1, 1))})


def piece_mi_path(cat, aid, piece):
    return "%s/%s/MI_%s_%s" % (C.MI_ROOT, cat, aid, piece)


def variant_names(aid, entry):
    names = list(L.TINT_VARIANTS.get(aid, []))
    for k in (entry.get("TintVariants") or {}):
        if k not in names:
            names.append(k)
    return names


def variant_color(aid, entry, name):
    tv = entry.get("TintVariants") or {}
    if name in tv:
        return tuple(tv[name][:3])
    return L.TINTS.get(name, (0.5, 0.5, 0.5))


def build_piece_instances(reg):
    pbr, glass, emis, masked = (C.load(MASTER_PBR), C.load(MASTER_GLASS), C.load(MASTER_EMISSIVE),
                                C.load(MASTER_MASKED))
    n = 0
    for aid, e in sorted(reg.items()):
        cat = e["Category"]
        for piece in e["Pieces"]:
            pn = piece["Name"]
            slots = piece.get("Slots") or []
            uses_unique = any(C.strip_slot_suffix(s).startswith("M_") for s in slots) or not slots
            if not uses_unique:
                continue
            role = C.piece_role(aid, piece)
            tdir = C.tex_dir(cat, aid)
            tx = {k: _tex("%s/T_%s_%s_%s" % (tdir, aid, pn, k)) for k in ("BC", "N", "ORM", "M", "Opacity")}
            path = piece_mi_path(cat, aid, pn)
            try:
                if pn == "Reticle":
                    make_mi(path, emis, scalars={"Intensity": RETICLE[1]}, vectors={"Color": RETICLE[0]})
                elif role == "glass":
                    tint, opac, rough, glow = GLASS.get(aid, GLASS["*"])
                    make_mi(path, glass, scalars={"Opacity": opac, "Roughness": rough, "Glow": glow},
                            vectors={"Tint": tint})
                elif role == "emissive":
                    col, inten = EMISSIVE.get(aid, EMISSIVE["*"])
                    make_mi(path, emis, scalars={"Intensity": inten}, vectors={"Color": col or (1, 1, 1)},
                            textures={"EmissiveMap": tx["BC"]})
                elif role == "masked":
                    make_mi(path, masked, textures={"BaseColor": tx["BC"], "Normal": tx["N"], "ORM": tx["ORM"],
                                                    "Opacity": tx["Opacity"]},
                            vectors={"Tint": (1, 1, 1) if tx["BC"] else (0.2, 0.35, 0.1)})
                else:
                    has_mask = tx["M"] is not None
                    vec, sc = {}, {}
                    if has_mask and cat not in C.NO_COLLISION_CATEGORIES:
                        dflt = L.DEFAULT_TINT.get(aid)
                        names = variant_names(aid, e)
                        if dflt or names:
                            vec["PrimaryTint"] = variant_color(aid, e, dflt or names[0])
                        if aid in L.TINT_SURFACE:
                            sc["TintMetallic"], sc["TintRoughness"] = L.TINT_SURFACE[aid]
                    base = make_mi(path, pbr, scalars=sc, vectors=vec,
                                   textures={"BaseColor": tx["BC"], "Normal": tx["N"], "ORM": tx["ORM"],
                                             "Mask": tx["M"]},
                                   switches={"UseMask": has_mask})
                    if has_mask and base is not None and cat not in C.NO_COLLISION_CATEGORIES:
                        for vn in variant_names(aid, e):
                            make_mi("%s_%s" % (path, vn), base, vectors={"PrimaryTint": variant_color(aid, e, vn)},
                                    scalars=sc, clear=True)
                    if not tx["BC"]:
                        C.SUMMARY.miss("piece textures", "%s/%s" % (aid, pn))
                n += 1
            except Exception as ex:
                C.SUMMARY.note("instance for %s/%s failed: %s" % (aid, pn, ex))
    return n


# ---------------------------------------------------------------------------------------------
# Slot assignment
# ---------------------------------------------------------------------------------------------
def resolve_slot(slot, cat, aid, piece):
    s = C.strip_slot_suffix(slot)
    if s.startswith("MI_"):
        mi = C.load(tileable_path(s[3:]))
        if mi:
            return mi
        if s[3:] in FALLBACK_COLOR:
            return get_box_mi(s[3:], world=False)
    if s.startswith("M_"):
        rest = s[2:]
        mi = C.load("%s/%s/MI_%s" % (C.MI_ROOT, cat, rest))
        if mi:
            return mi
    mi = C.load(piece_mi_path(cat, aid, piece["Name"]))
    if mi:
        return mi
    role = C.piece_role(aid, piece)
    if role == "glass":
        return C.load("%s/Glass/MI_Glass_Clear" % C.MI_ROOT)
    if role == "emissive":
        return get_emissive_mi("Warm", 12)
    return C.load("%s/Special/MI_Fallback_Grey" % C.MI_ROOT)


def assign_mesh_materials(reg):
    n = 0
    for aid, e in sorted(reg.items()):
        cat = e["Category"]
        for piece in e["Pieces"]:
            sm = C.load(C.mesh_path(cat, aid, piece["Name"]))
            if not sm:
                continue
            try:
                mats = sm.get_editor_property("static_materials")
                changed = False
                for i, smat in enumerate(mats):
                    slot = str(smat.get_editor_property("material_slot_name"))
                    mi = resolve_slot(slot, cat, aid, piece)
                    if mi is not None and smat.get_editor_property("material_interface") != mi:
                        sm.set_material(i, mi)
                        changed = True
                if changed:
                    C.save_asset(sm)
                    n += 1
            except Exception as ex:
                C.SUMMARY.note("material assignment on %s/%s failed: %s" % (aid, piece["Name"], ex))
    C.SUMMARY.inc("meshes with materials (re)assigned", n)
    return n


def tint_override(cat, aid, piece_name, tint):
    """Per-placement paint variant (e.g. Container_20ft Red) or None."""
    if not tint:
        return None
    return C.load("%s_%s" % (piece_mi_path(cat, aid, piece_name), tint))
