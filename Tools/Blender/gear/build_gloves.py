"""
First-person tactical gloves (+ combat-shirt sleeves) for Andrew's Airsoft.

    python Tools/Blender/gear/build_gloves.py                         # all pieces, bake, export, render
    python Tools/Blender/gear/build_gloves.py -- RightGrip --no-bake  # one piece, geometry only
    flags: --res 2048|1024 (texture size, default 2048), --h <m> (voxel size, default 0.001),
           --no-bake, --no-render, --preview (coarse 2 mm mesh, quick look renders),
           --renders-only (re-render from the exported FBX + textures)

Outputs (see Tools/Blender/CONVENTIONS.md):
    SourceAssets/Gear/Gloves/SM_Gloves_<Piece>.fbx + T_Gloves_<Piece>_{BC,N,ORM}.png
    Content/Airsoft/Data/Gear.json   (Assets.Gloves)
    Docs/Renders/Gear/Gloves_<Piece>.png, Gloves_FirstPerson.png, Gloves_FirstPerson_Pistol.png

Pieces and their origins (Blender metres, +X barrel, +Z up, right = -Y):
    RightGrip   gun space: origin = centre of the pistol grip.  Attach at the gun origin.
    LeftPistol  gun space, same origin as RightGrip (wraps over its fingers).  Attach at the gun origin.
    LeftSupport support space: origin = the gun's LeftHand point (bottom centre of the handguard,
                where the palm meets it).  Attach at Points.LeftHand.

How it works: the hand is a signed distance field (Tools/Blender/gear/handkit.py): an
anatomical skeleton wrapped in rounded cones/ellipsoids with smooth unions, posed per
piece.  The palm is placed with a weighted rigid fit of anatomical landmarks to target
points on the grip, the fingers close onto the real G17/M4 meshes (collision-driven grasp),
the trigger finger is solved to joint targets, and palm flesh that would sink into the gun
is pressed out onto its surface.  Glove details (knuckle shell, finger pads, palm patch,
velcro strap and tab) are raised offsets of the hand surface.  The field is meshed with
surface nets at 1 mm and projected onto the iso-surface; the sleeve is a parametric tube
with compression and drape folds, a rolled cuff and a closed end.  Zone fields and seam
distances are stored as vertex attributes and drive a procedural bake (leather grain,
silicone grip dots, stretch weave, TPR stipple, ripstop, double-row stitching, grime).
"""

import collections
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "common"))

import bpy  # noqa: E402,I001
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.kdtree import KDTree  # noqa: E402

import bakekit as bk  # noqa: E402
import gearlib as gl  # noqa: E402
import handkit as hk  # noqa: E402
import studio  # noqa: E402
from handkit import normalize, rot_axis  # noqa: E402

ASSET = "Gloves"
OUT_DIR = os.path.join(gl.SOURCE_DIR, "Gear", ASSET)
RENDER_DIR = os.path.join(gl.RENDER_DIR, "Gear")
PIECES = ["RightGrip", "LeftSupport", "LeftPistol"]
TRI_BUDGET = 150000
CM = 0.01

# --------------------------------------------------------------------------------------
# Pose configuration (all target points in cm, in the piece's authoring space)
# --------------------------------------------------------------------------------------

# anatomical landmarks (hand-local mm, right-hand convention)
LM_LOCAL = {
    "index": (91, 28, -1),
    "middle": (94, 9, 1),
    "ring": (88, -10, -1),
    "little": (78, -27, -5),
    "cmc": (24, 21, -11),
    "hypo": (38, -24, -9),
    "wrist": (0, 0, 0),
}
LM_WEIGHT = {"index": 2.0, "middle": 2.0, "ring": 2.0, "little": 1.5, "cmc": 1.5, "hypo": 1.0, "wrist": 1.0}

CONFIG = {
    "RightGrip": dict(
        left=False,
        space="gun",
        elbow=(-30.0, -9.0, -22.0),
        targets={
            "index": (1.4, -2.65, 1.3),
            "middle": (1.6, -2.75, -0.55),
            "ring": (1.3, -2.6, -2.45),
            "little": (0.8, -2.35, -4.3),
            "cmc": (-3.2, 1.3, 0.2),
            "hypo": (-3.6, -1.9, -3.8),
            "wrist": (-6.6, -0.9, -3.6),
        },
        thumb=[(-0.8, 3.0, 1.2), (1.8, 2.55, 2.1), (3.6, 2.35, 2.4)],
        trigger=[(4.9, -2.45, 2.2), (6.6, -0.75, 2.25), (5.95, 0.15, 2.25)],
        grasp=("middle", "ring", "little"),
        forearm_len=8.0,
    ),
    "LeftPistol": dict(
        left=True,
        space="gun",
        elbow=(-30.0, 16.0, -22.0),
        targets={
            "index": (3.0, 4.5, -1.0),
            "middle": (3.2, 4.6, -2.9),
            "ring": (2.8, 4.45, -4.8),
            "little": (2.1, 4.1, -6.5),
            "cmc": (-2.6, 3.6, -2.8),
            "hypo": (-1.0, 4.9, -6.4),
            "wrist": (-5.6, 5.4, -7.0),
        },
        thumb=[(0.3, 3.9, -0.6), (2.8, 3.6, 0.5), (4.6, 3.2, 0.9)],
        grasp=("index", "middle", "ring", "little"),
        abd={"index": -8.0, "middle": -3.0},
        forearm_len=8.0,
    ),
    "LeftSupport": dict(
        left=True,
        space="support",
        elbow=(-34.0, 24.0, -20.0),
        frame=dict(distal=(0.28, -0.9, 0.3), dorsal=(0.0, 0.32, -0.95), anchor_local=(52, 2, -16.5), anchor=(-0.8, 0.0, -0.15)),
        thumb=[(-1.0, 3.3, 1.2), (1.6, 3.0, 3.6), (3.6, 2.6, 5.0)],
        grasp=("index", "middle", "ring", "little"),
        forearm_len=8.0,
    ),
}

# handguard stand-in for the support hand (support space): 4.5 cm wide, 5.5 cm tall
HANDGUARD = dict(c=(0.0, 0.0, 2.75), b=(30.0, 2.25, 2.75), rad=0.8)


def P(v):
    return np.asarray(v, np.float64) * CM


# --------------------------------------------------------------------------------------
# Context: obstacles (gun meshes as signed distance functions)
# --------------------------------------------------------------------------------------


class Ctx:
    def __init__(self):
        coll = bpy.data.collections.new("Obstacles")
        bpy.context.scene.collection.children.link(coll)
        self.coll = coll
        _, self.bvhP = gl.load_gun("G17", coll, materials=False)
        _, self.bvhR = gl.load_gun("M4", coll, materials=False)
        self.lh = gl.weapon_points("M4")["LeftHand"]
        _, self.bvhS = gl.load_gun("M4", coll, materials=False, offset=tuple(-self.lh))
        coll.hide_render = True
        for o in coll.objects:
            o.hide_set(True)
        self.sdfP = gl.bvh_sdf(self.bvhP)
        self.sdfR = gl.bvh_sdf(self.bvhR)
        self.sdfS = gl.bvh_sdf(self.bvhS)
        Mi = np.eye(3)
        self.hg = hk.Prim("box", "hg", c=P(HANDGUARD["c"]), M=Mi, b=P(HANDGUARD["b"]), rad=HANDGUARD["rad"] * CM)
        self.right = None  # RightGrip field (obstacle for LeftPistol)

    def grip_union(self, Pp):
        d = np.minimum(self.sdfP(Pp), self.sdfR(Pp))
        far = Pp[:, 0] > 0.05
        d[far] = np.maximum(d[far], 0.02)
        return d


# --------------------------------------------------------------------------------------
# Posing
# --------------------------------------------------------------------------------------


def fit_landmarks(h, targets):
    keys = list(LM_LOCAL)
    A = np.array([LM_LOCAL[k] for k in keys], float) * 0.001
    if h.left:
        A[:, 1] *= -1.0
    B = np.array([targets[k] for k in keys], float) * CM
    w = np.array([LM_WEIGHT[k] for k in keys], float)[:, None]
    ca = (A * w).sum(0) / w.sum()
    cb = (B * w).sum(0) / w.sum()
    U, _, Vt = np.linalg.svd(((A - ca) * w).T @ (B - cb))
    R = Vt.T @ np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))]) @ U.T
    h.R = R
    h.t = cb - R @ ca
    res = {k: float(np.linalg.norm(h.L(LM_LOCAL[k]) - targets[k] * np.array(CM))) * 100 for k in keys}
    return res


def thumb_to_targets(h, targets):
    tw, _ = h.thumb_chain()
    dirs = []
    cur = tw[0]
    for tgt, ln in zip(targets, hk.THUMB["lens"]):
        d = normalize(P(tgt) - cur)
        dirs.append(d)
        cur = cur + d * ln * h.s
    h.thumb_dirs = dirs


def finger_to_targets(h, name, targets, x0=(15.0, 60.0, 30.0, 10.0)):
    """Coordinate descent on (MCP, PIP, DIP, abduction) to joint/pad targets."""
    f = hk.FINGERS[name]
    TG = [P(t) for t in targets]

    def err(ang):
        W, D = h.finger_chain(name, ang)
        pad = W[2] + (W[3] - W[2]) * 0.55 - D[2] * f["radii"][4] * h.s * 0.95
        return np.sum((W[1] - TG[0]) ** 2) + np.sum((W[2] - TG[1]) ** 2) + 1.5 * np.sum((pad - TG[2]) ** 2)

    x = np.array(x0, float)
    stepv = np.full(4, 8.0)
    e0 = err(x)
    for _ in range(600):
        improved = False
        for j in range(4):
            for sgn in (1, -1):
                y = x.copy()
                y[j] += sgn * stepv[j]
                ey = err(y)
                if ey < e0:
                    x, e0, improved = y, ey, True
        if not improved:
            stepv *= 0.6
            if stepv.max() < 0.05:
                break
    return tuple(x), math.sqrt(e0) * 1000


def pose_hand(piece, ctx):
    cfg = CONFIG[piece]
    h = hk.Hand(left=cfg["left"])
    if "frame" in cfg:
        fr = cfg["frame"]
        h.R = hk.frame_from(fr["distal"], fr["dorsal"])
        h.t = np.zeros(3)
        h.t = P(fr["anchor"]) - h.L(fr["anchor_local"])
        res = {}
    else:
        res = fit_landmarks(h, cfg["targets"])
    h.forearm_dir = normalize(P(cfg["elbow"]) - h.t)
    h.forearm_len = cfg["forearm_len"] * CM
    h.cup = 6.0
    thumb_to_targets(h, cfg["thumb"])
    if piece == "RightGrip":
        obst = ctx.grip_union
    elif piece == "LeftPistol":
        rf = ctx.right

        def obst(Pp):
            return np.minimum(ctx.sdfP(Pp), rf.eval(Pp))
    else:

        def obst(Pp):
            return np.minimum(ctx.hg.eval(Pp), ctx.sdfS(Pp))

    for n in cfg["grasp"]:
        ang = None
        abd = cfg.get("abd", {}).get(n, 0.0)
        for st in ((25, 30, 15), (12, 15, 5), (0, 0, 0)):
            ang = hk.grasp(h, n, obst, start=st, abd=abd)
            if ang != st:
                break
        h.pose[n] = (*ang, abd)
    if "trigger" in cfg:
        ang, err = finger_to_targets(h, "index", cfg["trigger"])
        h.pose["index"] = ang
    log(f"  {piece}: landmark residuals (cm) " + ", ".join(f"{k}={v:.2f}" for k, v in res.items()))
    log(f"  {piece}: wrist {np.round(h.t * 100, 2).tolist()} MCPs " + ", ".join(f"{n}={np.round(h.L(h.mcp_local(n)) * 100, 1).tolist()}" for n in hk.FINGERS) + f" CMC {np.round(h.thumb_chain()[0][0] * 100, 1).tolist()}")
    log(f"  {piece}: pose " + ", ".join(f"{k}=({', '.join(f'{a:.0f}' for a in v)})" for k, v in h.pose.items()))
    return h


# --------------------------------------------------------------------------------------
# Glove mesh
# --------------------------------------------------------------------------------------


def glove_field(h):
    F = hk.Field()
    h.build(F)
    hk.add_glove_features(h, F)
    return F


def triangulate_quads(v, q):
    d02 = np.linalg.norm(v[q[:, 0]] - v[q[:, 2]], axis=1)
    d13 = np.linalg.norm(v[q[:, 1]] - v[q[:, 3]], axis=1)
    a = d02 <= d13
    t1 = np.where(a[:, None], q[:, [0, 1, 2]], q[:, [0, 1, 3]])
    t2 = np.where(a[:, None], q[:, [0, 2, 3]], q[:, [1, 2, 3]])
    return np.concatenate([t1, t2])


def neighbours(nv, tris):
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    order = np.argsort(e[:, 0], kind="stable")
    e = e[order]
    starts = np.searchsorted(e[:, 0], np.arange(nv + 1))
    return e[:, 1], starts


def laplacian(vals, nbr, starts, iters=3, lam=0.5, mask=None):
    vals = vals.copy()
    cnt = np.maximum(np.diff(starts), 1)
    idx = np.repeat(np.arange(len(cnt)), np.diff(starts))
    for _ in range(iters):
        acc = np.zeros_like(vals)
        np.add.at(acc, idx, vals[nbr])
        avg = acc / (cnt[:, None] if vals.ndim == 2 else cnt)
        new = vals + lam * (avg - vals)
        if mask is not None:
            new[~mask] = vals[~mask]
        vals = new
    return vals


def carve(v, sdf_bvh_pairs, fields, region=None, clearance=0.0004):
    """Presses vertices that sink into an obstacle out onto its surface."""
    moved = np.zeros(len(v), bool)
    for bvh, sdf in sdf_bvh_pairs:
        sel = np.arange(len(v)) if region is None else np.nonzero(region(v))[0]
        d = sdf(v[sel])
        for i, di in zip(sel[d < clearance], d[d < clearance]):
            loc, nrm, _, dist = bvh.find_nearest(Vector(v[i]))
            if loc is None:
                continue
            vi = Vector(v[i])
            out = (loc - vi) if di < 0 else (vi - loc)
            if out.length < 1e-9:
                out = nrm
            v[i] = np.array(loc + out.normalized() * clearance)
            moved[i] = True
    for f in fields:
        for _ in range(3):
            d = f.eval(v)
            sel = d < clearance
            if not sel.any():
                break
            g = f.gradient(v[sel])
            g /= np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)
            v[sel] = v[sel] - g * (d[sel] - clearance)[:, None]
            moved |= np.isin(np.arange(len(v)), np.nonzero(sel)[0])
    return v, moved


def zone_values(h, F, v):
    """Per-vertex zone fields: feature masks, dorsal-ness, cuff."""
    d, b, parts, feats = F.eval(v, return_info=True)
    out = {}
    for tag in ("shell", "pad", "patch", "strap", "tab"):
        m = np.zeros(len(v))
        for f, fd in zip(F.features, feats):
            if f.tag == tag:
                m = np.maximum(m, np.clip((b - fd) / 0.0007, 0, 1))
        out[tag] = m
    parts = np.stack(parts)
    dom = np.argmin(parts, axis=0)
    dors = np.zeros(len(v))
    prims = [p for p, _ in F.prims]
    for j, prim in enumerate(prims):
        sel = dom == j
        if not sel.any() or prim.dorsal is None:
            continue
        q = v[sel]
        if prim.kind == "cone":
            rad = q - prim.axis_point(q)
            rad /= np.maximum(np.linalg.norm(rad, axis=1, keepdims=True), 1e-9)
            dv = rad @ prim.dorsal
            if prim.tag.endswith("_dist"):
                # the palm leather wraps over the fingertip (reinforced tips)
                a, b2 = np.asarray(prim.kw["a"]), np.asarray(prim.kw["b"])
                tt = ((q - a) @ (b2 - a)) / max((b2 - a) @ (b2 - a), 1e-12)
                dv = dv - 2.2 * np.clip((tt - 0.5) / 0.25, 0, 1)
            dors[sel] = dv
        else:
            dors[sel] = np.clip(((q - prim.kw["c"]) @ prim.dorsal) / 0.008, -1, 1)
    out["dorsal"] = dors
    w0, fd, side, up = h.landmarks["cuff_axis"]
    out["cuff"] = ((v - w0) @ fd - 0.017) / 0.002
    return out


# ----- seams: iso-lines of zone fields, chained, with arc length ----------------------


def iso_segments(v, tris, f, mask=None):
    """Marching triangles on vertex scalar f (iso 0).  Returns (points, chain arc s)."""
    fv = f[tris]
    s = fv > 0
    cross = s.any(1) & ~s.all(1)
    if mask is not None:
        cross &= mask[tris].all(1)
    T = tris[cross]
    fT = fv[cross]
    segs = []
    keypos = {}
    for t, ft in zip(T, fT):
        pts = []
        for a, bb in ((0, 1), (1, 2), (2, 0)):
            if (ft[a] > 0) != (ft[bb] > 0):
                ia, ib = int(t[a]), int(t[bb])
                key = (min(ia, ib), max(ia, ib))
                if key not in keypos:
                    fa, fb = f[ia], f[ib]
                    tt = fa / (fa - fb)
                    keypos[key] = v[ia] + (v[ib] - v[ia]) * tt
                pts.append(key)
        if len(pts) == 2:
            segs.append(pts)
    adj = collections.defaultdict(list)
    for a, bb in segs:
        adj[a].append(bb)
        adj[bb].append(a)
    seen = set()
    out_p, out_s = [], []
    base = 0.0
    for start in list(adj):
        if start in seen:
            continue
        # walk to one end first
        cur, prev = start, None
        for _ in range(len(adj) + 1):
            nxt = [n for n in adj[cur] if n != prev]
            if not nxt or nxt[0] == start:
                break
            prev, cur = cur, nxt[0]
        # now walk the chain from that end
        s_acc = base
        prev = None
        p_prev = None
        while cur is not None and cur not in seen:
            seen.add(cur)
            p = keypos[cur]
            if p_prev is not None:
                s_acc += float(np.linalg.norm(p - p_prev))
            out_p.append(p)
            out_s.append(s_acc)
            p_prev = p
            nxt = [n for n in adj[cur] if n != prev and n not in seen]
            prev, cur = cur, (nxt[0] if nxt else None)
        base = s_acc + 0.0137  # offset chains so the dash phase differs
    return np.array(out_p).reshape(-1, 3), np.array(out_s)


def seam_fields(v, tris, zv):
    m_feat = np.maximum.reduce([zv["shell"], zv["pad"], zv["strap"], zv["tab"]])
    cuff = np.clip(zv["cuff"], 0, 1)
    pts, ss = [], []
    free = (m_feat < 0.3) & (cuff < 0.5) & (zv["patch"] < 0.5)
    for f, mask in (
        (zv["dorsal"] - 0.05, free),
        (zv["shell"] - 0.5, None),
        (zv["pad"] - 0.5, None),
        (zv["patch"] - 0.5, (m_feat < 0.3)),
        (zv["strap"] - 0.5, None),
        (zv["tab"] - 0.5, None),
        (zv["cuff"], (m_feat < 0.3)),
    ):
        p, s = iso_segments(v, tris, f, mask)
        if len(p):
            pts.append(p)
            ss.append(s + (ss[-1].max() + 0.02 if ss else 0.0))
    P_ = np.concatenate(pts)
    S_ = np.concatenate(ss)
    kd = KDTree(len(P_))
    for i, p in enumerate(P_):
        kd.insert(Vector(p), i)
    kd.balance()
    sd = np.empty(len(v))
    sv = np.empty(len(v))
    for i, p in enumerate(v):
        co, idx, dist = kd.find(Vector(p))
        sd[i] = dist
        sv[i] = S_[idx]
    return sd, sv


# --------------------------------------------------------------------------------------
# Sleeve: parametric tube with folds, rolled cuff and a closed end
# --------------------------------------------------------------------------------------


def sleeve_mesh(h, elbow, seed=0):
    w0, fd, side, up = h.landmarks["cuff_axis"]
    end = P(elbow)
    L_tot = float((end - w0) @ fd)
    s0 = 0.047
    rng = np.random.default_rng(seed)
    N = 112
    th = np.arange(N) / N * 2 * math.pi
    # rings: dense near the cuff (folds), coarser towards the elbow
    s_list = list(np.arange(s0, s0 + 0.11, 0.0018)) + list(np.arange(s0 + 0.11, L_tot, 0.0035))
    s_list.append(L_tot)
    S = np.array(s_list)
    ph1, ph2, ph3 = rng.uniform(0, 2 * math.pi, 3)
    roll_c, roll_w = s0 + 0.013, 0.012
    verts, uvs = [], []
    for s in S:
        t = (s - s0) / (L_tot - s0)
        a = 0.0375 + 0.0125 * t ** 0.8  # half width (along side)
        bb = 0.0285 + 0.0175 * t ** 0.8  # half thickness (along up)
        # rolled cuff band
        x = (s - roll_c) / roll_w
        roll = 0.0068 * math.sqrt(max(0.0, 1 - x * x)) ** 0.7 if abs(x) < 1 else 0.0
        # tuck towards the glove at the open edge
        tuck = max(0.0, 1 - (s - s0) / 0.0035)
        r_scale = 1.0 - 0.18 * tuck
        se = s - (roll_c + roll_w)
        comp = 0.0046 * math.exp(-max(se, 0) / 0.065) if se > 0 else 0.0
        drape = 0.0034 * min(1.0, max(se, 0) / 0.04) * (1 - 0.5 * t)
        ring = []
        for j, a_ in enumerate(th):
            e = np.array([math.cos(a_), math.sin(a_)])
            # ellipse radius
            r = 1.0 / math.sqrt((e[0] / a) ** 2 + (e[1] / bb) ** 2)
            r *= r_scale
            r += roll * (1.0 + 0.08 * math.sin(6 * a_ + 40 * s))
            if comp > 0:
                phase = 2 * math.pi * se / 0.021 + 1.5 * math.sin(a_ + ph1) + 0.7 * math.sin(2 * a_ + ph2)
                r += comp * (0.5 + 0.5 * math.sin(phase)) ** 1.6
            r += drape * math.sin(5 * a_ + ph3 + 9.0 * s) * (0.6 + 0.4 * math.sin(3 * a_ + ph1))
            # diagonal twist folds running from the cuff towards the elbow
            r += 0.0018 * min(1.0, max(se, 0) / 0.03) * (1 - t) * max(0.0, math.sin(3 * a_ - 28.0 * s + ph2)) ** 3
            sag = 0.0035 * max(0.0, -math.sin(a_)) ** 2 * min(1.0, max(se, 0) / 0.05) * (1 - t)
            r += sag
            p = w0 + fd * s + side * (e[0] * r) + up * (e[1] * r)
            ring.append(p)
            uvs.append((a_, s))
        verts.append(ring)
    V = np.array(verts).reshape(-1, 3)
    nr = len(S)
    faces = []
    for i in range(nr - 1):
        for j in range(N):
            j2 = (j + 1) % N
            faces.append((i * N + j, i * N + j2, (i + 1) * N + j2, (i + 1) * N + j))
    # closed end: slightly domed cap
    c = w0 + fd * (L_tot + 0.006)
    ci = len(V)
    V = np.vstack([V, c])
    last = (nr - 1) * N
    tris = []
    for j in range(N):
        tris.append((last + j, last + (j + 1) % N, ci))
    q = np.array(faces)
    T = np.concatenate([triangulate_quads(V, q), np.array(tris)])
    # orient outwards
    cen = V[T].mean(1)
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    axis_pt = w0 + np.outer((cen - w0) @ fd, fd)
    outv = cen - axis_pt
    outv[-N:] = fd
    flip = np.einsum("ij,ij->i", n, outv) < 0
    T[flip] = T[flip][:, ::-1]
    uv = np.array(uvs + [(0.0, L_tot + 0.006)])
    # attributes: sleeve param (u = arc around, v = along), seam distance (inseam + roll hem)
    rad_mean = 0.036
    theta_seam = -math.pi / 2 - 0.5  # inseam under the forearm, towards the body
    dth = np.angle(np.exp(1j * (uv[:, 0] - theta_seam)))
    sd_in = np.abs(dth) * rad_mean
    sd_hem = np.abs(uv[:, 1] - (roll_c + roll_w + 0.002))
    seam_d = np.minimum(sd_in, sd_hem)
    seam_s = np.where(sd_in < sd_hem, uv[:, 1], uv[:, 0] * rad_mean + 0.5)
    attrs = dict(sl_u=uv[:, 0] * rad_mean, sl_v=uv[:, 1], seam_d=seam_d, seam_s=seam_s, m_sleeve=np.ones(len(V)))
    attrs["_theta"] = uv[:, 0]
    attrs["_cap"] = np.zeros(len(V), bool)
    attrs["_cap"][-1] = True
    attrs["_cap_tris"] = N
    return V, T, attrs


# --------------------------------------------------------------------------------------
# Build one piece
# --------------------------------------------------------------------------------------


SLEEVE_UV = {}


def unwrap(ob, res, sleeve_density=0.42):
    """Glove: smart project.  Sleeve: its own cylindrical (around, along) layout as one
    island plus the end cap, at ~40% of the glove's texel density (it is mostly seen at
    the screen edge).  Then everything is packed together."""
    me = ob.data
    ng = ob["n_glove_tris"]
    nvg = ob["n_glove_verts"]
    theta, along, ncap, axis, sv = SLEEVE_UV[ob.name]
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")
    bk.deselect_all()
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    sel = np.zeros(len(me.polygons), bool)
    sel[:ng] = True
    me.polygons.foreach_set("select", sel)
    # smart-project a smoothed copy of the surface: the voxel mesh's faceted normals would
    # otherwise shatter it into slivers; the UVs then go back onto the real vertices
    co0 = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co0)
    lt = np.empty(len(me.polygons) * 3, np.int64)
    me.polygons.foreach_get("vertices", lt)
    nbr, starts = neighbours(len(me.vertices), lt.reshape(-1, 3))
    sm = laplacian(co0.reshape(-1, 3), nbr, starts, iters=12, lam=0.6)
    me.vertices.foreach_set("co", sm.ravel())
    me.update()
    bpy.ops.object.mode_set(mode="EDIT")
    margin = 4 * 1.5 / 4096.0 * (4096 / res)
    bpy.ops.uv.smart_project(angle_limit=math.radians(70.0), island_margin=margin, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    me.vertices.foreach_set("co", co0)
    me.update()
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    # glove texel density (uv area / world area)
    tri_l = lv[: ng * 3].reshape(-1, 3)
    w = co[tri_l]
    a3 = np.linalg.norm(np.cross(w[:, 1] - w[:, 0], w[:, 2] - w[:, 0]), axis=1).sum()
    u = uv[: ng * 3].reshape(-1, 3, 2)
    e1, e2 = u[:, 1] - u[:, 0], u[:, 2] - u[:, 0]
    a2 = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum()
    k = math.sqrt(a2 / a3) * math.sqrt(sleeve_density)
    # sleeve loops: (theta * mean radius, along), unwrapped across the seam per face
    rad = 0.04
    sl = lv[ng * 3 :].reshape(-1, 3) - nvg
    th = theta[sl].copy()
    wrap = th.max(1) - th.min(1) > math.pi
    th[wrap] = np.where(th[wrap] < math.pi, th[wrap] + 2 * math.pi, th[wrap])
    us = np.stack([th * rad, along[sl]], -1) * k
    # cap: planar projection, offset away from the tube island
    ncap_f = ncap
    cap = slice(len(sl) - ncap_f, len(sl))
    w0, fd, side, up = axis
    pc = sv[sl[cap]]
    us[cap] = np.stack([(pc - w0) @ side, (pc - w0) @ up], -1) * k + np.array([-0.2, 0.0])
    uv[ng * 3 :] = us.reshape(-1, 2)
    me.uv_layers.active.data.foreach_set("uv", uv.ravel())
    me.polygons.foreach_set("select", np.ones(len(me.polygons), bool))
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, rotate_method="ANY", margin=margin, shape_method="CONVEX")
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)


def build_piece(piece, ctx, h_size, coll):
    t0 = time.time()
    cfg = CONFIG[piece]
    h = pose_hand(piece, ctx)
    F = glove_field(h)
    if piece == "RightGrip":
        ctx.right = F
        ctx.right_hand = h
    v, q = hk.mesh_field(F, h_size)
    v = F.project(v, 2)
    tris = triangulate_quads(v, q)
    tris = gl.fix_winding(v, tris, F)
    log(f"  {piece}: glove surface {len(v)} verts {len(tris)} tris ({time.time() - t0:.0f}s)")
    # press flesh that sinks into the gun out onto its surface
    if piece == "RightGrip":
        pairs = [(ctx.bvhP, ctx.sdfP), (ctx.bvhR, ctx.sdfR)]
        fields = []

        def region(p):
            return p[:, 0] < 0.035
    elif piece == "LeftPistol":
        pairs = [(ctx.bvhP, ctx.sdfP)]
        fields = [ctx.right]

        def region(p):
            return p[:, 0] < 0.05
    else:
        pairs = [(ctx.bvhS, ctx.sdfS)]
        hgF = hk.Field()
        hgF.add(ctx.hg)
        fields = [hgF]
        region = None
    v, moved = carve(v, pairs, fields, region)
    nbr, starts = neighbours(len(v), tris)
    grow = moved.copy()
    for _ in range(2):
        grow = grow | np.isin(np.arange(len(v)), nbr[np.isin(np.repeat(np.arange(len(v)), np.diff(starts)), np.nonzero(grow)[0])])
    ring = grow & ~moved
    v = laplacian(v, nbr, starts, iters=3, lam=0.5, mask=ring)
    v, moved2 = carve(v, pairs, fields, region)
    log(f"  {piece}: carved {moved.sum()} verts ({time.time() - t0:.0f}s)")
    # zone fields + seams
    zv = zone_values(h, F, v)
    zv["dorsal"] = laplacian(zv["dorsal"], nbr, starts, iters=8, lam=0.5)
    sd, ss = seam_fields(v, tris, zv)
    log(f"  {piece}: zones + seams ({time.time() - t0:.0f}s)")
    gattrs = dict(
        z_dorsal=zv["dorsal"],
        m_shell=zv["shell"],
        m_pad=zv["pad"],
        m_patch=zv["patch"],
        m_strap=zv["strap"],
        m_tab=zv["tab"],
        z_cuff=zv["cuff"],
        seam_d=sd,
        seam_s=ss,
        m_sleeve=np.zeros(len(v)),
        sl_u=np.zeros(len(v)),
        sl_v=np.zeros(len(v)),
    )
    # sleeve
    sv, st, sattrs = sleeve_mesh(h, cfg["elbow"], seed=PIECES.index(piece))
    nv = len(v)
    V = np.vstack([v, sv])
    T = np.vstack([tris, st + nv])
    attrs = {}
    for k in gattrs:
        sa = sattrs.get(k, np.zeros(len(sv)))
        if k == "z_dorsal":
            sa = np.ones(len(sv))
        if k == "z_cuff":
            sa = np.full(len(sv), 5.0)
        attrs[k] = np.concatenate([gattrs[k], sa]).astype(np.float32)
    ob = gl.mesh_object(f"SM_{ASSET}_{piece}", V, T, coll)
    me = ob.data
    for k, a in attrs.items():
        at = me.attributes.new(k, "FLOAT", "POINT")
        at.data.foreach_set("value", a)
    tri = len(T)
    log(f"  {piece}: {tri} triangles total (glove {len(tris)}, sleeve {len(st)}) ({time.time() - t0:.0f}s)")
    if tri > TRI_BUDGET:
        log(f"WARNING {piece}: {tri} triangles > {TRI_BUDGET}")
    ob["piece"] = piece
    ob["n_glove_tris"] = len(tris)
    ob["n_glove_verts"] = nv
    SLEEVE_UV[ob.name] = (sattrs["_theta"], sattrs["sl_v"], sattrs["_cap_tris"], h.landmarks["cuff_axis"], sv)
    return ob, h


# --------------------------------------------------------------------------------------
# Bake
# --------------------------------------------------------------------------------------

ZONE = {
    # base colour (linear), roughness
    "leather": ((0.030, 0.0245, 0.0195), 0.5),
    "patch": ((0.021, 0.0195, 0.018), 0.74),
    "dots": ((0.055, 0.052, 0.05), 0.42),
    "fabric": ((0.0155, 0.0155, 0.017), 0.84),
    "shell": ((0.19, 0.128, 0.072), 0.6),
    "pad": ((0.165, 0.112, 0.064), 0.66),
    "strap": ((0.017, 0.017, 0.019), 0.78),
    "tab": ((0.19, 0.128, 0.072), 0.6),
    "cuff": ((0.019, 0.019, 0.021), 0.72),
    "sleeve": ((0.062, 0.071, 0.045), 0.86),
}


def attr(nb, name):
    n = nb.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=name)
    return n.outputs["Fac"]


def glove_graph(mat, mask_img):
    """Returns {'mask','color','orm','normal'} sockets for one baking material."""
    nt = mat.node_tree
    nb = bk.NB(nt)
    geo = nb.node("ShaderNodeNewGeometry")
    pos = geo.outputs["Position"]
    out = {}
    # --- mask pass: R = convex edge, G = AO
    bev = nb.node("ShaderNodeBevel", samples=6)
    bev.inputs["Radius"].default_value = 0.0025
    dot = nb.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nb._in(dot.inputs[0], bev.outputs["Normal"])
    nb._in(dot.inputs[1], geo.outputs["Normal"])
    edge = nb.maprange(dot.outputs["Value"], 0.995, 0.8, 0.0, 1.0)
    ao = nb.node("ShaderNodeAmbientOcclusion", samples=12, only_local=True)
    ao.inputs["Distance"].default_value = 0.012
    out["mask"] = nb.emit(nb.combine(edge, ao.outputs["AO"], 0.0))
    # --- zone masks (anti-aliased thresholds of the vertex fields)
    dors = attr(nb, "z_dorsal")
    sleeve = nb.maprange(attr(nb, "m_sleeve"), 0.4, 0.6)
    cuffz = nb.maprange(attr(nb, "z_cuff"), -0.25, 0.25)
    m_dors = nb.maprange(dors, 0.0, 0.1)
    m_shell = nb.maprange(attr(nb, "m_shell"), 0.4, 0.6)
    m_pad = nb.maprange(attr(nb, "m_pad"), 0.4, 0.6)
    m_patch = nb.maprange(attr(nb, "m_patch"), 0.4, 0.6)
    m_strap = nb.maprange(attr(nb, "m_strap"), 0.4, 0.6)
    m_tab = nb.maprange(attr(nb, "m_tab"), 0.4, 0.6)
    seam_d = attr(nb, "seam_d")
    seam_s = attr(nb, "seam_s")
    if mask_img is not None:
        uv = nb.node("ShaderNodeUVMap", uv_map="UVMap")
        img = nb.node("ShaderNodeTexImage", image=mask_img, interpolation="Linear")
        nb._in(img.inputs["Vector"], uv.outputs["UV"])
        m_edge, m_ao, _ = nb.separate(img.outputs["Color"])
    else:
        m_edge, m_ao = 0.0, 1.0
    # --- micro height per zone
    grain = nb.maprange(nb.voronoi(pos, 750.0, "F1"), 0.0, 0.55, 1.0, 0.0, smooth=True)
    grain = nb.add(nb.mul(grain, 0.7), nb.mul(nb.noise(pos, 2600.0, 2.0), 0.3))
    dots_d = nb.voronoi(pos, 230.0, "F1", rand=0.25)
    dots = nb.maprange(dots_d, 0.26, 0.2, 0.0, 1.0, smooth=True)
    # stretch knit: isotropic fine cells + fibre noise (no direction, so no contour banding)
    knit = nb.maprange(nb.voronoi(nb.vscale(pos, (1.0, 1.0, 1.0)), 1700.0, "F1", rand=0.6), 0.0, 0.7, 1.0, 0.0)
    weave = nb.add(nb.mul(knit, 0.6), nb.mul(nb.noise(pos, 4200.0, 1.0), 0.4))
    stip = nb.maprange(nb.voronoi(pos, 1500.0, "F1"), 0.0, 0.6, 1.0, 0.0)
    twill = nb.add(nb.mul(nb.noise(nb.vscale(pos, (1.0, 1.0, 1.0)), 1400.0, 2.0), 0.6), nb.mul(knit, 0.4))
    # ripstop: grid every ~5 mm in sleeve (u, v) coordinates + fine weave
    su, sv_ = attr(nb, "sl_u"), attr(nb, "sl_v")
    gu = nb.math("PINGPONG", nb.mul(su, 200.0), 0.5)
    gv = nb.math("PINGPONG", nb.mul(sv_, 200.0), 0.5)
    grid = nb.math("MAXIMUM", nb.maprange(gu, 0.06, 0.0, 0.0, 1.0), nb.maprange(gv, 0.06, 0.0, 0.0, 1.0))
    fu = nb.math("PINGPONG", nb.mul(su, 1300.0), 0.5)
    fv_ = nb.math("PINGPONG", nb.mul(sv_, 1300.0), 0.5)
    fine = nb.mul(nb.add(fu, fv_), 1.0)
    rip = nb.add(nb.mul(grid, 0.32), nb.mul(fine, 0.3))
    # stitches: double row at 1.6 mm either side of every seam, 3.4 mm pitch
    row = nb.maprange(nb.math("ABSOLUTE", nb.sub(seam_d, 0.0016)), 0.00055, 0.00025, 0.0, 1.0, smooth=True)
    dash = nb.math("PINGPONG", nb.mul(seam_s, 1.0 / 0.0034), 0.5)
    dash = nb.maprange(dash, 0.1, 0.17, 0.0, 1.0, smooth=True)
    stitch = nb.mul(row, dash)
    groove = nb.maprange(seam_d, 0.0007, 0.0, 0.0, 1.0, smooth=True)
    # glove (non-sleeve) panels: leather -> patch / fabric -> cuff -> features
    h_leather = nb.mul(grain, 0.45)
    h_patch = nb.add(nb.mul(nb.noise(pos, 1800.0, 2.0), 0.2), nb.mul(dots, 0.9))
    h_fab = nb.mul(weave, 0.5)
    h_cuff = nb.mul(stip, 0.35)
    h = nb.lerp(m_patch, h_leather, h_patch)
    h = nb.lerp(m_dors, h, h_fab)
    h = nb.lerp(cuffz, h, h_cuff)
    h = nb.lerp(m_pad, h, nb.mul(stip, 0.4))
    h = nb.lerp(m_shell, h, nb.mul(stip, 0.3))
    h = nb.lerp(m_strap, h, nb.mul(twill, 0.55))
    h = nb.lerp(m_tab, h, nb.mul(stip, 0.3))
    seam_amt = nb.sub(1.0, sleeve)
    h = nb.add(h, nb.mul(nb.mul(stitch, 0.9), 1.0))
    h = nb.sub(h, nb.mul(groove, 0.9))
    h = nb.lerp(sleeve, h, nb.add(nb.sub(rip, nb.mul(groove, 0.8)), nb.mul(stitch, 0.9)))
    del seam_amt
    # colours
    def C(name):
        return ZONE[name][0]

    gvar = nb.noise(pos, 60.0, 3.0, 0.6)
    col = nb.mixc(1.0, C("leather"), nb.combine(*(nb.add(0.85, nb.mul(gvar, 0.3)),) * 3), "MULTIPLY")
    col = nb.mixc(nb.mul(grain, 0.25), col, tuple(c * 1.25 for c in C("leather")))
    patch_col = nb.mixc(dots, C("patch"), C("dots"))
    col = nb.mixc(m_patch, col, patch_col)
    col = nb.mixc(m_dors, col, C("fabric"))
    col = nb.mixc(cuffz, col, C("cuff"))
    col = nb.mixc(m_pad, col, C("pad"))
    col = nb.mixc(m_shell, col, C("shell"))
    col = nb.mixc(m_strap, col, C("strap"))
    col = nb.mixc(m_tab, col, C("tab"))
    rip_col = nb.mixc(nb.mul(grid, 0.14), C("sleeve"), tuple(c * 0.85 for c in C("sleeve")))
    rip_col = nb.mixc(1.0, rip_col, nb.combine(*(nb.add(0.88, nb.mul(gvar, 0.24)),) * 3), "MULTIPLY")
    col = nb.mixc(sleeve, col, rip_col)
    thread = nb.mixc(0.5, col, (0.05, 0.048, 0.045))
    col = nb.mixc(nb.mul(stitch, 0.85), col, thread)
    # wear (convex edges lighten / scuff) and grime (cavities darken, dust)
    wn = nb.noise(pos, 45.0, 4.0, 0.7)
    wear = nb.maprange(nb.sub(nb.mul(m_edge, 1.2), nb.mul(nb.maprange(wn, 0.35, 0.65), 0.7)), 0.1, 0.45, 0.0, 1.0, smooth=True)
    col = nb.mixc(nb.mul(wear, 0.5), col, nb.mixc(0.5, col, (0.11, 0.1, 0.09)))
    grime = nb.mul(nb.maprange(m_ao, 0.95, 0.4, 0.0, 1.0), nb.add(0.5, nb.mul(nb.noise(pos, 14.0, 2.0), 0.7)))
    col = nb.mixc(nb.mul(grime, 0.55), col, (0.0, 0.0, 0.0))
    dust = nb.mul(nb.maprange(nb.noise(pos, 9.0, 3.0), 0.55, 0.8), 0.25)
    col = nb.mixc(dust, col, nb.mixc(0.6, col, (0.16, 0.14, 0.11)))
    out["color"] = nb.emit(col)
    # roughness / AO / metal
    rough = nb.lerp(m_patch, ZONE["leather"][1], nb.lerp(dots, ZONE["patch"][1], ZONE["dots"][1]))
    rough = nb.add(rough, nb.mul(nb.sub(grain, 0.5), 0.12))
    for m_, z in ((m_dors, "fabric"), (cuffz, "cuff"), (m_pad, "pad"), (m_shell, "shell"), (m_strap, "strap"), (m_tab, "tab"), (sleeve, "sleeve")):
        rough = nb.lerp(m_, rough, ZONE[z][1])
    rough = nb.lerp(nb.mul(stitch, 0.8), rough, 0.7)
    rough = nb.lerp(nb.mul(wear, 0.5), rough, 0.42)
    rough = nb.lerp(nb.mul(grime, 0.5), rough, 0.9)
    rough = nb.add(rough, nb.mul(nb.sub(nb.noise(pos, 180.0, 3.0), 0.5), 0.08))
    rough = nb.math("MAXIMUM", nb.math("MINIMUM", rough, 1.0), 0.05)
    ao_o = nb.maprange(m_ao, 0.0, 1.0, 0.2, 1.0)
    out["orm"] = nb.emit(nb.combine(ao_o, rough, 0.0))
    # normal: bump from the combined micro height
    bump = nb.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.9
    bump.inputs["Distance"].default_value = 0.00045
    nb._in(bump.inputs["Height"], h)
    bsdf = nb.node("ShaderNodeBsdfDiffuse")
    nb._in(bsdf.inputs["Normal"], bump.outputs["Normal"])
    out["normal"] = bsdf.outputs[0]
    out["col_raw"], out["rough_raw"], out["bump_raw"] = col, rough, bump.outputs["Normal"]
    return out


def attr_preview_material(name):
    """Unbaked look-dev material straight from the procedural graph (vertex attributes)."""
    m = bk.fresh_material(name)
    nt = m.node_tree
    outs = glove_graph(m, None)
    outn = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(outs["col_raw"], b.inputs["Base Color"])
    nt.links.new(outs["rough_raw"], b.inputs["Roughness"])
    nt.links.new(outs["bump_raw"], b.inputs["Normal"])
    nt.links.new(b.outputs[0], outn.inputs["Surface"])
    return m


def bake_glove(ob, res, piece):
    paths = bk.texture_paths(OUT_DIR, ASSET, piece)
    paths.pop("M")
    os.makedirs(OUT_DIR, exist_ok=True)
    bk.setup_bake_engine()
    mat = bk.fresh_material(f"__bake_{piece}")
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    margin = max(4, res // 256)
    mask = bk._float_image(f"__mask_{piece}", res // 2)
    outs = glove_graph(mat, None)
    t0 = time.time()
    bk._bake(ob, [mat], [outs["mask"]], mask, "EMIT", max(2, margin // 2))
    bk._denoise_inplace(mask)
    log(f"    mask pass {time.time() - t0:.0f}s")
    mat.node_tree.nodes.clear()
    o = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    o.target = "ALL"
    outs = glove_graph(mat, mask)
    for passname, kind, srgb in (("color", "EMIT", True), ("orm", "EMIT", False), ("normal", "NORMAL", False)):
        t0 = time.time()
        img = bk._float_image(f"__{passname}_{piece}", res)
        bk._bake(ob, [mat], [outs[passname]], img, kind, margin)
        a = bk._pixels(img)
        bpy.data.images.remove(img)
        if passname == "normal":
            v = a[..., :3] * 2.0 - 1.0
            v /= np.maximum(np.linalg.norm(v, axis=2, keepdims=True), 1e-6)
            a[..., :3] = v * 0.5 + 0.5
        key = {"color": "BC", "orm": "ORM", "normal": "N"}[passname]
        bk.save_png(a, paths[key], srgb=srgb)
        log(f"    {key} {time.time() - t0:.0f}s")
    bpy.data.images.remove(mask)
    bpy.data.materials.remove(mat)
    return paths


def textured_material(name, paths):
    m = bk.fresh_material(name)
    nt = m.node_tree
    nb = bk.NB(nt)
    outn = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    bsdf = nb.node("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], outn.inputs["Surface"])
    uv = nb.node("ShaderNodeUVMap", uv_map="UVMap")
    t = {}
    for k, cs in (("BC", "sRGB"), ("ORM", "Non-Color"), ("N", "Non-Color")):
        n = nb.node("ShaderNodeTexImage", image=bk._load(paths[k], cs))
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        t[k] = n
    ao, rough, metal = nb.separate(t["ORM"].outputs["Color"])
    col = nb.mixc(0.5, t["BC"].outputs["Color"], nb.combine(ao, ao, ao), "MULTIPLY")
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(rough, bsdf.inputs["Roughness"])
    nt.links.new(metal, bsdf.inputs["Metallic"])
    nx, ny, nz = nb.separate(t["N"].outputs["Color"])
    nm = nb.node("ShaderNodeNormalMap")
    nt.links.new(nb.combine(nx, nb.sub(1.0, ny), nz), nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Sheen Weight"].default_value = 0.25
    bsdf.inputs["Sheen Roughness"].default_value = 0.4
    return m


def export_fbx(ob, path):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=True,
        object_types={"MESH"},
        axis_forward="X",
        axis_up="Z",
        apply_unit_scale=True,
        global_scale=1.0,
        apply_scale_options="FBX_SCALE_ALL",
        use_tspace=True,
        mesh_smooth_type="FACE",
        add_leaf_bones=False,
        use_mesh_modifiers=True,
        path_mode="STRIP",
        embed_textures=False,
        bake_anim=False,
    )
    ob.select_set(False)


# --------------------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------------------


def ue(p):
    return [round(p[0] * 100, 1) + 0.0, round(-p[1] * 100, 1) + 0.0, round(p[2] * 100, 1) + 0.0]


def bounds_ue(obs):
    lo, hi = studio.bbox(obs)
    a, b = ue(lo), ue(hi)
    return {"Min": [min(a[i], b[i]) for i in range(3)], "Max": [max(a[i], b[i]) for i in range(3)]}


def write_json(info):
    path = os.path.join(gl.DATA_DIR, "Gear.json")
    data = {"Version": 1, "Assets": {}}
    if os.path.exists(path):
        try:
            data = json.load(open(path))
        except Exception:
            pass
    old = data.get("Assets", {}).get(ASSET, {})
    pieces = {p["Name"]: p for p in old.get("Pieces", [])}
    for name, e in info.items():
        pieces[name] = e
    order = [p for p in PIECES if p in pieces]
    entry = {
        "Pieces": [{k: pieces[n][k] for k in ("Name", "Kind", "Slots", "Space", "Attach", "Bounds", "Triangles", "TextureSize") if k in pieces[n]} for n in order],
        "Points": {
            "RightGripAttach": [0.0, 0.0, 0.0],
            "LeftPistolAttach": [0.0, 0.0, 0.0],
            "RightElbow": ue(P(CONFIG["RightGrip"]["elbow"])),
            "LeftElbowPistol": ue(P(CONFIG["LeftPistol"]["elbow"])),
            "LeftElbowSupport": ue(P(CONFIG["LeftSupport"]["elbow"])),
        },
        "Notes": "Unreal cm. RightGrip and LeftPistol are authored in gun space (origin = pistol-grip centre, attach at the gun origin); "
        "LeftSupport is authored relative to the gun's LeftHand point (attach at Points.LeftHand). "
        "LeftElbowSupport is relative to LeftHand. Bounds are per piece in its own space; the asset Bounds is their union.",
    }
    mins = [p["Bounds"]["Min"] for p in entry["Pieces"] if "Bounds" in p]
    maxs = [p["Bounds"]["Max"] for p in entry["Pieces"] if "Bounds" in p]
    if mins:
        entry["Bounds"] = {"Min": [min(m[i] for m in mins) for i in range(3)], "Max": [max(m[i] for m in maxs) for i in range(3)]}
    data["Version"] = 1
    data.setdefault("Assets", {})[ASSET] = entry
    with open(path, "w", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


# --------------------------------------------------------------------------------------
# Renders
# --------------------------------------------------------------------------------------


def import_piece(piece, coll):
    f = os.path.join(OUT_DIR, f"SM_{ASSET}_{piece}.fbx")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=f, axis_forward="X", axis_up="Z")
    obs = [o for o in bpy.data.objects if o not in before]
    for o in obs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
        paths = bk.texture_paths(OUT_DIR, ASSET, piece)
        if all(os.path.exists(paths[k]) for k in ("BC", "N", "ORM")):
            m = textured_material(f"R_{piece}", paths)
        else:
            m = gl.simple_mat(f"R_{piece}", (0.03, 0.028, 0.025), 0.6)
        o.data.materials.clear()
        o.data.materials.append(m)
    return obs


def setup_render_scene(samples):
    scn = bpy.context.scene
    rig = studio.setup_studio()
    scn.cycles.samples = samples
    return rig


def render_product(piece, rig, coll, samples, res):
    obs = import_piece(piece, coll)
    for o in coll.objects:
        o.hide_render = o not in obs
    lo, hi = studio.bbox(obs)
    vd = {"RightGrip": (0.15, -1.0, 0.55), "LeftPistol": (0.25, 1.0, 0.45), "LeftSupport": (0.55, -0.8, 0.6)}[piece]
    rig["floor"].hide_render = True
    studio.frame(rig, lo, hi, view_dir=vd, lens=60, margin=1.1)
    path = os.path.join(RENDER_DIR, f"{ASSET}_{piece}.png")
    os.makedirs(RENDER_DIR, exist_ok=True)
    studio.render(path, res, samples=samples)
    log(f"  wrote {path}")
    for o in obs:
        o.hide_render = True
    return obs


# First-person eye relative to the grip, from the game's hip placement of the gun in camera
# space (AirsoftCombatComponent: rifle (20, 11, -15) cm, pistol (30, 10, -12) cm, UE axes),
# converted to Blender (y flips): the eye sits behind, above and LEFT (+Y) of the grip.
FP_EYE = {"rifle": (-0.20, 0.11, 0.15), "pistol": (-0.30, 0.10, 0.12)}
FP_PITCH = 10.0  # degrees below the barrel line, so both hands are in frame for the check image


def render_first_person(gun, right, left, left_offset, path, rig, samples, res, eye=FP_EYE["rifle"], pitch=FP_PITCH):
    scn = bpy.context.scene
    coll = bpy.data.collections.new("FP_" + gun)
    scn.collection.children.link(coll)
    gobs, _ = gl.load_gun(gun, coll, materials=True)
    for o in right + left:
        o.hide_render = False
    for o in left:
        o.location = Vector(left_offset)
    cam = rig["cam"]
    cam.location = Vector(eye)
    gl.look_at(cam, Vector(eye) + Vector((1.0, 0.0, -math.tan(math.radians(pitch)))))
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(80)
    cam.data.clip_start = 0.01
    cam.data.clip_end = 50
    rig["floor"].hide_render = True
    # light the scene like a bright overcast field
    L = rig["lights"]
    center = Vector((0.15, 0, 0))
    for k, (off, size, e) in {"key": ((0.3, -0.8, 1.0), 1.2, 60), "fill": ((-0.6, 0.6, 0.4), 1.5, 18), "rim": ((0.9, 0.5, 0.6), 0.8, 30), "kick": ((-0.2, -0.6, -0.3), 0.8, 6)}.items():
        L[k].location = center + Vector(off)
        gl.look_at(L[k], center)
        L[k].data.size = size
        L[k].data.size_y = size
        L[k].data.energy = e
        L[k].data.use_shadow = True
    studio.render(path, res, samples=samples)
    log(f"  wrote {path}")
    for o in gobs:
        o.hide_render = True
    for o in right + left:
        o.hide_render = True
        o.location = Vector((0, 0, 0))


def renders(samples, res_prod=(1920, 1080), res_fp=(1920, 1080)):
    reset_scene()
    rig = setup_render_scene(samples)
    coll = bpy.data.collections.new("Gloves")
    bpy.context.scene.collection.children.link(coll)
    obs = {p: render_product(p, rig, coll, samples, res_prod) for p in PIECES if os.path.exists(os.path.join(OUT_DIR, f"SM_{ASSET}_{p}.fbx"))}
    lh = gl.weapon_points("M4")["LeftHand"]
    if "RightGrip" in obs and "LeftSupport" in obs:
        render_first_person("M4", obs["RightGrip"], obs["LeftSupport"], tuple(lh), os.path.join(RENDER_DIR, f"{ASSET}_FirstPerson.png"), rig, samples, res_fp)
    if "RightGrip" in obs and "LeftPistol" in obs:
        render_first_person("G17", obs["RightGrip"], obs["LeftPistol"], (0, 0, 0), os.path.join(RENDER_DIR, f"{ASSET}_FirstPerson_Pistol.png"), rig, samples, res_fp, eye=FP_EYE["pistol"])


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def log(*a):
    print(*a, flush=True)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 1.0
    th = int(os.environ.get("GLOVES_THREADS", "0"))
    if th:
        scn.render.threads_mode = "FIXED"
        scn.render.threads = th


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    res = int(argv[argv.index("--res") + 1]) if "--res" in argv else 2048
    h_size = float(argv[argv.index("--h") + 1]) if "--h" in argv else 0.001
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 20
    skip = {argv[i + 1] for i, a in enumerate(argv) if a in ("--res", "--h", "--samples")}
    only = [a for a in argv if not a.startswith("--") and a not in skip]
    if "--preview" in flags:
        h_size = 0.002
    if "--renders-only" in flags:
        renders(samples)
        return
    reset_scene()
    coll = bpy.data.collections.new("Gloves")
    bpy.context.scene.collection.children.link(coll)
    ctx = Ctx()
    info = {}
    todo = [p for p in PIECES if not only or p in only]
    if "LeftPistol" in todo and "RightGrip" not in todo:
        todo = ["RightGrip"] + todo  # LeftPistol wraps around RightGrip
    for piece in ["RightGrip", "LeftSupport", "LeftPistol"]:
        if piece not in todo:
            continue
        build_only = only and piece not in only
        ob, h = build_piece(piece, ctx, h_size, coll)
        if build_only:
            continue
        tris = len(ob.data.polygons)
        slot = f"M_{ASSET}_{piece}"
        t0 = time.time()
        unwrap(ob, res)
        log(f"  {piece}: UVs {time.time() - t0:.0f}s")
        if "--no-bake" not in flags:
            t0 = time.time()
            bake_glove(ob, res, piece)
            log(f"  {piece}: baked {res}px in {time.time() - t0:.0f}s")
        ob.data.materials.clear()
        ob.data.materials.append(bpy.data.materials.get(slot) or bpy.data.materials.new(slot))
        os.makedirs(OUT_DIR, exist_ok=True)
        export_fbx(ob, os.path.join(OUT_DIR, f"SM_{ASSET}_{piece}.fbx"))
        info[piece] = {
            "Name": piece,
            "Kind": "Static",
            "Slots": [slot],
            "Space": "Gun" if CONFIG[piece]["space"] == "gun" else "LeftHand",
            "Attach": "Origin" if CONFIG[piece]["space"] == "gun" else "LeftHand",
            "Bounds": bounds_ue([ob]),
            "Triangles": tris,
            "TextureSize": res,
        }
        log(f"built {piece}: {tris} tris")
    if info:
        write_json(info)
    if "--no-render" not in flags and not only:
        renders(samples)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--" in a:
        a = a[a.index("--") + 1 :]
    main(a)
