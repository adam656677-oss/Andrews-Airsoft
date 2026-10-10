"""
teamgear_body: the assumed UE5 Manny reference pose and an original stand-in mannequin.

The third-person body in game is UE5 Manny (SKM_Manny_Simple from the Third Person pack).
Its skeleton is not available here, so the team gear is fitted to a stand-in body built
from smooth signed-distance primitives (Tools/Blender/gear/handkit.py) at roughly Manny's
proportions (about 180 cm, athletic build, A-pose with the arms ~45 deg down).  Nothing
here is derived from Epic's mesh.

Character space (Blender metres): +X forward, +Y = the character's LEFT, +Z up, feet at
z = 0.  Every gear piece is exported with its origin at its anchor bone's pivot below, so
the runtime (UAirsoftTeamGearComponent) only needs the bone's reference-pose position.
"""

import math

import numpy as np

import handkit as hk


def _n(v):
    v = np.asarray(v, np.float64)
    return v / np.linalg.norm(v)


def mirror(p):
    return (p[0], -p[1], p[2])


# --------------------------------------------------------------------------------------
# Assumed UE5 Manny reference pose (bone pivots, character space, metres)
# --------------------------------------------------------------------------------------

ARM_DIR = _n((0.10, 0.72, -0.69))  # left upper arm in the A-pose (down ~44 deg, slightly forward)
FOREARM_DIR = _n((0.16, 0.66, -0.73))
UPPERARM_LEN = 0.285
FOREARM_LEN = 0.265

SKEL = {
    "pelvis": (0.000, 0.0, 0.970),
    "spine_01": (-0.005, 0.0, 1.035),
    "spine_02": (-0.012, 0.0, 1.110),
    "spine_03": (-0.018, 0.0, 1.190),
    "spine_04": (-0.022, 0.0, 1.275),
    "spine_05": (-0.022, 0.0, 1.370),
    "neck_01": (-0.018, 0.0, 1.475),
    "neck_02": (-0.008, 0.0, 1.530),
    "head": (0.000, 0.0, 1.585),
    "clavicle_l": (0.020, 0.030, 1.440),
    "upperarm_l": (-0.010, 0.175, 1.425),
    "thigh_l": (0.000, 0.094, 0.930),
    "calf_l": (0.012, 0.106, 0.505),
    "foot_l": (-0.025, 0.114, 0.085),
}
SKEL["lowerarm_l"] = tuple(np.asarray(SKEL["upperarm_l"]) + ARM_DIR * UPPERARM_LEN)
SKEL["hand_l"] = tuple(np.asarray(SKEL["lowerarm_l"]) + FOREARM_DIR * FOREARM_LEN)
for _k in [k for k in SKEL if k.endswith("_l")]:
    SKEL[_k[:-2] + "_r"] = mirror(SKEL[_k])


def bone(name):
    return np.asarray(SKEL[name], np.float64)


def bone_ue(name):
    """Assumed bone position in UE character space, cm (X forward, Y right, Z up)."""
    p = SKEL[name]
    return [round(p[0] * 100, 1) + 0.0, round(-p[1] * 100, 1) + 0.0, round(p[2] * 100, 1) + 0.0]


def dir_ue(d):
    d = _n(d)
    return [round(float(d[0]), 4) + 0.0, round(float(-d[1]), 4) + 0.0, round(float(d[2]), 4) + 0.0]


HEAD = bone("head")
# head landmarks relative to the head pivot (stand-in)
CRANIUM_C = np.array([0.008, 0.0, 0.088])
CRANIUM_R = np.array([0.100, 0.079, 0.112])
EYE_Z = 0.070

# --------------------------------------------------------------------------------------
# Stand-in body (signed distance field)
# --------------------------------------------------------------------------------------


def _ell(tag, c, r, M=None):
    return hk.Prim("ell", tag, c=np.asarray(c, np.float64), M=np.eye(3) if M is None else M, r=np.asarray(r, np.float64))


def _cone(tag, a, b, r1, r2):
    return hk.Prim("cone", tag, a=np.asarray(a, np.float64), b=np.asarray(b, np.float64), r1=r1, r2=r2)


def _box(tag, c, b, rad, M=None):
    return hk.Prim("box", tag, c=np.asarray(c, np.float64), M=np.eye(3) if M is None else M, b=np.asarray(b, np.float64), rad=rad)


def _head_prims(F):
    H = HEAD
    F.add(_cone("neck", (-0.024, 0, 1.43), H + (-0.004, 0, 0.0), 0.062, 0.053), 0.03)
    F.add(_ell("cranium", H + CRANIUM_C, CRANIUM_R), 0.03)
    F.add(_ell("face", H + (0.050, 0, 0.032), (0.066, 0.060, 0.064)), 0.025)
    F.add(_ell("jaw", H + (0.070, 0, -0.010), (0.040, 0.046, 0.034)), 0.02)
    F.add(_cone("nose", H + (0.104, 0, 0.070), H + (0.119, 0, 0.046), 0.011, 0.009), 0.008)
    for s in (1, -1):
        F.add(_ell("brow", H + (0.088, 0.030 * s, 0.092), (0.022, 0.028, 0.012)), 0.01)
        F.add(_ell("ear", H + (-0.004, 0.081 * s, 0.062), (0.020, 0.008, 0.030)), 0.006)


def _torso_prims(F):
    F.add(_ell("ribcage", (0.000, 0, 1.300), (0.125, 0.165, 0.185)))
    F.add(_ell("abdomen", (0.012, 0, 1.125), (0.108, 0.140, 0.150)), 0.05)
    F.add(_ell("pelvis", (-0.005, 0, 0.965), (0.110, 0.162, 0.120)), 0.05)
    for s in (1, -1):
        F.add(_ell("pec", (0.060, 0.072 * s, 1.335), (0.068, 0.085, 0.062)), 0.03)
        F.add(_ell("lat", (-0.030, 0.110 * s, 1.270), (0.075, 0.070, 0.130)), 0.04)
        F.add(_ell("glute", (-0.050, 0.070 * s, 0.920), (0.075, 0.080, 0.090)), 0.04)
        sh = np.asarray(mirror(SKEL["upperarm_l"]) if s < 0 else SKEL["upperarm_l"])
        F.add(_cone("trap", (-0.025, 0.040 * s, 1.470), (-0.020, 0.150 * s, 1.432), 0.055, 0.050), 0.04)
        F.add(_ell("deltoid", sh + (0.0, 0.012 * s, 0.006), (0.064, 0.060, 0.072)), 0.03)


def _limb_prims(F):
    for side, s in (("l", 1), ("r", -1)):
        sh, el, wr = bone("upperarm_" + side), bone("lowerarm_" + side), bone("hand_" + side)
        F.add(_cone("upperarm", sh, el, 0.058, 0.044), 0.025)
        F.add(_cone("forearm", el, wr, 0.043, 0.030), 0.02)
        fd = _n(wr - el)
        side_ax = _n(np.cross(fd, (1.0, 0.0, 0.0)))
        M = hk.frame_from(fd, side_ax)  # thin axis across the palm
        F.add(_ell("hand", wr + fd * 0.085, (0.092, 0.046, 0.024), M), 0.02)
        th, kn, an = bone("thigh_" + side), bone("calf_" + side), bone("foot_" + side)
        F.add(_cone("thigh", th, kn, 0.096, 0.058), 0.035)
        F.add(_ell("quad", lerp(th, kn, 0.45) + (0.022, 0.0, 0.0), (0.070, 0.068, 0.150)), 0.04)
        F.add(_cone("calf", kn, an, 0.055, 0.036), 0.025)
        F.add(_ell("calfm", kn + (-0.022, 0.0, -0.130), (0.056, 0.052, 0.098)), 0.03)
        F.add(_box("foot", an + (0.060, 0.0, -0.048), (0.125, 0.048, 0.038), 0.030), 0.02)


def body_field(limbs=True, head=True):
    F = hk.Field()
    _torso_prims(F)
    if head:
        _head_prims(F)
    if limbs:
        _limb_prims(F)
    return F


_CACHE = {}


def field(kind="full"):
    """'full' (whole stand-in), 'torso' (torso + neck + head: carrier fitting), 'head'."""
    if kind not in _CACHE:
        if kind == "full":
            _CACHE[kind] = body_field(True, True)
        elif kind == "torso":
            _CACHE[kind] = body_field(False, True)
        elif kind == "head":
            F = hk.Field()
            _head_prims(F)
            _CACHE[kind] = F
        elif kind == "leg_l":
            F = hk.Field()
            th, kn, an = bone("thigh_l"), bone("calf_l"), bone("foot_l")
            F.add(_cone("thigh", th, kn, 0.096, 0.058))
            F.add(_ell("quad", lerp(th, kn, 0.45) + (0.022, 0.0, 0.0), (0.070, 0.068, 0.150)), 0.04)
            F.add(_cone("calf", kn, an, 0.055, 0.036), 0.025)
            F.add(_ell("calfm", kn + (-0.022, 0.0, -0.130), (0.056, 0.052, 0.098)), 0.03)
            _CACHE[kind] = F
        elif kind == "arm_l":
            F = hk.Field()
            F.add(_cone("upperarm", bone("upperarm_l"), bone("lowerarm_l"), 0.058, 0.044))
            _CACHE[kind] = F
        else:
            raise ValueError(kind)
    return _CACHE[kind]


# --------------------------------------------------------------------------------------
# Fitting queries
# --------------------------------------------------------------------------------------


def march(F, origins, dirs, steps=80, eps=2e-4):
    """Sphere-traces from outside points along dirs until the surface; returns hit points."""
    p = np.array(origins, np.float64, copy=True).reshape(-1, 3)
    d = np.broadcast_to(np.asarray(dirs, np.float64), p.shape).copy()
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    done = np.zeros(len(p), bool)
    for _ in range(steps):
        idx = np.nonzero(~done)[0]
        if not len(idx):
            break
        dist = F.eval(p[idx])
        hit = dist < eps
        done[idx[hit]] = True
        mv = idx[~hit]
        p[mv] += d[mv] * np.maximum(dist[~hit], eps)[:, None] * 0.95
    return p


def surface_normal(F, p):
    g = F.gradient(np.asarray(p, np.float64).reshape(-1, 3), 4e-4)
    return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)


def front_depth(F, y, z, sign=1.0, start=0.5):
    """x of the body surface seen from the front (sign=+1) or the back (sign=-1)."""
    y = np.atleast_1d(np.asarray(y, np.float64))
    z = np.atleast_1d(np.asarray(z, np.float64))
    o = np.stack([np.full(y.shape, sign * start), y, z], -1).reshape(-1, 3)
    p = march(F, o, (-sign, 0.0, 0.0))
    return p[:, 0].reshape(y.shape)


def radial_section(F, z, center_xy, thetas, start=0.45):
    """Horizontal body cross-section: radius from center_xy at each azimuth (0 = +X, ccw)."""
    th = np.asarray(thetas, np.float64)
    dirs = np.stack([np.cos(th), np.sin(th), np.zeros_like(th)], -1)
    o = np.stack([center_xy[0] + dirs[:, 0] * start, center_xy[1] + dirs[:, 1] * start, np.full(th.shape, z)], -1)
    p = march(F, o, -dirs)
    return np.hypot(p[:, 0] - center_xy[0], p[:, 1] - center_xy[1])


# --------------------------------------------------------------------------------------
# Stand-in mesh
# --------------------------------------------------------------------------------------


def mannequin_mesh(h=0.007):
    """Vertices and quads of the whole stand-in (surface nets, projected)."""
    F = field("full")
    v, q = hk.mesh_field(F, h)
    v = F.project(v, 2)
    return F, v, q


def lerp(a, b, t):
    return np.asarray(a) + (np.asarray(b) - np.asarray(a)) * t


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def deg(a):
    return math.radians(a)
