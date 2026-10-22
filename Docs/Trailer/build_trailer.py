"""Builds Docs/Trailer/Last_Contract_Trailer.mp4 from the existing stills, music and voice lines.

No rendering: every shot is a slow camera move over a 2560x1440 still (crop and scale per frame),
hard cuts land on gunshots, and the title cards are drawn with PIL. Audio is mixed in one ffmpeg
filter graph: music ducked under the voice lines, gunshots on the cuts, loudness normalised to -14 LUFS.

    python3 Docs/Trailer/build_trailer.py            # from the repo root; needs ffmpeg, Pillow and numpy
"""
import json
import os
import subprocess
import sys
import tempfile
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(ROOT, "Docs", "Trailer")
OUT = os.path.join(OUT_DIR, "Last_Contract_Trailer.mp4")
WORK = os.environ.get("TRAILER_WORK") or tempfile.mkdtemp(prefix="trailer_")
SCREENS = os.path.join(ROOT, "Docs", "Screens")
AFTER = os.path.join(ROOT, "Docs", "Renders", "BeforeAfter")
AUDIO = os.path.join(ROOT, "Tools", "Audio", "Generated")
VOICE = os.path.join(AUDIO, "Voice")

W, H, FPS = 1920, 1080, 30
BAR = 110  # letterbox bar height, about 2.2:1 inside the 16:9 frame
FONT_DIR = "/usr/share/fonts/opentype/inter"
MAGENTA = (255, 64, 170)
AMBER = (255, 178, 84)
GREY = (150, 146, 156)


def S(name):
    return os.path.join(SCREENS, name)


def A(name):
    return os.path.join(AFTER, name)


# Shots: (start, end, kind, args). Still args: path, (zoom0, cx0, cy0), (zoom1, cx1, cy1), options.
# zoom 1.0 shows the whole still; cx/cy are the crop centre as fractions of the still.
SHOTS = [
    (0.0, 3.0, "card", "open"),
    (3.0, 8.5, "still", (S("03_Staging_Armory.jpg"), (1.05, .50, .52), (1.22, .55, .50), {"fade": 18})),
    (8.5, 15.5, "still", (S("08_Armory_M4_Hero.jpg"), (1.10, .46, .52), (1.30, .52, .50), {"fade": 10})),
    (15.5, 20.2, "still", (S("07_Staging_Range.jpg"), (1.18, .40, .55), (1.18, .60, .55), {"fade": 10, "fadeout": 10})),
    (20.2, 23.6, "card", "ledger"),
    (23.6, 25.1, "black", None),
    (25.1, 29.0, "still", (A("20_Neon_Canyon_after.jpg"), (1.25, .50, .55), (1.08, .50, .52), {"flash": True})),
    (29.0, 32.4, "still", (S("21_Neon_WetStreet.jpg"), (1.20, .42, .55), (1.20, .58, .55), {})),
    (32.4, 35.6, "still", (S("22_Neon_ClubEntrance.jpg"), (1.05, .55, .50), (1.25, .62, .48), {})),
    (35.6, 38.0, "still", (S("04_VelvetClub_FirstPerson.jpg"), (1.06, .50, .50), (1.14, .50, .48), {"flash": True, "shake": 6})),
    (38.0, 41.6, "still", (S("02_VelvetClub_DanceFloor.jpg"), (1.30, .50, .45), (1.10, .50, .50), {})),
    (41.6, 45.8, "still", (S("01_VelvetClub_Street.jpg"), (1.08, .50, .50), (1.28, .55, .45), {})),
    (45.8, 49.2, "still", (S("11_NightjarGarage_Ramp.jpg"), (1.10, .50, .55), (1.30, .50, .52), {"flash": True})),
    (49.2, 52.4, "still", (A("12_NightjarGarage_ParkingRow_after.jpg"), (1.20, .58, .55), (1.20, .42, .55), {})),
    (52.4, 55.4, "still", (S("10_NightjarGarage_RoofDeck.jpg"), (1.05, .50, .50), (1.22, .45, .52), {})),
    (55.4, 58.8, "still", (S("13_NightjarGarage_ObjectiveC.jpg"), (1.25, .40, .55), (1.12, .50, .55), {})),
    (58.8, 63.0, "still", (A("05_Ironwood_GoldenHour_after.jpg"), (1.05, .50, .50), (1.22, .62, .48), {"flash": True})),
    (63.0, 65.4, "still", (S("06_Ironwood_ObjectiveA.jpg"), (1.20, .45, .52), (1.20, .58, .52), {})),
    (65.4, 71.2, "still", (S("09_Ironwood_Watchtower_Backlit.jpg"), (1.08, .50, .55), (1.35, .50, .42), {})),
]
# Montage: eight quick cuts, one gunshot each.
MONTAGE = [
    (A("20_Neon_Canyon_after.jpg"), (1.45, .55, .55), (1.60, .55, .55)),
    (S("08_Armory_M4_Hero.jpg"), (1.50, .48, .50), (1.65, .48, .50)),
    (S("02_VelvetClub_DanceFloor.jpg"), (1.40, .50, .50), (1.55, .52, .50)),
    (S("10_NightjarGarage_RoofDeck.jpg"), (1.45, .50, .55), (1.60, .48, .55)),
    (S("04_VelvetClub_FirstPerson.jpg"), (1.25, .62, .58), (1.40, .62, .58)),
    (S("21_Neon_WetStreet.jpg"), (1.50, .50, .55), (1.65, .50, .55)),
    (S("11_NightjarGarage_Ramp.jpg"), (1.45, .50, .55), (1.60, .50, .55)),
    (S("09_Ironwood_Watchtower_Backlit.jpg"), (1.50, .50, .40), (1.70, .50, .40)),
]
MONTAGE_START, MONTAGE_STEP = 71.2, 0.65
for i, (p, a, b) in enumerate(MONTAGE):
    t0 = MONTAGE_START + i * MONTAGE_STEP
    SHOTS.append((t0, t0 + MONTAGE_STEP, "still", (p, a, b, {"flash": True, "shake": 9})))
MONTAGE_END = MONTAGE_START + len(MONTAGE) * MONTAGE_STEP  # 76.4
SHOTS += [
    (MONTAGE_END, 79.2, "black", None),
    (79.2, 88.5, "card", "title"),
]
DURATION = 88.5

# Audio events: (time, file, gain dB, bus). Bus "voice" ducks the music.
VO = [
    (0.8, "VO_M1_I0"), (8.6, "VO_M1_I1"), (16.0, "VO_M1_I2"),
    (20.4, "VO_M1_Boss"), (23.7, "VO_M1_Andrew_Boss"),
    (25.8, "VO_M2_I0"), (32.6, "VO_M2_I2"), (38.2, "VO_M2_Boss"), (42.8, "VO_M2_Andrew_Boss"),
    (46.0, "VO_M3_I2"), (52.6, "VO_M3_Boss"), (54.9, "VO_M3_Andrew_Boss"),
    (59.0, "VO_M4_I0"), (65.6, "VO_M4_Boss"),
    (76.7, "VO_M4_Andrew_Boss"),
]
SHOTS_SFX = ["FireMagnum", "FireRifle", "FireShotgun", "FireSniper", "FireRifle_01", "FireDMR", "FireMagnum_01", "FireLMG"]


def font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def tracked(draw, text, fnt, tracking):
    """Width of text drawn with extra letter spacing."""
    return sum(draw.textlength(c, font=fnt) for c in text) + tracking * (len(text) - 1)


def draw_tracked(img, y, text, fnt, fill, tracking, glow=None, glow_radius=14):
    layer = Image.new("RGB", img.size, (0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = (img.width - tracked(d, text, fnt, tracking)) / 2
    for c in text:
        d.text((x, y), c, font=fnt, fill=fill)
        x += d.textlength(c, font=fnt) + tracking
    if glow:
        tint = Image.new("RGB", img.size, glow)
        mask = layer.convert("L").filter(ImageFilter.GaussianBlur(glow_radius))
        halo = Image.composite(tint, Image.new("RGB", img.size, (0, 0, 0)), mask)
        img.paste(Image.fromarray(np.clip(np.asarray(img, np.int16) + np.asarray(halo, np.int16) * 2, 0, 255).astype(np.uint8)))
    img.paste(Image.fromarray(np.maximum(np.asarray(img), np.asarray(layer))))


def make_card(kind):
    img = Image.new("RGB", (W, H), (4, 3, 6))
    if kind == "open":
        draw_tracked(img, 470, "FIVE YEARS AGO", font("InterDisplay-Medium.otf", 30), (225, 220, 228), 14)
        draw_tracked(img, 530, "ANDREW WALKED AWAY", font("InterDisplay-Bold.otf", 52), (240, 236, 242), 10, glow=AMBER, glow_radius=10)
    elif kind == "ledger":
        draw_tracked(img, 455, "THE LEDGER", font("InterDisplay-Medium.otf", 34), (225, 220, 228), 16)
        draw_tracked(img, 515, "ALWAYS COLLECTS", font("InterDisplay-Black.otf", 74), (246, 240, 246), 12, glow=MAGENTA, glow_radius=16)
    elif kind == "title":
        draw_tracked(img, 380, "ANDREW'S AIRSOFT", font("InterDisplay-SemiBold.otf", 34), AMBER, 18, glow=AMBER, glow_radius=8)
        draw_tracked(img, 440, "LAST CONTRACT", font("InterDisplay-Black.otf", 128), (250, 244, 250), 16, glow=MAGENTA, glow_radius=22)
        d = ImageDraw.Draw(img)
        d.line([(W / 2 - 260, 612), (W / 2 + 260, 612)], fill=MAGENTA, width=2)
        draw_tracked(img, 640, "SINGLE-PLAYER", font("InterDisplay-Medium.otf", 26), GREY, 14)
    return img


_cache = {}


def still(path):
    if path not in _cache:
        im = Image.open(path).convert("RGB")
        if im.size != (2560, 1440):
            im = im.resize((2560, 1440), Image.LANCZOS)
        _cache[path] = im
    return _cache[path]


def ease(u):
    return u * u * (3 - 2 * u)


def find_shot(t):
    for s in SHOTS:
        if s[0] <= t < s[1]:
            return s
    return SHOTS[-1]


_cards = {}
_grain = None


def render(frame):
    global _grain
    if _grain is None:
        rng = np.random.default_rng(7)
        _grain = [rng.normal(0, 5.0, (H, W, 1)).astype(np.int16) for _ in range(6)]
    t = frame / FPS
    t0, t1, kind, args = find_shot(t)
    u = (t - t0) / max(t1 - t0, 1e-6)
    local = frame - int(round(t0 * FPS))
    remaining = int(round(t1 * FPS)) - frame
    if kind == "black":
        img = np.zeros((H, W, 3), np.int16)
    elif kind == "card":
        if args not in _cards:
            _cards[args] = np.asarray(make_card(args), np.int16)
        img = _cards[args].copy()
        fade_in, fade_out = (12, 18) if args != "title" else (6, 45)
        a = min(1.0, local / fade_in, remaining / fade_out)
        if args == "title":
            img = (img * max(a, 0.0)).astype(np.int16)
            # A slow push on the title: scale up 4% over the hold.
            if u > 0:
                z = 1.0 + 0.04 * u
                pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
                cw, ch = W / z, H / z
                pil = pil.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
                img = np.asarray(pil, np.int16)
        else:
            img = (img * max(a, 0.0)).astype(np.int16)
    else:
        path, a, b, opt = args
        e = ease(u)
        z = a[0] + (b[0] - a[0]) * e
        cx = a[1] + (b[1] - a[1]) * e
        cy = a[2] + (b[2] - a[2]) * e
        src = still(path)
        cw, ch = 2560 / z, 1440 / z
        x0 = min(max(cx * 2560 - cw / 2, 0), 2560 - cw)
        y0 = min(max(cy * 1440 - ch / 2, 0), 1440 - ch)
        if opt.get("shake"):
            amp = opt["shake"] * max(0.0, 1.0 - local / 8.0) + 1.5
            x0 = min(max(x0 + amp * np.sin(frame * 2.7), 0), 2560 - cw)
            y0 = min(max(y0 + amp * np.cos(frame * 3.3), 0), 1440 - ch)
        pil = src.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
        img = np.asarray(pil, np.int16)
        # Grade: lift contrast slightly and cool the shadows for the noir look.
        img = np.clip((img - 128) * 1.06 + 124, 0, 255)
        img[..., 2] = np.clip(img[..., 2] + 4, 0, 255)
        if opt.get("fade") and local < opt["fade"]:
            img = img * (local / opt["fade"])
        if opt.get("fadeout") and remaining < opt["fadeout"]:
            img = img * (remaining / opt["fadeout"])
        if opt.get("flash") and local < 3:
            img = img + (255 - img) * (0.45, 0.22, 0.08)[local]
        img = img.astype(np.int16)
    img = img + _grain[frame % len(_grain)]
    img[:BAR] = 0
    img[H - BAR:] = 0
    return np.clip(img, 0, 255).astype(np.uint8).tobytes()


def cut_times():
    """Times of the hard cuts that get a gunshot: every shot with a flash."""
    return [s[0] for s in SHOTS if s[2] == "still" and s[3][3].get("flash")]


def build_audio(path):
    inputs, filters = [], []

    def add(file, t, gain_db, label):
        inputs.extend(["-i", file])
        n = len(inputs) // 2 - 1
        filters.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain_db}dB,adelay={int(t * 1000)}|{int(t * 1000)}[{label}]")
        return label

    add(os.path.join(AUDIO, "MenuMusic.wav"), 0.0, -4, "m0r")
    add(os.path.join(AUDIO, "ClubMusic.wav"), 25.1, -2, "m1r")
    add(os.path.join(AUDIO, "PostRoundMusic.wav"), 79.2, -3, "m2r")
    # Shape the music beds: menu fades out into the black, club runs to the montage, post-round under the title.
    filters.append("[m0r]afade=t=in:st=0:d=1.5,afade=t=out:st=23.4:d=1.6[m0]")
    filters.append("[m1r]afade=t=out:st=76.2:d=0.4[m1]")
    filters.append("[m2r]afade=t=in:st=79.2:d=0.3,afade=t=out:st=86.0:d=2.5[m2]")
    music = ["m0", "m1", "m2"]
    voices = [add(os.path.join(VOICE, name + ".wav"), t, 2, f"v{i}") for i, (t, name) in enumerate(VO)]
    sfx = []
    for i, t in enumerate(cut_times()):
        sfx.append(add(os.path.join(AUDIO, SHOTS_SFX[i % len(SHOTS_SFX)] + ".wav"), max(t - 0.02, 0), -3, f"s{i}"))
    sfx.append(add(os.path.join(AUDIO, "SlowMoHeartbeat.wav"), 20.2, -4, "hb"))
    sfx.append(add(os.path.join(AUDIO, "ReplayWhoosh.wav"), 78.0, -2, "wh"))
    sfx.append(add(os.path.join(AUDIO, "ReplayImpact.wav"), 79.15, 0, "im"))
    n_music, n_voice, n_sfx = len(music), len(voices), len(sfx)
    filters.append("".join(f"[{m}]" for m in music) + f"amix=inputs={n_music}:normalize=0[music]")
    filters.append("".join(f"[{v}]" for v in voices) + f"amix=inputs={n_voice}:normalize=0,asplit=2[voice][key]")
    filters.append("".join(f"[{s}]" for s in sfx) + f"amix=inputs={n_sfx}:normalize=0[sfx]")
    filters.append("[music][key]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350:makeup=1[ducked]")
    filters.append(f"[ducked][voice][sfx]amix=inputs=3:normalize=0,atrim=0:{DURATION},afade=t=out:st={DURATION - 1.2}:d=1.2[pre]")
    graph = ";".join(filters)

    raw = os.path.join(WORK, "mix_raw.wav")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[pre]",
                    "-ar", "48000", "-c:a", "pcm_s24le", raw], check=True)
    # Two-pass loudness normalisation to -14 LUFS integrated, -1.5 dBTP.
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", raw, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                            "-f", "null", "-"], capture_output=True, text=True).stderr
    m = json.loads(probe[probe.rindex("{"):probe.rindex("}") + 1])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", raw, "-af", ln, "-ar", "48000", "-c:a", "pcm_s16le", path], check=True)


def main():
    os.makedirs(WORK, exist_ok=True)
    audio = os.path.join(WORK, "mix.wav")
    build_audio(audio)
    print("audio done")
    frames = int(DURATION * FPS)
    enc = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                            "-i", audio,
                            "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-maxrate", "4M", "-bufsize", "8M",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                            "-shortest", OUT], stdin=subprocess.PIPE)
    with Pool(int(os.environ.get("TRAILER_JOBS", "3"))) as pool:
        for i, buf in enumerate(pool.imap(render, range(frames), chunksize=8)):
            enc.stdin.write(buf)
            if i % 300 == 0:
                print(f"frame {i}/{frames}", flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit("encode failed")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
