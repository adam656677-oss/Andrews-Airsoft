"""Ledger Tower kit: the syndicate's headquarters floors (Blender, propkit).

Every asset is registered with @asset and built by build_tower.py. Authoring space follows
Tools/Blender/CONVENTIONS.md: metres, +X = front, +Z = up, Blender +Y = Unreal -Y, origin =
floor centre of the footprint.

Extra per-asset data written to PropsTower.json:
    Layout        hints for Tools/Unreal/check_layouts.py (Core [[x0,y0],[x1,y1]] cm, Los / Cover / Solid).
Everything is original: the front company (Crane Fiduciary Trust), the ledgers and every label are invented;
no real brands or logos.
"""

import math
import os
import random

from mathutils import Matrix

import propkit as pk
import propkit_mats as pm

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "..", "club", "fonts")
ASSETS = {}

# Lineup sheet (rows back to front)
LINEUP = [
    ["Tower_ArchiveShelf_3m", "Tower_VaultDoor", "Tower_ServerRack", "Tower_FilingWall_2m"],
    ["Tower_ReceptionDesk", "Tower_ExecDesk", "Tower_Desk"],
    ["Tower_PendantLinear"],
]


def asset(aid, **kw):
    def deco(fn):
        ASSETS[aid] = {"fn": fn, "kw": dict(group="Tower", **kw)}
        return fn
    return deco


def font(name="BigShoulders-Bold.ttf"):
    p = os.path.abspath(os.path.join(FONT_DIR, name))
    return p if os.path.exists(p) else None


def serif():
    return font("LibreBaskerville-Regular.ttf")


# ======================================================================================
# Recipes (registered into propkit_mats.MATS so propkit.get_mat can build them)
# ======================================================================================
def _reg():
    M = pm.MATS
    M["t_cabinet"] = (pm.paint, dict(col=(0.055, 0.07, 0.068), rough=0.38, peel=0.15, grime=0.25, chip=0.15,
                                     chip_col=(0.3, 0.3, 0.3)))
    M["t_rack_black"] = (pm.paint, dict(col=(0.018, 0.018, 0.02), rough=0.45, peel=0.05, grime=0.2))
    M["t_paper"] = (pm.fabric, dict(col=(0.62, 0.58, 0.48), rough=0.9, weave=1400.0))
    M["t_paper_old"] = (pm.fabric, dict(col=(0.52, 0.44, 0.3), rough=0.92, weave=1400.0))
    M["t_spine_oxblood"] = (pm.leather, dict(col=(0.12, 0.018, 0.014), rough=0.5, crease=0.8, worn=0.9))
    M["t_spine_green"] = (pm.leather, dict(col=(0.02, 0.06, 0.035), rough=0.5, crease=0.8, worn=0.9))
    M["t_spine_black"] = (pm.leather, dict(col=(0.018, 0.016, 0.015), rough=0.45, crease=0.8, worn=0.9))
    M["t_spine_tan"] = (pm.leather, dict(col=(0.2, 0.1, 0.04), rough=0.5, crease=0.8, worn=1.0))
    M["t_vault_steel"] = (pm.metal, dict(col=(0.52, 0.53, 0.55), rough=0.22, brushed=1.0, dirt=0.35))
    M["t_vault_dark"] = (pm.metal, dict(col=(0.16, 0.16, 0.17), rough=0.32, brushed=0.6, dirt=0.4))
    M["t_screen"] = (pm.emissive, dict(col=(0.55, 0.78, 0.95)))
    M["t_screen_green"] = (pm.emissive, dict(col=(0.25, 0.95, 0.55)))
    M["t_led_blue"] = (pm.emissive, dict(col=(0.15, 0.45, 1.0)))
    M["t_led_green"] = (pm.emissive, dict(col=(0.15, 1.0, 0.35)))
    M["t_led_amber"] = (pm.emissive, dict(col=(1.0, 0.55, 0.12)))
    M["t_warm_strip"] = (pm.emissive, dict(col=(1.0, 0.8, 0.56)))
    M["t_cool_strip"] = (pm.emissive, dict(col=(0.86, 0.92, 1.0)))


_reg()

SPINES = ("t_spine_oxblood", "t_spine_green", "t_spine_black", "t_spine_tan", "t_spine_black", "t_spine_oxblood")


def _book_row(A, x_face, y0, y1, z, depth, rng, h_lo=0.24, h_hi=0.33, gap=0.12, face=1):
    """A shelf row of ledgers standing spine-out toward `face` (+1 = +X): random widths / heights, an
    occasional gap and a book leaning into it."""
    y = y0
    while y < y1 - 0.03:
        if rng.random() < 0.05:                               # gap with a leaning book
            w = rng.uniform(0.04, 0.07)
            hb = rng.uniform(h_lo, h_hi)
            ob = A.box((depth * 0.9, w, hb), at=(0, 0, 0), mat=rng.choice(SPINES), bevel=0.004)
            ob.matrix_world = (Matrix.Translation((x_face - face * depth / 2, min(y + gap, y1 - 0.04), z))
                               @ Matrix.Rotation(math.radians(rng.uniform(14, 22)), 4, "X")
                               @ Matrix.Translation((0, 0, hb / 2)) @ ob.matrix_world)
            y += gap + w
            continue
        w = rng.uniform(0.035, 0.075)
        if y + w > y1:
            break
        hb = rng.uniform(h_lo, h_hi)
        d = depth * rng.uniform(0.82, 0.98)
        A.box((d, w - 0.003, hb), at=(x_face - face * d / 2, y + w / 2, z + hb / 2), mat=rng.choice(SPINES),
              bevel=0.003, segs=1)
        y += w


# ======================================================================================
# Archive shelving (walls of ledgers)
# ======================================================================================
@asset("Tower_ArchiveShelf_3m", res=2048, collision="Box", edge=0.004, ao_dist=0.35)
def archive_shelf(A):
    """Double-sided archive shelving, 3 m (Y) x 0.6 m (X) x 2.6 m: dark walnut uprights and six shelves a side,
    every shelf full of leather-bound ledgers spine out (oxblood, green, black, tan), brass row labels.
    Head-high: blocks sight and movement (a shelving wall in the counting floor)."""
    rng = random.Random(7731)
    W, D, H = 3.0, 0.6, 2.6
    for y in (-W / 2 + 0.03, 0.0, W / 2 - 0.03):
        A.box((D, 0.05, H), at=(0, y, H / 2), mat="walnut_dark", bevel=0.005)
    A.box((0.02, W, H - 0.1), at=(0, 0, H / 2), mat="walnut_dark", bevel=0.0, segs=1)       # spine panel
    A.box((D + 0.04, W + 0.04, 0.05), at=(0, 0, H + 0.02), mat="walnut_dark", bevel=0.008)
    A.box((D, W, 0.1), at=(0, 0, 0.05), mat="walnut_dark", bevel=0.005)
    levels = [0.1 + i * 0.41 for i in range(6)]
    f = font()
    for i, z in enumerate(levels):
        A.box((D, W, 0.025), at=(0, 0, z + 0.0125), mat="walnut_dark", bevel=0.003)
        for face in (1, -1):
            for (ya, yb) in ((-W / 2 + 0.06, -0.03), (0.03, W / 2 - 0.06)):
                _book_row(A, face * (D / 2 - 0.005), ya, yb, z + 0.025, D / 2 - 0.03, rng, face=face)
            # brass row label on the shelf edge
            A.box((0.006, 0.12, 0.04), at=(face * (D / 2 + 0.003), -0.75, z + 0.0125), mat="brass_aged", bevel=0.001)
            A.box((0.006, 0.12, 0.04), at=(face * (D / 2 + 0.003), 0.75, z + 0.0125), mat="brass_aged", bevel=0.001)
    if f:
        for face in (1, -1):
            yaw = 90 if face > 0 else -90
            A.text("LEDGERS  1961 - 1974" if face > 0 else "ACCOUNTS  K - M", f, 0.06, 0.002,
                   at=(face * (D / 2 + 0.024), 0, H - 0.05), rot=(90, 0, yaw), mat="brass_aged")
    A.layout = {"Cover": True}
    A.view = (1.0, -0.55, 0.3)
    A.lens = 45


# ======================================================================================
# Filing wall
# ======================================================================================
@asset("Tower_FilingWall_2m", res=2048, collision="Box", edge=0.004, ao_dist=0.3)
def filing_wall(A):
    """A run of four tall steel filing cabinets back to back, 2 m (Y) x 0.75 m (X) x 1.9 m, bottle-green
    enamel with brass card holders and pulls on both faces; one drawer pulled out with hanging files."""
    W, D, H = 2.0, 0.75, 1.9
    A.box((D, W, H), at=(0, 0, H / 2), mat="t_cabinet", bevel=0.006)
    n = 4
    cw = W / n
    for face in (1, -1):
        for i in range(n):
            yc = -W / 2 + cw * (i + 0.5)
            for k in range(4):
                zc = 0.1 + k * 0.45 + 0.22
                if face > 0 and i == 2 and k == 2:
                    continue
                A.box((0.012, cw - 0.03, 0.42), at=(face * (D / 2 + 0.004), yc, zc), mat="t_cabinet", bevel=0.003)
                A.box((0.01, 0.07, 0.04), at=(face * (D / 2 + 0.012), yc, zc + 0.12), mat="brass_aged", bevel=0.002)
                A.box((0.008, 0.06, 0.03), at=(face * (D / 2 + 0.015), yc, zc + 0.12), mat="t_paper", bevel=0.0)
                A.box((0.03, 0.12, 0.018), at=(face * (D / 2 + 0.02), yc, zc + 0.02), mat="brass_aged", bevel=0.004)
    # the open drawer (face +X, cabinet 3, row 3) with files
    yc = -W / 2 + cw * 2.5
    zc = 0.1 + 2 * 0.45
    A.box((0.45, cw - 0.06, 0.02), at=(D / 2 + 0.2, yc, zc + 0.02), mat="t_cabinet", bevel=0.003)
    for s in (-1, 1):
        A.box((0.45, 0.012, 0.3), at=(D / 2 + 0.2, yc + s * (cw / 2 - 0.035), zc + 0.17), mat="t_cabinet", bevel=0.002)
    A.box((0.012, cw - 0.03, 0.42), at=(D / 2 + 0.43, yc, zc + 0.22), mat="t_cabinet", bevel=0.003)
    rng = random.Random(3)
    for j in range(14):
        x = D / 2 + 0.02 + j * 0.028
        A.box((0.004, cw - 0.1, 0.25 + rng.uniform(-0.02, 0.03)), at=(x, yc, zc + 0.16), mat="t_paper_old", bevel=0.0,
              rot=(0, rng.uniform(-6, 6), 0))
    A.layout = {"Cover": True}
    A.view = (1.0, -0.6, 0.3)
    A.lens = 50


# ======================================================================================
# Clerk desk
# ======================================================================================
@asset("Tower_Desk", res=2048, collision="Box", edge=0.004, ao_dist=0.3)
def clerk_desk(A):
    """Counting-floor clerk desk (1.6 m Y x 0.8 m X): walnut top on black steel legs, a 1.25 m high modesty /
    privacy screen at the back (-X, cover for a crouching player), a green-glass desk light, an old CRT-style
    ledger terminal glowing green, stacked ledgers and an open one with a fountain pen, an adding machine."""
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    W, D, Ht = 1.6, 0.8, 0.75
    A.box((D, W, 0.04), at=(0, 0, Ht - 0.02), mat="walnut_satin", bevel=0.006)
    for sy in (-1, 1):
        A.box((D - 0.08, 0.05, Ht - 0.04), at=(0, sy * (W / 2 - 0.05), (Ht - 0.04) / 2), mat="powder_black", bevel=0.004)
    A.box((0.03, W, 1.25), at=(-D / 2 + 0.015, 0, 0.625), mat="walnut_dark", bevel=0.004)      # screen / cover
    A.box((0.05, W + 0.02, 0.03), at=(-D / 2 + 0.015, 0, 1.25), mat="brass_aged", bevel=0.003)
    A.box((0.45, 0.42, 0.6), at=(0.05, W / 2 - 0.3, 0.33), mat="walnut_dark", bevel=0.005)    # drawer pedestal
    for k in range(3):
        A.box((0.02, 0.06, 0.012), at=(0.285, W / 2 - 0.3, 0.17 + k * 0.19), mat="brass_aged", bevel=0.002)
    # terminal
    A.box((0.36, 0.4, 0.34), at=(-0.15, -0.38, Ht + 0.17), mat="plastic_grey", bevel=0.02)
    A.box((0.32, 0.44, 0.04), at=(0.12, -0.38, Ht + 0.02), mat="plastic_grey", bevel=0.01)      # keyboard
    A.cur = "Emissive"
    A.box((0.01, 0.3, 0.22), at=(0.031, -0.38, Ht + 0.19), mat="t_screen_green", bevel=0.0)
    A.cur = "Body"
    # desk light
    A.cyl(0.07, 0.02, at=(-0.26, 0.55, Ht), mat="brass_aged", n=20)
    A.cyl(0.008, 0.32, at=(-0.26, 0.55, Ht + 0.02), mat="brass_aged", n=8)
    A.cyl(0.06, 0.26, at=(-0.2, 0.42, Ht + 0.33), axis="Y", mat="glass_green", n=20, bevel=0.005)
    A.cur = "Emissive"
    A.box((0.06, 0.22, 0.01), at=(-0.2, 0.42 - 0.13, Ht + 0.29), mat="t_warm_strip", bevel=0.0)
    A.cur = "Body"
    # ledgers: a stack and one open with a pen, an adding machine
    rng = random.Random(11)
    for k in range(4):
        A.box((0.3, 0.24, 0.04), at=(-0.18, 0.12 + rng.uniform(-0.02, 0.02), Ht + 0.02 + k * 0.042),
              mat=rng.choice(SPINES), bevel=0.004, rot=(0, 0, rng.uniform(-6, 6)))
    A.box((0.3, 0.46, 0.012), at=(0.15, 0.2, Ht + 0.006), mat="t_paper", bevel=0.002)
    A.box((0.31, 0.012, 0.016), at=(0.15, 0.2, Ht + 0.01), mat="t_spine_oxblood", bevel=0.002)
    A.cyl(0.005, 0.14, at=(0.18, 0.32, Ht + 0.016), axis="X", mat="lacquer_black", n=8, rot=(0, 0, 25))
    A.box((0.24, 0.2, 0.08), at=(0.1, 0.6, Ht + 0.04), mat="plastic_black", bevel=0.01)
    A.layout = {"Cover": True}
    A.view = (1.0, -0.7, 0.45)
    A.lens = 55


# ======================================================================================
# Reception desk (lobby)
# ======================================================================================
@asset("Tower_ReceptionDesk", res=4096, collision="Box", edge=0.005, ao_dist=0.4)
def reception_desk(A):
    """Lobby reception counter, 4.4 m (Y) x 1.2 m (X) x 1.15 m: black marble front with a brass inlay band
    and the front company's name in brass capitals (CRANE FIDUCIARY TRUST), walnut counter top, lower inner
    work top with a dark monitor and a desk bell, warm strip light under the top lip. Faces +X."""
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    W, D, H = 4.4, 1.2, 1.15
    A.box((0.12, W, H - 0.05), at=(D / 2 - 0.06, 0, (H - 0.05) / 2), mat="marble_black", bevel=0.006)
    for sy in (-1, 1):
        A.box((D, 0.12, H - 0.05), at=(0, sy * (W / 2 - 0.06), (H - 0.05) / 2), mat="marble_black", bevel=0.006)
    A.box((D * 0.55, W + 0.06, 0.05), at=(D / 2 - D * 0.55 / 2 + 0.03, 0, H - 0.025), mat="walnut_satin", bevel=0.008)
    A.box((0.6, W - 0.3, 0.04), at=(-0.15, 0, 0.78), mat="walnut_satin", bevel=0.005)          # inner work top
    A.box((0.012, W - 0.1, 0.03), at=(D / 2 + 0.002, 0, 0.32), mat="brass_polished", bevel=0.002)
    A.box((0.012, W - 0.1, 0.012), at=(D / 2 + 0.002, 0, H - 0.12), mat="brass_polished", bevel=0.001)
    A.box((0.4, 0.5, 0.32), at=(-0.25, -0.9, 0.96), mat="plastic_black", bevel=0.015)
    A.cyl(0.05, 0.05, at=(0.4, 1.4, H), mat="brass_polished", n=20, bevel=0.01)
    A.sphere(0.045, at=(0.4, 1.4, H + 0.05), mat="brass_polished", seg=16, rings=8, scale=(1, 1, 0.6))
    f = serif()
    if f:
        A.text("CRANE  FIDUCIARY  TRUST", f, 0.11, 0.008, at=(D / 2 + 0.004, 0, 0.55), rot=(90, 0, 90),
               mat="brass_polished")
    A.cur = "Emissive"
    A.box((0.02, W - 0.2, 0.012), at=(D / 2 - 0.2, 0, H - 0.06), mat="t_warm_strip", bevel=0.0)
    A.box((0.01, 0.36, 0.22), at=(-0.05, -0.9, 0.98), mat="t_screen", bevel=0.0)
    A.cur = "Body"
    A.layout = {"Cover": True}
    A.view = (1.0, -0.55, 0.3)
    A.lens = 40


# ======================================================================================
# Executive desk (Crane's office, penthouse)
# ======================================================================================
@asset("Tower_ExecDesk", res=4096, collision="Box", edge=0.005, ao_dist=0.35)
def exec_desk(A):
    """The Keeper's desk, 2.6 m (Y) x 1.1 m (X): a slab of black marble on two walnut pedestals, leather
    blotter with the master ledger open on it, fountain pen in a brass stand, a crystal tumbler, a rotary
    telephone, and a thin brass rail around the top. The sitting side faces -X."""
    W, D, H = 2.6, 1.1, 0.76
    for sy in (-1, 1):
        A.box((D - 0.1, 0.5, H - 0.07), at=(0, sy * (W / 2 - 0.3), (H - 0.07) / 2), mat="walnut_dark", bevel=0.006)
        for k in range(3):
            A.box((0.02, 0.1, 0.015), at=(-(D - 0.1) / 2 - 0.01, sy * (W / 2 - 0.3), 0.15 + k * 0.2), mat="brass_aged",
                  bevel=0.002)
    A.box((0.04, W - 1.2, 0.5), at=(D / 2 - 0.12, 0, 0.42), mat="walnut_dark", bevel=0.004)      # modesty panel
    A.box((D, W, 0.07), at=(0, 0, H - 0.035), mat="marble_black", bevel=0.008)
    A.box((D + 0.012, W + 0.012, 0.012), at=(0, 0, H - 0.066), mat="brass_aged", bevel=0.002)
    A.box((0.55, 0.8, 0.006), at=(-0.1, 0, H + 0.003), mat="leather_oxblood", bevel=0.002)
    # master ledger, open
    for s in (-1, 1):
        ob = A.box((0.36, 0.26, 0.022), at=(0, 0, 0), mat="t_paper_old", bevel=0.003)
        ob.matrix_world = Matrix.Translation((-0.1, s * 0.135, H + 0.017)) @ Matrix.Rotation(math.radians(-4 * s), 4, "X") @ ob.matrix_world
    A.box((0.37, 0.56, 0.008), at=(-0.1, 0, H + 0.008), mat="t_spine_oxblood", bevel=0.003)
    A.cyl(0.03, 0.04, at=(0.1, 0.6, H), mat="brass_polished", n=16, bevel=0.005)
    A.cyl(0.005, 0.15, at=(0.1, 0.6, H + 0.03), mat="lacquer_black", n=8, rot=(18, 0, 0))
    A.cyl(0.035, 0.09, at=(0.15, -0.75, H), mat="crystal", n=16, r2=0.04, bevel=0.003)
    A.box((0.22, 0.2, 0.08), at=(0.05, -1.0, H + 0.04), mat="lacquer_black", bevel=0.02)
    A.cyl(0.06, 0.012, at=(0.05, -1.0, H + 0.085), mat="lacquer_black", n=20)
    A.box((0.06, 0.24, 0.05), at=(0.05, -1.0, H + 0.11), mat="lacquer_black", bevel=0.02)
    A.layout = {"Cover": True}
    A.view = (-1.0, -0.65, 0.42)
    A.lens = 45


# ======================================================================================
# Server rack + vault door
# ======================================================================================
@asset("Tower_ServerRack", res=2048, collision="Box", edge=0.004, ao_dist=0.3)
def server_rack(A):
    """42U server cabinet, 0.6 m (Y) x 1.1 m (X) x 2.1 m: black frame, perforated front door with a smoked
    window, rows of blinking status LEDs (blue / green / amber) behind it, cable bundles at the top.
    Front faces +X."""
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    W, D, H = 0.6, 1.1, 2.1
    A.box((D, W, H), at=(0, 0, H / 2), mat="t_rack_black", bevel=0.006)
    A.box((0.02, W - 0.04, H - 0.1), at=(D / 2 + 0.01, 0, H / 2), mat="grille", bevel=0.004)
    A.box((0.02, 0.03, 0.3), at=(D / 2 + 0.03, -W / 2 + 0.06, 1.1), mat="steel", bevel=0.004)
    for k in range(4):
        A.cyl(0.03, 0.25, at=(-0.2 + k * 0.12, 0.12 - k * 0.05, H), mat="rubber", n=10)
    rng = random.Random(42 + int(W * 10))
    A.cur = "Emissive"
    for u in range(18):
        z = 0.15 + u * 0.1
        for k in range(rng.randint(2, 6)):
            y = -0.22 + rng.random() * 0.44
            A.box((0.005, 0.012, 0.008), at=(D / 2 + 0.022, y, z), mat=rng.choice(("t_led_blue", "t_led_green",
                                                                                     "t_led_green", "t_led_amber")),
                  bevel=0.0)
    A.cur = "Body"
    A.layout = {"Cover": True}
    A.view = (1.0, -0.8, 0.3)
    A.lens = 50


@asset("Tower_VaultDoor", res=4096, collision="Complex", edge=0.008, ao_dist=0.5)
def vault_door(A):
    """Vault wall section 4 m (Y) x 0.9 m (X) x 3.4 m with a 2.3 m round door standing open on its hinge
    (swung out toward +X, about 100 degrees), brushed steel with locking bolts, a five-spoke wheel and a
    time-lock dial; the doorway is walk-through (Solid false for the checker, complex collision in game)."""
    W, D, H = 4.0, 0.9, 3.4
    R = 1.15
    zc = 0.05 + R
    # wall section with a round opening (built from blocks around a 2.3 m square + corner fillers)
    A.box((D, (W - 2 * R) / 2, H), at=(0, -(R + (W - 2 * R) / 4), H / 2), mat="t_vault_dark", bevel=0.01)
    A.box((D, (W - 2 * R) / 2, H), at=(0, (R + (W - 2 * R) / 4), H / 2), mat="t_vault_dark", bevel=0.01)
    A.box((D, 2 * R, H - (zc + R)), at=(0, 0, (H + zc + R) / 2), mat="t_vault_dark", bevel=0.01)
    A.box((D, 2 * R, 0.05), at=(0, 0, 0.025), mat="t_vault_steel", bevel=0.004)
    # the round frame ring (lathed) on the front face
    ring = [(R - 0.02, 0.0), (R + 0.16, 0.0), (R + 0.16, 0.12), (R - 0.02, 0.12)]
    A.lathe(ring, at=(D / 2, 0, zc), mat="t_vault_steel", n=48, axis="X")
    # corner fillers so the square cut-out reads round from the front
    for sy in (-1, 1):
        for sz in (-1, 1):
            pts = [(sy * R, zc + sz * R)]
            for i in range(9):
                a = (math.pi / 2) * i / 8
                pts.append((sy * R * math.cos(a), zc + sz * R * math.sin(a)))
            A.prism(pts, D - 0.02, plane="YZ", mat="t_vault_dark", bevel=0.0)       # YZ prisms are centred in X
    # the door: a thick disc hinged at +Y, swung open ~100 degrees
    hinge_y = R + 0.05
    door = []
    door.append(A.cyl(R - 0.04, 0.55, at=(0, 0, 0), axis="X", mat="t_vault_steel", n=48, bevel=0.01))
    door.append(A.cyl(R * 0.62, 0.06, at=(0.55, 0, 0), axis="X", mat="t_vault_steel", n=40, bevel=0.006))
    for k in range(12):
        a = 2 * math.pi * k / 12
        door.append(A.cyl(0.05, 0.22, at=(0.2, (R - 0.02) * math.cos(a), (R - 0.02) * math.sin(a)), axis="X",
                          mat="chrome", n=12, bevel=0.004))
    door.append(A.cyl(0.06, 0.22, at=(0.6, 0, 0), axis="X", mat="chrome", n=16, bevel=0.005))
    for k in range(5):
        a = 2 * math.pi * k / 5
        ob = A.cyl(0.018, 0.46, at=(0, 0, 0), mat="chrome", n=8)
        ob.matrix_world = Matrix.Translation((0.76, 0, 0)) @ Matrix.Rotation(a, 4, "X") @ ob.matrix_world
        door.append(ob)
    door.append(A.cyl(0.11, 0.05, at=(0.6, 0.0, 0.55), axis="X", mat="brass_aged", n=24, bevel=0.004))
    door.append(A.box((0.4, 0.14, 0.5), at=(0.25, R - 0.1, 0), mat="t_vault_dark", bevel=0.01))
    Mopen = (Matrix.Translation((D / 2 + 0.02, hinge_y, zc)) @ Matrix.Rotation(math.radians(100), 4, "Z")
             @ Matrix.Translation((0, -hinge_y, 0)))
    for ob in door:
        ob.matrix_world = Mopen @ ob.matrix_world
    for z in (zc - 0.7, zc + 0.7):
        A.cyl(0.08, 0.5, at=(D / 2 + 0.02, hinge_y, z - 0.25), mat="t_vault_steel", n=16, bevel=0.005)
    f = font()
    if f:
        A.text("CRANE  FIDUCIARY  -  NO. 2", f, 0.09, 0.004, at=(D / 2 + 0.005, 0, zc + R + 0.32), rot=(90, 0, 90),
               mat="brass_aged")
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (1.0, -0.4, 0.25)
    A.lens = 35


# ======================================================================================
# Linear pendant light
# ======================================================================================
@asset("Tower_PendantLinear", res=1024, collision="None", edge=0.004, ao_dist=0.2)
def pendant_linear(A):
    """2.4 m linear pendant (long axis Y) hung on two thin cables from a ceiling 1.2 m above its top (point
    CeilingMount), black anodised extrusion with a warm diffuser underneath; Light point below the diffuser."""
    A.piece("Emissive", "Emissive", res=256, emissive=True)
    A.cur = "Body"
    L = 2.4
    A.box((0.08, L, 0.06), at=(0, 0, 0.03), mat="powder_black", bevel=0.004)
    for sy in (-1, 1):
        A.cyl(0.0015, 1.2, at=(0, sy * (L / 2 - 0.25), 0.06), mat="steel", n=6)
        A.cyl(0.03, 0.012, at=(0, sy * (L / 2 - 0.25), 1.248), mat="powder_black", n=16)
    A.cur = "Emissive"
    A.box((0.06, L - 0.04, 0.006), at=(0, 0, -0.002), mat="t_warm_strip", bevel=0.0)
    A.cur = "Body"
    A.point("CeilingMount", (0, 0, 1.26))
    A.point("Light", (0, 0, -0.05))
    A.layout = {"Solid": False, "Los": False, "Cover": False}
    A.view = (0.6, -1.0, 0.35)
    A.lens = 50


def make_images():
    """No decal images in this kit (labels are modelled text)."""
    return None
