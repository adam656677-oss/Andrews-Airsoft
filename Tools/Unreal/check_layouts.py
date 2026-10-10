#!/usr/bin/env python3
"""Andrew's Airsoft - layout sanity checker and plan renderer (plain Python, no Unreal).

Loads Content/Python/airsoft_setup_lib/layouts.py and the asset JSON in Content/Airsoft/Data,
checks every map against the gameplay rules and renders top-down plans to Tools/Unreal/Plans/<Map>.png.

    python3 Tools/Unreal/check_layouts.py              # all maps, plans on
    python3 Tools/Unreal/check_layouts.py --maps IronwoodYard --no-plans

Checks:
  * every referenced asset id exists in the JSON data or has a built-in fallback; materials/tints known
  * spawns inside the playable bounds and not inside props; >= 1.5 m spacing
  * match maps: >= 10 Blue and >= 10 Red starts, objectives A/B/C present, reachable, not inside props,
    no enemy-spawn -> spawn sight lines, spawn exposure and cover-spacing stats, bot nav bounds cover
    the playable area, every start and every objective
  * staging: >= 16 neutral starts, 14 armory displays (one per weapon), practice targets at 10/25/40/60 m
Exit code 1 when any error is found.
"""

import argparse
import glob
import importlib.util
import json
import math
import os
import sys
import types
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
LAYOUTS_PY = os.path.join(ROOT, "Content", "Python", "airsoft_setup_lib", "layouts.py")
DATA_DIR = os.path.join(ROOT, "Content", "Airsoft", "Data")
PLAN_DIR = os.path.join(HERE, "Plans")
CATEGORIES = ("Weapons", "Attachments", "Gear", "Props", "Architecture")
SPECIAL_MATS = {"Puddle", "Foliage", "Blocker", "Glass"}


def load_layouts():
    """Import layouts.py by path. Guard: stub `unreal` so an accidental import cannot break the checker."""
    sys.dont_write_bytecode = True          # never drop __pycache__ into Content/Python
    stubbed = False
    try:
        import unreal  # noqa: F401  (only inside the editor)
    except ImportError:
        sys.modules["unreal"] = types.ModuleType("unreal")
        stubbed = True
    try:
        spec = importlib.util.spec_from_file_location("airsoft_layouts", LAYOUTS_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if stubbed:
            sys.modules.pop("unreal", None)


def load_json_assets():
    assets, materials = {}, {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        name = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # file may be mid-write by a generator
            print("  [warn] cannot read %s: %s" % (name, e))
            continue
        if name == "Materials.json":
            materials = data.get("Materials", {})
            continue
        cat = next((c for c in CATEGORIES if name.startswith(c)), "Props")
        for aid, a in (data.get("Assets") or {}).items():
            a = dict(a)
            a["_Category"] = cat
            assets[aid] = a
    return assets, materials


# ---------------------------------------------------------------------------------------------
class Index:
    """Uniform grid over footprints for fast segment / radius queries."""

    def __init__(self, fps, cell=4.0):
        self.cell = cell
        self.grid = {}
        for i, fp in enumerate(fps):
            r = math.hypot(*fp["h"])
            x0, x1 = int(math.floor((fp["c"][0] - r) / cell)), int(math.floor((fp["c"][0] + r) / cell))
            y0, y1 = int(math.floor((fp["c"][1] - r) / cell)), int(math.floor((fp["c"][1] + r) / cell))
            for gx in range(x0, x1 + 1):
                for gy in range(y0, y1 + 1):
                    self.grid.setdefault((gx, gy), []).append(i)
        self.fps = fps

    def near(self, x, y, r):
        c = self.cell
        out = set()
        for gx in range(int(math.floor((x - r) / c)), int(math.floor((x + r) / c)) + 1):
            for gy in range(int(math.floor((y - r) / c)), int(math.floor((y + r) / c)) + 1):
                out.update(self.grid.get((gx, gy), ()))
        return out

    def along(self, ax, ay, bx, by):
        L = math.hypot(bx - ax, by - ay)
        n = max(1, int(L / (self.cell * 0.5)))
        out = set()
        for k in range(n + 1):
            t = k / n
            x, y = ax + (bx - ax) * t, ay + (by - ay) * t
            gx, gy = int(math.floor(x / self.cell)), int(math.floor(y / self.cell))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    out.update(self.grid.get((gx + dx, gy + dy), ()))
        return out


def rect_distance(L, px, py, fp):
    dx, dy = px - fp["c"][0], py - fp["c"][1]
    lx, ly = L.rot2(dx, dy, -fp["yaw"])
    ex = max(abs(lx) - fp["h"][0], 0.0)
    ey = max(abs(ly) - fp["h"][1], 0.0)
    return math.hypot(ex, ey)


def split_openings(L, fp):
    """Door/window walls: turn the AABB into solid pieces around the openings (local cm)."""
    ops = fp.get("openings")
    if not ops:
        return [fp]
    hx, hy = fp["h"]
    cx, cy = fp["c"]
    z0b, z1b = fp["z0"], fp["z1"]
    out = []
    for (y0, oz0, y1, oz1) in ops:
        y0, y1, oz0, oz1 = y0 / 100.0, y1 / 100.0, oz0 / 100.0, oz1 / 100.0
        pieces = [(-hy, y0, z0b, z1b), (y1, hy, z0b, z1b)]
        if oz0 > 0.01:
            pieces.append((y0, y1, z0b, z0b + oz0))
        pieces.append((y0, y1, z0b + oz1, z1b))
        for (a, b, za, zb) in pieces:
            if b - a < 0.01:
                continue
            ox, oy = L.rot2(0.0, (a + b) / 2, fp["yaw"])
            n = dict(fp)
            n["c"] = (cx + ox, cy + oy)
            n["h"] = (hx, (b - a) / 2)
            n["z0"], n["z1"] = za, zb
            n["openings"] = None
            out.append(n)
    return out


def analyse(L, m, assets, materials, plans=True):
    errors, warns, info = [], [], []
    name = m["name"]
    bx0, by0, bx1, by1 = m["bounds"]
    items = m["items"]

    # ---- references ----
    for it in items:
        if it["t"] == "prop":
            aid = it["id"]
            if aid not in assets and not L.has_fallback(aid):
                errors.append("unknown asset id '%s' (no JSON entry and no fallback)" % aid)
            if it.get("tint") and it["tint"] not in L.TINTS:
                errors.append("unknown tint '%s' on %s" % (it["tint"], aid))
            if it.get("display"):
                w = it["display"]
                if w not in L.WEAPON_IDS and w not in assets:
                    errors.append("armory display weapon '%s' unknown" % w)
        elif it["t"] == "box":
            mat = it["mat"]
            if mat.startswith("Emissive:"):
                if mat.split(":", 1)[1] not in L.EMISSIVE_COLORS:
                    errors.append("unknown emissive colour %s" % mat)
            elif mat not in materials and mat not in SPECIAL_MATS:
                if materials:
                    errors.append("box material '%s' not in Materials.json" % mat)
            if it.get("tint") and it["tint"] not in L.TINTS:
                errors.append("unknown tint '%s' on box" % it["tint"])
    if m.get("levels"):      # multi-storey map: surface-based 3D checks and per-level plans (see analyse_levels)
        return analyse_levels(L, m, assets, materials, errors, warns, info, plans)

    fps = []
    for it in items:
        for fp in L.item_footprints(it, assets):
            fps.extend(split_openings(L, fp))
    solids = [f for f in fps if f["solid"] and not f["walk"] and f["z0"] < 1.2 and f["z1"] > L.STEP_HEIGHT + 0.01
              and f["kind"] != "blocker"]
    sight = [f for f in fps if f["los"] and f["z0"] <= L.EYE_HEIGHT <= f["z1"] and f["kind"] != "blocker"]
    cover = [f for f in fps if f["solid"] and f["z0"] < 0.5 and f["z1"] >= L.COVER_HEIGHT and f["kind"] != "blocker"
             and not f["walk"]]
    sidx, lidx, cidx = Index(solids), Index(sight), Index(cover)

    def blocked_at(x, y, pad=0.0, z=0.0):
        for i in sidx.near(x, y, 1.0 + pad):
            f = solids[i]
            if f["z1"] <= z + L.STEP_HEIGHT or f["z0"] >= z + 1.2:
                continue
            if L.point_in_rect(x, y, f, pad):
                return f
        return None

    def visible(ax, ay, bx, by):
        for i in lidx.along(ax, ay, bx, by):
            if L.segment_hits_rect(ax, ay, bx, by, sight[i], shrink=0.02):
                return False
        return True

    starts = [it for it in items if it["t"] == "start"]
    objs = {it["letter"]: it for it in items if it["t"] == "objective"}
    kind = m["kind"]

    # ---- starts ----
    for s in starts:
        x, y, z = s["p"]
        if not (bx0 + 0.4 <= x <= bx1 - 0.4 and by0 + 0.4 <= y <= by1 - 0.4):
            errors.append("start %s at (%.1f, %.1f) outside bounds" % (s["team"], x, y))
        f = blocked_at(x, y, pad=0.42, z=z)
        if f:
            errors.append("start %s at (%.1f, %.1f) inside %s" % (s["team"], x, y, f["label"]))
    for i in range(len(starts)):
        for j in range(i + 1, len(starts)):
            a, b = starts[i]["p"], starts[j]["p"]
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if d < 1.5 and abs(a[2] - b[2]) < 1.5:
                errors.append("starts too close (%.2f m) at (%.1f,%.1f)/(%.1f,%.1f)" % (d, a[0], a[1], b[0], b[1]))
    teams = {"Blue": [], "Red": [], "None": []}
    for s in starts:
        teams.setdefault(s["team"], []).append(s)
    info.append("starts: Blue %d, Red %d, Neutral %d" % (len(teams["Blue"]), len(teams["Red"]), len(teams["None"])))

    # ---- walk grid for reachability ----
    cell = 0.5
    nx, ny = int((bx1 - bx0) / cell), int((by1 - by0) / cell)
    walk = [[blocked_at(bx0 + (i + 0.5) * cell, by0 + (j + 0.5) * cell, pad=0.34) is None for j in range(ny)]
            for i in range(nx)]

    def to_cell(x, y):
        return (min(nx - 1, max(0, int((x - bx0) / cell))), min(ny - 1, max(0, int((y - by0) / cell))))

    def bfs(src):
        dist = {src: 0}
        q = deque([src])
        while q:
            c = q.popleft()
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + d[0], c[1] + d[1])
                if 0 <= n[0] < nx and 0 <= n[1] < ny and walk[n[0]][n[1]] and n not in dist:
                    dist[n] = dist[c] + 1
                    q.append(n)
        return dist

    def dijkstra(src):
        import heapq
        dist = {src: 0.0}
        pq = [(0.0, src)]
        steps = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.4142), (1, -1, 1.4142),
                 (-1, 1, 1.4142), (-1, -1, 1.4142)]
        while pq:
            d, c = heapq.heappop(pq)
            if d > dist.get(c, 1e18):
                continue
            for (dx, dy, w) in steps:
                n = (c[0] + dx, c[1] + dy)
                if not (0 <= n[0] < nx and 0 <= n[1] < ny) or not walk[n[0]][n[1]]:
                    continue
                if dx and dy and not (walk[c[0] + dx][c[1]] and walk[c[0]][c[1] + dy]):
                    continue
                nd = d + w
                if nd < dist.get(n, 1e18):
                    dist[n] = nd
                    heapq.heappush(pq, (nd, n))
        return dist

    reach = {}
    for team in ("Blue", "Red", "None"):
        if teams.get(team):
            reach[team] = bfs(to_cell(*teams[team][0]["p"][:2]))
            for s in teams[team]:
                if to_cell(*s["p"][:2]) not in reach[team]:
                    errors.append("%s start at (%.1f, %.1f) not connected to its spawn group" % (team, s["p"][0], s["p"][1]))

    # ---- match rules ----
    exposure = []
    cover_dist = []
    if kind == "match":
        if len(teams["Blue"]) < 10 or len(teams["Red"]) < 10:
            errors.append("needs >= 10 Blue and >= 10 Red starts")
        for letter in "ABC":
            o = objs.get(letter)
            if not o:
                errors.append("objective %s missing" % letter)
                continue
            x, y, z = o["p"]
            if not (bx0 <= x <= bx1 and by0 <= y <= by1):
                errors.append("objective %s outside bounds" % letter)
            f = blocked_at(x, y, pad=0.3, z=z)
            if f:
                errors.append("objective %s centre inside %s" % (letter, f["label"]))
            dmap = dijkstra(to_cell(x, y))
            line = []
            for team in ("Blue", "Red"):
                if reach.get(team, {}).get(to_cell(x, y)) is None:
                    errors.append("objective %s not reachable from %s spawn" % (letter, team))
                    continue
                ds = [dmap.get(to_cell(*s["p"][:2])) for s in teams[team]]
                ds = [d for d in ds if d is not None]
                if ds:
                    line.append("%s %.0f m" % (team, sum(ds) / len(ds) * cell))
            info.append("walk to %s (mean over starts): %s" % (letter, ", ".join(line)))
        # enemy spawn -> spawn sight lines
        bad = 0
        for a in teams["Blue"]:
            for b in teams["Red"]:
                if visible(a["p"][0], a["p"][1], b["p"][0], b["p"][1]):
                    bad += 1
        if bad:
            errors.append("%d Blue<->Red spawn pairs have line of sight" % bad)
        # exposure: walkable points >= 14 m from a team's spawn that see any of its starts
        step = 2.0
        pts = []
        y = by0 + 1.0
        while y < by1:
            x = bx0 + 1.0
            while x < bx1:
                c = to_cell(x, y)
                if walk[c[0]][c[1]]:
                    pts.append((x, y))
                x += step
            y += step
        for team, other in (("Blue", "Red"), ("Red", "Blue")):
            ss = teams[team]
            if not ss:
                continue
            far_vis = 0
            worst = 0.0
            for (x, y) in pts:
                dmin = min(math.hypot(x - s["p"][0], y - s["p"][1]) for s in ss)
                if dmin < 14.0:
                    continue
                seen = None
                for s in ss:
                    if visible(x, y, s["p"][0], s["p"][1]):
                        seen = s
                        break
                if seen:
                    d = math.hypot(x - seen["p"][0], y - seen["p"][1])
                    exposure.append((x, y, team))
                    far_vis += 1
                    worst = max(worst, d)
            info.append("%s spawn exposure: %d of %d points >= 14 m away see a start (farthest %.0f m)" %
                        (team, far_vis, len(pts), worst))
            if worst > 45.0:
                warns.append("%s spawn visible from %.0f m away" % (team, worst))
        # cover spacing
        for (x, y) in pts:
            best = 99.0
            for i in cidx.near(x, y, 10.0):
                best = min(best, rect_distance(L, x, y, cover[i]))
            cover_dist.append((x, y, best))
        ds = sorted(d for (_, _, d) in cover_dist)
        if ds:
            p50, p90, p98 = ds[len(ds) // 2], ds[int(len(ds) * 0.9)], ds[int(len(ds) * 0.98)]
            info.append("distance to nearest cover: median %.1f m, p90 %.1f m, p98 %.1f m, max %.1f m"
                        % (p50, p90, p98, ds[-1]))
            if p90 > 5.0:
                warns.append("cover too sparse (p90 %.1f m > 5 m, i.e. cover farther apart than ~10 m)" % p90)
        # bots: the NavMeshBoundsVolume must cover the playable area, every start and every objective
        nav = L.nav_bounds(m) if hasattr(L, "nav_bounds") else m.get("nav")
        if not nav:
            errors.append("no 'nav' bounds: bots need a NavMeshBoundsVolume on match maps")
        else:
            vx0, vy0, vz0, vx1, vy1, vz1 = nav
            if vx0 > bx0 or vy0 > by0 or vx1 < bx1 or vy1 < by1:
                errors.append("nav bounds (%.1f, %.1f)-(%.1f, %.1f) do not cover the playable bounds" % (vx0, vy0, vx1, vy1))
            if vz1 - vz0 < 3.0:
                errors.append("nav bounds only %.1f m tall" % (vz1 - vz0))
            for it in items:
                if it["t"] not in ("start", "objective"):
                    continue
                x, y, z = it["p"]
                if not (vx0 <= x <= vx1 and vy0 <= y <= vy1 and vz0 <= z <= vz1 - 2.0):
                    errors.append("%s at (%.1f, %.1f, %.1f) outside the nav bounds (bots can't path there)"
                                  % (it["t"], x, y, z))
            info.append("nav bounds: %.0f x %.0f m, z %.1f..%.1f m" % (vx1 - vx0, vy1 - vy0, vz0, vz1))

    # ---- staging rules ----
    if kind == "staging":
        if len(teams["None"]) < 16:
            errors.append("staging needs >= 16 neutral starts (has %d)" % len(teams["None"]))
        disp = [it["display"] for it in items if it["t"] == "prop" and it.get("display")]
        if len(disp) != 14 or set(disp) != set(L.WEAPON_IDS):
            errors.append("armory needs 14 displays, one per weapon (has %d: missing %s)" %
                          (len(disp), sorted(set(L.WEAPON_IDS) - set(disp))))
        fl = m.get("firing_line_x", 0.0)
        targets = [it for it in items if it["t"] == "target"]
        for d in (10, 25, 40, 60):
            if not any(abs(t["p"][0] - fl - d) < 0.5 for t in targets):
                errors.append("no practice target at %d m" % d)
        for t in targets:
            f = blocked_at(t["p"][0], t["p"][1], pad=0.2)
            if f:
                errors.append("target %s inside %s" % (t.get("caption"), f["label"]))
            if not visible(fl + 0.5, t["p"][1], t["p"][0] - 0.3, t["p"][1]):
                warns.append("target %s at y=%.1f has no clear lane from the firing line" % (t.get("caption"), t["p"][1]))
        info.append("displays %d, targets %d" % (len(disp), len(targets)))
        for team in ("None",):
            r = reach.get(team, {})
            for t in targets:
                if to_cell(t["p"][0] - 1.0, t["p"][1]) not in r:
                    warns.append("target %s not walkable from the hall" % t.get("caption"))
                    break
            for it in items:
                if it["t"] == "prop" and it.get("display"):
                    x, y = it["p"][0], it["p"][1]
                    ok = any(to_cell(x + dx, y + dy) in r for dx in (-1.2, 0, 1.2) for dy in (-1.2, 0, 1.2))
                    if not ok:
                        warns.append("display %s not reachable" % it["display"])

    counts = {}
    for it in items:
        k = it["t"] if it["t"] != "prop" else "prop"
        counts[k] = counts.get(k, 0) + 1
    info.append("items: " + ", ".join("%s %d" % kv for kv in sorted(counts.items())))
    if plans:
        render(L, m, fps, exposure, cover_dist, assets)
    return errors, warns, info


# ---------------------------------------------------------------------------------------------
MAT_COL = {"Grass": "#7fa35a", "Dirt": "#a98a63", "Gravel": "#b4aea2", "Mud": "#8a7356", "AsphaltWet": "#3b3d42",
           "Asphalt": "#55575c", "ConcreteFloor": "#a9a9a6", "MarbleBlack": "#2b2a2e", "Walnut": "#6b4127",
           "Carpet": "#6c2433", "DiamondPlate": "#8d9196", "Concrete": "#9b9b97", "BrickDark": "#5a3a33",
           "Brick": "#8a4f3c", "Velvet": "#701c2c", "PlywoodPainted": "#53625a", "Timber": "#9b7a52",
           "PaintedSteel": "#6d7378", "CorrodedMetal": "#7a5a43", "Brass": "#c7a250", "Plywood": "#c9a46e"}
TINT_COL = {"Blue": "#3a5f9a", "Red": "#a6382c", "Green": "#4e7a46", "Rust": "#9a5a2f", "Sand": "#b9a271",
            "Grey": "#808487", "Black": "#202124", "Gunmetal": "#4a4e52", "DeepRed": "#6b1018", "White": "#d9d9d6"}


def render(L, m, fps, exposure, cover_dist, assets):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Circle

    bx0, by0, bx1, by1 = m["bounds"]
    w, h = bx1 - bx0, by1 - by0
    match = m["kind"] == "match"
    fig_w = 22 if match else 14
    fig_h = max(6.0, fig_w * (h / w) * (0.5 if match else 1.0) + 1.2)
    fig, axes = plt.subplots(1, 2 if match else 1, figsize=(fig_w, fig_h), dpi=110)
    axes = axes if match else [axes]
    ax = axes[0]
    pad = 4.0
    for a in axes:
        a.set_xlim(bx0 - pad, bx1 + pad)
        a.set_ylim(by1 + pad, by0 - pad)       # +Y down, like the Unreal top view
        a.set_aspect("equal")
        a.set_facecolor("#ecebe6")
        a.grid(True, color="#00000014", lw=0.5)
        a.set_xticks(range(int(bx0 // 10 * 10), int(bx1) + 1, 10))
        a.set_yticks(range(int(by0 // 10 * 10), int(by1) + 1, 10))
    order = sorted(fps, key=lambda f: (f["z1"] > 0.06, f["z0"] > 1.2, f["z1"]))
    for f in order:
        poly = L.rect_corners(f)
        lab = f["label"]
        if f["kind"] == "blocker":
            ax.add_patch(Polygon(poly, closed=True, fill=False, ec="#d0303070", lw=0.5, ls=":"))
            continue
        if f["z1"] <= 0.06:                       # floor / ground decals
            col = MAT_COL.get(lab.split("_")[0], None)
            for it_m in MAT_COL:
                if lab.startswith(it_m) or lab == it_m:
                    col = MAT_COL[it_m]
            ax.add_patch(Polygon(poly, closed=True, fc=(col or "#c8c4b8") + "55", ec="none"))
            continue
        if f["z0"] >= 1.2:                        # overhead: roofs, decks, lamps
            ax.add_patch(Polygon(poly, closed=True, fill=False, ec="#5a5a5a90", lw=0.6, ls="--"))
            continue
        if not f["solid"]:
            ax.add_patch(Polygon(poly, closed=True, fill=False, ec="#9c8f6a", lw=0.5))
            continue
        if f["walk"]:
            fc = "#c9b48a"
        elif lab.startswith("Tree"):
            ax.add_patch(Circle(f["c"], 3.2, fc="#3d6b2c30", ec="#3d6b2c60", lw=0.5))
            fc = "#5b3d22"
        elif lab.startswith("Bush"):
            fc = "#4f7f3a"
        elif lab.startswith("Container"):
            fc = "#5f7e98"
        elif lab.startswith("Wall_Plywood"):
            fc = "#8a5a2b"
        elif lab.startswith("Wall_Concrete") or lab.endswith("Wall"):
            fc = "#555555"
        elif not f["los"]:
            fc = "#c7b991"
        elif f["z1"] >= L.EYE_HEIGHT:
            fc = "#3e3e3e"
        elif f["z1"] >= L.COVER_HEIGHT:
            fc = "#8c7b5a"
        else:
            fc = "#c2b38c"
        ax.add_patch(Polygon(poly, closed=True, fc=fc, ec="#00000060", lw=0.4))
    # objectives, starts, targets, displays, lights
    for it in m["items"]:
        t = it["t"]
        x, y = it["p"][0], it["p"][1]
        if t == "objective":
            ax.add_patch(Circle((x, y), it["radius"], fc="#f0b42a30", ec="#c48a00", lw=1.6))
            ax.text(x, y, it["letter"], ha="center", va="center", fontsize=16, weight="bold", color="#8a5a00")
        elif t == "start":
            col = {"Blue": "#1f5fd0", "Red": "#d0301f"}.get(it["team"], "#555555")
            a = math.radians(it["yaw"])
            tri = [(x + 0.9 * math.cos(a), y + 0.9 * math.sin(a)),
                   (x + 0.55 * math.cos(a + 2.5), y + 0.55 * math.sin(a + 2.5)),
                   (x + 0.55 * math.cos(a - 2.5), y + 0.55 * math.sin(a - 2.5))]
            ax.add_patch(Polygon(tri, closed=True, fc=col, ec="white", lw=0.4))
        elif t == "target":
            ax.plot([x], [y], marker="x", color="#e06a00", ms=6, mew=1.6)
            ax.text(x, y - 0.9, it.get("caption", ""), ha="center", fontsize=5, color="#a04a00")
        elif t == "prop" and it.get("display"):
            ax.plot([x], [y], marker="s", color="#d4a537", ms=4)
            ax.text(x, y + 0.9, it["display"], ha="center", fontsize=5, color="#6b5010", rotation=0)
        elif t == "light":
            ax.plot([x], [y], marker="*", color="#f2c200", ms=5)
        elif t == "camera":
            a = math.radians(it["yaw"])
            ax.plot([x], [y], marker="o", color="black", ms=5)
            for da in (-18.75, 18.75):
                ax.plot([x, x + 9 * math.cos(a + math.radians(da))], [y, y + 9 * math.sin(a + math.radians(da))],
                        color="black", lw=0.8)
    ax.add_patch(Polygon([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)], closed=True, fill=False, ec="#d03030",
                         lw=1.0))
    ax.set_title("%s  (%s)  %.0f x %.0f m  -  plan" % (m["name"], m["path"], w, h), fontsize=11)
    if match:
        ax2 = axes[1]
        import numpy as np
        xs = sorted(set(round(p[0], 2) for p in cover_dist))
        ys = sorted(set(round(p[1], 2) for p in cover_dist))
        grid = np.full((len(ys), len(xs)), np.nan)
        xi = {v: i for i, v in enumerate(xs)}
        yi = {v: i for i, v in enumerate(ys)}
        for (x, y, d) in cover_dist:
            grid[yi[round(y, 2)], xi[round(x, 2)]] = d
        if xs and ys:
            im = ax2.imshow(grid, extent=(xs[0] - 1, xs[-1] + 1, ys[-1] + 1, ys[0] - 1), cmap="magma_r", vmin=0,
                            vmax=8, interpolation="nearest", alpha=0.85)
            fig.colorbar(im, ax=ax2, fraction=0.03, pad=0.01, label="m to nearest cover")
        for f in fps:
            if f["solid"] and f["z0"] < 1.2 and f["z1"] > 0.5 and f["kind"] != "blocker":
                ax2.add_patch(Polygon(L.rect_corners(f), closed=True, fc="#ffffff", ec="#00000080", lw=0.3))
        for (x, y, team) in exposure:
            ax2.plot([x], [y], marker="o", ms=2.2, color="#1f5fd0" if team == "Blue" else "#d0301f", alpha=0.7)
        for it in m["items"]:
            if it["t"] == "start":
                ax2.plot([it["p"][0]], [it["p"][1]], marker="^", ms=4,
                         color={"Blue": "#1f5fd0", "Red": "#d0301f"}.get(it["team"], "#444"))
            if it["t"] == "objective":
                ax2.add_patch(Circle(it["p"][:2], it["radius"], fill=False, ec="#c48a00", lw=1.2))
        ax2.set_title("cover distance (dark = exposed)  ·  dots: points >= 14 m out that see a spawn", fontsize=10)
    fig.tight_layout()
    os.makedirs(PLAN_DIR, exist_ok=True)
    out = os.path.join(PLAN_DIR, m["name"] + ".png")
    fig.savefig(out)
    plt.close(fig)
    return out


# =============================================================================================
# Multi-storey maps (map key "levels"): surface-based navigation, 3D sight lines, per-level plans
# =============================================================================================
# Used for maps that declare "levels": [(name, floor_z), ...] (NightjarGarage). Instead of the 2D ground
# grid above, every walkable surface (top faces of solid boxes, pitched ramp slabs, ramp props described
# by JSON "Layout": {"Ramp": ...}) becomes a node per 0.5 m cell; a node needs capsule headroom, nodes link
# when their heights differ by <= STEP_HEIGHT and one-way when a player can drop (<= MAX_DROP). Sight lines
# are 3D segments (eye to eye) against oriented boxes, so floor slabs block them. Asset hints from the JSON
# "Layout" dict: Core (cm rect), Los / Cover / Solid (bools), Ramp {X0, X1, Y0, Y1, Z0, Z1, Wall, WallT} (cm).
CAPSULE_H = 1.75
CAPSULE_R = 0.34
MAX_DROP = 4.0
NODE_MERGE = 0.5          # surfaces closer than this in one cell are one floor (the upper one counts)


def _vol(cx, cy, cz, hx, hy, hz, yaw=0.0, pitch=0.0, **kw):
    d = {"c": (cx, cy), "cz": cz, "h": (hx, hy), "hz": hz, "yaw": yaw, "pitch": pitch}
    p = math.radians(pitch)
    d["ex"] = (abs(hx * math.cos(p)) + abs(hz * math.sin(p)), hy)      # XY projection half extents (yawed frame)
    d["z0"] = cz - (abs(hx * math.sin(p)) + abs(hz * math.cos(p)))
    d["z1"] = cz + (abs(hx * math.sin(p)) + abs(hz * math.cos(p)))
    d.update(kw)
    return d


def _local(v, x, y):
    dx, dy = x - v["c"][0], y - v["c"][1]
    a = math.radians(-v["yaw"])
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


def vol_span_at(v, x, y, pad=0.0):
    """(z_bottom, z_top) of the volume above the point (x, y) grown by pad, or None."""
    u, w = _local(v, x, y)
    ex, ey = v["ex"]
    if abs(u) > ex + pad or abs(w) > ey + pad:
        return None
    if not v["pitch"]:
        return v["cz"] - v["hz"], v["cz"] + v["hz"]
    p = math.radians(v["pitch"])
    cp, sp = math.cos(p), math.sin(p)
    hx, hz = v["h"][0], v["hz"]
    u = max(-ex, min(ex, u))
    lt = max(-hx, min(hx, (u + hz * sp) / cp))
    lb = max(-hx, min(hx, (u - hz * sp) / cp))
    return v["cz"] + lb * sp - hz * cp, v["cz"] + lt * sp + hz * cp


def vol_top_at(v, x, y):
    """Height of the top face over (x, y) (inside the footprint only), or None."""
    u, w = _local(v, x, y)
    if abs(w) > v["h"][1]:
        return None
    if not v["pitch"]:
        return v["cz"] + v["hz"] if abs(u) <= v["h"][0] else None
    p = math.radians(v["pitch"])
    cp, sp = math.cos(p), math.sin(p)
    lt = (u + v["hz"] * sp) / cp
    if abs(lt) > v["h"][0]:
        return None
    return v["cz"] + lt * sp + v["hz"] * cp


def seg_hits_vol(v, a, b, shrink=0.02):
    """3D segment a-b against the oriented (yaw, pitch) box."""
    ax, ay = _local(v, a[0], a[1])
    bx, by = _local(v, b[0], b[1])
    az, bz = a[2] - v["cz"], b[2] - v["cz"]
    if v["pitch"]:
        p = math.radians(v["pitch"])
        cp, sp = math.cos(p), math.sin(p)
        ax, az = ax * cp + az * sp, -ax * sp + az * cp
        bx, bz = bx * cp + bz * sp, -bx * sp + bz * cp
    t0, t1 = 0.0, 1.0
    for p0, d, h in ((ax, bx - ax, v["h"][0] - shrink), (ay, by - ay, v["h"][1] - shrink), (az, bz - az, v["hz"] - shrink)):
        if h <= 0:
            return False
        if abs(d) < 1e-9:
            if p0 < -h or p0 > h:
                return False
            continue
        ta, tb = (-h - p0) / d, (h - p0) / d
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 > t1:
            return False
    return True


def level_volumes(L, items, assets):
    """Oriented volumes (movement / sight / cover) and walkable surfaces of a multi-storey map."""
    vols, surfs = [], []
    for it in items:
        t = it["t"]
        if t in ("box", "blocker"):
            cx, cy, cz = it["p"]
            sx, sy, sz = it["s"]
            coll = it.get("coll", True)
            pitch = it.get("pitch", 0.0) if t == "box" else 0.0
            v = _vol(cx, cy, cz, abs(sx) / 2, abs(sy) / 2, abs(sz) / 2, it.get("yaw", 0.0), pitch,
                     solid=bool(coll), los=bool(coll) and t == "box", cover=bool(coll) and t == "box" and not pitch,
                     kind=t, label=it.get("name", it.get("mat", "")), mat=it.get("mat", ""))
            if coll:
                vols.append(v)
                if t == "box":
                    surfs.append(v)
            elif t == "box":
                vols.append(dict(v, solid=False, los=False, cover=False))
            continue
        if t != "prop":
            continue
        aid = it["id"]
        a = assets.get(aid, {})
        lay = a.get("Layout") or {}
        k = L.KNOWN_ASSETS.get(aid, {})
        coll = a.get("Collision") or k.get("coll", "Box")
        solid = (coll != "None") and not it.get("nocoll") and lay.get("Solid", k.get("solid", True))
        los = solid and lay.get("Los", k.get("los", True))
        cover = solid and lay.get("Cover", True)
        sc = it.get("scale", (1.0, 1.0, 1.0))
        if isinstance(sc, (int, float)):
            sc = (sc, sc, sc)
        px, py, pz = it["p"]
        yaw = it.get("yaw", 0.0)
        if lay.get("Ramp"):
            r = lay["Ramp"]
            x0, x1, y0, y1 = (r["X0"] / 100.0 * sc[0], r["X1"] / 100.0 * sc[0], r["Y0"] / 100.0 * sc[1], r["Y1"] / 100.0 * sc[1])
            z0, z1 = r["Z0"] / 100.0 * sc[2], r["Z1"] / 100.0 * sc[2]
            wall, wt = r.get("Wall", 0.0) / 100.0 * sc[2], r.get("WallT", 25.0) / 100.0 * sc[1]
            n = max(4, int(math.ceil((x1 - x0) / 1.0)))
            for i in range(n):
                xa, xb = x0 + (x1 - x0) * i / n, x0 + (x1 - x0) * (i + 1) / n
                zt = z0 + (z1 - z0) * (i + 1) / n
                for (ya, yb, top, lab) in ((y0, y1, zt, "RampDeck"), (y0 - wt, y0, zt + wall, "RampWall"),
                                           (y1, y1 + wt, zt + wall, "RampWall")):
                    ox, oy = L.rot2((xa + xb) / 2, (ya + yb) / 2, yaw)
                    vols.append(_vol(px + ox, py + oy, pz + top / 2, (xb - xa) / 2, (yb - ya) / 2, top / 2, yaw, 0.0,
                                     solid=True, los=True, cover=False, kind="ramp", label=aid + ":" + lab))
            ox, oy = L.rot2((x0 + x1) / 2, (y0 + y1) / 2, yaw)
            surfs.append({"ramp": True, "c": (px + ox, py + oy), "h": ((x1 - x0) / 2, (y1 - y0) / 2), "ex": ((x1 - x0) / 2, (y1 - y0) / 2),
                          "yaw": yaw, "pitch": 0.0, "z_lo": pz + z0, "z_hi": pz + z1, "label": aid,
                          "cz": pz, "hz": 0.0, "z0": pz + z0, "z1": pz + z1})
            continue
        bmin, bmax = L.asset_bounds(aid, assets)
        if lay.get("Core"):
            (ax_, ay_), (bx_, by_) = lay["Core"]
        elif k.get("core"):
            (ax_, ay_), (bx_, by_) = k["core"]
        else:
            ax_, ay_, bx_, by_ = bmin[0], bmin[1], bmax[0], bmax[1]
        lx, ly = (ax_ + bx_) / 2 / 100.0 * sc[0], (ay_ + by_) / 2 / 100.0 * sc[1]
        hx, hy = abs(bx_ - ax_) / 2 / 100.0 * sc[0], abs(by_ - ay_) / 2 / 100.0 * sc[1]
        ox, oy = L.rot2(lx, ly, yaw)
        zlo, zhi = pz + bmin[2] / 100.0 * sc[2], pz + bmax[2] / 100.0 * sc[2]
        vols.append(_vol(px + ox, py + oy, (zlo + zhi) / 2, hx, hy, (zhi - zlo) / 2, yaw, 0.0, solid=bool(solid),
                         los=bool(los), cover=bool(cover), kind="prop", label=aid))
    return vols, surfs


def surf_top(s, x, y):
    if s.get("ramp"):
        u, w = _local(s, x, y)
        if abs(u) > s["h"][0] or abs(w) > s["h"][1]:
            return None
        f = (u + s["h"][0]) / (2 * s["h"][0])
        return s["z_lo"] + (s["z_hi"] - s["z_lo"]) * f
    return vol_top_at(s, x, y)


class Index3(Index):
    """Index over oriented volumes (uses the XY projection radius)."""

    def __init__(self, vols, cell=4.0):
        Index.__init__(self, [{"c": v["c"], "h": v["ex"]} for v in vols], cell)
        self.fps = vols


def analyse_levels(L, m, assets, materials, errors, warns, info, plans=True):
    bx0, by0, bx1, by1 = m["bounds"]
    items = m["items"]
    levels = sorted(m["levels"], key=lambda lv: lv[1])
    vols, surfs = level_volumes(L, items, assets)
    move = [v for v in vols if v["solid"]]
    sight = [v for v in vols if v["los"] and v["kind"] != "blocker"]
    cover = [v for v in vols if v["cover"] and v["kind"] in ("box", "prop")]
    midx, lidx, cidx, sidx = Index3(move), Index3(sight), Index3(cover), Index3(surfs)

    def blocked(x, y, h, pad):
        for i in midx.near(x, y, pad + 1.0):
            v = move[i]
            if v["z1"] <= h + L.STEP_HEIGHT + 0.01 or v["z0"] >= h + CAPSULE_H:
                continue
            sp = vol_span_at(v, x, y, pad)
            if sp and sp[1] > h + L.STEP_HEIGHT + 0.01 and sp[0] < h + CAPSULE_H:
                return v
        return None

    def visible(a, b):
        for i in lidx.along(a[0], a[1], b[0], b[1]):
            if seg_hits_vol(sight[i], a, b):
                return False
        return True

    # ---- nodes: walkable floor heights per 0.5 m cell ----
    cell = 0.5
    nx, ny = int((bx1 - bx0) / cell), int((by1 - by0) / cell)
    nodes = {}                      # (i, j) -> sorted list of valid heights
    for i in range(nx):
        x = bx0 + (i + 0.5) * cell
        for j in range(ny):
            y = by0 + (j + 0.5) * cell
            hs = []
            for k in sidx.near(x, y, 0.0):
                h = surf_top(surfs[k], x, y)
                if h is not None:
                    hs.append(h)
            if not hs:
                continue
            hs.sort(reverse=True)
            keep = []
            for h in hs:
                if not keep or keep[-1] - h > NODE_MERGE:
                    keep.append(h)
            ok = [h for h in keep if blocked(x, y, h, CAPSULE_R) is None]
            if ok:
                nodes[(i, j)] = sorted(ok)

    def to_cell(x, y):
        return (min(nx - 1, max(0, int((x - bx0) / cell))), min(ny - 1, max(0, int((y - by0) / cell))))

    def node_at(x, y, z, tol=0.35):
        c = to_cell(x, y)
        best = None
        for k, h in enumerate(nodes.get(c, ())):
            if abs(h - z) <= tol and (best is None or abs(h - z) < abs(nodes[c][best] - z)):
                best = k
        return None if best is None else (c[0], c[1], best)

    def height(n):
        return nodes[(n[0], n[1])][n[2]]

    steps = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.4142), (1, -1, 1.4142),
             (-1, 1, 1.4142), (-1, -1, 1.4142)]
    STEP = L.STEP_HEIGHT

    def near_h(c, h):
        return any(abs(h2 - h) <= STEP for h2 in nodes.get(c, ()))

    adj = {}
    for (i, j), hs in nodes.items():
        for k, h in enumerate(hs):
            out = []
            for (di, dj, w) in steps:
                c2 = (i + di, j + dj)
                hs2 = nodes.get(c2)
                if not hs2:
                    continue
                for k2, h2 in enumerate(hs2):
                    dh = h2 - h
                    if abs(dh) <= STEP or -MAX_DROP <= dh < -STEP:
                        if di and dj and not (near_h((i + di, j), h) or near_h((i + di, j), h2)) or \
                                di and dj and not (near_h((i, j + dj), h) or near_h((i, j + dj), h2)):
                            continue
                        out.append(((c2[0], c2[1], k2), w * cell + abs(dh)))
            adj[(i, j, k)] = out
    radj = {}
    for n, outs in adj.items():
        for n2, w in outs:
            radj.setdefault(n2, []).append((n, w))

    def bfs(srcs):
        seen = set(srcs)
        q = deque(srcs)
        while q:
            n = q.popleft()
            for n2, _ in adj.get(n, ()):
                if n2 not in seen:
                    seen.add(n2)
                    q.append(n2)
        return seen

    def dijkstra_to(dst):
        import heapq
        dist = {dst: 0.0}
        pq = [(0.0, dst)]
        while pq:
            d, n = heapq.heappop(pq)
            if d > dist.get(n, 1e18):
                continue
            for n2, w in radj.get(n, ()):
                nd = d + w
                if nd < dist.get(n2, 1e18):
                    dist[n2] = nd
                    heapq.heappush(pq, (nd, n2))
        return dist

    def level_of(z):
        name = levels[0][0]
        for (lname, lz) in levels:
            if z >= lz - 0.6:
                name = lname
        return name

    starts = [it for it in items if it["t"] == "start"]
    objs = {it["letter"]: it for it in items if it["t"] == "objective"}
    teams = {"Blue": [], "Red": [], "None": []}
    for s in starts:
        teams.setdefault(s["team"], []).append(s)
    info.append("starts: Blue %d, Red %d, Neutral %d" % (len(teams["Blue"]), len(teams["Red"]), len(teams["None"])))
    per_level = {}
    for (c, hs) in nodes.items():
        for h in hs:
            per_level[level_of(h)] = per_level.get(level_of(h), 0) + 1
    info.append("walkable cells per level: " + ", ".join("%s %d" % (n, per_level.get(n, 0)) for n, _ in levels))

    # ---- starts ----
    start_node = {}
    for s in starts:
        x, y, z = s["p"]
        if not (bx0 + 0.4 <= x <= bx1 - 0.4 and by0 + 0.4 <= y <= by1 - 0.4):
            errors.append("start %s at (%.1f, %.1f) outside bounds" % (s["team"], x, y))
        f = blocked(x, y, z, 0.42)
        if f:
            errors.append("start %s at (%.1f, %.1f, %.1f) inside %s" % (s["team"], x, y, z, f["label"]))
        n = node_at(x, y, z)
        if n is None:
            errors.append("start %s at (%.1f, %.1f, %.1f) has no floor / headroom under it" % (s["team"], x, y, z))
        else:
            start_node[id(s)] = n
    for i in range(len(starts)):
        for j in range(i + 1, len(starts)):
            a, b = starts[i]["p"], starts[j]["p"]
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if d < 1.5 and abs(a[2] - b[2]) < 1.5:
                errors.append("starts too close (%.2f m) at (%.1f,%.1f)/(%.1f,%.1f)" % (d, a[0], a[1], b[0], b[1]))
    reach = {}
    for team in ("Blue", "Red", "None"):
        ss = [start_node[id(s)] for s in teams.get(team, []) if id(s) in start_node]
        if not ss:
            continue
        reach[team] = bfs(ss[:1])
        for s in teams[team]:
            n = start_node.get(id(s))
            if n is not None and n not in reach[team]:
                errors.append("%s start at (%.1f, %.1f, %.1f) not connected to its spawn group" % ((team,) + tuple(s["p"])))
        reach[team] = bfs(ss)

    exposure, cover_dist = [], []
    if m["kind"] == "match":
        if len(teams["Blue"]) < 10 or len(teams["Red"]) < 10:
            errors.append("needs >= 10 Blue and >= 10 Red starts")
        for letter in "ABC":
            o = objs.get(letter)
            if not o:
                errors.append("objective %s missing" % letter)
                continue
            x, y, z = o["p"]
            if not (bx0 <= x <= bx1 and by0 <= y <= by1):
                errors.append("objective %s outside bounds" % letter)
            f = blocked(x, y, z, 0.3)
            if f:
                errors.append("objective %s centre inside %s" % (letter, f["label"]))
            n = node_at(x, y, z)
            if n is None:
                errors.append("objective %s at (%.1f, %.1f, %.1f) has no floor under it" % (letter, x, y, z))
                continue
            dist = dijkstra_to(n)
            line = []
            for team in ("Blue", "Red"):
                if n not in reach.get(team, ()):
                    errors.append("objective %s not reachable from %s spawn" % (letter, team))
                    continue
                ds = [dist.get(start_node.get(id(s))) for s in teams[team]]
                ds = [d for d in ds if d is not None]
                if ds:
                    line.append("%s %.0f m" % (team, sum(ds) / len(ds)))
            info.append("walk to %s on %s (mean over starts): %s" % (letter, level_of(z), ", ".join(line)))
        bad = 0
        for a in teams["Blue"]:
            for b in teams["Red"]:
                if visible((a["p"][0], a["p"][1], a["p"][2] + L.EYE_HEIGHT), (b["p"][0], b["p"][1], b["p"][2] + L.EYE_HEIGHT)):
                    bad += 1
        if bad:
            errors.append("%d Blue<->Red spawn pairs have line of sight" % bad)
        both = reach.get("Blue", set()) | reach.get("Red", set())
        pts = [(bx0 + (i + 0.5) * cell, by0 + (j + 0.5) * cell, h) for (i, j), hs in nodes.items()
               if i % 4 == 1 and j % 4 == 1 for k, h in enumerate(hs) if (i, j, k) in both]
        for team in ("Blue", "Red"):
            ss = teams[team]
            if not ss:
                continue
            far_vis, worst = 0, 0.0
            for (x, y, h) in pts:
                dmin = min(math.dist((x, y, h), s["p"]) for s in ss)
                if dmin < 14.0:
                    continue
                for s in ss:
                    if visible((x, y, h + L.EYE_HEIGHT), (s["p"][0], s["p"][1], s["p"][2] + L.EYE_HEIGHT)):
                        exposure.append((x, y, h, team))
                        far_vis += 1
                        worst = max(worst, math.dist((x, y, h), s["p"]))
                        break
            info.append("%s spawn exposure: %d of %d points >= 14 m away see a start (farthest %.0f m)"
                        % (team, far_vis, len(pts), worst))
            if worst > 45.0:
                warns.append("%s spawn visible from %.0f m away" % (team, worst))
        for (x, y, h) in pts:
            best = 99.0
            for i in cidx.near(x, y, 10.0):
                v = cover[i]
                if v["z0"] < h + 0.5 and v["z1"] >= h + 0.9 and v["z0"] > h - 0.6:
                    best = min(best, rect_distance(L, x, y, {"c": v["c"], "h": v["ex"], "yaw": v["yaw"]}))
            cover_dist.append((x, y, h, best))
        ds = sorted(d for (_, _, _, d) in cover_dist)
        if ds:
            p50, p90, p98 = ds[len(ds) // 2], ds[int(len(ds) * 0.9)], ds[int(len(ds) * 0.98)]
            info.append("distance to nearest cover: median %.1f m, p90 %.1f m, p98 %.1f m, max %.1f m"
                        % (p50, p90, p98, ds[-1]))
            if p90 > 5.0:
                warns.append("cover too sparse (p90 %.1f m > 5 m, i.e. cover farther apart than ~10 m)" % p90)
        # bots: nav bounds must contain the playable area, every start and every objective (same rule as 2D maps)
        nav = L.nav_bounds(m) if hasattr(L, "nav_bounds") else m.get("nav")
        if not nav:
            errors.append("no 'nav' bounds: bots need a NavMeshBoundsVolume on match maps")
        else:
            vx0, vy0, vz0, vx1, vy1, vz1 = nav
            if vx0 > bx0 or vy0 > by0 or vx1 < bx1 or vy1 < by1:
                errors.append("nav bounds (%.1f, %.1f)-(%.1f, %.1f) do not cover the playable bounds" % (vx0, vy0, vx1, vy1))
            for it in items:
                if it["t"] in ("start", "objective"):
                    x, y, z = it["p"]
                    if not (vx0 <= x <= vx1 and vy0 <= y <= vy1 and vz0 <= z <= vz1 - 2.0):
                        errors.append("%s at (%.1f, %.1f, %.1f) outside the nav bounds" % (it["t"], x, y, z))
            info.append("nav bounds: %.0f x %.0f m, z %.1f..%.1f m" % (vx1 - vx0, vy1 - vy0, vz0, vz1))
    counts = {}
    for it in items:
        counts[it["t"]] = counts.get(it["t"], 0) + 1
    info.append("items: " + ", ".join("%s %d" % kv for kv in sorted(counts.items())))
    if plans:
        render_levels(L, m, levels, vols, surfs, nodes, cell, exposure, cover_dist, level_of)
    return errors, warns, info


def render_levels(L, m, levels, vols, surfs, nodes, cell, exposure, cover_dist, level_of):
    """One row per storey (top storey first): plan of what stands on that floor + cover-distance heat map."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Polygon, Circle, FancyArrow

    bx0, by0, bx1, by1 = m["bounds"]
    w, h = bx1 - bx0, by1 - by0
    rows = list(reversed(levels))
    fig, axes = plt.subplots(len(rows), 2, figsize=(22, 22 * (h / w) * 0.5 * len(rows) + 1.0), dpi=100)
    pad = 3.0

    def rect(v):
        return L.rect_corners({"c": v["c"], "h": v["ex"], "yaw": v["yaw"]})
    for r, (lname, lz) in enumerate(rows):
        nxt = [z for (_, z) in levels if z > lz + 0.5]
        ztop = min(nxt) if nxt else lz + 4.0
        ax, ax2 = axes[r][0], axes[r][1]
        for a in (ax, ax2):
            a.set_xlim(bx0 - pad, bx1 + pad)
            a.set_ylim(by1 + pad, by0 - pad)
            a.set_aspect("equal")
            a.set_facecolor("#3b3c40")
            a.grid(True, color="#ffffff14", lw=0.5)
            a.set_xticks(range(int(bx0 // 10 * 10), int(bx1) + 1, 10))
            a.set_yticks(range(int(by0 // 10 * 10), int(by1) + 1, 10))
        # floor: the walkable cells of this storey (light = at floor height, sand = ramps / steps)
        img = np.zeros((int(round(h / cell)), int(round(w / cell)), 4), np.float32)
        img2 = np.zeros_like(img)
        for (i, j), hs in nodes.items():
            for hh in hs:
                if level_of(hh) == lname and j < img.shape[0] and i < img.shape[1]:
                    img[j, i] = (0.85, 0.84, 0.8, 1.0) if abs(hh - lz) < 0.3 else (0.79, 0.71, 0.54, 1.0)
                    img2[j, i] = (0.91, 0.9, 0.88, 1.0)
        ax.imshow(img, extent=(bx0, bx1, by1, by0), interpolation="nearest", zorder=0.2)
        ax2.imshow(img2, extent=(bx0, bx1, by1, by0), interpolation="nearest", zorder=0.2)
        for s in surfs:
            if s.get("ramp") and lz - 0.5 <= s["z_lo"] < ztop - 0.5:
                (cx, cy), yaw = s["c"], math.radians(s["yaw"])
                L_ = s["h"][0] * 1.6
                ax.add_patch(FancyArrow(cx - math.cos(yaw) * L_ / 2, cy - math.sin(yaw) * L_ / 2, math.cos(yaw) * L_,
                                        math.sin(yaw) * L_, width=0.8, head_width=2.2, head_length=2.0, color="#8a6d3b"))
                ax.text(cx, cy + 3.0, "ramp %.1f -> %.1f m" % (s["z_lo"], s["z_hi"]), ha="center", fontsize=7, color="#5a4520")
        for v in sorted(vols, key=lambda v: v["z1"]):
            if v["kind"] == "blocker":
                if lz - 0.2 <= v["z0"] < lz + 2.0:
                    ax.add_patch(Polygon(rect(v), closed=True, fill=False, ec="#ff505090", lw=0.5, ls=":"))
                continue
            if not (v["z0"] < lz + 2.0 and v["z1"] > lz + L.STEP_HEIGHT and v["z0"] > lz - 0.6):
                continue
            if v["kind"] == "box" and v["z1"] - v["z0"] < 0.05:
                continue
            if not v["solid"]:
                ax.add_patch(Polygon(rect(v), closed=True, fill=False, ec="#9c8f6a", lw=0.5))
                continue
            top = v["z1"] - lz
            if v["kind"] == "ramp":
                fc = "#7a6a50" if "Wall" in v["label"] else "#b8a47c"
            elif not v["los"]:
                fc = "#c7b991"
            elif top >= L.EYE_HEIGHT:
                fc = "#2e2e30"
            elif top >= L.COVER_HEIGHT:
                fc = "#8c7b5a"
            else:
                fc = "#c2b38c"
            ax.add_patch(Polygon(rect(v), closed=True, fc=fc, ec="#00000060", lw=0.35))
            if v["solid"] and v["kind"] != "ramp" and top > 0.5:
                ax2.add_patch(Polygon(rect(v), closed=True, fc="#ffffff", ec="#00000080", lw=0.3))
        # heat map of cover distance for this storey
        pts = [(x, y, d) for (x, y, hh, d) in cover_dist if level_of(hh) == lname]
        if pts:
            xs = sorted(set(round(p[0], 2) for p in pts))
            ys = sorted(set(round(p[1], 2) for p in pts))
            grid = np.full((len(ys), len(xs)), np.nan)
            xi = {v: i for i, v in enumerate(xs)}
            yi = {v: i for i, v in enumerate(ys)}
            for (x, y, d) in pts:
                grid[yi[round(y, 2)], xi[round(x, 2)]] = d
            im = ax2.imshow(grid, extent=(xs[0] - 1, xs[-1] + 1, ys[-1] + 1, ys[0] - 1), cmap="magma_r", vmin=0, vmax=8,
                            interpolation="nearest", alpha=0.85, zorder=0.5)
            fig.colorbar(im, ax=ax2, fraction=0.025, pad=0.01, label="m to nearest cover")
        for (x, y, hh, team) in exposure:
            if level_of(hh) == lname:
                ax2.plot([x], [y], marker="o", ms=2.6, color="#1f5fd0" if team == "Blue" else "#d0301f", alpha=0.8)
        for it in m["items"]:
            t = it["t"]
            x, y, z = it["p"][0], it["p"][1], it["p"][2]
            if t in ("start", "objective") and level_of(z) != lname:
                continue
            if t == "objective":
                for a in (ax, ax2):
                    a.add_patch(Circle((x, y), it["radius"], fc="#f0b42a30", ec="#c48a00", lw=1.6))
                ax.text(x, y, it["letter"], ha="center", va="center", fontsize=16, weight="bold", color="#8a5a00")
            elif t == "start":
                col = {"Blue": "#1f5fd0", "Red": "#d0301f"}.get(it["team"], "#555555")
                a_ = math.radians(it["yaw"])
                tri = [(x + 0.9 * math.cos(a_), y + 0.9 * math.sin(a_)), (x + 0.55 * math.cos(a_ + 2.5), y + 0.55 * math.sin(a_ + 2.5)),
                       (x + 0.55 * math.cos(a_ - 2.5), y + 0.55 * math.sin(a_ - 2.5))]
                ax.add_patch(Polygon(tri, closed=True, fc=col, ec="white", lw=0.4))
                ax2.plot([x], [y], marker="^", ms=4, color=col)
            elif t == "light" and lz - 0.2 <= z < ztop:
                ax.plot([x], [y], marker="*", color="#f2c200", ms=4)
        ax.add_patch(Polygon([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)], closed=True, fill=False, ec="#d03030", lw=1.0))
        ax.set_title("%s  -  %s (floor %.1f m)  %.0f x %.0f m" % (m["name"], lname, lz, w, h), fontsize=11)
        ax2.set_title("%s: cover distance (dark = exposed) - dots: points >= 14 m out that see a spawn" % lname, fontsize=10)
    fig.tight_layout()
    os.makedirs(PLAN_DIR, exist_ok=True)
    out = os.path.join(PLAN_DIR, m["name"] + ".png")
    fig.savefig(out)
    plt.close(fig)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--maps", default="", help="comma separated map names (default: all)")
    ap.add_argument("--no-plans", action="store_true")
    a = ap.parse_args(argv)
    L = load_layouts()
    assets, materials = load_json_assets()
    print("layouts: %s" % LAYOUTS_PY)
    print("JSON assets: %d (%s), tileable materials: %d" % (len(assets), ", ".join(sorted(set(
        v["_Category"] for v in assets.values()))), len(materials)))
    names = [L.resolve_map_name(n) for n in a.maps.split(",") if n.strip()] or L.MAP_ORDER
    total_err = 0
    for n in names:
        m = L.get_map(n)
        errors, warns, info = analyse(L, m, assets, materials, plans=not a.no_plans)
        print("\n== %s ==" % m["name"])
        for s in info:
            print("   " + s)
        for s in warns:
            print("   WARN  " + s)
        for s in errors[:40]:
            print("   ERROR " + s)
        if len(errors) > 40:
            print("   ... %d more errors" % (len(errors) - 40))
        total_err += len(errors)
        if not a.no_plans:
            print("   plan -> %s" % os.path.join(PLAN_DIR, m["name"] + ".png"))
    print("\n%s: %d error(s)" % ("FAILED" if total_err else "OK", total_err))
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())
