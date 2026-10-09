"""Importers: FBX pieces (legacy FBX pipeline), PNG textures, WAV audio. Skips unchanged sources."""

import glob
import os

import unreal

from . import common as C
from . import layouts as L

INTERCHANGE_FBX_CVAR = "Interchange.FeatureFlags.Import.FBX"
STAMP_TAG = "AirsoftSource"
POST_TAG = "AirsoftPost"

LOOPING_KEYS = {"AmbienceField", "AmbienceClubStreet", "AmbienceClubInterior", "ClubMusic", "AmbienceStaging",
                "MenuMusic"}

# Collision overrides (asset id -> Box/Convex/Complex/None) on top of the JSON "Collision" field.
COLLISION_OVERRIDE = {
    "Tree_Oak_A": "Complex", "Tree_Oak_B": "Complex", "Tree_Oak_C": "Complex",   # trunk + branches, not a hull
    "RugPersian": "None",
}
NO_COLLISION_PIECES = {"Flag", "Rope", "Plaque", "Shrub", "Chain", "Leaves", "Net", "Reticle"}

DEFAULT_TEXTURES = {   # name: (rgba, kind)
    "T_Default_BC": ((255, 255, 255, 255), "BC"),
    "T_Default_N": ((128, 128, 255, 255), "N"),
    "T_Default_ORM": ((255, 140, 0, 255), "ORM"),      # AO 1, roughness 0.55, metallic 0
    "T_Default_M": ((0, 0, 0, 255), "M"),              # no tint roles
    "T_Default_H": ((128, 128, 128, 255), "H"),
    "T_Default_Opacity": ((255, 255, 255, 255), "Opacity"),
}
DEFAULT_TEX_DIR = C.TEX_ROOT + "/Defaults"


# ---------------------------------------------------------------------------------------------
# Interchange switch (UE 5.5+ routes FBX through Interchange, which ignores FbxImportUI)
# ---------------------------------------------------------------------------------------------
class LegacyFbx(object):
    def __init__(self):
        self.old = None

    def __enter__(self):
        self.old = C.cvar_bool(INTERCHANGE_FBX_CVAR, None)
        C.console(INTERCHANGE_FBX_CVAR + " False")
        C.log("Interchange FBX import disabled for this run (was %s)" % self.old)
        return self

    def __exit__(self, *exc):
        restore = True if self.old is None else self.old
        C.console("%s %s" % (INTERCHANGE_FBX_CVAR, "True" if restore else "False"))
        C.log("Interchange FBX import restored to %s" % restore)
        return False


# ---------------------------------------------------------------------------------------------
def _task(src, dest_dir, name, options=None):
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", src)
    t.set_editor_property("destination_path", dest_dir)
    t.set_editor_property("destination_name", name)
    t.set_editor_property("replace_existing", True)
    C.try_set(t, "replace_existing_settings", True, quiet=True)
    t.set_editor_property("automated", True)
    t.set_editor_property("save", False)
    if options is not None:
        t.set_editor_property("options", options)
    return t


def _run(tasks):
    try:
        C.asset_tools().import_asset_tasks(tasks)
        return True
    except Exception as e:
        C.SUMMARY.note("import_asset_tasks failed: %s" % e)
        return False


def _imported(task, cls):
    out = []
    try:
        for p in task.get_editor_property("imported_object_paths") or []:
            a = unreal.EditorAssetLibrary.load_asset(str(p))
            if a and isinstance(a, cls):
                out.append((str(p).split(".")[0], a))
    except Exception:
        pass
    return out


def _settle_name(task, cls, want_path):
    """The legacy FBX importer may name a non-combined mesh after its node; move it to want_path."""
    a = C.load(want_path)
    if a:
        return a
    got = _imported(task, cls)
    if len(got) == 1:
        src = got[0][0]
        try:
            if unreal.EditorAssetLibrary.rename_asset(src, want_path):
                return C.load(want_path)
        except Exception as e:
            C.warn("rename %s -> %s failed: %s" % (src, want_path, e))
        return got[0][1]
    return None


# ---------------------------------------------------------------------------------------------
# Textures
# ---------------------------------------------------------------------------------------------
def _enum(enum_cls, *names):
    for n in names:
        if hasattr(enum_cls, n):
            return getattr(enum_cls, n)
    return None


def configure_texture(tex, kind, weapon=False):
    TC = unreal.TextureCompressionSettings
    TG = unreal.TextureGroup
    if kind == "BC":
        comp, srgb = _enum(TC, "TC_DEFAULT"), True
        group = _enum(TG, "TEXTUREGROUP_WEAPON" if weapon else "TEXTUREGROUP_WORLD")
    elif kind == "N":
        comp, srgb = _enum(TC, "TC_NORMALMAP"), False
        group = _enum(TG, "TEXTUREGROUP_WEAPON_NORMAL_MAP" if weapon else "TEXTUREGROUP_WORLD_NORMAL_MAP")
    else:  # ORM, M, H, Opacity: linear data, BC1/BC5-style mask compression
        comp, srgb = _enum(TC, "TC_MASKS"), False
        group = _enum(TG, "TEXTUREGROUP_WEAPON_SPECULAR" if weapon else "TEXTUREGROUP_WORLD_SPECULAR")
    if comp is not None:
        C.try_set(tex, "compression_settings", comp)
    C.try_set(tex, "srgb", srgb)
    if group is not None:
        C.try_set(tex, "lod_group", group)
    if kind == "N":
        C.try_set(tex, "flip_green_channel", False, quiet=True)   # DirectX normals, as Unreal expects
    C.try_set(tex, "virtual_texture_streaming", bool(C.USE_VIRTUAL_TEXTURES), quiet=True)


def import_texture(src, dest_dir, name, kind, weapon=False, force=False):
    path = "%s/%s" % (dest_dir, name)
    stamp = C.source_stamp(src)
    tex = C.load(path)
    if tex and not force and C.get_metadata(tex, STAMP_TAG) == stamp:
        C.SUMMARY.inc("textures unchanged (skipped)")
        return tex
    C.ensure_dir(dest_dir)
    t = _task(src, dest_dir, name)
    if not _run([t]):
        C.SUMMARY.miss("texture import", name)
        return tex
    tex = _settle_name(t, unreal.Texture, path)
    if not tex:
        C.SUMMARY.miss("texture import", name)
        return None
    configure_texture(tex, kind, weapon)
    C.set_metadata(tex, STAMP_TAG, stamp)
    C.save_asset(tex)
    C.SUMMARY.inc("textures imported")
    return tex


def import_default_textures(force=False):
    folder = os.path.join(C.saved_dir(), "DefaultTextures")
    os.makedirs(folder, exist_ok=True)
    out = {}
    for name, (rgba, kind) in DEFAULT_TEXTURES.items():
        p = os.path.join(folder, name + ".png")
        if not os.path.isfile(p):
            C.write_png(p, 8, 8, rgba)
        out[name] = import_texture(p, DEFAULT_TEX_DIR, name, kind, force=force)
    return out


def import_tileable_textures(materials, force=False):
    n = 0
    for mid, m in sorted(materials.items()):
        for key in ("BC", "N", "ORM", "H", "Opacity"):
            rel = m.get(key)
            if not rel:
                continue
            src = os.path.join(C.source_dir(), rel)
            if not os.path.isfile(src):
                C.SUMMARY.miss("tileable texture", os.path.basename(rel))
                continue
            if import_texture(src, "%s/Materials/%s" % (C.TEX_ROOT, mid), "T_%s_%s" % (mid, key), key, force=force):
                n += 1
    return n


# ---------------------------------------------------------------------------------------------
# Meshes
# ---------------------------------------------------------------------------------------------
def _fbx_options(build_nanite, combine):
    o = unreal.FbxImportUI()
    for k, v in (("import_mesh", True), ("import_textures", False), ("import_materials", False),
                 ("import_as_skeletal", False), ("import_animations", False), ("create_physics_asset", False),
                 ("automated_import_should_detect_type", False)):
        C.try_set(o, k, v, quiet=True)
    C.try_set(o, "mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    sm = o.get_editor_property("static_mesh_import_data")
    for k, v in (("combine_meshes", combine), ("auto_generate_collision", False), ("generate_lightmap_u_vs", False),
                 ("remove_degenerates", True), ("build_nanite", build_nanite), ("one_convex_hull_per_ucx", True),
                 ("convert_scene", C.FBX_CONVERT_SCENE), ("force_front_x_axis", C.FBX_FORCE_FRONT_X),
                 ("convert_scene_unit", False), ("import_uniform_scale", 1.0),
                 ("reorder_material_to_fbx_order", True), ("transform_vertex_to_absolute", True),
                 ("compute_weighted_normals", True)):
        C.try_set(sm, k, v, quiet=True)
    C.try_set(sm, "normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
    C.try_set(sm, "import_rotation", C.rot(yaw=C.FBX_IMPORT_YAW), quiet=True)
    try:
        C.try_set(sm, "vertex_color_import_option", unreal.VertexColorImportOption.IGNORE, quiet=True)
    except Exception:
        pass
    return o


def set_nanite(sm, enabled, foliage=False):
    sub = None
    try:
        sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    except Exception:
        pass
    if sub is not None and hasattr(sub, "get_nanite_settings") and hasattr(sub, "set_nanite_settings"):
        try:
            ns = sub.get_nanite_settings(sm)
            ns.set_editor_property("enabled", bool(enabled))
            if foliage:
                C.try_set(ns, "preserve_area", True, quiet=True)
            sub.set_nanite_settings(sm, ns, True)
            return True
        except Exception as e:
            C.SUMMARY.once("nanite-sub", "StaticMeshEditorSubsystem.set_nanite_settings failed (%s); using the property" % e)
    try:
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", bool(enabled))
        if foliage:
            C.try_set(ns, "preserve_area", True, quiet=True)
        sm.set_editor_property("nanite_settings", ns)   # set_editor_property runs PostEditChange -> rebuild
        return True
    except Exception as e:
        C.SUMMARY.once("nanite-prop", "could not set Nanite on %s: %s" % (sm.get_name(), e))
        return False


def set_collision(sm, mode, big=True):
    CTF = unreal.CollisionTraceFlag
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    try:
        sub.remove_collisions(sm)
    except Exception:
        pass
    flag = CTF.CTF_USE_DEFAULT
    try:
        if mode == "Box":
            sub.add_simple_collisions(sm, unreal.ScriptCollisionShapeType.BOX)
        elif mode == "Convex":
            ok = False
            try:
                ok = sub.set_convex_decomposition_collisions(sm, 4 if big else 1, 16, 100000)
            except Exception as e:
                C.SUMMARY.once("convex", "convex decomposition unavailable (%s); using 26-DOP hulls" % e)
            if not ok:
                sub.add_simple_collisions(sm, unreal.ScriptCollisionShapeType.NDOP26)
        elif mode == "Complex":
            flag = CTF.CTF_USE_COMPLEX_AS_SIMPLE
        else:  # None: no simple shapes and complex disabled -> traces and pawns pass through
            flag = CTF.CTF_USE_SIMPLE_AS_COMPLEX
    except Exception as e:
        C.SUMMARY.once("coll-" + mode, "collision %s failed on %s: %s" % (mode, sm.get_name(), e))
    bs = C.try_get(sm, "body_setup")
    if bs is not None:
        C.try_set(bs, "collision_trace_flag", flag)


def collision_for(entry, aid, piece, role):
    cat = entry["Category"]
    pn = piece.get("Name", "")
    if cat in C.NO_COLLISION_CATEGORIES or role in ("glass", "emissive", "masked") or pn in NO_COLLISION_PIECES:
        return "None"
    if pn == "Plate":
        return "Box"            # practice target plate: query-only box for BB hits
    if pn != "Body" and piece.get("Kind") not in ("Body",):
        return "None"
    c = COLLISION_OVERRIDE.get(aid) or entry.get("Collision") or L.KNOWN_ASSETS.get(aid, {}).get("coll")
    if not c:
        c = "Complex" if cat == "Architecture" else "Convex"
    return c


def _mesh_big(entry):
    b = entry.get("Bounds") or {}
    try:
        return max(b["Max"][i] - b["Min"][i] for i in range(3)) > 120.0
    except Exception:
        return True


def import_mesh(entry, aid, piece, force=False):
    cat = entry["Category"]
    pn = piece["Name"]
    src = entry["Fbx"].get(pn)
    path = C.mesh_path(cat, aid, pn)
    if not src:
        return C.load(path)
    role = C.piece_role(aid, piece)
    nanite = role in ("opaque", "emissive") or (role == "masked" and C.NANITE_MASKED_FOLIAGE)
    coll = collision_for(entry, aid, piece, role)
    post = "%s|%s|%s|%s" % (role, coll, nanite, C.IMPORT_VERSION)
    stamp = C.source_stamp(src)
    sm = C.load(path)
    if sm and not force and C.get_metadata(sm, STAMP_TAG) == stamp:
        if C.get_metadata(sm, POST_TAG) != post:
            set_nanite(sm, nanite, foliage=(role == "masked"))
            set_collision(sm, coll, _mesh_big(entry))
            C.set_metadata(sm, POST_TAG, post)
            C.save_asset(sm)
        C.SUMMARY.inc("meshes unchanged (skipped)")
        return sm
    dest = C.mesh_dir(cat, aid)
    C.ensure_dir(dest)
    name = "SM_%s_%s" % (aid, pn)
    t = _task(src, dest, name, _fbx_options(nanite, C.COMBINE_MESHES))
    if not _run([t]):
        C.SUMMARY.miss("mesh import", name)
        return sm
    got = _imported(t, unreal.StaticMesh)
    if not C.exists(path) and len(got) > 1 and not C.COMBINE_MESHES:
        # several nodes in one FBX: re-import combined so the piece stays one asset
        for p, _ in got:
            unreal.EditorAssetLibrary.delete_asset(p)
        t = _task(src, dest, name, _fbx_options(nanite, True))
        _run([t])
    sm = _settle_name(t, unreal.StaticMesh, path)
    if not sm:
        C.SUMMARY.miss("mesh import", name)
        return None
    set_nanite(sm, nanite, foliage=(role == "masked"))
    set_collision(sm, coll, _mesh_big(entry))
    check_bounds(sm, entry, aid, pn)
    C.set_metadata(sm, STAMP_TAG, stamp)
    C.set_metadata(sm, POST_TAG, post)
    C.save_asset(sm)
    C.SUMMARY.inc("meshes imported")
    return sm


def check_bounds(sm, entry, aid, pn):
    """Warn when an imported Body looks rotated against its JSON bounds (axis convention mismatch)."""
    if pn != "Body":
        return
    try:
        b = entry["Bounds"]
        box = sm.get_bounding_box()
        mn, mx = box.min, box.max
        ex = (mx.x - mn.x, mx.y - mn.y)
        jx = (b["Max"][0] - b["Min"][0], b["Max"][1] - b["Min"][1])
        if min(jx) > 20 and abs(jx[0] - jx[1]) > 0.25 * max(jx):
            if abs(ex[0] - jx[1]) < abs(ex[0] - jx[0]) * 0.5 and abs(ex[1] - jx[0]) < abs(ex[1] - jx[1]) * 0.5:
                C.SUMMARY.note("%s imported rotated 90 deg vs JSON bounds (X %.0f/Y %.0f vs %.0f/%.0f) - see SETUP.md "
                               "'Meshes face the wrong way' (FBX_IMPORT_YAW / FBX_FORCE_FRONT_X)" %
                               (aid, ex[0], ex[1], jx[0], jx[1]))
    except Exception:
        pass


def import_assets(reg, force=False, only=None):
    items = [(aid, e) for aid, e in sorted(reg.items()) if not only or aid in only]
    total = sum(len(e["Pieces"]) for _, e in items)
    with unreal.ScopedSlowTask(max(1, total), "Andrew's Airsoft: importing meshes and textures") as slow:
        slow.make_dialog(True)
        for aid, e in items:
            cat = e["Category"]
            for piece in e["Pieces"]:
                if slow.should_cancel():
                    C.SUMMARY.note("import cancelled by user")
                    return
                pn = piece["Name"]
                slow.enter_progress_frame(1, "Importing %s / %s" % (aid, pn))
                try:
                    for key, src in sorted(e["Textures"].get(pn, {}).items()):
                        import_texture(src, C.tex_dir(cat, aid), "T_%s_%s_%s" % (aid, pn, key), key,
                                       weapon=cat in ("Weapons", "Attachments"), force=force)
                    if pn in e["Fbx"]:
                        import_mesh(e, aid, piece, force=force)
                    elif not C.exists(C.mesh_path(cat, aid, pn)):
                        C.SUMMARY.miss("mesh source (FBX not generated yet)", "%s/%s" % (aid, pn))
                except Exception as ex:
                    C.SUMMARY.note("import of %s/%s failed: %s" % (aid, pn, ex))


# ---------------------------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------------------------
def import_audio(force=False):
    d = C.audio_dir()
    files = sorted(set(glob.glob(os.path.join(d, "*.wav")) + glob.glob(os.path.join(d, "**", "*.wav"), recursive=True)))
    if not files:
        C.SUMMARY.note("no WAV files in %s yet - ambience/music actors are skipped until audio exists" % d)
        return 0
    C.ensure_dir(C.AUDIO_ROOT)
    n = 0
    with unreal.ScopedSlowTask(len(files), "Andrew's Airsoft: importing audio") as slow:
        slow.make_dialog(True)
        for f in files:
            key = os.path.splitext(os.path.basename(f))[0]
            slow.enter_progress_frame(1, "Audio " + key)
            path = "%s/%s" % (C.AUDIO_ROOT, key)
            stamp = C.source_stamp(f)
            snd = C.load(path)
            if snd and not force and C.get_metadata(snd, STAMP_TAG) == stamp:
                C.SUMMARY.inc("sounds unchanged (skipped)")
                continue
            t = _task(f, C.AUDIO_ROOT, key)
            if not _run([t]):
                C.SUMMARY.miss("sound import", key)
                continue
            snd = _settle_name(t, unreal.SoundWave, path)
            if not snd:
                C.SUMMARY.miss("sound import", key)
                continue
            loop = key in LOOPING_KEYS or key.startswith("Ambience") or key.endswith("Music")
            C.try_set(snd, "looping", loop)
            C.set_metadata(snd, STAMP_TAG, stamp)
            C.save_asset(snd)
            C.SUMMARY.inc("sounds imported")
            n += 1
    return n
