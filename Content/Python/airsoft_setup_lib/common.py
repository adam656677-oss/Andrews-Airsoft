"""Shared helpers for the Andrew's Airsoft editor setup: logging, paths, asset registry, summary."""

import glob
import json
import os
import re
import struct
import time
import zlib

import unreal

from . import layouts

LOG_PREFIX = "[AirsoftSetup] "
TAG = "AirsoftGen"                      # every generated level actor carries this tag (re-runs delete them)
IMPORT_VERSION = "3"                    # bump to force a re-import of every mesh/texture

GAME_ROOT = "/Game/Airsoft"
MESH_ROOT = "/Game/Airsoft/Meshes"
TEX_ROOT = "/Game/Airsoft/Textures"
MAT_ROOT = "/Game/Airsoft/Materials"
MI_ROOT = "/Game/Airsoft/Materials/Instances"
AUDIO_ROOT = "/Game/Airsoft/Audio"
MAPS_ROOT = "/Game/Maps"
CATEGORIES = ("Weapons", "Attachments", "Gear", "Props", "Architecture")
NO_COLLISION_CATEGORIES = ("Weapons", "Attachments", "Gear")

# Optional behaviour switches (see Tools/Unreal/SETUP.md)
USE_VIRTUAL_TEXTURES = False   # VT needs every sampler in a material to match; off keeps instances interchangeable
NANITE_MASKED_FOLIAGE = True   # UE 5.1+ renders masked (leaf / net) materials with Nanite
FBX_CONVERT_SCENE = True       # Blender exports +X forward / +Z up; Unreal's default FBX conversion maps it 1:1
FBX_FORCE_FRONT_X = False
FBX_IMPORT_YAW = 0.0           # extra yaw (deg) applied at import if meshes arrive rotated
COMBINE_MESHES = False         # each FBX holds exactly one piece; the importer renames the result to SM_<Id>_<Piece>


# ---------------------------------------------------------------------------------------------
# Logging + summary
# ---------------------------------------------------------------------------------------------
def log(msg):
    unreal.log(LOG_PREFIX + str(msg))


def warn(msg):
    unreal.log_warning(LOG_PREFIX + str(msg))


def error(msg):
    unreal.log_error(LOG_PREFIX + str(msg))


class Summary(object):
    def __init__(self):
        self.counts = {}
        self.missing = {}
        self.notes = []
        self.maps = []
        self.t0 = time.time()
        self._once = set()

    def inc(self, key, n=1):
        self.counts[key] = self.counts.get(key, 0) + n

    def miss(self, kind, name):
        self.missing.setdefault(kind, set()).add(name)

    def note(self, msg):
        self.notes.append(msg)
        warn(msg)

    def once(self, key, msg):
        """Warn only the first time `key` is seen (API differences between engine versions)."""
        if key not in self._once:
            self._once.add(key)
            self.note(msg)

    def report(self):
        lines = ["", "=" * 78, "Andrew's Airsoft setup summary (%.0f s)" % (time.time() - self.t0), "=" * 78]
        for k in sorted(self.counts):
            lines.append("  %-44s %6d" % (k, self.counts[k]))
        for kind in sorted(self.missing):
            names = sorted(self.missing[kind])
            lines.append("  missing %-36s %6d  %s" % (kind, len(names), ", ".join(names[:30]) +
                                                      (" ..." if len(names) > 30 else "")))
        for m in self.maps:
            lines.append("  map  " + m)
        if self.notes:
            lines.append("  warnings: %d (see log above)" % len(self.notes))
        lines.append("=" * 78)
        for ln in lines:
            unreal.log(LOG_PREFIX + ln)


SUMMARY = Summary()


def reset_summary():
    global SUMMARY
    SUMMARY = Summary()
    return SUMMARY


# ---------------------------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------------------------
def project_dir():
    return os.path.normpath(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))


def source_dir():
    return os.path.join(project_dir(), "SourceAssets")


def data_dir():
    return os.path.join(project_dir(), "Content", "Airsoft", "Data")


def audio_dir():
    return os.path.join(project_dir(), "Tools", "Audio", "Generated")


def saved_dir():
    d = os.path.join(project_dir(), "Saved", "AirsoftSetup")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------------------------
# Asset helpers
# ---------------------------------------------------------------------------------------------
def asset_tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def exists(path):
    try:
        return unreal.EditorAssetLibrary.does_asset_exist(path)
    except Exception:
        return False


def load(path):
    if not exists(path):
        return None
    try:
        return unreal.EditorAssetLibrary.load_asset(path)
    except Exception:
        return None


def ensure_dir(path):
    try:
        if not unreal.EditorAssetLibrary.does_directory_exist(path):
            unreal.EditorAssetLibrary.make_directory(path)
    except Exception as e:
        warn("cannot create %s: %s" % (path, e))


def save_asset(asset):
    try:
        unreal.EditorAssetLibrary.save_loaded_asset(asset, False)
    except Exception as e:
        warn("save failed for %s: %s" % (asset, e))


def save_dir(path):
    try:
        unreal.EditorAssetLibrary.save_directory(path, only_if_is_dirty=True, recursive=True)
    except Exception as e:
        warn("save_directory %s failed: %s" % (path, e))


def try_set(obj, prop, value, quiet=False):
    """set_editor_property that never raises; reports each missing property once."""
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as e:
        if not quiet:
            SUMMARY.once("prop:%s.%s" % (type(obj).__name__, prop),
                         "property %s.%s not set (%s)" % (type(obj).__name__, prop, str(e).splitlines()[0][:120]))
        return False


def try_get(obj, prop, default=None):
    try:
        return obj.get_editor_property(prop)
    except Exception:
        return default


def get_metadata(asset, tag):
    try:
        return unreal.EditorAssetLibrary.get_metadata_tag(asset, tag) or ""
    except Exception:
        return ""


def set_metadata(asset, tag, value):
    try:
        unreal.EditorAssetLibrary.set_metadata_tag(asset, tag, str(value))
    except Exception as e:
        SUMMARY.once("meta", "set_metadata_tag failed (%s); change detection disabled" % e)


def editor_world():
    try:
        return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    except Exception:
        try:
            return unreal.EditorLevelLibrary.get_editor_world()
        except Exception:
            return None


def console(cmd):
    try:
        unreal.SystemLibrary.execute_console_command(editor_world(), cmd)
        return True
    except Exception as e:
        warn("console command '%s' failed: %s" % (cmd, e))
        return False


def cvar_bool(name, default=None):
    try:
        return bool(unreal.SystemLibrary.get_console_variable_bool_value(name))
    except Exception:
        return default


def lc(rgb, a=1.0):
    return unreal.LinearColor(float(rgb[0]), float(rgb[1]), float(rgb[2]), float(a))


def rot(pitch=0.0, yaw=0.0, roll=0.0):
    """unreal.Rotator takes (roll, pitch, yaw) positionally - always build it by keyword."""
    return unreal.Rotator(roll=float(roll), pitch=float(pitch), yaw=float(yaw))


def vec(x, y, z):
    return unreal.Vector(float(x), float(y), float(z))


def source_stamp(path):
    try:
        st = os.stat(path)
        return "%d:%d:%s" % (int(st.st_mtime), st.st_size, IMPORT_VERSION)
    except OSError:
        return ""


# ---------------------------------------------------------------------------------------------
# Asset registry: JSON data merged with what is on disk under SourceAssets/
# ---------------------------------------------------------------------------------------------
def _category_for_json(fname):
    for c in CATEGORIES:
        if fname.startswith(c):
            return c
    return None


def load_materials_json():
    p = os.path.join(data_dir(), "Materials.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("Materials", {})
    except Exception as e:
        warn("Materials.json not readable (%s); tileables use flat colours" % e)
        return {}


def load_registry():
    """Returns {asset_id: entry}. entry: Category, Pieces[{Name, Kind, Slots, BlendMode}], Bounds, Points,
    Collision, TintVariants, Textures{piece: {BC,N,ORM,M,Opacity: abs path}}, Fbx{piece: abs path}."""
    reg = {}
    for path in sorted(glob.glob(os.path.join(data_dir(), "*.json"))):
        name = os.path.basename(path)
        if name == "Materials.json":
            continue
        cat = _category_for_json(name)
        if not cat:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            SUMMARY.note("cannot parse %s (%s) - skipped (a generator may still be writing it)" % (name, e))
            continue
        for aid, a in (data.get("Assets") or {}).items():
            e = dict(a)
            e["Category"] = cat
            e["_json"] = name
            e["Pieces"] = [dict(p) for p in a.get("Pieces", [])]
            reg[aid] = e
    # disk scan: assets/pieces the JSON does not know yet
    for cat in CATEGORIES:
        for d in sorted(glob.glob(os.path.join(source_dir(), cat, "*"))):
            if not os.path.isdir(d):
                continue
            aid = os.path.basename(d)
            fbxs = sorted(glob.glob(os.path.join(d, "SM_%s_*.fbx" % aid)))
            if not fbxs:
                continue
            e = reg.setdefault(aid, {"Category": cat, "Pieces": [], "_json": None})
            e["Category"] = cat if e.get("_json") is None else e["Category"]
            known = {p["Name"] for p in e["Pieces"]}
            for f in fbxs:
                piece = os.path.basename(f)[len("SM_%s_" % aid):-4]
                if piece and piece not in known:
                    e["Pieces"].append({"Name": piece, "Kind": guess_kind(piece), "Slots": []})
                    known.add(piece)
    # resolve files
    for aid, e in reg.items():
        d = os.path.join(source_dir(), e["Category"], aid)
        e["Fbx"] = {}
        e["Textures"] = {}
        for p in e["Pieces"]:
            pn = p["Name"]
            f = os.path.join(d, "SM_%s_%s.fbx" % (aid, pn))
            if os.path.isfile(f):
                e["Fbx"][pn] = f
            tex = {}
            for key in ("BC", "N", "ORM", "M", "Opacity", "H"):
                t = os.path.join(d, "T_%s_%s_%s.png" % (aid, pn, key))
                if os.path.isfile(t):
                    tex[key] = t
            e["Textures"][pn] = tex
        if "Bounds" not in e:
            mn, mx = layouts.asset_bounds(aid)
            e["Bounds"] = {"Min": list(mn), "Max": list(mx)}
        if not e["Pieces"]:
            e["Pieces"] = [{"Name": "Body", "Kind": "Body", "Slots": []}]
    return reg


def guess_kind(piece):
    if piece in ("Body", "Mag", "Slide", "Bolt", "Pump", "Glass", "Emissive"):
        return piece
    return "Static"


def piece_role(aid, piece):
    """How a piece renders: 'glass', 'emissive', 'masked' or 'opaque'."""
    pn = piece.get("Name", "")
    kind = piece.get("Kind", "")
    if kind == "Glass" or pn == "Glass" or pn.endswith("Lamp"):
        return "glass"
    if kind == "Emissive" or pn in ("Emissive", "Reticle", "LED"):
        return "emissive"
    if piece.get("BlendMode") == "Masked" or pn in ("Leaves", "Net"):
        return "masked"
    return "opaque"


def mesh_dir(cat, aid):
    return "%s/%s/%s" % (MESH_ROOT, cat, aid)


def mesh_path(cat, aid, piece):
    return "%s/SM_%s_%s" % (mesh_dir(cat, aid), aid, piece)


def tex_dir(cat, aid):
    return "%s/%s/%s" % (TEX_ROOT, cat, aid)


def json_assets_for_layouts(reg):
    """Shape the registry like the raw JSON (with _Category) for layouts.* helpers."""
    out = {}
    for aid, e in reg.items():
        d = {"_Category": e["Category"], "Bounds": e.get("Bounds"), "Points": e.get("Points", {})}
        out[aid] = d
    return out


# ---------------------------------------------------------------------------------------------
# Tiny PNG writer (no PIL inside the editor) for default textures
# ---------------------------------------------------------------------------------------------
def write_png(path, w, h, rgba):
    """rgba: (r, g, b, a) 0-255 used for every pixel."""
    raw = b"".join(b"\x00" + bytes(rgba) * w for _ in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def strip_slot_suffix(name):
    """Blender/FBX may append .001 / _001 / _R to material names."""
    n = re.sub(r"([._]\d{3})+$", "", name)
    if n.endswith("_R"):
        n = n[:-2]
    return n
