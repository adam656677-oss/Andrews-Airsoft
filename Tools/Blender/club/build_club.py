"""Velvet Club + The Armory prop generator.

    python build_club.py -- [AssetId ...] [--res 4096|2048|1024] [--no-render] [--lineup club|armory|both]
    blender -b -P build_club.py -- ...

Builds every prop listed in club_assets.py / armory_assets.py: one FBX per piece under
SourceAssets/Props/<AssetId>/, baked BC/N/ORM/M textures, a 1920x1080 render under
Docs/Renders/PropsClub/, and the asset's entry in Content/Airsoft/Data/PropsClub.json.
Deterministic: every noise is seeded by position, every random choice by a fixed seed.
"""

import os
import sys
import time
import math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector as V  # noqa: E402
import propkit as pk  # noqa: E402
from club_registry import ASSETS, LINEUPS  # noqa: E402
import club_assets  # noqa: F401,E402  (registers assets)
import armory_assets  # noqa: F401,E402
import vehicles  # noqa: F401,E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT, "SourceAssets", "Props")
RENDERS = os.path.join(ROOT, "Docs", "Renders", "PropsClub")
JSON_PATH = os.path.join(ROOT, "Content", "Airsoft", "Data", "PropsClub.json")
CACHE = os.environ.get("CLUB_CACHE", os.path.join(os.environ.get("TMPDIR", "/tmp"), "club_cache"))


def log(*a):
    print(*a, flush=True)


def make_decal_images():
    """Text masks used by decal recipes (licence plates, crate stencils, engraved plaque)."""
    from club_registry import font
    specs = {
        "PLATE": ("VLV 707", font("BigShoulders-Bold.ttf"), 512, 128, 0.12),
        "STENCIL": ("7.62 x 39 mm\nCARTRIDGES  1080\nLOT  4-71   AIRSOFT ARMORY", font("BigShoulders-Bold.ttf"), 1024, 512, 0.06),
        "PLAQUE": ("THE  ARMORY\nBAY  No. 1", font("LibreBaskerville-Regular.ttf"), 1024, 320, 0.10),
    }
    for name, (txt, f, w, h, pad) in specs.items():
        m = pk.text_mask(txt, f, w, h, pad=pad)
        if name == "STENCIL":
            # stencil bridges: thin vertical gaps through the letters
            xs = np.arange(w)
            bridge = ((xs % 37) < 3).astype(np.float32)
            m = m * (1.0 - bridge[None, :] * 0.0)
        if name == "PLAQUE":
            # engraved double border
            yy, xx = np.mgrid[0:h, 0:w]
            d = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy))
            m = np.maximum(m, ((d > 10) & (d < 15)).astype(np.float32))
            m = np.maximum(m, ((d > 20) & (d < 22)).astype(np.float32))
        a = np.zeros((h, w, 4), np.float32)
        a[..., 0] = a[..., 1] = a[..., 2] = m
        a[..., 3] = 1.0
        pk.np_to_image(name, a)


def build(aid, res_cap, do_render=True, render_res=(1920, 1080), samples=40):
    t0 = time.time()
    spec = ASSETS[aid]
    pk.reset_scene()
    make_decal_images()
    A = pk.Asset(aid, **spec["kw"])
    spec["fn"](A)
    out_dir = os.path.join(OUT, aid)
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith((".fbx", ".png")):
            os.remove(os.path.join(out_dir, f))
    objs = A.finish(out_dir)
    pieces_json = []
    tris = {}
    tex = {}
    scale = res_cap / 4096.0
    for pname, ob in objs.items():
        pc = A.pieces[pname]
        res = max(128, int(pc.res * scale))
        if pc.tileable:
            pk.unwrap(ob, res, world_scale=2.0)
            for s in ob.material_slots:
                base = s.material.name[2:].split("_")[0]
                s.material.name = "MI_" + base[:1].upper() + base[1:]
            slots = [s.material.name for s in ob.material_slots]
            pv = {}
        else:
            paths = pk.bake_piece(ob, A, pc, res, out_dir, log=log)
            slot = pc.slot or f"M_{aid}_{pname}"
            slots = [slot]
            pk.assign_single(ob, pk.textured_material(slot, paths))
            tex[pname] = res
        tris[pname] = pk.tri_count(ob)
        pk.export_fbx(ob, os.path.join(out_dir, f"SM_{aid}_{pname}.fbx"))
        if pc.tileable:
            aux = bpy.data.images.get("AUX")
            if aux is not None:
                aux.generated_color = (0.0, 1.0, 0.0, 1.0)
                aux.source = "GENERATED"
            for s in ob.material_slots:
                for n in s.material.node_tree.nodes:
                    if n.bl_idname == "ShaderNodeOutputMaterial":
                        n.is_active_output = n.name == "OUT_PV"
        if not pc.tileable:
            pv = A.preview.get(pname, {})
            if pc.glass:
                pv = dict(pv)
                pv.setdefault("glass", {})
            pk.assign_single(ob, pk.textured_material(slots[0] + "_PV", paths, pv))
        pieces_json.append({"Name": pname, "Kind": pc.kind, "Slots": slots})
    lo, hi = pk.bbox_of(objs.values())
    entry = {
        "Group": A.group,
        "Pieces": pieces_json,
        "Points": {k: pk.ue(v) for k, v in A.points.items()},
        "Bounds": {"Min": pk.ue((lo.x, hi.y, lo.z)), "Max": pk.ue((hi.x, lo.y, hi.z))},
        "Collision": A.collision,
        "Triangles": tris,
        "TextureSize": tex,
    }
    pk.update_json(JSON_PATH, aid, entry)
    os.makedirs(CACHE, exist_ok=True)
    for o in objs.values():
        o["pv_view"] = list(A.view or (1.0, -0.62, 0.38))
        o["pv_lens"] = A.lens
        o["pv_margin"] = A.margin
    bpy.data.libraries.write(os.path.join(CACHE, aid + ".blend"), set(objs.values()), fake_user=True, path_remap="ABSOLUTE")
    log(f"  {aid}: tris {tris} tex {tex} build {time.time() - t0:.0f}s")
    if do_render:
        st = pk.setup_studio()
        for L in A.lights:
            L(bpy.context.scene)
        view = A.view or (1.0, -0.62, 0.38)
        pk.frame(st, lo, hi, view=view, lens=A.lens, margin=A.margin)
        t1 = time.time()
        pk.render(os.path.join(RENDERS, aid + ".png"), render_res, samples)
        log(f"  {aid}: render {time.time() - t1:.0f}s")
    return entry


def render_only(aid, render_res, samples):
    pk.reset_scene()
    path = os.path.join(CACHE, aid + ".blend")
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
    objs = [o for o in dst.objects if o is not None]
    for o in objs:
        bpy.context.scene.collection.objects.link(o)
    lo, hi = pk.bbox_of(objs)
    st = pk.setup_studio()
    o0 = objs[0]
    pk.frame(st, lo, hi, view=tuple(o0.get("pv_view", (1.0, -0.62, 0.38))), lens=o0.get("pv_lens", 60), margin=o0.get("pv_margin", 1.1))
    t1 = time.time()
    pk.render(os.path.join(RENDERS, aid + ".png"), render_res, samples)
    log(f"  {aid}: render {time.time() - t1:.0f}s")


def lineup(group, res=(3840, 2160), samples=48):
    pk.reset_scene()
    rows = LINEUPS[group]
    placed = []
    gap = 0.5
    zoff = 0.0
    row_objs = []
    y_cursor = 0.0
    for r, row in enumerate(rows):
        items = []
        for aid in row:
            path = os.path.join(CACHE, aid + ".blend")
            if not os.path.exists(path):
                continue
            with bpy.data.libraries.load(path, link=False) as (src, dst):
                dst.objects = list(src.objects)
            objs = [o for o in dst.objects if o is not None]
            for o in objs:
                bpy.context.scene.collection.objects.link(o)
            lo, hi = pk.bbox_of(objs)
            items.append((aid, objs, lo, hi))
        if not items:
            continue
        depth = max(hi.x - lo.x for _, _, lo, hi in items)
        total = sum(hi.y - lo.y for _, _, lo, hi in items) + gap * (len(items) - 1)
        y = total / 2
        for aid, objs, lo, hi in items:
            w = hi.y - lo.y
            off = V((y_cursor + depth / 2 - (lo.x + hi.x) / 2, y - w / 2 - (lo.y + hi.y) / 2, -lo.z))
            for o in objs:
                o.location += off
            placed.extend(objs)
            y -= w + gap
        y_cursor += depth + gap * 1.6
    st = pk.setup_studio()
    lo, hi = pk.bbox_of(placed)
    pk.frame(st, lo, hi, view=(1.0, -0.12, 0.42), lens=50, margin=1.03)
    pk.render(os.path.join(RENDERS, "_Lineup_4K.png" if group == "club" else f"_Lineup_{group.capitalize()}_4K.png"), res, samples)


def main(argv):
    res = 4096
    if "--res" in argv:
        res = int(argv[argv.index("--res") + 1])
    flags = set(a for a in argv if a.startswith("--"))
    ids = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--res", "--lineup", "--samples"))]
    do_render = "--no-render" not in flags
    rr = (1920, 1080) if res >= 2048 or "--full-render" in flags else (768, 432)
    samples = 16 if res >= 2048 else 14
    if "--samples" in argv:
        samples = int(argv[argv.index("--samples") + 1])
    if "--render-only" in flags:
        for aid in ids or list(ASSETS):
            render_only(aid, rr, samples)
    elif "--lineup-only" not in flags:
        for aid in ids or list(ASSETS):
            if aid not in ASSETS:
                log("unknown asset", aid)
                continue
            log(f"== {aid}")
            build(aid, res, do_render, rr, samples)
    if "--lineup" in flags:
        g = argv[argv.index("--lineup") + 1]
        for grp in (["club", "armory"] if g == "both" else [g]):
            lineup(grp, (3840, 2160) if res >= 2048 else (1920, 1080), 48 if res >= 2048 else 24)


if __name__ == "__main__":
    argv = sys.argv[1:]
    argv = argv[argv.index("--") + 1 :] if "--" in argv else argv
    main(argv)
