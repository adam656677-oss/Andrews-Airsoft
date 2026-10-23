"""Player feedback, replay / bullet-time effects, UI and stingers. HitCall is positional
mono; everything else is 2D stereo.

The stingers share the score's palette and its C# minor tonal centre: FM metal, analog
synth stacks, a distorted sub and big low drums (see instruments.py)."""

import numpy as np

from .dsp import (Mix, band, bp, burst, colored, conv, env, env_pts, hp, lp, make_ir, modes, ns, pan, phase,
                  saturate, smooth_random, space, stereo, sweep, tail_cut, thump, tvec, tvf)
from .instruments import (analog, fm, metal, midi, reverse_swell, ride, snare, stack, sub_boom, taiko, wet_only)
from . import mech

ST = {"ch": 2}
STLOOP = {"ch": 2, "loop": True}


def _ui(x, r, length, wet=0.04, room="small"):
    return tail_cut(space(stereo(x), r, room, wet, ch=2), length, min(0.02, length * 0.4))


def _norm(x):
    return x / (np.max(np.abs(x)) + 1e-12)


def _wide(x, r, amount=0.5, ms=11.0):
    """Mono -> stereo with a short decorrelating delay on the side signal (mono-safe)."""
    d = ns(ms / 1000.0)
    side = np.concatenate([np.zeros(d), x[:-d]]) - x
    return np.stack([x + amount * 0.5 * side, x - amount * 0.5 * side])


# ----------------------------------------------------------------- feedback

def hit_marker(r, v):
    """Hit confirm: a short, punchy low-mid 'thwack' (pitched body + driven noise slap)
    with a tiny bright tick riding 4 ms behind it."""
    m = Mix(0.13)
    m.add(thump(0.08, 300, 125, 0.014, pitch_tau=0.006), 0.0, 0.9)
    slap = bp(burst(r, 0.06, 0.009, attack=0.0004), 1350, 1.1) + 0.4 * bp(burst(r, 0.06, 0.006, attack=0.0003), 2600, 1.4)
    m.add(_norm(slap), 0.0003, 0.75)
    m.add(hp(burst(r, 0.01, 0.0005, attack=0.00004), 1800), 0.0, 0.35)
    body = saturate(m.out(), 1.7)
    tick = mech.latch(r, 7200, 0.015)
    out = Mix(0.13, stereo=True)
    out.add(body, 0.0, 1.0)
    out.add(tick, 0.004, 0.32, pan_pos=0.12)
    out.add(tick * 0.6, 0.0046, 0.2, pan_pos=-0.12)
    return tail_cut(space(out.out(), r, "small", 0.05, ch=2), 0.13, 0.03)


def hit_call(r, v):
    """'HIT!' call as a loud pea-whistle chirp: sharp rising onset, pea trill, stronger
    harmonics and a little drive so it cuts through gunfire; mostly dry."""
    L = 0.34
    n = ns(L)
    f = env_pts(n, [(0, 2350), (0.012, 3080), (0.045, 3200), (0.22, 3140), (L, 2780)])
    trill_rate = 40 + 4 * smooth_random(r, n, 6)
    tr = 0.5 + 0.5 * np.sin(2 * np.pi * phase(trill_rate, n))
    f = f + 60 * tr
    ph = phase(f, n)
    tone = np.sin(2 * np.pi * ph) + 0.28 * np.sin(4 * np.pi * ph) + 0.12 * np.sin(6 * np.pi * ph) + 0.05 * np.sin(8 * np.pi * ph)
    tone *= 1 - 0.55 * tr ** 2
    breath = bp(r.standard_normal(n), 3150, 5.0) * 0.3 + hp(r.standard_normal(n), 5000) * 0.05
    e = env_pts(n, [(0, 0), (0.004, 1.0), (0.03, 0.92), (0.25, 0.88), (L, 0.0)])
    x = saturate((tone + breath) * e * 0.9, 1.3)
    x = x + 0.6 * bp(x, 3200, 1.2)  # presence
    return tail_cut(space(x, r, "outdoor", 0.09, t60=0.5, lo_cut=500), 0.5, 0.14)


def _heartbeat(r, lub=1.0, dub=0.6, gap=0.2, depth=1.0):
    """One deep heartbeat (lub-dub): pitched chest thumps + damped low noise."""
    L = gap + 0.45
    m = Mix(L)
    for at, g, f0 in ((0.0, lub, 64.0), (gap, dub, 72.0)):
        th = thump(0.4, f0 * depth, 36.0 * depth, 0.075, pitch_tau=0.02, attack=0.006)
        th += 0.5 * lp(burst(r, 0.4, 0.035, attack=0.004), 140)
        th += 0.18 * lp(bp(burst(r, 0.4, 0.02, attack=0.003), 210, 1.2), 400)
        m.add(th, at, g)
    return saturate(m.out(), 1.3)


def tagged(r, v):
    """You've been hit (~1.5 s): low cinematic thud, the world goes muffled with a dull
    ringing, and two heartbeat pulses as it clears."""
    L = 1.55
    n = ns(L)
    m = Mix(L, stereo=True)
    thud = sub_boom(r, 0.9, f0=88, f1=31, tau=0.06, decay=0.22, drive=2.0)
    thud = thud + 0.55 * lp(burst(r, 0.9, 0.05, attack=0.0015), 700) + 0.35 * bp(burst(r, 0.9, 0.012, attack=0.0005), 900, 1.0)
    m.add(saturate(thud, 1.4), 0.0, 1.0)
    # muffled ringing: a beating pair low in the mids, swelling in after the hit
    rn = ns(1.45)
    rt = tvec(rn)
    re = np.clip(rt / 0.12, 0, 1) * np.exp(-np.maximum(rt - 0.35, 0) / 0.42)
    ring = np.stack([np.sin(2 * np.pi * 1870 * rt) + 0.4 * np.sin(2 * np.pi * 3742 * rt + 0.5),
                     np.sin(2 * np.pi * 1877 * rt + 1.0) + 0.4 * np.sin(2 * np.pi * 3749 * rt + 1.3)])
    ring = lp(ring, 2600, order=4)
    m.add(ring * re, 0.04, 0.06)
    # pressure bed: dark noise that opens up again as the hearing returns
    bed = colored(r, n, -6.0, ch=2) * env_pts(n, [(0, 0), (0.05, 1.0), (0.6, 0.5), (L, 0.0)])
    bed = np.stack([tvf(bed[c], "lp", env_pts(n, [(0, 250), (0.8, 300), (L, 1600)]), q=0.8) for c in range(2)])
    m.add(bed, 0.0, 0.18)
    hb = _heartbeat(r, 1.0, 0.65, 0.19)
    m.add(hb, 0.48, 0.55)
    m.add(hb, 1.04, 0.38)
    x = m.out()
    return tail_cut(space(x, r, "small", 0.1, ch=2, hf=0.2), L, 0.25)


# ----------------------------------------------------------------- replay / bullet time

def replay_whoosh(r, v):
    """Slow-motion entry (~1.2 s): a reversed reverb swell that sucks in to ~0.45 s, then
    a low whoosh dropping in pitch and a time-stretched 'breath' smearing underneath."""
    L = 1.25
    n = ns(L)
    m = Mix(L, stereo=True)
    peak = 0.46
    m.add(reverse_swell(r, peak), 0.0, 0.5)
    # pitch-dropping whoosh: noise band falling 2.6 kHz -> 180 Hz, plus a sub drop
    wn = ns(L - peak + 0.12)
    wt = tvec(wn)
    nz = r.standard_normal((2, wn))
    fc = sweep(2600, 180, wn)
    wh = np.stack([tvf(nz[c], "bp", fc * (1.0 + 0.04 * c), q=1.6) for c in range(2)])
    we = env_pts(wn, [(0, 0), (0.07, 1.0), (0.3, 0.6), (wt[-1], 0.0)])
    m.add(wh * we, peak - 0.1, 0.9)
    sub = np.sin(2 * np.pi * phase(sweep(150, 34, wn, tau=0.18), wn)) * env_pts(wn, [(0, 0), (0.05, 1.0), (wt[-1], 0.0)])
    m.add(saturate(sub, 1.6), peak - 0.06, 0.55)
    # time-stretched breath: vowel-formant noise with slow grain flutter
    bn = ns(1.0)
    bt = tvec(bn)
    b = r.standard_normal((2, bn))
    f1 = sweep(780, 480, bn)
    br = np.stack([tvf(b[c], "bp", f1, q=4.0) + 0.6 * tvf(b[c], "bp", f1 * 1.9, q=5.0) for c in range(2)])
    grain = 0.65 + 0.35 * np.sin(2 * np.pi * phase(sweep(22, 9, bn), bn))
    br *= grain * env_pts(bn, [(0, 0), (0.35, 1.0), (0.7, 0.6), (bt[-1], 0.0)])
    m.add(lp(br, 2400), 0.2, 0.35)
    x = m.out()
    x = x + 0.25 * wet_only(x, r, "cinema", t60=2.4)[:, :n]
    return tail_cut(x, L, 0.3)


def replay_impact(r, v):
    """Slowed-down hit (~1.5 s): a gunshot-like impact pitched far down (sub drop, slow
    bark, smeared crack), with a shimmer of debris particles drifting through a hall."""
    L = 1.55
    n = ns(L)
    m = Mix(L, stereo=True)
    boom = sub_boom(r, 1.5, f0=62, f1=22, tau=0.15, decay=0.42, drive=2.2)
    bark = bp(burst(r, 1.0, 0.11, attack=0.004), 210, 1.2) + 0.5 * bp(burst(r, 1.0, 0.07, attack=0.003), 480, 1.5)
    tone = np.sin(2 * np.pi * phase(sweep(180, 55, ns(1.0), tau=0.12), ns(1.0))) * env(ns(1.0), 0.004, 0.16)
    crack = lp(burst(r, 0.3, 0.025, attack=0.0025), 1600) + 0.4 * band(burst(r, 0.3, 0.012, attack=0.002), 900, 3000)
    hit = Mix(1.5)
    hit.add(boom, 0.0, 1.0)
    hit.add(_norm(saturate(_norm(bark) + 0.6 * tone, 2.0)), 0.003, 0.75)
    hit.add(_norm(crack), 0.0, 0.5)
    h = saturate(hit.out(), 1.5)
    m.add(_wide(h, r, 0.3), 0.0, 1.0)
    # debris shimmer: tiny metal/glass particles, thinning out and panned around
    count = 70
    times = np.sort(0.03 + r.gamma(1.4, 0.22, count))
    times = times[times < 1.35]
    for t0 in times:
        f = r.uniform(2800, 9500)
        p = modes(0.25, [f, f * 1.37, f * 2.11], [0.05, 0.03, 0.02], [1, 0.5, 0.25], rng=r)
        m.add(p, t0, 0.13 * np.exp(-t0 / 0.7) * r.uniform(0.4, 1.0), pan_pos=r.uniform(-0.85, 0.85))
    sh = hp(colored(r, n, -3.0, ch=2), 5500) * env_pts(n, [(0, 0), (0.05, 1.0), (0.5, 0.4), (L, 0.0)])
    m.add(sh, 0.0, 0.07)
    x = m.out()
    x = x + 0.35 * wet_only(x, r, "cinema", t60=2.8)[:, :n]
    return tail_cut(x, L, 0.4)


def slowmo_heartbeat(r, v):
    """Bullet-time heartbeat, 2.0 s seamless loop (one slow, deep lub-dub = 30 BPM) over a
    low pressure bed; built circularly so the loop point is continuous."""
    L = 2.0
    n = ns(L)
    m = Mix(L, stereo=True, circular=True)
    hb = np.pad(_heartbeat(r, 1.0, 0.62, 0.23, depth=0.85), (0, ns(0.7)))
    hb = hb + 0.3 * wet_only(hb, r, "small", ch=1, t60=0.5)[:len(hb)]
    m.add(np.stack([hb, hb]), 0.05, 1.0)
    t = tvec(n)
    bed = lp(colored(r, n, -6.0, ch=2), 110, circular=True)
    swell = 0.6 + 0.4 * np.cos(2 * np.pi * (t - 0.05) / L)  # the 'blood rush' swells with the beat
    m.add(bed * swell, 0.0, 0.06)
    rush = band(colored(r, n, -3.0, ch=2), 250, 700, circular=True) * (0.5 + 0.5 * np.cos(2 * np.pi * (t - 0.15) / L)) ** 2
    m.add(rush, 0.0, 0.025)
    return m.out()


def announce(r, v):
    """Reversed swell into a deep hit (sub drop, low drum, dark metal, distorted C# minor
    stab) at 0.45 s, ~1.8 s total."""
    hit_at = 0.45
    L = 1.85
    m = Mix(L, stereo=True)
    m.add(reverse_swell(r, hit_at), 0.0, 0.42)
    h = Mix(L - hit_at)
    h.add(sub_boom(r, 1.4, f0=66, f1=30, tau=0.12, decay=0.45), 0.0, 1.0)
    h.add(taiko(r, 58, 1.0, decay=0.3), 0.0, 0.6)
    h.add(metal(r, 92.5, 1.4, decay=0.6, bright=0.6, click=0.2), 0.002, 0.3)
    m.add(h.out(), hit_at, 1.0)
    chord = stack(r, midi([37, 44, 49, 52]), 1.3, cutoff=900, attack=0.004, release=0.7, gate=0.5, drive=2.2)
    m.add(chord, hit_at, 0.35)
    x = m.out()
    x = x + 0.3 * wet_only(x, r, "cinema")[:, :x.shape[-1]]
    return tail_cut(x, L, 0.5)


def ui_click(r, v):
    """Refined soft click (~40 ms)."""
    m = Mix(0.04)
    m.add(modes(0.04, [1900, 3800], [0.004, 0.002], [1.0, 0.4], rng=r, attack=0.0002), 0.0, 1.0)
    m.add(lp(burst(r, 0.01, 0.0006, attack=0.00005), 6000), 0.0, 0.35)
    m.add(thump(0.03, 700, 520, 0.006), 0.0, 0.3)
    return _ui(m.out(), r, 0.04, 0.03)


def ui_hover(r, v):
    """Very soft, short tick with a rounded onset."""
    m = Mix(0.03)
    m.add(modes(0.03, [3100, 1550], [0.003, 0.004], [0.8, 0.5], rng=r, attack=0.0012), 0.0, 1.0)
    return _ui(lp(m.out(), 7000), r, 0.03, 0.02)


def capture_tick(r, v):
    """Subtle capture-progress tick: a short metallic FM blip over a soft click."""
    m = Mix(0.11)
    m.add(fm(r, 1760, 0.1, ratio=1.41, index=2.2, index_decay=0.012, decay=0.022, attack=0.0008), 0.0, 0.8)
    m.add(fm(r, 880, 0.1, ratio=2.0, index=0.8, index_decay=0.02, decay=0.03, attack=0.001), 0.0, 0.35)
    m.add(lp(burst(r, 0.01, 0.0005, attack=0.00005), 5000), 0.0, 0.25)
    return _ui(m.out(), r, 0.11, 0.06)


def point_captured(r, v):
    """Point secured: two struck-metal FM tones rising a fourth (G#5 -> C#6) over a low
    thump and a soft C# fifth, in a dark hall."""
    L = 1.15
    m = Mix(L, stereo=True)
    for at, note, p in ((0.0, 80, -0.2), (0.13, 85, 0.2)):
        f = float(midi(note))
        tone = fm(r, f, 1.0, ratio=3.5, index=3.0, index_decay=0.05, index_floor=0.3, decay=0.38)
        tone += 0.35 * fm(r, f * 2.0, 1.0, ratio=1.41, index=1.5, index_decay=0.02, decay=0.12)
        m.add(tone, at, 0.55, pan_pos=p)
    m.add(thump(0.35, 160, 70, 0.07, pitch_tau=0.02), 0.13, 0.45)
    m.add(stack(r, midi([49, 56]), 1.0, cutoff=1300, attack=0.01, release=0.45, gate=0.4), 0.13, 0.18)
    return tail_cut(space(m.out(), r, "hall", 0.22, ch=2, t60=1.5), L, 0.35)


# ----------------------------------------------------------------- stingers

def _hit(r, seconds, depth=1.0, metal_f=69.3):
    """Heavy cinematic hit: distorted sub drop + big drum + snare crack + dark metal."""
    h = Mix(seconds)
    h.add(sub_boom(r, seconds, f0=64 * depth, f1=27, tau=0.14, decay=0.5), 0.0, 1.0)
    h.add(taiko(r, 55, min(seconds, 1.2), decay=0.32), 0.0, 0.7)
    h.add(snare(r, 0.6, tone=170, decay=0.22), 0.0, 0.32)
    h.add(metal(r, metal_f, seconds, decay=0.55, bright=0.55, click=0.15), 0.002, 0.28)
    return saturate(h.out(), 1.3)


def round_start(r, v):
    """Tension riser (noise sweep, rising FM metal, accelerating ticks, reversed swell)
    into a heavy hit at 1.95 s, ~2.5 s total."""
    hit_at = 1.95
    L = 2.5
    n = ns(hit_at)
    t = tvec(n)
    ramp = (t / hit_at) ** 2.0
    m = Mix(L, stereo=True)
    nz = r.standard_normal((2, n))
    noise = np.stack([tvf(nz[c], "bp", sweep(220, 6500, n) * (1 + 0.03 * c), q=1.5) for c in range(2)]) * ramp
    m.add(noise, 0.0, 0.5)
    f = float(midi(37)) * 2 ** (2.0 * (t / hit_at) ** 1.7)  # C#2 rising two octaves
    rise = np.stack([saturate(analog(r, f * 2 ** (c * 0.06 / 12), hit_at, cutoff=300, env_amt=0.0, reso=1.4, sub=0.2,
                                     release=0.01), 1.4) for c in range(2)])
    rise = np.stack([tvf(rise[c], "lp", 250 + 4000 * ramp, q=1.3) for c in range(2)]) * (0.25 + 0.75 * ramp)
    m.add(rise, 0.0, 0.35)
    tick = fm(r, 2200, 0.06, ratio=1.41, index=2.5, index_decay=0.01, decay=0.012)
    tt, gap = 0.0, 0.3
    while tt < hit_at - 0.03:
        m.add(tick, tt, 0.12 + 0.3 * tt / hit_at, pan_pos=0.3 * np.sin(tt * 9))
        tt += gap
        gap = max(0.04, gap * 0.85)
    m.add(reverse_swell(r, 0.5), hit_at - 0.5, 0.45)
    m.add(_hit(r, L - hit_at), hit_at, 1.0)
    x = m.out()
    x = x + 0.22 * wet_only(x, r, "hall")[:, :x.shape[-1]]
    return tail_cut(x, L, 0.35)


def victory(r, v):
    """Triumphant but dark (~3.5 s): drums drive A -> B -> C# major (a minor key resolving
    to its major tonic) as a synth chord stack rises and opens; big hit on the resolve."""
    L = 3.5
    m = Mix(L, stereo=True)
    chords = [(0.0, [45, 52, 57, 61, 64], 0.36), (0.36, [47, 54, 59, 63, 66], 0.36),
              (0.72, [37, 49, 56, 61, 65, 68, 75], 2.6)]
    for i, (at, notes, dur) in enumerate(chords):
        held = i == 2
        c = stack(r, midi(notes), dur + (0.8 if held else 0.12), cutoff=1200 + 900 * i, attack=0.012,
                  release=0.9 if held else 0.08, gate=dur, drive=1.5)
        if held:  # the resolve keeps opening up
            nn = c.shape[-1]
            c = np.stack([tvf(c[ch], "lp", env_pts(nn, [(0, 1800), (1.2, 5200), (nn / 48000, 3000)]), q=0.9)
                          for ch in range(2)])
        m.add(c, at, 0.42 if held else 0.36)
    for at, g in ((0.0, 0.55), (0.18, 0.4), (0.36, 0.6), (0.54, 0.45), (0.63, 0.5)):
        m.add(taiko(r, 66, 0.8, decay=0.22), at, g)
        m.add(snare(r, 0.4, tone=200, decay=0.12), at, 0.15 * g)
    m.add(_hit(r, 2.6, metal_f=69.3), 0.72, 0.95)
    lead = fm(r, float(midi(80)), 2.4, ratio=3.0, index=2.2, index_decay=0.25, index_floor=0.4, decay=1.2, attack=0.03)
    m.add(lead, 0.72, 0.18, pan_pos=0.25)
    m.add(ride(r, 2.6, decay=0.9, bell=0.5), 0.72, 0.12, pan_pos=-0.3)
    x = m.out()
    x = x + 0.3 * wet_only(x, r, "hall")[:, :x.shape[-1]]
    return tail_cut(x, L, 0.7)


def defeat(r, v):
    """Low and descending (~3.5 s): C# minor sinking through B and A to G# over a gliding
    bass, two slow low drums, everything darkening into the reverb."""
    L = 3.5
    m = Mix(L, stereo=True)
    seq = [(0.0, [49, 52, 56], 37), (0.62, [47, 51, 54], 35), (1.24, [45, 49, 52], 33), (1.86, [44, 48, 51], 32)]
    for i, (at, notes, bass) in enumerate(seq):
        last = i == 3
        dur = 1.6 if last else 0.62
        c = stack(r, midi(notes), dur + 0.6, cutoff=1100 - 180 * i, attack=0.06, release=0.6, gate=dur, drive=1.3)
        m.add(c, at, 0.34)
    bn = ns(3.0)
    bf = env_pts(bn, [(0, float(midi(37))), (0.6, float(midi(37))), (0.66, float(midi(35))), (1.22, float(midi(35))),
                      (1.28, float(midi(33))), (1.84, float(midi(33))), (1.92, float(midi(32))), (2.6, float(midi(32))),
                      (3.0, float(midi(30)))])
    m.add(analog(r, bf, 3.0, cutoff=260, env_amt=0.5, f_decay=0.4, reso=1.1, sub=0.8, gate=2.5, release=0.45), 0.0, 0.5)
    m.add(taiko(r, 50, 1.4, decay=0.45, stick=0.2), 0.0, 0.55)
    m.add(taiko(r, 44, 1.6, decay=0.6, stick=0.15), 1.86, 0.7)
    m.add(sub_boom(r, 1.6, f0=52, f1=26, tau=0.3, decay=0.7), 1.86, 0.5)
    m.add(metal(r, 103.8, 1.6, decay=0.8, bright=0.35, click=0.0), 1.87, 0.12)
    x = m.out()
    x = x + 0.35 * wet_only(x, r, "hall", t60=3.0)[:, :x.shape[-1]]
    n = x.shape[-1]
    x = np.stack([tvf(x[c], "lp", env_pts(n, [(0, 5000), (1.8, 2600), (n / 48000, 900)]), q=0.7) for c in range(2)])
    return tail_cut(x, L, 0.8)


def rank_up(r, v):
    """Bright metallic ascent (~2 s): FM bell arpeggio rising through E major add9 and #11
    colours, a soft upward air sweep and a shimmer tail."""
    L = 2.05
    m = Mix(L, stereo=True)
    notes = [76, 83, 87, 90, 92, 95, 99]
    for i, note in enumerate(notes):
        f = float(midi(note))
        b = fm(r, f, 1.5, ratio=3.5, index=2.6, index_decay=0.04, index_floor=0.25, decay=0.55 + 0.05 * i)
        b += 0.3 * fm(r, f * 2, 1.5, ratio=1.0, index=0.6, index_decay=0.1, decay=0.3)
        m.add(b, 0.065 * i, 0.32, pan_pos=-0.6 + 0.2 * i)
    m.add(stack(r, midi([64, 71, 75, 78]), 1.6, cutoff=2600, attack=0.25, release=0.6, gate=0.9), 0.15, 0.14)
    an = ns(0.5)
    air = np.stack([tvf(r.standard_normal(an), "bp", sweep(1500, 9000, an), q=2.0) for _ in range(2)])
    m.add(air * env_pts(an, [(0, 0), (0.4, 1.0), (0.5, 0.0)]), 0.0, 0.12)
    for _ in range(16):
        at = 0.35 + r.random() * 0.9
        f = r.uniform(5000, 9500)
        m.add(modes(0.2, [f], [0.03], [1.0], rng=r), at, 0.05, pan_pos=r.uniform(-0.8, 0.8))
    m.add(thump(0.6, 140, 82, 0.15, pitch_tau=0.05), 0.0, 0.25)
    x = m.out()
    x = x + 0.32 * wet_only(x, r, "hall")[:, :x.shape[-1]]
    return tail_cut(x, L, 0.5)


RECIPES = {
    "HitMarker": (hit_marker, 1, "2D hit confirm: punchy low-mid 'thwack' (pitched body + driven slap) + tiny high tick", ST),
    "HitCall": (hit_call, 1, "Positional pea-whistle chirp standing in for a 'HIT!' call: sharper onset, more harmonics, drier"),
    "Tagged": (tagged, 1, "2D you're hit (~1.5 s): low cinematic thud, muffled ringing, pressure bed opening up, two heartbeats", ST),
    "ReplayWhoosh": (replay_whoosh, 1, "2D slow-motion entry (~1.2 s): reversed swell, low pitch-dropping whoosh, time-stretched breath", ST),
    "ReplayImpact": (replay_impact, 1, "2D slowed-down impact (~1.5 s): massive sub/bark boom + debris shimmer in a hall", ST),
    "SlowMoHeartbeat": (slowmo_heartbeat, 1, "2D bullet-time bed, 2.0 s seamless loop: one deep slow lub-dub over a pressure bed", STLOOP),
    "Announce": (announce, 1, "2D: reversed swell into a deep hit (sub, drum, metal, distorted C#m stab) at 0.45 s (~1.8 s)", ST),
    "UIClick": (ui_click, 1, "2D refined soft click (~40 ms)", ST),
    "UIHover": (ui_hover, 1, "2D very soft tick (~30 ms)", ST),
    "RoundStart": (round_start, 1, "2D riser (noise, rising synth, accelerating ticks, reverse swell) into a heavy hit at 1.95 s (~2.5 s)", ST),
    "Victory": (victory, 1, "2D triumphant but dark (~3.5 s): driving drums, A -> B -> C# major synth stack opening up, big hit", ST),
    "Defeat": (defeat, 1, "2D low descending (~3.5 s): C#m -> B -> A -> G# over a gliding bass, slow low drums, darkening", ST),
    "RankUp": (rank_up, 1, "2D bright metallic ascent (~2 s): FM bell arpeggio (E major add9/#11), air sweep, shimmer", ST),
    "CaptureTick": (capture_tick, 1, "2D subtle metallic capture-progress tick (~0.1 s)", ST),
    "PointCaptured": (point_captured, 1, "2D point secured: two FM metal tones G#5 -> C#6 over a low thump (~1.1 s)", ST),
}
