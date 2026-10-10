"""Andrew's Airsoft - L_NightjarGarage: a three-storey concrete parking garage at night in the rain.

Plain layout data (no `unreal` import), registered in layouts.py as "NightjarGarage" and loaded lazily by
layouts._garage(), which passes the layouts module in: build(L) -> item list, MAP -> map metadata.
Units and axes as layouts.py: metres, +X east, +Y south on the plans, yaw turns +X toward +Y.

Storeys (floor heights in LEVELS): Street 0.0 (entrance with cashier booth and barrier arms; Blue spawns on
the covered street forecourt west of the facade), Mid 3.3, open Roof deck 6.6 (Red spawns in the roof-level
lobby of the east stair tower). Two straight car ramps side by side in the central strip: R1 Street->Mid and
R2 Mid->Roof, both rising east. Two stair cores (Blue NW on the street, Red SE in the tower) and an elevator
lobby on the east wall. Lanes: north aisle, ramp strip, south aisle on every storey, flanked vertically by the
stairs. Objectives: A Street (repair works beside R1), B Mid (the median between the ramps, overlooking
both), C Roof (resurfacing works). Connectivity is symmetric under (x, y, storey) -> (-x, -y, 4 - storey):
Blue's street <-> Red's lobby, R1 <-> R2, A <-> C.
Everything is original: no real brand names, logos or signage.
"""

import math
import random

LEVELS = (("Street", 0.0), ("Mid", 3.3), ("Roof", 6.6))
Z1, Z2, Z3 = 0.0, 3.3, 6.6
SLAB = 0.30            # structural slab (its underside is the ceiling of the storey below)
WEAR = 0.05            # wearing course on top of every deck
PARKED = ["Body", "Glass"]     # parked vehicles: lights off (skip the Emissive head/tail-light piece)
GX, GY = 30.0, 23.0    # garage deck half extents (x, y)
T = 0.25               # wall thickness
RAMP_X = 11.0          # ramps run x = -11 .. +11
R1_Y, R2_Y = -3.5, 3.5
RAMP_HW = 2.25         # Garage_Ramp half width including its upstand walls
COL_X = (-22.5, -15.0, -7.5, 0.0, 7.5, 15.0, 22.5)
COL_Y = (-17.3, -6.3, 6.3, 17.3)
X0, X1, Y0, Y1 = -36.0, 36.0, -23.0, 23.0

MAP = {
    "name": "NightjarGarage", "path": "/Game/Maps/L_NightjarGarage", "kind": "match",
    "bounds": (X0, Y0, X1, Y1), "lighting": "nightjar_rain", "game_mode": "AirsoftGameMode",
    "kill_z": -10.0, "levels": LEVELS,
    # bots: NavMeshBoundsVolume (m) from under the street to above the roof deck (roof 6.6 + standing room);
    # the lobby / stair-tower roofs (9.9) stay outside it
    "nav": (X0 - 1.0, Y0 - 1.0, -1.0, X1 + 1.0, Y1 + 1.0, 9.2),
}


def _sub_rects(rect, holes):
    """Axis-aligned rect minus holes (each fully inside or overlapping) -> list of rects."""
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


def build(L=None):
    if L is None:                       # editor package import (layouts passes itself in normally)
        from . import layouts as L
    it = []
    rng = random.Random(4417)
    prop, box, slab, patch, blocker = L.prop, L.box, L.slab, L.patch, L.blocker

    # =========================================================================================
    # Ground: garage floor, street forecourt, the street and neighbours beyond the bounds
    # =========================================================================================
    it += [slab(-GX, -GY, GX, GY, -0.3, 0.0, "ConcreteGarage", name="Floor_Street"),
           slab(-36.0, -15.0, -GX, GY, -0.3, 0.0, "ConcreteFloor", name="Forecourt", tint="Grey"),
           slab(-36.0, -6.0, -GX, 6.0, -0.3, 0.004, "AsphaltWet", name="Forecourt_Lanes"),
           slab(-70.0, -60.0, -36.0, 60.0, -0.45, -0.15, "AsphaltWet", name="Street", tile=3.0),
           slab(-36.4, -60.0, -36.0, 60.0, -0.45, 0.0, "Concrete", name="Kerb"),
           slab(-90.0, -60.0, -70.0, 60.0, -0.3, 0.0, "ConcreteFloor", name="Sidewalk_Far", tint="Grey")]
    # neighbours north / south of the deck (seen through the open sides) and across the street
    it += [slab(-36.0, -40.0, 40.0, -24.2, 0.0, 10.5, "BrickDark", name="Neighbour_N"),
           slab(-36.0, 24.2, 40.0, 40.0, 0.0, 9.0, "BrickDark", name="Neighbour_S"),
           slab(-36.0, -24.2, 40.0, -23.0, -0.3, 0.0, "Asphalt", name="Alley_N"),
           slab(-36.0, 23.0, 40.0, 24.2, -0.3, 0.0, "Asphalt", name="Alley_S"),
           slab(36.0, -24.2, 60.0, 24.2, 0.0, 9.6, "Brick", name="Neighbour_E")]
    for k, (x, y, sx, sy, h) in enumerate(((-82, -38, 18, 26, 26), (-80, -6, 14, 28, 34), (-84, 24, 20, 26, 22))):
        it.append(slab(x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2, 0.0, h, "BrickDark", name="AcrossStreet"))
    it += _skyline(L, random.Random(5150))      # own stream: skyline tweaks never reshuffle the parked cars

    # =========================================================================================
    # Decks: Mid (hole for R1) and Roof (hole for R2); structural slab + wearing course
    # =========================================================================================
    r1_hole = (-RAMP_X, R1_Y - RAMP_HW, RAMP_X, R1_Y + RAMP_HW)
    r2_hole = (-RAMP_X, R2_Y - RAMP_HW, RAMP_X, R2_Y + RAMP_HW)
    for (z, hole, top, nm) in ((Z2, r1_hole, "ConcreteGarage", "Deck_Mid"), (Z3, r2_hole, "ConcreteGarageWet", "Deck_Roof")):
        for (x0, y0, x1, y1) in _sub_rects((-GX, -GY, GX, GY), [hole]):
            it += [slab(x0, y0, x1, y1, z - SLAB, z - WEAR, "Concrete", name=nm + "_Slab"),
                   slab(x0, y0, x1, y1, z - WEAR, z, top, name=nm)]
    # downstand beams (0.45 m) under both decks on the column lines, cut at the ramp holes
    for (z, hole) in ((Z2, r1_hole), (Z3, r2_hole)):
        for x in COL_X:
            for (ya, yb) in ((-GY, hole[1]), (hole[3], GY)) if hole[0] < x < hole[2] else ((-GY, GY),):
                it.append(slab(x - 0.2, ya, x + 0.2, yb, z - SLAB - 0.45, z - SLAB, "Concrete", name="Beam"))

    # ramps (Garage_Ramp: 22 m run, 3.3 m rise, rising toward +X)
    it += [prop("Garage_Ramp", 0.0, R1_Y, Z1, 0.0), prop("Garage_Ramp", 0.0, R2_Y, Z2, 0.0)]
    # guard rails around the ramp holes (on the deck above each ramp) + drains at the ramp feet
    for (z, yc) in ((Z2, R1_Y), (Z3, R2_Y)):
        y_n, y_s = yc - RAMP_HW - 0.12, yc + RAMP_HW + 0.12
        for x in (-9.4, -6.4, -3.4, -0.4, 2.6, 5.6):
            it += [prop("Garage_Railing_3m", x, y_n, z, 90), prop("Garage_Railing_3m", x, y_s, z, 90)]
        it += [prop("Garage_Railing_3m", -RAMP_X - 0.12, yc - 0.75, z, 0), prop("Garage_Railing_3m", -RAMP_X - 0.12, yc + 0.75, z, 0)]
    for (z, yc) in ((Z1, R1_Y), (Z2, R2_Y)):
        it.append(prop("Garage_Drain", -RAMP_X - 0.5, yc, z, 90, scale=(1.0, 1.0, 1.0)))
        it.append(prop("Garage_Drain", -RAMP_X - 0.5, yc + 1.5 if yc < 0 else yc - 1.5, z, 90))

    # =========================================================================================
    # Columns, level bands and painted bay codes (Street = teal, Mid = orange)
    # =========================================================================================
    for li, (z, tint) in enumerate(((Z1, "Teal"), (Z2, "Orange"))):
        for xi, x in enumerate(COL_X):
            for yi, y in enumerate(COL_Y):
                it.append(prop("Garage_Pillar", x, y, z, 0.0, tint=tint))
                face = 1.0 if y in (-17.3, 6.3) else -1.0          # the face toward the drive aisle
                code = "P%d  %s%d" % (li + 1, "ABCD"[yi], xi + 1)
                it.append(L.text(x, y + face * 0.305, z + 1.9, 90.0 if face > 0 else -90.0, code, size=20.0,
                                 color="White", glow=1.4))
    # canopy columns on the street
    for y in (-12.0, -4.0, 4.0, 12.0, 20.0):
        it.append(prop("Garage_Pillar", -35.55, y, Z1, 0.0, tint="Teal"))

    # =========================================================================================
    # Perimeter: open-sided parapets (north / south), solid facade (west), tower wall (east)
    # =========================================================================================
    for (z, zt) in ((Z1, Z2 - SLAB), (Z2, Z3 - SLAB)):
        for ys, yb in ((-GY, -GY + T), (GY - T, GY)):
            it.append(slab(-GX, ys, GX, yb, z, z + 1.1, "Concrete", name="Parapet"))
            it.append(slab(-GX, ys - 0.02, GX, yb + 0.02, z + 1.1, z + 1.16, "PaintedSteel", tint="Gunmetal", name="ParapetCap"))
            it.append(blocker(-GX, ys - 0.4 if ys < 0 else ys, GX, yb if ys < 0 else yb + 0.4, z + 1.1, zt))
    it += [slab(-GX, -GY, GX, -GY + T, Z3, Z3 + 1.1, "Concrete", name="Parapet_Roof"),
           slab(-GX, GY - T, GX, GY, Z3, Z3 + 1.1, "Concrete", name="Parapet_Roof"),
           slab(GX - T, -GY, GX, 2.0, Z3, Z3 + 1.1, "Concrete", name="Parapet_Roof"),
           slab(-GX, -15.0, -GX + T, GY, Z3, Z3 + 1.1, "Concrete", name="Parapet_Roof")]
    it += [blocker(-GX - 0.6, -GY - 0.6, GX + 0.6, -GY + T, Z3 + 1.1, 14.0),
           blocker(-GX - 0.6, GY - T, GX + 0.6, GY + 0.6, Z3 + 1.1, 14.0),
           blocker(GX - T, -GY - 0.6, GX + 0.6, 2.0, Z3 + 1.1, 14.0),
           blocker(-GX - 0.6, -15.0, -GX + T, GY + 0.6, Z3 + 1.1, 14.0)]
    # west facade: street entrance (10 m) + pedestrian door on the Street storey, solid on the Mid storey
    it += L.wall_run("y", -GX + T / 2, -15.0, GY, Z1, Z2 - SLAB, T, "Concrete", openings=[(-5.0, 5.0, 2.6), (17.0, 18.4, 2.2)],
                     name="Facade_W")
    it += L.wall_run("y", -GX + T / 2, -15.0, GY, Z2, Z3 - SLAB, T, "Concrete", name="Facade_W2")
    # east wall: elevator landings on both storeys (tower annex behind)
    for z in (Z1, Z2):
        it += L.wall_run("y", GX - T / 2, -GY, 15.0, z, z + 3.0, T, "Concrete", openings=[(7.5, 10.5, 3.0)], name="Wall_E")
        it.append(prop("Garage_ElevatorDoors", GX - 0.15, 9.0, z, 180.0))
        it.append(L.text(GX - 0.32, 9.0, z + 2.62, 180.0, "LEVEL %d" % (1 if z < 1 else 2), size=16.0, color="Amber", glow=2.0))
    # annex below the roof lobby (plant rooms, not playable) and the elevator shaft
    it += [slab(GX, 2.0, 36.0, 15.0, Z1, Z3 - SLAB, "Concrete", name="Annex"),
           blocker(GX, -GY, 36.6, 2.0, 0.0, 14.0)]

    # =========================================================================================
    # Stair cores: Blue NW (street) and Red SE (tower); the Red one is the Blue one turned 180 deg
    # =========================================================================================
    blue = _stair_core(L, -33.0, -19.0, +1, doors={"street_L1": True})
    red = _stair_core(L, 33.0, 19.0, -1, doors={"lobby_L3": True})
    it += blue + red

    # =========================================================================================
    # Street forecourt: canopy, Blue spawn, entrance island with cashier booth and barrier arms
    # =========================================================================================
    it += [slab(-36.0, -15.0, -GX, GY, Z2 - SLAB, Z2 - 0.1, "Concrete", name="Canopy"),
           slab(-36.0, -15.0, -GX, GY, Z2 - 0.1, Z2, "PaintedSteel", tint="Gunmetal", name="CanopyTop"),
           slab(-36.1, -15.0, -36.0, GY, Z2 - 0.65, Z2, "PaintedSteel", tint="Black", name="CanopyFascia"),
           blocker(-36.6, -15.0, -GX, GY + 0.6, Z2, 14.0),
           blocker(-36.6, -GY - 0.6, -36.0, GY + 0.6, 0.0, 14.0),
           slab(-36.0, GY - 0.4, -GX, GY, 0.0, 8.0, "BrickDark", name="ForecourtEnd")]
    it += [slab(-36.08, -14.8, -36.0, -6.2, Z2 - 0.62, Z2 - 0.58, "Emissive:Sodium", glow=8.0, coll=False, name="CanopyLED"),
           slab(-36.08, 6.2, -36.0, 22.6, Z2 - 0.62, Z2 - 0.58, "Emissive:Sodium", glow=8.0, coll=False, name="CanopyLED")]
    for y in (-11.0, -1.0, 9.0, 17.0):
        it.append(prop("Garage_LightSodium", -GX - 0.02, y, 2.25, 180.0, light={"cd": 9.0, "radius": 10.0}))
    # Blue starts: north forecourt between the Blue stair door and the entrance, behind the facade
    for x in (-34.6, -33.0, -31.4):
        for y in (-13.8, -11.9, -10.0, -8.1):
            it.append(L.start(x, y, "Blue", 30.0))
    # pedestrian screen across the forecourt south of the spawn: a dog-leg, no straight sight line through it
    it += [slab(-36.0, -6.75, -31.8, -6.45, Z1, 2.4, "Concrete", name="Screen"),
           slab(-32.6, -4.55, -GX, -4.25, Z1, 2.4, "Concrete", name="Screen"),
           slab(-36.0, -6.8, -31.75, -6.4, 2.4, 2.48, "PaintedSteel", tint="Gunmetal", name="ScreenCap"),
           slab(-32.65, -4.6, -GX, -4.2, 2.4, 2.48, "PaintedSteel", tint="Gunmetal", name="ScreenCap"),
           L.text(-34.0, -6.43, 1.75, 90.0, "PARKING  -  ENTRANCE", size=26.0, color="White", glow=1.6),
           slab(-35.6, -6.46, -32.2, -6.43, 1.45, 1.49, "Emissive:Sodium", glow=10.0, coll=False, name="ScreenLED")]
    # street dressing: bollards on the kerb line, planters screening the entrance edges, a news kiosk, bins
    for y in (-14.0, -7.0, 7.0, 15.0, 21.0):
        it.append(prop("Bollard", -35.75, y, Z1, 0.0))
    it += [prop("Planter_Concrete", -31.0, -6.2, Z1, 0.0), prop("Planter_Concrete", -31.0, 6.2, Z1, 0.0),
           prop("Kiosk", -34.6, 4.6, Z1, 0.0), prop("Dumpster", -34.9, -2.6, Z1, 90.0, tint="Green"),
           prop("TrashBags", -34.6, -4.6, Z1, 20.0), prop("Garage_PayMachine", -31.0, 15.2, Z1, 0.0),
           prop("Garage_Cone", -31.4, -4.0, Z1, 10.0), prop("Garage_Cone", -31.6, 4.2, Z1, 40.0)]
    # entrance island (15 cm kerb) with the booth, barrier arms, ticket station, clearance bars
    it += [slab(-29.7, -0.85, -24.6, 0.85, 0.0, 0.15, "Concrete", name="Island"),
           slab(-29.7, -0.88, -24.6, -0.85, 0.0, 0.16, "PaintLineYellow", name="IslandEdge"),
           slab(-29.7, 0.85, -24.6, 0.88, 0.0, 0.16, "PaintLineYellow", name="IslandEdge"),
           prop("Garage_TicketBooth", -27.3, 0.0, 0.15, 0.0, light=True),
           prop("Garage_BarrierArm", -25.2, -0.6, 0.15, 180.0),
           prop("Garage_BarrierArm", -29.35, 0.6, 0.15, 0.0),
           prop("Garage_PayMachine", -24.85, 0.25, 0.15, 0.0)]
    for y in (-2.6, 2.6):
        it.append(prop("Garage_HeightBar", -28.6, y, Z2 - SLAB - 0.732, 0.0, hang=Z2 - SLAB))
    for y in (-4.6, -1.4, 1.4, 4.6):
        it.append(patch(-29.9, y - 0.06, -14.0, y + 0.06, 0.006, "PaintLineWhite", name="LaneLine"))
    for x in (-23.0, -17.0):
        it += _arrow(L, x, -2.9, 0.007, 0.0) + _arrow(L, x + 3.0, 2.9, 0.007, 180.0)

    # =========================================================================================
    # Parking rows: stall lines, wheel stops and parked cars on all three decks
    # =========================================================================================
    paints = ["Black", "Gunmetal", "DeepRed", "White", "Black", "Gunmetal"]
    rows = [(-20.15, 90.0, "N"), (-9.15, -90.0, "N"), (9.15, 90.0, "S"), (20.15, -90.0, "S")]
    rowy = {-20.15: (-22.75, -17.6), -9.15: (-11.6, -6.6), 9.15: (6.6, 11.6), 20.15: (17.6, 22.75)}
    occupied = _parking_plan()
    for (z, lvl) in ((Z1, 0), (Z2, 1), (Z3, 2)):
        for (yc, yaw, side) in rows:
            ya, yb = rowy[yc]
            for c in (-30.0,) + COL_X:
                for k in range(4):
                    xl = c + 0.3 + 2.3 * k
                    if -GX + 0.3 < xl < GX - 0.3 and _stall_ok(lvl, xl, yc):
                        it.append(patch(xl - 0.05, ya + (0.4 if ya < 0 else 0.0), xl + 0.05, yb - (0.0 if ya < 0 else 0.4),
                                        z + 0.006, "PaintLineWhite", name="Stall"))
                for k in range(3):
                    xc = c + 1.45 + 2.3 * k
                    if not (-GX + 1.4 < xc < GX - 1.4) or not _stall_ok(lvl, xc, yc):
                        continue
                    key = (lvl, round(xc, 2), yc)
                    head = yb - 0.55 if yaw > 0 else ya + 0.55          # wheel stop at the head of the stall
                    if key in occupied:
                        aid = occupied[key]
                        flip = 180.0 if rng.random() < 0.3 else 0.0
                        it.append(prop(aid, xc + rng.uniform(-0.12, 0.12), yc + rng.uniform(-0.15, 0.1), z,
                                       yaw + flip + rng.uniform(-3.0, 3.0), tint=rng.choice(paints), pieces=PARKED))
                    if rng.random() < 0.8:
                        it.append(prop("Garage_WheelStop", xc, head, z, 0.0))

    # =========================================================================================
    # Street storey (A: repair works beside R1; entrance cross-aisle; elevator lobby east)
    # =========================================================================================
    it += _street_level(L, rng)
    it += _mid_level(L, rng)
    it += _roof_level(L, rng)
    it += _lighting(L)

    # objectives (A <-> C mirror; B on the Mid median between the ramps). Capture is a cylinder around the
    # actor tested on the pawn's capsule centre (feet + 0.92 m standing, + 0.58 crouched); the default 2.5 m
    # half height would let a player on the deck below (centre 2.38 m under the point) capture it through
    # the slab, so 1.8 m: own deck incl. jumps counts, the decks above and below do not.
    hh = 1.8
    it += [L.objective("A", -4.0, 2.6, Z1, radius=5.0, half_height=hh),
           L.objective("B", 0.0, 0.1, Z2, radius=4.5, half_height=hh),
           L.objective("C", 4.0, -2.6, Z3, radius=5.0, half_height=hh)]

    # atmosphere, reflections, sound
    it += [L.fogvol(-2.0, 0.0, 1.5, 30.0, 22.0, 1.7, density=0.22, color=(0.55, 0.6, 0.7)),
           L.fogvol(0.0, 0.0, 4.8, 30.0, 22.0, 1.7, density=0.22, color=(0.6, 0.58, 0.62)),
           L.fogvol(0.0, 0.0, 8.0, 34.0, 26.0, 2.6, density=0.42, color=(0.5, 0.55, 0.65)),
           L.fogvol(-33.0, 4.0, 1.6, 4.0, 18.0, 1.8, density=0.3, color=(0.7, 0.55, 0.4))]
    for z in (1.6, 4.9):
        it += [L.capture(-18.0, 0.0, z, 16.0), L.capture(0.0, 0.0, z, 16.0), L.capture(18.0, 0.0, z, 16.0),
               L.capture(0.0, -15.0, z, 14.0), L.capture(0.0, 15.0, z, 14.0)]
    it += [L.capture(-15.0, 0.0, 8.4, 22.0), L.capture(15.0, 0.0, 8.4, 22.0), L.capture(-33.0, 0.0, 1.6, 12.0),
           L.capture(33.0, 8.5, 8.0, 7.0)]
    it += [L.sound("AmbienceGarage", -15.0, -8.0, 1.8, spatial=True, radius=22.0, falloff=14.0, volume=0.9),
           L.sound("AmbienceGarage", 15.0, 8.0, 1.8, spatial=True, radius=22.0, falloff=14.0, volume=0.9),
           L.sound("AmbienceGarage", 0.0, 0.0, 5.0, spatial=True, radius=24.0, falloff=12.0, volume=0.8),
           L.sound("AmbienceGarageRoof", -12.0, 0.0, 8.5, spatial=True, radius=20.0, falloff=16.0, volume=1.0),
           L.sound("AmbienceGarageRoof", 14.0, 0.0, 8.5, spatial=True, radius=20.0, falloff=16.0, volume=1.0),
           L.sound("AmbienceGarageRoof", -33.0, 4.0, 2.0, spatial=True, radius=8.0, falloff=14.0, volume=0.7)]
    return it


# =============================================================================================
# Parking plan: which stalls hold a car (deterministic, kept clear of objectives and lanes)
# =============================================================================================
def _stall_ok(lvl, x, yc):
    """Stalls that exist: not in front of the entrance, the stair cores, the elevator lobby or the lobby doors."""
    if lvl == 0 and yc in (-9.15, 9.15) and x < -24.5:
        return False                  # entrance approach
    if lvl == 0 and yc in (9.15, 20.15) and x > 24.5:
        return False                  # elevator lobby / Red core door (street)
    if lvl == 1 and yc in (9.15, 20.15) and x > 24.5:
        return False                  # elevator landing / Red core door (mid)
    if lvl == 1 and yc == -20.15 and x < -24.5:
        return False                  # Blue core door (mid)
    if lvl == 2 and yc == -20.15 and x < -22.0:
        return False                  # Blue core door (roof)
    if lvl == 2 and yc == 20.15 and x > 22.0:
        return False                  # Red core door (roof)
    if lvl == 2 and yc in (-9.15, 9.15) and x > 24.5:
        return False                  # lobby doors (mirror of the street entrance approach)
    return True


def _parking_plan():
    """Occupied stalls, point-symmetric under (x, y, storey) -> (-x, -y, 4 - storey) so neither team's
    half gets luckier gaps through the rows; the objective zones stay clear."""
    rng = random.Random(77)
    out = {}
    for lvl in (0, 1, 2):
        for yc in (-20.15, -9.15, 9.15, 20.15):
            for c in (-30.0,) + COL_X:
                for k in range(3):
                    xc = round(c + 1.45 + 2.3 * k, 2)
                    if lvl == 2 or (lvl == 1 and (xc > 0 or (xc == 0 and yc > 0))):
                        continue                      # filled by the mirror below
                    if lvl == 0 and yc == 9.15 and -12.0 < xc < 4.0:
                        continue                      # A works
                    if rng.random() < (0.5 if lvl == 0 else 0.45):
                        aid = rng.choice(["Car_Sedan", "Car_Coupe", "Car_Sedan"])
                        out[(lvl, xc, yc)] = aid
                        out[(2 - lvl, round(-xc, 2), -yc)] = rng.choice(["Car_Sedan", "Car_Coupe"])
    return out


def _arrow(L, x, y, z, yaw, length=2.4):
    """Painted direction arrow (shaft + two head bars) lying on the floor, pointing along yaw."""
    a = math.radians(yaw)
    tip = (x + math.cos(a) * length / 2, y + math.sin(a) * length / 2)
    out = [L.box(x, y, z, length, 0.16, 0.012, "PaintLineWhite", yaw=yaw, coll=False, cast=False, name="Arrow")]
    for sgn in (-1.0, 1.0):
        b = math.radians(yaw + sgn * 35.0)
        out.append(L.box(tip[0] - math.cos(b) * 0.42, tip[1] - math.sin(b) * 0.42, z, 0.9, 0.16, 0.012, "PaintLineWhite",
                         yaw=yaw + sgn * 35.0, coll=False, cast=False, name="Arrow"))
    return out


# =============================================================================================
# Stair core (6 x 8 m): two straight flights per storey pair, landings, doors; s = +1 Blue, -1 Red
# =============================================================================================
def _stair_core(L, cx, cy, s, doors):
    it = []
    W = lambda lx, ly: (cx + s * lx, cy + s * ly)          # local -> world (Red = Blue turned 180 deg)

    def rect(lx0, ly0, lx1, ly1, z0, z1, mat, **kw):
        ax, ay = W(lx0, ly0)
        bx, by = W(lx1, ly1)
        return L.slab(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), z0, z1, mat, **kw)

    rise_n = 16
    run = 4.48
    # flights: A = Street->Mid (west half), B = Mid->Roof (east half), each 2.6 m wide
    flights = (((-2.75, -0.15), 2.23, -2.25, Z1, Z2), ((0.15, 2.75), -2.25, 2.23, Z2, Z3))
    for (xa, xb), ylo, yhi, zlo, zhi in flights:
        dy = (yhi - ylo) / rise_n
        dz = (zhi - zlo) / rise_n
        for k in range(1, rise_n):
            y0_, y1_ = ylo + (k - 1) * dy, ylo + k * dy
            top = zlo + k * dz
            it.append(rect(xa, min(y0_, y1_), xb, max(y0_, y1_), top - 0.24, top, "Concrete", name="Step"))
        # sloped soffit under the flight (a pitched concrete slab under the nosing line)
        lx = (xa + xb) / 2
        mx, my = W(lx, (ylo + yhi) / 2)
        length = math.hypot(run, zhi - zlo)
        pitch = math.degrees(math.atan2(zhi - zlo, run))
        dir_y = s * (1.0 if yhi > ylo else -1.0)
        yaw = 90.0 if dir_y > 0 else -90.0
        it.append(L.box(mx, my, (zlo + zhi) / 2 - 0.42, length, abs(xb - xa), 0.14, "Concrete", yaw=yaw, pitch=pitch, name="Soffit"))
        # handrail on the open side (a pitched steel tube, 0.9 m above the nosing line)
        hxl = xb - 0.08 if xa < 0 else xa + 0.08
        hx_, hy_ = W(hxl, (ylo + yhi) / 2)
        it.append(L.box(hx_, hy_, (zlo + zhi) / 2 + 0.9, length, 0.05, 0.05, "PaintedSteel", tint="Black", yaw=yaw, pitch=pitch,
                        coll=False, name="Handrail"))
    # central wall between the flights (full height)
    it.append(rect(-0.15, -2.25, 0.15, 2.23, Z1, Z3 + 3.0, "Concrete", name="CoreSpine"))
    # landings: Mid at the north end (local -y), Roof over the street landing (local +y)
    it.append(rect(-2.75, -3.75, 2.75, -2.25, Z2 - 0.25, Z2, "Concrete", name="Landing"))
    it.append(rect(-2.75, 2.23, 2.75, 3.75, Z3 - 0.25, Z3, "Concrete", name="Landing"))
    it.append(rect(-3.0, -4.0, 3.0, 4.0, -0.3, 0.0, "ConcreteFloor", name="CoreFloor", tint="Grey"))
    # walls: outer (local x = -3), garage side (local x = +3), outer end (local y = -4), street / lobby end (local y = +4)
    def wall_y(lx, z0, z1, openings):
        wx, _ = W(lx, 0.0)
        a0, a1 = sorted((W(0, -4.0)[1], W(0, 4.0)[1]))
        ops = []
        for (b0, b1, top) in openings:
            ya, yb = sorted((W(0, b0)[1], W(0, b1)[1]))
            ops.append((ya, yb, top))
        return L.wall_run("y", wx, a0, a1, z0, z1, T, "Concrete", openings=ops, name="CoreWall")

    def wall_x(ly, z0, z1, openings):
        _, wy = W(0.0, ly)
        a0, a1 = sorted((W(-3.0, 0)[0], W(3.0, 0)[0]))
        ops = []
        for (b0, b1, top) in openings:
            xa_, xb_ = sorted((W(b0, 0)[0], W(b1, 0)[0]))
            ops.append((xa_, xb_, top))
        return L.wall_run("x", wy, a0, a1, z0, z1, T, "Concrete", openings=ops, name="CoreWall")
    for (z0, z1) in ((Z1, Z2), (Z2, Z3), (Z3, Z3 + 3.0)):
        it += wall_y(-3.0 + T / 2, z0, z1, [])
        it += wall_x(-4.0 + T / 2, z0, z1, [])
    it += wall_y(3.0 - T / 2, Z1, Z2, [(2.35, 3.6, 2.2)])            # garage door, Street
    it += wall_y(3.0 - T / 2, Z2, Z3, [(-3.6, -2.35, 2.2)])          # garage door, Mid
    it += wall_y(3.0 - T / 2, Z3, Z3 + 3.0, [(2.35, 3.6, 2.2)])      # roof door
    end_ops = {Z1: [(-2.6, -1.3, 2.2)] if doors.get("street_L1") else [],
               Z3: [(-2.6, -1.3, 2.2)] if doors.get("lobby_L3") else []}
    for (z0, z1) in ((Z1, Z2), (Z2, Z3), (Z3, Z3 + 3.0)):
        it += wall_x(4.0 - T / 2, z0, z1, end_ops.get(z0, []))
    it.append(rect(-3.0, -4.0, 3.0, 4.0, Z3 + 3.0, Z3 + 3.3, "Concrete", name="CoreRoof"))
    it.append(L.blocker(min(W(-3.2, -4.2)[0], W(3.2, 4.2)[0]), min(W(-3.2, -4.2)[1], W(3.2, 4.2)[1]),
                        max(W(-3.2, -4.2)[0], W(3.2, 4.2)[0]), max(W(-3.2, -4.2)[1], W(3.2, 4.2)[1]), Z3 + 3.3, 14.0))
    # light, exit signs, level codes on the landings (painted, reflective)
    for (lz, ly) in ((Z1, 3.0), (Z2, -3.0), (Z3, 3.0)):
        px, py = W(0.0, ly)
        it.append(L.light("point", px, py, lz + 2.5, color="Cool", cd=1.6, radius=6.0, shadows=False))
        ex, ey = W(2.6, ly)
        it.append(L.prop("Garage_ExitSign", ex, ey, lz + 2.35, 0.0 if s > 0 else 180.0, light={"cd": 0.4, "radius": 3.0}))
        tx, ty = W(-2.73, ly)
        it.append(L.text(tx, ty, lz + 1.7, 0.0 if s > 0 else 180.0, {Z1: "LEVEL 1", Z2: "LEVEL 2", Z3: "ROOF"}[lz],
                         size=30.0, color="White", glow=1.6))
    return it


# =============================================================================================
# Street storey
# =============================================================================================
def _street_level(L, rng):
    it = []
    prop = L.prop
    z = Z1
    # --- A: repair works beside R1 (central strip, south of the ramp, under the Mid deck) ---
    it += [prop("Garage_Scaffold", -5.6, -0.55, z, 0.0), prop("Garage_Scaffold", -2.6, -0.55, z, 0.0),
           prop("Garage_JerseyBarrier", -9.2, 4.7, z, 0.0), prop("Garage_JerseyBarrier", 1.6, 4.7, z, 0.0),
           prop("Garage_JerseyBarrier", -11.6, 1.9, z, 90.0),
           prop("Garage_BlockPallet", -7.6, 2.2, z, 5.0), prop("Garage_BlockPallet", -0.4, 1.6, z, -8.0),
           prop("Garage_BlockPallet", -0.4, 1.6, z + 1.08, -3.0),
           prop("Garage_MaintCage", 5.4, 2.8, z, 0.0),
           prop("PalletStack", -5.6, 3.9, z, 15.0), prop("Crate_Wood", -5.6, 3.9, z + 0.58, 22.0),
           prop("OilDrum", -9.9, 3.1, z, 0.0, tint="Blue"), prop("OilDrum", -9.4, 3.5, z, 30.0, tint="Blue"),
           prop("WreckedCar", 1.2, 9.2, z, 84.0)]
    for (x, y) in ((-10.4, 0.6), (-3.0, 4.2), (0.4, 4.2), (3.0, 0.4), (-12.4, -0.2)):
        it.append(prop("Garage_Cone", x, y, z, rng.uniform(0, 90)))
    it += [L.light("spot", -4.5, 2.8, 2.55, pitch=-70.0, yaw=-90.0, color="Warm", cd=7.0, radius=10.0, cone=(30, 55),
                   shadows=True, vol=1.2),
           L.box(-4.5, 2.8, 2.62, 0.35, 0.2, 0.1, "PaintedSteel", tint="Black", coll=False, name="WorkLamp"),
           L.box(-4.5, 2.8, 2.565, 0.3, 0.16, 0.012, "Emissive:Warm", glow=30.0, coll=False, name="WorkLampLens")]
    # --- entrance cross-aisle (west of R1): lane divider and a breakdown ---
    it += [prop("Garage_JerseyBarrier", -20.2, 0.05, z, 0.0), prop("Garage_JerseyBarrier", -14.4, 0.05, z, 0.0),
           prop("Car_Sedan", -19.0, 3.4, z, 172.0, tint="White", pieces=PARKED),
           prop("Garage_Cone", -21.4, 2.2, z, 0.0), prop("Garage_Cone", -16.8, 4.6, z, 30.0)]
    # --- north aisle chicane: plywood hoarding + barriers (closing half the lane) ---
    it += [prop("Barricade_Plywood_4m", -2.0, -15.4, z, 90.0), prop("Garage_JerseyBarrier", 2.2, -15.6, z, 0.0),
           prop("Garage_Cone", 4.4, -14.2, z, 0.0), prop("Garage_Cone", -4.6, -14.0, z, 0.0),
           prop("Barricade_Plywood_4m", 12.0, -12.8, z, -90.0), prop("Garage_BlockPallet", 9.6, -13.0, z, 10.0)]
    # --- south aisle chicane ---
    it += [prop("Garage_BlockPallet", 3.2, 15.9, z, 4.0), prop("Garage_BlockPallet", 3.2, 15.9, z + 1.08, -6.0),
           prop("Garage_BlockPallet", 4.5, 15.8, z, -3.0), prop("Barricade_Plywood_4m", -9.0, 12.8, z, -90.0),
           prop("Garage_JerseyBarrier", -13.5, 12.9, z, 0.0), prop("Dumpster", 17.6, 15.9, z, 0.0, tint="Blue"),
           prop("TrashBags", 19.2, 16.2, z, 0.0)]
    # --- east: elevator lobby (pay machines), behind R1's head ---
    it += [prop("Garage_PayMachine", 29.25, 5.4, z, 180.0), prop("Garage_PayMachine", 29.25, 12.6, z, 180.0),
           prop("Garage_JerseyBarrier", 26.4, 9.0, z, 90.0), prop("Car_Coupe", 18.0, -0.4, z, 96.0, tint="DeepRed", pieces=PARKED),
           prop("Garage_JerseyBarrier", 13.4, 1.9, z, 90.0), prop("Garage_Cone", 12.4, -0.2, z, 0.0)]
    # puddles only where rain blows in under the open sides: deep under the deck a mirror patch only shows the
    # dark soffit and reads as a black sheet
    for (x, y, sx, sy) in ((-22.0, -21.4, 2.6, 1.2), (8.0, 21.6, 3.0, 1.0), (24.0, -21.8, 2.0, 0.8)):
        it += _puddle(L, x, y, z, sx, sy)
    return it


# =============================================================================================
# Mid storey
# =============================================================================================
def _mid_level(L, rng):
    it = []
    prop = L.prop
    z = Z2
    # --- B: the median between the ramps (R1 drops away north, R2 climbs south) ---
    it += [prop("Garage_BlockPallet", -5.2, -0.51, z, 0.0), prop("Garage_BlockPallet", 5.2, 0.7, z, 180.0),
           prop("Garage_Cone", -8.4, -0.4, z, 0.0), prop("Garage_Cone", 8.6, 0.4, z, 0.0),
           prop("Garage_Cone", 0.2, -0.45, z, 20.0), prop("Garage_PayMachine", -1.6, 0.85, z, -90.0)]
    it += [prop("Garage_JerseyBarrier", -14.5, 0.0, z, 90.0), prop("Garage_JerseyBarrier", 14.5, 0.0, z, 90.0)]
    # --- north aisle: a fender-bender blocking a lane ---
    it += [prop("WreckedCar", -6.0, -14.2, z, 28.0), prop("Car_Coupe", -1.4, -13.2, z, -152.0, tint="White"),
           prop("Garage_Cone", 1.6, -15.6, z, 0.0), prop("Garage_Cone", -9.6, -12.6, z, 0.0),
           prop("Garage_JerseyBarrier", 9.4, -15.4, z, 0.0), prop("Barricade_Plywood_4m", 14.6, -12.8, z, -90.0)]
    # --- south aisle: repair zone with scaffold + hoarding ---
    it += [prop("Garage_Scaffold", 5.6, 16.4, z, 0.0), prop("Barricade_Plywood_4m", 2.4, 12.8, z, -90.0),
           prop("Garage_BlockPallet", 8.6, 15.6, z, 8.0), prop("Garage_BlockPallet", 8.6, 15.6, z + 1.08, 2.0),
           prop("Garage_JerseyBarrier", -8.0, 15.6, z, 0.0), prop("Garage_MaintCage", -16.8, 15.3, z, 0.0),
           prop("Garage_Cone", 3.4, 14.4, z, 0.0), prop("Garage_Cone", 0.6, 15.6, z, 50.0)]
    # --- cross aisles ---
    it += [prop("Garage_JerseyBarrier", -20.0, -2.8, z, 0.0), prop("Garage_JerseyBarrier", 20.0, 2.8, z, 0.0),
           prop("Car_Sedan", 20.2, -3.4, z, 8.0, tint="Gunmetal", pieces=PARKED),
           prop("Car_Sedan", -20.6, 3.6, z, 176.0, tint="Black", pieces=PARKED),
           prop("Garage_PayMachine", 29.25, 12.6, z, 180.0), prop("Dumpster", -29.0, 11.0, z, 0.0, tint="Green")]
    for (x, y, sx, sy) in ((-24.0, 21.6, 2.4, 0.9), (2.0, -21.5, 2.0, 1.0)):      # open sides only (see street)
        it += _puddle(L, x, y, z, sx, sy)
    return it


# =============================================================================================
# Roof deck
# =============================================================================================
def _roof_level(L, rng):
    it = []
    prop = L.prop
    z = Z3
    # --- Red lobby (roof level, east tower): walls, roof, vestibules, elevator, starts ---
    it += [L.slab(GX, 2.0, 36.0, 15.0, Z3 - 0.3, Z3, "ConcreteFloor", name="LobbyFloor", tint="Grey"),
           L.slab(GX, 2.0, 36.0, 15.0, Z3 + 3.0, Z3 + 3.3, "Concrete", name="LobbyRoof"),
           L.slab(36.0 - T, 2.0, 36.0, 15.0, Z3, Z3 + 3.0, "Concrete", name="LobbyWall"),
           L.slab(GX, 2.0, 36.0, 2.0 + T, Z3, Z3 + 3.0, "Concrete", name="LobbyWall"),
           L.blocker(GX - 0.2, 1.8, 36.6, 15.0, Z3 + 3.3, 14.0)]
    it += L.wall_run("y", GX + T / 2, 2.0, 15.0, Z3, Z3 + 3.0, T, "Concrete", openings=[(3.0, 4.4, 2.2), (12.4, 13.8, 2.2)],
                     name="LobbyWall_W")
    it += [L.slab(31.5, 2.25, 31.75, 6.4, Z3, Z3 + 2.4, "Concrete", name="Vestibule"),
           L.slab(31.5, 10.6, 31.75, 14.75, Z3, Z3 + 2.4, "Concrete", name="Vestibule"),
           L.slab(GX, 7.5, 32.5, 10.5, Z3, Z3 + 3.0, "Concrete", name="ElevatorShaft"),
           prop("Garage_ElevatorDoors", 32.65, 9.0, Z3, 0.0)]
    for x in (33.6, 35.1):
        for y in (3.4, 5.4, 7.4, 10.6, 12.6, 14.4):
            it.append(L.start(x, y, "Red", 180.0, z=Z3))
    it += [L.light("rect", 34.0, 8.5, Z3 + 2.95, pitch=-90.0, color="Cool", cd=3.0, radius=8.0, w=1.2, h=0.25, shadows=False),
           L.box(34.0, 8.5, Z3 + 2.97, 1.3, 0.3, 0.04, "Emissive:Cool", glow=12.0, coll=False, cast=False, name="LobbyPanel"),
           prop("Garage_ExitSign", 30.6, 3.7, Z3 + 2.35, 0.0, light={"cd": 0.4, "radius": 3.0}),
           prop("Garage_ExitSign", 30.6, 13.1, Z3 + 2.35, 0.0, light={"cd": 0.4, "radius": 3.0}),
           L.text(36.0 - T - 0.02, 8.5, Z3 + 1.9, 180.0, "ROOF  -  LEVEL 3", size=28.0, color="White", glow=1.5)]
    # --- C: resurfacing works on the roof deck (north central strip, above R1) ---
    it += [prop("Garage_JerseyBarrier", 9.4, -4.6, z, 0.0), prop("Garage_JerseyBarrier", -1.6, -4.6, z, 0.0),
           prop("Garage_JerseyBarrier", 11.6, -1.9, z, 90.0),
           prop("Garage_BlockPallet", 7.6, -2.2, z, -5.0), prop("Garage_BlockPallet", 0.4, -1.6, z, 8.0),
           prop("Garage_BlockPallet", 0.4, -1.6, z + 1.08, 3.0), prop("Garage_RoofHVAC", 4.4, -5.1, z, 0.0),
           prop("Garage_Scaffold", -4.6, -2.0, z, 0.0),
           prop("PalletStack", 4.0, -1.1, z, -15.0), prop("OilDrum", 9.9, -3.1, z, 0.0, tint="Red"),
           prop("OilDrum", 9.4, -3.5, z, 30.0, tint="Red")]
    for (x, y) in ((10.4, -0.6), (3.0, -4.2), (-0.4, -0.2), (-3.0, -0.4), (12.4, 0.2)):
        it.append(prop("Garage_Cone", x, y, z, rng.uniform(0, 90)))
    # --- hard cover across the roof: box trucks, plant, a stripped wreck ---
    it += [prop("BoxTruck", -10.0, -14.3, z, 0.0, tint="White", pieces=PARKED),
           prop("BoxTruck", 12.0, 14.3, z, 180.0, tint="Grey", pieces=PARKED),
           prop("Garage_RoofHVAC", 18.4, -14.6, z, 90.0), prop("Garage_RoofHVAC", -17.4, 14.8, z, 90.0),
           prop("Garage_RoofHVAC", -22.6, -2.6, z, 0.0), prop("Garage_RoofHVAC", 22.6, 2.6, z, 0.0),
           prop("WreckedCar", -2.0, 14.0, z, -8.0), prop("Garage_JerseyBarrier", 2.6, -14.0, z, 15.0),
           prop("Garage_JerseyBarrier", -3.0, 14.6, z, 0.0), prop("Garage_Scaffold", 24.0, -15.8, z, 90.0),
           prop("Garage_BlockPallet", -24.4, 16.0, z, 0.0), prop("Garage_MaintCage", 16.0, 3.4, z, 90.0)]
    # light poles (sodium) along the parapets and the ramp strip
    for (x, y, yaw) in ((-22.5, -22.3, 90.0), (0.0, -22.3, 90.0), (22.5, -22.3, 90.0), (-22.5, 22.3, -90.0),
                        (0.0, 22.3, -90.0), (15.0, 22.3, -90.0), (-26.0, 5.6, 0.0), (26.0, -5.6, 180.0)):
        it.append(prop("StreetLamp", x, y, z, yaw, light={"cd": 16.0, "radius": 18.0, "shadows": abs(x) < 1.0}))
    # puddles where a roof deck really ponds: aisle low spots under the lamps, the foot of the end walls and
    # in front of the Red lobby (point-mirrored pairs); the open middle of the deck stays clear
    for (x, y, sx, sy) in ((-20.0, 14.4, 2.6, 1.3), (20.0, -14.4, 2.6, 1.3), (-28.3, -8.0, 1.1, 2.6), (28.3, 8.0, 1.1, 2.6),
                           (4.6, 16.4, 2.0, 1.0), (-4.6, -16.4, 2.0, 1.0)):
        it += _puddle(L, x, y, z, sx, sy)
    return it


# =============================================================================================
# Ceiling fixtures and services (Street and Mid), ramp lights
# =============================================================================================
def _lighting(L):
    it = []

    def batten(x, y, soffit, yaw, light=None):
        # Garage_LightFluo hangs 0.5 m on its own rods (CeilingMount 0.65), clear of the downstand beams,
        # so whole rows read down an aisle
        return [L.prop("Garage_LightFluo", x, y, soffit - 0.65, yaw, hang=soffit, light=light)]

    for (z, soffit) in ((Z1, Z2 - SLAB), (Z2, Z3 - SLAB)):
        lit = 0
        for yrow in (-14.3, 14.3):
            for k, x in enumerate((-26.25, -18.75, -11.25, -3.75, 3.75, 11.25, 18.75, 26.25)):
                on = (k % 2 == (0 if yrow < 0 else 1))
                it += batten(x, yrow, soffit, 0.0, light=({"shadows": False} if on else None))
                lit += 1 if on else 0
        for yrow in (-9.2, 9.2):
            for x in (-18.75, -11.25, 11.25, 18.75, -3.75, 3.75):
                it += batten(x, yrow, soffit, 0.0)
        for x in (-18.75, 18.75):
            for y in (-3.0, 3.0):
                it += batten(x, y, soffit, 90.0, light=({"shadows": False} if y < 0 else None))
        # services: 6 m sprinkler / cable runs crossing the aisles between the beams (parallel to them)
        for yrow in (-14.3, 14.3):
            for c in COL_X[:-1]:
                it.append(L.prop("Garage_PipeRun", c + 1.8, yrow, soffit - 0.55, 90.0, hang=soffit))
        # exit signs over the stair and elevator doors
        it += [L.prop("Garage_ExitSign", -29.3, -16.0 if z < 1 else -22.0, soffit - 0.352, 0.0, hang=soffit,
                      light={"cd": 0.4, "radius": 3.0}),
               L.prop("Garage_ExitSign", 29.3, 16.0 if z < 1 else 22.0, soffit - 0.352, 0.0, hang=soffit,
                      light={"cd": 0.4, "radius": 3.0})]
    # sodium wallpacks on the columns lighting the ramps
    for (z, yc, ycol) in ((Z1, R1_Y, -6.3), (Z2, R2_Y, 6.3)):
        for x in (-7.5, 7.5):
            face = 90.0 if ycol < 0 else -90.0
            it.append(L.prop("Garage_LightSodium", x, ycol + (0.32 if ycol < 0 else -0.32), z + 2.3, face,
                             light={"cd": 10.0, "radius": 12.0, "shadows": x > 0}))
    return it


# =============================================================================================
# Skyline: distant towers with lit window bands (emissive), seen from the roof and the open sides
# =============================================================================================
def _puddle(L, x, y, z, sx, sy):
    """Standing water as three overlapping, differently turned flat boxes, so the outline reads as an
    irregular polygon instead of a crisp rectangle. Tops step 3 mm apart (no z-fighting where they overlap)."""
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


def _skyline(L, rng):
    it = []
    cols = ["Warm", "Warm", "Cool", "Amber", "Warm", "Cool", "Gold"]
    ring = []
    for k in range(26):
        a = k / 26.0 * 2 * math.pi + rng.uniform(-0.08, 0.08)
        r = rng.uniform(70.0, 150.0)
        ring.append((math.cos(a) * r * 1.2, math.sin(a) * r, rng.uniform(14.0, 30.0), rng.uniform(12.0, 26.0),
                     rng.uniform(25.0, 85.0)))
    for (x, y, sx, sy, h) in ring:
        it.append(L.slab(x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2, 0.0, h, "BrickDark" if rng.random() < 0.6 else "Concrete",
                         name="Tower", cast=False))
        # face toward the garage gets the window bands
        fx = -1.0 if x > 0 else 1.0
        fy = -1.0 if y > 0 else 1.0
        horiz = abs(x) > abs(y)
        face_w = sy if horiz else sx
        for b in range(int(h / 3.2)):
            if rng.random() < 0.55:
                continue
            zb = 3.0 + b * 3.2
            if zb > h - 2.0:
                break
            # one or two lit runs of offices per floor at random spots, not a full-width ribbon
            for _ in range(1 if rng.random() < 0.7 else 2):
                w = rng.uniform(2.5, max(3.0, 0.45 * face_w))
                a0 = rng.uniform(-face_w / 2 + 1.0, face_w / 2 - 1.0 - w)
                c = rng.choice(cols)
                glow = rng.uniform(0.8, 2.6)
                if horiz:
                    xf = x + fx * (sx / 2 + 0.05)
                    it.append(L.slab(xf - 0.05, y + a0, xf + 0.05, y + a0 + w, zb, zb + 1.3, "Emissive:" + c, glow=glow,
                                     coll=False, cast=False, name="Windows"))
                else:
                    yf = y + fy * (sy / 2 + 0.05)
                    it.append(L.slab(x + a0, yf - 0.05, x + a0 + w, yf + 0.05, zb, zb + 1.3, "Emissive:" + c, glow=glow,
                                     coll=False, cast=False, name="Windows"))
        if h > 55.0:
            it.append(L.slab(x - 0.4, y - 0.4, x + 0.4, y + 0.4, h, h + 0.6, "Emissive:Red", glow=25.0, coll=False, cast=False,
                             name="AviationLight"))
    # the neighbours' facades facing the open sides: a few lit windows (and on the east block's roofline side)
    for k in range(2):
        it.append(L.slab(36.0 - 0.06, -18.0 + 9 * k, 36.0, -14.5 + 9 * k, 4.2, 5.6, "Emissive:Warm", glow=1.6, coll=False,
                         cast=False, name="Windows"))
    for (y, face) in ((-24.2, 1.0), (24.2, -1.0)):
        for x in (-28.0, -14.0, -2.0, 12.0, 26.0):
            for zb in (4.0, 7.4):
                if rng.random() < 0.55:
                    it.append(L.slab(x, y - 0.05 * face - 0.03, x + rng.uniform(2.0, 4.5), y - 0.05 * face + 0.03, zb, zb + 1.4,
                                     "Emissive:" + rng.choice(cols), glow=rng.uniform(1.0, 2.5), coll=False, cast=False,
                                     name="Windows"))
    return it
