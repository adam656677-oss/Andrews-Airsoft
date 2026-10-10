"""Pack SourceAssets/ into GitHub-Release-sized zips (and unpack them again).

    python3 Tools/Release/package_assets.py pack      # -> Build/Release/SourceAssets-<Category>[-N].zip
    python3 Tools/Release/package_assets.py unpack DIR  # extract every SourceAssets-*.zip in DIR into SourceAssets/

GitHub release assets are limited to 2 GiB each, so every category is split
into parts of at most ~1.9 GB (whole asset folders are never split). PNG/FBX
data is already compressed, so files are stored without recompression.
"""

import os
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "SourceAssets")
OUT = os.path.join(ROOT, "Build", "Release")
LIMIT = int(1.9 * 1024 ** 3)


def folder_size(path):
    total = 0
    for base, _, files in os.walk(path):
        for name in files:
            total += os.path.getsize(os.path.join(base, name))
    return total


def pack():
    os.makedirs(OUT, exist_ok=True)
    for category in sorted(os.listdir(SRC)):
        cat_dir = os.path.join(SRC, category)
        if not os.path.isdir(cat_dir):
            continue
        groups, current, current_size = [], [], 0
        for asset in sorted(os.listdir(cat_dir)):
            size = folder_size(os.path.join(cat_dir, asset))
            if current and current_size + size > LIMIT:
                groups.append(current)
                current, current_size = [], 0
            current.append(asset)
            current_size += size
        if current:
            groups.append(current)
        for index, assets in enumerate(groups, 1):
            suffix = f"-{index}" if len(groups) > 1 else ""
            zip_path = os.path.join(OUT, f"SourceAssets-{category}{suffix}.zip")
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
                for asset in assets:
                    asset_dir = os.path.join(cat_dir, asset)
                    for base, _, files in os.walk(asset_dir):
                        for name in sorted(files):
                            full = os.path.join(base, name)
                            zf.write(full, os.path.relpath(full, SRC))
            print(f"{zip_path}  {os.path.getsize(zip_path) / 1024 ** 2:.0f} MB  ({len(assets)} assets)")


def unpack(directory):
    os.makedirs(SRC, exist_ok=True)
    for name in sorted(os.listdir(directory)):
        if name.startswith("SourceAssets-") and name.endswith(".zip"):
            with zipfile.ZipFile(os.path.join(directory, name)) as zf:
                zf.extractall(SRC)
            print(f"extracted {name}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "pack":
        pack()
    elif len(sys.argv) >= 3 and sys.argv[1] == "unpack":
        unpack(sys.argv[2])
    else:
        print(__doc__)
