"""Replace procedural tileable materials with CC0 photo-scanned PBR sets (Poly Haven, ambientCG).

    python3 -I Tools/Textures/fetch_cc0.py --work /some/empty/scratch/dir            # every row of TABLE
    python3 -I Tools/Textures/fetch_cc0.py --work DIR Asphalt AsphaltWet              # just these materials
    python3 -I Tools/Textures/fetch_cc0.py --list                                     # print the table
    flags: --res N (cap the output size, e.g. 1024 for a quick preview), --keep (keep the raw downloads),
           --no-json (don't touch Materials.json / Docs/CREDITS.md)

What it does, per row of TABLE (deterministic: same asset ids, same resolutions, same maths):
  1. Checks the licence on the asset's own page (Poly Haven: "CC0 1.0 Universal" in the page's licence
     metadata; ambientCG: "Creative Commons CC0" on the asset page) and refuses anything else.
  2. Downloads the maps into a new, empty directory <work>/<source>_<asset>/ (Poly Haven: single PNG maps,
     md5-checked against the API; ambientCG: the PNG zip, from which only the image maps are extracted).
     Downloads are treated as data: only decoded as images, never executed or imported.
  3. Converts to the project's format (Tools/Blender/CONVENTIONS.md, Materials.json):
       T_<Id>_BC.png   sRGB base colour            T_<Id>_N.png   DirectX normal (green = -Y)
       T_<Id>_ORM.png  R = AO, G = roughness, B = metallic (linear)
       T_<Id>_H.png    16-bit height (only for the materials that had one), 0..1 over HeightRangeM
     The normal map is cross-checked against the displacement map (sign of the slope correlation), so a
     mislabelled OpenGL map is caught and flipped. Optional per-row steps: rotate (wood grain / bark grooves
     run along U), repeat n x n inside one tile, colour-match the scan's linear mean to the game's
     art-directed albedo (the lighting presets were tuned against it), retarget roughness, and the
     procedural layers the game relies on (wet asphalt puddles, parking-deck joints / oil / tyre wear,
     the club carpet's printed pattern), which are generated with the same code and seeds as before
     (Tools/Blender/environment/mat_defs.py).
  4. Updates Content/Airsoft/Data/Materials.json (TileMeters = the scan's real-world size x repeat, plus a
     "Source" record) and the CC0 table in Docs/CREDITS.md, then deletes the raw downloads.

The procedural generator (Tools/Blender/environment/materials.py) still works; it skips scanned materials
unless their ids are passed explicitly.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ENV = os.path.join(ROOT, 'Tools', 'Blender', 'environment')
sys.path.insert(0, ENV)

from envlib import tex
from envlib.tex import F32, col, cover, lerp

MATDIR = os.path.join(ROOT, 'SourceAssets', 'Materials')
JSON_PATH = os.path.join(ROOT, 'Content', 'Airsoft', 'Data', 'Materials.json')
CREDITS = os.path.join(ROOT, 'Docs', 'CREDITS.md')
UA = {'User-Agent': 'AndrewsAirsoft-cc0-fetch/1.0 (+https://github.com)'}
Image.MAX_IMAGE_PIXELS = 300_000_000

# ------------------------------------------------------------------------------------------------
# The table. size = real-world width of the scan in metres (Poly Haven: the API's "dimensions";
# ambientCG: its dimensionX, or an estimate where the API gives none - marked "est.").
#   rep      the scan repeats rep x rep times inside one tile (TileMeters = size * rep)
#   res      output resolution; dl = download resolution ('4k' / '2k')
#   rot      quarter turns counter-clockwise (wood grain / bark grooves along U, as mat_defs.py)
#   match    (mode, target sRGB mean, strength): 'lum' scales luminance only, 'rgb' per channel, in linear
#            light, towards the procedural texture's mean (the art-directed albedo); desat greys the scan first
#   flatten  (metres, amount): divide out the scan's colour blotches larger than this (anti-repetition)
#   rough    (target mean, contrast) for the roughness channel; None keeps the scan's
#   metal    'scan' keeps the scan's metalness map (metals only); default 0 (dielectric); a float overrides
#   height   export T_<Id>_H.png with this HeightRangeM (only materials that had a height map)
#   special  procedural layer kept from the old generator: asphalt_wet, garage, garage_wet, carpet
# ------------------------------------------------------------------------------------------------
TABLE = {
    # streets (Neon / Velvet Club): an even, dense-graded road surface - no single crack to repeat every
    # tile (asphalt_02's crack read as stripes once tiled); the wet variant keeps the old puddle mask
    'Asphalt': dict(src='ph', asset='clean_asphalt', size=2.1, match=('lum', (0.335, 0.323, 0.304), 1.0),
                    height=0.008),
    'AsphaltWet': dict(src='ph', asset='clean_asphalt', size=2.1, rep=2,   # 4.2 m: puddles repeat less often
                       match=('lum', (0.335, 0.323, 0.304), 1.0), special='asphalt_wet'),
    # cast concrete walls (form-panel lines), sealed floors, broom-finished parking decks
    'Concrete': dict(src='ph', asset='concrete_wall_008', size=2.71, match=('rgb', (0.555, 0.546, 0.523), 1.0)),
    'ConcreteFloor': dict(src='ph', asset='concrete_floor_worn_001', size=3.0,
                          match=('rgb', (0.618, 0.609, 0.577), 0.8), rough=(0.42, 0.8)),
    'ConcreteGarage': dict(src='ph', asset='brushed_concrete', size=2.5, rep=2, special='garage',
                           match=('rgb', (0.519, 0.511, 0.487), 1.0), flatten=(0.25, 0.85)),
    'ConcreteGarageWet': dict(src='ph', asset='brushed_concrete', size=2.5, rep=2, special='garage_wet',
                              match=('rgb', (0.519, 0.511, 0.487), 1.0), flatten=(0.25, 0.85)),
    # brick facades
    'Brick': dict(src='ph', asset='red_brick', size=1.4, match=('lum', (0.487, 0.283, 0.221), 0.7), height=0.01),
    'BrickDark': dict(src='ph', asset='brick_wall_001', size=3.0, match=('lum', (0.268, 0.215, 0.196), 0.8)),
    # wood
    'Plywood': dict(src='ph', asset='oak_veneer_01', size=1.83, rot=1, match=('rgb', (0.727, 0.610, 0.459), 0.9),
                    rough=(0.74, 0.8)),
    'OSB': dict(src='ph', asset='oriented_strand_board', size=2.51, match=('rgb', (0.613, 0.480, 0.307), 0.6)),
    'Timber': dict(src='acg', asset='Wood062', size=0.5, size_note='est. from grain/pores; API gives none',
                   match=('rgb', (0.555, 0.485, 0.392), 0.6), rough=(0.82, 0.9)),
    'Walnut': dict(src='ph', asset='walnut_veneer', size=1.8, rot=1, match=('rgb', (0.383, 0.252, 0.164), 0.9),
                   rough=(0.36, 0.7)),   # finished walnut (bar tops, furniture); 1.8 m of figure, few repeats
    # club interior
    'Carpet': dict(src='acg', asset='Carpet016', size=1.7, special='carpet', rough=(0.93, 0.6)),
    'Velvet': dict(src='ph', asset='velour_velvet', size=0.279, res=2048, dl='2k',
                   match=('rgb', (0.375, 0.074, 0.128), 1.0)),
    'Leather': dict(src='ph', asset='brown_leather', size=0.4, res=2048, dl='2k',
                    match=('rgb', (0.250, 0.154, 0.098), 0.8)),
    # field gear
    'Burlap': dict(src='ph', asset='hessian_230', size=0.268, res=2048, dl='2k',
                   match=('rgb', (0.501, 0.413, 0.275), 0.5)),
    'Canvas': dict(src='ph', asset='rough_linen', size=0.271, res=2048, dl='2k', desat=1.0,
                   match=('rgb', (0.331, 0.327, 0.216), 1.0)),
    # Ironwood ground
    'Grass': dict(src='ph', asset='leafy_grass', size=2.0, match=('rgb', (0.369, 0.380, 0.187), 0.5)),
    'Dirt': dict(src='ph', asset='dirt', size=2.0, match=('lum', (0.390, 0.313, 0.242), 0.7), height=0.04),
    'Mud': dict(src='ph', asset='brown_mud_02', size=1.3, match=('lum', (0.213, 0.160, 0.102), 0.6),
                rough=(0.5, 1.0), flatten=(0.1, 0.75)),
    'Gravel': dict(src='acg', asset='Gravel033', size=2.0, match=('lum', (0.430, 0.402, 0.359), 0.7), height=0.034),
    'ForestFloor': dict(src='ph', asset='dry_decay_leaves', size=2.0, match=('lum', (0.442, 0.302, 0.136), 0.6),
                        height=0.039),
    'Bark': dict(src='ph', asset='bark_willow', size=1.0, rot=1, match=('lum', (0.305, 0.281, 0.240), 0.7),
                 height=0.034),   # even furrows: no knot / moss band to repeat up the trunk
    # metal
    'PaintedSteel': dict(src='ph', asset='rusty_metal_sheet', size=2.0,   # paint (metal 0); tinted in game
                         match=('rgb', (0.385, 0.360, 0.298), 1.0), flatten=(0.08, 0.9), rough=(0.55, 0.8)),
    'DiamondPlate': dict(src='acg', asset='DiamondPlate009', size=0.84, metal=0.75,   # its metalness map is ~0
                         size_note='est.: 28 lug rows per scan (FFT) at the procedural plate\'s 30 mm pitch',
                         match=('rgb', (0.485, 0.483, 0.480), 0.8)),
    'CorrodedMetal': dict(src='ph', asset='rust_coarse_01', size=2.2, metal='scan',
                          match=('lum', (0.355, 0.244, 0.186), 0.7), flatten=(0.08, 0.9)),
}
# Not replaced (no CC0 photo scan that fits; see Docs/CREDITS.md): MarbleBlack, Brass, Rubber, Netting,
# Straw, Granite (baked into the rock props), PlywoodPainted, PaintLineWhite/Yellow.


# ------------------------------------------------------------------------------------------------
# network
# ------------------------------------------------------------------------------------------------
def http_get(url, dest=None, md5=None, size=None, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                if dest is None:
                    return r.read()
                h = hashlib.md5()
                with open(dest, 'wb') as f:
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                        h.update(b)
            if md5 and h.hexdigest() != md5:
                raise OSError('md5 mismatch for %s' % url)
            if size and os.path.getsize(dest) != size:
                raise OSError('truncated download %s (%d of %d bytes)' % (url, os.path.getsize(dest), size))
            return dest
        except Exception as e:  # network hiccups: retry with backoff
            last = e
            time.sleep(2 + 3 * i)
    raise OSError('download failed: %s (%s)' % (url, last))


def ph_page(aid):
    return 'https://polyhaven.com/a/%s' % aid


def acg_page(aid):
    return 'https://ambientcg.com/view?id=%s' % aid


def check_license(src, aid):
    """True only when the asset's own page states CC0."""
    if src == 'ph':
        html = http_get(ph_page(aid)).decode('utf-8', 'replace')
        return '"copyrightNotice":"CC0 1.0 Universal' in html
    html = http_get(acg_page(aid)).decode('utf-8', 'replace')
    return 'Creative Commons CC0' in html and aid.lower() in html.lower()


def fetch_ph(aid, dl, d, want_disp):
    info = json.loads(http_get('https://api.polyhaven.com/info/%s' % aid))
    files = json.loads(http_get('https://api.polyhaven.com/files/%s' % aid))
    out = {}
    for key, name in (('Diffuse', 'bc'), ('nor_dx', 'n'), ('arm', 'arm'), ('Displacement', 'disp')):
        if key not in files or dl not in files[key]:
            continue
        if name == 'disp' and not want_disp:
            continue
        f = files[key][dl]['png']
        p = os.path.join(d, name + '.png')
        http_get(f['url'], p, md5=f.get('md5'), size=f.get('size'))
        out[name] = p
    meta = {'authors': list(info.get('authors', {}).keys()), 'name': info.get('name', aid),
            'dims_mm': info.get('dimensions'), 'files_hash': info.get('files_hash')}
    return out, meta


def fetch_acg(aid, dl, d, want_disp):
    q = json.loads(http_get('https://ambientcg.com/api/v2/full_json?id=%s'
                            '&include=downloadData,dimensionsData,displayData' % aid))
    a = q['foundAssets'][0]
    att = dl.upper() + '-PNG'
    dls = a['downloadFolders']['default']['downloadFiletypeCategories']['zip']['downloads']
    z = [x for x in dls if x['attribute'] == att][0]
    zp = os.path.join(d, 'maps.zip')
    http_get(z['fullDownloadPath'], zp, size=z.get('size'))
    want = {'_Color.png': 'bc', '_NormalDX.png': 'n', '_Roughness.png': 'rough', '_AmbientOcclusion.png': 'ao',
            '_Metalness.png': 'metal', '_Displacement.png': 'disp'}
    out = {}
    with zipfile.ZipFile(zp) as zf:
        for info in zf.infolist():
            base = os.path.basename(info.filename)
            for suf, name in want.items():
                if base.endswith(suf) and info.file_size < 600_000_000:
                    p = os.path.join(d, name + '.png')      # our own file name, never the archive's path
                    with zf.open(info) as src, open(p, 'wb') as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                    out[name] = p
    os.remove(zp)
    meta = {'authors': ['ambientCG (Lennart Demes)'], 'name': a.get('displayName', aid),
            'dims_cm': [a.get('dimensionX'), a.get('dimensionY')], 'method': a.get('creationMethodName')}
    return out, meta


# ------------------------------------------------------------------------------------------------
# image helpers (float32, row 0 = top)
# ------------------------------------------------------------------------------------------------
def load(path, kind):
    im = Image.open(path)
    im.load()
    if kind == 'gray':
        if im.mode in ('I;16', 'I;16B', 'I', 'I;16L'):
            a = np.asarray(im, dtype=np.float64)
            return (a / (65535.0 if a.max() > 255 else 255.0)).astype(F32)
        if im.mode == 'F':
            return np.asarray(im, F32)
        return np.asarray(im.convert('L'), F32) / 255.0
    if im.mode in ('I;16', 'I;16B', 'I'):
        a = np.asarray(im, np.float64) / 65535.0
        return np.repeat(a[..., None], 3, -1).astype(F32)
    if im.mode == 'RGB' and getattr(im, 'bits', 8) == 16:   # 16-bit RGB comes back as 8-bit in PIL; fine
        pass
    return np.asarray(im.convert('RGB'), F32) / 255.0


def avg(a):
    return float(a.mean(dtype=np.float64))   # float64: a float32 mean over 16 M texels drifts by a few %


def lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((np.maximum(c, 0) + 0.055) / 1.055) ** 2.4).astype(F32)


def srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055).astype(F32)


def resize_wrap(a, n, m=None):
    """Resize a tileable image to n rows x m columns (default square; Lanczos) with wrap padding so the
    seams stay seamless."""
    m = n if m is None else m
    if a.ndim == 3:
        return np.stack([resize_wrap(a[..., i], n, m) for i in range(a.shape[2])], -1)
    h, w = a.shape
    if h == n and w == m:
        return a
    p = 16
    pad = np.pad(a, ((p, p), (p, p)), mode='wrap')
    sy, sx = n / h, m / w
    ph, pw = int(round((h + 2 * p) * sy)), int(round((w + 2 * p) * sx))
    big = np.asarray(Image.fromarray(pad.astype(F32), 'F').resize((pw, ph), Image.LANCZOS), F32)
    oy, ox = int(round(p * sy)), int(round(p * sx))
    return big[oy:oy + n, ox:ox + m]


def rot_img(a, k):
    return np.ascontiguousarray(np.rot90(a, k, axes=(0, 1))) if k % 4 else a


def rot_normal(nm, k):
    """Rotate a DX normal map k quarter turns CCW: image vector (x right, y down) -> (y, -x) per turn."""
    nm = rot_img(nm, k)
    x, y, z = nm[..., 0] * 2 - 1, nm[..., 1] * 2 - 1, nm[..., 2]
    for _ in range(k % 4):
        x, y = y, -x
    return np.stack([x * 0.5 + 0.5, y * 0.5 + 0.5, z], -1).astype(F32)


def renorm(nm, strength=1.0):
    x, y = (nm[..., 0] * 2 - 1) * strength, (nm[..., 1] * 2 - 1) * strength
    z = np.maximum(nm[..., 2] * 2 - 1, 0.02)
    ln = np.sqrt(x * x + y * y + z * z)
    return np.stack([x / ln * 0.5 + 0.5, y / ln * 0.5 + 0.5, z / ln * 0.5 + 0.5], -1).astype(F32)


def combine_normals(a, b):
    """UDN blend of two DX normal maps (detail b on base a)."""
    ax, ay, az = a[..., 0] * 2 - 1, a[..., 1] * 2 - 1, a[..., 2] * 2 - 1
    bx, by = b[..., 0] * 2 - 1, b[..., 1] * 2 - 1
    x, y, z = ax + bx, ay + by, np.maximum(az, 0.02)
    ln = np.sqrt(x * x + y * y + z * z)
    return np.stack([x / ln * 0.5 + 0.5, y / ln * 0.5 + 0.5, z / ln * 0.5 + 0.5], -1).astype(F32)


def normal_vs_height(nm, h):
    """Correlation of the normal's (x, y) slope with the height field's slope, band-passed at ~1/1000 to
    ~1/100 of the tile (where both maps carry the same detail). A DirectX map gives clearly negative
    values on both axes (n = -grad h, image y down); OpenGL flips y. Near 0 = the height map is too flat
    to tell."""
    s = max(1, min(nm.shape[:2]) // 1024)
    k = min(nm.shape[:2]) // s * s

    def box(a):   # block average down to ~1024 px (a plain stride would alias the fine detail)
        a = a[:k, :k]
        return a.reshape(k // s, s, k // s, s, *a.shape[2:]).mean((1, 3)).astype(F32)
    n2, h2 = box(nm), box(h)
    hb = tex.blur(h2, 1.5) - tex.blur(h2, 12.0)
    nb = tex.blur(n2, 1.5)
    gx = np.roll(hb, -1, 1) - np.roll(hb, 1, 1)
    gy = np.roll(hb, -1, 0) - np.roll(hb, 1, 0)
    cx = np.corrcoef(nb[..., 0].ravel(), gx.ravel())[0, 1]
    cy = np.corrcoef(nb[..., 1].ravel(), gy.ravel())[0, 1]
    return float(np.nan_to_num(cx)), float(np.nan_to_num(cy))


def color_match(bc, mode, target, strength, desat=0.0):
    """Scale the linear colour so its mean moves towards the target (sRGB triple)."""
    L = lin(bc)
    if desat:
        g = (L * np.array([0.2126, 0.7152, 0.0722], F32)).sum(-1, keepdims=True)
        L = lerp(L, np.repeat(g, 3, -1), desat)
    m = L.reshape(-1, 3).mean(0, dtype=np.float64).astype(F32)
    t = lin(np.array(target, F32))
    if mode == 'rgb':
        gain = (t / np.maximum(m, 1e-4)) ** strength
    else:
        w = np.array([0.2126, 0.7152, 0.0722], F32)
        gain = np.full(3, (float((t * w).sum()) / max(float((m * w).sum()), 1e-4)) ** strength, F32)
    return srgb(L * gain.astype(F32))


def retarget_rough(r, target, contrast):
    return np.clip(target + (r - avg(r)) * contrast, 0.03, 1.0).astype(F32)


# ------------------------------------------------------------------------------------------------
# procedural layers kept from the old generator (same code, same seeds -> same puddles / joints)
# ------------------------------------------------------------------------------------------------
def special_asphalt_wet(m, res, tile):
    import mat_defs
    ctx = tex.Ctx(res, tile, 16)                     # AsphaltWet's seed in mat_defs.SPECS
    mat_defs.asphalt_base(ctx)                       # same RNG sequence as m_AsphaltWet
    lowf = ctx.noise(1.0, oct=4, rough=0.5)
    puddle = cover(-lowf, 0.22, 0.05)
    damp = cover(-lowf, 0.65, 0.3)
    bc = m['bc'] * (0.62 - 0.08 * puddle)[..., None]
    bc = lerp(bc, col('#141618'), puddle * 0.25)
    # water held in the scan's own pores / crack network (fine cavities), wetter where damp
    h = m['h']
    cav = np.clip((tex.blur(h, res / tile * 0.004) - h) / max(float(h.std()), 1e-4) * 1.5, 0, 1)
    rough = m['rough'] * (1 - 0.55 * damp) * (1 - 0.35 * cav * (0.4 + 0.6 * damp))
    rough = np.clip(rough, 0.2, 1) * (1 - puddle) + 0.03 * puddle
    m['bc'], m['rough'] = bc, rough
    m['n'] = lerp(m['n'], np.broadcast_to(np.array([0.5, 0.5, 1.0], F32), m['n'].shape), puddle * 0.97)
    m['n'] = renorm(m['n'])


def _garage(m, res, tile, wet):
    import mat_defs
    ctx = tex.Ctx(res, tile, 42)                     # ConcreteGarage(Wet) seed in mat_defs.SPECS
    d = mat_defs.garage_deck(ctx)
    # the deck's art-directed layers (tyre paths, scuffs, oil, patch, cracks, saw-cut joints) as a
    # multiplier on the scan; the procedural speckle / broom noise is blurred out (the scan has the real one)
    base = col('#8f8d87')
    mod = lin(tex.blur(d['bc'], res / tile * 0.004)) / lin(base)
    mod = mod / mod.reshape(-1, 3).mean(0, dtype=np.float64).astype(F32)
    bc = srgb(lin(m['bc']) * mod)
    rough = np.clip(tex.blur(d['rough'], res / tile * 0.003) + (m['rough'] - avg(m['rough'])) * 0.8, 0.05, 1)
    # keep only the deck's crisp features in its normal (joints, cracks, patch edge), not its fake broom
    hfeat = -d['joint'] * 0.004 - d['crack'] * 0.0006
    pn = tex.height_to_normal(hfeat, tile, 1.6)
    m['n'] = combine_normals(m['n'], pn)
    m['ao'] = m['ao'] * tex.cavity_ao(hfeat, tile, (0.002, 0.008), 1.0)
    if wet:   # m_ConcreteGarageWet
        lowf = ctx.noise(1.9, oct=3, rough=0.45) - 0.5 * d['wheel']
        damp = cover(-lowf, 0.7, 0.35)
        bc = bc * (0.58 - 0.04 * damp)[..., None]
        jwet = np.clip(d['joint'] * 1.5 + d['crack'], 0, 1)
        bc = lerp(bc, col('#141414'), jwet * 0.4)
        rough = np.clip(rough * (1 - 0.6 * damp), 0.12, 1)
        rough = rough * (1 - 0.7 * jwet)
        rough = np.where(d['oil'] > 0.4, np.minimum(rough, 0.2), rough)
        m['n'] = renorm(m['n'], 0.8)              # a water film softens the broom texture
    m['bc'], m['rough'] = bc, rough


def special_garage(m, res, tile):
    _garage(m, res, tile, False)


def special_garage_wet(m, res, tile):
    _garage(m, res, tile, True)


def special_carpet(m, res, tile):
    """The club's printed diamond/medallion pattern (mat_defs.m_Carpet's design, ~25 cm motif) dyed into the
    scanned loop pile: pattern colour x the scan's pile luminance detail."""
    ctx = tex.Ctx(res, tile, 34)
    P = max(1, int(round(tile / 0.25)))
    x = (ctx.u * P) % 1 - 0.5
    y = (ctx.v * P) % 1 - 0.5
    sstep = tex.sstep
    dia = np.abs(x) + np.abs(y)
    gold_line = sstep(0.02, 0.008, np.abs(dia - 0.42)) + sstep(0.012, 0.004, np.abs(dia - 0.36))
    inner = sstep(0.26, 0.24, dia)
    r = np.sqrt(x * x + y * y)
    medal = sstep(0.09, 0.07, r) - sstep(0.05, 0.035, r)
    flor = sstep(0.04, 0.025, np.abs(np.abs(x) - np.abs(y))) * inner * (dia > 0.12)
    corner = sstep(0.05, 0.035, np.sqrt((np.abs(x) - 0.5) ** 2 + (np.abs(y) - 0.5) ** 2))
    pat = np.zeros((res, res, 3), F32) + col('#5a0f16')
    pat = lerp(pat, col('#3a0a10'), np.broadcast_to(inner, (res, res)) * 0.8)
    pat = lerp(pat, col('#b08a3a'), np.clip(np.broadcast_to(gold_line + medal + corner, (res, res)), 0, 1))
    pat = lerp(pat, col('#1a1210'), np.broadcast_to(flor, (res, res)) * 0.8)
    pat = tex.blur(pat, res / tile * 0.0008)       # dyed pile: soft pattern edges
    g = (lin(m['bc']) * np.array([0.2126, 0.7152, 0.0722], F32)).sum(-1)
    detail = g / np.maximum(tex.blur(g, res / tile * 0.05), 1e-4)
    detail = np.clip(detail, 0.3, 1.8) ** 1.8
    wear = cover(ctx.n01(0.4, oct=4), 0.3, 0.3)
    shade = 0.8 + 0.2 * np.clip(tex.blur(g, res / tile * 0.05) / avg(g), 0.6, 1.4)   # the pile's own soft mottling
    out = lin(pat) * (detail * shade)[..., None]
    out = lerp(out, out * 1.25 + 0.004, wear * 0.3)
    m['bc'] = srgb(out)


SPECIAL = {'asphalt_wet': special_asphalt_wet, 'garage': special_garage, 'garage_wet': special_garage_wet,
           'carpet': special_carpet}


# ------------------------------------------------------------------------------------------------
# conversion
# ------------------------------------------------------------------------------------------------
def load_maps(files):
    m = {'bc': load(files['bc'], 'rgb'), 'n': load(files['n'], 'rgb')}
    if 'arm' in files:
        arm = load(files['arm'], 'rgb')
        m['ao'], m['rough'], m['metal'] = arm[..., 0], arm[..., 1], arm[..., 2]
    else:
        m['rough'] = load(files['rough'], 'gray')
        m['ao'] = load(files['ao'], 'gray') if 'ao' in files else None
        m['metal'] = load(files['metal'], 'gray') if 'metal' in files else None
    m['disp'] = load(files['disp'], 'gray') if 'disp' in files else None
    h, w = m['bc'].shape[:2]
    for k in ('n', 'ao', 'rough', 'metal', 'disp'):   # some sets ship maps a pixel or two apart in size
        if m.get(k) is not None and m[k].shape[:2] != (h, w):
            m[k] = resize_wrap(m[k], h, w)
    return m


def convert(mid, spec, files, res_cap, log):
    res = min(spec.get('res', 4096), res_cap)
    rep = spec.get('rep', 1)
    tile = round(spec['size'] * rep, 4)
    rot = spec.get('rot', 0)
    m = load_maps(files)
    # orientation check on the raw scan: DirectX normal vs displacement slope
    if m['disp'] is not None:
        cx, cy = normal_vs_height(m['n'], m['disp'])
        notes = []
        for ch, c in ((0, cx), (1, cy)):       # an axis that clearly disagrees with the scan's height is flipped
            if c > 0.3:
                m['n'][..., ch] = 1 - m['n'][..., ch]
                notes.append('flipped %s' % 'RG'[ch])
        log('    normal/height slope correlation x=%.2f y=%.2f -> %s' % (
            cx, cy, ', '.join(notes) if notes else ('DirectX ok' if max(cx, cy) < -0.2 else 'height too flat to tell; '
                                                     'trusting the DirectX label')))
    # rotate (grain along U)
    if rot:
        for k in ('bc', 'ao', 'rough', 'metal', 'disp'):
            if m.get(k) is not None:
                m[k] = rot_img(m[k], rot)
        m['n'] = rot_normal(m['n'], rot)
    # resample: rep x rep copies of the scan in one res x res tile
    sub = res // rep
    for k in ('bc', 'n', 'ao', 'rough', 'metal', 'disp'):
        if m.get(k) is not None:
            a = resize_wrap(m[k], sub)
            m[k] = np.tile(a, (rep, rep, 1) if a.ndim == 3 else (rep, rep)) if rep > 1 else a
    m['n'] = renorm(m['n'], spec.get('nstr', 1.0))
    h = m['disp'] if m['disp'] is not None else None
    m['h'] = (h - avg(h)) * spec.get('height', 0.01) if h is not None else np.zeros((res, res), F32)
    if m['ao'] is None:
        m['ao'] = tex.cavity_ao(m['h'], tile, (0.002, 0.008, 0.02)) if h is not None else np.ones((res, res), F32)
    metal = spec.get('metal', 0.0)
    if metal == 'scan' and m['metal'] is not None:
        pass
    else:   # dielectrics: some fabric / mineral scans ship a stray metalness map
        m['metal'] = np.full((res, res), 0.0 if metal == 'scan' else float(metal), F32)
    if spec.get('match'):
        mode, target, strength = spec['match']
        m['bc'] = color_match(m['bc'], mode, target, strength, spec.get('desat', 0.0))
    elif spec.get('desat'):
        m['bc'] = color_match(m['bc'], 'lum', (0.5, 0.5, 0.5), 0.0, spec['desat'])
    if spec.get('flatten'):   # take out the scan's own blotches (they repeat with it); keep the fine detail
        size_m, amount = spec['flatten']
        L = lin(m['bc'])
        low = tex.blur(L, res / tile * size_m)
        m['bc'] = srgb(L * (L.reshape(-1, 3).mean(0, dtype=np.float64).astype(F32) / np.maximum(low, 1e-4)) ** amount)
    if spec.get('rough'):
        m['rough'] = retarget_rough(m['rough'], *spec['rough'])
    # re-check the normal against the height after rotation / repeat (must still be DirectX)
    if m['disp'] is not None:
        cx, cy = normal_vs_height(m['n'], m['disp'])
        log('    converted slope correlation x=%.2f y=%.2f' % (cx, cy))
        if max(cx, cy) > 0.3:
            raise RuntimeError('%s: normal map does not match its height field after conversion' % mid)
    if spec.get('special'):
        SPECIAL[spec['special']](m, res, tile)
    out = os.path.join(MATDIR, mid)
    os.makedirs(out, exist_ok=True)
    pre = os.path.join(out, 'T_%s_' % mid)
    tex.save_png(pre + 'BC.png', np.clip(m['bc'], 0, 1))
    tex.save_png(pre + 'N.png', m['n'])
    tex.save_png(pre + 'ORM.png', np.stack([m['ao'], np.clip(m['rough'], 0.02, 1), m['metal']], -1))
    entry = {'TileMeters': tile, 'BC': 'Materials/%s/T_%s_BC.png' % (mid, mid),
             'N': 'Materials/%s/T_%s_N.png' % (mid, mid), 'ORM': 'Materials/%s/T_%s_ORM.png' % (mid, mid),
             'H': None, 'Opacity': None, 'Resolution': res, 'ArchUVScale': round(2.0 / tile, 5)}
    hp = pre + 'H.png'
    if spec.get('height') and h is not None:
        lo, hi = float(h.min()), float(h.max())
        tex.save_png(hp, (h - lo) / max(hi - lo, 1e-9), bits=16)
        entry['H'] = 'Materials/%s/T_%s_H.png' % (mid, mid)
        entry['HeightRangeM'] = spec['height']
    elif os.path.exists(hp):
        os.remove(hp)
    for stale in ('Opacity',):
        if os.path.exists(pre + stale + '.png'):
            os.remove(pre + stale + '.png')
    lm = srgb(lin(np.clip(m['bc'], 0, 1)).reshape(-1, 3).mean(0, dtype=np.float64).astype(F32))
    log('    -> %s %dpx tile %.3f m  mean BC (%.3f %.3f %.3f) rough %.2f metal %.2f ao %.2f'
        % (mid, res, tile, lm[0], lm[1], lm[2], avg(m['rough']), avg(m['metal']), avg(m['ao'])))
    return entry


def source_record(spec, meta):
    src, aid = spec['src'], spec['asset']
    rec = {'Site': 'Poly Haven' if src == 'ph' else 'ambientCG', 'Asset': aid,
           'Name': str(meta.get('name', aid)).strip(),
           'Url': ph_page(aid) if src == 'ph' else acg_page(aid), 'Authors': meta.get('authors', []),
           'License': 'CC0 1.0', 'ScanMeters': spec['size'], 'Repeat': spec.get('rep', 1),
           'Download': spec.get('dl', '4k')}
    if spec.get('size_note'):
        rec['ScanMetersNote'] = spec['size_note']
    if spec.get('special'):
        rec['ProceduralLayers'] = spec['special']
    return rec


# ------------------------------------------------------------------------------------------------
# JSON + credits
# ------------------------------------------------------------------------------------------------
def read_text(path, default=''):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return f.read()


def write_json(entries):
    d = json.loads(read_text(JSON_PATH, '{"Version": 1, "Materials": {}}'))
    d.setdefault('Materials', {}).update(entries)
    d['Materials'] = dict(sorted(d['Materials'].items()))
    with open(JSON_PATH, 'w') as f:
        json.dump(d, f, indent=2)
        f.write('\n')


BEGIN = '<!-- cc0-textures:begin (generated by Tools/Textures/fetch_cc0.py) -->'
END = '<!-- cc0-textures:end -->'


def write_credits():
    mats = json.loads(read_text(JSON_PATH, '{}')).get('Materials', {})
    rows = []
    for mid in sorted(mats):
        s = mats[mid].get('Source')
        if not s:
            continue
        size = '%.2f m' % s['ScanMeters'] + (' (est.)' if s.get('ScanMetersNote') else '')
        rows.append('| %s | [%s](%s) | %s | %s | %s | CC0 1.0 |' % (
            mid, s['Name'], s['Url'], s['Site'], ', '.join(s.get('Authors') or ['-']), size))
    block = '\n'.join([
        BEGIN,
        '### Tileable surface materials (photo-scanned, CC0)',
        '',
        'All are released under [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/) '
        '(public domain); attribution is not required but given gladly. Converted to the project format '
        '(DirectX normals, packed ORM, colour-matched to the game palette) by `Tools/Textures/fetch_cc0.py`.',
        '',
        '| Material | Source asset | Site | Author(s) | Scan size | Licence |',
        '|---|---|---|---|---|---|',
    ] + rows + [END])
    text = read_text(CREDITS, '# Credits\n\n')
    if BEGIN in text and END in text:
        a, b = text.index(BEGIN), text.index(END) + len(END)
        text = text[:a] + block + text[b:]
    else:
        text = text.rstrip('\n') + '\n\n' + block + '\n'
    with open(CREDITS, 'w') as f:
        f.write(text if text.endswith('\n') else text + '\n')


# ------------------------------------------------------------------------------------------------
def main(argv):
    flags = [a for a in argv if a.startswith('--')]
    vals = {}
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--work', '--res'):
            vals[a] = argv[i + 1]
            i += 2
            continue
        if not a.startswith('--'):
            rest.append(a)
        i += 1
    if '--list' in flags:
        for mid, s in TABLE.items():
            print('%-18s %-4s %-24s %5.2f m x%d -> tile %5.2f m  %s %dpx%s' % (
                mid, s['src'], s['asset'], s['size'], s.get('rep', 1), s['size'] * s.get('rep', 1),
                s.get('dl', '4k'), s.get('res', 4096), ('  +' + s['special']) if s.get('special') else ''))
        return
    ids = rest or list(TABLE)
    bad = [m for m in ids if m not in TABLE]
    if bad:
        raise SystemExit('not in TABLE: %s' % ', '.join(bad))
    res_cap = int(vals.get('--res', 4096))
    work = vals.get('--work') or tempfile.mkdtemp(prefix='cc0_')
    os.makedirs(work, exist_ok=True)

    def log(s):
        print(s, flush=True)

    by_asset = {}
    for mid in ids:
        s = TABLE[mid]
        by_asset.setdefault((s['src'], s['asset'], s.get('dl', '4k')), []).append(mid)
    entries = {}
    for (src, aid, dl), mids in by_asset.items():
        t0 = time.time()
        log('%s:%s (%s) -> %s' % (src, aid, dl, ', '.join(mids)))
        if not check_license(src, aid):
            log('    SKIP: CC0 licence not confirmed on %s' % (ph_page(aid) if src == 'ph' else acg_page(aid)))
            continue
        d = os.path.join(work, '%s_%s' % (src, aid))
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)                                   # a new, empty directory per asset
        want_disp = True                                 # used for the normal check / AO / wet cavities
        files, meta = (fetch_ph if src == 'ph' else fetch_acg)(aid, dl, d, want_disp)
        log('    downloaded %d maps (%.0f MB) in %.0fs' % (
            len(files), sum(os.path.getsize(p) for p in files.values()) / 1e6, time.time() - t0))
        for mid in mids:
            e = convert(mid, TABLE[mid], files, res_cap, log)
            e['Source'] = source_record(TABLE[mid], meta)
            entries[mid] = e
            if '--no-json' not in flags:
                write_json({mid: e})
        if '--keep' not in flags:
            shutil.rmtree(d)
    if '--no-json' not in flags and entries:
        write_credits()
    log('done: %d materials' % len(entries))


if __name__ == '__main__':
    main(sys.argv[1:])
