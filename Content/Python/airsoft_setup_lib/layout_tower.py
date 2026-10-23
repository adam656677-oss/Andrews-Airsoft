"""Andrew's Airsoft - L_LedgerTower: the syndicate's headquarters, top floors of a high-rise at night (story mission 7,
"The Books").

Plain layout data (no `unreal` import), registered in layouts.py as "LedgerTower" and loaded lazily by layouts._tower(),
which passes the layouts module in: build(L) -> item list, MAP -> map metadata.
Units and axes as layouts.py: metres, +X east, +Y south on the plans, yaw turns +X toward +Y.

Look: cold teal night through floor-to-ceiling glass, rain on the windows, warm practical lamps on walnut and black
marble, deep shadows, the city lit up far below. Two levels:
  Floor 40 (z 0): west, the elevator lobby and the Crane Fiduciary Trust reception (Blue / Andrew starts). Middle, the
  open-plan counting floor: glass offices along the north windows (north lane), clerk desk clusters split by filing
  walls (central lane), walnut archive stacks full of ledgers along the south windows (south lane). East, under the
  penthouse: the server room (north, objective A), a security corridor, and the vault antechamber with the round vault
  door standing open into the vault (south).
  Penthouse (z 4.6): reached by the grand stair in its walnut hall (centre) or the service stairs in the server room and
  the vault (flanks). Lounge north, Crane's desk and the boss arena in the middle (objective C), bar south, and the
  glass terrace in the rain on the east side (Red starts). Below the terrace, on the roof deck of the building next
  door, a grey '69 Fastback under a single lamp ("We saw the grey Fastback in the lot.").
Objective B: the middle of the counting floor.
Everything is original: the front company (Crane Fiduciary Trust), names and signs are invented.
"""

import math
import random

LEVELS = (("Floor40", 0.0), ("Penthouse", 4.6))
X0, X1, Y0, Y1 = -32.0, 32.0, -22.0, 22.0
CEIL = 4.0                      # floor-40 ceiling underside
PH = 4.6                        # penthouse floor (top of the floor-40 ceiling slab)
PH_CEIL = 8.6                   # penthouse ceiling underside
PH_X0, PH_X1 = 14.0, 28.0       # penthouse interior (terrace beyond PH_X1 to X1)
LOBBY_X1 = -21.0                # lobby / cores east wall
WELL = (6.7, -1.5, 14.0, 1.5)   # grand stair well (x0, y0, x1, y1)
STAIR_N = (17.0, -19.9, 24.0, -18.1)    # service stair holes in the penthouse floor
STAIR_S = (17.0, 18.1, 24.0, 19.9)
PODIUM_Z = -14.0                # roof deck of the building next door (east), out of bounds
STREET_Z = -150.0

MAP = {
    "name": "LedgerTower", "path": "/Game/Maps/L_LedgerTower", "kind": "match",
    "bounds": (X0, Y0, X1, Y1), "lighting": "ledger_night", "game_mode": "AirsoftGameMode",
    "kill_z": -20.0, "levels": LEVELS,
    "nav": (X0 - 1.0, Y0 - 1.0, -1.0, X1 + 1.0, Y1 + 1.0, 9.6),
}


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


def _local_rect(L, x, y, yaw, lx0, ly0, lx1, ly1):
    """World AABB of a local rect under a yaw that is a multiple of 90 degrees."""
    pts = [L.rot2(a, b, yaw) for (a, b) in ((lx0, ly0), (lx1, ly0), (lx0, ly1), (lx1, ly1))]
    xs, ys = [x + p[0] for p in pts], [y + p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _glass_wall(L, axis, fixed, a0, a1, z0, z1, mullion=3.0, openings=(), name="Window"):
    """Floor-to-ceiling glazing along `axis` with black mullions every `mullion` m and a sill / head rail;
    openings (b0, b1, top) leave a doorway (glass above `top`)."""
    out = L.wall_run(axis, fixed, a0, a1, z0, z1, 0.03, "Glass", openings=openings, name=name)
    n = int(round((a1 - a0) / mullion))
    for i in range(n + 1):
        a = a0 + i * (a1 - a0) / n
        if any(b0 - 0.05 < a < b1 + 0.05 for (b0, b1, _) in openings):
            continue
        if axis == "x":
            out.append(L.slab(a - 0.05, fixed - 0.12, a + 0.05, fixed + 0.12, z0, z1, "PaintedSteel", tint="Black",
                              name="Mullion"))
        else:
            out.append(L.slab(fixed - 0.12, a - 0.05, fixed + 0.12, a + 0.05, z0, z1, "PaintedSteel", tint="Black",
                              name="Mullion"))
    for (zz0, zz1) in ((z0, z0 + 0.08), (z1 - 0.1, z1)):
        if axis == "x":
            out.append(L.slab(a0, fixed - 0.1, a1, fixed + 0.1, zz0, zz1, "PaintedSteel", tint="Black", name="WindowRail",
                              coll=False))
        else:
            out.append(L.slab(fixed - 0.1, a0, fixed + 0.1, a1, zz0, zz1, "PaintedSteel", tint="Black", name="WindowRail",
                              coll=False))
    return out


def _rail(L, x0, y0, x1, y1, z, mat="Glass", h=1.05):
    """Balustrade: glass panel on a black shoe and a brass top rail."""
    return [L.slab(x0, y0, x1, y1, z, z + h, mat, name="Balustrade"),
            L.slab(x0, y0, x1, y1, z + h, z + h + 0.04, "Brass", name="RailTop", coll=False)]


# =============================================================================================
# Build
# =============================================================================================
def build(L=None):
    if L is None:
        from . import layouts as L
    it = []
    it += _shell(L)
    it += _lobby(L)
    it += _counting_floor(L, random.Random(4040))
    it += _east_block(L, random.Random(4141))
    it += _penthouse(L, random.Random(4242))
    it += _outside(L, random.Random(4343))
    # objectives (skirmish): A server room, B the counting floor, C Crane's office
    it += [L.objective("A", 25.0, -12.8, 0.0, radius=4.5, half_height=1.8),
           L.objective("B", -4.0, 0.0, 0.0, radius=5.0, half_height=1.8),
           L.objective("C", 21.0, 0.0, PH, radius=4.5, half_height=1.8)]
    return it


# ---------------------------------------------------------------------------------------------
# Shell: floors, ceilings, exterior glass, the grand-stair hall, the roof
# ---------------------------------------------------------------------------------------------
def _shell(L):
    slab = L.slab
    it = []
    # floor 40: polished black marble in the lobby, carpet on the counting floor, concrete under the penthouse
    it += [slab(X0, Y0, LOBBY_X1, Y1, -0.3, 0.0, "MarbleBlack", name="LobbyFloor"),
           slab(LOBBY_X1, Y0, PH_X0, Y1, -0.3, 0.0, "Carpet", name="CountingFloor", tint="Grey"),
           slab(PH_X0, Y0, X1, Y1, -0.3, 0.0, "ConcreteFloor", name="EastFloor", tint="Grey")]
    # floor-40 ceiling = penthouse floor (one slab, minus the stair well and the two service-stair holes)
    for (rx0, ry0, rx1, ry1) in _sub_rects((X0, Y0, X1, Y1), [WELL, STAIR_N, STAIR_S]):
        it.append(slab(rx0, ry0, rx1, ry1, CEIL, PH, "PlywoodPainted", tint="Black", name="Ceiling40"))
    # penthouse finishes: walnut floor inside, wet stone on the terrace (decals on the slab)
    it += [L.patch(PH_X0, Y0, PH_X1, Y1, PH + 0.012, "Walnut", name="PenthouseFloor", coll=False),
           L.patch(PH_X1, Y0, X1, Y1, PH + 0.012, "Granite", name="TerraceStone", coll=False)]
    # roof over the penthouse and the stair hall; low roof over the counting floor (dark, with plant)
    it += [slab(PH_X0 - 0.2, Y0 - 0.2, PH_X1 + 0.4, Y1 + 0.2, PH_CEIL, PH_CEIL + 0.4, "PlywoodPainted", tint="Black",
                name="PenthouseRoof"),
           slab(WELL[0] - 0.2, WELL[1] - 0.2, PH_X0, WELL[3] + 0.2, PH_CEIL, PH_CEIL + 0.4, "PlywoodPainted", tint="Black",
                name="StairHallRoof")]
    for (x, y) in ((-12.0, -9.0), (-2.0, 9.0), (6.0, -12.0)):
        it.append(L.prop("Garage_RoofHVAC", x, y, PH, 0.0, nocoll=True))
    # exterior glass on floor 40: north / south windows from the cores to the east end, east windows under the terrace
    it += _glass_wall(L, "x", Y0, LOBBY_X1, X1, 0.0, CEIL)
    it += _glass_wall(L, "x", Y1, LOBBY_X1, X1, 0.0, CEIL)
    it += _glass_wall(L, "y", X1, Y0, Y1, 0.0, CEIL)
    # the penthouse: glass north / south, glass to the terrace on the east with two sliding-door openings
    it += _glass_wall(L, "x", Y0, PH_X0, PH_X1, PH, PH_CEIL)
    it += _glass_wall(L, "x", Y1, PH_X0, PH_X1, PH, PH_CEIL)
    it += _glass_wall(L, "y", PH_X1, Y0, Y1, PH, PH_CEIL, openings=[(-8.0, -4.6, 2.8), (4.6, 8.0, 2.8)], name="TerraceGlass")
    # the penthouse west wall (walnut over the counting-floor roof), open only where the grand stair arrives
    it += L.wall_run("y", PH_X0, Y0, Y1, PH, PH_CEIL, 0.3, "Walnut", openings=[(WELL[1], WELL[3], 3.2)],
                     name="PenthouseWest")
    # grand-stair hall: walnut walls rising from the floor-40 ceiling to the roof around the well (no way onto the
    # counting-floor roof from the stair)
    it += [slab(WELL[0], WELL[1] - 0.25, PH_X0, WELL[1], CEIL, PH_CEIL, "Walnut", name="StairHallWall"),
           slab(WELL[0], WELL[3], PH_X0, WELL[3] + 0.25, CEIL, PH_CEIL, "Walnut", name="StairHallWall"),
           slab(WELL[0] - 0.25, WELL[1] - 0.25, WELL[0], WELL[3] + 0.25, CEIL, PH_CEIL, "Walnut", name="StairHallWall")]
    # the grand stair: walnut treads from the counting floor up to the penthouse, brass handrails
    rise, run = 0.2, 0.3
    n = int(round(PH / rise))
    sx0 = PH_X0 - n * run
    it += L.stairs(sx0, 0.0, 0.0, PH, "+x", 2.9, "Walnut", rise=PH / n, run=run)
    for s in (-1, 1):
        it.append(L.slab(sx0 - 0.3, s * 1.42 - 0.04, PH_X0, s * 1.42 + 0.04, 0.9, PH + 1.0, "Brass", name="StairRail",
                         coll=False))
    it.append(L.hanging("Chandelier", 10.4, 0.0, PH_CEIL, light={"cd": 7.0, "radius": 10.0}))
    # world edge: invisible walls just outside the glass on both levels (the glass is the visible boundary)
    it += [L.blocker(X0 - 0.6, Y0 - 0.6, X1 + 0.6, Y0 - 0.15, -1.0, 14.0),
           L.blocker(X0 - 0.6, Y1 + 0.15, X1 + 0.6, Y1 + 0.6, -1.0, 14.0),
           L.blocker(X1 + 0.15, Y0, X1 + 0.6, Y1, -1.0, 14.0),
           L.blocker(X0 - 0.6, Y0, X0, Y1, -1.0, 14.0)]
    return it


# ---------------------------------------------------------------------------------------------
# Lobby (Blue / Andrew starts)
# ---------------------------------------------------------------------------------------------
def _lobby(L):
    slab, prop = L.slab, L.prop
    it = []
    # service cores north and south of the lobby (lift machinery, stair cores): solid marble-clad blocks
    it += [slab(X0, Y0, LOBBY_X1, -10.0, 0.0, CEIL, "MarbleBlack", name="CoreNorth"),
           slab(X0, 10.0, LOBBY_X1, Y1, 0.0, CEIL, "MarbleBlack", name="CoreSouth")]
    # west wall with three lift doors, east wall to the counting floor with two doorways (no straight sight line)
    it += [slab(X0 - 0.3, -10.0, X0, 10.0, 0.0, CEIL, "Walnut", name="LiftWall")]
    for y in (-6.0, 0.0, 6.0):
        it.append(prop("Garage_ElevatorDoors", X0 + 0.15, y, 0.0, 0.0))
        it.append(L.box(X0 + 0.08, y, 3.3, 0.04, 0.9, 0.18, "Emissive:Amber", glow=6.0, coll=False, cast=False,
                        name="FloorIndicator"))
        it.append(L.text(X0 + 0.1, y, 3.32, 0.0, "40", size=14.0, color="Amber", glow=4.0))
    it += L.wall_run("y", LOBBY_X1, -10.0, 10.0, 0.0, CEIL, 0.3, "Walnut", openings=[(-8.4, -5.4, 2.8), (5.4, 8.4, 2.8)],
                     name="LobbyEast")
    # marble screens just inside each doorway: no straight sight line from the counting floor into the lifts
    it += [slab(-23.4, -8.9, -23.0, -4.9, 0.0, 2.9, "MarbleBlack", name="LobbyScreen"),
           slab(-23.4, 4.9, -23.0, 8.9, 0.0, 2.9, "MarbleBlack", name="LobbyScreen")]
    it += [prop("Tower_ReceptionDesk", -24.0, 0.0, 0.0, 180.0),
           prop("Armchair_Leather", -22.6, -1.4, 0.0, 180.0), prop("Armchair_Leather", -22.6, 1.4, 0.0, 180.0),
           prop("Planter_Concrete", -27.0, -8.9, 0.0, 0.0), prop("Planter_Concrete", -27.0, 8.9, 0.0, 0.0),
           prop("RugPersian", -28.4, 0.0, 0.0, 90.0)]
    it.append(L.text(LOBBY_X1 - 0.18, 0.0, 2.9, 180.0, "CRANE FIDUCIARY TRUST", size=34.0, color="Gold", glow=2.0))
    # Blue starts (the first is Andrew's story start, stepping out of the middle lift)
    starts = [(-30.6, 0.0)]
    for x in (-30.4, -28.6, -26.8):
        for y in (-7.4, -4.0, 4.0, 7.4):
            if (x, y) != (-30.4, 0.0):
                starts.append((x, y))
    starts.append((-28.6, -1.8))
    for (x, y) in starts:
        it.append(L.start(x, y, "Blue", 0.0))
    # light: one hard downlight on the reception, two brass ceiling lights (unshadowed)
    it += [L.light("spot", -24.6, 0.0, CEIL - 0.05, pitch=-90.0, yaw=0.0, color="Warm", cd=40.0, radius=9.0, cone=(25, 45),
                   shadows=True, vol=1.2, src=6.0),
           L.hanging("CeilingLight_Brass", -29.0, -5.0, CEIL, light={"shadows": False}),
           L.hanging("CeilingLight_Brass", -29.0, 5.0, CEIL, light={"shadows": False})]
    it += [L.sound("AmbienceStaging", -27.0, 0.0, 2.0, spatial=True, radius=6.0, falloff=8.0, volume=0.35),
           L.capture(-27.0, 0.0, 2.0, 9.0)]
    return it


# ---------------------------------------------------------------------------------------------
# The counting floor
# ---------------------------------------------------------------------------------------------
def _counting_floor(L, rng):
    slab, prop = L.slab, L.prop
    it = []
    # --- north: five glass offices along the windows (y -22..-16), walnut dividers, glass fronts with doors
    xs = (LOBBY_X1, -14.0, -7.0, 0.0, 7.0, PH_X0)
    for x in xs[1:-1]:
        it.append(slab(x - 0.12, Y0, x + 0.12, -16.0, 0.0, CEIL, "Walnut", name="OfficeDivider"))
    doors = []
    for i in range(5):
        a, b = xs[i], xs[i + 1]
        d0 = (a + b) / 2 + 1.0
        doors.append((d0, d0 + 1.3, 2.5))
        cx = (a + b) / 2
        it += [prop("Tower_Desk", cx - 0.6, -19.4, 0.0, 180.0 if i % 2 else 0.0),
               prop("Tower_FilingWall_2m", a + 0.75, -20.6, 0.0, 0.0),
               prop("Armchair_Leather", cx + 1.6, -20.6, 0.0, 200.0)]
        it.append(L.hanging("Tower_PendantLinear", cx - 0.6, -19.4, CEIL, light=True))
    it += _glass_front(L, -16.0, LOBBY_X1, PH_X0, doors)
    it.append(L.text(-17.5, -16.08, 2.4, -90.0, "ACCOUNTS RECEIVABLE", size=12.0, color="Gold", glow=1.2))

    # --- middle: clerk desk clusters (2 x 2, privacy screens back to back) and filing walls; central lane y -2..2
    for cx in (-16.5, -10.5, -4.5, 1.5):
        for cy in (-7.6, 6.4):
            for dy in (-0.85, 0.85):
                it.append(prop("Tower_Desk", cx + 0.42, cy + dy, 0.0, 0.0))
                it.append(prop("Tower_Desk", cx - 0.42, cy + dy, 0.0, 180.0))
            it.append(L.hanging("Tower_PendantLinear", cx, cy, CEIL, yaw=0.0, light=True))
        it.append(prop("Tower_FilingWall_2m", cx + 3.0, -4.6, 0.0, 0.0))
        it.append(prop("Tower_FilingWall_2m", cx + 3.0, 3.4, 0.0, 0.0))
    # central-lane cover: planters, a low marble plinth with a brass model of the tower, a document trolley
    it += [prop("Planter_Concrete", -13.4, 1.1, 0.0, 0.0), prop("Planter_Concrete", -7.4, -1.2, 0.0, 0.0),
           prop("Planter_Concrete", 4.6, 1.1, 0.0, 0.0),
           slab(-2.0, -0.7, 0.2, 0.7, 0.0, 0.95, "MarbleBlack", name="Plinth"),
           slab(-1.2, -0.25, -0.6, 0.25, 0.95, 1.9, "Brass", name="TowerModel", coll=False),
           prop("Tower_FilingWall_2m", -19.2, 1.4, 0.0, 90.0), prop("Crate_Wood", 5.8, -1.6, 0.0, 12.0)]
    # the north lane (y -16..-11): a few loose pieces of cover
    it += [prop("Planter_Concrete", -17.0, -13.0, 0.0, 0.0), prop("Tower_FilingWall_2m", -8.0, -13.4, 0.0, 90.0),
           prop("Planter_Concrete", 2.0, -12.8, 0.0, 0.0), prop("Tower_FilingWall_2m", 10.6, -13.0, 0.0, 90.0)]

    # --- south: the archive stacks (walnut shelving full of ledgers) with a cross aisle at y 17.2; south lane y 10..13.6
    for x in (-18.6, -15.4, -12.2, -9.0, -5.8, -2.6, 0.6, 3.8, 7.0):
        it.append(prop("Tower_ArchiveShelf_3m", x, 15.1, 0.0, 0.0))
        it.append(prop("Tower_ArchiveShelf_3m", x, 19.3, 0.0, 0.0))
        it.append(L.hanging("Tower_PendantLinear", x + 1.6, 17.2, CEIL, yaw=90.0, light=False))
    it += [prop("Tower_Desk", 10.6, 17.2, 0.0, 180.0), prop("Tower_FilingWall_2m", 11.4, 20.4, 0.0, 90.0),
           prop("Tower_FilingWall_2m", -12.0, 11.8, 0.0, 90.0), prop("Planter_Concrete", -3.0, 11.6, 0.0, 0.0),
           prop("Tower_FilingWall_2m", 5.4, 11.9, 0.0, 90.0)]
    it.append(L.text(-19.8, 13.3, 2.6, 90.0, "ARCHIVE  -  BY APPOINTMENT", size=12.0, color="Gold", glow=1.2))

    # --- light: three shadowed key spots (north lane, central lane, archive); pendants do the fill
    it += [L.light("spot", -6.0, -13.6, CEIL - 0.05, pitch=-90.0, color="Warm", cd=22.0, radius=10.0, cone=(30, 55),
                   shadows=True, vol=1.0, src=8.0),
           L.light("spot", -4.0, 0.0, CEIL - 0.05, pitch=-90.0, color="Warm", cd=30.0, radius=11.0, cone=(30, 55),
                   shadows=True, vol=1.0, src=8.0),
           L.light("spot", -4.0, 17.2, CEIL - 0.05, pitch=-90.0, color="Warm", cd=18.0, radius=9.0, cone=(25, 50),
                   shadows=True, vol=1.0, src=6.0)]
    it += [L.fogvol(-4.0, 0.0, 2.0, 18.0, 21.0, 2.0, density=0.18, color=(0.55, 0.66, 0.7))]
    for (x, y) in ((-14.0, -6.0), (2.0, -6.0), (-14.0, 6.0), (2.0, 6.0), (-6.0, 17.0), (-6.0, -19.0)):
        it.append(L.capture(x, y, 1.8, 9.0))
    it += [L.sound("AmbienceGarageRoof", -6.0, -20.0, 2.0, spatial=True, radius=14.0, falloff=12.0, volume=0.7),
           L.sound("AmbienceGarageRoof", -6.0, 20.0, 2.0, spatial=True, radius=14.0, falloff=12.0, volume=0.7)]
    return it


def _glass_front(L, y, x0, x1, doors):
    """Office glass front along x at y: glass to 2.8 m with walnut transom above, doors (b0, b1, top) open."""
    it = L.wall_run("x", y, x0, x1, 0.0, 2.8, 0.04, "Glass", openings=doors, name="OfficeGlass")
    it += L.wall_run("x", y, x0, x1, 2.8, CEIL, 0.2, "Walnut", name="OfficeTransom")
    for (b0, b1, _) in doors:
        for b in (b0, b1):
            it.append(L.slab(b - 0.04, y - 0.06, b + 0.04, y + 0.06, 0.0, 2.8, "Brass", name="DoorFrame"))
    return it


# ---------------------------------------------------------------------------------------------
# East block under the penthouse: server room, security corridor, vault
# ---------------------------------------------------------------------------------------------
def _east_block(L, rng):
    slab, prop = L.slab, L.prop
    it = []
    # walls: west (to the counting floor) with doors into each room, server / corridor / vault partitions
    it += L.wall_run("y", PH_X0, Y0, -7.0, 0.0, CEIL, 0.3, "Concrete", openings=[(-15.2, -12.6, 2.6)], name="ServerWest")
    it += L.wall_run("y", PH_X0, 7.0, Y1, 0.0, CEIL, 0.3, "Concrete", openings=[(10.0, 12.6, 2.6)], name="VaultWest")
    it += L.wall_run("x", -7.0, PH_X0, X1, 0.0, CEIL, 0.3, "Concrete", openings=[(26.0, 28.4, 2.6)], name="ServerSouth")
    it += L.wall_run("x", 7.0, PH_X0, X1, 0.0, CEIL, 0.3, "Concrete", openings=[(26.0, 28.4, 2.6)], name="VaultNorth")
    # the stair mass abuts the corridor: walls either side of it close the corridor's west end except two doors
    it += L.wall_run("y", PH_X0, -7.0, 7.0, 0.0, CEIL, 0.3, "Walnut", openings=[(-6.4, -3.2, 2.6), (3.2, 6.4, 2.6)],
                     name="CorridorWest")

    # --- server room (y -22..-7): three rows of racks, the north service stair up to the penthouse
    for x in (18.6, 22.6, 26.6, 30.4):
        for k in range(10):
            y = -16.2 + k * 0.62
            it.append(prop("Tower_ServerRack", x, y, 0.0, 0.0 if x < 29 else 180.0))
    it += L.stairs(STAIR_N[0], (STAIR_N[1] + STAIR_N[3]) / 2, 0.0, PH, "+x", 1.6, "PaintedSteel", rise=PH / 23, run=0.3,
                   tint="Gunmetal")
    it += [slab(STAIR_N[0] - 0.3, -17.9, STAIR_N[2] + 0.05, -17.84, 0.9, PH + 1.0, "PaintedSteel", tint="Black",
                name="StairRail", coll=False)]
    it += [L.light("spot", 24.6, -12.8, CEIL - 0.05, pitch=-90.0, color="Cool", cd=24.0, radius=10.0, cone=(30, 60),
                   shadows=True, vol=1.4, src=6.0),
           L.light("rect", 20.6, -12.8, CEIL - 0.05, pitch=-90.0, color="Cool", cd=3.0, radius=6.0, w=0.4, h=3.0,
                   shadows=False),
           L.text(PH_X0 + 0.18, -16.6, 2.9, 0.0, "SERVER  ROOM  -  NO ENTRY", size=12.0, color="Red", glow=2.0),
           L.fogvol(23.0, -13.0, 2.0, 8.0, 5.0, 2.0, density=0.3, color=(0.5, 0.68, 0.9)),
           L.sound("AmbienceGarage", 24.0, -13.0, 2.0, spatial=True, radius=8.0, falloff=8.0, volume=0.8),
           L.capture(23.0, -13.0, 2.0, 8.0)]

    # --- security corridor (y -7..7): guard desk, monitor wall, cover
    it += [prop("Tower_Desk", 22.0, -4.6, 0.0, 180.0), prop("Tower_FilingWall_2m", 18.0, 4.8, 0.0, 90.0),
           prop("Tower_ServerRack", 31.2, -5.0, 0.0, 180.0), prop("Tower_ServerRack", 31.2, -4.38, 0.0, 180.0),
           prop("Crate_Ammo", 27.4, 4.6, 0.0, 20.0), prop("GunCase_Hard", 29.6, 4.6, 0.0, 0.0),
           L.box(31.8, 0.0, 2.2, 0.06, 4.6, 1.2, "Emissive:Cool", glow=3.0, coll=False, cast=False, name="MonitorWall"),
           L.light("point", 26.0, 0.0, CEIL - 0.3, color="Cool", cd=3.0, radius=8.0, shadows=False, src=20.0)]

    # --- vault: antechamber (y 7..14), the open round door, the vault (y 14..22) with the south service stair
    vx, vy, vyaw = 26.0, 14.0, -90.0
    it.append(prop("Tower_VaultDoor", vx, vy, 0.0, vyaw))
    # vault wall either side of the door section; the door asset is walk-through for the checker -> blockers for its
    # wall parts, the head above the opening and the swung-open door
    it += [slab(PH_X0, vy - 0.45, vx - 2.0, vy + 0.45, 0.0, CEIL, "Concrete", name="VaultWall"),
           slab(vx + 2.0, vy - 0.45, X1, vy + 0.45, 0.0, CEIL, "Concrete", name="VaultWall"),
           slab(vx - 2.0, vy - 0.45, vx + 2.0, vy + 0.45, 3.4, CEIL, "Concrete", name="VaultWallHead")]
    for (lx0, ly0, lx1, ly1, z0, z1) in ((-0.45, -2.0, 0.45, -1.15, 0.0, 3.4), (-0.45, 1.15, 0.45, 2.0, 0.0, 3.4),
                                         (-0.45, -1.15, 0.45, 1.15, 2.35, 3.4), (0.5, -1.95, 2.85, -1.15, 0.0, 2.45)):
        bx0, by0, bx1, by1 = _local_rect(L, vx, vy, vyaw, lx0, ly0, lx1, ly1)
        it.append(L.blocker(bx0, by0, bx1, by1, z0, z1))
    it += [L.light("spot", vx, 9.6, CEIL - 0.05, pitch=-55.0, yaw=90.0, color="Warm", cd=26.0, radius=9.0, cone=(18, 34),
                   shadows=True, vol=2.0, src=4.0),
           prop("Tower_FilingWall_2m", 18.4, 9.4, 0.0, 90.0), prop("Planter_Concrete", 21.0, 12.4, 0.0, 0.0)]
    # inside the vault: deposit-box walls along the windows, pallets of cash crates, a counting table
    for x in (15.6, 18.0, 20.4, 26.6, 29.0, 31.0):
        it.append(prop("Tower_FilingWall_2m", x, 21.4, 0.0, -90.0))
    it += [prop("PalletStack", 27.2, 16.8, 0.0, 0.0), prop("Crate_Wood", 27.2, 16.8, 0.58, 10.0),
           prop("PalletStack", 30.0, 17.4, 0.0, 20.0), prop("Crate_Wood", 30.0, 17.4, 0.58, -4.0),
           prop("Tower_Desk", 25.6, 19.0, 0.0, 90.0)]
    it += L.stairs(STAIR_S[0], (STAIR_S[1] + STAIR_S[3]) / 2, 0.0, PH, "+x", 1.6, "PaintedSteel", rise=PH / 23, run=0.3,
                   tint="Gunmetal")
    it += [slab(STAIR_S[0] - 0.3, 17.84, STAIR_S[2] + 0.05, 17.9, 0.9, PH + 1.0, "PaintedSteel", tint="Black",
                name="StairRail", coll=False),
           L.light("point", 22.0, 16.4, CEIL - 0.3, color="Warm", cd=2.5, radius=7.0, shadows=False, src=15.0),
           L.text(vx - 2.1, vy - 0.48, 3.0, -90.0, "VAULT  2", size=14.0, color="Gold", glow=1.5),
           L.capture(23.0, 10.5, 2.0, 7.0), L.capture(24.0, 18.0, 2.0, 7.0)]
    return it


# ---------------------------------------------------------------------------------------------
# Penthouse (Red starts on the terrace)
# ---------------------------------------------------------------------------------------------
def _penthouse(L, rng):
    slab, prop = L.slab, L.prop
    it = []
    z = PH
    # railings round the two service-stair holes (open on the east end, where the stair arrives)
    for (hx0, hy0, hx1, hy1) in (STAIR_N, STAIR_S):
        it += _rail(L, hx0, hy0 - 0.1, hx1, hy0, z) + _rail(L, hx0, hy1, hx1, hy1 + 0.1, z) + \
            _rail(L, hx0 - 0.1, hy0 - 0.1, hx0, hy1 + 0.1, z)
    # walnut wall panels on the west wall, marble columns
    for y in (-18.0, -10.0, 10.0, 18.0):
        it.append(prop("WallPanel_Walnut_4m", PH_X0 + 0.16, y, z, 0.0))
    for (x, y) in ((17.6, -6.4), (17.6, 6.4), (23.4, -6.4), (23.4, 6.4)):
        it.append(slab(x - 0.4, y - 0.4, x + 0.4, y + 0.4, z, PH_CEIL, "MarbleBlack", name="Column"))

    # --- lounge (north): curved booth, armchairs on a rug, low tables; chandelier (shadowed)
    it += [prop("RugPersian", 21.6, -12.0, z, 0.0), prop("BoothSofa_Curved", 19.4, -12.0, z, 0.0),
           prop("BoothTable", 20.8, -12.0, z, 0.0), prop("Armchair_Leather", 22.8, -13.2, z, 150.0),
           prop("Armchair_Leather", 22.8, -10.8, z, 210.0), prop("Planter_Concrete", 26.6, -15.0, z, 0.0),
           prop("Planter_Concrete", 15.0, -15.6, z, 0.0), prop("HighTable", 25.4, -9.2, z, 0.0),
           L.hanging("Chandelier", 21.0, -12.0, PH_CEIL, light={"cd": 8.0, "radius": 10.0})]

    # --- Crane's desk and the boss arena (middle): the desk faces the stair, the city behind him
    it += [prop("Tower_ExecDesk", 25.2, 0.0, z, 180.0), prop("Armchair_Leather", 26.4, 0.0, z, 180.0),
           prop("BankersLamp", 25.0, 0.9, z + 0.76, 180.0, light={"cd": 1.8, "radius": 4.0, "shadows": True}),
           prop("Armchair_Leather", 23.2, -1.2, z, 20.0), prop("Armchair_Leather", 23.2, 1.2, z, -20.0),
           prop("Planter_Concrete", 19.2, -3.0, z, 0.0), prop("Planter_Concrete", 19.2, 3.0, z, 0.0),
           prop("Tower_ArchiveShelf_3m", 27.4, -4.2, z, 0.0), prop("Tower_ArchiveShelf_3m", 27.4, 4.2, z, 0.0)]
    for (x, y) in ((16.0, -3.6), (16.0, 3.6), (21.0, -9.6), (21.0, 9.6)):
        it.append(L.hanging("CeilingLight_Brass", x, y, PH_CEIL, light={"shadows": False}))
    it.append(L.text(PH_X0 + 0.18, 0.0, z + 3.3, 0.0, "C R A N E", size=26.0, color="Gold", glow=1.2))

    # --- bar (south): counter facing north, back bar behind it, stools; private dining strip beyond
    for x in (19.2, 23.2):
        it.append(prop("BarCounter_4m", x, 12.4, z, -90.0))
        it.append(prop("BackBar_4m", x, 15.6, z, -90.0))
    for x in (17.8, 19.0, 20.2, 21.8, 23.0, 24.2):
        it.append(prop("BarStool", x, 11.4, z, -90.0 + rng.uniform(-14, 14)))
    it += [prop("BoothTable", 26.2, 19.6, z, 0.0), prop("Armchair_Leather", 25.2, 19.6, z, 90.0),
           prop("Armchair_Leather", 27.2, 19.6, z, -90.0), prop("Planter_Concrete", 15.2, 15.8, z, 0.0)]

    # --- terrace (x 28..32): rain, glass balustrade, Red starts; the drop to the roof deck next door below
    it += _rail(L, X1 - 0.12, Y0, X1, Y1, z) + _rail(L, PH_X1, Y0, X1, Y0 + 0.12, z) + _rail(L, PH_X1, Y1 - 0.12, X1, Y1, z)
    it += [prop("Planter_Concrete", 29.0, -10.6, z, 0.0), prop("Planter_Concrete", 29.0, 10.6, z, 0.0),
           prop("Planter_Concrete", 30.8, 0.0, z, 0.0)]
    for (x, y) in ((29.4, -19.6), (31.0, -17.4), (29.4, -15.2), (31.0, -13.0), (29.4, -8.6), (31.0, -6.4),
                   (29.4, 19.6), (31.0, 17.4), (29.4, 15.2), (31.0, 13.0), (29.4, 8.6), (31.0, 6.4)):
        it.append(L.start(x, y, "Red", 180.0, z=z))
    # light: cold rim spot from the terrace edge back through the glass (shadowed), bar strip lights
    it += [L.light("spot", 31.6, 0.0, PH_CEIL + 0.8, pitch=-30.0, yaw=180.0, color=(0.62, 0.8, 1.0), cd=60.0, radius=22.0,
                   cone=(30, 55), shadows=True, vol=3.0, src=6.0),
           L.fogvol(21.0, 0.0, z + 2.0, 7.0, 21.0, 2.0, density=0.32, color=(0.56, 0.7, 0.78)),
           L.capture(21.0, -12.0, z + 1.8, 9.0), L.capture(21.0, 0.0, z + 1.8, 9.0), L.capture(21.0, 14.0, z + 1.8, 9.0),
           L.capture(30.0, 0.0, z + 1.8, 10.0),
           L.sound("AmbienceGarageRoof", 30.0, 0.0, z + 2.0, spatial=True, radius=12.0, falloff=12.0, volume=1.0),
           L.sound("AmbienceClubInterior", 21.0, 14.0, z + 2.0, spatial=True, radius=6.0, falloff=8.0, volume=0.25)]
    return it


# ---------------------------------------------------------------------------------------------
# Outside (no collision): the roof deck next door with the grey Fastback, the city below and around
# ---------------------------------------------------------------------------------------------
def _outside(L, rng):
    slab, prop = L.slab, L.prop
    it = []
    # the next building east: a roof parking deck 14 m below the terrace
    it += [slab(38.0, -26.0, 78.0, 26.0, PODIUM_Z - 0.4, PODIUM_Z, "ConcreteGarageWet", name="RoofDeck", coll=False),
           slab(38.0, -26.0, 78.0, 26.0, STREET_Z, PODIUM_Z - 0.4, "BrickDark", name="NextBuilding", coll=False,
                cast=False),
           slab(37.6, -26.0, 38.0, 26.0, PODIUM_Z, PODIUM_Z + 1.1, "Concrete", name="DeckParapet", coll=False)]
    for x in (44.0, 50.0, 56.0, 62.0):
        it.append(L.patch(x - 0.05, -2.0, x + 0.05, 4.0, PODIUM_Z + 0.006, "PaintLineWhite", name="Stall", coll=False))
    it += [prop("Car_Hero", 47.0, 1.0, PODIUM_Z, 96.0, tint="HeroGunmetal", nocoll=True),
           prop("Car_SUV", 59.0, 1.2, PODIUM_Z, 90.0, tint="Obsidian", nocoll=True),
           prop("StreetLamp", 47.0, -2.6, PODIUM_Z, 90.0, nocoll=True, light=False),
           L.light("spot", 47.0, 1.0, PODIUM_Z + 6.5, pitch=-90.0, color="Sodium", cd=40.0, radius=12.0, cone=(25, 50),
                   shadows=True, vol=1.5, src=4.0)]
    for (x, y) in ((60.0, -12.0), (70.0, 12.0)):
        it.append(prop("StreetLamp", x, y, PODIUM_Z, 0.0, nocoll=True, light={"cd": 10.0, "radius": 12.0}))
    for k in range(10):
        it.append(L.box(40.0 + k * 3.6, -25.0, PODIUM_Z + 1.2, 0.4, 0.1, 0.08, "Emissive:Sodium", glow=8.0, coll=False,
                        cast=False, name="DeckLight"))
    # the street far below: a dark plane, sodium street grid, car light streaks
    it.append(slab(-400.0, -400.0, 400.0, 400.0, STREET_Z - 1.0, STREET_Z, "AsphaltWet", name="Street", coll=False,
                   cast=False))
    for k in range(-6, 7):
        it.append(L.box(k * 60.0, 0.0, STREET_Z + 0.2, 1.2, 760.0, 0.2, "Emissive:Sodium", glow=3.0, coll=False, cast=False,
                        name="StreetGlow"))
        it.append(L.box(0.0, k * 60.0, STREET_Z + 0.2, 760.0, 1.2, 0.2, "Emissive:Sodium", glow=3.0, coll=False, cast=False,
                        name="StreetGlow"))
    # skyline: towers all around, some taller than this one, lit window runs, red aviation lights
    cols = ["Warm", "Warm", "Cool", "Amber", "Cool", "White"]
    for k in range(34):
        a = math.radians(rng.uniform(0.0, 360.0))
        if -40.0 < math.degrees(a) % 360.0 < 40.0 and k % 3:     # keep the east view (deck + harbour) more open
            continue
        r = rng.uniform(90.0, 240.0)
        x, y = math.cos(a) * r, math.sin(a) * r
        sx, sy = rng.uniform(18.0, 34.0), rng.uniform(18.0, 34.0)
        top = STREET_Z + rng.uniform(110.0, 210.0)
        it.append(slab(x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2, STREET_Z, top, "BrickDark" if rng.random() < 0.5
                       else "Concrete", name="Tower", coll=False, cast=False))
        # lit window runs on the face toward this tower
        fx, fy = -math.cos(a), -math.sin(a)
        for b in range(int((top - STREET_Z) / 3.6)):
            zb = STREET_Z + 4.0 + b * 3.6
            if zb < -40.0 or rng.random() < 0.55:
                continue
            w = rng.uniform(3.0, 10.0)
            o = rng.uniform(-6.0, 6.0)
            if abs(fx) > abs(fy):
                px = x + fx * (sx / 2 + 0.05)
                it.append(slab(px - 0.05, y + o - w / 2, px + 0.05, y + o + w / 2, zb, zb + 1.6, "Emissive:" + rng.choice(cols),
                               glow=rng.uniform(0.8, 2.6), coll=False, cast=False, name="Windows"))
            else:
                py = y + fy * (sy / 2 + 0.05)
                it.append(slab(x + o - w / 2, py - 0.05, x + o + w / 2, py + 0.05, zb, zb + 1.6, "Emissive:" + rng.choice(cols),
                               glow=rng.uniform(0.8, 2.6), coll=False, cast=False, name="Windows"))
        if top > 20.0:
            it.append(L.box(x, y, top + 0.6, 0.8, 0.8, 0.8, "Emissive:Red", glow=25.0, coll=False, cast=False,
                            name="AviationLight"))
    # a red neon brand on the tower across the street (invented)
    it.append(L.text(-60.0, -70.0, 18.0, 60.0, "HALLORAN", size=900.0, color="Red", glow=6.0))
    return it
