"""
Render-only pass for weapons and attachments: product shots and lineups straight from the
exported FBX files and baked textures (no re-modelling, no re-baking, nothing re-exported).

    python Tools/Blender/render_imported.py -- M249 G18 RedDot          # product shots
    python Tools/Blender/render_imported.py -- --lineup weapons          # 3840x2160 lineup
    python Tools/Blender/render_imported.py -- --lineup attachments
    flags: --samples N (default 16), --threads N (default: all cores)

It uses the same studio rig, framing, tint colours and row layout as
Tools/Blender/weapons/build_weapons.py, so the images match the generator's own renders.
Material slots are matched to the conventions' texture sets:
    M_<Id>_<Piece>  -> T_<Id>_<Piece>_BC/N/ORM/M.png next to the FBX
    Glass / Reticle -> the generator's plain glass / emissive reticle materials
Missing textures are an error (no magenta renders).
"""

import ast
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "common"))
sys.path.insert(0, os.path.join(HERE, "weapons"))

import bpy  # noqa: E402,I001

import bakekit as bk  # noqa: E402
import build_weapons as bw  # noqa: E402  (definitions only; main() is not run)
import studio  # noqa: E402

ROOT = bw.ROOT
SOURCE_DIR = bw.SOURCE_DIR
RENDER_DIR = bw.RENDER_DIR


# --------------------------------------------------------------------------------------
# Default finish (preview tint) per asset, read from the generator source
# --------------------------------------------------------------------------------------


def _material_overrides():
    """{function name: (mats overrides, tints overrides)} from g.mats.update(...) /
    g.mats["X"] = "y" statements, following calls into shared helpers (glock(), ...)."""
    tree = ast.parse(open(bw.__file__).read())
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

    def scan(fn, seen):
        mats, tints = {}, {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Attribute) and f.attr == "update" and isinstance(f.value, ast.Attribute) and f.value.attr in ("mats", "tints"):
                    d = mats if f.value.attr == "mats" else tints
                    for kw in node.keywords:
                        try:
                            d[kw.arg] = ast.literal_eval(kw.value)
                        except ValueError:
                            pass
                elif isinstance(f, ast.Name) and f.id in funcs and f.id not in seen:
                    m2, t2 = scan(funcs[f.id], seen | {f.id})
                    for k, v in m2.items():
                        mats.setdefault(k, v)
                    for k, v in t2.items():
                        tints.setdefault(k, v)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute) and t.value.attr in ("mats", "tints"):
                        try:
                            (mats if t.value.attr == "mats" else tints)[ast.literal_eval(t.slice)] = ast.literal_eval(node.value)
                        except ValueError:
                            pass
        return mats, tints

    return {name: scan(fn, {name}) for name, fn in funcs.items()}


_OVR = None


def tints_for(gid):
    """Same rule as build_weapons.tints_for(): first group with a role sets that role."""
    global _OVR
    if _OVR is None:
        _OVR = _material_overrides()
    kind, fn = bw.BUILDERS[gid]
    g = bw.Gun(gid, kind)
    m, t = _OVR.get(fn.__name__, ({}, {}))
    g.mats.update(m)
    g.tints.update(t)
    out = {}
    for group, role in g.tints.items():
        if role and group in g.mats and g.mats[group] in bw.PALETTE:
            out.setdefault(role, tuple(c / bk.TINT_GREY for c in bw.PALETTE[g.mats[group]]))
    return out


# --------------------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------------------


def import_asset(gid, coll):
    kind = bw.BUILDERS[gid][0]
    category = "Attachments" if kind == "Attachment" else "Weapons"
    d = os.path.join(SOURCE_DIR, category, gid)
    files = sorted(glob.glob(os.path.join(d, f"SM_{gid}_*.fbx")))
    if not files:
        raise RuntimeError(f"{gid}: no FBX in {d}")
    tints = tints_for(gid)
    objs = []
    for f in files:
        piece = os.path.basename(f)[len(f"SM_{gid}_") : -4]
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=f, axis_forward="X", axis_up="Z")
        new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            coll.objects.link(o)
            if piece == "Glass":
                mat = bk.plain_material(f"RG_{gid}_Glass", bw.PALETTE["glass"], 0.03, 0.0, alpha=0.25)
            elif piece == "Reticle":
                mat = bk.plain_material(f"RG_{gid}_Reticle", (1.0, 0.05, 0.03), 0.4, 0.0, emission=(1.0, 0.05, 0.02))
            else:
                paths = bk.texture_paths(d, gid, piece)
                missing = [p for k, p in paths.items() if not os.path.exists(p)]
                if missing:
                    raise RuntimeError(f"{gid}.{piece}: missing textures {missing}")
                mat = bk.preview_material(f"PV_{gid}_{piece}", paths, tints, proxy_res=2048)
            o.data.materials.clear()
            o.data.materials.append(mat)
            for p in o.data.polygons:
                p.material_index = 0
            o["asset"] = gid
            o.name = f"{gid}_{piece}"
            objs.append(o)
    return kind, objs


def check_images():
    bad = [im.name for im in bpy.data.images if im.source == "FILE" and (not os.path.exists(bpy.path.abspath(im.filepath)) or im.size[0] == 0)]
    if bad:
        raise RuntimeError(f"missing/unloadable images: {bad}")


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def main(argv):
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 16
    threads = int(argv[argv.index("--threads") + 1]) if "--threads" in argv else 0
    lineup = argv[argv.index("--lineup") + 1] if "--lineup" in argv else None
    skip = {argv[i + 1] for i, a in enumerate(argv) if a in ("--samples", "--threads", "--lineup")}
    ids = [a for a in argv if not a.startswith("--") and a not in skip]

    bw.reset_scene()
    scn = bpy.context.scene
    if threads:
        scn.render.threads_mode = "FIXED"
        scn.render.threads = threads
    rig = studio.setup_studio()
    coll = bw.WORK["coll"]

    if lineup:
        cat = "Attachments" if lineup.lower().startswith("att") else "Weapons"
        want = [gid for gid, (k, _) in bw.BUILDERS.items() if (k == "Attachment") == (cat == "Attachments")]
        groups = {}
        for gid in want:
            groups[gid] = import_asset(gid, coll)[1]
        check_images()
        if cat == "Weapons":
            rows, rg, cg, ls, vd, lens = bw.WEAPON_ROWS, 0.07, 0.07, 0.022, (0.1, -1.0, 0.12), 135
        else:
            rows, rg, cg, ls, vd, lens = [want[0:5], want[5:9], want[9:13], want[13:]], 0.05, 0.06, 0.012, (0.35, -1.0, 0.3), 100
        shown = studio.layout_rows(groups, rows, rg, cg, bw.WORK["labels"], ls)
        lo, hi = studio.bbox(shown)
        rig["floor"].hide_render = True
        studio.frame(rig, lo, hi, view_dir=vd, margin=1.05, lens=lens)
        path = os.path.join(RENDER_DIR, cat, "_Lineup_4K.png")
        studio.render(path, bw.LINEUP_RES, samples=samples)
        print("wrote", path, flush=True)
        return

    for gid in ids:
        kind, objs = import_asset(gid, coll)
        check_images()
        for o in coll.objects:
            o.hide_render = o.get("asset") != gid
        rig["floor"].hide_render = False
        lo, hi = studio.bbox(objs)
        studio.frame(rig, lo, hi, view_dir=(0.5, -1.0, 0.3) if kind != "Attachment" else (0.6, -1.0, 0.45), lens=85)
        cat = "Attachments" if kind == "Attachment" else "Weapons"
        path = os.path.join(RENDER_DIR, cat, f"{gid}.png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        studio.render(path, bw.RENDER_RES, samples=samples)
        print("wrote", path, flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--" in a:
        a = a[a.index("--") + 1 :]
    main(a)
