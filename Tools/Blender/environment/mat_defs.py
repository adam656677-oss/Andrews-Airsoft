"""Tileable PBR material definitions (numpy, periodic, resolution independent).

Each ``m_<Id>(ctx)`` returns a dict:
  bc     (n,n,3) sRGB base colour
  h      (n,n)   height in metres
  rough  (n,n)   roughness
  metal  (n,n) or float
  ao     optional (n,n) extra occlusion multiplier
  nstr   normal strength multiplier (default 1)
  aor    AO radii in metres
  op     optional (n,n) opacity
Convention: wood grain and brushing run along U (image x).
"""
import math

import numpy as np

from envlib.tex import (F32, blur, cell_rand, col, cover, downward_smear, draw_polylines, lerp,
                        norm01, pct, ramp, sstep, warp, worley)

TAU = 2 * math.pi

# Id -> (TileMeters, seed, export height map)
SPECS = {
    'Plywood': (2.0, 11, False),
    'PlywoodPainted': (2.0, 12, False),
    'OSB': (1.5, 13, False),
    'Concrete': (2.4, 14, False),
    'ConcreteFloor': (4.0, 15, False),
    'Asphalt': (3.0, 16, True),
    'AsphaltWet': (3.0, 16, False),
    'Brick': (1.8, 18, True),
    'BrickDark': (1.8, 19, False),
    'MarbleBlack': (2.0, 20, False),
    'Walnut': (1.2, 21, False),
    'Brass': (0.5, 22, False),
    'PaintedSteel': (1.0, 23, False),
    'CorrodedMetal': (1.0, 24, False),
    'DiamondPlate': (0.6, 25, False),
    'Gravel': (1.5, 26, True),
    'Dirt': (2.0, 27, True),
    'Mud': (2.0, 28, False),
    'ForestFloor': (2.0, 29, True),
    'Grass': (2.0, 30, False),
    'Burlap': (0.5, 31, False),
    'Velvet': (1.0, 32, False),
    'Leather': (0.5, 33, False),
    'Carpet': (1.0, 34, False),
    'Rubber': (1.0, 35, False),
    'Netting': (1.0, 36, False),
    # extras used by the architecture / props kits
    'Timber': (2.0, 37, False),
    'Canvas': (1.0, 38, False),
    'Bark': (1.0, 39, True),
    'Straw': (1.0, 40, False),
    'Granite': (1.5, 41, False),
}


# ----------------------------------------------------------------------------
# shared building blocks
# ----------------------------------------------------------------------------
def wood_face(ctx, light, dark, ring_cyc, wild=0.35, knots=3, seed_shift=0):
    """Rotary/flat-cut softwood face; grain along x. Returns bc, h(0-1), late."""
    n = ctx.n
    w1 = ctx.noise(ctx.tile * 0.6, oct=3, rough=0.45, aniso=4.0)
    w2 = ctx.noise(ctx.tile * 0.12, oct=3, rough=0.5, aniso=6.0)
    w3 = ctx.noise(ctx.tile * 0.03, oct=2, rough=0.5, aniso=8.0)
    c = ctx.v * ring_cyc + w1 * wild * ring_cyc * 0.06 + w2 * 0.3 + w3 * 0.05
    f = c - np.floor(c)
    late = sstep(0.55, 0.85, f) * (1 - sstep(0.9, 1.0, f))
    early_var = ctx.n01(ctx.tile * 0.05, oct=4, aniso=10.0)
    fiber = ctx.noise(0.004, oct=3, rough=0.6, aniso=12.0)
    tone = ctx.n01(ctx.tile * 0.4, oct=3)
    bc = lerp(light, dark, np.clip(late * 0.7 + early_var * 0.3 + fiber * 0.05, 0, 1))
    bc = bc * (0.86 + 0.24 * tone)[..., None]
    h = late * 0.6 + fiber * 0.05 + early_var * 0.15
    return np.clip(bc, 0, 1).astype(F32), h.astype(F32), late, c


def scratches(ctx, count, len_m=(0.02, 0.2), ang_spread=math.pi, base_ang=0.0, width=1.0, curve=0.1):
    rg = ctx.rng()
    polys = []
    for _ in range(count):
        x, y = rg.random(2)
        L = (len_m[0] + rg.random() * (len_m[1] - len_m[0])) / ctx.tile
        a = base_ang + (rg.random() - 0.5) * ang_spread
        k = 8
        t = np.linspace(0, 1, k)
        bend = (rg.random() - 0.5) * curve
        px = x + np.cos(a) * L * t - np.sin(a) * L * bend * np.sin(t * math.pi)
        py = y + np.sin(a) * L * t + np.cos(a) * L * bend * np.sin(t * math.pi)
        polys.append(np.stack([px, py], 1))
    cov, _ = draw_polylines(ctx.n, polys, widths=[np.array([0.2, 1, 1, 0.3]) * width] * count)
    cov = blur(cov, max(0.6, ctx.n / 4096 * 1.2))
    return np.clip(cov * 1.5, 0, 1)


def dirt_layer(ctx, size_m=0.3, cov=0.35):
    a = ctx.n01(size_m, oct=5, rough=0.6)
    return cover(a, cov, soft=0.25)


def chips_mask(ctx, size_m, coverage, edge=0.03):
    a = ctx.noise(size_m, oct=4, rough=0.5) + ctx.noise(size_m * 6, oct=2, rough=0.5) * 0.9
    return cover(a, coverage, soft=edge)


def finish_grime(bc, rough, ao_like, amount=0.35, grime=(0.22, 0.2, 0.17)):
    g = np.clip((1 - ao_like) * amount * 2.5, 0, 1)
    return lerp(bc, col(grime), g), np.clip(rough + g * 0.1, 0, 1)


# ----------------------------------------------------------------------------
# woods
# ----------------------------------------------------------------------------
def m_Plywood(ctx):
    bc, h, late, c = wood_face(ctx, col('#d6b98f'), col('#b08455'), ring_cyc=17, wild=0.8, knots=0)
    sheet = ctx.n01(1.0, oct=2)
    bc = bc * (0.9 + 0.16 * sheet)[..., None]
    n = ctx.n
    # football patches (oval plugs) with different grain
    rg = ctx.rng()
    patch = np.zeros((n, n), F32)
    for _ in range(3):
        px, py = rg.random(2)
        dx = ((ctx.u - px + 0.5) % 1 - 0.5) * ctx.tile
        dy = ((ctx.v - py + 0.5) % 1 - 0.5) * ctx.tile
        d = (dx / 0.05) ** 2 + (dy / 0.022) ** 2
        patch = np.maximum(patch, sstep(1.05, 0.95, d))
    edge = sstep(0.0, 0.25, patch) * (1 - sstep(0.75, 1.0, patch))
    bc = lerp(bc, bc * col('#e6cfa3') / 0.8, patch * 0.35)
    bc = lerp(bc, col('#7a5532'), edge * 0.5)
    # weathering: greying + water marks
    weather = ctx.n01(0.5, oct=4)
    grey = (bc.mean(-1, keepdims=True) * 0.9 + 0.05)
    bc = lerp(bc, np.repeat(grey, 3, -1) * col('#c9c2b4'), cover(weather, 0.3, 0.4) * 0.18)
    stain = cover(ctx.n01(0.4, oct=3, aniso=0.5), 0.12, 0.4)
    bc = bc * (1 - 0.08 * stain)[..., None]
    # surface checks (thin cracks along grain)
    cr = cover(ctx.noise(0.15, oct=3, aniso=20.0), 0.015, 0.02) * cover(ctx.n01(0.3), 0.3, 0.1)
    bc = lerp(bc, col('#6a4a2c'), cr * 0.45)
    rough = 0.72 + 0.1 * late + 0.06 * weather - 0.04 * patch
    hm = h * 0.0006 - cr * 0.0008 - edge * 0.0003
    return dict(bc=bc, h=hm, rough=rough, metal=0.0, nstr=3.0, aor=(0.002, 0.006))


def m_PlywoodPainted(ctx):
    bc_w, h_w, late, c = wood_face(ctx, col('#d4b285'), col('#8f6038'), ring_cyc=26, wild=1.0, knots=0)
    od = col('#4b5126')
    tone = ctx.n01(0.6, oct=4)
    roller = ctx.n01(0.01, oct=3, rough=0.5)  # orange peel / roller stipple
    streak = ctx.n01(0.25, oct=3, aniso=0.15)  # vertical roller streaks
    paint = od * (0.88 + 0.16 * tone + 0.05 * roller - 0.05 * streak)[..., None]
    # sun fade / chalking
    fade = cover(ctx.n01(0.4, oct=5), 0.35, 0.35)
    paint = lerp(paint, col('#6d7048'), fade * 0.35)
    # chips revealing wood
    ch = chips_mask(ctx, 0.05, 0.08, 0.012)
    ch_small = chips_mask(ctx, 0.015, 0.03, 0.02)
    chips = np.clip(ch + ch_small, 0, 1)
    ring = np.clip(blur(chips, ctx.px(0.003)) * 1.5 - chips, 0, 1)
    wood = lerp(bc_w, col('#7c5a3a'), 0.25)
    bc = lerp(paint, wood, chips)
    bc = lerp(bc, col('#2e3018'), ring * 0.5)
    # dust / dirt
    d = dirt_layer(ctx, 0.35, 0.3)
    bc = lerp(bc, col('#6e6450'), d * 0.18)
    scr = scratches(ctx, 60, (0.02, 0.12), width=0.8)
    bc = lerp(bc, col('#8d8b6b'), scr * 0.5)
    rough = 0.62 + 0.08 * roller + 0.1 * fade + chips * 0.15 + scr * 0.1
    hm = h_w * 0.00045 * (1 - chips) + (1 - chips) * 0.00025 + roller * 0.00004 - scr * 0.00005 + h_w * chips * 0.0003
    return dict(bc=bc, h=hm, rough=rough, metal=0.0, aor=(0.002, 0.006))


def m_OSB(ctx):
    n = ctx.n
    h = np.full((n, n), -1.0, F32)
    bc = np.zeros((n, n, 3), F32)
    rough = np.zeros((n, n), F32)
    pal = [col('#c9a26a'), col('#b48a55'), col('#d6b57d'), col('#a07444'), col('#8a6239'), col('#c4955c')]
    for layer in range(3):
        rg = ctx.rng()
        wx = ctx.noise(0.3, oct=2) * 0.004
        wy = ctx.noise(0.3, oct=2) * 0.003
        U = (ctx.u + wx + rg.random()) % 1.0
        V = (ctx.v + wy + rg.random()) % 1.0
        cx = ctx.cyc(0.09)
        cy = ctx.cyc(0.025)
        F1, F2, ID = worley(n, cx, cy, rg, jitter=0.95, U=U, V=V, cellmetric=True)
        cnt = cx * cy
        hz = cell_rand(ID, cnt, rg)
        tone = cell_rand(ID, cnt, rg)
        ph = cell_rand(ID, cnt, rg)
        edge = sstep(0.0, 0.06, F2 - F1)
        hl = layer * 0.3 + hz * 0.6 + edge * 0.15
        top = hl > h
        g = 0.5 + 0.5 * np.sin(TAU * (V * ctx.cyc(0.002) + ph * 9 + ctx.noise(0.05, oct=2, aniso=6.0) * 0.6))
        c = np.zeros((n, n, 3), F32)
        idx = (tone * len(pal)).astype(int) % len(pal)
        palarr = np.stack(pal)
        c = palarr[idx] * (0.85 + 0.2 * g)[..., None]
        c = lerp(c * 0.6, c, edge)
        bc = np.where(top[..., None], c, bc)
        rough = np.where(top, 0.55 + 0.2 * tone, rough)
        h = np.where(top, hl, h)
    fine = ctx.noise(0.003, oct=3, aniso=6.0)
    bc = bc * (0.95 + 0.05 * fine)[..., None]
    dark = cover(ctx.n01(0.3, oct=4), 0.25, 0.3)
    bc = bc * (1 - 0.12 * dark)[..., None]
    hm = h * 0.0012 + fine * 0.00004
    return dict(bc=bc, h=hm, rough=rough + 0.08 * dark, metal=0.0, aor=(0.002, 0.008))


def m_Walnut(ctx):
    n = ctx.n
    leaves = 6
    lw = 1.0 / leaves
    li = np.floor(ctx.v / lw)
    lv = (ctx.v - li * lw) / lw
    mirror = (li % 2 == 1)
    lv2 = np.where(mirror, 1 - lv, lv)
    w1 = ctx.noise(0.35, oct=3, aniso=3.0)
    w2 = ctx.noise(0.06, oct=3, aniso=5.0)
    # cathedral figure: parabola-ish arches along x
    arch = 0.25 * np.cos(TAU * ctx.u * 2 + w1 * 0.8) ** 2
    c = (lv2 + arch) * 9 + w2 * 0.25 + w1 * 0.5
    f = c - np.floor(c)
    late = sstep(0.6, 0.9, f) * (1 - sstep(0.92, 1.0, f))
    pores = cover(ctx.noise(0.0015, oct=2, aniso=10.0), 0.12, 0.05)
    tone = ctx.n01(0.3, oct=3)
    base = ramp(np.clip(late * 0.8 + tone * 0.3, 0, 1), [(0, col('#7a5236')), (0.45, col('#5a3a25')), (1, col('#2f1d12'))])
    bc = base * (1 - 0.25 * pores)[..., None]
    # leaf tone variation & seams
    lt = np.random.default_rng(ctx.seed).random(leaves + 1).astype(F32)[li.astype(int)]
    bc = bc * (0.92 + 0.14 * lt)[..., None]
    seam = sstep(0.004, 0.0, np.minimum(lv, 1 - lv) * lw * ctx.tile / 0.4)
    bc = lerp(bc, col('#1e130b'), seam * 0.6)
    rough = 0.32 + 0.06 * pores + 0.05 * ctx.n01(0.2) + seam * 0.1
    hm = -pores * 0.00008 + late * 0.00002 - seam * 0.0002
    return dict(bc=bc, h=hm, rough=rough, metal=0.0, aor=(0.001, 0.003))


# ----------------------------------------------------------------------------
# concrete / masonry / stone
# ----------------------------------------------------------------------------
def m_Concrete(ctx):
    n = ctx.n
    mott = ctx.noise(0.6, oct=5, rough=0.55)
    mott2 = ctx.noise(0.08, oct=4, rough=0.6)
    speck = ctx.noise(0.003, oct=2, rough=0.7)
    base = col('#93918b')
    bc = base * (1 + 0.07 * mott + 0.03 * mott2 + 0.015 * speck)[..., None]
    bc = lerp(bc, col('#a29e94'), sstep(0.5, 1.5, mott)[..., None] * 0.4)
    h = mott2 * 0.0004 + speck * 0.00015
    # bug holes
    rg = ctx.rng()
    F1, F2, ID = worley(n, ctx.cyc(0.03), ctx.cyc(0.03), rg)
    rnd = cell_rand(ID, ctx.cyc(0.03) ** 2, rg)
    hole_r = np.where(rnd > 0.82, 0.0015 + (rnd - 0.82) * 0.02, 0)
    bug = sstep(1.0, 0.6, F1 * ctx.tile / np.maximum(hole_r, 1e-5)) * (hole_r > 0)
    h -= bug * 0.002
    bc = lerp(bc, col('#5d5b56'), bug * 0.6)
    # form panel seams at 1.2 m (both axes)
    def seam(c, period_m):
        d = np.abs(((c * ctx.tile / period_m) + 0.5) % 1.0 - 0.5) * period_m
        return sstep(0.003, 0.0, d)
    sx = seam(ctx.u, 1.2)
    sy = seam(ctx.v, 1.2)
    fin = np.maximum(sx, sy)
    h += fin * 0.0008
    bc = lerp(bc, col('#7e7c76'), fin * 0.5)
    # form tie holes on 0.6 m grid, offset 0.3
    k = 0.6 / ctx.tile
    dx = (((ctx.u - 0.125) / k + 0.5) % 1 - 0.5) * 0.6
    dy = (((ctx.v - 0.125) / k + 0.5) % 1 - 0.5) * 0.6
    d = np.sqrt(dx ** 2 + dy ** 2)
    cone = sstep(0.016, 0.010, d)
    plug = sstep(0.008, 0.006, d)
    ring = sstep(0.02, 0.016, d) - cone
    h -= cone * 0.006 - plug * 0.003
    bc = lerp(bc, col('#6a6762'), cone)
    bc = lerp(bc, col('#4c4a46'), plug)
    bc = lerp(bc, col('#86837c'), np.clip(ring, 0, 1) * 0.4)
    # rust/water streaks beneath tie holes
    st = downward_smear(cone, ctx.px(0.35), steps=20, decay=0.9)
    st = st * (0.5 + 0.5 * ctx.n01(0.05, oct=3, aniso=0.08))
    bc = lerp(bc, col('#7a6450'), np.clip(st * 0.5, 0, 1))
    # broad water stains / efflorescence (vertical)
    ws = cover(ctx.n01(0.5, oct=5, aniso=0.2), 0.3, 0.3)
    bc = bc * (1 - 0.14 * ws)[..., None]
    ef = cover(ctx.n01(0.2, oct=5, aniso=0.3), 0.06, 0.4)
    bc = lerp(bc, col('#c3c0b8'), ef * 0.35)
    rough = 0.88 + 0.06 * mott2 * 0.3 - 0.06 * ws + bug * 0.05
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.003, 0.012, 0.04), nstr=2.0)


def m_ConcreteFloor(ctx):
    n = ctx.n
    m1 = ctx.noise(1.2, oct=5, rough=0.55)
    m2 = ctx.noise(0.15, oct=4, rough=0.6)
    bc = col('#a3a199') * (1 + 0.06 * m1 + 0.03 * m2)[..., None]
    bc = lerp(bc, col('#8f8b82'), sstep(0.3, 1.6, -m1)[..., None] * 0.6)
    # exposed fine aggregate (polished)
    rg = ctx.rng()
    cs = ctx.cyc(0.012)
    F1, F2, ID = worley(n, cs, cs, rg)
    r = cell_rand(ID, cs * cs, rg)
    agg = sstep(0.004 / ctx.tile, 0.0025 / ctx.tile, F1) * (r > 0.55)
    tone = cell_rand(ID, cs * cs, rg)
    aggc = ramp(tone, [(0, col('#6f6c66')), (0.5, col('#b9b5ab')), (1, col('#8a7f70'))])
    bc = lerp(bc, aggc, agg * 0.55)
    # trowel swirls -> roughness + slight tone
    sw = ctx.noise(0.5, oct=2) * 3.0
    arcs = 0.5 + 0.5 * np.sin(TAU * (np.sqrt((ctx.u * 4 % 1 - 0.5) ** 2 + (ctx.v * 4 % 1 - 0.5) ** 2) * 6 + sw))
    trowel = arcs * ctx.n01(0.4, oct=3)
    bc = bc * (1 + 0.025 * (trowel - 0.5))[..., None]
    # hairline cracks
    rg2 = ctx.rng()
    cc = ctx.cyc(0.9)
    wU = (ctx.u + ctx.noise(0.3, oct=4) * 0.01) % 1
    wV = (ctx.v + ctx.noise(0.3, oct=4) * 0.01) % 1
    G1, G2, _ = worley(n, cc, cc, rg2, U=np.broadcast_to(wU, (n, n)), V=np.broadcast_to(wV, (n, n)))
    crack = sstep(0.0012 / ctx.tile, 0.0, G2 - G1) * cover(ctx.n01(0.6, oct=3), 0.35, 0.1)
    bc = lerp(bc, col('#5c5a55'), crack * 0.6)
    # stains (spills, tyre scuffs)
    st = cover(ctx.n01(0.35, oct=5), 0.12, 0.25)
    bc = bc * (1 - 0.15 * st)[..., None]
    rough = 0.22 + 0.1 * trowel + 0.08 * st + crack * 0.3 + 0.04 * norm01(m2)
    h = m2 * 0.00005 - crack * 0.0006 + agg * 0.00002
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.002, 0.006))


def asphalt_base(ctx):
    n = ctx.n
    h = np.zeros((n, n), F32)
    bc = np.zeros((n, n, 3), F32) + col('#2b2a28')
    binder = ctx.noise(0.004, oct=3, rough=0.6)
    h += binder * 0.0003
    stone_cov = np.zeros((n, n), F32)
    pal = [(0, col('#4a4946')), (0.4, col('#6d6b66')), (0.75, col('#8c8780')), (1, col('#9a8e80'))]
    for size, thr, z in ((0.014, 0.35, 0.002), (0.008, 0.25, 0.0015), (0.004, 0.0, 0.001)):
        rg = ctx.rng()
        cs = ctx.cyc(size)
        F1, F2, ID = worley(n, cs, cs, rg, jitter=1.0)
        keep = cell_rand(ID, cs * cs, rg) > thr
        dome = np.sqrt(np.clip(sstep(0.0, 0.45 * size / ctx.tile, F2 - F1), 0, 1)) * keep
        hz = dome * z * (0.6 + 0.4 * cell_rand(ID, cs * cs, rg))
        top = hz > h
        tone = cell_rand(ID, cs * cs, rg)
        c = ramp(tone, pal)
        bc = np.where((top & (dome > 0.15))[..., None], lerp(bc, c, sstep(0.15, 0.5, dome)), bc)
        h = np.maximum(h, hz)
        stone_cov = np.maximum(stone_cov, dome)
    # tar coats the stones partially (aged)
    tar = cover(ctx.n01(0.01, oct=3), 0.45, 0.2)
    bc = lerp(bc, col('#262523'), tar * 0.55)
    # large scale wear / patching
    patch = cover(ctx.n01(0.8, oct=4), 0.18, 0.08)
    bc = lerp(bc, col('#1f1e1d'), patch * 0.55)
    bc = bc * (1 + 0.12 * ctx.noise(0.5, oct=4))[..., None]
    # oil stains
    oil = cover(ctx.n01(0.25, oct=5), 0.07, 0.3)
    bc = lerp(bc, col('#151413'), oil * 0.5)
    # cracks
    rg = ctx.rng()
    cc = ctx.cyc(0.6)
    wU = (ctx.u + ctx.noise(0.25, oct=4) * 0.012) % 1
    wV = (ctx.v + ctx.noise(0.25, oct=4) * 0.012) % 1
    G1, G2, _ = worley(n, cc, cc, rg, U=np.broadcast_to(wU, (n, n)), V=np.broadcast_to(wV, (n, n)))
    cm = cover(ctx.n01(0.7, oct=3), 0.3, 0.1)
    crack = sstep(0.003 / ctx.tile, 0.0, G2 - G1) * cm
    h = h - crack * 0.006
    bc = lerp(bc, col('#121211'), crack * 0.85)
    rough = 0.86 + 0.06 * stone_cov - 0.15 * oil
    return bc, h, rough, crack, oil, patch


def m_Asphalt(ctx):
    bc, h, rough, crack, oil, patch = asphalt_base(ctx)
    dust = cover(ctx.n01(0.3, oct=5), 0.3, 0.3)
    bc = lerp(bc, col('#6a655c'), dust * 0.12 * (1 - crack)[..., None][..., 0])
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.002, 0.006, 0.02))


def m_AsphaltWet(ctx):
    bc, h, rough, crack, oil, patch = asphalt_base(ctx)
    lowf = ctx.noise(1.0, oct=4, rough=0.5)
    puddle = cover(-lowf, 0.22, 0.05)
    damp = cover(-lowf, 0.65, 0.3)
    bc = bc * (0.62 - 0.08 * puddle)[..., None]
    bc = lerp(bc, col('#141618'), puddle * 0.25)
    rough = np.clip(rough * (1 - 0.55 * damp), 0.25, 1) * (1 - puddle) + 0.03 * puddle
    level = pct(h, 70)
    h = lerp(h, np.full_like(h, level), puddle)
    # oil rainbow sheen is a shader effect; keep oil darker + smoother
    rough = np.where(oil > 0.5, rough * 0.7, rough)
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.002, 0.006, 0.02))


def bricks(ctx, pal, mortar_c, soot_amt):
    n = ctx.n
    nx, ny = 8, 24
    row = np.floor(ctx.v * ny)
    off = (row % 2) * 0.5
    X = ctx.u * nx + off
    colI = np.floor(X) % nx
    bx = X - np.floor(X)
    by = ctx.v * ny - row
    dxm = np.minimum(bx, 1 - bx) * 0.225
    dym = np.minimum(by, 1 - by) * 0.075
    BID = (row * nx + colI).astype(np.int32)
    BID = np.broadcast_to(BID, (n, n))
    rg = ctx.rng()
    cnt = nx * ny
    r1 = cell_rand(BID, cnt, rg)
    r2 = cell_rand(BID, cnt, rg)
    r3 = cell_rand(BID, cnt, rg)
    r4 = cell_rand(BID, cnt, rg)
    en = ctx.noise(0.012, oct=4, rough=0.6) * 0.0022 + ctx.noise(0.004, oct=2) * 0.0006
    inside = np.minimum(dxm, dym) - 0.005 + en
    face = sstep(-0.0005, 0.003, inside)
    # brick colour
    pal_arr = np.stack([p for p in pal])
    base = pal_arr[(r1 * len(pal)).astype(int) % len(pal)]
    mot = ctx.noise(0.03, oct=4, rough=0.55)
    sandy = ctx.noise(0.002, oct=2, rough=0.7)
    flash = sstep(0.6, 1.0, r2) * (1 - sstep(0.0, 0.5, np.abs(bx - 0.5) * 2)) * 0  # disabled
    bc_b = base * (1 + 0.08 * mot + 0.06 * sandy + (r3 - 0.5) * 0.18)[..., None]
    # burnt / darker ends on some bricks
    ends = sstep(0.25, 0.5, np.abs(bx - 0.5)) * (r4 > 0.7)
    bc_b = bc_b * (1 - 0.22 * ends)[..., None]
    mort = mortar_c * (1 + 0.1 * ctx.noise(0.01, oct=3) + 0.08 * sandy)[..., None]
    bc = lerp(mort, bc_b, face)
    # face tilt + pitting
    tilt = (r2 - 0.5) * 0.0012 * (bx - 0.5) + (r3 - 0.5) * 0.0008 * (by - 0.5)
    rgp = ctx.rng()
    cs = ctx.cyc(0.008)
    P1, P2, PID = worley(n, cs, cs, rgp)
    pr = cell_rand(PID, cs * cs, rgp)
    pits = sstep(0.0015 / ctx.tile, 0.0006 / ctx.tile, P1) * (pr > 0.85)
    h = face * (0.006 + tilt + mot * 0.0002 + sandy * 0.00008 - pits * 0.0012) + (1 - face) * (sandy * 0.0003)
    bc = lerp(bc, bc * 0.6, pits * face)
    # soot & efflorescence
    soot = cover(ctx.n01(0.5, oct=5, rough=0.6), 0.35, 0.35) * soot_amt
    bc = bc * (1 - 0.45 * soot)[..., None]
    eff = cover(ctx.n01(0.15, oct=5), 0.05, 0.4)
    bc = lerp(bc, col('#d8d2c4'), eff * 0.3 * face)
    rough = 0.82 + 0.06 * (1 - face) + 0.05 * sandy * 0.3 - 0.04 * soot
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.003, 0.01, 0.03))


def m_Brick(ctx):
    pal = [col('#8e3b26'), col('#a2492e'), col('#7c2f1f'), col('#b05a3b'), col('#93432b'), col('#6e2a1c'),
           col('#a8533a'), col('#5c2418')]
    return bricks(ctx, pal, col('#a19a8c'), 0.8)


def m_BrickDark(ctx):
    pal = [col('#3d2b27'), col('#4b3530'), col('#2f2421'), col('#56403a'), col('#433029'), col('#5e4a40')]
    return bricks(ctx, pal, col('#5a5753'), 0.5)


def m_MarbleBlack(ctx):
    n = ctx.n
    base = col('#141416')
    cloud = ctx.noise(0.5, oct=5, rough=0.6)
    bc = base * (1 + 0.25 * cloud)[..., None] + col('#0a0a0c') * 0
    veins = np.zeros((n, n), F32)
    for (k, m, w, a, wa) in ((2, 1, 0.010, 1.0, 0.25), (3, 2, 0.006, 0.8, 0.2), (5, 1, 0.004, 0.5, 0.15),
                             (7, 3, 0.003, 0.35, 0.1)):
        c = (ctx.u * m + ctx.v) * k + ctx.noise(1.5, oct=3, rough=0.45) * 0.1 * (k ** 0.5) + ctx.noise(0.3, oct=2) * 0.012 * k
        f = (c - np.floor(c)) - 0.5
        wid = w * k * (0.4 + 1.2 * ctx.n01(0.3, oct=3))
        line = np.exp(-(f / wid) ** 2) * (0.35 + 0.65 * ctx.n01(0.5, oct=3))
        veins = np.maximum(veins, line * a)
    web = np.exp(-(ctx.noise(0.15, oct=3) / 0.04) ** 2) * 0.18 * cover(ctx.n01(0.4), 0.3, 0.2)
    veins = np.clip(veins + web, 0, 1)
    vc = lerp(col('#8f8d88'), col('#e8e4dc'), np.clip(veins * 1.3 - 0.2, 0, 1))
    bc = lerp(bc, vc, sstep(0.05, 0.8, veins))
    rough = 0.07 + 0.04 * ctx.n01(0.3, oct=3) + 0.02 * veins
    h = -veins * 0.00002 + ctx.noise(0.02) * 0.000005
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.002,))


def m_Gravel(ctx):
    n = ctx.n
    h = ctx.noise(0.1, oct=4) * 0.002 - 0.004
    soil = col('#5b5045') * (1 + 0.15 * ctx.noise(0.2, oct=4))[..., None]
    bc = soil.copy()
    pal = [(0, col('#5f5b56')), (0.25, col('#8f8a80')), (0.45, col('#b0a690')), (0.6, col('#7d6a55')),
           (0.75, col('#c9c2b2')), (0.88, col('#6a5e52')), (1, col('#9a8f86'))]
    for size, z in ((0.036, 0.012), (0.024, 0.009), (0.015, 0.006)):
        rg = ctx.rng()
        cs = ctx.cyc(size)
        wU = (ctx.u + ctx.noise(size * 3, oct=1) * size / ctx.tile * 0.06) % 1
        wV = (ctx.v + ctx.noise(size * 3, oct=1) * size / ctx.tile * 0.06) % 1
        F1, F2, ID = worley(n, cs, cs, rg, jitter=1.0, U=np.broadcast_to(wU, (n, n)), V=np.broadcast_to(wV, (n, n)))
        cnt = cs * cs
        rz = cell_rand(ID, cnt, rg)
        R = 0.5 * (0.75 + 0.35 * cell_rand(ID, cnt, rg))
        e = F1 * ctx.tile / size / R
        e2 = sstep(0.0, 0.25, (F2 - F1) * ctx.tile / size)
        dome = np.sqrt(np.clip(1 - e ** 2.2, 0, 1)) * e2
        facet = ctx.noise(size * 0.6, oct=2) * 0.12
        hz = (dome * (0.7 + 0.3 * rz) + facet * dome) * z * 1.2 - z * 0.15 + rz * z * 0.25
        keep = cell_rand(ID, cnt, rg) > 0.12
        top = (hz > h) & (dome > 0.05) & keep
        tone = cell_rand(ID, cnt, rg)
        c = ramp(tone, pal) * (0.9 + 0.12 * ctx.noise(0.003, oct=2))[..., None]
        c = lerp(c * 0.7, c, dome)
        bc = np.where(top[..., None], c, bc)
        h = np.where(top, hz, h)
    dust = cover(ctx.n01(0.25, oct=4), 0.3, 0.3)
    bc = lerp(bc, col('#8a8070'), dust * 0.2)
    rough = 0.8 + 0.1 * ctx.n01(0.05)
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.004, 0.012, 0.03), aog=1.4)


def m_Dirt(ctx):
    n = ctx.n
    m = ctx.noise(0.6, oct=6, rough=0.58)
    clump = ctx.noise(0.02, oct=3, rough=0.6)
    bc = ramp(norm01(m), [(0, col('#4e3c2c')), (0.5, col('#6b5440')), (1, col('#8a7258'))])
    bc = bc * (1 + 0.08 * clump)[..., None]
    h = m * 0.004 + clump * 0.0012
    # pebbles
    rg = ctx.rng()
    cs = ctx.cyc(0.02)
    F1, F2, ID = worley(n, cs, cs, rg)
    keep = cell_rand(ID, cs * cs, rg) > 0.8
    rr = 0.002 + cell_rand(ID, cs * cs, rg) * 0.005
    peb = np.sqrt(np.clip(1 - (F1 * ctx.tile / rr) ** 2, 0, 1)) * keep
    pc = ramp(cell_rand(ID, cs * cs, rg), [(0, col('#6b665e')), (0.5, col('#8b8378')), (1, col('#a29a8a'))])
    bc = lerp(bc, pc, sstep(0.0, 0.3, peb))
    h = np.maximum(h, h + peb * rr * 0.8)
    # dry cracks
    rg2 = ctx.rng()
    cc = ctx.cyc(0.12)
    G1, G2, _ = worley(n, cc, cc, rg2)
    crack = sstep(0.0025 / ctx.tile, 0.0, G2 - G1) * cover(ctx.n01(0.5), 0.35, 0.15)
    h -= crack * 0.003
    bc = lerp(bc, col('#2e241b'), crack * 0.6)
    # organic specks / tiny twigs
    org = cover(ctx.noise(0.004, oct=2), 0.04, 0.05)
    bc = lerp(bc, col('#2c2016'), org * 0.6)
    rough = 0.88 + 0.05 * ctx.n01(0.1) - peb * 0.1
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.003, 0.01, 0.03))


def m_Mud(ctx):
    n = ctx.n
    m = ctx.noise(0.5, oct=6, rough=0.55)
    rip = ctx.noise(0.08, oct=3, rough=0.5)
    clump = ctx.noise(0.015, oct=3, rough=0.6)
    h = m * 0.008 + rip * 0.002 + clump * 0.0006
    wet = cover(-blur(h, ctx.px(0.03)), 0.4, 0.25)
    bc = ramp(norm01(m + rip * 0.3), [(0, col('#2e2117')), (0.5, col('#45331f')), (1, col('#5e4a33'))])
    bc = bc * (1 - 0.35 * wet)[..., None]
    # puddles in deepest areas
    pud = cover(-blur(h, ctx.px(0.05)), 0.12, 0.05)
    h = lerp(h, np.full_like(h, pct(h, 14)), pud)
    bc = lerp(bc, col('#1d160f'), pud * 0.5)
    # straw bits
    st = scratches(ctx, 120, (0.02, 0.08), width=1.5, curve=0.2)
    bc = lerp(bc, col('#7d6a43'), st * 0.5)
    rough = np.clip(0.65 - 0.45 * wet - 0.2 * pud + 0.1 * clump * 0.3, 0.04, 1)
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.004, 0.015))


def leaf_sprite(sz_px, rg, kind):
    """Returns (rgb, alpha, height) sprite of a leaf at a random rotation."""
    s = int(sz_px)
    y, x = np.mgrid[0:s, 0:s].astype(F32)
    x = (x + 0.5) / s - 0.5
    y = (y + 0.5) / s - 0.5
    a = rg.random() * TAU
    xr = x * math.cos(a) + y * math.sin(a)
    yr = -x * math.sin(a) + y * math.cos(a)
    t = xr / 0.46 + 0.5  # along midrib 0..1
    lob = 5 + int(rg.random() * 3)
    if kind == 'oak':
        w = np.clip(np.sin(np.clip(t, 0, 1) * math.pi), 0, 1) ** 0.7 * (0.085 + 0.06 * np.abs(np.sin(t * math.pi * lob)))
    else:  # beech-like
        w = np.clip(np.sin(np.clip(t, 0, 1) * math.pi), 0, 1) ** 0.9 * 0.12 * (1 + 0.04 * np.sin(t * 40))
    inside = (t > 0) & (t < 1)
    alpha = sstep(0.004, -0.006, np.abs(yr) - w) * inside
    stem = (np.abs(yr) < 0.008) & (t > -0.12) & (t <= 0)
    alpha = np.maximum(alpha, stem.astype(F32))
    vein = np.exp(-(yr / 0.006) ** 2) + 0.5 * np.exp(-((np.abs(yr) * 1.4 - (t * 0.6 % 0.12)) / 0.008) ** 2) * (np.abs(yr) < w)
    curl = (1 - (yr / np.maximum(w, 1e-3)) ** 2).clip(0, 1) * 0.6 + rg.random() * 0.4
    hue = rg.random()
    base = ramp(np.array(hue, F32), [(0, col('#6b3d1c')), (0.3, col('#8a5426')), (0.55, col('#a5702f')),
                                      (0.75, col('#5c3a1e')), (0.9, col('#b08a3c')), (1, col('#3e2a18'))])
    rgb = np.broadcast_to(base, (s, s, 3)) * (1 - 0.25 * vein.clip(0, 1))[..., None]
    spots = (np.sin(xr * 90 + a) * np.sin(yr * 70)) > 0.85
    rgb = rgb * (1 - 0.2 * spots)[..., None]
    hgt = alpha * (0.4 + 0.6 * curl) - vein.clip(0, 1) * 0.1 * alpha
    return rgb.astype(F32), alpha.astype(F32), hgt.astype(F32)


def m_ForestFloor(ctx):
    n = ctx.n
    m = ctx.noise(0.4, oct=6)
    bc = ramp(norm01(m), [(0, col('#2a1e14')), (0.6, col('#3e2d1e')), (1, col('#54412b'))])
    h = m * 0.004
    rg = ctx.rng()
    # twigs under the leaves
    polys = []
    for _ in range(140):
        x, y = rg.random(2)
        L = (0.05 + rg.random() * 0.3) / ctx.tile
        a = rg.random() * TAU
        k = 10
        t = np.linspace(0, 1, k)
        jit = np.cumsum(rg.standard_normal(k) * 0.08)
        px = x + np.cos(a + jit * 0.3) * L * t
        py = y + np.sin(a + jit * 0.3) * L * t
        polys.append(np.stack([px, py], 1))
    cov, _ = draw_polylines(n, polys, widths=[1.0] * len(polys))
    tw = np.clip(blur(cov, ctx.px(0.0025)) * ctx.px(0.006), 0, 1)
    bc = lerp(bc, col('#4a3524'), tw)
    h = h + tw * 0.004
    # leaves (several layers)
    count = int(4200 * (ctx.tile / 2.0) ** 2)
    hl = h.copy()
    for i in range(count):
        size = ctx.px(0.10 + rg.random() * 0.09)
        if size < 4:
            size = 4
        rgb, al, hg = leaf_sprite(size, rg, 'oak' if rg.random() < 0.6 else 'beech')
        x = rg.random() * n
        y = rg.random() * n
        layer = 0.004 + i / count * 0.01
        s = rgb.shape[0]
        ys = (np.arange(s) + int(y)) % n
        xs = (np.arange(s) + int(x)) % n
        ix = np.ix_(ys, xs)
        cur = hl[ix]
        newh = layer + hg * 0.004
        m_ = (al > 0.5) & (newh > cur)
        a3 = (al * m_)[..., None]
        bc[ix] = bc[ix] * (1 - a3) + rgb * a3
        hl[ix] = np.where(m_, newh, cur)
    h = hl
    # moss patches
    moss = cover(ctx.n01(0.3, oct=5), 0.08, 0.2) * sstep(0.01, 0.0, h - pct(h, 40))
    bc = lerp(bc, col('#4a5a26'), moss * 0.7)
    bc = bc * (1 + 0.1 * ctx.noise(0.5, oct=3))[..., None]
    rough = 0.82 + 0.1 * ctx.n01(0.1)
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.004, 0.012, 0.03), aog=1.3)


def m_Grass(ctx):
    n = ctx.n
    rg = ctx.rng()
    soil = ramp(ctx.n01(0.3, oct=5), [(0, col('#3b2f20')), (1, col('#5a4a33'))])
    thatch_c = col('#8c7a4a')
    bc = lerp(soil, thatch_c, 0.35)
    h = np.zeros((n, n), F32)
    clump = ctx.n01(0.35, oct=4)
    dry = ctx.n01(0.8, oct=4)
    layers = [(0.25, 9000, col('#8a7d4c'), col('#6b6a38')), (0.6, 14000, col('#5b7030'), col('#7f8a3c')),
              (1.0, 9000, col('#4f6a24'), col('#86963f'))]
    area = (ctx.tile / 2.0) ** 2
    for li, (z, cnt, c0, c1) in enumerate(layers):
        cnt = int(cnt * area)
        polys, ws, vals = [], [], []
        xs = rg.random(cnt)
        ys = rg.random(cnt)
        for i in range(cnt):
            L = (0.02 + rg.random() * 0.05) / ctx.tile
            a = rg.random() * TAU
            bend = (rg.random() - 0.5) * 0.6
            t = np.linspace(0, 1, 6)
            ang = a + bend * t
            px = xs[i] + np.cumsum(np.cos(ang)) * L / 6
            py = ys[i] + np.cumsum(np.sin(ang)) * L / 6
            polys.append(np.stack([px, py], 1))
            vals.append(rg.random())
        cov, val = draw_polylines(n, polys, widths=[np.array([1.0, 0.8, 0.3])] * cnt, values=vals)
        sig = max(0.5, ctx.px(0.0012))
        covb = blur(cov, sig)
        valb = blur(val, sig)
        t = np.clip(valb / np.maximum(covb, 1e-4), 0, 1)
        a = np.clip(covb * ctx.px(0.0025) * 1.2, 0, 1) * (0.55 + 0.6 * clump if li > 0 else 1)
        a = np.clip(a, 0, 1)
        gc = lerp(c0, c1, t)
        gc = lerp(gc, col('#9c8f52'), (dry * 0.6 * (1 - li * 0.3))[..., None][..., 0])
        bc = lerp(bc, gc, a)
        h = np.maximum(h, a * (0.005 + z * 0.02))
    bc = bc * (0.9 + 0.2 * ctx.n01(0.15, oct=3))[..., None]
    rough = 0.78 + 0.12 * ctx.n01(0.05)
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.003, 0.01), aog=1.2, nstr=0.6)


# ----------------------------------------------------------------------------
# metals
# ----------------------------------------------------------------------------
def m_Brass(ctx):
    n = ctx.n
    brush = ctx.noise(0.0015, oct=3, rough=0.7, aniso=40.0)
    brush2 = ctx.noise(0.01, oct=2, aniso=30.0)
    base = col('#d4b46e')
    bc = base * (1 + 0.03 * brush + 0.04 * brush2)[..., None]
    tarn = cover(ctx.n01(0.2, oct=4, rough=0.5), 0.3, 0.5)
    tarn2 = cover(ctx.n01(0.06, oct=3), 0.2, 0.5) * tarn
    bc = lerp(bc, col('#8a6b3a'), tarn * 0.55)
    bc = lerp(bc, col('#4e4630'), tarn2 * 0.5)
    scr = scratches(ctx, 70, (0.01, 0.1), width=0.8)
    bc = lerp(bc, col('#f0d79a'), scr * 0.4)
    rough = 0.28 + 0.05 * brush2 + 0.2 * tarn + 0.15 * tarn2 - 0.08 * scr
    metal = 1.0 - 0.25 * tarn2
    h = brush * 0.000008 - scr * 0.00002
    return dict(bc=bc, h=h, rough=rough, metal=metal, aor=(0.001,))


def m_PaintedSteel(ctx):
    n = ctx.n
    paint = col('#5b6356')
    peel = ctx.noise(0.004, oct=2, rough=0.5)
    tone = ctx.noise(0.4, oct=4)
    bc = paint * (1 + 0.05 * tone + 0.02 * peel)[..., None]
    fade = cover(ctx.n01(0.3, oct=5), 0.3, 0.3)
    bc = lerp(bc, col('#78806f'), fade * 0.25)
    chips = np.clip(chips_mask(ctx, 0.04, 0.06, 0.01) + chips_mask(ctx, 0.012, 0.025, 0.015), 0, 1)
    halo = np.clip(blur(chips, ctx.px(0.004)) * 2.0 - chips, 0, 1)
    steel = col('#7c7b77') * (1 + 0.1 * ctx.noise(0.003))[..., None]
    rust = col('#7a4026') * (1 + 0.2 * ctx.noise(0.01, oct=3))[..., None]
    inner = sstep(0.4, 0.9, blur(chips, ctx.px(0.002)))
    chipc = lerp(rust, steel, inner * cover(ctx.n01(0.05), 0.5, 0.2))
    bc = lerp(bc, chipc, chips)
    bc = lerp(bc, col('#6b3a22'), halo * 0.5)
    bleed = downward_smear(np.clip(chips + halo * 0.5, 0, 1), ctx.px(0.25), steps=24, decay=0.9)
    bleed *= 0.5 + 0.5 * ctx.n01(0.02, oct=3, aniso=0.1)
    bc = lerp(bc, col('#7d4a2c'), np.clip(bleed * 0.45, 0, 1) * (1 - chips))
    scr = scratches(ctx, 80, (0.01, 0.12), width=0.8, curve=0.03)
    bc = lerp(bc, col('#9b9c95'), scr * 0.5)
    g = dirt_layer(ctx, 0.25, 0.3)
    bc = lerp(bc, col('#3f3b33'), g * 0.15)
    is_metal = chips * inner * cover(ctx.n01(0.05), 0.5, 0.2)
    metal = np.clip(is_metal + scr * 0.6, 0, 1)
    rough = 0.48 + 0.06 * peel + 0.12 * fade + chips * 0.3 - is_metal * 0.3 + bleed * 0.1
    h = (1 - chips) * 0.0002 + peel * 0.000008 - scr * 0.00002 - chips * ctx.noise(0.005) * 0.00003
    return dict(bc=bc, h=h, rough=rough, metal=metal, aor=(0.001, 0.004))


def m_CorrodedMetal(ctx):
    n = ctx.n
    rg = ctx.rng()
    cs = ctx.cyc(0.05)
    wU = (ctx.u + ctx.noise(0.05, oct=3) * 0.01) % 1
    wV = (ctx.v + ctx.noise(0.05, oct=3) * 0.01) % 1
    F1, F2, ID = worley(n, cs, cs, rg, U=np.broadcast_to(wU, (n, n)), V=np.broadcast_to(wV, (n, n)))
    flake = sstep(0.0, 0.0035 / ctx.tile, F2 - F1)
    fz = cell_rand(ID, cs * cs, rg)
    lay = ctx.noise(0.25, oct=5, rough=0.5)
    deep = cover(lay, 0.5, 0.2)
    pits_n = ctx.noise(0.002, oct=2, rough=0.7)
    pits = cover(-pits_n, 0.08, 0.05)
    bc = ramp(norm01(lay + fz * 0.6 * flake), [(0, col('#2d1a10')), (0.35, col('#5a2e18')), (0.6, col('#8a4522')),
                                                (0.8, col('#a65d2c')), (1, col('#c07a3e'))])
    bc = bc * (1 + 0.06 * ctx.noise(0.004, oct=2))[..., None]
    bc = lerp(bc, col('#1c120c'), pits * 0.5)
    # remnant paint + bare steel patches
    paint = cover(ctx.n01(0.3, oct=4, rough=0.55), 0.12, 0.03)
    steel = cover(ctx.n01(0.15, oct=4), 0.08, 0.05) * (1 - paint)
    bc = lerp(bc, col('#4f5a52'), paint)
    bc = lerp(bc, col('#56514b'), steel)
    h = lay * 0.0006 + flake * fz * 0.0004 * deep - pits * 0.0006 + paint * 0.0006
    metal = steel * 0.8
    rough = 0.86 + 0.08 * fz - steel * 0.35 - paint * 0.25
    return dict(bc=bc, h=h, rough=rough, metal=metal, aor=(0.002, 0.008))


def m_DiamondPlate(ctx):
    n = ctx.n
    K = 20  # lugs per tile (30 mm pitch)
    X = ctx.u * K
    Y = ctx.v * K
    i = np.floor(X)
    j = np.floor(Y)
    lx = (X - i - 0.5)
    ly = (Y - j - 0.5)
    sgn = np.where(((i + j) % 2) == 0, 1.0, -1.0).astype(F32)
    c = math.cos(math.pi / 4)
    xr = (lx + sgn * ly) * c
    yr = (-sgn * lx + ly) * c
    a, b = 0.42, 0.085
    d = (np.abs(xr) / a) ** 1.6 + (np.abs(yr) / b) ** 2
    lug = sstep(1.0, 0.55, d)
    lugt = np.sqrt(np.clip(1 - d, 0, 1))
    h = lug * 0.0012 + lugt * 0.0004
    base = col('#8f9396')
    mill = ctx.noise(0.002, oct=2, rough=0.6)
    bc = base * (1 + 0.04 * mill + 0.06 * ctx.noise(0.2, oct=4))[..., None]
    wear = lug * sstep(0.3, 0.9, lugt)
    bc = lerp(bc, col('#b8bcbe'), wear * 0.5)
    dirt = (1 - lug) * cover(ctx.n01(0.08, oct=5), 0.5, 0.3)
    bc = lerp(bc, col('#4a453c'), dirt * 0.6)
    rust = cover(ctx.n01(0.06, oct=6), 0.06, 0.2) * (1 - wear)
    bc = lerp(bc, col('#6e3c22'), rust * 0.7)
    scr = scratches(ctx, 60, (0.02, 0.15), width=0.8)
    bc = lerp(bc, col('#c8cacc'), scr * 0.4)
    metal = np.clip(1 - rust - dirt * 0.6, 0, 1)
    rough = 0.45 - wear * 0.2 + dirt * 0.35 + rust * 0.4 + 0.05 * mill
    return dict(bc=bc, h=h, rough=rough, metal=metal, aor=(0.001, 0.004))


# ----------------------------------------------------------------------------
# fabrics / soft
# ----------------------------------------------------------------------------
def m_Burlap(ctx):
    n = ctx.n
    K = ctx.cyc(0.004)  # thread pitch 4 mm
    wob_u = ctx.noise(0.05, oct=3) * 0.18 / K
    wob_v = ctx.noise(0.05, oct=3) * 0.18 / K
    U = ctx.u + wob_u
    V = ctx.v + wob_v
    X = U * K
    Y = V * K
    i = np.floor(X)
    j = np.floor(Y)
    fx = X - i - 0.5
    fy = Y - j - 0.5
    rg = ctx.rng()
    thick_i = rg.random(K + 2).astype(F32)
    thick_j = rg.random(K + 2).astype(F32)
    ti = thick_i[(i % K).astype(int)]
    tj = thick_j[(j % K).astype(int)]
    slub_x = ctx.n01(0.03, oct=2, aniso=0.2)
    slub_y = ctx.n01(0.03, oct=2, aniso=5.0)
    wi = 0.28 + 0.12 * ti + 0.1 * slub_x  # warp half width (vertical threads)
    wj = 0.28 + 0.12 * tj + 0.1 * slub_y
    pw = np.clip(1 - (fx / wi) ** 2, 0, 1) ** 0.5
    pf = np.clip(1 - (fy / wj) ** 2, 0, 1) ** 0.5
    par = ((i + j) % 2) * 2 - 1
    und_w = 0.5 + 0.5 * par * np.cos(math.pi * fy * 1.0) * 1.0
    und_f = 0.5 - 0.5 * par * np.cos(math.pi * fx * 1.0)
    hw = pw * (0.45 + 0.55 * und_w)
    hf = pf * (0.45 + 0.55 * und_f)
    warpTop = hw > hf
    hh = np.maximum(hw, hf)
    fib = np.where(warpTop, ctx.noise(0.0008, oct=2, aniso=0.1), ctx.noise(0.0008, oct=2, aniso=10.0))
    hair = cover(ctx.noise(0.002, oct=3, rough=0.7), 0.1, 0.1)
    tone_t = np.where(warpTop, ti, tj)
    base = ramp(tone_t * 0.6 + 0.2 * ctx.n01(0.2), [(0, col('#8a6d45')), (0.5, col('#a68a5c')), (1, col('#bfa274'))])
    bc = base * (0.55 + 0.45 * hh + 0.06 * fib)[..., None]
    gap = (hh < 0.05).astype(F32)
    bc = lerp(bc, col('#2a2014'), gap * 0.75)
    bc = lerp(bc, col('#c8ae80'), hair * 0.25)
    stain = cover(ctx.n01(0.15, oct=5), 0.2, 0.3)
    bc = bc * (1 - 0.12 * stain)[..., None]
    h = hh * 0.0012 + fib * 0.00005 + hair * 0.0001
    rough = 0.9 + 0.05 * hair
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.0008, 0.002), aog=1.2)


def m_Velvet(ctx):
    pile = ctx.noise(0.0008, oct=2, rough=0.6)
    crush = ctx.noise(0.12, oct=5, rough=0.6)
    crush2 = ctx.noise(0.03, oct=3, aniso=3.0)
    base = col('#5e1220')
    bc = base * (1 + 0.18 * crush + 0.08 * crush2 + 0.03 * pile)[..., None]
    bc = lerp(bc, col('#8a2a38'), sstep(0.8, 2.2, crush)[..., None][..., 0] * 0.4)
    rough = 0.82 + 0.06 * crush2 * 0.3 - 0.06 * sstep(0.5, 2.0, crush)
    h = crush * 0.00015 + crush2 * 0.00006 + pile * 0.00001
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.002,), nstr=1.0)


def m_Leather(ctx):
    n = ctx.n
    rg = ctx.rng()
    cs = ctx.cyc(0.0018)
    wU = (ctx.u + ctx.noise(0.01, oct=2) * 0.0006 / ctx.tile) % 1
    wV = (ctx.v + ctx.noise(0.01, oct=2) * 0.0006 / ctx.tile) % 1
    F1, F2, ID = worley(n, cs, cs, rg, U=np.broadcast_to(wU, (n, n)), V=np.broadcast_to(wV, (n, n)))
    peb = np.sqrt(np.clip(sstep(0.0, 0.0008 / ctx.tile, F2 - F1), 0, 1))
    wr = ctx.noise(0.04, oct=4, aniso=3.0)
    crease = np.exp(-(ctx.noise(0.08, oct=3) / 0.05) ** 2) * cover(ctx.n01(0.3), 0.5, 0.2)
    tone = ctx.noise(0.2, oct=4)
    bc = col('#3e2618') * (1 + 0.1 * tone)[..., None]
    bc = lerp(bc * 0.7, bc * 1.15, peb)
    bc = lerp(bc, col('#1d110a'), crease * 0.5)
    worn = cover(ctx.n01(0.15, oct=5), 0.2, 0.3) * peb
    bc = lerp(bc, col('#6a4630'), worn * 0.4)
    h = peb * 0.00012 + wr * 0.0001 - crease * 0.0003
    rough = 0.55 - 0.1 * peb - 0.1 * worn + crease * 0.1
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.0006, 0.002))


def m_Carpet(ctx):
    n = ctx.n
    P = 4  # pattern repeats per tile (25 cm)
    x = (ctx.u * P) % 1 - 0.5
    y = (ctx.v * P) % 1 - 0.5
    dia = np.abs(x) + np.abs(y)
    gold_line = sstep(0.02, 0.008, np.abs(dia - 0.42)) + sstep(0.012, 0.004, np.abs(dia - 0.36))
    inner = sstep(0.26, 0.24, dia)
    medal = sstep(0.09, 0.07, np.sqrt(x * x + y * y)) - sstep(0.05, 0.035, np.sqrt(x * x + y * y))
    flor = sstep(0.04, 0.025, np.abs(np.abs(x) - np.abs(y))) * inner * (dia > 0.12)
    corner = sstep(0.05, 0.035, np.sqrt((np.abs(x) - 0.5) ** 2 + (np.abs(y) - 0.5) ** 2))
    bc = col('#5a0f16') * (1 + 0.0 * x)[..., None]
    bc = lerp(bc, col('#3a0a10'), inner * 0.8)
    bc = lerp(bc, col('#b08a3a'), np.clip(gold_line + medal + corner, 0, 1))
    bc = lerp(bc, col('#1a1210'), flor * 0.8)
    # loop pile
    rg = ctx.rng()
    cs = ctx.cyc(0.0025)
    F1, F2, ID = worley(n, cs, cs, rg)
    loop = np.sqrt(np.clip(1 - (F1 * ctx.tile / 0.0014) ** 2, 0, 1))
    tufts = cell_rand(ID, cs * cs, rg)
    bc = bc * (0.72 + 0.28 * loop + 0.08 * (tufts - 0.5))[..., None]
    wear = cover(ctx.n01(0.4, oct=4), 0.3, 0.3)
    bc = lerp(bc, bc * 1.15 + 0.02, wear * 0.3)
    dirt = cover(ctx.n01(0.1, oct=5), 0.15, 0.3)
    bc = bc * (1 - 0.15 * dirt)[..., None]
    h = loop * 0.0015 + tufts * 0.0002
    rough = 0.93 + 0.0 * loop
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.001, 0.003), aog=0.8)


def m_Rubber(ctx):
    n = ctx.n
    st = ctx.noise(0.0012, oct=2, rough=0.6)
    tone = ctx.noise(0.3, oct=4)
    bc = col('#1d1d1c') * (1 + 0.08 * tone + 0.04 * st)[..., None]
    scuff = scratches(ctx, 120, (0.02, 0.2), width=2.5, curve=0.3)
    bc = lerp(bc, col('#4a4846'), scuff * 0.35)
    dust = cover(ctx.n01(0.15, oct=5), 0.3, 0.3)
    bc = lerp(bc, col('#5a564e'), dust * 0.25)
    bloom = cover(ctx.n01(0.4, oct=4), 0.2, 0.4)
    bc = lerp(bc, col('#383735'), bloom * 0.3)
    rough = 0.78 + 0.08 * st * 0.3 + 0.1 * dust - 0.15 * scuff
    h = st * 0.00003 - scuff * 0.00005
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.001,))


def m_Netting(ctx):
    n = ctx.n
    K = 20  # 50 mm diamond mesh
    a = (ctx.u + ctx.v) * K
    b = (ctx.u - ctx.v) * K
    wob = ctx.noise(0.2, oct=3) * 0.04
    da = np.abs((a + wob) - np.round(a + wob)) / K / math.sqrt(2) * ctx.tile
    db = np.abs((b - wob) - np.round(b - wob)) / K / math.sqrt(2) * ctx.tile
    w = 0.0014
    ta = sstep(w + 0.0004, w - 0.0004, da)
    tb = sstep(w + 0.0004, w - 0.0004, db)
    knot = sstep(0.0042, 0.0030, np.sqrt(da ** 2 + db ** 2))
    op = np.clip(np.maximum(np.maximum(ta, tb), knot), 0, 1)
    # twisted strand pattern along each thread
    twa = 0.5 + 0.5 * np.sin((b * 30 + da / w * 4) * math.pi)
    twb = 0.5 + 0.5 * np.sin((a * 30 + db / w * 4) * math.pi)
    tw = np.where(ta >= tb, twa, twb)
    prof = np.where(ta >= tb, np.sqrt(np.clip(1 - (da / w) ** 2, 0, 1)), np.sqrt(np.clip(1 - (db / w) ** 2, 0, 1)))
    prof = np.maximum(prof, knot * np.sqrt(np.clip(1 - (np.sqrt(da ** 2 + db ** 2) / 0.0042) ** 2, 0, 1)))
    base = col('#252b22')
    bc = base * (0.65 + 0.35 * prof + 0.1 * tw)[..., None]
    bc = bc * (1 + 0.15 * ctx.noise(0.3, oct=3))[..., None]
    fade = cover(ctx.n01(0.5), 0.3, 0.3)
    bc = lerp(bc, col('#4a5040'), fade * 0.3)
    h = prof * 0.0015 + tw * 0.0002 + knot * 0.001
    rough = 0.8 + 0.1 * tw
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.0008,), op=op)


def m_Timber(ctx):
    n = ctx.n
    w1 = ctx.noise(0.8, oct=3, rough=0.45, aniso=6.0)
    w2 = ctx.noise(0.1, oct=3, rough=0.5, aniso=8.0)
    c = ctx.v * 40 + w1 * 0.9 + w2 * 0.12
    f = c - np.floor(c)
    late = sstep(0.6, 0.85, f) * (1 - sstep(0.9, 1.0, f))
    fiber = ctx.noise(0.003, oct=3, rough=0.6, aniso=14.0)
    tone = ctx.n01(0.5, oct=3, aniso=3.0)
    bc = lerp(col('#b59b78'), col('#7d6448'), np.clip(late * 0.6 + fiber * 0.06 + tone * 0.3, 0, 1))
    # weathering to silver grey
    wth = cover(ctx.n01(0.35, oct=5, aniso=4.0), 0.55, 0.4)
    g = bc.mean(-1, keepdims=True)
    bc = lerp(bc, np.repeat(g, 3, -1) * col('#c4c0b6') * 1.05, wth * 0.55)
    # rough-sawn marks across the grain
    saw = 0.5 + 0.5 * np.sin(TAU * (ctx.u * ctx.cyc(0.022) + ctx.noise(0.3, oct=2) * 0.3))
    # knots
    rg = ctx.rng()
    knot = np.zeros((n, n), F32)
    for _ in range(int(5 * ctx.tile / 2.0) + 1):
        kx, ky = rg.random(2)
        r = 0.012 + rg.random() * 0.018
        dx = ((ctx.u - kx + 0.5) % 1.0 - 0.5) * ctx.tile
        dy = ((ctx.v - ky + 0.5) % 1.0 - 0.5) * ctx.tile
        d = np.sqrt((dx / 1.4) ** 2 + dy ** 2)
        knot = np.maximum(knot, sstep(r, r * 0.6, d) * (0.6 + 0.4 * np.sin(d / r * 9) ** 2))
    bc = lerp(bc, col('#4a3524'), knot * 0.8)
    # checks
    cr = cover(ctx.noise(0.25, oct=3, aniso=25.0), 0.02, 0.02) * cover(ctx.n01(0.4), 0.35, 0.1)
    bc = lerp(bc, col('#3a2c20'), cr * 0.75)
    dirt = cover(ctx.n01(0.3, oct=5), 0.25, 0.3)
    bc = bc * (1 - 0.15 * dirt)[..., None]
    h = late * 0.0005 + fiber * 0.00008 + saw * 0.0003 - cr * 0.0015 + knot * 0.0002
    rough = 0.78 + 0.08 * wth + 0.05 * late
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.002, 0.008), nstr=2.0)


def m_Canvas(ctx):
    n = ctx.n
    K = ctx.cyc(0.0012)
    X = ctx.u * K
    Y = ctx.v * K
    fx = X - np.floor(X) - 0.5
    fy = Y - np.floor(Y) - 0.5
    par = ((np.floor(X) + np.floor(Y)) % 2) * 2 - 1
    hw = np.sqrt(np.clip(1 - (fx / 0.42) ** 2, 0, 1)) * (0.5 + 0.5 * par * np.cos(math.pi * fy))
    hf = np.sqrt(np.clip(1 - (fy / 0.42) ** 2, 0, 1)) * (0.5 - 0.5 * par * np.cos(math.pi * fx))
    hh = np.maximum(hw, hf)
    tone = ctx.noise(0.3, oct=5)
    bc = col('#5a5a3a') * (0.85 + 0.15 * hh + 0.07 * tone)[..., None]
    fade = cover(ctx.n01(0.5, oct=4), 0.35, 0.35)
    bc = lerp(bc, col('#7a7856'), fade * 0.35)
    stain = cover(ctx.n01(0.2, oct=6, aniso=0.4), 0.15, 0.25)
    bc = lerp(bc, col('#3c3a26'), stain * 0.35)
    mud = cover(ctx.n01(0.12, oct=5), 0.06, 0.3)
    bc = lerp(bc, col('#5e4c36'), mud * 0.4)
    wr = ctx.noise(0.06, oct=3, aniso=0.3)
    h = hh * 0.0002 + wr * 0.0004
    rough = 0.85 + 0.05 * fade
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.0005, 0.004), nstr=1.5)


def m_Bark(ctx):
    n = ctx.n
    # deep furrows running along U, broken into plates
    w = ctx.noise(0.3, oct=3, rough=0.45, aniso=5.0) * 0.3
    c = ctx.v * ctx.cyc(0.035) + w
    f = np.abs((c - np.floor(c)) - 0.5) * 2
    ridge = sstep(0.15, 0.85, 1 - f)
    brk = cover(ctx.noise(0.05, oct=3, aniso=0.4), 0.15, 0.08)
    plate = ridge * (1 - brk * 0.8)
    rough_n = ctx.noise(0.01, oct=4, rough=0.6)
    h = plate * 0.012 + rough_n * 0.0012 + ctx.noise(0.15, oct=3) * 0.002
    bc = ramp(norm01(h), [(0, col('#1e1812')), (0.4, col('#4a4036')), (0.8, col('#6e655a')), (1, col('#8a8174'))])
    lich = cover(ctx.n01(0.08, oct=5), 0.12, 0.2) * sstep(0.4, 0.8, plate)
    bc = lerp(bc, col('#8f9a78'), lich * 0.6)
    moss = cover(ctx.n01(0.2, oct=5), 0.1, 0.25) * (1 - plate)
    bc = lerp(bc, col('#3d4a22'), moss * 0.7)
    rough = 0.9 - 0.05 * plate
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.004, 0.012), aog=1.3)


def m_Straw(ctx):
    n = ctx.n
    rg = ctx.rng()
    bc = np.zeros((n, n, 3), F32) + col('#6e5a2e')
    h = np.zeros((n, n), F32)
    area = (ctx.tile / 1.0) ** 2
    bc = bc * 0.6
    for li, (cnt, c0, c1) in enumerate(((9000, col('#7a6230'), col('#a08540')), (9000, col('#a88c4a'), col('#cdb06a')),
                                         (7000, col('#c4a65a'), col('#e3cb84')))):
        cnt = int(cnt * area)
        polys, vals = [], []
        for i in range(cnt):
            x, y = rg.random(2)
            L = (0.04 + rg.random() * 0.12) / ctx.tile
            a = (rg.random() - 0.5) * 0.9  # mostly along U
            bend = (rg.random() - 0.5) * 0.3
            t = np.linspace(0, 1, 6)
            ang = a + bend * t
            px = x + np.cumsum(np.cos(ang)) * L / 6
            py = y + np.cumsum(np.sin(ang)) * L / 6
            polys.append(np.stack([px, py], 1))
            vals.append(rg.random())
        cov, val = draw_polylines(n, polys, widths=[1.0] * cnt, values=vals)
        sig = max(0.5, ctx.px(0.0008))
        covb = blur(cov, sig)
        t = np.clip(blur(val, sig) / np.maximum(covb, 1e-4), 0, 1)
        a = np.clip(covb * ctx.px(0.0016), 0, 1)
        sh = np.clip(blur(cov, sig * 3) * ctx.px(0.002), 0, 1)
        bc = bc * (1 - 0.35 * sh * (1 - a))[..., None]
        bc = lerp(bc, lerp(c0, c1, t), a)
        h = np.maximum(h, a * (0.004 + li * 0.004))
    bc = bc * (0.85 + 0.25 * ctx.n01(0.2, oct=4))[..., None]
    dark = cover(ctx.n01(0.3, oct=4), 0.2, 0.3)
    bc = lerp(bc, col('#5e4a26'), dark * 0.3)
    return dict(bc=bc, h=h, rough=0.75 + 0.1 * ctx.n01(0.05), metal=0.0, aor=(0.002, 0.008), aog=1.3, nstr=0.8)


def m_Granite(ctx):
    n = ctx.n
    rg = ctx.rng()
    cs = ctx.cyc(0.006)
    F1, F2, ID = worley(n, cs, cs, rg)
    cnt = cs * cs
    t = cell_rand(ID, cnt, rg)
    grains = ramp(t, [(0, col('#2a2826')), (0.12, col('#4a4744')), (0.35, col('#8d8781')), (0.6, col('#b4ada4')),
                      (0.8, col('#c9b7a6')), (1, col('#a8968a'))])
    edge = sstep(0.0, 0.0015 / ctx.tile, F2 - F1)
    bc = grains * (0.85 + 0.15 * edge)[..., None]
    fine = ctx.noise(0.0015, oct=2, rough=0.6)
    bc = bc * (1 + 0.08 * fine)[..., None]
    weather = ctx.noise(0.4, oct=5)
    bc = bc * (1 + 0.1 * weather)[..., None]
    stain = cover(ctx.n01(0.3, oct=5), 0.25, 0.35)
    bc = lerp(bc, col('#6a5e50'), stain * 0.35)
    lich = cover(ctx.n01(0.06, oct=5), 0.06, 0.15)
    bc = lerp(bc, col('#a9ad90'), lich * 0.5)
    h = edge * 0.0002 + fine * 0.0001 + weather * 0.001 + t * 0.0001
    rough = 0.72 + 0.1 * (1 - edge) - 0.15 * (t < 0.12)
    return dict(bc=bc, h=h, rough=rough, metal=0.0, aor=(0.002, 0.01))


GEN = {k: globals()['m_' + k] for k in SPECS}
