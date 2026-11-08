"""Print the path of a Blender executable (4.2+), or exit 1 with install hints.

  python find_blender.py            -> /Applications/Blender.app/Contents/MacOS/Blender
Set BLENDER=/path/to/blender to override.
"""
import glob
import os
import shutil
import subprocess
import sys

CANDIDATES = [
    os.environ.get("BLENDER", ""),
    shutil.which("blender") or "",
    "/Applications/Blender.app/Contents/MacOS/Blender",
    os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender"),
    os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/Blender/Blender.app/Contents/MacOS/Blender"),
    "/snap/bin/blender",
    "/usr/bin/blender",
    os.path.expanduser("~/.steam/steam/steamapps/common/Blender/blender"),
    r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
]
CANDIDATES += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)


def version(path):
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60).stdout
        return out.splitlines()[0].strip()
    except Exception:
        return None


for c in CANDIDATES:
    if c and os.path.isfile(c):
        v = version(c)
        if v:
            print(c)
            print(v, file=sys.stderr)
            sys.exit(0)
sys.stderr.write("Blender not found. Install Blender 4.2 or newer from https://www.blender.org/download/ "
                 "(or Steam), or set BLENDER=/path/to/blender.\n")
sys.exit(1)
