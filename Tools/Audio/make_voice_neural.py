"""Andrew's Airsoft - neural story voice-over for the "Last Contract" campaign.

Replaces the Windows text-to-speech voices of make_voice.ps1 (kept as a no-download fallback)
with Kokoro-82M (https://huggingface.co/hexgrad/Kokoro-82M, Apache-2.0, runs on CPU).
All voices are Kokoro's own synthetic voices (some blended); none imitates a real person.

Reads Content/Airsoft/Data/Campaign.json and writes (make_voice.ps1 covers the first three only):
    Tools/Audio/Generated/Voice/VO_M<n>_I<k>.wav          narrator, mission intro line k
    Tools/Audio/Generated/Voice/VO_M<n>_Boss.wav          the mission boss's taunt
    Tools/Audio/Generated/Voice/VO_M<n>_Outro.wav         narrator, mission outro
    Tools/Audio/Generated/Voice/VO_M<n>_Andrew_Start.wav  Andrew, as the opening cinematic ends
    Tools/Audio/Generated/Voice/VO_M<n>_Andrew_Boss.wav   Andrew's reply to the boss
    Tools/Audio/Generated/Voice/VO_M<n>_Boss_Mid.wav      the boss at half health
    Tools/Audio/Generated/Voice/VO_M<n>_Boss_Death.wav    the boss going down
    Tools/Audio/Generated/Voice/VO_Andrew_*.wav, VO_Crew_<A|B|C>_*.wav   combat barks ("Barks")
48 kHz / 16-bit mono, about -18 LUFS, true peak <= -1 dBTP. The editor setup script imports
them as /Game/Airsoft/Audio/<name>; AirsoftCampaign::VoiceKey() finds them by that name.

Optional: --next-build DIR also voices any spoken lines still marked "new" (not yet in the game) in
Docs/Last_Contract_Voice_Script.html under the script's file names into DIR. They are kept out of
Tools/Audio/Generated (the importer imports every WAV under it).

Setup (Python 3.10-3.12; 3.13 has no wheels for some dependencies yet):
    python -m venv .ttsvenv
    .ttsvenv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
    .ttsvenv/Scripts/pip install kokoro soundfile "misaki[en]"
    .ttsvenv/Scripts/pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
    .ttsvenv/Scripts/python Tools/Audio/make_voice_neural.py
The model (~330 MB) and voices download from Hugging Face on first run (HF_HOME sets the cache).

    python Tools/Audio/make_voice_neural.py                 # all campaign lines
    python Tools/Audio/make_voice_neural.py VO_M1_I0 VO_M4_Boss
    python Tools/Audio/make_voice_neural.py --next-build Saved/VoiceNextBuild
    python Tools/Audio/make_voice_neural.py --check         # measure the files only, no synthesis
    python Tools/Audio/make_voice_neural.py --asr openai/whisper-tiny.en   # also transcribe back

Deterministic: each line seeds torch from crc32(<file name>#<sentence>) and the reverb / dither
from crc32(<file name>); same packages + same machine -> identical files.
"""

import argparse
import html
import json
import math
import os
import re
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from airsoft_audio import dsp  # noqa: E402  (shared filters, reverb IRs, BS.1770 loudness, true peak, dithered WAV writer)

KOKORO_REPO = "hexgrad/Kokoro-82M"
KOKORO_SR = 24000
FRAME = 600  # Kokoro samples per predicted duration frame (25 ms)
MAX_FRAMES = 12  # longest any single spoken phoneme may last (0.3 s)
PUNCT = set(" ;:,.!?—…\"()“”")
SR = dsp.SR  # 48 kHz
TARGET_LUFS = -18.0
CEILING_DBTP = -1.0

# ------------------------------------------------------------------------------------ cast
# voice: {kokoro voice id: weight} (weights > 1 voice = a blended, original voice)
# lang:  "a" American / "b" British G2P (must match the voice family)
# speed: Kokoro speed (1.0 = the voice's default pace)
# gap:   silence between sentences (s); comma: speed factor on commas (<1 = longer comma pause)
# land:  speed factor on the last word of each sentence (<1 = leans on it)
# fx:    post chain, see FX
CAST = {
    "narrator": dict(voice={"am_michael": 0.65, "am_onyx": 0.35}, lang="a", speed=0.82, gap=0.55, comma=0.55, land=0.84, fx="narrator",
                     why="Michael's natural, warm delivery deepened with a third of Onyx (the darkest, lowest Kokoro male, ~90 Hz): "
                         "a low, weathered storyteller. Slowed to ~130 wpm (speed 0.82), real comma pauses, last word of each sentence leaned on."),
    "kade": dict(voice={"am_puck": 1.0}, lang="a", speed=1.10, gap=0.28, comma=0.9, land=1.0, fx="boss_street",
                 why="Puck is the brightest, most energetic young American male: cocky and quick, pushed 10% faster."),
    "dorian": dict(voice={"bm_fable": 1.0}, lang="b", speed=0.93, gap=0.4, comma=0.75, land=0.88, fx="boss_smooth",
                   why="Fable is a theatrical British storyteller with crisp, polished diction: the smooth club manager, unhurried."),
    "mara": dict(voice={"af_kore": 1.0}, lang="a", speed=1.02, gap=0.32, comma=0.85, land=0.95, fx="boss_cold",
                 why="Kore is the firmest, lowest American female voice: flat, controlled and clipped, like radio orders."),
    "varga": dict(voice={"bm_george": 0.45, "bm_lewis": 0.35, "am_onyx": 0.2}, lang="b", speed=0.85, gap=0.6, comma=0.6, land=0.82, fx="boss_dark",
                  why="George (older, measured British) blended with Lewis and a little Onyx for a lower, darker register: soft-spoken old money; slow, close."),
    # Andrew's lines and the crew barks
    "andrew": dict(voice={"am_fenrir": 0.7, "am_onyx": 0.3}, lang="a", speed=0.95, gap=0.4, comma=0.75, land=0.9, fx="dry",
                   why="Fenrir (40s, plain) with some Onyx grit: quiet, tired, economical."),
    "crew_a": dict(voice={"am_eric": 1.0}, lang="a", speed=1.12, gap=0.2, comma=1.0, land=1.0, fx="dry", why="Aggressive and loud."),
    "crew_b": dict(voice={"am_liam": 1.0}, lang="a", speed=1.18, gap=0.15, comma=1.0, land=1.0, fx="dry", why="Younger, nervous, fast."),
    "crew_c": dict(voice={"am_echo": 0.6, "am_onyx": 0.4}, lang="a", speed=1.0, gap=0.25, comma=0.9, land=1.0, fx="dry", why="Older veteran, low and calm."),
}

# Boss name in Campaign.json -> cast id
BOSS_CAST = {"Kade": "kade", "Dorian": "dorian", "Mara": "mara", "Varga": "varga"}

# Pronunciations the lexicon gets wrong (misaki inline phonemes, [word](/phonemes/)).
PRONOUNCE = {
    "Mara": "mˈɑɹə",     # lexicon: mˈɑɹɹə
    "Silas": "sˈIləs",    # lexicon: sˈiləz ("see-luz")
}

# Per-line direction (from the voice script's parentheticals).
#   slow:   {phrase: speed factor} for words inside a sentence
#   gaps:   explicit silences between this line's sentences (overrides the cast gap)
#   speed:  multiplies the cast speed for this line
#   pre:    leading silence (s, <= 0.3)
DIRECTION = {
    "VO_M1_I2": dict(slow={"settle a debt": 0.78}),                 # "Slow down on 'settle a debt.'"
    "VO_M4_I2": dict(speed=0.88, pre=0.25, slow={"Andrew": 0.8}),     # "Three words. Give it a beat before and after."
    "VO_M4_Outro": dict(gaps=[0.6, 0.85]),                           # "'For now' is almost a smile." - let it land late
    "VO_M1_I1": dict(gaps=[0.65]),                                   # "Oil, brass, and silence." after a breath
    "VO_M3_Boss_Death": dict(speed=0.85),
    "VO_M1_Boss_Death": dict(speed=0.85),
    "VO_M2_Boss_Death": dict(speed=0.9),
    "VO_M4_Boss_Death": dict(speed=0.88),
    "VO_M3_Andrew_Boss": dict(speed=0.92),
}

# ------------------------------------------------------------------------------------ post chain
# hp: high-pass Hz; eq: dsp.eq bands; comp: (threshold dBFS, ratio, attack s, release s);
# verb: dict(make_ir kwargs + wet) or None; tail: reverb tail kept after the last word (s)
FX = {
    "narrator": dict(hp=70, eq=[("lowshelf", 160, 0.7, 1.5), ("peak", 320, 1.0, -1.0), ("peak", 3200, 0.9, 1.5), ("highshelf", 9000, 0.7, -2.0)],
                     comp=(-26.0, 2.5, 0.008, 0.16),
                     verb=dict(t60=0.9, predelay=0.014, early=[(0.011, 0.25), (0.019, 0.18), (0.029, 0.12)], hf=0.35, lf=1.0,
                               build=0.012, lo_cut=220.0, hi_cut=7000.0, wet=0.16), tail=0.22),
    "boss_dark": dict(hp=65, eq=[("lowshelf", 180, 0.7, 2.0), ("peak", 2800, 0.9, -1.0), ("highshelf", 5500, 0.7, -3.5)],
                      comp=(-26.0, 3.0, 0.006, 0.14), verb=dict(t60=0.45, predelay=0.006, hf=0.35, build=0.006, lo_cut=250.0, hi_cut=6000.0, wet=0.07), tail=0.15),
    "boss_smooth": dict(hp=80, eq=[("lowshelf", 200, 0.7, 1.0), ("peak", 3500, 0.9, -0.5), ("highshelf", 7000, 0.7, -2.5)],
                        comp=(-26.0, 2.5, 0.006, 0.14), verb=dict(t60=0.45, predelay=0.008, hf=0.4, build=0.008, lo_cut=250.0, hi_cut=7000.0, wet=0.08), tail=0.1),
    "boss_cold": dict(hp=110, eq=[("peak", 250, 1.0, -1.5), ("peak", 2500, 1.0, 1.0), ("highshelf", 7500, 0.7, -2.5)],
                      comp=(-27.0, 3.0, 0.004, 0.10), verb=dict(t60=0.35, predelay=0.004, hf=0.4, build=0.004, lo_cut=300.0, hi_cut=6500.0, wet=0.05), tail=0.12),
    "boss_street": dict(hp=90, eq=[("peak", 1800, 1.0, 1.0), ("highshelf", 7000, 0.7, -2.5)],
                        comp=(-27.0, 3.5, 0.004, 0.10), verb=dict(t60=0.4, predelay=0.005, hf=0.4, build=0.005, lo_cut=300.0, hi_cut=6500.0, wet=0.06), tail=0.12),
    "dry": dict(hp=80, eq=[("highshelf", 8000, 0.7, -1.5)], comp=(-26.0, 3.0, 0.005, 0.12), verb=None, tail=0.15),
}

LEAD = 0.10   # leading silence (s)
TRAIL = 0.03  # silence after the last word, before any reverb tail (s)


# ------------------------------------------------------------------------------------ script
def campaign_lines(root):
    with open(os.path.join(root, "Content", "Airsoft", "Data", "Campaign.json"), encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for n, m in enumerate(data["Missions"], 1):
        for k, t in enumerate(m.get("Intro", [])):
            out.append(("VO_M%d_I%d" % (n, k), "narrator", t))
        if m.get("AndrewStart"):
            out.append(("VO_M%d_Andrew_Start" % n, "andrew", m["AndrewStart"]))
        boss = m.get("Boss") or {}
        if boss.get("Name"):
            cast = next((c for key, c in BOSS_CAST.items() if key in boss.get("Name", "")), None)
            if not cast:
                raise SystemExit("No cast entry for boss %r: add it to BOSS_CAST" % boss.get("Name"))
            for field, suffix in (("Taunt", "Boss"), ("Mid", "Boss_Mid"), ("Death", "Boss_Death")):
                if boss.get(field):
                    out.append(("VO_M%d_%s" % (n, suffix), cast, boss[field]))
            if boss.get("AndrewReply"):
                out.append(("VO_M%d_Andrew_Boss" % n, "andrew", boss["AndrewReply"]))
        if m.get("Outro"):
            out.append(("VO_M%d_Outro" % n, "narrator", m["Outro"]))
    # Combat barks: Andrew's (VO_Andrew_*) and the three crew voices (VO_Crew_<A|B|C>_*).
    for lines in (data.get("Barks") or {}).values():
        for b in lines:
            f = b["File"]
            cast = "andrew" if f.startswith("VO_Andrew_") else "crew_" + f.split("_")[2].lower()
            out.append((f, cast, b["Text"]))
    return out


def next_build_lines(root):
    """Spoken 'new' lines from the LINES table of Docs/Last_Contract_Voice_Script.html."""
    with open(os.path.join(root, "Docs", "Last_Contract_Voice_Script.html"), encoding="utf-8") as f:
        src = f.read()
    out = []
    for m in re.finditer(r'\{\s*c:\s*"(\w+)",\s*f:\s*"(\w+)",.*?s:\s*"(\w+)",\s*t:\s*"((?:[^"\\]|\\.)*)"', src):
        c, fname, status, text = m.group(1), m.group(2), m.group(3), html.unescape(m.group(4))
        if status != "new" or text.startswith("("):
            continue  # live lines come from Campaign.json; "(...)" rows are effort sounds, not speech
        if c == "crew":
            c = "crew_" + fname.split("_")[2].lower()
        out.append((fname, c, text))
    return out


# ------------------------------------------------------------------------------------ synthesis
class Voicer:
    def __init__(self):
        import torch
        from kokoro import KModel, KPipeline
        self.torch = torch
        torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
        self.model = KModel(repo_id=KOKORO_REPO).eval()
        self.g2p = {lc: KPipeline(lang_code=lc, repo_id=KOKORO_REPO, model=False) for lc in ("a", "b")}
        self.packs = {}
        self.rvocab = {i: ch for ch, i in self.model.vocab.items()}

    def pack(self, cast_id):
        if cast_id not in self.packs:
            spec = CAST[cast_id]["voice"]
            total = sum(spec.values())
            self.packs[cast_id] = sum(self.g2p[v[0] if v[0] == "b" else "a"].load_single_voice(v) * (w / total)
                                      for v, w in spec.items())
        return self.packs[cast_id]

    def sentence(self, text, cast_id, speed, slow, seed):
        """One sentence -> float32 audio at 24 kHz, with per-phoneme speed (commas, landed last word, slowed phrases)."""
        torch = self.torch
        c = CAST[cast_id]
        _, tokens = self.g2p[c["lang"]].g2p(markup(text))
        words = [i for i, t in enumerate(tokens) if t.phonemes and any(ch.isalpha() for ch in t.text)]
        factors = [1.0] * len(tokens)
        if words:
            factors[words[-1]] = c["land"]
        for i, t in enumerate(tokens):
            if t.phonemes in (",", "—", ";", ":"):
                factors[i] = c["comma"]
            if t.phonemes == "…":
                factors[i] = 0.6
        for phrase, fac in (slow or {}).items():
            want = phrase.lower().split()
            texts = [tokens[i].text.lower() for i in words]
            for s in range(len(texts) - len(want) + 1):
                if texts[s:s + len(want)] == want:
                    for j in words[s:s + len(want)]:
                        factors[j] = min(factors[j], fac)
        ids, spd = [], []
        last_sound = 0  # index in ids of the last spoken (non-punctuation) phoneme
        for t, fac in zip(tokens, factors):
            if t.phonemes is None:
                print("    ! no pronunciation for %r (add it to PRONOUNCE)" % t.text)
                continue
            for ch in t.phonemes + (" " if t.whitespace else ""):
                i = self.model.vocab.get(ch)
                if i is not None:
                    ids.append(i)
                    spd.append(fac)
                    if ch not in PUNCT:
                        last_sound = len(ids) - 1
        while ids and ids[-1] == self.model.vocab.get(" "):
            ids.pop()
            spd.pop()
        assert 0 < len(ids) <= 510, (text, len(ids))
        input_ids = torch.LongTensor([[0, *ids, 0]])
        speeds = torch.tensor([[1.0, *spd, 1.0]]) * speed
        ref_s = self.pack(cast_id)[len(ids) - 1]
        sounds = torch.tensor([[False, *[inv not in PUNCT for inv in map(self.rvocab.get, ids)], False]])
        for _ in range(2):
            torch.manual_seed(seed)
            with torch.no_grad():
                audio, pred_dur = self.model.forward_with_tokens(input_ids, ref_s, speeds)
            # Kokoro sometimes stretches a sentence-final consonant into a long hiss (e.g. 0.75 s on
            # the "z" of "regards"): cap every spoken phoneme at MAX_FRAMES and render again.
            over = (pred_dur.float() / MAX_FRAMES).unsqueeze(0) * sounds
            if over.max() <= 1.0:
                break
            speeds = speeds * torch.clamp(over, min=1.0)
        audio = audio.float().numpy()
        # Kokoro often lets a sentence trail off into breath/hiss for a few hundred ms after the
        # final '.'/'?' token: cut at the end of the last spoken phoneme (+ a short release).
        end = int(pred_dur[:last_sound + 2].sum()) * FRAME + int(0.12 * KOKORO_SR)
        return audio[:end]

    def line(self, name, cast_id, text):
        c = CAST[cast_id]
        d = DIRECTION.get(name, {})
        speed = c["speed"] * d.get("speed", 1.0)
        sentences = split_sentences(text)
        gaps = list(d.get("gaps", [])) + [c["gap"]] * len(sentences)
        parts = [np.zeros(int(KOKORO_SR * min(0.3, d.get("pre", LEAD))), np.float32)]
        for k, s in enumerate(sentences):
            a = trim(self.sentence(s, cast_id, speed, d.get("slow"), zlib.crc32(("%s#%d" % (name, k)).encode())))
            parts.append(a)
            if k < len(sentences) - 1:
                parts.append(np.zeros(int(KOKORO_SR * gaps[k]), np.float32))
        return np.concatenate(parts)


def markup(text):
    text = text.replace("...", "…")
    text = re.sub(r"\b[A-Z]{2,}\b", lambda m: m.group(0).capitalize(), text)  # shouted "HIM" is a word, not an acronym
    for word, ps in PRONOUNCE.items():
        text = re.sub(r"\b%s\b" % re.escape(word), "[%s](/%s/)" % (word, ps), text)
    return text


def split_sentences(text):
    """Split after . ? ! (not after an ellipsis, which stays a pause inside the sentence)."""
    parts = re.split(r"(?<=[.?!])(?<!\.\.\.)\s+", text.strip())
    return [p for p in parts if p]


def trim(a, sr=KOKORO_SR, thr_db=-42.0, pre=0.035, post=0.05):
    """Cut Kokoro's padding: keep from just before the first to just after the last 10 ms block above thr (rel. peak)."""
    blk = int(0.01 * sr)
    n = len(a) // blk
    if n == 0:
        return a
    rms = np.sqrt(np.mean(a[:n * blk].reshape(n, blk) ** 2, axis=1) + 1e-12)
    on = np.nonzero(20 * np.log10(rms / rms.max()) > thr_db)[0]
    s = max(0, on[0] * blk - int(pre * sr))
    e = min(len(a), (on[-1] + 1) * blk + int(post * sr))
    out = a[s:e].copy()
    k = int(0.004 * sr)
    out[:k] *= np.linspace(0, 1, k)
    k = int(0.03 * sr)
    out[-k:] *= np.cos(np.linspace(0, np.pi / 2, k)) ** 2
    return out


# ------------------------------------------------------------------------------------ post
def compress(x, thr_db, ratio, attack, release, knee=6.0):
    """Feed-forward RMS compressor (10 ms window, 1 ms control rate), soft knee; make-up comes from the loudness stage."""
    blk = SR // 1000
    n = len(x)
    m = -(-n // blk)
    p = np.pad(x, (0, m * blk - n)) ** 2
    pw = p.reshape(m, blk).mean(axis=1)
    pw = np.convolve(pw, np.ones(10) / 10, mode="same")
    lvl = 10 * np.log10(pw + 1e-12)
    over = lvl - thr_db
    gr = np.where(over <= -knee / 2, 0.0,
                  np.where(over >= knee / 2, over * (1 - 1 / ratio), (1 - 1 / ratio) * (over + knee / 2) ** 2 / (2 * knee)))
    ka, kr = math.exp(-1e-3 / attack), math.exp(-1e-3 / release)
    sm = np.empty(m)
    g = 0.0
    for i in range(m):
        k = ka if gr[i] > g else kr
        g = k * g + (1 - k) * gr[i]
        sm[i] = g
    gain = dsp.undb(-np.interp(np.arange(n) / blk, np.arange(m), sm))
    return x * gain


def master(x24, name, fx_name):
    fx = FX[fx_name]
    x = dsp.resample_fft(np.concatenate([x24.astype(float), np.zeros(KOKORO_SR // 2)]), 2, 1)
    voiced_end = len(x) - SR // 2  # where the half second of padding begins
    x = dsp.hp(x, fx["hp"], order=2)
    x = dsp.eq(x, fx["eq"])
    x = compress(x, *fx["comp"])
    end = voiced_end + int(TRAIL * SR)
    if fx["verb"]:
        v = dict(fx["verb"])
        wet = v.pop("wet")
        ir = dsp.make_ir(dsp.rng_for(name, 1), **v)
        x = x + wet * dsp.conv(x, ir)[:len(x)]
        end += int(fx["tail"] * SR)
    x = dsp.tail_cut(x, end / SR, fade_s=min(0.25, fx["tail"] + 0.05))
    x = x - x.mean()
    k = int(0.004 * SR)
    x[:k] *= np.linspace(0, 1, k)
    for _ in range(3):  # loudness, then catch any peaks over the ceiling, then re-level
        x = x * dsp.undb(TARGET_LUFS - dsp.loudness(x))
        if dsp.true_peak(x) > dsp.undb(CEILING_DBTP - 0.3):
            x = dsp.limit(x, dsp.undb(CEILING_DBTP - 0.8), lookahead=0.002, hold=0.008, release=0.06)
    # A quiet room tail (below -50 dBFS) can still run on for a few hundred ms: end the file
    # 0.2 s after the last 10 ms block above -50 dBFS (the decay is faded, not chopped).
    blk = SR // 100
    n = len(x) // blk
    loud = np.nonzero(20 * np.log10(np.sqrt(np.mean(x[:n * blk].reshape(n, blk) ** 2, axis=1)) + 1e-12) > -50.0)[0]
    if len(loud) and (loud[-1] + 1) * blk + int(0.2 * SR) < len(x):
        x = dsp.tail_cut(x, ((loud[-1] + 1) * blk + int(0.2 * SR)) / SR, fade_s=0.18)
    return x * min(1.0, dsp.undb(CEILING_DBTP - 0.1) / dsp.true_peak(x))


# ------------------------------------------------------------------------------------ checks
def measure(path, text=None):
    x, sr = dsp.read_wav(path)
    if x.ndim > 1:
        x = x.mean(axis=0)
    blk = sr // 100
    n = len(x) // blk
    rms = np.sqrt(np.mean(x[:n * blk].reshape(n, blk) ** 2, axis=1) + 1e-12)
    on = np.nonzero(20 * np.log10(rms) > -50.0)[0]  # absolute -50 dBFS, 10 ms blocks
    words = len(re.findall(r"[A-Za-z']+", text)) if text else 0
    dur = len(x) / sr
    return dict(sr=sr, dur=dur, lufs=dsp.loudness(x) if sr == SR else float("nan"), tp=dsp.db(dsp.true_peak(x)),
                lead=(on[0] * blk / sr) if len(on) else dur, trail=(dur - (on[-1] + 1) * blk / sr) if len(on) else dur,
                clip=int(np.sum(np.abs(x) >= 32767 / 32767.0)), wpm=(60.0 * words / dur) if words else 0.0)


def report(rows, out_dir):
    print("\n%-22s %6s %6s %7s %6s %5s %5s %4s" % ("file", "len s", "wpm", "LUFS", "dBTP", "lead", "trail", "clip"))
    total = 0
    bad = []
    for name, text in rows:
        p = os.path.join(out_dir, name + ".wav")
        if not os.path.exists(p):
            continue
        r = measure(p, text)
        total += os.path.getsize(p)
        flag = ""
        if r["tp"] > CEILING_DBTP + 0.05 or r["clip"] or r["lead"] > 0.3 or r["trail"] > 0.3 or abs(r["lufs"] - TARGET_LUFS) > 1.0 or not 0.8 < r["dur"] < 15:
            flag = "  <-- check"
            bad.append(name)
        print("%-22s %6.2f %6.0f %7.1f %6.1f %5.2f %5.2f %4d%s" % (name, r["dur"], r["wpm"], r["lufs"], r["tp"], r["lead"], r["trail"], r["clip"], flag))
    print("total %.2f MB in %s" % (total / 1e6, out_dir))
    return bad


def transcribe(model_id, rows, out_dir):
    from transformers import pipeline
    asr = pipeline("automatic-speech-recognition", model=model_id, device="cpu")
    def norm(s):  # compare words, not spelling: "Mister"/"Mr.", "should've"/"should have"
        s = s.lower().replace("mister", "mr").replace("’", "'")
        for a, b in (("n't", " not"), ("'ve", " have"), ("'ll", " will"), ("'re", " are"), ("'m", " am")):
            s = s.replace(a, b)
        return re.findall(r"[a-z0-9']+", s)
    errs = words = 0
    for name, text in rows:
        p = os.path.join(out_dir, name + ".wav")
        x, sr = dsp.read_wav(p)
        n = int(len(x) * 16000 / sr)
        x16 = np.interp(np.arange(n) * sr / 16000, np.arange(len(x)), x).astype(np.float32)
        hyp = asr({"raw": x16, "sampling_rate": 16000})["text"].strip()
        r, h = norm(text), norm(hyp)
        e = edit_distance(r, h)
        errs += e
        words += len(r)
        print("%-22s WER %3.0f%%  %s" % (name, 100.0 * e / max(1, len(r)), hyp))
    print("overall WER %.1f%% (%d/%d words)" % (100.0 * errs / max(1, words), errs, words))


def edit_distance(a, b):
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
    return d[len(b)]


# ------------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("names", nargs="*", help="only these file names (e.g. VO_M1_I0)")
    ap.add_argument("--out", default=os.path.join(ROOT, "Tools", "Audio", "Generated", "Voice"))
    ap.add_argument("--next-build", metavar="DIR", help="also voice the script's next-build lines into DIR (not Generated/)")
    ap.add_argument("--check", action="store_true", help="only measure existing files")
    ap.add_argument("--asr", metavar="MODEL", help="transcribe the results back with a transformers ASR model (e.g. openai/whisper-tiny.en)")
    ap.add_argument("--cast", action="store_true", help="print the cast and exit")
    a = ap.parse_args()

    if a.cast:
        for k, c in CAST.items():
            print("%-9s %-36s speed %.2f  %s" % (k, "+".join("%s %.0f%%" % (v, 100 * w / sum(c["voice"].values())) for v, w in c["voice"].items()), c["speed"], c["why"]))
        return

    jobs = [(n, c, t, a.out) for n, c, t in campaign_lines(ROOT)]
    if a.next_build:
        nb = os.path.abspath(a.next_build)
        if nb.startswith(os.path.join(ROOT, "Tools", "Audio", "Generated")):
            raise SystemExit("--next-build must be outside Tools/Audio/Generated (the importer would pull those files into the game)")
        live = {j[0] for j in jobs}
        jobs += [(n, c, t, nb) for n, c, t in next_build_lines(ROOT) if n not in live]
    if a.names:
        jobs = [j for j in jobs if j[0] in set(a.names)]
        if not jobs:
            raise SystemExit("no such line")

    if not a.check:
        voicer = Voicer()
        for name, cast_id, text, out in jobs:
            os.makedirs(out, exist_ok=True)
            x = master(voicer.line(name, cast_id, text), name, CAST[cast_id]["fx"])
            dsp.write_wav(os.path.join(out, name + ".wav"), x, seed=dsp.seed_for(name))
            print("  %-22s %-8s %5.2fs  %s" % (name, cast_id, len(x) / SR, text), flush=True)

    bad = []
    for out in sorted({j[3] for j in jobs}):
        rows = [(n, t) for n, c, t, o in jobs if o == out]
        bad += report(rows, out)
        if a.asr:
            transcribe(a.asr, rows, out)
    if bad:
        print("check: " + ", ".join(bad))


if __name__ == "__main__":
    main()
