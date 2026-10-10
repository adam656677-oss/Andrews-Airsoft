"""Ambience loops: stereo, 60 s, seamless by construction.

Every layer is built circularly: noise beds are coloured in the FFT domain
(periodic), slow modulators come from periodic random spectra, filters and
reverbs run as circular convolutions, and one-shot events that would run past
the end wrap around to the start. The last sample therefore flows into the
first exactly as any other pair of neighbouring samples would.
"""

import numpy as np

from . import foley, weapons
from .dsp import (SR, Mix, bp, burst, colored, conv, env, env_pts, eq, hp, lp, make_ir,
                  modes, ns, pan, phase, resample_fft, saw, scatter, sine, smooth_random,
                  stft_apply, sweep, thump, tvec, ROOMS)
from .instruments import kick

L = 60.0
LOOP = {"ch": 2, "loop": True}


# ----------------------------------------------------------------- helpers

def lvl(x, rms_db):
    rms = np.sqrt(np.mean(np.asarray(x) ** 2)) + 1e-12
    return x * (10 ** (rms_db / 20.0) / rms)


def per(f):
    """Round a frequency so it completes a whole number of cycles per loop."""
    return max(1.0, round(f * L)) / L


def verb(x, r, room, wet, **kw):
    """Circular stereo reverb (wet + dry) for loop buses."""
    p = dict(ROOMS[room])
    p.update(kw)
    ir = make_ir(r, ch=2, **p)
    x = np.stack([x, x]) if x.ndim == 1 else x
    w = np.stack([conv(x[i], ir[i], circular=True) for i in range(2)])
    return x + wet * w


def wide_noise(r, n, slope=-3.0, shared=0.75):
    c = colored(r, n, slope)
    s = colored(r, n, slope, ch=2)
    return shared * c[None, :] + (1 - shared) * 1.4 * s


def grit(r, n, rate=60.0):
    g = np.abs(lp(r.standard_normal(n), rate, circular=True))
    return g / (g.max() + 1e-12)


# ----------------------------------------------------------------- field

def wind(r, n):
    g = 0.5 + 0.5 * smooth_random(r, n, 0.06)
    g2 = 0.5 + 0.5 * smooth_random(r, n, 0.22)
    gust = np.clip(0.3 + 0.7 * g * (0.7 + 0.3 * g2), 0, 1)
    pink = wide_noise(r, n, -3.0, 0.7)
    low = lp(pink, 240, circular=True)
    mid = bp(pink, 480, 0.7, circular=True)
    hi = bp(pink, 1250, 0.9, circular=True)
    air = hp(pink, 3500, circular=True)
    w = 0.55 * low + mid * (0.25 + 0.75 * gust) + 0.55 * hi * gust ** 2 + 0.1 * air * gust ** 3
    leaves = hp(r.standard_normal((2, n)), 2400, circular=True) * grit(r, n, 45) * gust ** 3
    return w + 0.35 * leaves


def _tweets(r):
    out = []
    f0 = r.uniform(2800, 5200)
    up = r.random() < 0.5
    for _ in range(int(r.integers(3, 8))):
        d = r.uniform(0.035, 0.08)
        n = ns(d)
        f = sweep(f0 * (0.8 if up else 1.25), f0 * (1.25 if up else 0.8), n)
        ph = phase(f, n)
        s = (np.sin(2 * np.pi * ph) + 0.15 * np.sin(4 * np.pi * ph)) * np.hanning(n)
        out.append(s)
        out.append(np.zeros(ns(r.uniform(0.07, 0.15))))
    return np.concatenate(out)


def _warble(r):
    d = r.uniform(0.5, 1.2)
    n = ns(d)
    t = tvec(n)
    fc = r.uniform(3000, 4600)
    f = fc + r.uniform(300, 650) * np.sin(2 * np.pi * r.uniform(22, 38) * t) + 400 * np.sin(2 * np.pi * t / d * r.uniform(0.5, 1.5))
    a = (0.6 + 0.4 * np.sin(2 * np.pi * r.uniform(9, 14) * t)) * env_pts(n, [(0, 0), (0.03, 1), (d - 0.08, 0.8), (d, 0)])
    return np.sin(2 * np.pi * phase(f, n)) * a


def _whistle(r):
    parts = []
    f1 = r.uniform(3600, 4100)
    for f, d in ((f1, r.uniform(0.22, 0.3)), (f1 * r.uniform(0.82, 0.88), r.uniform(0.25, 0.35))):
        n = ns(d)
        fq = f * (1 + 0.02 * np.linspace(1, -1, n))
        parts.append(np.sin(2 * np.pi * phase(fq, n)) * env_pts(n, [(0, 0), (0.02, 1), (d - 0.05, 0.85), (d, 0)]))
        parts.append(np.zeros(ns(0.05)))
    return np.concatenate(parts)


def _crow(r):
    parts = []
    for _ in range(int(r.integers(2, 4))):
        d = r.uniform(0.22, 0.32)
        n = ns(d)
        f0 = r.uniform(380, 480) * (1 - 0.15 * np.linspace(0, 1, n))
        src = saw(f0, n) + 0.3 * r.standard_normal(n)
        s = bp(src, 1100, 2.0) + 0.7 * bp(src, 1750, 3.0)
        parts.append(s * env_pts(n, [(0, 0), (0.02, 1), (d * 0.6, 0.8), (d, 0)]))
        parts.append(np.zeros(ns(r.uniform(0.15, 0.3))))
    return lp(np.concatenate(parts), 3000)


def birds(r, n):
    m = Mix(L, stereo=True, circular=True)
    plan = [(_tweets, 22), (_warble, 8), (_whistle, 6), (_crow, 2)]
    for fn, count in plan:
        for _ in range(count):
            call = fn(r)
            dist = r.uniform(0.0, 1.0)
            call = lp(call, 9000 - 5000 * dist)
            m.add(call, r.uniform(0, L), (0.6 - 0.45 * dist) * (0.5 if fn is _crow else 1.0), pan_pos=r.uniform(-0.9, 0.9))
    return verb(m.out(), r, "field_far", 0.35)


def insects(r, n):
    out = np.zeros((2, n))
    for _ in range(3):
        fc = r.uniform(4200, 5000)
        syl = int(r.integers(3, 5))
        k = np.zeros(ns(0.028 * syl + 0.02))
        sn = ns(0.016)
        s = np.sin(2 * np.pi * fc * tvec(sn)) * np.hanning(sn)
        for j in range(syl):
            a = ns(0.028 * j)
            k[a:a + sn] += s
        period = r.uniform(0.55, 0.95)
        times = np.arange(0, L, period) + r.normal(0, 0.008, int(np.ceil(L / period)))
        keep = r.random(len(times)) > 0.12
        times = times[keep]
        swell = 0.6 + 0.4 * smooth_random(r, n, 0.05)
        c = scatter(n, times, np.ones(len(times)), k, circular=True) * swell
        c = lp(c, 7000, circular=True)
        out += pan(c, r.uniform(-0.8, 0.8)) * r.uniform(0.3, 1.0)
    t = tvec(n)
    buzz = hp(r.standard_normal(n), 6500, circular=True) * (0.5 + 0.5 * np.sin(2 * np.pi * per(110) * t)) ** 2
    buzz *= 0.5 + 0.5 * smooth_random(r, n, 0.04)
    return out + 0.12 * np.stack([buzz, np.roll(buzz, 911)])


def _shot_pool(r, keys=("FireRifle", "FireLMG", "FireSMG"), each=2):
    pool = []
    for key in keys:
        fn = weapons.AIRSOFT[key][0]  # the distant field bursts stay airsoft
        for v in range(each):
            pool.append(fn(np.random.default_rng(r.integers(1 << 30)), v))
    return pool


def distant_fire(r, n, count=8, cutoff=1700.0, room="field_far", wet=0.7, pistols=False):
    pool = _shot_pool(r)
    pis = _shot_pool(r, ("FirePistol",), 2) if pistols else []
    m = Mix(L, stereo=True, circular=True)
    for e in range(count):
        at = (e + r.uniform(0.1, 0.9)) * L / count
        p = r.uniform(-0.9, 0.9)
        g = r.uniform(0.3, 0.8)
        kind = r.random()
        if pistols and kind < 0.35:
            for i in range(int(r.integers(1, 4))):
                m.add(pis[int(r.integers(len(pis)))], at + i * r.uniform(0.25, 0.6), g * 0.8, pan_pos=p)
        elif kind < 0.7:
            rps = r.uniform(13, 19)
            for i in range(int(r.integers(3, 11))):
                m.add(pool[int(r.integers(len(pool)))], at + i / rps, g * r.uniform(0.85, 1.0), pan_pos=p)
        else:
            for i in range(int(r.integers(2, 5))):
                m.add(pool[int(r.integers(len(pool)))], at + i * r.uniform(0.3, 0.9), g, pan_pos=p)
        if r.random() < 0.35:
            ding = foley.steel_ding(np.random.default_rng(r.integers(1 << 30)), int(r.integers(3)))
            m.add(ding, at + r.uniform(0.2, 0.7), g * 0.35, pan_pos=p + r.uniform(-0.2, 0.2))
    bus = lp(hp(m.out(), 150, circular=True), cutoff, order=4, circular=True)
    return verb(bus, r, room, wet)


def field(r, v):
    n = ns(L)
    mix = (lvl(wind(r, n), -27.0) + lvl(birds(r, n), -35.0) + lvl(insects(r, n), -42.0)
           + lvl(distant_fire(r, n), -35.0))
    return mix


# ----------------------------------------------------------------- club street

def _plink(r, f0, d):
    n = ns(d)
    f = f0 * (1 + 0.18 * (1 - np.exp(-tvec(n) / 0.006)))
    return np.sin(2 * np.pi * phase(f, n)) * env(n, 0.0003, d * 0.3)


def rain(r, n):
    bed = wide_noise(r, n, -1.5, 0.5)
    bed = eq(hp(bed, 400, circular=True), [("peak", 4500, 0.7, 6.0), ("highshelf", 9500, 0.7, -5.0)], circular=True)
    out = lvl(bed, -20.0)
    drops = np.zeros((2, n))
    kernels = []
    for _ in range(12):
        kernels.append(("tick", bp(burst(r, 0.004, r.uniform(0.0002, 0.0008), attack=0.00003), r.uniform(2000, 9000), 1.0)))
    for _ in range(5):
        kernels.append(("plink", _plink(r, r.uniform(1200, 3200), r.uniform(0.02, 0.05))))
    for kind, ker in kernels:
        rate = 15.0 if kind == "tick" else 1.2
        cnt = int(rate * L)
        times = r.uniform(0, L, cnt)
        gains = np.minimum(r.lognormal(-1.0, 0.5, cnt), 0.9) * (1.0 if kind == "tick" else 0.5)  # capped: no freak drops
        pans = r.uniform(-1, 1, cnt)
        for ch, sgn in ((0, -1), (1, 1)):
            w = np.sqrt(0.5 * (1 + sgn * pans))
            drops[ch] += scatter(n, times, gains * w, ker, circular=True)
    out += lvl(drops, -24.0)
    times = np.cumsum(r.uniform(0.6, 1.4, int(L / 0.6) + 2))
    times = times[times < L]
    which = r.integers(0, 4, len(times))
    drip = np.zeros(n)
    for j in range(4):  # gutter drip: a lower plink + splash, four variants
        ker = _plink(r, r.uniform(900, 1400), 0.06) + 0.3 * hp(burst(r, 0.06, 0.004), 1500)
        sel = which == j
        drip += scatter(n, times[sel], r.uniform(0.6, 1.0, sel.sum()), ker, circular=True)
    out += lvl(verb(pan(drip, -0.6), r, "small", 0.5), -38.0)
    return out


def car_pass(r, d=8.0):
    n = ns(d)
    t = tvec(n) - d / 2
    v = r.uniform(11, 15) * (1 if r.random() < 0.5 else -1)
    d0 = r.uniform(4, 7)
    x = v * t
    dist = np.sqrt(x ** 2 + d0 ** 2)
    prox = (d0 / dist) ** 2
    band_noise = r.standard_normal(n)
    bright = bp(hp(band_noise, 900), 3500, 0.6)
    dark = lp(hp(band_noise, 300), 1500)
    spray = hp(r.standard_normal(n), 4000) * grit(r, n, 300)
    vr = v * x / dist
    f_eng = r.uniform(42, 60) / (1 + vr / 343.0)
    eng = lp(saw(f_eng, n) + 0.5 * saw(f_eng * 2, n), 380)
    sig = (bright * prox + dark * np.sqrt(prox)) * 0.8 + spray * prox ** 1.5 * 0.4 + eng * np.sqrt(prox) * 0.35
    sig *= np.clip((t + d / 2) / 0.8, 0, 1) * np.clip((d / 2 - t) / 0.8, 0, 1)
    return pan(sig, np.clip(x / dist, -1, 1) * 0.9)


def city(r, n):
    rumble = lp(wide_noise(r, n, -6.0, 0.8), 190, circular=True) * (0.7 + 0.3 * smooth_random(r, n, 0.05))
    wash = bp(wide_noise(r, n, -3.0, 0.6), 700, 0.6, circular=True) * (0.6 + 0.4 * smooth_random(r, n, 0.08))
    out = lvl(rumble, -26.0) + lvl(wash, -36.0)
    m = Mix(L, stereo=True, circular=True)
    for _ in range(2):  # far-off horns
        d = r.uniform(0.3, 0.7)
        hn = ns(d)
        f = r.uniform(380, 440)
        horn = lp(saw(f, hn) + saw(f * 1.26, hn), 1800) * env_pts(hn, [(0, 0), (0.03, 1), (d - 0.05, 0.9), (d, 0)])
        m.add(horn, r.uniform(0, L), 0.25, pan_pos=r.uniform(-0.8, 0.8))
    sd = 11.0
    sn = ns(sd)
    st = tvec(sn)
    siren = sine(950 + 330 * np.sin(2 * np.pi * st / 3.7), sn) * np.sin(np.pi * st / sd) ** 2
    m.add(lp(siren, 2200), r.uniform(0, L), 0.12, pan_pos=-0.5)
    out += lvl(verb(m.out(), r, "field_far", 0.8), -38.0)
    return out


def club_leak(r, n):
    """Club music bleeding through the walls: kick + offbeat bass, lows only."""
    beat = 60.0 / 128.0  # same tempo as ClubMusic
    nb = int(round(L / beat))
    m = Mix(L, circular=True)
    k = kick(r, 0.45, f0=120, f1=45, decay=0.3, click=0.0, drive=1.3)
    for b in range(nb):
        m.add(k, b * beat, 1.0)
    for b in range(nb):
        f = 55.0 if (b % 2 == 0) else 55.0 * (1.0 if r.random() < 0.7 else 1.189)
        nn = ns(beat * 0.4)
        note = (sine(f, nn) + 0.4 * saw(f, nn)) * env_pts(nn, [(0, 0), (0.005, 1), (beat * 0.32, 0.7), (beat * 0.4, 0)])
        m.add(note, b * beat + beat / 2, 0.55)
    x = lp(m.out(), 115, order=4, circular=True)
    x = x + 0.25 * bp(m.out(), 300, 1.0, circular=True)
    return verb(pan(x, 0.35), r, "small", 0.4, t60=0.5)


def neon(r, n):
    b = bp(saw(per(120.0), n), 2200, 1.5) * (0.8 + 0.2 * (smooth_random(r, n, 2.0) > -0.85))
    return pan(b, 0.55)


def club_street(r, v):
    n = ns(L)
    m = Mix(L, stereo=True, circular=True)
    for at in (L * 0.13 + r.uniform(0, 3), L * 0.45 + r.uniform(0, 3), L * 0.78 + r.uniform(0, 3)):
        m.add(car_pass(r), at, 1.0)
    cars = verb(m.out(), r, "outdoor", 0.25)
    return (lvl(rain(r, n), -21.0) + lvl(city(r, n), -31.0) + lvl(cars, -27.0)
            + lvl(club_leak(r, n), -27.0) + lvl(neon(r, n), -52.0))


# ----------------------------------------------------------------- club interior

VSR = 16000  # voices are synthesised at 16 kHz then upsampled x3
VOWELS = [(730, 1090, 2440), (530, 1840, 2480), (390, 1990, 2550), (570, 840, 2410),
          (440, 1020, 2240), (660, 1720, 2410), (490, 1350, 1690), (640, 1190, 2390)]


def voice(r, seconds, f0_base, female):
    """Crude conversational voice: glottal saw through moving formants, with
    syllables, phrases, pauses and fricative onsets. Silent at both ends."""
    nv = int(seconds * VSR)
    nc = int(seconds * 100)
    amp = np.zeros(nc)
    nz = np.zeros(nc)
    F = np.tile(np.array(VOWELS[0], float), (nc, 1))
    f0c = np.full(nc, f0_base)
    fs = 1.17 if female else 1.0
    t = 0.4
    while t < seconds - 0.8:
        end = min(t + r.uniform(1.0, 3.5), seconds - 0.6)
        p0 = t
        while t < end:
            syl = r.uniform(0.11, 0.26)
            a, b = int(t * 100), int((t + syl) * 100)
            if b <= a:
                break
            amp[a:b] = np.sin(np.linspace(0, np.pi, b - a)) ** 0.7 * r.uniform(0.5, 1.0)
            F[a:b] = np.array(VOWELS[int(r.integers(len(VOWELS)))]) * fs * r.uniform(0.95, 1.05)
            decl = 1.1 - 0.2 * (t - p0) / max(end - p0, 0.1)
            f0c[a:b] = f0_base * decl * r.uniform(0.94, 1.08)
            if r.random() < 0.6:
                c = min(b, a + int(r.integers(2, 5)))
                nz[a:c] = r.uniform(0.3, 0.8)
            t += syl + r.uniform(0.0, 0.06)
        t += r.uniform(0.3, 2.2)
    ker = np.ones(5) / 5
    F = np.stack([np.convolve(F[:, i], ker, mode="same") for i in range(3)], axis=1)
    f0c = np.convolve(f0c, ker, mode="same")
    amp = np.convolve(amp, np.ones(3) / 3, mode="same")
    tc = np.arange(nc) / 100.0
    tv = np.arange(nv) / VSR
    f0a = np.interp(tv, tc, f0c) * (1 + 0.01 * np.sin(2 * np.pi * 5.2 * tv))
    src = lp(saw(f0a * 3.0, nv), 700 * 3.0, order=1) * np.interp(tv, tc, amp)
    bws = np.array([90.0, 120.0, 180.0])
    gains = np.array([1.0, 0.7, 0.35])

    def mag(freqs, centers):
        fa = freqs / 3.0
        idx = np.clip(centers * 100 // VSR, 0, nc - 1).astype(int)
        Fi = F[idx]
        m = 0.03 + sum(gains[i] / np.sqrt(1 + ((fa[None, :] - Fi[:, i:i + 1]) / (bws[i] / 2)) ** 2) for i in range(3))
        return m * (fa[None, :] < 3800)

    vo = stft_apply(src, mag, frame=512, hop=128)
    fric = hp(r.standard_normal(nv), 2600 * 3.0) * np.interp(tv, tc, nz) * 0.25
    return vo + fric  # 16 kHz; the caller sums all voices and upsamples once


def babble(r, n, layers=6):
    out = np.zeros((2, n))
    for _ in range(layers):
        sn = colored(r, n, -3.0)
        sn = eq(lp(hp(sn, 150, circular=True), 1800, circular=True), [("peak", 500, 0.8, 6.0)], circular=True)
        mod = np.clip(0.55 + 0.45 * smooth_random(r, n, 4.0) + 0.2 * smooth_random(r, n, 9.0), 0, None)
        out += pan(sn * mod, r.uniform(-0.9, 0.9))
    return out


def glass(r):
    f = np.sort(r.uniform(1800, 6500, 4))
    return modes(0.6, f, r.uniform(0.12, 0.3, 4), r.uniform(0.4, 1.0, 4), rng=r) + 0.2 * hp(burst(r, 0.6, 0.0005), 3000)


def club_interior(r, v):
    n = ns(L)
    t = tvec(n)
    tone = lp(wide_noise(r, n, -3.0, 0.6), 1500, circular=True)
    hum = sum(a * np.sin(2 * np.pi * per(f) * t) for f, a in ((50, 1.0), (100, 0.5), (150, 0.25)))
    hiss = hp(wide_noise(r, n, 0.0, 0.3), 4000, circular=True)
    room = lvl(tone, -40.0) + lvl(np.stack([hum, hum]), -52.0) + lvl(hiss, -54.0)
    n16 = n * VSR // SR
    crowd16 = np.zeros((2, n16))
    for i in range(14):  # voices live at 16 kHz (dsp cutoffs assume 48 kHz, hence * 3)
        female = i % 2 == 1
        vo = voice(np.random.default_rng(r.integers(1 << 30)), L, r.uniform(165, 235) if female else r.uniform(92, 135), female)
        vo = lp(pad_len(vo, n16), r.uniform(2400, 4500) * SR / VSR)
        vo = np.roll(vo, int(r.integers(n16)))  # silent margins land at different times per voice
        crowd16 += pan(vo, r.uniform(-0.85, 0.85)) * r.uniform(0.35, 1.0)
    crowd = resample_fft(crowd16, SR // VSR, 1)
    crowd = lvl(crowd, -30.0) + lvl(babble(r, n), -31.0)
    crowd *= 0.85 + 0.15 * smooth_random(r, n, 0.03)
    m = Mix(L, stereo=True, circular=True)
    for _ in range(14):
        m.add(glass(r), r.uniform(0, L), r.uniform(0.2, 0.6), pan_pos=r.uniform(-0.9, 0.9))
    for _ in range(4):
        thunk = thump(0.15, 260, 150, 0.03) + 0.4 * glass(r)[:ns(0.15)]
        m.add(thunk, r.uniform(0, L), 0.4, pan_pos=r.uniform(-0.7, 0.7))
    bar = lvl(m.out(), -44.0)
    return room + verb(crowd + bar, r, "club", 0.45)


def pad_len(x, n):
    return x[:n] if len(x) >= n else np.pad(x, (0, n - len(x)))


# ----------------------------------------------------------------- staging

def clank(r):
    f = np.sort(r.uniform(160, 1400, 6))
    x = modes(1.2, f, r.uniform(0.15, 0.6, 6), r.uniform(0.3, 1.0, 6) * (300 / f) ** 0.3, rng=r, beat=0.6)
    return x + 0.5 * hp(burst(r, 1.2, 0.002), 1200) + 0.4 * thump(1.2, 180, 90, 0.03)


def staging(r, v):
    n = ns(L)
    t = tvec(n)
    hum = sum(a * np.sin(2 * np.pi * per(f) * t + r.uniform(0, 6)) for f, a in ((60, 1.0), (120, 0.6), (180, 0.3), (240, 0.15)))
    blade = np.sin(2 * np.pi * per(147.0) * t) * (0.8 + 0.2 * smooth_random(r, n, 0.3))
    air = eq(lp(wide_noise(r, n, -3.0, 0.7), 900, circular=True), [("peak", 210, 2.0, 5.0), ("peak", 480, 2.5, 4.0)], circular=True)
    diff = hp(wide_noise(r, n, 0.0, 0.4), 4200, circular=True)
    rattle = bp(r.standard_normal(n), 900, 4.0, circular=True) * (0.5 + 0.5 * np.sin(2 * np.pi * per(24.5) * t)) ** 4
    rattle *= np.clip(smooth_random(r, n, 0.05), 0, 1)
    hvac = (lvl(np.stack([hum, hum]), -44.0) + lvl(np.stack([blade, blade]), -47.0) + lvl(air, -31.0)
            + lvl(diff, -48.0) + lvl(pan(rattle, -0.4), -50.0))
    shots = distant_fire(r, n, count=9, cutoff=1100.0, room="range", wet=0.9, pistols=True)
    m = Mix(L, stereo=True, circular=True)
    for _ in range(6):
        m.add(clank(r), r.uniform(0, L), r.uniform(0.4, 1.0), pan_pos=r.uniform(-0.9, 0.9))
    door = lp(thump(0.5, 110, 60, 0.08) + 0.5 * burst(r, 0.5, 0.05, attack=0.001), 800)
    for _ in range(2):
        m.add(door, r.uniform(0, L), 0.6, pan_pos=r.uniform(-0.9, 0.9))
    clanks = verb(lp(m.out(), 6000, circular=True), r, "range", 0.6)
    return hvac + lvl(shots, -37.0) + lvl(clanks, -38.0)


# ----------------------------------------------------------------- parking garage (Nightjar Garage)

GARAGE_VERB = dict(t60=2.4, hf=0.35, lf=1.25)   # bare concrete decks: long, dark tail


def fluo_hum(r, n):
    """Fluorescent battens: 100 Hz ballast hum + harmonics, a gritty buzz, and one failing tube that
    stutters (starter ticks) a few times a minute."""
    t = tvec(n)
    hum = sum(a * np.sin(2 * np.pi * per(100.0 * k) * t + r.uniform(0, 6))
              for k, a in ((1, 1.0), (2, 0.5), (3, 0.28), (4, 0.12), (6, 0.06)))
    buzz = bp(saw(per(100.0), n), 3100, 2.2, circular=True) * (0.75 + 0.25 * smooth_random(r, n, 0.5))
    m = Mix(L, circular=True)
    tick = pad_len(hp(burst(r, 0.025, 0.003), 2200), ns(0.06)) + 0.4 * bp(burst(r, 0.06, 0.02), 700, 1.5)
    for _ in range(7):
        at = r.uniform(0, L)
        for i in range(int(r.integers(3, 8))):
            m.add(tick, at + i * r.uniform(0.05, 0.16), r.uniform(0.3, 0.9))
    return pan(0.7 * hum + 0.25 * buzz, -0.25) + pan(m.out(), 0.45) * 0.6


def drips(r, n, rate=0.9):
    """Water dripping off slab edges into puddles: pitched plinks, a few close, most far."""
    times = np.cumsum(r.uniform(0.25, 2.0 / rate, int(L * rate * 1.6) + 4))
    times = times[times < L]
    out = np.zeros((2, n))
    for k in range(5):
        pl = _plink(r, r.uniform(700, 1900), r.uniform(0.05, 0.12))
        ker = pl + 0.2 * pad_len(hp(burst(r, 0.05, 0.004), 1800), len(pl))
        sel = (np.arange(len(times)) % 5) == k
        p = r.uniform(-0.9, 0.9)
        out += pan(scatter(n, times[sel], r.uniform(0.25, 1.0, sel.sum()), ker, circular=True), p)
    return out


def car_alarm_chirp(r):
    """Lock 'chirp' of a car somewhere on the deck: two short bright beeps (original, synthetic)."""
    parts = []
    for i in range(2):
        d = 0.075
        nn = ns(d)
        f = sweep(2900, 3300, nn)
        s = (np.sign(np.sin(2 * np.pi * phase(f, nn))) * 0.6 + np.sin(2 * np.pi * phase(f * 2, nn)) * 0.2)
        parts.append(lp(s, 7000) * env_pts(nn, [(0, 0), (0.004, 1), (d - 0.01, 0.9), (d, 0)]))
        parts.append(np.zeros(ns(0.09)))
    return np.concatenate(parts)


def door_slam(r):
    """Car door shutting far away on concrete: low thump + latch click + panel rattle."""
    d = 0.6
    x = thump(d, 95, 55, 0.09) + 0.35 * bp(burst(r, d, 0.03), 900, 1.2) + 0.25 * pad_len(hp(burst(r, 0.03, 0.004), 3000), ns(d))
    return lp(x, 4000)


def tyre_squeal(r):
    """Distant tyre squeal on painted concrete as a car takes a ramp too fast."""
    d = r.uniform(0.9, 1.4)
    nn = ns(d)
    t = tvec(nn)
    f = 1150 + 220 * np.sin(2 * np.pi * 3.1 * t) + 120 * smooth_random(r, nn, 6.0)
    tone = np.sin(2 * np.pi * phase(f, nn)) + 0.35 * np.sin(2 * np.pi * phase(f * 2.03, nn))
    noise = bp(r.standard_normal(nn), 2400, 1.5)
    a = env_pts(nn, [(0, 0), (0.12, 0.8), (d * 0.5, 1.0), (d - 0.15, 0.6), (d, 0)])
    return lp((tone * 0.6 + noise * 0.4) * a, 5000)


def garage(r, v):
    """Inside the decks: concrete room tone, battens humming, rain washing past the open sides, drips,
    muffled traffic on the street below, and now and then a chirp, a door, a squeal - all in a long
    concrete tail."""
    n = ns(L)
    room = lp(wide_noise(r, n, -4.5, 0.75), 600, circular=True) * (0.8 + 0.2 * smooth_random(r, n, 0.07))
    air = bp(wide_noise(r, n, -3.0, 0.5), 260, 0.8, circular=True)
    wash = lp(rain(r, n), 2600, circular=True)            # rain heard through the open sides
    m = Mix(L, stereo=True, circular=True)
    for at in (L * 0.2 + r.uniform(0, 4), L * 0.62 + r.uniform(0, 4)):
        m.add(lp(car_pass(r), 1400), at, 0.8)
    events = Mix(L, stereo=True, circular=True)
    events.add(car_alarm_chirp(r), r.uniform(3, 15), 0.5, pan_pos=r.uniform(-0.8, 0.8))
    events.add(car_alarm_chirp(r), r.uniform(33, 45), 0.35, pan_pos=r.uniform(-0.8, 0.8))
    for _ in range(3):
        events.add(door_slam(r), r.uniform(0, L), r.uniform(0.4, 0.8), pan_pos=r.uniform(-0.9, 0.9))
    events.add(tyre_squeal(r), r.uniform(20, 30), 0.35, pan_pos=r.uniform(-0.7, 0.7))
    wet = verb(lvl(drips(r, n), -30.0) + lvl(events.out(), -31.0) + lvl(m.out(), -33.0), r, "hall", 0.55, **GARAGE_VERB)
    return (lvl(room, -36.0) + lvl(air, -46.0) + lvl(fluo_hum(r, n), -45.0) + lvl(wash, -32.0)
            + lvl(city(r, n), -40.0) + wet)


def rain_on_cars(r, n):
    """Rain on parked car roofs and bonnets: denser, more metallic ticks than on concrete."""
    out = np.zeros((2, n))
    for _ in range(6):
        ker = bp(burst(r, 0.006, r.uniform(0.0004, 0.0012), attack=0.00003), r.uniform(3500, 7500), 2.5)
        cnt = int(r.uniform(18, 30) * L)
        times = r.uniform(0, L, cnt)
        gains = np.minimum(r.lognormal(-1.2, 0.5, cnt), 0.8)
        out += pan(scatter(n, times, gains, ker, circular=True), r.uniform(-0.9, 0.9))
    return out


def garage_roof(r, v):
    """Open roof deck in the rain: rain on wet concrete and on car roofs, gusts over the parapet, the city
    all around (horns, a siren), cars hissing past on the street below, one far-off roll of thunder."""
    n = ns(L)
    m = Mix(L, stereo=True, circular=True)
    for at in (L * 0.1 + r.uniform(0, 3), L * 0.4 + r.uniform(0, 3), L * 0.75 + r.uniform(0, 3)):
        m.add(car_pass(r), at, 0.9)
    cars = verb(lp(m.out(), 3500, circular=True), r, "outdoor", 0.3)
    td = 7.0
    tn = ns(td)
    thunder = lp(r.standard_normal(tn), 120) * env_pts(tn, [(0, 0), (0.4, 0.6), (1.2, 1.0), (3.0, 0.5), (td, 0)])
    thunder += 0.3 * lp(r.standard_normal(tn), 400) * env_pts(tn, [(0, 0), (0.6, 0.5), (1.5, 0.2), (td, 0)])
    tm = Mix(L, stereo=True, circular=True)
    tm.add(thunder, r.uniform(25, 40), 1.0, pan_pos=r.uniform(-0.6, 0.6))
    return (lvl(rain(r, n), -19.0) + lvl(rain_on_cars(r, n), -27.0) + lvl(wind(r, n), -31.0)
            + lvl(city(r, n), -30.0) + lvl(cars, -29.0) + lvl(verb(tm.out(), r, "field_far", 0.6), -30.0))


RECIPES = {
    "AmbienceField": (field, 1, "60 s loop: gusting wind + leaves, distant birds, crickets, far-off airsoft bursts and steel pings", LOOP),
    "AmbienceClubStreet": (club_street, 1, "60 s loop: rain on pavement + drips, distant city, three wet car passes, muffled club bass (128 BPM), neon buzz", LOOP),
    "AmbienceClubInterior": (club_interior, 1, "60 s loop: room tone + HVAC, synthetic crowd murmur, bar glass clinks; no music", LOOP),
    "AmbienceStaging": (staging, 1, "60 s loop: indoor HVAC hum/airflow, faint range shots through walls, metallic clanks", LOOP),
    "AmbienceGarage": (garage, 1, "60 s loop: garage decks - concrete room tone, fluorescent hum + failing tube, rain through the open sides, drips, muffled traffic, a car chirp / door / tyre squeal in a long concrete tail", LOOP),
    "AmbienceGarageRoof": (garage_roof, 1, "60 s loop: rooftop deck in the rain - rain on concrete and car roofs, gusts, distant city and siren, wet car passes below, far thunder", LOOP),
}
