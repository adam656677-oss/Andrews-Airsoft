"""Handling and foley one-shots (positional, mono): trigger, magazines, bolt,
BB impacts on wood and steel, grenade bounce/burst, footsteps and landing."""

import numpy as np

from .dsp import (Mix, bp, burst, env, hp, lp, modes, ns, scatter, space, sweep,
                  tail_cut, thump, tvec, tvf)
from .weapons import _k, struck


def friction(r, seconds, f0, f1, q=1.4, grit=0.6, attack=0.006, decay=None):
    """Sliding contact: band-passed noise sweeping f0->f1 with gritty grain AM."""
    n = ns(seconds)
    y = tvf(r.standard_normal(n), "bp", sweep(f0, f1, n), q=q)
    g = np.abs(lp(r.standard_normal(n), 380))
    g /= g.max() + 1e-12
    e = env(n, attack, decay or seconds * 0.5)
    return y * np.clip((1 - grit) + grit * g * 3, 0, 3) * e


def ticks(r, n, times, gains, f=(5600, 7400, 9100), decay=0.0005):
    k = struck(r, list(f), [decay, decay * 0.8, decay * 0.6], [1, 0.6, 0.35], seconds=0.008, noise_mix=0.5)
    return scatter(n, times, gains, k)


def room(x, r, length, wet=0.07, kind="small", fade_s=0.04, **kw):
    return tail_cut(space(x, r, kind, wet, **kw), length, fade_s)


# ----------------------------------------------------------------- handling

def dry_fire(r, v):
    k = _k(r, v)
    m = Mix(0.12)
    m.add(struck(r, [2600 * k, 4100 * k, 6050 * k], [0.004, 0.003, 0.002], [1, 0.7, 0.4], seconds=0.04, noise_mix=0.4), 0.0, 0.6)
    m.add(struck(r, [5200 * k, 7450 * k, 9800 * k], [0.003, 0.002, 0.0015], [1, 0.6, 0.3], seconds=0.03, noise_mix=0.6), 0.009, 1.0)
    m.add(thump(0.03, 900 * k, 420 * k, 0.004), 0.009, 0.35)
    m.add(struck(r, [3100 * k, 4900 * k], [0.002, 0.0015], [1, 0.5], seconds=0.02, noise_mix=0.3), 0.052, 0.25)  # reset
    return room(m.out(), r, 0.12, 0.06)


def mag_out(r, v):
    k = _k(r, v)
    m = Mix(0.42)
    n = ns(0.42)
    m.add(struck(r, [3200 * k, 5000 * k, 7100 * k], [0.003, 0.0025, 0.002], [1, 0.6, 0.35], seconds=0.03), 0.0, 0.7)
    m.add(struck(r, [2100 * k, 3500 * k, 5600 * k], [0.007, 0.005, 0.003], [1, 0.7, 0.4], seconds=0.05), 0.012, 0.8)
    m.add(thump(0.04, 320 * k, 180 * k, 0.008), 0.012, 0.35)
    m.add(friction(r, 0.17, 2600 * k, 1700 * k, attack=0.01, decay=0.06), 0.02, 0.45)
    tt = np.sort(r.uniform(0.03, 0.2, 9))
    m.add(ticks(r, n, tt, r.uniform(0.15, 0.5, len(tt))), 0.0, 0.5)
    m.add(struck(r, [1900 * k, 3300 * k], [0.004, 0.003], [1, 0.5], seconds=0.03, noise_mix=0.3), 0.19 + r.uniform(0, 0.02), 0.3)
    return room(m.out(), r, 0.4, 0.08)


def mag_in(r, v):
    k = _k(r, v)
    seat = 0.03
    m = Mix(0.34)
    n = ns(0.34)
    m.add(friction(r, 0.06, 1600 * k, 2500 * k, attack=0.005, decay=0.05), 0.0, 0.35)
    m.add(struck(r, [1180 * k, 2620 * k, 3900 * k, 5600 * k], [0.014, 0.01, 0.007, 0.004], [1, 0.8, 0.55, 0.3], noise_mix=0.5), seat, 1.0)
    m.add(struck(r, [4200 * k, 6300 * k, 8400 * k], [0.005, 0.004, 0.003], [1, 0.6, 0.35], seconds=0.04, noise_mix=0.4), seat + 0.0015, 0.55)
    m.add(thump(0.08, 260 * k, 150 * k, 0.02), seat, 0.8)
    m.add(modes(0.12, [600 * k, 980 * k], [0.03, 0.02], [1, 0.6], rng=r), seat + 0.001, 0.22)
    tt = seat + np.sort(r.uniform(0.004, 0.08, 7))
    m.add(ticks(r, n, tt, r.uniform(0.1, 0.35, len(tt))), 0.0, 0.4)
    return room(m.out(), r, 0.32, 0.08)


def bolt_cycle(r, v):
    k = _k(r, v)
    j = 1.0 + r.uniform(-0.08, 0.08)
    back, rel, fwd = 0.11 * j, 0.25 * j, 0.285 * j
    m = Mix(0.52)
    m.add(struck(r, [2500 * k, 4100 * k, 6200 * k], [0.004, 0.003, 0.002], [1, 0.7, 0.4], seconds=0.03), 0.0, 0.8)
    m.add(friction(r, back, 1400 * k, 2600 * k, attack=0.008, decay=0.2), 0.008, 0.45)
    nb = ns(back)
    m.add(tvf(r.standard_normal(nb), "bp", sweep(900 * k, 1400 * k, nb), q=18) * env(nb, 0.01, 0.2), 0.008, 0.25)  # spring buzz
    m.add(struck(r, [1900 * k, 3000 * k, 4500 * k, 6300 * k], [0.012, 0.009, 0.006, 0.004], [1, 0.8, 0.5, 0.3]), back, 0.8)
    m.add(thump(0.06, 220 * k, 140 * k, 0.012), back, 0.45)
    m.add(friction(r, fwd - rel, 2600 * k, 1600 * k, attack=0.003, decay=0.03), rel, 0.35)
    m.add(struck(r, [1700 * k, 2800 * k, 4200 * k, 6000 * k, 8100 * k], [0.016, 0.012, 0.008, 0.005, 0.003], [1, 0.85, 0.55, 0.35, 0.2], noise_mix=0.5), fwd, 1.0)
    m.add(thump(0.08, 200 * k, 110 * k, 0.022), fwd, 0.7)
    m.add(struck(r, [5200 * k, 7300 * k], [0.003, 0.002], [1, 0.5], seconds=0.02), fwd + 0.006, 0.3)
    return room(m.out(), r, 0.5, 0.08)


# ----------------------------------------------------------------- impacts

def impact(r, v):
    """BB on plywood: a dry tick on top of short, damped board modes."""
    k = (1.0, 1.25, 0.8, 1.1)[v % 4] * (1 + r.uniform(-0.03, 0.03))
    m = Mix(0.16)
    m.add(hp(burst(r, 0.01, 0.00025, attack=0.00003), 2500), 0.0, 0.6)
    f = np.sort(r.uniform(260, 1900, 9)) * k
    d = (0.004 + 0.016 * r.random(9)) * np.sqrt(600.0 / f)
    a = r.uniform(0.3, 1.0, 9) * (500.0 / f) ** 0.3
    m.add(struck(r, f, d, a, seconds=0.1, noise_mix=0.35, lo=1200), 0.0, 1.0)
    m.add(thump(0.03, 700 * k, 350 * k, 0.003), 0.0, 0.25)
    if v % 4 == 3:  # loose board chatter
        m.add(struck(r, f[:4] * 1.1, d[:4] * 0.5, a[:4]), 0.021, 0.18)
    return room(m.out(), r, 0.18, 0.1, "outdoor", fade_s=0.06, t60=0.4, lo_cut=200)


def steel_ding(r, v):
    """BB on a steel plate: strike tick + 2.3/3.1/4.7 kHz partials (beating
    pairs) ringing ~0.6 s, faint lower plate modes and quick high partials."""
    k = 1.0 + (0.0, 0.03, -0.025)[v % 3] + r.uniform(-0.005, 0.005)
    n = ns(0.9)
    t = tvec(n)
    amp = r.uniform(0.75, 1.25, 3)
    main = modes(0.9, [2300 * k, 3100 * k, 4700 * k], [0.17, 0.14, 0.1], [1.0 * amp[0], 0.8 * amp[1], 0.55 * amp[2]], rng=r, beat=1.3)
    main *= 1.0 + 0.08 * np.sin(2 * np.pi * (6.5 + v) * t)  # plate swinging on its hanger
    low = modes(0.9, [930 * k, 1580 * k], [0.06, 0.05], [0.35, 0.3], rng=r)
    high = modes(0.9, [6250 * k, 7900 * k, 9800 * k], [0.02, 0.015, 0.01], [0.4, 0.3, 0.2], rng=r)
    m = Mix(0.9)
    m.add(main + low + high, 0.0, 1.0)
    m.add(hp(burst(r, 0.01, 0.0003, attack=0.00003), 3000), 0.0, 0.9)
    return room(m.out(), r, 0.85, 0.12, "outdoor", fade_s=0.3, t60=0.6, lo_cut=300)


# ----------------------------------------------------------------- grenade

def grenade_bounce(r, v):
    k = _k(r, v, 0.04)
    n = ns(0.6)
    m = Mix(0.6)

    def knock():
        x = struck(r, [610 * k, 1330 * k, 2140 * k, 3280 * k, 4700 * k], [0.009, 0.007, 0.005, 0.0035, 0.0025],
                   [1, 0.8, 0.6, 0.4, 0.25], seconds=0.06, noise_mix=0.5)
        return x + 0.5 * np.pad(thump(0.04, 420 * k, 260 * k, 0.006), (0, len(x) - ns(0.04)))

    def rattle(at, count, dur, g):
        tt = at + np.sort(r.uniform(0.003, dur, count))
        y = ticks(r, n, tt, r.uniform(0.2, 1.0, count) * np.exp(-(tt - at) / (dur * 0.6)))
        return bp(y, 2100 * k, 0.9) * 2.0 * g

    t2 = 0.13 + r.uniform(0, 0.06)
    t3 = t2 + 0.07 + r.uniform(0, 0.03)
    for at, g in ((0.0, 1.0), (t2, 0.45), (t3, 0.18)):
        m.add(knock(), at, g)
        m.add(rattle(at, 18, 0.07, g), 0.0, 0.5)
    if v == 2:
        m.add(friction(r, 0.12, 1800, 1200, q=1.0, attack=0.01, decay=0.05), t3 + 0.02, 0.12)
    return room(m.out(), r, 0.55, 0.1, "outdoor", fade_s=0.12, t60=0.4, lo_cut=200)


def _shower_kernels(r):
    ks = []
    for _ in range(8):  # ground / concrete ticks
        x = hp(burst(r, 0.012, 0.0004 + 0.0004 * r.random(), attack=0.00003), 1800)
        ks.append(("ground", x + 0.4 * bp(burst(r, 0.012, 0.001), r.uniform(900, 1500), 1.5)))
    for _ in range(5):  # wood / pallets
        f = np.sort(r.uniform(400, 1800, 5))
        ks.append(("wood", struck(r, f, 0.003 + 0.006 * r.random(5), r.uniform(0.4, 1, 5), seconds=0.04, noise_mix=0.4)))
    for _ in range(4):  # foliage / leaves
        ks.append(("leaf", bp(burst(r, 0.02, 0.003 + 0.003 * r.random(), attack=0.0008), r.uniform(2000, 4200), 1.2)))
    for _ in range(3):  # plastic barrels / crates
        f = np.sort(r.uniform(700, 2100, 4))
        ks.append(("plastic", struck(r, f, 0.006 + 0.006 * r.random(4), r.uniform(0.5, 1, 4), seconds=0.05)))
    for _ in range(2):  # the odd steel ping
        f = np.sort(r.uniform(2400, 5200, 3))
        ks.append(("steel", struck(r, f, 0.03 + 0.03 * r.random(3), [1, 0.7, 0.5], seconds=0.2, noise_mix=0.2)))
    return ks


def grenade_burst(r, v):
    """BB grenade: gas pop + shell split, then ~1.2 s of BBs pattering down."""
    L = 1.75
    n = ns(L)
    m = Mix(L)
    m.add(hp(burst(r, 0.03, 0.0012, attack=0.00003), 900), 0.0, 1.0)
    m.add(thump(0.2, 260, 70, 0.035, pitch_tau=0.008), 0.0, 1.0)
    m.add(burst(r, 0.45, 0.07, attack=0.002, lo=150, hi=2800), 0.001, 0.6)
    m.add(burst(r, 0.25, 0.03, attack=0.001, lo=3000, hi=12000), 0.0005, 0.25)
    m.add(struck(r, [820, 1710, 2900, 4100], [0.012, 0.008, 0.005, 0.003], [1, 0.8, 0.5, 0.3]), 0.001, 0.5)
    N = 420
    tt = 0.025 + r.gamma(1.6, 0.16, N)
    bounce = r.random(N) < 0.35
    tb = tt[bounce] + r.uniform(0.04, 0.12, bounce.sum())
    times = np.concatenate([tt, tb])
    gains = np.concatenate([r.uniform(0.15, 1.0, N), r.uniform(0.05, 0.3, len(tb))])
    keep = times < 1.3
    times, gains = times[keep], gains[keep] * np.exp(-times[keep] / 0.6)
    kernels = _shower_kernels(r)
    weights = {"ground": 0.45, "wood": 0.25, "leaf": 0.15, "plastic": 0.11, "steel": 0.04}
    p = np.array([weights[c] / sum(1 for cc, _ in kernels if cc == c) for c, _ in kernels])
    pick = r.choice(len(kernels), size=len(times), p=p / p.sum())
    shower = np.zeros(n)
    for j, (cat, ker) in enumerate(kernels):
        sel = pick == j
        if sel.any():
            g = gains[sel] * (0.5 if cat == "steel" else 1.0)
            shower += scatter(n, times[sel], g, ker)
    m.add(shower, 0.0, 0.55)
    return room(m.out(), r, 1.7, 0.18, "outdoor", fade_s=0.4, t60=0.8, lo_cut=160)


# ----------------------------------------------------------------- movement

def _grains(r, n, at, count, spread, lo=1500, hi=7000, gain=1.0):
    kernels = []
    for _ in range(6):
        g = burst(r, 0.006, 0.0004 + 0.0018 * r.random(), attack=0.00005)
        kernels.append(bp(g, r.uniform(lo, hi), 1.3))
    tt = at + np.minimum(r.gamma(1.4, spread, count), spread * 6)
    gg = r.uniform(0.1, 1.0, count) * np.exp(-(tt - at) / (spread * 3))
    pick = r.integers(0, len(kernels), count)
    out = np.zeros(n)
    for j, ker in enumerate(kernels):
        sel = pick == j
        if sel.any():
            out += scatter(n, tt[sel], gg[sel], ker)
    return out * gain


def footstep(r, v):
    """Boot on gravel over concrete: heel thud + sole 'tok' + gravel crunch + toe roll."""
    k = _k(r, v, 0.05)
    heavy = v % 2 == 0
    n = ns(0.32)
    m = Mix(0.32)
    m.add(thump(0.06, 140 * k, 70 * k, 0.012 if heavy else 0.008), 0.0, 0.8 if heavy else 0.55)
    m.add(bp(burst(r, 0.04, 0.006, attack=0.0004), 850 * k, 1.3), 0.0, 0.7)
    m.add(_grains(r, n, 0.002, int(r.integers(50, 100)), 0.02), 0.0, 1.0)
    toe = 0.05 + r.uniform(0, 0.035)
    m.add(bp(burst(r, 0.03, 0.004, attack=0.0005), 1100 * k, 1.2), toe, 0.35)
    m.add(_grains(r, n, toe, int(r.integers(25, 55)), 0.014), 0.0, 0.65)
    if v in (2, 5):
        m.add(friction(r, 0.05, 2500, 3500, q=1.0, attack=0.008, decay=0.02), toe + 0.01, 0.18)
    return room(m.out(), r, 0.3, 0.06, "outdoor", fade_s=0.08, t60=0.35, lo_cut=200)


def land(r, v):
    """Jump landing: two boots, big gravel crunch, plate-carrier and pouch rattle."""
    n = ns(0.66)
    m = Mix(0.66)
    for at, g in ((0.0, 1.0), (0.018, 0.8)):
        m.add(thump(0.1, 120, 55, 0.02), at, g)
        m.add(bp(burst(r, 0.05, 0.008, attack=0.0004), 800, 1.2), at, 0.7 * g)
    m.add(thump(0.15, 70, 45, 0.04), 0.004, 0.5)
    m.add(_grains(r, n, 0.002, 180, 0.032), 0.0, 1.1)
    for at in np.sort(r.uniform(0.03, 0.2, 4)):
        f = r.uniform(900, 1500)
        m.add(struck(r, [f, f * 2.2, f * 3.4], [0.008, 0.006, 0.004], [1, 0.6, 0.35], seconds=0.04), at, r.uniform(0.2, 0.35))
    for at in np.sort(r.uniform(0.05, 0.25, 3)):
        f = r.uniform(3000, 4500)
        m.add(modes(0.08, [f, f * 1.37, f * 1.81], [0.02, 0.015, 0.01], [1, 0.6, 0.4], rng=r), at, 0.12)
    m.add(friction(r, 0.4, 1500, 3800, q=0.8, grit=0.8, attack=0.03, decay=0.12), 0.01, 0.25)
    return room(m.out(), r, 0.6, 0.07, "outdoor", fade_s=0.12, t60=0.4, lo_cut=200)


RECIPES = {
    "DryFire": (dry_fire, 1, "Trigger pull on an empty gun: plastic trigger travel, sear click, reset tick"),
    "MagOut": (mag_out, 1, "Mag release button + latch clack, polymer mag sliding out, BBs shifting"),
    "MagIn": (mag_in, 1, "Short insertion slide then a solid polymer seat click with metal catch and palm slap"),
    "BoltCycle": (bolt_cycle, 1, "Charging handle / bolt / pump rack: unlatch, gritty pull, rear stop, slam forward"),
    "Impact": (impact, 4, "BB hitting plywood/wood: dry tick over damped board modes"),
    "SteelDing": (steel_ding, 3, "BB on a steel plate: bright ping, partials 2.3/3.1/4.7 kHz, ~0.6 s ring"),
    "GrenadeBounce": (grenade_bounce, 3, "Small polymer BB-grenade canister bouncing on hard ground, BBs rattling inside"),
    "GrenadeBurst": (grenade_burst, 1, "BB grenade: gas pop + shell split + ~1.2 s shower of BBs pattering on surfaces"),
    "Footstep": (footstep, 6, "Boots on gravel over concrete (alternating heavier heel / lighter roll)"),
    "Land": (land, 1, "Jump landing: double boot thud, gravel crunch, gear and pouch rattle"),
}
