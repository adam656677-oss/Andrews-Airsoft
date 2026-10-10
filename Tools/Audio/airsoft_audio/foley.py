"""Handling and foley one-shots (positional, mono): trigger, magazines, bolt,
BB impacts on wood and steel, grenade bounce/burst, footsteps and landing."""

import numpy as np

from .dsp import (Mix, bp, burst, env, hp, lp, modes, ns, saturate, scatter, space, sweep,
                  tail_cut, thump, tvec, tvf)
from . import mech
from .mech import friction
from .weapons import _k, struck


def ticks(r, n, times, gains, f=(5600, 7400, 9100), decay=0.0005):
    k = struck(r, list(f), [decay, decay * 0.8, decay * 0.6], [1, 0.6, 0.35], seconds=0.008, noise_mix=0.5)
    return scatter(n, times, gains, k)


def room(x, r, length, wet=0.07, kind="small", fade_s=0.04, **kw):
    return tail_cut(space(x, r, kind, wet, **kw), length, fade_s)


# ----------------------------------------------------------------- handling (cinematic)
# Weighty, close-miked movie foley: every action has a low "mass" component under the
# metal, latches are crisp and bright, and a little saturation glues the layers.

def dry_fire(r, v):
    """Empty gun: short trigger creep, hammer/striker fall (hard steel clack with a little
    mass), then the trigger reset tick."""
    k = _k(r, v)
    m = Mix(0.16)
    m.add(friction(r, 0.012, 2600 * k, 3400 * k, q=1.2, grit=0.4, attack=0.002, decay=0.006), 0.0, 0.12)
    m.add(mech.latch(r, 4700 * k), 0.004, 0.35)                                   # sear releases
    m.add(mech.clack(r, 2500 * k, weight=0.7, bright=1.25, mass=0.9, seconds=0.06), 0.012, 1.0)  # hammer
    m.add(thump(0.05, 420 * k, 190 * k, 0.007), 0.012, 0.35)
    m.add(mech.latch(r, 6200 * k, 0.015), 0.07, 0.3)                               # reset
    return room(saturate(m.out(), 1.3), r, 0.15, 0.06)


def mag_out(r, v):
    """Mag release: button click, catch lets go, steel-lipped mag drags out of the well,
    lips clear with a scrape, hand catches it."""
    k = _k(r, v)
    m = Mix(0.42)
    n = ns(0.42)
    m.add(mech.latch(r, 5600 * k), 0.0, 0.55)                                      # button
    m.add(mech.clack(r, 2400 * k, weight=0.7, bright=1.0, mass=0.5, seconds=0.05), 0.009, 0.6)  # catch
    m.add(friction(r, 0.15, 2300 * k, 1300 * k, q=1.3, grit=0.65, attack=0.008, decay=0.07), 0.016, 0.45)
    m.add(bp(burst(r, 0.04, 0.008, attack=0.002), 5200 * k, 3.0), 0.135, 0.22)    # lips scrape the catch
    m.add(mech.poly_knock(r, 820 * k, weight=1.1), 0.165 + r.uniform(0, 0.01), 0.55)  # caught in the palm
    m.add(thump(0.06, 210 * k, 120 * k, 0.012), 0.165, 0.45)
    tt = np.sort(r.uniform(0.03, 0.2, 6))
    m.add(ticks(r, n, tt, r.uniform(0.1, 0.3, len(tt))), 0.0, 0.35)              # BBs / follower shift
    return room(saturate(m.out(), 1.3), r, 0.4, 0.07)


def mag_in(r, v):
    """Mag insertion: short drag into the well, then a weighty seat (low palm-driven mass,
    polymer body, steel catch) and a crisp, satisfying double click as the catch snaps in."""
    k = _k(r, v)
    seat = 0.052
    m = Mix(0.36)
    n = ns(0.36)
    m.add(friction(r, 0.055, 1500 * k, 2700 * k, q=1.3, grit=0.6, attack=0.006, decay=0.04), 0.0, 0.35)
    m.add(thump(0.12, 230 * k, 105 * k, 0.022, pitch_tau=0.008), seat, 0.95)       # mass of the seat
    m.add(mech.poly_knock(r, 680 * k, weight=1.3), seat, 0.7)
    m.add(mech.clack(r, 1500 * k, weight=1.1, bright=0.9, mass=0.8), seat + 0.0008, 0.75)
    m.add(lp(bp(burst(r, 0.05, 0.008, attack=0.0006), 700, 1.0), 1800), seat, 0.5)  # palm slap
    m.add(mech.latch(r, 5300 * k), seat + 0.0045, 0.85)                            # catch: click
    m.add(mech.latch(r, 6900 * k), seat + 0.0095, 0.45)                            #        ...clack
    tt = seat + np.sort(r.uniform(0.012, 0.09, 6))
    m.add(ticks(r, n, tt, r.uniform(0.08, 0.25, len(tt))), 0.0, 0.3)
    return room(saturate(m.out(), 1.35), r, 0.34, 0.07)


def bolt_cycle(r, v):
    """Heavy charging-handle rack: unlatch, gritty pull against the spring, hard rear stop,
    release, and a bolt slamming home with receiver body resonance."""
    k = _k(r, v)
    j = 1.0 + r.uniform(-0.06, 0.06)
    t_stop, t_rel, t_home = 0.13 * j, 0.24 * j, 0.275 * j
    m = Mix(0.6)
    m.add(mech.rack(r, 0.0, t_stop, t_rel, t_home, k=k, weight=1.45, grit=0.7, f_stop=1750.0, f_home=1350.0,
                    seconds=0.6), 0.0, 1.0)
    m.add(thump(0.16, 170 * k, 85 * k, 0.03, pitch_tau=0.01), t_home, 0.75)       # receiver mass
    m.add(thump(0.08, 260 * k, 140 * k, 0.012), t_stop, 0.35)
    m.add(mech.ring(r, [410 * k, 690 * k, 1130 * k], [0.06, 0.04, 0.025], [1, 0.6, 0.35], 0.25), t_home + 0.001, 0.12)
    m.add(mech.rattle(r, 0.07, 6, f=3600 * k), t_home + 0.006, 0.18)
    return room(saturate(m.out(), 1.35), r, 0.56, 0.08)


# ----------------------------------------------------------------- impacts

def _snap(r, sharp=1.0):
    """Hit transient: a short N-shaped click + 0.3 ms high-passed noise."""
    n = ns(0.012)
    x = np.zeros(n)
    w = max(3, int(9 / sharp))
    x[:w] = np.linspace(1, -1, w)
    return hp(x, 2200, order=2) + 0.8 * hp(burst(r, 0.012, 0.0003, attack=0.00003), 2500, order=2)


def impact(r, v):
    """Bullet-style hit that stays plausible for a BB: sharp tick, then the struck body
    (0 hard wood, 1 hollow plywood/crate, 2 sheet metal, 3 board with a steel fitting),
    a dry low knock and a few splinter/dust ticks."""
    kind = v % 4
    k = 1 + r.uniform(-0.04, 0.04)
    L = 0.34 if kind == 2 else 0.3
    n = ns(L)
    m = Mix(L)
    m.add(_snap(r, 1.0 + 0.3 * (kind == 2)), 0.0, 0.85)
    if kind in (0, 3):
        f = np.sort(r.uniform(380, 2300, 10)) * k
        d = (0.004 + 0.012 * r.random(10)) * np.sqrt(700.0 / f)
        m.add(struck(r, f, d, r.uniform(0.3, 1.0, 10) * (600.0 / f) ** 0.3, seconds=0.12, noise_mix=0.3, lo=1200), 0.0003, 0.9)
        m.add(thump(0.05, 520 * k, 260 * k, 0.006), 0.0, 0.45)
    elif kind == 1:
        f = np.sort(r.uniform(170, 1100, 9)) * k
        d = (0.008 + 0.02 * r.random(9)) * np.sqrt(400.0 / f)
        m.add(struck(r, f, d, r.uniform(0.4, 1.0, 9), seconds=0.18, noise_mix=0.25, lo=900), 0.0003, 1.0)
        m.add(thump(0.09, 260 * k, 140 * k, 0.016), 0.0, 0.6)                      # box resonance
    else:  # metal-backed: a short 'thunk-tink', damped so repeated hits don't sing one pitch
        f = 1150 * k * np.array([1.0, 1.31, 1.47, 2.09, 2.43, 2.76, 3.51, 4.38])
        m.add(struck(r, f, [0.032, 0.026, 0.024, 0.019, 0.016, 0.013, 0.011, 0.008],
                     [1, 0.7, 0.8, 0.6, 0.45, 0.45, 0.3, 0.2], seconds=0.3, noise_mix=0.4), 0.0002, 0.55)
        m.add(thump(0.06, 420 * k, 210 * k, 0.01), 0.0, 0.5)
    if kind == 3:
        m.add(mech.ring(r, [3300 * k, 4870 * k, 7020 * k], [0.05, 0.035, 0.02], [1, 0.6, 0.35], 0.2), 0.0005, 0.25)
        m.add(mech.rattle(r, 0.06, 5, f=2400 * k), 0.012, 0.25)
    m.add(_grains(r, n, 0.008, 14, 0.012, lo=2500, hi=8000, gain=0.35), 0.0, 1.0)  # splinters / dust
    x = saturate(m.out(), 1.3)
    return room(x, r, L, 0.12, "outdoor", fade_s=0.08, t60=0.45, lo_cut=200)


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
    "DryFire": (dry_fire, 2, "Empty gun: trigger creep, sear release, hard hammer/striker clack with a little mass, reset tick"),
    "MagOut": (mag_out, 2, "Mag release click, catch lets go, mag drags out with a lip scrape, caught in the palm"),
    "MagIn": (mag_in, 2, "Short drag in, weighty seat (low mass + polymer + steel) and a crisp double catch click"),
    "BoltCycle": (bolt_cycle, 2, "Heavy charging-handle rack: unlatch, gritty spring pull, rear stop, bolt slams home with receiver ring"),
    "Impact": (impact, 4, "Bullet-style hit, plausible for a BB: sharp tick + body (hard wood / hollow crate / sheet metal / board with steel fitting) + splinters"),
    "SteelDing": (steel_ding, 3, "BB on a steel plate: bright ping, partials 2.3/3.1/4.7 kHz, ~0.6 s ring"),
    "GrenadeBounce": (grenade_bounce, 3, "Small polymer BB-grenade canister bouncing on hard ground, BBs rattling inside"),
    "GrenadeBurst": (grenade_burst, 1, "BB grenade: gas pop + shell split + ~1.2 s shower of BBs pattering on surfaces"),
    "Footstep": (footstep, 6, "Boots on gravel over concrete (alternating heavier heel / lighter roll)"),
    "Land": (land, 1, "Jump landing: double boot thud, gravel crunch, gear and pouch rattle"),
}
