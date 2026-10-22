"""
headlib: original, procedurally sculpted character heads for the story cast (Last Contract).

A head is a smooth signed-distance field: a cranium, face mass, cheekbones, jaw and chin, brow
ridge, nose (bridge, tip, wings, nostrils), lips, eyes in sockets with eyelids, ears and a neck,
blended with smooth unions.  Every character is the same generic base driven by a handful of
proportion parameters (the "shape keys" in CAST: jaw width, chin, cheekbones, brow, nose length /
width / bridge, lip width and fullness, face length, ear size, neck, age).  The base is fitted
around the stand-in mannequin head (Tools/Blender/gear/teamgear_body.py) and always encloses it
by a few millimetres, so the attached head covers the in-game mannequin head.  None of the faces
is modelled on a real person or on any film character.

Hair (and Silas's beard) is a separate shell over the head field, with a hairline and thickness
profile per style.

Coordinates: metres, head-local (origin = the head bone pivot of the assumed UE5 Manny reference
pose, +X forward, +Y the character's left, +Z up).
"""

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gear"))
sys.path.insert(0, os.path.join(HERE, "..", "common"))

import handkit as hk  # noqa: E402
import teamgear_body as tb  # noqa: E402

HEAD_PIVOT = tb.HEAD.copy()  # character space
NECK_CUT = -0.122  # the neck ends inside the shirt collar
COVER_MARGIN = 0.0030  # every point of the stand-in head stays this far inside the new head
COVER_MARGIN_EYES = 0.0004  # ... except around the eyes, where the sockets need the room


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def gauss(x, c, w):
    return np.exp(-(((np.asarray(x, np.float64) - c) / w) ** 2))


def ell(p, c, r):
    return hk.sd_ellipsoid(p - np.asarray(c, np.float64), r)


def ell_rot(p, c, r, M):
    """Ellipsoid whose local axes are the columns of M."""
    q = (p - np.asarray(c, np.float64)) @ M
    return hk.sd_ellipsoid(q, r)


def cone(p, a, b, r1, r2):
    return hk.sd_round_cone(p, a, b, r1, r2)


def sphere(p, c, r):
    return np.linalg.norm(p - np.asarray(c, np.float64), axis=1) - r


def rot_z(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rot_y(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


# --------------------------------------------------------------------------------------
# Cast: proportions, colours and hair (all original designs)
# --------------------------------------------------------------------------------------

BASE = dict(
    skull=(1.0, 1.0, 1.0), face_len=1.0, face_w=1.0, jaw_w=1.0, jaw_drop=0.0, chin=0.0, chin_w=1.0, cheek=1.0, brow=1.0,
    nose_len=1.0, nose_w=1.0, nose_bridge=0.0, nose_tip=1.0, nose_flat=0.0, lip_w=1.0, lip_full=1.0, ear=1.0, neck=1.0, age=0.3,
    eye_open=1.0, eye_set=0.0, female=0.0,
)

# Skin albedo as sRGB (converted to linear at bake time); hair and brow colours are linear.
CAST = {
    "Andrew": dict(
        title="Andrew", role="Retired contractor", seed=11,
        shape=dict(jaw_w=1.03, chin=0.004, cheek=1.12, brow=1.08, nose_len=1.03, nose_bridge=0.0025, lip_full=0.92, face_len=1.02, age=0.45,
                   face_w=0.97, eye_set=0.0015),
        skin=(0.71, 0.53, 0.43), redness=0.35, stubble=0.55, stubble_col=(0.030, 0.026, 0.024),
        brow_col=(0.028, 0.022, 0.019), brow_thick=1.05, iris=(0.10, 0.075, 0.045),
        hair=dict(style="crop", col=(0.026, 0.022, 0.020), grey=0.28)),
    "Kade": dict(
        title="Kade", role="The Ledger's runner", seed=23,
        shape=dict(skull=(0.98, 0.98, 1.0), jaw_w=0.93, chin=-0.002, cheek=0.94, brow=0.88, nose_len=0.94, nose_tip=1.08, nose_w=0.96,
                   lip_full=1.05, face_len=0.97, age=0.05, face_w=1.0),
        skin=(0.66, 0.48, 0.36), redness=0.25, stubble=0.0, stubble_col=(0.03, 0.025, 0.02),
        brow_col=(0.030, 0.022, 0.016), brow_thick=0.9, iris=(0.05, 0.03, 0.015),
        hair=dict(style="textured", col=(0.032, 0.022, 0.015), grey=0.0)),
    "Dorian Sloane": dict(
        title="Dorian Sloane", role="Club owner, the Ledger's front man", seed=37,
        shape=dict(skull=(1.0, 0.97, 1.04), face_len=1.07, face_w=0.93, jaw_w=0.92, chin=0.006, chin_w=0.9, cheek=1.05, brow=0.95,
                   nose_len=1.09, nose_w=0.86, nose_bridge=0.0035, lip_w=0.95, lip_full=0.78, age=0.55, eye_set=0.0005),
        skin=(0.80, 0.65, 0.56), redness=0.30, stubble=0.0, stubble_col=(0.06, 0.05, 0.04),
        brow_col=(0.10, 0.085, 0.065), brow_thick=0.8, iris=(0.12, 0.17, 0.20),
        hair=dict(style="slick", col=(0.17, 0.145, 0.11), grey=0.25)),
    "Mara Voss": dict(
        title="Mara Voss", role="The Ledger's enforcer", seed=41,
        shape=dict(skull=(0.96, 0.94, 0.97), face_len=0.95, face_w=0.92, jaw_w=0.84, chin=0.001, chin_w=0.82, cheek=1.14, brow=0.72,
                   nose_len=0.92, nose_w=0.84, nose_tip=0.92, lip_w=0.94, lip_full=1.18, ear=0.9, neck=0.86, age=0.2, female=1.0),
        skin=(0.62, 0.45, 0.35), redness=0.22, stubble=0.0, stubble_col=(0.02, 0.02, 0.02),
        brow_col=(0.022, 0.016, 0.012), brow_thick=0.7, iris=(0.05, 0.035, 0.02), lip_tint=(0.36, 0.11, 0.10),
        hair=dict(style="bun", col=(0.030, 0.012, 0.008), grey=0.0)),
    "Silas Varga": dict(
        title="Silas Varga", role="Head of the Ledger", seed=53,
        shape=dict(skull=(1.03, 1.05, 0.98), face_len=1.01, face_w=1.08, jaw_w=1.12, jaw_drop=0.003, chin=0.002, cheek=1.0, brow=1.25,
                   nose_len=1.05, nose_w=1.15, nose_tip=1.22, lip_full=0.85, ear=1.08, neck=1.12, age=0.95, eye_open=0.85),
        skin=(0.74, 0.57, 0.48), redness=0.55, stubble=0.0, stubble_col=(0.2, 0.2, 0.2),
        brow_col=(0.19, 0.185, 0.18), brow_thick=1.2, iris=(0.09, 0.10, 0.10),
        hair=dict(style="horseshoe", col=(0.30, 0.29, 0.28), grey=0.0, beard="boxed")),
    "Ledger A": dict(
        title="Ledger crew A", role="Henchman", seed=61, crew=True,
        shape=dict(jaw_w=1.08, chin=0.003, cheek=1.0, brow=1.05, nose_len=0.97, nose_w=1.12, lip_full=1.15, face_w=1.03, neck=1.1, age=0.3),
        skin=(0.36, 0.24, 0.18), redness=0.05, stubble=0.0, stubble_col=(0.012, 0.010, 0.010),
        brow_col=(0.010, 0.008, 0.007), brow_thick=1.0, iris=(0.03, 0.018, 0.010),
        hair=dict(style="buzz", col=(0.010, 0.008, 0.007), grey=0.0)),
    "Ledger B": dict(
        title="Ledger crew B", role="Henchman", seed=67, crew=True,
        shape=dict(skull=(1.02, 1.04, 0.97), jaw_w=1.1, brow=1.2, nose_len=1.0, nose_w=1.05, nose_flat=0.5, lip_full=0.9, face_w=1.05,
                   neck=1.18, age=0.4, eye_open=0.9),
        skin=(0.76, 0.58, 0.48), redness=0.45, stubble=0.8, stubble_col=(0.035, 0.028, 0.022),
        brow_col=(0.05, 0.035, 0.025), brow_thick=1.1, iris=(0.12, 0.13, 0.12),
        hair=dict(style="bald", col=(0.04, 0.03, 0.025), grey=0.0)),
    "Ledger C": dict(
        title="Ledger crew C", role="Henchman", seed=71, crew=True,
        shape=dict(face_len=1.04, jaw_w=0.98, chin=0.002, cheek=0.96, brow=1.0, nose_len=1.06, nose_bridge=-0.002, nose_flat=0.3,
                   lip_full=0.95, age=0.35),
        skin=(0.68, 0.50, 0.38), redness=0.3, stubble=0.45, stubble_col=(0.04, 0.03, 0.022),
        brow_col=(0.05, 0.035, 0.024), brow_thick=0.95, iris=(0.07, 0.05, 0.03),
        hair=dict(style="crew", col=(0.06, 0.040, 0.026), grey=0.0)),
    "Ledger D": dict(
        title="Ledger crew D", role="Henchman", seed=79, crew=True,
        shape=dict(skull=(1.0, 1.0, 1.02), face_len=0.99, jaw_w=1.0, chin=0.0, cheek=1.06, brow=0.95, nose_len=0.95, nose_w=1.18,
                   lip_w=1.04, lip_full=1.22, age=0.2),
        skin=(0.44, 0.30, 0.22), redness=0.06, stubble=0.0, stubble_col=(0.01, 0.01, 0.01),
        brow_col=(0.012, 0.010, 0.008), brow_thick=0.95, iris=(0.035, 0.02, 0.012),
        hair=dict(style="curly", col=(0.012, 0.010, 0.009), grey=0.0)),
}

ASSET_IDS = {
    "Andrew": "Head_Andrew", "Kade": "Head_Kade", "Dorian Sloane": "Head_Dorian", "Mara Voss": "Head_Mara", "Silas Varga": "Head_Silas",
    "Ledger A": "Head_LedgerA", "Ledger B": "Head_LedgerB", "Ledger C": "Head_LedgerC", "Ledger D": "Head_LedgerD",
}


def params(name):
    s = dict(BASE)
    s.update(CAST[name]["shape"])
    return s


# --------------------------------------------------------------------------------------
# Head field
# --------------------------------------------------------------------------------------

_STANDIN = None


def standin_head(p_local):
    """Signed distance to the stand-in mannequin head (and neck) in head-local coordinates."""
    global _STANDIN
    if _STANDIN is None:
        _STANDIN = tb.field("head")
    return _STANDIN.eval(p_local + HEAD_PIVOT)


class Head:
    """One character's head as signed-distance functions (head-local metres)."""

    def __init__(self, name):
        self.name = name
        self.s = s = params(name)
        sx, sy, sz = s["skull"]
        fl, fw = s["face_len"], s["face_w"]
        self.fl, self.fw = fl, fw
        # landmarks (scaled by face length below the brow line / face width)
        self.eye_c = np.array([0.0950 - 0.4 * s["eye_set"], 0.0322 * fw, 0.0705])
        self.eye_r = 0.0121
        self.brow_z = 0.0925
        self.nasion = np.array([0.1120, 0.0, 0.0845])
        self.nose_tip = np.array([0.1390 + 0.010 * (s["nose_len"] - 1.0) + 0.002 * (s["nose_tip"] - 1.0), 0.0, 0.0700 - 0.0255 * fl * s["nose_len"]])
        self.mouth_z = 0.0105 - 0.040 * (fl - 1.0)
        self.chin_c = np.array([0.1020 + s["chin"], 0.0, -0.0330 - 0.050 * (fl - 1.0) - 0.4 * s["jaw_drop"]])
        self.skull_c = np.array([0.004, 0.0, 0.0905])
        self.skull_r = np.array([0.1035 * sx, 0.0815 * sy, 0.1135 * sz])

    # -- parts ------------------------------------------------------------------------
    def cranium(self, p):
        s = self.s
        d = ell(p, self.skull_c, self.skull_r)
        # flatter temples and a slightly fuller occiput
        d = hk.smin(d, ell(p, (-0.040, 0.0, 0.080), (0.070, 0.072 * s["skull"][1], 0.085)), 0.02)
        return d

    def face(self, p):
        s, fl, fw = self.s, self.fl, self.fw
        d = ell(p, (0.054, 0.0, 0.034 - 0.02 * (fl - 1.0)), (0.072, 0.0660 * fw, 0.070 * fl))
        # forehead
        d = hk.smin(d, ell(p, (0.070, 0.0, 0.112), (0.043, 0.068 * self.s["skull"][1], 0.052)), 0.025)
        # cheekbones
        cz = 0.0505 - 0.004 * (fl - 1.0)
        for sgn in (1.0, -1.0):
            M = rot_z(18.0 * sgn)
            d = hk.smin(d, ell_rot(p, (0.077, 0.0495 * fw * sgn, cz - 0.004), (0.028, 0.019 * s["cheek"], 0.015 * s["cheek"]), M), 0.020)
        return d

    def jaw(self, p):
        s, fl, fw = self.s, self.fl, self.fw
        jw = s["jaw_w"] * fw
        zc = -0.010 - 0.030 * (fl - 1.0) - s["jaw_drop"]
        d = ell(p, (0.058, 0.0, zc), (0.052, 0.054 * jw, 0.037))
        # angles of the mandible (squarer jaws stick out more)
        for sgn in (1.0, -1.0):
            d = hk.smin(d, cone(p, (0.004, 0.051 * jw * sgn, 0.018), (0.024, 0.049 * jw * sgn, -0.026 + zc * 0.4), 0.014, 0.012), 0.022)
        # chin
        d = hk.smin(d, ell(p, self.chin_c, (0.0145, 0.0205 * s["chin_w"] * (1.0 - 0.12 * s["female"]), 0.0165)), 0.020)
        # muzzle (teeth / maxilla mass under the lips)
        d = hk.smin(d, ell(p, (0.096, 0.0, self.mouth_z + 0.010), (0.027, 0.034 * s["lip_w"], 0.031 * fl)), 0.018)
        return d

    def brow_ridge(self, p):
        s = self.s
        b = s["brow"]
        x0 = self.eye_c[0]
        d = cone(p, (x0 + 0.004, 0.042 * self.fw, self.brow_z), (x0 + 0.011, 0.011, self.brow_z + 0.002), 0.0095 * b, 0.0080 * b)
        d = np.minimum(d, cone(p, (x0 + 0.004, -0.042 * self.fw, self.brow_z), (x0 + 0.011, -0.011, self.brow_z + 0.002), 0.0095 * b, 0.0080 * b))
        return d

    def nose(self, p):
        s = self.s
        nw = s["nose_w"]
        tip = self.nose_tip
        flat = s["nose_flat"]
        mid = (self.nasion + tip) * 0.5 + np.array([0.0035 + s["nose_bridge"] - 0.003 * flat, 0.0, 0.0])
        d = cone(p, self.nasion + (0.002, 0, 0), mid, 0.0072 * (1 + 0.3 * flat), 0.0076 * nw * (1 + 0.25 * flat))
        d = hk.smin(d, cone(p, mid, tip + (-0.004, 0, 0.002), 0.0076 * nw * (1 + 0.25 * flat), 0.0090 * nw), 0.004)
        d = hk.smin(d, sphere(p, tip + (-0.0025, 0.0, 0.0), 0.0098 * s["nose_tip"] * (0.9 + 0.1 * nw)), 0.004)
        # wings (alae)
        for sgn in (1.0, -1.0):
            d = hk.smin(d, ell(p, tip + (-0.0120, 0.0128 * nw * sgn, -0.0060), (0.0078, 0.0068 * nw, 0.0062)), 0.005)
        # columella and the nose's base into the lip
        d = hk.smin(d, ell(p, tip + (-0.009, 0.0, -0.010), (0.010, 0.006, 0.0045)), 0.004)
        return d

    def nostril_cut(self, p):
        tip = self.nose_tip
        nw = self.s["nose_w"]
        d = None
        for sgn in (1.0, -1.0):
            M = rot_z(-25.0 * sgn)
            e = ell_rot(p, tip + (-0.0060, 0.0072 * nw * sgn, -0.0095), (0.0048, 0.0030 * nw, 0.0028), M)
            d = e if d is None else np.minimum(d, e)
        return d

    def lips(self, p):
        s = self.s
        lw, lf = s["lip_w"], s["lip_full"]
        mz = self.mouth_z
        up = ell_rot(p, (0.1200, 0.0, mz + 0.0058), (0.0105 * (0.8 + 0.2 * lf), 0.0250 * lw, 0.0062 * lf), rot_y(-14.0))
        lo = ell_rot(p, (0.1172, 0.0, mz - 0.0060), (0.0105 * (0.8 + 0.2 * lf), 0.0220 * lw, 0.0072 * lf), rot_y(16.0))
        return np.minimum(up, lo)

    def mouth_cut(self, p):
        lw = self.s["lip_w"]
        q = p - np.array([0.1310, 0.0, self.mouth_z + 0.0002])
        # a thin slit, curving back at the corners
        q2 = q.copy()
        q2[:, 0] = q[:, 0] + 26.0 * q[:, 1] ** 2
        return hk.sd_ellipsoid(q2, np.array([0.0125, 0.0268 * lw, 0.0010]))

    def eye_socket_cut(self, p):
        d = None
        for sgn in (1.0, -1.0):
            c = self.eye_c * (1, sgn, 1) + (0.0065, 0.0012 * sgn, 0.0004)
            e = ell(p, c, (0.0110, 0.0150, 0.0105))
            d = e if d is None else np.minimum(d, e)
        return d

    def eyeballs(self, p):
        d = None
        for sgn in (1.0, -1.0):
            e = sphere(p, self.eye_c * (1, sgn, 1), self.eye_r)
            d = e if d is None else np.minimum(d, e)
        return d

    def eyelids(self, p):
        s = self.s
        d = None
        for sgn in (1.0, -1.0):
            c = self.eye_c * (1, sgn, 1)
            shell = sphere(p, c, self.eye_r + 0.0014)
            # almond opening: wider towards the outer corner, a little hooded with age
            q = p - (c + np.array([self.eye_r, 0.0015 * sgn, 0.0006 - 0.0006 * s["age"]]))
            q = q @ rot_z(-6.0 * sgn)
            open_h = 0.0052 * s["eye_open"] * (1.0 - 0.10 * s["age"]) * (1.0 + 0.06 * s["female"])
            ap = hk.sd_ellipsoid(q, np.array([0.0105, 0.0132, open_h]))
            lid = hk.smax(shell, -ap, 0.0008)
            # keep only the front half of the shell (the back is buried in the socket)
            lid = np.maximum(lid, -(p[:, 0] - (c[0] - 0.004)))
            # under-eye fullness grows with age
            bag = ell(p, c + (0.0075, 0.0005 * sgn, -0.0100), (0.0060, 0.0110, 0.0035 + 0.0012 * s["age"]))
            lid = hk.smin(lid, bag, 0.003)
            d = lid if d is None else np.minimum(d, lid)
        return d

    def ears(self, p):
        s = self.s
        es = s["ear"]
        d = None
        for sgn in (1.0, -1.0):
            M = rot_z(-12.0 * sgn) @ rot_y(-8.0)
            c = np.array([-0.0035, 0.0838 * s["skull"][1] * sgn, 0.0610])
            outer = ell_rot(p, c, (0.0175 * es, 0.0068, 0.0295 * es), M)
            # helix rim and the bowl (concha)
            bowl = ell_rot(p, c + (0.003, 0.0055 * sgn, -0.003), (0.0095 * es, 0.0045, 0.0145 * es), M)
            ear = hk.smax(outer, -bowl, 0.0016)
            lobe = ell_rot(p, c + (0.004, 0.0005 * sgn, -0.0245 * es), (0.0075 * es, 0.0045, 0.0075 * es), M)
            ear = hk.smin(ear, lobe, 0.003)
            d = ear if d is None else np.minimum(d, ear)
        return d

    def neck(self, p):
        s = self.s
        nk = s["neck"]
        d = cone(p, (-0.020, 0.0, NECK_CUT - 0.010), (-0.006, 0.0, -0.004), 0.0585 * nk, 0.0530 * nk)
        # throat / Adam's apple
        d = hk.smin(d, ell(p, (0.032 - 0.004 * s["female"], 0.0, -0.068), (0.020, 0.022, 0.040)), 0.018)
        if s["female"] < 0.5:
            d = hk.smin(d, ell(p, (0.047, 0.0, -0.066), (0.009, 0.010, 0.012)), 0.010)
        # sternocleidomastoids
        for sgn in (1.0, -1.0):
            d = hk.smin(d, cone(p, (-0.002, 0.044 * nk * sgn, 0.015), (0.040, 0.020 * sgn, NECK_CUT + 0.004), 0.014 * nk, 0.011 * nk), 0.016)
        return d

    # -- whole head -------------------------------------------------------------------
    def skin_sdf(self, p, with_eyes=True):
        d = self.cranium(p)
        d = hk.smin(d, self.face(p), 0.030)
        d = hk.smin(d, self.jaw(p), 0.022)
        d = hk.smin(d, self.brow_ridge(p), 0.016)
        d = hk.smin(d, self.neck(p), 0.030)
        d = hk.smin(d, self.nose(p), 0.006)
        # eye sockets, then lids
        d = hk.smax(d, -self.eye_socket_cut(p), 0.006)
        d = hk.smin(d, self.lips(p), 0.0035)
        d = hk.smax(d, -self.mouth_cut(p), 0.0007)
        d = hk.smax(d, -self.nostril_cut(p), 0.0015)
        d = hk.smin(d, self.ears(p), 0.006)
        # cover the stand-in mannequin head everywhere (no poke-through in game)
        near_eye = np.maximum(gauss(np.linalg.norm((p - self.eye_c) * (1.0, 0.8, 1.3), axis=1), 0, 0.016),
                              gauss(np.linalg.norm((p - self.eye_c * (1, -1, 1)) * (1.0, 0.8, 1.3), axis=1), 0, 0.016))
        margin = COVER_MARGIN + (COVER_MARGIN_EYES - COVER_MARGIN) * near_eye
        d = hk.smin(d, standin_head(p) - margin, 0.003)
        if with_eyes:
            d = hk.smin(d, self.eyelids(p), 0.0022)
            d = np.minimum(d, self.eyeballs(p))
        # the neck ends inside the collar
        d = hk.smax(d, -(p[:, 2] - NECK_CUT), 0.002)
        return d

    def bounds(self):
        return np.array([-0.125, -0.115, NECK_CUT - 0.01]), np.array([0.165, 0.115, 0.225])

    # -- surface attributes for the bake (per vertex) ---------------------------------------
    def attributes(self, v, n):
        """Masks used by the skin shader: eye (iris/pupil cosine), lips, brows, beard, cheeks, ears, lashes, scalp, AO."""
        s = self.s
        out = {}
        ey = self.eyeballs(v)
        eye = (np.abs(ey) < 0.0006).astype(np.float64)
        cosang = np.full(len(v), -1.0)
        for sgn in (1.0, -1.0):
            c = self.eye_c * (1, sgn, 1)
            w = v - c
            nrm = np.linalg.norm(w, axis=1)
            gaze = np.array([1.0, 0.07 * sgn, -0.02])
            gaze /= np.linalg.norm(gaze)
            ca = (w @ gaze) / np.maximum(nrm, 1e-9)
            sel = (np.abs(nrm - self.eye_r) < 0.0006) & (w[:, 1] * sgn > -0.02)
            cosang = np.where(sel, np.maximum(cosang, ca), cosang)
        out["eye"] = eye
        out["eye_cos"] = cosang
        lips = self.lips(v)
        out["lip"] = smoothstep(0.0022, -0.0006, lips) * smoothstep(0.100, 0.110, v[:, 0])
        # lashes / lid line: lid surface close to the eyeball, in front
        lids = self.eyelids(v)
        lash = smoothstep(0.0011, 0.0003, np.abs(lids)) * smoothstep(0.0024, 0.0014, ey) * (1.0 - eye) * smoothstep(0.090, 0.097, v[:, 0])
        out["lash"] = lash
        # brows: an arc above each eye
        brow = np.zeros(len(v))
        for sgn in (1.0, -1.0):
            y = v[:, 1] * sgn
            t = (y - 0.012 * self.fw) / (0.045 * self.fw)  # 0 inner end .. 1 outer end
            arch = self.brow_z + 0.0015 + 0.0050 * np.sin(np.clip(t, 0, 1) * math.pi * 0.8) - 0.002 * t - 0.0012 * s["female"] + 0.0018 * s["female"] * np.sin(np.clip(t, 0, 1) * math.pi)
            half_h = (0.0040 - 0.0016 * t) * CAST[self.name]["brow_thick"]
            m = smoothstep(half_h + 0.0012, half_h - 0.0004, np.abs(v[:, 2] - arch)) * smoothstep(-0.05, 0.05, t) * smoothstep(1.08, 0.92, t)
            m *= smoothstep(0.080, 0.092, v[:, 0]) * (v[:, 1] * sgn > 0)
            brow = np.maximum(brow, m)
        out["brow"] = brow
        # beard / stubble region: jaw, chin, upper lip, cheeks below the cheekbones, under the jaw
        x, y, z = v[:, 0], v[:, 1], v[:, 2]
        ay = np.abs(y)
        upper = 0.040 - 0.20 * np.maximum(ay - 0.030, 0.0) - 0.08 * np.maximum(0.06 - x, 0.0)
        beard = smoothstep(upper + 0.006, upper - 0.004, z) * smoothstep(-0.075, -0.050, z) * smoothstep(-0.010, 0.020, x + 0.02)
        beard *= 1.0 - out["lip"]
        beard *= 1.0 - smoothstep(0.0018, 0.0002, np.abs(self.nostril_cut(v)))
        # thinner on the upper cheeks
        beard *= 1.0 - 0.6 * smoothstep(0.025, 0.040, z) * smoothstep(0.035, 0.05, ay)
        out["beard"] = np.clip(beard, 0, 1)
        out["cheek"] = gauss(np.linalg.norm((v - (0.090, 0.045, 0.040)) * (1, 1, 1), axis=1), 0, 0.020) + gauss(
            np.linalg.norm(v - (0.090, -0.045, 0.040), axis=1), 0, 0.020)
        out["nose"] = gauss(np.linalg.norm(v - self.nose_tip, axis=1), 0, 0.014)
        out["ear"] = np.maximum(smoothstep(0.0025, 0.0, self.ears(v)), 0.0) * (ay > 0.07)
        out["scalp"] = smoothstep(0.100, 0.130, z + 0.25 * np.maximum(-x, 0)) * (1 - smoothstep(0.09, 0.11, x))
        out["under_eye"] = np.zeros(len(v))
        for sgn in (1.0, -1.0):
            out["under_eye"] = np.maximum(out["under_eye"], gauss(np.linalg.norm((v - (self.eye_c * (1, sgn, 1) + (0.010, 0.0, -0.0115))) * (1.0, 0.7, 1.6), axis=1), 0, 0.0075))
        out["neck"] = smoothstep(-0.03, -0.07, z) * smoothstep(0.01, -0.02, x + 0.03)
        # T-zone (forehead, nose ridge, chin): slightly shinier
        out["tzone"] = np.maximum(gauss(ay, 0, 0.022) * smoothstep(0.03, 0.06, z) * smoothstep(0.08, 0.10, x), smoothstep(0.10, 0.13, z) * smoothstep(0.08, 0.1, x) * 0.6)
        out["ao"] = sdf_ao(lambda q: self.skin_sdf(q), v, n)
        return out


def sdf_ao(f, v, n, steps=(0.0015, 0.0035, 0.007, 0.012, 0.018), k=1.0):
    occ = np.zeros(len(v))
    w = 0.5
    for d in steps:
        occ += w * np.clip(d - f(v + n * d), 0.0, None) / d
        w *= 0.6
    return np.clip(1.0 - k * occ, 0.0, 1.0)


# --------------------------------------------------------------------------------------
# Hair and beard shells
# --------------------------------------------------------------------------------------

# Hairlines: (azimuth deg from the front, elevation deg of the hairline above the skull centre)
HAIRLINES = {
    "crop": ([0, 22, 40, 58, 70, 86, 105, 140, 180], [30, 28, 22, 2, -2, 6, -6, -28, -40]),
    "textured": ([0, 22, 40, 58, 70, 86, 105, 140, 180], [32, 30, 24, 6, 2, 8, -2, -24, -36]),
    "slick": ([0, 25, 45, 62, 72, 88, 108, 140, 180], [27, 24, 17, -4, -6, 5, -8, -30, -44]),
    "bun": ([0, 25, 45, 62, 72, 88, 108, 140, 180], [29, 26, 18, -2, -6, 4, -8, -32, -46]),
    "horseshoe": ([0, 30, 50, 70, 86, 105, 140, 180], [80, 70, 40, 2, 6, -6, -26, -38]),
    "buzz": ([0, 22, 40, 58, 70, 86, 105, 140, 180], [31, 29, 23, 3, -1, 7, -5, -27, -40]),
    "crew": ([0, 22, 40, 58, 70, 86, 105, 140, 180], [30, 28, 22, 2, -2, 6, -6, -28, -40]),
    "curly": ([0, 22, 40, 58, 70, 86, 105, 140, 180], [31, 29, 22, 4, 0, 8, -4, -26, -38]),
}


class Hair:
    def __init__(self, head, style):
        self.h = head
        self.style = style
        self.c = head.skull_c
        self.r = head.skull_r

    def coords(self, p):
        q = (p - self.c) / self.r
        az = np.degrees(np.arctan2(np.abs(q[:, 1]), q[:, 0]))
        el = np.degrees(np.arcsin(np.clip(q[:, 2] / np.maximum(np.linalg.norm(q, axis=1), 1e-9), -1, 1)))
        return az, el

    def thickness(self, p, az, el):
        st = self.style
        if st == "crop":
            # short on the sides and back, a little longer on top, neat edges
            tau = 0.0032 + 0.0050 * smoothstep(5.0, 45.0, el)
            tau += 0.0022 * gauss(el, 38.0, 14.0) * gauss(az, 0.0, 40.0)
            return tau
        if st == "textured":
            # skin fade on the sides, full textured top
            tau = 0.0012 + 0.0016 * smoothstep(-20.0, 10.0, el) + 0.0110 * smoothstep(18.0, 40.0, el)
            tau += 0.0050 * gauss(el, 42.0, 14.0) * gauss(az, 0.0, 35.0)
            return tau
        if st in ("slick", "bun"):
            tau = 0.0045 + 0.0070 * smoothstep(8.0, 48.0, el)
            if st == "slick":
                tau += 0.0070 * gauss(el, 40.0, 12.0) * gauss(az, 0.0, 38.0)
            else:
                tau = tau * 0.65  # pulled tight
            return tau
        if st == "horseshoe":
            return 0.0030 + 0.0012 * smoothstep(-30.0, 0.0, el)
        if st == "buzz":
            return np.full(len(p), 0.0027)
        if st == "crew":
            return 0.0020 + 0.0060 * smoothstep(10.0, 45.0, el) + 0.0020 * gauss(az, 0.0, 30.0) * smoothstep(20, 45, el)
        if st == "curly":
            return 0.0060 + 0.0060 * smoothstep(0.0, 40.0, el)
        return np.full(len(p), 0.003)

    def sdf(self, p):
        h = self.h
        az, el = self.coords(p)
        tbl_az, tbl_el = HAIRLINES[self.style]
        el_min = np.interp(az, tbl_az, tbl_el)
        e = np.radians(el - el_min)
        tau = self.thickness(p, az, el)
        if self.style == "horseshoe":
            # the hairline is a lower bound on the sides and back; the top is bald
            top = np.radians(28.0 + 10.0 * smoothstep(120.0, 180.0, az) - el)
            e = np.minimum(e, top)
        tau = np.maximum(tau * smoothstep(0.0, 0.12, e), 0.0026)  # a resolvable rounded rim at the hairline
        if self.style == "curly":
            # tight curls: a bumpy outer surface
            tau = tau + 0.0016 * (np.sin(p[:, 0] * 900.0) * np.sin(p[:, 1] * 900.0 + 1.3) * np.sin(p[:, 2] * 900.0 + 2.1))
        base = h.skin_sdf(p, with_eyes=False)
        d = base - tau
        d = hk.smax(d, -e * 0.10, 0.0030)
        # do not grow inside the head
        d = hk.smax(d, -(base + 0.0006), 0.0004)
        if self.style == "bun":
            # a low bun at the back of the head
            bun = ell(p, (-0.098, 0.0, 0.058), (0.026, 0.030, 0.024))
            bun = hk.smin(bun, ell(p, (-0.086, 0.0, 0.062), (0.020, 0.022, 0.020)), 0.010)
            d = hk.smin(d, bun, 0.010)
        return d

    def beard_sdf(self, p):
        """Short boxed beard and moustache (Silas)."""
        h = self.h
        base = h.skin_sdf(p, with_eyes=False)
        v = p
        x, y, z = v[:, 0], v[:, 1], v[:, 2]
        ay = np.abs(y)
        upper = 0.034 - 0.25 * np.maximum(ay - 0.032, 0.0) - 0.10 * np.maximum(0.05 - x, 0.0)
        region = smoothstep(upper + 0.003, upper - 0.003, z) * smoothstep(-0.072, -0.055, z) * smoothstep(-0.005, 0.015, x + 0.02)
        lips = h.lips(p)
        region *= smoothstep(-0.0005, 0.0030, lips)  # keep the lips clear
        # moustache band over the upper lip
        mz = h.mouth_z
        mo = smoothstep(0.004, 0.000, np.abs(z - (mz + 0.014)) - 0.004) * smoothstep(0.045, 0.030, ay) * smoothstep(0.098, 0.108, x)
        region = np.maximum(region, mo * smoothstep(-0.0005, 0.0025, lips))
        tau = 0.0045 * region + 0.0025 * smoothstep(0.0, 0.02, -z) * region
        d = base - tau
        d = hk.smax(d, 0.0015 - region * 0.004, 0.001)
        d = hk.smax(d, -(base + 0.0004), 0.0005)
        return d

    def bounds(self):
        lo, hi = self.h.bounds()
        if self.style == "bun":
            lo = lo + np.array([-0.02, 0, 0])
        return lo, hi


def style_has_mesh(style):
    return style not in ("bald",)
