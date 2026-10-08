"""
Synthesises the game's sound effects so they can be uploaded to Roblox.

Run:  python3 tools/audio/make_sounds.py
Needs numpy, and ffmpeg on PATH to write .ogg (falls back to .wav).
Output goes to assets/audio/. Upload those files to Roblox and paste the IDs
into src/shared/AssetIds.lua.

Airsoft guns don't bang: an AEG is a piston slap + gearbox whir + BB snap,
gas guns are a sharp pneumatic crack + slide clack, springers are a heavy
thunk with spring ring. These recipes layer filtered noise, pitched thumps and
resonant metal pings to get those characters.
"""

import os
import shutil
import subprocess
import wave

import numpy as np

SR = 44100
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "audio")
rng = np.random.default_rng(1234)


# ---------------------------------------------------------------- primitives

def t(seconds):
    return np.arange(int(SR * seconds)) / SR


def env_exp(n, decay, attack=0.0005):
    x = np.arange(n) / SR
    a = np.clip(x / max(attack, 1e-6), 0, 1)
    return a * np.exp(-x / decay)


def noise(seconds):
    return rng.uniform(-1, 1, int(SR * seconds))


def biquad(x, b, a):
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    b0, b1, b2 = b
    _, a1, a2 = a
    for i in range(len(x)):
        xi = x[i]
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, xi
        y2, y1 = y1, yi
        y[i] = yi
    return y


def bandpass(x, freq, q=0.8):
    w = 2 * np.pi * freq / SR
    alpha = np.sin(w) / (2 * q)
    a0 = 1 + alpha
    b = (alpha / a0, 0.0, -alpha / a0)
    a = (1.0, -2 * np.cos(w) / a0, (1 - alpha) / a0)
    return biquad(x, b, a)


def lowpass(x, freq, q=0.707):
    w = 2 * np.pi * freq / SR
    alpha = np.sin(w) / (2 * q)
    cw = np.cos(w)
    a0 = 1 + alpha
    b = ((1 - cw) / 2 / a0, (1 - cw) / a0, (1 - cw) / 2 / a0)
    a = (1.0, -2 * cw / a0, (1 - alpha) / a0)
    return biquad(x, b, a)


def highpass(x, freq, q=0.707):
    w = 2 * np.pi * freq / SR
    alpha = np.sin(w) / (2 * q)
    cw = np.cos(w)
    a0 = 1 + alpha
    b = ((1 + cw) / 2 / a0, -(1 + cw) / a0, (1 + cw) / 2 / a0)
    a = (1.0, -2 * cw / a0, (1 - alpha) / a0)
    return biquad(x, b, a)


def thump(seconds, f0, f1, decay):
    x = t(seconds)
    freq = f1 + (f0 - f1) * np.exp(-x / (decay * 0.5))
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * env_exp(len(x), decay)


def ping(seconds, freqs, decay):
    x = t(seconds)
    out = np.zeros_like(x)
    for i, f in enumerate(freqs):
        out += np.sin(2 * np.pi * f * x + rng.uniform(0, 6)) * np.exp(-x / (decay / (1 + i * 0.6))) / (1 + i * 0.5)
    return out


def burst(seconds, freq, q, decay, attack=0.0005):
    n = noise(seconds)
    return bandpass(n, freq, q) * env_exp(len(n), decay, attack)


def add(a, b):
    n = max(len(a), len(b))
    out = np.zeros(n)
    out[: len(a)] += a
    out[: len(b)] += b
    return out


def mix(length, *layers):
    out = np.zeros(int(SR * length))
    for offset, sig, gain in layers:
        start = int(SR * offset)
        end = min(len(out), start + len(sig))
        out[start:end] += sig[: end - start] * gain
    return out


def reverb(x, amount=0.25, room=0.045):
    # Few-tap feedback comb: enough to put the shot "in a space".
    out = x.copy()
    for delay, gain in ((room, 0.5), (room * 1.7, 0.35), (room * 2.9, 0.22), (room * 4.3, 0.14)):
        d = int(SR * delay)
        pad = np.zeros(len(x))
        pad[d:] = x[: len(x) - d]
        out += lowpass(pad, 3500) * gain * amount * 2
    return out


def normalise(x, peak=0.89):
    x = x - np.mean(x)
    m = np.max(np.abs(x)) or 1
    fade = np.ones(len(x))
    tail = min(len(x), int(SR * 0.02))
    fade[-tail:] = np.linspace(1, 0, tail)
    return x / m * peak * fade


# ---------------------------------------------------------------- recipes

def aeg(body_freq=1800, punch=1.0, length=0.32, space=0.25):
    snap = burst(0.03, 5200, 1.2, 0.004)
    piston = thump(0.12, 240, 90, 0.035) * punch
    body = burst(0.12, body_freq, 0.9, 0.028)
    whir = lowpass(np.sign(np.sin(2 * np.pi * 95 * t(0.06))) * env_exp(int(SR * 0.06), 0.02), 900)
    gear = burst(0.05, 700, 2.5, 0.012)
    dry = mix(length, (0, snap, 0.9), (0.001, piston, 1.0), (0.002, body, 0.7), (0.004, whir, 0.18), (0.006, gear, 0.25))
    return normalise(reverb(dry, space))


def gas(crack_freq=3200, slide=True, length=0.34, weight=1.0, space=0.25):
    crack = add(burst(0.05, crack_freq, 0.7, 0.008), burst(0.04, 7000, 1.5, 0.003) * 0.6)
    puff = lowpass(noise(0.15) * env_exp(int(SR * 0.15), 0.04), 2200)
    low = thump(0.15, 180 * weight, 70, 0.04 * weight)
    layers = [(0, crack, 1.0), (0.001, puff, 0.5), (0, low, 0.9 * weight)]
    if slide:
        layers.append((0.018, ping(0.08, [2300, 3900, 5600], 0.012), 0.35))
        layers.append((0.045, ping(0.06, [1900, 3300], 0.01), 0.3))
    return normalise(reverb(mix(length, *layers), space))


def spring():
    thunk = thump(0.2, 160, 55, 0.07)
    crack = burst(0.04, 3000, 0.8, 0.006)
    ring = ping(0.5, [410, 830, 1270], 0.12)
    rattle = burst(0.1, 1400, 3, 0.03)
    return normalise(reverb(mix(0.6, (0, crack, 0.7), (0, thunk, 1.0), (0.004, ring, 0.22), (0.006, rattle, 0.2)), 0.35, 0.06))


def shotgun():
    blast = add(burst(0.12, 1500, 0.5, 0.03), burst(0.06, 4500, 0.9, 0.008) * 0.7)
    low = thump(0.25, 140, 50, 0.08)
    puff = lowpass(noise(0.3) * env_exp(int(SR * 0.3), 0.08), 1800)
    return normalise(reverb(mix(0.55, (0, blast, 1.0), (0, low, 1.0), (0.003, puff, 0.6)), 0.4, 0.06))


def suppressed():
    pop = lowpass(burst(0.06, 900, 0.7, 0.012), 1800)
    thud = thump(0.1, 150, 70, 0.025)
    hiss = highpass(noise(0.08) * env_exp(int(SR * 0.08), 0.02), 4000)
    return normalise(mix(0.2, (0, pop, 1.0), (0, thud, 0.8), (0.002, hiss, 0.15)))


def click(freqs=(3200, 5400), decay=0.004, length=0.05, noise_amt=0.6):
    return normalise(mix(length, (0, ping(length, list(freqs), decay), 1.0), (0, burst(length, 4000, 1.0, decay * 0.7), noise_amt)))


def mag_out():
    release = click((2800, 4700), 0.005, 0.06)
    slide = bandpass(noise(0.12), 2400, 1.5) * np.linspace(0.3, 0, int(SR * 0.12))
    return normalise(mix(0.25, (0, release, 1.0), (0.02, slide, 0.5)))


def mag_in():
    seat = mix(0.2, (0, thump(0.08, 300, 140, 0.015), 0.8), (0, ping(0.1, [1800, 3100, 4500], 0.01), 0.7), (0, burst(0.05, 2500, 1.2, 0.006), 0.6))
    return normalise(seat)


def bolt():
    back = mix(0.3, (0, click((2500, 4100), 0.006, 0.08), 1.0), (0.02, bandpass(noise(0.1), 2000, 2) * np.linspace(0.5, 0, int(SR * 0.1)), 0.6))
    fwd = mix(0.2, (0, click((2900, 4800), 0.005, 0.07), 1.0), (0, thump(0.06, 260, 140, 0.012), 0.6))
    return normalise(mix(0.45, (0, back, 1.0), (0.2, fwd, 1.0)))


def hit_marker():
    return normalise(mix(0.12, (0, ping(0.12, [2600, 5200], 0.025), 1.0), (0, burst(0.02, 6000, 1, 0.002), 0.3)))


def tagged():
    return normalise(mix(0.4, (0, ping(0.2, [880, 1760], 0.06), 1.0), (0.09, ping(0.25, [1320, 2640], 0.07), 1.0)))


def steel_ding():
    return normalise(mix(0.9, (0, ping(0.9, [920, 2470, 3960, 5730], 0.22), 1.0), (0, burst(0.01, 5000, 1, 0.002), 0.4)))


def grenade():
    out = mix(0.7, (0, lowpass(noise(0.4) * env_exp(int(SR * 0.4), 0.09), 1600), 0.9), (0, thump(0.3, 120, 45, 0.09), 0.9))
    for _ in range(46):
        start = rng.uniform(0.0, 0.32)
        out = out + mix(0.7, (start, burst(0.02, rng.uniform(2500, 6000), 1.2, 0.003), rng.uniform(0.15, 0.4)))
    return normalise(reverb(out, 0.35, 0.05))


def impact():
    return normalise(mix(0.1, (0, burst(0.05, 2400, 1.5, 0.006), 1.0), (0, thump(0.05, 400, 200, 0.008), 0.5)))


def ui_click():
    return normalise(mix(0.05, (0, ping(0.05, [1600, 3200], 0.006), 1.0)))


SOUNDS = {
    "FireRifle": lambda: aeg(1800, 1.0),
    "FireSMG": lambda: aeg(2400, 0.7, 0.26, 0.18),
    "FireDMR": lambda: aeg(1400, 1.35, 0.4, 0.32),
    "FireLMG": lambda: aeg(1300, 1.2, 0.34, 0.28),
    "FireSniper": spring,
    "FireShotgun": shotgun,
    "FirePistol": lambda: gas(3400, True, 0.3, 0.9),
    "FireMagnum": lambda: gas(2400, True, 0.45, 1.4, 0.35),
    "FireSuppressed": suppressed,
    "DryFire": lambda: click((3600, 6100), 0.003, 0.04, 0.3),
    "Reload": mag_in,
    "MagOut": mag_out,
    "MagIn": mag_in,
    "BoltCycle": bolt,
    "HitMarker": hit_marker,
    "Tagged": tagged,
    "Ding": steel_ding,
    "UIClick": ui_click,
    "Grenade": grenade,
    "Impact": impact,
}


def write_wav(path, samples):
    data = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def main():
    os.makedirs(OUT, exist_ok=True)
    have_ffmpeg = shutil.which("ffmpeg") is not None
    for name, recipe in SOUNDS.items():
        samples = recipe()
        wav_path = os.path.join(OUT, name + ".wav")
        write_wav(wav_path, samples)
        if have_ffmpeg:
            ogg_path = os.path.join(OUT, name + ".ogg")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path, "-c:a", "libvorbis", "-q:a", "6", ogg_path], check=True)
            os.remove(wav_path)
        print("wrote", name)


if __name__ == "__main__":
    main()
