"""One-time setup for realistic people (the "what if" look): MPFB (MakeHuman for Blender) + its CC0 asset pack.

  python setup_people.py            # checks, installs what is missing, prints what it did
  python setup_people.py --check    # only report

Downloads (ask the user first): the MPFB extension from extensions.blender.org (~43 MB) and
makehuman_system_assets_cc0.zip from files.makehumancommunity.org (~270 MB, unpacks to ~290 MB).
Works on macOS, Windows and Linux; needs Blender 4.2+ (find_blender.py).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS_URL = "https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip"
PROBE = r'''
import sys
try:
    from bl_ext.blender_org.mpfb.services.locationservice import LocationService
    d = LocationService.get_user_data()
    print("MPFB_DATA=" + d)
except Exception as e:
    print("MPFB_MISSING=" + repr(e))
'''


def blender():
    out = subprocess.run([sys.executable, os.path.join(HERE, "find_blender.py")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(out.stdout + out.stderr)
    return out.stdout.strip().splitlines()[0]


def probe(b):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(PROBE)
    r = subprocess.run([b, "-b", "--python", f.name], capture_output=True, text=True)   # user prefs = enabled extensions
    os.unlink(f.name)
    for line in r.stdout.splitlines():
        if line.startswith("MPFB_DATA="):
            return line.split("=", 1)[1]
    return None


def has_assets(d):
    return d and os.path.isdir(os.path.join(d, "skins")) and os.path.isdir(os.path.join(d, "clothes"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    b = blender()
    d = probe(b)
    print("Blender:", b)
    print("MPFB:", "installed" if d else "missing")
    print("MakeHuman assets:", "installed" if has_assets(d) else "missing")
    if a.check or (d and has_assets(d)):
        return
    if not d:
        print("installing MPFB from extensions.blender.org ...")
        subprocess.run([b, "--online-mode", "--command", "extension", "sync"], check=False)
        subprocess.run([b, "--online-mode", "--command", "extension", "install", "mpfb", "--enable"], check=True)
        d = probe(b)
        if not d:
            sys.exit("MPFB did not load after install - open Blender > Preferences > Get Extensions, install 'MPFB' by hand")
    if not has_assets(d):
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(tempfile.mkdtemp(prefix="mpfb_"), "assets.zip")
        print("downloading MakeHuman CC0 assets (~270 MB) ...")
        with urllib.request.urlopen(ASSETS_URL, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, length=1 << 20)
        print("unpacking into", d)
        with zipfile.ZipFile(tmp) as z:
            for m in z.infolist():                     # stay inside the target folder
                target = os.path.realpath(os.path.join(d, m.filename))
                if not target.startswith(os.path.realpath(d) + os.sep):
                    continue
                z.extract(m, d)
        os.remove(tmp)
    print("done: realistic people are ready (mh.py make ...)")


if __name__ == "__main__":
    main()
