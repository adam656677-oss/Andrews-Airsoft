"""Cinematic gunfire (the default `Fire*` set) and distant versions (`Fire*_Far`).

Big-screen action gunfire is a designed sound, not a recording of one event. Each shot
is layered from:

  crack   supersonic N-wave + 2-8 kHz noise snap (instant attack) + air-rip sizzle and a
          faint muzzle-device ring
  thump   chest-hit low end: a sine body that drops from ~100-170 Hz to 40-75 Hz in a few
          ms, with a short octave partial so it still reads on small speakers
  bark    the midrange punch: a noise burst through 3-4 formant resonances plus a falling
          tone, driven into saturation, over a 130-330 Hz low-mid body
  mech    the gun working, slightly behind the blast: bolt carrier / slide / bolt clacks,
          buffer springs, belt links, pump strokes
  tail    environment: discrete slap echoes off nearby walls, a 0.6-1.25 s synthesised
          room/outdoor reverb with early reflections, and for the heavy guns a rolling
          tail of low-passed reflection clusters

The blast layers are glued with oversampled saturation and a look-ahead limiter (a few dB
of gain reduction on the crack) so the body is dense without clipping. Renders are mono
(positional) and contain no stereo tricks, so there is nothing to collapse.

Variations change micro-timing of the mechanism, crack length, every pitch (+-4 %), formant
placement, slap echo times and the reverb/noise seeds, so full-auto never repeats exactly.

Distant versions keep only what survives distance: a softened, low-passed crack that
arrives first, the boom a few tens of ms later through a steep low-pass, and a much wetter,
longer field tail with late slaps and rolling.
"""

import numpy as np

from . import mech
from .dsp import (Mix, band, bp, burst, conv, env, hp, limit, lp, make_ir, ns, phase, resonate,
                  saturate, sweep, tail_cut, tvec, undb)

VAR_PITCH = (0.0, 0.034, -0.03, 0.017, -0.012, 0.045)
VAR_TIME = (1.0, 0.93, 1.07, 0.97, 1.04, 0.9)
THUMP_SCALE = 0.62  # chest-thump level inside the boom (against the bark)
BODY_G = 0.5  # low-mid body level relative to the bark
CRACK_REL = 1.15  # crack peak relative to the glued body peak


# ----------------------------------------------------------------- layers

def _norm(x):
    return x / (np.max(np.abs(x)) + 1e-12)


def nwave(seconds):
    """Supersonic crack pressure signature: instant rise, linear fall through zero,
    instant return (an 'N'). 0.2-0.6 ms puts its energy at roughly 2-8 kHz."""
    m = max(3, ns(seconds))
    x = np.zeros(m + ns(0.004))
    x[:m] = np.linspace(1.0, -1.0, m)
    return x


def crack_layer(r, nw=0.00032, lo=2200.0, hi=8000.0, sizzle=0.01, sizzle_g=0.35, ring_f=3600.0, ring_g=0.18,
                extra=()):
    """Sharp transient: N-wave + band-limited snap + air-rip sizzle + muzzle-device ring.
    `extra` adds further N-waves [(delay_s, gain, nw_s)] (shotgun pellets)."""
    L = 0.09
    m = Mix(L)
    m.add(hp(nwave(nw), lo * 0.7, order=2), 0.0, 1.0)
    for dt, g, w in extra:
        m.add(hp(nwave(w), lo * 0.7, order=2), dt, g)
    snap = band(burst(r, 0.05, 0.0009, attack=0.00004), lo, hi, order=2)
    m.add(_norm(snap), 0.0, 0.85)
    sz = hp(burst(r, 0.07, sizzle, attack=0.0003), 3000, order=2)
    m.add(_norm(sz), 0.0002, sizzle_g)
    if ring_g > 0:
        m.add(_norm(mech.ring(r, [ring_f, ring_f * 1.47, ring_f * 2.09], [0.006, 0.004, 0.003], [1, 0.6, 0.35], 0.05)),
              0.0003, ring_g)
    return _norm(m.out())


def thump_layer(f0, f1, tau, decay, octave=0.45, drive=1.6):
    """Chest thump: pitch-dropping sine body + short octave partial, saturated, low-passed."""
    n = ns(decay * 7 + 0.04)
    t = tvec(n)
    f = f1 + (f0 - f1) * np.exp(-t / tau)
    body = np.sin(2 * np.pi * phase(f, n, 0.0)) * env(n, 0.0006, decay)
    up = np.sin(2 * np.pi * phase(2.0 * f, n, 0.0)) * env(n, 0.0004, decay * 0.4)
    x = saturate(body + octave * up, drive)
    return _norm(lp(x, 420, order=2))


def bark_layer(r, f, q=1.8, decay=0.024, tone=(640.0, 300.0), tone_g=0.45, grit=2.2, formants=(0.55, 1.0, 1.8, 2.9),
               lowpass=None):
    """Midrange punch: formant-filtered noise burst + falling tone, driven."""
    n = ns(decay * 9 + 0.02)
    nz = r.standard_normal(n) * env(n, 0.0003, decay)
    gains = (0.55, 1.0, 0.6, 0.3)[:len(formants)]
    qs = (1.2, q, q * 1.15, 1.5)[:len(formants)]
    x = _norm(resonate(nz, [f * k for k in formants], qs, gains))
    tn = np.sin(2 * np.pi * phase(sweep(tone[0], tone[1], n, tau=decay * 0.6), n)) * env(n, 0.0005, decay * 0.75)
    y = saturate(x + tone_g * tn, grit)
    if lowpass:
        y = lp(y, lowpass, order=4)
    return _norm(y)


def slaps(r, src, echoes, cutoff=3200.0):
    """Discrete slap echoes [(delay_s, gain)], each low-passed and blurred into a reflection."""
    if not echoes:
        return np.zeros(1)
    L = max(d for d, _ in echoes) + 0.06 + src.shape[-1] / 48000.0
    m = Mix(L)
    base = hp(lp(src, cutoff, order=2), 140.0, order=2)
    for i, (d, g) in enumerate(echoes):
        e = conv(base, mech.smear(r, 0.012 + 0.008 * i))
        m.add(lp(e, cutoff * (0.85 ** i)), d, g)
    return m.out()


def rolling(r, src, length, start=0.11, count=9, gap0=0.06, grow=1.22, decay=0.32, cutoff=1100.0):
    """Rolling tail: low-passed reflection clusters at growing gaps (distant terrain),
    each darker and blurrier than the last."""
    m = Mix(length + 0.3)
    base = hp(lp(src, cutoff, order=2), 90.0, order=2)
    t, gap = start, gap0
    for i in range(count):
        if t > length:
            break
        e = conv(base, mech.smear(r, 0.03 + 0.012 * i, decay=0.012 + 0.006 * i))
        m.add(lp(e, cutoff * (0.88 ** i), order=2), t * (1 + r.uniform(-0.06, 0.06)), np.exp(-t / decay) * r.uniform(0.7, 1.0))
        t += gap * (1 + r.uniform(-0.15, 0.15))
        gap *= grow
    return m.out()


def room_tail(r, src, t60, predelay, early, hf=0.35, lo_cut=170.0, hi_cut=9000.0, build=0.015):
    """Diffuse tail. Lows are kept out of the send and the IR so the sub stays in the
    short thump instead of droning under the reverb."""
    ir = make_ir(r, t60=t60, predelay=predelay, early=early, hf=hf, lf=0.9, build=build, lo_cut=lo_cut, hi_cut=hi_cut)
    return conv(hp(src, 110.0, order=2), ir)


# ----------------------------------------------------------------- mechanisms

def mech_ar(r, k, tj, P):
    """Gas-operated rifle / SMG / DMR: carrier unlocks and slams back, buffer spring
    compresses, carrier returns and locks."""
    m = Mix(0.25)
    tb, tf = P["t_back"] * tj, P["t_fwd"] * tj
    w = P.get("mech_w", 1.0)
    m.add(mech.clack(r, P["f_back"] * k, weight=0.8 * w, bright=1.1, mass=0.6), tb, 0.55)
    m.add(mech.zing(r, 1500 * k / w, 1100 * k / w, tf - tb + 0.02, decay=(tf - tb) * 0.6), tb + 0.002, 0.1)
    m.add(mech.friction(r, tf - tb, 2600 * k, 1800 * k, q=1.2, attack=0.002, decay=(tf - tb) * 0.4), tb + 0.003, 0.12)
    m.add(mech.clack(r, P["f_fwd"] * k, weight=1.1 * w, bright=0.9, mass=1.2), tf, 0.85)
    m.add(mech.latch(r, 5600 * k), tf + 0.003, 0.25)
    return m.out()


def mech_lmg(r, k, tj, P):
    """Belt-fed: feed tray / pawl clank, heavy bolt, and the belt links rattling."""
    m = Mix(0.3)
    m.add(mech_ar(r, k, tj, P), 0.0, 1.0)
    m.add(mech.clack(r, 1250 * k, weight=1.4, bright=0.7, mass=1.0), P["t_back"] * tj + 0.006, 0.45)  # feed pawl
    m.add(mech.rattle(r, 0.12, 16, f=3900 * k, decay_s=0.05), P["t_back"] * tj, 0.6)
    m.add(mech.rattle(r, 0.09, 8, f=2600 * k, decay_s=0.04), P["t_fwd"] * tj, 0.35)
    return m.out()


def mech_slide(r, k, tj, P):
    """Pistol: slide hits its rearward stop, returns into battery with a 'shk'."""
    m = Mix(0.2)
    tb, tf = P["t_back"] * tj, P["t_fwd"] * tj
    w = P.get("mech_w", 1.0)
    m.add(mech.clack(r, P["f_back"] * k, weight=0.85 * w, bright=1.2, mass=0.7), tb, 0.6)
    m.add(mech.friction(r, tf - tb + 0.004, 3000 * k, 2000 * k, q=1.0, grit=0.7, attack=0.002, decay=(tf - tb) * 0.5),
          tb + 0.002, 0.22)
    m.add(mech.clack(r, P["f_fwd"] * k, weight=1.0 * w, bright=1.1, mass=1.0), tf, 0.85)
    m.add(mech.latch(r, 6300 * k), tf + 0.0025, 0.2)
    return m.out()


def mech_pump(r, k, tj, P):
    """Pump shotgun: the fore-end racked back and slammed forward after the shot."""
    t0 = P["t_pump"] * tj
    return mech.rack(r, t0, t0 + 0.085 * tj, t0 + 0.11 * tj, t0 + 0.175 * tj, k=k * 0.9, weight=1.3, grit=0.7,
                     f_stop=1500.0, f_home=1250.0, spring=False, seconds=t0 + 0.4)


def mech_bolt(r, k, tj, P):
    """Bolt-action: handle lifts, bolt drawn back, pushed home, handle locked down."""
    t0 = P["t_bolt"]
    L = t0 + 0.55
    m = Mix(L)
    j = tj
    m.add(mech.clack(r, 2800 * k, weight=0.6, bright=1.2, mass=0.4), t0, 0.45)          # handle lift / cock
    m.add(mech.friction(r, 0.075 * j, 1700 * k, 2700 * k, q=1.3, grit=0.5, attack=0.01, decay=0.05), t0 + 0.03 * j, 0.35)
    m.add(mech.clack(r, 2000 * k, weight=1.0, bright=1.0, mass=0.8), t0 + 0.11 * j, 0.7)  # rear stop
    m.add(mech.friction(r, 0.06 * j, 2600 * k, 1500 * k, q=1.3, grit=0.5, attack=0.005, decay=0.04), t0 + 0.2 * j, 0.3)
    m.add(mech.clack(r, 1750 * k, weight=1.2, bright=0.9, mass=1.0), t0 + 0.265 * j, 0.75)  # bolt home
    m.add(mech.clack(r, 1500 * k, weight=1.4, bright=0.8, mass=1.3), t0 + 0.33 * j, 0.9)    # handle down, lock
    m.add(mech.latch(r, 5200 * k), t0 + 0.335 * j, 0.25)
    return m.out()


def mech_suppressed(r, k, tj, P):
    """Suppressed SMG: the action is the loudest part, plus the can's tube ring."""
    m = Mix(0.2)
    m.add(mech_ar(r, k, tj, P), 0.0, 1.0)
    m.add(mech.ring(r, [1180 * k, 2870 * k, 4610 * k], [0.02, 0.011, 0.007], [1, 0.5, 0.25], 0.1), 0.0008, 0.12)
    return m.out()


MECH = {"ar": mech_ar, "lmg": mech_lmg, "slide": mech_slide, "pump": mech_pump, "bolt": mech_bolt,
        "suppressed": mech_suppressed}


# ----------------------------------------------------------------- weapon classes

def _P(**kw):
    base = dict(
        nw=0.00032, c_lo=2200, c_hi=8000, sizzle=0.01, sizzle_g=0.35, ring_f=3600, ring_g=0.18, crack_g=1.0, extra=(),
        f0=135, f1=52, tau=0.018, decay=0.05, octave=0.45, thump_g=0.95,
        bark_f=820, bark_q=1.8, bark_d=0.03, tone=(640, 300), bark_g=0.75, grit=2.2, bark_lp=None, bark2=None,
        mech="ar", t_back=0.009, t_fwd=0.052, f_back=2300, f_fwd=1700, mech_g=0.42, mech_w=1.0,
        t60=0.95, pre=0.006, early=((0.004, 0.5), (0.013, 0.3), (0.027, 0.22), (0.041, 0.15)), slap=((0.07, 0.3), (0.13, 0.18)),
        wet=0.8, roll=0.0, roll_decay=0.32, hf=0.35, drive=1.6, glue=5.5, length=0.85, whoomp=0.0, hiss=0.0,
        far_delay=0.045, far_len=0.9, far_lp=1500.0, supersonic=True,
    )
    base.update(kw)
    return base


WEAPONS = {
    "FireRifle": _P(),
    "FireSMG": _P(nw=0.00024, c_lo=3000, c_hi=9000, sizzle=0.007, ring_f=4800, ring_g=0.2, crack_g=0.95,
                  f0=165, f1=70, tau=0.011, decay=0.035, thump_g=0.75,
                  bark_f=1150, bark_q=2.0, bark_d=0.02, tone=(900, 480), bark_g=0.7, grit=2.0,
                  t_back=0.006, t_fwd=0.034, f_back=2900, f_fwd=2500, mech_g=0.4, mech_w=0.75,
                  t60=0.7, early=((0.003, 0.45), (0.009, 0.3), (0.019, 0.2)), slap=((0.05, 0.25), (0.095, 0.12)),
                  wet=0.64, drive=1.5, glue=4.5, length=0.55, far_delay=0.035, far_len=0.7, far_lp=1800.0),
    "FireDMR": _P(nw=0.00042, c_lo=1800, c_hi=7500, sizzle=0.016, ring_f=3000, crack_g=1.1,
                  f0=120, f1=46, tau=0.022, decay=0.07, thump_g=1.0,
                  bark_f=700, bark_q=1.6, bark_d=0.04, tone=(520, 240), bark_g=0.8,
                  t_back=0.011, t_fwd=0.066, f_back=2000, f_fwd=1500, mech_g=0.45, mech_w=1.25,
                  t60=1.15, early=((0.005, 0.5), (0.016, 0.32), (0.031, 0.22), (0.052, 0.15)),
                  slap=((0.085, 0.35), (0.16, 0.22), (0.27, 0.12)), wet=0.88, roll=0.3, drive=1.7, glue=6.5, length=1.05,
                  far_delay=0.06, far_len=1.0, far_lp=1300.0),
    "FireLMG": _P(nw=0.00034, c_lo=2000, c_hi=7500, sizzle=0.012, ring_f=3300,
                  f0=125, f1=50, tau=0.02, decay=0.06, thump_g=1.0,
                  bark_f=640, bark_q=1.3, bark_d=0.0375, tone=(560, 260), bark_g=0.85, bark2=(380, 0.5),
                  mech="lmg", t_back=0.01, t_fwd=0.06, f_back=2100, f_fwd=1450, mech_g=0.45, mech_w=1.2,
                  t60=1.0, slap=((0.075, 0.32), (0.14, 0.2)), wet=0.88, roll=0.15, drive=1.8, glue=6.5, length=0.9,
                  far_delay=0.05, far_len=0.95, far_lp=1300.0),
    "FirePistol": _P(nw=0.00026, c_lo=2500, c_hi=8500, sizzle=0.008, ring_f=4200, ring_g=0.12,
                     f0=170, f1=75, tau=0.01, decay=0.032, thump_g=0.72,
                     bark_f=1250, bark_q=2.2, bark_d=0.02, tone=(1000, 520), bark_g=0.82, grit=2.0,
                     mech="slide", t_back=0.005, t_fwd=0.03, f_back=2600, f_fwd=2200, mech_g=0.45, mech_w=0.85,
                     t60=0.75, early=((0.003, 0.45), (0.01, 0.3), (0.021, 0.2)), slap=((0.055, 0.28), (0.1, 0.15)),
                     wet=0.72, drive=1.5, glue=5.0, length=0.6, far_delay=0.03, far_len=0.7, far_lp=1700.0),
    "FireMagnum": _P(nw=0.00048, c_lo=1500, c_hi=7000, sizzle=0.02, ring_f=2500, crack_g=1.15,
                     f0=105, f1=40, tau=0.028, decay=0.09, thump_g=1.1,
                     bark_f=520, bark_q=1.4, bark_d=0.05, tone=(420, 190), bark_g=0.95, grit=2.4,
                     mech="slide", t_back=0.008, t_fwd=0.06, f_back=1900, f_fwd=1600, mech_g=0.42, mech_w=1.35,
                     t60=1.3, early=((0.006, 0.5), (0.018, 0.34), (0.035, 0.25), (0.06, 0.16)),
                     slap=((0.09, 0.4), (0.18, 0.25), (0.3, 0.15)), wet=0.96, roll=0.45, roll_decay=0.38,
                     drive=1.8, glue=7.0, length=1.25, far_delay=0.05, far_len=1.1, far_lp=1200.0),
    "FireShotgun": _P(nw=0.0004, c_lo=1500, c_hi=6500, sizzle=0.018, ring_g=0.0, crack_g=0.85,
                      extra=((0.0006, 0.7, 0.00036), (0.0013, 0.55, 0.00044)),
                      f0=95, f1=42, tau=0.03, decay=0.085, thump_g=1.15,
                      bark_f=480, bark_q=1.0, bark_d=0.0625, tone=(380, 170), bark_g=1.0, grit=2.4, whoomp=0.6,
                      mech="pump", t_pump=0.36, mech_g=0.5,
                      t60=1.1, slap=((0.08, 0.38), (0.15, 0.25), (0.24, 0.12)), wet=0.96, roll=0.3,
                      drive=1.8, glue=6.5, length=1.1, far_delay=0.03, far_len=1.0, far_lp=1100.0),
    # The only sniper is the integrally suppressed VSR ("whisper-quiet" in AirsoftWeaponData), so its
    # cinematic voice is a heavy subsonic thwump through a long can, then the bolt is cycled.
    "FireSniper": _P(crack_g=0.0, hiss=0.2,
                     f0=112, f1=44, tau=0.02, decay=0.06, thump_g=0.95,
                     bark_f=360, bark_q=1.1, bark_d=0.035, tone=(320, 160), bark_g=0.8, grit=1.9, bark_lp=1100,
                     mech="bolt", t_bolt=0.55, mech_g=0.75,
                     t60=0.75, early=((0.004, 0.35), (0.011, 0.22), (0.022, 0.14)), slap=((0.06, 0.16), (0.12, 0.08)),
                     wet=0.45, hf=0.25, drive=1.5, glue=5.0, length=1.05, far_len=0.6, far_lp=900.0,
                     supersonic=False),
    "FireSuppressed": _P(crack_g=0.0, hiss=0.16,
                         f0=140, f1=62, tau=0.012, decay=0.04, thump_g=0.75,
                         bark_f=420, bark_q=1.2, bark_d=0.0275, tone=(380, 200), bark_g=0.75, grit=1.8, bark_lp=1300,
                         mech="suppressed", t_back=0.006, t_fwd=0.036, f_back=2600, f_fwd=2200, mech_g=1.1, mech_w=0.8,
                         t60=0.5, early=((0.003, 0.35), (0.008, 0.2)), slap=((0.04, 0.12),), wet=0.35, hf=0.25,
                         drive=1.4, glue=4.5, length=0.45, far_len=0.5, far_lp=900.0, supersonic=False),
}


def _var(r, v):
    k = 1.0 + VAR_PITCH[v % len(VAR_PITCH)] + r.uniform(-0.01, 0.01)
    tj = VAR_TIME[v % len(VAR_TIME)] * (1 + r.uniform(-0.03, 0.03))
    return k, tj


def blast(r, P, k, far=False):
    """The muzzle event: (crack, boom) where boom = thump + bark (+ extras)."""
    nwj = P["nw"] * (1 + r.uniform(-0.15, 0.15))
    crack = crack_layer(r, nwj, P["c_lo"] * k, P["c_hi"] * k, P["sizzle"], P["sizzle_g"], P["ring_f"] * k, P["ring_g"],
                        P["extra"]) if P["crack_g"] > 0 else np.zeros(1)
    fj = 1 + r.uniform(-0.05, 0.05)
    dk = 1.6 if far else 1.0
    th = thump_layer(P["f0"] * k, P["f1"] * k, P["tau"] * dk, P["decay"] * dk, P["octave"])
    bk = bark_layer(r, P["bark_f"] * k * fj, P["bark_q"], P["bark_d"] * dk, (P["tone"][0] * k, P["tone"][1] * k),
                    grit=P["grit"], lowpass=P["bark_lp"])
    m = Mix(0.6)
    m.add(th, 0.0002, P["thump_g"] * THUMP_SCALE)
    m.add(bk, 0.0004, P["bark_g"])
    # low-mid body (130-330 Hz): fills the gap between the thump and the bark
    body = band(burst(r, 0.35, P["bark_d"] * 1.4 * dk, attack=0.0006), 130 * k, 330 * k, order=2)
    m.add(_norm(saturate(_norm(body), 1.5)), 0.0003, BODY_G * P["bark_g"])
    if P["bark2"]:
        f2, g2 = P["bark2"]
        m.add(bark_layer(r, f2 * k, 1.1, P["bark_d"] * 1.4 * dk, (f2 * 0.9 * k, f2 * 0.45 * k), grit=2.0), 0.0006, g2)
    if P["whoomp"]:
        w = lp(burst(r, 0.4, 0.06 * dk, attack=0.0015), 1100, order=2)
        m.add(_norm(saturate(_norm(w), 1.6)), 0.0005, P["whoomp"])
    if P["hiss"]:  # subsonic gas hiss leaking from the can (suppressed)
        m.add(_norm(mech.pfft(r, 0.12, 0.022, 2800, 7500, attack=0.0015)), 0.001, P["hiss"])
        m.add(_norm(mech.pfft(r, 0.06, 0.009, 700, 2500, attack=0.0006)), 0.0, 0.35)
    return crack * P["crack_g"], m.out()


def shot(r, v, P):
    """Close/medium-range cinematic shot (mono).

    The boom, mechanism and environment form one body bus that is saturated and glued by
    the limiter; the crack is laid on top afterwards, untouched, so it stays the sharpest
    and highest peak (about 2-3 dB over the body)."""
    k, tj = _var(r, v)
    crack, boom = blast(r, P, k)
    L = P["length"] + 0.6
    boom = _norm(saturate(_norm(boom), P["drive"]))
    mechs = MECH[P["mech"]](r, k, tj, P) * P["mech_g"]
    cr = np.pad(crack, (0, max(0, len(boom) - len(crack))))[:len(boom)]
    mc = np.pad(mechs, (0, max(0, len(boom) - len(mechs))))[:len(boom)]
    send = boom + 0.3 * cr + 0.4 * mc
    sj = 1 + r.uniform(-0.12, 0.12)
    body = Mix(L)
    body.add(boom, 0.0, 1.0)
    body.add(mechs, 0.0, 1.0)
    body.add(room_tail(r, send, P["t60"] * (1 + r.uniform(-0.06, 0.06)), P["pre"], P["early"], hf=P["hf"]), 0.0, P["wet"])
    body.add(slaps(r, boom + 0.3 * cr, [(d * sj, g) for d, g in P["slap"]]), 0.0, 1.0)
    if P["roll"]:
        body.add(rolling(r, boom, P["length"], decay=P["roll_decay"]), 0.0, P["roll"])
    b = body.out()
    b = limit(b, np.max(np.abs(b)) * undb(-P["glue"]), lookahead=0.0015, hold=0.006, release=0.06)
    out = Mix(L)
    out.add(_norm(b), 0.0, 1.0)
    out.add(crack, 0.0, CRACK_REL * P["crack_g"])
    return tail_cut(out.out(), P["length"], fade_s=0.3 * P["length"])


def far_shot(r, v, P):
    """Distant version: crack first (if supersonic), boom later through a steep low-pass,
    no mechanism, wet field tail with late slaps and rolling."""
    k, tj = _var(r, v)
    crack, boom = blast(r, P, k, far=True)
    L = P["far_len"]
    m = Mix(L + 0.6)
    delay = P["far_delay"] * (1 + r.uniform(-0.12, 0.12))
    if P["supersonic"] and P["crack_g"] > 0:
        soft = conv(lp(crack, 4200, order=2), np.hanning(ns(0.0006)))  # rounded, duller crack
        m.add(_norm(soft), 0.0, 0.55 * min(1.0, P["crack_g"]))
    else:
        delay = 0.0
    b = saturate(hp(lp(boom, P["far_lp"] * k, order=4), 90.0, order=2), 1.3)
    m.add(_norm(b), delay, 1.0)
    if P["mech"] == "suppressed":  # far away a suppressed gun is mostly a dull 'tk' of the action
        m.add(lp(mech.clack(r, 2200 * k, weight=0.8), 3500, order=2), delay + P["t_fwd"] * tj, 0.25)
    dry = m.out()
    out = Mix(L + 0.8)
    out.add(dry, 0.0, 1.0)
    out.add(room_tail(r, lp(dry, 2500, order=2), 1.6 * (1 + r.uniform(-0.08, 0.08)), 0.018,
                      ((0.05, 0.3), (0.11, 0.22), (0.19, 0.15)), hf=0.22, lo_cut=120.0, hi_cut=4000.0, build=0.04),
            0.0, 0.85)
    sj = 1 + r.uniform(-0.15, 0.15)
    out.add(slaps(r, dry, [(0.17 * sj, 0.35), (0.31 * sj, 0.24), (0.48 * sj, 0.14)], cutoff=1500.0), 0.0, 1.0)
    out.add(rolling(r, dry, L, start=0.14, count=10, gap0=0.07, decay=0.42, cutoff=800.0), 0.0, 0.55)
    x = out.out()
    x = limit(x, np.max(np.abs(x)) * undb(-3.0), lookahead=0.002, hold=0.01, release=0.08)
    return tail_cut(x, L, fade_s=0.45 * L)


DESC = {
    "FireRifle": "balanced, punchy: 2-8 kHz crack, 135->52 Hz chest thump, 820 Hz bark, bolt carrier back/home at 9/52 ms, slaps + 0.95 s T60 tail",
    "FireSMG": "tight, fast, small: brighter shorter crack, 165->70 Hz thump, 1.15 kHz bark, quick light bolt (6/34 ms), 0.7 s T60 tail",
    "FireDMR": "heavier: longer crack, 120->46 Hz thump, 700 Hz bark, slower heavy carrier (11/66 ms), 1.15 s T60 tail, three slaps, some rolling",
    "FireLMG": "thick: double-formant bark (640 + 380 Hz), feed-pawl clank, belt-link rattle, heavy bolt, 1.0 s T60 tail",
    "FirePistol": "snappy: short bright crack, 170->75 Hz thump, 1.25 kHz bark, slide back + 'shk' into battery (5/30 ms), 0.75 s T60 tail",
    "FireMagnum": "huge: long crack, 105->40 Hz thump, 520 Hz bark, heavy slow slide (8/60 ms), 1.3 s T60 tail with long rolling",
    "FireShotgun": "wide boom: three pellet cracks + low whoomp, 95->42 Hz thump, pump racked back and slammed home at ~0.36-0.53 s",
    "FireSniper": "suppressed bolt-action: heavy 112->44 Hz thwump + low-passed bark, subsonic gas hiss, bolt cycled (lift/back/home/lock) at 0.55-0.88 s",
    "FireSuppressed": "muffled 140->62 Hz thump + low-passed bark, quiet subsonic gas hiss, bolt carrier is the loudest part, small 0.5 s T60 tail",
}
FAR_DESC = "distant: softened crack first, low-passed boom ~{d} ms later, wet field tail with late slaps and rolling"


def _shot_fn(P):
    return lambda r, v: shot(r, v, P)


def _far_fn(P):
    return lambda r, v: far_shot(r, v, P)


RECIPES = {key: (_shot_fn(P), 4, DESC[key]) for key, P in WEAPONS.items()}

FAR_RECIPES = {}
for _key, _P_ in WEAPONS.items():
    _d = "no crack (subsonic), dull thud + faint action, field tail" if not _P_["supersonic"] else \
        FAR_DESC.format(d=int(round(_P_["far_delay"] * 1000)))
    FAR_RECIPES[_key + "_Far"] = (_far_fn(_P_), 2, _d)
