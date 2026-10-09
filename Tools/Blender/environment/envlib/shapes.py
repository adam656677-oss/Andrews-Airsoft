"""Reusable organic / sheet shapes (bmesh)."""
import math

import bmesh
import numpy as np
from mathutils import Vector

from .geo import fbm3


def cube_sphere_bm(cuts):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    for v in bm.verts:
        v.co = v.co.normalized()
    return bm


def sandbag_bm(seed, L=0.56, W=0.33, T=0.13, cuts=13, tie=True, slump=0.0):
    """Filled burlap sandbag lying along X, bottom at z=0, centred in x/y.
    The tied end points to +X."""
    rng = np.random.default_rng(seed)
    bm = cube_sphere_bm(cuts)
    P = np.array([v.co[:] for v in bm.verts])
    e1, e2 = 0.42, 0.7
    sx = np.sign(P[:, 0]) * np.abs(P[:, 0]) ** e1
    sy = np.sign(P[:, 1]) * np.abs(P[:, 1]) ** e1
    sz = np.sign(P[:, 2]) * np.abs(P[:, 2]) ** e2
    x = sx * L / 2
    y = sy * W / 2
    z = sz * T / 2
    # pillow: thinner towards the ends/sides
    edge = np.clip(1 - np.maximum(np.abs(sx), np.abs(sy)) ** 6, 0, 1)
    z = z * (0.55 + 0.45 * edge ** 0.5)
    # tied end
    if tie:
        tx = (x - (L / 2 - 0.10)) / 0.10
        neck = np.clip(tx, 0, 1)
        k = 1 - 0.62 * np.sin(np.clip(neck, 0, 1) * math.pi / 2) ** 1.5
        y = y * k
        z = z * k
        flap = x > L / 2 - 0.035
        z = np.where(flap, z * 0.3, z)
        x = np.where(flap, x + 0.02, x)
        y = np.where(flap, y * 1.15, y)
        # radial folds near the tie
        ang = np.arctan2(z, y)
        z = z + np.sin(ang * 9 + seed) * 0.004 * neck * np.cos(ang)
        y = y + np.sin(ang * 9 + seed) * 0.004 * neck * np.sin(ang)
    # flat bottom, slumped top
    bot = z < 0
    z = np.where(bot, np.maximum(z, -T / 2 * 0.82) * 1.0, z * (0.9 + 0.2 * rng.random()))
    # seam ridge along the long sides
    side = np.clip((np.abs(y) / (W / 2) - 0.75) / 0.25, 0, 1)
    ridge = np.exp(-(z / 0.006) ** 2) * side * 0.006
    y = y + np.sign(y) * ridge
    Q = np.stack([x, y, z], 1)
    # wrinkles / lumps
    n1 = fbm3(Q * 9.0 + seed * 3.1, 1.0, 4, 0.5, seed)
    n2 = fbm3(Q * 30.0 + seed * 1.7, 1.0, 3, 0.5, seed + 9)
    nrm = Q / np.maximum(np.linalg.norm(Q * [1 / L, 1 / W, 1 / T], axis=1, keepdims=True), 1e-6)
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-6)
    Q = Q + nrm * (n1 * 0.012 + n2 * 0.003)[:, None]
    # random bend (slump over courses below) and squash
    bend = (rng.random() - 0.5) * 0.06 + slump
    Q[:, 2] -= bend * (1 - (Q[:, 0] / (L / 2)) ** 2)
    Q[:, 2] -= Q[:, 2].min()
    for v, q in zip(bm.verts, Q):
        v.co = Vector(q)
    bm.normal_update()
    return bm


def log_bm(length, r, seed, n=20, segs=None, taper=0.08):
    """Debarked-ish log along X centred at origin, radius noise + knots."""
    segs = segs or max(6, int(length / 0.12))
    bm = bmesh.new()
    rng = np.random.default_rng(seed)
    rings = []
    for i in range(segs + 1):
        t = i / segs
        x = (t - 0.5) * length
        ring = []
        for j in range(n):
            a = j / n * math.tau
            ring.append((x, a))
        rings.append(ring)
    X = np.array([[p[0] for p in ring] for ring in rings])
    A = np.array([[p[1] for p in ring] for ring in rings])
    P = np.stack([X, np.cos(A), np.sin(A)], -1).reshape(-1, 3)
    rad = r * (1 + taper * (0.5 - (X.ravel() / length + 0.5)))
    rad = rad * (1 + 0.06 * fbm3(np.stack([X.ravel() * 2.0, P[:, 1] * 1.5, P[:, 2] * 1.5], 1), 1.0, 3, 0.5, seed))
    rad = rad * (1 + 0.035 * np.sin(X.ravel() * 3.0 + seed))
    V = np.stack([X.ravel(), P[:, 1] * rad, P[:, 2] * rad], 1)
    vs = [bm.verts.new(v) for v in V]
    for i in range(segs):
        for j in range(n):
            a = vs[i * n + j]
            b = vs[i * n + (j + 1) % n]
            c = vs[(i + 1) * n + (j + 1) % n]
            d = vs[(i + 1) * n + j]
            bm.faces.new((a, b, c, d))
    # end caps (slightly sawn, with small chamfer ring)
    for i, sgn in ((0, -1), (segs, 1)):
        ring = [vs[i * n + j] for j in range(n)]
        if sgn < 0:
            ring = ring[::-1]
        f = bm.faces.new(ring)
        res = bmesh.ops.inset_region(bm, faces=[f], thickness=r * 0.08, depth=-r * 0.03)
    bm.normal_update()
    return bm


def corrugated_bm(length, width, pitch=0.076, depth=0.018, thick=0.0012, nl=None, profile='sine'):
    """Corrugated sheet: ribs run along X (length), waves across Y."""
    bm = bmesh.new()
    nw = int(width / pitch * 10)
    nl = nl or max(2, int(length / 0.25))
    ys = np.linspace(-width / 2, width / 2, nw + 1)
    if profile == 'sine':
        zs = depth / 2 * np.sin(ys / pitch * math.tau)
    else:  # trapezoid (container)
        ph = (ys / pitch) % 1.0
        zs = depth * np.clip(np.abs(ph - 0.5) * 4 - 0.5, -0.5, 0.5)
    xs = np.linspace(-length / 2, length / 2, nl + 1)
    top = [[bm.verts.new((x, y, z + thick / 2)) for y, z in zip(ys, zs)] for x in xs]
    bot = [[bm.verts.new((x, y, z - thick / 2)) for y, z in zip(ys, zs)] for x in xs]
    for i in range(nl):
        for j in range(nw):
            bm.faces.new((top[i][j], top[i][j + 1], top[i + 1][j + 1], top[i + 1][j]))
            bm.faces.new((bot[i][j], bot[i + 1][j], bot[i + 1][j + 1], bot[i][j + 1]))
    for i in range(nl):
        for j in (0, nw):
            a, b, c, d = top[i][j], top[i + 1][j], bot[i + 1][j], bot[i][j]
            bm.faces.new((a, b, c, d) if j == nw else (d, c, b, a))
    for i in (0, nl):
        for j in range(nw):
            a, b, c, d = top[i][j], top[i][j + 1], bot[i][j + 1], bot[i][j]
            bm.faces.new((a, b, c, d) if i == 0 else (d, c, b, a))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def rect_sub(rects, hole):
    """Subtract axis-aligned rectangle hole=(y0,z0,y1,z1) from list of rects."""
    out = []
    hy0, hz0, hy1, hz1 = hole
    for (y0, z0, y1, z1) in rects:
        if hy1 <= y0 or hy0 >= y1 or hz1 <= z0 or hz0 >= z1:
            out.append((y0, z0, y1, z1))
            continue
        if hy0 > y0:
            out.append((y0, z0, hy0, z1))
        if hy1 < y1:
            out.append((hy1, z0, y1, z1))
        cy0, cy1 = max(y0, hy0), min(y1, hy1)
        if hz0 > z0:
            out.append((cy0, z0, cy1, hz0))
        if hz1 < z1:
            out.append((cy0, hz1, cy1, z1))
    return [r for r in out if (r[2] - r[0]) > 0.01 and (r[3] - r[1]) > 0.01]
