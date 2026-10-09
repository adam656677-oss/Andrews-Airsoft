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
    no enemy-spawn -> spawn sight lines, spawn exposure and cover-spacing stats
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
