"""Measure a reference short (or your own render) so you can match its rhythm and look.

  uv run --with numpy --with pillow python measure.py video.mp4 [words.json]

Prints: duration, number of cuts and average shot length (ffmpeg scene detection), brightness/saturation,
a 6-colour palette, integrated loudness, and words per second if a words.json is given.
Run it on the reference and on your render: the differences are your to-do list.
"""
import json
import re
import subprocess
import sys

import numpy as np
from PIL import Image


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def main():
    v = sys.argv[1]
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", v]).stdout)
    sc = run(["ffmpeg", "-hide_banner", "-i", v, "-vf", "select='gt(scene,0.32)',showinfo", "-an", "-f", "null", "-"]).stderr
    cuts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", sc)]
    shots = np.diff([0] + cuts + [dur]) if True else []
    # palette + brightness from 1 frame per second
    w = 96
    probe = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", v]).stdout.strip()
    W, H = map(int, probe.split(","))
    h = int(round(H * w / W / 2) * 2) if False else int(H * w / W)
    data = subprocess.run(["ffmpeg", "-v", "error", "-i", v, "-vf", f"fps=1,scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True).stdout
    px = np.frombuffer(data, np.uint8).reshape(-1, 3).astype(np.float32)
    hsv = np.array(Image.fromarray(px.reshape(1, -1, 3).astype(np.uint8)).convert("HSV")).reshape(-1, 3)
    rng = np.random.default_rng(0)
    sample = px[rng.choice(len(px), min(20000, len(px)), replace=False)]
    cent = sample[rng.choice(len(sample), 6, replace=False)]
    for _ in range(15):
        lab = np.argmin(((sample[:, None] - cent[None]) ** 2).sum(-1), 1)
        cent = np.array([sample[lab == k].mean(0) if (lab == k).any() else cent[k] for k in range(6)])
    share = np.bincount(lab, minlength=6) / len(lab)
    order = np.argsort(-share)
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", run(["ffmpeg", "-hide_banner", "-nostats", "-i", v, "-af", "ebur128", "-f", "null", "-"]).stderr)
    print(f"duration      {dur:.1f} s")
    print(f"cuts          {len(cuts)}  (avg shot {np.mean(shots):.1f} s, median {np.median(shots):.1f} s)")
    print(f"brightness    {hsv[:, 2].mean() / 255:.2f}   saturation {hsv[:, 1].mean() / 255:.2f}")
    print("palette       " + "  ".join(f"#{int(c[0]):02X}{int(c[1]):02X}{int(c[2]):02X} {share[k] * 100:.0f}%" for k, c in ((k, cent[k]) for k in order)))
    print(f"loudness      {lufs[-1] if lufs else 'n/a'} LUFS integrated")
    if len(sys.argv) > 2:
        words = json.load(open(sys.argv[2]))
        span = words[-1]["e"] - words[0]["s"]
        print(f"speech        {len(words) / span:.2f} words/s over {span:.1f} s")


if __name__ == "__main__":
    main()
