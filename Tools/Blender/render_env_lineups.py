"""
Render-only: the Architecture and field-Props 3840x2160 lineups from the environment
generator's scratch checkpoints (ENV_SCRATCH/<Id>.blend, P_<Id>.blend), using the
generator's own lineup layout and studio.

    ENV_SCRATCH=/path/to/cache python Tools/Blender/render_env_lineups.py -- [architecture] [props]

The generator's camera fit (envlib.bl.camera_fit) under-estimates the distance needed for
points nearer than the target (it adds the depth offset instead of subtracting it), which
crops the front row of a wide lineup.  This script swaps in a corrected fit for its own
run only; the generator files are not modified.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, "environment")
sys.path.insert(0, ENV)
sys.path.insert(0, os.path.join(HERE, "common"))

import bpy  # noqa: E402,F401,I001
from mathutils import Vector  # noqa: E402

from envlib import bl  # noqa: E402


def camera_fit(corners, az_deg=-38.0, el_deg=18.0, lens=60.0, margin=1.08, target=None, shift_z=0.0):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("Cam")
    cd.lens = lens
    cd.sensor_fit = "HORIZONTAL"
    cd.sensor_width = 36.0
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    pts = [Vector(p) for p in corners]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    az, el = math.radians(az_deg), math.radians(el_deg)
    back = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
    fwd = -back
    right = fwd.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(fwd).normalized()
    W, H = sc.render.resolution_x, sc.render.resolution_y
    th = 18.0 / lens / margin
    tv = 18.0 / lens * H / W / margin
    tgt = Vector(target) if target else (lo + hi) / 2
    # centre the projected extents (a few fixed-point iterations), then fit the distance
    d = (hi - lo).length * 2.0
    for _ in range(6):
        xs, ys = [], []
        for p in pts:
            q = p - (tgt - fwd * d)
            depth = q.dot(fwd)
            xs.append(q.dot(right) / depth)
            ys.append(q.dot(up) / depth)
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        tgt = tgt + right * cx * d + up * cy * d
        need = 0.0
        for p in pts:
            q = p - tgt
            a, b, f = q.dot(right), q.dot(up), q.dot(fwd)
            need = max(need, abs(a) / th - f, abs(b) / tv - f)
        d = need
    cam.location = tgt - fwd * d
    cam.rotation_euler = fwd.to_track_quat("-Z", "Y").to_euler()
    cd.clip_start = max(0.01, d * 0.01)
    cd.clip_end = d * 50
    return cam, tgt, d


bl.camera_fit = camera_fit

import architecture  # noqa: E402
import props  # noqa: E402

ARCH_ROWS = [
    ["Post_Timber", "Ladder_Metal_4m", "Wall_Plywood_2m", "Wall_Plywood_4m", "Wall_Plywood_Door_4m", "Wall_Plywood_Window_4m", "Wall_Concrete_4m"],
    ["Platform_Timber_4m", "Roof_Corrugated_4m", "NettingFence_4m", "Container_20ft", "SpawnTent"],
    ["Bunker_Logs", "Watchtower", "FloodlightTower"],
]
PROP_ROWS = [
    ["Tire", "TireStack", "OilDrum", "Crate_Ammo", "Crate_Wood", "Pallet", "PalletStack", "HayBale_Square", "Rock_B"],
    ["SteelTarget", "ChronoTable", "HayBale_Round", "CableSpool", "Rock_A", "SandbagCorner", "FlagPole_Objective"],
    ["SandbagWall_3m", "Barricade_Plywood_3m", "Barricade_Plywood_4m", "WreckedCar", "Bush_A"],
    ["Tree_Oak_B", "Tree_Oak_A", "Tree_Oak_C"],
]


def lineup(rows, cat, prefix="", spacing=0.6, az=-35.0, el=24.0, lens=50.0):
    """Rows front (nearest the camera) to back, each centred, every asset on the floor."""
    bl.reset()
    scratch = architecture.SCRATCH
    placed = []
    row_x = 0.0
    for row in rows:
        groups = []
        for aid in row:
            path = os.path.join(scratch, prefix + aid + ".blend")
            if not os.path.exists(path):
                print("missing checkpoint", path, flush=True)
                continue
            with bpy.data.libraries.load(path, link=False) as (src, dst):
                dst.objects = [n for n in src.objects if not (n.startswith("Cam") or n in ("Key", "Fill", "Rim", "Cyc"))]
            g = [o for o in dst.objects if o is not None and o.type == "MESH" and not o.name.startswith("Cyc")]
            for o in g:
                bpy.context.scene.collection.objects.link(o)
            bpy.context.view_layer.update()
            pts = bl.bbox_world(g)
            lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
            hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
            groups.append((g, lo, hi))
        if not groups:
            continue
        depth = max(hi.x - lo.x for _, lo, hi in groups)
        total = sum(hi.y - lo.y for _, lo, hi in groups) + spacing * (len(groups) - 1)
        y = total / 2
        for g, lo, hi in groups:
            w = hi.y - lo.y
            off = Vector((row_x - depth / 2 - (lo.x + hi.x) / 2, y - w / 2 - (lo.y + hi.y) / 2, -lo.z))
            for o in g:
                o.location = o.location + off
            placed += g
            y -= w + spacing
        row_x -= depth + spacing * 1.5
    bpy.context.view_layer.update()
    pts = bl.bbox_world(placed)
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2
    for o in placed:
        o.location.x -= c.x
        o.location.y -= c.y
    bpy.context.view_layer.update()
    bl.product_shot(placed, os.path.join(bl.RENDERS, cat, "_Lineup_4K.png"), az=az, el=el, lens=lens, samples=16, margin=1.04, w=3840, h=2160, tex_limit="1024")


def main(argv):
    which = [a for a in argv if not a.startswith("--")] or ["architecture", "props"]
    if "architecture" in which:
        lineup(ARCH_ROWS, "Architecture", spacing=1.0, el=24.0)
    if "props" in which:
        architecture.SCRATCH = props.SCRATCH
        lineup(PROP_ROWS, "Props", prefix="P_", spacing=0.6, el=26.0)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--" in a:
        a = a[a.index("--") + 1 :]
    main(a)
