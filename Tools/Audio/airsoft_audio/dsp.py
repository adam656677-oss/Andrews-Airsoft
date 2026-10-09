"""Core DSP for the Andrew's Airsoft sound generator.

numpy only; scipy.signal is used for IIR filtering when importable, otherwise
filters run as exact frequency-domain IIR responses (FFT of the b/a
polynomials), which is vectorised and fast. Signals are float64, mono arrays
of shape (n,) or stereo arrays of shape (2, n).
"""

import math
import wave
import zlib

import numpy as np

SR = 48000

try:  # optional accelerator
    from scipy import signal as _sps  # type: ignore
except Exception:  # pragma: no cover - depends on the machine
    _sps = None

HAVE_SCIPY = _sps is not None


# ----------------------------------------------------------------- basics

def seed_for(key, var=0):
    return zlib.crc32(f"{key}#{var}".encode("utf-8"))


def rng_for(key, var=0):
    return np.random.default_rng(seed_for(key, var))


def ns(seconds):
    return max(1, int(round(seconds * SR)))


def tvec(n):
    return np.arange(n) / SR


def db(x):
    return 20.0 * math.log10(max(float(x), 1e-12))


def undb(d):
    return 10.0 ** (d / 20.0)


def fast_len(n):
    """Smallest 2^a 3^b 5^c >= n (fast FFT size)."""
    n = int(n)
    if n <= 16:
        return max(n, 1)
    best = 1 << (n - 1).bit_length()
    f5 = 1
    while f5 < best:
        f35 = f5
        while f35 < best:
            q = -(-n // f35)
            cand = f35 * (1 << (q - 1).bit_length())
            best = min(best, cand)
            f35 *= 3
        f5 *= 5
    return best


def pad_to(x, n):
    if x.shape[-1] >= n:
        return x[..., :n]
    pad = [(0, 0)] * (x.ndim - 1) + [(0, n - x.shape[-1])]
    return np.pad(x, pad)


class Mix:
    """Accumulates layers on a timeline. Mono by default; stereo=True -> (2, n)."""

    def __init__(self, seconds, stereo=False, circular=False):
        self.n = ns(seconds)
        self.circular = circular
        self.buf = np.zeros((2, self.n) if stereo else self.n)

    def add(self, sig, at=0.0, gain=1.0, pan_pos=None):
        sig = np.asarray(sig, float) * gain
        if pan_pos is not None:
            sig = pan(sig, pan_pos)
        if self.buf.ndim == 2 and sig.ndim == 1:
            sig = np.stack([sig, sig])
        if self.buf.ndim == 1 and sig.ndim == 2:
            sig = sig.mean(axis=0)
        start = int(round(at * SR))
        length = sig.shape[-1]
        if self.circular:  # wrap anything that runs past the loop end
            pos, off = start % self.n, 0
            while off < length:
                take = min(self.n - pos, length - off)
                self.buf[..., pos:pos + take] += sig[..., off:off + take]
                off += take
                pos = 0
            return self
        s0 = max(0, start)
        e0 = min(self.n, start + length)
        if e0 > s0:
            self.buf[..., s0:e0] += sig[..., s0 - start:e0 - start]
        return self

    def out(self):
        return self.buf


# ----------------------------------------------------------------- filters

def _bq(kind, f, q=0.7071, gain_db=0.0):
    f = float(np.clip(f, 5.0, SR * 0.475))
    w = 2.0 * math.pi * f / SR
    cw, sw = math.cos(w), math.sin(w)
    alpha = sw / (2.0 * q)
    A = 10.0 ** (gain_db / 40.0)
    if kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "bp":
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "notch":
        b = [1.0, -2 * cw, 1.0]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind in ("lowshelf", "highshelf"):
        sq = 2.0 * math.sqrt(A) * alpha
        if kind == "lowshelf":
            b = [A * ((A + 1) - (A - 1) * cw + sq), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sq)]
            a = [(A + 1) + (A - 1) * cw + sq, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sq]
        else:
            b = [A * ((A + 1) + (A - 1) * cw + sq), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sq)]
            a = [(A + 1) - (A - 1) * cw + sq, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sq]
    elif kind == "lp1":
        k = math.exp(-w)
        b, a = [1 - k, 0.0], [1.0, -k]
    elif kind == "hp1":
        k = math.exp(-w)
        b, a = [(1 + k) / 2, -(1 + k) / 2], [1.0, -k]
    else:
        raise ValueError(kind)
    b = np.array(b, float) / a[0]
    a = np.array(a, float) / a[0]
    return b, a


def _tail(a):
    if len(a) <= 1:
        return 0
    r = float(np.max(np.abs(np.roots(a))))
    if r <= 1e-9:
        return len(a)
    r = min(r, 0.999999)
    return int(min(math.log(1e-9) / math.log(r), 8 * SR)) + len(a)


def filt(x, sections, circular=False):
    """Apply a cascade of (b, a) sections along the last axis."""
    x = np.asarray(x, float)
    if not sections:
        return x.copy()
    if not circular and HAVE_SCIPY:
        sos = np.array([np.r_[pad_to(b, 3), pad_to(a, 3)] for b, a in sections])
        return _sps.sosfilt(sos, x, axis=-1)
    n = x.shape[-1]
    nfft = n if circular else fast_len(n + sum(_tail(a) for _, a in sections))
    H = response(sections, nfft)
    return np.fft.irfft(np.fft.rfft(x, nfft, axis=-1) * H, nfft, axis=-1)[..., :n]


def response(sections, nfft, z=None):
    """Complex response of a (b, a) cascade on the rfft grid of size nfft
    (Horner evaluation of B(z^-1)/A(z^-1): far cheaper than FFTs of the taps)."""
    if z is None:
        z = np.exp(-2j * np.pi * np.arange(nfft // 2 + 1) / nfft)
    H = np.ones(nfft // 2 + 1, complex)
    for b, a in sections:
        nb = np.full_like(z, b[-1])
        for c in b[-2::-1]:
            nb = nb * z + c
        na = np.full_like(z, a[-1])
        for c in a[-2::-1]:
            na = na * z + c
        H *= nb / na
    return H


_BUTTER_Q = {2: [0.7071], 4: [0.5412, 1.3066], 6: [0.5176, 0.7071, 1.9319], 8: [0.5098, 0.6013, 0.9000, 2.5629]}


def lp(x, f, q=None, order=2, circular=False):
    if order == 1:
        return filt(x, [_bq("lp1", f)], circular)
    qs = [q] if (q is not None and order == 2) else _BUTTER_Q[order]
    return filt(x, [_bq("lp", f, qq) for qq in qs], circular)


def hp(x, f, q=None, order=2, circular=False):
    if order == 1:
        return filt(x, [_bq("hp1", f)], circular)
    qs = [q] if (q is not None and order == 2) else _BUTTER_Q[order]
    return filt(x, [_bq("hp", f, qq) for qq in qs], circular)


def bp(x, f, q=1.0, circular=False, stages=1):
    return filt(x, [_bq("bp", f, q)] * stages, circular)


def eq(x, bands, circular=False):
    """bands: list of (kind, f, q, gain_db), kind in peak/lowshelf/highshelf/notch."""
    return filt(x, [_bq(k, f, q, g) for k, f, q, g in bands], circular)


def band(x, lo, hi, order=2, circular=False):
    return lp(hp(x, lo, order=order, circular=circular), hi, order=order, circular=circular)


def stft_apply(x, mag_fn, circular=False, frame=2048, hop=512):
    """Zero-phase time-varying spectral shaping by STFT overlap-add.

    mag_fn(freqs, centers) -> (len(centers), len(freqs)) magnitude per frame;
    centers are sample indices into x (may be <0 or >=n near the edges).
    """
    x = np.asarray(x, float)
    if x.ndim == 2:
        return np.stack([stft_apply(c, mag_fn, circular, frame, hop) for c in x])
    n = len(x)
    pad = frame
    if circular:
        reps = -(-pad // n) + 1
        big = np.tile(x, 2 * reps + 1)
        xp = big[reps * n - pad:reps * n + n + pad]
    else:
        xp = np.concatenate([np.zeros(pad), x, np.zeros(pad)])
    total = len(xp)
    nfr = -(-(total - frame) // hop) + 1
    xp = np.pad(xp, (0, (nfr - 1) * hop + frame - total))
    win = np.sqrt(0.5 - 0.5 * np.cos(2 * np.pi * np.arange(frame) / frame))
    freqs = np.fft.rfftfreq(frame, 1.0 / SR)
    nblk = frame // hop
    out = np.zeros((nfr + nblk, hop))
    wsum = np.zeros((nfr + nblk, hop))
    w2 = (win * win).reshape(nblk, hop)
    view = np.lib.stride_tricks.sliding_window_view(xp, frame)[::hop][:nfr]
    centers = np.arange(nfr) * hop + frame // 2 - pad
    for s in range(0, nfr, 256):
        e = min(nfr, s + 256)
        spec = np.fft.rfft(view[s:e] * win, axis=-1)
        y = np.fft.irfft(spec * mag_fn(freqs, centers[s:e]), frame, axis=-1) * win
        yb = y.reshape(e - s, nblk, hop)
        for j in range(nblk):
            out[s + j:e + j] += yb[:, j]
    for j in range(nblk):
        wsum[j:nfr + j] += w2[j]
    return (out / np.maximum(wsum, 1e-6)).ravel()[pad:pad + n]


def tvf(x, kind, fc, q=0.7071, order=2, circular=False, frame=2048, hop=512):
    """Time-varying zero-phase filter (analog-prototype magnitude per STFT frame).

    kind: 'lp' | 'hp' | 'bp'. fc: scalar or per-sample cutoff array.
    """
    x = np.asarray(x, float)
    n = x.shape[-1]
    fc = np.broadcast_to(np.asarray(fc, float), (n,))

    def mag(freqs, centers):
        c = np.mod(centers, n) if circular else np.clip(centers, 0, n - 1)
        r = freqs[None, :] / np.maximum(fc[c][:, None], 1.0)
        den = (1 - r * r) ** 2 + (r / q) ** 2
        if kind == "lp":
            m2 = 1.0 / den
        elif kind == "hp":
            m2 = r ** 4 / den
        else:
            m2 = (r / q) ** 2 / den
        return m2 ** (order / 4.0)

    return stft_apply(x, mag, circular, frame, hop)


# ----------------------------------------------------------------- sources

def white(rng, n, ch=None):
    return rng.standard_normal(n if ch is None else (ch, n))


def colored(rng, n, slope_db_oct=-3.0, ch=None, lo=20.0):
    """Circular coloured noise (pink=-3, brown=-6 dB/oct), unit RMS."""
    w = white(rng, n, ch)
    X = np.fft.rfft(w, axis=-1)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    g = (np.maximum(f, lo) / 1000.0) ** (slope_db_oct / 6.0206)
    g[0] = 0.0
    y = np.fft.irfft(X * g, n, axis=-1)
    return y / (np.std(y, axis=-1, keepdims=True) + 1e-12)


def smooth_random(rng, n, rate_hz, ch=None):
    """Periodic (loop-safe) smooth random control signal in about [-1, 1]."""
    X = np.zeros((ch, n // 2 + 1) if ch else n // 2 + 1, complex)
    k = max(2, int(rate_hz * n / SR))
    shape = (ch, k) if ch else (k,)
    X[..., 1:k + 1] = (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)) * np.exp(-np.arange(k) / (0.5 * k))
    y = np.fft.irfft(X, n, axis=-1)
    return y / (np.max(np.abs(y), axis=-1, keepdims=True) + 1e-12)


def phase(freq, n, phase0=0.0):
    """Instantaneous phase in cycles for a scalar or per-sample frequency."""
    f = np.broadcast_to(np.asarray(freq, float), (n,))
    return phase0 + np.concatenate([[0.0], np.cumsum(f[:-1])]) / SR


def sine(freq, n, phase0=0.0):
    return np.sin(2 * np.pi * phase(freq, n, phase0))


def _blep(ph, dt):
    y = np.zeros_like(ph)
    m1 = ph < dt
    x = ph[m1] / dt[m1]
    y[m1] = x + x - x * x - 1.0
    m2 = ph > 1.0 - dt
    x = (ph[m2] - 1.0) / dt[m2]
    y[m2] = x * x + x + x + 1.0
    return y


def saw(freq, n, phase0=0.0):
    f = np.broadcast_to(np.asarray(freq, float), (n,))
    dt = np.maximum(f / SR, 1e-9)
    ph = phase(f, n, phase0) % 1.0
    return 2.0 * ph - 1.0 - _blep(ph, dt)


def pulse(freq, n, width=0.5, phase0=0.0):
    f = np.broadcast_to(np.asarray(freq, float), (n,))
    dt = np.maximum(f / SR, 1e-9)
    p = phase(f, n, phase0)
    a = p % 1.0
    b = (p + width) % 1.0
    return (2 * a - 1 - _blep(a, dt)) - (2 * b - 1 - _blep(b, dt))


def sweep(f0, f1, n, curve="exp", tau=None):
    t = np.arange(n) / n
    if tau is not None:
        return f1 + (f0 - f1) * np.exp(-np.arange(n) / SR / tau)
    if curve == "exp":
        return f0 * (f1 / f0) ** t
    return f0 + (f1 - f0) * t


# ----------------------------------------------------------------- envelopes

def env(n, attack=0.0005, decay=0.05, hold=0.0, curve=1.0):
    """Attack (raised cosine) -> hold -> exponential decay (time constant)."""
    t = np.arange(n) / SR
    a = np.ones(n)
    if attack > 0:
        m = t < attack
        a[m] = 0.5 - 0.5 * np.cos(np.pi * t[m] / attack)
    d = np.exp(-np.maximum(t - attack - hold, 0.0) / max(decay, 1e-6))
    return a * d ** curve


def env_pts(n, pts):
    """Piecewise-linear envelope from (time_s, value) points."""
    ts, vs = zip(*pts)
    return np.interp(np.arange(n) / SR, ts, vs)


def fade(x, fin=0.0, fout=0.0):
    x = np.array(x, float, copy=True)
    n = x.shape[-1]
    if fin > 0:
        k = min(n, ns(fin))
        x[..., :k] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(k) / k)
    if fout > 0:
        k = min(n, ns(fout))
        x[..., n - k:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(1, k + 1) / k)
    return x


# ----------------------------------------------------------------- building blocks

def burst(rng, seconds, decay, lo=None, hi=None, attack=0.0002, q=None, center=None):
    """Enveloped noise burst, optionally band-limited."""
    n = ns(seconds)
    x = white(rng, n) * env(n, attack, decay)
    if center is not None:
        x = bp(x, center, q or 1.0)
    if lo:
        x = hp(x, lo)
    if hi:
        x = lp(x, hi)
    return x


def thump(seconds, f0, f1, decay, pitch_tau=None, attack=0.0004, phase0=0.25):
    n = ns(seconds)
    f = sweep(f0, f1, n, tau=pitch_tau or decay * 0.35)
    return np.sin(2 * np.pi * phase(f, n, phase0)) * env(n, attack, decay)


def modes(seconds, freqs, decays, amps=None, rng=None, attack=0.0002, detune=0.0, beat=0.0):
    """Bank of exponentially decaying sinusoids (struck-object partials)."""
    n = ns(seconds)
    t = np.arange(n) / SR
    freqs = np.asarray(freqs, float)
    decays = np.broadcast_to(np.asarray(decays, float), freqs.shape)
    amps = np.ones_like(freqs) if amps is None else np.broadcast_to(np.asarray(amps, float), freqs.shape)
    rng = rng or np.random.default_rng(0)
    if detune:
        freqs = freqs * (1 + rng.uniform(-detune, detune, freqs.shape))
    out = np.zeros(n)
    for f, d, a in zip(freqs, decays, amps):
        if f >= SR * 0.45:
            continue
        ph = rng.uniform(0, 2 * np.pi)
        s = np.sin(2 * np.pi * f * t + ph)
        if beat:
            s = 0.5 * (s + np.sin(2 * np.pi * (f + beat * rng.uniform(0.5, 1.5)) * t + ph))
        out += a * s * np.exp(-t / d)
    return out * env(n, attack, 1e9)


def resonate(x, freqs, qs, gains=None):
    """Excite a parallel bank of resonant band-passes with x."""
    gains = np.ones(len(freqs)) if gains is None else gains
    qs = np.broadcast_to(np.asarray(qs, float), (len(freqs),))
    out = np.zeros_like(x)
    for f, q, g in zip(freqs, qs, gains):
        if f < SR * 0.45:
            out += g * bp(x, f, q)
    return out


def scatter(n, times, gains, kernel, circular=False):
    """Place copies of kernel at times (s) with gains via an impulse train + FFT."""
    idx = np.round(np.asarray(times) * SR).astype(int)
    g = np.broadcast_to(np.asarray(gains, float), idx.shape)
    kernel = np.asarray(kernel, float)
    if len(idx) * len(kernel) <= 3_000_000:  # short kernels: direct overlap-add
        out = np.zeros(n)
        pos = idx[:, None] + np.arange(len(kernel))[None, :]
        vals = g[:, None] * kernel[None, :]
        if circular:
            np.add.at(out, pos % n, vals)
        else:
            m = (pos >= 0) & (pos < n)
            np.add.at(out, pos[m], vals[m])
        return out
    imp = np.zeros(n)
    if circular:
        np.add.at(imp, idx % n, g)
        return conv(imp, kernel, circular=True)
    m = (idx >= 0) & (idx < n)
    np.add.at(imp, idx[m], g[m])
    return conv(imp, kernel)[:n]


def pan(x, p):
    """Constant-power pan of a mono signal; p in [-1, 1] (scalar or per-sample)."""
    ang = (np.asarray(p, float) + 1.0) * np.pi / 4.0
    return np.stack([x * np.cos(ang), x * np.sin(ang)]) * math.sqrt(2.0)


def stereo(x):
    return np.stack([x, x]) if x.ndim == 1 else x


def mono(x):
    return x.mean(axis=0) if x.ndim == 2 else x


def resample_fft(x, factor_up=1, factor_down=1):
    n = x.shape[-1]
    X = np.fft.rfft(x, axis=-1)
    m = n * factor_up // factor_down
    Y = np.zeros(X.shape[:-1] + (m // 2 + 1,), complex)
    k = min(X.shape[-1], Y.shape[-1])
    Y[..., :k] = X[..., :k]
    if m < n and m % 2 == 0:
        Y[..., -1] = 0.0  # that bin is not the source's Nyquist: drop it, or it becomes a 24 kHz tone
    return np.fft.irfft(Y, m, axis=-1) * (m / n)


def tail_cut(x, seconds, fade_s=0.12):
    """Truncate to `seconds` with a raised-cosine fade over the last `fade_s`."""
    x = x[..., :ns(seconds)]
    return fade(x, 0.0, min(fade_s, x.shape[-1] / SR))


def saturate(x, drive=1.5, os=4, asym=0.0):
    """Oversampled tanh soft-clip (keeps aliasing out of the audio band)."""
    x = np.asarray(x, float)
    n = x.shape[-1]
    padn = fast_len(n + 2048)
    xp = pad_to(x, padn)
    up = resample_fft(xp, os, 1)
    y = np.tanh(drive * (up + asym)) - math.tanh(drive * asym)
    y /= math.tanh(drive)
    return resample_fft(y, 1, os)[..., :n]


def conv(x, h, circular=False):
    """FFT convolution along the last axis; mono x with stereo h -> stereo."""
    x = np.asarray(x, float)
    h = np.asarray(h, float)
    n, m = x.shape[-1], h.shape[-1]
    if circular:
        nfft = n
        if m > n:
            hh = np.zeros(h.shape[:-1] + (n,))
            for s in range(0, m, n):
                seg = h[..., s:s + n]
                hh[..., :seg.shape[-1]] += seg
            h = hh
        return np.fft.irfft(np.fft.rfft(x, nfft, axis=-1) * np.fft.rfft(h, nfft, axis=-1), nfft, axis=-1)
    nfft = fast_len(n + m - 1)
    return np.fft.irfft(np.fft.rfft(x, nfft, axis=-1) * np.fft.rfft(h, nfft, axis=-1), nfft, axis=-1)[..., :n + m - 1]


# ----------------------------------------------------------------- reverb

def make_ir(rng, t60=1.0, seconds=None, predelay=0.0, early=(), hf=0.45, lf=1.15,
            build=0.006, ch=1, width=1.0, lo_cut=80.0, hi_cut=12000.0):
    """Synthesised impulse response: exponentially decaying noise with
    frequency-dependent decay (lows ring longer, highs die first), a diffuse
    build-up, optional early reflections [(time_s, gain)], unit energy."""
    seconds = seconds or min(t60 * 1.1 + predelay, 6.0)
    n = ns(seconds)
    t = np.arange(n) / SR
    nz = white(rng, n, 2 if ch == 2 else None)
    X = np.fft.rfft(nz, axis=-1)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    lf_ = np.log2(np.maximum(f, 1.0))
    edges = [250.0, 1500.0, 5000.0]
    t60s = [t60 * lf, t60, t60 * (0.5 + 0.5 * hf), t60 * hf]
    out = np.zeros_like(nz)
    for i, T in enumerate(t60s):
        lo_w = np.ones_like(f) if i == 0 else np.clip((lf_ - np.log2(edges[i - 1]) + 0.5), 0, 1)
        hi_w = np.ones_like(f) if i == len(t60s) - 1 else 1 - np.clip((lf_ - np.log2(edges[i]) + 0.5), 0, 1)
        bandsig = np.fft.irfft(X * (lo_w * hi_w), n, axis=-1)
        out += bandsig * 10 ** (-3.0 * t / T)
    out *= 1 - np.exp(-t / max(build, 1e-4))
    for et, eg in early:
        k = int(et * SR)
        if k + 24 < n:
            blip = white(rng, 24, 2 if ch == 2 else None) * np.hanning(24)
            out[..., k:k + 24] += blip * eg * 6.0
    if ch == 2 and width < 1.0:
        mid = out.mean(axis=0, keepdims=True)
        out = mid + (out - mid) * width
    out = band(out, lo_cut, hi_cut)
    if predelay > 0:
        out = np.concatenate([np.zeros(out.shape[:-1] + (ns(predelay),)), out], axis=-1)[..., :n]
    return out / (np.sqrt(np.sum(out ** 2) / (2 if ch == 2 else 1)) + 1e-12)


ROOMS = {
    # name: kwargs for make_ir
    "outdoor": dict(t60=0.9, predelay=0.004, early=[(0.0035, 0.5), (0.011, 0.25), (0.093, 0.18), (0.161, 0.12), (0.247, 0.07)], hf=0.30, lf=1.0, build=0.03),
    "field_far": dict(t60=1.8, predelay=0.02, early=[(0.12, 0.3), (0.31, 0.2), (0.52, 0.12)], hf=0.25, lf=1.2, build=0.08),
    "small": dict(t60=0.28, predelay=0.001, early=[(0.0022, 0.4), (0.0051, 0.3), (0.0087, 0.2)], hf=0.5, build=0.003),
    "range": dict(t60=1.0, predelay=0.006, early=[(0.009, 0.35), (0.017, 0.3), (0.029, 0.2)], hf=0.45, build=0.01),
    "club": dict(t60=1.3, predelay=0.012, early=[(0.015, 0.3), (0.027, 0.25), (0.041, 0.2)], hf=0.4, build=0.012),
    "hall": dict(t60=2.6, predelay=0.022, early=[(0.019, 0.25), (0.033, 0.2), (0.051, 0.15)], hf=0.45, build=0.02),
    "cinema": dict(t60=3.4, predelay=0.03, early=[(0.025, 0.2), (0.047, 0.15)], hf=0.35, lf=1.3, build=0.03),
}


def space(x, rng, room="outdoor", wet=0.2, ch=None, circular=False, tail=True, **over):
    """Dry + convolution reverb. Mono in -> mono out unless ch=2."""
    params = dict(ROOMS[room])
    params.update(over)
    ch = ch or (2 if x.ndim == 2 else 1)
    ir = make_ir(rng, ch=ch, **params)
    if x.ndim == 2 and ch == 2:
        w = np.stack([conv(x[0], ir[0], circular), conv(x[1], ir[1], circular)])
    elif ch == 2:
        w = conv(x, ir, circular)
    else:
        w = conv(x, ir, circular)
    dry = stereo(x) if (ch == 2 and x.ndim == 1) else x
    if circular:
        return dry + wet * w
    if not tail:
        w = w[..., :x.shape[-1]]
    out = np.zeros(w.shape)
    out[..., :dry.shape[-1]] += dry
    return out + wet * w


# ----------------------------------------------------------------- finishing

PEAK_DB = -1.0


def true_peak(x, os=4, block=65536):
    x = np.atleast_2d(np.asarray(x, float))
    n = x.shape[-1]
    peak = float(np.max(np.abs(x))) if n else 0.0
    ov = 256
    for s in range(0, n, block):
        a, b = max(0, s - ov), min(n, s + block + ov)
        seg = x[:, a:b] * 1.0
        if seg.shape[-1] < 8:
            continue
        up = resample_fft(seg, os, 1)
        lo = (s - a) * os
        hi = up.shape[-1] - (b - min(n, s + block)) * os
        peak = max(peak, float(np.max(np.abs(up[:, lo:hi]))))
    return peak


def finish_oneshot(x, peak_db=PEAK_DB, trim_db=-62.0, fade_ms=5.0, hp_hz=20.0):
    """DC/rumble high-pass, trim true silence, 5 ms fade-out, normalise to -1 dBTP."""
    x = np.asarray(x, float)
    x = hp(x, hp_hz, order=2)
    a = np.max(np.abs(np.atleast_2d(x)), axis=0)
    pk = float(a.max()) or 1.0
    thr = pk * undb(trim_db)
    above = np.nonzero(a > thr)[0]
    start = max(0, int(above[0]) - 8) if len(above) else 0
    end = min(len(a), int(above[-1]) + ns(0.002)) if len(above) else len(a)
    x = x[..., start:end]
    if start > 0:  # ramp only the 8 sub-threshold lead-in samples, never the transient
        k = min(8, x.shape[-1])
        x[..., :k] *= np.linspace(0.0, 1.0, k + 1)[1:]
    x = fade(x, 0.0, fade_ms / 1000.0)
    tp = true_peak(x)
    return x * (undb(peak_db) / (tp or 1.0))


def finish_loop(x, peak_db=PEAK_DB, hp_hz=20.0):
    """Circular DC/rumble high-pass (keeps the seam continuous) + normalise."""
    x = hp(np.asarray(x, float), hp_hz, order=2, circular=True)
    x = x - np.mean(x, axis=-1, keepdims=True)
    tp = true_peak(x)
    return x * (undb(peak_db) / (tp or 1.0))


def fold_tail(x, n):
    """Make a seamless loop of length n from a render longer than n by
    overlap-adding everything past n back onto the start (wraps reverb/delay tails)."""
    out = np.array(x[..., :n], float, copy=True)
    s = n
    while s < x.shape[-1]:
        seg = x[..., s:s + n]
        out[..., :seg.shape[-1]] += seg
        s += n
    return out


def to_int16(x, seed=0):
    """TPDF-dithered 16-bit quantisation (deterministic)."""
    r = np.random.default_rng(seed)
    d = (r.random(x.shape) - r.random(x.shape))
    q = np.round(x * 32767.0 + d)
    return np.clip(q, -32767, 32767).astype(np.int16)


def write_wav(path, x, seed=0):
    x = np.asarray(x, float)
    ch = 1 if x.ndim == 1 else x.shape[0]
    data = to_int16(x, seed)
    if ch == 2:
        data = np.ascontiguousarray(data.T)
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.astype("<i2").tobytes())
    return data


def read_wav(path):
    with wave.open(path, "rb") as w:
        ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
        data = np.frombuffer(w.readframes(n), "<i2").astype(float) / 32767.0
    if ch == 2:
        data = data.reshape(-1, 2).T
    return data, sr
