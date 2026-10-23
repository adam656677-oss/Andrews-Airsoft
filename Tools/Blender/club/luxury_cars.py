"""Ultra-luxury street cars for the Velvet Club and the Nightjar Garage (marque: AVERNE, invented).

    Car_Limousine   "Averne Regent"     stately long-wheelbase saloon, upright vertical-bar grille, coach doors,
                                         chrome beltline, two-tone paint (role mask G = upper body)
    Car_GrandTourer "Averne Meridian"   front-engine long-hood fastback coupe, slim LED light bars
    Car_Hypercar    "Averne Vanta"      mid-engine hypercar: low, wide, side intakes, carbon aero, centre-lock wheels
    Car_SUV         "Averne Bastion"    upright full-size luxury SUV, chrome accents, privacy glass

All shapes, names, the lozenge emblem and the light signatures are original. Build with
Tools/Blender/club/build_cars.py (bakes, JSON, product renders); the assets are also registered with
club_registry so build_club.py can rebuild them.

Surface model (asset space, metres, front +X, floor-centre origin):
* Lower body: a loft of feature-aligned half-sections (floor, rocker, sill crease, door bulge, shoulder
  crease, belt edge, crowned hood / deck top). Wheel arches (and the hypercar's side intakes) are boolean
  cuts; the top between windscreen base and backlight base is removed so the cabin is an open tub.
* Greenhouse: a parametric arch surface S(x, s) sitting on the belt (s = 0 belt edge .. 1 roof centre).
  It is meshed as a warped grid whose columns run exactly along the pillar / glass edges, so glass,
  pillars, roof and the chrome DLO surround have clean, exact boundaries (no stair-stepping).
* Details (lamps, grille, plates, handles, badges, intakes) are conformal patches projected onto the
  body surface (front_x / rear_x / side_y / top_z).
Panel gaps are baked from analytic lines (groove in the normal map, dark in BC, mask cleared).

Pieces: Body (4K, paint mask R primary / G secondary), Wheels (2K), Interior (2K), Glass,
GlassPrivacy (SUV rear), Emissive (head / tail light signature, lit on the night maps).
"""

import math
import bisect
import bpy
import bmesh
import numpy as np
from mathutils import Vector as V, Matrix

import propkit as pk
from propkit import round_poly, rrect_pts, circle_pts
from propkit_mats import MATS, _out, paint, metal, leather, plastic, rubber, emissive, decal, glass, wood
from club_registry import asset, font

# ======================================================================================
# Small math helpers
# ======================================================================================


def ss(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


_SLOPES = {}


def _slopes(table):
    key = id(table)
    hit = _SLOPES.get(key)
    if hit is not None and hit[0] is table:
        return hit[1], hit[2], hit[3]
    xs = [p[0] for p in table]
    ys = [p[1] for p in table]
    n = len(xs)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):
        if abs(d[i]) < 1e-12:
            m[i] = m[i + 1] = 0.0
        else:
            a, b = m[i] / d[i], m[i + 1] / d[i]
            q = a * a + b * b
            if q > 9:
                t = 3 / math.sqrt(q)
                m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    _SLOPES[key] = (table, xs, ys, m)
    return xs, ys, m


def interp(table, x):
    """Monotone (Fritsch-Carlson) cubic through (x, y) knots; clamped outside."""
    xs, ys, m = _slopes(table)
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = max(0, min(len(xs) - 2, bisect.bisect_left(xs, x) - 1))
    h = xs[i + 1] - xs[i]
    t = (x - xs[i]) / h
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]


def resample(pts, n):
    P = [V(p) for p in pts]
    d = [0.0]
    for a, b in zip(P[:-1], P[1:]):
        d.append(d[-1] + (b - a).length)
    L = d[-1] if d[-1] > 1e-9 else 1.0
    out, j = [], 0
    for i in range(n):
        s = L * i / (n - 1)
        while j < len(d) - 2 and d[j + 1] < s:
            j += 1
        seg = d[j + 1] - d[j]
        t = (s - d[j]) / seg if seg > 1e-9 else 0.0
        out.append(P[j].lerp(P[j + 1], t))
    return out


def chaikin(pts, it=2, closed=False):
    P = [V(p) for p in pts]
    for _ in range(it):
        Q = [] if closed else [P[0]]
        rng = range(len(P)) if closed else range(len(P) - 1)
        for i in rng:
            a, b = P[i], P[(i + 1) % len(P)]
            Q.append(a.lerp(b, 0.25))
            Q.append(a.lerp(b, 0.75))
        if not closed:
            Q.append(P[-1])
        P = Q
    return P


def pip(poly, y, z):
    """Point in polygon (list of (y, z))."""
    inside = False
    n = len(poly)
    for i in range(n):
        y1, z1 = poly[i]
        y2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            yi = y1 + (z - z1) * (y2 - y1) / (z2 - z1)
            if y < yi:
                inside = not inside
    return inside


# ======================================================================================
# Car surface model
# ======================================================================================

SEG = [4, 3, 4, 5, 3, 3, 2, 3, 3]   # points per lower key segment (floor .. belt edge)
TOP = [0.0, 0.07, 0.16, 0.27, 0.40, 0.54, 0.68, 0.81, 0.92, 1.0]   # hood / deck crown samples


class Car:
    """Tables are (x, value) knots. plan_r rounds the plan view at the ends; the greenhouse spans x_ws..x_bl."""

    def __init__(self, **kw):
        self.lean_f = 0.0
        self.lean_r = 0.0
        self.n_exp = 4.0
        self.bow = 0.0
        self.__dict__.update(kw)
        self.half = self.x1  # x0 = -x1
        self._phi = None

    # ---- plan / profile ----------------------------------------------------------
    def plan(self, x):
        r_f, r_r, hw = self.plan_rf, self.plan_rr, interp(self.width, x)
        if x > 0:
            d = x - (self.x1 - r_f)
            r = r_f
        else:
            d = (self.x0 + r_r) - x
            r = r_r
        if d <= 0:
            return 1.0
        d = min(d, r * 0.999)
        return max(0.3, (hw - r + math.sqrt(r * r - d * d)) / hw)

    def w(self, x):
        return interp(self.width, x) * self.plan(x)

    def tuck(self, x):
        return interp(self.tuck_t, x)

    def yb(self, x):
        return self.w(x) - self.tuck(x)

    def belt(self, x):
        return interp(self.belt_t, x)

    def deck(self, x):
        return interp(self.deck_t, x)

    def roof(self, x):
        return interp(self.roof_t, x)

    def keys(self, x):
        w = self.w(x)
        zb = interp(self.zbot, x)
        zs = interp(self.zsill, x)
        zh = interp(self.zsh, x)
        bt = self.belt(x)
        tk = self.tuck(x)
        zs = max(zs, zb + 0.06)
        zh = min(max(zh, zs + 0.05), bt - 0.02)
        cc = getattr(self, "concave", 0.010)
        lo = [(0.0, zb), (w * 0.80, zb), (w * 0.955, zb + 0.032), (w * 0.982, zs),
              (w * 0.996, zs + (zh - zs) * 0.45), (w - cc, zh - min(0.07, (zh - zs) * 0.3)), (w, zh),
              (w - tk * 0.16, zh + 0.014), (w - tk * 0.62, zh + (bt - zh) * 0.62), (w - tk, bt)]
        return lo

    def topsurf(self, x, y):
        yb = self.yb(x)
        bt, dk = self.belt(x), self.deck(x)
        u = min(1.0, abs(y) / max(yb, 1e-4))
        return bt + (dk - bt) * (1 - u * u)

    def half_section(self, x):
        lo = self.keys(x)
        pts = []
        for k in range(len(lo) - 1):
            seg = resample([lo[k], lo[k + 1]], SEG[k] + 1)
            pts.extend((p.x, p.y) for p in seg[:-1])
        yb = self.yb(x)
        for u in TOP:
            y = yb * (1 - u)
            pts.append((y, self.topsurf(x, y)))
        return pts

    def poly(self, x):
        h = self.half_section(x)
        return h + [(0.0, h[-1][1])]

    def side_y(self, x, z):
        best = None
        h = self.half_section(x)
        for (y1, z1), (y2, z2) in zip(h[:-1], h[1:]):
            if (z1 - z) * (z2 - z) <= 0 and abs(z2 - z1) > 1e-7:
                y = y1 + (y2 - y1) * (z - z1) / (z2 - z1)
                best = y if best is None else max(best, y)
        return best if best is not None else 0.0

    def top_z(self, x, y):
        best = None
        h = self.half_section(x)
        y = abs(y)
        for (y1, z1), (y2, z2) in zip(h[:-1], h[1:]):
            if (y1 - y) * (y2 - y) <= 0 and abs(y2 - y1) > 1e-7:
                z = z1 + (z2 - z1) * (y - y1) / (y2 - y1)
                best = z if best is None else max(best, z)
        return best if best is not None else interp(self.zbot, x)

    def inside(self, x, y, z):
        if x <= self.x0 or x >= self.x1:
            return False
        return pip(self.poly(x), abs(y), z)

    def _end_grid(self, front):
        key = "_eg_f" if front else "_eg_r"
        g = getattr(self, key, None)
        if g is None:
            xs = np.linspace(self.x1 - 1.4, self.x1 - 1e-4, 701) if front else np.linspace(self.x0 + 1.4, self.x0 + 1e-4, 701)
            g = (xs, [self.poly(float(x)) for x in xs])
            setattr(self, key, g)
        return g

    def end_x(self, y, z, front=True, it=10):
        """Surface x of the front (or rear) end at (y, z): binary search on a cached 2 mm station grid, then bisection."""
        xs, polys = self._end_grid(front)
        ay = abs(y)
        if not pip(polys[0], ay, z):
            return None
        lo, hi = 0, len(xs) - 1
        if pip(polys[hi], ay, z):
            return float(xs[hi])
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if pip(polys[mid], ay, z):
                lo = mid
            else:
                hi = mid
        a, b = float(xs[lo]), float(xs[hi])
        for _ in range(it):
            m = (a + b) / 2
            if self.inside(m, y, z):
                a = m
            else:
                b = m
        return (a + b) / 2

    # ---- greenhouse --------------------------------------------------------------------
    def phi_of_s(self, s):
        if self._phi is None:
            n = self.n_exp
            N = 400
            ph = [0.5 * math.pi * i / (N - 1) for i in range(N)]
            pts = []
            for p in ph:
                c = math.cos(p) ** (2 / n)
                v = math.sin(p) ** (2 / n)
                pts.append(V((c * (1.0 - 0.18 * v), 0.6 * v)))
            d = [0.0]
            for a, b in zip(pts[:-1], pts[1:]):
                d.append(d[-1] + (b - a).length)
            self._phi = (ph, [x / d[-1] for x in d])
        ph, d = self._phi
        s = min(max(s, 0.0), 1.0)
        i = max(1, min(len(d) - 1, int(np.searchsorted(d, s))))
        t = (s - d[i - 1]) / max(d[i] - d[i - 1], 1e-9)
        return lerp(ph[i - 1], ph[i], t)

    def H(self, x):
        return max(0.0, self.roof(x) - self.deck(x))

    def gh(self, x, s, side=1):
        """Greenhouse point at station x, arch fraction s (0 belt edge .. 1 roof centre)."""
        x = min(max(x, self.x_bl), self.x_ws)
        n = self.n_exp
        p = self.phi_of_s(s)
        c = math.cos(p) ** (2 / n)
        v = math.sin(p) ** (2 / n)
        yb = self.yb(x)
        lean = interp(self.lean_t, x)          # inward lean of the side glass at the roof (m)
        y = c * (yb - lean * v) + self.bow * math.sin(math.pi * min(1.0, s / max(self.s_rail, 1e-3))) * min(1.0, self.H(x) / 0.3) * (s < self.s_rail)
        z = self.topsurf(x, y) + self.H(x) * v
        return V((x, side * y, z))

    def gh_normal(self, x, s, side=1):
        e = 0.004
        p = self.gh(x, s, side)
        dx = self.gh(min(x + e, self.x_ws), s, side) - self.gh(max(x - e, self.x_bl), s, side)
        ds = self.gh(x, min(s + e, 1.0), side) - self.gh(x, max(s - e, 0.0), side)
        nrm = dx.cross(ds) if side > 0 else ds.cross(dx)
        if nrm.length < 1e-9:
            return V((0, side, 0))
        nrm.normalize()
        # outward: away from the car centre line / up
        if nrm.dot(V((0, p.y, p.z - (self.belt(x) - 0.3)))) < 0:
            nrm = -nrm
        return nrm


# ======================================================================================
# Material recipes (registered into propkit_mats.MATS)
# ======================================================================================


def _vec2(nb, a, b):
    return nb.combine(a, b, 0.0)


def gap_field(nb, c, gaps):
    """Distance-based panel-gap mask from analytic polylines. Each gap: (plane, pts, gate)
    plane XZ: side view (x, z) on |n.y| > gate; XY: top view (x, |y|) on n.z > gate;
    YZ: end view (|y|, z) on |n.x| > gate (front if pts flagged by x sign in gate tuple)."""
    x, y, z = nb.sep(c.P)
    nx, ny, nz = nb.sep(c.Nobj)
    ay = nb.math("ABSOLUTE", y)
    total = None
    for g in gaps:
        plane, pts, gate = g[0], g[1], g[2]
        width = g[3] if len(g) > 3 else 0.0022
        if plane == "XZ":
            p2 = _vec2(nb, x, z)
            gm = nb.ss(gate, gate + 0.15, nb.math("ABSOLUTE", ny))
        elif plane == "XY":
            p2 = _vec2(nb, x, ay)
            gm = nb.ss(gate, gate + 0.15, nz)
        else:  # "YZf" front / "YZr" rear
            p2 = _vec2(nb, ay, z)
            gm = nb.ss(gate, gate + 0.15, nx if plane == "YZf" else nb.mul(nx, -1.0))
        dmin = None
        for (a, b) in zip(pts[:-1], pts[1:]):
            A = (a[0], a[1], 0.0)
            BA = (b[0] - a[0], b[1] - a[1], 0.0)
            L2 = max(BA[0] ** 2 + BA[1] ** 2, 1e-9)
            pa = nb.vmath("SUBTRACT", p2, A)
            t = nb.clamp(nb.div(nb.vmath("DOT_PRODUCT", pa, BA), L2))
            q = nb.vmath("SUBTRACT", pa, nb.vscale(BA, t))
            d = nb.vmath("LENGTH", q)
            dmin = d if dmin is None else nb.mn(dmin, d)
        gm_ = nb.mul(nb.ss(width + 0.0012, width, dmin), gm)
        gr_ = nb.mul(nb.ss(width + 0.004, width * 0.4, dmin), gm)
        total = (gm_, gr_) if total is None else (nb.mx(total[0], gm_), nb.mx(total[1], gr_))
    return total if total is not None else (0.0, 0.0)


def _vscale_fix(nb):
    """propkit_mats.NB.vscale returns a vector socket; make sure SCALE works with socket factors."""
    return nb


def pw_linear(nb, x, table):
    """Piecewise-linear f(x) through (x, y) knots as a node chain (clamped at the ends)."""
    out = table[0][1]
    for (x0, y0), (x1, y1) in zip(table[:-1], table[1:]):
        out = nb.add(out, nb.mul(nb.maprange(x, x0, x1, 0.0, 1.0), y1 - y0))
    return out


def lux_paint(nb, c, gaps=(), mask=1.0, rough=0.06, col=(0.75, 0.75, 0.75), split=None, coachline=None):
    """Clean deep paint (neutral grey, tinted in engine). split: z(x) knots - above the line the role mask
    switches to secondary (two-tone upper body, crisp per texel). coachline: (z(x) knots, rgb) pinstripe."""
    op, _ = nb.noise(c.P, 340.0, 2.0, 0.5)
    sm, _ = nb.noise(c.P, 4.0, 4.0, 0.6)
    col_s = nb.cmul(col, nb.add(0.985, nb.mul(sm, 0.03)))
    g, groove = gap_field(nb, c, gaps) if gaps else (0.0, 0.0)
    if split:
        x, y, z = nb.sep(c.P)
        zs_ = pw_linear(nb, x, split)
        above = nb.math("GREATER_THAN", nb.sub(z, zs_), 0.0)
        mask = nb.sub(1.0, nb.mul(above, 0.5))
    shade = nb.clamp(nb.mul(c.cav, 0.6))
    col_s = nb.cmul(col_s, nb.sub(1.0, nb.mul(shade, 0.08)))
    r = nb.add(rough, nb.mul(op, 0.02))
    m = mask
    h = nb.mul(op, 0.08)
    if coachline:
        x, y, z = nb.sep(c.P)
        zc = pw_linear(nb, x, coachline[0])
        cl = nb.ss(0.0022, 0.0012, nb.math("ABSOLUTE", nb.sub(z, zc)))
        cl = nb.mul(cl, nb.ss(0.5, 0.7, nb.math("ABSOLUTE", nb.sep(c.Nobj)[1])))
        col_s = nb.mixc(cl, col_s, coachline[1])
        r = nb.mix(cl, r, 0.25)
    if gaps:
        col_s = nb.mixc(g, col_s, (0.004, 0.004, 0.005))
        col_s = nb.cmul(col_s, nb.sub(1.0, nb.mul(groove, 0.35)))
        r = nb.mix(g, r, 0.7)
        h = nb.sub(h, groove)                            # role mask kept: the gap BC is near-black under any tint
    return _out(col_s, r, 0.0, h, 0.25, 0.0006, m)


def lux_metal(nb, c, col=(0.8, 0.8, 0.82), rough=0.03, brushed=0.0, radial=False):
    br, _ = nb.noise(nb.vmath("MULTIPLY", c.gP, (3.0, 900.0, 900.0)), 1.0, 2.0, 0.6)
    col_s = nb.cmul(col, nb.add(0.97, nb.mul(br, 0.06 * brushed)))
    col_s = nb.cmul(col_s, nb.mix(nb.mul(c.cav, 0.4), 1.0, 0.7))
    r = nb.add(rough, nb.mul(br, 0.08 * brushed))
    return _out(col_s, r, 1.0, nb.mul(br, brushed * 0.3), 0.1, 0.0002)


def lux_carbon(nb, c, col=(0.018, 0.019, 0.021), rough=0.07, k=260.0):
    """2x2 twill carbon weave, projected on the dominant object-space plane."""
    x, y, z = nb.sep(c.P)
    nx, ny, nz = nb.sep(c.Nobj)
    fy = nb.ss(0.5, 0.6, nb.math("ABSOLUTE", ny))
    fz = nb.ss(0.5, 0.6, nb.math("ABSOLUTE", nz))
    u = nb.mix(fz, nb.mix(fy, y, x), x)
    v = nb.mix(fz, z, y)
    a = nb.math("FLOOR", nb.mul(u, k))
    b = nb.math("FLOOR", nb.mul(v, k))
    tw = nb.math("LESS_THAN", nb.math("FRACT", nb.div(nb.add(a, b), 4.0)), 0.5)
    fu = nb.math("SINE", nb.mul(nb.math("FRACT", nb.mul(u, k)), math.pi))
    fv = nb.math("SINE", nb.mul(nb.math("FRACT", nb.mul(v, k)), math.pi))
    sheen = nb.mix(tw, fv, fu)
    col_s = nb.cmul(col, nb.add(0.55, nb.mul(sheen, 1.3)))
    r = nb.add(rough, nb.mul(nb.sub(1.0, sheen), 0.12))
    return _out(col_s, r, 0.0, nb.mul(sheen, 0.2), 0.15, 0.0003)


def lux_leather(nb, c, col=(0.4, 0.3, 0.2), rough=0.45, quilt=0.0, k=22.0, stitch=(0.6, 0.55, 0.45)):
    o = leather(nb, c, col=col, rough=rough, crease=0.25, worn=0.08)
    if quilt:
        x, y, z = nb.sep(c.P)
        nx, ny, nz = nb.sep(c.Nobj)
        fz = nb.ss(0.55, 0.75, nb.math("ABSOLUTE", nz))
        u = nb.mix(fz, y, x)
        v = nb.mix(fz, z, y)
        d1 = nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", nb.mul(nb.add(u, v), k)), 0.5))
        d2 = nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", nb.mul(nb.sub(u, v), k)), 0.5))
        dm = nb.math("MAXIMUM", d1, d2)
        seam = nb.ss(0.43, 0.49, dm)
        puff = nb.sub(1.0, nb.mul(dm, 2.0))
        o["col"] = nb.cmul(o["col"], nb.sub(1.0, nb.mul(seam, 0.45 * quilt)))
        o["h"] = nb.add(o["h"], nb.mul(nb.sub(nb.mul(puff, 0.6), nb.mul(seam, 1.4)), 2.5 * quilt))
        o["bs"] = 0.6
        o["bd"] = 0.002
    return o


def lux_tyre(nb, c):
    """Low-profile tyre: tread blocks / sipes on the crown, sidewall rib, faux lettering arc, radial striations.
    Wheel centre + axle side come from the face attributes wcx / wcz / wcy."""
    x, y, z = nb.sep(c.P)
    cx, cz, cy = nb.attr("wcx"), nb.attr("wcz"), nb.attr("wcy")
    dx = nb.sub(x, cx)
    dz = nb.sub(z, cz)
    r = nb.math("SQRT", nb.add(nb.mul(dx, dx), nb.mul(dz, dz)))
    ang = nb.math("ARCTAN2", dz, dx)
    ly = nb.sub(y, cy)
    nx_, ny_, nz_ = nb.sep(c.Nobj)
    crown = nb.ss(0.75, 0.45, nb.math("ABSOLUTE", ny_))
    base = (0.016, 0.016, 0.017)
    # crown: lateral sipes
    sip = nb.math("FRACT", nb.add(nb.mul(ang, 80.0 / math.pi), nb.mul(ly, 6.0)))
    sipe = nb.mul(nb.ss(0.08, 0.02, nb.math("ABSOLUTE", nb.sub(sip, 0.5))), crown)
    # sidewall: striations + lettering arc band
    side = nb.sub(1.0, crown)
    stri = nb.math("SINE", nb.mul(ang, 900.0))
    rr = nb.attr("wrt")
    band = nb.mul(nb.ss(0.012, 0.006, nb.math("ABSOLUTE", nb.sub(r, nb.sub(rr, 0.055)))), side)
    tn, _ = nb.noise(nb.combine(nb.mul(ang, 30.0), nb.mul(r, 260.0), 0.0), 1.0, 0.0, 0.5)
    arc = nb.mul(nb.math("LESS_THAN", nb.math("ABSOLUTE", nb.math("SINE", nb.mul(ang, 1.0))), 0.45), 1.0)
    letters = nb.mul(nb.mul(band, nb.math("GREATER_THAN", tn, 0.5)), arc)
    col = nb.cmul(base, nb.add(1.0, nb.mul(letters, 0.9)))
    rgh = nb.add(0.78, nb.mul(sipe, 0.1))
    rgh = nb.sub(rgh, nb.mul(letters, 0.3))
    h = nb.add(nb.mul(sipe, -1.0), nb.add(nb.mul(nb.mul(stri, side), 0.06), nb.mul(letters, 0.5)))
    return _out(col, rgh, 0.0, h, 0.6, 0.0015)


def lux_disc(nb, c, col=(0.42, 0.42, 0.43), ceramic=False):
    """Brake disc: drilled + curved slots (or carbon-ceramic speckle), polar coords from wcx/wcz."""
    x, y, z = nb.sep(c.P)
    cx, cz = nb.attr("wcx"), nb.attr("wcz")
    dx = nb.sub(x, cx)
    dz = nb.sub(z, cz)
    r = nb.math("SQRT", nb.add(nb.mul(dx, dx), nb.mul(dz, dz)))
    ang = nb.math("ARCTAN2", dz, dx)
    rd = nb.attr("wrd")
    rn = nb.div(r, nb.math("MAXIMUM", rd, 0.05))
    if ceramic:
        sp, _ = nb.noise(c.P, 900.0, 2.0, 0.6)
        colc = nb.cmul((0.11, 0.11, 0.115), nb.add(0.7, nb.mul(sp, 0.6)))
        holes = 0.0
        col_s = colc
        rough = nb.add(0.5, nb.mul(sp, 0.2))
        met = 0.2
    else:
        k = 28.0
        a1 = nb.math("FRACT", nb.mul(nb.add(ang, nb.mul(rn, 0.9)), k / (2 * math.pi)))
        ring = nb.math("FRACT", nb.mul(rn, 6.0))
        hole = nb.mul(nb.ss(0.2, 0.12, nb.math("ABSOLUTE", nb.sub(a1, 0.5))), nb.ss(0.26, 0.18, nb.math("ABSOLUTE", nb.sub(ring, 0.5))))
        hole = nb.mul(hole, nb.mul(nb.ss(0.55, 0.6, rn), nb.ss(0.97, 0.93, rn)))
        holes = hole
        lathe = nb.math("SINE", nb.mul(r, 2400.0))
        col_s = nb.cmul(col, nb.add(0.95, nb.mul(lathe, 0.05)))
        col_s = nb.mixc(hole, col_s, (0.01, 0.01, 0.01))
        rough = nb.add(0.32, nb.mul(hole, 0.5))
        met = nb.sub(1.0, hole)
    hat = nb.ss(0.56, 0.53, rn)
    col_s = nb.mixc(hat, col_s, (0.03, 0.03, 0.032))
    h = nb.mul(holes, -1.0) if holes else None
    return _out(col_s, rough, met, h, 0.8, 0.003)


def lux_plate(nb, c, image="PLATE_X"):
    return decal(nb, c, paint, image, ink=(0.012, 0.012, 0.014), ink_rough=0.35, col=(0.78, 0.78, 0.76), rough=0.25, grime=0.05, peel=0.1)


def lux_emit(nb, c, col=(0.9, 0.95, 1.0)):
    return _out(col, 0.3, 0.0, None)


def lux_mesh(nb, c, col=(0.012, 0.012, 0.013), pitch=60.0, web_col=None, web_metal=0.0):
    """Diamond intake mesh (front view YZ, side view XZ chosen by normal); web_col / web_metal = chrome mesh."""
    x, y, z = nb.sep(c.P)
    nx, ny, nz = nb.sep(c.Nobj)
    fx = nb.ss(0.5, 0.6, nb.math("ABSOLUTE", nx))
    u = nb.mix(fx, x, y)
    a = nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", nb.mul(nb.add(u, nb.mul(z, 1.6)), pitch)), 0.5))
    b = nb.math("ABSOLUTE", nb.sub(nb.math("FRACT", nb.mul(nb.sub(u, nb.mul(z, 1.6)), pitch)), 0.5))
    web = nb.ss(0.36, 0.44, nb.math("MAXIMUM", a, b))
    col_s = nb.mixc(web, nb.cmul(col, 0.25), web_col or tuple(min(1.0, c_ * 2.5) for c_ in col))
    return _out(col_s, nb.add(0.5, nb.mul(web, -0.4 if web_metal else -0.25)), nb.mul(web, web_metal),
                nb.mul(nb.sub(1.0, web), -1.0), 0.8, 0.004)


def lux_fabric(nb, c, col=(0.5, 0.45, 0.4), rough=0.9):
    n, _ = nb.noise(c.P, 1200.0, 2.0, 0.5)
    sm, _ = nb.noise(c.P, 8.0, 3.0, 0.5)
    col_s = nb.cmul(col, nb.add(0.9, nb.mul(sm, 0.15)))
    return _out(col_s, rough, 0.0, nb.mul(n, 0.4), 0.3, 0.0005)


def lux_screen(nb, c):
    x, y, z = nb.sep(c.P)
    n, _ = nb.noise(c.P, 30.0, 2.0, 0.5)
    return _out(nb.cmul((0.004, 0.005, 0.007), nb.add(0.9, nb.mul(n, 0.2))), 0.04, 0.0, None)


_BASE_MATS = {
    "lx_chrome": (lux_metal, dict(col=(0.86, 0.86, 0.88), rough=0.025)),
    "lx_chrome_dark": (lux_metal, dict(col=(0.16, 0.16, 0.17), rough=0.06)),
    "lx_satin": (lux_metal, dict(col=(0.62, 0.62, 0.63), rough=0.2, brushed=0.8)),
    "lx_rim": (lux_metal, dict(col=(0.80, 0.80, 0.81), rough=0.09, brushed=0.4)),
    "lx_rim_dark": (lux_metal, dict(col=(0.06, 0.06, 0.065), rough=0.25)),
    "lx_rim_gun": (lux_metal, dict(col=(0.20, 0.205, 0.215), rough=0.16, brushed=0.3)),
    "lx_black": (paint, dict(col=(0.006, 0.006, 0.007), rough=0.04, peel=0.1, grime=0.02)),
    "lx_satin_black": (paint, dict(col=(0.012, 0.012, 0.013), rough=0.35, peel=0.2, grime=0.05)),
    "lx_under": (plastic, dict(col=(0.012, 0.012, 0.013), rough=0.7, grain=180.0, gstr=0.6, dirt=0.3)),
    "lx_carbon": (lux_carbon, dict()),
    "lx_tyre": (lux_tyre, dict()),
    "lx_disc": (lux_disc, dict()),
    "lx_disc_cc": (lux_disc, dict(ceramic=True)),
    "lx_emit_white": (lux_emit, dict(col=(0.88, 0.93, 1.0))),
    "lx_emit_warm": (lux_emit, dict(col=(1.0, 0.86, 0.66))),
    "lx_emit_red": (lux_emit, dict(col=(1.0, 0.025, 0.02))),
    "lx_emit_amber": (lux_emit, dict(col=(1.0, 0.42, 0.04))),
    "lx_redlens": (plastic, dict(col=(0.22, 0.004, 0.004), rough=0.06, grain=100.0, gstr=0.05, dirt=0.0)),
    "lx_smoke": (plastic, dict(col=(0.01, 0.01, 0.011), rough=0.04, grain=100.0, gstr=0.05, dirt=0.0)),
    "lx_lens": (glass, dict(col=(0.6, 0.62, 0.64), rough=0.02, dirt=0.0)),
    "lx_mesh": (lux_mesh, dict()),
    "lx_mesh_chrome": (lux_mesh, dict(web_col=(0.7, 0.7, 0.72), web_metal=1.0, pitch=45.0)),
    "lx_screen": (lux_screen, dict()),
    "lx_rubber": (rubber, dict(col=(0.015, 0.015, 0.016), rough=0.7)),
    "lx_mirror": (lux_metal, dict(col=(0.9, 0.9, 0.92), rough=0.0)),
    "lx_walnut": (wood, dict(dark=(0.02, 0.008, 0.004), light=(0.11, 0.05, 0.022), rough=0.12, figure=0.9, worn=0.0)),
    "lx_glass": (glass, dict(col=(0.22, 0.25, 0.25), rough=0.02, dirt=0.05)),
}
MATS.update(_BASE_MATS)


def reg(name, fn, **kw):
    MATS[name] = (fn, kw)
    return name


# ======================================================================================
# Geometry helpers on top of propkit.Asset
# ======================================================================================


def grid_mesh(A, P, mat, closed_u=False, flip=False, **kw):
    """P: list of rows (each a list of 3D points), quads between consecutive rows / columns."""
    nr, nc = len(P), len(P[0])
    verts = [tuple(p) for row in P for p in row]
    faces = []
    cols = nc if closed_u else nc - 1
    for i in range(nr - 1):
        for j in range(cols):
            j2 = (j + 1) % nc
            f = (i * nc + j, i * nc + j2, (i + 1) * nc + j2, (i + 1) * nc + j)
            faces.append(tuple(reversed(f)) if flip else f)
    return A.mesh(verts, faces, mat, recalc=False, **kw)


def fan_patch(A, outline, surf, height, mat, rings=4, wall=True, piece=None, smooth=40, bevel_in=0.0, cap=True, **kw):
    """Raised conformal patch: outline = closed list of (u, v); surf(u, v) -> (point, normal).
    The top sits `height` above the surface; a wall drops 0.02 below it (hidden in the body)."""
    cu = sum(p[0] for p in outline) / len(outline)
    cv = sum(p[1] for p in outline) / len(outline)
    rows = []
    for k in range(rings + 1):
        t = 1.0 - k / rings
        ring = []
        for (u, v) in outline:
            uu, vv = cu + (u - cu) * t, cv + (v - cv) * t
            p, n = surf(uu, vv)
            ring.append(p + n * height)
        rows.append(ring)
    verts, faces = [], []
    m = len(outline)
    for ring in rows[:-1]:
        verts.extend(tuple(p) for p in ring)
    pc, nc_ = surf(cu, cv)
    verts.append(tuple(pc + nc_ * height))
    ci = len(verts) - 1
    if cap:
        for k in range(rings - 1):
            for j in range(m):
                j2 = (j + 1) % m
                faces.append((k * m + j, k * m + j2, (k + 1) * m + j2, (k + 1) * m + j))
        last = (rings - 1) * m
        for j in range(m):
            faces.append((last + j, last + (j + 1) % m, ci))
    if wall:
        base = len(verts)
        for (u, v) in outline:
            p, n = surf(u, v)
            verts.append(tuple(p - n * 0.02))
        for j in range(m):
            j2 = (j + 1) % m
            faces.append((base + j, base + j2, j2, j))
    ob = A.mesh(verts, faces, mat, recalc=False, piece=piece, smooth=smooth, **kw)
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    ncap = len(bm.faces) - (m if wall else 0)
    dot = sum(f.normal.dot(V(nc_)) for f in list(bm.faces)[:max(1, ncap)])
    if dot < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return ob


def frame_sweep(A, path, w, t, mat, closed=False, up=None, **kw):
    """Flat rounded strip swept along path (w across, t thick)."""
    prof = rrect_pts(w, t, min(w, t) * 0.45, 1)
    return A.sweep(path, prof=prof, mat=mat, closed=closed, up=up, **kw)


# ---- surface samplers ------------------------------------------------------------------------


def _end_x_safe(cs, u, v, front):
    x = cs.end_x(u, v, front)
    k = 0
    while x is None and k < 40:
        u *= 0.985
        v = v - 0.004 if v > 0.5 else v + 0.004
        x = cs.end_x(u, v, front)
        k += 1
    return x if x is not None else (cs.x1 if front else cs.x0)


def surf_front(cs, side_sign=1):
    def f(u, v):  # u = y, v = z
        x = _end_x_safe(cs, u, v, True)
        e = 0.006
        xa = cs.end_x(u + e, v, True) or x
        xb = cs.end_x(u, v + e, True) or x
        p = V((x, u, v))
        n = V((x - xa, -e, 0)).cross(V((x - xb, 0, -e)))
        n = V((1, 0, 0)) if n.length < 1e-9 else n.normalized()
        if n.x < 0:
            n = -n
        return p, n
    return f


def surf_rear(cs):
    def f(u, v):
        x = _end_x_safe(cs, u, v, False)
        e = 0.006
        xa = cs.end_x(u + e, v, False) or x
        xb = cs.end_x(u, v + e, False) or x
        p = V((x, u, v))
        n = V((xa - x, e, 0)).cross(V((xb - x, 0, e)))
        n = V((-1, 0, 0)) if n.length < 1e-9 else n.normalized()
        if n.x > 0:
            n = -n
        return p, n
    return f


def surf_side(cs, side=1):
    def f(u, v):  # u = x, v = z
        y = cs.side_y(u, v)
        e = 0.006
        ya = cs.side_y(u + e, v)
        yb = cs.side_y(u, v + e)
        n = V((-(ya - y) / e, 1.0, -(yb - y) / e)).normalized()
        return V((u, side * y, v)), V((n.x, side * n.y, n.z))
    return f


def surf_top(cs):
    def f(u, v):  # u = x, v = y
        z = cs.top_z(u, v)
        e = 0.006
        za = cs.top_z(u + e, v)
        zb = cs.top_z(u, v + e)
        n = V((-(za - z) / e, -(zb - z) / e, 1.0)).normalized()
        return V((u, v, z)), n
    return f


# ======================================================================================
# Body: lower loft + greenhouse
# ======================================================================================


def stations(cs, n=150, extra=()):
    xs = [cs.x0 + (cs.x1 - cs.x0) * (0.5 - 0.5 * math.cos(math.pi * i / (n - 1))) for i in range(n)]
    force = sorted(set(extra))
    out = [x for x in xs if all(abs(x - f) > 0.012 for f in force)] + list(force)
    return sorted(out)


def build_lower(A, cs, mats, cutters=(), nst=150):
    """Lower body loft, arch / intake booleans, open cabin tub. mats(c, n) -> recipe name per face."""
    xs = stations(cs, nst, (cs.x_ws, cs.x_bl) + tuple(getattr(cs, "force_x", ())))
    rings = []
    for x in xs:
        h = cs.half_section(x)
        loop = [(x, y, z) for (y, z) in h] + [(x, -y, z) for (y, z) in reversed(h[1:-1])]
        rings.append(loop)
    k = len(rings[0])
    verts = [p for r in rings for p in r]
    faces = []
    for i in range(len(rings) - 1):
        for j in range(k):
            j2 = (j + 1) % k
            faces.append((i * k + j, i * k + j2, (i + 1) * k + j2, (i + 1) * k + j))
    faces.append(tuple(range(k - 1, -1, -1)))
    faces.append(tuple((len(rings) - 1) * k + j for j in range(k)))
    body = A.mesh(verts, faces, "lx_black", smooth=48)
    cut_objs = []
    for (kind, data) in list(cutters):
        bm = bmesh.new()
        if kind == "arch":
            x, z, r, yin = data
            yout = cs.w(x) + 0.3
            for sgn in (1, -1):
                bm2 = bmesh.new()
                bmesh.ops.create_cone(bm2, cap_ends=True, segments=96, radius1=r, radius2=r, depth=yout - yin)
                bmesh.ops.transform(bm2, matrix=Matrix.Translation((x, sgn * (yin + yout) / 2, z)) @ Matrix.Rotation(math.pi / 2, 4, "X"), verts=bm2.verts)
                me_ = bpy.data.meshes.new("t")
                bm2.to_mesh(me_)
                bm2.free()
                bm.from_mesh(me_)
                bpy.data.meshes.remove(me_)
            M = Matrix.Identity(4)
        else:  # "prism": (poly_xz, y0, y1) side intake / vents, mirrored
            poly, y0, y1 = data
            for sgn in (1, -1):
                ring0 = [bm.verts.new((px, sgn * y0, pz)) for (px, pz) in poly]
                ring1 = [bm.verts.new((px, sgn * y1, pz)) for (px, pz) in poly]
                bm.faces.new(ring0)
                bm.faces.new(list(reversed(ring1)))
                n_ = len(poly)
                for j in range(n_):
                    bm.faces.new((ring0[j], ring0[(j + 1) % n_], ring1[(j + 1) % n_], ring1[j]))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            M = Matrix.Identity(4)
        me = bpy.data.meshes.new("cut")
        bm.to_mesh(me)
        bm.free()
        co = bpy.data.objects.new("cut", me)
        pk.link(co)
        co.matrix_world = M
        co.hide_render = True
        cut_objs.append(co)
        m = body.modifiers.new("cut", "BOOLEAN")
        m.object = co
        m.operation = "DIFFERENCE"
        m.solver = "EXACT"
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(body.evaluated_get(dg))
    body.modifiers.clear()
    old = body.data
    body.data = me2
    bpy.data.meshes.remove(old)
    pk.delete_objects(cut_objs)
    # classify faces: tub opening (delete), per-face recipe
    me = body.data
    me.materials.clear()
    names = []
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    kill = []
    lo, hi = min(cs.x_ws, cs.x_bl), max(cs.x_ws, cs.x_bl)
    for f in bm.faces:
        c = f.calc_center_median()
        n = f.normal
        if lo + 1e-4 < c.x < hi - 1e-4 and abs(c.y) < cs.yb(c.x) - 0.002 and n.z > 0.2 and c.z > cs.belt(c.x) - 0.05:
            kill.append(f)
            continue
        nm = None
        for (kind, data) in cutters:
            if kind == "arch":
                ax, az, ar, ayin = data
                if (c.x - ax) ** 2 + (c.z - az) ** 2 < (ar + 0.004) ** 2 and abs(c.y) < cs.w(c.x) - 0.01 and \
                        (abs(n.y) < 0.5 or abs(c.y) < cs.w(c.x) - 0.06):
                    nm = "lx_under"
        nm = nm or mats(c, n)
        if nm not in names:
            names.append(nm)
        f.material_index = names.index(nm)
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(me)
    bm.free()
    for nm in names:
        me.materials.append(pk.get_mat(nm))
    m_ = body.modifiers.new("bev", "BEVEL")
    m_.width = 0.005
    m_.segments = 2
    m_.limit_method = "ANGLE"
    m_.angle_limit = math.radians(55)
    m_.harden_normals = False
    m_.use_clamp_overlap = True
    return body


def build_greenhouse(A, cs, tagmat, glass_piece=lambda tag, j: "Glass", headliner="lx_alcantara", rows=None, cols=None):
    """Warped-grid greenhouse. Returns dict with paths for trims."""
    # rows in s for the right half: belt band, glass, frame, rail, windscreen/roof
    s_rows = []
    def seg(a, b, n):
        for i in range(n):
            s_rows.append(a + (b - a) * i / n)
    seg(0.0, cs.s_g0, 2)
    seg(cs.s_g0, cs.s_g1, 10)
    seg(cs.s_g1, cs.s_rail, 3)
    seg(cs.s_rail, cs.s_w0, 3)
    seg(cs.s_w0, 1.0, 10)
    s_rows.append(1.0)
    counts = cs.col_counts

    def breaks(s):
        if s <= cs.s_rail + 1e-6:
            q = (s - cs.s_g0) / (cs.s_g1 - cs.s_g0)
            out = []
            for b in cs.side_breaks:
                out.append(b if not isinstance(b, tuple) else lerp(b[0], b[1], q))
            return out
        return list(cs.roof_breaks(s) if callable(cs.roof_breaks) else cs.roof_breaks)

    def xcols(s):
        br = breaks(s)
        xs_, tags = [], []
        for k in range(len(counts)):
            a, b = br[k], br[k + 1]
            for i in range(counts[k]):
                t = i / counts[k]
                # cosine bunching at both interval ends (sharper corners at pillars)
                t2 = 0.5 - 0.5 * math.cos(math.pi * t)
                xs_.append(lerp(a, b, lerp(t, t2, 0.35)))
                tags.append(k)
        xs_.append(br[-1])
        return xs_

    def row_kind(s0, s1):
        sm = (s0 + s1) / 2
        if sm < cs.s_g0:
            return "belt"
        if sm < cs.s_g1:
            return "side"
        if sm < cs.s_rail:
            return "frame"
        if sm < cs.s_w0:
            return "rail"
        return "roof"

    full = []   # rows across: right half from belt up to the centre, then left half back down
    srow = []
    for s in s_rows:
        full.append([cs.gh(x, s, 1) for x in xcols(s)])
        srow.append((s, 1))
    for s in reversed(s_rows[:-1]):
        full.append([cs.gh(x, s, -1) for x in xcols(s)])
        srow.append((s, -1))
    ncol = len(full[0])
    col_int = []
    for k in range(len(counts)):
        col_int += [k] * counts[k]
    groups = {}
    for i in range(len(full) - 1):
        s0, s1 = srow[i][0], srow[i + 1][0]
        rk = row_kind(min(s0, s1), max(s0, s1))
        side = srow[i][1] if srow[i][1] == srow[i + 1][1] else 1
        for j in range(ncol - 1):
            tag = tagmat(rk, col_int[j], (s0 + s1) / 2)
            quad = (full[i][j], full[i][j + 1], full[i + 1][j + 1], full[i + 1][j])
            groups.setdefault(tag, []).append((quad, col_int[j], side))
    out = {"glass_faces": []}
    for tag, quads in groups.items():
        if tag == "glass":
            byp = {}
            for q, k, sd in quads:
                byp.setdefault(glass_piece(tag, k), []).append(q)
            for pname, qs in byp.items():
                verts, faces = [], []
                for q in qs:
                    b = len(verts)
                    verts += [tuple(p) for p in q]
                    faces.append((b, b + 1, b + 2, b + 3))
                g = A.mesh(verts, faces, "lx_glass", piece=pname, smooth=180, recalc=False)
                _weld(g)
                _orient_out(g, cs)
            continue
        verts, faces = [], []
        for q, k, sd in quads:
            b = len(verts)
            verts += [tuple(p) for p in q]
            faces.append((b, b + 1, b + 2, b + 3))
        ob = A.mesh(verts, faces, tag, smooth=50, recalc=False)
        _weld(ob)
        _orient_out(ob, cs)
        # headliner: inner skin of every non-glass greenhouse face
        verts2 = []
        for q, k, sd in quads:
            for p in q:
                nrm = V((0, p.y, p.z - (cs.belt(p.x) - 0.25))).normalized()
                verts2.append(tuple(p - nrm * 0.03))
        hl = A.mesh(verts2, faces, headliner, piece="Interior", smooth=50, recalc=False)
        _weld(hl)
        _orient_out(hl, cs, inward=True)
        dm = hl.modifiers.new("dec", "DECIMATE")
        dm.decimate_type = "DISSOLVE"
        dm.angle_limit = math.radians(4)
    out["breaks"] = breaks
    out["s_rows"] = s_rows
    return out


def _weld(ob, d=1e-5):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=d)
    bm.to_mesh(ob.data)
    bm.free()


def _orient_out(ob, cs, inward=False):
    """Faces of greenhouse surfaces point away from the cabin centre."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bad = []
    for f in bm.faces:
        c = f.calc_center_median()
        ref = V((0, c.y, c.z - (cs.belt(c.x) - 0.3)))
        if (f.normal.dot(ref) < 0) != inward:
            bad.append(f)
    if bad:
        bmesh.ops.reverse_faces(bm, faces=bad)
    bm.to_mesh(me)
    bm.free()


def dlo_loop(cs, x_front, x_rear, s0, s1, side, off=0.004, n=18):
    """Closed path around the side-glass opening (x_front/x_rear are (x_at_s0, x_at_s1))."""
    def xa(s, xx):
        q = (s - cs.s_g0) / (cs.s_g1 - cs.s_g0)
        return lerp(xx[0], xx[1], q)
    pts = []
    for i in range(n + 1):
        x = lerp(xa(s0, x_front), xa(s0, x_rear), i / n)
        pts.append((x, s0))
    for i in range(1, 6):
        s = lerp(s0, s1, i / 5)
        pts.append((xa(s, x_rear), s))
    for i in range(1, n + 1):
        x = lerp(xa(s1, x_rear), xa(s1, x_front), i / n)
        pts.append((x, s1))
    for i in range(1, 5):
        s = lerp(s1, s0, i / 5)
        pts.append((xa(s, x_front), s))
    P = []
    for (x, s) in pts:
        p = cs.gh(x, s, side)
        P.append(p + cs.gh_normal(x, s, side) * off)
    return chaikin(P, 1, closed=True)


# ======================================================================================
# Wheels
# ======================================================================================


def wheel(A, cs, at, r_t, wdt, rim_r, side, style="multi", rim="lx_rim", rim2="lx_rim_dark", caliper="lx_black",
          disc="lx_disc", centre_lock=False, spokes=10, piece="Wheels"):
    """Forged multi-spoke wheel, low-profile tyre with sidewall detail, big disc + monobloc caliper.
    Built around the local axle (local Z = outward), then placed at `at` facing side (+1 left/+Y, -1 right)."""
    x, y, z = at
    attrs = {"wcx": x, "wcz": z, "wcy": y, "wrt": r_t, "wrd": rim_r * 0.86, "wny": float(side)}
    sw = wdt / 2
    M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(-side * math.pi / 2, 4, "X")   # local Z -> world side
    parts = []
    # ---- tyre: rounded shoulders, slight sidewall bulge, rim protector rib, 4 circumferential grooves
    sh = 0.022
    prof = [(rim_r + 0.012, -sw * 0.84), (rim_r + 0.022, -sw * 0.93), (rim_r + 0.035, -sw * 0.985), ((rim_r + r_t) / 2, -sw * 1.0),
            (r_t - sh * 1.6, -sw * 0.985), (r_t - sh * 0.55, -sw * 0.93), (r_t - 0.003, -sw * 0.84), (r_t, -sw * 0.72)]
    grooves = [-0.42, 0.0, 0.42]
    crown = []
    for g in grooves:
        crown += [(r_t, sw * (g - 0.07)), (r_t - 0.008, sw * (g - 0.045)), (r_t - 0.008, sw * (g + 0.045)), (r_t, sw * (g + 0.07))]
    tail = [(p[0], -p[1]) for p in reversed(prof)]
    full = prof + crown + tail
    t = A.lathe(full, mat="lx_tyre", n=52, cap=False, smooth=40, piece=piece, attrs=attrs)
    parts.append(t)
    # rim protector rib on the outer sidewall
    rib = A.lathe([(rim_r + 0.006, sw * 0.86), (rim_r + 0.016, sw * 0.98), (rim_r + 0.03, sw * 0.96), (rim_r + 0.034, sw * 0.9)], mat="lx_tyre", n=64, cap=False, smooth=40, piece=piece, attrs=attrs)
    parts.append(rib)
    # ---- rim: barrel + polished lip + inner dish
    face = sw * 0.9
    barrel = A.lathe([(rim_r - 0.004, -sw * 0.82), (rim_r - 0.012, -sw * 0.74), (rim_r - 0.016, sw * 0.6), (rim_r - 0.006, face - 0.012)], mat=rim2, n=48, cap=False, smooth=50, piece=piece, attrs=attrs)
    parts.append(barrel)
    lip = A.lathe([(rim_r - 0.018, face - 0.016), (rim_r - 0.006, face - 0.004), (rim_r + 0.006, face - 0.002), (rim_r + 0.012, face - 0.010), (rim_r + 0.012, face - 0.02)],
                  mat=rim, n=64, cap=False, smooth=40, piece=piece, attrs=attrs)
    parts.append(lip)
    # ---- spokes (concave: they dive from the lip toward the hub set back by `dish`)
    dish = 0.045
    hub_r = rim_r * 0.24
    ns = spokes
    for i in range(ns):
        a = 2 * math.pi * i / ns
        twins = (-0.055, 0.055) if style == "twin" else ((0.0,) if style != "y" else (-0.06, 0.06))
        for k, off in enumerate(twins):
            pts = []
            for j in range(7):
                t_ = j / 6
                rr = lerp(hub_r * 0.95, rim_r - 0.012, t_)
                spread = off * (t_ ** 1.3 if style == "y" else 1.0) * (1.0 if style != "twin" else t_ * 0.6 + 0.4)
                ang = a + spread * (1.0 if style != "twin" else 0.5) + 0.02 * math.sin(t_ * math.pi)
                zz = face - 0.014 - dish * (1 - t_) ** 1.6 + 0.004
                pts.append((rr * math.cos(ang), rr * math.sin(ang), zz))
            wroot = 0.034 if style == "multi" else 0.024
            wtip = 0.018 if style == "multi" else 0.013
            scales = [lerp(1.0, wtip / wroot, (j / 6) ** 0.8) for j in range(7)]
            prof = round_poly([(-wroot / 2, -0.010), (wroot / 2, -0.010), (wroot * 0.36, 0.009), (-wroot * 0.36, 0.009)], 0.003, iters=1)
            sp = A.sweep(pts, prof=prof, mat=rim, scales=scales, smooth=45, piece=piece, attrs=attrs, up=(0, 0, 1))
            parts.append(sp)
        # dark windows between the spokes on the inner dish (depth)
    dishm = A.lathe([(hub_r * 0.9, face - 0.06), (rim_r * 0.7, face - 0.072), (rim_r - 0.02, face - 0.04)], mat=rim2, n=40, cap=False, smooth=50, piece=piece, attrs=attrs)
    parts.append(dishm)
    # hub + centre cap / centre-lock
    hub = A.lathe(round_poly([(0.0, face - 0.012), (hub_r, face - 0.012), (hub_r * 1.02, face - 0.04), (0.0, face - 0.04)], 0.004, closed=False),
                  mat=rim, n=48, smooth=40, piece=piece, attrs=attrs)
    parts.append(hub)
    if centre_lock:
        nut = A.cyl(0.048, 0.045, at=(0, 0, face - 0.02), mat="lx_rim_dark", n=6, bevel=0.004, segs=2, piece=piece, attrs=attrs)
        parts.append(nut)
        for i in range(6):
            aa = 2 * math.pi * (i + 0.5) / 6
            parts.append(A.box((0.032, 0.012, 0.03), at=(0.047 * math.cos(aa), 0.047 * math.sin(aa), face + 0.0), rot=(0, 0, math.degrees(aa)), mat="lx_rim_dark", bevel=0.003, piece=piece, attrs=attrs))
        parts.append(A.cyl(0.026, 0.012, at=(0, 0, face + 0.024), mat="lx_chrome", n=32, bevel=0.003, piece=piece, attrs=attrs))
    else:
        cap = A.lathe(round_poly([(0.0, face - 0.004), (0.036, face - 0.004), (0.04, face - 0.016), (0.0, face - 0.016)], 0.004, closed=False), mat="lx_black", n=40, smooth=40, piece=piece, attrs=attrs)
        parts.append(cap)
        parts.append(emblem(A, (0, 0, face - 0.002), 0.022, piece=piece, axis="Z", attrs=attrs))
        nb_ = 5
        for i in range(nb_):
            aa = 2 * math.pi * i / nb_ + 0.3
            parts.append(A.cyl(0.0085, 0.016, at=(hub_r * 0.62 * math.cos(aa), hub_r * 0.62 * math.sin(aa), face - 0.028), mat="lx_chrome", n=8, bevel=0.0015, piece=piece, attrs=attrs))
    for p in parts:
        p.matrix_world = M @ p.matrix_world
    # ---- brake disc + caliper (inboard of the spokes)
    rd = rim_r * 0.86
    M2 = Matrix.Translation((x, y + side * (face - 0.11), z)) @ Matrix.Rotation(-side * math.pi / 2, 4, "X")
    d = A.lathe([(rd * 0.5, -0.016), (rd, -0.016), (rd, 0.016), (rd * 0.5, 0.016)], mat=disc, n=64, cap=False, smooth=40, piece=piece, attrs=attrs)
    d.matrix_world = M2 @ d.matrix_world
    dh = A.lathe([(0.0, 0.03), (rd * 0.5, 0.03), (rd * 0.53, 0.0), (rd * 0.53, -0.016), (0.0, -0.016)], mat="lx_rim_dark", n=48, cap=False, smooth=40, piece=piece, attrs=attrs)
    dh.matrix_world = M2 @ dh.matrix_world
    # monobloc caliper: an arc block hugging the disc at the rear-top
    b0, b1 = math.radians(112), math.radians(162)        # world angle: trailing the axle, upper half
    arc0, arc1 = (-b1, -b0) if side > 0 else (b0, b1)
    outer = []
    inner = []
    for i in range(7):
        aa = lerp(arc0, arc1, i / 6)
        outer.append((math.cos(aa) * (rd + 0.018), math.sin(aa) * (rd + 0.018)))
        inner.append((math.cos(aa) * (rd - 0.07), math.sin(aa) * (rd - 0.07)))
    poly = round_poly(outer + list(reversed(inner)), 0.012, iters=1)
    cal = A.prism(poly, 0.075, mat=caliper, plane="XY", z0=-0.0375 + 0.0, bevel=0.006, segs=1, piece=piece, attrs=attrs)
    cal.matrix_world = M2 @ Matrix.Translation((0, 0, 0.0)) @ cal.matrix_world
    # caliper logo plate
    aa = (arc0 + arc1) / 2
    plate = A.box((0.05, 0.016, 0.003), at=(math.cos(aa) * (rd - 0.026), math.sin(aa) * (rd - 0.026), 0.039), rot=(0, 0, math.degrees(aa) + 90), mat="lx_chrome", bevel=0.001, piece=piece, attrs=attrs)
    plate.matrix_world = M2 @ plate.matrix_world


def emblem(A, at, r, piece=None, axis="X", mat="lx_chrome", depth=0.004, attrs=None):
    """AVERNE lozenge: a slim rhombus outline with a horizontal bar through it (original mark)."""
    w, h = r * 1.0, r * 1.25
    outer = [(w, 0), (0, h), (-w, 0), (0, -h)]
    ring = round_poly(outer, r * 0.05)
    k = 0.72
    inner = [(p[0] * k, p[1] * k) for p in ring]
    verts, faces = [], []
    n = len(ring)
    for d in (0.0, depth):
        for p in ring:
            verts.append((p[0], p[1], d))
        for p in inner:
            verts.append((p[0], p[1], d))
    o0, i0, o1, i1 = 0, n, 2 * n, 3 * n
    for j in range(n):
        j2 = (j + 1) % n
        faces.append((o1 + j, o1 + j2, i1 + j2, i1 + j))
        faces.append((o0 + j2, o0 + j, i0 + j, i0 + j2))
        faces.append((o0 + j, o0 + j2, o1 + j2, o1 + j))
        faces.append((i0 + j2, i0 + j, i1 + j, i1 + j2))
    if axis == "X":
        R = Matrix.Rotation(math.pi / 2, 4, "Y") @ Matrix.Rotation(math.pi / 2, 4, "Z")
    elif axis == "+Y":
        R = Matrix.Rotation(-math.pi / 2, 4, "X")
    elif axis == "-Y":
        R = Matrix.Rotation(math.pi / 2, 4, "X")
    elif axis == "-X":
        R = Matrix.Rotation(-math.pi / 2, 4, "Y") @ Matrix.Rotation(-math.pi / 2, 4, "Z")
    else:
        R = Matrix.Identity(4)
    ob = A.mesh(verts, faces, mat, piece=piece, smooth=30, attrs=attrs)
    bar = A.box((w * 2.3, h * 0.13, depth * 1.3), at=(0, 0, depth * 0.65), mat=mat, bevel=0.0008, piece=piece, attrs=attrs)
    dot = A.box((w * 0.32, w * 0.32, depth * 1.6), at=(0, 0, depth * 0.8), rot=(0, 0, 45), mat=mat, bevel=0.0006, piece=piece, attrs=attrs)
    for o in (ob, bar, dot):
        o.matrix_world = Matrix.Translation(at) @ R @ o.matrix_world
    return ob


# ======================================================================================
# Interior
# ======================================================================================


def seat(A, x, y, z, w=0.54, depth=0.54, back_h=0.68, mat="lx_leather", quilt_mat=None, recline=16, headrest=True, piece="Interior", lounge=False):
    """Bucket / lounge seat: cushion with side bolsters, backrest with bolsters, separate headrest."""
    qm = quilt_mat or mat
    zc = z
    # cushion base + quilted insert + bolsters
    A.box((depth, w, 0.11), at=(x, y, zc + 0.055), mat=mat, bevel=0.035, segs=3, piece=piece)
    A.box((depth * 0.82, w * 0.62, 0.035), at=(x + 0.01, y, zc + 0.122), mat=qm, bevel=0.014, segs=3, piece=piece)
    for s in (-1, 1):
        A.box((depth * 0.92, 0.09, 0.15), at=(x, y + s * (w / 2 - 0.045), zc + 0.09), mat=mat, bevel=0.04, segs=3, piece=piece)
    # backrest
    R = (0, -recline, 0)
    bx = x - depth / 2 + 0.06
    bz = zc + 0.12
    def place(o, local):
        o.matrix_world = Matrix.Translation((bx, y, bz)) @ pk.rot_matrix(R) @ Matrix.Translation(local) @ o.matrix_world
    o = A.box((0.12, w, back_h), mat=mat, bevel=0.045, segs=3, piece=piece)
    place(o, (-0.02, 0, back_h / 2))
    o = A.box((0.03, w * 0.6, back_h * 0.78), mat=qm, bevel=0.012, segs=3, piece=piece)
    place(o, (0.045, 0, back_h * 0.45))
    for s in (-1, 1):
        o = A.box((0.15, 0.085, back_h * 0.85), mat=mat, bevel=0.04, segs=3, piece=piece)
        place(o, (0.0, s * (w / 2 - 0.04), back_h * 0.45))
    if headrest:
        o = A.box((0.1, w * 0.52, 0.17), mat=mat, bevel=0.045, segs=3, piece=piece)
        place(o, (0.0, 0, back_h + 0.12))
        for s in (-1, 1):
            o = A.cyl(0.006, 0.08, mat="lx_chrome", n=8, piece=piece)
            place(o, (0.0, s * 0.07, back_h - 0.01))
    if lounge:
        # calf rest + armrests
        A.box((0.08, w * 0.85, 0.32), at=(x + depth / 2 + 0.02, y, zc - 0.05), rot=(0, 30, 0), mat=mat, bevel=0.03, segs=3, piece=piece)


def steering_wheel(A, at, r=0.19, tilt=62, rim_mat="lx_black", wood_mat=None, piece="Interior"):
    parts = []
    path = [(r * math.cos(2 * math.pi * i / 48), r * math.sin(2 * math.pi * i / 48), 0) for i in range(48)]
    parts.append(A.sweep(path, r=0.017, n=14, mat=rim_mat, closed=True, piece=piece))
    if wood_mat:
        arc = [(r * math.cos(a), r * math.sin(a), 0) for a in np.linspace(math.radians(40), math.radians(140), 12)]
        parts.append(A.sweep(arc, r=0.0175, n=14, mat=wood_mat, piece=piece))
    for a in (0, 180, 270):
        aa = math.radians(a)
        parts.append(A.box((r * 0.86, 0.036, 0.014), at=(r * 0.43 * math.cos(aa), r * 0.43 * math.sin(aa), -0.012), rot=(0, 0, a), mat="lx_satin", bevel=0.005, piece=piece))
    parts.append(A.cyl(0.062, 0.05, at=(0, 0, -0.045), mat=rim_mat, n=32, bevel=0.01, piece=piece))
    parts.append(emblem(A, (0, 0, 0.006), 0.018, piece=piece, axis="Z"))
    parts.append(A.cyl(0.03, 0.3, at=(0, 0, -0.33), mat="lx_satin_black", n=16, piece=piece))
    M = Matrix.Translation(at) @ Matrix.Rotation(math.radians(-90 + (90 - tilt)), 4, "Y") @ Matrix.Rotation(math.radians(-90), 4, "Z")
    for p in parts:
        p.matrix_world = M @ p.matrix_world


def cabin(A, cs, leather_m, quilt_m, wood_m, door_m, dash_m, rows=2, rear_lounge=False, wheel_y=0.37, dash_wood=True, carbon=False, seat_w=0.54, rear_bench=False,
          x_back=None, wheel_r=0.19, flat_bottom=False, back_h=0.68, floor_dz=0.12):
    """Interior tub: floor, door cards, dash, console, seats, steering wheel."""
    P = "Interior"
    x_front = cs.x_ws - 0.05
    x_back = x_back if x_back is not None else cs.x_bl + 0.05
    zf = interp(cs.zbot, 0.0) + floor_dz
    # floor (carpet) + rear bulkhead / parcel shelf
    A.box((x_front - x_back + 0.1, 2 * (cs.yb(0.0) - 0.02), 0.03), at=((x_front + x_back) / 2, 0, zf), mat="lx_carpet", bevel=0.005, piece=P)
    belt = cs.belt
    # door cards (inner side walls) + wood / leather capping at the belt
    for s in (-1, 1):
        xs_ = np.linspace(x_back + 0.02, x_front - 0.02, 28)
        top = [(x, s * (cs.yb(x) - 0.035), belt(x) - 0.006) for x in xs_]
        def zbot_(x):
            z_ = zf
            for wx in (cs.wf, cs.wr):
                if abs(x - wx) < cs.arch_r + 0.06:
                    z_ = max(z_, cs.r_tire + cs.arch_r + 0.04)
            return min(z_, belt(x) - 0.12)
        bot = [(x, s * (cs.yb(x) - 0.06), zbot_(x)) for x in xs_]
        grid_mesh(A, [bot, top], door_m, flip=(s < 0), piece=P, smooth=60)
        cap_in = [(x, s * (cs.yb(x) - 0.075), belt(x) - 0.012) for x in xs_]
        cap_out = [(x, s * (cs.yb(x) + 0.004), belt(x) - 0.012) for x in xs_]
        grid_mesh(A, [cap_in, cap_out] if s > 0 else [cap_out, cap_in], wood_m if dash_wood else leather_m, piece=P, smooth=60)
        # armrest
        A.box((0.5, 0.08, 0.06), at=(cs.seat_x[0] - 0.05, s * (cs.yb(cs.seat_x[0]) - 0.1), belt(cs.seat_x[0]) - 0.28), mat=leather_m, bevel=0.025, segs=3, piece=P)
    # dashboard: from the windscreen base back
    xd = cs.x_ws
    dz = belt(xd)
    yb = cs.yb(xd + -0.3) - 0.03
    A.box((0.5, 2 * yb, 0.16), at=(xd - 0.15, 0, dz - 0.04), mat=dash_m, bevel=0.05, segs=3, piece=P)
    A.box((0.3, 2 * yb - 0.04, 0.3), at=(xd - 0.2, 0, dz - 0.28), mat=dash_m, bevel=0.05, segs=3, piece=P)
    if dash_wood:
        A.box((0.04, 2 * yb - 0.08, 0.07), at=(xd - 0.4, 0, dz - 0.09), mat=wood_m, bevel=0.012, segs=3, piece=P)
    else:
        A.box((0.04, 2 * yb - 0.08, 0.07), at=(xd - 0.4, 0, dz - 0.09), mat="lx_carbon", bevel=0.012, segs=3, piece=P)
    A.box((0.012, 0.95, 0.15), at=(xd - 0.36, 0.08, dz + 0.02), rot=(0, -12, 0), mat="lx_screen", bevel=0.004, piece=P)
    for yv in (-0.55, -0.15, 0.15, 0.55):
        A.cyl(0.03, 0.02, at=(xd - 0.43, yv, dz - 0.09), axis="X", rot=(0, 0, 180), mat="lx_chrome", n=20, bevel=0.003, piece=P)
    # centre console
    xs0, xs1 = cs.seat_x[0] - 0.35, xd - 0.3
    A.box((xs1 - xs0, 0.24, 0.24), at=((xs0 + xs1) / 2, 0, zf + 0.14), mat=leather_m, bevel=0.04, segs=3, piece=P)
    A.box((xs1 - xs0 - 0.08, 0.16, 0.015), at=((xs0 + xs1) / 2, 0, zf + 0.265), mat=wood_m if dash_wood else "lx_carbon", bevel=0.004, piece=P)
    A.cyl(0.022, 0.04, at=((xs0 + xs1) / 2 + 0.1, 0, zf + 0.27), mat="lx_chrome", n=24, bevel=0.004, piece=P)
    # steering wheel (left-hand drive: driver on +Y)
    steering_wheel(A, (xd - 0.62, wheel_y, dz - 0.02), r=wheel_r, rim_mat=dash_m, wood_mat=wood_m if dash_wood else None, piece=P)
    # seats
    zs = zf + 0.04
    room = cs.roof(cs.seat_x[0] - 0.2) - 0.16 - (zs + 0.12)          # headrest top stays 16 cm under the roof
    back_h = min(back_h, max(0.42, room / 1.25 - 0.12))
    for s in (-1, 1):
        seat(A, cs.seat_x[0], s * 0.37, zs, w=seat_w, mat=leather_m, quilt_mat=quilt_m, piece=P, back_h=back_h, recline=16 if back_h > 0.6 else 28)
    if rows >= 2:
        if rear_bench:
            for yy in (-0.42, 0.0, 0.42):
                seat(A, cs.seat_x[1], yy, zs + 0.02, w=0.44 if yy == 0 else 0.5, mat=leather_m, quilt_mat=quilt_m, piece=P, recline=20, headrest=(yy != 0))
        else:
            for s in (-1, 1):
                seat(A, cs.seat_x[1], s * 0.38, zs + 0.02, w=seat_w + 0.04, mat=leather_m, quilt_mat=quilt_m, piece=P, recline=24 if rear_lounge else 20, lounge=rear_lounge)
            # rear centre console
            A.box((0.62, 0.26, 0.42), at=(cs.seat_x[1] - 0.02, 0, zf + 0.21), mat=leather_m, bevel=0.04, segs=3, piece=P)
            A.box((0.56, 0.2, 0.015), at=(cs.seat_x[1] - 0.02, 0, zf + 0.43), mat=wood_m if dash_wood else "lx_carbon", bevel=0.004, piece=P)
    # parcel shelf / rear bulkhead under the backlight
    A.box((0.4, 2 * (cs.yb(x_back + 0.2) - 0.05), 0.03), at=(x_back + 0.2, 0, belt(x_back + 0.2) - 0.02), mat="lx_carpet", bevel=0.005, piece=P)
    A.box((0.04, 2 * (cs.yb(x_back + 0.05) - 0.05), belt(x_back) - zf), at=(x_back + 0.03, 0, (belt(x_back) + zf) / 2), mat="lx_carpet", bevel=0.005, piece=P)


# ======================================================================================
# Shared exterior details
# ======================================================================================


def plate_image(name, text):
    if bpy.data.images.get(name) is not None:
        return name
    f = font("BigShoulders-Bold.ttf")
    m = pk.text_mask(text, f, 512, 112, pad=0.14, spacing=1.15)
    yy, xx = np.mgrid[0:112, 0:512]
    d = np.minimum(np.minimum(xx, 511 - xx), np.minimum(yy, 111 - yy))
    m = np.maximum(m, ((d >= 4) & (d < 7)).astype(np.float32))
    a = np.zeros((112, 512, 4), np.float32)
    a[..., 0] = a[..., 1] = a[..., 2] = m
    a[..., 3] = 1.0
    pk.np_to_image(name, a)
    return name


def number_plate(A, cs, mat, z, front=True, w=0.52, h=0.112):
    surf = surf_front(cs) if front else surf_rear(cs)
    outline = round_poly(rrect_pts(w, h, 0.008, 3), 0.002)
    outline = [(p[0], z + p[1]) for p in outline]
    if not front:
        outline = list(reversed(outline))
    ob = fan_patch(A, outline, surf, 0.012, mat, rings=2)
    sgn = 1 if front else -1
    A.vattr(ob, "luv", lambda co: ((0.5 + sgn * co.y / w), (co.z - z) / h + 0.5, 1.0))
    # thin chrome frame
    fr = round_poly(rrect_pts(w + 0.02, h + 0.02, 0.012, 3), 0.003)
    path = []
    for (u, v) in fr:
        p, n = surf(u, z + v)
        path.append(p + n * 0.014)
    frame_sweep(A, path, 0.008, 0.005, "lx_chrome", closed=True, smooth=50)


def side_path(cs, x0, x1, z, side, off=0.003, n=40):
    out = []
    for i in range(n):
        x = lerp(x0, x1, i / (n - 1))
        p, nn = surf_side(cs, side)(x, z if not callable(z) else z(x))
        out.append(p + nn * off)
    return out


def flush_handle(A, cs, x, z, side, length=0.2):
    f = surf_side(cs, side)
    outline = round_poly(rrect_pts(length, 0.024, 0.011, 4), 0.004)
    outline = [(x + p[0], z + p[1]) for p in outline]
    if side < 0:
        outline = list(reversed(outline))
    fan_patch(A, outline, f, 0.004, "lx_chrome", rings=2)
    # recess shadow behind the bar
    outline2 = round_poly(rrect_pts(length + 0.03, 0.05, 0.022, 4), 0.006)
    outline2 = [(x + p[0], z + p[1]) for p in outline2]
    if side < 0:
        outline2 = list(reversed(outline2))
    fan_patch(A, outline2, f, 0.0008, "lx_satin_black", rings=2)


def mirror(A, cs, x, z, side, paint_m, reach=0.2, size=(0.22, 0.12, 0.13), piece="Body"):
    """Door mirror: slim swept arm from the belt edge, smooth teardrop housing (paint), chrome lower trim,
    glass on the rear face, LED repeater along the leading edge."""
    zb_ = cs.belt(x)
    y0 = max(cs.yb(x) + 0.006, cs.side_y(x, zb_ - 0.03))
    sx, sy, sz = size
    s = side
    zc = zb_ + 0.035 + sz * 0.45
    ycen = y0 + reach * 0.62 + sy * 0.55
    A.sweep([(x + 0.03, s * (y0 - 0.01), zb_ + 0.01), (x + 0.0, s * (y0 + reach * 0.35), zc - sz * 0.25), (x - 0.02, s * (ycen - sy * 0.3), zc - sz * 0.15)],
            prof=round_poly(rrect_pts(0.055, 0.016, 0.007, 2), 0.003, iters=1), mat="lx_black", smooth=50, up=(0, 0, 1))
    shell = A.sphere(1.0, at=(x - 0.03, s * ycen, zc), mat=paint_m, seg=28, rings=14, scale=(sx * 0.42, sy * 1.0, sz * 0.5))
    A.box((0.006, sy * 1.55, sz * 0.72), at=(x - 0.03 - sx * 0.40, s * ycen, zc + 0.002), mat="lx_mirror", bevel=0.003)
    A.box((sx * 0.55, sy * 1.7, 0.01), at=(x - 0.04, s * ycen, zc - sz * 0.46), mat="lx_chrome", bevel=0.004)
    A.box((0.012, sy * 1.2, 0.006), at=(x - 0.03 + sx * 0.36, s * (ycen + 0.01), zc - sz * 0.32), mat="lx_emit_amber", piece="Emissive", bevel=0.002)


def chrome_strip_side(A, cs, x0, x1, z, side, w=0.03, t=0.005, mat="lx_chrome", off=0.003):
    path = side_path(cs, x0, x1, z, side, off=off)
    return frame_sweep(A, path, t, w, mat, up=(0, side, 0), smooth=60)


def lamp_lines(A, outline_fn, surf, mat, height, piece="Emissive"):
    fan_patch(A, outline_fn, surf, height, mat, rings=2, piece=piece, smooth=180)


def mirror_outline(poly):
    """(y, z) outline on the +Y side -> the same outline on -Y (keeps CCW)."""
    return [(-p[0], p[1]) for p in reversed(poly)]


def make_points(A, pts):
    for k, v in pts.items():
        A.point(k, v)


# ======================================================================================
# 1. Stately limousine saloon
# ======================================================================================

LIM_GAPS = [
    ("XZ", [(1.20, 0.30), (1.21, 0.62), (1.18, 0.99)], 0.45),                                   # front door, front edge
    ("XZ", [(-0.47, 0.30), (-0.47, 1.0)], 0.45),                                                # front door, rear edge
    ("XZ", [(-0.64, 0.30), (-0.64, 1.0)], 0.45),                                                # coach door, front edge
    ("XZ", [(-1.07, 0.30), (-1.07, 0.66), (-1.12, 0.78), (-1.25, 0.87), (-1.45, 0.93), (-1.62, 0.96), (-1.68, 1.0)], 0.45),
    ("XZ", [(1.20, 0.30), (-1.07, 0.30)], 0.6, 0.0016),                                         # door bottoms
    ("XZ", [(-2.0, 0.80), (-2.12, 0.80), (-2.12, 0.92), (-2.0, 0.92), (-2.0, 0.80)], 0.6),        # fuel flap
    ("XY", [(0.90, 0.0), (0.90, 0.79), (2.83, 0.77), (2.83, 0.0)], 0.5),                          # bonnet
    ("XY", [(-2.17, 0.0), (-2.17, 0.84), (-2.86, 0.80), (-2.86, 0.0)], 0.5),                      # boot lid
    ("YZr", [(0.0, 0.78), (0.78, 0.78), (0.82, 0.99)], 0.5),
]


def lim_spec():
    cs = Car(
        x0=-2.90, x1=2.90, wf=1.98, wr=-1.57, track=1.74, r_tire=0.385, tire_w=0.275, rim_r=0.282, arch_r=0.43,
        plan_rf=0.17, plan_rr=0.28,
        width=[(-2.9, 0.93), (-2.55, 0.985), (-1.6, 0.998), (-0.4, 0.982), (1.2, 0.985), (1.98, 0.995), (2.6, 0.99), (2.9, 0.975)],
        zbot=[(-2.9, 0.42), (-2.62, 0.27), (-2.2, 0.20), (2.35, 0.20), (2.72, 0.27), (2.9, 0.33)],
        zsill=[(-2.9, 0.47), (-2.5, 0.38), (2.5, 0.37), (2.9, 0.42)],
        zsh=[(-2.9, 0.86), (-1.6, 0.885), (0.0, 0.875), (2.0, 0.885), (2.9, 0.87)],
        belt_t=[(-2.9, 0.965), (-2.2, 1.0), (0.0, 1.0), (0.9, 1.005), (2.0, 1.0), (2.9, 0.985)],
        deck_t=[(-2.9, 0.985), (-2.55, 1.035), (-2.15, 1.045), (-1.7, 1.03), (0.85, 1.04), (1.3, 1.05), (2.6, 1.045), (2.9, 1.03)],
        tuck_t=[(-2.9, 0.03), (-2.0, 0.07), (0.0, 0.075), (2.0, 0.06), (2.9, 0.035)],
        x_ws=0.85, x_bl=-2.15,
        roof_t=[(-2.15, 1.045), (-1.95, 1.33), (-1.62, 1.50), (-1.1, 1.555), (-0.3, 1.565), (0.2, 1.535), (0.5, 1.35), (0.85, 1.04)],
        lean_t=[(-2.2, 0.11), (0.9, 0.13)], n_exp=4.0,
        s_g0=0.035, s_g1=0.35, s_rail=0.405, s_w0=0.455,
        side_breaks=[0.85, (0.53, 0.20), -0.47, -0.64, (-1.70, -1.52), -2.15],
        roof_breaks=[0.85, 0.22, -0.47, -0.64, -1.78, -2.15],
        col_counts=[18, 18, 3, 18, 12],
        seat_x=[0.02, -1.25],
    )
    return cs


@asset("Car_Limousine", group="Cars", res=4096, collision="Convex", edge=0.003, ao_dist=0.45, mask=True)
def car_limousine(A):
    cs = lim_spec()
    A.piece("Wheels", "Static", res=2048)
    A.piece("Interior", "Static", res=2048)
    A.piece("Glass", "Glass", res=256, glass=True)
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    cs_ = lim_spec()
    split = [(x, interp(cs_.zsh, x) + 0.0015) for x in np.linspace(cs_.x0, cs_.x1, 13)]
    coach = [(x, interp(cs_.zsh, x) - 0.035) for x in np.linspace(cs_.x0, cs_.x1, 13)]
    P1 = reg("lx_paint_lim", lux_paint, gaps=LIM_GAPS, mask=1.0, split=split)
    P2 = reg("lx_paint2_lim", lux_paint, gaps=LIM_GAPS, mask=0.5)
    reg("lx_leather_lim", lux_leather, col=(0.42, 0.33, 0.22), rough=0.42)
    reg("lx_quilt_lim", lux_leather, col=(0.42, 0.33, 0.22), rough=0.42, quilt=1.0)
    reg("lx_dash_lim", lux_leather, col=(0.05, 0.03, 0.02), rough=0.45)
    reg("lx_alcantara_lim", lux_fabric, col=(0.40, 0.37, 0.32), rough=0.92)
    reg("lx_carpet", lux_fabric, col=(0.03, 0.025, 0.02), rough=0.95)
    reg("lx_plate_lim", lux_plate, image=plate_image("PLATE_LIM", "RGT 001"))
    reg("lx_caliper_lim", paint, col=(0.02, 0.02, 0.022), rough=0.15, peel=0.1, grime=0.02)

    def mats(c, n):
        if n.z < -0.5 and c.z < interp(cs.zbot, c.x) + 0.04:
            return "lx_under"
        return P1

    cut = [("arch", (cs.wf, cs.r_tire + 0.012, cs.arch_r, cs.track / 2 - 0.2)), ("arch", (cs.wr, cs.r_tire + 0.012, cs.arch_r, cs.track / 2 - 0.2))]
    build_lower(A, cs, mats, cut, nst=118)

    def tagmat(rk, k, s):
        if rk == "side":
            return "glass" if k in (1, 3) else ("lx_black" if k == 2 else P2)
        if rk in ("belt", "frame"):
            return "lx_black" if k == 2 else P2
        if rk == "rail":
            return P2
        # roof rows
        if k == 0 or k == 4:
            return "glass" if s >= cs.s_w0 else P2
        return P2

    build_greenhouse(A, cs, tagmat, headliner="lx_alcantara_lim")
    # ---- chrome: beltline, DLO surrounds, sill strips -------------------------------------------
    for side in (1, -1):
        bl = [cs.gh(x, 0.0, side) + cs.gh_normal(x, 0.0, side) * 0.004 for x in np.linspace(0.75, -2.05, 70)]
        frame_sweep(A, bl, 0.007, 0.018, "lx_chrome", up=(0, side, 0.3), smooth=60)
        for (xf, xr) in (((0.53, 0.20), (-0.47, -0.47)), ((-0.64, -0.64), (-1.70, -1.52))):
            loop = dlo_loop(cs, xf, xr, cs.s_g0, cs.s_g1, side, off=0.004)
            frame_sweep(A, loop, 0.005, 0.014, "lx_chrome", closed=True, smooth=60)
        chrome_strip_side(A, cs, 1.45, -1.12, 0.36, side, w=0.045, t=0.006, mat="lx_satin")
        xs_ = np.linspace(cs.x1 - 0.12, cs.x0 + 0.14, 90)
        pin = [V((x, side * (cs.side_y(x, interp(cs.zsh, x)) + 0.0015), interp(cs.zsh, x))) for x in xs_]
        frame_sweep(A, pin, 0.004, 0.0035, "lx_chrome", up=(0, side, 0), smooth=60)
        # coach-door handles (both beside the B pillar)
        flush_handle(A, cs, -0.33, 0.93, side, 0.2)
        flush_handle(A, cs, -0.78, 0.93, side, 0.2)
        mirror(A, cs, 0.62, 1.03, side, P2, reach=0.17)
        emblem(A, (1.38, side * (cs.side_y(1.38, 0.74) + 0.001), 0.74), 0.026, axis="+Y" if side > 0 else "-Y")
    # ---- front: vertical-bar grille, slim lamps, chrome blade, intake -------------------------
    F = surf_front(cs)
    zg0, zg1 = 0.58, 0.99
    gr = []
    for i in range(9):
        t = i / 8
        gr.append((lerp(0.32, 0.29, t), lerp(zg0, zg1, t)))
    grille_outline = round_poly([(0.32, zg0), (0.29, zg1), (-0.29, zg1), (-0.32, zg0)], 0.045)
    fan_patch(A, grille_outline, F, 0.045, "lx_chrome", rings=3)
    inner = round_poly([(0.29, zg0 + 0.035), (0.265, zg1 - 0.035), (-0.265, zg1 - 0.035), (-0.29, zg0 + 0.035)], 0.03)
    fan_patch(A, inner, F, 0.047, "lx_black", rings=2)
    xg = max(F(0.0, zg0 + 0.1)[0].x, F(0.0, zg1 - 0.1)[0].x) + 0.047
    nb_ = 17
    for i in range(nb_):
        yv = lerp(-0.25, 0.25, i / (nb_ - 1))
        A.box((0.036, 0.008, zg1 - zg0 - 0.075), at=(xg + 0.012, yv, (zg0 + zg1) / 2), mat="lx_satin", bevel=0.0025, segs=2)
    A.box((0.03, 0.62, 0.028), at=(xg + 0.02, 0, zg1 - 0.05), mat="lx_satin", bevel=0.006, segs=2)
    A.box((0.03, 0.03, zg1 - zg0 - 0.06), at=(xg + 0.024, 0, (zg0 + zg1) / 2), mat="lx_chrome", bevel=0.006, segs=2)
    emblem(A, (xg + 0.036, 0, zg1 - 0.05), 0.032, axis="X")
    # headlamps: slim horizontal units wrapping the corners, LED brow + three vertical ticks
    for s in (1, -1):
        hl = round_poly(rrect_pts(0.34, 0.095, 0.03, 4), 0.006)
        hl = [(s * 0.635 + p[0], 0.93 + p[1] - 0.04 * (p[0] * s) / 0.17 * 0.25) for p in hl]
        if s < 0:
            hl = list(reversed(hl))
        fan_patch(A, hl, F, 0.012, "lx_chrome_dark", rings=3)
        brow = round_poly(rrect_pts(0.30, 0.012, 0.005, 2), 0.002)
        brow = [(s * 0.635 + p[0], 0.962 + p[1] - 0.04 * (p[0] * s) / 0.17 * 0.25) for p in brow]
        if s < 0:
            brow = list(reversed(brow))
        fan_patch(A, brow, F, 0.016, "lx_emit_white", rings=1, piece="Emissive", smooth=180)
        for k in range(3):
            yv = s * (0.74 + 0.028 * k)
            tk = round_poly(rrect_pts(0.008, 0.05, 0.003, 2), 0.001)
            tk = [(yv + p[0], 0.91 + p[1] - 0.04 * (yv * s - 0.635) / 0.17 * 0.25) for p in tk]
            fan_patch(A, tk if s > 0 else list(reversed(tk)), F, 0.016, "lx_emit_white", rings=1, piece="Emissive", smooth=180)
        for k, yv in enumerate((0.56, 0.645)):
            p, n = F(s * yv, 0.91)
            A.cyl(0.026, 0.02, at=tuple(p + n * 0.006), axis="X", mat="lx_lens", n=28, bevel=0.003)
            A.cyl(0.03, 0.012, at=tuple(p + n * 0.004), axis="X", mat="lx_chrome", n=28, bevel=0.002)
        A.point("Headlight" + ("L" if s > 0 else "R"), tuple(F(s * 0.62, 0.93)[0]))
    # chrome blade + plate + lower intake + fog lines
    blade = []
    for yv in np.linspace(-0.86, 0.86, 40):
        p, n = F(yv, 0.44)
        blade.append(p + n * 0.012)
    frame_sweep(A, blade, 0.022, 0.014, "lx_chrome", up=(0, 0, 1), smooth=50)
    number_plate(A, cs, "lx_plate_lim", 0.52, True)
    intake = round_poly(rrect_pts(1.15, 0.12, 0.04, 4), 0.01)
    intake = [(p[0], 0.33 + p[1]) for p in intake]
    fan_patch(A, intake, F, 0.006, "lx_mesh_chrome", rings=3)
    for s in (1, -1):
        fl = round_poly(rrect_pts(0.16, 0.012, 0.005, 2), 0.002)
        fl = [(s * 0.74 + p[0], 0.36 + p[1]) for p in fl]
        fan_patch(A, fl if s > 0 else list(reversed(fl)), F, 0.01, "lx_emit_white", rings=1, piece="Emissive", smooth=180)
    # ---- rear: horizontal tail lamps with a twin-line signature, chrome bar, plate, tips -----------
    R = surf_rear(cs)
    for s in (1, -1):
        tl = round_poly(rrect_pts(0.40, 0.12, 0.025, 4), 0.006)
        tl = [(s * 0.62 + p[0], 0.88 + p[1]) for p in tl]
        if s > 0:
            tl = list(reversed(tl))
        fan_patch(A, tl, R, 0.01, "lx_redlens", rings=3)
        for zz in (0.905, 0.86):
            ln = round_poly(rrect_pts(0.34, 0.01, 0.004, 2), 0.0015)
            ln = [(s * 0.63 + p[0], zz + p[1]) for p in ln]
            fan_patch(A, ln if s < 0 else list(reversed(ln)), R, 0.014, "lx_emit_red", rings=1, piece="Emissive", smooth=180)
        vt = round_poly(rrect_pts(0.012, 0.09, 0.004, 2), 0.0015)
        vt = [(s * 0.80 + p[0], 0.88 + p[1]) for p in vt]
        fan_patch(A, vt if s < 0 else list(reversed(vt)), R, 0.014, "lx_emit_red", rings=1, piece="Emissive", smooth=180)
        A.point("Taillight" + ("L" if s > 0 else "R"), tuple(R(s * 0.62, 0.88)[0]))
    bar = []
    for yv in np.linspace(-0.40, 0.40, 24):
        p, n = R(yv, 0.88)
        bar.append(p + n * 0.006)
    frame_sweep(A, bar, 0.014, 0.012, "lx_chrome", up=(0, 0, 1), smooth=50)
    p, n = R(0.0, 0.88)
    emblem(A, tuple(p + n * 0.016), 0.03, axis="-X")
    number_plate(A, cs, "lx_plate_lim", 0.68, False)
    blade = []
    for yv in np.linspace(-0.88, 0.88, 40):
        p, n = R(yv, 0.47)
        blade.append(p + n * 0.01)
    frame_sweep(A, blade, 0.018, 0.012, "lx_chrome", up=(0, 0, 1), smooth=50)
    for s in (1, -1):
        p, n = R(s * 0.55, 0.32)
        A.prism(round_poly(rrect_pts(0.17, 0.06, 0.028, 4), 0.004), 0.08, mat="lx_chrome", plane="YZ", at=tuple(p + V((0.0, 0, 0))), bevel=0.004)
        A.prism(round_poly(rrect_pts(0.15, 0.045, 0.02, 4), 0.004), 0.08, mat="lx_black", plane="YZ", at=tuple(p + V((-0.006, 0, 0))), bevel=0.002)
    # ---- wheels ------------------------------------------------------------------------------
    for wx in (cs.wf, cs.wr):
        for s in (1, -1):
            wheel(A, cs, (wx, s * cs.track / 2, cs.r_tire), cs.r_tire, cs.tire_w, cs.rim_r, s, style="multi", rim="lx_rim", rim2="lx_rim_dark",
                  caliper="lx_caliper_lim", spokes=10)
    # ---- interior ----------------------------------------------------------------------------
    cabin(A, cs, "lx_leather_lim", "lx_quilt_lim", "lx_walnut", "lx_leather_lim", "lx_dash_lim", rows=2, rear_lounge=True)
    A.preview["Body"] = {"tint": (0.09, 0.006, 0.016), "tint2": (0.006, 0.006, 0.008), "coat": True}
    A.view = (1.0, -0.72, 0.25)
    A.lens = 55


def in_xz(poly, x, z):
    return pip(poly, x, z)


def bar_across(A, surf, y0, y1, z, w, t, mat, off=0.006, n=30, piece=None):
    path = []
    for yv in np.linspace(y0, y1, n):
        p, nn = surf(yv, z if not callable(z) else z(yv))
        path.append(p + nn * off)
    return frame_sweep(A, path, w, t, mat, up=(0, 0, 1), smooth=50, piece=piece)


def mirror_poly(poly, s):
    """Outline (y, z) given for the +Y side: return it for side s, keeping a consistent winding."""
    if s > 0:
        return poly
    return [(-p[0], p[1]) for p in reversed(poly)]


def slit(cy, cz, w, h, r=None, slope=0.0):
    pts = round_poly(rrect_pts(w, h, r if r is not None else min(w, h) * 0.45, 3), min(w, h) * 0.15)
    return [(cy + p[0], cz + p[1] + slope * p[0]) for p in pts]


# ======================================================================================
# 2. Long-hood grand tourer
# ======================================================================================

GT_GAPS = [
    ("XZ", [(0.16, 0.25), (0.15, 0.55), (0.11, 0.85)], 0.45),
    ("XZ", [(-1.16, 0.25), (-1.17, 0.6), (-1.2, 0.9)], 0.45),
    ("XZ", [(0.16, 0.25), (-1.16, 0.25)], 0.6, 0.0016),
    ("XZ", [(-1.72, 0.74), (-1.84, 0.74), (-1.84, 0.84), (-1.72, 0.84), (-1.72, 0.74)], 0.6),
    ("XY", [(0.09, 0.0), (0.09, 0.70), (0.9, 0.73), (2.0, 0.66), (2.36, 0.52), (2.38, 0.0)], 0.5),
    ("XY", [(-1.99, 0.0), (-1.99, 0.74), (-2.33, 0.70), (-2.36, 0.0)], 0.5),
    ("YZr", [(0.0, 0.70), (0.70, 0.70), (0.76, 0.92)], 0.5),
]


def gt_spec():
    return Car(
        x0=-2.425, x1=2.425, wf=1.56, wr=-1.29, track=1.70, r_tire=0.355, tire_w=0.265, tire_wr=0.295, rim_r=0.268, arch_r=0.395,
        plan_rf=0.24, plan_rr=0.30,
        width=[(-2.425, 0.90), (-2.1, 0.985), (-1.29, 1.0), (-0.45, 0.958), (0.5, 0.962), (1.56, 0.99), (2.15, 0.975), (2.425, 0.90)],
        zbot=[(-2.425, 0.36), (-2.15, 0.20), (-1.8, 0.14), (1.9, 0.14), (2.22, 0.18), (2.425, 0.27)],
        zsill=[(-2.425, 0.40), (-2.0, 0.27), (1.9, 0.27), (2.425, 0.33)],
        zsh=[(-2.425, 0.72), (-1.3, 0.80), (-0.3, 0.745), (0.8, 0.73), (1.6, 0.72), (2.425, 0.58)],
        belt_t=[(-2.425, 0.86), (-1.7, 0.925), (-1.0, 0.895), (0.05, 0.86), (1.0, 0.83), (1.6, 0.81), (2.2, 0.72), (2.425, 0.62)],
        deck_t=[(-2.425, 0.885), (-2.26, 0.955), (-1.95, 0.955), (-1.5, 0.93), (0.05, 0.885), (0.6, 0.875), (1.25, 0.845), (1.9, 0.775),
                (2.28, 0.67), (2.425, 0.60)],
        tuck_t=[(-2.425, 0.03), (-1.3, 0.095), (-0.4, 0.075), (0.8, 0.06), (1.6, 0.05), (2.425, 0.03)],
        x_ws=0.05, x_bl=-1.95,
        roof_t=[(-1.95, 0.955), (-1.6, 1.06), (-1.3, 1.165), (-1.0, 1.25), (-0.75, 1.29), (-0.56, 1.295), (-0.42, 1.25), (-0.2, 1.11), (0.05, 0.885)],
        lean_t=[(-2.0, 0.15), (0.1, 0.13)], n_exp=4.0,
        s_g0=0.035, s_g1=0.36, s_rail=0.41, s_w0=0.46,
        side_breaks=[0.05, (-0.16, -0.47), -1.10, -1.15, (-1.62, -1.24), -1.95],
        roof_breaks=[0.05, -0.50, -1.10, -1.15, -1.30, -1.95],
        col_counts=[16, 18, 3, 12, 15],
        seat_x=[-0.72, -1.42],
    )


@asset("Car_GrandTourer", group="Cars", res=4096, collision="Convex", edge=0.003, ao_dist=0.45, mask=True)
def car_grandtourer(A):
    cs = gt_spec()
    A.piece("Wheels", "Static", res=2048)
    A.piece("Interior", "Static", res=2048)
    A.piece("Glass", "Glass", res=256, glass=True)
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    P1 = reg("lx_paint_gt", lux_paint, gaps=GT_GAPS, mask=1.0)
    reg("lx_leather_gt", lux_leather, col=(0.30, 0.11, 0.035), rough=0.40)
    reg("lx_quilt_gt", lux_leather, col=(0.30, 0.11, 0.035), rough=0.40, quilt=0.8, k=30.0)
    reg("lx_dash_gt", lux_leather, col=(0.012, 0.011, 0.011), rough=0.42)
    reg("lx_alcantara_dark", lux_fabric, col=(0.02, 0.02, 0.021), rough=0.95)
    reg("lx_carpet", lux_fabric, col=(0.03, 0.025, 0.02), rough=0.95)
    reg("lx_plate_gt", lux_plate, image=plate_image("PLATE_GT", "MRD 77"))
    reg("lx_caliper_bronze", lux_metal, col=(0.42, 0.25, 0.10), rough=0.25)

    def mats(c, n):
        if n.z < -0.5 and c.z < interp(cs.zbot, c.x) + 0.04:
            return "lx_under"
        return P1

    cut = [("arch", (cs.wf, cs.r_tire + 0.012, cs.arch_r, cs.track / 2 - 0.22)), ("arch", (cs.wr, cs.r_tire + 0.012, cs.arch_r, cs.track / 2 - 0.22))]
    build_lower(A, cs, mats, cut, nst=112)

    def tagmat(rk, k, s):
        if rk == "side":
            return "glass" if k in (1, 3) else ("lx_black" if k in (0, 2) else P1)
        if rk in ("belt", "frame"):
            return "lx_black" if k in (0, 1, 2, 3) else P1
        if rk == "rail":
            return P1 if k == 4 else "lx_black"
        if k == 0 or k == 4:
            return "glass" if s >= cs.s_w0 else ("lx_black" if k == 0 else P1)
        return "lx_black"     # floating black roof

    build_greenhouse(A, cs, tagmat, headliner="lx_alcantara_dark")
    for side in (1, -1):
        loop = dlo_loop(cs, (-0.16, -0.47), (-1.62, -1.24), cs.s_g0, cs.s_g1, side, off=0.004)
        frame_sweep(A, loop, 0.004, 0.011, "lx_chrome", closed=True, smooth=60)
        flush_handle(A, cs, -0.95, 0.80, side, 0.18)
        mirror(A, cs, -0.05, 0.89, side, P1, reach=0.16, size=(0.2, 0.1, 0.11))
        # front fender gill: three dark-chrome blades
        S = surf_side(cs, side)
        gill = [(0.95, 0.44), (1.13, 0.44), (1.10, 0.66), (0.98, 0.66)]
        gill = round_poly(gill, 0.02)
        fan_patch(A, gill if side > 0 else list(reversed(gill)), S, 0.002, "lx_black", rings=2)
        for k in range(3):
            xx = 0.99 + k * 0.045
            bl = [(xx - 0.008, 0.46), (xx + 0.008, 0.46), (xx - 0.012, 0.64), (xx - 0.028, 0.64)]
            fan_patch(A, bl if side > 0 else list(reversed(bl)), S, 0.006, "lx_chrome_dark", rings=1)
        emblem(A, (1.04, side * (cs.side_y(1.04, 0.72) + 0.002), 0.72), 0.02, axis="+Y" if side > 0 else "-Y")
        chrome_strip_side(A, cs, 1.15, -0.85, 0.30, side, w=0.02, t=0.005, mat="lx_satin")
    # ---- front: low wide grille, slim LED light bars --------------------------------------------
    F = surf_front(cs)
    gr = round_poly([(0.46, 0.27), (0.42, 0.44), (-0.42, 0.44), (-0.46, 0.27)], 0.06)
    fan_patch(A, gr, F, 0.02, "lx_chrome", rings=3)
    gr2 = round_poly([(0.43, 0.29), (0.395, 0.42), (-0.395, 0.42), (-0.43, 0.29)], 0.05)
    fan_patch(A, gr2, F, 0.022, "lx_mesh_chrome", rings=3)
    for zz in (0.33, 0.375):
        bar_across(A, F, -0.40, 0.40, zz, 0.006, 0.01, "lx_chrome_dark", off=0.03, n=20)
    p, n = F(0.0, 0.47)
    emblem(A, tuple(p + n * 0.012), 0.028, axis="X")
    for s in (1, -1):
        hl = slit(0.62, 0.585, 0.40, 0.055, slope=-0.12)
        fan_patch(A, mirror_poly(hl, s), F, 0.006, "lx_smoke", rings=3)
        for zz, hh in ((0.598, 0.011), (0.571, 0.006)):
            bar = slit(0.62, zz, 0.37, hh, slope=-0.12)
            fan_patch(A, mirror_poly(bar, s), F, 0.011, "lx_emit_white", rings=1, piece="Emissive", smooth=180)
        A.point("Headlight" + ("L" if s > 0 else "R"), tuple(F(s * 0.62, 0.585)[0]))
        si = round_poly([(0.62, 0.20), (0.80, 0.22), (0.78, 0.33), (0.60, 0.30)], 0.03)
        fan_patch(A, mirror_poly(si, s), F, 0.004, "lx_mesh", rings=2)
    number_plate(A, cs, "lx_plate_gt", 0.205, True, w=0.46, h=0.10)
    bar_across(A, F, -0.9, 0.9, 0.17, 0.02, 0.008, "lx_black", off=0.004, n=30)
    # ---- rear: ducktail, full-width slim light bar, quad tips ---------------------------------
    R = surf_rear(cs)
    bar = slit(0.0, 0.86, 1.46, 0.016)
    fan_patch(A, list(reversed(bar)), R, 0.008, "lx_smoke", rings=1)
    bar2 = slit(0.0, 0.86, 1.42, 0.009)
    fan_patch(A, list(reversed(bar2)), R, 0.012, "lx_emit_red", rings=1, piece="Emissive", smooth=180)
    for s in (1, -1):
        tl = round_poly([(0.58, 0.79), (0.80, 0.80), (0.82, 0.885), (0.58, 0.875)], 0.02)
        fan_patch(A, list(reversed(mirror_poly(tl, s))), R, 0.006, "lx_redlens", rings=2)
        ln = slit(0.70, 0.81, 0.2, 0.008)
        fan_patch(A, list(reversed(mirror_poly(ln, s))), R, 0.01, "lx_emit_red", rings=1, piece="Emissive", smooth=180)
        A.point("Taillight" + ("L" if s > 0 else "R"), tuple(R(s * 0.70, 0.84)[0]))
        for yy in (0.42, 0.56):
            pp, nn = R(s * yy, 0.40)
            A.cyl(0.042, 0.1, at=tuple(pp + nn * 0.02), axis="X", rot=(0, 0, 180), mat="lx_chrome", n=28, bevel=0.004)
            A.cyl(0.034, 0.1, at=tuple(pp + nn * 0.021), axis="X", rot=(0, 0, 180), mat="lx_black", n=24, bevel=0.002)
    p, n = R(0.0, 0.79)
    emblem(A, tuple(p + n * 0.01), 0.024, axis="-X")
    number_plate(A, cs, "lx_plate_gt", 0.53, False, w=0.46, h=0.10)
    dif = round_poly([(-0.66, 0.16), (0.66, 0.16), (0.62, 0.32), (-0.62, 0.32)], 0.03)
    fan_patch(A, list(reversed(dif)), R, 0.004, "lx_black", rings=2)
    # ---- wheels ------------------------------------------------------------------------------
    for wx, tw in ((cs.wf, cs.tire_w), (cs.wr, cs.tire_wr)):
        for s in (1, -1):
            wheel(A, cs, (wx, s * cs.track / 2, cs.r_tire), cs.r_tire, tw, cs.rim_r, s, style="twin", rim="lx_rim", rim2="lx_rim_gun",
                  caliper="lx_caliper_bronze", spokes=5)
    cabin(A, cs, "lx_leather_gt", "lx_quilt_gt", "lx_walnut", "lx_leather_gt", "lx_dash_gt", rows=1, seat_w=0.52, wheel_r=0.18)
    # 2+2 occasional rear: low quilted cushions + a leather luggage shelf under the fastback
    A.cur = "Interior"
    for s in (1, -1):
        A.box((0.42, 0.46, 0.1), at=(-1.30, s * 0.36, 0.36), mat="lx_quilt_gt", bevel=0.035, segs=3)
        A.box((0.1, 0.46, 0.34), at=(-1.55, s * 0.36, 0.55), rot=(0, -30, 0), mat="lx_quilt_gt", bevel=0.035, segs=3)
    A.box((0.45, 1.5, 0.03), at=(-1.75, 0, 0.78), mat="lx_leather_gt", bevel=0.01)
    A.cur = "Body"
    A.preview["Body"] = {"tint": (0.006, 0.014, 0.045), "coat": True}
    A.view = (1.0, -0.75, 0.22)
    A.lens = 55


# ======================================================================================
# 3. Mid-engine hypercar
# ======================================================================================

HY_INTAKE = [(-0.62, 0.30), (-0.60, 0.60), (-1.08, 0.66), (-1.16, 0.34)]
HY_GAPS = [
    ("XZ", [(0.62, 0.22), (0.60, 0.50), (0.52, 0.70)], 0.45),
    ("XZ", [(-0.56, 0.22), (-0.57, 0.62), (-0.5, 0.78)], 0.45),
    ("XY", [(0.62, 0.0), (0.62, 0.52), (1.9, 0.46), (2.2, 0.30), (2.25, 0.0)], 0.4),
    ("XY", [(-1.52, 0.0), (-1.52, 0.70), (-2.25, 0.66), (-2.28, 0.0)], 0.4),
]


def hy_spec():
    return Car(
        x0=-2.35, x1=2.35, wf=1.33, wr=-1.37, track=1.72, track_r=1.70, r_tire=0.335, r_tire_r=0.35, tire_w=0.265, tire_wr=0.335,
        rim_r=0.255, rim_rr=0.268, arch_r=0.375, arch_rr=0.39,
        plan_rf=0.48, plan_rr=0.22,
        width=[(-2.35, 0.92), (-2.0, 1.02), (-1.37, 1.04), (-0.75, 0.985), (0.3, 0.975), (1.33, 1.0), (1.95, 0.975), (2.35, 0.86)],
        zbot=[(-2.35, 0.30), (-2.05, 0.15), (-1.8, 0.10), (1.85, 0.10), (2.2, 0.11), (2.35, 0.15)],
        zsill=[(-2.35, 0.36), (-1.9, 0.22), (1.9, 0.21), (2.35, 0.20)],
        zsh=[(-2.35, 0.66), (-1.37, 0.74), (-0.6, 0.67), (0.5, 0.60), (1.33, 0.64), (2.0, 0.52), (2.35, 0.34)],
        belt_t=[(-2.35, 0.80), (-1.75, 0.86), (-1.1, 0.82), (-0.2, 0.735), (0.75, 0.71), (1.33, 0.745), (1.9, 0.63), (2.35, 0.39)],
        deck_t=[(-2.35, 0.84), (-2.15, 0.925), (-1.75, 0.97), (-1.45, 0.975), (-1.0, 0.80), (0.0, 0.75), (0.75, 0.70), (1.1, 0.665),
                (1.7, 0.585), (2.1, 0.48), (2.35, 0.36)],
        tuck_t=[(-2.35, 0.03), (-1.37, 0.10), (-0.5, 0.12), (0.5, 0.11), (1.33, 0.07), (2.35, 0.03)],
        x_ws=0.95, x_bl=-1.45,
        roof_t=[(-1.45, 0.975), (-1.15, 1.05), (-0.75, 1.10), (-0.35, 1.115), (0.05, 1.08), (0.5, 0.93), (0.95, 0.678)],
        lean_t=[(-1.5, 0.17), (0.8, 0.16)], n_exp=3.6,
        s_g0=0.04, s_g1=0.37, s_rail=0.42, s_w0=0.47,
        side_breaks=[0.95, (0.64, 0.10), (-0.52, -0.40), (-0.56, -0.44), (-0.70, -0.52), -1.45],
        roof_breaks=[0.95, 0.08, -0.40, -0.45, -0.80, -1.45],
        col_counts=[15, 18, 3, 5, 15],
        seat_x=[-0.18],
    )


@asset("Car_Hypercar", group="Cars", res=4096, collision="Convex", edge=0.003, ao_dist=0.4, mask=True)
def car_hypercar(A):
    cs = hy_spec()
    A.piece("Wheels", "Static", res=2048)
    A.piece("Interior", "Static", res=2048)
    A.piece("Glass", "Glass", res=256, glass=True)
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    P1 = reg("lx_paint_hy", lux_paint, gaps=HY_GAPS, mask=1.0)
    reg("lx_leather_hy", lux_leather, col=(0.012, 0.012, 0.013), rough=0.45)
    reg("lx_quilt_hy", lux_leather, col=(0.012, 0.012, 0.013), rough=0.45, quilt=0.7, k=34.0)
    reg("lx_alcantara_dark", lux_fabric, col=(0.02, 0.02, 0.021), rough=0.95)
    reg("lx_carpet", lux_fabric, col=(0.03, 0.025, 0.02), rough=0.95)
    reg("lx_plate_hy", lux_plate, image=plate_image("PLATE_HY", "VNT 9"))
    reg("lx_caliper_orange", paint, col=(0.75, 0.16, 0.012), rough=0.2, peel=0.1, grime=0.02)

    def mats(c, n):
        if n.z < -0.5 and c.z < interp(cs.zbot, c.x) + 0.04:
            return "lx_under"
        if in_xz(HY_INTAKE, c.x, c.z) and abs(c.y) < cs.w(c.x) - 0.006:
            return "lx_carbon"
        if c.z < interp(cs.zsill, c.x) + 0.01 and abs(n.y) > 0.3:
            return "lx_carbon"
        return P1

    cut = [("arch", (cs.wf, cs.r_tire + 0.01, cs.arch_r, cs.track / 2 - 0.22)), ("arch", (cs.wr, cs.r_tire_r + 0.01, cs.arch_rr, cs.track_r / 2 - 0.24)),
           ("prism", (HY_INTAKE, 0.80, 1.3))]
    build_lower(A, cs, mats, cut, nst=112)

    def tagmat(rk, k, s):
        if rk == "side":
            return "glass" if k in (1, 3) else ("lx_black" if k in (0, 2) else P1)
        if rk in ("belt", "frame"):
            return "lx_black" if k < 4 else P1
        if rk == "rail":
            return "lx_black" if k < 4 else P1
        if k == 0:
            return "glass" if s >= cs.s_w0 else "lx_black"
        if k == 4:
            return "glass" if s >= cs.s_w0 + 0.05 else P1
        return "lx_carbon"    # exposed-weave carbon roof

    build_greenhouse(A, cs, tagmat, headliner="lx_alcantara_dark")
    for side in (1, -1):
        # intake: mesh back wall + two carbon vanes + chrome lip
        yin = 0.80
        pts = [(x, side * yin, z) for (x, z) in HY_INTAKE]
        A.mesh(pts if side < 0 else list(reversed(pts)), [(0, 1, 2, 3)], "lx_mesh", smooth=0, recalc=False)
        for t in (0.35, 0.68):
            x0_ = lerp(-0.61, -1.12, t)
            A.box((0.012, 0.14, 0.28), at=(x0_, side * (yin + 0.07), 0.48), rot=(0, 8, 0), mat="lx_carbon", bevel=0.003)
        flush_handle(A, cs, -0.30, 0.66, side, 0.13)
        S = surf_side(cs, side)
        # carbon mirror on a slim stalk
        mirror(A, cs, 0.42, 0.74, side, "lx_carbon", reach=0.15, size=(0.18, 0.08, 0.08))
        emblem(A, (1.75, side * (cs.side_y(1.75, 0.52) + 0.002), 0.52), 0.016, axis="+Y" if side > 0 else "-Y")
    # engine-cover louvres (black slats on the deck) + glass-covered bay behind the cabin
    T = surf_top(cs)
    for k in range(7):
        xx = -1.62 - k * 0.075
        for s in (1, -1):
            sl = [(xx - 0.02, 0.18), (xx + 0.02, 0.18), (xx + 0.02, 0.58), (xx - 0.02, 0.58)]
            sl = round_poly(sl, 0.006)
            sl = [(p[0], s * p[1]) for p in sl]
            fan_patch(A, sl if s > 0 else list(reversed(sl)), T, 0.008, "lx_black", rings=1)
    # front: low nose, big side intakes, thin blade headlamps, carbon splitter
    F = surf_front(cs)
    for s in (1, -1):
        it = round_poly([(0.30, 0.15), (0.82, 0.17), (0.80, 0.355), (0.36, 0.375)], 0.035)
        fan_patch(A, mirror_poly(it, s), F, 0.004, "lx_mesh", rings=3)
        fr = [F(p[0] * s, p[1])[0] + F(p[0] * s, p[1])[1] * 0.006 for p in chaikin(it, 1, closed=True)]
        frame_sweep(A, fr, 0.006, 0.01, "lx_carbon", closed=True, smooth=50)
        hl = slit(0.58, 0.43, 0.42, 0.075, slope=-0.16)
        fan_patch(A, mirror_poly(hl, s), F, 0.006, "lx_smoke", rings=3)
        for zz, hh in ((0.448, 0.01), (0.418, 0.01)):
            ln = slit(0.58, zz, 0.38, hh, slope=-0.16)
            fan_patch(A, mirror_poly(ln, s), F, 0.011, "lx_emit_white", rings=1, piece="Emissive", smooth=180)
        A.point("Headlight" + ("L" if s > 0 else "R"), tuple(F(s * 0.58, 0.425)[0]))
    ci = round_poly([(0.24, 0.16), (0.24, 0.26), (-0.24, 0.26), (-0.24, 0.16)], 0.03)
    fan_patch(A, ci, F, 0.004, "lx_mesh", rings=2)
    p, n = F(0.0, 0.33)
    emblem(A, tuple(p + n * 0.006), 0.026, axis="X")
    lipp = []
    for yv in np.linspace(-0.84, 0.84, 34):
        pp, nn = F(yv, 0.15)
        lipp.append(pp + V((0.035, 0, -0.04)))
    frame_sweep(A, lipp, 0.014, 0.11, "lx_carbon", up=(0, 0, 1), smooth=50)
    for side in (1, -1):
        sk = [V((x, side * (cs.w(x) * 0.985 + 0.012), 0.115)) for x in np.linspace(1.0, -1.05, 24)]
        frame_sweep(A, sk, 0.03, 0.05, "lx_carbon", up=(0, 0, 1), smooth=50)
    number_plate(A, cs, "lx_plate_hy", 0.21, True, w=0.40, h=0.09)
    # rear: open mesh, double-line lamps, ducktail, diffuser fins, centre twin exhaust
    R = surf_rear(cs)
    mesh = round_poly([(-0.72, 0.36), (0.72, 0.36), (0.78, 0.70), (-0.78, 0.70)], 0.04)
    fan_patch(A, list(reversed(mesh)), R, 0.004, "lx_mesh", rings=3)
    for s in (1, -1):
        for zz in (0.765, 0.735):
            ln = slit(0.62, zz, 0.42, 0.010)
            fan_patch(A, list(reversed(mirror_poly(ln, s))), R, 0.01, "lx_emit_red", rings=1, piece="Emissive", smooth=180)
        A.point("Taillight" + ("L" if s > 0 else "R"), tuple(R(s * 0.62, 0.75)[0]))
    ln = slit(0.0, 0.79, 0.5, 0.007)
    fan_patch(A, list(reversed(ln)), R, 0.01, "lx_emit_red", rings=1, piece="Emissive", smooth=180)
    for s in (1, -1):
        pp, nn = R(s * 0.11, 0.42)
        A.lathe([(0.05, -0.02), (0.062, -0.02), (0.062, 0.05), (0.05, 0.05)], at=tuple(pp), axis="X", rot=(0, 0, 180), mat="lx_satin", n=32, cap=False)
        A.cyl(0.05, 0.06, at=tuple(pp + nn * 0.005), axis="X", rot=(0, 0, 180), mat="lx_black", n=28, bevel=0.002)
    for k in range(5):
        yy = -0.5 + k * 0.25
        A.box((0.42, 0.012, 0.09), at=(-2.02, yy, 0.13), rot=(0, -10, 0), mat="lx_carbon", bevel=0.003)
    number_plate(A, cs, "lx_plate_hy", 0.29, False, w=0.40, h=0.09)
    # fixed ducktail lip
    lip = []
    for yv in np.linspace(-0.74, 0.74, 30):
        pp, nn = R(yv, 0.80)
        lip.append(pp + V((-0.02, 0, 0.0)))
    frame_sweep(A, lip, 0.006, 0.05, "lx_carbon", up=(0, 0, 1), smooth=50)
    # wheels: centre-lock, Y spokes, carbon-ceramic discs, orange calipers
    for wx, tr, rt, tw, rr in ((cs.wf, cs.track, cs.r_tire, cs.tire_w, cs.rim_r), (cs.wr, cs.track_r, cs.r_tire_r, cs.tire_wr, cs.rim_rr)):
        for s in (1, -1):
            wheel(A, cs, (wx, s * tr / 2, rt), rt, tw, rr, s, style="y", rim="lx_rim_gun", rim2="lx_rim_dark",
                  caliper="lx_caliper_orange", disc="lx_disc_cc", centre_lock=True, spokes=7)
    cabin(A, cs, "lx_leather_hy", "lx_quilt_hy", "lx_carbon", "lx_alcantara_dark", "lx_leather_hy", rows=1, dash_wood=False, seat_w=0.5,
          x_back=-0.62, wheel_r=0.17, back_h=0.5, floor_dz=0.06)
    # engine bay under the rear glass: bulkhead + engine block + intake plenum
    A.cur = "Interior"
    A.box((0.03, 1.4, 0.5), at=(-0.64, 0, 0.55), mat="lx_carbon", bevel=0.005)
    A.box((0.75, 0.62, 0.3), at=(-1.08, 0, 0.62), mat="lx_rim_dark", bevel=0.03, segs=3)
    for s in (1, -1):
        A.box((0.7, 0.16, 0.08), at=(-1.08, s * 0.18, 0.80), rot=(s * 12, 0, 0), mat="lx_carbon", bevel=0.02, segs=2)
    A.box((0.9, 1.3, 0.02), at=(-1.08, 0, 0.45), mat="lx_under", bevel=0.004)
    A.cur = "Body"
    A.preview["Body"] = {"tint": (0.055, 0.058, 0.062), "coat": True}
    A.view = (1.0, -0.75, 0.2)
    A.lens = 55


# ======================================================================================
# 4. Full-size luxury SUV
# ======================================================================================

SUV_GAPS = [
    ("XZ", [(1.10, 0.40), (1.12, 0.80), (1.10, 1.18)], 0.45),
    ("XZ", [(-0.80, 0.40), (-0.80, 1.19)], 0.45),
    ("XZ", [(-0.84, 0.40), (-0.84, 1.19)], 0.45),
    ("XZ", [(-0.95, 0.40), (-0.95, 0.80), (-1.02, 0.92), (-1.20, 1.0), (-1.45, 1.02), (-1.70, 1.07), (-1.86, 1.19)], 0.45),
    ("XZ", [(1.10, 0.42), (-0.95, 0.42)], 0.6, 0.0016),
    ("XZ", [(-1.92, 0.88), (-2.06, 0.88), (-2.06, 1.0), (-1.92, 1.0), (-1.92, 0.88)], 0.6),
    ("XY", [(0.90, 0.0), (0.90, 0.83), (2.50, 0.82), (2.50, 0.0)], 0.5),
    ("YZr", [(0.0, 0.62), (0.86, 0.62), (0.88, 1.16)], 0.5),
]


def suv_spec():
    return Car(
        x0=-2.575, x1=2.575, wf=1.655, wr=-1.445, track=1.74, r_tire=0.41, tire_w=0.285, rim_r=0.282, arch_r=0.462,
        plan_rf=0.15, plan_rr=0.13,
        width=[(-2.575, 0.95), (-2.25, 0.99), (-1.445, 1.012), (-0.8, 0.988), (0.0, 0.985), (0.9, 0.988), (1.655, 1.012), (2.3, 0.995),
               (2.575, 0.965)], concave=0.016,
        zbot=[(-2.575, 0.48), (-2.36, 0.32), (-2.0, 0.24), (2.1, 0.24), (2.4, 0.33), (2.575, 0.42)],
        zsill=[(-2.575, 0.52), (-2.2, 0.45), (2.2, 0.45), (2.575, 0.50)],
        zsh=[(-2.575, 1.07), (0.0, 1.085), (2.575, 1.10)],
        belt_t=[(-2.575, 1.14), (-1.0, 1.17), (0.8, 1.175), (2.0, 1.205), (2.575, 1.195)],
        deck_t=[(-2.575, 1.16), (-2.42, 1.20), (0.85, 1.20), (1.4, 1.262), (2.4, 1.272), (2.575, 1.245)],
        tuck_t=[(-2.575, 0.03), (-1.4, 0.06), (0.0, 0.06), (1.6, 0.05), (2.575, 0.03)],
        x_ws=0.85, x_bl=-2.42,
        roof_t=[(-2.42, 1.20), (-2.37, 1.67), (-2.22, 1.885), (-1.6, 1.92), (-0.5, 1.935), (0.0, 1.92), (0.22, 1.86), (0.85, 1.20)],
        lean_t=[(-2.5, 0.10), (0.9, 0.11)], n_exp=6.0,
        s_g0=0.03, s_g1=0.34, s_rail=0.39, s_w0=0.44,
        side_breaks=[0.85, (0.62, 0.21), -0.78, -0.86, -1.80, -1.88, (-2.30, -2.22), -2.42],
        roof_breaks=[0.85, 0.20, -0.78, -0.86, -1.80, -1.88, -2.30, -2.42],
        col_counts=[15, 18, 3, 18, 3, 8, 6],
        seat_x=[0.02, -1.0],
    )


@asset("Car_SUV", group="Cars", res=4096, collision="Convex", edge=0.003, ao_dist=0.45, mask=True)
def car_suv(A):
    cs = suv_spec()
    A.piece("Wheels", "Static", res=2048)
    A.piece("Interior", "Static", res=2048)
    A.piece("Glass", "Glass", res=256, glass=True)
    A.piece("GlassPrivacy", "Glass", res=256, glass=True)
    A.piece("Emissive", "Emissive", res=512, emissive=True)
    A.cur = "Body"
    P1 = reg("lx_paint_suv", lux_paint, gaps=SUV_GAPS, mask=1.0)
    reg("lx_leather_suv", lux_leather, col=(0.24, 0.13, 0.06), rough=0.42)
    reg("lx_quilt_suv", lux_leather, col=(0.24, 0.13, 0.06), rough=0.42, quilt=0.7, k=24.0)
    reg("lx_dash_suv", lux_leather, col=(0.03, 0.02, 0.015), rough=0.45)
    reg("lx_alcantara_lim", lux_fabric, col=(0.40, 0.37, 0.32), rough=0.92)
    reg("lx_carpet", lux_fabric, col=(0.03, 0.025, 0.02), rough=0.95)
    reg("lx_plate_suv", lux_plate, image=plate_image("PLATE_SUV", "BST 404"))
    reg("lx_caliper_suv", paint, col=(0.30, 0.012, 0.012), rough=0.18, peel=0.1, grime=0.02)

    def mats(c, n):
        if n.z < -0.5 and c.z < interp(cs.zbot, c.x) + 0.04:
            return "lx_under"
        return P1

    cut = [("arch", (cs.wf, cs.r_tire + 0.02, cs.arch_r, cs.track / 2 - 0.22)), ("arch", (cs.wr, cs.r_tire + 0.02, cs.arch_r, cs.track / 2 - 0.22))]
    build_lower(A, cs, mats, cut, nst=112)

    def tagmat(rk, k, s):
        if rk == "side":
            return "glass" if k in (1, 3, 5) else ("lx_black" if k in (0, 2, 4, 6) else P1)
        if rk in ("belt", "frame", "rail"):
            return "lx_black" if 0 < k < 6 else ("lx_black" if k == 0 else "lx_black")
        if k == 0 or k == 6:
            return "glass" if s >= cs.s_w0 else "lx_black"
        return P1

    build_greenhouse(A, cs, tagmat, glass_piece=lambda tag, k: "GlassPrivacy" if k >= 3 else "Glass", headliner="lx_alcantara_lim")
    for side in (1, -1):
        for (xf, xr) in (((0.62, 0.21), (-0.78, -0.78)), ((-0.86, -0.86), (-1.80, -1.80)), ((-1.88, -1.88), (-2.30, -2.22))):
            loop = dlo_loop(cs, xf, xr, cs.s_g0, cs.s_g1, side, off=0.004)
            frame_sweep(A, loop, 0.005, 0.016, "lx_chrome", closed=True, smooth=60)
        flush_handle(A, cs, -0.55, 1.10, side, 0.21)
        flush_handle(A, cs, -1.62, 1.10, side, 0.21)
        mirror(A, cs, 0.62, 1.20, side, P1, reach=0.12, size=(0.25, 0.11, 0.15))
        chrome_strip_side(A, cs, 1.18, -1.0, 0.50, side, w=0.06, t=0.007, mat="lx_chrome")
        # roof rail
        rail = [cs.gh(x, cs.s_rail + 0.05, side) + V((0, 0, 0.035)) for x in np.linspace(0.1, -2.2, 30)]
        frame_sweep(A, rail, 0.025, 0.03, "lx_satin", up=(0, 0, 1), smooth=50)
        for x in (0.05, -2.2):
            p = cs.gh(x, cs.s_rail + 0.05, side)
            A.box((0.08, 0.04, 0.05), at=(x, p.y, p.z + 0.02), mat="lx_black", bevel=0.012, segs=2)
        # front fender vent
        S = surf_side(cs, side)
        vent = round_poly([(1.08, 0.80), (1.26, 0.80), (1.24, 0.86), (1.10, 0.86)], 0.012)
        fan_patch(A, vent if side > 0 else list(reversed(vent)), S, 0.006, "lx_chrome", rings=2)
        emblem(A, (1.17, side * (cs.side_y(1.17, 0.83) + 0.008), 0.83), 0.015, axis="+Y" if side > 0 else "-Y")
    # front: imposing upright grille with horizontal bars, slim twin-line lamps
    F = surf_front(cs)
    gr = round_poly([(0.43, 0.64), (0.41, 1.15), (-0.41, 1.15), (-0.43, 0.64)], 0.05)
    fan_patch(A, gr, F, 0.04, "lx_chrome", rings=3)
    gr2 = round_poly([(0.385, 0.685), (0.365, 1.105), (-0.365, 1.105), (-0.385, 0.685)], 0.03)
    fan_patch(A, gr2, F, 0.042, "lx_black", rings=2)
    for k in range(7):
        zz = 0.725 + k * 0.06
        bar_across(A, F, -0.37, 0.37, zz, 0.02, 0.026, "lx_satin", off=0.055, n=16)
    p, n = F(0.0, 0.93)
    emblem(A, tuple(p + n * 0.07), 0.036, axis="X")
    for s in (1, -1):
        hl = round_poly([(0.47, 1.00), (0.93, 1.015), (0.94, 1.16), (0.47, 1.155)], 0.025)
        fan_patch(A, mirror_poly(hl, s), F, 0.008, "lx_chrome_dark", rings=3)
        for zz in (1.135, 1.105):
            ln = slit(0.70, zz, 0.42, 0.011)
            fan_patch(A, mirror_poly(ln, s), F, 0.013, "lx_emit_white", rings=1, piece="Emissive", smooth=180)
        vb = slit(0.70, 1.022, 0.42, 0.008)
        fan_patch(A, mirror_poly(vb, s), F, 0.01, "lx_emit_white", rings=1, piece="Emissive", smooth=180)
        for yv in (0.60, 0.70, 0.80):
            pp, nn = F(s * yv, 1.062)
            A.cyl(0.022, 0.012, at=tuple(pp + nn * 0.008), axis="X", mat="lx_lens", n=24, bevel=0.002)
        A.point("Headlight" + ("L" if s > 0 else "R"), tuple(F(s * 0.735, 1.10)[0]))
        si = round_poly([(0.58, 0.40), (0.86, 0.40), (0.84, 0.55), (0.60, 0.55)], 0.03)
        fan_patch(A, mirror_poly(si, s), F, 0.006, "lx_mesh_chrome", rings=2)
    li = round_poly([(-0.48, 0.36), (0.48, 0.36), (0.46, 0.50), (-0.46, 0.50)], 0.03)
    fan_patch(A, li, F, 0.006, "lx_mesh_chrome", rings=2)
    skid = round_poly([(-0.55, 0.27), (0.55, 0.27), (0.52, 0.33), (-0.52, 0.33)], 0.02)
    fan_patch(A, skid, F, 0.012, "lx_satin", rings=2)
    number_plate(A, cs, "lx_plate_suv", 0.555, True)
    # rear: L-shaped lamps joined by a chrome bar, plate, twin square tips
    R = surf_rear(cs)
    for s in (1, -1):
        tl = round_poly([(0.62, 0.99), (0.90, 0.99), (0.91, 1.16), (0.80, 1.16), (0.79, 1.06), (0.62, 1.06)], 0.015)
        fan_patch(A, list(reversed(mirror_poly(tl, s))), R, 0.008, "lx_redlens", rings=3)
        ln = slit(0.75, 1.025, 0.25, 0.01)
        fan_patch(A, list(reversed(mirror_poly(ln, s))), R, 0.012, "lx_emit_red", rings=1, piece="Emissive", smooth=180)
        vt = slit(0.865, 1.10, 0.01, 0.11)
        fan_patch(A, list(reversed(mirror_poly(vt, s))), R, 0.012, "lx_emit_red", rings=1, piece="Emissive", smooth=180)
        A.point("Taillight" + ("L" if s > 0 else "R"), tuple(R(s * 0.76, 1.04)[0]))
        pp, nn = R(s * 0.62, 0.36)
        A.prism(round_poly(rrect_pts(0.20, 0.07, 0.015, 3), 0.004), 0.08, mat="lx_chrome", plane="YZ", at=tuple(pp), bevel=0.004)
        A.prism(round_poly(rrect_pts(0.18, 0.054, 0.01, 3), 0.004), 0.08, mat="lx_black", plane="YZ", at=tuple(pp + V((-0.006, 0, 0))), bevel=0.002)
    bar_across(A, R, -0.62, 0.62, 1.025, 0.014, 0.018, "lx_chrome", off=0.008, n=24)
    p, n = R(0.0, 0.88)
    emblem(A, tuple(p + n * 0.01), 0.034, axis="-X")
    number_plate(A, cs, "lx_plate_suv", 0.75, False)
    skid = round_poly([(-0.55, 0.42), (0.55, 0.42), (0.52, 0.48), (-0.52, 0.48)], 0.02)
    fan_patch(A, list(reversed(skid)), R, 0.012, "lx_satin", rings=2)
    for wx in (cs.wf, cs.wr):
        for s in (1, -1):
            wheel(A, cs, (wx, s * cs.track / 2, cs.r_tire), cs.r_tire, cs.tire_w, cs.rim_r, s, style="twin", rim="lx_rim", rim2="lx_rim_dark",
                  caliper="lx_caliper_suv", spokes=6)
    cabin(A, cs, "lx_leather_suv", "lx_quilt_suv", "lx_walnut", "lx_leather_suv", "lx_dash_suv", rows=2, rear_bench=True, seat_w=0.56)
    A.preview["Body"] = {"tint": (0.70, 0.69, 0.66), "coat": True}
    A.view = (1.0, -0.75, 0.22)
    A.lens = 55
