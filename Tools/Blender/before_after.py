"""Before / after sheets for Docs/Renders/BeforeAfter (plain Python + PIL, no bpy).

    python3 Tools/Blender/before_after.py 20_Neon_Canyon 12_NightjarGarage_ParkingRow ...

For each name: <name>_before.jpg (kept from git before the change) beside Docs/Screens/<name>.jpg (the new still),
copied to <name>_after.jpg and stacked into <name>_compare.jpg with BEFORE / AFTER tags.
"""
import os
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "Docs", "Renders", "BeforeAfter")
FONT = os.path.join(ROOT, "Tools", "Blender", "club", "fonts")


def font(size):
    for f in sorted(os.listdir(FONT)) if os.path.isdir(FONT) else []:
        if f.lower().endswith((".ttf", ".otf")):
            try:
                return ImageFont.truetype(os.path.join(FONT, f), size)
            except OSError:
                pass
    return ImageFont.load_default()


def tag(img, text):
    d = ImageDraw.Draw(img)
    f = font(max(18, img.width // 48))
    pad = img.width // 120
    x0, y0, x1, y1 = d.textbbox((0, 0), text, font=f)
    d.rectangle((pad, pad, pad * 3 + x1 - x0, pad * 3 + y1 - y0), fill=(12, 10, 16))
    d.text((pad * 2 - x0, pad * 2 - y0), text, font=f, fill=(240, 236, 245))


def sheet(name, width=1920):
    before = Image.open(os.path.join(OUT, name + "_before.jpg")).convert("RGB")
    after_src = os.path.join(ROOT, "Docs", "Screens", name + ".jpg")
    shutil.copyfile(after_src, os.path.join(OUT, name + "_after.jpg"))
    after = Image.open(after_src).convert("RGB")
    h = round(width * after.height / after.width)
    a, b = before.resize((width, h), Image.LANCZOS), after.resize((width, h), Image.LANCZOS)
    tag(a, "BEFORE")
    tag(b, "AFTER")
    out = Image.new("RGB", (width, h * 2 + 8), (12, 10, 16))
    out.paste(a, (0, 0))
    out.paste(b, (0, h + 8))
    path = os.path.join(OUT, name + "_compare.jpg")
    out.save(path, quality=88)
    print(path)


if __name__ == "__main__":
    for n in sys.argv[1:]:
        sheet(n)
