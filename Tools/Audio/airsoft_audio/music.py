"""Original neo-noir score (stereo, seamless loops).

Every piece is rendered once with its reverb and delay tails and then folded, so
everything past the loop end is overlap-added back onto the start (dsp.fold_tail);
drones are synthesised circularly with loop-periodic frequencies. Loops are mastered to
an integrated-loudness target (see the "lufs" option, never above -1 dBTP) so their
volumes in the game are predictable.

All melodies, riffs, progressions and arrangements here were written for this game. The
pieces aim at a genre (brooding neo-noir, dark industrial techno, lounge noir), not at any
existing film score or track.

  MenuMusic       32 bars @ 85.33 BPM = 90 s, C# minor. Pedal drone, metal textures, the
                  main motif on a dark analog lead, half-time heavy drums from bar 9.
  ClubMusic       64 bars @ 128 BPM = 120 s, F minor. Distorted kick + rumble, sidechained
                  rolling bass, metal percussion, gritty stabs, hook from bar 17, breakdown
                  (33-40), build (41-48), drop (49-60), outro back into the intro.
  PostRoundMusic  12 bars @ 72 BPM = 40 s, G minor. Electric piano, warm pads, sub bass,
                  soft low drums, sparse vibraphone motif.
  StagingMusic    28 bars @ 89.6 BPM = 75 s, C minor. Swung lounge groove: brushes, ride,
                  rim, upright bass walking, electric piano comping, vibraphone tune.
"""

import numpy as np

from .dsp import (SR, Mix, _bq, band, bp, burst, colored, conv, env, env_pts, eq, fast_len, fold_tail, hp, lp,
                  make_ir, ns, phase, response, saturate, saw, scatter, sine, smooth_random, sweep, thump,
                  tvec, tvf, ROOMS)
from .instruments import (analog, brush, epiano, fm, hat, kick, metal, midi, rim, ride, shaker, snare, stack, tom,
                          upright, vibes)

LOOP = {"ch": 2, "loop": True}


# ----------------------------------------------------------------- helpers

def lvl(x, rms_db):
    rms = np.sqrt(np.mean(np.asarray(x) ** 2)) + 1e-12
    return x * (10 ** (rms_db / 20.0) / rms)


def wet(x, r, room, amount, **kw):
    """Dry + stereo convolution reverb (non-circular; the tail is folded later)."""
    p = dict(ROOMS[room])
    p.update(kw)
    ir = make_ir(r, ch=2, **p)
    x = np.stack([x, x]) if x.ndim == 1 else x
    w = np.stack([conv(x[i], ir[i])[:x.shape[-1]] for i in range(2)])
    return x + amount * w


def pingpong(x, delay_s, taps=4, fb=0.42, pan_amt=0.7, tone=3200.0):
    """Ping-pong delay done in one FFT: tap k is delayed k*delay_s, scaled fb**k,
    low-passed a little more each repeat and alternately panned L/R."""
    if x.ndim == 2:
        x = x.mean(axis=0)
    n = len(x)
    nfft = fast_len(n)
    k = np.arange(nfft // 2 + 1)
    z = np.exp(-2j * np.pi * k / nfft)
    X = np.fft.rfft(x, nfft)
    ang = (np.array([-pan_amt, pan_amt]) + 1.0) * np.pi / 4.0
    gl, gr = np.cos(ang) * np.sqrt(2), np.sin(ang) * np.sqrt(2)
    Ls, Rs = X.copy(), X.copy()
    H = np.ones_like(X)
    for tap in range(1, taps + 1):
        H = H * response([_bq("lp", max(600.0, tone - 400 * tap))], nfft, z)
        D = H * (fb ** tap) * np.exp(-2j * np.pi * k * round(tap * delay_s * SR) / nfft)
        side = 0 if tap % 2 else 1
        Ls += D * X * gl[side]
        Rs += D * X * gr[side]
    return np.stack([np.fft.irfft(Ls, nfft)[:n], np.fft.irfft(Rs, nfft)[:n]])


def st(x):
    return np.stack([x, x]) if x.ndim == 1 else x


def duck(n, times, depth=0.6, release=0.12, attack=0.004):
    """Sidechain gain curve: dips by `depth` at each trigger time and recovers exponentially."""
    k = np.arange(ns(release * 6))
    kern = np.minimum(1.0, k / max(1, ns(attack))) * np.exp(-k / (release * SR))
    trig = scatter(n, np.asarray(times), 1.0, kern)
    return 1.0 - depth * np.clip(trig, 0.0, 1.0)


class Grid:
    """Tempo grid: t(bar, beat) in seconds; loop_n samples; total render length with tail."""

    def __init__(self, bpm, bars, tail=6.0, swing=0.5):
        self.beat = 60.0 / bpm
        self.bar = 4 * self.beat
        self.bars = bars
        self.length = bars * self.bar
        self.loop_n = int(round(self.length * SR))
        self.total = self.length + tail
        self.swing = swing  # fraction of the beat where the off-beat 8th lands (0.5 = straight)

    def t(self, bar, beat=0.0):
        b = float(beat)
        whole = np.floor(b)
        frac = b - whole
        if self.swing != 0.5 and abs(frac - 0.5) < 1e-6:
            frac = self.swing
        return bar * self.bar + (whole + frac) * self.beat


class Cache(dict):
    def get_or(self, key, fn):
        if key not in self:
            self[key] = fn()
        return self[key]


def periodic(f, length):
    """Round a frequency so it completes a whole number of cycles per loop."""
    return max(1.0, round(f * length)) / length


def place(events, bar0, octave=0):
    """(bar, beat, midi, length_beats[, vel]) relative to bar0 -> absolute tuples."""
    out = []
    for e in events:
        bar, beat, note, ln = e[:4]
        vel = e[4] if len(e) > 4 else 0.8
        out.append((bar0 + bar, beat, note + octave, ln, vel))
    return out


# ================================================================= MENU (C# minor)

M = Grid(85.0 + 1.0 / 3.0, 32, tail=8.0)  # 32 bars x 2.8125 s = 90 s

M_CHORDS = [  # per bar of a 4-bar cycle: bass root, pad voicing
    (37, [52, 56, 61, 64]),  # C#m
    (33, [52, 57, 61, 64]),  # A
    (30, [54, 57, 61, 64]),  # F#m7
    (38, [54, 57, 62, 64]),  # Dadd9 (-> G# on beat 3)
]
M_G_SHARP = (32, [51, 56, 60, 63])  # G# major, last half of every 4th bar

# The menu motif: a fifth up, a b6 neighbour, a falling line; the answer climbs to the
# 11th and lands through the flat second (bar, beat, midi, length in beats, velocity).
THEME_A = [(0, 0.0, 61, 0.5, 0.75), (0, 0.5, 68, 1.5, 0.9), (0, 2.0, 69, 0.5, 0.7), (0, 2.5, 68, 0.5, 0.7),
           (0, 3.0, 64, 1.0, 0.8), (1, 0.0, 63, 2.0, 0.85), (1, 2.0, 64, 0.5, 0.65), (1, 2.5, 66, 0.5, 0.7),
           (1, 3.0, 61, 1.0, 0.75)]
THEME_B = [(0, 0.0, 64, 1.0, 0.8), (0, 1.0, 66, 0.5, 0.7), (0, 1.5, 68, 0.5, 0.75), (0, 2.0, 71, 2.0, 0.9),
           (1, 0.0, 69, 1.0, 0.8), (1, 1.0, 68, 0.5, 0.7), (1, 1.5, 62, 0.5, 0.75), (1, 2.0, 61, 2.0, 0.85)]
THEME_C = [(0, 0.0, 68, 1.0, 0.8), (0, 1.0, 73, 1.0, 0.9), (0, 2.0, 71, 0.5, 0.7), (0, 2.5, 69, 0.5, 0.7),
           (0, 3.0, 68, 1.0, 0.8), (1, 0.0, 66, 1.5, 0.8), (1, 1.5, 64, 0.5, 0.65), (1, 2.0, 63, 2.0, 0.85),
           (2, 0.0, 64, 0.5, 0.7), (2, 0.5, 68, 0.5, 0.75), (2, 1.0, 73, 1.5, 0.9), (2, 2.5, 74, 0.5, 0.8),
           (2, 3.0, 73, 1.0, 0.8), (3, 0.0, 71, 1.0, 0.8), (3, 1.0, 69, 1.0, 0.75), (3, 2.0, 68, 2.0, 0.85)]
BELL_LINE = [(12, 0, 76, 4), (13, 0, 73, 4), (14, 0, 69, 4), (15, 0, 68, 4),
             (20, 0, 76, 3), (20, 3, 75, 1), (21, 0, 73, 4), (22, 0, 69, 2), (22, 2, 74, 2), (23, 0, 72, 4)]


def _menu_drone(r):
    """C# pedal (circular): two detuned saws + fifth + sub through a slowly breathing
    low-pass, with a bowed-metal shimmer on top."""
    n, L = M.loop_n, M.length
    t = tvec(n)
    d = np.zeros((2, n))
    for c in range(2):
        for f, a in ((69.3, 1.0), (69.3 * 2 ** (7 / 1200), 0.8), (103.83, 0.45), (138.6, 0.2)):
            d[c] += a * saw(periodic(f * (1.0 if c == 0 else 1.0007), L), n, r.random())
    breathe = 0.5 + 0.5 * np.sin(2 * np.pi * 2 * t / L) * (0.75 + 0.25 * np.sin(2 * np.pi * 3 * t / L + 1.0))
    d = np.stack([tvf(d[c], "lp", 140 + 330 * breathe, q=1.2, order=4, circular=True) for c in range(2)])
    sub = np.sin(2 * np.pi * periodic(34.65, L) * t)
    # bowed metal: noise through very narrow inharmonic resonances, slowly swelling
    nz = colored(r, n, -3.0, ch=2)
    partials = [277.2 * k for k in (1.0, 1.593, 2.135, 2.653, 3.155)]
    bowed = sum(g * bp(nz, f, 90.0, circular=True) for f, g in zip(partials, (1.0, 0.8, 0.6, 0.45, 0.3)))
    sw = np.clip(0.5 + 0.5 * smooth_random(r, n, 0.05, ch=2), 0, 1) ** 2
    room = lp(colored(r, n, -6.0, ch=2), 180, circular=True)
    return lvl(d, -25.0) + lvl(st(sub), -31.0) + lvl(bowed * sw, -39.0) + lvl(room, -44.0)


def menu_music(r, v):
    G = M
    n = ns(G.total)
    cache = Cache()
    lead, bell, pad, bass = Mix(G.total), Mix(G.total, stereo=True), Mix(G.total, stereo=True), Mix(G.total)
    kick_b, snare_b, tom_b, hat_b, metal_b = Mix(G.total), Mix(G.total), Mix(G.total, stereo=True), Mix(G.total), Mix(G.total, stereo=True)

    # --- lead motif: dark analog voice (+ a sine an octave below for weight)
    notes = (place(THEME_A, 4) + place(THEME_B, 6) + place(THEME_A, 8) + place(THEME_B, 10)
             + place(THEME_A, 12) + place(THEME_B, 14) + place(THEME_C, 16) + place(THEME_A, 20) + place(THEME_B, 22)
             + [(26, 0.0, 61, 0.5, 0.6), (26, 0.5, 68, 3.5, 0.7), (28, 0.0, 64, 2.0, 0.5), (28, 2.0, 63, 2.0, 0.45)])
    for bar, beat, m, ln, vel in notes:
        dur = ln * G.beat
        key = (m, round(ln, 3))

        def make(m=m, dur=dur):
            f = float(midi(m))
            x = analog(r, f, dur + 0.35, cutoff=f * 1.6, env_amt=1.6, f_decay=0.12, reso=1.1, detune_c=6, sub=0.0,
                       gate=dur, attack=0.03, release=0.3, drive=1.3)
            return x + 0.35 * np.sin(2 * np.pi * phase(f / 2, len(x))) * env(len(x), 0.04, dur * 0.8)
        soft = 0.55 if bar < 8 else 1.0  # the first statement is held back
        lead.add(cache.get_or(("lead",) + key, make), G.t(bar, beat), vel * soft)
    # --- FM bell counter-line
    for bar, beat, m, ln in BELL_LINE:
        f = float(midi(m))
        x = fm(r, f, ln * G.beat + 1.5, ratio=3.5, index=1.8, index_decay=0.06, index_floor=0.2, decay=1.4)
        bell.add(x, G.t(bar, beat), 0.8, pan_pos=0.35 if bar % 2 else -0.35)
    # --- pads and bass
    for bar in range(G.bars):
        root, voicing = M_CHORDS[bar % 4]
        split = bar % 4 == 3
        main = 8 <= bar < 24
        if 8 <= bar < 28:
            dur = (2 if split else 4) * G.beat
            pv = cache.get_or(("pad", tuple(voicing), split),
                              lambda v_=voicing, d_=dur: stack(r, midi(v_), d_ + 0.9, cutoff=850, attack=0.4, release=0.8,
                                                               gate=d_, voices=3, drive=1.1))
            pad.add(pv, G.t(bar), 0.7 if main else 0.45)
            if split:
                gv = cache.get_or(("pad", "g#"), lambda: stack(r, midi(M_G_SHARP[1]), 2 * G.beat + 0.9, cutoff=850,
                                                               attack=0.2, release=0.8, gate=2 * G.beat, voices=3, drive=1.1))
                pad.add(gv, G.t(bar, 2), 0.7 if main else 0.45)
        if main:  # 8th-note bass pulse following the roots
            for step in range(8):
                rt = M_G_SHARP[0] if (split and step >= 4) else root
                m = rt + (12 if step in (3, 7) and bar % 2 else 0)
                bn = cache.get_or(("bass", m), lambda m_=m: analog(r, float(midi(m_)), 0.36, cutoff=170, env_amt=2.2,
                                                                   f_decay=0.05, reso=1.2, sub=0.7, attack=0.003,
                                                                   release=0.08, drive=1.6))
                bass.add(bn, G.t(bar, step * 0.5), 1.0 if step % 2 == 0 else 0.7)
        elif 24 <= bar < 29:  # outro: long held roots, fading
            bn = cache.get_or(("bassl", root), lambda rt_=root: analog(r, float(midi(rt_)), 3.2, cutoff=140, env_amt=0.8,
                                                                     f_decay=0.4, reso=1.0, sub=0.8, gate=2.6,
                                                                     attack=0.05, release=0.5, drive=1.3))
            bass.add(bn, G.t(bar), 0.9 * (1 - (bar - 24) / 6))
    # --- drums: slow and heavy, half-time feel
    k = kick(r, 0.9, f0=115, f1=41, decay=0.42, click=0.25, drive=1.9)
    sn = snare(r, 0.9, tone=160, decay=0.3, snap=0.8)
    lo_tom, hi_tom = tom(r, 62, 1.0, decay=0.35), tom(r, 84, 0.9, decay=0.3)
    ch = hat(r, 0.07, 0.02, tone=0.9)
    for bar in range(G.bars):
        if 8 <= bar < 24:
            kick_b.add(k, G.t(bar), 1.0)
            if bar % 2 == 1:
                kick_b.add(k, G.t(bar, 2.5), 0.55)
            if bar % 4 == 3:
                kick_b.add(k, G.t(bar, 3.75), 0.4)
            snare_b.add(sn, G.t(bar, 2), 1.0 if bar >= 12 else 0.85)
            if bar >= 12:
                for e in range(8):
                    hat_b.add(ch, G.t(bar, e * 0.5), (0.35, 0.8)[e % 2] * (0.9 + 0.2 * r.random()))
            if bar in (15, 23):  # tom fills into the next phrase
                for i, (bt, tt, g) in enumerate(((3.0, hi_tom, 0.7), (3.25, hi_tom, 0.6), (3.5, lo_tom, 0.8),
                                                 (3.75, lo_tom, 0.9))):
                    tom_b.add(tt, G.t(bar, bt), g, pan_pos=0.3 - 0.2 * i)
        elif bar in (6, 7) or (24 <= bar < 30 and bar % 2 == 0):  # distant toms outside the drum section
            tom_b.add(lo_tom, G.t(bar), 0.55, pan_pos=-0.2)
    # --- metal: struck plates and a slow scrape, far back in the room
    for bar, beat, f, g in ((0, 0, 92.5, 0.9), (3, 2, 138.6, 0.6), (5, 1.5, 110.0, 0.7), (16, 0, 92.5, 0.6),
                            (24, 0, 92.5, 0.9), (27, 2, 123.5, 0.6), (30, 1, 103.8, 0.7)):
        metal_b.add(metal(r, f, 4.0, decay=1.4, bright=0.45, click=0.1), G.t(bar, beat), g, pan_pos=r.uniform(-0.6, 0.6))
    sn_n = ns(3.0)
    for bar in (2, 18, 28):
        scrape = tvf(r.standard_normal(sn_n), "bp", sweep(2400, 900, sn_n), q=22) * env_pts(sn_n, [(0, 0), (1.2, 1), (3.0, 0)])
        metal_b.add(scrape, G.t(bar, 1), 0.5, pan_pos=0.5)

    lead_bus = wet(pingpong(lp(lead.out(), 5000), 0.75 * G.beat, taps=4, fb=0.38, tone=2600), r, "cinema", 0.45)
    bell_bus = wet(bell.out(), r, "cinema", 0.7)
    pad_bus = wet(pad.out(), r, "hall", 0.4)
    drum_bus = (lvl(st(kick_b.out()), -25.0) + lvl(wet(snare_b.out(), r, "hall", 0.55, t60=2.2), -27.5)
                + lvl(wet(tom_b.out(), r, "hall", 0.5), -30.0) + lvl(wet(hat_b.out(), r, "small", 0.2), -38.0))
    tails = (lvl(lead_bus, -23.0) + lvl(bell_bus, -34.0) + lvl(pad_bus, -31.0) + lvl(st(bass.out()), -25.0)
             + drum_bus + lvl(wet(metal_b.out(), r, "cinema", 0.8), -33.0))
    return _menu_drone(r) + fold_tail(tails, G.loop_n)


# ================================================================= CLUB (F minor)

C = Grid(128.0, 64, tail=4.0)  # 64 bars x 1.875 s = 120 s
S16 = C.beat / 4
C_ROOTS = [29, 29, 29, 29, 25, 25, 27, 24]  # F F F F Db Db Eb C (8-bar cycle)
C_STABS = {29: [53, 56, 60, 67], 25: [49, 53, 56, 60], 27: [51, 55, 58, 65], 24: [48, 52, 55, 58]}
# The hook (2 bars on a 16th grid): a tritone kink (B natural) inside a minor riff.
# (step, midi, length in 16ths, velocity)
HOOK = [(0, 65, 2, 1.0), (3, 65, 1, 0.7), (4, 72, 2, 0.95), (7, 71, 1, 0.8), (8, 68, 3, 0.95), (11, 67, 1, 0.7),
        (12, 68, 2, 0.85), (14, 72, 2, 0.9), (16, 73, 3, 1.0), (19, 72, 1, 0.75), (20, 68, 2, 0.9), (22, 65, 2, 0.8),
        (24, 63, 3, 0.9), (27, 65, 1, 0.7), (30, 60, 2, 0.85)]
HOOK_ALT = HOOK[:12] + [(24, 75, 2, 0.95), (26, 73, 2, 0.85), (28, 72, 2, 0.9), (30, 68, 2, 0.8)]


def _club_parts(bar):
    s = dict(kick=True, kick_lp=False, bass=True, bass_open=True, clap=True, ch=True, oh=False, metal=False,
             stab=False, hook=False, hook_alt=False, ride=False, pad=False, roll=0, riser=False, perc2=False)
    if bar < 8:
        s.update(clap=False, bass_open=False, metal=bar >= 4)
    if 8 <= bar < 32 or 48 <= bar < 60:
        s.update(oh=True, metal=True, stab=True)
    if 16 <= bar < 32 or 48 <= bar < 60:
        s.update(hook=True, perc2=True)
    if 48 <= bar < 60:
        s.update(ride=True, hook_alt=bar % 4 >= 2)
    if 32 <= bar < 40:  # breakdown
        s.update(kick=False, bass=False, clap=False, ch=bar % 2 == 1, metal=bar >= 36, pad=True, stab=bar >= 34,
                 hook=bar >= 36)
    if 40 <= bar < 48:  # build
        s.update(kick=bar >= 44, kick_lp=True, bass=False, clap=False, ch=True, pad=True, stab=True, metal=True,
                 roll=1 if bar < 44 else (2 if bar < 46 else 4), riser=True)
    if bar >= 60:  # outro: strip back to the intro's groove
        s.update(oh=bar < 62, metal=True, clap=bar < 62)
    return s


def club_music(r, v):
    G = C
    n = ns(G.total)
    t = tvec(n)
    bars_f = t / G.bar
    cache = Cache()
    kick_b, kick_lp_b, clap_b, hats_b, metal_b = Mix(G.total), Mix(G.total), Mix(G.total), Mix(G.total, stereo=True), Mix(G.total, stereo=True)
    bass_b, stab_b, hook_b, pad_b, roll_b, ride_b = Mix(G.total), Mix(G.total), Mix(G.total), Mix(G.total, stereo=True), Mix(G.total), Mix(G.total)

    k = kick(r, 0.5, f0=175, f1=44, decay=0.26, click=0.5, drive=3.2)
    k = lp(k, 7000)
    cl = snare(r, 0.4, tone=230, decay=0.13, snap=1.2, wires=1.3) + 0.6 * _clap(r, 0.4)
    chh = hat(r, 0.06, 0.016, tone=1.15)
    ohh = hat(r, 0.2, 0.07, tone=1.05)
    rd = ride(r, 0.9, decay=0.3, bell=0.15)
    pipes = [metal(r, f, 0.35, decay=0.07, bright=0.9, click=0.4) for f in (412.0, 587.0, 733.0, 921.0)]
    clank = metal(r, 260.0, 0.5, decay=0.12, bright=0.7, click=0.6)
    sn_roll = snare(r, 0.25, tone=240, decay=0.07, snap=1.0)
    kick_times = []
    for bar in range(G.bars):
        s = _club_parts(bar)
        root = C_ROOTS[bar % 8]
        for beat in range(4):
            tb = G.t(bar, beat)
            if s["kick"]:
                (kick_lp_b if s["kick_lp"] else kick_b).add(k, tb, 1.0)
                if not s["kick_lp"]:
                    kick_times.append(tb)
            if s["clap"] and beat in (1, 3):
                clap_b.add(cl, tb, 1.0)
            if s["ch"]:
                for j in range(4):
                    hats_b.add(chh, tb + j * S16, (0.45, 0.25, 0.8, 0.3)[j] * (0.9 + 0.2 * r.random()), pan_pos=0.15)
            if s["oh"]:
                hats_b.add(ohh, tb + 2 * S16, 0.65, pan_pos=-0.1)
            if s["ride"]:
                ride_b.add(rd, tb + 2 * S16, 0.7)
                ride_b.add(rd, tb, 0.4)
        if s["metal"]:
            pat = (3, 6, 10, 13) if not s["perc2"] else (3, 6, 7, 10, 13, 15)
            for i, step in enumerate(pat):
                p = pipes[(i + bar) % len(pipes)]
                metal_b.add(p, G.t(bar) + step * S16, (0.5 + 0.4 * ((step * 7 + bar) % 3 == 0)) * 0.8,
                            pan_pos=(-0.6, 0.5, -0.2, 0.7, 0.2, -0.5)[i % 6])
            if bar % 4 == 3:
                metal_b.add(clank, G.t(bar, 3.5), 0.7, pan_pos=0.35)
        if s["bass"]:  # rolling 16ths between the kicks
            for beat in range(4):
                for j, vel in ((1, 0.55), (2, 1.0), (3, 0.7)):
                    m = root + (12 if (j == 3 and beat == 3 and bar % 2) else 0)
                    bn = cache.get_or(("bass", m), lambda m_=m: analog(r, float(midi(m_)), S16 * 0.95, cutoff=240,
                                                                       env_amt=3.0, f_decay=0.03, reso=1.4, sub=0.7,
                                                                       attack=0.002, release=0.02, drive=2.2))
                    bass_b.add(bn, G.t(bar, beat) + j * S16, vel)
        if s["stab"]:
            chord = C_STABS[root]
            steps = (3, 10) if bar % 2 == 0 else (3, 10, 13)
            for step in steps:
                sb = cache.get_or(("stab", root), lambda c_=chord: _stab(r, c_))
                stab_b.add(sb, G.t(bar) + step * S16, 1.0 if step != 13 else 0.7)
        if s["hook"]:
            if bar % 2 == 0:
                phrase = HOOK_ALT if s["hook_alt"] else HOOK
                for step, m, ln, vel in phrase:
                    for octv in ((0, 12) if 48 <= bar < 60 else (0,)):
                        hn = cache.get_or(("hook", m + octv, ln), lambda m_=m + octv, l_=ln: _lead(r, float(midi(m_)), l_ * S16))
                        hook_b.add(hn, G.t(bar) + step * S16, vel * (0.4 if octv else 1.0))
        if s["pad"] and bar % 2 == 0:
            pv = cache.get_or(("pad", root), lambda c_=C_STABS[root]: stack(r, midi(c_), 2 * G.bar + 1.0, cutoff=1400,
                                                                            attack=0.6, release=1.0, gate=2 * G.bar,
                                                                            voices=4, drive=1.2))
            pad_b.add(pv, G.t(bar), 1.0)
        if s["roll"]:
            per_beat = s["roll"]
            for beat in range(4):
                for j in range(per_beat):
                    tt = G.t(bar, beat + j / per_beat)
                    prog = (bar - 40 + (beat + j / per_beat) / 4) / 8.0
                    roll_b.add(sn_roll, tt, 0.25 + 0.75 * prog ** 1.5)

    # sidechain from the four-on-the-floor kick
    dk = duck(n, kick_times, depth=0.7, release=0.11)
    # rumble: the kick through a dark club reverb, low-passed and ducked (techno 'rumble')
    rumble = lp(wet(kick_b.out(), r, "club", 1.0, t60=1.5)[0] - kick_b.out(), 160, order=4) * dk
    # filters that move with the arrangement
    bass_cut = np.interp(bars_f, [0, 7.9, 8, 32, 48, 64, 70], [140, 140, 600, 600, 600, 600, 140])
    bass_sig = tvf(bass_b.out(), "lp", bass_cut, q=0.9, order=2) * (1 - 0.75 * (1 - dk))
    stab_cut = np.interp(bars_f, [8, 16, 32, 34, 40, 48, 60, 70], [700, 1800, 2400, 900, 900, 2600, 2400, 900])
    stab_sig = tvf(stab_b.out(), "bp", stab_cut, q=1.3) * (1 - 0.4 * (1 - dk))
    stab_bus = wet(pingpong(stab_sig, 0.75 * G.beat, taps=3, fb=0.35), r, "club", 0.35, t60=1.6)
    hook_cut = np.interp(bars_f, [16, 18, 32, 36, 40, 48, 70], [900, 4200, 4200, 1100, 1100, 5000, 5000])
    hook_sig = tvf(hook_b.out(), "lp", hook_cut, q=1.1)
    hook_bus = wet(pingpong(hook_sig, 0.75 * G.beat, taps=4, fb=0.33), r, "club", 0.3)
    pad_cut = np.interp(bars_f, [32, 36, 40, 48, 70], [500, 1300, 700, 3500, 3500])
    pad_sig = np.stack([tvf(pad_b.out()[c], "lp", pad_cut, q=1.0) for c in range(2)])
    noise = np.zeros(n)
    a, b = ns(G.t(40)), ns(G.t(48))
    nz = r.standard_normal(b - a)
    nz = tvf(nz, "bp", sweep(400, 9000, b - a), q=1.2) * np.linspace(0, 1, b - a) ** 2
    noise[a:b] = nz
    mix = (lvl(st(kick_b.out()), -16.0) + lvl(st(lp(kick_lp_b.out(), 320)), -21.0) + lvl(st(rumble), -24.0)
           + lvl(st(bass_sig), -19.0) + lvl(wet(clap_b.out(), r, "club", 0.3, t60=0.9), -24.5)
           + lvl(hats_b.out(), -30.0) + lvl(wet(metal_b.out(), r, "club", 0.35), -29.0)
           + lvl(stab_bus, -26.0) + lvl(hook_bus, -24.5) + lvl(pad_sig, -27.0)
           + lvl(wet(roll_b.out(), r, "club", 0.4), -27.0) + lvl(wet(st(noise), r, "hall", 0.4), -30.0)
           + lvl(st(ride_b.out()), -35.0))
    mix = eq(mix, [("peak", 2800, 0.8, -2.5), ("highshelf", 10000, 0.7, -1.5)])  # leave room for gunfire
    return fold_tail(mix, G.loop_n)


def _clap(r, seconds=0.3):
    out = np.zeros(ns(seconds))
    t0 = 0.0
    for i in range(4):
        dec = 0.003 if i < 3 else 0.05
        b = bp(burst(r, seconds - t0, dec, attack=0.0003), 1250, 1.0)
        k0 = ns(t0)
        out[k0:] += b[:len(out) - k0]
        t0 += 0.008 + 0.003 * r.random()
    return out


def _stab(r, chord):
    """Gritty stab: detuned saw chord, hard-driven, short envelope."""
    x = stack(r, midi(chord), 0.32, cutoff=3500, attack=0.002, release=0.1, gate=0.12, voices=3, drive=3.0)
    x = x.mean(axis=0)
    return saturate(hp(x, 180) * env(len(x), 0.002, 0.09), 2.5)


def _lead(r, f, dur):
    """Hook voice: saw pair + square sub-octave, plucky filter, driven."""
    return analog(r, f, dur + 0.12, cutoff=f * 1.4, env_amt=4.0, f_decay=0.07, reso=1.5, detune_c=9, sub=0.0,
                  square=0.35, gate=dur * 0.9, attack=0.003, release=0.08, drive=2.4)


# ================================================================= POST-ROUND (G minor)

P = Grid(72.0, 12, tail=6.0)  # 12 bars x 3.333 s = 40 s
P_CHORDS = [  # root, epiano voicing
    (31, [58, 62, 65, 69]),  # Gm9
    (39, [55, 58, 62, 65]),  # Ebmaj9
    (36, [58, 62, 63, 67]),  # Cm9
    (38, [60, 62, 67, 69]),  # D7sus4 (-> D7b9 on beat 3)
]
P_D7B9 = [60, 63, 66, 69]
P_MOTIF = [(0, 0.0, 74, 1.5, 0.8), (0, 1.5, 72, 0.5, 0.6), (0, 2.0, 70, 1.0, 0.7), (0, 3.0, 69, 1.0, 0.65),
           (1, 0.0, 67, 2.0, 0.75), (1, 2.5, 65, 0.5, 0.55), (1, 3.0, 62, 1.0, 0.6)]
P_MOTIF2 = [(0, 0.0, 75, 1.0, 0.75), (0, 1.0, 74, 1.0, 0.7), (0, 2.0, 70, 2.0, 0.75),
            (1, 0.0, 72, 1.5, 0.7), (1, 1.5, 69, 0.5, 0.6), (1, 2.0, 67, 2.0, 0.7)]


def postround_music(r, v):
    G = P
    cache = Cache()
    ep, pad, bass, mel = Mix(G.total, stereo=True), Mix(G.total, stereo=True), Mix(G.total), Mix(G.total, stereo=True)
    kick_b, rim_b, hat_b, tom_b = Mix(G.total), Mix(G.total), Mix(G.total, stereo=True), Mix(G.total)
    for bar in range(G.bars):
        root, voicing = P_CHORDS[bar % 4]
        last = bar % 4 == 3
        # electric piano: chord on 1, a softer re-strike on the 'and' of 2
        for beat, vel, vc in ((0.0, 0.7, voicing), (1.5, 0.45, voicing)) + (((2.0, 0.6, P_D7B9),) if last else ()):
            for i, m in enumerate(vc):
                x = cache.get_or(("ep", m, vel), lambda m_=m, v_=vel: epiano(r, float(midi(m_)), 3.2, vel=v_, trem=0.18))
                ep.add(x, G.t(bar, beat) + 0.012 * i, vel, pan_pos=-0.3 + 0.2 * i)
        pv = cache.get_or(("pad", bar % 4), lambda v_=voicing: stack(r, midi([x_ - 12 for x_ in v_]), G.bar + 1.2,
                                                                     cutoff=950, attack=0.8, release=1.0, gate=G.bar,
                                                                     voices=3, drive=1.05))
        pad.add(pv, G.t(bar), 1.0)
        for beat, ln in ((0, 2.5), (2.5, 1.5)):
            m = root
            bn = cache.get_or(("bass", m, ln), lambda m_=m, l_=ln: analog(r, float(midi(m_)), l_ * G.beat + 0.2,
                                                                          cutoff=180, env_amt=1.0, f_decay=0.1, reso=0.9,
                                                                          sub=0.9, gate=l_ * G.beat * 0.9, attack=0.01,
                                                                          release=0.15, drive=1.2))
            bass.add(bn, G.t(bar, beat), 1.0 if beat == 0 else 0.7)
    k = kick(r, 0.6, f0=95, f1=44, decay=0.3, click=0.12, drive=1.4)
    rm = rim(r, 0.1, 1500)
    sh = shaker(r, 0.08, 0.02)
    lt = tom(r, 70, 0.9, decay=0.3)
    for bar in range(G.bars):
        kick_b.add(k, G.t(bar), 1.0)
        kick_b.add(k, G.t(bar, 1.5), 0.6)
        if bar % 2:
            kick_b.add(k, G.t(bar, 3.5), 0.45)
        rim_b.add(rm, G.t(bar, 2), 0.9)
        for e in range(8):
            hat_b.add(sh, G.t(bar, e * 0.5), (0.5, 0.9)[e % 2] * (0.85 + 0.3 * r.random()), pan_pos=0.25)
        if bar % 4 == 3:
            tom_b.add(lt, G.t(bar, 3.25), 0.6)
            tom_b.add(lt, G.t(bar, 3.5), 0.75)
    for bar0, phrase in ((4, P_MOTIF), (8, P_MOTIF2), (10, P_MOTIF)):
        for bar, beat, m, ln, vel in place(phrase, bar0):
            x = cache.get_or(("vib", m), lambda m_=m: vibes(r, float(midi(m_)), 3.0, vel=0.8, motor=0.3, motor_hz=4.6))
            mel.add(x, G.t(bar, beat), vel, pan_pos=0.25)
    mel_bus = wet(pingpong(mel.out(), 0.75 * G.beat, taps=3, fb=0.3, tone=2400), r, "hall", 0.45)
    mix = (lvl(wet(ep.out(), r, "hall", 0.3), -25.0) + lvl(wet(pad.out(), r, "hall", 0.35), -30.0)
           + lvl(st(bass.out()), -24.0) + lvl(mel_bus, -27.0) + lvl(st(kick_b.out()), -25.0)
           + lvl(wet(rim_b.out(), r, "small", 0.3), -31.0) + lvl(hat_b.out(), -36.0)
           + lvl(wet(tom_b.out(), r, "hall", 0.4), -32.0))
    mix = lp(mix, 11000, order=2)
    return fold_tail(mix, G.loop_n)


# ================================================================= STAGING (C minor lounge)

S = Grid(89.6, 28, tail=6.0, swing=0.62)  # 28 bars x 2.679 s = 75 s, swung 8ths
S_CHORDS = [  # walking bass (4 quarters), epiano voicing
    ([36, 31, 34, 33], [51, 55, 58, 62]),  # Cm9
    ([32, 39, 36, 30], [51, 55, 60, 62]),  # Abmaj7(#11)
    ([29, 32, 36, 32], [51, 56, 60, 67]),  # Fm9
    ([31, 35, 38, 37], [53, 59, 63, 68]),  # G7(#5 b9)
]
# The lobby tune (vibraphone), 4 bars, and an answer that rises at the end.
S_TUNE = [(0, 0.0, 67, 1.5, 0.8), (0, 1.5, 70, 0.5, 0.65), (0, 2.0, 74, 1.0, 0.8), (0, 3.0, 72, 1.0, 0.7),
          (1, 0.0, 70, 1.0, 0.75), (1, 1.0, 67, 0.5, 0.6), (1, 1.5, 65, 0.5, 0.6), (1, 2.0, 63, 2.0, 0.75),
          (2, 0.0, 68, 1.0, 0.75), (2, 1.0, 72, 0.5, 0.65), (2, 1.5, 75, 0.5, 0.7), (2, 2.0, 74, 1.0, 0.75),
          (2, 3.0, 72, 1.0, 0.65), (3, 0.0, 71, 1.5, 0.8), (3, 1.5, 68, 0.5, 0.6), (3, 2.0, 67, 1.0, 0.7),
          (3, 3.0, 65, 0.5, 0.55), (3, 3.5, 62, 0.5, 0.55)]
S_ANSWER = S_TUNE[:8] + [(2, 0.0, 72, 1.0, 0.75), (2, 1.0, 75, 0.5, 0.65), (2, 1.5, 77, 0.5, 0.7),
                         (2, 2.0, 80, 2.0, 0.8), (3, 0.0, 79, 1.0, 0.75), (3, 1.0, 74, 1.0, 0.65), (3, 2.0, 71, 2.0, 0.7)]


def staging_music(r, v):
    G = S
    cache = Cache()
    ep, bass, vib = Mix(G.total, stereo=True), Mix(G.total), Mix(G.total, stereo=True)
    kick_b, rim_b, brush_b, ride_b = Mix(G.total), Mix(G.total), Mix(G.total, stereo=True), Mix(G.total, stereo=True)
    for bar in range(G.bars):
        walk, voicing = S_CHORDS[bar % 4]
        sparse = bar >= 24 or bar < 2
        for q, m in enumerate(walk):
            x = cache.get_or(("ub", m), lambda m_=m: upright(r, float(midi(m_)), 1.0, vel=0.8, gate=0.62))
            bass.add(x, G.t(bar, q) + r.uniform(-0.004, 0.004), (1.0 if q == 0 else 0.82) * (0.9 + 0.2 * r.random()))
        comp = ((0.0, 0.55), (1.5, 0.45), (3.5, 0.35)) if not sparse else ((0.0, 0.5),)
        for beat, vel in comp:
            for i, m in enumerate(voicing):
                x = cache.get_or(("ep", m, vel), lambda m_=m, v_=vel: epiano(r, float(midi(m_)), 2.6, vel=v_,
                                                                            gate=1.0 if v_ < 0.5 else 2.4, trem=0.25))
                ep.add(x, G.t(bar, beat) + 0.01 * i, vel, pan_pos=-0.35 + 0.15 * i)
    kk = kick(r, 0.5, f0=90, f1=48, decay=0.22, click=0.05, drive=1.2)
    rm = rim(r, 0.08, 1750)
    sw = brush(r, 0.4, decay=0.12, lo=1800, hi=7500, attack=0.03)
    tap = brush(r, 0.12, decay=0.03, lo=2000, hi=8000, attack=0.003)
    rd = ride(r, 1.4, decay=0.6, bell=0.12)
    for bar in range(G.bars):
        kick_b.add(kk, G.t(bar), 1.0)
        kick_b.add(kk, G.t(bar, 2.5), 0.65)
        for beat in range(4):
            brush_b.add(sw, G.t(bar, beat) - 0.03, 0.55 + 0.25 * (beat % 2), pan_pos=-0.25)
            brush_b.add(tap, G.t(bar, beat + 0.5), 0.35, pan_pos=-0.2)
            if beat in (1, 3):
                rim_b.add(rm, G.t(bar, beat), 0.75 if 4 <= bar < 24 else 0.5)
        if 4 <= bar < 24:  # ride: ding, ding-a ding
            for beat, vel in ((0, 0.7), (1, 0.8), (1.5, 0.45), (2, 0.7), (3, 0.8), (3.5, 0.45)):
                ride_b.add(rd, G.t(bar, beat), vel, pan_pos=0.35)
    for bar0, phrase, octave in ((4, S_TUNE, 0), (8, S_ANSWER, 0), (12, S_TUNE, 12), (16, S_ANSWER, 0),
                                 (20, S_TUNE[:8], 0)):
        for bar, beat, m, ln, vel in place(phrase, bar0, octave):
            x = cache.get_or(("vib", m), lambda m_=m: vibes(r, float(midi(m_)), 2.8, vel=0.75, motor=0.35))
            vib.add(x, G.t(bar, beat), vel * (0.8 if octave else 1.0), pan_pos=0.2)
    # brush swirl: the snare head swept in circles, two strokes per bar; continuous, so it is
    # built circularly at exactly the loop length and added after the fold
    tt = tvec(G.loop_n)
    stroke = 0.35 + 0.65 * np.abs(np.sin(np.pi * tt / (2 * G.beat))) ** 1.5
    swirl = band(r.standard_normal(G.loop_n), 2200, 6500, circular=True) * stroke
    swirl = np.stack([swirl, np.roll(swirl, ns(0.013))])
    vib_bus = wet(pingpong(vib.out(), 0.5 * G.beat * 1.5, taps=3, fb=0.25, tone=2200), r, "club", 0.4, t60=1.6)
    mix = (lvl(wet(ep.out(), r, "club", 0.3, t60=1.4), -27.0) + lvl(st(bass.out()), -24.0) + lvl(vib_bus, -26.5)
           + lvl(st(kick_b.out()), -29.0) + lvl(wet(rim_b.out(), r, "club", 0.3), -33.0)
           + lvl(wet(brush_b.out(), r, "small", 0.3), -35.0) + lvl(ride_b.out(), -36.0))
    mix = fold_tail(mix, G.loop_n) + lvl(swirl, -42.0)
    return lp(mix, 9000, order=2, circular=True)  # warm, nothing harsh


RECIPES = {
    "ClubMusic": (club_music, 1, "64 bars @ 128 BPM (120 s) dark industrial techno in F minor: distorted kick + rumble, "
                  "sidechained rolling bass, metal percussion, gritty stabs, original hook from bar 17, breakdown 33-40, "
                  "build 41-48, drop 49-60 (in-world speakers)", dict(LOOP, lufs=-16.0)),
    "MenuMusic": (menu_music, 1, "32 bars @ 85.3 BPM (90 s) brooding neo-noir in C# minor: analog pedal drone, metal "
                  "textures, original motif on a dark lead, slow heavy half-time drums from bar 9", dict(LOOP, lufs=-18.0)),
    "PostRoundMusic": (postround_music, 1, "12 bars @ 72 BPM (40 s) after-action bed in G minor: electric piano, warm "
                       "pads, sub bass, soft low drums, sparse vibraphone motif", dict(LOOP, lufs=-19.0)),
    "StagingMusic": (staging_music, 1, "28 bars @ 89.6 BPM (75 s) swung lounge-noir groove in C minor for lobby/armory: "
                     "brushes, ride, upright bass, electric piano, vibraphone tune; quiet, no harsh elements",
                     dict(LOOP, lufs=-21.0)),
}
