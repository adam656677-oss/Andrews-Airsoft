"""
handkit: signed-distance-field hands for the first-person glove meshes.

A hand is an anatomical skeleton (wrist, carpus, four metacarpals, finger phalanges,
thumb chain) whose bones are wrapped in rounded cones and ellipsoids and blended with
smooth unions.  Glove details (knuckle shell, finger pads, velcro strap, palm
reinforcement) are raised offsets of that surface inside a region, so they follow the
hand exactly.  The field is meshed with naive surface nets (numpy only) and the vertices
are projected back onto the iso-surface with a few Newton steps.

Units are metres.  Hand-local frame (right hand): origin at the wrist joint centre,
+x distal (towards the fingers), +y radial (thumb side), +z dorsal (back of the hand).
A left hand is the same skeleton mirrored (y -> -y) before it is placed.
"""

import math

import numpy as np

MM = 0.001


# --------------------------------------------------------------------------------------
# SDF primitives (p: (N, 3) float arrays; all return (N,) distances)
# --------------------------------------------------------------------------------------


def sd_round_cone(p, a, b, r1, r2):
    """Exact distance to a rounded cone (capsule with radii r1 at a, r2 at b)."""
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    ba = b - a
    l2 = float(ba @ ba)
    if l2 < 1e-12:
        return np.linalg.norm(p - a, axis=1) - max(r1, r2)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    xv = pa * l2 - y[:, None] * ba
    x2 = np.einsum("ij,ij->i", xv, xv)
    y2 = y * y * l2
    z2 = z * z * l2
    k = math.copysign(1.0, rr) * rr * rr * x2 if rr != 0 else np.zeros_like(x2)
    out = (np.sqrt(np.maximum(x2 * a2 * il2, 0.0)) + y * rr) * il2 - r1
    c2 = np.sign(y) * a2 * y2 < k
    out = np.where(c2, np.sqrt(x2 + y2) * il2 - r1, out)
    c1 = np.sign(z) * a2 * z2 > k
    out = np.where(c1, np.sqrt(x2 + z2) * il2 - r2, out)
    return out


def sd_ellipsoid(q, r):
    """Approximate (bound) distance to an axis-aligned ellipsoid, q in its local frame."""
    r = np.asarray(r, np.float64)
    k0 = np.linalg.norm(q / r, axis=1)
    k1 = np.linalg.norm(q / (r * r), axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)


def sd_round_box(q, b, rad):
    """Rounded box with half extents b (rounding included), q in its local frame."""
    d = np.abs(q) - (np.asarray(b) - rad)
    return np.linalg.norm(np.maximum(d, 0.0), axis=1) + np.minimum(d.max(axis=1), 0.0) - rad


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def normalize(v):
    v = np.asarray(v, np.float64)
    return v / np.linalg.norm(v)


def rot_axis(axis, ang):
    """Rotation matrix (Rodrigues) about a unit axis, angle in radians."""
    x, y, z = normalize(axis)
    c, s = math.cos(ang), math.sin(ang)
    C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s], [y * x * C + z * s, c + y * y * C, y * z * C - x * s], [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def frame_from(x_dir, z_hint):
    """Orthonormal frame (columns x, y, z) with x along x_dir and z close to z_hint."""
    x = normalize(x_dir)
    z = np.asarray(z_hint, np.float64)
    z = normalize(z - x * (z @ x))
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=1)


# --------------------------------------------------------------------------------------
# Field: a list of primitives combined in order
# --------------------------------------------------------------------------------------


class Prim:
    """One shape in world space.  kind: 'cone' (a, b, r1, r2), 'ell' (c, M, r),
    'box' (c, M, b, rad).  tag: zone/body-part name.  dorsal: unit vector (world) that
    points to the back of the hand for this part (palmar/dorsal classification)."""

    def __init__(self, kind, tag, dorsal=None, blend=0.0, **kw):
        self.kind = kind
        self.tag = tag
        self.dorsal = None if dorsal is None else normalize(dorsal)
        self.blend = blend
        self.kw = kw

    def eval(self, p):
        k = self.kw
        if self.kind == "cone":
            return sd_round_cone(p, k["a"], k["b"], k["r1"], k["r2"])
        if self.kind == "ell":
            q = (p - k["c"]) @ k["M"]
            return sd_ellipsoid(q, k["r"])
        if self.kind == "box":
            q = (p - k["c"]) @ k["M"]
            return sd_round_box(q, k["b"], k["rad"])
        raise ValueError(self.kind)

    def axis_point(self, p):
        """Closest point on the primitive's core (for radial direction)."""
        k = self.kw
        if self.kind == "cone":
            a, b = np.asarray(k["a"]), np.asarray(k["b"])
            ba = b - a
            t = np.clip(((p - a) @ ba) / max(ba @ ba, 1e-12), 0, 1)
            return a + t[:, None] * ba
        return np.broadcast_to(np.asarray(k["c"]), p.shape)

    def bounds(self):
        k = self.kw
        if self.kind == "cone":
            r = max(k["r1"], k["r2"])
            a, b = np.asarray(k["a"]), np.asarray(k["b"])
            return np.minimum(a, b) - r, np.maximum(a, b) + r
        r = float(np.max(k["r"])) if self.kind == "ell" else float(np.linalg.norm(k["b"]))
        c = np.asarray(k["c"])
        return c - r, c + r


class Feature:
    """A raised glove detail: (base - thickness) intersected with a region SDF.
    region: callable p -> distance (negative inside)."""

    def __init__(self, tag, thickness, region, k_edge=0.0012, k_join=0.0008, base_tags=None):
        self.tag = tag
        self.t = thickness
        self.region = region
        self.k_edge = k_edge
        self.k_join = k_join
        self.base_tags = base_tags


class Field:
    def __init__(self):
        self.prims = []  # (Prim, smooth k)
        self.features = []
        self.cuts = []  # callables: distance of material removed (grooves)

    def add(self, prim, k=0.0):
        self.prims.append((prim, k))
        return prim

    def base(self, p, return_parts=False):
        d = None
        parts = []
        for prim, k in self.prims:
            di = prim.eval(p)
            parts.append(di)
            d = di if d is None else smin(d, di, k)
        return (d, parts) if return_parts else d

    def eval(self, p, return_info=False):
        b, parts = self.base(p, True)
        d = b
        feats = []
        for f in self.features:
            fd = smax(b - f.t, f.region(p), f.k_edge)
            feats.append(fd)
            d = smin(d, fd, f.k_join)
        for c in self.cuts:
            d = smax(d, -c(p), 0.0006)
        if return_info:
            return d, b, parts, feats
        return d

    def bounds(self, pad=0.01):
        lo = np.full(3, 1e9)
        hi = np.full(3, -1e9)
        for prim, _ in self.prims:
            a, b = prim.bounds()
            lo = np.minimum(lo, a)
            hi = np.maximum(hi, b)
        return lo - pad, hi + pad

    def gradient(self, p, h=2e-4):
        g = np.zeros_like(p)
        for i in range(3):
            e = np.zeros(3)
            e[i] = h
            g[:, i] = (self.eval(p + e) - self.eval(p - e)) / (2 * h)
        return g

    def project(self, p, iters=3):
        for _ in range(iters):
            d = self.eval(p)
            g = self.gradient(p)
            g2 = np.maximum(np.einsum("ij,ij->i", g, g), 1e-8)
            p = p - (d / g2)[:, None] * g
        return p


# --------------------------------------------------------------------------------------
# Surface nets
# --------------------------------------------------------------------------------------


def surface_nets(F, origin, h):
    """F: (nx, ny, nz) samples (negative inside) at origin + (i, j, k) * h.
    Returns vertices (V, 3) and quads (Q, 4) with outward winding."""
    nx, ny, nz = F.shape
    inside = F < 0
    # edge crossings along each axis
    cell_sum = {}
    cell_cnt = {}
    sums = np.zeros((nx - 1, ny - 1, nz - 1, 3), np.float64)
    cnts = np.zeros((nx - 1, ny - 1, nz - 1), np.int32)
    quads = []
    offs = np.array([[0, 0, 0]])
    for ax in range(3):
        sl0 = [slice(None)] * 3
        sl1 = [slice(None)] * 3
        sl0[ax] = slice(0, -1)
        sl1[ax] = slice(1, None)
        a = F[tuple(sl0)]
        b = F[tuple(sl1)]
        s = inside[tuple(sl0)] != inside[tuple(sl1)]
        idx = np.argwhere(s)  # edge start grid index
        if len(idx) == 0:
            continue
        fa = a[s]
        fb = b[s]
        t = fa / (fa - fb)
        pos = idx.astype(np.float64)
        pos[:, ax] += t
        # the 4 cells around this edge: vary the two other axes by -1/0
        o1, o2 = [i for i in range(3) if i != ax]
        cells = []
        for d1, d2 in ((-1, -1), (0, -1), (0, 0), (-1, 0)):
            c = idx.copy()
            c[:, o1] += d1
            c[:, o2] += d2
            cells.append(c)
        valid = np.ones(len(idx), bool)
        for c in cells:
            valid &= (c[:, o1] >= 0) & (c[:, o2] >= 0) & (c[:, o1] < [nx - 1, ny - 1, nz - 1][o1]) & (c[:, o2] < [nx - 1, ny - 1, nz - 1][o2]) & (c[:, ax] < [nx - 1, ny - 1, nz - 1][ax])
        for c in cells:
            np.add.at(sums, (c[valid, 0], c[valid, 1], c[valid, 2]), pos[valid])
            np.add.at(cnts, (c[valid, 0], c[valid, 1], c[valid, 2]), 1)
        flip = inside[tuple(sl0)][s][valid]  # inside at the lower end
        q = np.stack([c[valid] for c in cells], axis=1)  # (n, 4, 3)
        # orientation: for an edge along +ax going inside->outside, the normal points +ax
        if ax == 1:
            q = q[:, ::-1]
        q = np.where(flip[:, None, None], q, q[:, ::-1])
        quads.append(q)
    active = cnts > 0
    vid = -np.ones(cnts.shape, np.int64)
    vid[active] = np.arange(active.sum())
    verts = sums[active] / cnts[active][:, None]
    verts = origin + verts * h
    Q = np.concatenate(quads, axis=0)
    faces = vid[Q[..., 0], Q[..., 1], Q[..., 2]]
    faces = faces[(faces >= 0).all(axis=1)]
    return verts, faces


def mesh_field(field, h, lo=None, hi=None, coarse=4):
    """Samples the field on a grid (narrow band refinement) and meshes it."""
    if lo is None:
        lo, hi = field.bounds(pad=3 * h + 0.004)
    n = np.ceil((hi - lo) / h).astype(int) + 1
    # coarse pass
    hc = h * coarse
    nc = np.ceil((n - 1) / coarse).astype(int) + 2
    gc = np.stack(np.meshgrid(*[lo[i] + np.arange(nc[i]) * hc for i in range(3)], indexing="ij"), -1).reshape(-1, 3)
    Fc = field.eval(gc).reshape(nc)
    # fine grid filled from the coarse one, exact values near the surface
    ii = [np.minimum(np.round(np.arange(n[i]) / coarse).astype(int), nc[i] - 1) for i in range(3)]
    F = Fc[np.ix_(*ii)].astype(np.float64)
    band = np.abs(F) < hc * 1.9
    pts = np.argwhere(band)
    P = lo + pts * h
    vals = np.empty(len(P))
    step = 400000
    for s in range(0, len(P), step):
        vals[s : s + step] = field.eval(P[s : s + step])
    F[band] = vals
    F[0, :, :] = F[-1, :, :] = F[:, 0, :] = F[:, -1, :] = F[:, :, 0] = F[:, :, -1] = abs(h)
    return surface_nets(F, lo, h)


# --------------------------------------------------------------------------------------
# Hand skeleton
# --------------------------------------------------------------------------------------

# per finger: MCP joint centre (mm, hand-local), phalanx lengths (P, M, D to tip-sphere
# centre), radii (P base, P end, M base, M end, D base, tip) incl. ~1.5 mm of glove
FINGERS = {
    "index": dict(mcp=(91, 28, -1), lens=(42, 25, 14.5), radii=(10.4, 9.8, 9.4, 8.9, 8.7, 7.7), splay=3.0),
    "middle": dict(mcp=(94, 9, 1), lens=(46, 29, 15.5), radii=(10.7, 10.1, 9.7, 9.2, 8.9, 7.9), splay=0.0),
    "ring": dict(mcp=(88, -10, -1), lens=(43, 28, 15.5), radii=(10.1, 9.6, 9.2, 8.7, 8.4, 7.5), splay=-3.0),
    "little": dict(mcp=(78, -27, -5), lens=(34, 20, 13.5), radii=(9.2, 8.7, 8.3, 7.9, 7.6, 6.8), splay=-8.0),
}
THUMB = dict(cmc=(24, 21, -11), lens=(44, 32, 19), radii=(13.5, 11.6, 11.2, 10.6, 10.4, 8.6))


class Hand:
    """Skeleton + pose -> primitives in world space.

    pose: {finger: (mcp_flex, pip_flex, dip_flex, abduction)} degrees,
          'thumb': list of 3 world-space unit directions (metacarpal, proximal, distal)
                   or None for a default, 'cup': palm cupping (deg).
    place: (R 3x3 hand-local -> world rotation, t wrist position) in world space.
    """

    def __init__(self, left=False, scale=1.0):
        self.left = left
        self.s = scale * MM
        self.R = np.eye(3)
        self.t = np.zeros(3)
        self.pose = {f: (10.0, 10.0, 5.0, 0.0) for f in FINGERS}
        self.thumb_dirs = None
        self.cup = 6.0
        self.forearm_dir = None  # world unit vector from the wrist towards the elbow
        self.forearm_len = 0.09

    # local (mm, right-hand convention) -> world (m)
    def L(self, v):
        v = np.asarray(v, np.float64) * self.s
        if self.left:
            v = v * np.array([1.0, -1.0, 1.0])
        return self.t + self.R @ v

    def Ldir(self, v):
        v = np.asarray(v, np.float64)
        if self.left:
            v = v * np.array([1.0, -1.0, 1.0])
        return normalize(self.R @ v)

    def mcp_local(self, name):
        x, y, z = FINGERS[name]["mcp"]
        # cupping: ulnar metacarpals roll palmar
        c = {"index": -0.3, "middle": 0.0, "ring": 0.6, "little": 1.3}[name] * self.cup
        return np.array([x, y, z - c * 0.6])

    def finger_chain(self, name, angles=None):
        """World joint positions [MCP, PIP, DIP, tip] and the segment dorsal vectors."""
        f = FINGERS[name]
        m, p, d, ab = angles if angles is not None else self.pose[name]
        mcp = self.mcp_local(name)
        # finger base frame in hand-local coordinates
        ax_x = rot_axis((0, 0, 1), math.radians(f["splay"] + ab)) @ np.array([1.0, 0, 0])
        Fr = frame_from(ax_x, (0, 0, 1))
        # cupping rolls the ulnar fingers a little towards the thumb
        roll = {"index": -2.0, "middle": 0.0, "ring": 3.0, "little": 7.0}[name] * self.cup / 6.0
        Fr = rot_axis(Fr[:, 0], math.radians(roll)) @ Fr
        pts = [mcp]
        dors = []
        cur = Fr
        for ang, ln in zip((m, p, d), f["lens"]):
            cur = rot_axis(cur[:, 1], math.radians(ang)) @ cur  # +flex curls towards -z
            pts.append(pts[-1] + cur[:, 0] * ln)
            dors.append(cur[:, 2].copy())
        W = [self.L(q) for q in pts]
        D = [self.Ldir(q) for q in dors]
        return W, D

    def thumb_chain(self):
        t = THUMB
        cmc = np.asarray(t["cmc"], np.float64)
        if self.thumb_dirs is None:
            dirs = [self.Ldir((0.55, 0.62, -0.56)), self.Ldir((0.75, 0.45, -0.48)), self.Ldir((0.9, 0.3, -0.3))]
        else:
            dirs = [normalize(d) for d in self.thumb_dirs]
        W = [self.L(cmc)]
        for d, ln in zip(dirs, t["lens"]):
            W.append(W[-1] + d * ln * self.s)
        return W, dirs

    # ----------------------------------------------------------------------------------
    def build(self, field, details=True):
        """Adds the hand's primitives to `field`; returns landmark dict."""
        s = self.s
        L, Ld = self.L, self.Ldir
        dz = Ld((0, 0, 1))
        lm = {}
        # palm core: rounded slab + metacarpal heads + pads
        Mloc = np.stack([Ld((1, 0, 0)), Ld((0, 1, 0)) * (-1 if self.left else 1), dz], axis=1)
        if self.left:
            Mloc = np.stack([Ld((1, 0, 0)), -Ld((0, -1, 0)) * -1, dz], axis=1)
        Mloc = np.stack([Ld((1, 0, 0)), np.cross(dz, Ld((1, 0, 0))), dz], axis=1)
        # (Mloc columns: x distal, y = z cross x (radial for right, ulnar for left), z dorsal)
        sy = -1.0 if self.left else 1.0

        def box(c, b, rad, tag="palm"):
            q = Prim("box", tag, dorsal=dz, c=L(c), M=Mloc, b=np.asarray(b) * s, rad=rad * s)
            return q

        def ell(c, r, tag, M=None, dors=dz):
            return Prim("ell", tag, dorsal=dors, c=L(c), M=Mloc if M is None else M, r=np.asarray(r) * s)

        def cone(a, b, r1, r2, tag, dors=dz):
            return Prim("cone", tag, dorsal=dors, a=a, b=b, r1=r1 * s, r2=r2 * s)

        k_soft = 7 * s
        field.add(box((50, 1, -3), (36, 34, 13.5), 11.5), 0)
        mcps = {n: self.mcp_local(n) for n in FINGERS}
        bases = {"index": (14, 15, -1), "middle": (12, 5, 0), "ring": (14, -5, -1), "little": (16, -14, -3)}
        for n in FINGERS:
            r_head = FINGERS[n]["radii"][0] + 2.2
            field.add(cone(L(bases[n]), L(mcps[n]), 11.0, r_head, "palm"), k_soft)
        # distal palmar pad (base of the fingers) and heel pads
        field.add(cone(L(mcps["index"] + np.array([-4, 2, -8])), L(mcps["little"] + np.array([-6, -1, -6])), 9.5, 8.5, "palm"), k_soft)
        field.add(ell((38, -24, -9), (32, 13, 13), "palm"), 9 * s)  # hypothenar
        # thenar eminence along the thumb metacarpal
        tw, tdirs = self.thumb_chain()
        mt = tdirs[0]
        Mt = frame_from(mt, -dz)
        field.add(Prim("ell", "palm", dorsal=dz, c=(tw[0] + tw[1]) * 0.5 - dz * 6 * s - Ld((0, 1, 0)) * 3 * s * sy, M=Mt, r=np.array([27, 15, 13]) * s), 8 * s)
        # wrist / carpus
        for yy in (12.0, -11.0):
            field.add(cone(L((22, yy, -2)), L((-6, yy * 0.95, -1)), 17.5, 17.0, "wrist"), 9 * s)
        lm["wrist"] = L((0, 0, 0))
        # forearm / cuff from the wrist joint towards the elbow
        if self.forearm_dir is not None:
            fd = normalize(self.forearm_dir)
            side = Ld((0, 1, 0))
            side = normalize(side - fd * (side @ fd))
            up = np.cross(fd, side)
            w0 = L((-4, 0, 0))
            for yy in (11.5, -10.5):
                a = w0 + side * yy * s * sy
                b = w0 + fd * self.forearm_len + side * yy * 1.12 * s * sy
                field.add(cone(a, b, 17.5, 21.5, "cuff", dors=up), 10 * s)
            lm["cuff_axis"] = (w0, fd, side, up)
        # fingers
        for n, f in FINGERS.items():
            W, D = self.finger_chain(n)
            r = f["radii"]
            tags = ("prox", "mid", "dist")
            for i in range(3):
                a, b = W[i], W[i + 1]
                field.add(cone(a, b, r[2 * i], r[2 * i + 1], f"{n}_{tags[i]}", dors=D[i]), 2.8 * s if i else 6.5 * s)
                # palmar pad: slightly flattened, fuller finger pads
                padoff = -D[i] * 2.3 * s
                ins = 0.12 if i < 2 else 0.05
                pa = a + (b - a) * ins + padoff
                pb = b - (b - a) * 0.12 + padoff
                field.add(cone(pa, pb, r[2 * i] - 2.4, r[2 * i + 1] - 2.1, f"{n}_{tags[i]}", dors=D[i]), 2.5 * s)
            lm[n] = (W, D)
        # thumb
        r = THUMB["radii"]
        # thumb segment dorsal: the nail side faces away from the palm
        prev = None
        tags = ("thumb_mc", "thumb_prox", "thumb_dist")
        for i in range(3):
            a, b = tw[i], tw[i + 1]
            ax = normalize(b - a)
            dd = np.cross(ax, dz) * sy
            dd = normalize(dd if np.linalg.norm(dd) > 1e-3 else dz)
            # make the thumb's dorsal point away from the palm centre
            pc = L((45, 0, -12))
            if dd @ (a - pc) < 0:
                dd = -dd
            field.add(cone(a, b, r[2 * i], r[2 * i + 1], tags[i], dors=dd), 6 * s if i == 0 else 2.8 * s)
            if i > 0:
                padoff = -dd * 2.2 * s
                field.add(cone(a + (b - a) * 0.15 + padoff, b - (b - a) * 0.1 + padoff, r[2 * i] - 2.2, r[2 * i + 1] - 1.8, tags[i], dors=dd), 2.5 * s)
        lm["thumb"] = (tw, tdirs)
        lm["frame"] = Mloc
        self.landmarks = lm
        return lm


# --------------------------------------------------------------------------------------
# Grasping: close finger joints until the links touch an obstacle
# --------------------------------------------------------------------------------------


def grasp(hand, name, obstacle, start=(0.0, 0.0, 0.0), ratios=(1.0, 1.15, 0.8), maxang=(95.0, 105.0, 75.0), clearance=0.0006, step=1.0, abd=0.0):
    """obstacle(p) -> signed distance (m).  Closes MCP/PIP/DIP together; a link that
    touches locks itself and the joints proximal to it.  Returns the angles."""
    f = FINGERS[name]
    ang = list(start)
    locked = [False, False, False]

    def collide(angs):
        W, _ = hand.finger_chain(name, (angs[0], angs[1], angs[2], abd))
        hits = []
        for i in range(3):
            a, b = W[i], W[i + 1]
            ts = np.linspace(0.15 if i == 0 else 0.0, 1.0, 9)
            P = a[None] + ts[:, None] * (b - a)[None]
            rr = (f["radii"][2 * i] + (f["radii"][2 * i + 1] - f["radii"][2 * i]) * ts) * hand.s
            d = obstacle(P) - rr
            hits.append(d.min() < clearance)
        return hits

    if any(collide(ang)):
        return tuple(ang)
    for _ in range(400):
        if all(locked):
            break
        trial = list(ang)
        for j in range(3):
            if not locked[j]:
                trial[j] = min(maxang[j], trial[j] + step * ratios[j])
        if trial == ang:
            break
        hits = collide(trial)
        if any(hits):
            first = hits.index(True)
            for j in range(first + 1):
                locked[j] = True
            # accept the move for joints distal to the hit link only
            for j in range(first + 1, 3):
                if not locked[j]:
                    t2 = list(ang)
                    t2[j] = trial[j]
                    if not any(collide(t2)):
                        ang = t2
            continue
        ang = trial
        for j in range(3):
            if ang[j] >= maxang[j]:
                locked[j] = True
    return tuple(ang)
