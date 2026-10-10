"""Synth instruments shared by the stings and the music loops."""

import numpy as np

from .dsp import (band, burst, bp, conv, env, env_pts, hp, lp, make_ir, modes, ns,
                  phase, pulse, saturate, saw, sweep, thump, tvec, tvf, ROOMS)


def midi(n):
    return 440.0 * 2.0 ** ((np.asarray(n, float) - 69.0) / 12.0)


def adsr(n, a, d, s, rel, gate):
    """ADSR with a gate (s) after which the release starts; n samples total."""
    t = tvec(n)
    e = np.where(t < a, t / max(a, 1e-6), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-6)))
    g_end = np.interp(gate, t, e) if gate < t[-1] else e[-1]
    return np.where(t < gate, e, g_end * np.exp(-(t - gate) / max(rel, 1e-6)))


# ----------------------------------------------------------------- tonal

def brass(r, f, seconds, gate=None, bright=1.0, attack=0.03, vib=0.006, detune_c=6.0):
    """Brass-like section voice: detuned saws through a blooming low-pass."""
    n = ns(seconds)
    t = tvec(n)
    gate = gate or seconds * 0.7
    v = 1.0 + vib * np.clip((t - 0.35) / 0.3, 0, 1) * np.sin(2 * np.pi * 5.3 * t + r.uniform(0, 6))
    x = sum(saw(f * v * 2 ** (c / 1200.0), n, r.random()) for c in (-detune_c, 0.0, detune_c)) / 3.0
    bloom = env_pts(n, [(0, 0.0), (attack * 1.6, 1.0), (attack * 5, 0.62), (seconds, 0.5)])
    fc = np.clip(f * (1.5 + 7.0 * bright * bloom), 150, 16000)
    y = tvf(x, "lp", fc, q=0.9, order=2)
    y = saturate(y * 1.3, 1.6) * adsr(n, attack, 0.25, 0.8, 0.35, gate)
    return y


def bell(r, f, seconds, bright=1.0, decay=1.2):
    """Glockenspiel / chime: bar partials with fast-dying highs + strike tick."""
    ratios = np.array([1.0, 2.756, 5.404, 8.933, 13.34])
    amps = np.array([1.0, 0.5, 0.28, 0.14, 0.07]) * np.array([1, bright, bright, bright ** 2, bright ** 2])
    decs = decay * np.array([1.0, 0.45, 0.22, 0.12, 0.07])
    x = modes(seconds, f * ratios, decs, amps, rng=r, attack=0.0008, beat=0.8)
    x += 0.15 * hp(burst(r, seconds, 0.0006, attack=0.0001), 4000)
    return x


def piano(r, f, seconds, vel=0.7, gate=None):
    """Additive piano-ish tone: stiff-string partials, two-stage decay, hammer thunk."""
    n = ns(seconds)
    t = tvec(n)
    gate = gate or seconds
    B = 0.00035
    T0 = 2.8 * (220.0 / f) ** 0.45
    out = np.zeros(n)
    for k in range(1, 25):
        fk = k * f * np.sqrt(1 + B * k * k)
        if fk > 9000:
            break
        a = k ** -1.1 * np.exp(-k / (3.0 + 7.0 * vel))
        Tk = T0 / (1 + 0.38 * (k - 1))
        nk = min(n, ns(Tk * 9.2))  # stop once the partial is ~-80 dB
        tk = t[:nk]
        e = 0.65 * np.exp(-tk / (Tk * 0.18)) + 0.35 * np.exp(-tk / Tk)
        ph = r.uniform(0, 2 * np.pi)
        det = 1 + r.uniform(0.2, 0.6) / 1200.0
        out[:nk] += a * e * 0.5 * (np.sin(2 * np.pi * fk * tk + ph) + np.sin(2 * np.pi * fk * det * tk + ph))
    out *= np.where(t < gate, 1.0, np.exp(-(t - gate) / 0.12))
    out *= np.clip(t / 0.002, 0, 1)
    ham = bp(burst(r, 0.04, 0.004, attack=0.0003), min(f * 3, 4000), 1.0)
    out[:len(ham)] += ham * 0.25 * vel
    return out


def pluck(r, f, seconds, bright=1.0, decay=0.18, width=0.35):
    """Arp pluck: saw + pulse through a fast-closing low-pass."""
    n = ns(seconds)
    x = 0.6 * saw(f, n, r.random()) + 0.4 * pulse(f * 1.003, n, width, r.random())
    fc = f * (1.2 + 10 * bright * np.exp(-tvec(n) / (decay * 0.5)))
    return tvf(x, "lp", np.clip(fc, 80, 15000), q=1.2) * env(n, 0.002, decay)


def pad_voice(r, f, n, detune_c=11.0, voices=4):
    """Wide detuned-saw pad, returns stereo (2, n)."""
    out = np.zeros((2, n))
    for ch in range(2):
        for i in range(voices):
            c = detune_c * (2 * i / (voices - 1) - 1) * (1.0 if ch == 0 else -0.85) + r.uniform(-2, 2)
            out[ch] += saw(f * 2 ** (c / 1200.0), n, r.random())
    return out / voices


# ----------------------------------------------------------------- drums

def kick(r, seconds=0.45, f0=150.0, f1=46.0, decay=0.32, click=0.5, drive=1.6):
    n = ns(seconds)
    body = np.sin(2 * np.pi * phase(sweep(f0, f1, n, tau=0.028), n, 0.25)) * env(n, 0.0008, decay)
    c = hp(burst(r, seconds, 0.0012, attack=0.0001), 1500) * click
    return saturate(body + c, drive)


def hat(r, seconds=0.12, decay=0.035, tone=1.0):
    """808-style metallic hat: six detuned square oscillators + noise, high-passed."""
    n = ns(seconds)
    sq = sum(pulse(fq * tone, n, 0.5, r.random()) for fq in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0))
    x = 0.7 * sq / 6 + 0.5 * r.standard_normal(n)
    x = hp(bp(x, 10000, 0.9), 7000)
    return x * env(n, 0.0005, decay)


def clap(r, seconds=0.35):
    n = ns(seconds)
    out = np.zeros(n)
    t0 = 0.0
    for i in range(4):
        dec = 0.003 if i < 3 else 0.055
        b = bp(burst(r, seconds - t0, dec, attack=0.0003), 1150, 1.1) + 0.3 * bp(burst(r, seconds - t0, dec), 2500, 1.5)
        k = ns(t0)
        out[k:] += b[:n - k] * (0.8 if i < 3 else 1.0)
        t0 += 0.0085 + 0.0025 * r.random()
    return out


# ----------------------------------------------------------------- cinematic

def cinematic_hit(r, seconds=1.6, depth=1.0):
    """Deep trailer hit: transient crack, sub drop, low-mid thump, metallic clang."""
    n = ns(seconds)
    t = tvec(n)
    x = np.zeros(n)
    x += 0.9 * hp(burst(r, seconds, 0.004, attack=0.0002), 600)
    x += 1.3 * depth * np.sin(2 * np.pi * phase(sweep(62, 31, n, tau=0.25), n, 0.25)) * env(n, 0.002, 0.55)
    x += 0.8 * thump(seconds, 190, 85, 0.06)
    x += 0.55 * lp(burst(r, seconds, 0.22, attack=0.002), 1400)
    clang = modes(seconds, [98, 147.3, 212.6, 311.1, 467.9, 702.2], [0.9, 0.7, 0.55, 0.4, 0.3, 0.2],
                  [1, 0.8, 0.6, 0.45, 0.3, 0.2], rng=r, beat=0.7)
    x += 0.35 * clang * (1 - np.exp(-t / 0.01))
    return saturate(x, 1.4)


def wet_only(x, r, room="cinema", ch=2, **kw):
    params = dict(ROOMS[room])
    params.update(kw)
    ir = make_ir(r, ch=ch, **params)
    return conv(x, ir) if x.ndim == 1 else np.stack([conv(x[i], ir[i]) for i in range(2)])


def reverse_swell(r, seconds=0.45):
    """Reversed cymbal + chord reverb that builds and stops dead on the downbeat."""
    src = hp(burst(r, 1.2, 0.35, attack=0.001), 1800) * 0.6
    src = src + 0.4 * modes(1.2, [220, 330, 440, 587, 880], 0.5, [1, 0.7, 0.6, 0.4, 0.3], rng=r)
    w = wet_only(src, r, "cinema")
    rev = w[:, ::-1]
    k = ns(seconds)
    out = rev[:, -k:]
    out = out * np.linspace(0, 1, k) ** 1.5
    return out / (np.max(np.abs(out)) + 1e-9)


def riser(r, seconds=2.0):
    """Tension riser: sweeping noise band + rising detuned saws + accelerating ticks (stereo)."""
    n = ns(seconds)
    t = tvec(n)
    ramp = (t / seconds) ** 2.2
    nz = r.standard_normal((2, n))
    fc = sweep(250, 7000, n)
    noise = np.stack([tvf(nz[c], "bp", fc, q=1.4) for c in range(2)]) * ramp
    f = 55 * 2 ** (2.0 * (t / seconds) ** 1.6)
    tone = np.stack([saw(f * 1.004, n, 0.1) + saw(f * 2.0, n, 0.3), saw(f * 0.996, n, 0.6) + saw(f * 2.003, n, 0.8)])
    tone = np.stack([tvf(tone[c], "lp", f * 6, q=1.5) for c in range(2)]) * (0.25 + 0.75 * ramp)
    ticks = np.zeros(n)
    tt, gap = 0.0, 0.26
    tick = modes(0.05, [3100, 4650, 6900], [0.006, 0.004, 0.003], [1, 0.6, 0.3], rng=r)
    while tt < seconds - 0.03:
        k = ns(tt)
        seg = tick[:max(0, min(len(tick), n - k))]
        ticks[k:k + len(seg)] += seg * (0.3 + 0.7 * tt / seconds)
        tt += gap
        gap = max(0.035, gap * 0.86)
    return 0.6 * noise + 0.35 * tone + 0.35 * np.stack([ticks, ticks])


# ----------------------------------------------------------------- neo-noir palette
# (added for the cinematic score: FM metal, analog bass/lead, electric piano, vibes,
#  upright bass, heavy and industrial drums, brushes and ride)

PLATE = np.array([1.0, 1.593, 2.135, 2.653, 3.155, 3.65, 4.06, 4.6])  # circular-plate-like ratios


def fm(r, f, seconds, ratio=1.0, index=2.0, index_decay=0.3, index_floor=0.0, decay=0.6, attack=0.002):
    """Two-operator FM voice: index envelope decays from `index` to `index_floor`."""
    n = ns(seconds)
    t = tvec(n)
    idx = index_floor + (index - index_floor) * np.exp(-t / max(index_decay, 1e-4))
    mod = np.sin(2 * np.pi * f * ratio * t + r.uniform(0, 2 * np.pi))
    return np.sin(2 * np.pi * f * t + idx * mod) * env(n, attack, decay)


def metal(r, f, seconds=1.2, decay=0.5, bright=1.0, click=0.3, beat=0.6):
    """Struck metal (plate / pipe): inharmonic modes, highs die first, strike click."""
    amps = np.array([1.0, 0.8, 0.65, 0.5, 0.42, 0.33, 0.25, 0.2]) * np.r_[1, 1, bright, bright, bright ** 2, bright ** 2, bright ** 3, bright ** 3]
    decs = decay * np.array([1.0, 0.8, 0.62, 0.5, 0.4, 0.32, 0.26, 0.2])
    x = modes(seconds, f * PLATE, decs, amps, rng=r, attack=0.0004, beat=beat)
    x = x / (np.max(np.abs(x)) + 1e-12)
    return x + click * hp(burst(r, seconds, 0.0008, attack=0.00005), 2500)


def sub_boom(r, seconds=1.5, f0=70.0, f1=28.0, tau=0.2, decay=0.6, drive=1.8):
    """Distorted downward sub hit with a low noise body."""
    n = ns(seconds)
    x = np.sin(2 * np.pi * phase(sweep(f0, f1, n, tau=tau), n, 0.0)) * env(n, 0.002, decay)
    x += 0.35 * lp(burst(r, seconds, decay * 0.25, attack=0.002), 300)
    return lp(saturate(x, drive), 900)


def taiko(r, f=62.0, seconds=1.0, decay=0.28, stick=0.5):
    """Big low drum: pitched membrane drop, skin noise, stick click."""
    n = ns(seconds)
    body = np.sin(2 * np.pi * phase(sweep(f * 2.1, f, n, tau=0.03), n, 0.0)) * env(n, 0.001, decay)
    skin = bp(burst(r, seconds, decay * 0.35, attack=0.0008), f * 5.2, 0.9)
    over = np.sin(2 * np.pi * phase(sweep(f * 3.4, f * 2.6, n, tau=0.05), n)) * env(n, 0.001, decay * 0.3)
    click = hp(burst(r, seconds, 0.0015, attack=0.0001), 1800)
    return saturate(body + 0.5 * skin + 0.25 * over + stick * click, 1.5)


def snare(r, seconds=0.5, tone=190.0, decay=0.16, snap=1.0, wires=1.0):
    """Snare: two shell modes + wire noise + stick snap."""
    n = ns(seconds)
    t = tvec(n)
    shell = (np.sin(2 * np.pi * tone * t) + 0.6 * np.sin(2 * np.pi * tone * 1.72 * t)) * env(n, 0.0008, decay * 0.35)
    wire = bp(r.standard_normal(n), 4200, 0.6) * env(n, 0.001, decay) * wires
    wire += 0.5 * bp(r.standard_normal(n), 1900, 0.9) * env(n, 0.001, decay * 0.6) * wires
    s = hp(burst(r, seconds, 0.0012, attack=0.00008), 1200) * snap
    return saturate(0.8 * shell + 0.7 * wire + 0.6 * s, 1.4)


def tom(r, f=95.0, seconds=0.8, decay=0.22):
    n = ns(seconds)
    body = np.sin(2 * np.pi * phase(sweep(f * 1.6, f, n, tau=0.04), n, 0.0)) * env(n, 0.001, decay)
    skin = bp(burst(r, seconds, 0.03, attack=0.0008), f * 4, 1.0)
    return saturate(body + 0.3 * skin, 1.3)


def ride(r, seconds=1.2, decay=0.45, bell=0.3):
    """Ride cymbal: dense inharmonic squares + noise, bright, long; optional bell."""
    n = ns(seconds)
    sq = sum(pulse(fq, n, 0.5, r.random()) for fq in (312.0, 419.4, 541.7, 677.3, 811.9, 1033.1, 1284.6))
    x = hp(0.6 * sq / 7 + 0.4 * r.standard_normal(n), 3500) * env(n, 0.001, decay)
    b = modes(seconds, [2120.0, 3180.0, 4730.0], [decay * 0.5, decay * 0.35, decay * 0.25], [1, 0.5, 0.3], rng=r)
    return x + bell * b


def brush(r, seconds=0.25, decay=0.08, lo=1500.0, hi=7000.0, attack=0.02):
    """Brush swish on a snare: soft band-limited noise with a rounded attack."""
    n = ns(seconds)
    return band(r.standard_normal(n), lo, hi) * env(n, attack, decay)


def rim(r, seconds=0.08, f=1650.0):
    """Cross-stick / rim click: woody high modes + click."""
    x = modes(seconds, [f, f * 1.48, f * 2.3], [0.012, 0.008, 0.005], [1, 0.6, 0.3], rng=r, attack=0.0002)
    return x + 0.4 * hp(burst(r, seconds, 0.0006, attack=0.00005), 2000)


def shaker(r, seconds=0.07, decay=0.018):
    n = ns(seconds)
    return hp(r.standard_normal(n), 5500) * env(n, 0.004, decay)


def analog(r, f, seconds, cutoff=800.0, env_amt=2.0, f_decay=0.15, reso=1.2, detune_c=7.0, sub=0.5, gate=None,
           attack=0.004, release=0.06, drive=1.4, square=0.0):
    """Analog-style mono synth: detuned saws (+ optional square) + sub sine through an
    enveloped low-pass with resonance, gently driven. `f` may be a per-sample array (glide)."""
    n = ns(seconds)
    f = np.broadcast_to(np.asarray(f, float), (n,))
    x = 0.5 * saw(f * 2 ** (detune_c / 1200), n, r.random()) + 0.5 * saw(f * 2 ** (-detune_c / 1200), n, r.random())
    if square:
        x = x + square * pulse(f * 0.5, n, 0.5, r.random())
    x += sub * np.sin(2 * np.pi * phase(f * 0.5, n))
    t = tvec(n)
    fc = np.clip(cutoff * (1 + env_amt * np.exp(-t / max(f_decay, 1e-3))), 40, 16000)
    y = tvf(x, "lp", fc, q=reso, order=4)
    gate = seconds - release if gate is None else gate
    return saturate(y, drive) * adsr(n, attack, 0.2, 0.85, release, gate)


def epiano(r, f, seconds, vel=0.7, gate=None, trem=0.0):
    """Electric piano (tine-ish FM): mellow 1:1 body + bell-like 14:1 attack transient."""
    n = ns(seconds)
    t = tvec(n)
    gate = gate or seconds
    T = 1.6 * (261.6 / f) ** 0.35
    body_idx = (0.6 + 1.6 * vel) * np.exp(-t / 0.5) + 0.25
    body = np.sin(2 * np.pi * f * t + body_idx * np.sin(2 * np.pi * f * t))
    tine = np.sin(2 * np.pi * f * t + (1.5 * vel) * np.exp(-t / 0.015) * np.sin(2 * np.pi * f * 14.0 * t))
    e = 0.7 * np.exp(-t / T) + 0.3 * np.exp(-t / (T * 0.2))
    x = (body + 0.35 * vel * (tine - np.sin(2 * np.pi * f * t))) * e
    x *= np.where(t < gate, 1.0, np.exp(-(t - gate) / 0.09)) * np.clip(t / 0.0015, 0, 1)
    if trem:
        x *= 1 - trem * (0.5 + 0.5 * np.sin(2 * np.pi * 4.6 * t))
    return x


def vibes(r, f, seconds, vel=0.7, motor=0.25, motor_hz=5.2):
    """Vibraphone: bar partials (1, 4, 10) with a soft mallet and motor tremolo."""
    n = ns(seconds)
    t = tvec(n)
    T = 2.2 * (440.0 / f) ** 0.3
    x = modes(seconds, [f, f * 3.98, f * 9.85], [T, T * 0.22, T * 0.06], [1.0, 0.3 * vel, 0.08 * vel], rng=r, attack=0.002)
    x *= 1 - motor * (0.5 + 0.5 * np.sin(2 * np.pi * motor_hz * t + r.uniform(0, 6)))
    return x


def upright(r, f, seconds, vel=0.8, gate=None):
    """Plucked upright bass: low harmonics with fast-dying upper partials, finger thump."""
    n = ns(seconds)
    t = tvec(n)
    gate = gate or seconds
    out = np.zeros(n)
    for k in range(1, 9):
        a = vel * k ** -1.3
        d = 1.1 / (1 + 0.9 * (k - 1))
        out += a * np.sin(2 * np.pi * k * f * (1 + 0.0004 * k * k) * t + r.uniform(0, 6)) * np.exp(-t / d)
    out += 0.3 * lp(burst(r, seconds, 0.012, attack=0.001), 400)
    out *= np.where(t < gate, 1.0, np.exp(-(t - gate) / 0.05)) * np.clip(t / 0.003, 0, 1)
    return lp(out, 1800)


def stack(r, freqs, seconds, cutoff=1500.0, reso=0.9, detune_c=9.0, attack=0.05, release=0.4, gate=None, voices=3,
          drive=1.2):
    """Chord of detuned saws through a static low-pass (pads, stabs, swells); stereo."""
    n = ns(seconds)
    out = np.zeros((2, n))
    for f in np.atleast_1d(freqs):
        for c in range(2):
            for i in range(voices):
                d = detune_c * (2 * i / max(voices - 1, 1) - 1) * (1 if c == 0 else -0.8)
                out[c] += saw(f * 2 ** (d / 1200), n, r.random())
    out /= voices * len(np.atleast_1d(freqs)) ** 0.7
    out = lp(out, cutoff, q=reso)
    gate = seconds - release if gate is None else gate
    return saturate(out, drive) * adsr(n, attack, 0.3, 0.9, release, gate)
