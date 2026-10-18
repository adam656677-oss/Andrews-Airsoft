"""
Third-person tailored suit for Andrew's Airsoft ("Last Contract" story missions, and an optional
multiplayer outfit): a slim two-button jacket worn open with notch lapels, dress shirt and slim tie,
belt, slim trousers with a slight break over polished cap-toe shoes, plus a short slicked-back
hairstyle.  Everything is an original, generic design: no likeness of any person or character.

The suit is a set of rigid pieces, each attached to one UE5 Manny bone exactly like the team gear
(UAirsoftTeamGearComponent::ApplySuit): segments overlap at the joints so bends hide the gaps.

    python Tools/Blender/gear/build_suit.py                 # build, bake, export, JSON, renders
    python Tools/Blender/gear/build_suit.py -- Suit         # only this asset (Suit | HairSlick)
    flags: --res 4096|2048|1024 (texture scale, default 4096), --no-bake, --no-render,
           --renders-only, --lineup-only, --preview (flat-shaded shape check renders), --samples N

Outputs (Tools/Blender/CONVENTIONS.md):
    SourceAssets/Gear/<Id>/SM_<Id>_<Piece>.fbx + T_<Id>_<Piece>_{BC,N,ORM,M}.png
    Content/Airsoft/Data/Gear.json  (Assets.Suit / Assets.HairSlick with per-piece Anchors and an
                                     "Outfit" block, plus the top-level "Suit" block: colourways)
    Docs/Renders/Gear/Suit_*.jpg, Docs/Renders/Gear/_Suit_Lineup.jpg

Role mask: R = suit cloth (suit colourway; hair colour on HairSlick), G = shirt, B = tie and pocket
square.  Shoes, belt, buckle and buttons keep their real colours.
"""

import json
import math
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "common"))

import bpy  # noqa: E402,I001
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import bakekit as bk  # noqa: E402
import gearlib as gl  # noqa: E402
import handkit as hk  # noqa: E402
import studio  # noqa: E402
import suit_geo as sg  # noqa: E402
import teamgear_bake as tbk  # noqa: E402
import teamgear_body as tb  # noqa: E402
import teamgear_geo as tg  # noqa: E402
from suit_geo import A, _n, gauss, smoothstep  # noqa: E402

OUT_ROOT = os.path.join(gl.SOURCE_DIR, "Gear")
RENDER_DIR = os.path.join(gl.RENDER_DIR, "Gear")
SCRATCH = os.environ.get("SUIT_SCRATCH", os.path.join(os.environ.get("TMPDIR", "/tmp"), "suit"))


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------------------
# Tailoring parameters (metres)
# --------------------------------------------------------------------------------------

JACKET = dict(
    ease=0.019, thick=0.0042, hem=0.800, button_pt=1.090, gorge=1.452,
    # front edge (roll line above the button point, open hanging fronts below), lateral y by s
    edge_s=[0.800, 0.815, 0.840, 0.880, 0.960, 1.090, 1.300, 1.452, 1.600],
    edge_y=[0.132, 0.118, 0.104, 0.094, 0.084, 0.068, 0.064, 0.066, 0.070],
    neck_r=0.084, neck_r_back=0.066,
)
# torso segments: (piece, bone, s_lo, s_hi); neighbours overlap, the lower one sits 1.5 mm inside
TORSO_SEGMENTS = [("Chest", "spine_05", 1.160, 9.0), ("Waist", "spine_03", 0.995, 1.190), ("Hips", "pelvis", 0.0, 1.025)]
SHIRT = dict(ease=0.0065, bottom=0.965, neck_r=0.079, side=math.radians(82))


# --------------------------------------------------------------------------------------
# Builder (as in build_teamgear)
# --------------------------------------------------------------------------------------


class Builder:
    def __init__(self, aid, coll):
        self.aid = aid
        self.coll = coll
        self.parts = {}
        self.count = 0

    def add(self, M, zone, piece, smooth_angle=None):
        if M is None or not M.n:
            return None
        self.count += 1
        ob = tg.to_object(f"{self.aid}_{piece}_{self.count}", M, zone, self.coll, smooth_angle)
        self.parts.setdefault(piece, []).append(ob)
        return ob

    def finish(self):
        return {piece: tg.join(objs, f"SM_{self.aid}_{piece}") for piece, objs in self.parts.items()}


# --------------------------------------------------------------------------------------
# Jacket surface
# --------------------------------------------------------------------------------------


class Jacket:
    def __init__(self):
        J = JACKET
        body = sg.torso_body()
        S = sg.TorsoBody.S[:, None]
        TH = sg.TorsoBody.TH[None, :]
        c, s = np.cos(TH), np.sin(TH)
        R = body.R + J["ease"]
        # structured shoulders: a little pad over the shoulder point
        R = R + 0.003 * gauss(S, 1.43, 0.05) * np.abs(s) ** 4
        # drape: the cloth hangs from the chest and shoulder blades instead of following the waist
        chest = np.max(np.where((S >= 1.20) & (S <= 1.34), R, 0.0), axis=0, keepdims=True)
        wf, wb, ws = np.maximum(c, 0) ** 2, np.maximum(-c, 0) ** 2, s * s
        k = wf * (1 - 0.015 * gauss(S, 1.10, 0.12)) + wb * (1 - 0.075 * gauss(S, 1.10, 0.11)) + ws * (1 - 0.10 * gauss(S, 1.12, 0.10))
        drape = chest * k
        R = np.where(S < sg.S_SPLIT, np.maximum(R, drape), R)
        # skirt: never comes back in below the widest hip, slight flare to the hem
        hip = S[:, 0] < 0.975
        top = np.nonzero(~hip)[0][0]
        run = R[top].copy()
        for i in range(top - 1, -1, -1):
            run = np.maximum(run, R[i])
            R[i] = run
        R = R + 0.010 * smoothstep(0.95, 0.80, S)
        R = sg.box_smooth(R, 0, 5, 3)
        R = sg.box_smooth(R, 1, 5, 3, periodic=True)
        self.R = R
        self.surf = sg.TorsoSurface(R)
        es = np.array(J["edge_s"])
        self.edge_lat = sg.Lattice(es, np.array([0.0, 1.0]), np.stack([np.array(J["edge_y"])] * 2, -1), periodic=False)
        # front edge angle by s (left side, th > 0), tabulated
        self.es = np.arange(0.78, 1.70, 0.004)
        ye = np.interp(self.es, es, J["edge_y"])
        self.eth = self.surf.theta_for_y(ye, self.es, side=1.0)
        # neckline: where the cloth comes within neck_r of the neck axis
        # neckline: where the cloth comes within neck_r of the neck axis (tighter behind the neck)
        self.nl_th = np.radians(np.arange(0, 360.1, 2.0))
        ss = np.arange(1.30, 1.70, 0.002)
        tt, s2 = np.meshgrid(self.nl_th, ss, indexing="ij")
        d = sg.neck_dist(self.surf.point(tt, s2))
        nr = J["neck_r"] - (J["neck_r"] - J["neck_r_back"]) * np.maximum(-np.cos(self.nl_th), 0.0)[:, None] ** 1.2
        first = np.argmax(d <= nr, axis=1)
        self.nl_s = sg.box_smooth(ss[first], 0, 7, 2)

    def edge_theta(self, s):
        return np.interp(s, self.es, self.eth)

    def neckline(self, th):
        th = np.mod(th, 2 * math.pi)
        return np.interp(th, self.nl_th, self.nl_s)

    def grid(self, s_lo, s_hi, nt=96, du=0.011, side_lift=None):
        """Outer points / normals of the jacket body between s_lo and s_hi (clipped to hem and neckline).
        Columns run from the left front edge around the back to the right front edge."""
        J = JACKET
        t = np.linspace(0.0, 1.0, nt)
        e0 = self.edge_theta(np.array([1.2]))[0]
        th_ref = e0 + t * (2 * math.pi - 2 * e0)
        top = np.maximum(self.neckline(th_ref), J["gorge"])
        # near the front edges the top follows the gorge
        top = np.where((t < 0.02) | (t > 0.98), J["gorge"], top)
        top = sg.box_smooth(top, 0, 3, 2)
        lo = np.maximum(J["hem"], s_lo)
        hi = np.minimum(top, s_hi)
        span = float(np.max(hi - lo))
        nu = max(4, int(math.ceil(span / du)) + 1)
        u = np.linspace(0.0, 1.0, nu)[:, None]
        S = lo + (hi - lo)[None, :] * u
        th_e = self.edge_theta(S)
        TH = th_e + t[None, :] * (2 * math.pi - 2 * th_e)
        P = self.surf.point(TH, S)
        N = self.surf.normal(TH, S)
        return P, N, TH, S, (lo, hi)

    def lapel_map(self, side=1.0):
        """Surface map for the lapels: a = metres outward from the roll line, b = s."""
        surf = self

        def m(U, V, H):
            U, V, H = A(U), A(V), A(H)
            th_e = side * surf.edge_theta(V)
            sc = surf.surf.lateral_scale(th_e, V)
            th = th_e + side * U / sc
            P = surf.surf.point(th, V)
            N = surf.surf.normal(th, V)
            return P + N * H[:, None], N

        return m


# --------------------------------------------------------------------------------------
# Torso pieces
# --------------------------------------------------------------------------------------


def s_at_z(surf, th, z, s_lo=0.75, s_hi=1.68):
    """Torso-surface s at which the column th reaches height z (columns rise monotonically)."""
    ss = np.linspace(s_lo, s_hi, 400)
    th = np.atleast_1d(np.asarray(th, np.float64))
    z = np.atleast_1d(np.asarray(z, np.float64))
    th, z = np.broadcast_arrays(th, z)
    out = np.empty(th.shape)
    for k in np.ndindex(th.shape):
        zz = surf.point(np.full(len(ss), th[k]), ss)[:, 2]
        zz = np.maximum.accumulate(zz)
        out[k] = np.interp(z[k], zz, ss)
    return out


def build_torso(B):
    J = JACKET
    jk = Jacket()
    B.jacket = jk
    for piece, bone, s_lo, s_hi in TORSO_SEGMENTS:
        P, N, TH, S, (lo, hi) = jk.grid(s_lo, s_hi, nt=84, du=0.012)
        nu, nt = P.shape[:2]
        thick = np.full((nu, nt), J["thick"])
        # the lower segment tucks 1.5 mm under its upper neighbour; the upper one thins out over the overlap
        upper = {"Waist": 1.160, "Hips": 0.995}.get(piece)
        if upper:
            P = P - N * (0.0026 * smoothstep(upper - 0.004, upper + 0.006, S))[..., None]
        if s_lo > J["hem"]:
            # the upper segment eases in over its last 2.5 cm to meet the one underneath without a ledge
            P = P - N * (0.0022 * smoothstep(s_lo + 0.025, s_lo, S))[..., None]
            thick = thick * (0.3 + 0.7 * smoothstep(s_lo, s_lo + 0.025, S))
        is_top = s_hi > 2.0
        is_bot = s_lo < J["hem"]
        attrs = {"sd": np.ones((nu, nt)), "ss": TH * 0.15, "puv": np.stack([TH * 0.15, S, np.zeros_like(S)], -1)}
        M = sg.shell(P, N, thick, closed_t=False, band_rows=(4 if is_bot else 1, 2 if is_top else 1), band_cols=12, attrs=attrs)
        B.add(M, "wool", piece)
    build_lapels(B, jk)
    build_collar(B, jk)
    build_shirt(B, jk)


def lapel_outline():
    """Notch lapel (left side) in (a = metres outward from the roll line, b = s)."""
    J = JACKET
    bp, g = J["button_pt"], J["gorge"]
    pts = [(0.0, bp), (0.009, bp + 0.020), (0.027, bp + 0.075), (0.046, bp + 0.145), (0.060, 1.290), (0.068, 1.350),
           (0.072, 1.390), (0.069, 1.406),  # lapel point
           (0.052, 1.402),  # notch, lower side
           (0.045, 1.416),  # notch apex: the gorge seam starts here
           (0.022, g - 0.016), (0.0, g - 0.008)]
    return tg.fillet(np.array(pts), 0.004, 3)


def build_lapels(B, jk):
    J = JACKET
    ol = lapel_outline()
    for side in (1.0, -1.0):
        base = jk.lapel_map(side)

        def m(U, V, H, base=base):
            # the lapel rolls off the chest: lifted along the roll line, lying flat at its outer edge
            lift = 0.0035 * np.exp(-A(U) / 0.025) * smoothstep(J["button_pt"] + 0.02, J["button_pt"] + 0.12, A(V))
            return base(U, V, A(H) + lift)

        # split where the chest and waist segments meet so each part follows its own bone
        for piece, lo, hi in (("Waist", 0.0, 1.163), ("Chest", 1.163, 9.0)):
            pts = clip_poly_v(ol, lo, hi)
            if pts is None:
                continue
            M = tg.pillow(pts, 0.0036, m, n=64, kind="round", puff=0.0008, steps=3, inner=False,
                          face_insets=(0.0, 0.002, 0.005, 0.010), scales=(0.6, 0.3))
            B.add(M, "wool_edge", piece)


def clip_poly_v(P, lo, hi):
    """Clips a closed polygon to lo <= y <= hi (Sutherland-Hodgman on two half planes)."""
    def clip(poly, keep, inter):
        out = []
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            ka, kb = keep(a), keep(b)
            if ka:
                out.append(a)
            if ka != kb:
                out.append(inter(a, b))
        return out

    def iy(y):
        def f(a, b):
            t = (y - a[1]) / (b[1] - a[1])
            return (a[0] + (b[0] - a[0]) * t, y)
        return f

    poly = [tuple(p) for p in P]
    poly = clip(poly, lambda p: p[1] >= lo, iy(lo))
    if len(poly) < 3:
        return None
    poly = clip(poly, lambda p: p[1] <= hi, iy(hi))
    if len(poly) < 3:
        return None
    return np.array(poly)


def neck_out(P):
    """Unit direction away from the neck axis (perpendicular to it) at points P."""
    a, b = sg.NECK_AXIS
    ax = _n(b - a)
    v = P - a
    v = v - np.outer(v @ ax, ax)
    return _n(v), ax


def build_collar(B, jk):
    """Jacket collar: a short stand round the back of the neck folded over into a fall that lies on the
    jacket, narrowing at the front into the notch where it meets the lapel."""
    J = JACKET
    n = 56
    t = np.linspace(0.0, 1.0, n)
    e0 = jk.edge_theta(np.array([J["gorge"]]))[0]
    th = e0 + t * (2 * math.pi - 2 * e0)
    s_nl = np.maximum(jk.neckline(th), J["gorge"])
    s_nl = np.where((t < 0.02) | (t > 0.98), J["gorge"], s_nl)
    s_nl = sg.box_smooth(s_nl, 0, 5, 2)
    e = smoothstep(0.0, 0.18, t) * smoothstep(1.0, 0.82, t)  # 0 at the gorge ends, 1 round the back
    side = np.where(t < 0.5, 1.0, -1.0)
    Pn = jk.surf.point(th, s_nl)
    Nn = jk.surf.normal(th, s_nl)
    out, ax = neck_out(Pn)
    sc = jk.surf.lateral_scale(th, s_nl)
    th_L = th + side * (1 - e) * 0.044 / sc
    s_L = s_nl - (0.036 + 0.006 * e) * (0.5 + 0.5 * e) - (1 - e) * 0.010
    PL = jk.surf.point(th_L, s_L)
    NL = jk.surf.normal(th_L, s_L)
    stand = 0.014 * e
    # fold line: just above the neckline round the back, on the roll line at the gorge
    T = Pn + ax * stand[:, None] + Nn * (0.004 + 0.002 * e)[:, None] - out * (0.003 * e)[:, None]
    rings = []
    for i in range(n):
        L, Nl, Tp, B0, o, nn, ei = PL[i], NL[i], T[i], Pn[i], out[i], Nn[i], e[i]
        nm = _n(Nl + nn)
        f1 = L + (Tp - L) * 0.35 + nm * 0.0032
        f2 = L + (Tp - L) * 0.75 + nm * 0.0042
        To = Tp + ax * 0.0022 + nm * 0.0022
        Ti = Tp - o * 0.0032 * ei - nn * 0.0025 * (1 - ei)
        St = B0 + (Ti - B0) * 0.5 - o * 0.002 * ei
        Bb = B0 - nn * 0.0015
        U = B0 + (L - B0) * 0.6 + Nl * 0.0004
        rings.append(np.array([L + Nl * 0.0010, f1, f2, To, Ti, St, Bb, U]))
    B.add(sg.loft(rings, caps=True, attrs={"sd": [np.full(8, 0.004)] * n, "ss": [np.full(8, x * 0.5) for x in t]}), "wool_edge", "Chest")


def build_shirt(B, jk):
    """Shirt front (visible in the open jacket) with collar band, spread collar and tie."""
    body = sg.torso_body()
    S = sg.TorsoBody.S[:, None]
    TH = sg.TorsoBody.TH[None, :]
    R = body.R + SHIRT["ease"]
    chest = np.max(np.where((S >= 1.22) & (S <= 1.34), R, 0.0), axis=0, keepdims=True)
    c = np.maximum(np.cos(TH), 0) ** 3
    R = np.where(S < 1.28, np.maximum(R, chest * (1 - 0.06 * gauss(S, 1.08, 0.12)) * c + R * (1 - c)), R)
    R = sg.box_smooth(R, 0, 5, 3)
    R = sg.box_smooth(R, 1, 5, 3, periodic=True)
    ss = sg.TorsoSurface(R)
    B.shirt = ss
    th_n = np.radians(np.arange(-90, 90.1, 2.0))
    s_scan = np.arange(1.30, 1.70, 0.002)
    tt, s2 = np.meshgrid(th_n, s_scan, indexing="ij")
    d = sg.neck_dist(ss.point(tt, s2))
    nl = s_scan[np.argmax(d <= SHIRT["neck_r"], axis=1)]
    nl = sg.box_smooth(nl, 0, 5, 2)
    for piece, lo, hi in (("Waist", SHIRT["bottom"], 1.19), ("Chest", 1.16, 9.0)):
        nt = 40
        tcol = np.linspace(-SHIRT["side"], SHIRT["side"], nt)
        top = np.minimum(np.interp(tcol, th_n, nl), hi)
        bot = np.full(nt, lo)
        nu = max(4, int(math.ceil(float(np.max(top - bot)) / 0.014)) + 1)
        u = np.linspace(0, 1, nu)[:, None]
        Sg = bot[None, :] + (top - bot)[None, :] * u
        THg = np.broadcast_to(tcol[None, :], Sg.shape)
        P = ss.point(THg, Sg)
        N = ss.normal(THg, Sg)
        if piece == "Waist":
            P = P - N * (0.0016 * smoothstep(1.155, 1.17, Sg))[..., None]
        else:
            P = P - N * (0.0013 * smoothstep(lo + 0.02, lo, Sg))[..., None]
        # placket: a slight ridge down the centre front
        P = P + N * (0.0012 * gauss(THg * 0.13, 0.0, 0.012))[..., None]
        M = sg.shell(P, N, 0.002, inner=False)
        B.add(M, "shirt", piece)
    build_shirt_collar(B, ss)
    build_tie(B, ss)


NECK_COLLAR = dict(z0=1.474, back_rise=0.026, h=0.032, ease=0.0045)


def neck_frame():
    a, b = sg.NECK_AXIS
    return a, _n(b - a)


def shirt_collar_ring(theta, height=0.0, extra=0.0):
    """Shirt collar band: points round the neck at azimuth theta (0 = front), `height` above its base,
    which is low at the front and higher at the back."""
    a, ax = neck_frame()
    th = A(theta)
    z = NECK_COLLAR["z0"] + NECK_COLLAR["back_rise"] * (0.5 - 0.5 * np.cos(th))
    t = (z - a[2]) / ax[2]
    c = a + t[:, None] * ax
    e1 = _n(np.array([1.0, 0, 0]) - ax * ax[0])
    e2 = np.cross(ax, e1)
    d = np.outer(np.cos(th), e1) + np.outer(np.sin(th), e2)
    # the neck alone (the torso field would catch the trapezius at the sides), at least as far out as
    # the chest where it blends into the neck at the front, capped
    Fh, Ft = tb.field("head"), tb.field("torso")
    r = np.zeros(len(th))
    for hh in (0.0, NECK_COLLAR["h"] * 0.5, NECK_COLLAR["h"]):
        cc = c + ax * hh
        hit = tb.march(Fh, cc + d * 0.25, -d)
        rh = np.linalg.norm(hit - cc, axis=1)
        hit = tb.march(Ft, cc + d * 0.25, -d)
        rt = np.minimum(np.linalg.norm(hit - cc, axis=1), 0.075)
        r = np.maximum(r, np.maximum(rh, rt))
    r = sg.box_smooth(r, 0, 5, 2) if len(r) > 6 else r
    r = r + NECK_COLLAR["ease"] + A(extra)
    return c + d * r[:, None] + ax * A(height)[:, None], d


def build_shirt_collar(B, ss):
    nc = NECK_COLLAR
    a, ax = neck_frame()
    # band (stand), open under the knot
    th = np.linspace(math.radians(9), math.radians(351), 64)
    H = nc["h"] * (0.88 + 0.12 * (0.5 - 0.5 * np.cos(th)))
    rows = [shirt_collar_ring(th, H * f, 0.0015 * f)[0] for f in np.linspace(0, 1, 5)]
    P = np.stack(rows)
    N = np.broadcast_to(shirt_collar_ring(th)[1][None], P.shape)
    B.add(sg.shell(P, N, 0.0022, band_rows=(1, 1), band_cols=1), "shirt", "Chest")
    # leaves: folded over the band, spreading into collar points over the chest at the front
    for side in (1.0, -1.0):
        al = np.linspace(math.radians(7), math.radians(180), 40)
        al = al if side > 0 else 2 * math.pi - al
        fr = np.maximum(np.cos(al), 0.0) ** 2
        Ht = nc["h"] * (0.88 + 0.12 * (0.5 - 0.5 * np.cos(al)))
        T, d = shirt_collar_ring(al, Ht + 0.002, 0.004)
        spread = side * np.radians(38) * fr
        Lb, dL = shirt_collar_ring(al + spread, -0.006 - 0.046 * fr, 0.006 + 0.012 * fr)
        cols = []
        for f in np.linspace(0, 1, 7):
            bul = math.sin(math.pi * min(1.0, f * 1.4)) * 0.004
            cols.append(T + (Lb - T) * f + (d * (1 - f) + dL * f) * bul)
        P = np.stack(cols)
        N = np.stack([d * (1 - f) + dL * f for f in np.linspace(0, 1, 7)])
        B.add(sg.shell(P, N, 0.0018, band_rows=(1, 2), band_cols=2), "shirt", "Chest")


def build_tie(B, ss):
    """Slim tie: four-in-hand knot at the collar, blade down to just above the belt."""
    a, ax = neck_frame()
    top, d = shirt_collar_ring(np.array([0.0]), NECK_COLLAR["h"] * 0.93, 0.010)
    top = top[0]
    fwd = d[0]
    knot_len = 0.046
    bot = top - ax * knot_len + fwd * 0.004
    # knot: tapered rounded block, a soft inverted triangle seen from the front
    axis = _n(bot - top)
    across = np.array([0.0, 1.0, 0.0])
    depth = _n(np.cross(across, axis))
    if depth @ fwd < 0:
        depth = -depth
    rings = []
    for f in np.linspace(0, 1, 9):
        w = 0.0185 - 0.0115 * f ** 0.9
        dp = 0.0085 - 0.003 * f
        c = top + (bot - top) * f + depth * (0.004 * math.sin(math.pi * f))
        sec = sg.superellipse(14, w, dp, 0.55)
        rings.append(c + np.outer(sec[:, 0], across) + np.outer(sec[:, 1], depth))
    B.add(sg.loft(rings), "silk", "Chest")
    # blade
    z_top, z_tip = bot[2] + 0.006, 1.005
    zs = np.array([z_tip, z_tip + 0.026, 1.20, z_top - 0.03, z_top])
    hw = np.array([0.0, 0.0305, 0.029, 0.019, 0.015])
    left = [(hw[i], zs[i]) for i in range(1, 5)]
    pts = [(0.0, z_tip)] + left + [(-x, z) for x, z in left[::-1]]
    ol = tg.fillet(np.array(pts), 0.003, 3)
    s_lut_z = np.linspace(0.95, 1.50, 200)
    s_lut_s = s_at_z(ss, 0.0, s_lut_z)

    def m(U, V, H):
        U, V, H = A(U), A(V), A(H)
        sv = np.interp(V, s_lut_z, s_lut_s)
        sc = ss.lateral_scale(np.zeros_like(sv), sv)
        th = U / sc
        P = ss.point(th, sv)
        N = ss.normal(th, sv)
        # hangs straight: stands off where the shirt curves away below the chest, tucks under the knot
        hang = np.interp(V, [z_tip, 1.15, 1.30, z_top - 0.02, z_top], [0.011, 0.007, 0.004, 0.006, 0.010])
        return P + N * (H + hang)[:, None], N

    M = tg.pillow(ol, 0.0040, m, n=60, kind="round", puff=0.0015, steps=3, inner=False, face_insets=(0.0, 0.002, 0.005, 0.01),
                  scales=(0.6, 0.3))
    B.add(M, "silk", "Chest")


# --------------------------------------------------------------------------------------
# Limbs: sleeves and trouser legs
# --------------------------------------------------------------------------------------


def limb_grid(surf, v_bot, v_top, nt, dv, th0=0.0):
    """Closed tube grid on a LimbSurface between per-column v_bot(th) and v_top(th)."""
    th = th0 + np.linspace(0.0, 2 * math.pi, nt, endpoint=False)
    vb, vt = v_bot(th), v_top(th)
    nu = max(4, int(math.ceil(float(np.max(vt - vb)) / dv)) + 1)
    u = np.linspace(0.0, 1.0, nu)[:, None]
    V = vb[None, :] + (vt - vb)[None, :] * u
    TH = np.broadcast_to(th[None, :], V.shape)
    return surf.point(TH, V), surf.normal(TH, V), TH, V


def inside_jacket(jk, Q, margin=0.0):
    """True where points Q are inside the jacket's outer surface (torso ray parametrisation)."""
    Q = np.asarray(Q, np.float64)
    x, y, z = Q[..., 0] - sg.TORSO_AXIS_X, Q[..., 1], Q[..., 2]
    hr = np.hypot(x, y)
    th = np.arctan2(y, x)
    phi = np.where(z > sg.S_SPLIT, np.arctan2(z - sg.S_SPLIT, hr), 0.0)
    s = np.where(z > sg.S_SPLIT, sg.S_SPLIT + phi * sg.R_REF, z)
    r = np.where(z > sg.S_SPLIT, np.hypot(hr, z - sg.S_SPLIT), hr)
    return r < jk.surf.lat(th, s) - margin


SLEEVE = dict(ease=0.017, top_r=0.074, elbow_r=0.060, hem_r=0.047, thick=0.0036, hem_back=0.006)
TROUSER = dict(ease=0.013, top_r=0.104, knee_r=0.067, hem_r=0.058, thick=0.0032)


def build_sleeves(B):
    jk = getattr(B, "jacket", None) or Jacket()
    sh, el, wr = tb.bone("upperarm_l"), tb.bone("lowerarm_l"), tb.bone("hand_l")
    Fa = sg.field("arm_l")
    up_len = float(np.linalg.norm(el - sh))
    fo_len = float(np.linalg.norm(wr - el))
    # upper sleeve: from inside the jacket shoulder to just past the elbow
    lb = sg.LimbBody(Fa, sh, el, (1.0, 0.0, 0.0), -0.08, up_len + 0.06)
    V = lb.V[:, None]
    prof = np.interp(V, [-0.08, 0.0, 0.10, up_len, up_len + 0.06], [SLEEVE["top_r"] + 0.004, SLEEVE["top_r"], SLEEVE["top_r"] - 0.004,
                                                                   SLEEVE["elbow_r"], SLEEVE["elbow_r"] - 0.001])
    R = np.maximum(lb.R + SLEEVE["ease"], prof)
    R = sg.box_smooth(sg.box_smooth(R, 0, 7, 3), 1, 5, 2, periodic=True)
    up = lb.surface(R)
    # top edge: where the sleeve comes out of the jacket, plus 1.5 cm tucked inside it
    ths = np.radians(np.arange(0, 360, 5.0))
    vs = np.arange(-0.08, 0.14, 0.003)
    tt, vv = np.meshgrid(ths, vs, indexing="ij")
    ins = inside_jacket(jk, up.point(tt, vv), 0.002)
    first_out = np.array([vs[np.argmax(~row)] if np.any(~row) else vs[-1] for row in ins])
    v_top_tab = np.clip(first_out - 0.016, -0.075, 0.12)
    v_top_tab = sg.box_smooth(v_top_tab, 0, 5, 2, periodic=True)

    def v_top(th):
        return np.interp(np.mod(th, 2 * math.pi), np.concatenate([ths, [2 * math.pi]]), np.concatenate([v_top_tab, v_top_tab[:1]]))

    P, N, TH, Vg = limb_grid(up, v_top, lambda th: np.full(th.shape, up_len + 0.055), 28, 0.014)
    P, N = P[::-1], N[::-1]  # rows from the bottom (elbow) up
    M = sg.shell(P, N, SLEEVE["thick"], closed_t=True, band_rows=(1, 0), rims=(True, False, False, False))
    B.add(M, "wool", "UpperArmL")
    # lower sleeve: from inside the upper sleeve to the wrist; the cuff is cut slightly longer behind
    lb2 = sg.LimbBody(Fa, el, wr, (1.0, 0.0, 0.0), -0.07, fo_len + 0.03)
    V = lb2.V[:, None]
    prof = np.interp(V, [-0.07, 0.0, 0.08, fo_len], [SLEEVE["elbow_r"] - 0.005, SLEEVE["elbow_r"] - 0.005, SLEEVE["elbow_r"] - 0.007, SLEEVE["hem_r"]])
    R = np.maximum(lb2.R + SLEEVE["ease"] - 0.003, prof)
    R = np.minimum(R, np.where(V < 0.03, SLEEVE["elbow_r"] - 0.004, 1.0))
    R = sg.box_smooth(sg.box_smooth(R, 0, 7, 3), 1, 5, 2, periodic=True)
    lo = lb2.surface(R)
    B.forearm = (lb2, lo, fo_len)

    def v_hem(th):
        # th = 0 points forward (thumb side in the A-pose), pi the back of the arm
        return fo_len - 0.008 + SLEEVE["hem_back"] * (0.5 - 0.5 * np.cos(th))

    P, N, TH, Vg = limb_grid(lo, lambda th: np.full(th.shape, -0.065), v_hem, 26, 0.014)
    M = sg.shell(P, N, SLEEVE["thick"], closed_t=True, band_rows=(0, 3), rims=(False, True, False, False))
    B.add(M, "wool", "ForearmL")
    # shirt cuff showing past the sleeve
    Rc = np.minimum(R - 0.0055, R)
    cu = lb2.surface(Rc)
    P, N, TH, Vg = limb_grid(cu, lambda th: v_hem(th) - 0.035, lambda th: v_hem(th) + 0.013, 24, 0.008)
    B.add(sg.shell(P, N, 0.0028, closed_t=True, band_rows=(0, 3), rims=(False, True, False, False)), "shirt", "ForearmL")
    # sleeve buttons: four, kissing, on the back of the cuff
    for k in range(4):
        v = fo_len - 0.030 - k * 0.0135
        th = math.radians(200)
        p = lo.point(np.array([th]), np.array([v]))[0]
        n = lo.normal(np.array([th]), np.array([v]))[0]
        B.add(button(p, n, 0.0068, 0.0028), "button", "ForearmL", smooth_angle=50)


def button(p, n, r, h):
    """Small four-hole suit button (lathe) sitting on a surface point p with normal n."""
    prof = [(0.0, 0.0), (r * 0.95, 0.0), (r, h * 0.35), (r * 0.92, h * 0.8), (r * 0.7, h), (r * 0.62, h * 0.82), (0.0, h * 0.7)]
    M = tg.lathe(prof, 20, axis=n, center=p - n * 0.0004)
    return M


def build_trousers(B):
    # seat and waistband (pelvis)
    body = sg.torso_body()
    S = sg.TorsoBody.S[:, None]
    TH = sg.TorsoBody.TH[None, :]
    R = body.R + 0.010
    run = R[np.searchsorted(sg.TorsoBody.S, 0.93)].copy()
    i0 = np.searchsorted(sg.TorsoBody.S, 0.93)
    for i in range(i0, -1, -1):  # no undercut below the seat
        run = np.maximum(run * 0.995, R[i])
        R[i] = run
    R = sg.box_smooth(sg.box_smooth(R, 0, 5, 3), 1, 5, 3, periodic=True)
    ts = sg.TorsoSurface(R)
    B.trouser_top = ts
    nt = 72
    th = np.linspace(0, 2 * math.pi, nt, endpoint=False)
    lo, hi = 0.835, 1.005
    nu = int(math.ceil((hi - lo) / 0.012)) + 1
    Sg, THg = np.meshgrid(np.linspace(lo, hi, nu), th, indexing="ij")
    P, N = ts.point(THg, Sg), ts.normal(THg, Sg)
    B.add(sg.shell(P, N, 0.003, closed_t=True, band_rows=(0, 2), rims=(False, True, False, False)), "wool", "Hips")
    build_belt(B, ts)
    # legs
    th_, kn, an = tb.bone("thigh_l"), tb.bone("calf_l"), tb.bone("foot_l")
    Fl = sg.field("leg_l")
    tl = float(np.linalg.norm(kn - th_))
    lb = sg.LimbBody(Fl, th_, kn, (1.0, 0.0, 0.0), -0.13, tl + 0.07)
    V = lb.V[:, None]
    T = TROUSER
    prof = np.interp(V, [-0.13, 0.0, 0.12, tl], [T["top_r"] + 0.006, T["top_r"], T["top_r"] - 0.010, T["knee_r"]])
    R = np.maximum(lb.R + T["ease"], prof)
    # pressed crease down the front
    R = R + 0.0028 * gauss(lb.TH[None, :], 0.0, 0.07) + 0.0028 * gauss(lb.TH[None, :], 2 * math.pi, 0.07)
    R = sg.box_smooth(R, 0, 7, 3)
    up = lb.surface(R)
    P, N, _, _ = limb_grid(up, lambda t: np.full(t.shape, -0.12), lambda t: np.full(t.shape, tl + 0.065), 32, 0.016, th0=-math.pi)
    B.add(sg.shell(P, N, T["thick"], closed_t=True, inner=False), "wool", "ThighL")
    # shin with a slight break over the shoe
    cl = float(np.linalg.norm(an - kn))
    lb2 = sg.LimbBody(Fl, kn, an, (1.0, 0.0, 0.0), -0.075, cl + 0.02)
    V = lb2.V[:, None]
    prof = np.interp(V, [-0.075, 0.0, cl], [T["knee_r"] - 0.005, T["knee_r"] - 0.005, T["hem_r"]])
    R = np.maximum(lb2.R + T["ease"] - 0.002, prof)
    R = np.minimum(R, np.where(V < 0.04, T["knee_r"] - 0.004, 1.0))
    TH2 = lb2.TH[None, :]
    front = np.maximum(np.cos(TH2), 0.0) ** 2
    # the break: the front of the leg folds once just above the hem
    R = R + 0.0055 * front * gauss(V, cl - 0.045, 0.014) - 0.002 * front * gauss(V, cl - 0.022, 0.008)
    R = R + 0.0026 * gauss(TH2, 0.0, 0.07) * (1 - smoothstep(cl - 0.08, cl - 0.04, V)) + 0.0026 * gauss(TH2, 2 * math.pi, 0.07)
    R = sg.box_smooth(R, 1, 3, 1, periodic=True)
    sh_ = lb2.surface(R)

    def v_hem(t):
        # hem height above the floor: rests on the shoe at the front, a little higher at the heel
        zt = 0.056 + 0.040 * (0.5 + 0.5 * np.cos(t))
        a = lb2.a[2]
        return (a - zt) / max(-lb2.ax[2], 1e-3)

    P, N, _, _ = limb_grid(sh_, lambda t: np.full(t.shape, -0.07), v_hem, 32, 0.016, th0=-math.pi)
    B.add(sg.shell(P, N, T["thick"], closed_t=True, band_rows=(0, 3), rims=(False, True, False, False)), "wool", "ShinL")
    B.shin = sh_


def build_belt(B, ts):
    """Leather belt on the waistband: strap, buckle, tongue and loops."""
    zc, w, th_ = 0.986, 0.032, 0.0036
    nt = 96
    t = np.linspace(0, 2 * math.pi, nt, endpoint=False)
    rows = [ts.point(t, np.full(nt, z)) + ts.normal(t, np.full(nt, z)) * 0.0012 for z in np.linspace(zc - w / 2, zc + w / 2, 4)]
    P = np.stack(rows)
    N = np.stack([ts.normal(t, np.full(nt, z)) for z in np.linspace(zc - w / 2, zc + w / 2, 4)])
    P = P + N * th_
    B.add(sg.shell(P, N, th_, closed_t=True, band_rows=(1, 1)), "leather_belt", "Hips")
    # tongue past the buckle on the wearer's left, on top of the strap
    ol = tg.rrect(0.075, w - 0.002, 0.012, 4, 0.050, 0.0)

    def m(U, V, H):
        U, V, H = A(U), A(V), A(H)
        sc = ts.lateral_scale(np.zeros_like(U), np.full(len(U), zc))
        th = U / sc
        Pp = ts.point(th, zc + V)
        Nn = ts.normal(th, zc + V)
        return Pp + Nn * (H + th_ + 0.0012)[:, None], Nn

    B.add(tg.pillow(ol, 0.0032, m, n=48, kind="round", steps=2, inner=True), "leather_belt", "Hips")
    # buckle: a rounded rectangular frame, polished steel
    c = ts.point(np.array([0.0]), np.array([zc]))[0]
    n = ts.normal(np.array([0.0]), np.array([zc]))[0]
    base = c + n * (th_ + 0.0012 + 0.0035)
    bw, bh = 0.044, 0.040
    ring = tg.rrect(bw, bh, 0.006, 4)
    ring_in = tg.rrect(bw - 0.009, bh - 0.009, 0.003, 4)
    yax = np.array([0.0, 1.0, 0.0])
    zax = np.array([0.0, 0.0, 1.0])
    rings = []
    for (o, h) in ((ring, 0.0), (ring, 0.0045), (ring_in, 0.0045), (ring_in, 0.0)):
        rings.append(base + np.outer(o[:, 0], yax) + np.outer(o[:, 1], zax) + n * (h - 0.002))
    M = tg.Mesh()
    k = len(ring)
    ids = [M.add_verts(r) for r in rings]
    for a, b in zip(ids, ids[1:] + ids[:1]):
        for j in range(k):
            j2 = (j + 1) % k
            M.f.append((a + j, a + j2, b + j2, b + j))
    sg.orient_outward(M, lambda cc: base + n * 0.0003 + 0 * cc)
    # orientation by centre fails for a ring: fix faces of the inner wall to point inwards
    B.add(fix_ring(M, base, n), "steel", "Hips", smooth_angle=45)
    # prong
    B.add(tg.cyl(base - zax * 0.0 + yax * 0.006 + n * 0.002, base + yax * -0.016 + n * 0.003, 0.0016, 8), "steel", "Hips", smooth_angle=45)
    # belt loops
    for deg in (-40, 40, -105, 105, 180):
        a_ = math.radians(deg)
        lp = tg.rrect(0.010, w + 0.010, 0.003, 2, 0.0, 0.0)

        def ml(U, V, H, a_=a_):
            U, V, H = A(U), A(V), A(H)
            sc = ts.lateral_scale(np.full(len(U), a_), np.full(len(U), zc))
            th = a_ + U / sc
            Pp = ts.point(th, zc + V)
            Nn = ts.normal(th, zc + V)
            return Pp + Nn * (H + th_ + 0.0012)[:, None], Nn

        B.add(tg.pillow(lp, 0.0022, ml, n=24, kind="round", steps=2, inner=False), "wool", "Hips")


def fix_ring(M, c, n):
    """Orients the faces of a closed frame (buckle) away from its own wall mid-surface."""
    V, F, _ = M.arrays()
    newf = []
    for f in F:
        p = V[list(f)]
        fc = p.mean(axis=0)
        fn = np.cross(p[2] - p[0], p[3] - p[1])
        rel = fc - c
        rel_ip = rel - n * (rel @ n)
        # reference: the frame's mid-surface below/above, radially in the middle of the wall
        ref = c + n * (0.0003) + rel_ip * 0.92
        if fn @ (fc - ref) < 0:
            f = f[::-1]
        newf.append(tuple(f))
    M.f = newf
    return M


def jacket_patch_map(jk, th0, s0):
    """Local metric map on the jacket around (th0, s0): U across (towards +th), V up (s)."""
    def m(U, V, H):
        U, V, H = A(U), A(V), A(H)
        sv = s0 + V
        sc = jk.surf.lateral_scale(np.full(len(U), th0), sv)
        th = th0 + U / sc
        P = jk.surf.point(th, sv)
        N = jk.surf.normal(th, sv)
        return P + N * H[:, None], N
    return m


def build_details(B):
    jk = B.jacket
    J = JACKET
    # buttons on the wearer's right front (-Y), two-button
    for z, piece in ((J["button_pt"] - 0.004, "Waist"), (J["button_pt"] - 0.104, "Hips")):
        th_e = -jk.edge_theta(np.array([z]))[0]
        sc = jk.surf.lateral_scale(np.array([th_e]), np.array([z]))[0]
        th = th_e - 0.024 / sc
        p = jk.surf.point(np.array([th]), np.array([z]))[0]
        n = jk.surf.normal(np.array([th]), np.array([z]))[0]
        B.add(button(p, n, 0.0095, 0.0036), "button", piece, smooth_angle=50)
    # flap pockets on the hips
    for side in (1.0, -1.0):
        th0 = side * math.radians(64)
        m = jacket_patch_map(jk, th0, 0.928)
        ol = tg.rrect(0.150, 0.052, 0.006, 3, 0.0, -0.024)
        ol[:, 1] = np.where(ol[:, 1] < -0.02, ol[:, 1] - 0.004 * np.cos(ol[:, 0] / 0.075 * math.pi / 2), ol[:, 1])
        B.add(tg.pillow(ol, 0.0028, m, n=56, kind="round", puff=0.0006, steps=2, inner=False, face_insets=(0.0, 0.002, 0.005), scales=(0.5,)),
              "wool_edge", "Hips")
    # chest welt pocket (wearer's left), tilted up towards the arm, with a pocket square
    th0 = math.radians(44)
    m = jacket_patch_map(jk, th0, 1.255)
    ol = np.array([(-0.050, -0.012), (0.050, -0.006), (0.050, 0.014), (-0.050, 0.008)])
    ol = tg.fillet(ol, 0.003, 2)
    B.add(tg.pillow(ol, 0.0026, m, n=40, kind="round", steps=2, inner=False, face_insets=(0.0, 0.002, 0.004), scales=(0.5,)), "wool_edge", "Chest")
    sq = tg.fillet(np.array([(-0.034, 0.006), (0.030, 0.012), (0.032, 0.022), (0.004, 0.030), (-0.020, 0.024), (-0.036, 0.016)]), 0.003, 2)
    B.add(tg.pillow(sq, 0.0022, offset_map(m, dh=0.0012), n=36, kind="round", steps=2, inner=False, face_insets=(0.0, 0.002), scales=(0.5,)),
          "pocket_sq", "Chest")
    # back vent: the right panel laps over the left from the hem up to the waist
    m = jacket_patch_map(jk, math.pi, 0.80)
    ol = np.array([(-0.004, 0.0), (0.022, 0.0), (0.022, 0.20), (0.010, 0.215), (-0.004, 0.215)])
    ol = tg.fillet(ol, 0.004, 2)
    B.add(tg.pillow(ol, 0.0024, m, n=48, kind="round", steps=2, inner=False, face_insets=(0.0, 0.002, 0.004), scales=(0.5,)), "wool_edge", "Hips")


def offset_map(mapf, du=0.0, dv=0.0, dh=0.0):
    def m(U, V, H):
        return mapf(A(U) + du, A(V) + dv, A(H) + dh)
    return m


# --------------------------------------------------------------------------------------
# Preview (flat shading) for shape iteration
# --------------------------------------------------------------------------------------

PREVIEW_COL = {"wool": (0.035, 0.036, 0.04), "wool_edge": (0.04, 0.041, 0.046), "shirt": (0.02, 0.02, 0.022), "silk": (0.012, 0.012, 0.013),
               "lining": (0.02, 0.02, 0.024), "leather": (0.01, 0.01, 0.011), "sole": (0.01, 0.008, 0.007), "steel": (0.6, 0.6, 0.62),
               "button": (0.015, 0.015, 0.016), "hair": (0.02, 0.016, 0.013), "pocket_sq": (0.3, 0.3, 0.3), "leather_belt": (0.012, 0.011, 0.011)}


def preview_materials(obs, white_shirt=False):
    for ob in obs:
        for slot in ob.material_slots:
            z = slot.material.name[2:] if slot.material and slot.material.name.startswith("Z_") else "wool"
            name = "PV_" + z
            m = bpy.data.materials.get(name)
            if m is None:
                col = PREVIEW_COL.get(z, (0.5, 0.5, 0.5))
                if os.environ.get("SUIT_DEBUG_COLS"):
                    col = {"shirt": (0.7, 0.7, 0.68), "silk": (0.5, 0.02, 0.02), "wool_edge": (0.06, 0.12, 0.25)}.get(z, col)
                if z == "shirt" and white_shirt:
                    col = (0.7, 0.7, 0.68)
                rough = {"leather": 0.18, "silk": 0.35, "steel": 0.25, "button": 0.3, "sole": 0.6}.get(z, 0.7)
                m = gl.simple_mat(name, col, rough, 1.0 if z == "steel" else 0.0)
            slot.material = m


def mannequin(coll, color=(0.22, 0.22, 0.23)):
    F, v, q = tb.mannequin_mesh(0.007)
    q = gl.fix_winding(v, q, F)
    ob = gl.mesh_object("Mannequin", v, q, coll)
    m = bpy.data.materials.new("Mannequin")
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = 0.45
    ob.data.materials.append(m)
    return ob


def noir_rig():
    """Moody studio: warm key, cool teal rim from behind, dark blue-grey surround."""
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.render.film_transparent = False
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    scn.view_settings.exposure = 0.0
    world = bpy.data.worlds.new("Noir")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.010, 0.016, 0.020, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    scn.world = world
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.sensor_width = 36
    scn.collection.objects.link(cam)
    scn.camera = cam

    def area(name, color, energy, size, loc, target=(0, 0, 1.1), sy=None):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "RECTANGLE"
        ld.color = color
        ld.energy = energy
        ld.size = size
        ld.size_y = sy or size
        lo = bpy.data.objects.new(name, ld)
        scn.collection.objects.link(lo)
        lo.location = loc
        studio.look_at(lo, target)
        return lo

    lights = {
        "key": area("Key", (1.0, 0.80, 0.58), 70.0, 1.2, (2.2, -1.6, 2.4), sy=0.9),
        "rim_l": area("RimL", (0.35, 0.85, 1.0), 140.0, 0.35, (-1.8, 1.6, 2.0), sy=2.0),
        "rim_r": area("RimR", (0.40, 0.80, 1.0), 100.0, 0.35, (-1.8, -1.9, 1.8), sy=2.0),
        "fill": area("Fill", (0.55, 0.70, 0.95), 10.0, 2.0, (2.5, 2.0, 1.0)),
        "top": area("Top", (1.0, 0.9, 0.8), 20.0, 0.8, (0.3, 0.0, 3.2)),
    }
    # wet dark floor with a soft gradient backdrop
    floor = bpy.data.objects.new("Floor", bpy.data.meshes.new("Floor"))
    floor.data.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [(0, 1, 2, 3)])
    fm = bpy.data.materials.new("Floor")
    b = fm.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.012, 0.014, 0.016, 1)
    b.inputs["Roughness"].default_value = 0.32
    floor.data.materials.append(fm)
    scn.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", bpy.data.meshes.new("Wall"))
    wall.data.from_pydata([(-6, -20, 0), (-6, 20, 0), (-6, 20, 10), (-6, -20, 10)], [], [(0, 1, 2, 3)])
    wm = bpy.data.materials.new("Wall")
    nt = wm.node_tree
    b = nt.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.02, 0.05, 0.06, 1)
    b.inputs["Roughness"].default_value = 0.9
    b.inputs["Emission Color"].default_value = (0.03, 0.10, 0.12, 1)
    b.inputs["Emission Strength"].default_value = 0.35
    wall.data.materials.append(wm)
    scn.collection.objects.link(wall)
    return {"cam": cam, "lights": lights}


def place_cam(cam, target, view_dir, dist, lens=50):
    cam.data.lens = lens
    vd = Vector(view_dir).normalized()
    cam.location = Vector(target) + vd * dist
    studio.look_at(cam, target)


def render(path, res, samples):
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.cycles.samples = samples
    scn.cycles.use_adaptive_sampling = True
    scn.cycles.adaptive_threshold = 0.03
    scn.cycles.max_bounces = 6
    scn.cycles.use_denoising = True
    scn.render.image_settings.file_format = "PNG"
    scn.render.image_settings.color_mode = "RGB"
    scn.render.use_persistent_data = True
    th = int(os.environ.get("SUIT_THREADS", "0"))
    if th:
        scn.render.threads_mode = "FIXED"
        scn.render.threads = th
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"


def preview(builders, tag, samples=12, views=None):
    reset_scene()
    coll = bpy.data.collections.new("P")
    bpy.context.scene.collection.children.link(coll)
    B = Builder("Suit", coll)
    for fn in builders:
        fn(B)
    obs = list(B.finish().values())
    for ob in obs:
        log(f"  {ob.name}: {tg.tri_count(ob)} tris")
    preview_materials(obs)
    mannequin(coll)
    rig = noir_rig()
    os.makedirs(SCRATCH, exist_ok=True)
    views = views or {"front": ((1.0, -0.12, 0.10), (0, 0, 1.10), 3.1), "back": ((-1.0, -0.25, 0.12), (0, 0, 1.10), 3.1),
                      "tq": ((0.8, -0.75, 0.15), (0, 0, 1.15), 3.0)}
    for name, (vd, tgt, dist) in views.items():
        place_cam(rig["cam"], tgt, vd, dist, 50)
        p = os.path.join(SCRATCH, f"pv_{name}.png")
        render(p, (640, 900), samples)
        log("wrote", p)


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    if "--preview" in flags:
        views = None
        if "--close" in flags:
            views = {"cfront": ((1.0, -0.15, 0.12), (0.05, 0, 1.36), 1.1), "cback": ((-1.0, -0.3, 0.3), (0, 0, 1.40), 1.1),
                     "ctq": ((0.7, -0.8, 0.2), (0.05, 0, 1.36), 1.1)}
        preview([build_torso, build_sleeves, build_trousers, build_details], "suit", views=views)
        return


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--" in a:
        a = a[a.index("--") + 1:]
    main(a)
