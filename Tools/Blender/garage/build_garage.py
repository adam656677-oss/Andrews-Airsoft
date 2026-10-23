"""Nightjar Garage kit generator (parking-garage pieces and props).

    python build_garage.py -- [AssetId ...] [--res 4096|2048|1024] [--no-render] [--lineup] [--lineup-only]
                             [--samples N] [--render-only]
    blender -b -P build_garage.py -- ...

Builds every asset in garage_assets.py: one FBX per piece under SourceAssets/Props/<AssetId>/, baked
BC/N/ORM/M textures for unique pieces (tileable pieces use MI_<Material> slots with UVs at 1 UV = 2 m),
a 1920x1080 product shot at Docs/Renders/Garage/<AssetId>.jpg (PNG masters stay in Saved/Renders/Garage,
git-ignored), the 3840x2160 Docs/Renders/Garage/_Lineup_4K.jpg, and the asset's entry in
Content/Airsoft/Data/PropsGarage.json (category Props: the editor importer and the layout checker
pick up every Props*.json). Deterministic (fixed seeds).
"""

import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
sys.path.insert(0, os.path.join(HERE, "..", "environment"))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Matrix, Vector as V  # noqa: E402

import propkit as pk  # noqa: E402
import garage_assets as GA  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT, "SourceAssets", "Props")
RENDERS = os.path.join(ROOT, "Docs", "Renders", "Garage")
PNG_DIR = os.path.join(ROOT, "Saved", "Renders", "Garage")
JSON_PATH = os.path.join(ROOT, "Content", "Airsoft", "Data", "PropsGarage.json")
CACHE = os.environ.get("GARAGE_CACHE", os.path.join(os.environ.get("TMPDIR", "/tmp"), "garage_cache"))
MAT_DIR = os.path.join(ROOT, "SourceAssets", "Materials")


def log(*a):
    print(*a, flush=True)


def to_jpg(png, jpg, quality=90):
    from PIL import Image
    os.makedirs(os.path.dirname(jpg), exist_ok=True)
    Image.open(png).convert("RGB").save(jpg, quality=quality, subsampling=0, optimize=True)
    log("  wrote", os.path.relpath(jpg, ROOT))


def tile_meters(mid):
    try:
        return float(json.load(open(os.path.join(ROOT, "Content", "Airsoft", "Data", "Materials.json")))["Materials"][mid]["TileMeters"])
    except Exception:
        return 2.0


def library_material(mid):
    """Preview material for an MI_<mid> slot using the real tileable textures (1 UV = 2 m)."""
    from envlib import bl as envbl
    if not os.path.exists(os.path.join(MAT_DIR, mid, f"T_{mid}_BC.png")):
        return None
    return envbl.lib_material(mid, uv_scale=2.0 / tile_meters(mid), name=f"MI_{mid}_PV")


def build(aid, res_cap, do_render=True, render_res=(1920, 1080), samples=40):
    t0 = time.time()
    spec = GA.ASSETS[aid]
    pk.reset_scene()
    GA.make_images()
    A = pk.Asset(aid, **spec["kw"])
    spec["fn"](A)
    out_dir = os.path.join(OUT, aid)
    os.makedirs(out_dir, exist_ok=True)
    objs = A.finish(out_dir)
    pieces_json, tris, tex = [], {}, {}
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
        else:
            paths = pk.bake_piece(ob, A, pc, res, out_dir, log=log)
            slot = pc.slot or f"M_{aid}_{pname}"
            slots = [slot]
            pk.assign_single(ob, pk.textured_material(slot, paths))
            tex[pname] = res
        tris[pname] = pk.tri_count(ob)
        pk.export_fbx(ob, os.path.join(out_dir, f"SM_{aid}_{pname}.fbx"))
        if pc.tileable:     # preview: the real library textures
            for i, s in enumerate(ob.material_slots):
                m = library_material(s.material.name[3:])
                if m is not None:
                    ob.material_slots[i].material = m
        else:
            pv = dict(A.preview.get(pname, {}))
            if pc.glass:
                pv.setdefault("glass", {})
            pk.assign_single(ob, pk.textured_material(slots[0] + "_PV", paths, pv))
        pe = {"Name": pname, "Kind": pc.kind, "Slots": slots}
        if pc.emissive and pc.kind != "Emissive":
            pe["Kind"] = "Emissive"
        pieces_json.append(pe)
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
    if getattr(A, "layout", None):
        entry["Layout"] = A.layout
    if getattr(A, "tint_variants", None):
        entry["TintVariants"] = A.tint_variants
    pk.update_json(JSON_PATH, aid, entry)
    os.makedirs(CACHE, exist_ok=True)
    for o in objs.values():
        o["pv_flip"] = 1 if getattr(A, "pv_flip", False) else 0
        o["pv_view"] = list(A.view or (1.0, -0.62, 0.38))
        o["pv_lens"] = A.lens
        o["pv_margin"] = A.margin
    bpy.data.libraries.write(os.path.join(CACHE, aid + ".blend"), set(objs.values()), fake_user=True, path_remap="ABSOLUTE")
    log(f"  {aid}: tris {tris} tex {tex} bounds {entry['Bounds']} build {time.time() - t0:.0f}s")
    if do_render:
        obl = list(objs.values())
        if getattr(A, "pv_flip", False):
            lo, hi = flip(obl)
        render_shot(aid, obl, lo, hi, A.view or (1.0, -0.62, 0.38), A.lens, A.margin, render_res, samples)
    return entry


def flip(objs):
    """Ceiling pieces are shown upside down on the studio floor (their visible underside up)."""
    R = Matrix.Rotation(math.pi, 4, "X")
    for o in objs:
        o.matrix_world = R @ o.matrix_world
    bpy.context.view_layer.update()
    lo, hi = pk.bbox_of(objs)
    for o in objs:
        o.location.z -= lo.z
    bpy.context.view_layer.update()
    return pk.bbox_of(objs)


def render_shot(aid, objs, lo, hi, view, lens, margin, render_res, samples):
    st = pk.setup_studio()
    pk.frame(st, lo, hi, view=view, lens=lens, margin=margin)
    t1 = time.time()
    png = os.path.join(PNG_DIR, aid + ".png")
    pk.render(png, render_res, samples)
    to_jpg(png, os.path.join(RENDERS, aid + ".jpg"))
    log(f"  {aid}: render {time.time() - t1:.0f}s")


def render_only(aid, render_res, samples):
    pk.reset_scene()
    path = os.path.join(CACHE, aid + ".blend")
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
    objs = [o for o in dst.objects if o is not None]
    for o in objs:
        bpy.context.scene.collection.objects.link(o)
    lo, hi = pk.bbox_of(objs)
    o0 = objs[0]
    if o0.get("pv_flip"):
        lo, hi = flip(objs)
    render_shot(aid, objs, lo, hi, tuple(o0.get("pv_view", (1.0, -0.62, 0.38))), o0.get("pv_lens", 60),
                o0.get("pv_margin", 1.1), render_res, samples)


def lineup(res=(3840, 2160), samples=48):
    pk.reset_scene()
    placed = []
    gap = 0.45
    y_cursor = 0.0
    for r, row in enumerate(GA.LINEUP):
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
                for s in o.material_slots:
                    if s.material is None or not s.material.use_nodes:
                        continue
                    for n in s.material.node_tree.nodes:
                        if n.bl_idname == "ShaderNodeTexImage" and n.image is not None and n.image.size[0] > 1024:
                            n.image.scale(1024, 1024)
            lo, hi = pk.bbox_of(objs)
            if objs and objs[0].get("pv_flip"):
                lo, hi = flip(objs)
            if aid == "Garage_Ramp":      # long piece: show it side-on along the back row
                R = Matrix.Rotation(math.radians(-90), 4, "Z")
                for o in objs:
                    o.matrix_world = R @ o.matrix_world
                bpy.context.view_layer.update()
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
    bpy.context.view_layer.update()
    st = pk.setup_studio()
    lo, hi = pk.bbox_of(placed)
    pk.frame(st, lo, hi, view=(1.0, -0.1, 0.5), lens=50, margin=1.03)
    png = os.path.join(PNG_DIR, "_Lineup_4K.png")
    pk.render(png, res, samples)
    to_jpg(png, os.path.join(RENDERS, "_Lineup_4K.jpg"))


def main(argv):
    res = 4096
    if "--res" in argv:
        res = int(argv[argv.index("--res") + 1])
    flags = set(a for a in argv if a.startswith("--"))
    ids = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--res", "--samples"))]
    do_render = "--no-render" not in flags
    rr = (1920, 1080) if res >= 2048 or "--full-render" in flags else (768, 432)
    samples = 10 if res >= 2048 else 12
    if "--samples" in argv:
        samples = int(argv[argv.index("--samples") + 1])
    if "--render-only" in flags:
        for aid in ids or list(GA.ASSETS):
            render_only(aid, rr, samples)
    elif "--lineup-only" not in flags:
        for aid in ids or list(GA.ASSETS):
            if aid not in GA.ASSETS:
                log("unknown asset", aid)
                continue
            log(f"== {aid}")
            build(aid, res, do_render, rr, samples)
    if "--lineup" in flags or "--lineup-only" in flags:
        lineup((3840, 2160) if res >= 2048 else (1280, 720), max(samples, 24))


if __name__ == "__main__":
    argv = sys.argv[1:]
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv
    main(argv)
