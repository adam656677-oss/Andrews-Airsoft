"""
Original character heads for the story cast (Andrew, Kade, Dorian Sloane, Mara Voss, Silas Varga)
and four Ledger crew variants.  Every face is a generic procedural sculpt (headlib.py): no likeness
of any real person, actor or film character.

    python Tools/Blender/heads/build_heads.py                    # build, bake, export, JSON, renders
    python Tools/Blender/heads/build_heads.py -- Andrew Kade     # only these characters
    python Tools/Blender/heads/build_heads.py -- --preview [Name]  # flat-shaded shape check (scratch dir)
    python Tools/Blender/heads/build_heads.py -- --renders-only  # lineup + Andrew portrait from the exported files
    flags: --res 2048|1024 (texture size, default 2048)  --samples N  --no-render  --no-bake

Output (Tools/Blender/CONVENTIONS.md):
    SourceAssets/Characters/Heads/<AssetId>/SM_<AssetId>_Head.fbx   (+ _Hair.fbx where the style has hair)
    SourceAssets/Characters/Heads/<AssetId>/T_<AssetId>_<Piece>_BC / _N / _ORM / _M.png
    Content/Airsoft/Data/GearHeads.json   anchors (head bone), cast and crew lists
    Docs/Renders/Heads/_Lineup_4K.jpg, Docs/Renders/Heads/Andrew_Portrait.jpg

Pieces are rigid, attached to the head bone with their origin at its pivot in the assumed UE5
Manny reference pose (like the suit's hair); UAirsoftTeamGearComponent::ApplyHead puts them on.
"""

import json
import math
import os
import sys
import time

import bpy  # noqa: I001
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "gear"))
sys.path.insert(0, os.path.join(HERE, "..", "common"))

import headlib as hl  # noqa: E402
import handkit as hk  # noqa: E402
import bakekit as bk  # noqa: E402
import studio  # noqa: E402
import teamgear_body as tb  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT_ROOT = os.path.join(ROOT, "SourceAssets", "Characters", "Heads")
DATA_PATH = os.path.join(ROOT, "Content", "Airsoft", "Data", "GearHeads.json")
RENDER_DIR = os.path.join(ROOT, "Docs", "Renders", "Heads")
SCRATCH = os.environ.get("HEADS_SCRATCH", os.path.join(ROOT, "Saved", "HeadsScratch"))
MESH_H = 0.00135  # surface-nets cell (m)
HAIR_H = 0.0011


def log(*a):
    print("[heads]", *a, flush=True)


# --------------------------------------------------------------------------------------
# Meshing
# --------------------------------------------------------------------------------------


class Fn:
    def __init__(self, f, lo, hi):
        self.f, self.lo, self.hi = f, np.asarray(lo, np.float64), np.asarray(hi, np.float64)

    def eval(self, p):
        return self.f(np.asarray(p, np.float64))

    def bounds(self, pad=0.0):
        return self.lo - pad, self.hi + pad

    def gradient(self, p, h=2e-4):
        g = np.zeros_like(p)
        for i in range(3):
            e = np.zeros(3)
            e[i] = h
            g[:, i] = (self.eval(p + e) - self.eval(p - e)) / (2 * h)
        return g

    def project(self, p, iters=3):
        for _ in range(iters):
            d = self.eval(p)
            g = self.gradient(p)
            g2 = np.maximum(np.einsum("ij,ij->i", g, g), 1e-8)
            p = p - (d / g2)[:, None] * g
        return p


def mesh_sdf(F, h):
    lo, hi = F.bounds(3 * h)
    v, q = hk.mesh_field(F, h, lo, hi)
    v = F.project(v, 3)
    vq = v[q]
    n = np.cross(vq[:, 1] - vq[:, 0], vq[:, 2] - vq[:, 0]) + np.cross(vq[:, 2] - vq[:, 0], vq[:, 3] - vq[:, 0])
    g = F.gradient(vq.mean(axis=1), 3e-4)
    flip = np.einsum("ij,ij->i", n, g) < 0
    q = q.copy()
    q[flip] = q[flip][:, ::-1]
    return v, q


def keep_largest(v, q):
    """Drops tiny loose islands (surface-nets specks): min-label propagation with pointer jumping."""
    n = len(v)
    a = np.concatenate([q[:, i] for i in range(4)])
    b = np.concatenate([q[:, (i + 1) % 4] for i in range(4)])
    lab = np.arange(n)
    for _ in range(2000):
        m = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    roots, inv = np.unique(lab, return_inverse=True)
    if len(roots) <= 1:
        return v, q
    face_lab = inv[q[:, 0]]
    sizes = np.bincount(face_lab, minlength=len(roots))
    keep_f = sizes[face_lab] >= max(200, sizes.max() * 0.01)
    q = q[keep_f]
    used = np.unique(q)
    remap = -np.ones(n, np.int64)
    remap[used] = np.arange(len(used))
    return v[used], remap[q]


def mesh_object(name, v, q, coll):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(v))
    me.vertices.foreach_set("co", v.astype(np.float32).ravel())
    me.loops.add(len(q) * 4)
    me.loops.foreach_set("vertex_index", q.astype(np.int32).ravel())
    me.polygons.add(len(q))
    me.polygons.foreach_set("loop_start", np.arange(0, len(q) * 4, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(q), 4, np.int32))
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def set_attr(ob, name, values):
    me = ob.data
    a = me.attributes.get(name) or me.attributes.new(name, "FLOAT", "POINT")
    a.data.foreach_set("value", np.asarray(values, np.float32))


def vertex_normals(ob):
    me = ob.data
    n = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", n)
    return n.reshape(-1, 3).astype(np.float64)


def build_head_mesh(head, coll, h=MESH_H):
    lo, hi = head.bounds()
    F = Fn(lambda p: head.skin_sdf(p), lo, hi)
    t0 = time.time()
    v, q = mesh_sdf(F, h)
    v, q = keep_largest(v, q)
    ob = mesh_object(f"SM_{hl.ASSET_IDS[head.name]}_Head", v, q, coll)
    attrs = head.attributes(v, vertex_normals(ob))
    for k, a in attrs.items():
        set_attr(ob, k, a)
    log(f"  {head.name}: head {len(q) * 2} tris ({time.time() - t0:.0f}s)")
    return ob


def build_hair_mesh(head, coll, h=HAIR_H):
    style = hl.CAST[head.name]["hair"]
    if not hl.style_has_mesh(style["style"]) and not style.get("beard"):
        return None
    hair = hl.Hair(head, style["style"])
    parts_v, parts_q = [], []
    t0 = time.time()
    if hl.style_has_mesh(style["style"]):
        lo, hi = hair.bounds()
        v, q = mesh_sdf(Fn(hair.sdf, lo, hi), h)
        v, q = keep_largest(v, q)
        parts_v.append(v)
        parts_q.append(q)
    if style.get("beard"):
        lo, hi = np.array([-0.02, -0.08, -0.09]), np.array([0.16, 0.08, 0.06])
        v, q = mesh_sdf(Fn(hair.beard_sdf, lo, hi), h * 0.9)
        v, q = keep_largest(v, q)
        off = sum(len(x) for x in parts_v)
        parts_v.append(v)
        parts_q.append(q + off)
    v = np.concatenate(parts_v)
    q = np.concatenate(parts_q)
    ob = mesh_object(f"SM_{hl.ASSET_IDS[head.name]}_Hair", v, q, coll)
    # strand flow: lines of constant 'psi' run from the hairline back (combed) or across (short)
    c = head.skull_c
    psi = np.arctan2(v[:, 2] - c[2], v[:, 1] - c[1])
    set_attr(ob, "psi", psi)
    set_attr(ob, "ao", hl.sdf_ao(lambda p: np.minimum(hair.sdf(p), head.skin_sdf(p, False)), v, vertex_normals(ob), k=0.8))
    log(f"  {head.name}: hair {len(q) * 2} tris ({time.time() - t0:.0f}s)")
    return ob


# --------------------------------------------------------------------------------------
# Bake graphs
# --------------------------------------------------------------------------------------


def srgb_to_lin(c):
    c = np.asarray(c, np.float64)
    return tuple(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


class G:
    """Tiny node-graph helper."""

    def __init__(self, mat):
        self.nt = mat.node_tree
        self.nodes, self.links = self.nt.nodes, self.nt.links

    def node(self, kind, **kw):
        n = self.nodes.new(kind)
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def _in(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.links.new(v, sock)
        elif isinstance(v, (tuple, list)):
            sock.default_value = tuple(v) + ((1.0,) if len(v) == 3 and len(sock.default_value) == 4 else ())
        else:
            sock.default_value = v

    def attr(self, name):
        n = self.node("ShaderNodeAttribute", attribute_name=name)
        return n.outputs["Fac"]

    def math(self, op, a, b=0.0, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._in(n.inputs[0], a)
        self._in(n.inputs[1], b)
        return n.outputs[0]

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def add(self, a, b):
        return self.math("ADD", a, b)

    def sub(self, a, b):
        return self.math("SUBTRACT", a, b)

    def mr(self, v, a, b, c=0.0, d=1.0, smooth=True):
        n = self.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP" if smooth else "LINEAR", clamp=True)
        self._in(n.inputs["Value"], v)
        n.inputs["From Min"].default_value = a
        n.inputs["From Max"].default_value = b
        n.inputs["To Min"].default_value = c
        n.inputs["To Max"].default_value = d
        return n.outputs["Result"]

    def mix(self, fac, a, b):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type="MIX", clamp_factor=True)
        self._in(n.inputs["Factor"], fac)
        self._in(n.inputs[6], a)
        self._in(n.inputs[7], b)
        return n.outputs[2]

    def mixmul(self, fac, a, b):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY", clamp_factor=True)
        self._in(n.inputs["Factor"], fac)
        self._in(n.inputs[6], a)
        self._in(n.inputs[7], b)
        return n.outputs[2]

    def obj_pos(self):
        return self.node("ShaderNodeTexCoord").outputs["Object"]

    def scale_vec(self, v, s):
        n = self.node("ShaderNodeVectorMath", operation="MULTIPLY")
        self._in(n.inputs[0], v)
        n.inputs[1].default_value = s
        return n.outputs[0]

    def noise(self, vec, scale, detail=2.0, rough=0.5, out="Fac", dim="3D"):
        n = self.node("ShaderNodeTexNoise", noise_dimensions=dim)
        self._in(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        return n.outputs[out]

    def voronoi(self, vec, scale, feature="F1", out="Distance"):
        n = self.node("ShaderNodeTexVoronoi", feature=feature)
        self._in(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        return n.outputs[out]

    def emit(self, col):
        n = self.node("ShaderNodeEmission")
        self._in(n.inputs["Color"], col)
        n.inputs["Strength"].default_value = 1.0
        return n.outputs[0]

    def combine(self, r, g, b):
        n = self.node("ShaderNodeCombineColor")
        self._in(n.inputs[0], r)
        self._in(n.inputs[1], g)
        self._in(n.inputs[2], b)
        return n.outputs[0]


def skin_graph(mat, name):
    """Returns {'color', 'orm', 'normal'} shader outputs for the head bake."""
    cfg = hl.CAST[name]
    head_s = hl.params(name)
    g = G(mat)
    P = g.obj_pos()
    skin = srgb_to_lin(cfg["skin"])
    redness = cfg.get("redness", 0.3)
    # base skin: subtle low-frequency mottling plus fine variation
    mott = g.noise(P, 18.0, 3.0, 0.55)
    fine = g.noise(P, 220.0, 2.0, 0.5)
    col = g.mixmul(g.mr(mott, 0.3, 0.7, 0.0, 0.18), skin, (0.82, 0.74, 0.72))
    col = g.mix(g.mr(fine, 0.35, 0.65, 0.0, 0.08), col, (min(1.0, skin[0] * 1.15), skin[1] * 0.95, skin[2] * 0.92))
    # warmth: cheeks, nose, ears, lips' surround
    red = (min(1.0, skin[0] * 1.25), skin[1] * 0.70, skin[2] * 0.72)
    warm = g.add(g.mul(g.attr("cheek"), 0.55), g.add(g.mul(g.attr("nose"), 0.75), g.mul(g.attr("ear"), 0.5)))
    col = g.mix(g.mul(warm, redness), col, red)
    # neck slightly lighter/cooler, scalp a touch paler
    col = g.mix(g.mul(g.attr("neck"), 0.25), col, (skin[0] * 0.95, skin[1] * 0.97, skin[2] * 1.0))
    # under-eye darkening with age
    col = g.mixmul(g.mul(g.attr("under_eye"), 0.25 + 0.45 * head_s["age"]), col, (0.78, 0.70, 0.72))
    # stubble: dense dark dots in the beard region
    stub = cfg.get("stubble", 0.0)
    if stub > 0:
        dots = g.voronoi(P, 1800.0)
        dotm = g.mr(dots, 0.18, 0.05)
        shadow = g.mul(g.attr("beard"), stub)
        col = g.mixmul(g.mul(shadow, 0.55), col, (0.72, 0.68, 0.66))
        col = g.mix(g.mul(g.mul(dotm, shadow), 0.85), col, cfg["stubble_col"])
    # lips
    lip_col = cfg.get("lip_tint") or (skin[0] * 0.85, skin[1] * 0.42, skin[2] * 0.45)
    col = g.mix(g.mr(g.attr("lip"), 0.15, 0.7), col, lip_col)
    # brows: strands across the arch
    bpos = g.scale_vec(P, (1.0, 9.0, 1.0))
    strands = g.noise(bpos, 900.0, 1.0, 0.5)
    brow = g.mul(g.attr("brow"), g.mr(strands, 0.40, 0.62, 0.55, 1.0))
    col = g.mix(brow, col, cfg["brow_col"])
    # lashes / lid line
    col = g.mix(g.mul(g.attr("lash"), 0.9), col, (0.012, 0.010, 0.009))
    # eyes
    cosv = g.attr("eye_cos")
    iris_m = g.mr(cosv, 0.855, 0.875)  # ~29 deg
    pupil_m = g.mr(cosv, 0.972, 0.978)
    limbal = g.mul(g.mr(cosv, 0.850, 0.862), g.mr(cosv, 0.885, 0.868))
    rays = g.noise(g.scale_vec(P, (1.0, 1.0, 1.0)), 1400.0, 2.0, 0.6)
    iris_col = g.mix(g.mr(rays, 0.3, 0.7), cfg["iris"], tuple(min(1.0, c * 2.2) for c in cfg["iris"]))
    sclera = g.mix(g.mul(g.mr(cosv, 0.6, 0.2), 0.35), (0.62, 0.58, 0.55), (0.55, 0.40, 0.38))
    eye_col = g.mix(iris_m, sclera, iris_col)
    eye_col = g.mix(g.mul(limbal, 0.7), eye_col, (0.02, 0.02, 0.02))
    eye_col = g.mix(pupil_m, eye_col, (0.004, 0.004, 0.004))
    eye = g.mr(g.attr("eye"), 0.3, 0.8)
    col = g.mix(eye, col, eye_col)
    # ambient occlusion baked into the colour lightly (UE adds its own AO)
    ao = g.mr(g.attr("ao"), 0.0, 1.0, 0.0, 1.0, smooth=False)
    col = g.mixmul(g.mr(ao, 1.0, 0.4, 0.0, 0.45), col, (0.55, 0.45, 0.43))

    # roughness: skin 0.52, T-zone shinier, lips moister, eyes wet, brows / stubble matte
    rough = g.add(0.52, g.mul(g.attr("tzone"), -0.10))
    rough = g.add(rough, g.mul(g.mr(fine, 0.3, 0.7), 0.08))
    rough = g.math("MAXIMUM", g.math("MINIMUM", rough, g.add(1.0, g.mul(g.attr("lip"), -0.62))), 0.0)
    rough = g.add(g.mul(rough, g.sub(1.0, eye)), g.mul(eye, 0.06))
    rough = g.add(rough, g.mul(brow, 0.12))
    orm = g.combine(ao, rough, 0.0)

    # normal detail: pores, fine wrinkles with age, brow strands, stubble
    bump = g.node("ShaderNodeBump")
    pores = g.voronoi(P, 1500.0)
    pore_h = g.mr(pores, 0.0, 0.25, 0.0, 1.0)
    h = g.add(g.mul(pore_h, 0.6), g.mul(g.noise(P, 600.0, 2.0, 0.6), 0.4))
    h = g.mul(h, g.sub(1.0, eye))
    if head_s["age"] > 0.3:
        fore = g.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Z")
        g._in(fore.inputs["Vector"], P)
        fore.inputs["Scale"].default_value = 170.0
        fore.inputs["Distortion"].default_value = 3.0
        fmask = g.mul(g.attr("tzone"), (head_s["age"] - 0.3) * 0.8)
        h = g.add(h, g.mul(g.mul(fore.outputs["Color"], fmask), 0.8))
    h = g.add(h, g.mul(brow, 0.7))
    g._in(bump.inputs["Height"], h)
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.0004
    bsdf = g.node("ShaderNodeBsdfPrincipled")
    g.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return {"color": g.emit(col), "orm": g.emit(orm), "normal": bsdf.outputs[0]}


def hair_graph(mat, name):
    cfg = hl.CAST[name]["hair"]
    g = G(mat)
    P = g.obj_pos()
    psi = g.attr("psi")
    style = cfg["style"]
    col = tuple(cfg["col"])
    # streaks along the flow: stretch a noise along X (combed back), shorter for short cuts
    stretch = {"slick": (1.0, 40.0, 40.0), "bun": (1.0, 45.0, 45.0), "crop": (1.0, 14.0, 14.0), "textured": (1.0, 6.0, 6.0),
               "horseshoe": (8.0, 12.0, 1.0), "buzz": (1.0, 1.0, 1.0), "crew": (1.0, 5.0, 5.0), "curly": (1.0, 1.0, 1.0)}[style]
    sp = g.scale_vec(P, stretch)
    streak = g.noise(sp, 260.0, 4.0, 0.6)
    fine = g.noise(g.scale_vec(P, stretch), 1200.0, 2.0, 0.5)
    lighter = tuple(min(1.0, c * 2.4 + 0.004) for c in col)
    c = g.mix(g.mr(streak, 0.35, 0.7), col, lighter)
    c = g.mix(g.mr(fine, 0.4, 0.7, 0.0, 0.5), c, tuple(x * 0.5 for x in col))
    if cfg.get("grey", 0.0) > 0:
        grey = g.mr(g.noise(P, 900.0, 2.0, 0.5), 0.55 - cfg["grey"] * 0.5, 0.62 - cfg["grey"] * 0.5)
        c = g.mix(g.mul(grey, cfg["grey"] * 1.4), c, (0.30, 0.29, 0.28))
    ao = g.attr("ao")
    c = g.mixmul(g.mr(ao, 1.0, 0.3, 0.0, 0.6), c, (0.4, 0.4, 0.4))
    rough = g.add(0.42, g.mul(g.mr(fine, 0.3, 0.7), 0.12))
    orm = g.combine(ao, rough, 0.0)
    bump = g.node("ShaderNodeBump")
    g._in(bump.inputs["Height"], g.add(g.mul(streak, 0.7), g.mul(fine, 0.3)))
    bump.inputs["Strength"].default_value = 0.6 if style not in ("buzz",) else 0.3
    bump.inputs["Distance"].default_value = 0.0008
    bsdf = g.node("ShaderNodeBsdfPrincipled")
    g.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _ = psi
    return {"color": g.emit(c), "orm": g.emit(orm), "normal": bsdf.outputs[0]}


def bake_object(ob, graph_fn, name, out_dir, aid, piece, res):
    bk.setup_bake_engine()
    paths = bk.texture_paths(out_dir, aid, piece)
    mat = bk.fresh_material(f"__bake_{aid}_{piece}")
    outs = graph_fn(mat, name)
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    for passname, kind, key, srgb in (("color", "EMIT", "BC", True), ("orm", "EMIT", "ORM", False), ("normal", "NORMAL", "N", False)):
        img = bk._float_image(f"__{aid}_{piece}_{key}", res)
        t0 = time.time()
        bk._bake(ob, [mat], [outs[passname]], img, kind, margin=max(4, res // 256))
        a = bk._pixels(img).copy()
        bk.save_png(a, paths[key], srgb=srgb)
        bpy.data.images.remove(img)
        log(f"    {aid}.{piece} {key}: {res}px {time.time() - t0:.0f}s")
    # role mask: nothing tinted (real colours are baked)
    m = np.zeros((256, 256, 4), np.float32)
    bk.save_png(m, paths["M"], srgb=False)
    bpy.data.materials.remove(mat)
    return paths


# --------------------------------------------------------------------------------------
# Export and data
# --------------------------------------------------------------------------------------


def export_fbx(ob, path):
    bk.deselect_all()
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH"}, axis_forward="X", axis_up="Z", apply_unit_scale=True, global_scale=1.0,
        apply_scale_options="FBX_SCALE_ALL", use_tspace=True, mesh_smooth_type="FACE", add_leaf_bones=False, use_mesh_modifiers=True,
        path_mode="STRIP", embed_textures=False, bake_anim=False)
    ob.select_set(False)


def ue(p):
    return [round(p[0] * 100, 1) + 0.0, round(-p[1] * 100, 1) + 0.0, round(p[2] * 100, 1) + 0.0]


def bounds_ue(ob):
    v = np.empty(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    a, b = ue(v.min(axis=0)), ue(v.max(axis=0))
    return {"Min": [min(a[i], b[i]) for i in range(3)], "Max": [max(a[i], b[i]) for i in range(3)]}


def anchor():
    return {"Bone": "head", "Offset": [0.0, 0.0, 0.0], "Rotation": [0.0, 0.0, 0.0], "Scale": 1.0, "AssumedBonePos": tb.bone_ue("head")}


def assign_single(ob, name):
    me = ob.data
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    me.materials.clear()
    me.materials.append(m)


def decimate(ob, ratio):
    if ratio >= 1.0:
        return
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.ratio = ratio
    bk.deselect_all()
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    ob.select_set(False)


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def build_character(name, res, do_bake, coll):
    t0 = time.time()
    aid = hl.ASSET_IDS[name]
    out_dir = os.path.join(OUT_ROOT, aid)
    os.makedirs(out_dir, exist_ok=True)
    head = hl.Head(name)
    pieces = []
    for piece, builder, graph, pres in (("Head", build_head_mesh, skin_graph, res), ("Hair", build_hair_mesh, hair_graph, res)):
        ob = builder(head, coll)
        if ob is None:
            continue
        bk.uv_unwrap(ob, pres, 62.0, 4, cache_key=f"{aid}_{piece}")
        if do_bake:
            bake_object(ob, graph, name, out_dir, aid, piece, pres)
        assign_single(ob, f"M_{aid}_{piece}")
        export_fbx(ob, os.path.join(out_dir, f"SM_{aid}_{piece}.fbx"))
        pieces.append({"Name": piece, "Kind": "Static", "Slots": [f"M_{aid}_{piece}"], "Bounds": bounds_ue(ob), "Triangles": tri_count(ob),
                       "TextureSize": pres, "Anchor": anchor()})
    mins = [p["Bounds"]["Min"] for p in pieces]
    maxs = [p["Bounds"]["Max"] for p in pieces]
    cfg = hl.CAST[name]
    entry = {
        "Pieces": pieces,
        "Points": {"Pivot": [0.0, 0.0, 0.0]},
        "Bounds": {"Min": [min(m[i] for m in mins) for i in range(3)], "Max": [max(m[i] for m in maxs) for i in range(3)]},
        "Anchor": anchor(),
        "Outfit": {"Outfit": "Head", "Tint": "Head", "TintRoughness": 0.5, "RoughnessDetail": 1.0, "TintMetallic": 0.0},
        "SourceDir": "Characters/Heads",
        "Character": name,
        "Notes": "Original procedural head (Tools/Blender/heads). Unreal cm, character space; origin = the head bone pivot of the assumed "
                 "UE5 Manny reference pose. UAirsoftTeamGearComponent::ApplyHead attaches every piece to the head bone (tune with "
                 "airsoft.gear.tune " + aid + "). Colours are baked; the role mask is empty.",
    }
    log(f"  {name}: done in {time.time() - t0:.0f}s ({cfg['title']})")
    return aid, entry


def write_json(entries):
    data = {"Version": 1, "Assets": {}}
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH) as f:
            data = json.load(f)
    data.setdefault("Assets", {})
    for aid, e in entries.items():
        old = data["Assets"].get(aid)
        if old:  # keep live-tuned anchors
            for k in ("Offset", "Rotation", "Scale"):
                if k in old.get("Anchor", {}):
                    e["Anchor"][k] = old["Anchor"][k]
        data["Assets"][aid] = e
    data["Heads"] = {
        "Cast": {name: aid for name, aid in hl.ASSET_IDS.items() if not hl.CAST[name].get("crew")},
        "Crew": [aid for name, aid in hl.ASSET_IDS.items() if hl.CAST[name].get("crew")],
        "HideHair": ["HairSlick"],
        "Notes": "Story characters by name (Andrew, and the bosses by their Campaign.json names). Ledger crew heads are picked by seed. "
                 "Putting a head on removes the suit's own haircut (HideHair).",
    }
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    log("wrote", DATA_PATH)


# --------------------------------------------------------------------------------------
# Preview, renders
# --------------------------------------------------------------------------------------


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"


def noir_rig(target=(0.0, 0.0, 1.62), scale=1.0):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    world = bpy.data.worlds.new("Noir")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.012, 0.017, 0.022, 1.0)
    scn.world = world
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.sensor_width = 36
    scn.collection.objects.link(cam)
    scn.camera = cam
    T = Vector(target)

    def area(name, color, energy, size, off, sy=None):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "RECTANGLE"
        ld.color = color
        ld.energy = energy * scale * scale
        ld.size = size * scale
        ld.size_y = (sy or size) * scale
        lo = bpy.data.objects.new(name, ld)
        scn.collection.objects.link(lo)
        lo.location = T + Vector(off) * scale
        studio.look_at(lo, T)
        return lo

    area("Key", (1.0, 0.85, 0.70), 60.0, 0.8, (1.4, -1.0, 0.7), 0.6)
    area("RimL", (0.35, 0.80, 1.0), 70.0, 0.25, (-1.2, 1.1, 0.4), 1.2)
    area("RimR", (1.0, 0.25, 0.55), 40.0, 0.25, (-1.2, -1.2, 0.3), 1.2)
    area("Fill", (0.5, 0.65, 0.95), 6.0, 1.5, (1.6, 1.4, -0.1))
    wall = bpy.data.objects.new("Wall", bpy.data.meshes.new("Wall"))
    wall.data.from_pydata([(-3, -20, -5), (-3, 20, -5), (-3, 20, 10), (-3, -20, 10)], [], [(0, 1, 2, 3)])
    wm = bpy.data.materials.new("Wall")
    b = wm.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.02, 0.04, 0.05, 1)
    b.inputs["Roughness"].default_value = 0.9
    wall.data.materials.append(wm)
    scn.collection.objects.link(wall)
    return cam


def place_cam(cam, target, view_dir, dist, lens):
    cam.data.lens = lens
    cam.location = Vector(target) + Vector(view_dir).normalized() * dist
    studio.look_at(cam, target)


def render(path, res, samples):
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.cycles.samples = samples
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.03
    scn.cycles.max_bounces = 6
    scn.cycles.use_denoising = True
    scn.render.image_settings.file_format = "PNG"
    scn.render.image_settings.color_mode = "RGB"
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)


def save_jpg(png, jpg, quality=92):
    os.makedirs(os.path.dirname(jpg), exist_ok=True)
    from PIL import Image
    Image.open(png).convert("RGB").save(jpg, quality=quality, subsampling=0)


def preview(names):
    reset_scene()
    coll = bpy.data.collections.new("P")
    bpy.context.scene.collection.children.link(coll)
    os.makedirs(SCRATCH, exist_ok=True)
    skin = bpy.data.materials.new("PV_skin")
    b = skin.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.45, 0.32, 0.27, 1)
    b.inputs["Roughness"].default_value = 0.5
    hairm = bpy.data.materials.new("PV_hair")
    b = hairm.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.02, 0.016, 0.013, 1)
    for i, name in enumerate(names):
        head = hl.Head(name)
        hob = build_head_mesh(head, coll, h=0.0018)
        hob.data.materials.append(skin)
        hair = build_hair_mesh(head, coll, h=0.0022 if len(names) > 1 else 0.0014)
        obs = [hob] + ([hair] if hair else [])
        if hair:
            hair.data.materials.append(hairm)
        for o in obs:
            o.location = (0.0, (i - (len(names) - 1) / 2) * 0.30, 0.0)
    cam = noir_rig((0.0, 0.0, 0.05))
    w = max(1, len(names))
    for vname, vd in (("front", (1.0, 0.0, 0.05)), ("tq", (0.75, -0.65, 0.08)), ("side", (0.0, -1.0, 0.03))):
        place_cam(cam, (0.0, 0.0, 0.05), vd, 0.55 + 0.32 * w, 50)
        p = os.path.join(SCRATCH, f"pv_{vname}.png")
        render(p, (min(3200, 520 * w), 640), 12)
        log("wrote", p)
    if len(names) == 1:
        place_cam(cam, (0.10, 0.0, 0.055), (0.85, -0.45, 0.05), 0.30, 50)
        p = os.path.join(SCRATCH, "pv_close.png")
        render(p, (800, 640), 16)
        log("wrote", p)


# -- final renders (baked textures, skin with subsurface) ----------------------------------


def head_material(name, paths, skin=True):
    m = bk.fresh_material(name)
    g = G(m)
    out = next(n for n in g.nodes if n.type == "OUTPUT_MATERIAL")
    bsdf = g.node("ShaderNodeBsdfPrincipled")
    g.links.new(bsdf.outputs[0], out.inputs["Surface"])
    uv = g.node("ShaderNodeUVMap", uv_map="UVMap")
    tex = {}
    for k, cs in (("BC", "sRGB"), ("ORM", "Non-Color"), ("N", "Non-Color")):
        t = g.node("ShaderNodeTexImage", image=bk._load(paths[k], cs))
        g.links.new(uv.outputs["UV"], t.inputs["Vector"])
        tex[k] = t
    g.links.new(tex["BC"].outputs["Color"], bsdf.inputs["Base Color"])
    sep = g.node("ShaderNodeSeparateColor")
    g.links.new(tex["ORM"].outputs["Color"], sep.inputs[0])
    g.links.new(sep.outputs[1], bsdf.inputs["Roughness"])
    nsep = g.node("ShaderNodeSeparateColor")
    g.links.new(tex["N"].outputs["Color"], nsep.inputs[0])
    flip = g.combine(nsep.outputs[0], g.sub(1.0, nsep.outputs[1]), nsep.outputs[2])
    nm = g.node("ShaderNodeNormalMap")
    g.links.new(flip, nm.inputs["Color"])
    g.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if skin:
        bsdf.inputs["Subsurface Weight"].default_value = 0.22
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.38, 0.20)
        bsdf.inputs["Subsurface Scale"].default_value = 0.004
        bsdf.inputs["Specular IOR Level"].default_value = 0.45
    else:
        bsdf.inputs["Specular IOR Level"].default_value = 0.6
    return m


def import_head(name, coll, offset=(0, 0, 0), rot_z=0.0):
    aid = hl.ASSET_IDS[name]
    out_dir = os.path.join(OUT_ROOT, aid)
    obs = []
    for piece in ("Head", "Hair"):
        f = os.path.join(out_dir, f"SM_{aid}_{piece}.fbx")
        if not os.path.exists(f):
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=f, axis_forward="X", axis_up="Z")
        for o in [o for o in bpy.data.objects if o not in before]:
            if o.type != "MESH":
                bpy.data.objects.remove(o)
                continue
            for c in list(o.users_collection):
                c.objects.unlink(o)
            coll.objects.link(o)
            o.matrix_world = Matrix.Translation(Vector(offset)) @ Matrix.Rotation(rot_z, 4, "Z") @ Matrix.Translation(Vector(tuple(hl.HEAD_PIVOT)))
            paths = bk.texture_paths(out_dir, aid, piece)
            o.data.materials.clear()
            o.data.materials.append(head_material(f"R_{aid}_{piece}", paths, skin=piece == "Head"))
            obs.append(o)
    return obs


SUITS = {  # colourway, shirt, tie per character (Gear.json Suit colourways)
    "Andrew": ("Charcoal", "Black", "Black"), "Kade": ("MidnightNavy", "White", "Black"), "Dorian Sloane": ("Oxblood", "Black", "Wine"),
    "Mara Voss": ("Black", "Black", "Black"), "Silas Varga": ("Oxblood", "White", "Graphite"),
    "Ledger A": ("MidnightNavy", "Black", "Black"), "Ledger B": ("MidnightNavy", "White", "Black"), "Ledger C": ("MidnightNavy", "Black", "Graphite"),
    "Ledger D": ("MidnightNavy", "White", "Black"),
}


def suit_module():
    import build_suit as bs  # Tools/Blender/gear
    return bs


def dress_bust(coll, name, off, rz):
    bs = suit_module()
    suit, shirt, tie = SUITS[name]
    try:
        return bs.import_asset("Suit", coll, {"P": bs.cw("Suit", suit), "S": bs.cw("Shirt", shirt), "A": bs.cw("Tie", tie)}, off, rz, 1024)
    except Exception as e:  # suit not generated: heads only
        log("  suit not available:", e)
        return []


def render_lineup(samples, res=(3840, 2160)):
    reset_scene()
    coll = bpy.data.collections.new("Lineup")
    bpy.context.scene.collection.children.link(coll)
    bs = suit_module()
    base = bs.mannequin_trimmed(coll, (0.012, 0.012, 0.013))
    names = list(hl.ASSET_IDS)
    n = len(names)
    gap = 0.50
    for i, name in enumerate(names):
        y = (i - (n - 1) / 2) * gap
        off = (0.0, y, 0.0)
        R = math.radians(-12.0 + 24.0 * (i % 2))
        man = bpy.data.objects.new("Man", base.data)
        coll.objects.link(man)
        man.matrix_world = Matrix.Translation(Vector(off)) @ Matrix.Rotation(R, 4, "Z")
        dress_bust(coll, name, off, R)
        import_head(name, coll, off, R)
    coll.objects.unlink(base)
    cam = noir_rig((0.0, 0.0, 1.55), scale=2.6)
    place_cam(cam, (0.0, 0.0, 1.50), (1.0, 0.0, 0.02), 6.6, 85)
    png = os.path.join(SCRATCH, "_Heads_Lineup.png")
    t0 = time.time()
    render(png, res, samples)
    save_jpg(png, os.path.join(RENDER_DIR, "_Lineup_4K.jpg"))
    log(f"wrote {RENDER_DIR}/_Lineup_4K.jpg ({time.time() - t0:.0f}s)")


def render_portrait(samples, res=(1800, 2250)):
    reset_scene()
    coll = bpy.data.collections.new("Portrait")
    bpy.context.scene.collection.children.link(coll)
    bs = suit_module()
    bs.mannequin_trimmed(coll, (0.012, 0.012, 0.013))
    dress_bust(coll, "Andrew", (0, 0, 0), 0.0)
    import_head("Andrew", coll)
    cam = noir_rig((0.0, 0.0, 1.62), scale=1.0)
    place_cam(cam, (0.02, 0.0, 1.58), (0.85, -0.52, 0.04), 1.05, 70)
    png = os.path.join(SCRATCH, "Andrew_Portrait.png")
    t0 = time.time()
    render(png, res, samples)
    save_jpg(png, os.path.join(RENDER_DIR, "Andrew_Portrait.jpg"))
    log(f"wrote {RENDER_DIR}/Andrew_Portrait.jpg ({time.time() - t0:.0f}s)")


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    res = int(argv[argv.index("--res") + 1]) if "--res" in argv else 2048
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 64
    skip = {argv[i + 1] for i, a in enumerate(argv) if a in ("--res", "--samples")}
    only = [a for a in argv if not a.startswith("--") and a not in skip]
    names = [n for n in hl.ASSET_IDS if not only or n in only or n.split()[0] in only]
    if "--preview" in flags:
        preview(names)
        return
    if "--renders-only" in flags:
        if "--portrait-only" not in flags:
            render_lineup(samples)
        render_portrait(samples)
        return
    entries = {}
    for name in names:
        reset_scene()
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
        log(f"== {name}")
        aid, e = build_character(name, res, "--no-bake" not in flags, coll)
        entries[aid] = e
    if entries:
        write_json(entries)
    if "--no-render" not in flags:
        render_lineup(samples)
        render_portrait(samples)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--" in a:
        a = a[a.index("--") + 1:]
    main(a)
