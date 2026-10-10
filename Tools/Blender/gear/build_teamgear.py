"""
Third-person airsoft team gear for Andrew's Airsoft: plate carrier, bump helmet, soft cap,
full-seal goggles, mesh lower-face mask, team armband and knee pads.  Every player's
third-person body wears a set (UAirsoftTeamGearComponent); the team colour comes from the
Accent (blue) channel of each piece's role mask, the kit colourway from Primary/Secondary.
All designs are original and carry no brand names, logos or markings.

    python Tools/Blender/gear/build_teamgear.py                    # all assets: build, bake, export, JSON, renders
    python Tools/Blender/gear/build_teamgear.py -- Helmet Goggles  # only these assets
    flags: --res 4096|2048|1024 (texture scale, default 4096), --no-bake, --no-render,
           --renders-only (product shots + lineup from the exported FBX/textures),
           --lineup-only, --samples N

Outputs (Tools/Blender/CONVENTIONS.md):
    SourceAssets/Gear/<Id>/SM_<Id>_<Piece>.fbx + T_<Id>_<Piece>_{BC,N,ORM,M}.png
    Content/Airsoft/Data/Gear.json  (Assets.<Id> with Pieces/Points/Bounds + Anchor + TeamGear,
                                     and the top-level "TeamGear" block: colourways, variant slots)
    Docs/Renders/Gear/<Id>.jpg, Docs/Renders/Gear/_TeamGear_Lineup.jpg

Space: each piece is modelled in character space (+X forward, +Z up, Blender +Y = the
character's left) and exported with its origin at its anchor bone's pivot in the assumed
UE5 Manny reference pose (teamgear_body.SKEL).  The runtime places it from the skeleton's
reference pose, so bone local axes never matter; Anchor.Offset/Rotation/Scale are tuned
live with `airsoft.gear.tune`.
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
import studio  # noqa: E402
import teamgear_bake as tbk  # noqa: E402
import teamgear_body as tb  # noqa: E402
import teamgear_geo as tg  # noqa: E402
from teamgear_body import deg  # noqa: E402

OUT_ROOT = os.path.join(gl.SOURCE_DIR, "Gear")
RENDER_DIR = os.path.join(gl.RENDER_DIR, "Gear")
SCRATCH = os.environ.get("TEAMGEAR_SCRATCH", os.path.join(os.environ.get("TMPDIR", "/tmp"), "teamgear"))
TRI_BUDGET = 25000


def log(*a):
    print(*a, flush=True)


def _n(v):
    v = np.asarray(v, np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def A(x):
    return np.atleast_1d(np.asarray(x, np.float64))


# --------------------------------------------------------------------------------------
# Colourways (linear tints; in game and here the final albedo is 0.75 * tint)
# --------------------------------------------------------------------------------------

COLORWAYS = {
    "Kit": [
        {"Name": "Black", "Primary": [0.034, 0.034, 0.037], "Secondary": [0.030, 0.030, 0.033]},
        {"Name": "Charcoal", "Primary": [0.080, 0.080, 0.084], "Secondary": [0.042, 0.042, 0.045]},
        {"Name": "RangerGreen", "Primary": [0.096, 0.106, 0.066], "Secondary": [0.060, 0.066, 0.044]},
    ],
    "Helmet": [
        {"Name": "Black", "Primary": [0.040, 0.040, 0.043], "Secondary": [0.034, 0.034, 0.037]},
        {"Name": "RangerGreen", "Primary": [0.090, 0.100, 0.062], "Secondary": [0.060, 0.066, 0.044]},
        {"Name": "Charcoal", "Primary": [0.085, 0.085, 0.090], "Secondary": [0.045, 0.045, 0.048]},
        {"Name": "Tan", "Primary": [0.300, 0.235, 0.150], "Secondary": [0.160, 0.130, 0.090]},
    ],
    "Cap": [
        {"Name": "Black", "Primary": [0.036, 0.036, 0.039], "Secondary": [0.030, 0.030, 0.033]},
        {"Name": "Charcoal", "Primary": [0.085, 0.085, 0.090], "Secondary": [0.045, 0.045, 0.048]},
        {"Name": "RangerGreen", "Primary": [0.096, 0.106, 0.066], "Secondary": [0.060, 0.066, 0.044]},
    ],
}
# AirsoftColors::Team() in AirsoftTypes.h
TEAM = {"Blue": (0.08, 0.30, 1.0), "Red": (1.0, 0.09, 0.07)}

SLOTS = [
    {"Slot": "Torso", "Options": [{"Asset": "PlateCarrier", "Weight": 1.0}]},
    {"Slot": "Head", "Options": [{"Asset": "Helmet", "Weight": 0.6}, {"Asset": "SoftCap", "Weight": 0.4}]},
    {"Slot": "Eyes", "Options": [{"Asset": "Goggles", "Weight": 1.0}]},
    {"Slot": "Face", "Options": [{"Asset": "FaceMask", "Weight": 1.0}]},
    {"Slot": "Arm", "Options": [{"Asset": "Armband", "Weight": 1.0}]},
    {"Slot": "Knees", "Chance": 0.55, "Options": [{"Asset": "KneePads", "Weight": 1.0}]},
]


# --------------------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------------------


class Builder:
    def __init__(self, aid, coll):
        self.aid = aid
        self.coll = coll
        self.parts = {}  # piece -> [objects]
        self.count = 0

    def add(self, M, zone, piece="Body", smooth_angle=None):
        if M is None or not M.n:
            return None
        self.count += 1
        ob = tg.to_object(f"{self.aid}_{piece}_{self.count}", M, zone, self.coll, smooth_angle)
        self.parts.setdefault(piece, []).append(ob)
        return ob

    def finish(self):
        out = {}
        for piece, objs in self.parts.items():
            ob = tg.join(objs, f"SM_{self.aid}_{piece}")
            out[piece] = ob
        return out


def inside(poly, P):
    """Even-odd point-in-polygon for (N, 2) points."""
    poly = np.asarray(poly)
    x, y = P[:, 0], P[:, 1]
    res = np.zeros(len(P), bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        cond = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        res ^= cond
        j = i
    return res


def patch_puv(uc, vc, w, h):
    half = h / 2

    def f(U, V):
        return np.stack([(U - uc) / half, (V - vc) / half, np.full(len(U), w / h)], -1)

    return f


def lin_puv(u0, v0, du=(1.0, 0.0), dv=(0.0, 1.0)):
    def f(U, V):
        a = (U - u0) * du[0] + (V - v0) * du[1]
        b = (U - u0) * dv[0] + (V - v0) * dv[1]
        return np.stack([a, b, np.zeros(len(U))], -1)

    return f


def offset_map(mapf, du=0.0, dv=0.0, dh=0.0):
    def m(U, V, H):
        return mapf(U + du, V + dv, H + dh)

    return m


def frame_at(mapf, u, v, h, eps=1e-4):
    """Point and orthonormal frame (tu, tv, n) of a surface map at (u, v, h)."""
    P, N = mapf(A(u), A(v), A(h))
    Pu, _ = mapf(A(u + eps), A(v), A(h))
    Pv, _ = mapf(A(u), A(v + eps), A(h))
    n = _n(N[0])
    tu = _n(Pu[0] - P[0])
    tv = _n(np.cross(n, tu))
    return P[0], tu, tv, n


def box_on(mapf, u, v, h, size, r, n=2, tilt=None):
    """Rounded box centred at surface coords (u, v, h): size = (along u, along v, along n)."""
    P, tu, tv, nn = frame_at(mapf, u, v, h)
    R = np.stack([tu, tv, nn], axis=1)
    if tilt is not None:
        R = R @ tilt
    return tg.rbox(P, size, r, R, n)


# --------------------------------------------------------------------------------------
# Carrier surfaces
# --------------------------------------------------------------------------------------


class PlateSurf:
    """A plate bag surface: depth d(u, v) = D0 + B v - u^2 / 2R along +X (front) or -X (back)."""

    def __init__(self, sign, zc, D0, B, R):
        self.sign, self.zc, self.D0, self.B, self.R = sign, zc, D0, B, R

    def map(self, U, V, H):
        U, V, H = A(U), A(V), A(H)
        d = self.D0 + self.B * V - U * U / (2 * self.R)
        S = np.stack([self.sign * d, U, self.zc + V], -1)
        N = _n(np.stack([np.full(U.shape, float(self.sign)), U / self.R, np.full(U.shape, -self.B)], -1))
        return S + N * H[:, None], N

    @staticmethod
    def fit(F, sign, zc, outline, R, clear):
        lo, hi = outline.min(0), outline.max(0)
        uu, vv = np.meshgrid(np.linspace(lo[0], hi[0], 17), np.linspace(lo[1], hi[1], 17))
        P = np.stack([uu.ravel(), vv.ravel()], -1)
        P = P[inside(outline, P)]
        depth = sign * tb.front_depth(F, P[:, 0], zc + P[:, 1], sign)
        best = None
        for B in np.linspace(-0.4, 0.4, 81):
            D0 = float(np.max(depth + P[:, 0] ** 2 / (2 * R) - B * P[:, 1])) + clear
            gap = float(np.mean(D0 + B * P[:, 1] - P[:, 0] ** 2 / (2 * R) - depth))
            if best is None or gap < best[0]:
                best = (gap, B, D0)
        log(f"    plate fit sign {sign:+d}: tilt {best[1]:+.3f} depth {best[2]:.3f} mean gap {best[0] * 100:.1f} cm")
        return PlateSurf(sign, zc, best[2], best[1], R)


class BandSurf:
    """A generalized cylinder around the torso (cummerbund): horizontal section offset from the body."""

    def __init__(self, F, zs, center, clear, zc, smooth=6):
        th = np.linspace(0, 2 * math.pi, 360, endpoint=False)
        r = np.max(np.stack([tb.radial_section(F, z, center, th) for z in zs]), axis=0) + clear
        k = np.ones(9) / 9
        for _ in range(smooth):
            r = np.convolve(np.concatenate([r[-4:], r, r[:4]]), k, mode="valid")
        self.center = np.asarray(center, np.float64)
        self.zc = zc
        self.th = th
        self.pts = np.stack([center[0] + r * np.cos(th), center[1] + r * np.sin(th)], -1)
        seg = np.linalg.norm(np.roll(self.pts, -1, axis=0) - self.pts, axis=1)
        self.s = np.concatenate([[0.0], np.cumsum(seg)[:-1]])
        self.total = float(np.sum(seg))
        t = np.roll(self.pts, -1, axis=0) - np.roll(self.pts, 1, axis=0)
        t = _n(t)
        self.nrm = np.stack([t[:, 1], -t[:, 0]], -1)

    def _interp(self, U, arr):
        s_ext = np.concatenate([self.s, [self.total]])
        out = []
        for i in range(arr.shape[1]):
            a = np.concatenate([arr[:, i], arr[:1, i]])
            out.append(np.interp(np.mod(U, self.total), s_ext, a))
        return np.stack(out, -1)

    def s_at(self, theta):
        return float(np.interp(theta % (2 * math.pi), np.concatenate([self.th, [2 * math.pi]]), np.concatenate([self.s, [self.total]])))

    def theta_at_y(self, y, front=True):
        """Azimuth where the section reaches lateral position y (front or back half)."""
        sel = self.pts[:, 0] >= self.center[0] if front else self.pts[:, 0] < self.center[0]
        idx = np.nonzero(sel & (np.sign(self.pts[:, 1]) == np.sign(y)))[0]
        i = idx[np.argmin(np.abs(self.pts[idx, 1] - y))]
        return float(self.th[i])

    def map(self, U, V, H):
        U, V, H = A(U), A(V), A(H)
        p = self._interp(U, self.pts)
        n = _n(self._interp(U, self.nrm))
        N = np.stack([n[:, 0], n[:, 1], np.zeros(len(U))], -1)
        S = np.stack([p[:, 0], p[:, 1], self.zc + V], -1)
        return S + N * H[:, None], N


# --------------------------------------------------------------------------------------
# Plate carrier
# --------------------------------------------------------------------------------------

CARRIER = dict(
    front_zc=1.285, front_thick=0.030, back_zc=1.290, back_thick=0.028, plate_R=0.30, clear=0.016,
    band_zc=1.200, band_h=0.170, band_thick=0.011, band_clear=0.014,
)


def molle_rows(mapf, u0, u1, vs, thick=0.0022, h0=0.0, pitch=0.038):
    """Horizontal webbing rows sewn down every `pitch` (bar tacks), bulging slightly between tacks."""
    M = tg.Mesh()
    for v in vs:
        nu = max(8, int(round((u1 - u0) / pitch * 5)))

        def bulge(u, _u0=u0):
            return 0.0017 * abs(math.sin(math.pi * (u - _u0) / pitch)) ** 0.7

        M.merge(tg.strip(mapf, u0, u1, v, 0.025, thick, nu, h0=h0, bulge=bulge))
    return M


def id_panel(B, mapf, uc, vc, w, h, h0, piece="Body", loop=True):
    """Hook-and-loop ID panel (loop field in the kit colour) with a team patch on it."""
    dh = h0
    if loop:
        lo = tg.rrect(w, h, 0.008, 3, uc, vc)
        B.add(tg.pillow(lo, 0.0022, offset_map(mapf, dh=h0), n=40, kind="box", r_in=0.0005, r_out=0.0012, inner=False, steps=1,
                        face_insets=(0.0, 0.003, 0.0065), scales=(0.5,)), "loop", piece)
        dh = h0 + 0.0021
        pw, ph = w - 0.018, h - 0.014
    else:
        pw, ph = w, h
    pa = tg.rrect(pw, ph, 0.009, 4, uc, vc)
    B.add(tg.pillow(pa, 0.0026, offset_map(mapf, dh=dh), n=48, kind="round", inner=False, steps=2,
                    face_insets=(0.0, 0.002, 0.0045, 0.008), scales=(0.55, 0.25), puv=patch_puv(uc, vc, pw, ph)), "patch", piece)


def mag_pouch(B, fs, h0, uc, piece="Body"):
    """Open-top rifle mag pouch with a generic polymer magazine and a bungee retention loop."""
    w, top, bot = 0.076, -0.055, -0.170
    pm = offset_map(fs.map, dh=h0)
    ol = tg.rrect(w, top - bot, 0.010, 4, uc, (top + bot) / 2)
    B.add(tg.pillow(ol, 0.038, pm, n=44, kind="box", r_in=0.003, r_out=0.009, inner=False, puff=0.002, steps=2,
                    face_insets=(0.0, 0.0025, 0.0055, 0.011), scales=(0.6, 0.25)), "cordura", piece)
    # pouch mouth binding (a lip around the opening)
    P0, tu, tv, nn = frame_at(pm, uc, top - 0.002, 0.019)
    lip = []
    for a in np.linspace(0, 2 * math.pi, 28, endpoint=False):
        lip.append(P0 + tu * (w / 2 - 0.003) * math.cos(a) + nn * 0.0175 * math.sin(a))
    lip = np.array(lip)
    ups = np.tile(tv, (len(lip), 1))
    B.add(tg.sweep(lip, ups, tg.rrect_profile(0.007, 0.004, 0.0018, 1) - np.array([0.0, 0.002]), closed=True, half_w=0.0035), "binding", piece)
    # magazine (stowed base plate up), slightly curved body
    mag = box_on(pm, uc, top - 0.004, 0.019, (0.060, 0.050, 0.023), 0.004, 2)
    B.add(mag, "polymer_mag", piece, smooth_angle=40)
    plate = box_on(pm, uc, top + 0.0235, 0.019, (0.066, 0.008, 0.027), 0.0028, 2)
    B.add(plate, "polymer_mag", piece, smooth_angle=40)
    for k in (-1, 1):
        rib = box_on(pm, uc + k * 0.012, top + 0.016, 0.019 + 0.0118, (0.004, 0.014, 0.0016), 0.0006, 1)
        B.add(rib, "polymer_mag", piece, smooth_angle=40)
    # bungee: from the pouch face, over the base plate, down behind the magazine
    vh = [(top - 0.030, 0.0392), (top - 0.004, 0.0405), (top + 0.022, 0.034), (top + 0.0305, 0.019), (top + 0.022, 0.004), (top - 0.006, 0.0015)]
    path = np.array([pm(A(uc), A(v), A(h))[0][0] for v, h in vh])
    path = tg.resample_path(tg.smooth_path(path, 2), 18)
    ups = np.tile(tu, (len(path), 1))
    circ = np.array([(0.0021 * math.cos(a), 0.0021 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 6, endpoint=False)])
    B.add(tg.sweep(path, ups, circ, caps=True), "elastic", piece)
    tab = box_on(pm, uc, top - 0.034, 0.0405, (0.018, 0.024, 0.004), 0.0018, 2)
    B.add(tab, "rubber", piece, smooth_angle=40)


def build_carrier(B):
    C = CARRIER
    F = tb.field("torso")
    # front plate bag (shooter's cut) and back plate bag
    fo = tg.fillet(np.array([(-0.135, -0.165), (0.135, -0.165), (0.135, 0.060), (0.085, 0.165), (-0.085, 0.165), (-0.135, 0.060)]), 0.024, 5)
    bo = tg.fillet(np.array([(-0.140, -0.175), (0.140, -0.175), (0.140, 0.120), (0.110, 0.175), (-0.110, 0.175), (-0.140, 0.120)]), 0.026, 5)
    fs = PlateSurf.fit(F, +1, C["front_zc"], fo, C["plate_R"], C["clear"])
    bs = PlateSurf.fit(F, -1, C["back_zc"], bo, C["plate_R"], C["clear"])
    ft, bt = C["front_thick"], C["back_thick"]
    B.add(tg.pillow(fo, ft, fs.map, n=56, kind="round", puff=0.004, steps=3, face_insets=(0.0, 0.0025, 0.0055, 0.010, 0.020), scales=(0.66, 0.33)), "cordura")
    B.add(tg.pillow(bo, bt, bs.map, n=56, kind="round", puff=0.004, steps=3, face_insets=(0.0, 0.0025, 0.0055, 0.010, 0.020), scales=(0.66, 0.33)), "cordura")
    # --- front: admin pouch with zipper + chest ID panel, three mag pouches
    fh = ft
    pm = offset_map(fs.map, dh=fh)
    ad = tg.rrect(0.200, 0.105, 0.012, 4, 0.0, 0.0525)
    B.add(tg.pillow(ad, 0.030, pm, n=48, kind="box", r_in=0.003, r_out=0.008, inner=False, puff=0.0, steps=2,
                    face_insets=(0.0, 0.0025, 0.0055, 0.011), scales=(0.6, 0.25)), "cordura")
    zv = 0.0525 + 0.0525 - 0.011
    zol = tg.rrect(0.176, 0.009, 0.0035, 2, 0.0, zv)
    B.add(tg.pillow(zol, 0.0022, offset_map(pm, dh=0.030), n=48, kind="box", r_in=0.0005, r_out=0.001, inner=False,
                    face_insets=(0.0, 0.0015), scales=(0.5,), puv=lin_puv(0.0, zv)), "zipper")
    pull = box_on(pm, 0.070, zv - 0.012, 0.0345, (0.010, 0.020, 0.0035), 0.0015, 2)
    B.add(pull, "polymer", smooth_angle=40)
    id_panel(B, pm, 0.0, 0.044, 0.140, 0.072, 0.030)
    for uc in (-0.083, 0.0, 0.083):
        mag_pouch(B, fs, fh, uc)
    # --- back: drag handle, ID panel, MOLLE
    bh = bt
    bm = offset_map(bs.map, dh=bh)
    id_panel(B, bm, 0.0, 0.080, 0.165, 0.088, 0.0)
    B.add(molle_rows(bm, -0.118, 0.118, [-0.150, -0.112, -0.074, -0.036]), "webbing")
    hp = []
    for t in np.linspace(0, 1, 22):
        u = -0.06 + 0.12 * t
        hp.append(bm(A(u), A(0.140), A(0.003 + 0.022 * math.sin(math.pi * t) ** 0.8))[0][0])
    hp = np.array(hp)
    c0 = bm(A(0.0), A(0.140), A(-0.01))[0][0]
    ups = _n(hp - c0)
    B.add(tg.sweep(hp, ups, tg.rrect_profile(0.026, 0.0032, 0.0012, 2), caps=True, half_w=0.013), "webbing")
    # --- cummerbund (both sides), tucked under both plate bags
    band = BandSurf(F, [C["band_zc"] - 0.08, C["band_zc"], C["band_zc"] + 0.08], (-0.010, 0.0), C["band_clear"], C["band_zc"])
    hh = C["band_h"] / 2
    for side in (1, -1):
        ta = band.theta_at_y(0.100 * side, True)
        tb_ = band.theta_at_y(0.105 * side, False)
        sa, sb = band.s_at(ta), band.s_at(tb_)
        if side < 0:  # right side runs clockwise: walk from the back to the front
            sa, sb = band.s_at(tb_), band.s_at(ta)
        if sb < sa:
            sb += band.total
        ol = tg.rrect(sb - sa, 2 * hh, 0.02, 4, (sa + sb) / 2, 0.0)
        B.add(tg.pillow(ol, C["band_thick"], band.map, n=60, kind="round", puff=0.0015, steps=2,
                        face_insets=(0.0, 0.0025, 0.0055, 0.012), scales=(0.6, 0.3), inner_scale=(0.5,)), "cordura")
        bmap = offset_map(band.map, dh=C["band_thick"])
        sfront = band.s_at(band.theta_at_y(0.135 * side, True))
        sside = band.s_at(math.pi / 2 * side + (0.10 if side > 0 else -0.10))
        if side > 0:
            m0, m1 = sfront + 0.012, sfront + 0.012 + 3 * 0.038
            pc = sside + 0.030
        else:
            m1, m0 = sfront - 0.012, sfront - 0.012 - 3 * 0.038
            pc = sside - 0.030
            if m0 < sa:
                m0 += band.total
                m1 += band.total
            if pc < sa:
                pc += band.total
        B.add(molle_rows(bmap, m0, m1, [-0.040, -0.002, 0.036]), "webbing")
        id_panel(B, bmap, pc, 0.0, 0.080, 0.056, 0.0, loop=False)
    # --- shoulder straps over the trapezius into both bag tops
    for side in (1, -1):
        yf, yt, yb = 0.068 * side, 0.112 * side, 0.082 * side
        pts = [fs.map(A(yf), A(0.120), A(0.013))[0][0], fs.map(A(yf), A(0.168), A(0.010))[0][0]]
        arc = []
        for th in np.linspace(deg(25), deg(160), 28):
            k = (th - deg(25)) / deg(135)
            y = np.interp(k, [0.0, 0.45, 1.0], [yf, yt, yb])
            cpt = np.array([-0.015, y, 1.390])
            d = np.array([math.cos(th), 0.0, math.sin(th)])
            hit = tb.march(F, cpt + d * 0.4, -d)[0]
            nrm = tb.surface_normal(F, hit)[0]
            q = hit + nrm * 0.010
            if q[2] > 1.462:
                arc.append(q)
        pts += arc
        pts += [bs.map(A(yb), A(0.178), A(0.010))[0][0], bs.map(A(yb), A(0.125), A(0.013))[0][0]]
        path = tg.resample_path(tg.smooth_path(np.array(pts), 4), 32)
        ups = tb.surface_normal(F, path)
        B.add(tg.sweep(path, ups, tg.rrect_profile(0.050, 0.012, 0.0055, 2), caps=True, half_w=0.025), "cordura_pad")
    return dict(fs=fs, bs=bs, band=band)


# --------------------------------------------------------------------------------------
# Head gear helpers
# --------------------------------------------------------------------------------------


class RadialShell:
    """Star-shaped shell around c: superellipse (exponent p) in plan, elliptic in elevation.
    A direction d from c meets the surface at c + d / sqrt(F(d)) (F is 2-homogeneous)."""

    def __init__(self, c, a, b, cz, p=2.3):
        self.c = np.asarray(c, np.float64)
        self.a, self.b, self.cz, self.p = a, b, cz, p

    def F(self, Q):
        Q = np.asarray(Q, np.float64).reshape(-1, 3)
        s = (np.abs(Q[:, 0] / self.a) ** self.p + np.abs(Q[:, 1] / self.b) ** self.p) ** (2.0 / self.p)
        return s + (Q[:, 2] / self.cz) ** 2

    def normal(self, P):
        Q = np.asarray(P, np.float64).reshape(-1, 3) - self.c
        g = np.zeros_like(Q)
        e = 1e-5
        for i in range(3):
            dq = np.zeros(3)
            dq[i] = e
            g[:, i] = (self.F(Q + dq) - self.F(Q - dq)) / (2 * e)
        return _n(g)

    def point(self, D):
        D = _n(np.asarray(D, np.float64).reshape(-1, 3))
        t = 1.0 / np.sqrt(self.F(D))
        P = self.c + D * t[:, None]
        return P, self.normal(P)

    @staticmethod
    def dirs(phi, psi):
        phi, psi = A(phi), A(psi)
        return np.stack([np.cos(psi) * np.cos(phi), np.cos(psi) * np.sin(phi), np.sin(psi)], -1)

    def psi_at_z(self, phi, z):
        """Elevation angle at azimuth phi where the surface reaches height z (absolute)."""
        phi = A(phi)
        lo = np.full(phi.shape, deg(-75.0))
        hi = np.full(phi.shape, deg(89.5))
        for _ in range(40):
            mid = (lo + hi) / 2
            P, _ = self.point(self.dirs(phi, mid))
            below = P[:, 2] < z
            lo = np.where(below, mid, lo)
            hi = np.where(below, hi, mid)
        return (lo + hi) / 2

    def at_z(self, phi, z):
        return self.point(self.dirs(phi, self.psi_at_z(phi, z)))

    def panel_map(self, d0, up=(0.0, 0.0, 1.0)):
        """Gnomonic map around direction d0: (U, V) metres in the tangent plane."""
        P0, N0 = self.point(_n(d0)[None, :])
        P0, N0 = P0[0], N0[0]
        eu = _n(np.cross(np.asarray(up, np.float64), N0))
        ev = np.cross(N0, eu)
        R0 = P0 - self.c

        def m(U, V, H):
            U, V, H = A(U), A(V), A(H)
            D = R0[None, :] + np.outer(U, eu) + np.outer(V, ev)
            P, N = self.point(D)
            return P + N * H[:, None], N

        return m


def periodic_curve(keys, n=360, smooth=4):
    """Symmetric periodic function of azimuth from (deg 0..180, value) keys, sampled at n points."""
    ks = sorted(keys)
    xs = [k[0] for k in ks] + [360 - k[0] for k in reversed(ks) if 0 < k[0] < 180]
    ys = [k[1] for k in ks] + [k[1] for k in reversed(ks) if 0 < k[0] < 180]
    xs = np.array(xs + [360.0])
    ys = np.array(ys + [ks[0][1]])
    t = np.arange(n) / n * 360.0
    v = np.interp(t, xs, ys)
    k = np.ones(7) / 7
    for _ in range(smooth):
        v = np.convolve(np.concatenate([v[-3:], v, v[:3]]), k, mode="valid")
    return lambda phi: np.interp(np.degrees(np.mod(A(phi), 2 * math.pi)), np.append(t, 360.0), np.append(v, v[0]))


def shell_grid(shell, z_rim, nphi=96, nrows=18, inset=0.0, top_frac=0.985):
    """Quad grid over a shell from the rim curve z_rim(phi) up to the pole (plus a pole fan)."""
    H0 = tb.HEAD
    phis = np.arange(nphi) / nphi * 2 * math.pi
    psi0 = shell.psi_at_z(phis, H0[2] + z_rim(phis))
    M = tg.Mesh()
    rows = []
    for r in range(nrows):
        t = r / nrows
        tt = t * top_frac
        psi = psi0 + (deg(89.9) - psi0) * (1 - (1 - tt) ** 1.15)
        P, N = shell.point(shell.dirs(phis, psi))
        rows.append(M.add_verts(P - N * inset, ss=phis * 0.12))
    for a, b in zip(rows[:-1], rows[1:]):
        for i in range(nphi):
            j = (i + 1) % nphi
            M.f.append((a + i, a + j, b + j, b + i))
    top, Nt = shell.point(np.array([[0.0, 0.0, 1.0]]))
    c = M.add_verts(top - Nt * inset)
    M.add_faces(tg.fan_faces(c, [rows[-1] + i for i in range(nphi)]))
    if inset > 0:
        M.f = [f[::-1] for f in M.f]
    return M, phis, psi0


def head_ring_path(F, phis, zs, offset, center_x=0.0):
    """Points around the head at given azimuths and heights (relative to the head pivot), offset outward."""
    H0 = tb.HEAD
    out = []
    for phi, z in zip(phis, zs):
        d = np.array([math.cos(phi), math.sin(phi), 0.0])
        cpt = H0 + np.array([center_x, 0.0, z])
        hit = tb.march(F, cpt + d * 0.3, -d)[0]
        nrm = tb.surface_normal(F, hit)[0]
        out.append(hit + nrm * offset)
    return np.array(out)


# --------------------------------------------------------------------------------------
# Helmet: generic high-cut bump helmet
# --------------------------------------------------------------------------------------

HELMET_SHELL = dict(c=(0.000, 0.0, 0.098), a=0.130, b=0.108, cz=0.128, p=2.3, thick=0.008)
# rim height (m above the head pivot) by azimuth: brow, temple, ear cut arch, nape
HELMET_RIM = [(0, 0.124), (22, 0.119), (48, 0.102), (66, 0.114), (88, 0.121), (112, 0.100), (135, 0.074), (160, 0.056), (180, 0.052)]


def build_helmet(B):
    H0 = tb.HEAD
    S = HELMET_SHELL
    shell = RadialShell(H0 + np.array(S["c"]), S["a"], S["b"], S["cz"], S["p"])
    z_rim = periodic_curve(HELMET_RIM)
    outer, phis, psi0 = shell_grid(shell, z_rim, 96, 18)
    B.add(outer, "shell")
    inner, _, _ = shell_grid(shell, z_rim, 64, 9, inset=S["thick"])
    B.add(inner, "foam")
    # rubber edge trim straddling the rim
    rim, rn = shell.point(shell.dirs(phis, psi0))
    prof = tg.rrect(0.012, 0.0125, 0.0035, 2)
    prof[:, 0] += 0.0015
    prof[:, 1] -= 0.0040
    B.add(tg.sweep(rim, rn, prof, closed=True), "rubber")
    # accessory rails above the ear cut, with end screws
    for side in (1, -1):
        ph = np.linspace(deg(54), deg(126), 30) * side
        zc = H0[2] + 0.139 - 0.006 * ((np.abs(ph) - deg(90)) / deg(36)) ** 2
        P, N = shell.at_z(ph, zc)
        P = P + N * 0.0005
        s, _ = tg.arclen(P)
        B.add(tg.sweep(P, N, tg.rrect_profile(0.024, 0.0085, 0.0022, 2), caps=True, puv_fn=lambda ss, a: (ss, a, 0.0)), "rail", smooth_angle=50)
        for k in (2, len(P) - 3):
            B.add(tg.cyl(P[k] + N[k] * 0.0080, P[k] + N[k] * 0.0105, 0.0042, n=12), "anod", smooth_angle=50)
    # NVG shroud: contoured plate, mount receiver, three screws
    sm = shell.panel_map(RadialShell.dirs(0.0, shell.psi_at_z(0.0, H0[2] + 0.153))[0])
    so = tg.fillet(np.array([(-0.038, -0.022), (0.038, -0.022), (0.031, 0.022), (-0.031, 0.022)]), 0.008, 4)
    B.add(tg.pillow(so, 0.0055, sm, n=48, kind="box", r_in=0.001, r_out=0.0025, inner=False, steps=2,
                    face_insets=(0.0, 0.002, 0.005), scales=(0.5,)), "anod", smooth_angle=50)
    B.add(box_on(sm, 0.0, -0.002, 0.0055 + 0.006, (0.034, 0.022, 0.012), 0.0025, 2), "anod", smooth_angle=50)
    B.add(box_on(sm, 0.0, -0.002, 0.0055 + 0.0122, (0.022, 0.010, 0.0012), 0.0005, 1), "vent", smooth_angle=50)
    for (u, v) in ((0.0, 0.016), (-0.028, -0.015), (0.028, -0.015)):
        P, tu, tv, nn = frame_at(sm, u, v, 0.0055)
        B.add(tg.cyl(P - nn * 0.001, P + nn * 0.0022, 0.0032, n=12), "steel", smooth_angle=50)
    # loop panels: crown and rear (with the rear team patch)
    tm = shell.panel_map(np.array([0.0, 0.0, 1.0]), up=(1.0, 0.0, 0.0))
    tl = tg.rrect(0.075, 0.110, 0.014, 4)
    B.add(tg.pillow(tl, 0.0022, tm, n=48, kind="box", r_in=0.0005, r_out=0.0012, inner=False, steps=1,
                    face_insets=(0.0, 0.003, 0.0065), scales=(0.5,)), "loop")
    rm = shell.panel_map(RadialShell.dirs(math.pi, shell.psi_at_z(math.pi, H0[2] + 0.112))[0])
    id_panel(B, rm, 0.0, 0.0, 0.092, 0.056, 0.0)
    # team cover band (elastic), higher at the front
    phb = np.arange(120) / 120 * 2 * math.pi
    zb = H0[2] + 0.180 + 0.011 * np.cos(phb)
    P, N = shell.at_z(phb, zb)
    B.add(tg.sweep(P + N * 0.0004, N, tg.rrect_profile(0.026, 0.0034, 0.0014, 2), closed=True, half_w=0.013), "teamband")
    # retention harness: front and rear straps to a junction below the ear, chin strap
    Fh = tb.field("head")
    for side in (1, -1):
        j = H0 + np.array([-0.002, 0.084 * side, 0.004])
        jn = tb.surface_normal(Fh, tb.march(Fh, j + np.array([0, 0.2 * side, 0]), (0, -side, 0)))[0]
        jp = tb.march(Fh, j + np.array([0, 0.2 * side, 0]), (0, -side, 0))[0] + jn * 0.010
        for phd in (52, 118):
            ph = deg(phd) * side
            a, an = shell.point(shell.dirs(ph, shell.psi_at_z(ph, H0[2] + z_rim(ph)[0] + 0.012)))
            a = a[0] - an[0] * 0.012
            path = np.array([a + (jp - a) * t for t in np.linspace(0, 1, 10)])
            hits = []
            for q in path:
                d = _n(q - (H0 + np.array([0.0, 0.0, 0.07])))
                hp = tb.march(Fh, q + d * 0.15, -d)[0]
                hits.append(hp + tb.surface_normal(Fh, hp)[0] * 0.007)
            hits[0] = a
            path = tg.resample_path(tg.smooth_path(np.array(hits), 2), 14)
            ups = _n(path - (H0 + np.array([0.0, 0.0, 0.07])))
            B.add(tg.sweep(path, ups, tg.rrect_profile(0.018, 0.0022, 0.0009, 1), caps=True, half_w=0.009), "webbing_black")
        jf = np.stack([_n(np.array([1.0, 0.0, 0.0]) - jn * jn[0]), np.array([0.0, 0.0, 1.0]), jn], axis=1)
        jf[:, 1] = _n(np.cross(jf[:, 2], jf[:, 0]))
        B.add(tg.rbox(jp + jn * 0.002, (0.022, 0.026, 0.005), 0.0022, jf, 2), "polymer", smooth_angle=45)
    # chin strap under the jaw, outside the face mask
    key = [(-0.002, 0.090, 0.004), (0.022, 0.080, -0.036), (0.048, 0.050, -0.068), (0.062, 0.0, -0.080)]
    key = key + [(x, -y, z) for (x, y, z) in reversed(key[:-1])]
    pts = tg.resample_path(tg.smooth_path(np.array([H0 + np.array(k) for k in key]), 3), 26)
    for _ in range(3):
        d = Fh.eval(pts)
        nn = tb.surface_normal(Fh, pts)
        pts = pts + nn * np.maximum(0.0, 0.021 - d)[:, None]
    pts = tg.smooth_path(pts, 2)
    ups = _n(pts - (H0 + np.array([0.02, 0.0, 0.03])))
    B.add(tg.sweep(pts, ups, tg.rrect_profile(0.018, 0.0022, 0.0009, 1), caps=True, half_w=0.009), "webbing_black")
    cup = pts[len(pts) // 2]
    cf = np.stack([np.array([0.0, 1.0, 0.0]), _n(np.cross(ups[len(pts) // 2], (0.0, 1.0, 0.0))), ups[len(pts) // 2]], axis=1)
    B.add(tg.rbox(cup + ups[len(pts) // 2] * 0.003, (0.045, 0.028, 0.006), 0.003, cf, 2), "cordura_pad", smooth_angle=45)


# --------------------------------------------------------------------------------------
# Soft cap: six panels, curved brim, front loop panel with team patch, rear strap
# --------------------------------------------------------------------------------------

CAP_RIM = [(0, 0.121), (40, 0.112), (80, 0.094), (120, 0.084), (150, 0.080), (166, 0.088), (174, 0.104), (180, 0.110)]


def build_softcap(B):
    H0 = tb.HEAD
    shell = RadialShell(H0 + np.array([0.004, 0.0, 0.090]), 0.1085, 0.0885, 0.1205, 2.08)
    z_rim = periodic_curve(CAP_RIM, smooth=2)
    nphi, nrows = 96, 16
    phis = np.arange(nphi) / nphi * 2 * math.pi
    psi0 = shell.psi_at_z(phis, H0[2] + z_rim(phis))
    seams = np.radians([0, 60, 120, 180, 240, 300])
    M = tg.Mesh()
    rows = []
    for r in range(nrows):
        t = r / nrows * 0.985
        psi = psi0 + (deg(89.9) - psi0) * (1 - (1 - t) ** 1.2)
        P, N = shell.point(shell.dirs(phis, psi))
        # distance to the nearest panel seam (metres along the horizontal circle)
        dphi = np.min(np.abs(np.angle(np.exp(1j * (phis[:, None] - seams[None, :])))), axis=1)
        horiz = np.cos(psi) * 0.1
        sd = dphi * horiz
        puffp = 0.0016 * np.clip(sd / 0.02, 0, 1) * np.sin(np.clip(t, 0, 1) * math.pi) ** 0.5
        dent = -0.0010 * np.exp(-(sd / 0.0022) ** 2) * (t < 0.97)
        P = P + N * (puffp + dent)[:, None]
        rows.append(M.add_verts(P, sd=sd + 0.0002, ss=psi * 0.1))
    for a, b in zip(rows[:-1], rows[1:]):
        for i in range(nphi):
            j = (i + 1) % nphi
            M.f.append((a + i, a + j, b + j, b + i))
    top, Nt = shell.point(np.array([[0.0, 0.0, 1.0]]))
    c = M.add_verts(top, sd=0.0)
    M.add_faces(tg.fan_faces(c, [rows[-1] + i for i in range(nphi)]))
    B.add(M, "twill")
    inner, _, _ = shell_grid(shell, z_rim, 48, 6, inset=0.0025)
    B.add(inner, "twill")
    rim, rn = shell.point(shell.dirs(phis, psi0))
    prof = tg.rrect(0.008, 0.0045, 0.0018, 1)
    prof[:, 1] -= 0.0012
    B.add(tg.sweep(rim, rn, prof, closed=True, half_w=0.004), "binding")
    # top button
    B.add(tg.lathe([(0.0, 0.0), (0.0075, 0.0), (0.0072, 0.0025), (0.0045, 0.0048), (0.0, 0.0055)], 16, Nt[0], top[0] - Nt[0] * 0.0015), "twill")
    # brim: crescent, arched across, tilted down
    def brim_map(U, V, H):
        U, V, H = A(U), A(V), A(H)
        phi = U / 0.105
        base, bn = shell.point(shell.dirs(phi, shell.psi_at_z(phi, H0[2] + z_rim(phi))))
        out = _n(np.stack([np.cos(phi), np.sin(phi), np.zeros(len(U))], -1))
        tilt = deg(5) + 0.9 * (phi / deg(70)) ** 2 * 0.25
        drop = 0.010 * (phi / deg(70)) ** 2
        P = base + out * (V * np.cos(tilt))[:, None] + np.stack([np.zeros(len(U)), np.zeros(len(U)), -V * np.sin(tilt) - drop * np.clip(V / 0.07, 0, 1)], -1)
        side = _n(np.stack([-np.sin(phi), np.cos(phi), np.zeros(len(U))], -1))
        Nn = _n(np.cross(out * np.cos(tilt)[:, None] - np.array([0, 0, 1.0]) * np.sin(tilt)[:, None], side))
        Nn = Nn * np.sign(Nn[:, 2:3] + 1e-9)
        return P + Nn * (H - 0.0025)[:, None], Nn

    us = np.linspace(-deg(74) * 0.105, deg(74) * 0.105, 25)
    outer_edge = [(u, 0.074 * max(0.0, math.cos(u / (deg(74) * 0.105) * math.pi / 2)) ** 0.55 + 0.002) for u in us]
    ol = np.array([(us[-1], -0.006), (us[0], -0.006)] + outer_edge)
    ol = tg.fillet(tg.ccw(ol), 0.008, 3)
    bo = B.add(tg.pillow(ol, 0.005, brim_map, n=72, kind="round", steps=2, face_insets=(0.0, 0.002, 0.0045, 0.008, 0.013, 0.02), scales=(0.6, 0.3)), "twill_brim")
    del bo
    # front loop panel + team patch
    fm = shell.panel_map(RadialShell.dirs(0.0, shell.psi_at_z(0.0, H0[2] + 0.152))[0])
    id_panel(B, fm, 0.0, 0.0, 0.078, 0.050, 0.0012)
    # rear adjustment strap across the opening
    ph = np.linspace(deg(160), deg(200), 16)
    P, N = shell.at_z(ph, np.full(len(ph), H0[2] + 0.093))
    B.add(tg.sweep(P + N * 0.0008, N, tg.rrect_profile(0.020, 0.0026, 0.001, 1), caps=True, half_w=0.010), "strap_kit")
    P2, N2 = shell.at_z(np.linspace(deg(168), deg(186), 8), np.full(8, H0[2] + 0.093))
    B.add(tg.sweep(P2 + N2 * 0.0032, N2, tg.rrect_profile(0.017, 0.0022, 0.0009, 1), caps=True, half_w=0.0085), "loop")


# --------------------------------------------------------------------------------------
# Goggles: full-seal, wrap-around frame, smoked lens, foam seal, elastic strap
# --------------------------------------------------------------------------------------

GOG_OUTLINE = [(0.000, 0.047), (0.018, 0.044), (0.027, 0.030), (0.040, 0.022), (0.066, 0.024), (0.080, 0.036),
               (0.084, 0.062), (0.079, 0.088), (0.058, 0.100), (0.000, 0.104)]
LENS_R, LENS_X = 0.110, 0.154


def goggle_frame_data(n=72):
    H0 = tb.HEAD
    half = GOG_OUTLINE
    full = half + [(-y, z) for (y, z) in reversed(half[1:-1])]
    O = tg.fillet(tg.ccw(np.array(full)), 0.008, 4)
    O = tg.resample(O, n)
    Fh = tb.field("head")
    xc = LENS_X - LENS_R
    y, z = O[:, 0], O[:, 1]
    xf = xc + np.sqrt(np.maximum(LENS_R ** 2 - y ** 2, 1e-6))
    Pf = H0 + np.stack([xf, y, z], -1)
    cin = H0 + np.array([-0.015, 0.0, 0.068])
    hit = tb.march(Fh, Pf, cin - Pf)
    # smooth the face contact line around the outline (the stand-in face is lumpy at this scale)
    for _ in range(6):
        hit = 0.5 * hit + 0.25 * (np.roll(hit, 1, axis=0) + np.roll(hit, -1, axis=0))
    dirb = _n(Pf - hit)
    for _ in range(4):
        dirb = _n(0.5 * dirb + 0.25 * (np.roll(dirb, 1, axis=0) + np.roll(dirb, -1, axis=0)))
    Pc = hit + dirb * 0.012
    L = np.linalg.norm(Pf - Pc, axis=1)
    e = np.roll(O, -1, axis=0) - np.roll(O, 1, axis=0)
    n2 = _n(np.stack([e[:, 1], -e[:, 0]], -1))  # outward for CCW
    N3 = np.stack([np.zeros(n), n2[:, 0], n2[:, 1]], -1)
    seg = np.linalg.norm(np.roll(O, -1, axis=0) - O, axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)[:-1]])
    return dict(O=O, Pf=Pf, Pc=Pc, hit=hit, dirb=dirb, L=L, N3=N3, arc=arc, n=n)


def ring_loft(G, prof, puv=None):
    """Closed loft around the goggle outline; prof = [(mode, s, d)] closed cross-section loop.
    mode 'a': s metres back from the lens front, 'b': s metres in front of the back edge, 'f': fraction."""
    Pf, Pc, L, N3 = G["Pf"], G["Pc"], G["L"], G["N3"]
    D = _n(Pc - Pf)
    M = tg.Mesh()
    rows = []
    for mode, sv, d in prof:
        if mode == "a":
            s = np.minimum(np.full(len(L), sv), L)
        elif mode == "b":
            s = np.maximum(L - sv, 0.0)
        else:
            s = L * sv
        P = Pf + D * s[:, None] + N3 * d
        rows.append(M.add_verts(P, ss=G["arc"]))
    n = G["n"]
    k = len(rows)
    for r in range(k):
        a, b = rows[r], rows[(r + 1) % k]
        for i in range(n):
            j = (i + 1) % n
            M.f.append((a + i, b + i, b + j, a + j))
    return M


def build_goggles(B):
    H0 = tb.HEAD
    G = goggle_frame_data(72)
    frame = [("a", 0.0, 0.0012), ("a", 0.0012, 0.0040), ("a", 0.006, 0.0056), ("f", 0.5, 0.0064), ("b", 0.005, 0.0054), ("b", 0.0, 0.0030),
             ("b", 0.0, -0.0012), ("b", 0.003, -0.0028), ("f", 0.5, -0.0034), ("a", 0.006, -0.0038), ("a", 0.0020, -0.0058), ("a", 0.0, -0.0048)]
    fr = ring_loft(G, frame)
    # orientation: outward faces
    V, F_, _ = fr.arrays()
    f0 = F_[len(F_) // 2]
    c0 = V[list(f0)].mean(0)
    fn = np.cross(V[f0[1]] - V[f0[0]], V[f0[2]] - V[f0[0]])
    ctr = (G["Pf"].mean(0) + G["Pc"].mean(0)) / 2
    if fn @ (c0 - ctr) < 0 and False:
        fr.f = [f[::-1] for f in fr.f]
    B.add(fr, "tpu", smooth_angle=60)
    # foam seal against the face
    Gf = dict(G)
    Gf["Pf"] = G["hit"] + G["dirb"] * 0.0125
    Gf["Pc"] = G["hit"] - G["dirb"] * 0.0005
    Gf["L"] = np.linalg.norm(Gf["Pf"] - Gf["Pc"], axis=1)
    foam = [("a", 0.0, 0.0030), ("a", 0.003, 0.0058), ("b", 0.003, 0.0060), ("b", 0.0, 0.0030), ("b", 0.0, -0.0030), ("b", 0.003, -0.0050),
            ("a", 0.003, -0.0050), ("a", 0.0, -0.0025)]
    B.add(ring_loft(Gf, foam), "foam")
    # vents on the top and lower sides of the skirt
    O, Pf, Pc, N3, arc = G["O"], G["Pf"], G["Pc"], G["N3"], G["arc"]
    D = _n(Pc - Pf)
    for sel in (O[:, 1] > 0.093, (O[:, 1] < 0.036) & (np.abs(O[:, 0]) > 0.045) & (O[:, 0] > 0), (O[:, 1] < 0.036) & (np.abs(O[:, 0]) > 0.045) & (O[:, 0] < 0)):
        idx = np.nonzero(sel)[0]
        if len(idx) < 3:
            continue
        # contiguous run around the closed outline
        if idx[0] == 0 and idx[-1] == len(O) - 1:
            br = np.nonzero(np.diff(idx) > 1)[0]
            if len(br):
                idx = np.concatenate([idx[br[0] + 1:], idx[: br[0] + 1]])
        M = tg.Mesh()
        prof = [(0.0085, 0.0), (0.009, 0.0009), (0.019, 0.0009), (0.0195, 0.0)]
        rows = []
        for i in idx:
            pts = np.array([Pf[i] + D[i] * s + N3[i] * (0.0062 + h) for s, h in prof])
            pv = np.array([(arc[i], s - 0.014, 0.0) for s, _ in prof])
            rows.append(M.add_verts(pts, puv=pv))
        for a, b in zip(rows[:-1], rows[1:]):
            for j in range(len(prof) - 1):
                M.f.append((a + j, a + j + 1, b + j + 1, b + j))
        B.add(M, "vent", smooth_angle=60)
    # strap clips at the sides
    clips = {}
    for side in (1, -1):
        i = int(np.argmax(O[:, 0] * side))
        cpos = Pf[i] + D[i] * (G["L"][i] * 0.52) + N3[i] * 0.0085
        fx = D[i]
        fz = np.array([0.0, 0.0, 1.0])
        fz = _n(fz - fx * (fx @ fz))
        fy = np.cross(fz, fx)
        Rm = np.stack([fx, fz, np.cross(fx, fz)], axis=1)
        B.add(tg.rbox(cpos, (0.024, 0.032, 0.007), 0.0025, Rm, 2), "polymer", smooth_angle=45)
        clips[side] = (cpos, fx, N3[i])
        del fy
    # lens (Glass piece): double-sided thin shell on the lens cylinder, seated in the frame groove
    xc = LENS_X - LENS_R

    def lens_map(U, V, H):
        U, V, H = A(U), A(V), A(H)
        r = LENS_R - 0.0032 + H
        x = xc + np.sqrt(np.maximum(r ** 2 - U ** 2, 1e-8))
        P = H0 + np.stack([x, U, V], -1)
        N = _n(np.stack([x - xc, U, np.zeros(len(U))], -1))
        return P, N

    lo = tg.inset_radial(O, 0.0025)
    B.add(tg.pillow(lo, 0.0016, lens_map, n=64, kind="round", steps=1, face_insets=(0.0, 0.004, 0.012), scales=(0.6, 0.3),
                    inner_scale=(0.6, 0.3)), "glass", "Glass")
    # elastic strap around the head, adjuster slider at the back
    Fh = tb.field("head")
    for side in (1, -1):
        cpos, fx, nn = clips[side]
        phs = np.linspace(deg(62), deg(180), 22)
        zs = np.interp(phs, [deg(62), deg(95), deg(140), deg(180)], [0.068, 0.062, 0.046, 0.040])
        ring = head_ring_path(Fh, phs * side, zs, 0.0045)
        pts = np.vstack([cpos - fx * 0.004 + nn * 0.004, ring])
        path = tg.resample_path(tg.smooth_path(pts, 6), 30)
        ups = _n(path - (H0 + np.array([0.0, 0.0, 0.06])))
        ups[:2] = nn
        B.add(tg.sweep(path, ups, tg.rrect_profile(0.034, 0.0028, 0.0012, 1), caps=True, half_w=0.017), "strap_kit")
    back = head_ring_path(Fh, [math.pi], [0.040], 0.0075)[0]
    Rm = np.stack([np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0]), np.array([-1.0, 0.0, 0.0])], axis=1)
    B.add(tg.rbox(back, (0.020, 0.040, 0.006), 0.0024, Rm, 2), "polymer", smooth_angle=45)


# --------------------------------------------------------------------------------------
# Face mask: pressed steel mesh over the lower face, fabric binding, two elastic straps
# --------------------------------------------------------------------------------------


class MaskSurf:
    def __init__(self, cx=0.010):
        H0 = tb.HEAD
        Fh = tb.field("head")
        self.c = np.array([H0[0] + cx, 0.0])
        self.phis = np.radians(np.linspace(-96, 96, 49))
        self.zs = np.linspace(-0.080, 0.075, 32)
        R = np.stack([tb.radial_section(Fh, H0[2] + z, self.c, self.phis, start=0.3) for z in self.zs])
        raw = R + 0.012
        S = raw.copy()
        for _ in range(3):
            S = self._blur(S, 2)
            S = np.maximum(S, raw - 0.002)
        self.R = self._blur(S, 1)

    @staticmethod
    def _blur(a, r):
        k = np.exp(-np.linspace(-2, 2, 2 * r + 1) ** 2)
        k /= k.sum()
        for ax in (0, 1):
            pad = [(r, r) if i == ax else (0, 0) for i in range(2)]
            ap = np.pad(a, pad, mode="edge")
            a = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), ax, ap)
        return a

    def radius(self, phi, z):
        # bilinear on the (z, phi) grid
        fi = np.interp(phi, self.phis, np.arange(len(self.phis)))
        fj = np.interp(z, self.zs, np.arange(len(self.zs)))
        i0 = np.clip(np.floor(fi).astype(int), 0, len(self.phis) - 2)
        j0 = np.clip(np.floor(fj).astype(int), 0, len(self.zs) - 2)
        ti, tj = fi - i0, fj - j0
        R = self.R
        return (R[j0, i0] * (1 - ti) * (1 - tj) + R[j0, i0 + 1] * ti * (1 - tj) + R[j0 + 1, i0] * (1 - ti) * tj + R[j0 + 1, i0 + 1] * ti * tj)

    def map(self, U, V, H):
        U, V, H = A(U), A(V), A(H)
        H0 = tb.HEAD

        def P_(u, v):
            phi = u / 0.1
            r = self.radius(phi, v)
            return np.stack([self.c[0] + r * np.cos(phi), self.c[1] + r * np.sin(phi), H0[2] + v], -1)

        P = P_(U, V)
        e = 1e-4
        Tu = P_(U + e, V) - P_(U - e, V)
        Tv = P_(U, V + e) - P_(U, V - e)
        N = _n(np.cross(Tu, Tv))
        return P + N * H[:, None], N


def build_facemask(B):
    H0 = tb.HEAD
    ms = MaskSurf()
    top = [(0, 0.044), (9, 0.041), (18, 0.030), (30, 0.017), (50, 0.013), (74, 0.010)]
    bot = [(74, -0.012), (52, -0.034), (24, -0.050), (0, -0.054)]
    pts = [(math.radians(a) * 0.1, z) for a, z in top] + [(math.radians(a) * 0.1, z) for a, z in bot]
    pts += [(-u, z) for (u, z) in reversed(pts[1:-1])]
    ol = tg.fillet(tg.ccw(np.array(pts)), 0.010, 3)
    B.add(tg.pillow(ol, 0.0014, ms.map, n=96, kind="box", r_in=0.0004, r_out=0.0006, inner=True, steps=1,
                    face_insets=(0.0, 0.004, 0.010, 0.020), scales=(0.66, 0.33), inner_scale=(0.5,), puv=lin_puv(0.0, 0.0)), "mesh")
    # binding around the edge
    O = tg.resample(tg.ccw(ol), 120)
    P, N = ms.map(O[:, 0], O[:, 1], np.full(len(O), 0.0007))
    prof = tg.rrect(0.010, 0.0038, 0.0016, 1)
    prof[:, 1] += 0.0002
    B.add(tg.sweep(P, N, prof, closed=True, half_w=0.005), "binding")
    # straps: top above the ear to the crown back, bottom around the nape
    Fh = tb.field("head")
    for side in (1, -1):
        for (z0, zs, off, a0) in ((0.010, [0.010, 0.060, 0.094, 0.100], 0.010, 74), (-0.012, [-0.012, -0.020, -0.034, -0.038], 0.006, 74)):
            phs = np.linspace(deg(a0 + 6), deg(180), 20)
            zz = np.interp(phs, [deg(a0 + 6), deg(105), deg(135), deg(180)], zs)
            ring = head_ring_path(Fh, phs * side, zz, off)
            u0 = math.radians(a0 - 3) * 0.1 * side
            start, sn = ms.map(A(u0), A(z0), A(0.0016))
            path = tg.resample_path(tg.smooth_path(np.vstack([start, ring]), 5), 26)
            ups = _n(path - (H0 + np.array([0.0, 0.0, 0.04])))
            ups[0] = sn[0]
            B.add(tg.sweep(path, ups, tg.rrect_profile(0.016, 0.0022, 0.0009, 1), caps=True, half_w=0.008), "elastic")
            P0, tu, tv, nn = frame_at(ms.map, u0, z0, 0.0016)
            B.add(tg.rbox(P0 + nn * 0.0015, (0.012, 0.020, 0.0035), 0.0014, np.stack([tu, tv, nn], axis=1), 2), "polymer", smooth_angle=45)


# --------------------------------------------------------------------------------------
# Team armband (left upper arm) and knee pads
# --------------------------------------------------------------------------------------

ARMBAND = dict(s=0.105, width=0.078, clear=0.0075, thick=0.0026)


def build_armband(B):
    sh = tb.bone("upperarm_l")
    ax = tb.ARM_DIR
    Fa = tb.field("arm_l")
    ref = _n(np.cross(ax, (1.0, 0.0, 0.0)))
    e2 = np.cross(ax, ref)
    th = np.arange(72) / 72 * 2 * math.pi
    W = ARMBAND["width"]
    prof = tg.rrect(W, ARMBAND["thick"], 0.0011, 2)
    M = tg.Mesh()
    rows = []
    rad_at = {}
    for a in np.unique(np.round(prof[:, 0], 6)):
        c = sh + ax * (ARMBAND["s"] + a)
        dirs = np.outer(np.cos(th), ref) + np.outer(np.sin(th), e2)
        hit = tb.march(Fa, c + dirs * 0.15, -dirs)
        rad_at[a] = np.linalg.norm(hit - c, axis=1).mean()
    for t in th:
        d = math.cos(t) * ref + math.sin(t) * e2
        pts = []
        for (a, b) in prof:
            r = rad_at[round(a, 6)] + ARMBAND["clear"] + b
            pts.append(sh + ax * (ARMBAND["s"] + a) + d * r)
        rows.append(M.add_verts(np.array(pts), sd=W / 2 - np.abs(prof[:, 0]), ss=np.full(len(prof), t * 0.06)))
    k = len(prof)
    for i in range(len(rows)):
        a, b = rows[i], rows[(i + 1) % len(rows)]
        for j in range(k):
            j2 = (j + 1) % k
            M.f.append((a + j, a + j2, b + j2, b + j))
    # orientation: outward
    V, F_, _ = M.arrays()
    jt = int(np.argmax(prof[:, 1]))
    f = F_[jt]
    fn = np.cross(V[f[1]] - V[f[0]], V[f[2]] - V[f[0]])
    cc = sh + ax * ARMBAND["s"]
    if fn @ (V[f[0]] - cc) < 0:
        M.f = [ff[::-1] for ff in M.f]
    B.add(M, "armband")
    # hook-and-loop overlap flap on the outer side
    rmean = float(np.mean(list(rad_at.values()))) + ARMBAND["clear"] + ARMBAND["thick"]
    out_dir = _n(np.array([0.0, 1.0, 0.25]) - ax * (ax @ np.array([0.0, 1.0, 0.25])))
    t0 = math.atan2(out_dir @ e2, out_dir @ ref)

    def flap_map(U, V, H):
        U, V, H = A(U), A(V), A(H)
        t = t0 + U / rmean
        d = np.outer(np.cos(t), ref) + np.outer(np.sin(t), e2)
        P = sh + np.outer(ARMBAND["s"] + V, ax) + d * (rmean + H)[:, None]
        return P, d

    fo = tg.rrect(0.050, W - 0.010, 0.010, 3, 0.012, 0.0)
    B.add(tg.pillow(fo, 0.0018, flap_map, n=48, kind="round", steps=1, inner=False, face_insets=(0.0, 0.002, 0.0045, 0.008), scales=(0.5,)), "armband")


KNEE = dict(clear=0.006)


class LegSurf:
    """A sleeve-like surface around the left knee (axis through the knee, along thigh-shin)."""

    def __init__(self):
        Fl = tb.field("leg_l")
        self.k = tb.bone("calf_l")
        up = _n(tb.bone("thigh_l") - self.k)
        dn = _n(tb.bone("foot_l") - self.k)
        self.ax = _n(up - dn)
        self.e1 = _n(np.array([1.0, 0.0, 0.0]) - self.ax * self.ax[0])
        self.e2 = np.cross(self.ax, self.e1)
        self.vs = np.linspace(-0.16, 0.16, 33)
        self.ts = np.radians(np.linspace(-180, 180, 73))
        R = np.zeros((len(self.vs), len(self.ts)))
        for i, v in enumerate(self.vs):
            c = self.k + self.ax * v
            d = np.outer(np.cos(self.ts), self.e1) + np.outer(np.sin(self.ts), self.e2)
            hit = tb.march(Fl, c + d * 0.2, -d)
            R[i] = np.linalg.norm(hit - c, axis=1)
        k = np.ones(5) / 5
        for _ in range(2):
            R = np.apply_along_axis(lambda r: np.convolve(np.concatenate([r[-2:], r, r[:2]]), k, mode="valid"), 1, R)
            R = np.apply_along_axis(lambda r: np.convolve(np.pad(r, 2, mode="edge"), k, mode="valid"), 0, R)
        self.R = R + KNEE["clear"]

    def radius(self, t, v):
        fi = np.interp(v, self.vs, np.arange(len(self.vs)))
        fj = np.interp(t, self.ts, np.arange(len(self.ts)))
        i0 = np.clip(np.floor(fi).astype(int), 0, len(self.vs) - 2)
        j0 = np.clip(np.floor(fj).astype(int), 0, len(self.ts) - 2)
        a, b = fi - i0, fj - j0
        R = self.R
        return R[i0, j0] * (1 - a) * (1 - b) + R[i0 + 1, j0] * a * (1 - b) + R[i0, j0 + 1] * (1 - a) * b + R[i0 + 1, j0 + 1] * a * b

    def map(self, U, V, H):
        U, V, H = A(U), A(V), A(H)

        def P_(u, v):
            t = u / 0.06
            r = self.radius(t, v)
            d = np.outer(np.cos(t), self.e1) + np.outer(np.sin(t), self.e2)
            return self.k + np.outer(v, self.ax) + d * r[:, None]

        P = P_(U, V)
        e = 1e-4
        N = _n(np.cross(P_(U + e, V) - P_(U - e, V), P_(U, V + e) - P_(U, V - e)))
        return P + N * H[:, None], N


def build_kneepad_left(B, piece="Left"):
    ls = LegSurf()
    base = tg.rrect(0.112, 0.200, 0.040, 4, 0.0, -0.012)
    B.add(tg.pillow(base, 0.012, ls.map, n=60, kind="round", puff=0.003, steps=2, face_insets=(0.0, 0.0025, 0.0055, 0.011, 0.02), scales=(0.6, 0.3)), "cordura_pad", piece)
    cm = offset_map(ls.map, dh=0.012)
    cap = tg.fillet(np.array([(-0.040, -0.072), (0.040, -0.072), (0.046, 0.010), (0.034, 0.058), (-0.034, 0.058), (-0.046, 0.010)]), 0.022, 5)
    B.add(tg.pillow(cap, 0.010, cm, n=60, kind="round", puff=0.012, steps=2, inner=False, face_insets=(0.0, 0.002, 0.005, 0.010, 0.018), scales=(0.6, 0.3)), "polymer", piece)
    tread = tg.fillet(np.array([(-0.030, -0.066), (0.030, -0.066), (0.034, -0.028), (-0.034, -0.028)]), 0.010, 3)
    B.add(tg.pillow(tread, 0.004, offset_map(cm, dh=0.0105), n=40, kind="round", steps=1, inner=False, face_insets=(0.0, 0.002, 0.005), scales=(0.5,)), "rubber", piece)
    # elastic straps above and below the knee, buckles on the outer side
    for v in (0.088, -0.112):
        ts = np.radians(np.linspace(-180, 180, 49))[:-1]
        P, N = ls.map(ts * 0.06, np.full(len(ts), v), np.full(len(ts), 0.0))
        B.add(tg.sweep(P, N, tg.rrect_profile(0.030, 0.0026, 0.0011, 1), closed=True, half_w=0.015), "elastic", piece)
        B.add(box_on(ls.map, 0.090 * 0.06 / 0.06 * 1.0, v, 0.004, (0.026, 0.036, 0.006), 0.0025, 2), "polymer", piece, smooth_angle=45)


def build_kneepads(B):
    build_kneepad_left(B, "Left")


# --------------------------------------------------------------------------------------
# Asset registry
# --------------------------------------------------------------------------------------

SPECS = {
    "PlateCarrier": dict(fn=build_carrier, res={"Body": 4096}, bone="spine_04", slot="Torso", colorway="Kit"),
    "Helmet": dict(fn=build_helmet, res={"Body": 2048}, bone="head", slot="Head", colorway="Helmet"),
    "SoftCap": dict(fn=build_softcap, res={"Body": 2048}, bone="head", slot="Head", colorway="Cap"),
    "Goggles": dict(fn=build_goggles, res={"Body": 2048}, bone="head", slot="Eyes", colorway="Kit"),
    "FaceMask": dict(fn=build_facemask, res={"Body": 2048}, bone="head", slot="Face", colorway="Kit"),
    "Armband": dict(fn=build_armband, res={"Body": 1024}, bone="upperarm_l", align="lowerarm_l", slot="Arm", colorway="None"),
    "KneePads": dict(fn=build_kneepads, res={"Left": 2048}, bone="calf_l", align="foot_l", slot="Knees", colorway="Kit", mirror={"Right": "Left"}),
}
ASSET_ORDER = ["PlateCarrier", "Helmet", "SoftCap", "Goggles", "FaceMask", "Armband", "KneePads"]

TINT_DEFAULTS = {"TintRoughness": 0.5, "RoughnessDetail": 1.0, "TintMetallic": 0.0}
GLASS = {"Tint": [0.025, 0.027, 0.030], "Opacity": 0.62, "Roughness": 0.04}


def piece_bone(aid, piece):
    spec = SPECS[aid]
    bone = spec["bone"]
    align = spec.get("align")
    if piece in spec.get("mirror", {}):
        bone = bone[:-2] + "_r" if bone.endswith("_l") else bone
        align = align[:-2] + "_r" if align and align.endswith("_l") else align
    return bone, align


def anchor_block(aid, piece=None):
    bone, align = piece_bone(aid, piece) if piece else (SPECS[aid]["bone"], SPECS[aid].get("align"))
    a = {"Bone": bone, "Offset": [0.0, 0.0, 0.0], "Rotation": [0.0, 0.0, 0.0], "Scale": 1.0}
    if align:
        a["AlignBone"] = align
        a["ModelDir"] = tb.dir_ue(tb.bone(align) - tb.bone(bone))
    a["AssumedBonePos"] = tb.bone_ue(bone)
    return a


# --------------------------------------------------------------------------------------
# Export + JSON
# --------------------------------------------------------------------------------------


def export_fbx(ob, path):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH"}, axis_forward="X", axis_up="Z", apply_unit_scale=True, global_scale=1.0,
        apply_scale_options="FBX_SCALE_ALL", use_tspace=True, mesh_smooth_type="FACE", add_leaf_bones=False, use_mesh_modifiers=True,
        path_mode="STRIP", embed_textures=False, bake_anim=False)
    ob.select_set(False)


def ue(p):
    return [round(p[0] * 100, 1) + 0.0, round(-p[1] * 100, 1) + 0.0, round(p[2] * 100, 1) + 0.0]


def bounds_ue(obs):
    lo, hi = studio.bbox(obs)
    a, b = ue(lo), ue(hi)
    return {"Min": [min(a[i], b[i]) for i in range(3)], "Max": [max(a[i], b[i]) for i in range(3)]}


def assign_single(ob, name):
    me = ob.data
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    me.materials.clear()
    me.materials.append(m)
    me.polygons.foreach_set("material_index", np.zeros(len(me.polygons), np.int32))
    me.update()


def mirror_object(src, name):
    me = src.data.copy()
    me.name = name
    me.transform(Matrix.Diagonal((1.0, -1.0, 1.0, 1.0)))
    me.flip_normals()
    ob = bpy.data.objects.new(name, me)
    for c in src.users_collection:
        c.objects.link(ob)
    return ob


def build_asset(aid, res_scale, do_bake, coll, seed):
    """Builds, (bakes) and exports one asset; returns its JSON entry."""
    t0 = time.time()
    spec = SPECS[aid]
    out_dir = os.path.join(OUT_ROOT, aid)
    os.makedirs(out_dir, exist_ok=True)
    B = Builder(aid, coll)
    spec["fn"](B)
    obs = B.finish()
    log(f"  {aid}: geometry {time.time() - t0:.0f}s")
    pieces = []
    order = list(obs) + list(spec.get("mirror", {}))
    built = {}
    for piece in order:
        bone, _ = piece_bone(aid, piece)
        if piece in spec.get("mirror", {}):
            src = spec["mirror"][piece]
            ob = mirror_object(built[src], f"SM_{aid}_{piece}")  # already relative to the source bone; mirrored = relative to its twin
            res = max(256, int(spec["res"][src] * res_scale))
            for k, p in bk.texture_paths(out_dir, aid, src).items():
                if os.path.exists(p):
                    shutil.copyfile(p, bk.texture_paths(out_dir, aid, piece)[k])
            assign_single(ob, f"M_{aid}_{piece}")
        else:
            ob = obs[piece]
            ob.data.transform(Matrix.Translation(Vector(tuple(-tb.bone(bone)))))
            tg.weld(ob, 1e-7)
            if piece == "Glass":
                res = 0
                assign_single(ob, f"M_{aid}_{piece}")
            else:
                res = max(256, int(spec["res"].get(piece, 2048) * res_scale))
                bk.uv_unwrap(ob, res, 62.0, 4)
                if do_bake:
                    t1 = time.time()
                    tbk.bake_piece(ob, out_dir, aid, piece, res, seed=seed, log=log)
                    log(f"  {aid}.{piece}: baked {res}px in {time.time() - t1:.0f}s")
                assign_single(ob, f"M_{aid}_{piece}")
        built[piece] = ob
        tris = tg.tri_count(ob)
        budget = 5000 if piece == "Glass" else TRI_BUDGET
        if tris > budget:
            log(f"WARNING {aid}.{piece}: {tris} triangles > {budget}")
        export_fbx(ob, os.path.join(out_dir, f"SM_{aid}_{piece}.fbx"))
        e = {"Name": piece, "Kind": "Glass" if piece == "Glass" else "Static", "Slots": [f"M_{aid}_{piece}"], "Bounds": bounds_ue([ob]), "Triangles": tris}
        if res:
            e["TextureSize"] = res
        if spec.get("mirror"):
            e["Anchor"] = anchor_block(aid, piece)
        pieces.append(e)
        log(f"  {aid}.{piece}: {tris} tris, bone {bone}")
    mins = [p["Bounds"]["Min"] for p in pieces]
    maxs = [p["Bounds"]["Max"] for p in pieces]
    tgb = {"Slot": spec["slot"], "Colorway": spec["colorway"]}
    tgb.update(TINT_DEFAULTS)
    if any(p["Name"] == "Glass" for p in pieces):
        tgb["Glass"] = GLASS
    entry = {
        "Pieces": pieces,
        "Points": {"Pivot": [0.0, 0.0, 0.0]},
        "Bounds": {"Min": [min(m[i] for m in mins) for i in range(3)], "Max": [max(m[i] for m in maxs) for i in range(3)]},
        "Anchor": anchor_block(aid),
        "TeamGear": tgb,
        "Notes": "Unreal cm, character space (X forward, Y right, Z up). Origin = the anchor bone's pivot in the assumed UE5 Manny reference pose; "
        "UAirsoftTeamGearComponent attaches it to that bone from the skeleton's reference pose. Offset/Rotation/Scale are tuned with airsoft.gear.tune. "
        "Mask: R = kit colourway (PrimaryTint), G = SecondaryTint, B = team colour (AccentTint).",
    }
    log(f"  {aid}: done in {time.time() - t0:.0f}s")
    return entry


def write_json(entries):
    path = os.path.join(gl.DATA_DIR, "Gear.json")
    data = {"Version": 1, "Assets": {}}
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            pass
    data["Version"] = 1
    data.setdefault("Assets", {})
    for aid, e in entries.items():
        data["Assets"][aid] = e
    data["TeamGear"] = {
        "Version": 1,
        "Colorways": COLORWAYS,
        "Slots": SLOTS,
        "FallbackHeadCenter": ue(tb.CRANIUM_C),
        "Notes": "Per-player variant: each slot picks an asset by weight (and Chance for optional slots) and each colourway group picks one entry, "
        "all hashed from the PlayerState id. Tints are linear; albedo = 0.75 * tint (the baked base colour is neutral grey 0.75 where the mask is set). "
        "Team colours come from AirsoftColors::Team.",
    }
    with open(path, "w", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    log(f"wrote {path}")


# --------------------------------------------------------------------------------------
# Renders
# --------------------------------------------------------------------------------------

PRODUCT = {
    # asset: (view direction, team, colourway group index)
    "PlateCarrier": ((1.0, -0.75, 0.22), "Blue", 2),
    "Helmet": ((1.0, -0.85, 0.42), "Red", 1),
    "SoftCap": ((1.0, -0.95, 0.38), "Blue", 0),
    "Goggles": ((1.0, -0.62, 0.22), "Red", 0),
    "FaceMask": ((1.0, -0.75, 0.10), "Blue", 2),
    "Armband": ((0.35, 1.0, 0.35), "Red", 0),
    "KneePads": ((1.0, -0.45, 0.22), "Blue", 1),
}


def tints_for(aid, team, cw_index):
    group = SPECS[aid]["colorway"]
    t = {"A": tuple(TEAM[team])}
    if group in COLORWAYS:
        cw = COLORWAYS[group][cw_index % len(COLORWAYS[group])]
        t["P"] = tuple(cw["Primary"])
        t["S"] = tuple(cw["Secondary"])
    else:
        t["P"] = t["S"] = (0.04, 0.04, 0.043)
    return t


def import_asset(aid, coll, tints, offset=(0, 0, 0), rot_z=0.0, proxy_res=2048):
    """Imports an asset's exported pieces, placed at their anchor bones (+ offset), with preview materials."""
    out_dir = os.path.join(OUT_ROOT, aid)
    spec = SPECS[aid]
    names = [os.path.basename(f)[len(f"SM_{aid}_"):-4] for f in sorted(os.listdir(out_dir)) if f.startswith(f"SM_{aid}_") and f.endswith(".fbx")]
    obs = []
    for piece in names:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=os.path.join(out_dir, f"SM_{aid}_{piece}.fbx"), axis_forward="X", axis_up="Z")
        new = [o for o in bpy.data.objects if o not in before]
        bone, _ = piece_bone(aid, piece)
        for o in new:
            if o.type != "MESH":
                bpy.data.objects.remove(o)
                continue
            for c in list(o.users_collection):
                c.objects.unlink(o)
            coll.objects.link(o)
            o.matrix_world = Matrix.Translation(Vector(offset)) @ Matrix.Rotation(rot_z, 4, "Z") @ Matrix.Translation(Vector(tuple(tb.bone(bone))))
            if piece == "Glass":
                m = tbk.glass_material(f"PVG_{aid}", tuple(GLASS["Tint"]))
            else:
                paths = bk.texture_paths(out_dir, aid, piece)
                if all(os.path.exists(p) for p in paths.values()):
                    m = bk.preview_material(f"PV_{aid}_{piece}_{len(bpy.data.materials)}", paths, tints, proxy_res=proxy_res)
                else:
                    m = gl.simple_mat(f"PVF_{aid}", (0.05, 0.05, 0.05), 0.7)
            o.data.materials.clear()
            o.data.materials.append(m)
            obs.append(o)
    del spec
    return obs


def save_jpg(png, jpg, quality=92):
    """Re-encodes a rendered (display-referred) PNG as JPEG without any colour transform."""
    os.makedirs(os.path.dirname(jpg), exist_ok=True)
    try:
        from PIL import Image

        Image.open(png).convert("RGB").save(jpg, quality=quality, subsampling=0)
        return
    except ImportError:
        pass
    im = bpy.data.images.load(png)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    o = bpy.data.images.new("__jpg", w, h, alpha=False)
    o.pixels.foreach_set(a)
    o.filepath_raw = jpg
    o.file_format = "JPEG"
    try:
        o.save(quality=quality)
    except TypeError:
        o.save()
    bpy.data.images.remove(o)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    th = int(os.environ.get("TEAMGEAR_THREADS", "0"))
    if th:
        scn.render.threads_mode = "FIXED"
        scn.render.threads = th


def setup_studio():
    """The shared studio rig with AgX Punchy: saturated team colours survive the view transform."""
    rig = studio.setup_studio()
    try:
        bpy.context.scene.view_settings.look = "AgX - Punchy"
    except Exception:
        pass
    return rig


def render_products(ids, samples, res=(1920, 1080)):
    os.makedirs(SCRATCH, exist_ok=True)
    for aid in ids:
        if not os.path.isdir(os.path.join(OUT_ROOT, aid)):
            continue
        reset_scene()
        coll = bpy.data.collections.new("R")
        bpy.context.scene.collection.children.link(coll)
        vd, team, cw = PRODUCT[aid]
        obs = import_asset(aid, coll, tints_for(aid, team, cw))
        if not obs:
            continue
        rig = setup_studio()
        lo, hi = studio.bbox(obs)
        studio.frame(rig, lo, hi, view_dir=vd, lens=70, margin=1.12)
        png = os.path.join(SCRATCH, f"{aid}.png")
        t0 = time.time()
        studio.render(png, res, samples=samples)
        save_jpg(png, os.path.join(RENDER_DIR, f"{aid}.jpg"))
        log(f"  wrote {RENDER_DIR}/{aid}.jpg ({time.time() - t0:.0f}s)")


LINEUP = [
    # (team, head asset, kit cw, head cw, knee pads, x offset, rotation deg)
    ("Blue", "Helmet", 2, 1, True, -1.35, -24.0),
    ("Red", "SoftCap", 0, 1, False, -0.45, -14.0),
    ("Blue", "Helmet", 2, 1, True, 0.45, 166.0),
    ("Red", "SoftCap", 0, 1, False, 1.35, 156.0),
]


def render_lineup(samples, res=(3840, 1800)):
    reset_scene()
    coll = bpy.data.collections.new("Lineup")
    bpy.context.scene.collection.children.link(coll)
    F, v, q = tb.mannequin_mesh(0.007)
    q = gl.fix_winding(v, q, F)
    base = gl.mesh_object("Mannequin", v, q, coll)
    mm = bpy.data.materials.new("Mannequin")
    b = mm.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.20, 0.20, 0.21, 1.0)
    b.inputs["Roughness"].default_value = 0.42
    b.inputs["Coat Weight"].default_value = 0.15
    base.data.materials.append(mm)
    shown = []
    for team, head, kcw, hcw, knees, x, rz in LINEUP:
        off = (0.0, x, 0.0)  # the camera looks along -X, so +Y is screen right
        R = math.radians(rz)
        man = bpy.data.objects.new("Man", base.data)
        coll.objects.link(man)
        man.matrix_world = Matrix.Translation(Vector(off)) @ Matrix.Rotation(R, 4, "Z")
        shown.append(man)
        for aid in ("PlateCarrier", head, "Goggles", "FaceMask", "Armband") + (("KneePads",) if knees else ()):
            if not os.path.isdir(os.path.join(OUT_ROOT, aid)):
                continue
            cw = hcw if aid == head else kcw
            shown += import_asset(aid, coll, tints_for(aid, team, cw), off, R, proxy_res=1024)
    coll.objects.unlink(base)
    rig = setup_studio()
    lo, hi = studio.bbox(shown)
    studio.frame(rig, lo, hi, view_dir=(1.0, -0.06, 0.16), lens=50, margin=1.04)
    png = os.path.join(SCRATCH, "_TeamGear_Lineup.png")
    t0 = time.time()
    studio.render(png, res, samples=samples)
    save_jpg(png, os.path.join(RENDER_DIR, "_TeamGear_Lineup.jpg"))
    log(f"  wrote {RENDER_DIR}/_TeamGear_Lineup.jpg ({time.time() - t0:.0f}s)")


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    res = int(argv[argv.index("--res") + 1]) if "--res" in argv else 4096
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 32
    skip = {argv[i + 1] for i, a in enumerate(argv) if a in ("--res", "--samples")}
    only = [a for a in argv if not a.startswith("--") and a not in skip]
    ids = [a for a in ASSET_ORDER if not only or a in only]
    unknown = [a for a in only if a not in SPECS]
    if unknown:
        log("unknown assets:", unknown)
    if "--renders-only" in flags:
        render_products(ids, samples)
        render_lineup(samples)
        return
    if "--lineup-only" in flags:
        render_lineup(samples)
        return
    entries = {}
    for i, aid in enumerate(ids):
        reset_scene()
        coll = bpy.data.collections.new(aid)
        bpy.context.scene.collection.children.link(coll)
        log(f"== {aid}")
        entries[aid] = build_asset(aid, res / 4096.0, "--no-bake" not in flags, coll, seed=float(i + 1))
    if entries:
        write_json(entries)
    if "--no-render" not in flags:
        render_products(ids, samples)
        render_lineup(samples)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--" in a:
        a = a[a.index("--") + 1:]
    main(a)
