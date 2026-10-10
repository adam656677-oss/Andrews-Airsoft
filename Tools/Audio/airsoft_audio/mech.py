"""Mechanical building blocks shared by the cinematic gunfire and the handling foley:
steel-on-steel clacks, latch clicks, sliding friction, coil-spring zings and loose-part
rattles. Every helper returns a mono float array starting at its own t = 0."""

import numpy as np

from .dsp import Mix, bp, burst, env, hp, lp, modes, ns, phase, scatter, sweep, thump, tvec, tvf
from .weapons import struck

# Inharmonic ratios of a small steel part (bolt carrier / slide / latch); measured-looking
# rather than harmonic so the clack reads as metal, not as a pitched note.
STEEL = np.array([1.0, 1.52, 2.17, 2.94, 3.83, 5.08])
POLY = np.array([1.0, 1.71, 2.62, 3.9])


def friction(r, seconds, f0, f1, q=1.4, grit=0.6, attack=0.006, decay=None):
    """Sliding contact: band-passed noise sweeping f0->f1 with gritty grain AM."""
    n = ns(seconds)
    y = tvf(r.standard_normal(n), "bp", sweep(f0, f1, n), q=q)
    g = np.abs(lp(r.standard_normal(n), 380))
    g /= g.max() + 1e-12
    e = env(n, attack, decay or seconds * 0.5)
    return y * np.clip((1 - grit) + grit * g * 3, 0, 3) * e


def clack(r, f, weight=1.0, bright=1.0, mass=1.0, seconds=0.1, click=0.55):
    """Steel-on-steel impact: inharmonic part modes + strike click + a short mass thump
    (weight lengthens the ring and lowers the thump; bright lifts the upper modes)."""
    decs = np.array([0.016, 0.012, 0.0085, 0.006, 0.0042, 0.003]) * weight
    amps = np.array([0.75, 1.0, 0.75, 0.5 * bright, 0.35 * bright, 0.22 * bright])
    x = struck(r, f * STEEL, decs, amps, seconds=seconds, noise_mix=click)
    pk = np.max(np.abs(x)) + 1e-12
    th = thump(seconds, 330.0 / weight ** 0.5, 150.0 / weight ** 0.5, 0.009 * weight, attack=0.0003)
    return x / pk + 0.55 * mass * th


def poly_knock(r, f, weight=1.0, seconds=0.08):
    """Polymer / composite knock: lower, deader modes with a woody body."""
    decs = np.array([0.009, 0.006, 0.004, 0.0025]) * weight
    x = struck(r, f * POLY, decs, [1.0, 0.7, 0.4, 0.2], seconds=seconds, noise_mix=0.45, lo=900)
    return x / (np.max(np.abs(x)) + 1e-12)


def latch(r, f=5200.0, seconds=0.02):
    """Tiny, very bright detent click (mag catch, safety, sear)."""
    x = struck(r, [f, f * 1.37, f * 1.83], [0.0016, 0.0012, 0.0008], [1, 0.6, 0.35], seconds=seconds, noise_mix=0.7, lo=3000)
    return x / (np.max(np.abs(x)) + 1e-12)


def zing(r, f0, f1, seconds, decay=None, partials=(1.0, 2.31, 3.86)):
    """Coil spring: a few dispersive partials gliding f0->f1 with a noisy edge."""
    n = ns(seconds)
    t = tvec(n)
    f = sweep(f0, f1, n)
    out = np.zeros(n)
    for i, p in enumerate(partials):
        out += np.sin(2 * np.pi * phase(f * p * (1 + 0.004 * i), n, r.random())) * (0.6 ** i)
    out *= 1 + 0.25 * np.sin(2 * np.pi * 37 * t)
    nz = bp(r.standard_normal(n), f0 * 1.8, 2.5) * 0.3
    return (out + nz) * env(n, 0.0015, decay or seconds * 0.35)


def rattle(r, seconds, count, f=4200.0, spread=0.25, decay_s=None, gain_range=(0.25, 1.0)):
    """Loose small parts (belt links, sling swivels): random bright ticks that thin out."""
    n = ns(seconds)
    times = np.sort(r.uniform(0.0, seconds * 0.85, count))
    g = r.uniform(*gain_range, count) * np.exp(-times / (decay_s or seconds * 0.45))
    out = np.zeros(n)
    for j in range(3):
        fj = f * (1 + spread * (j - 1) / 2)
        k = struck(r, [fj, fj * 1.41, fj * 2.03], [0.0012, 0.0009, 0.0006], [1, 0.6, 0.35], seconds=0.012, noise_mix=0.5)
        sel = (np.arange(count) % 3) == j
        out += scatter(n, times[sel], g[sel], k / (np.max(np.abs(k)) + 1e-12))
    return out


def rack(r, t_pull, t_stop, t_release, t_home, k=1.0, weight=1.0, grit=0.6, f_stop=1900.0, f_home=1650.0,
         spring=True, seconds=None):
    """A complete pull-and-release cycle (charging handle, bolt, pump):
    unlatch tick, gritty pull with spring tension, rear stop clack, release, forward slam."""
    L = seconds or (t_home + 0.18)
    m = Mix(L)
    m.add(latch(r, 4300 * k), t_pull, 0.45)
    pull = t_stop - t_pull
    if pull > 0.01:
        m.add(friction(r, pull + 0.01, 1300 * k, 2500 * k, grit=grit, attack=0.006, decay=pull * 0.9), t_pull + 0.003, 0.4)
        if spring:
            m.add(zing(r, 820 * k, 1250 * k, pull + 0.015, decay=pull * 0.8), t_pull + 0.004, 0.12)
    m.add(clack(r, f_stop * k, weight=weight * 0.9, bright=0.9), t_stop, 0.75)
    fwd = t_home - t_release
    if fwd > 0.008:
        m.add(friction(r, fwd + 0.005, 2400 * k, 1500 * k, grit=grit * 0.8, attack=0.002, decay=fwd * 0.7), t_release, 0.3)
    m.add(clack(r, f_home * k, weight=weight * 1.15, bright=1.0, mass=1.3), t_home, 1.0)
    m.add(latch(r, 6100 * k), t_home + 0.004, 0.22)
    return m.out()


def smear(r, seconds=0.03, decay=None):
    """Short diffuse kernel (unit energy) used to blur echoes into reflections."""
    n = ns(seconds)
    k = r.standard_normal(n) * env(n, 0.001, decay or seconds * 0.3)
    return k / (np.sqrt(np.sum(k * k)) + 1e-12)


def pfft(r, seconds, decay, lo, hi, attack=0.0008):
    """Gas through baffles / out of a port: band-limited noise puff."""
    return hp(lp(burst(r, seconds, decay, attack=attack), hi, order=2), lo, order=2)


def ring(r, freqs, decays, amps, seconds=0.2):
    """Plain decaying partials (tube / receiver ring) without a strike click."""
    return modes(seconds, freqs, decays, amps, rng=r, attack=0.0003)
