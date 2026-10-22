"""Andrew's Airsoft - L_SaltmarshTerminal: a rain-soaked container port at night (story mission 5, "Dead Tide").

Plain layout data (no `unreal` import), registered in layouts.py as "SaltmarshTerminal" and loaded lazily by
layouts._harbor(), which passes the layouts module in: build(L) -> item list, MAP -> map metadata.
Units and axes as layouts.py: metres, +X east, +Y south on the plans, yaw turns +X toward +Y.

Look: a cold teal-blue night, rain, sodium-orange floodlight pools between black container canyons, red crane
beacons and a few neon accents. West: the truck gate (Gate 3) and its booth; Blue / Andrew start on the gate
apron. Middle: the stacking yard, container blocks 1-3 high in four bands with three east-west lanes (north,
central, south) and three cross aisles; slip gaps between rows. East: the quay. A warehouse (Shed 7) sits on
it with a north mezzanine office; it is the boss arena (rain through the broken roof sheets, backlit haze,
one hard key light through the roof gap). Red spawns at its back behind the pallet racks. South apron: the
ship-to-shore crane over a moored container ship (out of bounds, across a strip of water).
Skirmish objectives: A north lane, B central lane, C under the crane.
Everything is original: no real port, shipping line, ship or brand names.
"""

import math
import random

LEVELS = (("Yard", 0.0), ("Mezzanine", 3.6))
X0, X1, Y0, Y1 = -50.0, 48.0, -34.0, 34.0
FENCE_Y = 33.0                 # north / south fence lines (y = -33 / +33)
WEST_FENCE_X = -38.0
QUAY_X = 48.0                  # quay edge (water beyond)
WH_X0, WH_X1, WH_Y0, WH_Y1 = 22.0, 46.0, -22.0, 6.0     # warehouse (Shed 7)
WH_H = 8.0                     # eaves (cladding panel height)
MEZ_Z = 3.6
MEZ = (34.0, -22.0, 46.0, -15.0)                        # mezzanine office deck (x0, y0, x1, y1)
C40_L, C40_W, C40_H = 12.19, 2.44, 2.59
C20_L = 6.06
CRANE_X, CRANE_Y = 38.0, 19.0                           # STS crane centre (legs at +-8 m)
PARKED = ["Body", "Glass", "GlassPrivacy", "Wheels", "Interior"]

MAP = {
    "name": "SaltmarshTerminal", "path": "/Game/Maps/L_SaltmarshTerminal", "kind": "match",
    "bounds": (X0, Y0, X1, Y1), "lighting": "saltmarsh_rain", "game_mode": "AirsoftGameMode",
    "kill_z": -10.0, "levels": LEVELS,
    "nav": (X0 - 1.0, Y0 - 1.0, -1.0, X1 + 1.0, Y1 + 1.0, 8.0),
}

CONTAINER_TINTS = ["Rust", "Teal", "Blue", "Red", "Grey", "Sand", "Green", "Orange", "White", "Rust", "Teal", "Grey"]


def _sub_rects(rect, holes):
    """Axis-aligned rect minus holes -> list of rects."""
    out = [rect]
    for (hx0, hy0, hx1, hy1) in holes:
        nxt = []
        for (x0, y0, x1, y1) in out:
            if hx1 <= x0 or hx0 >= x1 or hy1 <= y0 or hy0 >= y1:
                nxt.append((x0, y0, x1, y1))
                continue
            if hy0 > y0:
                nxt.append((x0, y0, x1, hy0))
            if hy1 < y1:
                nxt.append((x0, hy1, x1, y1))
            my0, my1 = max(y0, hy0), min(y1, hy1)
            if hx0 > x0:
                nxt.append((x0, my0, hx0, my1))
            if hx1 < x1:
                nxt.append((hx1, my0, x1, my1))
        out = nxt
    return out


def _puddle(L, x, y, z, sx, sy):
    """Standing water: three overlapping, differently turned flat boxes (irregular outline, no z-fighting)."""
    r = random.Random(int(x * 131 + y * 17 + sx * 7))
    a = r.uniform(-25.0, 25.0)
    out = []
    for k, (fx, fy, ox, oy, da) in enumerate(((1.0, 0.8, 0.0, 0.0, 0.0), (0.75, 0.9, 0.3, -0.2, 32.0),
                                               (0.6, 0.7, -0.32, 0.25, -27.0))):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        dx, dy = ox * sx * ca - oy * sy * sa, ox * sx * sa + oy * sy * ca
        t = 0.008 + 0.003 * k
        out.append(L.box(x + dx, y + dy, z + t / 2, sx * fx, sy * fy, t, "Puddle", yaw=a + da + r.uniform(-6, 6),
                         coll=False, cast=False, name="Puddle"))
    return out


# =============================================================================================
# Container yard plan: (band rows, blocks) -> stacks
# =============================================================================================
# rows: y centre of each container row (containers lie along X)
BANDS = {
    "N": (-30.6, -28.1, -23.6),
    "MN": (-14.7, -12.2, -7.9, -5.4),
    "MS": (5.4, 7.9, 12.2, 14.7),
    "S": (23.6, 28.1, 30.6),
}
BLOCK_X = (-31.0, -13.0, 5.0)          # 40 ft slot centres (12.19 m long); aisles between at -22, -4; quay beyond 11.1
# height of each stack (0 = empty slot, "20" = two 20 ft boxes with a slip gap, "20h" = one 20 ft only)
STACKS = {
    ("N", -31.0): (3, 2, 1), ("N", -13.0): (2, 3, "20"), ("N", 5.0): (3, 2, 2),
    ("MN", -31.0): (2, 1, 2, "20h"), ("MN", -13.0): (3, 2, 1, 2), ("MN", 5.0): (1, "20", 3, 2),
    ("MS", -31.0): ("20h", 2, 1, 2), ("MS", -13.0): (2, 1, 2, 3), ("MS", 5.0): (2, 3, "20", 1),
    ("S", -31.0): (1, 2, 3), ("S", -13.0): ("20", 3, 2), ("S", 5.0): (2, 2, 3),
}


def _container_stacks(L, rng):
    it = []
    k = 0
    for (band, bx), hs in STACKS.items():
        rows = BANDS[band]
        for ry, h in zip(rows, hs):
            if h == 0:
                continue
            if h in ("20", "20h"):
                # two 20 ft boxes end to end with a 0.9 m slip gap between them (or one, leaving half the slot open)
                xs = (bx - C20_L / 2 - 0.45, bx + C20_L / 2 + 0.45) if h == "20" else (bx - C20_L / 2 - 0.45,)
                for x in xs:
                    it.append(L.prop("Container_20ft", x, ry, 0.0, 180.0 if rng.random() < 0.5 else 0.0,
                                     tint=CONTAINER_TINTS[k % len(CONTAINER_TINTS)]))
                    k += 1
                    if rng.random() < 0.5:
                        it.append(L.prop("Container_20ft", x + rng.uniform(-0.15, 0.15), ry, C40_H,
                                         0.0, tint=CONTAINER_TINTS[(k * 5) % len(CONTAINER_TINTS)]))
                        k += 1
                continue
            for lvl in range(h):
                it.append(L.prop("Harbor_Container40", bx + rng.uniform(-0.12, 0.12), ry + rng.uniform(-0.04, 0.04),
                                 lvl * C40_H, (180.0 if (k * 7) % 3 == 0 else 0.0) + rng.uniform(-0.6, 0.6),
                                 tint=CONTAINER_TINTS[(k * 7 + lvl) % len(CONTAINER_TINTS)]))
                k += 1
    # 20 ft boxes at the yard's east edge (x 14..20), two rows per band, 1-2 high
    for band, rows in BANDS.items():
        for j, ry in enumerate(rows[:2] if band in ("N", "S") else (rows[0], rows[3])):
            h = 1 + (j + len(band)) % 2
            for lvl in range(h):
                it.append(L.prop("Container_20ft", 17.2, ry, lvl * C40_H, 0.0, tint=CONTAINER_TINTS[(k + lvl) % 12]))
            k += 1
    return it


def _outside_stacks(L, rng):
    """Out-of-bounds container walls beyond the north / south fences (silhouettes, 2-4 high)."""
    it = []
    k = 3
    for y in (-37.0, -39.6, -42.2, 37.0, 39.6, 42.2, 46.0):
        for x in (-44.0, -31.0, -18.0, -5.0, 8.0, 21.0, 34.0):
            h = 2 + (k * 3) % 3
            for lvl in range(h):
                it.append(L.prop("Harbor_Container40", x + rng.uniform(-0.3, 0.3), y, lvl * C40_H, 0.0,
                                 tint=CONTAINER_TINTS[(k + lvl * 5) % 12], nocoll=True))
            k += 1
    return it


# =============================================================================================
# Build
# =============================================================================================
def build(L=None):
    if L is None:
        from . import layouts as L
    it = []
    rng = random.Random(5150)
    prop, slab, patch, blocker = L.prop, L.slab, L.patch, L.blocker

    # ---------------------------------------------------------------- ground, water, quay
    it += [slab(X0 - 30.0, -60.0, QUAY_X, 60.0, -0.4, 0.0, "AsphaltWet", name="Yard", tile=3.0),
           slab(QUAY_X - 0.4, -120.0, QUAY_X, 120.0, -2.6, 0.0, "Concrete", name="QuayWall"),
           slab(QUAY_X - 0.6, -120.0, QUAY_X, 120.0, -0.02, 0.05, "PaintLineYellow", name="QuayCope", coll=False),
           slab(QUAY_X, -260.0, 260.0, 260.0, -2.4, -2.0, "Puddle", name="Harbour", coll=False, cast=False),
           blocker(QUAY_X - 0.2, Y0 - 2.0, QUAY_X + 0.6, Y1 + 2.0, 0.0, 14.0),
           slab(QUAY_X - 0.8, -120.0, QUAY_X - 0.6, 120.0, 0.0, 0.25, "Concrete", name="QuayKerb")]
    # lane markings and stacking-slot lines
    for (y, mat) in ((-19.0, "PaintLineYellow"), (0.0, "PaintLineYellow"), (19.0, "PaintLineYellow")):
        for x in range(-36, 12, 6):
            it.append(patch(x, y - 0.06, x + 3.0, y + 0.06, 0.006, mat, name="LaneDash"))
    for band, rows in BANDS.items():
        for bx in BLOCK_X:
            for ry in rows:
                it.append(patch(bx - 6.3, ry - 1.32, bx + 6.3, ry - 1.26, 0.006, "PaintLineWhite", name="SlotLine"))
    # crane rails on the south apron
    for x in (CRANE_X - 8.0, CRANE_X + 8.0):
        it += [slab(x - 0.09, 6.4, x + 0.09, 34.0, 0.0, 0.06, "PaintedSteel", tint="Gunmetal", name="CraneRail"),
               patch(x - 0.6, 6.4, x + 0.6, 34.0, 0.005, "ConcreteGarageWet", name="RailBed")]

    # ---------------------------------------------------------------- perimeter fences + blockers
    def fence_x_run(y, xa, xb):
        out = []
        n = int(round((xb - xa) / 4.0))
        for i in range(n):
            out.append(prop("Harbor_ChainFence_4m", xa + 2.0 + i * 4.0, y, 0.0, 90.0))
        return out

    def fence_y_run(x, ya, yb):
        out = []
        n = int(round((yb - ya) / 4.0))
        for i in range(n):
            out.append(prop("Harbor_ChainFence_4m", x, ya + 2.0 + i * 4.0, 0.0, 0.0))
        return out
    it += fence_x_run(-FENCE_Y, WEST_FENCE_X, QUAY_X - 2.0) + fence_x_run(FENCE_Y, WEST_FENCE_X, QUAY_X - 2.0)
    it += [blocker(WEST_FENCE_X, -FENCE_Y - 0.4, QUAY_X, -FENCE_Y + 0.15, 0.0, 14.0),
           blocker(WEST_FENCE_X, FENCE_Y - 0.15, QUAY_X, FENCE_Y + 0.4, 0.0, 14.0)]
    # west fence with the truck gate (y -8..8) and two pedestrian gaps (north / south lanes)
    for (ya, yb) in ((-FENCE_Y, -22.0), (-20.0, -8.0), (8.0, 20.0), (22.0, FENCE_Y)):
        it += fence_y_run(WEST_FENCE_X, ya, yb)
        it.append(blocker(WEST_FENCE_X - 0.2, ya, WEST_FENCE_X + 0.2, yb, 2.6, 14.0))
    it += [blocker(X0 - 0.6, -FENCE_Y - 0.4, WEST_FENCE_X, -FENCE_Y + 0.15, 0.0, 14.0),
           blocker(X0 - 0.6, FENCE_Y - 0.15, WEST_FENCE_X, FENCE_Y + 0.4, 0.0, 14.0),
           blocker(X0 - 0.6, -FENCE_Y, X0, FENCE_Y, 0.0, 14.0)]
    # gate apron: kerbed islands, gatehouse, barrier arms (raised side by side, lanes open), signage
    it += [slab(-49.0, -FENCE_Y, X0, FENCE_Y, 0.0, 0.18, "Concrete", name="ApronKerb"),
           slab(-46.0, -0.5, -40.5, 0.5, 0.0, 0.15, "Concrete", name="LaneIsland"),
           prop("Harbor_Gatehouse", -42.0, -11.2, 0.0, 0.0, light=True),
           prop("Garage_BarrierArm", -38.6, -7.6, 0.0, 0.0), prop("Garage_BarrierArm", -38.6, 7.6, 0.0, 180.0),
           prop("Garage_Cone", -40.0, -0.9, 0.0, 0.0), prop("Garage_Cone", -44.5, 0.9, 0.0, 30.0),
           prop("Garage_JerseyBarrier", -40.4, -17.0, 0.0, 90.0), prop("Garage_JerseyBarrier", -40.4, 17.0, 0.0, 90.0),
           L.text(-38.1, -13.0, 3.3, 180.0, "SALTMARSH TERMINAL  -  GATE 3", size=34.0, color="White", glow=1.4)]
    for (x, y, yaw) in ((-48.6, -24.0, 0.0), (-48.6, -6.0, 0.0), (-48.6, 12.0, 0.0), (-48.6, 28.0, 0.0)):
        it.append(prop("StreetLamp", x, y, 0.0, yaw, light={"cd": 14.0, "radius": 14.0}))

    # Blue / Andrew starts on the gate apron (the first one is Andrew's story start beside the booth)
    starts = [(-44.6, -6.0)]
    for x in (-47.6, -45.6):
        for y in (-3.6, -1.6, 1.6, 3.6, 5.6):
            starts.append((x, y))
    starts.append((-43.4, 3.0))
    for (x, y) in starts:
        it.append(L.start(x, y, "Blue", 0.0))

    # ---------------------------------------------------------------- yard containers + lane cover
    it += _container_stacks(L, rng)
    it += _outside_stacks(L, random.Random(808))
    it += _lane_cover(L, rng)

    # ---------------------------------------------------------------- warehouse (Shed 7)
    it += _warehouse(L, rng)

    # ---------------------------------------------------------------- quay: bollards, fenders, crane, VIP lot
    for y in range(-30, 34, 8):
        it.append(prop("Harbor_MooringBollard", QUAY_X - 0.9, float(y), 0.0, 0.0))
        it.append(prop("Harbor_Fender", QUAY_X, float(y) + 4.0, 0.0, 0.0))
    for y in (-30.0, -14.0, 2.0, 18.0, 26.0):
        # mooring lines from the bollards out to the ship's rail (pitched thin boxes)
        dx, dz = 52.0 - (QUAY_X - 0.9), 8.0 - 0.6
        ln = math.hypot(dx, dz)
        it.append(L.box(QUAY_X - 0.9 + dx / 2, y + 1.0, 0.6 + dz / 2, ln, 0.05, 0.05, "Rubber", pitch=-math.degrees(math.atan2(dz, dx)),
                        yaw=8.0, coll=False, name="MooringLine"))
    it.append(prop("Harbor_STSCrane", CRANE_X, CRANE_Y, 0.0, 0.0))
    # the crane's legs + rail bogies (the asset is Solid false for the checker: its portal is open)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = CRANE_X + sx * 8.0, CRANE_Y + sy * 8.0
            it.append(blocker(cx - 1.7, cy - 0.7, cx + 1.7, cy + 0.7, 0.0, 14.0))
    # containers being worked under the crane, a forklift and the VIP lot (Varga's cars) on the north apron
    it += [prop("Harbor_Container40", CRANE_X - 1.0, CRANE_Y - 3.6, 0.0, 90.0, tint="Teal"),
           prop("Harbor_Container40", CRANE_X + 1.8, CRANE_Y + 4.2, 0.0, 90.0, tint="Rust"),
           prop("Harbor_Container40", CRANE_X + 1.8, CRANE_Y + 4.2, C40_H, 90.0, tint="Grey"),
           prop("Garage_JerseyBarrier", 30.6, 12.6, 0.0, 90.0), prop("OilDrum", 27.0, 30.6, 0.0, 0.0, tint="Blue"),
           prop("OilDrum", 27.6, 31.1, 0.0, 30.0, tint="Blue"), prop("PalletStack", 25.2, 13.0, 0.0, 10.0),
           prop("Crate_Wood", 25.2, 13.0, 0.58, 4.0), prop("Harbor_Forklift", 26.5, 24.5, 0.0, 200.0),
           prop("CableSpool", 44.6, 9.8, 0.0, 0.0)]
    it += [prop("Car_Limousine", 28.0, -26.6, 0.0, 180.0, tint="Obsidian", pieces=PARKED),
           prop("Car_SUV", 33.4, -26.8, 0.0, 180.0, tint="Obsidian", pieces=PARKED),
           prop("Car_SUV", 38.8, -26.6, 0.0, 176.0, tint="Gunmetal", pieces=PARKED),
           prop("Car_GrandTourer", 44.0, -29.8, 0.0, 90.0, tint="DeepBurgundy", pieces=PARKED),
           prop("Garage_JerseyBarrier", 30.6, -30.4, 0.0, 0.0), prop("Garage_JerseyBarrier", 41.0, -24.0, 0.0, 0.0)]
    for x in (26.0, 31.0, 36.0, 41.0):
        it.append(patch(x - 0.05, -30.0, x + 0.05, -24.0, 0.006, "PaintLineWhite", name="Stall"))

    # ---------------------------------------------------------------- ship (out of bounds) + skyline
    it += _ship(L, random.Random(4242))
    it += _skyline(L, random.Random(6161))
    it += [prop("Harbor_STSCrane", CRANE_X, -64.0, 0.0, 0.0), prop("Harbor_STSCrane", CRANE_X, 68.0, 0.0, 0.0)]

    # ---------------------------------------------------------------- lights (shadowed: 4 masts, crane, shed key)
    for (x, y, yaw) in ((-27.0, -18.6, 0.0), (-3.5, 3.4, 180.0), (12.7, 17.2, 200.0), (21.6, -28.2, 30.0)):
        it.append(prop("Harbor_FloodMast", x, y, 0.0, yaw, light=True))
    it.append(L.light("spot", CRANE_X + 2.0, CRANE_Y, 29.6, pitch=-90.0, yaw=0.0, color=(0.82, 0.88, 1.0), cd=800.0,
                      radius=42.0, cone=(30, 55), shadows=True, vol=0.8, src=30.0))
    # sodium wallpacks on the shed facades (unshadowed pools of orange on the wet asphalt)
    for (x, y, yaw) in ((WH_X0 - 0.15, -18.0, 180.0), (WH_X0 - 0.15, -6.0, 180.0), (WH_X0 - 0.15, 3.0, 180.0),
                        (30.0, WH_Y1 + 0.15, 90.0), (40.0, WH_Y1 + 0.15, 90.0), (30.0, WH_Y0 - 0.15, -90.0)):
        it.append(prop("Garage_LightSodium", x, y, 4.2, yaw, light={"cd": 10.0, "radius": 13.0}))

    # ---------------------------------------------------------------- objectives (skirmish)
    it += [L.objective("A", -16.5, -19.0, 0.0, radius=5.0, half_height=1.8),
           L.objective("B", -4.0, -0.4, 0.0, radius=5.0, half_height=1.8),
           L.objective("C", CRANE_X - 4.6, CRANE_Y, 0.0, radius=5.0, half_height=1.8)]

    # ---------------------------------------------------------------- atmosphere, reflections, sound
    it += [L.fogvol(-12.0, 0.0, 2.5, 30.0, 30.0, 3.0, density=0.22, color=(0.5, 0.62, 0.66)),
           L.fogvol(34.0, -8.0, 4.5, 12.0, 14.0, 4.5, density=0.5, color=(0.62, 0.68, 0.72)),
           L.fogvol(36.0, 20.0, 3.0, 14.0, 14.0, 3.0, density=0.25, color=(0.52, 0.6, 0.66))]
    for (x, y) in ((-30.0, 0.0), (-12.0, -19.0), (-12.0, 19.0), (5.0, 0.0), (34.0, -8.0), (36.0, 19.0), (-44.0, 0.0)):
        it.append(L.capture(x, y, 2.0, 16.0))
    it += [L.sound("AmbienceGarageRoof", -20.0, 0.0, 2.0, spatial=True, radius=30.0, falloff=20.0, volume=1.0),
           L.sound("AmbienceGarageRoof", 10.0, 0.0, 2.0, spatial=True, radius=30.0, falloff=20.0, volume=1.0),
           L.sound("AmbienceGarageRoof", 38.0, 20.0, 2.0, spatial=True, radius=20.0, falloff=16.0, volume=1.0),
           L.sound("AmbienceGarage", 34.0, -8.0, 2.0, spatial=True, radius=12.0, falloff=10.0, volume=0.9),
           L.sound("AmbienceStaging", -44.0, 0.0, 2.0, spatial=True, radius=8.0, falloff=10.0, volume=0.5)]
    return it


# =============================================================================================
# Lane cover: waist / head height pieces every few metres along the three lanes and the cross aisles
# =============================================================================================
def _lane_cover(L, rng):
    prop = L.prop
    it = []
    # central lane (y -4..4): the reach stacker holding a box high over the lane, a box truck, barriers, pallets
    rs_x, rs_y = -10.0, 0.6
    it.append(prop("Harbor_ReachStacker", rs_x, rs_y, 0.0, 180.0))
    # the box hangs under the spreader (SpreaderBottom: local +X 7.8 m, z 5.82 m; yaw 180 puts it at -X), across
    # the lane with 3.2 m of headroom under it
    it.append(prop("Harbor_Container40", rs_x - 7.8, rs_y, 5.82 - C40_H, 90.0, tint="Rust"))
    # a 20 ft box parked across the lane mouth inside the gate: screens the gate apron from the length of the lane
    it.append(prop("Container_20ft", -35.8, 0.0, 0.0, 90.0, tint="Sand"))
    it += [prop("BoxTruck", -29.5, 1.6, 0.0, 4.0, tint="Grey", pieces=PARKED),
           prop("Garage_JerseyBarrier", -22.0, -2.2, 0.0, 0.0), prop("Garage_JerseyBarrier", -18.4, 2.4, 0.0, 15.0),
           prop("PalletStack", -24.6, 2.8, 0.0, 12.0), prop("PalletStack", -24.6, 2.8, 0.58, 30.0),
           prop("OilDrum", -2.4, 2.9, 0.0, 0.0, tint="Red"), prop("OilDrum", -1.8, 3.4, 0.0, 40.0, tint="Red"),
           prop("Crate_Wood", 2.2, -2.8, 0.0, 8.0), prop("Crate_Wood", 2.2, -2.8, 0.62, -6.0),
           prop("Garage_JerseyBarrier", 7.4, 2.0, 0.0, 0.0), prop("PalletStack", 11.8, -2.4, 0.0, 0.0),
           prop("Harbor_Forklift", 14.6, 1.8, 0.0, 160.0), prop("Garage_Cone", -6.6, -3.2, 0.0, 0.0),
           prop("Garage_Cone", 4.6, 3.3, 0.0, 30.0), prop("TireStack", -33.6, -2.9, 0.0, 0.0)]
    # north lane (y -22..-16)
    it += [prop("Garage_JerseyBarrier", -32.0, -20.4, 0.0, 10.0), prop("PalletStack", -21.0, -17.6, 0.0, 0.0),
           prop("Crate_Wood", -21.0, -17.6, 0.58, 15.0), prop("OilDrum", -11.0, -21.0, 0.0, 0.0, tint="Blue"),
           prop("OilDrum", -10.4, -21.4, 0.0, 0.0, tint="Blue"), prop("Garage_JerseyBarrier", -4.0, -17.2, 0.0, -8.0),
           prop("PalletStack", 3.4, -20.8, 0.0, 6.0), prop("Garage_JerseyBarrier", 9.6, -17.8, 0.0, 0.0),
           prop("Crate_Ammo", -23.4, -21.2, 0.0, 30.0), prop("Garage_Cone", -14.0, -16.6, 0.0, 0.0)]
    # south lane (y 16..22)
    it += [prop("PalletStack", -32.4, 20.6, 0.0, 0.0), prop("Garage_JerseyBarrier", -25.0, 17.4, 0.0, 0.0),
           prop("OilDrum", -16.6, 21.0, 0.0, 0.0, tint="Green"), prop("Crate_Wood", -9.0, 17.2, 0.0, -10.0),
           prop("Garage_JerseyBarrier", -2.0, 20.6, 0.0, 6.0), prop("Dumpster", 4.0, 17.4, 0.0, 90.0, tint="Rust"),
           prop("PalletStack", 9.2, 20.8, 0.0, 0.0), prop("PalletStack", 9.2, 20.8, 0.58, 20.0),
           prop("TireStack", -28.6, 21.2, 0.0, 0.0)]
    # cross aisles (x -22, -4, 11..14)
    for (x, y, aid, yaw) in ((-22.0, -10.0, "PalletStack", 0.0), (-21.6, 9.4, "Crate_Wood", 20.0), (-4.2, -10.4, "OilDrum", 0.0),
                             (-3.6, 10.6, "PalletStack", 10.0), (-22.4, -26.0, "Crate_Wood", 0.0), (-4.0, 26.2, "PalletStack", 0.0),
                             (12.6, -10.8, "Garage_JerseyBarrier", 90.0), (12.6, 10.2, "Garage_JerseyBarrier", 90.0),
                             (12.6, -26.0, "OilDrum", 0.0), (12.8, 26.4, "Crate_Wood", 0.0)):
        it.append(prop(aid, x, y, 0.0, yaw, tint="Rust") if aid == "OilDrum" else prop(aid, x, y, 0.0, yaw))
    # puddles in the lanes (where the asphalt dips) and along the quay
    for (x, y, sx, sy) in ((-30.0, -1.0, 3.2, 1.6), (-16.0, 2.4, 2.4, 1.2), (0.6, -1.2, 3.0, 1.4), (9.0, 1.6, 2.0, 1.0),
                           (-26.0, -19.4, 2.2, 1.0), (-8.0, -18.6, 2.6, 1.2), (6.0, -19.2, 1.8, 0.9),
                           (-20.0, 19.0, 2.6, 1.1), (-6.0, 18.6, 2.0, 1.0), (7.0, 19.6, 2.4, 1.0),
                           (-43.0, 2.0, 3.0, 1.6), (-41.0, -4.6, 1.8, 1.0), (30.0, 9.6, 2.6, 1.2), (44.0, 22.0, 2.2, 1.0),
                           (34.0, -30.0, 3.0, 1.2), (20.0, -12.0, 1.6, 2.6), (24.0, 30.0, 2.4, 1.0)):
        it += _puddle(L, x, y, 0.0, sx, sy)
    return it


# =============================================================================================
# Warehouse (Shed 7): corrugated walls, two roller doors on the yard side, one to the south apron,
# trusses and a broken roof, pallet racks, the boss's car, mezzanine office on the north end
# =============================================================================================
def _warehouse(L, rng):
    prop, slab, blocker = L.prop, L.slab, L.blocker
    it = []
    x0, x1, y0, y1 = WH_X0, WH_X1, WH_Y0, WH_Y1
    it.append(slab(x0, y0, x1, y1, -0.05, 0.02, "ConcreteFloor", name="ShedFloor", tint="Grey"))
    # west wall (yard side, outside = -X): 7 bays, roller doors at bays 1 and 3 (y -18, -10)
    for i in range(7):
        yc = y0 + 2.0 + i * 4.0
        aid = "Harbor_RollerDoor" if i in (1, 3) else "Harbor_CladdingPanel_4m"
        it.append(prop(aid, x0, yc, 0.0, 180.0, tint=None if aid == "Harbor_RollerDoor" else "Teal"))
    # east wall (quay side, outside = +X): solid
    for i in range(7):
        it.append(prop("Harbor_CladdingPanel_4m", x1, y0 + 2.0 + i * 4.0, 0.0, 0.0, tint="Teal"))
    # north / south walls (outside = -Y / +Y): 6 bays; a roller door on the south side (to the crane apron)
    for i in range(6):
        xc = x0 + 2.0 + i * 4.0
        it.append(prop("Harbor_CladdingPanel_4m", xc, y0, 0.0, -90.0, tint="Teal"))
        aid = "Harbor_RollerDoor" if i == 2 else "Harbor_CladdingPanel_4m"
        it.append(prop(aid, xc, y1, 0.0, 90.0, tint=None if aid == "Harbor_RollerDoor" else "Teal"))
    # wall blockers above the doors' clear height (the doors are walk-through for the checker) and solid
    # walls for the walk graph (the panels' box collision); door gaps left open below 3.2 m
    def wall_block(axis, fixed, a0, a1, doors):
        out = []
        cur = a0
        for (d0, d1) in doors:
            if d0 > cur:
                out.append((cur, d0, 0.0))
            out.append((d0, d1, 3.2))
            cur = d1
        if cur < a1:
            out.append((cur, a1, 0.0))
        res = []
        for (s0, s1, zb) in out:
            if axis == "y":
                res.append(blocker(fixed - 0.15, s0, fixed + 0.15, s1, zb, 14.0))
            else:
                res.append(blocker(s0, fixed - 0.15, s1, fixed + 0.15, zb, 14.0))
        return res
    it += wall_block("y", x0, y0, y1, [(-19.8, -16.2), (-11.8, -8.2)])
    it += wall_block("x", y1, x0, x1, [(30.2, 33.8)])
    it += [blocker(x1 - 0.15, y0, x1 + 0.15, y1, 0.0, 14.0), blocker(x0, y0 - 0.15, x1, y0 + 0.15, 0.0, 14.0)]
    # trusses every 4 m (span along X, scaled to 24 m) and the roof: sheets with two broken gaps over the
    # floor (rain falls through; the key light shafts in through the east gap)
    for i in range(8):
        yc = y0 + i * 4.0
        it.append(prop("Harbor_RoofTruss_22m", (x0 + x1) / 2, yc, WH_H, 0.0, scale=(24.0 / 22.0, 1.0, 1.0)))
    roof_z = WH_H + 2.75
    gaps = [(28.0, -9.0, 32.0, -6.0), (36.0, -4.0, 39.0, 0.5)]
    for (rx0, ry0, rx1, ry1) in _sub_rects((x0, y0, x1, y1), gaps):
        it.append(slab(rx0, ry0, rx1, ry1, roof_z, roof_z + 0.08, "CorrodedMetal", name="RoofSheet"))
    it.append(slab(x0 - 0.3, y0 - 0.3, x1 + 0.3, y1 + 0.3, roof_z + 0.08, roof_z + 0.12, "PaintedSteel", tint="Gunmetal",
                   name="RoofCap", coll=False))
    # gable infill between the eaves (8 m) and the roof (10.75 m) on all four sides
    it += [slab(x0 - 0.1, y0, x0 + 0.05, y1, WH_H, roof_z, "CorrodedMetal", name="Gable"),
           slab(x1 - 0.05, y0, x1 + 0.1, y1, WH_H, roof_z, "CorrodedMetal", name="Gable"),
           slab(x0, y0 - 0.1, x1, y0 + 0.05, WH_H, roof_z, "CorrodedMetal", name="Gable"),
           slab(x0, y1 - 0.05, x1, y1 + 0.1, WH_H, roof_z, "CorrodedMetal", name="Gable")]
    # puddles under the roof gaps
    for (gx0, gy0, gx1, gy1) in gaps:
        it += _puddle(L, (gx0 + gx1) / 2, (gy0 + gy1) / 2, 0.02, gx1 - gx0 + 0.6, gy1 - gy0 + 0.4)

    # --- arena floor: rack rows screening the Red spawn at the back (east), cover islands mid-floor
    for y in (-13.2, -10.5, -7.8, -2.4, 0.3):
        it.append(prop("Harbor_PalletRack", 37.2, y, 0.0, 0.0))
    for y in (-7.8, 3.0):
        it.append(prop("Harbor_PalletRack", 27.4, y, 0.0, 0.0))
    it += [prop("Car_Limousine", 31.0, -1.6, 0.0, 200.0, tint="Obsidian"),          # Varga's car, lights on
           prop("Harbor_Forklift", 29.6, -12.6, 0.0, 70.0),
           prop("PalletStack", 25.4, -14.4, 0.0, 10.0), prop("PalletStack", 25.4, -14.4, 0.58, -6.0),
           prop("Crate_Wood", 33.0, -9.6, 0.0, 15.0), prop("Crate_Wood", 33.0, -9.6, 0.62, 0.0),
           prop("Crate_Ammo", 33.4, -8.4, 0.0, 30.0), prop("Garage_JerseyBarrier", 25.6, -4.0, 0.0, 90.0),
           prop("OilDrum", 41.6, 4.6, 0.0, 0.0, tint="Red"), prop("OilDrum", 42.2, 4.2, 0.0, 30.0, tint="Red"),
           prop("Container_20ft", 44.2, -18.6, 0.0, 90.0, tint="Rust"), prop("Container_20ft", 25.6, 4.0, 0.0, 0.0, tint="Grey")]
    # Red starts at the back of the shed, behind the rack rows (x 39.6..44.4)
    for x in (40.0, 42.0, 44.0):
        for y in (-12.6, -6.0, -3.6, -1.2):
            it.append(L.start(x, y, "Red", 180.0))

    # --- mezzanine office (north end, z 3.6): deck on columns, stair down to the floor, rail, lit office cabin
    mx0, my0, mx1, my1 = MEZ
    it += [slab(mx0, my0, mx1, my1, MEZ_Z - 0.3, MEZ_Z, "ConcreteFloor", name="MezzDeck", tint="Grey")]
    for (cx, cy) in ((mx0 + 0.2, my1 - 0.2), (mx0 + 6.0, my1 - 0.2), (mx1 - 0.6, my1 - 0.2)):
        it.append(slab(cx - 0.15, cy - 0.15, cx + 0.15, cy + 0.15, 0.0, MEZ_Z - 0.3, "PaintedSteel", tint="Gunmetal",
                       name="MezzColumn"))
    it += _stair_west(L, mx0, my1 - 1.0)
    # rail along the open edges (south edge and the west edge north of the stair)
    it += [slab(mx0 + 1.2, my1 - 0.06, mx1, my1, MEZ_Z, MEZ_Z + 1.05, "PaintedSteel", tint="Black", name="MezzRail",
                coll=True),
           slab(mx0 - 0.06, my0, mx0, my1 - 2.2, MEZ_Z, MEZ_Z + 1.05, "PaintedSteel", tint="Black", name="MezzRail")]
    # office cabin on the deck (east half): walls with a window band, lit inside, door gap to the deck
    ox0, oy0, ox1, oy1 = 40.0, my0, mx1, my0 + 4.6
    it += L.wall_run("x", oy1, ox0, ox1, MEZ_Z, MEZ_Z + 2.8, 0.12, "PlywoodPainted", openings=[(40.6, 41.6, 2.1)],
                     name="OfficeWall", tint="Grey")
    it += [slab(ox0 - 0.06, oy0, ox0 + 0.06, oy1, MEZ_Z, MEZ_Z + 1.0, "PlywoodPainted", name="OfficeWall", tint="Grey"),
           slab(ox0 - 0.06, oy0, ox0 + 0.06, oy1, MEZ_Z + 2.2, MEZ_Z + 2.8, "PlywoodPainted", name="OfficeWall", tint="Grey"),
           slab(ox0 - 0.03, oy0 + 0.2, ox0 + 0.03, oy1 - 0.2, MEZ_Z + 1.0, MEZ_Z + 2.2, "Glass", name="OfficeWindow"),
           slab(ox0, oy0, ox1, oy1, MEZ_Z + 2.8, MEZ_Z + 2.9, "PlywoodPainted", name="OfficeRoof", tint="Grey"),
           L.box((ox0 + ox1) / 2, (oy0 + oy1) / 2, MEZ_Z + 2.76, 3.2, 0.3, 0.04, "Emissive:Warm", glow=10.0, coll=False,
                 cast=False, name="OfficePanel"),
           L.light("rect", (ox0 + ox1) / 2, (oy0 + oy1) / 2, MEZ_Z + 2.7, pitch=-90.0, color="Warm", cd=3.0, radius=7.0,
                   w=3.0, h=0.3, shadows=False),
           prop("Crate_Wood", 44.6, -21.0, MEZ_Z, 0.0), prop("Crate_Ammo", 43.4, -21.2, MEZ_Z, 10.0)]
    it.append(L.text(ox0 - 0.08, (oy0 + oy1) / 2, MEZ_Z + 3.2, 180.0, "SHED 7  -  OFFICE", size=18.0, color="Amber", glow=2.0))
    # cover on the deck for the boss (crates by the rail)
    it += [prop("Crate_Wood", 36.0, -16.0, MEZ_Z, 0.0), prop("PalletStack", 38.6, -16.0, MEZ_Z, 0.0)]

    # --- lighting inside: the hard key through the east roof gap, four hanging work lamps (unshadowed), neon
    it.append(L.light("spot", 37.6, -1.6, roof_z + 2.6, pitch=-70.0, yaw=200.0, color=(0.6, 0.82, 1.0), cd=900.0,
                      radius=26.0, cone=(10, 18), shadows=True, vol=4.0, src=4.0))
    for (x, y) in ((27.0, -15.0), (27.0, 1.0), (33.0, -6.0), (35.0, 2.0)):
        it += [L.box(x, y, 6.2, 0.5, 0.5, 0.25, "PaintedSteel", tint="Black", coll=False, name="WorkLamp"),
               L.box(x, y, 6.06, 0.42, 0.42, 0.02, "Emissive:Sodium", glow=18.0, coll=False, cast=False, name="WorkLampLens"),
               L.light("point", x, y, 5.9, color="Sodium", cd=8.0, radius=9.0, shadows=False, src=20.0)]
    it += [L.text(x0 - 0.12, -14.0, 6.6, 180.0, "SHED  7", size=70.0, color="Cyan", glow=5.0),
           L.box(x0 - 0.1, -8.0, WH_H - 0.25, 0.06, 27.6, 0.06, "Emissive:Teal", glow=10.0, coll=False, cast=False,
                 name="NeonEaves"),
           L.text(x1 + 0.12, -8.0, 6.6, 0.0, "ORSAVIK  -  BERTH 7", size=46.0, color="Red", glow=4.0)]
    return it


def _stair_west(L, x_top, y):
    """Straight stair from the floor up to the mezzanine edge at x = x_top, climbing east (+x) toward it."""
    rise, run = 0.2, 0.28
    n = int(round(MEZ_Z / rise))
    x_start = x_top - n * run
    out = L.stairs(x_start, y, 0.0, MEZ_Z, "+x", 1.4, "PaintedSteel", rise=MEZ_Z / n, run=run, tint="Gunmetal")
    out.append(L.slab(x_start, y - 0.76, x_top, y - 0.7, 0.9, MEZ_Z + 1.0, "PaintedSteel", tint="Black", name="StairRail",
                      coll=False))
    return out


# =============================================================================================
# Ship alongside (out of bounds): hull, deck boxes, accommodation block with lit windows
# =============================================================================================
def _ship(L, rng):
    it = []
    hx0, hx1 = 52.0, 66.0
    ya, yb = -96.0, 64.0
    it += [L.slab(hx0, ya + 8.0, hx1, yb, -2.0, 1.2, "PaintedSteel", tint="DeepRed", name="HullLow", cast=False),
           L.slab(hx0, ya + 8.0, hx1, yb, 1.2, 9.0, "PaintedSteel", tint="Black", name="HullTop"),
           L.slab(hx0 + 1.5, ya, hx1 - 1.5, ya + 8.0, -2.0, 9.4, "PaintedSteel", tint="Black", name="Bow"),
           L.slab(hx0 - 0.05, ya + 8.0, hx0, yb, 8.8, 9.0, "PaintedSteel", tint="White", name="Sheer", coll=False)]
    it.append(L.text(hx0 - 0.08, -60.0, 6.2, 180.0, "NORDHAVN TIDE", size=120.0, color="White", glow=0.5))
    # deck cargo: rows of 40 ft boxes along the ship, 2-4 high
    k = 0
    for row_x in (54.4, 57.0, 59.6, 62.2):
        for y in (-80.0, -67.0, -54.0, -41.0, -28.0, -15.0, -2.0, 11.0, 24.0):
            h = 2 + (k * 7 + int(row_x)) % 3
            for lvl in range(h):
                it.append(L.prop("Harbor_Container40", row_x, y, 9.0 + lvl * C40_H, 90.0,
                                 tint=CONTAINER_TINTS[(k + lvl * 3) % 12], nocoll=True))
            k += 1
    # accommodation block at the stern with lit window rows and a bridge
    it += [L.slab(53.0, 38.0, 65.0, 50.0, 9.0, 24.0, "PaintedSteel", tint="White", name="Accommodation"),
           L.slab(51.0, 40.0, 67.0, 44.0, 24.0, 27.0, "PaintedSteel", tint="White", name="Bridge"),
           L.slab(57.6, 46.0, 60.4, 49.0, 27.0, 33.0, "PaintedSteel", tint="Black", name="Funnel"),
           L.slab(57.8, 46.2, 60.2, 48.8, 31.0, 32.0, "PaintedSteel", tint="DeepRed", name="FunnelBand")]
    for z in (11.0, 14.0, 17.0, 20.0):
        for y in range(39, 50, 2):
            if rng.random() < 0.55:
                it.append(L.slab(52.94, y, 53.0, y + 1.0, z, z + 1.0, "Emissive:Warm", glow=rng.uniform(1.5, 3.0), coll=False,
                                 cast=False, name="Porthole"))
    it.append(L.slab(50.94, 40.4, 51.0, 43.6, 25.0, 26.4, "Emissive:Cool", glow=2.5, coll=False, cast=False, name="BridgeGlass"))
    for (x, y, z, c) in ((52.0, 63.0, 9.6, "Red"), (59.0, 48.0, 33.4, "Red"), (59.0, -94.0, 10.0, "White")):
        it.append(L.box(x, y, z, 0.35, 0.35, 0.35, "Emissive:" + c, glow=30.0, coll=False, cast=False, name="NavLight"))
    return it


def _skyline(L, rng):
    """Distant city to the west and north: dark towers with sparse lit window runs; harbour lights east."""
    it = []
    cols = ["Warm", "Warm", "Cool", "Amber", "Sodium", "Cool"]
    for k in range(22):
        a = math.radians(rng.uniform(100.0, 260.0))
        r = rng.uniform(95.0, 170.0)
        x, y = math.cos(a) * r, math.sin(a) * r
        sx, sy, h = rng.uniform(14.0, 28.0), rng.uniform(12.0, 24.0), rng.uniform(22.0, 80.0)
        it.append(L.slab(x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2, 0.0, h, "BrickDark" if rng.random() < 0.6 else "Concrete",
                         name="Tower", cast=False, coll=False))
        fx = x + sx / 2 + 0.05
        for b in range(int(h / 3.4)):
            if rng.random() < 0.6:
                continue
            zb = 3.0 + b * 3.4
            w = rng.uniform(2.0, max(2.5, 0.4 * sy))
            a0 = rng.uniform(-sy / 2 + 0.5, sy / 2 - 0.5 - w)
            it.append(L.slab(fx - 0.05, y + a0, fx + 0.05, y + a0 + w, zb, zb + 1.3, "Emissive:" + rng.choice(cols),
                             glow=rng.uniform(0.8, 2.4), coll=False, cast=False, name="Windows"))
        if h > 60.0:
            it.append(L.slab(x - 0.4, y - 0.4, x + 0.4, y + 0.4, h, h + 0.6, "Emissive:Red", glow=25.0, coll=False, cast=False,
                             name="AviationLight"))
    # far shore lights across the harbour (east)
    for k in range(40):
        x = rng.uniform(170.0, 240.0)
        y = rng.uniform(-200.0, 200.0)
        it.append(L.box(x, y, rng.uniform(1.0, 6.0), 0.6, 2.0, 0.6, "Emissive:" + rng.choice(["Sodium", "Warm", "Cool"]),
                        glow=rng.uniform(8.0, 20.0), coll=False, cast=False, name="FarShore"))
    return it
