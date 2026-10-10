"""
teamgear_geo: parametric modelling helpers for the third-person team gear.

Soft goods are built as "pillows": a closed 2D outline in a local (u, v) frame is turned
into a padded slab (outer face, rounded or boxy rim, optional inner face) and mapped onto
a carrier surface (a plate, a band around the torso, a helmet shell ...) through a map
function  map(u, v, h) -> (points, normals)  where h is the height above that surface.
Straps and bands are profile sweeps along a path with explicit "up" vectors.

Every vertex carries three attributes that the baker reads (Tools/Blender/gear/teamgear_bake.py):
    sd   distance in from the panel edge (stitch rows, edge binding); 1.0 = far from any edge
    ss   arc length along the panel outline / strap (stitch dashes, bar tacks)
    puv  local pattern coordinates (patch emblem, mesh holes, rail slots, zipper teeth)
"""

import math

import bpy  # noqa: I001
import bmesh
import numpy as np

ATTRS = {"sd": ("FLOAT", 1.0), "ss": ("FLOAT", 0.0), "puv": ("FLOAT_VECTOR", (0.0, 0.0, 0.0))}


def _n(v):
    v = np.asarray(v, np.float64)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


# --------------------------------------------------------------------------------------
# 2D outlines
# --------------------------------------------------------------------------------------


def resample(poly, n):
    """Resamples a closed polyline to n points evenly spaced by arc length."""
    P = np.asarray(poly, np.float64)
    seg = np.roll(P, -1, axis=0) - P
    L = np.linalg.norm(seg, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(L)])
    total = cum[-1]
    t = np.arange(n) / n * total
    idx = np.clip(np.searchsorted(cum, t, side="right") - 1, 0, len(P) - 1)
    f = (t - cum[idx]) / np.maximum(L[idx], 1e-12)
    return P[idx] + seg[idx] * f[:, None]


def rrect(w, h, r, n=8, cx=0.0, cy=0.0):
    """Rounded rectangle centred at (cx, cy), CCW."""
    r = min(r, w / 2 - 1e-5, h / 2 - 1e-5)
    pts = []
    for qx, qy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + qx + r * math.cos(a), cy + qy + r * math.sin(a)))
    return np.array(pts)


def fillet(poly, r, n=6):
    """Rounds every corner of a closed polygon with radius r (clamped to the edges)."""
    P = np.asarray(poly, np.float64)
    out = []
    m = len(P)
    for i in range(m):
        a, p, c = P[i - 1], P[i], P[(i + 1) % m]
        da, dc = a - p, c - p
        la, lc = np.linalg.norm(da), np.linalg.norm(dc)
        if la < 1e-9 or lc < 1e-9:
            out.append(p)
            continue
        da, dc = da / la, dc / lc
        cosang = float(np.clip(da @ dc, -1, 1))
        ang = math.acos(cosang)
        if ang > math.radians(178):
            out.append(p)
            continue
        t = r / math.tan(ang / 2)
        t = min(t, la * 0.48, lc * 0.48)
        rr = t * math.tan(ang / 2)
        p0, p1 = p + da * t, p + dc * t
        bis = _n(da + dc)
        ctr = p + bis * math.sqrt(t * t + rr * rr)
        a0 = math.atan2(p0[1] - ctr[1], p0[0] - ctr[0])
        a1 = math.atan2(p1[1] - ctr[1], p1[0] - ctr[0])
        da_ = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(n + 1):
            aa = a0 + da_ * k / n
            out.append(ctr + rr * np.array([math.cos(aa), math.sin(aa)]))
    return np.array(out)


def poly_area(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def ccw(P):
    P = np.asarray(P, np.float64)
    return P if poly_area(P) > 0 else P[::-1].copy()


def offset_poly(P, d):
    """Insets a CCW polygon by d (positive = inward) using mitred vertex normals."""
    e = np.roll(P, -1, axis=0) - P
    en = _n(np.stack([-e[:, 1], e[:, 0]], -1))  # inward normal for CCW
    vn = en + np.roll(en, 1, axis=0)
    vn = _n(vn)
    cosh = np.clip(np.einsum("ij,ij->i", vn, en), 0.4, 1.0)
    return P + vn * (d / cosh)[:, None]


def dist_to_poly(P, O):
    """Distance from (N, 2) points to the closed polyline O."""
    A_ = O
    AB = np.roll(O, -1, axis=0) - O
    AP = P[:, None, :] - A_[None, :, :]
    t = np.clip(np.einsum("nmk,mk->nm", AP, AB) / np.maximum(np.einsum("mk,mk->m", AB, AB), 1e-14)[None, :], 0.0, 1.0)
    proj = A_[None, :, :] + t[..., None] * AB[None, :, :]
    return np.linalg.norm(P[:, None, :] - proj, axis=2).min(axis=1)


def inset_radial(O, d, c=None, iters=22):
    """Ring at distance d inside the outline, each vertex moved along its line to the centroid
    (vertices never cross, unlike a normal offset at corners tighter than d)."""
    if d <= 0:
        return O.copy()
    c = O.mean(axis=0) if c is None else np.asarray(c)
    D = c - O
    lo = np.zeros(len(O))
    hi = np.full(len(O), 0.98)
    for _ in range(iters):
        mid = (lo + hi) * 0.5
        dd = dist_to_poly(O + D * mid[:, None], O)
        below = dd < d
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    return O + D * ((lo + hi) * 0.5)[:, None]


def inradius(P):
    c = P.mean(axis=0)
    e = np.roll(P, -1, axis=0) - P
    en = _n(np.stack([-e[:, 1], e[:, 0]], -1))
    return float(np.min(np.einsum("ij,ij->i", c - P, en)))


# --------------------------------------------------------------------------------------
# Mesh assembly
# --------------------------------------------------------------------------------------


class Mesh:
    """Accumulates vertices, faces and per-vertex attributes for one part."""

    def __init__(self):
        self.v = []
        self.f = []
        self.a = {k: [] for k in ATTRS}
        self.n = 0

    def add_verts(self, P, **attrs):
        P = np.asarray(P, np.float64).reshape(-1, 3)
        base = self.n
        self.v.append(P)
        for k, (kind, dflt) in ATTRS.items():
            val = attrs.get(k)
            if val is None:
                val = np.tile(np.asarray(dflt, np.float64), (len(P), 1)) if kind == "FLOAT_VECTOR" else np.full(len(P), dflt)
            else:
                val = np.asarray(val, np.float64)
                if kind == "FLOAT_VECTOR":
                    val = np.broadcast_to(val, (len(P), 3)).copy()
                else:
                    val = np.broadcast_to(val, (len(P),)).copy()
            self.a[k].append(val)
        self.n += len(P)
        return base

    def add_faces(self, F, base=0):
        for f in F:
            self.f.append(tuple(int(i) + base for i in f))

    def merge(self, other):
        if not other.n:
            return
        base = self.n
        self.v.extend(other.v)
        for k in ATTRS:
            self.a[k].extend(other.a[k])
        self.n += other.n
        self.add_faces(other.f, base)

    def arrays(self):
        V = np.concatenate(self.v) if self.v else np.zeros((0, 3))
        A = {k: (np.concatenate(v) if v else np.zeros(0)) for k, v in self.a.items()}
        return V, self.f, A

    def transform(self, fn):
        """Applies fn(points) -> points to every vertex."""
        self.v = [fn(np.asarray(p)) for p in self.v]
        return self


def grid_faces(rows, cols, closed=True, base=0, flip=False):
    """Quads between consecutive rows of a (rows x cols) vertex grid."""
    F = []
    cc = cols if closed else cols - 1
    for r in range(rows - 1):
        for c in range(cc):
            c2 = (c + 1) % cols
            q = (base + r * cols + c, base + r * cols + c2, base + (r + 1) * cols + c2, base + (r + 1) * cols + c)
            F.append(q[::-1] if flip else q)
    return F


def fan_faces(center, ring, flip=False):
    F = []
    m = len(ring)
    for i in range(m):
        t = (ring[i], ring[(i + 1) % m], center)
        F.append(t[::-1] if flip else t)
    return F


# --------------------------------------------------------------------------------------
# Pillow: padded slab from an outline, mapped onto a surface
# --------------------------------------------------------------------------------------


def edge_profile(thick, kind="round", r_in=0.003, r_out=0.006, steps=4):
    """(inset, h) samples around the rim from the inner face edge to the outer face edge."""
    pts = []
    if kind == "round":
        r = thick / 2
        for i in range(2 * steps + 1):
            a = -math.pi / 2 + math.pi * i / (2 * steps)
            pts.append((r * (1 - math.cos(a)), r + r * math.sin(a)))
    else:
        r_in = min(r_in, thick * 0.45)
        r_out = min(r_out, thick * 0.55)
        for i in range(steps + 1):
            a = math.radians(270 - 90 * i / steps)
            pts.append((r_in + r_in * math.cos(a), r_in + r_in * math.sin(a)))
        for i in range(steps + 1):
            a = math.radians(180 - 90 * i / steps)
            pts.append((r_out + r_out * math.cos(a), thick - r_out + r_out * math.sin(a)))
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > 1e-7 or abs(p[1] - out[-1][1]) > 1e-7:
            out.append(p)
    return out


def pillow(outline, thick, mapf, n=64, kind="round", r_in=0.003, r_out=0.006, puff=0.0, inner=True, steps=4,
           face_insets=(0.0, 0.0025, 0.0055, 0.010, 0.018), scales=(0.72, 0.45, 0.2), puv=None, inner_scale=(0.55,),
           bulge=None):
    """Builds a padded slab.  outline: CCW (u, v) polygon (resampled to n points).
    mapf(U, V, H) -> (P, N) maps arrays of local coordinates onto the base surface.
    puv: callable (U, V) -> (N,3) pattern coordinates, or None.
    bulge: optional callable (U, V) -> extra outer height (e.g. webbing between bar tacks).
    Returns a Mesh."""
    O = resample(ccw(outline), n)
    ir = inradius(O)
    prof = edge_profile(thick, kind, r_in, r_out, steps)
    face0 = prof[-1][0]  # inset where the outer face starts
    in0 = prof[0][0]
    seg = np.linalg.norm(np.roll(O, -1, axis=0) - O, axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)[:-1]])
    c = O.mean(axis=0)
    rings = []  # (UV ring or None for centre, h, sd, is_center)

    def add_ring(UV, h, sd):
        rings.append((UV, h, sd))

    # inner face (centre -> edge), then rim, then outer face (edge -> centre)
    max_in = ir * 0.8
    if inner:
        add_ring(None, 0.0, 1.0)
        last_inner = inset_radial(O, min(in0 + 0.01, max_in)) if in0 + 0.01 < max_in else inset_radial(O, max_in * 0.6)
        for s in inner_scale:
            add_ring(c + (last_inner - c) * s, 0.0, 1.0)
        if in0 + 0.01 < max_in:
            add_ring(last_inner, 0.0, 0.01)
    for (ins, h) in prof:
        add_ring(inset_radial(O, ins), h, 0.0)
    fin = [d for d in face_insets if face0 + d < max_in]
    last = inset_radial(O, face0)
    for d in fin[1:]:
        last = inset_radial(O, face0 + d)
        add_ring(last, thick, d)
    lastd = fin[-1] if fin else 0.0
    rc = float(np.mean(np.linalg.norm(last - c, axis=1)))
    for s in scales:
        add_ring(c + (last - c) * s, thick, lastd + (1 - s) * rc)
    add_ring(None, thick, 1.0)
    M = Mesh()
    idx_rings = []
    for UV, h, sd in rings:
        if UV is None:
            UV = c[None, :]
        U, Vv = UV[:, 0], UV[:, 1]
        H = np.full(len(U), h)
        if h > 0 and (puff or bulge is not None):
            if sd > 0:
                dfrac = np.clip(np.full(len(U), sd) / max(ir * 0.55, 1e-4), 0, 1)
                H = H + puff * dfrac * dfrac * (3 - 2 * dfrac)
            if bulge is not None and h >= thick - 1e-9:
                H = H + bulge(U, Vv)
        P, _ = mapf(U, Vv, H)
        sd_arr = np.full(len(U), sd if UV.shape[0] > 1 else 1.0)
        ss_arr = arc if UV.shape[0] > 1 else np.zeros(1)
        pv = puv(U, Vv) if puv is not None else None
        b = M.add_verts(P, sd=sd_arr, ss=ss_arr, puv=pv)
        idx_rings.append((b, len(U)))
    # faces
    for (b0, n0), (b1, n1) in zip(idx_rings[:-1], idx_rings[1:]):
        if n0 == 1 and n1 == 1:
            continue
        if n0 == 1:
            M.add_faces(fan_faces(b0, [b1 + i for i in range(n1)], flip=True))
        elif n1 == 1:
            M.add_faces(fan_faces(b1, [b0 + i for i in range(n0)]))
        else:
            for i in range(n0):
                j = (i + 1) % n0
                M.f.append((b0 + i, b0 + j, b1 + j, b1 + i))
    # orientation: the outer centre fan must face along the surface normal
    V, F, _ = M.arrays()
    _, Nc = mapf(c[None, 0], c[None, 1], np.array([thick]))
    tri = F[-1]
    fn = np.cross(V[tri[1]] - V[tri[0]], V[tri[2]] - V[tri[0]])
    if fn @ Nc[0] < 0:
        M.f = [f[::-1] for f in M.f]
    return M


# --------------------------------------------------------------------------------------
# Sweeps
# --------------------------------------------------------------------------------------


def frames(path, ups, closed=False):
    P = np.asarray(path, np.float64)
    if closed:
        T = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    else:
        T = np.gradient(P, axis=0)
    T = _n(T)
    U = np.asarray(ups, np.float64)
    U = np.broadcast_to(U, P.shape)
    B = _n(np.cross(T, U))
    N = _n(np.cross(B, T))
    return T, B, N


def arclen(P, closed=False):
    P = np.asarray(P)
    d = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(d)])
    if closed:
        return s, s[-1] + np.linalg.norm(P[0] - P[-1])
    return s, s[-1]


def sweep(path, ups, profile, closed=False, caps=True, scales=None, half_w=None, puv_fn=None):
    """Sweeps a closed 2D profile [(a, b)] (a across = binormal, b = up) along path.
    half_w: half width for sd (stitch rows run along both strap edges).
    puv_fn(s, a) -> (u, v, w) optional pattern coordinates."""
    P = np.asarray(path, np.float64)
    T, B, N = frames(P, ups, closed)
    prof = np.asarray(profile, np.float64)
    k = len(prof)
    s, _ = arclen(P, closed)
    M = Mesh()
    rows = []
    for i in range(len(P)):
        sc = 1.0 if scales is None else scales[i]
        pts = P[i] + np.outer(prof[:, 0] * sc, B[i]) + np.outer(prof[:, 1] * sc, N[i])
        sd = (half_w - np.abs(prof[:, 0])) if half_w else np.full(k, 1.0)
        pv = None
        if puv_fn is not None:
            pv = np.array([puv_fn(s[i], a) for a in prof[:, 0]])
        rows.append(M.add_verts(pts, sd=sd, ss=np.full(k, s[i]), puv=pv))
    nr = len(rows)
    rr = nr if closed else nr - 1
    for r in range(rr):
        b0, b1 = rows[r], rows[(r + 1) % nr]
        for j in range(k):
            j2 = (j + 1) % k
            M.f.append((b0 + j, b0 + j2, b1 + j2, b1 + j))
    if caps and not closed:
        c0 = M.add_verts(P[0][None, :], sd=0.0, ss=0.0)
        c1 = M.add_verts(P[-1][None, :], sd=0.0, ss=float(s[-1]))
        M.add_faces(fan_faces(c0, [rows[0] + j for j in range(k)], flip=True))
        M.add_faces(fan_faces(c1, [rows[-1] + j for j in range(k)]))
    # orientation: (B, N, T) is left-handed, so a CCW profile in (a, b) builds inward faces
    if poly_area(prof) > 0:
        M.f = [f[::-1] for f in M.f]
    return M


def rrect_profile(w, t, r, n=3):
    """Rounded rectangle profile centred on (0, t/2) so it sits on the surface (b >= 0)."""
    P = rrect(w, t, r, n)
    P[:, 1] += t / 2
    return P


def smooth_path(P, iters=3, closed=False, lam=0.5):
    P = np.array(P, np.float64)
    for _ in range(iters):
        if closed:
            Q = 0.5 * (np.roll(P, 1, axis=0) + np.roll(P, -1, axis=0))
            P = P + lam * (Q - P)
        else:
            Q = P.copy()
            Q[1:-1] = 0.5 * (P[:-2] + P[2:])
            P = P + lam * (Q - P)
    return P


def resample_path(P, n, closed=False):
    P = np.asarray(P, np.float64)
    if closed:
        P = np.vstack([P, P[:1]])
    s, total = arclen(P)
    t = np.linspace(0, total, n + (0 if closed else 0), endpoint=not closed)
    out = np.stack([np.interp(t, s, P[:, i]) for i in range(3)], -1)
    return out


# --------------------------------------------------------------------------------------
# Solids
# --------------------------------------------------------------------------------------


def lathe(prof, n=24, axis=(0, 0, 1), center=(0, 0, 0), ref=None, sd=1.0):
    """Revolves [(r, z)] around axis through center; r == 0 ends close to a pole."""
    ax = _n(axis)
    ref = np.array([1.0, 0, 0]) if ref is None else _n(ref)
    if abs(ref @ ax) > 0.9:
        ref = np.array([0, 1.0, 0])
    e1 = _n(ref - ax * (ref @ ax))
    e2 = np.cross(ax, e1)
    C = np.asarray(center, np.float64)
    M = Mesh()
    rows = []
    for (r, z) in prof:
        if r < 1e-7:
            rows.append((M.add_verts((C + ax * z)[None, :], sd=sd), 1))
        else:
            a = np.arange(n) / n * 2 * math.pi
            pts = C + ax * z + np.outer(np.cos(a) * r, e1) + np.outer(np.sin(a) * r, e2)
            rows.append((M.add_verts(pts, sd=sd), n))
    for (b0, n0), (b1, n1) in zip(rows[:-1], rows[1:]):
        if n0 == 1 and n1 == 1:
            continue
        if n0 == 1:
            M.add_faces(fan_faces(b0, [b1 + i for i in range(n1)], flip=True))
        elif n1 == 1:
            M.add_faces(fan_faces(b1, [b0 + i for i in range(n0)]))
        else:
            for i in range(n0):
                j = (i + 1) % n0
                M.f.append((b0 + i, b0 + j, b1 + j, b1 + i))
    return M


def rbox(center, size, r, frame=None, n=2):
    """Rounded box (bmesh cube + bevel) in a local frame (columns x, y, z)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=tuple(size), verts=bm.verts)
    if r > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=min(r, min(size) * 0.45), segments=n, profile=0.5, affect="EDGES", clamp_overlap=True)
    me = bpy.data.meshes.new("_rb")
    bm.to_mesh(me)
    bm.free()
    V = np.array([v.co[:] for v in me.vertices])
    F = [tuple(p.vertices) for p in me.polygons]
    bpy.data.meshes.remove(me)
    Rm = np.eye(3) if frame is None else np.asarray(frame)
    V = V @ Rm.T + np.asarray(center)
    M = Mesh()
    M.add_verts(V)
    M.add_faces(F)
    return M


def cyl(p0, p1, r, n=16, r1=None, cap=True):
    p0, p1 = np.asarray(p0, np.float64), np.asarray(p1, np.float64)
    L = float(np.linalg.norm(p1 - p0))
    r1 = r if r1 is None else r1
    prof = ([(0.0, 0.0)] if cap else []) + [(r, 0.0), (r1, L)] + ([(0.0, L)] if cap else [])
    return lathe(prof, n, p1 - p0, p0)


# --------------------------------------------------------------------------------------
# Blender objects
# --------------------------------------------------------------------------------------


def to_object(name, M, zone, coll, smooth_angle=None):
    """Creates a mesh object with the zone's placeholder material and the bake attributes."""
    V, F, A = M.arrays()
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in V], [], F)
    me.validate(clean_customdata=False)
    for k, (kind, _d) in ATTRS.items():
        at = me.attributes.new(k, kind, "POINT")
        vals = A[k]
        if kind == "FLOAT_VECTOR":
            at.data.foreach_set("vector", np.asarray(vals, np.float32).reshape(-1, 3).ravel())
        else:
            at.data.foreach_set("value", np.asarray(vals, np.float32).ravel())
    mat = bpy.data.materials.get("Z_" + zone) or bpy.data.materials.new("Z_" + zone)
    me.materials.append(mat)
    me.shade_smooth()
    if smooth_angle is not None:
        me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def join(objs, name):
    """Joins objects into one (attributes and material slots merge by name)."""
    objs = [o for o in objs if o is not None]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    ob.select_set(False)
    return ob


def weld(ob, dist=1e-6):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bm.to_mesh(ob.data)
    bm.free()


def tri_count(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def mirror_mesh(M, axis=1):
    """Mirrored copy (flips winding)."""
    R = Mesh()
    V, F, A = M.arrays()
    V = V.copy()
    V[:, axis] *= -1
    R.add_verts(V, sd=A["sd"], ss=A["ss"], puv=A["puv"])
    R.add_faces([f[::-1] for f in F])
    return R


def strip(mapf, u0, u1, v, w, thick, nu, h0=0.0, r=0.0008, bulge=None, ss0=0.0):
    """A flat strap lying along u on a surface (MOLLE webbing, tapes): grid of rows along u with a
    rounded-rectangle cross-section in (v, h); bulge(u) lifts the top between bar tacks."""
    prof = rrect_profile(w, thick, r, 1)
    k = len(prof)
    us = np.linspace(u0, u1, nu + 1)
    M = Mesh()
    rows = []
    for u in us:
        dv = prof[:, 0]
        hh = prof[:, 1].copy()
        if bulge is not None:
            hh = hh + (hh > thick * 0.5) * bulge(u)
        P, _ = mapf(np.full(k, u), v + dv, h0 + hh)
        rows.append(M.add_verts(P, sd=np.full(k, 1.0), ss=np.full(k, ss0 + u - u0), puv=np.stack([np.full(k, u - u0), dv, np.zeros(k)], -1)))
    for a, b in zip(rows[:-1], rows[1:]):
        for j in range(k):
            j2 = (j + 1) % k
            M.f.append((a + j, a + j2, b + j2, b + j))
    c0 = M.add_verts(mapf(np.array([u0]), np.array([v]), np.array([h0 + thick * 0.5]))[0])
    c1 = M.add_verts(mapf(np.array([u1]), np.array([v]), np.array([h0 + thick * 0.5]))[0])
    M.add_faces(fan_faces(c0, [rows[0] + j for j in range(k)], flip=True))
    M.add_faces(fan_faces(c1, [rows[-1] + j for j in range(k)]))
    # orientation check against the surface normal at the middle of the top
    V, F, _ = M.arrays()
    mid = rows[len(rows) // 2]
    jt = int(np.argmax(prof[:, 1] - np.abs(prof[:, 0]) * 1e-3))
    fidx = (len(rows) // 2) * k + jt
    f = F[min(fidx, len(F) - 1)]
    fn = np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])
    _, Nn = mapf(np.array([us[len(us) // 2]]), np.array([v]), np.array([h0]))
    if fn @ Nn[0] < 0:
        M.f = [ff[::-1] for ff in M.f]
    del mid
    return M
