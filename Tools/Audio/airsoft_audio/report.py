"""Numeric listen-check (peak / true-peak / RMS / onset / centroid / seam) and a
waveform + spectrogram contact sheet rendered with Pillow (or matplotlib-free)."""

import math

import numpy as np

from .dsp import SR, db, loudness, true_peak


def stats(data_i16, loop=False):
    x = np.asarray(data_i16, float) / 32767.0
    if x.ndim == 2 and x.shape[1] == 2:  # interleaved (n, 2) -> (2, n)
        x = x.T
    xs = np.atleast_2d(x)
    m = xs.mean(axis=0)
    n = xs.shape[-1]
    a = np.max(np.abs(xs), axis=0)
    pk = float(a.max())
    win = max(1, int(0.05 * SR))
    pw = (xs ** 2).mean(axis=0)
    e = np.convolve(pw, np.ones(win) / win, mode="valid") if n > win else np.array([pw.mean()])
    onset = int(np.argmax(a >= 0.5 * pk)) if pk > 0 else 0
    spec = np.abs(np.fft.rfft(m[:min(n, 1 << 18)]))
    f = np.fft.rfftfreq(min(n, 1 << 18), 1.0 / SR)
    cen = float((spec * f).sum() / (spec.sum() + 1e-12))
    out = dict(
        ch=xs.shape[0], dur=n / SR, peak=db(pk), tp=db(true_peak(xs)), rms=db(math.sqrt(float((xs ** 2).mean()))),
        st_rms=db(math.sqrt(float(e.max()))) if len(e) else -120.0, onset_ms=1000.0 * onset / SR, centroid=cen,
        dc=float(np.abs(xs.mean(axis=-1)).max()), clipped=int(np.sum(np.abs(np.asarray(data_i16)) >= 32767)),
        lufs=loudness(xs),
    )
    if loop:
        d = np.abs(np.diff(xs, axis=-1))
        seam = np.abs(xs[:, 0] - xs[:, -1]).max()
        out["seam"] = float(seam / (np.percentile(d, 99.9) + 1e-12))  # <1 means seam is an ordinary step
    return out


def fmt_table(rows):
    hdr = (f"{'file':28s} {'ch':>2s} {'dur s':>7s} {'peak':>6s} {'TP':>6s} {'RMS':>6s} {'maxRMS50':>8s} {'LUFS':>6s} "
           f"{'onset':>6s} {'cent Hz':>7s} {'DC':>6s} {'clip':>4s} {'seam':>5s}")
    lines = [hdr, "-" * len(hdr)]
    for name, s in rows:
        seam = f"{s['seam']:5.2f}" if "seam" in s else "    -"
        lines.append(f"{name:28s} {s['ch']:2d} {s['dur']:7.3f} {s['peak']:6.1f} {s['tp']:6.1f} {s['rms']:6.1f} {s['st_rms']:8.1f} "
                     f"{s['lufs']:6.1f} {s['onset_ms']:6.1f} {s['centroid']:7.0f} {s['dc']:6.4f} {s['clipped']:4d} {seam}")
    return "\n".join(lines)


# ----------------------------------------------------------------- contact sheet

_CMAP = np.array([[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66],
                  [245, 125, 21], [250, 193, 39], [252, 255, 164]], float)


def _colorize(v):
    v = np.clip(v, 0, 1) * (len(_CMAP) - 1)
    i = np.minimum(v.astype(int), len(_CMAP) - 2)
    f = (v - i)[..., None]
    return (_CMAP[i] * (1 - f) + _CMAP[i + 1] * f).astype(np.uint8)


def _spectrogram(m, width, height, fmin=30.0, nfft=1024):
    n = len(m)
    centers = np.linspace(0, max(n - 1, 0), width).astype(int)
    pad = np.pad(m, (nfft // 2, nfft // 2))
    idx = centers[:, None] + np.arange(nfft)[None, :]
    frames = pad[idx] * np.hanning(nfft)
    mag = np.abs(np.fft.rfft(frames, axis=-1)) / (nfft / 4)
    freqs = np.fft.rfftfreq(nfft, 1.0 / SR)
    rows = np.geomspace(fmin, SR / 2, height)[::-1]
    cols = np.stack([np.interp(rows, freqs, col) for col in mag], axis=1)
    dbv = 20 * np.log10(cols + 1e-9)
    return _colorize((dbv + 96.0) / 96.0)


def _wave(m, width, height, clip_mask=None):
    img = np.full((height, width, 3), 18, np.uint8)
    n = len(m)
    edges = np.linspace(0, n, width + 1).astype(int)
    mid = height // 2
    img[mid, :] = (60, 60, 60)
    for c in range(width):
        seg = m[edges[c]:max(edges[c + 1], edges[c] + 1)]
        lo, hi = float(seg.min()), float(seg.max())
        y0 = int(mid - hi * (mid - 1))
        y1 = int(mid - lo * (mid - 1))
        col = (230, 60, 60) if max(abs(lo), abs(hi)) > 0.995 else (120, 200, 255)
        img[max(0, y0):min(height, y1 + 1), c] = col
    return img


def contact_sheet(path, items, loops, cols=6, tile_w=300):
    """items/loops: list of (name, float array (n,) or (2, n), stats)."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.load_default(size=13)
    except TypeError:
        font = ImageFont.load_default()
    lab_h, wav_h, spec_h, gap = 30, 46, 90, 6
    tile_h = lab_h + wav_h + spec_h
    rows = -(-len(items) // cols)
    loop_h = lab_h + 40 + 80
    W = cols * (tile_w + gap) + gap
    H = 40 + rows * (tile_h + gap) + 30 + len(loops) * (loop_h + gap) + gap
    sheet = Image.new("RGB", (W, H), (8, 8, 10))
    d = ImageDraw.Draw(sheet)
    d.text((gap, 10), "Andrew's Airsoft - generated audio overview (wave: red = >-0.04 dBFS; spectrogram log-freq 30 Hz-24 kHz, 96 dB range)",
           fill=(230, 230, 230), font=font)
    for i, (name, x, s) in enumerate(items):
        cx = gap + (i % cols) * (tile_w + gap)
        cy = 40 + (i // cols) * (tile_h + gap)
        m = x.mean(axis=0) if x.ndim == 2 else x
        d.text((cx + 3, cy + 1), f"{name}  {s['ch']}ch {s['dur']:.2f}s", fill=(240, 240, 240), font=font)
        d.text((cx + 3, cy + 15), f"pk {s['peak']:.1f}  rms {s['rms']:.1f}  on {s['onset_ms']:.1f}ms", fill=(150, 160, 170), font=font)
        sheet.paste(Image.fromarray(_wave(m, tile_w, wav_h)), (cx, cy + lab_h))
        sheet.paste(Image.fromarray(_spectrogram(m, tile_w, spec_h)), (cx, cy + lab_h + wav_h))
    y = 40 + rows * (tile_h + gap) + 30
    d.text((gap, y - 22), "Loops (full length; seam = |first-last| / p99.9 step, <~1 is seamless)", fill=(230, 230, 230), font=font)
    lw = W - 2 * gap
    for name, x, s in loops:
        m = x.mean(axis=0) if x.ndim == 2 else x
        d.text((gap + 3, y + 1), f"{name}  {s['ch']}ch {s['dur']:.1f}s  pk {s['peak']:.1f}  rms {s['rms']:.1f}  seam {s.get('seam', 0):.2f}",
               fill=(240, 240, 240), font=font)
        sheet.paste(Image.fromarray(_wave(m, lw, 40)), (gap, y + lab_h))
        sheet.paste(Image.fromarray(_spectrogram(m, lw, 80, nfft=2048)), (gap, y + lab_h + 40))
        y += loop_h + gap
    sheet.save(path, optimize=True)
    return path
