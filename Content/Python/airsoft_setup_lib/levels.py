"""Builds the five maps from layouts.py. Generated actors carry the AirsoftGen tag and are rebuilt on re-run;
anything you place by hand (untagged) is left alone."""

import unreal

from . import common as C
from . import layouts as L
from . import lighting as LIGHT
from . import materials as MAT

CUBE = "/Engine/BasicShapes/Cube.Cube"
CYLINDER = "/Engine/BasicShapes/Cylinder.Cylinder"
SPHERE = "/Engine/BasicShapes/Sphere.Sphere"
SHAPES = {"cube": CUBE, "cyl": CYLINDER, "sphere": SPHERE}
TEAMS = {"None": "NONE", "Blue": "BLUE", "Red": "RED"}


class Ctx(object):
    def __init__(self, reg):
        self.reg = reg
        self.json_assets = C.json_assets_for_layouts(reg)
        self.labels = {}
        self.shadow_lights = 0
        self.counts = {}
        self._mesh = {}
        self.actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    def mesh(self, path):
        if path not in self._mesh:
            self._mesh[path] = C.load(path)
        return self._mesh[path]

    def count(self, key, n=1):
        self.counts[key] = self.counts.get(key, 0) + n

    def label(self, base):
        k = self.labels.get(base, 0) + 1
        self.labels[base] = k
        return "%s_%03d" % (base, k)

    def spawn(self, cls, loc, rotation, label=None, folder=None):
        a = self.actor_sub.spawn_actor_from_class(cls, loc, rotation)
        if a is None:
            raise RuntimeError("spawn of %s failed" % cls)
        try:
            a.set_editor_property("tags", [unreal.Name(C.TAG)])
        except Exception:
            a.tags = [unreal.Name(C.TAG)]
        if label:
            try:
                a.set_actor_label(self.label(label))
            except Exception:
                pass
        if folder:
            try:
                a.set_folder_path(unreal.Name("Airsoft/" + folder))
            except Exception:
                pass
        return a


# ---------------------------------------------------------------------------------------------
# Level management
# ---------------------------------------------------------------------------------------------
def _les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def open_or_create(path):
    les = _les()
    if C.exists(path):
        ok = les.load_level(path)
        if not ok:
            raise RuntimeError("could not load %s" % path)
        return "loaded"
    C.ensure_dir(path.rsplit("/", 1)[0])
    ok = False
    try:
        ok = les.new_level(path)           # non World Partition (bIsPartitionedWorld defaults to false)
    except Exception as e:
        C.warn("new_level(%s) failed: %s" % (path, e))
    if not ok:
        try:
            unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
            ok = unreal.EditorLoadingAndSavingUtils.save_map(C.editor_world(), path)
        except Exception as e:
            raise RuntimeError("could not create %s: %s" % (path, e))
    return "created"


def clear_generated(ctx):
    actors = ctx.actor_sub.get_all_level_actors()
    gen = []
    stray_starts = []
    for a in actors:
        try:
            if a.actor_has_tag(C.TAG):
                gen.append(a)
            elif type(a) is unreal.PlayerStart:
                stray_starts.append(a)
        except Exception:
            pass
    if stray_starts:
        C.SUMMARY.note("removing %d plain PlayerStart actor(s): maps use AirsoftTeamStart only" % len(stray_starts))
        gen += stray_starts
    if gen:
        try:
            ctx.actor_sub.destroy_actors(gen)
        except Exception:
            for a in gen:
                try:
                    ctx.actor_sub.destroy_actor(a)
                except Exception:
                    pass
    return len(gen)


def configure_world(m):
    world = C.editor_world()
    ws = world.get_world_settings()
    C.try_set(ws, "kill_z", float(m.get("kill_z", -10.0)) * 100.0)
    C.try_set(ws, "enable_world_bounds_checks", True, quiet=True)
    gm = m.get("game_mode")
    if gm:
        cls = getattr(unreal, gm, None)
        if cls is None:
            C.SUMMARY.note("class unreal.%s not found - compile the C++ module first; GameMode override not set" % gm)
        else:
            C.try_set(ws, "default_game_mode", cls.static_class())


# ---------------------------------------------------------------------------------------------
# Spawning helpers
# ---------------------------------------------------------------------------------------------
def spawn_mesh(ctx, mesh, loc, rotation, scale, label, folder, materials=None, coll=True, cast=True):
    a = ctx.spawn(unreal.StaticMeshActor, loc, rotation, label, folder)
    comp = a.static_mesh_component
    comp.set_static_mesh(mesh)
    if scale is not None:
        a.set_actor_scale3d(scale)
    for i, mi in enumerate(materials or []):
        if mi is not None:
            comp.set_material(i, mi)
    if not coll:
        comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    if not cast:
        comp.set_cast_shadow(False)
    return a


def _scale3(sc):
    if sc is None:
        return (1.0, 1.0, 1.0)
    if isinstance(sc, (int, float)):
        return (float(sc), float(sc), float(sc))
    return tuple(float(v) for v in sc)


def _world(it, local_cm):
    """Asset-space point (cm) -> world unreal.Vector for a prop item."""
    sc = _scale3(it.get("scale"))
    x, y, z = it["p"]
    lx, ly = L.rot2(local_cm[0] * sc[0], local_cm[1] * sc[1], it.get("yaw", 0.0))
    return C.vec(x * 100.0 + lx, y * 100.0 + ly, z * 100.0 + local_cm[2] * sc[2])


def place_prop(ctx, it):
    aid = it["id"]
    e = ctx.reg.get(aid)
    cat = e["Category"] if e else L.category_of(aid)
    pieces = e["Pieces"] if e else [{"Name": "Body", "Kind": "Body"}]
    filt = it.get("pieces")
    if "hang" in it:
        mount = L.asset_point(aid, "CeilingMount", ctx.json_assets)
        mz = mount[2] if mount else L.asset_bounds(aid, ctx.json_assets)[1][2]
        it = dict(it)
        it["p"] = (it["p"][0], it["p"][1], it["hang"] - mz / 100.0)
    sc = _scale3(it.get("scale"))
    loc = _world(it, (0.0, 0.0, 0.0))
    rotation = C.rot(yaw=it.get("yaw", 0.0))
    scale = C.vec(*sc)
    folder = "Props/" + cat
    found = [(p, ctx.mesh(C.mesh_path(cat, aid, p["Name"]))) for p in pieces if not filt or p["Name"] in filt]
    has_body = any(m is not None for p, m in found if p["Name"] == "Body") or \
        (not any(p["Name"] == "Body" for p, _ in found) and any(m is not None for _, m in found))
    if has_body:
        body = None
        for p, mesh in found:
            if mesh is None:
                continue
            role = C.piece_role(aid, p)
            mats = None
            tint = it.get("tint")
            if tint:
                var = MAT.tint_override(cat, aid, p["Name"], tint)
                if var is not None:
                    base_path = MAT.piece_mi_path(cat, aid, p["Name"])
                    mats = []
                    nslots = len(mesh.get_editor_property("static_materials") or [])
                    for i in range(nslots):
                        cur = mesh.get_material(i)
                        mats.append(var if cur is not None and cur.get_path_name().split(".")[0] == base_path else None)
            coll = ((role == "opaque" or p["Name"] == "Net") and not it.get("nocoll") and
                    p["Name"] not in ("Leaves", "Flag", "Rope", "Plaque", "Shrub"))
            a = spawn_mesh(ctx, mesh, loc, rotation, scale, aid if body is None else "%s_%s" % (aid, p["Name"]),
                           folder, mats, coll=coll)
            if role == "emissive":
                C.try_set(a.static_mesh_component, "emissive_light_source", True, quiet=True)
            if body is None:
                body = a
            else:
                try:
                    a.attach_to_actor(body, "", unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD,
                                      unreal.AttachmentRule.KEEP_WORLD, False)
                except Exception:
                    pass
        ctx.count("props (imported mesh)")
    else:
        place_fallback(ctx, it, aid, folder)
        ctx.count("props (fallback shapes)")
        C.SUMMARY.miss("meshes (fallback shapes placed)", aid)
    if it.get("display"):
        place_display(ctx, it)
    if it.get("light"):
        try:
            _, sh = LIGHT.spawn_fixture(ctx.spawn, aid, it, ctx.json_assets, lambda pt: _world(it, pt))
            ctx.shadow_lights += 1 if sh else 0
        except Exception as ex:
            C.SUMMARY.note("fixture light for %s failed: %s" % (aid, ex))


def place_fallback(ctx, it, aid, folder):
    bmin, bmax = L.asset_bounds(aid, ctx.json_assets)
    parts = L.fallback_parts(aid, bmin, bmax)
    k = L.KNOWN_ASSETS.get(aid, {})
    main_mat = k.get("fb", "box:Concrete").partition(":")[2] or "Concrete"
    tint = it.get("tint") or k.get("tint")
    sc = _scale3(it.get("scale"))
    yaw = it.get("yaw", 0.0)
    first = None
    for part in parts:
        mn, mx = part["min"], part["max"]
        c = [(mn[i] + mx[i]) / 2.0 for i in range(3)]
        size = [(mx[i] - mn[i]) * sc[i] for i in range(3)]
        loc = _world(it, c)
        if part["axis"] == "y":
            rotation, s = C.rot(yaw=yaw, roll=90.0), (size[0], size[2], size[1])
        elif part["axis"] == "x":
            rotation, s = C.rot(yaw=yaw, pitch=90.0), (size[2], size[1], size[0])
        else:
            rotation, s = C.rot(yaw=yaw), size
        mesh = ctx.mesh(SHAPES[part["shape"]])
        if mesh is None:
            continue
        mat = part["mat"]
        mi = MAT.get_box_mi(mat, tint if (mat == main_mat and tint) else None, world=True)
        coll = part["coll"] and not it.get("nocoll")
        a = spawn_mesh(ctx, mesh, loc, rotation, C.vec(*(max(v, 0.5) / 100.0 for v in s)),
                       aid + "_FB" if first is None else None, folder, [mi], coll=coll,
                       cast=not mat.startswith("Emissive:"))
        if mat.startswith("Emissive:"):
            C.try_set(a.static_mesh_component, "emissive_light_source", True, quiet=True)
        if first is None:
            first = a
        else:
            try:
                a.attach_to_actor(first, "", unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD,
                                  unreal.AttachmentRule.KEEP_WORLD, False)
            except Exception:
                pass


def place_display(ctx, it):
    cls = getattr(unreal, "AirsoftArmoryDisplay", None)
    if cls is None:
        C.SUMMARY.once("cls-display", "unreal.AirsoftArmoryDisplay missing - compile the C++ module; displays skipped")
        return
    gm = L.asset_point("GunDisplayBay", "GunMount", ctx.json_assets)
    if gm is None:   # no JSON point: bay centre, 120 cm above the floor
        mn, mx = L.asset_bounds("GunDisplayBay", ctx.json_assets)
        gm = ((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, 120.0 - it["p"][2] * 100.0)
    a = ctx.spawn(cls, _world(it, gm), C.rot(yaw=it.get("yaw", 0.0)), "Display_" + it["display"], "Armory")
    C.try_set(a, "weapon_id", unreal.Name(it["display"]))
    C.try_set(a, "rotate", False)
    C.try_set(a, "show_label", True)
    ctx.count("armory displays")


def place_box(ctx, it):
    cx, cy, cz = it["p"]
    sx, sy, sz = it["s"]
    mat = it["mat"]
    if mat.startswith("Emissive:"):
        mi = MAT.get_emissive_mi(mat.split(":", 1)[1], it.get("glow", 20.0))
    else:
        mi = MAT.get_box_mi(mat, it.get("tint"), world=True, tile=it.get("tile"))
    a = spawn_mesh(ctx, ctx.mesh(CUBE), C.vec(cx * 100, cy * 100, cz * 100),
                   C.rot(pitch=it.get("pitch", 0.0), yaw=it.get("yaw", 0.0)), C.vec(sx, sy, sz),
                   it.get("name", "Block"), "Blocks", [mi], coll=it.get("coll", True),
                   cast=it.get("cast", True) and not mat.startswith("Emissive:"))
    if mat.startswith("Emissive:"):
        C.try_set(a.static_mesh_component, "emissive_light_source", True, quiet=True)
    ctx.count("blocks")


def place_blocker(ctx, it):
    cx, cy, cz = it["p"]
    sx, sy, sz = it["s"]
    a = spawn_mesh(ctx, ctx.mesh(CUBE), C.vec(cx * 100, cy * 100, cz * 100), C.rot(yaw=it.get("yaw", 0.0)),
                   C.vec(sx, sy, sz), "Blocker", "Blockers", [MAT.get_box_mi("Blocker")], cast=False)
    comp = a.static_mesh_component
    comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
    comp.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
    comp.set_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN, unreal.CollisionResponseType.ECR_BLOCK)
    for k in ("affect_distance_field_lighting", "affect_dynamic_indirect_lighting", "visible_in_ray_tracing"):
        C.try_set(comp, k, False, quiet=True)
    a.set_actor_hidden_in_game(True)
    ctx.count("blockers")


def place_start(ctx, it):
    cls = getattr(unreal, "AirsoftTeamStart", None)
    x, y, z = it["p"]
    loc = C.vec(x * 100, y * 100, (z + L.START_Z_OFFSET) * 100)
    if cls is None:
        C.SUMMARY.once("cls-start", "unreal.AirsoftTeamStart missing - compile the C++ module; using PlayerStart")
        cls = unreal.PlayerStart
    a = ctx.spawn(cls, loc, C.rot(yaw=it["yaw"]), "Start_" + it["team"], "Spawns")
    team_enum = getattr(unreal, "AirsoftTeam", None)
    if team_enum is not None and cls is not unreal.PlayerStart:
        C.try_set(a, "team", getattr(team_enum, TEAMS[it["team"]]))
    ctx.count("team starts (%s)" % it["team"])


def place_objective(ctx, it):
    cls = getattr(unreal, "AirsoftObjective", None)
    if cls is None:
        C.SUMMARY.once("cls-obj", "unreal.AirsoftObjective missing - compile the C++ module; objectives skipped")
        return
    x, y, z = it["p"]
    a = ctx.spawn(cls, C.vec(x * 100, y * 100, z * 100), C.rot(), "Objective_" + it["letter"], "Objectives")
    C.try_set(a, "letter", it["letter"])
    C.try_set(a, "radius", float(it.get("radius", 5.0)) * 100.0)
    C.try_set(a, "half_height", float(it.get("half_height", 2.5)) * 100.0)
    ctx.count("objectives")


def place_target(ctx, it):
    cls = getattr(unreal, "AirsoftPracticeTarget", None)
    if cls is None:
        C.SUMMARY.once("cls-target", "unreal.AirsoftPracticeTarget missing - compile the C++ module; targets skipped")
        return
    x, y, z = it["p"]
    a = ctx.spawn(cls, C.vec(x * 100, y * 100, z * 100), C.rot(yaw=it.get("yaw", 0.0)), "Target", "Range")
    C.try_set(a, "caption", it.get("caption", ""))
    C.try_set(a, "plate_size", float(it.get("plate", 40.0)))
    ctx.count("practice targets")


def place_sound(ctx, it):
    snd = C.load("%s/%s" % (C.AUDIO_ROOT, it["key"]))
    if snd is None:
        C.SUMMARY.miss("sounds (AmbientSound skipped)", it["key"])
        return
    x, y, z = it["p"]
    a = ctx.spawn(unreal.AmbientSound, C.vec(x * 100, y * 100, z * 100), C.rot(), "Sound_" + it["key"], "Audio")
    ac = LIGHT.comp_of(a, unreal.AudioComponent)
    ac.set_sound(snd)
    try:
        ac.set_volume_multiplier(float(it.get("volume", 1.0)))
    except Exception:
        pass
    if not it.get("spatial"):
        C.try_set(ac, "allow_spatialization", False)
    else:
        C.try_set(ac, "allow_spatialization", True, quiet=True)
        if C.try_set(ac, "override_attenuation", True, quiet=True):
            try:
                att = ac.get_editor_property("attenuation_overrides")
                C.try_set(att, "attenuate", True, quiet=True)
                C.try_set(att, "spatialize", True, quiet=True)
                C.try_set(att, "attenuation_shape", unreal.AttenuationShape.SPHERE, quiet=True)
                C.try_set(att, "attenuation_shape_extents", C.vec(float(it["radius"]) * 100.0, 0, 0), quiet=True)
                C.try_set(att, "falloff_distance", float(it["falloff"]) * 100.0, quiet=True)
                ac.set_editor_property("attenuation_overrides", att)
            except Exception as e:
                C.SUMMARY.once("att", "sound attenuation override failed: %s" % e)
    ctx.count("ambient sounds")


def place_text(ctx, it):
    x, y, z = it["p"]
    a = ctx.spawn(unreal.TextRenderActor, C.vec(x * 100, y * 100, z * 100), C.rot(yaw=it.get("yaw", 0.0)), "Sign",
                  "Signs")
    tc = LIGHT.comp_of(a, unreal.TextRenderComponent)
    if not C.try_set(tc, "text", it["text"]):
        try:
            tc.set_text(it["text"])
        except Exception:
            pass
    C.try_set(tc, "world_size", float(it.get("size", 60.0)))
    C.try_set(tc, "horizontal_alignment", unreal.HorizTextAligment.EHTA_CENTER, quiet=True)
    C.try_set(tc, "vertical_alignment", unreal.VerticalTextAligment.EVRTA_TEXT_CENTER, quiet=True)
    col = L.EMISSIVE_COLORS.get(it.get("color", "Warm"), (1, 0.8, 0.5))
    C.try_set(tc, "text_render_color", unreal.Color(r=int(col[0] * 255), g=int(col[1] * 255), b=int(col[2] * 255),
                                                    a=255), quiet=True)
    sign = C.load(MAT.MASTER_SIGN)
    if sign is not None:
        mi = MAT.make_mi("%s/Emissive/MI_SignText_%s_%d" % (C.MI_ROOT, it.get("color", "Warm"), int(it.get("glow", 6))),
                         sign, scalars={"Intensity": float(it.get("glow", 6.0))}, vectors={"Color": (1, 1, 1)},
                         clear=False)
        if mi is not None:
            C.try_set(tc, "text_material", mi, quiet=True)
    ctx.count("sign texts")


def place_capture(ctx, it):
    x, y, z = it["p"]
    a = ctx.spawn(unreal.SphereReflectionCapture, C.vec(x * 100, y * 100, z * 100), C.rot(), "ReflectionCapture",
                  "Lighting")
    rc = LIGHT.comp_of(a, unreal.SphereReflectionCaptureComponent)
    if rc is not None:
        C.try_set(rc, "influence_radius", float(it["radius"]) * 100.0)
    ctx.count("reflection captures")


def place_fog(ctx, it):
    cls = getattr(unreal, "LocalFogVolume", None)
    if cls is None:
        C.SUMMARY.once("lfv", "LocalFogVolume not available; haze comes from the height fog only")
        return
    x, y, z = it["p"]
    a = ctx.spawn(cls, C.vec(x * 100, y * 100, z * 100), C.rot(), "LocalFog", "Lighting")
    a.set_actor_scale3d(C.vec(*it["s"]))        # unit sphere of 1 m radius scaled to the half extents (m)
    comp = None
    try:
        comp = a.get_component_by_class(unreal.LocalFogVolumeComponent)
    except Exception:
        pass
    if comp is not None:
        C.try_set(comp, "radial_fog_extinction", float(it.get("density", 0.5)), quiet=True)
        C.try_set(comp, "height_fog_extinction", float(it.get("density", 0.5)) * 0.6, quiet=True)
        C.try_set(comp, "fog_albedo", C.lc(it.get("color", (0.7, 0.6, 0.6))), quiet=True)
    ctx.count("local fog volumes")


def place_camera(ctx, it):
    x, y, z = it["p"]
    a = ctx.spawn(unreal.CineCameraActor, C.vec(x * 100, y * 100, z * 100),
                  C.rot(pitch=it.get("pitch", 0.0), yaw=it.get("yaw", 0.0)), "MenuCamera", "Camera")
    cam = a.get_cine_camera_component()
    C.try_set(cam, "current_focal_length", float(it.get("focal", 35.0)))
    C.try_set(cam, "current_aperture", float(it.get("fstop", 2.8)))
    try:
        fs = cam.get_editor_property("focus_settings")
        fs.set_editor_property("focus_method", unreal.CameraFocusMethod.MANUAL)
        fx, fy, fz = it.get("focus_at", (x + 3.0, y, z))
        d = ((fx - x) ** 2 + (fy - y) ** 2 + (fz - z) ** 2) ** 0.5 * 100.0
        fs.set_editor_property("manual_focus_distance", d)
        cam.set_editor_property("focus_settings", fs)
    except Exception as e:
        C.SUMMARY.once("focus", "camera focus settings failed: %s" % e)
    C.try_set(a, "auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
    ctx.count("cameras")


PLACERS = {"prop": place_prop, "box": place_box, "blocker": place_blocker, "start": place_start,
           "objective": place_objective, "target": place_target, "sound": place_sound, "text": place_text,
           "capture": place_capture, "fog": place_fog, "camera": place_camera}


# ---------------------------------------------------------------------------------------------
def build_map(name, reg):
    m = L.get_map(name)
    path = m["path"]
    ctx = Ctx(reg)
    state = open_or_create(path)
    removed = clear_generated(ctx)
    configure_world(m)
    if m.get("lighting"):
        LIGHT.build_environment(m["lighting"], ctx.spawn)
    items = m["items"]
    failures = 0
    with unreal.ScopedSlowTask(max(1, len(items)), "Andrew's Airsoft: building %s" % m["name"]) as slow:
        slow.make_dialog(True)
        for it in items:
            if slow.should_cancel():
                C.SUMMARY.note("map build cancelled by user")
                break
            slow.enter_progress_frame(1, "%s: %s %s" % (m["name"], it["t"], it.get("id", "")))
            try:
                if it["t"] == "light":
                    _, sh = LIGHT.spawn_item_light(ctx.spawn, it)
                    ctx.shadow_lights += 1 if sh else 0
                else:
                    PLACERS[it["t"]](ctx, it)
            except Exception as e:
                failures += 1
                if failures <= 25:
                    C.warn("%s: %s %s failed: %s" % (m["name"], it["t"], it.get("id", it.get("name", "")), e))
    if ctx.shadow_lights > LIGHT.SHADOW_BUDGET:
        C.SUMMARY.note("%s has %d shadow-casting local lights (budget %d)" % (m["name"], ctx.shadow_lights,
                                                                             LIGHT.SHADOW_BUDGET))
    saved = False
    try:
        saved = _les().save_current_level()
    except Exception as e:
        C.SUMMARY.note("saving %s failed: %s" % (path, e))
    C.save_dir(C.MI_ROOT)
    for k, v in ctx.counts.items():
        C.SUMMARY.inc("%s: %s" % (m["name"], k), v)
    msg = "%-34s %s, %d old actors removed, %d items, %d failed, %s" % (
        path, state, removed, len(items), failures, "saved" if saved else "NOT SAVED")
    C.SUMMARY.maps.append(msg)
    C.log(msg)
    return saved
