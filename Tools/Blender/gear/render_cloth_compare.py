"""
Close-up before / after renders of the cloth and leather on the suit and the team gear
(Docs/Renders/BeforeAfter/Cloth_compare.jpg), from the baked texture sets on disk.

    python Tools/Blender/gear/render_cloth_compare.py -- --tag before     # renders the textures on disk now
    (re-bake: build_suit.py -- Suit --no-render ; build_teamgear.py -- <ids> --no-render)
    python Tools/Blender/gear/render_cloth_compare.py -- --tag after      # renders again, then the sheet
    python Tools/Blender/gear/render_cloth_compare.py -- --sheet          # only rebuild the sheet
    flags: --samples N (default 64), --res W H (default 1600 1000), --only lapel,shoe,carrier

Every shot uses build_suit's noir rig at full texture resolution (no 2K proxies), so the baked
weave / grain is what shows.  The shots land in <scratch>/cloth_<tag>_<shot>.png; the sheet puts
BEFORE | AFTER side by side, one row per shot.
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "common"))

import bpy  # noqa: E402,I001

import build_suit as bs  # noqa: E402
import build_teamgear as bt  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(ROOT, "Docs", "Renders", "BeforeAfter")
SCRATCH = os.environ.get("CLOTH_SCRATCH", os.path.join(os.environ.get("TMPDIR", "/tmp"), "cloth_compare"))

# name: (label, what to dress, camera target, view direction, distance, lens)
SHOTS = {
    "lapel": ("Suit: worsted wool, poplin shirt, silk tie", ("suit", "MidnightNavy", "White", "Black"),
              (0.04, 0.0, 1.38), (1.0, -0.32, 0.06), 0.62, 60),
    "shoe": ("Suit: polished calf, belt leather, rubber sole", ("suit", "Charcoal", "Black", "Black"),
             (0.06, 0.10, 0.08), (0.95, -0.75, 0.30), 0.62, 60),
    "carrier": ("Team gear: Cordura, webbing", ("gear", "PlateCarrier"), (0.10, 0.0, 1.26), (1.0, -0.55, 0.12), 0.80, 60),
}


def log(*a):
    print(*a, flush=True)


def dress(spec, coll):
    if spec[0] == "suit":
        _, suit, shirt, tie = spec
        obs = bs.import_asset("Suit", coll, {"P": bs.cw("Suit", suit), "S": bs.cw("Shirt", shirt), "A": bs.cw("Tie", tie)},
                              proxy_res=4096)
        obs += bs.import_asset("HairSlick", coll, {"P": bs.cw("Hair", "Black")}, proxy_res=2048)
        return obs
    aid = spec[1]
    team, cwi = bt.PRODUCT[aid][1], bt.PRODUCT[aid][2]
    return bt.import_asset(aid, coll, bt.tints_for(aid, team, cwi), proxy_res=4096)


def render_tag(tag, samples, res, only=None):
    os.makedirs(SCRATCH, exist_ok=True)
    for name, (_label, spec, tgt, vd, dist, lens) in SHOTS.items():
        if only and name not in only:
            continue
        bs.reset_scene()
        coll = bpy.data.collections.new("R")
        bpy.context.scene.collection.children.link(coll)
        dress(spec, coll)
        bs.mannequin_trimmed(coll)
        rig = bs.noir_rig()
        bs.place_cam(rig["cam"], tgt, vd, dist, lens)
        png = os.path.join(SCRATCH, f"cloth_{tag}_{name}.png")
        t0 = time.time()
        bs.render(png, res, samples)
        log(f"  {png} ({time.time() - t0:.0f}s)")


def sheet(width=1920):
    from PIL import Image, ImageDraw, ImageFont

    fonts = os.path.join(ROOT, "Tools", "Blender", "club", "fonts")

    def font(size):
        for f in sorted(os.listdir(fonts)) if os.path.isdir(fonts) else []:
            if f.lower().endswith((".ttf", ".otf")):
                try:
                    return ImageFont.truetype(os.path.join(fonts, f), size)
                except OSError:
                    pass
        return ImageFont.load_default()

    def tag(img, text, size):
        d = ImageDraw.Draw(img)
        f = font(size)
        pad = size // 2
        x0, y0, x1, y1 = d.textbbox((0, 0), text, font=f)
        d.rectangle((pad, pad, pad * 3 + x1 - x0, pad * 3 + y1 - y0), fill=(12, 10, 16))
        d.text((pad * 2 - x0, pad * 2 - y0), text, font=f, fill=(240, 236, 245))

    rows = []
    half = width // 2
    for name, (label, *_rest) in SHOTS.items():
        pair = []
        for t in ("before", "after"):
            p = os.path.join(SCRATCH, f"cloth_{t}_{name}.png")
            if not os.path.exists(p):
                raise SystemExit(f"missing {p}: render --tag {t} first")
            im = Image.open(p).convert("RGB")
            im = im.resize((half, round(im.height * half / im.width)), Image.LANCZOS)
            tag(im, ("BEFORE  " if t == "before" else "AFTER  ") + ("procedural" if t == "before" else "CC0 scans") +
                ("" if t == "before" else "  ·  " + label), max(14, half // 60))
            pair.append(im)
        row = Image.new("RGB", (width, pair[0].height), (0, 0, 0))
        row.paste(pair[0], (0, 0))
        row.paste(pair[1], (half, 0))
        rows.append(row)
    gap = 6
    out = Image.new("RGB", (width, sum(r.height for r in rows) + gap * (len(rows) - 1)), (8, 8, 10))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + gap
    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, "Cloth_compare.jpg")
    out.save(dst, quality=90, subsampling=0)
    for name in SHOTS:  # the individual frames as well, for close inspection
        for t in ("before", "after"):
            Image.open(os.path.join(SCRATCH, f"cloth_{t}_{name}.png")).convert("RGB").save(
                os.path.join(OUT, f"Cloth_{name}_{t}.jpg"), quality=90, subsampling=0)
    log(f"wrote {dst}")


def main(argv):
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 64
    res = (int(argv[argv.index("--res") + 1]), int(argv[argv.index("--res") + 2])) if "--res" in argv else (1600, 1000)
    if "--tag" in argv:
        t = argv[argv.index("--tag") + 1]
        only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
        render_tag(t, samples, res, only)
        if t == "after":
            sheet()
    if "--sheet" in argv:
        sheet()


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--" in a:
        a = a[a.index("--") + 1:]
    main(a)
