"""Tileable PBR material library -> SourceAssets/Materials/<Id>/T_<Id>_BC|N|ORM(|H|Opacity).png

usage: python materials.py [--res 4096|2048|1024] [--no-render] [-- Id Id ...]

Textures are synthesised with periodic (FFT / wrapped-cellular) procedural
noise so every map tiles seamlessly; normals and AO are derived from a height
field in metres (resolution independent). Normals are DirectX (green = -Y).
ORM = AO, roughness, metallic (linear). Heights are 16-bit, 0..1 over
"HeightRangeM" metres.
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from envlib import tex  # noqa: E402
from mat_defs import GEN, SPECS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
MATDIR = os.path.join(ROOT, 'SourceAssets', 'Materials')


def build(mid, res):
    tile, seed, want_h = SPECS[mid]
    t0 = time.time()
    ctx = tex.Ctx(res, tile, seed)
    d = GEN[mid](ctx)
    n = res
    bc = np.clip(np.asarray(d['bc'], np.float32), 0, 1)
    h = np.asarray(d['h'], np.float32)
    if h.ndim == 0:
        h = np.zeros((n, n), np.float32)
    rough = np.clip(np.broadcast_to(np.asarray(d['rough'], np.float32), (n, n)), 0.02, 1)
    metal = np.clip(np.broadcast_to(np.asarray(d.get('metal', 0.0), np.float32), (n, n)), 0, 1)
    nrm = tex.height_to_normal(h, tile, d.get('nstr', 1.0))
    ao = tex.cavity_ao(h, tile, d.get('aor', (0.004, 0.015)), d.get('aog', 1.0))
    if 'ao' in d:
        ao = ao * d['ao']
    # bake cavity into the base colour slightly (as photo-sourced textures do)
    bc = bc * (0.55 + 0.45 * ao)[..., None]
    out = os.path.join(MATDIR, mid)
    os.makedirs(out, exist_ok=True)
    pre = os.path.join(out, 'T_%s_' % mid)
    tex.save_png(pre + 'BC.png', bc)
    tex.save_png(pre + 'N.png', nrm)
    tex.save_png(pre + 'ORM.png', np.stack([ao, rough, metal], -1))
    entry = {
        'TileMeters': tile,
        'BC': 'Materials/%s/T_%s_BC.png' % (mid, mid),
        'N': 'Materials/%s/T_%s_N.png' % (mid, mid),
        'ORM': 'Materials/%s/T_%s_ORM.png' % (mid, mid),
        'H': None,
        'Opacity': None,
        'Resolution': res,
        'ArchUVScale': round(2.0 / tile, 5),
    }
    hp = pre + 'H.png'
    if want_h:
        lo, hi = float(h.min()), float(h.max())
        tex.save_png(hp, (h - lo) / max(hi - lo, 1e-9), bits=16)
        entry['H'] = 'Materials/%s/T_%s_H.png' % (mid, mid)
        entry['HeightRangeM'] = round(hi - lo, 5)
    elif os.path.exists(hp):
        os.remove(hp)
    if 'op' in d:
        tex.save_png(pre + 'Opacity.png', np.clip(d['op'], 0, 1))
        entry['Opacity'] = 'Materials/%s/T_%s_Opacity.png' % (mid, mid)
        entry['BlendMode'] = 'Masked'
    print('  %-15s %4d  %.1fs' % (mid, res, time.time() - t0), flush=True)
    return entry


def write_json(entries):
    path = os.path.join(ROOT, 'Content', 'Airsoft', 'Data', 'Materials.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d = {'Version': 1, 'Materials': {}}
    if os.path.exists(path):
        try:
            d = json.load(open(path))
        except Exception:
            pass
    d.setdefault('Materials', {}).update(entries)
    d['Materials'] = dict(sorted(d['Materials'].items()))
    d['Notes'] = ('Paths relative to SourceAssets/. Tileable, seamless. N is DirectX. ORM = AO/Roughness/Metallic '
                  '(linear). Wood grain/brushing runs along U. TileMeters = real-world size of one texture tile; '
                  'architecture UVs are 1 UV = 2 m, so use UV tiling ArchUVScale = 2/TileMeters. '
                  'H is 16-bit, 0..1 spans HeightRangeM metres.')
    with open(path, 'w') as f:
        json.dump(d, f, indent=2)
        f.write('\n')


def render_lineup(ids):
    import bpy
    import bmesh
    from envlib import bl
    bl.reset()
    cols = 7
    size = 1.2
    gap = 0.35
    objs = []
    order = list(SPECS.keys())
    rows = int(math.ceil(len(order) / cols))
    for i, mid in enumerate(order):
        if not os.path.exists(os.path.join(MATDIR, mid, 'T_%s_BC.png' % mid)):
            continue
        r = i // cols
        c = i % cols
        x0 = (r - (rows - 1) / 2) * -(size + gap + 0.25)
        y0 = (c - (cols - 1) / 2) * (size + gap)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= size
            v.co.y *= size
            v.co.z = (v.co.z + 0.5) * 0.06
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.015, segments=3, profile=0.5, affect='EDGES',
                        clamp_overlap=True)
        uvl = bm.loops.layers.uv.new('UVMap')
        for f in bm.faces:
            for lp in f.loops:
                lp[uvl].uv = (lp.vert.co.x + 5.0, lp.vert.co.y + 5.0)
        me = bpy.data.meshes.new(mid)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=math.radians(50))
        o = bpy.data.objects.new('Swatch_' + mid, me)
        bpy.context.scene.collection.objects.link(o)
        o.location = (x0, y0, 0)
        tile = SPECS[mid][0]
        me.materials.append(bl.lib_material(mid, uv_scale=1.0 / tile))
        objs.append(o)
        # label
        cu = bpy.data.curves.new('Label_' + mid, 'FONT')
        cu.body = '%s  (%.1f m)' % (mid, tile)
        cu.size = 0.13
        cu.align_x = 'CENTER'
        t = bpy.data.objects.new('Label_' + mid, cu)
        bpy.context.scene.collection.objects.link(t)
        t.location = (x0 + size / 2 + 0.2, y0, 0.002)
        t.rotation_euler = (0, 0, math.radians(90))
        lm = bl.simple_material('LabelMat', (0.03, 0.03, 0.03), 0.6)
        cu.materials.append(lm)
    bl.cycles_setup(10, 3840, 2160, '1024')
    bpy.context.view_layer.update()
    pts = bl.bbox_world(objs)
    cam, tgt, d = bl.camera_fit(pts, az_deg=0.0, el_deg=58.0, lens=50, margin=1.04)
    from mathutils import Vector
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), 0))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), 0))
    bl.studio((lo + hi) / 2, (hi - lo).length / 2 * 0.6, az_deg=0.0, floor_z=-0.001, key=1.0,
              cyc_color=(0.55, 0.55, 0.53))
    bl.render_to(os.path.join(bl.RENDERS, 'Materials', '_Lineup_4K.png'))


def refresh_json():
    """Rebuild Materials.json entries from the files on disk (keeps HeightRangeM)."""
    import struct
    path = os.path.join(ROOT, 'Content', 'Airsoft', 'Data', 'Materials.json')
    old = json.load(open(path)).get('Materials', {}) if os.path.exists(path) else {}
    ents = {}
    for mid, (tile, seed, want_h) in SPECS.items():
        pre = os.path.join(MATDIR, mid, 'T_%s_' % mid)
        if not os.path.exists(pre + 'BC.png'):
            continue
        with open(pre + 'BC.png', 'rb') as f:
            f.read(16)
            w = struct.unpack('>I', f.read(4))[0]
        e = dict(old.get(mid, {}))
        e.update({'TileMeters': tile, 'BC': 'Materials/%s/T_%s_BC.png' % (mid, mid),
                  'N': 'Materials/%s/T_%s_N.png' % (mid, mid), 'ORM': 'Materials/%s/T_%s_ORM.png' % (mid, mid),
                  'H': ('Materials/%s/T_%s_H.png' % (mid, mid)) if os.path.exists(pre + 'H.png') else None,
                  'Opacity': ('Materials/%s/T_%s_Opacity.png' % (mid, mid)) if os.path.exists(pre + 'Opacity.png') else None,
                  'Resolution': w, 'ArchUVScale': round(2.0 / tile, 5)})
        ents[mid] = e
    write_json(ents)


def main():
    from envlib.bl import parse_args
    if '--json-only' in sys.argv:
        refresh_json()
        return
    o = parse_args()
    ids = o['ids'] or list(SPECS.keys())
    if not o['lineup_only']:
        for mid in ids:
            write_json({mid: build(mid, o['res'])})  # incremental, survives interruption
    if o['render']:
        render_lineup(ids)


if __name__ == '__main__':
    main()
