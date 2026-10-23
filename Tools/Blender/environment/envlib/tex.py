"""Numpy-only, resolution-independent, *periodic* texture synthesis.

Every generator works in tile space (u, v in [0, 1)) and wraps, so the output
tiles seamlessly by construction. Feature sizes are given in cycles per tile or
metres (via the ``Ctx`` helper), never in pixels, so a 1024 preview and the
4096 final look the same apart from detail.

Image arrays are row 0 = top, float32. Normal maps are DirectX (green = -Y).
"""
import math
import struct
import zlib

import numpy as np

F32 = np.float32


# ----------------------------------------------------------------------------
# context
# ----------------------------------------------------------------------------
class Ctx:
    """Resolution + physical tile size + deterministic RNG."""

    def __init__(self, n, tile_m, seed):
        self.n = int(n)
        self.tile = float(tile_m)
        self.seed = int(seed)
        self._k = 0
        u = (np.arange(self.n, dtype=F32) + 0.5) / self.n
        self.u = u[None, :]          # x, (1, n)
        self.v = u[:, None]          # y (down), (n, 1)

    def rng(self):
        self._k += 1
        return np.random.default_rng(self.seed * 1000 + self._k)

    def cyc(self, metres):
        """Number of cycles per tile for a feature of the given size."""
        return max(1, int(round(self.tile / metres)))

    def px(self, metres):
        return metres / self.tile * self.n

    # ---- noise -------------------------------------------------------------
    def noise(self, size_m, oct=4, rough=0.55, aniso=1.0, seed_off=0, lo=None):
        """Band-limited fBm noise with features ~size_m metres, zero mean,
        unit std. ``aniso`` > 1 stretches features along x."""
        return fbm(self.n, self.rng(), self.tile / size_m, oct=oct, rough=rough,
                   aniso=aniso)

    def n01(self, size_m, oct=4, rough=0.55, aniso=1.0):
        return norm01(self.noise(size_m, oct, rough, aniso))


def norm01(a, lo_pct=0.5, hi_pct=99.5):
    lo, hi = np.percentile(a[:: max(1, a.shape[0] // 512), :: max(1, a.shape[1] // 512)],
                           [lo_pct, hi_pct])
    return np.clip((a - lo) / max(1e-6, hi - lo), 0, 1).astype(F32)


def fbm(n, rng, base_freq, oct=4, rough=0.55, aniso=1.0):
    """Periodic fractal noise built directly in the frequency domain.

    base_freq: cycles per tile of the coarsest octave. Each octave doubles the
    frequency and multiplies amplitude by ``rough``.
    """
    fy = np.fft.fftfreq(n, d=1.0 / n).astype(F32)[:, None]
    fx = np.fft.rfftfreq(n, d=1.0 / n).astype(F32)[None, :]
    r = np.sqrt((fx * aniso) ** 2 + fy ** 2)
    r = np.maximum(r, 1e-3)
    amp = np.zeros_like(r)
    f = float(base_freq)
    a = 1.0
    nyq = n / 2.0
    f = min(f, nyq * 0.6)
    for _ in range(oct):
        if f > nyq * 1.2:
            break
        # log-gaussian band around f (one octave wide)
        band = np.exp(-0.5 * (np.log2(r / f) / 0.5) ** 2)
        amp += a * band
        f *= 2.0
        a *= rough
    amp[0, 0] = 0
    spec = (rng.standard_normal(r.shape, dtype=F32) + 1j * rng.standard_normal(r.shape, dtype=F32))
    spec = (spec * amp).astype(np.complex64)
    out = np.fft.irfft2(spec, s=(n, n)).astype(F32)
    s = out.std()
    return out / max(s, 1e-9)


def blur(a, sigma_px):
    """Periodic gaussian blur (FFT). Works on (n,n) or (n,n,c)."""
    if sigma_px <= 0.05:
        return a
    if a.ndim == 3:
        return np.stack([blur(a[..., i], sigma_px) for i in range(a.shape[2])], -1)
    h, w = a.shape
    fy = np.fft.fftfreq(h).astype(F32)[:, None]
    fx = np.fft.rfftfreq(w).astype(F32)[None, :]
    g = np.exp(-2 * (math.pi ** 2) * (sigma_px ** 2) * (fx ** 2 + fy ** 2)).astype(F32)
    return np.fft.irfft2(np.fft.rfft2(a) * g, s=(h, w)).astype(F32)


def sample(img, x, y):
    """Bilinear periodic sampling; x,y in pixels (any shape)."""
    h, w = img.shape[:2]
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = (x - x0).astype(F32)
    fy = (y - y0).astype(F32)
    x0 = x0.astype(np.int64) % w
    y0 = y0.astype(np.int64) % h
    x1 = (x0 + 1) % w
    y1 = (y0 + 1) % h
    if img.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    a = img[y0, x0] * (1 - fx) + img[y0, x1] * fx
    b = img[y1, x0] * (1 - fx) + img[y1, x1] * fx
    return (a * (1 - fy) + b * fy).astype(F32)


def warp(img, dx_px, dy_px):
    h, w = img.shape[:2]
    X = np.arange(w, dtype=F32)[None, :] + dx_px
    Y = np.arange(h, dtype=F32)[:, None] + dy_px
    return sample(img, X, Y)


def resize_periodic(img, n):
    h = img.shape[0]
    if h == n:
        return img
    s = h / n
    X = (np.arange(n, dtype=F32)[None, :] + 0.5) * s - 0.5
    Y = (np.arange(n, dtype=F32)[:, None] + 0.5) * s - 0.5
    return sample(img, np.broadcast_to(X, (n, n)), np.broadcast_to(Y, (n, n)))


# ----------------------------------------------------------------------------
# cellular
# ----------------------------------------------------------------------------
def worley(n, cx, cy, rng, jitter=0.9, U=None, V=None, want_pos=False, cellmetric=False):
    """Periodic Worley noise on a cx*cy jittered grid.

    Returns F1, F2 (tile units) and the int cell id of the nearest point.
    U, V: optional (n,n) warped coordinates in tile units.
    """
    px = (rng.random((cy, cx), dtype=F32) - 0.5) * jitter + 0.5
    py = (rng.random((cy, cx), dtype=F32) - 0.5) * jitter + 0.5
    if U is None:
        uu = (np.arange(n, dtype=F32)[None, :] + 0.5) / n
        vv = (np.arange(n, dtype=F32)[:, None] + 0.5) / n
        U = np.broadcast_to(uu, (n, n))
        V = np.broadcast_to(vv, (n, n))
    X = U * cx
    Y = V * cy
    ix = np.floor(X).astype(np.int32)
    iy = np.floor(Y).astype(np.int32)
    sx = 1.0 / cx
    sy = 1.0 / cy
    if cellmetric:
        sx = sy = 1.0
    F1 = np.full(X.shape, 1e9, F32)
    F2 = np.full(X.shape, 1e9, F32)
    ID = np.zeros(X.shape, np.int32)
    PX = np.zeros(X.shape, F32) if want_pos else None
    PY = np.zeros(X.shape, F32) if want_pos else None
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            jx = ix + ox
            jy = iy + oy
            wx = jx % cx
            wy = jy % cy
            ptx = jx + px[wy, wx]
            pty = jy + py[wy, wx]
            dx = (ptx - X) * sx
            dy = (pty - Y) * sy
            d = np.sqrt(dx * dx + dy * dy)
            m1 = d < F1
            m2 = (~m1) & (d < F2)
            F2 = np.where(m1, F1, np.where(m2, d, F2))
            F1 = np.where(m1, d, F1)
            ID = np.where(m1, wy * cx + wx, ID)
            if want_pos:
                PX = np.where(m1, ptx * sx, PX)
                PY = np.where(m1, pty * sy, PY)
    if want_pos:
        return F1, F2, ID, PX, PY
    return F1, F2, ID


def cell_rand(ID, count, rng):
    """Per-cell random value in [0,1)."""
    t = rng.random(count + 1, dtype=F32)
    return t[ID]


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return (t * t * (3 - 2 * t)).astype(F32)


def lerp(a, b, t):
    if isinstance(t, np.ndarray) and t.ndim == 2 and (np.ndim(a) in (1, 3) or np.ndim(b) in (1, 3)):
        t = t[..., None]
    return (a + (b - a) * t).astype(F32)


def col(hexstr_or_tuple):
    """sRGB colour (0-1 floats) from '#rrggbb' or tuple."""
    if isinstance(hexstr_or_tuple, str):
        h = hexstr_or_tuple.lstrip('#')
        return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], F32)
    return np.array(hexstr_or_tuple, F32)


def ramp(t, stops):
    """Colour ramp. stops = [(pos, colour), ...] sorted by pos."""
    t = np.clip(t, 0, 1)
    out = np.zeros(t.shape + (3,), F32)
    out[:] = stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops[:-1], stops[1:]):
        k = np.clip((t - p0) / max(1e-6, p1 - p0), 0, 1)[..., None]
        m = (t >= p0)[..., None]
        out = np.where(m, c0 + (c1 - c0) * k, out)
    return out.astype(F32)


def hsv_jitter(c, amount_v, amount_s=0.0, sat_ref=None):
    """Multiply value (and push saturation) of an sRGB colour image by
    per-pixel fields."""
    lum = c.mean(-1, keepdims=True)
    out = c * (1 + amount_v[..., None])
    if not isinstance(amount_s, float):
        out = lum * (1 + amount_v[..., None]) + (out - lum * (1 + amount_v[..., None])) * (1 + amount_s[..., None])
    return np.clip(out, 0, 1).astype(F32)


def height_to_normal(h_m, tile_m, strength=1.0):
    """DirectX tangent-space normal (0-1 encoded RGB) from height in metres."""
    n = h_m.shape[0]
    p = tile_m / n
    dx = (np.roll(h_m, -1, 1) - np.roll(h_m, 1, 1)) / (2 * p) * strength
    dr = (np.roll(h_m, -1, 0) - np.roll(h_m, 1, 0)) / (2 * p) * strength
    nx = -dx
    ny = -dr  # DirectX: green points down the image
    nz = np.ones_like(nx)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / l * 0.5 + 0.5, ny / l * 0.5 + 0.5, nz / l * 0.5 + 0.5], -1).astype(F32)


def cavity_ao(h_m, tile_m, radii_m=(0.004, 0.015, 0.05), gain=1.0):
    """Approximate AO from a height field: how far a pixel sits below its
    neighbourhood at several radii."""
    n = h_m.shape[0]
    occ = np.zeros_like(h_m)
    for r in radii_m:
        s = r / tile_m * n
        if s < 0.5:
            continue
        b = blur(h_m, s)
        occ += np.clip((b - h_m) / r * 2.2 * gain, 0, 1)
    occ /= max(1, len(radii_m))
    return np.clip(1 - occ, 0, 1).astype(F32)


def grain_lines(ctx, freq_cyc, warp_amt, warp_size_m, axis='x', seed_noise=None):
    """Wood-grain like periodic stripes (sin of warped coordinate)."""
    w = ctx.noise(warp_size_m, oct=4, rough=0.5)
    w2 = ctx.noise(warp_size_m * 0.25, oct=3, rough=0.5)
    if axis == 'x':  # grain runs along x -> stripes vary with v
        c = ctx.v + (w * warp_amt + w2 * warp_amt * 0.15)
    else:
        c = ctx.u + (w * warp_amt + w2 * warp_amt * 0.15)
    return (0.5 + 0.5 * np.sin(2 * math.pi * freq_cyc * c)).astype(F32), c


def stamp(canvas, sprite, x, y, mode='max', alpha=None):
    """Periodic blit of ``sprite`` with top-left at (x,y) pixels."""
    n = canvas.shape[0]
    sh, sw = sprite.shape[:2]
    ys = (np.arange(sh) + int(y)) % n
    xs = (np.arange(sw) + int(x)) % n
    sub = canvas[np.ix_(ys, xs)]
    if mode == 'max':
        res = np.maximum(sub, sprite)
    elif mode == 'add':
        res = sub + sprite
    elif mode == 'over':
        a = alpha if alpha is not None else 1.0
        if sub.ndim == 3 and np.ndim(a) == 2:
            a = a[..., None]
        res = sub * (1 - a) + sprite * a
    elif mode == 'min':
        res = np.minimum(sub, sprite)
    else:
        raise ValueError(mode)
    canvas[np.ix_(ys, xs)] = res


# ----------------------------------------------------------------------------
# PNG IO (no PIL in this python)
# ----------------------------------------------------------------------------
def _chunk(tag, data):
    c = struct.pack('>I', len(data)) + tag + data
    return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)


def save_png(path, arr, bits=8, level=6):
    """arr float in [0,1], (h,w) or (h,w,c) with c in 1..4, row 0 = top."""
    a = np.asarray(arr, dtype=F32)
    if a.ndim == 2:
        a = a[..., None]
    h, w, c = a.shape
    a = np.clip(a, 0, 1)
    if bits == 8:
        data = (a * 255 + 0.5).astype(np.uint8)
    else:
        data = (a * 65535 + 0.5).astype('>u2')
    ctype = {1: 0, 2: 4, 3: 2, 4: 6}[c]
    raw = np.ascontiguousarray(data).view(np.uint8).reshape(h, -1)
    bpp = c * (bits // 8)
    # Sub filter (type 1): byte - byte bpp to the left
    sub = raw.copy()
    sub[:, bpp:] = raw[:, bpp:] - raw[:, :-bpp]
    rows = np.concatenate([np.full((h, 1), 1, np.uint8), sub], 1)
    comp = zlib.compress(rows.tobytes(), level)
    out = b'\x89PNG\r\n\x1a\n'
    out += _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, bits, ctype, 0, 0, 0))
    out += _chunk(b'IDAT', comp)
    out += _chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(out)


def srgb_to_lin(c):
    c = np.asarray(c, F32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(F32)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, F32), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055).astype(F32)


def draw_polylines(n, polys, widths=None, values=None):
    """Rasterise polylines (list of (k,2) arrays in tile units, may exceed
    [0,1) - wraps) by dense point splatting. Returns (coverage, value_sum)."""
    cov = np.zeros((n, n), F32)
    val = np.zeros((n, n), F32) if values is not None else None
    allx, ally, allw, allv = [], [], [], []
    for i, p in enumerate(polys):
        p = np.asarray(p, F32) * n
        seg = np.diff(p, axis=0)
        L = np.sqrt((seg ** 2).sum(1))
        tot = L.sum()
        k = max(2, int(tot * 2.0) + 2)
        cl = np.concatenate([[0], np.cumsum(L)])
        s = np.linspace(0, tot, k, dtype=F32)
        x = np.interp(s, cl, p[:, 0])
        y = np.interp(s, cl, p[:, 1])
        allx.append(x); ally.append(y)
        w = 1.0 if widths is None else widths[i]
        if np.ndim(w) == 0:
            allw.append(np.full(k, w, F32))
        else:
            allw.append(np.interp(s / max(tot, 1e-6), np.linspace(0, 1, len(w)), w).astype(F32))
        if values is not None:
            allv.append(np.full(k, values[i], F32))
    x = np.concatenate(allx); y = np.concatenate(ally); w = np.concatenate(allw)
    xi = np.round(x).astype(np.int64) % n
    yi = np.round(y).astype(np.int64) % n
    np.add.at(cov, (yi, xi), w)
    if values is not None:
        v = np.concatenate(allv)
        np.add.at(val, (yi, xi), w * v)
    return cov, val


def downward_smear(mask, length_px, steps=24, decay=0.88):
    """Rust/water streaks running down the image from a mask."""
    out = np.zeros_like(mask)
    acc = mask.copy()
    step = max(1, int(length_px / steps))
    w = 1.0
    for _ in range(steps):
        acc = np.roll(acc, step, axis=0)
        w *= decay
        out = np.maximum(out, acc * w)
    return out


def pct(a, q):
    s = max(1, a.shape[0] // 512)
    return float(np.percentile(a[::s, ::s], q))


def cover(field, coverage, soft=0.04):
    """Threshold a field so ~coverage of the area is 1, with soft edge."""
    t = pct(field, 100 * (1 - coverage))
    rng_ = max(pct(field, 99) - pct(field, 1), 1e-6)
    return sstep(t - soft * rng_, t + soft * rng_, field)


def load_png(path):
    """Read PNGs written by save_png (8-bit, Sub filter)."""
    data = open(path, 'rb').read()
    pos = 8
    idat = b''
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if tag == b'IHDR':
            w, h, bits, ctype = struct.unpack('>IIBB', body[:10])
        elif tag == b'IDAT':
            idat += body
        pos += 12 + ln
    c = {0: 1, 4: 2, 2: 3, 6: 4}[ctype]
    bpc = bits // 8
    raw = np.frombuffer(zlib.decompress(idat), np.uint8).reshape(h, 1 + w * c * bpc)
    assert (raw[:, 0] == 1).all()
    px = raw[:, 1:].reshape(h, w, c * bpc)
    px = np.cumsum(px.astype(np.uint32), axis=1) % 256
    px = px.astype(np.uint8)
    if bits == 16:
        px = px.reshape(h, w, c, 2)
        v = (px[..., 0].astype(np.float32) * 256 + px[..., 1]) / 65535.0
    else:
        v = px.reshape(h, w, c).astype(np.float32) / 255.0
    return v
