"""Word timings for a short — the clock every animation is synced to.

  python voice.py plan  script.txt out_dir [--wps 2.7] [--beat-pause 0.45]
        -> out_dir/words.json estimated from the text (no audio). Lets you build and preview the animation
           before the narration exists; rebuild after `eleven.py voice` to lock it to the real voice.
  python voice.py words voice.mp3 out_dir [--lang en]
        -> out_dir/words.json from your own recording (Whisper word timestamps) + voice.wav (copy for assemble.py)
           + script.txt (one sentence per line) if the folder has none — so "drop a recording in the folder" works
           without writing anything.

ElevenLabs narration (recommended): `python eleven.py voice script.txt out_dir` writes voice.wav + words.json directly.
"""
from __future__ import annotations

import argparse
import json
import os
import re


def plan_words(lines, wps=2.7, beat_pause=0.45, lead_in=0.3):
    """Estimate word timings: ~2.7 words/s (measured ZackD pace), longer words take longer, pauses at punctuation."""
    t, out = lead_in, []
    base = 1.0 / wps
    for line in lines:
        for w in line.split():
            core = re.sub(r"[^\w']", "", w)
            dur = base * (0.65 + 0.07 * min(len(core), 12))
            out.append({"w": w, "s": round(t, 3), "e": round(t + dur * 0.92, 3)})
            t += dur
            if re.search(r"[,;:—]$", w):
                t += 0.18
            elif re.search(r"[.!?]$", w):
                t += 0.32
        t += beat_pause
    return out


def whisper_words(audio, lang=None):
    """Word timestamps: mlx-whisper on Apple Silicon, faster-whisper elsewhere."""
    try:
        import mlx_whisper  # type: ignore
        r = mlx_whisper.transcribe(audio, path_or_hf_repo="mlx-community/whisper-large-v3-turbo", word_timestamps=True, language=lang)
        return [{"w": w["word"].strip(), "s": round(w["start"], 3), "e": round(w["end"], 3)} for s in r["segments"] for w in s.get("words", [])]
    except ImportError:
        from faster_whisper import WhisperModel  # type: ignore
        m = WhisperModel("small", compute_type="int8")
        segs, _ = m.transcribe(audio, word_timestamps=True, language=lang)
        return [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in s.words]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "words"])
    ap.add_argument("src")
    ap.add_argument("out_dir")
    ap.add_argument("--wps", type=float, default=2.7)
    ap.add_argument("--beat-pause", type=float, default=0.45)
    ap.add_argument("--lang", default=None)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    if a.cmd == "plan":
        lines = [l.strip() for l in open(a.src) if l.strip()]
        words = plan_words(lines, a.wps, a.beat_pause)
    else:
        words = whisper_words(a.src, a.lang)
        import subprocess
        wav = os.path.join(a.out_dir, "voice.wav")
        if os.path.abspath(a.src) != os.path.abspath(wav):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-ar", "48000", "-ac", "1", wav], check=True)
        sp = os.path.join(a.out_dir, "script.txt")
        if not os.path.exists(sp):
            text = " ".join(w["w"] for w in words)
            lines = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
            open(sp, "w").write("\n".join(lines) + "\n")
            print(f"script.txt written from the recording ({len(lines)} beats) — check the line breaks = beats")
    with open(os.path.join(a.out_dir, "words.json"), "w") as f:
        json.dump(words, f, indent=0, ensure_ascii=False)
    print(f"words: {len(words)}  duration ~{words[-1]['e'] if words else 0:.1f}s")


if __name__ == "__main__":
    main()
