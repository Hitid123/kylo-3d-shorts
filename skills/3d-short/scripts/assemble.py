"""Final assembly: render + voice + captions + SFX + (optional) music -> upload-ready vertical mp4.

  uv run --with pillow --with numpy python assemble.py \
      --video render.mp4 --words words.json [--voice voice.wav] \
      [--sfx render.sfx.json --sfx-lib sfx_dir] [--music music.mp3] [--out final.mp4] [--case lower|upper|keep]

What it does (all measured choices for this format, change with flags if needed):
- captions: 1-3 words per chunk, white heavy sans with a thick black outline, centred at 62 % height
  (inside the Shorts safe zone), switch exactly on the spoken word;
- look: subtle vignette (no animated grain by default: it reads as flicker on phones; --grain to add it);
- SFX: dropped on the frames recorded by s3d.py (render.sfx.json). With --sfx-lib (made by `eleven.py sfx`)
  every cue uses its ElevenLabs sound; cues without one fall back to a small built-in synth;
- voice: optional, so a cut can be checked before the narration exists;
- music: optional, ducked under the voice with a sidechain compressor; use only tracks you own or
  that are licensed for YouTube (a claimed song can block a Short over 1 minute worldwide);
- loudness: -14 LUFS integrated, true peak <= -1.5 dBTP (what YouTube normalises to).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "assets", "fonts", "Montserrat-Variable.ttf")
SR = 48000


# ---------------------------------------------------------------- SFX (synthesised, no licensing issues)
def _env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(d, 1e-4))


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def _lp(x, k):
    # cheap one-pole low-pass, k in (0,1): smaller = darker
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += k * (v - acc)
        y[i] = acc
    return y


def synth_sfx(kind, seed=1):
    n = int(SR * 0.9)
    t = np.arange(n) / SR
    if kind == "thud":
        f = 55 + 90 * np.exp(-t * 30)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.16) + 0.25 * _lp(_noise(n, seed), 0.08) * _env(n, 0.001, 0.05)
    elif kind == "whoosh":
        nz = _noise(n, seed)
        sweep = np.linspace(0.02, 0.35, n)
        y = np.empty(n)
        acc = 0.0
        for i in range(n):
            acc += sweep[i] * (nz[i] - acc)
            y[i] = acc
        x = y * np.sin(np.pi * np.clip(t / 0.5, 0, 1)) ** 2
    elif kind == "pop":
        f = 900 - 500 * np.clip(t / 0.08, 0, 1)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.001, 0.04)
    elif kind in ("crunch", "crack"):
        x = _noise(n, seed) * _env(n, 0.001, 0.09 if kind == "crunch" else 0.04)
        x = x - _lp(x, 0.1)  # high-passed crackle
        x += 0.5 * np.sin(2 * np.pi * 70 * t) * _env(n, 0.001, 0.1)
    elif kind == "dig":
        x = np.zeros(n)
        for k in range(3):
            s = int(k * 0.22 * SR)
            m = min(n - s, int(0.18 * SR))
            x[s:s + m] += _lp(_noise(m, seed + k), 0.25) * _env(m, 0.005, 0.06)
    elif kind == "pour":
        x = _lp(_noise(n, seed), 0.15) * (0.6 + 0.4 * np.sin(2 * np.pi * 7 * t)) * np.sin(np.pi * np.clip(t / 0.9, 0, 1))
    else:
        x = _noise(n, seed) * _env(n, 0.001, 0.05)
    x = x / (np.abs(x).max() + 1e-9) * 0.8
    return x


def write_wav(path, x):
    x16 = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(x16.tobytes())


# ---------------------------------------------------------------- captions
def chunk_words(words, max_words=3, max_gap=0.25):
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        punct = re.search(r"[.,!?;:—]$", w["w"])
        gap = (nxt["s"] - w["e"]) if nxt else 9
        if len(cur) >= max_words or punct or gap > max_gap or not nxt:
            chunks.append(cur)
            cur = []
    out = []
    for k, c in enumerate(chunks):
        s = c[0]["s"]
        e = chunks[k + 1][0]["s"] if k + 1 < len(chunks) else c[-1]["e"] + 0.4
        e = min(e, c[-1]["e"] + 0.6)
        out.append({"text": " ".join(x["w"] for x in c), "s": s, "e": max(e, s + 0.25)})
    return out


def caption_png(text, path, W, H, case="lower", y_frac=0.62, size_frac=0.08):
    text = re.sub(r"[.,!?;:]+$", "", text)
    text = text.lower() if case == "lower" else text.upper() if case == "upper" else text
    size = int(W * size_frac)
    font = ImageFont.truetype(FONT, size)
    try:
        font.set_variation_by_name("ExtraBold")
    except Exception:
        pass
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    stroke = max(4, size // 9)
    bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke)
    tw = bbox[2] - bbox[0]
    while tw > W * 0.9 and size > 30:
        size -= 4
        font = ImageFont.truetype(FONT, size)
        try:
            font.set_variation_by_name("ExtraBold")
        except Exception:
            pass
        bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke)
        tw = bbox[2] - bbox[0]
    x = (W - tw) / 2 - bbox[0]
    y = H * y_frac - (bbox[3] - bbox[1]) / 2 - bbox[1]
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x, y + size * 0.06), text, font=font, fill=(0, 0, 0, 120), stroke_width=stroke, stroke_fill=(0, 0, 0, 120))
    img = Image.alpha_composite(img, shadow)
    ImageDraw.Draw(img).text((x, y), text, font=font, fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    img.save(path)


def probe(path, entry):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0" if entry != "duration" else "v:0", "-show_entries",
                           f"stream={entry}" if entry != "duration" else "format=duration", "-of", "csv=p=0", path],
                          capture_output=True, text=True).stdout.strip()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--voice", default=None)
    ap.add_argument("--sfx-lib", default=None, help="folder with manifest.json from eleven.py sfx")
    ap.add_argument("--grain", action="store_true")
    ap.add_argument("--lufs", type=float, default=None, help="loudness target (default -14 with voice, -20 without)")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--words", required=True)
    ap.add_argument("--sfx", default=None)
    ap.add_argument("--music", default=None)
    ap.add_argument("--music-db", type=float, default=-22.0, help="music level before ducking")
    ap.add_argument("--sfx-db", type=float, default=-10.0)
    ap.add_argument("--out", default="final.mp4")
    ap.add_argument("--case", default=None, help="lower | upper | as-is (default depends on --style)")
    ap.add_argument("--style", default="bold", choices=["bold", "explainer"],
                    help="bold: big centred 1-3 word captions (cutaway builds); explainer: small white sentence-case "
                         "lines low in the frame, up to 4 words (realistic 'what if' explainers)")
    ap.add_argument("--no-look", action="store_true")
    a = ap.parse_args()

    W, H = map(int, probe(a.video, "width,height").split(","))
    vdur = float(probe(a.video, "duration"))
    words = json.load(open(a.words))
    tmp = tempfile.mkdtemp(prefix="s3d_")

    # captions -> one RGBA overlay track
    style = {"bold": dict(max_words=3, y_frac=0.62, size_frac=0.08, case="lower"),
             "explainer": dict(max_words=4, y_frac=0.80, size_frac=0.056, case="as-is")}[a.style]
    case = a.case or style["case"]
    chunks = [] if a.no_captions else chunk_words(words, max_words=style["max_words"])
    blank = os.path.join(tmp, "blank.png")
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    lines, t = [], 0.0
    for i, c in enumerate(chunks):
        if c["s"] > t + 0.01:
            lines += [f"file '{blank}'", f"duration {c['s'] - t:.3f}"]
        p = os.path.join(tmp, f"c{i:04d}.png")
        caption_png(c["text"], p, W, H, case, y_frac=style["y_frac"], size_frac=style["size_frac"])
        lines += [f"file '{p}'", f"duration {c['e'] - c['s']:.3f}"]
        t = c["e"]
    total = max(vdur, t + 0.3)
    lines += [f"file '{blank}'", f"duration {max(0.1, total - t):.3f}", f"file '{blank}'"]
    lst = os.path.join(tmp, "caps.txt")
    open(lst, "w").write("\n".join(lines))
    caps = os.path.join(tmp, "caps.mov")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-vf", "fps=30,format=argb",
                    "-c:v", "qtrle", caps], check=True)

    # SFX
    voice_in = ["-i", a.voice] if a.voice else ["-f", "lavfi", "-t", f"{total:.3f}", "-i", f"anullsrc=r={SR}:cl=stereo"]
    inputs = ["-i", a.video, "-i", caps, *voice_in]
    fc = []
    look = "" if a.no_look else "vignette=angle=0.28," + ("noise=alls=2:allf=t," if a.grain else "")
    fc.append(f"[0:v]{look}tpad=stop_mode=clone:stop_duration=5,trim=duration={total:.3f}[base]")
    fc.append("[base][1:v]overlay=format=auto[v]")
    fc.append(f"[2:a]aresample={SR},aformat=channel_layouts=stereo,apad=whole_dur={total:.3f}[voice]")
    mix = ["[voice]"]
    k = 3
    if a.sfx and os.path.exists(a.sfx):
        cues = json.load(open(a.sfx))
        lib = {}
        if a.sfx_lib and os.path.exists(os.path.join(a.sfx_lib, "manifest.json")):
            lib = json.load(open(os.path.join(a.sfx_lib, "manifest.json")))
        made = {}
        for j, c in enumerate(cues):
            key = c.get("prompt") or c["sfx"]
            if key in lib and os.path.exists(os.path.join(a.sfx_lib, lib[key])):
                src = os.path.join(a.sfx_lib, lib[key])
            else:
                kind = c["sfx"]
                if kind not in made:
                    made[kind] = os.path.join(tmp, f"sfx_{kind}.wav")
                    write_wav(made[kind], synth_sfx(kind, seed=len(made)))
                src = made[kind]
            inputs += ["-i", src]
            ms = int(max(0, c["t"]) * 1000)
            gain = a.sfx_db + float(c.get("gain", 0))
            fc.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo,volume={gain}dB,adelay={ms}|{ms}[s{j}]")
            mix.append(f"[s{j}]")
            k += 1
    if a.music:
        inputs += ["-stream_loop", "-1", "-i", a.music]
        fc.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo,volume={a.music_db}dB,atrim=duration={total:.3f},"
                  f"afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[mus]")
        fc.append("[voice]asplit=2[voice1][vsc]")
        mix[0] = "[voice1]"
        if a.voice:
            fc.append("[mus][vsc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[duck]")
            mix.append("[duck]")
        else:
            fc.append("[vsc]anullsink")
            mix.append("[mus]")
        k += 1
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,loudnorm=I={a.lufs if a.lufs is not None else (-14 if a.voice else -20)}:TP=-2:LRA=11,alimiter=limit=0.84:level=disabled[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-t", f"{total:.3f}", a.out], check=True)
    print(f"done: {a.out}  ({total:.1f}s, {len(chunks)} captions)")


if __name__ == "__main__":
    main()
