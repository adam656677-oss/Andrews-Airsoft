"""Gunfire one-shots (positional, mono).

Airsoft guns do not bang. Each recipe layers the real mechanical events:
  AEG     : piston slap into the cylinder head (receiver modes + mass thump),
            air puff out of the barrel, small BB/air snap, gearbox motor whir
            with spin-down and anti-reversal-latch ticks.
  Gas GBB : sharp pneumatic crack + gas jet, hammer/valve tick, slide clack
            rearward and a second clack when it returns to battery.
  Spring  : heavy piston thunk, metal cylinder ring and the dispersive
            "twang" of the mainspring.
"""

import numpy as np

from .dsp import (Mix, burst, bp, env, hp, lp, modes, ns, phase, saturate, saw,
                  scatter, sine, space, sweep, tail_cut, thump, tvec)

VAR_PITCH = (0.0, 0.028, -0.024, 0.012, -0.012, 0.035)


def _k(r, v, jitter=0.012):
    return 1.0 + VAR_PITCH[v % len(VAR_PITCH)] + r.uniform(-jitter, jitter)


def air(dry, r, wet, length, t60=0.55):
    """Outdoor tail: short ground/treeline reflections, low end kept out of the
    tail so shots stay snappy, then trimmed to the target length."""
    return tail_cut(space(dry, r, "outdoor", wet, t60=t60, lo_cut=160), length, fade_s=0.35 * length)


def struck(r, freqs, decays, amps, seconds=0.12, noise_mix=0.4, exc_decay=0.0005, lo=1500):
    """Modal ring with a short broadband strike click on top."""
    ring = modes(seconds, freqs, decays, amps, rng=r, attack=0.00012)
    click = hp(burst(r, seconds, exc_decay, attack=0.00004), lo, order=2)
    return ring + noise_mix * click * (np.max(np.abs(ring)) / (np.max(np.abs(click)) + 1e-9))


def crack(r, decay=0.0007, lo=2600, center=6200, q=0.8):
    """BB / air snap: a sub-millisecond high-passed noise spike."""
    x = burst(r, 0.02, decay, attack=0.00004)
    return hp(x, lo, order=4) + 0.6 * bp(x, center, q)


def _whir(r, k, f0, length, rattle=0.0):
    """Gearbox: motor rotation buzz + gear-mesh whine + brush noise, spin-up/down."""
    n = ns(length + 0.04)
    t = tvec(n)
    curve = np.interp(t, [0.0, 0.22 * length, length, length + 0.04], [0.78, 1.0, 0.97, 0.55])
    f = f0 * k * curve
    motor = lp(saw(f, n), 2600, order=2)
    mesh = 0.45 * sine(f * 3.07, n) + 0.22 * sine(f * 4.6, n) + 0.12 * sine(f * 7.9, n)
    brush = bp(r.standard_normal(n), 3100 * k, 1.2) * (0.5 + 0.5 * np.abs(np.sin(np.pi * phase(f, n))))
    e = np.interp(t, [0.0, 0.004, length, length + 0.04], [0.0, 1.0, 0.85, 0.0])
    sig = (motor * 0.55 + mesh + brush * 0.5) * e
    # sector gear cycle wobble (the "brrt" grain)
    sig *= 1.0 + 0.35 * np.sin(2 * np.pi * phase(f / 9.5, n))
    # anti-reversal latch ticks while the gears coast to a stop
    times, tt, gap = [], length * 0.9, 0.0028
    while tt < length + 0.034:
        times.append(tt)
        tt += gap
        gap *= 1.32
    tick = struck(r, [4300 * k, 6100 * k, 7900 * k], [0.0012, 0.0009, 0.0006], [1, 0.6, 0.35], seconds=0.01, noise_mix=0.3)
    sig += scatter(n, times, 0.55 * 0.8 ** np.arange(len(times)), tick)
    return sig


def _box_mag(r, k):
    """LMG box mag: loose BBs settling + a sound-activated winding buzz."""
    n = ns(0.28)
    t = tvec(n)
    times = np.sort(r.uniform(0.006, 0.17, 26))
    tick = struck(r, [5200 * k, 6900 * k, 8800 * k], [0.0008, 0.0006, 0.0004], [1, 0.6, 0.4], seconds=0.008, noise_mix=0.5)
    bbs = scatter(n, times, r.uniform(0.2, 1.0, len(times)) * np.exp(-times / 0.09), tick)
    shake = bp(r.standard_normal(n), 1300 * k, 2.0) * env(n, 0.004, 0.05) * (0.6 + 0.4 * np.sin(2 * np.pi * 61 * t))
    wind_on = (t > 0.085) & (t < 0.19)
    wf = 640 * k
    wind = lp(saw(wf, n) * 0.6 + sine(wf * 2.02, n) * 0.3, 2200) * wind_on * np.clip((t - 0.085) / 0.01, 0, 1)
    wind *= np.clip((0.19 - t) / 0.02, 0, 1) * (1 + 0.5 * np.sign(np.sin(2 * np.pi * 34 * t)))
    return bbs * 0.9 + shake * 0.35 + lp(wind, 3000) * 0.18


def aeg(r, v, slap=1500.0, low=150.0, punch=1.0, whir=420.0, whir_len=0.065, whir_g=0.22,
        crack_g=0.5, puff_g=0.55, clank=0.0, box=False, suppressed=False, length=0.45, wet=0.2):
    k = _k(r, v)
    m = Mix(length)
    f = slap * k
    # piston slap: gearbox shell / receiver modes, strongest layer
    sl = struck(r, [f * 0.52, f, f * 1.43, f * 2.17, f * 3.05, f * 4.1],
                [0.011, 0.012, 0.008, 0.005, 0.003, 0.002], [0.55, 1.0, 0.75, 0.5, 0.32, 0.2],
                seconds=0.1, noise_mix=0.55)
    m.add(sl, 0.0, 0.7 * punch)
    # piston mass hitting the cylinder head: short pitched thump
    m.add(thump(0.12, low * 2.3 * k, low * k, 0.02 * (0.75 + 0.35 * punch)), 0.0004, 0.8 * punch)
    m.add(thump(0.14, 95 * k, 62 * k, 0.03 * punch), 0.0008, 0.22 * punch)
    # hollow receiver body ring
    m.add(struck(r, [300 * k, 515 * k, 790 * k, 1120 * k], [0.03, 0.02, 0.014, 0.01], [1, 0.6, 0.4, 0.25],
                 seconds=0.15, noise_mix=0.0), 0.0005, 0.22 * punch)
    if clank:  # steel piston head / reinforced cylinder: metallic edge on the slap
        m.add(struck(r, [2950 * k, 4420 * k, 6130 * k, 7800 * k], [0.013, 0.009, 0.006, 0.004],
                     [1, 0.7, 0.5, 0.3], noise_mix=0.4), 0.0006, clank)
    if suppressed:
        thup = lp(bp(burst(r, 0.1, 0.016, attack=0.0015), 620 * k, 1.8), 1400)
        m.add(thup, 0.001, puff_g * 1.6)
        can = struck(r, [880 * k, 2140 * k, 3350 * k], [0.014, 0.008, 0.005], [1, 0.5, 0.25], noise_mix=0.0)
        m.add(can, 0.0012, 0.12)
    else:
        m.add(burst(r, 0.08, 0.013, attack=0.0007, lo=420, hi=3600), 0.001, puff_g)
        m.add(crack(r), 0.0012, crack_g)
    m.add(_whir(r, k, whir, whir_len), 0.0015, whir_g)
    if box:
        m.add(_box_mag(r, k), 0.004, 0.35)
    dry = saturate(m.out(), 1.7)
    if suppressed:
        dry = lp(dry, 7500)
    return air(dry, r, wet, length)


def gbb(r, v, crack_f=3300.0, gas=1.0, slide_k=1.0, t_back=0.011, t_fwd=0.040, mass_f=170.0,
        weight=1.0, length=0.38, wet=0.2):
    k = _k(r, v)
    jt = 1.0 + r.uniform(-0.06, 0.06)
    m = Mix(length)
    c = burst(r, 0.03, 0.0011 * weight, attack=0.00003)
    m.add(hp(c, 1200, order=4) + 0.8 * bp(c, crack_f * k, 0.9), 0.0, 1.0)
    m.add(burst(r, 0.14, 0.017 * gas, attack=0.0004, lo=900, hi=7000), 0.0004, 0.42 * gas)
    m.add(burst(r, 0.12, 0.022 * gas, attack=0.001, lo=150, hi=1100), 0.0006, 0.35 * gas)
    m.add(thump(0.1, mass_f * 2.4 * k, mass_f * k, 0.018 * weight), 0.0, 0.75 * weight)
    m.add(struck(r, [3600 * k, 5300 * k, 7400 * k], [0.003, 0.002, 0.0015], [1, 0.6, 0.4], seconds=0.03), 0.0, 0.3)
    sk = slide_k * k
    back = struck(r, [1850 * sk, 2950 * sk, 4380 * sk, 6100 * sk, 8200 * sk],
                  np.array([0.016, 0.012, 0.008, 0.005, 0.003]) * weight, [0.8, 1, 0.7, 0.5, 0.3], noise_mix=0.5)
    m.add(back, t_back * jt, 0.62)
    m.add(thump(0.06, mass_f * 1.6 * k, mass_f * 0.9 * k, 0.012 * weight), t_back * jt, 0.35 * weight)
    fwd = struck(r, [2250 * sk, 3420 * sk, 5150 * sk, 6900 * sk],
                 np.array([0.012, 0.009, 0.006, 0.004]) * weight, [0.9, 1, 0.6, 0.4], noise_mix=0.6)
    m.add(fwd, t_fwd * jt, 0.55)
    m.add(thump(0.05, mass_f * 1.9 * k, mass_f * 1.1 * k, 0.008 * weight), t_fwd * jt, 0.24 * weight)
    dry = saturate(m.out(), 1.45)
    return air(dry, r, wet, length)


def shotgun(r, v):
    k = _k(r, v)
    m = Mix(0.7)
    m.add(thump(0.25, 210 * k, 60 * k, 0.05, pitch_tau=0.012), 0.0, 1.0)
    m.add(burst(r, 0.22, 0.032, attack=0.001, lo=60, hi=900), 0.0, 0.8)
    m.add(hp(burst(r, 0.03, 0.0012, attack=0.00004), 1500, order=4), 0.0, 0.5)
    for j, (dt, fc) in enumerate([(0.0015, 6200), (0.0042, 5400), (0.0071, 7100)]):
        h = burst(r, 0.16, 0.032 + 0.013 * j, attack=0.002)
        h = bp(h, fc * k * (1 + r.uniform(-0.05, 0.05)), 2.2) + 0.3 * hp(h, 8500)
        m.add(h, dt, 0.42)
    m.add(struck(r, [1250 * k, 2100 * k, 3300 * k, 4800 * k], [0.018, 0.012, 0.007, 0.004], [1, 0.8, 0.5, 0.3]), 0.0015, 0.55)
    m.add(bp(burst(r, 0.08, 0.012, attack=0.0006), 900 * k, 1.0), 0.0008, 0.5)
    dry = saturate(m.out(), 1.5)
    return air(dry, r, 0.24, 0.6, t60=0.65)


def spring_twang(r, k, seconds=0.55):
    n = ns(seconds)
    t = tvec(n)
    cn = ns(0.022)
    chirp = np.sin(2 * np.pi * phase(sweep(4300 * k, 360 * k, cn), cn)) * env(cn, 0.0002, 0.008)
    period = 0.0235 / k
    times = np.arange(0.0, seconds - 0.03, period)
    out = lp(scatter(n, times, 0.6 ** np.arange(len(times)), chirp), 5200)
    fb = 172 * k * (1 + 0.025 * np.exp(-t / 0.05))
    boing = sine(fb, n) * env(n, 0.002, 0.11) * (1 + 0.3 * np.sin(2 * np.pi * 9 * t))
    return out + 0.8 * boing


def sniper(r, v):
    k = _k(r, v)
    m = Mix(0.8)
    m.add(thump(0.25, 240 * k, 78 * k, 0.045, pitch_tau=0.01), 0.0, 1.0)
    m.add(struck(r, [560 * k, 910 * k, 1480 * k, 2230 * k, 3150 * k], [0.03, 0.022, 0.014, 0.008, 0.005],
                 [1, 0.8, 0.55, 0.3, 0.2], seconds=0.2, noise_mix=0.5), 0.0, 0.95)
    m.add(modes(0.65, [410 * k, 833 * k, 1271 * k, 1902 * k], [0.16, 0.11, 0.08, 0.05], [1, 0.55, 0.35, 0.2], rng=r), 0.002, 0.15)
    m.add(spring_twang(r, k), 0.004, 0.3)
    m.add(burst(r, 0.1, 0.02, attack=0.001, lo=300, hi=2200), 0.002, 0.35)
    m.add(crack(r), 0.002, 0.15)
    dry = saturate(m.out(), 1.5)
    return air(dry, r, 0.22, 0.62, t60=0.7)


RECIPES = {
    "FireRifle": (lambda r, v: aeg(r, v), 3,
                  "AEG (M4/AK): piston slap + receiver ring + air puff + BB snap + gearbox whir and latch ticks"),
    "FireSMG": (lambda r, v: aeg(r, v, slap=2100, low=190, punch=0.72, whir=560, whir_len=0.045, whir_g=0.2,
                                 crack_g=0.42, puff_g=0.42, length=0.32, wet=0.15), 3,
                "High-ROF compact AEG (P90/MP7/Vector/MP5): lighter, brighter slap, short fast whir"),
    "FireDMR": (lambda r, v: aeg(r, v, slap=1250, low=118, punch=1.4, whir=360, whir_len=0.085, whir_g=0.2,
                                 crack_g=0.85, puff_g=0.65, clank=0.32, length=0.56, wet=0.23), 3,
                "Upgraded high-FPS AEG: heavier piston slap with steel-head clank, louder snap"),
    "FireLMG": (lambda r, v: aeg(r, v, slap=1350, low=132, punch=1.15, whir=380, whir_len=0.075, whir_g=0.24,
                                 crack_g=0.55, box=True, length=0.5, wet=0.21), 3,
                "Support AEG: deeper motor + box-mag BB rattle and sound-activated winding buzz"),
    "FirePistol": (lambda r, v: gbb(r, v), 3,
                   "Gas blowback pistol: pneumatic crack + gas jet, slide clack back and into battery"),
    "FireMagnum": (lambda r, v: gbb(r, v, crack_f=2500, gas=1.6, slide_k=0.78, t_back=0.015, t_fwd=0.066,
                                    mass_f=118, weight=1.45, length=0.55, wet=0.25), 3,
                   "Big-bore gas pistol (Desert Eagle): deeper crack, more gas, heavier, slower slide"),
    "FireShotgun": (shotgun, 3, "Gas/spring shell shotgun: low whump + triple-BB hiss + receiver clack"),
    "FireSniper": (sniper, 3, "Spring bolt-action: heavy piston thunk + cylinder ring + mainspring twang (muted muzzle)"),
    "FireSuppressed": (lambda r, v: aeg(r, v, slap=1650, low=150, punch=0.85, whir=440, whir_len=0.06, whir_g=0.3,
                                        puff_g=0.55, suppressed=True, length=0.28, wet=0.08), 3,
                       "Suppressed AEG (MP5SD): muffled thup, mostly the mechanism"),
}
