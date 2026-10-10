"""Andrew's Airsoft - map layouts as plain data.

This module never imports `unreal`. It is loaded by the editor setup (levels.py) and by
Tools/Unreal/check_layouts.py (plain Python), so every rule it encodes is checked outside the
editor before the maps are built.

Conventions
-----------
* Layout coordinates are in METRES (x, y, z) and degrees; levels.py multiplies by 100.
  Unreal axes: +X forward/east on the plans, +Y right/south on the plans (top view), +Z up.
* Asset bounds (KNOWN_ASSETS and the JSON files) are in CENTIMETRES, floor-centre origin,
  front facing +X, exactly like Content/Airsoft/Data/*.json.
* yaw rotates local +X toward +Y (Unreal yaw). A prop with yaw 90 faces +Y.

Item kinds (dicts with key "t"):
    prop       placed asset (asset id "id"), optional tint / scale / display / light / nocoll
    box        procedural block (engine cube) with a tileable material, centre "p", size "s"
    blocker    invisible pawn-only blocker (keeps players in bounds / off roofs)
    start      AirsoftTeamStart (team None/Blue/Red), "p" is the floor point
    objective  AirsoftObjective (letter A/B/C), "p" is the floor point
    target     AirsoftPracticeTarget (caption, plate size)
    light      point / spot / rect light
    sound      AmbientSound (key, spatial, radius)
    text       TextRenderActor (emissive sign text)
    capture    SphereReflectionCapture
    fog        LocalFogVolume (haze), falls back to nothing if the class is missing
    camera     CineCameraActor (main menu)
Tune numbers here and re-run `py airsoft_setup.py --skip-import --maps <Map>`.
"""

import math
import random

CM = 100.0
EYE_HEIGHT = 1.6        # standing eye height used for line-of-sight checks (m)
COVER_HEIGHT = 0.9      # crouch cover (m)
STEP_HEIGHT = 0.45      # character max step (m)
START_Z_OFFSET = 0.95   # PlayerStart capsule centre above the floor (m)

# ---------------------------------------------------------------------------------------------
# Weapons on display (must match AirsoftWeaponData ids)
# ---------------------------------------------------------------------------------------------
PRIMARY_IDS = ["M4", "AK74", "SR25", "VSR", "M249", "MP5", "VECTOR", "MP7", "P90", "M870"]
SECONDARY_IDS = ["G17", "G18", "M1911", "DEAGLE"]
WEAPON_IDS = PRIMARY_IDS + SECONDARY_IDS
ATTACHMENT_IDS = ["RedDot", "Holo", "Scope4x", "ScopeLong", "Suppressor", "Compensator", "VerticalGrip",
                  "AngledGrip", "Laser", "Magnifier", "Bipod", "ExtMag", "DrumMag"]

# ---------------------------------------------------------------------------------------------
# Colours (linear) shared by tints, emissive boxes and lights
# ---------------------------------------------------------------------------------------------
TINTS = {
    "White": (0.8, 0.8, 0.78), "Grey": (0.3, 0.31, 0.32), "Black": (0.012, 0.012, 0.014),
    "Gunmetal": (0.07, 0.075, 0.08), "DeepRed": (0.22, 0.008, 0.012), "Red": (0.42, 0.04, 0.03),
    "Blue": (0.04, 0.13, 0.32), "Green": (0.07, 0.2, 0.09), "Rust": (0.36, 0.13, 0.05),
    "Sand": (0.5, 0.4, 0.26), "DeepGreen": (0.02, 0.06, 0.035), "Burgundy": (0.16, 0.012, 0.03),
    "Orange": (0.7, 0.22, 0.03), "Teal": (0.02, 0.18, 0.2),
}
EMISSIVE_COLORS = {
    "Warm": (1.0, 0.7, 0.42), "Gold": (1.0, 0.76, 0.38), "Sodium": (1.0, 0.55, 0.2),
    "Cool": (0.72, 0.84, 1.0), "White": (1.0, 1.0, 1.0), "Magenta": (1.0, 0.06, 0.55),
    "Cyan": (0.08, 0.75, 1.0), "Red": (1.0, 0.04, 0.04), "Amber": (1.0, 0.45, 0.08),
    "Violet": (0.45, 0.1, 1.0), "Green": (0.1, 1.0, 0.3), "Orange": (1.0, 0.3, 0.03),
}

# Paint variants created for tintable (role-mask) props; JSON "TintVariants" are merged on top.
TINT_VARIANTS = {
    "Container_20ft": ["Red", "Blue", "Green", "Rust", "Sand", "Grey"],
    "Car_Sedan": ["Black", "DeepRed", "Gunmetal", "White"],
    "Car_Coupe": ["Black", "DeepRed", "Gunmetal", "White"],
    "BoxTruck": ["White", "Grey", "Blue"],
    "OilDrum": ["Blue", "Red", "Green"],
    "FlagPole_Objective": ["Blue", "Red"],
    "Dumpster": ["Green", "Blue", "Rust"],
}
# Default PrimaryTint baked into the base instance of masked props (guns stay white: the game tints them).
DEFAULT_TINT = {"Container_20ft": "Blue", "Car_Sedan": "Gunmetal", "Car_Coupe": "Black", "BoxTruck": "White",
                "OilDrum": "Blue", "Dumpster": "Green"}
# Car paint is glossy: TintMetallic / TintRoughness for the masked areas.
TINT_SURFACE = {"Car_Sedan": (0.55, 0.28), "Car_Coupe": (0.6, 0.25), "BoxTruck": (0.0, 0.45),
                "Container_20ft": (0.0, 0.5), "OilDrum": (0.0, 0.45), "Dumpster": (0.0, 0.5)}


# ---------------------------------------------------------------------------------------------
# Asset knowledge: category, bounds (cm, used when the JSON has no entry yet) and fallback style.
# Flags for the layout checker: solid (blocks movement), los (can block line of sight),
# core = ((minx, miny), (maxx, maxy)) smaller footprint used for movement / sight (e.g. tree trunk).
# ---------------------------------------------------------------------------------------------
def _K(cat, mn, mx, fb, **flags):
    d = {"cat": cat, "min": tuple(float(v) for v in mn), "max": tuple(float(v) for v in mx), "fb": fb}
    d.update(flags)
    return d


KNOWN_ASSETS = {
    # --- architecture kit (Tools/Blender/environment/architecture.py) ---
    "Wall_Plywood_4m": _K("Architecture", (-6, -200, 0), (6.2, 200, 300), "box:Plywood", coll="Box"),
    "Wall_Plywood_Door_4m": _K("Architecture", (-6, -200, 0), (6.2, 200, 300), "door:Plywood", coll="Complex",
                               openings=[(-60, 0, 60, 210)]),
    "Wall_Plywood_Window_4m": _K("Architecture", (-6, -200, 0), (8.7, 200, 300), "window:Plywood", coll="Complex",
                                 openings=[(-60, 120, 60, 180)]),
    "Wall_Plywood_2m": _K("Architecture", (-6, -100, 0), (6.2, 100, 300), "box:Plywood", coll="Box"),
    "Wall_Concrete_4m": _K("Architecture", (-13, -200, 0), (13, 200, 302), "box:Concrete", coll="Box"),
    "Roof_Corrugated_4m": _K("Architecture", (-200, -200, 0), (200, 200, 13.2), "box:CorrodedMetal", coll="Box"),
    "Post_Timber": _K("Architecture", (-12.5, -12.5, 0), (12.5, 12.5, 300), "box:Timber", coll="Box", los=False),
    "Platform_Timber_4m": _K("Architecture", (-60.9, -200, 0), (60.7, 200, 23), "box:Timber", coll="Box"),
    "Ladder_Metal_4m": _K("Architecture", (-17, -26.5, 0), (4.5, 26.5, 400), "ladder:PaintedSteel", coll="Box",
                          los=False),
    "Container_20ft": _K("Architecture", (-303, -122, 0), (303, 122, 259.1), "box:PaintedSteel", coll="Box",
                         tintable=True),
    "Watchtower": _K("Architecture", (-270, -175, 0), (175, 175, 790), "tower:Timber", coll="Complex", los=False,
                     core=((-175, -175), (175, 175))),
    "FloodlightTower": _K("Architecture", (-50, -95, 0), (50, 95, 1040), "floodlight:PaintedSteel", coll="Convex",
                          los=False, core=((-50, -50), (50, 50))),
    "SpawnTent": _K("Architecture", (-310, -340, 0), (310, 340, 290), "tent:Canvas", coll="Complex",
                    core=((-300, -200), (300, 200))),
    "NettingFence_4m": _K("Architecture", (-16, -205, 0), (16, 205, 335), "fence:PaintedSteel", coll="Complex",
                          los=False),
    "Bunker_Logs": _K("Architecture", (-325, -325, 0), (325, 325, 195), "bunker:Timber", coll="Complex"),
    # --- field props (Tools/Blender/environment/props.py) ---
    "SandbagWall_3m": _K("Props", (-33, -150, 0), (33, 150, 95), "box:Burlap", coll="Complex"),
    "SandbagCorner": _K("Props", (-95, -95, 0), (95, 95, 95), "lcorner:Burlap", coll="Complex"),
    "Tire": _K("Props", (-33, -33, -0.5), (33, 33, 21.5), "cyl:Rubber", coll="Convex", los=False),
    "TireStack": _K("Props", (-34, -34, 0), (34, 34, 62), "cyl:Rubber", coll="Convex"),
    "CableSpool": _K("Props", (-100, -56, 0), (100, 56, 200), "spool:Timber", coll="Convex"),
    "Pallet": _K("Props", (-60, -40, 0), (60, 40, 14.4), "box:Timber", coll="Box"),
    "PalletStack": _K("Props", (-62, -42, 0), (62, 42, 58), "box:Timber", coll="Box"),
    "HayBale_Round": _K("Props", (-75, -60, 0), (75, 60, 150), "bale:Straw", coll="Convex"),
    "HayBale_Square": _K("Props", (-50, -24, 0), (50, 24, 38), "box:Straw", coll="Box"),
    "Barricade_Plywood_3m": _K("Props", (-115, -150, 0), (5, 150, 206), "barricade_win:Plywood", coll="Complex",
                               core=((-12, -150), (5, 150))),
    "Barricade_Plywood_4m": _K("Props", (-115, -200, 0), (5, 200, 206), "barricade:Plywood", coll="Box",
                               core=((-12, -200), (5, 200))),
    "OilDrum": _K("Props", (-30.1, -29.8, 0), (29.8, 29.8, 88.9), "cyl:PaintedSteel", coll="Convex", tintable=True),
    "Crate_Wood": _K("Props", (-50, -35, 0), (50, 35, 60), "box:OSB", coll="Box"),
    "Crate_Ammo": _K("Props", (-45, -23, 0), (45, 23, 36), "box:PaintedSteel", coll="Box", tint="Green"),
    "WreckedCar": _K("Props", (-230, -88, 0), (230, 88, 141), "car:CorrodedMetal", coll="Convex"),
    "Tree_Oak_A": _K("Props", (-450, -450, 0), (450, 450, 1300), "tree:Bark", coll="Convex",
                     core=((-35, -35), (35, 35))),
    "Tree_Oak_B": _K("Props", (-500, -500, 0), (500, 500, 1100), "tree:Bark", coll="Convex",
                     core=((-40, -40), (40, 40))),
    "Tree_Oak_C": _K("Props", (-380, -380, 0), (380, 380, 1450), "tree:Bark", coll="Convex",
                     core=((-32, -32), (32, 32))),
    "Bush_A": _K("Props", (-130, -130, 0), (130, 130, 180), "bush:Foliage", coll="Convex"),
    "Rock_A": _K("Props", (-100, -80, 0), (100, 80, 110), "rock:Granite", coll="Convex"),
    "Rock_B": _K("Props", (-70, -55, 0), (70, 55, 60), "rock:Granite", coll="Convex"),
    "FlagPole_Objective": _K("Props", (-25, -25, 0), (125, 25, 630), "cyl:PaintedSteel", coll="Convex", los=False),
    "SteelTarget": _K("Props", (-40, -50, 0), (40, 50, 130), "box:PaintedSteel", coll="Convex", los=False),
    "ChronoTable": _K("Props", (-38, -92, 0), (38, 92, 95), "box:Plywood", coll="Box", los=False),
    # --- club (Tools/Blender/club) ---
    "Armchair_Leather": _K("Props", (-45, -46, 0), (46.4, 46, 88.5), "box:Leather", coll="Convex", los=False),
    "BackBar_4m": _K("Props", (-30, -203, 0), (28.3, 203, 260), "backbar:Walnut", coll="Box"),
    "BarCounter_4m": _K("Props", (-60.8, -202, 0), (39.1, 202, 108), "box:Walnut", coll="Box"),
    "BarStool": _K("Props", (-27.4, -24, 0), (23.8, 24, 96.2), "cyl:Leather", coll="Convex", los=False),
    "BoothSofa_Curved": _K("Props", (-113, -152, 0), (114.7, 152, 115.3), "booth:Leather", coll="Complex"),
    "BoothTable": _K("Props", (-45.5, -45.5, 0), (45.5, 45.5, 74), "cyl:MarbleBlack", coll="Convex", los=False),
    "BoxTruck": _K("Props", (-378.3, -153.5, 0), (372, 153.5, 335), "truck:PaintedSteel", coll="Convex",
                   tintable=True),
    "Car_Coupe": _K("Props", (-269.8, -115, 0), (269.8, 115, 134.4), "car:PaintedSteel", coll="Convex",
                    tintable=True),
    "Car_Sedan": _K("Props", (-256, -118.5, 0), (256.5, 118.5, 146.5), "car:PaintedSteel", coll="Convex",
                    tintable=True),
    "Chandelier": _K("Props", (-44.1, -44.1, 0), (44.1, 44.1, 123), "hanglamp:Brass", coll="Convex", los=False),
    "DJBooth": _K("Props", (-43, -122, 0), (45.6, 122, 120.8), "box:MarbleBlack", coll="Box"),
    "Dumpster": _K("Props", (-58, -100, 0), (58, 100, 130), "box:PaintedSteel", coll="Box", tintable=True),
    "HighTable": _K("Props", (-37.4, -37.4, 0), (37.4, 37.4, 107), "cyl:Walnut", coll="Convex", los=False),
    "Kiosk": _K("Props", (-80, -122, 0), (110, 122, 245), "box:PaintedSteel", coll="Box"),
    "MovingHeadLight": _K("Props", (-22.3, -23.3, -0.8), (22.2, 23.3, 65.7), "box:PaintedSteel", coll="Box",
                          los=False),
    "NeonSign_Velvet": _K("Props", (-4, -62.5, -0.5), (4.3, 62.5, 62), "neon:PaintedSteel", coll="Box"),
    "Planter_Concrete": _K("Props", (-32.3, -32.8, 0), (32.3, 32, 126.8), "planter:Concrete", coll="Convex",
                           los=False),
    "SpeakerStack": _K("Props", (-71, -58.6, -1.2), (2, 58.6, 237.4), "box:Rubber", coll="Box"),
    "StreetLamp": _K("Props", (-22.2, -35.5, 0), (22.2, 35.5, 414.5), "streetlamp:PaintedSteel", coll="Convex",
                     los=False, core=((-22, -22), (22, 22))),
    "VelvetRopePost": _K("Props", (-16.7, -16.7, -0.3), (16.7, 144.2, 99), "rope:Brass", coll="Convex", los=False),
    "WallSconce": _K("Props", (-12, -7.5, 0), (14.5, 7.5, 36.5), "sconce:Brass", coll="Box", los=False),
    "Bollard": _K("Props", (-12, -12, 0), (12, 12, 100), "cyl:PaintedSteel", coll="Convex", los=False),
    "TrashBags": _K("Props", (-55, -55, 0), (60, 55, 75), "rock:Rubber", coll="Convex", los=False),
    # --- armory (Tools/Blender/club/armory_assets.py) ---
    "WallPanel_Walnut_4m": _K("Props", (-3, -200, 0), (9, 200, 300), "box:Walnut", coll="Box"),
    "ArmorySign": _K("Props", (-3, -80, 0), (5, 80, 40), "sign:Walnut", coll="Box", los=False),
    "GunDisplayBay": _K("Props", (-13, -73, 0), (16.5, 73, 120), "bay:Walnut", coll="Box", los=False),
    "ArmoryCounter": _K("Props", (-40, -122, 0), (42, 122, 104.5), "box:Walnut", coll="Box"),
    "Mannequin_Torso": _K("Props", (-35, -35, 0), (35, 35, 175), "mannequin:Canvas", coll="Convex", los=False),
    "CeilingLight_Brass": _K("Props", (-30, -30, 0), (30, 30, 70), "hanglamp:Brass", coll="Convex", los=False),
    "RugPersian": _K("Props", (-157, -107, 0), (157, 107, 2), "flat:Carpet", coll="None", solid=False, los=False),
    "GunCase_Hard": _K("Props", (-55, -20, 0), (55, 20, 14), "box:Rubber", coll="Box", los=False),
    "AmmoCrate_Wood": _K("Props", (-38, -22, 0), (38, 22, 32), "box:Timber", coll="Box", los=False),
    "BankersLamp": _K("Props", (-14, -14, 0), (18, 14, 42), "desklamp:Brass", coll="Convex", los=False),
}

# Points used when the JSON has no layout yet (cm, asset space).
DEFAULT_POINTS = {
    "GunDisplayBay": {"GunMount": (-3.0, 0.0, 61.5)},
    "Chandelier": {"CeilingMount": (0.0, 0.0, 123.0), "Light": (0.0, 0.0, 55.0)},
    "CeilingLight_Brass": {"CeilingMount": (0.0, 0.0, 70.0), "Light": (0.0, 0.0, 30.0)},
    "WallSconce": {"WallMount": (-12.0, 0.0, 13.0), "Light": (7.0, 0.0, 29.0)},
    "StreetLamp": {"Light": (0.0, 0.0, 344.0)},
    "NeonSign_Velvet": {"WallMount": (-4.0, 0.0, 31.0), "Light": (13.5, 0.0, 31.0)},
    "BankersLamp": {"Light": (9.0, 0.0, 38.5)},
    "FloodlightTower": {"Light": (40.0, 0.0, 1005.0)},
    "MovingHeadLight": {"Beam": (17.2, 0.0, 55.0)},
    "BackBar_4m": {"LEDTop": (2.0, 0.0, 246.9)},
    "ArmoryCounter": {"Top": (0.0, 0.0, 104.5)},
}


def category_of(aid, json_assets=None):
    if json_assets and aid in json_assets:
        return json_assets[aid].get("_Category", KNOWN_ASSETS.get(aid, {}).get("cat", "Props"))
    if aid in KNOWN_ASSETS:
        return KNOWN_ASSETS[aid]["cat"]
    if aid in WEAPON_IDS or aid == "GRENADE":
        return "Weapons"
    if aid in ATTACHMENT_IDS:
        return "Attachments"
    return "Props"


def asset_bounds(aid, json_assets=None):
    """(min, max) in cm. JSON wins over the built-in table."""
    if json_assets and aid in json_assets:
        b = json_assets[aid].get("Bounds")
        if b and "Min" in b and "Max" in b:
            return tuple(float(v) for v in b["Min"]), tuple(float(v) for v in b["Max"])
    k = KNOWN_ASSETS.get(aid)
    if k:
        return k["min"], k["max"]
    return (-50.0, -50.0, 0.0), (50.0, 50.0, 100.0)


def asset_point(aid, name, json_assets=None):
    if json_assets and aid in json_assets:
        p = (json_assets[aid].get("Points") or {}).get(name)
        if p and len(p) >= 3:
            return tuple(float(v) for v in p[:3])
    return DEFAULT_POINTS.get(aid, {}).get(name)


def has_fallback(aid):
    return aid in KNOWN_ASSETS


# ---------------------------------------------------------------------------------------------
# Fallback geometry: engine basic shapes shaped like the asset (local cm, asset space).
# Each part: shape cube|cyl|sphere, min/max (cm), mat (tileable id, "Foliage", "Emissive:<Colour>"),
# coll (bool), axis ("z" default, "x"/"y" for lying cylinders).
# ---------------------------------------------------------------------------------------------
def _part(shape, mn, mx, mat, coll=True, axis="z"):
    return {"shape": shape, "min": tuple(mn), "max": tuple(mx), "mat": mat, "coll": coll, "axis": axis}


def fallback_parts(aid, bmin, bmax):
    style = KNOWN_ASSETS.get(aid, {}).get("fb", "box:Concrete")
    kind, _, mat = style.partition(":")
    mat = mat or "Concrete"
    x0, y0, z0 = bmin
    x1, y1, z1 = bmax
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    P = []
    if kind == "box":
        P.append(_part("cube", bmin, bmax, mat))
    elif kind == "cyl":
        P.append(_part("cyl", bmin, bmax, mat))
    elif kind in ("rock", "bush"):
        P.append(_part("sphere", (x0, y0, z0 - (z1 - z0) * 0.25), (x1, y1, z1), mat))
    elif kind == "flat":
        P.append(_part("cube", (x0, y0, 0), (x1, y1, max(z1, 1.0)), mat, coll=False))
    elif kind == "door":
        P += [_part("cube", (x0, y0, 0), (x1, -60, z1), mat), _part("cube", (x0, 60, 0), (x1, y1, z1), mat),
              _part("cube", (x0, -60, 210), (x1, 60, z1), mat)]
    elif kind == "window":
        P += [_part("cube", (x0, y0, 0), (x1, -60, z1), mat), _part("cube", (x0, 60, 0), (x1, y1, z1), mat),
              _part("cube", (x0, -60, 0), (x1, 60, 120), mat), _part("cube", (x0, -60, 180), (x1, 60, z1), mat)]
    elif kind == "ladder":
        P += [_part("cube", (-6, -24, 0), (0, -18, z1), mat), _part("cube", (-6, 18, 0), (0, 24, z1), mat)]
        for z in range(30, int(z1), 30):
            P.append(_part("cube", (-5, -18, z), (-1, 18, z + 3), mat, coll=False))
    elif kind == "tower":
        for sx in (-1, 1):
            for sy in (-1, 1):
                P.append(_part("cube", (sx * 140 - 11, sy * 140 - 11, 0), (sx * 140 + 11, sy * 140 + 11, 500), mat))
        P.append(_part("cube", (-150, -150, 477), (150, 150, 500), mat))
        for (a, b) in (((-150, -150), (-140, 150)), ((140, -150), (150, 150)), ((-150, -150), (150, -140)),
                       ((-150, 140), (150, 150))):
            P.append(_part("cube", (a[0], a[1], 500), (b[0], b[1], 605), "Plywood"))
        P.append(_part("cube", (-175, -160, 735), (175, 160, 760), "CorrodedMetal"))
        for sx in (-1, 1):
            for sy in (-1, 1):
                P.append(_part("cube", (sx * 120 - 7, sy * 120 - 7, 500), (sx * 120 + 7, sy * 120 + 7, 735), mat))
    elif kind == "floodlight":
        P += [_part("cube", (-50, -50, 0), (50, 50, 45), "Concrete"),
              _part("cyl", (-11, -11, 45), (11, 11, 975), mat),
              _part("cube", (-10, -95, 975), (14, 95, 1035), mat),
              _part("cube", (14, -88, 985), (22, 88, 1025), "Emissive:Warm", coll=False)]
    elif kind == "tent":
        P += [_part("cube", (-300, -200, 0), (300, 200, 160), mat),
              _part("cube", (-300, -130, 160), (300, 130, 240), mat),
              _part("cube", (-300, -60, 240), (300, 60, 290), mat)]
    elif kind == "fence":
        P += [_part("cyl", (-5, -205, 0), (5, -195, 330), mat), _part("cyl", (-5, 195, 0), (5, 205, 330), mat),
              _part("cube", (4, -196, 10), (7, 196, 300), "Netting")]
    elif kind == "bunker":
        t = 32
        P += [_part("cube", (x1 - t, y0, 0), (x1, y1, 160), mat),                  # front wall (slit is cosmetic)
              _part("cube", (x0, y0, 0), (x1, y0 + t, 160), mat),
              _part("cube", (x0, y1 - t, 0), (x1, y1, 160), mat),
              _part("cube", (x0, y0, 0), (x0 + t, -55, 160), mat),
              _part("cube", (x0, 55, 0), (x0 + t, y1, 160), mat),
              _part("cube", (x0, -55, 106), (x0 + t, 55, 160), mat),
              _part("cube", (x0, y0, 160), (x1, y1, z1), "Burlap")]
    elif kind in ("barricade", "barricade_win"):
        if kind == "barricade_win":
            P += [_part("cube", (-2, y0, 6), (4, -40, 206), mat), _part("cube", (-2, 40, 6), (4, y1, 206), mat),
                  _part("cube", (-2, -40, 6), (4, 40, 110), mat), _part("cube", (-2, -40, 150), (4, 40, 206), mat)]
        else:
            P.append(_part("cube", (-2, y0, 6), (4, y1, 206), mat))
        P.append(_part("cube", (-115, y0, 0), (-5, y0 + 9, 8), "Timber"))
        P.append(_part("cube", (-115, y1 - 9, 0), (-5, y1, 8), "Timber"))
    elif kind == "lcorner":
        P += [_part("cube", (30, -95, 0), (95, 95, z1), mat), _part("cube", (-95, 30, 0), (30, 95, z1), mat)]
    elif kind == "spool":
        P.append(_part("cyl", (x0, -56, 0), (x1, 56, z1), mat, axis="y"))
    elif kind == "bale":
        P.append(_part("cyl", (x0, y0, 0), (x1, y1, z1), mat, axis="y"))
    elif kind == "tree":
        h = z1 - z0
        P += [_part("cyl", (-32, -32, 0), (32, 32, h * 0.55), mat),
              _part("sphere", (x0 * 0.85, y0 * 0.85, h * 0.32), (x1 * 0.85, y1 * 0.85, h), "Foliage", coll=False)]
    elif kind == "car":
        L = x1 - x0
        P += [_part("cube", (x0, y0 + 4, 18), (x1, y1 - 4, z1 * 0.58), mat),
              _part("cube", (x0 + L * 0.28, y0 + 14, z1 * 0.58), (x1 - L * 0.3, y1 - 14, z1), mat),
              _part("cyl", (x0 + L * 0.13, y0, 0), (x0 + L * 0.27, y1, 66), "Rubber", axis="y"),
              _part("cyl", (x1 - L * 0.27, y0, 0), (x1 - L * 0.13, y1, 66), "Rubber", axis="y")]
    elif kind == "truck":
        P += [_part("cube", (190, y0 + 10, 30), (x1, y1 - 10, 260), mat),
              _part("cube", (x0, y0, 55), (180, y1, z1), mat),
              _part("cyl", (230, y0, 0), (330, y1, 100), "Rubber", axis="y"),
              _part("cyl", (-300, y0, 0), (-200, y1, 100), "Rubber", axis="y")]
    elif kind == "backbar":
        P += [_part("cube", bmin, bmax, mat), _part("cube", (x1, y0 + 10, 240), (x1 + 2, y1 - 10, 246),
                                                         "Emissive:Amber", coll=False)]
    elif kind == "booth":
        P += [_part("cube", (x0, y0, 0), (x0 + 60, y1, z1), mat), _part("cube", (x0, y0, 0), (x1 - 80, y0 + 60, 45), mat),
              _part("cube", (x0, y1 - 60, 0), (x1 - 80, y1, 45), mat), _part("cube", (x0 + 60, y0, 0), (x0 + 120, y1, 45), mat)]
    elif kind == "hanglamp":
        P += [_part("cyl", (-2, -2, z1 * 0.5), (2, 2, z1), mat, coll=False),
              _part("sphere", (x0 * 0.6, y0 * 0.6, 0), (x1 * 0.6, y1 * 0.6, z1 * 0.55), "Emissive:Warm", coll=False)]
    elif kind == "desklamp":
        P += [_part("cube", (-10, -8, 0), (8, 8, 3), mat, coll=False), _part("cyl", (-2, -2, 0), (2, 2, 32), mat, coll=False),
              _part("cube", (-4, -12, 30), (18, 12, 42), "Emissive:Green", coll=False)]
    elif kind == "streetlamp":
        P += [_part("cyl", (-12, -12, 0), (12, 12, 400), mat), _part("cube", (-20, -20, 325), (20, 20, 370), "Emissive:Sodium", coll=False),
              _part("cube", (-22, -22, 370), (22, 22, 395), mat, coll=False)]
    elif kind == "sconce":
        P += [_part("cube", (x0, -6, 0), (x0 + 3, 6, 25), mat, coll=False),
              _part("cube", (x0 + 3, -5, 15), (x1, 5, z1), "Emissive:Warm", coll=False)]
    elif kind == "neon":
        P += [_part("cube", (x0, y0, z0), (x0 + 3, y1, z1), mat), _part("cube", (x0 + 3, y0 + 6, 8), (x1, y1 - 6, z1 - 8),
                                                                      "Emissive:Magenta", coll=False)]
    elif kind == "sign":
        P += [_part("cube", (x0, y0, z0), (x1 - 1, y1, z1), mat), _part("cube", (x1 - 1, y0 + 8, 8), (x1, y1 - 8, z1 - 8),
                                                                     "Emissive:Gold", coll=False)]
    elif kind == "bay":
        P += [_part("cube", (x0, y0, z0), (x0 + 6, y1, z1), mat), _part("cube", (x0, y0, z0), (x1, y1, z0 + 6), mat),
              _part("cube", (x0, y0, z1 - 6), (x1, y1, z1), mat),
              _part("cube", (x0, y0, z0), (x1, y0 + 6, z1), mat), _part("cube", (x0, y1 - 6, z0), (x1, y1, z1), mat),
              _part("cube", (x0 + 6, y0 + 10, z1 - 8), (x0 + 9, y1 - 10, z1 - 6), "Emissive:Warm", coll=False)]
    elif kind == "mannequin":
        P += [_part("cyl", (-30, -30, 0), (30, 30, 6), "Walnut"), _part("cyl", (-3, -3, 0), (3, 3, 100), "Walnut"),
              _part("cube", (-14, -24, 100), (14, 24, 165), mat), _part("sphere", (-9, -9, 160), (9, 9, 178), mat)]
    elif kind == "planter":
        P += [_part("cube", (x0, y0, 0), (x1, y1, 55), "Concrete"), _part("sphere", (x0, y0, 40), (x1, y1, z1), "Foliage",
                                                                         coll=False)]
    elif kind == "rope":
        P += [_part("cyl", (-8, -8, 0), (8, 8, 99), mat), _part("cyl", (-17, -17, 0), (17, 17, 4), mat),
              _part("cube", (-1.5, 4, 82), (1.5, 140, 88), "Velvet", coll=False)]
    else:
        P.append(_part("cube", bmin, bmax, mat))
    return P


# ---------------------------------------------------------------------------------------------
# Item constructors
# ---------------------------------------------------------------------------------------------
def prop(aid, x, y, z=0.0, yaw=0.0, **kw):
    d = {"t": "prop", "id": aid, "p": (float(x), float(y), float(z)), "yaw": float(yaw)}
    d.update(kw)
    return d


def box(cx, cy, cz, sx, sy, sz, mat, yaw=0.0, **kw):
    d = {"t": "box", "p": (float(cx), float(cy), float(cz)), "s": (float(sx), float(sy), float(sz)),
         "yaw": float(yaw), "mat": mat}
    d.update(kw)
    return d


def slab(x0, y0, x1, y1, z0, z1, mat, **kw):
    """Axis-aligned block from extents (m)."""
    return box((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), mat, **kw)


def patch(x0, y0, x1, y1, top, mat, **kw):
    """Thin ground decal block (no collision)."""
    kw.setdefault("coll", False)
    kw.setdefault("cast", False)
    return slab(x0, y0, x1, y1, top - 0.02, top, mat, **kw)


def wall_run(axis, fixed, a0, a1, z0, z1, thick, mat, openings=(), **kw):
    """Wall along `axis` ('x' or 'y') at coordinate `fixed`, from a0 to a1.
    openings: (b0, b1, top) gaps from the floor up to `top`, lintel above."""
    out = []
    cuts = sorted(openings)
    cur = a0
    for (b0, b1, top) in cuts:
        if b0 > cur:
            out.append((cur, b0, z0, z1))
        if top < z1:
            out.append((b0, b1, z0 + top, z1))
        cur = b1
    if cur < a1:
        out.append((cur, a1, z0, z1))
    items = []
    for (s0, s1, zz0, zz1) in out:
        if axis == "x":
            items.append(slab(s0, fixed - thick / 2, s1, fixed + thick / 2, zz0, zz1, mat, **kw))
        else:
            items.append(slab(fixed - thick / 2, s0, fixed + thick / 2, s1, zz0, zz1, mat, **kw))
    return items


def stairs(x, y, z0, z1, direction, width, mat, rise=0.2, run=0.3, **kw):
    """Solid steps starting at (x, y) (bottom edge centre) climbing along direction (+x,-x,+y,-y)."""
    n = max(1, int(round((z1 - z0) / rise)))
    rise = (z1 - z0) / n
    items = []
    for k in range(1, n + 1):
        d0, d1 = (k - 1) * run, k * run
        top = z0 + k * rise
        if direction in ("+x", "-x"):
            s = 1 if direction == "+x" else -1
            xa, xb = x + s * d0, x + s * d1
            items.append(slab(min(xa, xb), y - width / 2, max(xa, xb), y + width / 2, z0, top, mat, walk=True, **kw))
        else:
            s = 1 if direction == "+y" else -1
            ya, yb = y + s * d0, y + s * d1
            items.append(slab(x - width / 2, min(ya, yb), x + width / 2, max(ya, yb), z0, top, mat, walk=True, **kw))
    return items


def blocker(x0, y0, x1, y1, z0, z1, **kw):
    d = slab(x0, y0, x1, y1, z0, z1, "Blocker", **kw)
    d["t"] = "blocker"
    return d


def start(x, y, team, yaw, z=0.0):
    return {"t": "start", "p": (float(x), float(y), float(z)), "yaw": float(yaw), "team": team}


def objective(letter, x, y, z=0.0, radius=5.0, half_height=2.5):
    return {"t": "objective", "letter": letter, "p": (float(x), float(y), float(z)), "radius": radius,
            "half_height": half_height}


def light(kind, x, y, z, **kw):
    d = {"t": "light", "kind": kind, "p": (float(x), float(y), float(z))}
    d.update(kw)
    return d


def sound(key, x, y, z, spatial=False, radius=10.0, falloff=20.0, volume=1.0):
    return {"t": "sound", "key": key, "p": (float(x), float(y), float(z)), "spatial": spatial, "radius": radius,
            "falloff": falloff, "volume": volume}


def text(x, y, z, yaw, txt, size=60.0, color="Warm", glow=6.0):
    return {"t": "text", "p": (float(x), float(y), float(z)), "yaw": float(yaw), "text": txt, "size": size,
            "color": color, "glow": glow}


def capture(x, y, z, radius):
    return {"t": "capture", "p": (float(x), float(y), float(z)), "radius": radius}


def fogvol(x, y, z, sx, sy, sz, density=0.6, color=(0.7, 0.6, 0.6)):
    return {"t": "fog", "p": (float(x), float(y), float(z)), "s": (sx, sy, sz), "density": density, "color": color}


def rot2(x, y, yaw):
    a = math.radians(yaw)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def rot180(items, cx=0.0, cy=0.0, swap_tints=True):
    """Point-symmetric copy (180 deg about (cx, cy)): Blue <-> Red, objective A <-> C.
    An item may carry "east": {...} to override fields in the rotated copy (theme swaps)."""
    swap = {"Blue": "Red", "Red": "Blue"}
    out = []
    for it in items:
        n = dict(it)
        x, y, z = it["p"]
        n["p"] = (2 * cx - x, 2 * cy - y, z)
        if "yaw" in n:
            n["yaw"] = (n["yaw"] + 180.0) % 360.0
        if n["t"] == "start":
            n["team"] = swap.get(n["team"], n["team"])
        if n["t"] == "objective":
            n["letter"] = {"A": "C", "C": "A"}.get(n["letter"], n["letter"])
        if swap_tints and n.get("tint") in swap:
            n["tint"] = swap[n["tint"]]
        over = n.pop("east", None)
        n.pop("west", None)
        if over:
            n.update(over)
        out.append(n)
    return out


def scatter(seed, count, region, avoid, min_dist, ids, yaw_random=True, keep_out=None):
    """Deterministic scatter of props in region (x0,y0,x1,y1) outside `keep_out` rects."""
    rng = random.Random(seed)
    pts = []
    tries = 0
    while len(pts) < count and tries < count * 400:
        tries += 1
        x = rng.uniform(region[0], region[2])
        y = rng.uniform(region[1], region[3])
        if keep_out and any(k[0] <= x <= k[2] and k[1] <= y <= k[3] for k in keep_out):
            continue
        if any((x - p[0]) ** 2 + (y - p[1]) ** 2 < min_dist ** 2 for p in pts + list(avoid)):
            continue
        pts.append((x, y))
    out = []
    for (x, y) in pts:
        aid = ids[rng.randrange(len(ids))]
        out.append(prop(aid, round(x, 2), round(y, 2), 0.0, round(rng.uniform(0, 360), 1) if yaw_random else 0.0))
    return out


# --- 4 m modular plywood buildings ---------------------------------------------------------
_WALL_ID = {"W": "Wall_Plywood_4m", "D": "Wall_Plywood_Door_4m", "O": "Wall_Plywood_Window_4m"}


def ply_building(x0, y0, nx, ny, north="", south="", west="", east="", roof=True, roof_block=True, posts=True):
    """Walls on the cell edges of an nx * ny building of 4 m cells (top-left corner x0, y0).
    Each side string lists one code per cell: W wall, D door, O window, . open.
    north/south run west->east, west/east run north->south. Walls face outward."""
    items = []
    for i, c in enumerate(north.ljust(nx, ".")[:nx]):
        if c in _WALL_ID:
            items.append(prop(_WALL_ID[c], x0 + 4 * i + 2, y0, 0, -90))
    for i, c in enumerate(south.ljust(nx, ".")[:nx]):
        if c in _WALL_ID:
            items.append(prop(_WALL_ID[c], x0 + 4 * i + 2, y0 + 4 * ny, 0, 90))
    for j, c in enumerate(west.ljust(ny, ".")[:ny]):
        if c in _WALL_ID:
            items.append(prop(_WALL_ID[c], x0, y0 + 4 * j + 2, 0, 180))
    for j, c in enumerate(east.ljust(ny, ".")[:ny]):
        if c in _WALL_ID:
            items.append(prop(_WALL_ID[c], x0 + 4 * nx, y0 + 4 * j + 2, 0, 0))
    if roof:
        for i in range(nx):
            for j in range(ny):
                items.append(prop("Roof_Corrugated_4m", x0 + 4 * i + 2, y0 + 4 * j + 2, 3.0, 0))
        if roof_block:
            items.append(blocker(x0, y0, x0 + 4 * nx, y0 + 4 * ny, 3.1, 7.0))
    if posts:
        for (px, py) in ((x0, y0), (x0 + 4 * nx, y0), (x0, y0 + 4 * ny), (x0 + 4 * nx, y0 + 4 * ny)):
            items.append(prop("Post_Timber", px, py, 0, 0, scale=(1.0, 1.0, 1.0)))
    return items


def interior_wall(axis, fixed, a0, codes):
    """Interior plywood wall line: axis 'x' runs along X at y=fixed, 'y' along Y at x=fixed."""
    items = []
    for i, c in enumerate(codes):
        if c not in _WALL_ID:
            continue
        if axis == "x":
            items.append(prop(_WALL_ID[c], a0 + 4 * i + 2, fixed, 0, 90))
        else:
            items.append(prop(_WALL_ID[c], fixed, a0 + 4 * i + 2, 0, 0))
    return items


def fence_line(axis, fixed, a0, a1, aid="NettingFence_4m", step=4.0, yaw_extra=0.0):
    items = []
    n = max(1, int(math.ceil((a1 - a0) / step - 0.01)))
    pitch = (a1 - a0 - step) / max(1, n - 1) if n > 1 else 0.0   # modules overlap slightly, never gap
    for i in range(n):
        a = a0 + step / 2 + pitch * i
        if axis == "x":
            items.append(prop(aid, a, fixed, 0, 90 + yaw_extra))
        else:
            items.append(prop(aid, fixed, a, 0, 0 + yaw_extra))
    return items


def bay_with_display(weapon, x, y, yaw, z=0.585):
    """GunDisplayBay on a wall with its AirsoftArmoryDisplay (placed at the bay's GunMount by levels.py)."""
    return prop("GunDisplayBay", x, y, z, yaw, display=weapon)


def hanging(aid, x, y, ceiling_z, yaw=0.0, json_assets=None, **kw):
    mount = asset_point(aid, "CeilingMount", json_assets)
    mz = (mount[2] if mount else asset_bounds(aid, json_assets)[1][2]) / CM
    return prop(aid, x, y, ceiling_z - mz, yaw, hang=ceiling_z, **kw)


# =============================================================================================
# L_IronwoodYard - outdoor field, golden hour -> dusk. 130 x 90 m, three lanes, point-symmetric.
# =============================================================================================
def _ironwood():
    items = []
    W, H = 65.0, 45.0   # half extents of the playable area
    # ---- ground (full) ----
    items += [slab(-100, -80, 100, 80, -0.3, 0.0, "Grass", name="Ground", tile=3.0)]
    items += [patch(-104 / 2, -32.5, 104 / 2, -27.5, 0.010, "Dirt", name="Path_North"),
              patch(-104 / 2, 27.5, 104 / 2, 32.5, 0.010, "Dirt", name="Path_South"),
              patch(-52, -2.5, -36, 2.5, 0.010, "Dirt", name="Path_MidW"),
              patch(36, -2.5, 52, 2.5, 0.010, "Dirt", name="Path_MidE"),
              patch(-14, -14, 14, 14, 0.014, "Mud", name="Village_Pad"),
              patch(-37, -12, -15, 12, 0.018, "Gravel", name="Yard_A"),
              patch(15, -12, 37, 12, 0.018, "Gravel", name="Yard_C"),
              patch(-65, -14, -52, 14, 0.022, "Gravel", name="Spawn_Blue"),
              patch(52, -14, 65, 14, 0.022, "Gravel", name="Spawn_Red")]

    # ---- west half (Blue side). East half is its 180-degree rotation. ----
    west = []
    # Blue spawn: tent, concrete shield with a baffled centre gap, exits north/south/centre.
    # Pen: concrete U open to the map edge (exits through the back corridors), baffled front gap.
    west += [prop("SpawnTent", -61.5, 0, 0, 0)]
    # modules overlap by 6 cm so seams never leak light or sight lines
    for y in (-10.0, -6.06, 6.06, 10.0):
        west.append(prop("Wall_Concrete_4m", -54, y, 0, 0))
    for x in (-56.2, -60.14):
        west += [prop("Wall_Concrete_4m", x, -12, 0, 90), prop("Wall_Concrete_4m", x, 12, 0, 90)]
    for y in (-5.91, -1.97, 1.97, 5.91):
        west.append(prop("Wall_Concrete_4m", -50.5, y, 0, 0))
    for y in (-3.94, 0.0, 3.94):
        west.append(prop("Wall_Concrete_4m", -56.3, y, 0, 0))
    west += [blocker(-54.3, -12.2, -53.7, 12.2, 3.0, 8.0), blocker(-50.8, -8.2, -50.2, 8.2, 3.0, 8.0),
             blocker(-62.2, -12.3, -54, -11.7, 3.0, 8.0), blocker(-62.2, 11.7, -54, 12.3, 3.0, 8.0)]
    west += [prop("SandbagCorner", -50.5, -15, 0, 90), prop("SandbagCorner", -50.5, 15, 0, 0)]
    west += [prop("Crate_Ammo", -55.0, -11.0, 0, 0), prop("Crate_Ammo", -55.0, -11.0, 0.36, 4),
             prop("PalletStack", -55.2, 10.9, 0, 0), prop("Crate_Wood", -55.2, 10.9, 0.58, 3)]
    for x in (-61.0, -58.4):
        for y in (-10.4, -7.9, -5.4, 5.4, 7.9, 10.4):
            west.append(start(x, y, "Blue", 0.0))

    # Blue forward area (mid): cover leaving spawn toward A.
    west += [prop("HayBale_Round", -46, -7, 0, 0), prop("HayBale_Round", -45, 6.5, 0, 90),
             prop("PalletStack", -47.5, 1.5, 0, 10), prop("TireStack", -41.5, -3.5, 0, 0),
             prop("TireStack", -41, 4, 0, 30), prop("Tire", -40.3, 4.9, 0, 0),
             prop("SandbagWall_3m", -38.6, 0, 0, 0)]

    # A: container yard (pinwheel around the point), single + double stacks.
    west += [prop("Container_20ft", -26, -8.5, 0, 0, tint="Blue"),
             prop("Container_20ft", -25.85, -8.5, 2.591, 1.2, tint="Rust"),
             prop("Container_20ft", -26, 8.5, 0, 0, tint="Green"),
             prop("Container_20ft", -34, -2.5, 0, 90, tint="Rust",
                  east={"id": "Bunker_Logs", "p": (34.6, 2.5, 0.0), "yaw": 180.0, "tint": None}),
             prop("Container_20ft", -18, 2.5, 0, 90, tint="Blue"),
             prop("Ladder_Metal_4m", -24.0, -7.11, 0, 90)]
    west += [blocker(-29.2, -9.9, -22.8, -7.1, 5.2, 9.0), blocker(-29.2, 7.1, -22.8, 9.9, 2.6, 7.0),
             blocker(-35.4, -5.7, -32.6, 0.7, 2.6, 7.0, east={"p": (0.0, 0.0, 0.0), "skip": True}),
             blocker(-19.4, -0.7, -16.6, 5.7, 2.6, 7.0)]
    west += [prop("OilDrum", -23.4, 2.2, 0, 0, tint="Blue"), prop("OilDrum", -22.8, 2.9, 0, 40, tint="Red"),
             prop("OilDrum", -22.7, 2.15, 0, 80, tint="Blue"),
             prop("Crate_Wood", -28.6, -3.4, 0, 5), prop("Crate_Wood", -28.6, -3.4, 0.6, 12),
             prop("PalletStack", -29.2, 3.6, 0, 15), prop("Crate_Ammo", -23.8, -3.9, 0, 10)]

    # Between A and the village.
    west += [prop("SandbagWall_3m", -14.8, -7, 0, 0), prop("Barricade_Plywood_3m", -14.6, 7, 0, 0),
             prop("TireStack", -15.2, -1.3, 0, 0), prop("TireStack", -15.4, 1.0, 0, 50)]

    # North lane, west half.
    west += [prop("Rock_A", -49, -24, 0, 30), prop("CableSpool", -44, -32, 0, 15),
             prop("HayBale_Round", -47.5, -39.5, 0, 80), prop("TireStack", -38.5, -24.5, 0, 0),
             prop("Tire", -37.7, -25.6, 0, 20),
             prop("Container_20ft", -31, -16.2, 0, 0, tint="Sand"),
             prop("HayBale_Square", -36.5, -36, 0, 0), prop("HayBale_Square", -36.5, -36, 0.38, 6),
             prop("HayBale_Square", -36.4, -35.4, 0, 0),
             prop("Rock_B", -29, -40.5, 0, 140), prop("Bush_A", -23, -42.3, 0, 0),
             prop("WreckedCar", -24.5, -30, 0, -20),
             prop("Barricade_Plywood_3m", -17, -37, 0, 0), prop("TireStack", -15, -25, 0, 0),
             prop("Tire", -14.1, -24.1, 0, 0),
             prop("Watchtower", -7, -37.5, 0, 90),
             prop("PalletStack", -10.5, -18, 0, 0), prop("CableSpool", -4.2, -25.5, 0, 90),
             prop("SandbagWall_3m", -8.5, -30.5, 0, 90),
             prop("Tree_Oak_B", -57.5, -41.5, 0, 40), prop("Bush_A", -58.5, -33, 0, 0),
             prop("Rock_B", -32.5, -22.5, 0, 60),
             prop("SandbagWall_3m", -19.5, -21.5, 0, 30), prop("Rock_A", -42.5, -15.5, 0, 0),
             prop("Bush_A", -60.0, -25.5, 0, 0), prop("Rock_B", -56.5, -19.5, 0, 0),
             prop("Crate_Wood", -35.0, -27.5, 0, 15), prop("Crate_Wood", -35.0, -27.5, 0.6, 22),
             prop("HayBale_Round", -1.8, -33.5, 0, 90), prop("Barricade_Plywood_4m", -30.5, -33.5, 0, 90),
             prop("HayBale_Square", -36.5, -36, 0.76, 3), prop("SandbagWall_3m", -41.5, -27.0, 0, 60)]
    west += [blocker(-34.2, -17.4, -27.8, -15.0, 2.6, 7.0)]
    # South lane, west half.
    west += [prop("WreckedCar", -46, 27, 0, 25), prop("HayBale_Round", -50, 37.5, 0, 10),
             prop("Rock_A", -40, 39, 0, 60), prop("Rock_B", -38, 34.5, 0, 0), prop("TireStack", -41, 21, 0, 0),
             prop("Container_20ft", -21, 16.2, 0, 0, tint="Red"),
             prop("CableSpool", -31, 24, 0, 0),
             prop("Container_20ft", -11.5, 27, 0, 25, tint="Green"),
             prop("HayBale_Square", -27, 38.5, 0, 90), prop("HayBale_Square", -26.4, 38.5, 0, 90),
             prop("HayBale_Square", -26.7, 38.5, 0.38, 88),
             prop("Barricade_Plywood_4m", -33.5, 31, 0, 0), prop("SandbagWall_3m", -20, 33, 0, 90),
             prop("TireStack", -5.5, 40, 0, 0), prop("Tire", -6.4, 39.3, 0, 0),
             prop("PalletStack", -15, 39.5, 0, 30), prop("Bush_A", -44, 42.8, 0, 0),
             prop("Tree_Oak_C", -57, 41.5, 0, 10), prop("Rock_B", -55, 25.5, 0, 200),
             prop("SandbagWall_3m", -5.0, 20.5, 0, 0), prop("Crate_Wood", -26.5, 21.0, 0, 30),
             prop("HayBale_Round", -39.5, 15.5, 0, 0), prop("PalletStack", -36.0, 19.5, 0, 20),
             prop("TireStack", -60.0, 30.0, 0, 0), prop("Bush_A", -60.3, 19.5, 0, 0),
             prop("Rock_A", -33.0, 41.6, 0, 100), prop("Rock_A", -57.0, 33.5, 0, 40),
             prop("HayBale_Round", -30.5, 36.5, 0, 0), prop("Crate_Wood", -15, 39.5, 0.58, 40),
             prop("HayBale_Square", -26.7, 38.5, 0.76, 92), prop("Rock_A", -9.5, 36.5, 0, 210)]
    west += [blocker(-24.2, 15.0, -17.8, 17.4, 2.6, 7.0)]
    # Floodlight towers (lamps + spotlights, on at dusk).
    west += [prop("FloodlightTower", -40, -43.2, 0, 90, light=True),
             prop("FloodlightTower", -40, 43.2, 0, -90, light=True)]

    # ---- CQB village (west half authored; the east half is its rotation) ----
    vil = []
    vil += ply_building(-12, -12, 2, 2, north="OD", south="WD", west="OW", east="WO")       # NW house
    vil += ply_building(-12, 4, 2, 2, north=".D", south="DO", west="WO", east="DW")         # SW house
    vil += ply_building(-12, -4, 1, 2, north=".", south="W", west="DW", east="WD", posts=False)  # W hut, offset doors
    vil += [prop("Wall_Plywood_Window_4m", -2, -12, 0, -90)]                                  # north arm mouth breaker
    # bridge catwalk across the north arm (deck 2.4 m) with stairs down into the courtyard
    vil += [prop("Platform_Timber_4m", -2, -8, 2.17, 90), prop("Platform_Timber_4m", 2, -8, 2.17, 90)]
    for (px, py) in ((-3.75, -8.45), (-3.75, -7.55), (3.75, -8.45), (3.75, -7.55), (0.0, -8.45)):
        vil.append(prop("Post_Timber", px, py, 0, 0, scale=(1.0, 1.0, 2.17 / 3.0)))
    vil += stairs(0.6, -3.8, 0.0, 2.4, "-y", 1.2, "Timber")
    vil += [slab(-4, -8.66, 4, -8.6, 2.4, 3.4, "Timber", name="Rail"),
            slab(-4, -7.43, 0.0, -7.37, 2.4, 3.4, "Timber", name="Rail"),
            slab(1.2, -7.43, 4, -7.37, 2.4, 3.4, "Timber", name="Rail")]
    # courtyard + interiors cover
    vil += [prop("SandbagWall_3m", 0, -2.6, 0, 90), prop("CableSpool", -5, 1.6, 0, 0),
            prop("OilDrum", -2.4, 3.0, 0, 0, tint="Red"), prop("OilDrum", -1.8, 3.3, 0, 30, tint="Red"),
            prop("Crate_Wood", -6.6, -2.3, 0, 0), prop("Crate_Wood", -6.6, -2.3, 0.6, 8),
            prop("HayBale_Square", 2.6, -6.2, 0, 90), prop("HayBale_Square", 2.6, -6.2, 0.38, 92),
            prop("Crate_Wood", -9, -9, 0, 0), prop("Crate_Wood", -9, -9, 0.6, 15),
            prop("PalletStack", -6.4, -10.6, 0, 0), prop("OilDrum", -10.9, -5.4, 0, 0, tint="Blue"),
            prop("Crate_Ammo", -10.8, 0, 0, 90), prop("Crate_Ammo", -10.8, 0, 0.36, 92),
            prop("HayBale_Square", -9.5, 9.2, 0, 0), prop("HayBale_Square", -9.5, 9.2, 0.38, 0),
            prop("Crate_Wood", -6.2, 6.4, 0, 20)]

    items += west + rot180(west)
    items += vil + rot180(vil)
    items = [it for it in items if not it.get("skip")]

    # ---- objectives (centre authored once; A rotates to C) ----
    items += [objective("A", -26, 0), objective("B", 0, 0), objective("C", 26, 0)]

    # ---- perimeter: netting, trees outside, invisible walls ----
    items += fence_line("x", -H, -W, W) + fence_line("x", H, -W, W)
    items += fence_line("y", -W, -H, H) + fence_line("y", W, -H, H)
    items += [blocker(-W - 1.0, -H - 1, -W - 0.3, H + 1, 0, 12), blocker(W + 0.3, -H - 1, W + 1.0, H + 1, 0, 12),
              blocker(-W - 1, -H - 1.0, W + 1, -H - 0.3, 0, 12), blocker(-W - 1, H + 0.3, W + 1, H + 1.0, 0, 12)]
    outer = (-W - 2.5, -H - 2.5, W + 2.5, H + 2.5)
    items += scatter(11, 44, (-92, -72, 92, 72), [], 7.0, ["Tree_Oak_A", "Tree_Oak_B", "Tree_Oak_C"],
                     keep_out=[outer])
    items += scatter(12, 26, (-80, -60, 80, 60), [], 4.0, ["Bush_A", "Bush_A", "Rock_A", "Rock_B"],
                     keep_out=[outer])

    items += [sound("AmbienceField", 0, 0, 3)]
    items += [capture(0, 0, 3, 30.0)]
    return {
        "name": "IronwoodYard", "path": "/Game/Maps/L_IronwoodYard", "kind": "match",
        "bounds": (-W, -H, W, H), "lighting": "ironwood_golden", "game_mode": "AirsoftGameMode",
        "kill_z": -10.0, "items": items,
    }


# =============================================================================================
# L_VelvetClub - night, rain-soaked city block with a two-level club.
# Street (north, Blue) -> club -> back alley / loading dock (south-east, Red).
# =============================================================================================
def _velvet():
    it = []
    X0, X1, Y0, Y1 = -36.0, 36.0, -40.0, 32.0
    # ---- ground ----
    it += [slab(-60, -26, 60, -14, -0.45, -0.15, "AsphaltWet", name="Road", tile=3.0),
           slab(-60, -30, 60, -26, -0.3, 0.0, "ConcreteFloor", name="Sidewalk_N", tint="Grey"),
           slab(-60, -14, 60, -10, -0.3, 0.0, "ConcreteFloor", name="Sidewalk_S", tint="Grey"),
           slab(-60, -45, -36.2, -30, -0.3, 0.0, "ConcreteFloor", name="Beyond_N"),
           slab(-21.8, -45, 60, -30, -0.3, 0.0, "ConcreteFloor", name="Beyond_N"),
           slab(-36.2, -40.2, -21.8, -30.0, -0.3, 0.0, "Asphalt", name="ValetLot"),
           slab(-37, -10, -26, 22, -0.3, 0.0, "Asphalt", name="Alley_W"),
           slab(26, -10, 37, 22, -0.3, 0.0, "Asphalt", name="Alley_E"),
           slab(-37, 22, 37, 33, -0.3, 0.0, "Asphalt", name="Alley_Back"),
           slab(-26, -10, 26, 22, -0.3, 0.0, "MarbleBlack", name="ClubFloor")]
    # puddles (mirror-like, no collision)
    for (x, y, sx, sy) in ((-12, -21, 3.5, 2.2), (3, -18.2, 2.4, 1.6), (17, -22.5, 4.0, 2.0), (-31, 1, 2.5, 3.5),
                           (31, 12, 2.0, 3.0), (-15, 27, 3.0, 2.0), (6, 28.5, 2.6, 1.8), (-29, -21, 2.0, 1.4),
                           (27, -19, 2.2, 1.5)):
        z = -0.14 if -26 < y < -14 else 0.006
        it.append(box(x, y, z - 0.004, sx, sy, 0.008, "Puddle", coll=False, cast=False, name="Puddle"))

    # ---- club shell (BrickDark exterior, 8 m, roof at 7.2) ----
    T = 0.4
    it += wall_run("x", -10, -26.2, 26.2, 0, 8, T, "BrickDark", openings=[(-2, 2, 3.2)], name="Facade")
    it += wall_run("x", 22, -26.2, 26.2, 0, 8, T, "BrickDark", openings=[(-12, -10, 2.4), (22, 24, 2.4)],
                   name="BackWall")
    it += wall_run("y", -26, -10, 22, 0, 8, T, "BrickDark", openings=[(-8, -6, 2.4), (12, 14, 2.4)], name="WestWall")
    it += wall_run("y", 26, -10, 22, 0, 8, T, "BrickDark", openings=[(4, 6, 2.4), (17, 19, 2.4)], name="EastWall")
    it += [slab(-26.4, -10.4, 26.4, 22.4, 7.0, 7.4, "PaintedSteel", tint="Black", name="Ceiling")]
    it += [blocker(-27, -11, 27, 23, 8.0, 12.0)]
    # foyer (velvet walls, 4 m ceiling) with offset inner openings
    it += wall_run("x", -6, -10, 10, 0, 4, 0.3, "Velvet", openings=[(-8, -5, 3.0), (5, 8, 3.0)], name="FoyerWall")
    it += [slab(-10.15, -10, -9.85, -6, 0, 4, "Velvet"), slab(9.85, -10, 10.15, -6, 0, 4, "Velvet"),
           slab(-10, -10, 10, -6, 4.0, 4.2, "PaintedSteel", tint="Black", name="FoyerCeiling"),
           slab(-10, -10, 10, -6, 0.0, 0.01, "Carpet", coll=False, tint="Burgundy", name="FoyerCarpet")]
    it += [prop("Planter_Concrete", -9.2, -6.8, 0, 0), prop("Planter_Concrete", 9.2, -6.8, 0, 0),
           prop("BarCounter_4m", -7.6, -8.6, 0, 0, name="CoatCheck"),
           prop("WallSconce", -9.83, -8.0, 2.0, 0), prop("WallSconce", 9.83, -8.0, 2.0, 180),
           hanging("Chandelier", 0, -8, 4.0, light={"shadows": False, "cd": 4.0, "radius": 7.0})]
    # facade dressing: canopy, LED, neon sign, velvet rope queue
    it += [slab(-3.6, -12.6, 3.6, -10.2, 3.35, 3.6, "Velvet", tint="Black", name="Canopy"),
           slab(-3.6, -12.62, 3.6, -12.56, 3.3, 3.36, "Emissive:Magenta", glow=40, coll=False, name="CanopyLED"),
           prop("NeonSign_Velvet", 0, -10.3, 4.2, -90, scale=(2.4, 2.4, 2.4), light=True)]
    for x in (-2.6, -4.0, -5.4, -6.8):
        it.append(prop("VelvetRopePost", x, -11.4, 0, 90))
    it.append(prop("VelvetRopePost", -8.2, -11.4, 0, 90, pieces=["Body"]))

    # ---- main hall: island bar (B) ----
    for x in (-4, 0, 4):
        it += [prop("BarCounter_4m", x, 1.0, 0, -90), prop("BackBar_4m", x, 3.0, 0, -90, light=True)]
    it += [slab(-6.4, 3.32, 6.4, 3.62, 0, 3.0, "MarbleBlack", name="BarBack"),
           slab(-6.0, 0.57, 6.0, 0.6, 0.08, 0.12, "Emissive:Magenta", glow=30, coll=False, name="BarUnderglow")]
    for x in (-5.4, -3.6, -1.8, 0.0, 1.8, 3.6, 5.4):
        it.append(prop("BarStool", x, 0.15, 0, 90))
    for x in (-4, 0, 4):
        it.append(hanging("Chandelier", x, 2.0, 7.0, light=True))

    # ---- dance floor + DJ stage (C side) ----
    it += [slab(-10, 6, 10, 14, 0.0, 0.01, "MarbleBlack", coll=False, name="DanceFloorBase")]
    cols = ["Magenta", "Cyan", "Violet", "Amber"]
    for i in range(10):
        for j in range(4):
            if (i + j) % 3 == 0:
                c = cols[(i * 3 + j) % 4]
                it.append(box(-9 + 2 * i, 7 + 2 * j, 0.015, 1.9, 1.9, 0.01, "Emissive:" + c, glow=3.0, coll=False,
                              cast=False, name="DanceTile"))
    it += [slab(-6, 16, 6, 21.8, 0, 0.8, "MarbleBlack", name="Stage")]
    it += stairs(0, 14.8, 0, 0.8, "+y", 3.0, "MarbleBlack")
    it += [prop("DJBooth", 0, 18.0, 0.8, -90), prop("SpeakerStack", -5, 17.2, 0.8, -90),
           prop("SpeakerStack", 5, 17.2, 0.8, -90)]
    for k, x in enumerate((-4.5, -1.5, 1.5, 4.5)):
        it.append(prop("MovingHeadLight", x, 16.35, 0.8, -90, light={"color": ["Magenta", "Cyan", "Cyan", "Magenta"][k],
                                                                    "yaw_off": (-25, -8, 8, 25)[k]}))
    it += [slab(-7.0, 15.25, 7.0, 15.55, 5.9, 6.2, "PaintedSteel", tint="Black", name="Truss"),
           slab(-7.0, 15.25, -6.7, 15.55, 0, 5.9, "PaintedSteel", tint="Black", name="TrussLeg"),
           slab(6.7, 15.25, 7.0, 15.55, 0, 5.9, "PaintedSteel", tint="Black", name="TrussLeg")]
    it += [light("spot", -2.5, 15.4, 5.8, yaw=90, pitch=-62, color="Warm", cd=26, radius=14, cone=(14, 28),
                 shadows=True, vol=2.0),
           light("spot", 2.5, 15.4, 5.8, yaw=90, pitch=-62, color="Magenta", cd=22, radius=14, cone=(14, 28),
                 shadows=False, vol=3.0)]
    it += [slab(-25.8, 21.55, 25.8, 21.6, 0.3, 0.36, "Emissive:Violet", glow=20, coll=False, name="BackLED")]
    it += [slab(-4.3, 9.2, -3.7, 9.8, 0, 7.0, "MarbleBlack", name="Pillar"),
           slab(3.7, 9.2, 4.3, 9.8, 0, 7.0, "MarbleBlack", name="Pillar"),
           slab(-7.6, 11.9, -6.4, 13.1, 0, 1.0, "MarbleBlack", name="Podium"),
           slab(6.4, 7.4, 7.6, 8.6, 0, 1.0, "MarbleBlack", name="Podium"),
           slab(-7.6, 11.88, -6.4, 11.9, 0.9, 0.96, "Emissive:Cyan", glow=25, coll=False, name="PodiumLED"),
           slab(6.4, 7.38, 7.6, 7.4, 0.9, 0.96, "Emissive:Magenta", glow=25, coll=False, name="PodiumLED")]

    # ---- west VIP: booths under a mezzanine (deck 3.4 m) ----
    it += [slab(-25.8, -6, -18.5, 20, 3.1, 3.4, "Carpet", tint="Burgundy", name="Mezzanine")]
    for y in (-5.6, 0.0, 6.0, 12.0, 19.6):
        it.append(slab(-18.85, y - 0.15, -18.55, y + 0.15, 0, 3.1, "Brass", name="MezzPost"))
    it += [slab(-18.6, -6.0, -18.5, -5.6, 3.4, 4.4, "Brass", name="Rail"),
           slab(-18.6, -4.0, -18.5, 17.4, 3.4, 4.4, "Brass", name="Rail"),
           slab(-18.6, 19.0, -18.5, 20.0, 3.4, 4.4, "Brass", name="Rail"),
           slab(-25.8, -6.05, -18.5, -5.95, 3.4, 4.4, "Brass", name="Rail")]
    it += stairs(-13.4, -4.8, 0, 3.4, "-x", 1.5, "MarbleBlack")
    it += stairs(-13.4, 18.2, 0, 3.4, "-x", 1.5, "MarbleBlack")
    for y in (-3.0, 3.0, 9.0, 15.0):
        it += [prop("BoothSofa_Curved", -24.4, y, 0, 0), prop("BoothTable", -23.4, y, 0, 0)]
    for y in (0.0, 6.0, 12.0, 18.0):
        it.append(prop("WallSconce", -25.68, y, 2.0, 0, light=True))
    for y in (-2.0, 8.0, 16.0):
        it.append(prop("WallSconce", -25.68, y, 5.4, 0, light=True))
    it += [prop("Armchair_Leather", -23.2, 1.0, 3.4, 0), prop("Armchair_Leather", -21.0, 1.0, 3.4, 180),
           prop("BoothTable", -22.1, 1.0, 3.4, 0), prop("Armchair_Leather", -23.2, 8.0, 3.4, 0),
           prop("Armchair_Leather", -21.0, 8.0, 3.4, 180), prop("BoothTable", -22.1, 8.0, 3.4, 0),
           prop("HighTable", -19.6, 13.0, 3.4, 0), prop("HighTable", -19.6, 4.5, 3.4, 0),
           hanging("Chandelier", -22.2, 5.0, 7.0, light={"shadows": False})]
    it += [blocker(-26, -6.2, -18.4, 20.2, 4.4, 7.0)]

    # ---- east VIP lounge + high tables ----
    it += [prop("BoothSofa_Curved", 24.4, 2.0, 0, 180), prop("BoothTable", 23.4, 2.0, 0, 0),
           prop("BoothSofa_Curved", 24.4, 10.0, 0, 180), prop("BoothTable", 23.4, 10.0, 0, 0),
           prop("Armchair_Leather", 17.5, 11.5, 0, 200), prop("Armchair_Leather", 19.5, 12.5, 0, 230),
           prop("BoothTable", 18.6, 10.6, 0, 0),
           prop("HighTable", 14, -3, 0, 0), prop("HighTable", 18, -3, 0, 0), prop("HighTable", 14, 3.5, 0, 0),
           prop("HighTable", 10.5, -1.5, 0, 0), prop("HighTable", -10.5, -1.5, 0, 0), prop("HighTable", -14, 3.5, 0, 0),
           prop("Planter_Concrete", 12.5, 8.0, 0, 0), prop("Planter_Concrete", -12.5, 8.0, 0, 0),
           prop("Planter_Concrete", 25.2, -9.2, 0, 0), prop("Planter_Concrete", -17.6, -9.2, 0, 0)]
    for x in (12.5, 14.0, 15.5):
        it.append(prop("VelvetRopePost", x, 6.8, 0, -90))
    for y in (-2.0, 6.0, 13.0):
        it.append(prop("WallSconce", 25.68, y, 2.0, 180, light=True))
    it += [hanging("Chandelier", 19.0, 5.0, 7.0, light={"shadows": False})]
    # dividers so the hall is not one open box (break long sightlines)
    it += [slab(-12.3, 9.0, -11.7, 13.5, 0, 2.6, "Velvet", name="Divider"),
           slab(11.7, -4.5, 12.3, 0.0, 0, 2.6, "Velvet", name="Divider"),
           slab(-16.0, -1.0, -15.4, 3.0, 0, 1.2, "Walnut", name="HalfWall"),
           slab(15.4, 9.0, 16.0, 13.0, 0, 1.2, "Walnut", name="HalfWall")]

    # ---- kitchen / back of house ----
    it += wall_run("y", 14, 15, 22, 0, 4, 0.3, "PlywoodPainted", openings=[(16.0, 17.6, 2.4)], tint="Grey")
    it += wall_run("x", 15, 14, 26, 0, 4, 0.3, "PlywoodPainted", openings=[(20.0, 21.6, 2.4)], tint="Grey")
    it += [slab(14, 15, 26, 22, 4.0, 4.2, "PaintedSteel", tint="Grey", name="KitchenCeiling"),
           slab(14, 15, 26, 22, 0.0, 0.01, "DiamondPlate", coll=False, name="KitchenFloor"),
           slab(17, 18.0, 23, 19.2, 0, 0.92, "DiamondPlate", name="KitchenIsland"),
           slab(25.2, 15.6, 25.8, 21.0, 0, 0.92, "DiamondPlate", name="KitchenCounter"),
           prop("Crate_Wood", 15.0, 21.2, 0, 0), prop("Crate_Wood", 15.0, 21.2, 0.6, 10),
           prop("OilDrum", 16.3, 21.3, 0, 0, tint="Green"),
           light("point", 18.0, 17.0, 3.8, color="Cool", cd=5, radius=8, shadows=True),
           light("point", 23.0, 20.0, 3.8, color="Cool", cd=4, radius=7, shadows=False)]

    # ---- street (Blue side) ----
    it += [prop("BoxTruck", -21, -20.3, -0.15, 90, tint="White"),
           prop("Car_Sedan", 1.5, -20.2, -0.15, 8, tint="Black"),
           prop("Car_Coupe", 30.5, -20.0, -0.15, 75, tint="White"),
           prop("Kiosk", -24.2, -12.0, 0, 0),
           prop("Car_Sedan", -27.5, -24.6, -0.15, 0, tint="Black"),
           prop("Car_Coupe", -10.5, -24.6, -0.15, 180, tint="DeepRed"),
           prop("Car_Sedan", 7.5, -24.6, -0.15, 0, tint="Gunmetal"),
           prop("Car_Coupe", 25, -24.6, -0.15, 180, tint="Black"),
           prop("Car_Sedan", -14.5, -15.4, -0.15, 180, tint="Gunmetal"),
           prop("Car_Coupe", 15.5, -15.4, -0.15, 0, tint="DeepRed"),
           prop("Kiosk", 12, -28.1, 0, 90),
           prop("Dumpster", -3.0, -28.6, 0, 90, tint="Green"), prop("TrashBags", -5.3, -28.4, 0, 30),
           prop("Planter_Concrete", -6.6, -10.9, 0, 0), prop("Planter_Concrete", 6.6, -10.9, 0, 0),
           prop("Planter_Concrete", 20, -10.9, 0, 0), prop("Planter_Concrete", -20, -10.9, 0, 0),
           prop("Dumpster", 28.5, -12.2, 0, 0, tint="Blue")]
    for x in (-1.6, 1.6):
        it.append(prop("Bollard", x, -13.5, 0, 0))
    for (x, y) in ((-18, -13.6), (-6, -13.6), (6, -13.6), (18, -13.6), (-24, -29.4), (-8, -29.4), (8, -29.4),
                   (24, -29.4)):
        it.append(prop("StreetLamp", x, y, 0, 90 if y > -20 else -90,
                       light={"shadows": abs(x) < 10}))
    # street ends: bollards + invisible walls
    for x in (X0 + 0.6, X1 - 0.6):
        for k in range(13):
            it.append(prop("Bollard", x, -29.0 + 1.5 * k, -0.15 if -26 < -29.0 + 1.5 * k < -14 else 0.0, 0))
    # north buildings (backdrop) with lit shopfronts
    it += [slab(-60, -36, -38, -30.2, 0, 12, "Brick", name="ShopsN"),
           slab(-21.8, -36, 60, -30.2, 0, 12, "Brick", name="ShopsN")]
    # Blue spawn: valet lot behind the north building line, gate with piers and a parked car as baffle
    it += [slab(-38, -42, -20, -40.2, 0, 10, "Brick", name="LotBack"),
           slab(-38, -41, -36.2, -30.0, 0, 10, "Brick", name="LotWest"),
           slab(-22.2, -40.2, -21.8, -30.2, 0, 10, "Brick", name="LotEast")]
    it += wall_run("x", -30.4, -36.2, -21.8, 0, 6, 0.4, "Brick", openings=[(-29.2, -25.6, 4.0)], name="LotFront")
    it += [slab(-29.6, -30.2, -29.2, -29.0, 0, 2.6, "Brick", name="GatePier"),
           slab(-25.6, -30.2, -25.2, -29.0, 0, 2.6, "Brick", name="GatePier"),
           slab(-32.4, -27.4, -22.2, -27.0, 0, 2.4, "Brick", name="ValetScreen"),
           prop("Planter_Concrete", -33.1, -27.2, 0, 0), prop("Planter_Concrete", -21.5, -27.2, 0, 0),
           prop("Car_Coupe", -33.4, -38.6, 0, 0, tint="Gunmetal"), prop("Car_Sedan", -24.8, -38.6, 0, 180,
                                                                         tint="Black"),
           slab(-36.0, -30.8, -35.6, -30.6, 0.6, 3.0, "Emissive:Warm", glow=6, coll=False, name="LotLamp"),
           light("point", -29, -35, 4.5, color="Sodium", cd=10, radius=12, shadows=True),
           blocker(-36.2, -40.2, -21.8, -30.2, 10.0, 14.0)]
    for k, x in enumerate((-17, -6, 5, 16, 27, -44)):
        c = ["Warm", "Cool", "Amber", "Warm", "Cyan", "Warm"][k]
        it += [slab(x - 2.4, -30.24, x + 2.4, -30.2, 0.5, 2.9, "Emissive:" + c, glow=2.5, coll=False, name="Shopfront"),
               slab(x - 2.8, -30.9, x + 2.8, -30.2, 3.0, 3.25, "Canvas", tint=["Burgundy", "DeepGreen", "Teal"][k % 3],
                    name="Awning")]
    it += [slab(-60, -14, -37, -10, 0, 9, "BrickDark", name="BlockW"), slab(37, -14, 60, -10, 0, 9, "BrickDark",
                                                                              name="BlockE")]
    it += [slab(-38, -10, -36.2, 33, 0, 10, "Brick", name="BoundaryW"),
           slab(36.2, -10, 38, 33, 0, 10, "Brick", name="BoundaryE"),
           slab(-38, 32.2, 38, 34, 0, 6, "BrickDark", name="BoundaryS")]
    it += [blocker(X0 - 1.0, -30.5, X0 - 0.2, -10, 0, 12), blocker(X1 + 0.2, -30.5, X1 + 1.0, -10, 0, 12),
           blocker(X0, Y0 - 1.0, X1, Y0 - 0.2, 0, 12)]

    # ---- west alley ----
    it += [prop("Dumpster", -31.5, 4.0, 0, 90, tint="Rust"), prop("TrashBags", -33.6, 6.2, 0, 0),
           prop("TrashBags", -29.6, 6.0, 0, 120), prop("Crate_Wood", -27.4, 12.0, 0, 5),
           prop("Crate_Wood", -27.4, 12.0, 0.6, 12), prop("Car_Coupe", -32.4, 16.5, 0, 95, tint="Gunmetal"),
           prop("PalletStack", -34.6, -4.5, 0, 90), prop("OilDrum", -27.3, -3.0, 0, 0, tint="Red"),
           prop("Dumpster", -34.6, 24.6, 0, 90, tint="Blue"), prop("StreetLamp", -26.7, 2.0, 0, 0,
                                                                   light={"shadows": False, "cd": 12})]
    # ---- east alley ----
    it += [prop("Dumpster", 31.5, -2.0, 0, 90, tint="Green"), prop("TrashBags", 33.6, 0.3, 0, 40),
           prop("Car_Sedan", 32.3, 9.5, 0, 92, tint="DeepRed"), prop("PalletStack", 27.5, 14.5, 0, 0),
           prop("Crate_Wood", 34.4, 15.5, 0, 30), prop("OilDrum", 27.4, 1.5, 0, 0, tint="Blue"),
           prop("StreetLamp", 26.7, 12.0, 0, 180, light={"shadows": False, "cd": 12})]
    # ---- back alley + loading dock (Red side) ----
    it += [slab(8, 22.2, 20.5, 24.6, 0, 1.2, "ConcreteFloor", name="Dock")]
    it += stairs(8, 23.4, 0, 1.2, "-x", 1.4, "ConcreteFloor")
    # Red spawn: walled loading yard, west gate hugging the boundary (truck baffle), north door (dumpster baffle)
    it += wall_run("x", 24.4, 27.3, 36.2, 0, 3.5, 0.4, "BrickDark", openings=[(33.0, 35.6, 2.8)], name="YardN")
    it += wall_run("y", 27.5, 24.4, 32.2, 0, 3.5, 0.4, "BrickDark", openings=[(30.0, 32.2, 2.8)], name="YardW")
    it += [blocker(27.3, 24.2, 36.2, 32.2, 3.5, 8.0),
           prop("BoxTruck", 21.4, 30.7, 0, 0, tint="Grey"),
           slab(31.6, 20.6, 36.2, 21.0, 0, 2.6, "BrickDark", name="YardScreen"),
           prop("Dumpster", 34.3, 19.4, 0, 0, tint="Green"),
           prop("Dumpster", 24.4, 26.4, 0, 0, tint="Green"),
           prop("PalletStack", 25.4, 23.2, 0, 0), prop("Crate_Wood", 25.4, 23.2, 0.58, 5),
           prop("PalletStack", 35.2, 31.4, 0, 0), prop("Crate_Ammo", 33.8, 31.6, 0, 0),
           light("point", 31.5, 28, 3.6, color="Sodium", cd=8, radius=10, shadows=False),
           prop("Dumpster", -19.5, 30.7, 0, 0, tint="Blue"), prop("Dumpster", -5.5, 30.8, 0, 0, tint="Rust"),
           prop("TrashBags", -17.2, 31.0, 0, 0), prop("TrashBags", -3.4, 30.9, 0, 90),
           prop("PalletStack", -27.0, 24.0, 0, 10), prop("Crate_Wood", -11.0, 25.6, 0, 20),
           prop("Dumpster", -28.8, 30.8, 0, 0, tint="Green"), prop("PalletStack", -22.5, 27.6, 0, 70),
           prop("OilDrum", -6.5, 25.8, 0, 0, tint="Blue"), prop("OilDrum", -5.9, 26.3, 0, 0, tint="Blue"),
           prop("Crate_Wood", -11.0, 25.6, 0.6, 30), prop("OilDrum", 2.5, 24.0, 0, 0, tint="Red"),
           prop("OilDrum", 3.2, 24.4, 0, 30, tint="Red"), prop("PalletStack", 10.5, 30.5, 0, 0),
           prop("Crate_Ammo", 14.5, 23.0, 1.2, 0),
           prop("StreetLamp", -12.0, 32.0 - 0.6, 0, 180, light={"shadows": False, "cd": 14}),
           prop("StreetLamp", 6.0, 31.4, 0, 180, light={"shadows": False, "cd": 12}),
           light("spot", 23.0, 21.6, 3.2, yaw=90, pitch=-55, color="Sodium", cd=14, radius=12, cone=(25, 45),
                 shadows=True),
           slab(21.6, 21.75, 24.4, 21.8, 2.6, 2.7, "Emissive:Sodium", glow=30, coll=False, name="DoorLamp")]

    # ---- spawns ----
    for x in (-34.6, -31.9, -29.2, -26.5, -23.8):
        for y in (-36.4, -33.6):
            it.append(start(x, y, "Blue", 90.0))
    it += [start(-34.6, -31.3, "Blue", 0.0), start(-29.05, -39.0, "Blue", 90.0)]
    for x in (29.2, 31.4, 33.4, 35.4):
        for y in (25.6, 27.6, 29.6):
            it.append(start(x, y, "Red", 200.0))

    # ---- objectives ----
    # capture is distance-only (no sight test), so circles never reach through walls
    it += [objective("A", -4.0, -15.2, 0.0, radius=4.5), objective("B", 0.0, -1.4, 0.0, radius=4.5),
           objective("C", 8.0, 11.5, 0.0, radius=5.0)]

    # ---- atmosphere, sound ----
    it += [fogvol(0, 6, 3.5, 26, 16, 3.6, density=0.5, color=(0.8, 0.35, 0.55))]
    it += [capture(0, 4, 3, 20), capture(-22, 6, 2, 10), capture(0, -20, 3, 25), capture(20, 18, 2, 8)]
    it += [sound("AmbienceClubStreet", -18, -20, 3, spatial=True, radius=18, falloff=25, volume=0.9),
           sound("AmbienceClubStreet", 18, -20, 3, spatial=True, radius=18, falloff=25, volume=0.9),
           sound("AmbienceClubStreet", 0, 27, 3, spatial=True, radius=14, falloff=20, volume=0.6),
           sound("AmbienceClubInterior", 0, 6, 3, spatial=True, radius=18, falloff=10, volume=0.8),
           sound("ClubMusic", -5, 17.6, 2.4, spatial=True, radius=6, falloff=34, volume=1.0),
           sound("ClubMusic", 5, 17.6, 2.4, spatial=True, radius=6, falloff=34, volume=1.0)]
    return {
        "name": "VelvetClub", "path": "/Game/Maps/L_VelvetClub", "kind": "match",
        "bounds": (X0, Y0, X1, Y1), "lighting": "velvet_night", "game_mode": "AirsoftGameMode",
        "kill_z": -10.0, "items": it,
    }


# =============================================================================================
# L_Staging - lobby: spawn hall, The Armory, outdoor range and a kill house. Golden hour.
# =============================================================================================
FIRING_LINE_X = 6.0
RANGE_LANES = (-9.0, -3.0, 3.0, 9.0)
RANGE_DISTANCES = (10, 25, 40, 60)
ARMORY_SOUTH = ["M4", "AK74", "SR25", "VSR", "M870", "MP5", "VECTOR", "MP7"]
ARMORY_WEST = ["P90", "M249", "G18"]
ARMORY_EAST = ["G17", "M1911", "DEAGLE"]


def _staging():
    it = []
    X0, Y0, X1, Y1 = -28.0, -20.0, 82.0, 42.0
    it += [slab(-80, -70, 130, 90, -0.3, 0.0, "Grass", name="Ground", tile=3.0),
           patch(1.5, -15.5, 11, 15.5, 0.012, "Gravel", name="FiringPad"),
           patch(11, -15.5, 78, 15.5, 0.010, "Dirt", name="RangeFloor"),
           patch(-27, 15, 7, 41, 0.010, "Gravel", name="Yard"),
           patch(6, 18, 30, 38, 0.014, "Dirt", name="KillHousePad")]

    # ---- compound building ----
    it += [slab(-24.2, -14.2, 0.2, 14.2, -0.3, 0.0, "ConcreteFloor", name="BuildingFloor"),
           slab(-23.8, -0.85, -0.2, 13.8, 0.0, 0.01, "Walnut", coll=False, name="ArmoryFloor")]
    it += wall_run("x", -14, -24.4, 0.4, 0, 4.8, 0.4, "Concrete", name="NorthWall")
    it += wall_run("x", 14, -24.4, 0.4, 0, 4.8, 0.4, "Concrete", name="SouthWall")
    it += wall_run("y", -24, -14, 14, 0, 4.8, 0.4, "Concrete", name="WestWall")
    it += wall_run("y", 0, -14, 14, 0, 4.8, 0.4, "Concrete", openings=[(-10, -6, 3.0), (10.6, 13.4, 3.0)],
                   name="EastWall")
    it += wall_run("x", -1, -23.8, -0.2, 0, 4.8, 0.3, "PlywoodPainted", openings=[(-14, -10, 3.0)], tint="DeepGreen",
                   name="ArmoryNorthWall")
    it += [slab(-24.6, -14.6, 0.6, 14.6, 4.8, 5.1, "CorrodedMetal", name="Roof"),
           blocker(-24.6, -14.6, 0.6, 14.6, 5.1, 9.0)]
    # upper walls inside the armory painted deep green above the walnut
    it += [slab(-23.8, 13.75, -0.2, 13.8, 3.0, 4.8, "PlywoodPainted", tint="DeepGreen", coll=False),
           slab(-23.8, -0.85, -23.75, 13.8, 3.0, 4.8, "PlywoodPainted", tint="DeepGreen", coll=False),
           slab(-0.25, -0.85, -0.2, 13.8, 3.0, 4.8, "PlywoodPainted", tint="DeepGreen", coll=False)]

    # ---- spawn / briefing hall ----
    it += [slab(-17.6, -13.8, -6.4, -13.7, 2.2, 3.8, "Walnut", name="SignBoard"),
           text(-12.0, -13.66, 3.0, 90, "ANDREW'S AIRSOFT", size=95, color="Gold", glow=14),
           text(-12.0, -13.66, 2.42, 90, "TACTICAL  -  TRAINING  -  ARMORY", size=22, color="Warm", glow=6),
           slab(-17.6, -13.68, -6.4, -13.62, 2.12, 2.18, "Emissive:Gold", glow=40, coll=False, name="SignLED"),
           slab(-17.6, -13.68, -6.4, -13.62, 3.82, 3.88, "Emissive:Gold", glow=40, coll=False, name="SignLED"),
           light("rect", -12.0, -11.4, 4.5, yaw=-90, pitch=-40, color="Warm", cd=10, radius=10, w=8.0, h=0.4,
                 shadows=False)]
    for y in (-13.0, -10.5, -8.0, -5.5, -3.0):
        it.append(slab(-23.8, y - 1.15, -23.2, y + 1.15, 0, 2.0, "PaintedSteel", tint="Grey", name="Locker"))
    it += [slab(-22.6, -13.4, -22.1, -2.0, 0, 0.45, "Timber", name="Bench"),
           slab(-0.26, -4.6, -0.2, -1.6, 1.0, 2.4, "PlywoodPainted", tint="White", coll=False, name="Whiteboard"),
           prop("Crate_Ammo", -1.2, -13.2, 0, 0), prop("Crate_Ammo", -1.2, -13.2, 0.36, 4),
           prop("GunCase_Hard", -1.2, -13.2, 0.72, 10)]
    for x in (-19.5, -16.5, -13.5, -10.5, -7.5, -4.5):
        for y in (-9.5, -6.5, -3.5):
            it.append(start(x, y, "None", -90.0))
    for (x, y) in ((-18, -9.5), (-12, -9.5), (-6, -9.5), (-18, -4.5), (-12, -4.5), (-6, -4.5)):
        it.append(box(x, y, 4.76, 2.0, 0.6, 0.04, "Emissive:Cool", glow=10, coll=False, cast=False, name="LEDPanel"))
    it += [light("point", -15, -7, 4.2, color="Cool", cd=6, radius=12, shadows=True),
           light("point", -7, -7, 4.2, color="Cool", cd=6, radius=12, shadows=False),
           capture(-12, -7, 2.5, 14)]

    # ---- The Armory ----
    xs = [-21.0 + 2.4 * i for i in range(8)]
    for w, x in zip(ARMORY_SOUTH, xs):
        it.append(bay_with_display(w, x, 13.55, -90))
    for w, y in zip(ARMORY_WEST, (2.6, 5.6, 8.6)):
        it.append(bay_with_display(w, -23.55, y, 0))
    for w, y in zip(ARMORY_EAST, (2.0, 5.0, 8.0)):
        it.append(bay_with_display(w, -0.45, y, 180))
    for x in (-22, -18, -14, -10, -6, -2):
        it.append(prop("WallPanel_Walnut_4m", x, 13.77, 0, -90))
    for y in (1, 5, 9):
        it.append(prop("WallPanel_Walnut_4m", -23.77, y, 0, 0))
    it.append(prop("WallPanel_Walnut_4m", -23.77, 12.5, 0, 0, scale=(1.0, 0.75, 1.0)))
    for y in (1, 5):
        it.append(prop("WallPanel_Walnut_4m", -0.23, y, 0, 180))
    it.append(prop("WallPanel_Walnut_4m", -0.23, 8.75, 0, 180, scale=(1.0, 0.875, 1.0)))
    for x in (-22, -18, -8, -4):
        it.append(prop("WallPanel_Walnut_4m", x, -0.82, 0, 90))
    for x in (-15, -1):
        it.append(prop("WallPanel_Walnut_4m", x, -0.82, 0, 90, scale=(1.0, 0.5, 1.0)))
    it += [prop("RugPersian", -12.0, 5.6, 0.01, 0), prop("ArmoryCounter", -12.0, 9.0, 0, -90),
           prop("GunCase_Hard", -12.4, 9.0, 1.045, 85), prop("BankersLamp", -11.0, 9.1, 1.045, -60, light=True),
           prop("Mannequin_Torso", -21.8, 0.6, 0, 45), prop("Mannequin_Torso", -2.3, 0.7, 0, 135),
           prop("AmmoCrate_Wood", -22.2, 12.6, 0, 0), prop("AmmoCrate_Wood", -22.2, 12.6, 0.32, 4),
           prop("AmmoCrate_Wood", -21.1, 12.8, 0, 12), prop("ArmorySign", -12.0, -0.68, 3.2, 90)]
    for x in (-18, -12, -6):
        for y in (3.0, 10.0):
            it.append(hanging("CeilingLight_Brass", x, y, 4.8, light={"shadows": (x == -12)}))
    it += [capture(-12, 6.5, 2.0, 14)]

    # ---- range ----
    for y in (-12, -8, -4, 0, 4, 8, 12):
        it.append(prop("Roof_Corrugated_4m", 4.0, y, 2.8, 0))
    it += [blocker(2, -14, 6, 14, 2.95, 7)]
    for y in range(-14, 15, 4):
        it += [prop("Post_Timber", 2.2, y, 0, 0, scale=(1.0, 1.0, 2.8 / 3.0)),
               prop("Post_Timber", 5.8, y, 0, 0, scale=(1.0, 1.0, 2.8 / 3.0))]
    it += [prop("ChronoTable", 3.6, 14.6, 0, 90), prop("ChronoTable", 3.6, -14.6, 0, 90)]
    for y in RANGE_LANES:
        it.append(slab(4.6, y - 0.8, 5.3, y + 0.8, 0, 0.85, "Timber", name="ShootingBench"))
    for y in (-12.5, -6.0, 0.0, 6.0, 12.5):
        it.append(prop("Barricade_Plywood_3m", 8.6, y, 0, 0))
    stagger = (-1.5, -0.5, 0.5, 1.5)
    for y in RANGE_LANES:
        for k, d in enumerate(RANGE_DISTANCES):
            it.append({"t": "target", "p": (FIRING_LINE_X + d, y + stagger[k], 0.0), "yaw": 180.0,
                       "caption": "%d m" % d, "plate": 40.0 if d < 40 else 50.0})
    it += [slab(68, -17, 78, 17, 0, 1.5, "Dirt", name="Berm"), slab(70, -17, 78, 17, 1.5, 3.0, "Dirt", name="Berm"),
           slab(72, -17, 78, 17, 3.0, 4.5, "Dirt", name="Berm")]
    for y in (-14, -10, -6, -2, 2, 6, 10, 14):
        it.append(prop("HayBale_Square", 67.4, y, 0, 90))
    it += fence_line("x", -16.5, 6, 78) + fence_line("x", 16.5, 6, 78)
    it += [prop("FloodlightTower", 7.0, -18.0, 0, 30, light=False), prop("FloodlightTower", 7.0, 18.0, 0, -30,
                                                                         light=False)]
    it += [text(FIRING_LINE_X + 0.3, -15.7, 0.9, 0, "FIRING LINE", size=40, color="Amber", glow=4)]

    # ---- kill house (open top) ----
    it += ply_building(8, 20, 5, 4, north="WDWOW", south="OWDWO", west="WDWO", east="OWDW", roof=False)
    it += interior_wall("y", 16, 20, "DW")
    it += interior_wall("y", 16, 28, "WD")
    it += interior_wall("x", 28, 8, "WD")
    it += interior_wall("x", 28, 20, "DW")
    it += interior_wall("y", 24, 20, "WD")
    it += interior_wall("y", 20, 28, "DO")
    it += [prop("Crate_Wood", 11, 23, 0, 10), prop("OilDrum", 26.5, 34.8, 0, 0, tint="Blue"),
           prop("PalletStack", 18, 26.5, 0, 90), prop("HayBale_Square", 22, 33, 0, 0)]
    # movement lane
    it += [prop("Barricade_Plywood_3m", 36, 24, 0, 0), prop("SandbagWall_3m", 42, 30, 0, 0),
           prop("TireStack", 46, 23, 0, 0), prop("HayBale_Round", 50, 34, 0, 0),
           prop("Barricade_Plywood_4m", 55, 26, 0, 0), prop("CableSpool", 60, 33, 0, 90),
           prop("PalletStack", 39, 37, 0, 20), prop("SandbagCorner", 64, 24, 0, 0)]
    # yard (west of the range)
    it += [prop("Container_20ft", -18, 24, 0, 90, tint="Sand"), prop("Container_20ft", -10.5, 30.5, 0, 90, tint="Rust"),
           prop("SpawnTent", -19, 36.5, 0, 0), prop("PalletStack", -6, 21, 0, 0), prop("Crate_Wood", -6, 21, 0.58, 10),
           prop("WreckedCar", 0.5, 34.5, 0, 70), prop("OilDrum", -13.6, 20.0, 0, 0, tint="Blue"),
           prop("OilDrum", -13.0, 20.5, 0, 0, tint="Red")]

    # ---- perimeter (concrete compound wall) ----
    it += fence_line("x", Y0, X0, X1, aid="Wall_Concrete_4m") + fence_line("x", Y1, X0, X1, aid="Wall_Concrete_4m")
    it += fence_line("y", X0, Y0, Y1, aid="Wall_Concrete_4m") + fence_line("y", X1, Y0, Y1, aid="Wall_Concrete_4m")
    it += [blocker(X0 - 1, Y0 - 1, X1 + 1, Y0 - 0.2, 0, 12), blocker(X0 - 1, Y1 + 0.2, X1 + 1, Y1 + 1, 0, 12),
           blocker(X0 - 1, Y0, X0 - 0.2, Y1, 0, 12), blocker(X1 + 0.2, Y0, X1 + 1, Y1, 0, 12)]
    outer = (X0 - 2.5, Y0 - 2.5, X1 + 2.5, Y1 + 2.5)
    it += scatter(21, 34, (X0 - 30, Y0 - 25, X1 + 30, Y1 + 25), [], 7.5, ["Tree_Oak_A", "Tree_Oak_B", "Tree_Oak_C"],
                  keep_out=[outer])
    it += [sound("AmbienceStaging", -12, 0, 3),
           # low lounge groove playing in the armory
           sound("StagingMusic", -12, 6.5, 3.2, spatial=True, radius=8, falloff=14, volume=0.8)]
    return {
        "name": "Staging", "path": "/Game/Maps/L_Staging", "kind": "staging",
        "bounds": (X0, Y0, X1, Y1), "lighting": "staging_golden", "game_mode": "AirsoftGameMode",
        "kill_z": -10.0, "items": it, "firing_line_x": FIRING_LINE_X,
    }


# =============================================================================================
# L_MainMenu - a corner of The Armory framed by a cine camera.
# =============================================================================================
MENU_WEAPONS = ["M4", "AK74", "SR25", "MP5", "M870"]


def _menu():
    it = []
    it += [slab(-2.4, -4.4, 6.4, 4.4, -0.2, 0.0, "Walnut", name="Floor", tile=1.2),
           slab(6.0, -4.4, 6.4, 4.4, 0, 3.6, "BrickDark", name="WallBack"),
           slab(-2.4, -4.4, 6.4, -4.0, 0, 3.6, "BrickDark", name="WallSide"),
           slab(-2.4, 4.0, 6.4, 4.4, 0, 3.6, "BrickDark", name="WallLeft"),
           slab(-2.4, -4.4, -2.0, 4.4, 0, 3.6, "BrickDark", name="WallRear"),
           slab(-2.4, -4.4, 6.4, 4.4, 3.6, 3.8, "Timber", name="Ceiling"),
           slab(5.95, -4.0, 6.0, 4.0, 3.0, 3.6, "PlywoodPainted", tint="DeepGreen", coll=False),
           slab(-2.0, -4.0, 6.0, -3.95, 3.0, 3.6, "PlywoodPainted", tint="DeepGreen", coll=False)]
    for y in (-2.0, 2.0):
        it.append(prop("WallPanel_Walnut_4m", 5.97, y, 0, 180))
    for x in (0.0, 4.0):
        it.append(prop("WallPanel_Walnut_4m", x, -3.97, 0, 90))
    for x in (0.0, 4.0):
        it.append(prop("WallPanel_Walnut_4m", x, 3.97, 0, -90))
    it += [bay_with_display("M4", 5.78, -1.3, 180), bay_with_display("AK74", 5.78, -2.95, 180),
           bay_with_display("SR25", 5.78, 0.4, 180), bay_with_display("MP5", 4.85, -3.75, 90),
           bay_with_display("M870", 3.2, -3.75, 90)]
    it += [prop("ArmorySign", 5.84, -2.3, 2.15, 180),
           prop("RugPersian", 2.3, -0.9, 0.0, 15),
           prop("ArmoryCounter", 2.75, -0.55, 0, 168),
           prop("GunCase_Hard", 2.62, -0.95, 1.045, 105),
           prop("BankersLamp", 2.85, 0.25, 1.045, 205, light=True),
           prop("Mannequin_Torso", 5.0, 1.9, 0, 205),
           prop("AmmoCrate_Wood", 5.45, -3.45, 0, 2), prop("AmmoCrate_Wood", 4.55, -3.5, 0, 8)]
    for (x, y) in ((2.6, -1.0), (4.9, -2.6), (1.0, 1.6)):
        it.append(hanging("CeilingLight_Brass", x, y, 3.6, light={"shadows": True}))
    it += [{"t": "camera", "p": (0.6, 1.2, 1.45), "yaw": -38.0, "pitch": -6.0, "focal": 35.0, "fstop": 2.8,
            "focus_at": (2.62, -0.95, 1.1)}]
    it += [start(0.0, 2.5, "None", -40.0)]
    it += [fogvol(2.0, 0.0, 1.8, 4.6, 4.6, 2.0, density=0.35, color=(0.75, 0.6, 0.45))]
    it += [capture(3.0, -1.0, 1.6, 6.0)]
    it += [sound("MenuMusic", 2, 0, 2, spatial=False)]
    return {
        "name": "MainMenu", "path": "/Game/Maps/L_MainMenu", "kind": "menu",
        "bounds": (-2.0, -4.0, 6.0, 4.0), "lighting": "menu_armory", "game_mode": "AirsoftMenuGameMode",
        "kill_z": -10.0, "items": it,
    }


def _transition():
    return {"name": "Transition", "path": "/Game/Maps/L_Transition", "kind": "transition",
            "bounds": (-1, -1, 1, 1), "lighting": None, "game_mode": None, "kill_z": -10.0, "items": []}


_BUILDERS = {"MainMenu": _menu, "Transition": _transition, "Staging": _staging, "IronwoodYard": _ironwood,
             "VelvetClub": _velvet}
MAP_ORDER = ["MainMenu", "Transition", "Staging", "IronwoodYard", "VelvetClub"]
MAP_ALIASES = {"menu": "MainMenu", "mainmenu": "MainMenu", "l_mainmenu": "MainMenu", "transition": "Transition",
               "l_transition": "Transition", "staging": "Staging", "l_staging": "Staging", "lobby": "Staging",
               "ironwood": "IronwoodYard", "ironwoodyard": "IronwoodYard", "l_ironwoodyard": "IronwoodYard",
               "field": "IronwoodYard", "velvet": "VelvetClub", "velvetclub": "VelvetClub",
               "l_velvetclub": "VelvetClub", "club": "VelvetClub"}


def resolve_map_name(name):
    return MAP_ALIASES.get(name.strip().lower().replace(" ", ""), name)


def get_map(name):
    return _BUILDERS[resolve_map_name(name)]()


def all_maps():
    return [get_map(n) for n in MAP_ORDER]


# ---------------------------------------------------------------------------------------------
# Geometry helpers shared by the checker (footprints in metres, oriented rectangles)
# ---------------------------------------------------------------------------------------------
def item_footprints(item, json_assets=None):
    """Oriented footprints of an item for collision/sight checks.
    Returns dicts: c (x,y), h (half x, half y), yaw, z0, z1, solid, los, walk, label."""
    t = item["t"]
    out = []
    if t in ("box", "blocker"):
        cx, cy, cz = item["p"]
        sx, sy, sz = item["s"]
        solid = item.get("coll", True) and t == "box"
        out.append({"c": (cx, cy), "h": (sx / 2, sy / 2), "yaw": item.get("yaw", 0.0), "z0": cz - sz / 2,
                    "z1": cz + sz / 2, "solid": solid, "los": solid, "walk": item.get("walk", False),
                    "label": item.get("name", item.get("mat", "")), "kind": t})
    elif t == "prop":
        aid = item["id"]
        bmin, bmax = asset_bounds(aid, json_assets)
        k = KNOWN_ASSETS.get(aid, {})
        sc = item.get("scale", (1.0, 1.0, 1.0))
        if isinstance(sc, (int, float)):
            sc = (sc, sc, sc)
        if k.get("core"):
            (ax, ay), (bx, by) = k["core"]
        else:
            ax, ay, bx, by = bmin[0], bmin[1], bmax[0], bmax[1]
        lx, ly = (ax + bx) / 2 / CM * sc[0], (ay + by) / 2 / CM * sc[1]
        hx, hy = (bx - ax) / 2 / CM * sc[0], (by - ay) / 2 / CM * sc[1]
        px, py, pz = item["p"]
        ox, oy = rot2(lx, ly, item.get("yaw", 0.0))
        solid = k.get("solid", True) and not item.get("nocoll") and k.get("coll", "Box") != "None"
        out.append({"c": (px + ox, py + oy), "h": (hx, hy), "yaw": item.get("yaw", 0.0),
                    "z0": pz + bmin[2] / CM * sc[2], "z1": pz + bmax[2] / CM * sc[2], "solid": solid,
                    "los": solid and k.get("los", True), "walk": False, "label": aid, "kind": "prop",
                    "openings": k.get("openings")})
    return out


def point_in_rect(px, py, fp, pad=0.0):
    dx, dy = px - fp["c"][0], py - fp["c"][1]
    lx, ly = rot2(dx, dy, -fp["yaw"])
    return abs(lx) <= fp["h"][0] + pad and abs(ly) <= fp["h"][1] + pad


def rect_corners(fp):
    cx, cy = fp["c"]
    hx, hy = fp["h"]
    pts = []
    for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        ox, oy = rot2(sx * hx, sy * hy, fp["yaw"])
        pts.append((cx + ox, cy + oy))
    return pts


def segment_hits_rect(ax, ay, bx, by, fp, shrink=0.0):
    """True if segment a-b passes through the oriented rectangle (slab test in local space)."""
    cx, cy = fp["c"]
    lax, lay = rot2(ax - cx, ay - cy, -fp["yaw"])
    lbx, lby = rot2(bx - cx, by - cy, -fp["yaw"])
    hx, hy = fp["h"][0] - shrink, fp["h"][1] - shrink
    if hx <= 0 or hy <= 0:
        return False
    t0, t1 = 0.0, 1.0
    for (p, d, h) in ((lax, lbx - lax, hx), (lay, lby - lay, hy)):
        if abs(d) < 1e-9:
            if p < -h or p > h:
                return False
            continue
        ta, tb = (-h - p) / d, (h - p) / d
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 > t1:
            return False
    return True
