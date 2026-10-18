"""
suit_geo: tailoring surfaces for the third-person suit (Tools/Blender/gear/build_suit.py).

Garments are thin cloth shells around the stand-in body (teamgear_body).  Each one is a
parametric grid  P(t, u)  laid over a "radial" body surface: rays leave an axis (the torso
centre line, or a limb bone) and the body radius along every ray is sphere-traced once into a
lattice, then eased, draped and smoothed into a garment radius.  ShellGrid turns a grid of
outer points into a cloth panel with real thickness: the outer face, a rounded rim along every
open edge and a facing on the inside near those edges (hems, cuffs, the open jacket front).

Character space as in teamgear_body: metres, +X forward, +Y the character's left, +Z up.
"""

import math

import numpy as np

import handkit as hk
import teamgear_body as tb
import teamgear_geo as tg


def _n(v):
    v = np.asarray(v, np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def A(x):
    return np.atleast_1d(np.asarray(x, np.float64))


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def gauss(x, c, w):
    return np.exp(-(((np.asarray(x, np.float64) - c) / w) ** 2))


def box_smooth(a, axis, k, iters=1, periodic=False):
    """Repeated box filter (approximately Gaussian) along one axis of a lattice."""
    a = np.asarray(a, np.float64)
    h = k // 2
    for _ in range(iters):
        if periodic:
            pad = np.concatenate([np.take(a, range(-h, 0), axis=axis), a, np.take(a, range(0, h), axis=axis)], axis=axis)
        else:
            pad = np.pad(a, [(h, h) if i == axis else (0, 0) for i in range(a.ndim)], mode="edge")
        c = np.cumsum(pad, axis=axis)
        c = np.concatenate([np.zeros_like(np.take(c, [0], axis=axis)), c], axis=axis)
        n = a.shape[axis]
        a = (np.take(c, range(k, k + n), axis=axis) - np.take(c, range(0, n), axis=axis)) / k
    return a


# --------------------------------------------------------------------------------------
# Stand-in fields used for fitting
# --------------------------------------------------------------------------------------

_FIELDS = {}


def field(kind):
    """'trunk' torso + both legs (no arms, head or neck), 'arm_l', 'leg_l', 'head', 'neck'."""
    if kind in _FIELDS:
        return _FIELDS[kind]
    F = hk.Field()
    if kind == "trunk":
        tb._torso_prims(F)
        for side in ("l", "r"):
            th, kn = tb.bone("thigh_" + side), tb.bone("calf_" + side)
            F.add(tb._cone("thigh", th, kn, 0.096, 0.058), 0.035)
            F.add(tb._ell("quad", tb.lerp(th, kn, 0.45) + (0.022, 0.0, 0.0), (0.070, 0.068, 0.150)), 0.04)
    elif kind == "arm_l":
        sh, el, wr = tb.bone("upperarm_l"), tb.bone("lowerarm_l"), tb.bone("hand_l")
        F.add(tb._ell("deltoid", sh + (0.0, 0.012, 0.006), (0.064, 0.060, 0.072)))
        F.add(tb._cone("upperarm", sh, el, 0.058, 0.044), 0.025)
        F.add(tb._cone("forearm", el, wr, 0.043, 0.030), 0.02)
    elif kind == "leg_l":
        F = tb.field("leg_l")
    elif kind == "head":
        F = tb.field("head")
    else:
        raise ValueError(kind)
    _FIELDS[kind] = F
    return F


# --------------------------------------------------------------------------------------
# Lattices (bilinear, optionally periodic in the second axis)
# --------------------------------------------------------------------------------------


class Lattice:
    def __init__(self, s, th, R, periodic=True):
        self.s = np.asarray(s, np.float64)
        self.th = np.asarray(th, np.float64)
        self.R = np.asarray(R, np.float64)
        self.periodic = periodic

    def __call__(self, th, s):
        th, s = np.broadcast_arrays(A(th), A(s))
        shape = th.shape
        th, s = th.ravel(), s.ravel()
        fs = np.clip((s - self.s[0]) / (self.s[1] - self.s[0]), 0, len(self.s) - 1.000001)
        i0 = np.floor(fs).astype(int)
        a = fs - i0
        i1 = np.minimum(i0 + 1, len(self.s) - 1)
        if self.periodic:
            n = len(self.th)
            ft = np.mod(th - self.th[0], 2 * math.pi) / (2 * math.pi) * n
            j0 = np.floor(ft).astype(int) % n
            b = ft - np.floor(ft)
            j1 = (j0 + 1) % n
        else:
            ft = np.clip((th - self.th[0]) / (self.th[1] - self.th[0]), 0, len(self.th) - 1.000001)
            j0 = np.floor(ft).astype(int)
            b = ft - j0
            j1 = np.minimum(j0 + 1, len(self.th) - 1)
        R = self.R
        out = R[i0, j0] * (1 - a) * (1 - b) + R[i1, j0] * a * (1 - b) + R[i0, j1] * (1 - a) * b + R[i1, j1] * a * b
        return out.reshape(shape)


# --------------------------------------------------------------------------------------
# Torso parametrisation
# --------------------------------------------------------------------------------------

TORSO_AXIS_X = -0.004
S_SPLIT = 1.30  # below: horizontal rays at z = s; above: rays from (axis, S_SPLIT) tilted up
R_REF = 0.20  # s above the split ~ arc length: elevation = (s - S_SPLIT) / R_REF
NECK_AXIS = (np.array([-0.024, 0.0, 1.43]), tb.HEAD + np.array([-0.004, 0.0, 0.0]))


def torso_ray(th, s):
    th, s = np.broadcast_arrays(A(th), A(s))
    phi = np.clip((s - S_SPLIT) / R_REF, 0.0, 1.5)
    z0 = np.minimum(s, S_SPLIT)
    o = np.stack([np.full(th.shape, TORSO_AXIS_X), np.zeros(th.shape), z0], -1)
    d = np.stack([np.cos(th) * np.cos(phi), np.sin(th) * np.cos(phi), np.sin(phi)], -1)
    return o, d


def neck_dist(P):
    """Horizontal-ish distance of points from the neck axis."""
    a, b = NECK_AXIS
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), -2.0, 2.0)
    q = a + t[..., None] * ab
    return np.linalg.norm(P - q, axis=-1)


class TorsoBody:
    """Body radius along every torso ray (sphere traced once)."""

    S = np.arange(0.70, 1.701, 0.005)
    TH = np.radians(np.arange(0, 360, 2.0))

    def __init__(self):
        F = field("trunk")
        ss, tt = np.meshgrid(self.S, self.TH, indexing="ij")
        o, d = torso_ray(tt.ravel(), ss.ravel())
        hit = tb.march(F, o + d * 0.6, -d, steps=120)
        r = np.einsum("ij,ij->i", hit - o, d)
        self.R = np.clip(r.reshape(ss.shape), 0.0, 0.6)
        self.body = Lattice(self.S, self.TH, self.R)


_TB = None


def torso_body():
    global _TB
    if _TB is None:
        _TB = TorsoBody()
    return _TB


class TorsoSurface:
    """A garment surface over the torso: radius lattice R(s, th) -> P(th, s) + normals."""

    def __init__(self, R, S=None, TH=None):
        S = TorsoBody.S if S is None else S
        TH = TorsoBody.TH if TH is None else TH
        self.lat = Lattice(S, TH, R)

    def point(self, th, s, h=0.0):
        th, s, h = np.broadcast_arrays(A(th), A(s), A(h))
        o, d = torso_ray(th, s)
        r = self.lat(th, s)
        P = o + d * r[..., None]
        if np.any(h != 0):
            P = P + self.normal(th, s) * h[..., None]
        return P

    def normal(self, th, s, e=1e-3):
        th, s = np.broadcast_arrays(A(th), A(s))
        Pt = self.point(th + e, s) - self.point(th - e, s)
        Ps = self.point(th, s + e) - self.point(th, s - e)
        N = np.cross(Pt, Ps)
        _o, d = torso_ray(th, s)
        N = np.where((np.einsum("...i,...i->...", N, d) < 0)[..., None], -N, N)
        return _n(N)

    def lateral_scale(self, th, s):
        """Metres per radian along th at (th, s)."""
        return np.linalg.norm(self.point(th + 1e-3, s) - self.point(th - 1e-3, s), axis=-1) / 2e-3

    def theta_for_y(self, y, s, front=True, side=1.0):
        """th on the front (|th| < 90 deg) where the surface reaches lateral position y (sign = side)."""
        lo = np.zeros_like(A(s))
        hi = np.full_like(A(s), math.radians(100))
        for _ in range(40):
            mid = (lo + hi) / 2
            P = self.point(side * mid, s)
            below = side * P[..., 1] < y
            lo = np.where(below, mid, lo)
            hi = np.where(below, hi, mid)
        return side * (lo + hi) / 2


# --------------------------------------------------------------------------------------
# Limb tubes
# --------------------------------------------------------------------------------------


class LimbBody:
    """Body radius around a limb axis a->b (v metres along the axis from a, th around it, 0 = e1)."""

    def __init__(self, F, a, b, e1_hint, v0, v1, dv=0.004, dth=3.0):
        self.a = np.asarray(a, np.float64)
        self.ax = _n(np.asarray(b, np.float64) - self.a)
        h = np.asarray(e1_hint, np.float64)
        self.e1 = _n(h - self.ax * (h @ self.ax))
        self.e2 = np.cross(self.ax, self.e1)
        self.V = np.arange(v0, v1 + 1e-9, dv)
        self.TH = np.radians(np.arange(0, 360, dth))
        vv, tt = np.meshgrid(self.V, self.TH, indexing="ij")
        c = self.a + vv.ravel()[:, None] * self.ax
        d = np.outer(np.cos(tt.ravel()), self.e1) + np.outer(np.sin(tt.ravel()), self.e2)
        hit = tb.march(F, c + d * 0.25, -d, steps=100)
        r = np.einsum("ij,ij->i", hit - c, d)
        self.R = np.clip(r.reshape(vv.shape), 0.0, 0.25)

    def surface(self, R):
        return LimbSurface(self, Lattice(self.V, self.TH, R))


class LimbSurface:
    def __init__(self, body, lat):
        self.b = body
        self.lat = lat

    def dirs(self, th):
        th = A(th)
        return np.cos(th)[..., None] * self.b.e1 + np.sin(th)[..., None] * self.b.e2

    def point(self, th, v, h=0.0):
        th, v, h = np.broadcast_arrays(A(th), A(v), A(h))
        r = self.lat(th, v)
        P = self.b.a + v[..., None] * self.b.ax + self.dirs(th) * r[..., None]
        if np.any(h != 0):
            P = P + self.normal(th, v) * h[..., None]
        return P

    def normal(self, th, v, e=1e-3):
        th, v = np.broadcast_arrays(A(th), A(v))
        Pt = self.point(th + e, v) - self.point(th - e, v)
        Pv = self.point(th, v + e) - self.point(th, v - e)
        N = np.cross(Pt, Pv)
        d = self.dirs(th)
        N = np.where((np.einsum("...i,...i->...", N, d) < 0)[..., None], -N, N)
        return _n(N)


# --------------------------------------------------------------------------------------
# Cloth shell from a grid of outer points
# --------------------------------------------------------------------------------------


def _rim_dirs(P, closed_t):
    """Outward in-surface directions at the four borders (bottom, top, left, right)."""
    du = np.gradient(P, axis=0)
    dt = np.gradient(P, axis=1) if not closed_t else (np.roll(P, -1, axis=1) - np.roll(P, 1, axis=1)) * 0.5
    return _n(-du), _n(du), _n(-dt), _n(dt)


def shell(P, N, thick, closed_t=False, band_rows=(3, 3), band_cols=4, steps=3, attrs=None, rims=(True, True, True, True),
          inner=True, sd_scale=None):
    """Cloth panel with thickness from a (nu, nt) grid of outer points P and outward normals N.

    closed_t: the t direction wraps (a tube).  band_rows / band_cols: rows / columns of inside facing kept
    along each open border.  rims: (bottom, top, left, right) borders that get a rounded rim + facing.
    attrs: optional dict of per-grid-vertex arrays (nu, nt[, 3]) for 'sd', 'ss', 'puv'.
    Returns a teamgear_geo.Mesh with the outer face oriented along N."""
    P = np.asarray(P, np.float64)
    N = _n(N)
    nu, nt = P.shape[:2]
    M = tg.Mesh()
    attrs = attrs or {}

    def at(name, j, i):
        a = attrs.get(name)
        if a is None:
            return None
        return a[j, i]

    def grid_attrs(sl=slice(None)):
        out = {}
        for k in ("sd", "ss", "puv"):
            if k in attrs:
                a = np.asarray(attrs[k])
                out[k] = a.reshape(nu * nt, -1).squeeze() if a.ndim == 3 else a.reshape(-1)
        return out

    # orientation of grid faces (j,i)->(j,i+1)->(j+1,i+1)->(j+1,i) vs N
    j, i = nu // 2, nt // 2
    fn = np.cross(P[j, min(i + 1, nt - 1)] - P[j, i], P[min(j + 1, nu - 1), i] - P[j, i])
    flip = fn @ N[j, i] < 0

    def quad(a, b, c, d, inward=False):
        q = (a, b, c, d)
        if flip != inward:
            q = q[::-1]
        M.f.append(q)

    ob = M.add_verts(P.reshape(-1, 3), **grid_attrs())
    oid = lambda j, i: ob + j * nt + i  # noqa: E731
    ic = nt if closed_t else nt - 1
    for j in range(nu - 1):
        for i in range(ic):
            i2 = (i + 1) % nt
            quad(oid(j, i), oid(j, i2), oid(j + 1, i2), oid(j + 1, i))
    if not inner:
        return M
    # inner surface (facing near open borders); thick may vary per grid vertex (tapered overlaps)
    thick = np.broadcast_to(np.asarray(thick, np.float64), (nu, nt))
    Pin = P - N * thick[..., None]
    ib = M.add_verts(Pin.reshape(-1, 3), **grid_attrs())
    iid = lambda j, i: ib + j * nt + i  # noqa: E731
    rb, rt, rl, rr = rims
    for j in range(nu - 1):
        for i in range(ic):
            i2 = (i + 1) % nt
            near = (rb and j < band_rows[0]) or (rt and j >= nu - 1 - band_rows[1])
            if not closed_t:
                near = near or (rl and i < band_cols) or (rr and i >= nt - 1 - band_cols)
            if near:
                quad(iid(j, i), iid(j, i2), iid(j + 1, i2), iid(j + 1, i), inward=True)
    # rims
    Eb, Et, El, Er = _rim_dirs(P, closed_t)
    loops = []
    if rb:
        loops.append(([(0, i) for i in range(nt)], Eb[0], False))
    if rt:
        loops.append(([(nu - 1, i) for i in range(nt)][::-1], Et[-1][::-1], True))
    if not closed_t:
        if rr:
            loops.append(([(j, nt - 1) for j in range(nu)], Er[:, -1], False))
        if rl:
            loops.append(([(j, 0) for j in range(nu)][::-1], El[:, 0][::-1], True))
    rim_faces = []
    for idx, E, rev in loops:
        n = len(idx)
        rows = [[oid(j, i) for j, i in idx]]
        for k in range(1, steps):
            a = math.pi * k / steps
            pts = []
            for m, (j, i) in enumerate(idx):
                tk = thick[j, i]
                pts.append(P[j, i] - N[j, i] * tk * (1 - math.cos(a)) / 2 + E[m] * tk * 0.5 * math.sin(a))
            kw = {}
            if "sd" in attrs:
                kw["sd"] = np.zeros(n)
            if "ss" in attrs:
                kw["ss"] = np.array([attrs["ss"][j, i] for j, i in idx])
            if "puv" in attrs:
                kw["puv"] = np.array([attrs["puv"][j, i] for j, i in idx])
            rows.append(list(range(M.add_verts(np.array(pts), **kw), M.n)))
        rows.append([iid(j, i) for j, i in idx])
        seg = n if (closed_t and idx[0][0] == idx[-1][0] and len({p[0] for p in idx}) == 1) else n - 1
        for r in range(len(rows) - 1):
            for m in range(seg):
                m2 = (m + 1) % n
                q = [rows[r][m], rows[r][m2], rows[r + 1][m2], rows[r + 1][m]]
                (j0, i0), (j1, i1) = idx[m], idx[m2]
                ref = (P[j0, i0] + P[j1, i1]) * 0.5 - (N[j0, i0] * thick[j0, i0] + N[j1, i1] * thick[j1, i1]) * 0.25
                rim_faces.append((q, ref))
    if rim_faces:
        V = np.concatenate(M.v)
        for q, ref in rim_faces:
            p = V[q]
            fn = np.cross(p[2] - p[0], p[3] - p[1])
            if fn @ (p.mean(axis=0) - ref) < 0:
                q = q[::-1]
            M.f.append(tuple(q))
    return M


def orient_outward(M, centre_fn):
    """Orients every face so its normal points away from centre_fn(face centres) (closed blobs)."""
    V, F, _ = M.arrays()
    Fa = [np.asarray(f) for f in F]
    newf = []
    for f in Fa:
        p = V[f]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        c = p.mean(axis=0)
        if n @ (c - centre_fn(c)) < 0:
            f = f[::-1]
        newf.append(tuple(int(x) for x in f))
    M.f = newf
    return M


def loft(rings, caps=True, attrs=None):
    """Closed rings (list of (k, 3) arrays, same k) joined in order; every face is oriented away from the
    centroid of its rings (convex-ish cross-sections: collars, knots, buckles)."""
    M = tg.Mesh()
    k = len(rings[0])
    base = []
    cents = [np.mean(r, axis=0) for r in rings]
    for i, r in enumerate(rings):
        kw = {} if attrs is None else {key: v[i] for key, v in attrs.items()}
        base.append(M.add_verts(np.asarray(r), **kw))
    V = np.concatenate(M.v)
    faces = []
    for i in range(len(rings) - 1):
        c = (cents[i] + cents[i + 1]) / 2
        for j in range(k):
            j2 = (j + 1) % k
            q = [base[i] + j, base[i] + j2, base[i + 1] + j2, base[i + 1] + j]
            faces.append((q, c))
    if caps:
        for i, nb in ((0, 1), (len(rings) - 1, len(rings) - 2)):
            cc = M.add_verts(cents[i][None, :])
            V = np.concatenate(M.v)
            out = cents[i] - cents[nb]
            for j in range(k):
                j2 = (j + 1) % k
                faces.append(([base[i] + j, base[i] + j2, cc], cents[i] - out))
    V = np.concatenate(M.v)
    for q, c in faces:
        p = V[q]
        fn = np.cross(p[1] - p[0], p[-1] - p[0]) if len(q) == 3 else np.cross(p[2] - p[0], p[3] - p[1])
        if fn @ (p.mean(axis=0) - c) < 0:
            q = q[::-1]
        M.f.append(tuple(q))
    return M


def superellipse(n, w, d, e=0.6):
    """(n, 2) section points: half width w (across), half depth d, exponent e (< 1 boxier)."""
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c, s = np.cos(a), np.sin(a)
    return np.stack([np.sign(s) * np.abs(s) ** e * w, np.sign(c) * np.abs(c) ** e * d], -1)
