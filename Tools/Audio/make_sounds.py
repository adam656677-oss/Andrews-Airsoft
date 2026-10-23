#!/usr/bin/env python3
"""Andrew's Airsoft - synthesises every sound effect, ambience and music loop.

    python3 Tools/Audio/make_sounds.py              # everything (about 1-2 min on 4 cores)
    python3 Tools/Audio/make_sounds.py FireRifle SteelDing     # just these keys
    python3 Tools/Audio/make_sounds.py --only FireRifle,SteelDing
    python3 Tools/Audio/make_sounds.py --list

Writes 48 kHz / 16-bit PCM WAVs to Tools/Audio/Generated/<Key>.wav (keys with
variations also get <Key>_01.wav ... and <Key>.wav = the first variation).
Positional one-shots are mono; 2D UI / feedback / ambience / music are stereo.
Gunfire comes in three sets: the cinematic default (Fire<Gun>), distant versions
(Fire<Gun>_Far) and the original mechanical airsoft sounds (Fire<Gun>_Airsoft).
Deterministic: every key/variation has a fixed seed (crc32 of its name), so a
re-run reproduces identical files. Needs numpy; uses scipy.signal if present
(otherwise exact FFT-domain IIR filtering) and Pillow for _overview.png.
The Unreal editor setup script imports every Generated/*.wav to
/Game/Airsoft/Audio/<Key>; see README.md.
"""

import argparse
import os
import sys
import time

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from airsoft_audio import ambience, cinematic, dsp, feedback, foley, music, report, weapons  # noqa: E402

OUT = os.path.join(HERE, "Generated")
MODULES = [("Gunfire (cinematic)", cinematic.RECIPES), ("Gunfire (distant)", cinematic.FAR_RECIPES),
           ("Gunfire (airsoft alt)", weapons.RECIPES), ("Handling & foley", foley.RECIPES),
           ("Player & UI feedback", feedback.RECIPES), ("Ambience", ambience.RECIPES), ("Music", music.RECIPES)]


def registry():
    """key -> dict(fn, nvars, desc, ch, loop, group, seed, lufs) in a stable order.

    Recipe options: ch (1/2), loop (bool), seed (key name whose seed to use; lets a renamed
    key reproduce its old audio exactly), lufs (loops only: integrated-loudness target)."""
    reg = {}
    for group, recipes in MODULES:
        for key, entry in recipes.items():
            fn, nvars, desc = entry[:3]
            opts = entry[3] if len(entry) > 3 else {}
            reg[key] = dict(fn=fn, nvars=nvars, desc=desc, ch=opts.get("ch", 1), loop=opts.get("loop", False),
                            group=group, note=opts.get("note", ""), seed=opts.get("seed", key), lufs=opts.get("lufs"))
    return reg


def file_names(key, spec):
    if spec["nvars"] == 1:
        return [[key]]
    return [[f"{key}_{v + 1:02d}"] + ([key] if v == 0 else []) for v in range(spec["nvars"])]


def render_key(args):
    key, out_dir = args
    t0 = time.time()
    try:
        return _render_key(key, out_dir)
    except Exception:  # report and keep going so one broken recipe does not sink the run
        import traceback
        return key, [], time.time() - t0, traceback.format_exc()


def _render_key(key, out_dir):
    spec = registry()[key]  # looked up here: recipe lambdas cannot be pickled to workers
    t0 = time.time()
    results = []
    names = file_names(key, spec)
    for v in range(spec["nvars"]):
        r = dsp.rng_for(spec["seed"], v)
        x = spec["fn"](r, v)
        if spec["ch"] == 2:
            x = dsp.stereo(x)
        elif x.ndim == 2:
            raise ValueError(f"{key}: positional sound must be mono")
        x = dsp.finish_loop(x, lufs=spec["lufs"]) if spec["loop"] else dsp.finish_oneshot(x)
        for i, name in enumerate(names[v]):
            data = dsp.write_wav(os.path.join(out_dir, name + ".wav"), x, seed=dsp.seed_for(spec["seed"], v))
            if i == 0:
                st = report.stats(data, loop=spec["loop"])
                preview = x if spec["loop"] else data.astype(float).T / 32767.0
                if spec["loop"]:  # keep previews light for the contact sheet (band-limited 4x decimation)
                    preview = dsp.resample_fft(dsp.mono(x), 1, 4)
                    st["preview_sr"] = dsp.SR / 4
                results.append((name, st, preview))
            else:
                results.append((name, None, None))
    return key, results, time.time() - t0, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keys", nargs="*", help="keys to (re)build (same as --only)")
    ap.add_argument("--only", help="comma-separated keys to (re)build")
    ap.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 2),
                    help="worker processes (default: up to 4)")
    ap.add_argument("--no-overview", action="store_true", help="skip _overview.png")
    ap.add_argument("--list", action="store_true", help="list keys and exit")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    reg = registry()
    if a.list:
        for key, s in reg.items():
            kind = "loop" if s["loop"] else "one-shot"
            print(f"{key:22s} {s['group']:22s} {'stereo' if s['ch'] == 2 else 'mono':6s} {kind:8s} x{s['nvars']}  {s['desc']}")
        return
    picked = [k.strip() for k in (a.only or "").split(",") if k.strip()] + list(a.keys)
    partial = bool(picked)
    keys = list(dict.fromkeys(picked)) if partial else list(reg)
    bad = [k for k in keys if k not in reg]
    if bad:
        sys.exit(f"unknown key(s): {', '.join(bad)}")
    os.makedirs(a.out, exist_ok=True)

    # heaviest first so the pool stays busy
    keys.sort(key=lambda k: (not reg[k]["loop"], k))
    jobs = [(k, a.out) for k in keys]
    t0 = time.time()
    done, failed = {}, {}

    def collect(item):
        key, res, dt, err = item
        done[key] = res
        if err:
            failed[key] = err
            print(f"  {key:22s} FAILED\n{err}", flush=True)
        else:
            print(f"  {key:22s} {dt:6.1f}s", flush=True)

    if a.jobs > 1 and len(jobs) > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(a.jobs) as pool:
            for item in pool.imap_unordered(render_key, jobs):
                collect(item)
    else:
        for j in jobs:
            collect(render_key(j))

    if not partial and not failed:  # remove stale files from older layouts
        expected = {n + ".wav" for k in reg for grp in file_names(k, reg[k]) for n in grp}
        for f in os.listdir(a.out):
            if f.endswith(".wav") and f not in expected:
                os.remove(os.path.join(a.out, f))

    rows, items, loops = [], [], []
    for key in reg:
        for name, st, prev in done.get(key, []):
            if st is None:
                continue
            rows.append((name, st))
            if reg[key]["loop"]:
                loops.append((name, prev, st))
            else:
                items.append((name, prev, st))
    print()
    print(report.fmt_table(rows))
    total = sum(os.path.getsize(os.path.join(a.out, f)) for f in os.listdir(a.out) if f.endswith(".wav"))
    nfiles = len([f for f in os.listdir(a.out) if f.endswith(".wav")])
    print(f"\n{nfiles} WAV files, {total / 1e6:.1f} MB in {a.out}  ({time.time() - t0:.0f}s, scipy={'yes' if dsp.HAVE_SCIPY else 'no'})")
    clipped = [n for n, s in rows if s["clipped"]]
    if clipped:
        print("WARNING clipped:", ", ".join(clipped))
    if failed:
        print("FAILED keys:", ", ".join(sorted(failed)))
    if not a.no_overview and not partial:
        try:
            p = report.contact_sheet(os.path.join(a.out, "_overview.png"), items, loops)
            print("overview:", p)
        except ImportError:
            print("Pillow not installed; skipped _overview.png")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
