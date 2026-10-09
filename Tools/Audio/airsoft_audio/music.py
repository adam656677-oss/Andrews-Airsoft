"""Music loops (stereo, seamless): rendered with their reverb/delay tails and
then folded so everything past the loop end overlaps the start."""

import numpy as np

from .dsp import (SR, Mix, burst, colored, conv, env, env_pts, eq, fold_tail, hp, lp,
                  make_ir, modes, ns, pan, pulse, saturate, saw, sine, smooth_random,
                  thump, tvec, tvf, ROOMS)
from .instruments import clap, hat, kick, midi, pad_voice, piano

LOOP = {"ch": 2, "loop": True}


def lvl(x, rms_db):
    rms = np.sqrt(np.mean(np.asarray(x) ** 2)) + 1e-12
    return x * (10 ** (rms_db / 20.0) / rms)


def wet(x, r, room, amount, **kw):
    p = dict(ROOMS[room])
    p.update(kw)
    ir = make_ir(r, ch=2, **p)
    x = np.stack([x, x]) if x.ndim == 1 else x
    w = np.stack([conv(x[i], ir[i])[:x.shape[-1]] for i in range(2)])
    return x + amount * w


def simple_pluck(r, f, seconds=0.32):
    n = ns(seconds)
    x = 0.6 * saw(f, n, r.random()) + 0.4 * pulse(f * 1.004, n, 0.3, r.random())
    bright = lp(x, min(7000.0, f * 9))
    dark = lp(x, f * 2.2)
    return bright * env(n, 0.002, 0.045) + 0.8 * dark * env(n, 0.002, 0.16)


# ----------------------------------------------------------------- club music

BPM = 122.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
S16 = BEAT / 4
BARS = 64
CHORDS = [  # bass root (midi), pad voicing
    (33, [57, 60, 64, 67, 71]),  # Am9
    (29, [53, 57, 60, 64, 67]),  # Fmaj9
    (38, [50, 53, 57, 60, 64]),  # Dm9
    (40, [52, 55, 59, 62, 69]),  # Em7(11)
]
BASS_A = [(2, 0, 2, 1.0), (6, 0, 1, 0.8), (7, 12, 1, 0.55), (10, 0, 2, 0.9), (13, 7, 1, 0.6), (14, 0, 2, 0.8)]
BASS_B = [(2, 0, 2, 1.0), (5, 0, 1, 0.7), (6, 12, 1, 0.6), (10, 0, 2, 0.9), (12, 3, 1, 0.55), (14, 7, 2, 0.75)]
ARP = [0, 2, 1, 3, 2, 4, 3, 1, 0, 2, 1, 3, 4, 3, 2, 1]


def _sections(bar):
    """What plays in a (0-based) bar."""
    s = dict(kick=True, bass=True, clap=True, hats=True, ghost=False, shaker=False, arp=False, rim=False)
    if 16 <= bar < 56:
        s.update(arp=True)
    if 16 <= bar < 32 or 40 <= bar < 56:
        s.update(ghost=True, shaker=True)
    if 40 <= bar < 56:
        s.update(rim=True)
    if 32 <= bar < 36:
        s.update(kick=False, bass=False, clap=False)
    if 36 <= bar < 40:
        s.update(bass=False, clap=bar >= 38)
    return s


def club_music(r, v):
    loop_n = int(round(BARS * BAR * SR))
    total = BARS * BAR + 4.0
    n = ns(total)
    t = tvec(n)
    drums = Mix(total)
    claps = Mix(total)
    hats = Mix(total)
    bass = Mix(total)
    arp = Mix(total)
    k = kick(r, 0.45, f0=150, f1=47, decay=0.3, click=0.3)
    cl = clap(r)
    oh = hat(r, 0.15, 0.065)
    ch = hat(r, 0.06, 0.018, tone=1.1)
    sh = hp(burst(r, 0.06, 0.012, attack=0.003), 6000)
    rim = modes(0.06, [1700, 2450, 3900], [0.015, 0.01, 0.006], [1, 0.6, 0.3], rng=r)
    bass_cache, pluck_cache = {}, {}
    duck_depth = np.zeros(n)
    for bar in range(BARS):
        s = _sections(bar)
        b0 = bar * BAR
        root, voicing = CHORDS[(bar // 2) % 4]
        for beat in range(4):
            tb = b0 + beat * BEAT
            if s["kick"]:
                drums.add(k, tb, 1.0)
                duck_depth[ns(tb):ns(tb + BEAT)] = 1.0
            if s["clap"] and beat in (1, 3):
                claps.add(cl, tb, 1.0)
            if s["hats"]:
                hats.add(oh, tb + 2 * S16, 1.0 if beat % 2 else 0.85)
            if s["ghost"]:
                hats.add(ch, tb + S16, 0.3)
                hats.add(ch, tb + 3 * S16, 0.38)
            if s["shaker"]:
                for j in range(4):
                    hats.add(sh, tb + j * S16, (0.5, 0.25, 0.8, 0.3)[j] * 0.35)
        if s["rim"] and bar % 2 == 1:
            for step in (3, 11, 14):
                drums.add(rim, b0 + step * S16, 0.12)
        if s["bass"]:
            for step, semi, ln, vel in (BASS_A if bar % 2 == 0 else BASS_B):
                key = (root + semi, ln)
                if key not in bass_cache:
                    f = float(midi(root + semi))
                    nn = ns(ln * S16 + 0.03)
                    e = env_pts(nn, [(0, 0), (0.004, 1.0), (0.1, 0.65), (ln * S16, 0.6), (ln * S16 + 0.03, 0.0)])
                    note = 0.85 * sine(f, nn) + 0.45 * lp(saw(f, nn, 0.3), 240 + 3 * f)
                    bass_cache[key] = saturate(note * e, 1.4)
                bass.add(bass_cache[key], b0 + step * S16, vel)
        if s["arp"]:
            tones = [x + 12 for x in voicing]
            for step in range(16):
                if step in (7, 15) and bar % 4 == 3:
                    continue
                note = tones[ARP[step]]
                if note not in pluck_cache:
                    pluck_cache[note] = simple_pluck(r, float(midi(note)))
                arp.add(pluck_cache[note], b0 + step * S16, (1.0 if step % 4 == 0 else 0.7) * (0.9 + 0.2 * r.random()))
    # pad: one render per chord shape, reused
    pad = np.zeros((2, n))
    seg = 2 * BAR
    pad_cache = {}
    for i in range(BARS // 2):
        root, voicing = CHORDS[i % 4]
        if i % 4 not in pad_cache:
            pn = ns(seg + 0.6)
            p = sum(pad_voice(r, float(midi(m)), pn) for m in voicing) / len(voicing)
            pad_cache[i % 4] = p * env_pts(pn, [(0, 0), (0.25, 1.0), (seg, 0.9), (seg + 0.6, 0.0)])
        a = ns(i * seg)
        p = pad_cache[i % 4]
        e = min(n, a + p.shape[-1])
        pad[:, a:e] += p[:, :e - a]
    bars_f = t / BAR
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * bars_f / 8.0)
    cut = 650 + 350 * lfo + np.interp(bars_f, [0, 16, 32, 34, 36, 40, 56, 64, 70], [0, 250, 450, 1000, 700, 450, 450, 0, 0])
    pad = np.stack([tvf(pad[c], "lp", cut, q=0.9, order=4) for c in range(2)])
    # sidechain pump (bass + pad duck under each kick)
    tb = np.mod(t, BEAT)
    duck = 1.0 - duck_depth * np.exp(-tb / 0.11) * np.minimum(1.0, tb / 0.003)
    bass_sig = bass.out() * (1.0 - 0.55 * (1.0 - duck))
    pad = pad * (1.0 - 0.6 * (1.0 - duck))
    # arp: filter opens over its first 4 bars, then ping-pong dotted-eighth delay
    a_sig = arp.out()
    acut = np.interp(bars_f, [16, 20, 32, 36, 56], [700, 3800, 3800, 2200, 3800])
    a_sig = tvf(a_sig, "lp", acut, q=1.0)
    delay = Mix(total, stereo=True)
    delay.add(a_sig, 0.0, 1.0)
    src = a_sig
    for tap in range(1, 5):
        src = lp(src, 3200 - 400 * tap)
        delay.add(src, tap * 0.75 * BEAT, 0.42 ** tap, pan_pos=(-0.7 if tap % 2 else 0.7))
    arp_bus = delay.out() * (1.0 - 0.3 * (1.0 - duck))
    claps_bus = wet(claps.out(), r, "club", 0.35, t60=0.9)
    mix = (lvl(np.stack([drums.out()] * 2), -17.0) + lvl(np.stack([bass_sig] * 2), -19.5)
           + lvl(pad, -25.0) + lvl(np.stack([hats.out(), np.roll(hats.out(), 11)]), -31.0)
           + lvl(claps_bus, -28.0) + lvl(wet(arp_bus, r, "club", 0.3), -28.0))
    mix = eq(mix, [("peak", 2800, 0.8, -2.5), ("highshelf", 9000, 0.7, -2.0)])
    return fold_tail(mix, loop_n)


# ----------------------------------------------------------------- menu music

M_BPM = 64.0
M_BEAT = 60.0 / M_BPM
M_BAR = 4 * M_BEAT
M_BARS = 24
ML = M_BARS * M_BAR  # 90 s

# (bar, beat, midi notes, velocity, length in beats)
PHRASE_A = [(0, 0, [69], 0.55, 2), (0, 2.5, [77], 0.5, 1), (0, 3.5, [76], 0.45, 1), (1, 0, [74], 0.55, 2),
            (1, 2, [73], 0.5, 2), (2, 1, [69], 0.4, 1), (2, 2, [70], 0.45, 1), (2, 3, [69], 0.4, 3)]
PHRASE_B = [(0, 0, [50, 57, 64, 65], 0.45, 4), (1, 0, [46, 53, 57, 62], 0.42, 4),
            (2, 0, [43, 50, 52, 58], 0.42, 4), (3, 0, [45, 52, 55, 61, 70], 0.48, 4)]
PHRASE_C = [(0, 0, [86], 0.35, 3), (1, 1, [85], 0.33, 3), (2, 2, [81], 0.35, 4)]


def _place(events, bar0, octave=0, roll=0.0):
    out = []
    for bar, beat, notes, vel, ln in events:
        for i, m in enumerate(notes):
            out.append(((bar0 + bar) * M_BAR + (beat + i * roll) * M_BEAT, m + octave, vel, ln * M_BEAT))
    return out


def menu_music(r, v):
    loop_n = ns(ML)
    total = ML + 7.0
    n = ns(total)
    t = tvec(loop_n)

    def p(f):  # loop-periodic frequency
        return round(f * ML) / ML

    # drone (circular, so it needs no folding)
    d = np.zeros((2, loop_n))
    for c in range(2):
        for f, a in ((73.42, 1.0), (73.42 * 2 ** (6 / 1200), 0.9), (110.0, 0.55), (146.83, 0.25)):
            d[c] += a * saw(p(f * (1.0 if c == 0 else 1.0006)), loop_n, r.random())
    cut = 170 + 280 * (0.5 + 0.5 * np.sin(2 * np.pi * t / 45.0)) * (0.8 + 0.2 * np.sin(2 * np.pi * t / 30.0))
    d = np.stack([tvf(d[c], "lp", cut, q=1.1, order=4, circular=True) for c in range(2)])
    sub = np.sin(2 * np.pi * p(36.71) * t) * 0.5
    room = lp(colored(r, loop_n, -6.0, ch=2), 160, circular=True)
    drone = lvl(d, -25.0) + lvl(np.stack([sub, sub]), -33.0) + lvl(room, -42.0)
    # pulse + muted ostinato + piano + string tension, rendered with tails
    pulse_m = Mix(total)
    ost = Mix(total)
    pno = Mix(total, stereo=True)
    strings = Mix(total, stereo=True)
    beat_thump = thump(0.5, 72, 46, 0.11, pitch_tau=0.03)
    pl = lp(simple_pluck(r, float(midi(38)), 0.4), 420)
    for bar in range(M_BARS):
        for beat in range(4):
            tb = bar * M_BAR + beat * M_BEAT
            if 4 <= bar < 22:
                pulse_m.add(beat_thump, tb, 1.0 if beat % 2 == 0 else 0.55)
            if 8 <= bar < 20:
                ost.add(pl, tb, 0.9)
                ost.add(pl, tb + M_BEAT / 2, 0.55)
    notes = (_place(PHRASE_A, 2) + _place(PHRASE_B, 6, roll=0.12) + _place(PHRASE_A, 10, 12)
             + _place(PHRASE_C, 14) + _place(PHRASE_B, 18, roll=0.16) + [(22 * M_BAR, 69, 0.38, 4 * M_BEAT)])
    for at, m, vel, ln in notes:
        f = float(midi(m))
        x = piano(r, f, ln + 2.5, vel=vel, gate=ln)
        pno.add(x, at, vel, pan_pos=np.clip((m - 64) / 30.0, -0.7, 0.7))
    sn = ns(14.0)
    st = tvec(sn)
    sw = env_pts(sn, [(0, 0), (4.0, 1.0), (9.0, 0.8), (14.0, 0.0)])
    for bar0 in (8, 16):
        for f, pp in ((midi(81), -0.4), (midi(82), 0.4)):
            tone = sine(float(f) * (1 + 0.003 * np.sin(2 * np.pi * 5.1 * st + r.random())), sn) * sw
            strings.add(tone, bar0 * M_BAR, 1.0, pan_pos=pp)
    pno_bus = wet(pno.out(), r, "cinema", 0.5)
    str_bus = wet(strings.out(), r, "cinema", 0.7)
    tails = (lvl(np.stack([pulse_m.out()] * 2), -31.0) + lvl(np.stack([lp(ost.out(), 600)] * 2), -33.0)
             + lvl(pno_bus, -22.0) + lvl(str_bus, -36.0))
    return drone + fold_tail(tails, loop_n)


RECIPES = {
    "ClubMusic": (club_music, 1, "64 bars @ 122 BPM (~125.9 s) dark deep house in A minor: Am9-Fmaj9-Dm9-Em7, "
                  "sidechained bass/pad, offbeat hats, clap on 2/4, filtered pad, arp from bar 17 (out at bar 57), mixed under gameplay", LOOP),
    "MenuMusic": (menu_music, 1, "24 bars @ 64 BPM (90 s) neo-noir in D minor: evolving low drone, sparse piano, soft sub pulse, muted ostinato, string tension", LOOP),
}
