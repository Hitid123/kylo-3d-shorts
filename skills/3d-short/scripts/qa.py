"""qa — look at the pixels before the user does.

  uv run --with pillow --with numpy python qa.py preview/            # stills from `build.py ... preview`
  uv run --with pillow --with numpy python qa.py render.mp4 [--every 0.5]

Flags frames that are almost certainly broken and writes a contact sheet (qa_sheet.jpg next to the input)
that Claude must open and inspect (hands, faces, things floating or going through each other):
  * MAGENTA patches  -> a missing texture (Blender paints them pink) — never ship this;
  * black / white frames -> no camera, a light at 0, an exposure blow-out;
  * frozen video     -> the same picture for > 3 s (an animation or a camera that didn't key).
Exit code 1 if anything is flagged.
"""
import argparse
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw


def frames_from_video(path, every):
    tmp = tempfile.mkdtemp(prefix="qa_")
    subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps=1/{every},scale=360:-2",
                    os.path.join(tmp, "q%05d.png")], check=True)
    fs = sorted(glob.glob(os.path.join(tmp, "q*.png")))
    return [(f, (i + 0.5) * every) for i, f in enumerate(fs)]


def analyse(img):
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    magenta = ((r > 170) & (b > 150) & (g < 110) & (np.abs(r - b) < 90)).mean()
    mean = a.mean()
    return magenta, mean, a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="folder of stills or a video")
    ap.add_argument("--every", type=float, default=0.5, help="seconds between sampled video frames")
    ap.add_argument("--cols", type=int, default=8)
    a = ap.parse_args()

    if os.path.isdir(a.src):
        items = [(f, os.path.basename(f)) for f in sorted(glob.glob(os.path.join(a.src, "*.png")))]
        out_dir = a.src
    else:
        items = [(f, f"{t:.1f}s") for f, t in frames_from_video(a.src, a.every)]
        out_dir = os.path.dirname(os.path.abspath(a.src))
    if not items:
        sys.exit("qa: no frames found")

    problems, thumbs, prev, same_since = [], [], None, None
    for f, label in items:
        im = Image.open(f)
        mag, mean, arr = analyse(im)
        if mag > 0.002:
            problems.append(f"{label}: MAGENTA {mag * 100:.1f}% of the frame -> missing texture")
        if mean < 8:
            problems.append(f"{label}: black frame")
        if mean > 247:
            problems.append(f"{label}: white frame")
        small = np.asarray(im.convert("L").resize((48, 85))).astype(np.int16)
        if prev is not None and np.abs(small - prev).mean() < 0.6:
            same_since = same_since or label
        else:
            if same_since and not os.path.isdir(a.src):
                t0, t1 = float(same_since[:-1]), float(label[:-1])
                if t1 - t0 > 3.0:
                    problems.append(f"{same_since}-{label}: picture frozen for {t1 - t0:.1f}s")
            same_since = None
        prev = small
        th = im.convert("RGB")
        th.thumbnail((240, 427))
        d = ImageDraw.Draw(th)
        d.rectangle((0, 0, 70, 16), fill=(0, 0, 0))
        d.text((3, 2), label[:12], fill=(255, 255, 0))
        if mag > 0.002:
            d.rectangle((0, 0, th.width - 1, th.height - 1), outline=(255, 0, 255), width=4)
        thumbs.append(th)

    W = max(t.width for t in thumbs)
    H = max(t.height for t in thumbs)
    cols = min(a.cols, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * W, rows * H), (20, 20, 20))
    for i, t in enumerate(thumbs):
        sheet.paste(t, ((i % cols) * W, (i // cols) * H))
    out = os.path.join(out_dir, "qa_sheet.jpg")
    sheet.save(out, quality=85)
    print("sheet:", out, f"({len(thumbs)} frames) — open it and check hands, faces, contacts, scale")
    for p in problems:
        print("QA:", p)
    print("QA: ok" if not problems else f"QA: {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
