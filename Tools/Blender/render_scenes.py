"""
Cinematic stills of the real maps: rebuilds a section of a map in Blender from the layout data
(Content/Python/airsoft_setup_lib/layouts.py, no `unreal` import) with the exported FBX assets and
baked 4K textures, then renders named camera shots with Cycles (AgX, depth of field, bloom).

    python Tools/Blender/render_scenes.py -- --list
    python Tools/Blender/render_scenes.py -- --shot velvet_street                 # 2560x1440 final
    python Tools/Blender/render_scenes.py -- --shot velvet_street --preview       # 640x360 framing check
    python Tools/Blender/render_scenes.py -- --shot armory --preview --try '[{"cam": [-3, 1, 1.6]}, {"lens": 35}]'
                                                                                  # camera variants, one build
    python Tools/Blender/render_scenes.py -- --topdown VelvetClub                 # plan check (ortho, top view)
    python Tools/Blender/render_scenes.py -- --sheet       # contact sheet, title poster, HUD version (PIL only)
    flags: --res WxH, --samples N, --threads N, --png-dir DIR (PNG masters, default Saved/Screens, git-ignored),
           --jpg-dir DIR (quality-90 JPGs, default Docs/Screens), --tmp-dir DIR (raw renders / previews),
           --no-post, --keep-blend
    Finals take roughly 5-15 min each on 4 CPU cores (adaptive sampling, OpenImageDenoise).

What it builds (same rules as levels.py / lighting.py / materials.py, so it matches the editor build):
    prop     FBX pieces imported once per asset and instanced (collection instances); paint tints,
             car paint gloss, fixture lights (lighting.FIXTURES), GunDisplayBay guns, hanging lamps
    box      procedural blocks with the tileable materials, world-projected UVs (TileMeters or the
             item's "tile"), paint tints, Emissive:<Colour> glow, mirror-like Puddle
    light    point / spot / rect lights (candela -> Blender watts, see LIGHT_SCALE)
    text     emissive sign text (Tools/Blender/club/fonts)
    fog      LocalFogVolume -> homogeneous ellipsoid volume
    target   AirsoftPracticeTarget -> SteelTarget asset; objective -> FlagPole_Objective + ring (per shot)
Skipped: blocker, start, sound, capture, camera.

Axes: layouts are Unreal (left-handed, +Y right, yaw turns +X toward +Y, metres). Blender = (x, -y, z),
yaw -> -yaw.  Material slots follow Tools/Blender/CONVENTIONS.md:
    M_<Id>_<Piece>  -> T_<Id>_<Piece>_BC/N/ORM/M.png next to the FBX (role mask -> paint tints)
    MI_<Material>   -> SourceAssets/Materials/<Material> (mesh UVs * 2/TileMeters)
    Glass / Emissive / Reticle / Leaves -> the editor's glass, emissive and masked rules
Missing textures are an error (no magenta renders).

Shots (SHOTS below) are named camera setups: map, camera and target in layout metres (Unreal axes),
focal length, f-stop / focus point, exposure, look, optional extra props (noted per shot) and an optional
first-person rig (gloves + gun at the game's ADS / hip placement from AirsoftCombatComponent).
Texture resolution is picked per asset from its distance to the camera (proxies from bakekit).
Look: AgX + a per-shot look, compositor bloom and slight lens dispersion, then a vignette and fine grain
in display space. Lights keep Unreal's units 1:1 (LIGHT_SCALE) and the per-shot exposure stands in for
auto exposure; the haze boxes stand in for the height fog / volumetric fog (values eyeballed).
These are offline path-traced stills of the real assets and layouts, not in-engine screenshots.
"""

import ast
import glob
import importlib.util
import json
import math
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "common"))

SOURCE_DIR = os.path.join(ROOT, "SourceAssets")
DATA_DIR = os.path.join(ROOT, "Content", "Airsoft", "Data")
LIB_DIR = os.path.join(ROOT, "Content", "Python", "airsoft_setup_lib")
FONT_DIR = os.path.join(HERE, "club", "fonts")
JPG_DIR = os.path.join(ROOT, "Docs", "Screens")
PNG_DIR = os.path.join(ROOT, "Saved", "Screens")      # git-ignored; PNG masters stay local
CATEGORIES = ("Weapons", "Attachments", "Gear", "Props", "Architecture")

try:  # bpy is only needed to build / render; the post steps (--sheet) run on plain Python + PIL
    import bpy  # noqa: I001
    from mathutils import Matrix, Vector

    import bakekit as bk
except ImportError:  # pragma: no cover
    bpy = None

# Unreal's low physical light scale (lighting.py: sun 5-10 lux, lamps a few cd, emissive ~10) is kept
# 1:1: Blender W/m^2 = lux, point W = cd*4pi, area W = cd*pi, emission strength = UE emissive.
# Exposure (stops, per shot) then plays the part of Unreal's auto exposure.
LIGHT_SCALE = 1.0

# --------------------------------------------------------------------------------------
# Data: layouts (plain Python), lighting / material tables (literal dicts read with ast)
# --------------------------------------------------------------------------------------


def load_layouts():
    spec = importlib.util.spec_from_file_location("airsoft_layouts", os.path.join(LIB_DIR, "layouts.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def literal_tables(path, names):
    """Top-level NAME = {literal} assignments of a module that imports `unreal` (not executed)."""
    out = {}
    for node in ast.parse(open(path, encoding="utf-8").read()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in names:
                out[node.targets[0].id] = ast.literal_eval(node.value)
    return out


L = load_layouts()
_LT = literal_tables(os.path.join(LIB_DIR, "lighting.py"), ("PRESETS", "FIXTURES"))
PRESETS, FIXTURES = _LT["PRESETS"], _LT["FIXTURES"]
_MT = literal_tables(os.path.join(LIB_DIR, "materials.py"), ("GLASS", "EMISSIVE", "RETICLE", "FALLBACK_COLOR"))
GLASS, EMISSIVE, RETICLE, FALLBACK_COLOR = _MT["GLASS"], _MT["EMISSIVE"], _MT["RETICLE"], _MT["FALLBACK_COLOR"]
MATS = json.load(open(os.path.join(DATA_DIR, "Materials.json")))["Materials"]

# Game-side constants (Source/AndrewsAirsoft): default attachments per gun (AirsoftWeaponData.cpp),
# gun skins (BuildSkins), team colours (AirsoftTypes.h), display / objective / target components.
WEAPON_DEFAULTS = {"M4": {"Optic": "RedDot", "Grip": "VerticalGrip"}, "SR25": {"Optic": "Scope4x", "Grip": "Bipod"},
                   "VSR": {"Optic": "ScopeLong"}, "VECTOR": {"Optic": "Holo"}, "MP7": {"Optic": "RedDot"},
                   "P90": {"Optic": "RedDot"}, "G18": {"Muzzle": "Compensator"}}
ATTACH_POINT = {"Optic": "Optic", "Muzzle": "MuzzleMount", "Grip": "Underbarrel", "Laser": "Side", "Mag": "MagWell"}
SKINS = {  # primary, secondary, metallic, roughness
    "Black": ((0.025, 0.026, 0.03), (0.03, 0.031, 0.034), 0.0, 0.55),
    "FDE": ((0.32, 0.24, 0.15), (0.03, 0.031, 0.034), 0.0, 0.6),
    "OD": ((0.09, 0.11, 0.06), (0.03, 0.031, 0.034), 0.0, 0.6),
    "Gunmetal": ((0.09, 0.1, 0.12), (0.025, 0.026, 0.03), 0.35, 0.45),
}
TEAM = {"Blue": (0.08, 0.30, 1.0), "Red": (1.0, 0.09, 0.07), "None": (1.0, 0.55, 0.05)}
DISPLAY_ACCENT = (0.85, 0.6, 0.25)
UNITLESS_PER_CD = 625.0   # UE unitless intensity -> candela (lighting.py: objective glow 2500 = ~4 cd)


def srgb_to_lin(c):
    return tuple((v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def kelvin_rgb(t):
    """Approximate black-body colour (linear sRGB, max channel 1)."""
    t = max(1000.0, min(40000.0, t)) / 100.0
    r = 255.0 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * (t - 60) ** -0.0755148492
    b = 255.0 if t >= 66 else (0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    c = srgb_to_lin(tuple(max(0.0, min(255.0, v)) / 255.0 for v in (r, g, b)))
    m = max(c)
    return tuple(v / m for v in c)


def white_balanced(temp, white):
    a, w = kelvin_rgb(temp), kelvin_rgb(white)
    c = tuple(x / y for x, y in zip(a, w))
    m = max(c)
    return tuple(v / m for v in c)


def colour(c):
    if isinstance(c, (tuple, list)):
        return tuple(float(v) for v in c[:3])
    return L.EMISSIVE_COLORS.get(c, (1.0, 1.0, 1.0))


# --------------------------------------------------------------------------------------
# Asset registry (Content/Airsoft/Data/*.json merged with what is on disk)
# --------------------------------------------------------------------------------------


def load_registry():
    reg = {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        name = os.path.basename(path)
        cat = next((c for c in CATEGORIES if name.startswith(c)), None)
        if not cat:
            continue
        for aid, a in (json.load(open(path)).get("Assets") or {}).items():
            e = dict(a)
            e["Category"] = cat
            e["Pieces"] = [dict(p) for p in a.get("Pieces", [])]
            reg[aid] = e
    for cat in CATEGORIES:
        for d in sorted(glob.glob(os.path.join(SOURCE_DIR, cat, "*"))):
            aid = os.path.basename(d)
            fbxs = sorted(glob.glob(os.path.join(d, f"SM_{aid}_*.fbx")))
            if not fbxs:
                continue
            e = reg.setdefault(aid, {"Category": cat, "Pieces": []})
            known = {p["Name"] for p in e["Pieces"]}
            for f in fbxs:
                pn = os.path.basename(f)[len(f"SM_{aid}_") : -4]
                if pn not in known:
                    e["Pieces"].append({"Name": pn, "Kind": "Static", "Slots": []})
    for aid, e in reg.items():
        e["Dir"] = os.path.join(SOURCE_DIR, e["Category"], aid)
        e.setdefault("Points", {})
    return reg


REG = load_registry()
JSON_ASSETS = {aid: {"_Category": e["Category"], "Bounds": e.get("Bounds"), "Points": e.get("Points", {})}
               for aid, e in REG.items()}


def piece_role(aid, piece):
    """common.piece_role: 'glass', 'emissive', 'masked', 'reticle' or 'opaque'."""
    pn, kind = piece.get("Name", ""), piece.get("Kind", "")
    if pn == "Reticle":
        return "reticle"
    if kind == "Glass" or pn == "Glass" or pn.endswith("Lamp"):
        return "glass"
    if kind == "Emissive" or pn in ("Emissive", "LED"):
        return "emissive"
    if piece.get("BlendMode") == "Masked" or pn in ("Leaves", "Net"):
        return "masked"
    return "opaque"


def strip_slot_suffix(name):
    n = re.sub(r"([._]\d{3})+$", "", name)
    return n[:-2] if n.endswith("_R") else n


def point_of(aid, name):
    return L.asset_point(aid, name, JSON_ASSETS)


def tint_for(aid, tint):
    """(PrimaryTint, TintMetallic, TintRoughness) the editor build gives this placement (materials.py)."""
    e = REG.get(aid, {})
    variants = dict(e.get("TintVariants") or {})
    names = list(L.TINT_VARIANTS.get(aid, [])) + [k for k in variants if k not in L.TINT_VARIANTS.get(aid, [])]
    pick = tint if tint in names else (L.DEFAULT_TINT.get(aid) or (names[0] if names else None))
    col = (1.0, 1.0, 1.0)
    if pick:
        col = tuple(variants[pick][:3]) if pick in variants else L.TINTS.get(pick, (0.5, 0.5, 0.5))
    met, rough = L.TINT_SURFACE.get(aid, (0.0, 0.55))
    return col, met, rough


# --------------------------------------------------------------------------------------
# Coordinates
# --------------------------------------------------------------------------------------


def bl(p):
    """Unreal metres -> Blender metres."""
    return Vector((float(p[0]), -float(p[1]), float(p[2])))


def scale3(sc):
    if sc is None:
        return (1.0, 1.0, 1.0)
    if isinstance(sc, (int, float)):
        return (float(sc),) * 3
    return tuple(float(v) for v in sc)


def ue_world(p, yaw, sc, local_cm):
    """levels._world: asset-space point (cm) of a placement -> Unreal world metres."""
    lx, ly = L.rot2(local_cm[0] * sc[0], local_cm[1] * sc[1], yaw)
    return (p[0] + lx / 100.0, p[1] + ly / 100.0, p[2] + local_cm[2] * sc[2] / 100.0)


def ue_basis(pitch, yaw):
    """Unreal rotator -> Blender (forward, right, up) unit vectors."""
    p, y = math.radians(pitch), math.radians(yaw)
    fwd = (math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p))
    right = (-math.sin(y), math.cos(y), 0.0)
    up = (-math.sin(p) * math.cos(y), -math.sin(p) * math.sin(y), math.cos(p))
    return bl(fwd), bl(right), bl(up)


def light_matrix(pitch, yaw):
    """Blender light (emits along -Z, area width on X, height on Y) aimed like an Unreal light."""
    f, r, u = ue_basis(pitch, yaw)
    return Matrix((r, u, -f)).transposed().to_4x4()


# --------------------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------------------

_mat_cache = {}


def tex(nb, path, cs, res, key="X", uv=None):
    """Image node on a <= res proxy of path (bakekit proxies; res >= 4096 loads the original)."""
    if res and res < 4096:
        bk.ensure_proxies({"BC" if key == "BC" else key: path}, res)
        path = bk.proxy_path(path, res)
    n = nb.node("ShaderNodeTexImage", image=bk._load(path, cs))
    if uv is not None:
        nb.nt.links.new(uv, n.inputs["Vector"])
    return n


def vmul(nb, a, b):
    n = nb.node("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY", clamp_factor=True)
    bk.sid(n.inputs, "Factor_Float").default_value = 1.0
    nb._in(bk.sid(n.inputs, "A_Color"), a if isinstance(a, bpy.types.NodeSocket) else (*a, 1.0))
    nb._in(bk.sid(n.inputs, "B_Color"), b if isinstance(b, bpy.types.NodeSocket) else (*b, 1.0))
    return bk.sid(n.outputs, "Result_Color")


def dx_normal(nb, ntex, strength=1.0):
    nx, ny, nz = nb.separate(ntex.outputs["Color"])
    nm = nb.node("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = strength
    nb.nt.links.new(nb.combine(nx, nb.sub(1.0, ny), nz), nm.inputs["Color"])
    return nm.outputs["Normal"]


def fresh(name):
    """New node material that never replaces an existing one (bakekit.fresh_material deletes a namesake,
    which would free materials still cached / assigned elsewhere); Blender suffixes duplicates."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    m.node_tree.nodes.new("ShaderNodeOutputMaterial").target = "ALL"
    return m


def new_mat(name):
    m = fresh(name)
    nb = bk.NB(m.node_tree)
    out = next(n for n in m.node_tree.nodes if n.type == "OUTPUT_MATERIAL")
    return m, nb, out


def inst_attr(nb, name, kind="Color"):
    a = nb.node("ShaderNodeAttribute", attribute_type="INSTANCER", attribute_name=name)
    return a.outputs[kind]


def emission_mat(name, rgb, strength, tex_path=None, res=1024):
    key = ("emis", name, tuple(rgb), strength, tex_path, res)
    if key in _mat_cache:
        return _mat_cache[key]
    m, nb, out = new_mat(name)
    em = nb.node("ShaderNodeEmission")
    col = tuple(rgb)
    if tex_path:
        t = tex(nb, tex_path, "sRGB", res, "BC")
        nb.nt.links.new(vmul(nb, t.outputs["Color"], col), em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = (*col, 1.0)
    em.inputs["Strength"].default_value = strength * LIGHT_SCALE
    m.node_tree.links.new(em.outputs[0], out.inputs["Surface"])
    _mat_cache[key] = m
    return m


def glass_mat(aid):
    """materials.build_glass: tinted translucent glass with Fresnel opacity and optional glow."""
    key = ("glass", aid)
    if key in _mat_cache:
        return _mat_cache[key]
    tint, opac, rough, glow = GLASS.get(aid, GLASS["*"])
    m, nb, out = new_mat(f"Glass_{aid}")
    p = nb.node("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = (*tint, 1.0)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Specular IOR Level"].default_value = 0.6
    lw = nb.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    fres = nb.add(0.04, nb.mul(0.96, nb.math("POWER", lw.outputs["Facing"], 4.0)))
    opacity = nb.add(opac, nb.mul(fres, 0.5), clamp=True)
    mix = nb.node("ShaderNodeMixShader")
    nb.nt.links.new(opacity, mix.inputs[0])
    nb.nt.links.new(nb.node("ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
    nb.nt.links.new(p.outputs[0], mix.inputs[2])
    shader = mix.outputs[0]
    if glow > 0:
        em = nb.node("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*tint, 1.0)
        em.inputs["Strength"].default_value = glow * LIGHT_SCALE
        add = nb.node("ShaderNodeAddShader")
        nb.nt.links.new(shader, add.inputs[0])
        nb.nt.links.new(em.outputs[0], add.inputs[1])
        shader = add.outputs[0]
    m.node_tree.links.new(shader, out.inputs["Surface"])
    _mat_cache[key] = m
    return m


def texture_set(d, aid, piece):
    base = os.path.join(d, f"T_{aid}_{piece}")
    return {k: base + f"_{k}.png" for k in ("BC", "N", "ORM", "M", "Opacity")}


def baked_mat(aid, piece, d, res):
    """M_AirsoftPBR: BC * lerp(1, tint, role mask), TintMetallic / TintRoughness on the masked areas.
    Tints come from the placement (collection-instance custom props tP / tS / tA / tMet / tRough)."""
    key = ("baked", aid, piece, res)
    if key in _mat_cache:
        return _mat_cache[key]
    paths = texture_set(d, aid, piece)
    missing = [paths[k] for k in ("BC", "N", "ORM") if not os.path.exists(paths[k])]
    if missing:
        raise RuntimeError(f"{aid}.{piece}: missing textures {missing}")
    m, nb, out = new_mat(f"PBR_{aid}_{piece}")
    bsdf = nb.node("ShaderNodeBsdfPrincipled")
    m.node_tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    uv = nb.node("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    bc = tex(nb, paths["BC"], "sRGB", res, "BC", uv)
    orm = tex(nb, paths["ORM"], "Non-Color", res, "ORM", uv)
    nrm = tex(nb, paths["N"], "Non-Color", res, "N", uv)
    ao, rough, metal = nb.separate(orm.outputs["Color"])
    col = bc.outputs["Color"]
    if os.path.exists(paths["M"]):
        mt = tex(nb, paths["M"], "Non-Color", min(res, 1024), "M", uv)
        mr, mg, mb = nb.separate(mt.outputs["Color"])
        for msk, attr in ((mr, "tP"), (mg, "tS"), (mb, "tA")):
            col = nb.mixc(msk, col, vmul(nb, col, inst_attr(nb, attr)))
        msum = nb.add(nb.add(mr, mg), mb, clamp=True)
        metal = nb.lerp(msum, metal, inst_attr(nb, "tMet", "Fac"))
        rdet = nb.add(inst_attr(nb, "tRough", "Fac"), nb.mul(nb.sub(rough, 0.5), 0.35))
        rough = nb.lerp(msum, rough, rdet)
    nb.nt.links.new(col, bsdf.inputs["Base Color"])
    nb.nt.links.new(rough, bsdf.inputs["Roughness"])
    nb.nt.links.new(metal, bsdf.inputs["Metallic"])
    nb.nt.links.new(dx_normal(nb, nrm), bsdf.inputs["Normal"])
    if aid == "Gloves":  # build_gloves.textured_material: fabric sheen
        bsdf.inputs["Sheen Weight"].default_value = 0.25
        bsdf.inputs["Sheen Roughness"].default_value = 0.4
    _mat_cache[key] = m
    return m


def masked_mat(name, paths, res, uv_scale=1.0, tint=(1.0, 1.0, 1.0)):
    """M_Masked: alpha-clipped two-sided foliage / netting with a little translucency."""
    key = ("masked", name, res, uv_scale)
    if key in _mat_cache:
        return _mat_cache[key]
    m, nb, out = new_mat(name)
    uv = nb.node("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    if uv_scale != 1.0:
        uv = nb.vscale(uv, (uv_scale, uv_scale, uv_scale))
    bc = tex(nb, paths["BC"], "sRGB", res, "BC", uv)
    orm = tex(nb, paths["ORM"], "Non-Color", res, "ORM", uv)
    nrm = tex(nb, paths["N"], "Non-Color", res, "N", uv)
    opa = tex(nb, paths["Opacity"], "Non-Color", res, "Opacity", uv)
    base = vmul(nb, bc.outputs["Color"], tint)
    bsdf = nb.node("ShaderNodeBsdfPrincipled")
    nb.nt.links.new(base, bsdf.inputs["Base Color"])
    nb.nt.links.new(nb.separate(orm.outputs["Color"])[1], bsdf.inputs["Roughness"])
    nb.nt.links.new(dx_normal(nb, nrm), bsdf.inputs["Normal"])
    tr = nb.node("ShaderNodeBsdfTranslucent")
    nb.nt.links.new(vmul(nb, base, (0.55, 0.7, 0.25)), tr.inputs["Color"])
    leaf = nb.node("ShaderNodeMixShader")
    leaf.inputs[0].default_value = 0.25
    nb.nt.links.new(bsdf.outputs[0], leaf.inputs[1])
    nb.nt.links.new(tr.outputs[0], leaf.inputs[2])
    cut = nb.math("GREATER_THAN", nb.separate(opa.outputs["Color"])[0], 0.4)
    mix = nb.node("ShaderNodeMixShader")
    nb.nt.links.new(cut, mix.inputs[0])
    nb.nt.links.new(nb.node("ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
    nb.nt.links.new(leaf.outputs[0], mix.inputs[2])
    m.node_tree.links.new(mix.outputs[0], out.inputs["Surface"])
    _mat_cache[key] = m
    return m


def tile_paths(mid):
    d = os.path.join(SOURCE_DIR, "Materials", mid)
    return {k: os.path.join(d, f"T_{mid}_{k}.png") for k in ("BC", "N", "ORM", "Opacity")}


def tile_mat(mid, tint=None, uv_scale=1.0, res=2048, puddle=False):
    """M_Tileable on mesh UVs (architecture: uv * 2/TileMeters) or box UVs already in tile units.
    Paint tints use get_box_mi's rule (tint * 1.8, capped at 4); macro colour variation 0.3."""
    key = ("tile", mid, tint, round(uv_scale, 5), res, puddle)
    if key in _mat_cache:
        return _mat_cache[key]
    paths = tile_paths(mid)
    if mid == "Netting" or MATS.get(mid, {}).get("BlendMode") == "Masked":
        m = masked_mat(f"Tile_{mid}", paths, res, uv_scale)
        _mat_cache[key] = m
        return m
    if not os.path.exists(paths["BC"]):
        if mid not in FALLBACK_COLOR:
            raise RuntimeError(f"tileable {mid}: no textures in {os.path.dirname(paths['BC'])}")
        m = bk.plain_material(f"Tile_{mid}_flat", FALLBACK_COLOR[mid], 0.6, 0.0)
        _mat_cache[key] = m
        return m
    name = f"Tile_{mid}" + (f"_{tint}" if tint else "") + ("_Puddle" if puddle else "") + f"_{uv_scale:g}_{res}"
    m, nb, out = new_mat(name)
    bsdf = nb.node("ShaderNodeBsdfPrincipled")
    m.node_tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    uv = nb.node("ShaderNodeUVMap", uv_map="UVMap").outputs["UV"]
    if uv_scale != 1.0:
        uv = nb.vscale(uv, (uv_scale, uv_scale, uv_scale))
    bc = tex(nb, paths["BC"], "sRGB", res, "BC", uv)
    orm = tex(nb, paths["ORM"], "Non-Color", res, "ORM", uv)
    nrm = tex(nb, paths["N"], "Non-Color", res, "N", uv)
    col = bc.outputs["Color"]
    if puddle:   # MI_Puddle: AsphaltWet, roughness * 0.05, normal 0.15, tint (0.45, 0.45, 0.5)
        col = vmul(nb, col, (0.45, 0.45, 0.5))
        rough_scale, nstr = 0.05, 0.15
    else:
        macro = tex(nb, paths["BC"], "sRGB", min(res, 1024), "BC", nb.vscale(uv, (0.071, 0.071, 0.071)))
        dot = nb.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
        nb.nt.links.new(macro.outputs["Color"], dot.inputs[0])
        dot.inputs[1].default_value = (0.333, 0.333, 0.333)
        var = nb.lerp(0.3, 1.0, nb.mul(dot.outputs["Value"], 2.2))
        col = vmul(nb, col, nb.combine(var, var, var))
        if tint:
            col = vmul(nb, col, tuple(min(4.0, c * 1.8) for c in L.TINTS.get(tint, (0.5, 0.5, 0.5))))
        rough_scale, nstr = 1.0, 1.0
    _ao, rough, metal = nb.separate(orm.outputs["Color"])
    nb.nt.links.new(col, bsdf.inputs["Base Color"])
    nb.nt.links.new(nb.mul(rough, rough_scale, clamp=True), bsdf.inputs["Roughness"])
    nb.nt.links.new(metal, bsdf.inputs["Metallic"])
    nb.nt.links.new(dx_normal(nb, nrm, nstr), bsdf.inputs["Normal"])
    _mat_cache[key] = m
    return m


def box_material(mat, tint=None, glow=20.0, res=2048):
    if mat.startswith("Emissive:"):
        c = mat.split(":", 1)[1]
        return emission_mat(f"Emis_{c}_{glow:g}", colour(c), glow), True
    if mat == "Puddle":
        return tile_mat("AsphaltWet", res=res, puddle=True), False
    if mat == "Foliage":
        return tile_mat("Grass", tint=None, res=res), False
    if mat == "Glass":
        return glass_mat("*"), False
    return tile_mat(mat, tint=tint, res=res), False


def volume_mat(name, rgb, density, anisotropy=0.2):
    m = fresh(name)
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Color"].default_value = (*rgb, 1.0)
    v.inputs["Density"].default_value = density
    v.inputs["Anisotropy"].default_value = anisotropy
    nt.links.new(v.outputs[0], out.inputs["Volume"])
    return m


# --------------------------------------------------------------------------------------
# Asset library: each asset imported once, placed with collection instances
# --------------------------------------------------------------------------------------


class Library:
    def __init__(self, res_for):
        self.res_for = res_for            # aid -> texture resolution
        self.pieces = {}                  # (aid, piece) -> [objects]
        self.colls = {}
        self.root = bpy.data.collections.new("LIB")   # never linked to the scene

    def _coll(self, name):
        c = bpy.data.collections.new(name)
        self.root.children.link(c)
        return c

    def _import(self, path):
        before = set(bpy.data.objects)
        mats_before = set(bpy.data.materials)
        bpy.ops.import_scene.fbx(filepath=path, axis_forward="X", axis_up="Z")
        new = [o for o in bpy.data.objects if o not in before]
        obs = []
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            if o.type != "MESH":
                bpy.data.objects.remove(o)
            else:
                obs.append(o)
        return obs, [m for m in bpy.data.materials if m not in mats_before]

    def piece_objects(self, aid, piece):
        k = (aid, piece["Name"])
        if k in self.pieces:
            return self.pieces[k]
        e = REG[aid]
        pn = piece["Name"]
        f = os.path.join(e["Dir"], f"SM_{aid}_{pn}.fbx")
        if not os.path.exists(f):
            self.pieces[k] = []
            return []
        obs, imported_mats = self._import(f)
        res = self.res_for(aid)
        role = piece_role(aid, piece)
        for o in obs:
            o.name = f"{aid}_{pn}"
            if role == "glass":
                mats = [glass_mat(aid)]
            elif role == "reticle":
                col, inten = RETICLE
                mats = [emission_mat("Reticle", col, inten)]
            elif role == "emissive":
                col, inten = EMISSIVE.get(aid, EMISSIVE["*"])
                mats = [emission_mat(f"Emis_{aid}_{pn}", col or (1.0, 1.0, 1.0), inten,
                                     texture_set(e["Dir"], aid, pn)["BC"], min(res, 1024))]
            elif role == "masked":
                slot = strip_slot_suffix(o.data.materials[0].name) if o.data.materials else ""
                if slot.startswith("MI_"):
                    mid = slot[3:]
                    mats = [tile_mat(mid, uv_scale=2.0 / float(MATS.get(mid, {}).get("TileMeters", 2.0)))]
                else:
                    mats = [masked_mat(f"Masked_{aid}_{pn}", texture_set(e["Dir"], aid, pn), res)]
            else:
                mats = []
                for sm in o.data.materials:
                    slot = strip_slot_suffix(sm.name) if sm else ""
                    if slot.startswith("MI_"):
                        mid = slot[3:]
                        tm = float(MATS.get(mid, {}).get("TileMeters", 2.0))
                        mats.append(tile_mat(mid, uv_scale=2.0 / tm, res=min(2048, max(1024, res))))
                    else:
                        mats.append(baked_mat(aid, pn, e["Dir"], res))
                if not mats:
                    mats = [baked_mat(aid, pn, e["Dir"], res)]
            if len(mats) == 1 and len(o.data.materials) != 1:
                o.data.materials.clear()
                o.data.materials.append(mats[0])
                for p in o.data.polygons:
                    p.material_index = 0
            else:
                for i, m in enumerate(mats):
                    o.data.materials[i] = m
            if role in ("glass", "emissive", "reticle"):
                o.visible_shadow = False      # translucent / unlit parts never block their own light
            if role == "reticle":             # unlit in Unreal: seen, but lights nothing (no red glow in the tube)
                o.visible_diffuse = o.visible_glossy = o.visible_volume_scatter = False
        for m in imported_mats:
            if m.users == 0:
                bpy.data.materials.remove(m)
        self.pieces[k] = obs
        return obs

    def asset(self, aid, pieces=None):
        """Collection holding an asset's pieces at the asset origin (None if nothing on disk)."""
        key = (aid, tuple(pieces) if pieces else None)
        if key in self.colls:
            return self.colls[key]
        coll = None
        if aid in REG:
            obs = []
            for p in REG[aid]["Pieces"]:
                if pieces and p["Name"] not in pieces:
                    continue
                obs += self.piece_objects(aid, p)
            if obs:
                coll = self._coll(f"A_{aid}" + ("_" + "_".join(pieces) if pieces else ""))
                for o in obs:
                    coll.objects.link(o)
        self.colls[key] = coll
        return coll

    def gun(self, gid, fit=None):
        """Gun with attachments at their mount points (UAirsoftGunVisual::Build); fit=None -> defaults."""
        fit = dict(WEAPON_DEFAULTS.get(gid, {}) if fit is None else fit)
        key = ("gun", gid, tuple(sorted(fit.items())))
        if key in self.colls:
            return self.colls[key]
        coll = self._coll(f"G_{gid}_" + "_".join(v for _, v in sorted(fit.items())))
        pts = REG[gid].get("Points", {})
        custom_mag = fit.get("Mag") in ("ExtMag", "DrumMag")
        for p in REG[gid]["Pieces"]:
            if p["Name"] == "Mag" and custom_mag:
                continue
            for o in self.piece_objects(gid, p):
                coll.objects.link(o)
        for slot, aid in fit.items():
            mount = pts.get(ATTACH_POINT[slot]) or (pts.get("Underbarrel") if slot == "Laser" else None)
            if not mount or aid not in REG:
                continue
            for p in REG[aid]["Pieces"]:
                for o in self.piece_objects(aid, p):
                    c = o.copy()          # shares mesh data; own offset per gun
                    c.location = Vector(o.location) + Vector((mount[0] / 100.0, -mount[1] / 100.0, mount[2] / 100.0))
                    coll.objects.link(c)
        self.colls[key] = coll
        return coll


# --------------------------------------------------------------------------------------
# Scene builder
# --------------------------------------------------------------------------------------

_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3))


class Builder:
    def __init__(self, shot, m, opts):
        self.shot, self.map, self.opts = shot, m, opts
        self.scn = bpy.context.scene
        self.coll = bpy.data.collections.new("Map")
        self.scn.collection.children.link(self.coll)
        self.cam_pos = shot.get("cam", (0, 0, 2)) if shot else None
        self.lib = Library(self.res_for)
        self.boxes = {}
        self.dist = {}
        self.stats = {"props": 0, "boxes": 0, "lights": 0, "texts": 0}
        self.rests = []
        self.cull = shot.get("cull") if shot else None

    # ---- texture budget: resolution by distance from the camera ---------------------------
    def plan_resolutions(self, items, extra=()):
        if self.cam_pos is None:
            return
        cx, cy, cz = self.cam_pos
        for it in list(items) + list(extra):
            aid = it.get("id") or ("SteelTarget" if it["t"] == "target" else None)
            gid = it.get("display") or (it["id"] if it["t"] == "gun" else None)
            if it["t"] == "gun":
                for a in (it.get("fit") or {}).values():
                    px, py, pz = it["p"]
                    self.dist[a] = min(self.dist.get(a, 1e9), math.dist((px, py, pz), (cx, cy, cz)))
            px, py, pz = it["p"]
            d = math.sqrt((px - cx) ** 2 + (py - cy) ** 2 + (pz - cz) ** 2)
            if aid:
                bmin, bmax = L.asset_bounds(aid, JSON_ASSETS)
                r = max(bmax[i] - bmin[i] for i in range(3)) / 200.0 * max(scale3(it.get("scale")))
                self.dist[aid] = min(self.dist.get(aid, 1e9), max(0.0, d - r))
            if gid:
                self.dist[gid] = min(self.dist.get(gid, 1e9), d)
                for a in WEAPON_DEFAULTS.get(gid, {}).values():
                    self.dist[a] = min(self.dist.get(a, 1e9), d)

    def res_for(self, aid):
        if self.opts.get("preview"):
            return 512
        d = self.dist.get(aid, 50.0)
        if d < 1.2:
            return 4096
        if d < 5.0:
            return 2048
        if d < 25.0:
            return 1024
        return 512

    def tile_res(self):
        return 1024 if self.opts.get("preview") else self.shot.get("tile_res", 2048) if self.shot else 1024

    def culled(self, p):
        if not self.cull or self.cam_pos is None:
            return False
        return math.dist(p[:2], self.cam_pos[:2]) > self.cull

    # ---- placements --------------------------------------------------------------------
    def instance(self, coll, name, loc_ue, yaw, sc=(1, 1, 1), tint=None, tint_aid=None, skin=None, accent=None):
        e = bpy.data.objects.new(name, None)
        e.instance_type = "COLLECTION"
        e.instance_collection = coll
        e.location = bl(loc_ue)
        e.rotation_euler = (0.0, 0.0, math.radians(-yaw))
        e.scale = sc
        if skin:
            p, s, met, rough = SKINS[skin]
            e["tP"], e["tS"], e["tA"], e["tMet"], e["tRough"] = p, s, accent or DISPLAY_ACCENT, met, rough
        else:
            col, met, rough = tint_for(tint_aid, tint) if tint_aid else ((1.0, 1.0, 1.0), 0.0, 0.55)
            e["tP"], e["tS"], e["tA"], e["tMet"], e["tRough"] = col, (1.0, 1.0, 1.0), (1.0, 0.45, 0.08), met, rough
        self.coll.objects.link(e)
        return e

    def placed(self, coll, name, it, skin=None, accent=None, tint_aid=None):
        """Shot-only extra with a full rotator: it["rot"] = (pitch, yaw, roll) degrees (Unreal pitch/yaw,
        roll about the asset's own +X)."""
        pitch, yaw, roll = it.get("rot", (0.0, it.get("yaw", 0.0), 0.0))
        e = self.instance(coll, name, it["p"], 0.0, scale3(it.get("scale")), it.get("tint"), tint_aid, skin, accent)
        e.matrix_world = Matrix.Translation(bl(it["p"])) @ Matrix.Rotation(math.radians(-yaw), 4, "Z") @ \
            Matrix.Rotation(math.radians(-pitch), 4, "Y") @ Matrix.Rotation(math.radians(roll), 4, "X") @ \
            Matrix.Diagonal((*scale3(it.get("scale")), 1.0))
        return e

    def extra_gun(self, it):
        coll = self.lib.gun(it["id"], it.get("fit"))
        e = self.placed(coll, f"Gun_{it['id']}", it, skin=it.get("skin", "Black"),
                        accent=TEAM.get(it.get("team"), it.get("accent", DISPLAY_ACCENT)))
        if it.get("rest"):
            self.rests.append((e, coll))

    def settle(self):
        """Drop shot extras flagged "rest" onto whatever is under them (counter, bench, case foam):
        lowest point of the rotated asset on the first surface hit by a ray cast down through its footprint."""
        if not self.rests:
            return
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        for e, coll in self.rests:
            R = e.matrix_world.to_3x3().to_4x4()
            pts = [R @ (o.matrix_basis @ Vector(c)) for o in coll.all_objects if o.type == "MESH" for c in o.bound_box]
            lo = min(p.z for p in pts)
            xs, ys = [p.x for p in pts], [p.y for p in pts]
            base = e.matrix_world.translation.copy()
            hits = []
            e.hide_set(True)
            e.hide_render = True
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            for fx in (0.15, 0.5, 0.85):
                for fy in (0.3, 0.7):
                    ox = base.x + min(xs) + (max(xs) - min(xs)) * fx
                    oy = base.y + min(ys) + (max(ys) - min(ys)) * fy
                    ok, loc, *_ = bpy.context.scene.ray_cast(dg, Vector((ox, oy, base.z + 0.6)), Vector((0, 0, -1)), distance=2.0)
                    if ok:
                        hits.append(loc.z)
            e.hide_set(False)
            e.hide_render = False
            if hits:
                e.matrix_world.translation.z = max(hits) - lo + 0.002
                print(f"  {e.name} rests at z={e.matrix_world.translation.z:.3f} (surface {max(hits):.3f})", flush=True)

    def prop(self, it):
        aid = it["id"]
        if self.culled(it["p"]):
            return
        if "rot" in it:   # shot-only extra
            coll = self.lib.asset(aid, it.get("pieces"))
            if coll is not None:
                self.placed(coll, aid, it, tint_aid=aid)
            return
        p = it["p"]
        if "hang" in it:
            mount = point_of(aid, "CeilingMount")
            mz = mount[2] if mount else L.asset_bounds(aid, JSON_ASSETS)[1][2]
            p = (p[0], p[1], it["hang"] - mz / 100.0)
        sc = scale3(it.get("scale"))
        yaw = it.get("yaw", 0.0)
        coll = self.lib.asset(aid, it.get("pieces"))
        if coll is None:
            self.fallback(aid, p, yaw, sc, it.get("tint"))
        else:
            self.instance(coll, aid, p, yaw, sc, it.get("tint"), aid)
        self.stats["props"] += 1
        if it.get("display"):
            self.display(it["display"], p, yaw, sc)
        if it.get("light"):
            self.fixture(aid, dict(it, p=p))

    def fallback(self, aid, p, yaw, sc, tint):
        bmin, bmax = L.asset_bounds(aid, JSON_ASSETS)
        main = L.KNOWN_ASSETS.get(aid, {}).get("fb", "box:Concrete").partition(":")[2] or "Concrete"
        for part in L.fallback_parts(aid, bmin, bmax):
            mn, mx = part["min"], part["max"]
            c = ue_world(p, yaw, sc, [(mn[i] + mx[i]) / 2.0 for i in range(3)])
            s = [(mx[i] - mn[i]) * sc[i] / 100.0 for i in range(3)]
            mat = part["mat"]
            self.box({"p": c, "s": s, "yaw": yaw, "mat": mat, "tint": tint if mat == main else None,
                      "cast": not mat.startswith("Emissive:")})
        print(f"  fallback shapes for {aid} (no FBX on disk)", flush=True)

    def display(self, gid, bay_p, bay_yaw, sc):
        """AirsoftArmoryDisplay at the bay's GunMount: gun side-on (yaw +90), centred on its muzzle/stock span,
        Factory Black skin with a brass accent, default attachments, and the display's key spot light."""
        gm = point_of("GunDisplayBay", "GunMount") or (-3.0, 0.0, 61.5)
        d = ue_world(bay_p, bay_yaw, sc, gm)
        mx = (REG[gid].get("Points", {}).get("Muzzle") or [50.0])[0]
        length = mx + 30.0
        rel = (0.0, -(mx - length * 0.5), -6.0)
        gx, gy = L.rot2(rel[0], rel[1], bay_yaw)
        loc = (d[0] + gx / 100.0, d[1] + gy / 100.0, d[2] + rel[2] / 100.0)
        self.instance(self.lib.gun(gid), f"Display_{gid}", loc, bay_yaw + 90.0, skin="Black", accent=DISPLAY_ACCENT)
        kx, ky = L.rot2(90.0, 0.0, bay_yaw)
        self.add_light("spot", (d[0] + kx / 100.0, d[1] + ky / 100.0, d[2] + 0.7), -38.0, bay_yaw + 180.0,
                       (1.0, 0.86, 0.68), 2400.0 / UNITLESS_PER_CD, shadows=True, cone=(18, 38), src=2.0,
                       name=f"DisplayKey_{gid}")

    def fixture(self, aid, it):
        fx = dict(FIXTURES.get(aid, {}))
        if not fx:
            return
        if isinstance(it.get("light"), dict):
            fx.update(it["light"])
        sc = scale3(it.get("scale"))
        pt = point_of(aid, fx.get("point", "Light"))
        if pt is None:
            mn, mx = L.asset_bounds(aid, JSON_ASSETS)
            pt = ((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, mx[2] * 0.85)
        loc = ue_world(it["p"], it.get("yaw", 0.0), sc, pt)
        yaw = it.get("yaw", 0.0) + fx.get("yaw_off", 0.0)
        self.add_light(fx["kind"], loc, fx.get("pitch", 0.0), yaw, colour(fx.get("color", "Warm")), fx.get("cd", 5.0),
                       shadows=fx.get("shadows", False), cone=fx.get("cone"), w=fx.get("w", 100.0) * sc[1],
                       h=fx.get("h", 50.0) * sc[2], src=fx.get("src"), name=f"Fixture_{aid}")

    def add_light(self, kind, loc, pitch, yaw, rgb, cd, shadows=False, cone=None, w=None, h=None, src=None,
                  name="Light"):
        """lighting.spawn_light in Blender units: point/spot W = cd*4pi, rect W = cd*pi (LIGHT_SCALE)."""
        mult = self.shot.get("light_mult", 1.0) if self.shot else 1.0
        if kind == "rect":
            ld = bpy.data.lights.new(name, "AREA")
            ld.shape = "RECTANGLE"
            ld.size = max(0.01, (w or 100.0) / 100.0)
            ld.size_y = max(0.01, (h or 50.0) / 100.0)
            ld.energy = cd * math.pi * LIGHT_SCALE * mult
            ld.spread = math.radians(140.0)          # barn doors at 70 degrees
        else:
            ld = bpy.data.lights.new(name, "SPOT" if kind == "spot" else "POINT")
            ld.energy = cd * 4.0 * math.pi * LIGHT_SCALE * mult
            ld.shadow_soft_size = (src if src else 4.0) / 100.0
            if kind == "spot":
                inner, outer = cone or (30.0, 44.0)
                ld.spot_size = math.radians(min(179.0, 2.0 * outer))
                ld.spot_blend = max(0.0, min(1.0, 1.0 - inner / max(outer, 0.1)))
        ld.color = rgb
        ld.use_shadow = bool(shadows)
        o = bpy.data.objects.new(name, ld)
        o.matrix_world = Matrix.Translation(bl(loc)) @ light_matrix(pitch, yaw)
        self.coll.objects.link(o)
        self.stats["lights"] += 1
        return o

    def item_light(self, it):
        if self.culled(it["p"]):
            return
        self.add_light(it["kind"], it["p"], it.get("pitch", 0.0), it.get("yaw", 0.0), colour(it.get("color", "Warm")),
                       it.get("cd", 5.0), shadows=it.get("shadows", False), cone=it.get("cone"),
                       w=(it.get("w") or 1.0) * 100.0, h=(it.get("h") or 0.5) * 100.0, src=it.get("src"),
                       name="Light_" + it["kind"])

    # ---- boxes: one mesh per material, UVs = world-aligned planar projection / TileMeters --------
    def box(self, it):
        if self.culled(it["p"]):
            return
        mat = it["mat"]
        if mat == "Blocker":
            return
        tile = it.get("tile") or (MATS.get(mat, {}).get("TileMeters", 2.0) if mat == "Puddle" or mat in MATS else 2.0)
        if mat == "Puddle":
            tile = MATS["AsphaltWet"]["TileMeters"]
        key = (mat, it.get("tint"), float(tile), bool(it.get("cast", True)), float(it.get("glow", 20.0)))
        cx, cy, cz = it["p"]
        sx, sy, sz = (abs(v) / 2.0 for v in it["s"])
        yaw, pitch = math.radians(it.get("yaw", 0.0)), math.radians(it.get("pitch", 0.0))
        verts = []
        for (ax, ay, az) in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)):
            x, y, z = ax * sx, ay * sy, az * sz
            x, z = x * math.cos(pitch) - z * math.sin(pitch), x * math.sin(pitch) + z * math.cos(pitch)
            x, y = x * math.cos(yaw) - y * math.sin(yaw), x * math.sin(yaw) + y * math.cos(yaw)
            verts.append(bl((cx + x, cy + y, cz + z)))
        self.boxes.setdefault(key, []).append(verts)
        self.stats["boxes"] += 1

    def flush_boxes(self):
        for (mat, tint, tile, cast, glow), boxes in self.boxes.items():
            verts, faces, uvs = [], [], []
            for vs in boxes:
                base = len(verts)
                verts += [tuple(v) for v in vs]
                for f in _FACES:
                    a, b, c = (vs[f[0]], vs[f[1]], vs[f[2]])
                    n = (b - a).cross(c - a)
                    ax = max(range(3), key=lambda i: abs(n[i]))
                    faces.append(tuple(base + i for i in f))
                    for i in f:
                        v = vs[i]
                        u = (v.y, v.z) if ax == 0 else ((v.x, v.z) if ax == 1 else (v.x, v.y))
                        uvs += [u[0] / tile, u[1] / tile]
            me = bpy.data.meshes.new(f"Box_{mat}_{tint}")
            me.from_pydata(verts, [], faces)
            me.uv_layers.new(name="UVMap").data.foreach_set("uv", uvs)
            m, emissive = box_material(mat, tint, glow, self.tile_res())
            me.materials.append(m)
            o = bpy.data.objects.new(me.name, me)
            o.visible_shadow = cast and not emissive
            self.coll.objects.link(o)
        self.boxes = {}

    # ---- text / fog / targets / objectives -------------------------------------------------
    def text(self, it, font="BigShoulders-Bold.ttf", unlit_rgb=None):
        if self.culled(it["p"]):
            return
        cu = bpy.data.curves.new("Sign", "FONT")
        cu.body = it["text"]
        cu.size = float(it.get("size", 60.0)) / 100.0 * 0.95
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        cu.extrude = 0.004
        fp = os.path.join(FONT_DIR, font)
        if os.path.exists(fp):
            cu.font = bpy.data.fonts.load(fp, check_existing=True)
        rgb = srgb_to_lin(colour(it.get("color", "Warm"))) if unlit_rgb is None else unlit_rgb
        cu.materials.append(emission_mat(f"Text_{it.get('color')}_{it.get('glow', 6)}", rgb, float(it.get("glow", 6.0))))
        o = bpy.data.objects.new("Sign", cu)
        o.location = bl(it["p"])
        o.rotation_euler = (math.radians(90.0), 0.0, math.radians(90.0 - it.get("yaw", 0.0)))
        o.visible_shadow = False
        self.coll.objects.link(o)
        self.stats["texts"] += 1
        return o

    def fog(self, it, density_scale=None):
        """LocalFogVolume (unit sphere scaled to the half extents) as a homogeneous ellipsoid."""
        k = density_scale if density_scale is not None else (self.shot.get("fog_scale", 0.06) if self.shot else 0.06)
        if k <= 0:
            return
        me = bpy.data.meshes.new("Fog")
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(volume_mat("FogVol", tuple(it.get("color", (0.7, 0.6, 0.6))), it.get("density", 0.5) * k))
        o = bpy.data.objects.new("LocalFog", me)
        o.location = bl(it["p"])
        o.scale = tuple(it["s"])
        self.coll.objects.link(o)

    def target(self, it):
        """AirsoftPracticeTarget: SteelTarget stand + plate, caption 22 cm up (16 cm text, orange)."""
        coll = self.lib.asset("SteelTarget")
        if coll is None:
            return
        self.instance(coll, "Target", it["p"], it.get("yaw", 0.0), tint_aid="SteelTarget")
        if it.get("caption"):
            cp = ue_world(it["p"], it.get("yaw", 0.0), (1, 1, 1), (4.0, 0.0, 22.0))
            self.text({"p": cp, "yaw": it.get("yaw", 0.0), "text": it["caption"], "size": 16.0, "glow": 1.2},
                      font="BigShoulders-Bold.ttf", unlit_rgb=srgb_to_lin((1.0, 0.667, 0.235)))

    def objective(self, it, team="None", progress_rgb=None):
        """AirsoftObjective: FlagPole_Objective (flag PrimaryTint = state colour), glowing floor disc of the
        capture radius (emissive 1.5), point glow 40 cm under the flag top, floating letter."""
        rgb = progress_rgb or ((0.8, 0.8, 0.8) if team == "None" else TEAM[team])
        coll = self.lib.asset("FlagPole_Objective")
        if coll is not None:
            e = self.instance(coll, "Objective", it["p"], 0.0, tint_aid="FlagPole_Objective")
            e["tP"] = rgb
        r = float(it.get("radius", 5.0))
        bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=r, depth=0.02, location=bl((it["p"][0], it["p"][1], it["p"][2] + 0.02)))
        disc = bpy.context.active_object
        for c in list(disc.users_collection):
            c.objects.unlink(disc)
        self.coll.objects.link(disc)
        disc.data.materials.append(emission_mat("ObjectiveRing", rgb, self.shot.get("ring_glow", 1.5)))
        disc.visible_shadow = False
        top = (point_of("FlagPole_Objective", "FlagTop") or (0, 0, 600))[2]
        self.add_light("point", (it["p"][0], it["p"][1], it["p"][2] + (top - 40.0) / 100.0), 0, 0, rgb, 2500.0 / UNITLESS_PER_CD,
                       name="ObjectiveGlow")
        lab = self.shot.get("label_yaw")
        if lab == "auto":   # the letter billboards toward the local camera (AAirsoftObjective::Tick)
            lab = math.degrees(math.atan2(self.cam_pos[1] - it["p"][1], self.cam_pos[0] - it["p"][0]))
        if lab is not None:
            self.text({"p": (it["p"][0], it["p"][1], it["p"][2] + (top + 110.0) / 100.0), "yaw": lab,
                       "text": it["letter"], "size": 90.0, "glow": 2.0}, unlit_rgb=rgb)

    def rain(self, spec):
        """Shot-only rain (the editor build has no rain: in Unreal it needs a Niagara system): thin streaks along
        the fall direction, each turned to face the camera, lit only by the scene's own lights."""
        import random as _random
        rng = _random.Random(spec.get("seed", 3))
        x0, y0, z0, x1, y1, z1 = spec["box"]
        tx, ty = spec.get("tilt", (0.08, 0.03))
        fall = bl((tx, ty, -1.0)).normalized()
        cam = bl(self.cam_pos)
        verts, faces = [], []
        for _ in range(int(spec.get("count", 4000))):
            p = bl((rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(z0, z1)))
            side = fall.cross(cam - p)
            if side.length < 1e-6:
                continue
            side = side.normalized() * spec.get("width", 0.006) * rng.uniform(0.7, 1.3) * 0.5
            b = p + fall * spec.get("len", 0.6) * rng.uniform(0.6, 1.3)
            k = len(verts)
            verts += [tuple(p - side), tuple(p + side), tuple(b + side), tuple(b - side)]
            faces.append((k, k + 1, k + 2, k + 3))
        me = bpy.data.meshes.new("Rain")
        me.from_pydata(verts, [], faces)
        m, nb, out = new_mat("Rain")
        p = nb.node("ShaderNodeBsdfPrincipled")
        p.inputs["Base Color"].default_value = (0.8, 0.82, 0.86, 1.0)
        p.inputs["Roughness"].default_value = 0.2
        mix = nb.node("ShaderNodeMixShader")
        mix.inputs[0].default_value = spec.get("alpha", 0.35)
        m.node_tree.links.new(nb.node("ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
        m.node_tree.links.new(p.outputs[0], mix.inputs[2])
        m.node_tree.links.new(mix.outputs[0], out.inputs["Surface"])
        me.materials.append(m)
        o = bpy.data.objects.new("Rain", me)
        o.visible_shadow = False
        o.visible_diffuse = False
        self.coll.objects.link(o)
        print(f"  rain: {len(faces)} streaks", flush=True)

    # ---- whole map ------------------------------------------------------------------------
    def build(self, extra=()):
        items = list(self.map["items"]) + list(extra)
        self.plan_resolutions([i for i in items if i["t"] in ("prop", "target", "gun")] +
                              [dict(i, id=None) for i in items if i.get("display")])
        if self.shot and self.shot.get("fp"):     # first-person gun and gloves sit at the lens
            for a in ["Gloves", self.shot["fp"].get("gun", "M4")] + list((self.shot["fp"].get("fit") or
                                                                         WEAPON_DEFAULTS.get(self.shot["fp"].get("gun", "M4"), {})).values()):
                self.dist[a] = 0.3
        t0 = time.time()
        show_obj = self.shot.get("objectives", {}) if self.shot else {}
        for it in items:
            t = it["t"]
            if t == "prop":
                self.prop(it)
            elif t == "box":
                self.box(it)
            elif t == "light":
                self.item_light(it)
            elif t == "text":
                self.text(it)
            elif t == "fog":
                self.fog(it)
            elif t == "target":
                self.target(it)
            elif t == "gun":
                self.extra_gun(it)
            elif t == "objective" and it["letter"] in show_obj:
                o = show_obj[it["letter"]]
                self.objective(it, **(o if isinstance(o, dict) else {"team": o}))
        self.flush_boxes()
        self.settle()
        empty = sorted({o.name for o in list(self.lib.root.all_objects) + list(self.coll.objects)
                        if o.type == "MESH" and (not o.data.materials or any(m is None for m in o.data.materials))})
        if empty:
            raise RuntimeError(f"objects with empty material slots (would render untextured): {empty[:12]}")
        print(f"  built {self.map['name']}: {self.stats} in {time.time() - t0:.0f}s", flush=True)


# --------------------------------------------------------------------------------------
# Environment: sun, sky, haze (lighting.PRESETS)
# --------------------------------------------------------------------------------------


def setup_environment(preset_name, shot):
    scn = bpy.context.scene
    p = PRESETS[preset_name]
    s = p["sun"]
    wb = p.get("white_temp", 6500.0)
    f, _r, _u = ue_basis(s["pitch"], s["yaw"])
    sd = bpy.data.lights.new("Sun", "SUN")
    sd.energy = s["lux"] * LIGHT_SCALE * shot.get("sun_mult", 1.0)
    sd.angle = math.radians(s.get("angle", 0.5))
    sd.color = white_balanced(s["temp"], wb)
    sd.use_shadow = s.get("shadows", True)
    so = bpy.data.objects.new("Sun", sd)
    so.rotation_euler = f.to_track_quat("-Z", "Y").to_euler()
    scn.collection.objects.link(so)

    world = bpy.data.worlds.new("Sky")
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    sky_kind = shot.get("sky", "physical" if s["lux"] > 1.0 else "night")
    if sky_kind == "physical":
        sky = nt.nodes.new("ShaderNodeTexSky")
        sky.sky_type = "MULTIPLE_SCATTERING"
        to_sun = -f
        sky.sun_elevation = math.asin(max(-1.0, min(1.0, to_sun.z)))
        sky.sun_rotation = math.atan2(to_sun.x, to_sun.y)   # azimuth from +Y, clockwise (checked on a test render)
        sky.sun_disc = False
        for k, v in (("air_density", 1.0), ("aerosol_density", shot.get("dust", 1.5)), ("ozone_density", 1.0)):
            if hasattr(sky, k):
                setattr(sky, k, v)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        bk.sid(mix.inputs, "Factor_Float").default_value = 1.0
        nt.links.new(sky.outputs["Color"], bk.sid(mix.inputs, "A_Color"))
        bk.sid(mix.inputs, "B_Color").default_value = (*white_balanced(6500.0, wb), 1.0)
        nt.links.new(bk.sid(mix.outputs, "Result_Color"), bg.inputs["Color"])
        bg.inputs["Strength"].default_value = shot.get("sky_strength", 0.08) * LIGHT_SCALE
    else:
        # night: deep blue zenith, faint city glow at the horizon (sky light 0.35, black lower hemisphere)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
        el = ramp.color_ramp.elements
        el[0].position, el[0].color = 0.0, (0.0005, 0.0005, 0.0007, 1)
        el[1].position, el[1].color = 0.5, (0.010, 0.008, 0.013, 1)
        e2 = el.new(0.6)
        e2.color = (0.0035, 0.0045, 0.009, 1)
        e3 = el.new(1.0)
        e3.color = (0.0012, 0.0018, 0.0045, 1)
        nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = p["sky"]["intensity"] * shot.get("sky_strength", 1.0)
    scn.world = world

    hz = shot.get("haze")
    if hz:
        x0, y0, x1, y1 = hz.get("rect", (-80, -80, 80, 80))
        z1 = hz.get("top", 12.0)
        me = bpy.data.meshes.new("Haze")
        c0, c1 = bl((x0, y0, -0.5)), bl((x1, y1, z1))
        lo = Vector((min(c0.x, c1.x), min(c0.y, c1.y), -0.5))
        hi = Vector((max(c0.x, c1.x), max(c0.y, c1.y), z1))
        v = [(x, y, z) for z in (lo.z, hi.z) for y in (lo.y, hi.y) for x in (lo.x, hi.x)]
        me.from_pydata(v, [], [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)])
        me.materials.append(volume_mat("HazeVol", hz.get("color", (0.8, 0.75, 0.7)), hz["density"], hz.get("g", 0.45)))
        o = bpy.data.objects.new("Haze", me)
        scn.collection.objects.link(o)
    return so


# --------------------------------------------------------------------------------------
# Render setup, compositor (bloom + slight dispersion) and post (vignette, grain)
# --------------------------------------------------------------------------------------


def reset_scene(threads=0):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    if threads:
        scn.render.threads_mode = "FIXED"
        scn.render.threads = threads
    return scn


def setup_render(shot, res, samples, preview):
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    c = scn.cycles
    c.samples = samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.05 if preview else shot.get("noise", 0.03)
    c.adaptive_min_samples = 8 if preview else 16
    c.use_denoising = True
    c.denoiser = "OPENIMAGEDENOISE"
    c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    c.denoising_prefilter = "ACCURATE"
    c.max_bounces = 6
    c.diffuse_bounces = shot.get("diffuse_bounces", 3)
    c.glossy_bounces = 3
    c.transmission_bounces = 4
    c.volume_bounces = 0
    c.transparent_max_bounces = 24
    c.sample_clamp_indirect = shot.get("clamp", 8.0)
    c.sample_clamp_direct = 0.0
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.blur_glossy = 1.0
    c.volume_step_rate = 4.0
    c.use_light_tree = True
    scn.render.film_transparent = False
    scn.view_settings.view_transform = "AgX"
    scn.view_settings.look = shot.get("look", "AgX - Punchy")
    scn.view_settings.exposure = shot.get("exposure", 0.0)
    scn.view_settings.gamma = 1.0
    scn.render.image_settings.file_format = "PNG"
    scn.render.image_settings.color_mode = "RGB"
    scn.render.image_settings.color_depth = "16"
    scn.render.compositor_device = "CPU"
    setup_compositor(shot)


def setup_compositor(shot):
    scn = bpy.context.scene
    ng = bpy.data.node_groups.new("Grade", "CompositorNodeTree")
    scn.compositing_node_group = ng
    rl = ng.nodes.new("CompositorNodeRLayers")
    cur = rl.outputs["Image"]
    bloom = shot.get("bloom", 0.35)
    if bloom > 0:
        gl = ng.nodes.new("CompositorNodeGlare")
        gl.inputs["Type"].default_value = "Bloom"
        gl.inputs["Quality"].default_value = "High"
        # threshold in scene-linear units: the view exposure is applied after compositing
        gl.inputs["Threshold"].default_value = shot.get("bloom_threshold", 1.6) / (2.0 ** shot.get("exposure", 0.0))
        gl.inputs["Smoothness"].default_value = 0.6
        gl.inputs["Strength"].default_value = bloom
        gl.inputs["Size"].default_value = shot.get("bloom_size", 0.8)
        ng.links.new(cur, gl.inputs["Image"])
        cur = gl.outputs["Image"]
    ca = shot.get("ca", 0.012)
    if ca > 0:
        ld = ng.nodes.new("CompositorNodeLensdist")
        ld.inputs["Dispersion"].default_value = ca
        ld.inputs["Distortion"].default_value = shot.get("distortion", -0.006)
        ld.inputs["Fit"].default_value = True
        ng.links.new(cur, ld.inputs["Image"])
        cur = ld.outputs["Image"]
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    out = ng.nodes.new("NodeGroupOutput")
    ng.links.new(cur, out.inputs[0])
    scn.render.use_compositing = True


def setup_camera(shot):
    scn = bpy.context.scene
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    scn.collection.objects.link(cam)
    scn.camera = cam
    cd.sensor_fit = "HORIZONTAL"
    cd.sensor_width = 36.0
    if "hfov" in shot:
        cd.lens_unit = "FOV"
        cd.angle = math.radians(shot["hfov"])
    else:
        cd.lens = shot.get("lens", 35.0)
    cd.clip_start = shot.get("clip_start", 0.05)
    cd.clip_end = 600.0
    cam.location = bl(shot["cam"])
    d = bl(shot["target"]) - cam.location
    q = d.to_track_quat("-Z", "Y")
    if shot.get("roll"):
        q = q @ Matrix.Rotation(math.radians(shot["roll"]), 4, "Z").to_quaternion()
    cam.rotation_euler = q.to_euler()
    cd.shift_x = shot.get("shift_x", 0.0)
    cd.shift_y = shot.get("shift_y", 0.0)
    if shot.get("fstop"):
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = shot["fstop"]
        cd.dof.aperture_blades = 7
        cd.dof.aperture_rotation = math.radians(12)
        focus = shot.get("focus", shot["target"])
        cd.dof.focus_distance = (bl(focus) - cam.location).length if isinstance(focus, (tuple, list)) else float(focus)
    return cam


def post_process(src, png_out, jpg_out, shot):
    """Vignette + fine film grain in display space (PIL / numpy), 16-bit PNG master + quality-90 JPG."""
    import numpy as np
    from PIL import Image

    im = Image.open(src)
    a = np.asarray(im).astype(np.float32)
    a /= 65535.0 if a.max() > 255.5 else 255.0
    h, w = a.shape[:2]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = (x / w - 0.5) * 2.0, (y / h - 0.5) * 2.0
    r = np.sqrt(u * u * 0.9 + v * v * 0.6)
    vig = 1.0 - shot.get("vignette", 0.32) * np.clip((r - 0.35) / 0.95, 0.0, 1.0) ** 1.6
    a *= vig[..., None]
    rng = np.random.default_rng(7)
    g = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
    g = (g + np.roll(g, 1, 0) + np.roll(g, 1, 1)) / 3.0      # slightly soft grain, not per-pixel noise
    lum = a.mean(axis=2, keepdims=True)
    a += g[..., None] * shot.get("grain", 0.018) * (0.35 + 0.65 * np.sqrt(np.clip(lum, 0, 1))) * (1.0 - lum * 0.6)
    a = np.clip(a, 0.0, 1.0)
    if png_out:
        os.makedirs(os.path.dirname(png_out), exist_ok=True)
        Image.fromarray((a * 255.0 + 0.5).astype(np.uint8)).save(png_out, optimize=False)
    if jpg_out:
        os.makedirs(os.path.dirname(jpg_out), exist_ok=True)
        Image.fromarray((a * 255.0 + 0.5).astype(np.uint8)).save(jpg_out, quality=90, subsampling=0, optimize=True)


# --------------------------------------------------------------------------------------
# First-person rig (AirsoftCombatComponent placement, gloves from Gear.json)
# --------------------------------------------------------------------------------------


def place_first_person(b, shot):
    """Gun + gloves in camera space. ADS: gun at -AimPointLocal (eye on the optic's aim line); hip: (20, 11, -15) cm.
    aim = AimAlpha (0..1, eased like the game). Gloves: RightGrip at the gun origin, LeftSupport at Points.LeftHand."""
    fp = shot["fp"]
    gid = fp.get("gun", "M4")
    fit = fp.get("fit")
    fit = dict(WEAPON_DEFAULTS.get(gid, {}) if fit is None else fit)
    pts = REG[gid]["Points"]
    aim_local = list(pts.get("Aim", (0, 0, 0)))
    if fit.get("Optic") in REG and "AimOffset" in REG[fit["Optic"]] and "Optic" in pts:
        aim_local = [pts["Optic"][i] + REG[fit["Optic"]]["AimOffset"][i] for i in range(3)]
    hip = (20.0, 11.0, -15.0)
    eased = 1.0 - (1.0 - fp.get("aim", 1.0)) ** 2
    loc_cs = [hip[i] + (-aim_local[i] - hip[i]) * eased + fp.get("offset", (0, 0, 0))[i] for i in range(3)]
    pitch, yaw, roll = fp.get("rot", (0.0, 0.0, 0.0))   # extra sway (Unreal rotator, degrees)
    # camera space (Unreal: X fwd, Y right, Z up, cm) -> Blender camera local (-Z fwd, X right, Y up, m);
    # Blender gun space is (x, -y, z) of Unreal gun space, so gun +X -> forward, gun +Y -> left, +Z -> up.
    to_cam = Matrix(((0, -1, 0, 0), (0, 0, 1, 0), (-1, 0, 0, 0), (0, 0, 0, 1)))
    sway = Matrix.Rotation(math.radians(-yaw), 4, "Z") @ Matrix.Rotation(math.radians(-pitch), 4, "Y") @ \
        Matrix.Rotation(math.radians(roll), 4, "X")
    W = bpy.context.scene.camera.matrix_world @ Matrix.Translation(Vector((loc_cs[1], loc_cs[2], -loc_cs[0])) / 100.0) \
        @ to_cam @ sway
    skin = fp.get("skin", "Black")
    accent = TEAM[fp.get("team", "Blue")]
    for coll, off in ((b.lib.gun(gid, fit), None), (b.lib.asset("Gloves", ["RightGrip"]), None),
                      (b.lib.asset("Gloves", ["LeftSupport"]), pts.get("LeftHand"))):
        if coll is None:
            continue
        e = bpy.data.objects.new("FP", None)
        e.instance_type = "COLLECTION"
        e.instance_collection = coll
        m = W.copy()
        if off:
            m = m @ Matrix.Translation(Vector((off[0], -off[1], off[2])) / 100.0)
        e.matrix_world = m
        p, s, met, rough = SKINS[skin]
        e["tP"], e["tS"], e["tA"], e["tMet"], e["tRough"] = p, s, accent, met, rough
        b.coll.objects.link(e)


# --------------------------------------------------------------------------------------
# Shots (layout metres, Unreal axes). "extra" props are added for the shot only (noted).
# --------------------------------------------------------------------------------------

SHOTS = {}


def shot(name, **kw):
    SHOTS[name] = kw


# Atmosphere stands in for Unreal's height fog + volumetric fog (lighting.PRESETS); values eyeballed.
STREET_HAZE = {"rect": (-40, -36, 40, -10.4), "top": 10.0, "density": 0.0022, "color": (0.74, 0.8, 1.0), "g": 0.6}
FIELD_DUST = {"rect": (-95, -78, 95, 78), "top": 16.0, "density": 0.0022, "color": (1.0, 0.86, 0.68), "g": 0.65}
RANGE_DUST = {"rect": (-30, -24, 84, 44), "top": 12.0, "density": 0.0018, "color": (1.0, 0.86, 0.68), "g": 0.65}

shot("velvet_street", file="01_VelvetClub_Street", map="VelvetClub", poster=True, poster_sub="VELVET CLUB",
     caption="Velvet Club - the street at night: wet asphalt, neon sign, canopy LEDs and the velvet-rope queue",
     cam=(-5.0, -25.6, 0.3), target=(0.6, -11.0, 1.5), lens=22, fstop=2.8, focus=(0.0, -11.4, 1.6),
     exposure=1.6, sun_mult=0.45, haze=STREET_HAZE, bloom=0.45, samples=64, noise=0.02)
shot("velvet_interior", file="02_VelvetClub_DanceFloor", map="VelvetClub",
     caption="Velvet Club - the dance floor, DJ stage and moving-head lights in the haze",
     cam=(1.5, 7.5, 1.0), target=(-0.5, 18.0, 2.0), lens=20, fstop=2.8, focus=(0.0, 18.0, 1.5),
     exposure=1.7, sun_mult=0.4, fog_scale=0.035, bloom=0.5, samples=48)
shot("armory", file="03_Staging_Armory", map="Staging",
     caption="The Armory (Staging lobby) - walnut panelling, brass lamps and every gun on its display bay",
     cam=(-4.0, 5.2, 1.55), target=(-15.5, 12.2, 1.25), lens=28, fstop=4.0, focus=(-9.6, 13.4, 1.2),
     exposure=2.2, samples=48)
shot("fp_street", file="04_VelvetClub_FirstPerson", map="VelvetClub", hud=True,
     caption="First person - gloved hands on the M4 (red dot, vertical grip) on the wet street outside the club",
     cam=(-7.2, -28.4, 1.62), target=(0.0, -11.0, 1.9), hfov=90.0, clip_start=0.05, fstop=0,
     fp={"gun": "M4", "aim": 0.0, "team": "Blue"}, hud_crosshair=True,
     exposure=1.35, sun_mult=0.45, haze=STREET_HAZE, bloom=0.45, samples=48)
# optional (not in the set): ADS through the red dot - the open rear flip cap fills the top of the view
shot("fp_street_ads", file="04b_VelvetClub_FirstPerson_ADS", map="VelvetClub",
     caption="First person - aiming down the red dot at the club entrance",
     cam=(-3.0, -22.2, 1.62), target=(0.5, -11.0, 2.0), hfov=72.0, clip_start=0.05, fstop=0,
     fp={"gun": "M4", "aim": 1.0, "team": "Blue"},
     exposure=1.6, sun_mult=0.45, haze=STREET_HAZE, bloom=0.45, samples=48)
shot("ironwood_golden", file="05_Ironwood_GoldenHour", map="IronwoodYard",
     caption="Ironwood Yard at golden hour - the north lane, watchtower and field cover in long low light",
     cam=(4.5, -27.0, 0.8), target=(-14.0, -36.0, 3.8), lens=24, fstop=5.6, focus=(-7.0, -37.5, 4.0),
     exposure=0.6, sun_mult=1.3, sky_strength=0.065, haze=FIELD_DUST, samples=48)
shot("ironwood_backlit", file="09_Ironwood_Watchtower_Backlit", map="IronwoodYard",
     caption="Ironwood Yard - the north watchtower against the low sun, dust hanging over the CQB village",
     cam=(-1.2, -44.3, 0.6), target=(-7.5, -36.0, 4.9), lens=20, fstop=4.0, focus=(-7.0, -37.5, 4.0),
     exposure=0.2, sun_mult=1.3, sky_strength=0.065, haze=FIELD_DUST, samples=48)
shot("ironwood_objective", file="06_Ironwood_ObjectiveA", map="IronwoodYard",
     caption="Ironwood Yard - objective A in the container yard, Red team holding the flag",
     cam=(-21.8, 6.8, 0.9), target=(-27.0, -1.5, 2.7), lens=20, fstop=5.6, focus=(-26.0, 0.0, 2.0),
     objectives={"A": {"team": "Red"}}, label_yaw="auto", ring_glow=0.05,   # disc dimmed, see report
     exposure=0.4, sun_mult=1.3, sky_strength=0.065, haze=FIELD_DUST, samples=48)
shot("range", file="07_Staging_Range", map="Staging",
     caption="The practice range at golden hour - steel plates at 25 / 40 / 60 m in front of the hay-bale berm",
     cam=(28.5, -1.0, 0.5), target=(47.0, -9.0, 1.0), lens=28, fstop=4.0, focus=(31.0, -3.5, 0.8),
     exposure=1.0, sun_mult=1.2, sky_strength=0.065, haze=RANGE_DUST, samples=48)
shot("weapon_hero", file="08_Armory_M4_Hero", map="Staging",
     caption="Hero close-up - an M4 (FDE finish, 4x scope, suppressor) in its open case on the armory counter",
     cam=(-12.0, 10.15, 1.95), target=(-12.3, 9.05, 1.15), lens=35, fstop=2.2, focus=(-12.3, 9.05, 1.2),
     exposure=1.6, samples=64,
     extra_lights=[{"kind": "spot", "p": (-12.3, 9.6, 2.2), "pitch": -62.0, "yaw": -90.0, "color": (1.0, 0.85, 0.68),
                    "cd": 4.0, "cone": (12, 28), "shadows": True, "src": 6.0}],   # shot-only product key light
     # shot-only extra: the hero gun laid in the counter's open GunCase_Hard
     extra=[{"t": "gun", "id": "M4", "fit": {"Optic": "Scope4x", "Muzzle": "Suppressor"}, "skin": "FDE", "team": "Blue",
             "p": (-12.16, 9.06, 1.3), "rot": (0.0, 175.0, 90.0), "rest": True}])

# Nightjar Garage (night, rain). Rain streaks are shot-only geometry: the editor build has wet materials, puddles
# and fog but no rain particles (that needs a Niagara system).
GARAGE_HAZE = {"rect": (-36, -23, 36, 23), "top": 6.3, "density": 0.0025, "color": (0.78, 0.82, 0.92), "g": 0.55}
ROOF_HAZE = {"rect": (-170, -170, 170, 170), "top": 45.0, "density": 0.0032, "color": (0.72, 0.74, 0.82), "g": 0.6}
ROOF_RAIN = {"box": (-31, -23, 6.7, 31, 23, 13.5), "count": 14000, "len": 0.7, "width": 0.007, "alpha": 0.4}
HOLE_RAIN = {"box": (-11, 1.3, 3.4, 11, 5.7, 9.5), "count": 3500, "len": 0.6, "width": 0.006, "alpha": 0.45, "seed": 5}

shot("garage_roof", file="10_NightjarGarage_RoofDeck", map="NightjarGarage",
     caption="Nightjar Garage - the roof deck in the rain: wet concrete, sodium poles, the east tower and the city beyond",
     cam=(-29.0, -15.2, 8.35), target=(6.0, -2.5, 7.3), lens=24, fstop=4.0, focus=(-10.0, -9.0, 7.4),
     exposure=1.6, sun_mult=1.0, haze=ROOF_HAZE, rain=ROOF_RAIN, fog_scale=0.03, bloom=0.5, samples=64)
shot("garage_ramp", file="11_NightjarGarage_Ramp", map="NightjarGarage",
     caption="Nightjar Garage - ramp R2 climbing from the mid deck to the roof, sodium wallpacks and rain through the opening",
     cam=(-17.0, 3.2, 4.75), target=(6.0, 3.6, 6.1), lens=26, fstop=4.0, focus=(-6.0, 3.5, 4.4),
     exposure=1.7, sun_mult=1.0, haze=GARAGE_HAZE, rain=HOLE_RAIN, fog_scale=0.03, bloom=0.5, samples=64)
shot("garage_row", file="12_NightjarGarage_ParkingRow", map="NightjarGarage",
     caption="Nightjar Garage - first-person height down the mid-deck north aisle: fluorescent battens, painted bays, a fender-bender",
     cam=(-27.5, -14.0, 4.92), target=(10.0, -14.6, 4.6), hfov=80.0, fstop=0, clip_start=0.05,
     exposure=1.7, sun_mult=1.0, haze=GARAGE_HAZE, fog_scale=0.03, bloom=0.45, samples=64)
shot("garage_objective", file="13_NightjarGarage_ObjectiveB", map="NightjarGarage",
     caption="Nightjar Garage - objective B on the median between the ramps, Blue holding it",
     cam=(13.5, -0.4, 5.0), target=(-3.0, 0.4, 4.2), lens=24, fstop=4.0, focus=(0.0, 0.1, 4.0),
     objectives={"B": {"team": "Blue"}}, label_yaw="auto", ring_glow=0.05,
     exposure=1.7, sun_mult=1.0, haze=GARAGE_HAZE, rain=HOLE_RAIN, fog_scale=0.03, bloom=0.5, samples=64)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def build_scene(sh, opts):
    m = L.get_map(sh["map"])
    b = Builder(sh, m, opts)
    preset = sh.get("preset", m["lighting"])
    setup_environment(preset, sh)
    cam = setup_camera(sh)
    extra = [dict(e) for e in sh.get("extra", [])]
    b.build(extra)
    if sh.get("fp"):
        place_first_person(b, sh)
    for it in sh.get("extra_lights", []):
        b.item_light(dict(it, t="light"))
    for spec in ([sh["rain"]] if isinstance(sh.get("rain"), dict) else sh.get("rain", [])):
        b.rain(spec)
    return b, cam


def topdown(map_name, res, samples, out):
    m = L.get_map(map_name)
    x0, y0, x1, y1 = m["bounds"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    sh = {"map": map_name, "cam": (cx, cy, 120.0), "target": (cx, cy, 0.0), "exposure": 0.0, "bloom": 0.0, "ca": 0.0,
          "sun_mult": 1.0, "sky": "physical", "sky_strength": 0.08}
    b = Builder(sh, m, {"preview": True})
    setup_environment(m["lighting"], sh)
    for o in bpy.context.scene.objects:   # a high, even sun so night maps read on the plan too
        if o.type == "LIGHT" and o.data.type == "SUN":
            o.data.energy = 3.0
            o.rotation_euler = (0.35, 0.2, 0.0)
    b.build()
    cam = setup_camera(sh)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(x1 - x0, (y1 - y0) * res[0] / res[1]) * 1.04
    cam.rotation_euler = (0, 0, 0)
    for o in b.coll.objects:   # roofs and ceilings hide the interiors on the plan
        if o.name.startswith(("Box_PaintedSteel_Black", "Box_CorrodedMetal", "Box_PaintedSteel_Grey")):
            o.hide_render = True
    setup_render({"exposure": 0.0, "look": "AgX - Medium High Contrast", "bloom": 0, "ca": 0}, res, samples, True)
    bpy.context.scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("wrote", out, flush=True)


def render_shot(name, opts):
    sh = dict(SHOTS[name])
    res = opts.get("res") or ((640, 360) if opts.get("preview") else (2560, 1440))
    samples = opts.get("samples") or (24 if opts.get("preview") else sh.get("samples", 96))
    t0 = time.time()
    reset_scene(opts.get("threads", 0))
    b, cam = build_scene(sh, opts)
    setup_render(sh, res, samples, opts.get("preview"))
    tag = sh.get("file", name)
    tmp_dir = opts.get("tmp_dir") or os.path.join(PNG_DIR, "_raw")
    os.makedirs(tmp_dir, exist_ok=True)
    raw = os.path.join(tmp_dir, f"{tag}{'_preview' if opts.get('preview') else ''}.png")
    bpy.context.scene.render.filepath = raw
    if opts.get("keep_blend"):
        bpy.ops.wm.save_as_mainfile(filepath=raw[:-4] + ".blend")
    t1 = time.time()
    print(f"  scene ready in {t1 - t0:.0f}s; rendering {res[0]}x{res[1]} @ {samples} spp", flush=True)
    if opts.get("try"):   # framing exploration: several camera variants on one scene build
        for k, var in enumerate(json.loads(opts["try"])):
            bpy.data.objects.remove(bpy.context.scene.camera)
            v = dict(sh, **var)
            setup_camera(v)
            bpy.context.scene.view_settings.exposure = v.get("exposure", 0.0)
            out = os.path.join(tmp_dir, f"{tag}_try{k}.png")
            bpy.context.scene.render.filepath = out
            bpy.ops.render.render(write_still=True)
            post_process(out, None, out[:-4] + ".jpg", v)
            print("wrote", out[:-4] + ".jpg", var, flush=True)
        return
    bpy.ops.render.render(write_still=True)
    t2 = time.time()
    print(f"  rendered in {t2 - t1:.0f}s", flush=True)
    if opts.get("preview") or opts.get("no_post"):
        post_process(raw, None, raw[:-4] + ".jpg", sh)
        print("wrote", raw[:-4] + ".jpg", flush=True)
    else:
        png = os.path.join(opts.get("png_dir") or PNG_DIR, f"{tag}.png")
        jpg = os.path.join(opts.get("jpg_dir") or JPG_DIR, f"{tag}.jpg")
        post_process(raw, png, jpg, sh)
        print("wrote", png, "and", jpg, flush=True)
    print(f"TIME {name} build={t1 - t0:.0f}s render={t2 - t1:.0f}s total={time.time() - t0:.0f}s", flush=True)


def parse(argv):
    opts = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--shot", "--topdown", "--threads", "--samples", "--res", "--png-dir", "--jpg-dir", "--tmp-dir", "--try"):
            v = argv[i + 1]
            i += 1
            k = a[2:].replace("-", "_")
            if k == "res":
                w, h = v.lower().split("x")
                v = (int(w), int(h))
            elif k in ("threads", "samples"):
                v = int(v)
            if k == "shot":
                opts.setdefault("shots", []).append(v)
            else:
                opts[k] = v
        elif a.startswith("--"):
            opts[a[2:].replace("-", "_")] = True
        i += 1
    return opts


def main(argv):
    opts = parse(argv)
    if opts.get("list"):
        for k, v in SHOTS.items():
            print(f"{k:22s} {v.get('file', ''):28s} {v['map']:12s} {v.get('caption', '')}")
        return
    if opts.get("sheet"):
        make_sheet(opts)
        return
    if opts.get("topdown"):
        out = os.path.join(opts.get("tmp_dir") or os.path.join(PNG_DIR, "_raw"), f"topdown_{opts['topdown']}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        reset_scene(opts.get("threads", 0))
        topdown(opts["topdown"], opts.get("res") or (1600, 1100), opts.get("samples") or 8, out)
        return
    for name in opts.get("shots", []):
        if name not in SHOTS:
            raise SystemExit(f"unknown shot {name}; --list shows them")
        render_shot(name, opts)


# --------------------------------------------------------------------------------------
# Post products (PIL only): contact sheet, title poster, HUD overlay
# --------------------------------------------------------------------------------------

INTER = "/usr/share/fonts/opentype/inter/Inter-%s.otf"
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf"


def _font(size, weight="Regular", family="ui"):
    from PIL import ImageFont

    cands = []
    if family == "title":
        cands.append(os.path.join(FONT_DIR, "BigShoulders-Bold.ttf"))
    cands += [INTER % weight, INTER % "Regular", DEJAVU % ("-Bold" if weight in ("Bold", "SemiBold") else "")]
    for c in cands:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def _spaced(draw, xy, text, font, fill, spacing, anchor="l"):
    """Letter-spaced text (Slate-style tracking). anchor l / m / r on the x axis; returns the width."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * max(0, len(text) - 1)
    x, y = xy
    x -= {"l": 0.0, "m": total / 2.0, "r": total}[anchor]
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + spacing
    return total


def _lin2srgb8(c, a=255):
    return tuple(int(round(255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055))) for v in c) + (a,)


def make_hud(src, out, crosshair=False, spread_deg=2.4, hfov=90.0):
    """Minimal in-game HUD in the game's style (AirsoftUIStyle: dark translucent panels, hairline borders,
    accent orange, tracked caps): round timer + team scores + objective pips top-centre, ammo bottom-right.
    No crosshair (aiming through the red dot)."""
    from PIL import Image, ImageDraw

    base = Image.open(src).convert("RGBA")
    W, H = base.size
    s = W / 2560.0
    ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    text = _lin2srgb8((0.9, 0.88, 0.85))
    dim = _lin2srgb8((0.42, 0.41, 0.4))
    accent = _lin2srgb8((1.0, 0.55, 0.05))
    blue, red = _lin2srgb8(TEAM["Blue"]), _lin2srgb8(TEAM["Red"])
    panel, hair = (3, 3, 4, 150), (255, 255, 255, 26)

    def box(x0, y0, x1, y1, fill=panel):
        d.rounded_rectangle((x0, y0, x1, y1), radius=int(4 * s), fill=fill, outline=hair, width=max(1, int(s)))

    # top centre: BLUE 2 | 03:41 | 1 RED, objective pips A B C underneath
    cx, top = W / 2, int(34 * s)
    box(cx - 230 * s, top, cx + 230 * s, top + 64 * s)
    f_time, f_score, f_cap = _font(int(34 * s), "SemiBold"), _font(int(30 * s), "Bold"), _font(int(13 * s), "Medium")
    _spaced(d, (cx, top + 12 * s), "03:41", f_time, text, 3 * s, "m")
    d.rectangle((cx - 230 * s, top, cx - 222 * s, top + 64 * s), fill=blue)
    d.rectangle((cx + 222 * s, top, cx + 230 * s, top + 64 * s), fill=red)
    _spaced(d, (cx - 200 * s, top + 8 * s), "BLUE", f_cap, dim, 3 * s)
    _spaced(d, (cx - 200 * s, top + 24 * s), "2", f_score, blue, 0)
    _spaced(d, (cx + 200 * s, top + 8 * s), "RED", f_cap, dim, 3 * s, "r")
    _spaced(d, (cx + 200 * s, top + 24 * s), "1", f_score, red, 0, "r")
    f_pip = _font(int(15 * s), "Bold")
    for i, (letter, col) in enumerate((("A", blue), ("B", text), ("C", red))):
        px = cx + (i - 1) * 46 * s
        y0 = top + 76 * s
        d.rounded_rectangle((px - 17 * s, y0, px + 17 * s, y0 + 30 * s), radius=int(3 * s), fill=panel,
                            outline=col[:3] + (200,), width=max(1, int(1.5 * s)))
        _spaced(d, (px, y0 + 6 * s), letter, f_pip, col, 0, "m")
    # bottom right: ammo
    x1, y1 = W - 56 * s, H - 52 * s
    box(x1 - 300 * s, y1 - 104 * s, x1, y1)
    d.rectangle((x1 - 300 * s, y1 - 3 * s, x1, y1), fill=accent)
    f_ammo, f_res, f_name = _font(int(58 * s), "SemiBold"), _font(int(24 * s), "Medium"), _font(int(14 * s), "SemiBold")
    w_res = _spaced(d, (x1 - 24 * s, y1 - 58 * s), "/ 180", f_res, dim, 1 * s, "r")
    _spaced(d, (x1 - 36 * s - w_res, y1 - 88 * s), "27", f_ammo, text, 1 * s, "r")
    _spaced(d, (x1 - 276 * s, y1 - 92 * s), "M4", f_name, text, 3 * s)
    _spaced(d, (x1 - 276 * s, y1 - 70 * s), "AUTO", f_name, accent, 3 * s)
    _spaced(d, (x1 - 276 * s, y1 - 36 * s), "RED DOT", _font(int(11 * s), "Medium"), dim, 3 * s)
    if crosshair:   # SAirsoftHUDCanvas::PaintCrosshair at hip: gap from spread, 9 x 2 bars, centre dot
        u = H / 1080.0                     # Slate DPI scale (1080p = 1.0)
        gap = max(4.0 * u, math.tan(math.radians(spread_deg)) / math.tan(math.radians(hfov / 2)) * W / 2)
        ln, th = 9.0 * u, 2.0 * u
        cxx, cyy = W / 2, H / 2
        for (x0, y0, w, h) in ((cxx - gap - ln, cyy - th / 2, ln, th), (cxx + gap, cyy - th / 2, ln, th),
                               (cxx - th / 2, cyy - gap - ln, th, ln), (cxx - th / 2, cyy + gap, th, ln),
                               (cxx - u, cyy - u, 2 * u, 2 * u)):
            d.rectangle((x0 - u, y0 - u, x0 + w + u, y0 + h + u), fill=(0, 0, 0, 115))
            d.rectangle((x0, y0, x0 + w, y0 + h), fill=(255, 255, 255, 235))
    Image.alpha_composite(base, ov).convert("RGB").save(out, quality=90, subsampling=0, optimize=True)
    print("wrote", out, flush=True)


def make_poster(src, out, subtitle="VELVET CLUB"):
    """1920x1080 title card from the hero still: bottom gradient, tracked BigShoulders title, hairline rule."""
    import numpy as np
    from PIL import Image, ImageDraw

    im = Image.open(src).convert("RGB").resize((1920, 1080), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32) / 255.0
    y = np.linspace(0.0, 1.0, 1080, dtype=np.float32)[:, None, None]
    a *= 1.0 - 0.74 * np.clip((y - 0.5) / 0.5, 0, 1) ** 1.3
    im = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    title = "ANDREW'S AIRSOFT"
    f = _font(122, family="title")
    tw = _spaced(d, (960, 0), title, f, (0, 0, 0, 0), 18, "m")   # measure
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    ty = 812
    _spaced(d, (962, ty + 3), title, f, (0, 0, 0, 150), 18, "m")          # drop shadow
    _spaced(d, (960, ty), title, f, (246, 240, 232, 255), 18, "m")
    rule_y = ty + 158
    acc = _lin2srgb8((1.0, 0.55, 0.05))
    d.rectangle((960 - tw / 2, rule_y, 960 + tw / 2, rule_y + 2), fill=(246, 240, 232, 90))
    d.rectangle((960 - 60, rule_y - 1, 960 + 60, rule_y + 3), fill=acc)
    _spaced(d, (960, rule_y + 16), subtitle, _font(19, "Medium"), (220, 214, 206, 220), 8, "m")
    Image.alpha_composite(im, ov).convert("RGB").save(out, quality=92, subsampling=0, optimize=True)
    print("wrote", out, flush=True)


def make_contact_sheet(entries, out, title="ANDREW'S AIRSOFT  -  MAP STILLS"):
    """entries: [(jpg path, caption)] -> 2-column grid with captions."""
    from PIL import Image, ImageDraw

    tw, th, cap, pad, head = 960, 540, 64, 24, 96
    cols = 2
    rows = (len(entries) + cols - 1) // cols
    W = cols * tw + (cols + 1) * pad
    H = head + rows * (th + cap) + (rows + 1) * pad // 2
    sheet = Image.new("RGB", (W, H), (14, 14, 16))
    d = ImageDraw.Draw(sheet)
    _spaced(d, (pad, 34), title, _font(30, "SemiBold"), (236, 232, 226), 6)
    d.rectangle((pad, 80, pad + 90, 82), fill=_lin2srgb8((1.0, 0.55, 0.05))[:3])
    for i, (path, caption) in enumerate(entries):
        r, c = divmod(i, cols)
        x = pad + c * (tw + pad)
        y = head + pad // 2 + r * (th + cap + pad // 2)
        sheet.paste(Image.open(path).convert("RGB").resize((tw, th), Image.LANCZOS), (x, y))
        name = os.path.splitext(os.path.basename(path))[0]
        _spaced(d, (x, y + th + 10), name.split("_", 1)[0], _font(15, "Bold"), _lin2srgb8((1.0, 0.55, 0.05))[:3], 2)
        d.text((x + 34, y + th + 9), caption, font=_font(17, "Regular"), fill=(214, 210, 204))
    sheet.save(out, quality=90, subsampling=0, optimize=True)
    print("wrote", out, flush=True)


def make_sheet(opts):
    jpg_dir = opts.get("jpg_dir") or JPG_DIR
    png_dir = opts.get("png_dir") or PNG_DIR
    entries = []
    for name, sh in SHOTS.items():
        if not sh.get("file"):
            continue
        p = os.path.join(jpg_dir, sh["file"] + ".jpg")
        if os.path.exists(p):
            entries.append((p, sh.get("caption", "")))
        if sh.get("hud") and os.path.exists(p):
            src = os.path.join(png_dir, sh["file"] + ".png")
            make_hud(src if os.path.exists(src) else p, os.path.join(jpg_dir, sh["file"] + "_HUD.jpg"),
                     crosshair=sh.get("hud_crosshair", False), hfov=sh.get("hfov", 90.0))
        if sh.get("poster"):
            src = os.path.join(png_dir, sh["file"] + ".png")
            src = src if os.path.exists(src) else p
            if os.path.exists(src):
                make_poster(src, os.path.join(jpg_dir, "00_Poster_1920x1080.jpg"), sh.get("poster_sub", "VELVET CLUB"))
    if entries:
        make_contact_sheet(sorted(entries), os.path.join(jpg_dir, "_contact_sheet.jpg"))


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--" in a:
        a = a[a.index("--") + 1 :]
    main(a)
