"""Andrew's Airsoft - one-shot editor setup (UE 5.8).

Imports every generated asset (SourceAssets/, Tools/Audio/Generated/), builds the master materials and
instances, and builds all five maps (L_MainMenu, L_Transition, L_Staging, L_IronwoodYard, L_VelvetClub).
Idempotent: re-running updates changed assets and rebuilds generated level actors (tag "AirsoftGen").

Run in the editor (after compiling the C++ module):
    Tools > Execute Python Script... > Content/Python/airsoft_setup.py
    or the console:  py airsoft_setup.py [options]

Options:
    --maps A,B        maps to build (MainMenu, Transition, Staging, IronwoodYard, VelvetClub); "none" = no maps
    --skip-import     do not import meshes / textures (default textures are still ensured)
    --skip-audio      do not import WAVs
    --skip-materials  do not rebuild master materials / instances / slot assignment
    --force-import    re-import even when the source files are unchanged (also rebuilds master materials)
    --rebuild-masters rebuild the master material graphs even if their version tag is current
    --only ID,ID      import only these asset ids
Examples:
    py airsoft_setup.py --maps Staging --skip-import
    py airsoft_setup.py --skip-import --skip-materials --maps IronwoodYard,VelvetClub
See Tools/Unreal/SETUP.md.
"""

import argparse
import os
import sys
import traceback


def _fresh_import():
    """Drop cached helper modules so edits to airsoft_setup_lib take effect without restarting the editor."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    for name in list(sys.modules):
        if name == "airsoft_setup_lib" or name.startswith("airsoft_setup_lib."):
            del sys.modules[name]
    from airsoft_setup_lib import common, layouts, importers, materials, lighting, levels  # noqa: F401
    return common, layouts, importers, materials, levels


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="airsoft_setup.py", add_help=False)
    ap.add_argument("--maps", default="all")
    ap.add_argument("--skip-import", action="store_true")
    ap.add_argument("--skip-audio", action="store_true")
    ap.add_argument("--skip-materials", action="store_true")
    ap.add_argument("--force-import", action="store_true")
    ap.add_argument("--rebuild-masters", action="store_true")
    ap.add_argument("--only", default="")
    args, unknown = ap.parse_known_args(argv)
    return args, unknown


def main(argv=None):
    if argv is None:
        argv = [a for a in sys.argv[1:] if a]
    C, L, I, MAT, LV = _fresh_import()
    import unreal
    S = C.reset_summary()
    args, unknown = parse_args(argv)
    if unknown:
        C.warn("ignoring unknown arguments: %s" % " ".join(unknown))
    if args.maps.strip().lower() in ("all", ""):
        maps = list(L.MAP_ORDER)
    elif args.maps.strip().lower() == "none":
        maps = []
    else:
        maps = [L.resolve_map_name(m) for m in args.maps.split(",") if m.strip()]
        bad = [m for m in maps if m not in L.MAP_ORDER]
        if bad:
            C.error("unknown map(s) %s; choose from %s" % (bad, ", ".join(L.MAP_ORDER)))
            return False
    only = set(x.strip() for x in args.only.split(",") if x.strip()) or None
    C.log("Andrew's Airsoft setup - project %s" % C.project_dir())
    C.log("maps: %s | import: %s | audio: %s | materials: %s" % (
        ", ".join(maps) or "none", "skip" if args.skip_import else ("force" if args.force_import else "changed only"),
        "skip" if args.skip_audio else "yes", "skip" if args.skip_materials else "rebuild"))
    for cls in ("AirsoftTeamStart", "AirsoftObjective", "AirsoftPracticeTarget", "AirsoftArmoryDisplay",
                "AirsoftMenuGameMode", "AirsoftGameMode"):
        if getattr(unreal, cls, None) is None:
            S.note("unreal.%s not found: compile the AndrewsAirsoft module (and restart the editor) before running"
                   " this script, or gameplay actors will be missing" % cls)
    ok = True
    legacy = None
    try:
        reg = C.load_registry()
        mats = C.load_materials_json()
        C.log("registry: %d assets (%s), %d tileable materials" % (
            len(reg), ", ".join("%s %d" % (c, sum(1 for e in reg.values() if e["Category"] == c))
                                for c in C.CATEGORIES), len(mats)))
        I.import_default_textures(force=args.force_import)
        if not args.skip_import:
            legacy = I.LegacyFbx()
            legacy.__enter__()
            I.import_tileable_textures(mats, force=args.force_import)
            I.import_assets(reg, force=args.force_import, only=only)
        if not args.skip_audio:
            I.import_audio(force=args.force_import)
        if not args.skip_materials:
            MAT.build_masters(force=args.force_import or args.rebuild_masters)
            MAT.build_tileable_instances(mats)
            MAT.build_piece_instances(reg)
            MAT.assign_mesh_materials(reg)
        C.save_dir(C.GAME_ROOT)
        for name in maps:
            try:
                if not LV.build_map(name, reg):
                    ok = False
            except Exception as e:
                ok = False
                S.note("building %s failed: %s\n%s" % (name, e, traceback.format_exc()))
    except Exception as e:
        ok = False
        C.error("setup aborted: %s\n%s" % (e, traceback.format_exc()))
    finally:
        if legacy is not None:
            try:
                legacy.__exit__(None, None, None)
            except Exception as e:
                C.warn("could not restore Interchange FBX setting: %s" % e)
        S.report()
    return ok


if __name__ != "airsoft_setup":      # run when executed as a script (py airsoft_setup.py / Execute Python Script)
    main()
