"""Player feedback, UI and stingers. HitCall is positional mono; everything
else is 2D stereo."""

import numpy as np

from .dsp import (Mix, bp, burst, colored, env, env_pts, hp, lp, modes, ns, pan, phase,
                  saturate, smooth_random, space, stereo, tail_cut, thump, tvec)
from .instruments import bell, brass, cinematic_hit, midi, reverse_swell, riser, wet_only

ST = {"ch": 2}


def _ui(x, r, length, wet=0.04, room="small"):
    return tail_cut(space(stereo(x), r, room, wet, ch=2), length, min(0.02, length * 0.4))


# ----------------------------------------------------------------- feedback

def hit_marker(r, v):
    """Crisp confirm tick: transient + two bright blips + a touch of body."""
    m = Mix(0.09)
    m.add(hp(burst(r, 0.01, 0.0004, attack=0.00003), 2000), 0.0, 0.5)
    m.add(modes(0.08, [3150, 4720, 6300], [0.012, 0.008, 0.005], [1, 0.55, 0.3], rng=r, attack=0.0003), 0.0, 1.0)
    m.add(thump(0.03, 1400, 900, 0.004), 0.0, 0.3)
    return _ui(m.out(), r, 0.09)


def hit_call(r, v):
    """'HIT!' call as a loud pea-whistle chirp: rising onset, pea trill, breath."""
    L = 0.32
    n = ns(L)
    t = tvec(n)
    f = env_pts(n, [(0, 2450), (0.018, 3050), (0.05, 3170), (0.22, 3120), (L, 2750)])
    trill_rate = 38 + 4 * smooth_random(r, n, 6)
    tr = 0.5 + 0.5 * np.sin(2 * np.pi * phase(trill_rate, n))
    f = f + 55 * tr
    ph = phase(f, n)
    tone = np.sin(2 * np.pi * ph) + 0.12 * np.sin(4 * np.pi * ph) + 0.04 * np.sin(6 * np.pi * ph)
    tone *= 1 - 0.5 * tr ** 2
    breath = bp(r.standard_normal(n), 3100, 5.0) * 0.3 + hp(r.standard_normal(n), 5000) * 0.04
    e = env_pts(n, [(0, 0), (0.006, 1.0), (0.24, 0.9), (L, 0.0)])
    x = (tone + breath) * e
    return tail_cut(space(x, r, "outdoor", 0.15, t60=0.6, lo_cut=400), 0.5, 0.15)


def tagged(r, v):
    """You've been hit: body thud, tinnitus ring, muffled breath (stereo)."""
    L = 1.55
    n = ns(L)
    t = tvec(n)
    m = Mix(L, stereo=True)
    thud = thump(0.45, 95, 42, 0.11, pitch_tau=0.02) + 0.6 * lp(burst(r, 0.45, 0.03, attack=0.001), 500)
    thud = thud + 0.4 * bp(burst(r, 0.45, 0.008, attack=0.0003), 1100, 1.0)
    m.add(saturate(thud, 1.5), 0.0, 1.0)
    m.add(colored(r, ns(0.8), -6.0) * env(ns(0.8), 0.04, 0.25) * 0.5, 0.0, 0.35)
    ring_n = ns(1.45)
    rt = tvec(ring_n)
    ring_env = np.clip(rt / 0.08, 0, 1) * np.exp(-np.maximum(rt - 0.3, 0) / 0.33)
    ring = np.stack([np.sin(2 * np.pi * 6800 * rt), np.sin(2 * np.pi * 6831 * rt + 1.0)])
    ring += 0.25 * np.stack([np.sin(2 * np.pi * 3400 * rt), np.sin(2 * np.pi * 3412 * rt)])
    m.add(ring * ring_env, 0.03, 0.09)
    nz = r.standard_normal((2, n))
    ex = env_pts(n, [(0, 0), (0.25, 0), (0.45, 1.0), (0.7, 0.0), (L, 0)])
    inh = env_pts(n, [(0, 0), (0.85, 0), (1.15, 0.7), (1.38, 0.0), (L, 0)])
    breath = lp(nz, 650, order=4) * ex + lp(bp(nz, 900, 1.2), 1400, order=4) * inh * 0.6
    m.add(breath, 0.0, 0.45)
    x = m.out()
    return tail_cut(space(x, r, "small", 0.12, ch=2, hf=0.2), L, 0.3)


def announce(r, v):
    """Deep cinematic boom preceded by a short reversed swell (hit at 0.45 s)."""
    hit_at = 0.45
    L = 1.85
    m = Mix(L, stereo=True)
    m.add(reverse_swell(r, hit_at), 0.0, 0.45)
    h = cinematic_hit(r, L - hit_at)
    m.add(h, hit_at, 1.0)
    x = m.out()
    x = x + 0.32 * wet_only(x, r, "cinema")[:, :x.shape[-1]]
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
    """Subtle progress beep."""
    n = ns(0.11)
    t = tvec(n)
    x = (np.sin(2 * np.pi * 1320 * t) + 0.2 * np.sin(2 * np.pi * 2640 * t)) * env(n, 0.003, 0.03)
    return _ui(x, r, 0.11, 0.05)


def point_captured(r, v):
    """Confirming two-tone chime (E5 -> B5) with a soft low confirm."""
    L = 1.1
    m = Mix(L, stereo=True)
    m.add(bell(r, midi(76), 0.9, bright=0.6, decay=0.6), 0.0, 0.8, pan_pos=-0.15)
    m.add(bell(r, midi(83), 0.95, bright=0.7, decay=0.7), 0.14, 0.9, pan_pos=0.15)
    m.add(thump(0.25, 220, 160, 0.06), 0.14, 0.3)
    return tail_cut(space(m.out(), r, "hall", 0.18, ch=2, t60=1.4), L, 0.35)


# ----------------------------------------------------------------- stingers

def round_start(r, v):
    """Tense riser into a hit at 2.0 s."""
    hit_at = 2.0
    L = 2.6
    m = Mix(L, stereo=True)
    m.add(riser(r, hit_at), 0.0, 0.8)
    m.add(cinematic_hit(r, L - hit_at, depth=0.9), hit_at, 1.0)
    x = m.out()
    x = x + 0.22 * wet_only(x, r, "hall")[:, :x.shape[-1]]
    return tail_cut(x, L, 0.35)


def victory(r, v):
    """Bold brass sting: two F-major stabs then a held Bb-major chord, timpani, crash."""
    L = 3.1
    m = Mix(L, stereo=True)
    stab = [53, 57, 60, 65]
    for at in (0.0, 0.16):
        for i, note in enumerate(stab):
            m.add(brass(r, midi(note), 0.3, gate=0.11, bright=1.1, attack=0.015), at, 0.32, pan_pos=-0.5 + i / 3)
    final = [46, 53, 58, 62, 65, 70]
    for i, note in enumerate(final):
        m.add(brass(r, midi(note), 2.75, gate=1.9, bright=1.0, attack=0.03), 0.32, 0.3, pan_pos=-0.6 + 1.2 * i / 5)
    m.add(thump(1.4, 92, 58, 0.45, pitch_tau=0.05), 0.32, 0.9)
    crash = lp(hp(burst(r, 2.4, 0.5, attack=0.002), 3500), 11000)
    m.add(np.stack([crash, np.roll(crash, 37)]), 0.32, 0.12)
    x = m.out()
    x = x + 0.28 * wet_only(x, r, "hall")[:, :x.shape[-1]]
    return tail_cut(x, L, 0.6)


def defeat(r, v):
    """Low somber sting: Ab major sinks to C minor with a slow, dark brass swell."""
    L = 3.1
    m = Mix(L, stereo=True)
    for i, note in enumerate([44, 51, 56, 60]):
        m.add(brass(r, midi(note), 1.5, gate=1.0, bright=0.35, attack=0.12, vib=0.0), 0.0, 0.3, pan_pos=-0.45 + 0.3 * i)
    for i, note in enumerate([36, 43, 48, 51, 55]):
        m.add(brass(r, midi(note), 2.1, gate=1.3, bright=0.3, attack=0.15, vib=0.003), 1.0, 0.3, pan_pos=-0.5 + 0.25 * i)
    m.add(thump(1.5, 70, 38, 0.5, pitch_tau=0.06), 1.0, 0.8)
    m.add(thump(1.0, 80, 45, 0.3, pitch_tau=0.05), 0.0, 0.5)
    x = m.out()
    x = x + 0.32 * wet_only(x, r, "hall")[:, :x.shape[-1]]
    return tail_cut(lp(x, 5000), L, 0.7)


def rank_up(r, v):
    """Bright ascending chime: C6-E6-G6-C7-E7 bells, sparkle and a soft swell."""
    L = 2.1
    m = Mix(L, stereo=True)
    notes = [84, 88, 91, 96, 100]
    for i, note in enumerate(notes):
        m.add(bell(r, midi(note), 1.6, bright=0.9, decay=0.9), 0.075 * i, 0.55, pan_pos=-0.5 + 0.25 * i)
    for i, note in enumerate([72, 76, 79]):
        m.add(bell(r, midi(note), 1.6, bright=0.4, decay=1.1), 0.3, 0.35, pan_pos=-0.2 + 0.2 * i)
    for _ in range(14):
        at = 0.25 + r.random() * 0.9
        f = r.uniform(5000, 9000)
        m.add(modes(0.2, [f], [0.03], [1.0], rng=r), at, 0.07, pan_pos=r.uniform(-0.8, 0.8))
    m.add(thump(0.8, 130, 98, 0.3, pitch_tau=0.1), 0.3, 0.3)
    x = m.out()
    x = x + 0.3 * wet_only(x, r, "hall")[:, :x.shape[-1]]
    return tail_cut(x, L, 0.5)


RECIPES = {
    "HitMarker": (hit_marker, 1, "2D crisp short tick confirming a tag", ST),
    "HitCall": (hit_call, 1, "Positional loud pea-whistle chirp standing in for a 'HIT!' call (whistle only, no voice)"),
    "Tagged": (tagged, 1, "2D: low body thud + short tinnitus ring + muffled low-passed breath (~1.5 s)", ST),
    "Announce": (announce, 1, "2D: short reversed swell into a deep cinematic boom (~1.8 s, hit at 0.45 s)", ST),
    "UIClick": (ui_click, 1, "2D refined soft click (~40 ms)", ST),
    "UIHover": (ui_hover, 1, "2D very soft tick (~30 ms)", ST),
    "RoundStart": (round_start, 1, "2D tense riser into a hit at 2.0 s (~2.6 s)", ST),
    "Victory": (victory, 1, "2D bold brass synth sting in Bb major (~3 s)", ST),
    "Defeat": (defeat, 1, "2D low somber brass sting, Ab -> C minor (~3 s)", ST),
    "RankUp": (rank_up, 1, "2D bright ascending bell chime (~2 s)", ST),
    "CaptureTick": (capture_tick, 1, "2D subtle capture-progress beep", ST),
    "PointCaptured": (point_captured, 1, "2D confirming two-tone chime E5 -> B5", ST),
}
