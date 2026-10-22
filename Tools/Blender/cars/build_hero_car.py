"""Builds Car_Hero ("'69 Fastback", hero_car.py) and renders it.

    python build_hero_car.py -- --preview [--views 34f,side,...] [--out DIR]   # geometry check, no bake
    python build_hero_car.py -- [--res 4096|2048] [--samples N]                 # bake + export + all renders
    python build_hero_car.py -- --render-only [--samples N]                     # renders from the exported FBX
    python build_hero_car.py -- --night | --rear | --studio | --lineup          # one render

Build goes through club/build_club.build (FBX per piece under SourceAssets/Props/Car_Hero/, baked BC/N/ORM/M,
entry in Content/Airsoft/Data/PropsClub.json). Renders (Docs/Renders/Cars/):
  Hero_4K.jpg          3840x2160 night still: cold teal rain light, wet floor, a sodium pool, single overhead lamp
  Hero_Rear34.jpg      1920x1080 3/4 rear in the same night set
  Car_Hero.jpg         1920x1080 studio product shot
  _Lineup_Hero_4K.jpg  3840x2160 studio lineup next to the AVERNE cars
"""

import os
import sys
import math

HERE = os.path.dirname(os.path.abspath(__file__))
CLUB = os.path.join(HERE, "..", "club")
sys.path.insert(0, os.path.join(HERE, "..", "common"))
sys.path.insert(0, CLUB)
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector as V  # noqa: E402
import propkit as pk  # noqa: E402
import build_cars as bc  # noqa: E402  (registers the AVERNE cars; studio + render helpers)
import hero_car  # noqa: E402,F401  (registers Car_Hero)

AID = "Car_Hero"
PAINT = (0.045, 0.048, 0.052)        # dark gunmetal (linear); the stripes / hood panel are baked satin black
bc.SHOT_PAINT[AID] = (PAINT, None)
bc.FLAKE[AID] = 0.45
bc.METALLIC[AID] = 0.6
bc.SHOT_VIEW[AID] = ((1.0, -0.8, 0.16), 45)


def log(*a):
    print(*a, flush=True)


def _mat(name, col, rough, metal=0.0):
    m = bpy.data.materials.new(name)
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def night_set(objs, view, res, lens=40, margin=1.12):
    """Cold teal rain-at-night garage bay: wet glossy concrete with ripples, painted bay lines, a wall behind,
    one overhead fluorescent-ish lamp over the car, a warm sodium pool from the side, teal fill + rim, haze."""
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    lo, hi = pk.bbox_of(objs)
    c = (V(lo) + V(hi)) / 2
    world = bpy.data.worlds.new("Night")
    scn.world = world
    nt = world.node_tree
    bgn = nt.nodes.get("Background")
    bgn.inputs[0].default_value = (0.004, 0.012, 0.016, 1)
    bgn.inputs[1].default_value = 1.0
    # wet floor: dark concrete, low roughness broken up by noise puddles, fine ripple bump
    bpy.ops.mesh.primitive_plane_add(size=1, location=(c.x, c.y, 0.0))
    fl = bpy.context.active_object
    fl.scale = (40, 40, 1)
    fm = bpy.data.materials.new("WetFloor")
    nt2 = fm.node_tree
    b = nt2.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.045, 0.047, 0.05, 1)
    tc = nt2.nodes.new("ShaderNodeTexCoord")
    nz = nt2.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.35
    nz.inputs["Detail"].default_value = 6.0
    nt2.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    ramp = nt2.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.03, 0.03, 0.03, 1)
    ramp.color_ramp.elements[1].position = 0.6
    ramp.color_ramp.elements[1].color = (0.32, 0.32, 0.32, 1)
    nt2.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt2.links.new(ramp.outputs["Color"], b.inputs["Roughness"])
    rip = nt2.nodes.new("ShaderNodeTexNoise")
    rip.inputs["Scale"].default_value = 60.0
    nt2.links.new(tc.outputs["Object"], rip.inputs["Vector"])
    bump = nt2.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    nt2.links.new(rip.outputs["Fac"], bump.inputs["Height"])
    nt2.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    fl.data.materials.append(fm)
    # bay lines either side of the car
    line = _mat("BayLine", (0.55, 0.53, 0.48), 0.35)
    for s in (1, -1):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(c.x, c.y + s * 1.45, 0.002))
        ob = bpy.context.active_object
        ob.scale = (5.6, 0.1, 0.004)
        ob.data.materials.append(line)
    # back wall + pillars (concrete), so the reflections have something to show
    wall = _mat("Wall", (0.07, 0.075, 0.08), 0.8)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(c.x - 4.2, c.y, 2.0))
    ob = bpy.context.active_object
    ob.scale = (0.3, 14, 4)
    ob.data.materials.append(wall)
    for yy in (-3.4, 3.4):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(c.x - 3.0, c.y + yy, 2.0))
        ob = bpy.context.active_object
        ob.scale = (0.5, 0.5, 4)
        ob.data.materials.append(wall)
    # ceiling slab
    bpy.ops.mesh.primitive_cube_add(size=1, location=(c.x, c.y, 3.25))
    ob = bpy.context.active_object
    ob.scale = (16, 16, 0.3)
    ob.data.materials.append(wall)

    def light(kind, name, loc, energy, col, size=0.5, target=None, spot=None):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = col
        if kind == "AREA":
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = size
        elif kind == "SPOT":
            ld.spot_size = math.radians(spot or 60)
            ld.spot_blend = 0.6
            ld.shadow_soft_size = size
        else:
            ld.shadow_soft_size = size
        o = bpy.data.objects.new(name, ld)
        scn.collection.objects.link(o)
        o.location = loc
        if target is not None:
            pk.look_at(o, target)
        return o
    # the single overhead lamp: a cool-white strip right above the roof
    light("AREA", "Overhead", (c.x - 0.2, c.y, 3.05), 420, (0.80, 0.92, 1.0), size=(1.4, 0.18), target=(c.x - 0.2, c.y, 0))
    bpy.ops.mesh.primitive_cube_add(size=1, location=(c.x - 0.2, c.y, 3.08))
    ob = bpy.context.active_object
    ob.scale = (1.42, 0.2, 0.04)
    em = bpy.data.materials.new("LampLens")
    e = em.node_tree.nodes.get("Principled BSDF")
    e.inputs["Emission Color"].default_value = (0.82, 0.93, 1.0, 1)
    e.inputs["Emission Strength"].default_value = 18.0
    ob.data.materials.append(em)
    # sodium pool spilling in from the side (reflects orange in the wet floor)
    light("SPOT", "Sodium", (c.x + 1.8, c.y - 4.2, 2.8), 2600, (1.0, 0.5, 0.16), size=0.3, target=(c.x + 1.2, c.y - 1.2, 0), spot=70)
    # teal ambience: big soft fill from above-front, a cold rim from behind
    light("AREA", "TealFill", (c.x + 5.0, c.y + 3.0, 2.6), 520, (0.15, 0.6, 0.62), size=(4.0, 2.0), target=c)
    light("AREA", "Rim", (c.x - 3.6, c.y + 2.6, 1.8), 700, (0.45, 0.75, 0.95), size=(1.5, 1.0), target=c)
    light("AREA", "Kick", (c.x + 2.0, c.y - 3.5, 0.5), 160, (0.2, 0.55, 0.7), size=(2.0, 0.6), target=(c.x, c.y, 0.5))
    # thin haze for the shafts
    vol = bpy.data.materials.new("Haze")
    vt = vol.node_tree
    vt.nodes.clear()
    out = vt.nodes.new("ShaderNodeOutputMaterial")
    pv = vt.nodes.new("ShaderNodeVolumePrincipled")
    pv.inputs["Density"].default_value = 0.006
    pv.inputs["Color"].default_value = (0.7, 0.85, 0.9, 1)
    vt.links.new(pv.outputs[0], out.inputs["Volume"])
    bpy.ops.mesh.primitive_cube_add(size=1, location=(c.x, c.y, 1.55))
    hz = bpy.context.active_object
    hz.scale = (12, 12, 3.1)
    hz.data.materials.append(vol)
    hz.visible_shadow = False
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scn.collection.objects.link(cam)
    scn.camera = cam
    cam.data.sensor_width = 36
    bc._frame(cam, lo, hi, view, lens, res[0] / res[1], margin)
    scn.cycles.volume_bounces = 1
    scn.cycles.volume_step_rate = 4.0
    return cam


def night_shot(name, view, res, samples, lens=40, margin=1.12):
    pk.reset_scene()
    objs = bc.import_car(AID)
    # Emissive piece lit: parking lamps on, as Andrew's car sits ready
    night_set(objs, view, res, lens=lens, margin=margin)
    bc.render_jpg(os.path.join(bc.OUT_DIR, name), res, samples)


def lineup(res=(3840, 2160), samples=56):
    pk.reset_scene()
    allo = []
    place = {"Car_Hero": (0.7, 6.4, -28), "Car_Limousine": (0.0, 3.9, -28), "Car_GrandTourer": (-0.7, 1.3, -28),
             "Car_Hypercar": (-1.4, -1.25, -28), "Car_SUV": (-2.1, -3.85, -28)}
    for aid in ["Car_Hero"] + bc.CARS:
        x, y, yaw = place[aid]
        allo += bc.import_car(aid, at=(x, y, 0), yaw=yaw)
    lo, hi = pk.bbox_of(allo)
    bc.car_studio(lo, hi, view=(1.0, -0.42, 0.24), lens=45, res=res, margin=1.04)
    bc.render_jpg(os.path.join(bc.OUT_DIR, "_Lineup_Hero_4K.jpg"), res, samples)


def main(argv):
    res = int(argv[argv.index("--res") + 1]) if "--res" in argv else 4096
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else None
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(bc.OUT_DIR, "_preview")
    flags = set(a for a in argv if a.startswith("--"))
    if "--views" in argv:
        bc.VIEWS.extend(argv[argv.index("--views") + 1].split(","))
    if "--preview" in flags:
        bc.preview(AID, out, samples=samples or 24)
        return
    one = flags & {"--night", "--rear", "--studio", "--lineup"}
    if not one and "--render-only" not in flags:
        import build_club
        log(f"== {AID}")
        entry = build_club.build(AID, res, do_render=False)
        entry["DisplayName"] = hero_car.DISPLAY_NAME
        pk.update_json(build_club.JSON_PATH, AID, entry)
    if not one or "--night" in flags:
        night_shot("Hero_4K.jpg", (1.0, -0.62, 0.12), (3840, 2160), samples or 64, lens=38)
    if not one or "--rear" in flags:
        night_shot("Hero_Rear34.jpg", (-1.0, -0.7, 0.16), (1920, 1080), samples or 64, lens=40)
    if not one or "--studio" in flags:
        bc.product_shot(AID, samples=samples or 80)
    if not one or "--lineup" in flags:
        lineup(samples=samples or 56)


if __name__ == "__main__":
    argv = sys.argv[1:]
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv
    main(argv)
