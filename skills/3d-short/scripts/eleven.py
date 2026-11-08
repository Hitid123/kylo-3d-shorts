"""ElevenLabs for the short: narration with word timings, sound effects for every on-screen action, background music.

The key (https://elevenlabs.io/app/settings/api-keys) is read from, in order: $ELEVENLABS_API_KEY,
~/.config/kylo-3d-shorts/elevenlabs.key (written by `eleven.py setup` or by the plugin's install dialog).
Key permissions needed: Text to Speech, Sound Effects, Music Generation; Voices read + User read are optional
(voice list, credit check). Standard library only.

  python eleven.py setup                                       # paste the key in YOUR terminal (hidden), saved 600
  python eleven.py check                                       # is a key there, which plan, credits left (free)

  python eleven.py voices [--search "deep narrator"]          # pick a voice id
  python eleven.py voice  script.txt out_dir [--voice ID] [--model eleven_v4] [--speed 1.0] [--stability 0.5]
        -> out_dir/voice.wav + out_dir/words.json  (word timings straight from ElevenLabs, no Whisper pass)
  python eleven.py sfx    render.sfx.json sfx_dir [--force]
        -> one sound per distinct cue (kind or custom prompt) + sfx_dir/manifest.json, read by assemble.py
  python eleven.py sfx-one "metal container slams into dirt" out.mp3 [--seconds 1.5]
  python eleven.py music  "playful plucked strings, curious" out.mp3 [--seconds 60]
        -> instrumental bed; assemble.py ducks it under the voice

Licensing (check your plan): ElevenLabs output on the free plan is non-commercial and needs attribution;
a monetized channel needs a paid plan. Music generation is not available on the free plan.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.elevenlabs.io"
DEFAULT_VOICE = "nPczCjzI2devNBz1zQrb"  # "Brian": calm, deep American narrator (premade). Change with --voice.
DEFAULT_TTS_MODEL = "eleven_v4"
SFX_MODEL = "eleven_text_to_sound_v3"
MUSIC_MODEL = "music_v2_5"

# What each s3d cue kind should sound like. Short, dry, close-miked: they sit under a voice.
SFX_PROMPTS = {
    "thud": ("heavy object lands on packed dirt, one short dull thud, close, dry, no music", 1.2),
    "heavy": ("huge steel shipping container slams down into a dirt pit, deep metallic boom with dirt debris, short", 2.0),
    "whoosh": ("quick soft air whoosh as an object slides into place, short, clean", 0.8),
    "pop": ("small soft cartoon pop as an item appears, clean, short", 0.5),
    "crunch": ("metal sheet crunching and buckling under pressure, short", 1.2),
    "crack": ("mud wall cracking and crumbling, dirt clumps falling, short", 1.5),
    "dig": ("shovel digging into soil, three quick scoops with dirt tossed aside, close", 2.0),
    "pour": ("wet concrete pouring from a chute and spreading, short", 2.0),
    "splash": ("water rushing in and filling a pool with a splash", 2.0),
    "click": ("light switch click followed by a soft electric hum", 0.8),
    "clank": ("metal ladder clanks against a steel wall", 0.8),
    "step": ("two footsteps on grass", 0.7),
    "wood": ("wooden furniture placed down on a hard floor, short knock", 0.8),
    "cough": ("man coughs twice in a small closed room", 1.2),
    "rain": ("light rain shower on grass and dirt, steady", 3.0),
    "ding": ("bright soft success chime, single note", 1.0),
}


KEY_FILE = os.path.expanduser("~/.config/kylo-3d-shorts/elevenlabs.key")


def _key(required=True):
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not k and os.path.exists(KEY_FILE):
        k = open(KEY_FILE).read().strip()
    if not k and required:
        sys.exit("No ElevenLabs key. Run `python eleven.py setup` in your own terminal (or set it in the plugin settings: "
                 "/plugin configure kylo-3d-shorts), or record the voice yourself and use voice.py words.")
    return k


def _explain(code, body):
    try:
        d = json.loads(body).get("detail", {})
    except Exception:
        d = {}
    if isinstance(d, dict) and d.get("status") == "missing_permissions":
        return (f"the key is missing a permission: {d.get('message')}  -> elevenlabs.io/app/settings/api-keys, "
                f"edit the key and enable Text to Speech, Sound Effects, Music Generation (+ Voices/User read)")
    if code == 401:
        return "the key is invalid or revoked"
    if code == 402 or (isinstance(d, dict) and "quota" in str(d.get("status", ""))):
        return "not enough credits / feature not in your plan (music needs a paid plan)"
    return body[:400]


def setup():
    import getpass
    k = getpass.getpass("ElevenLabs API key (input hidden): ").strip()
    if not k:
        sys.exit("nothing saved")
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    old = os.umask(0o077)
    try:
        with open(KEY_FILE, "w") as f:
            f.write(k)
    finally:
        os.umask(old)
    os.chmod(KEY_FILE, 0o600)
    print("saved to", KEY_FILE, "(only your user can read it)")


def check():
    k = _key(required=False)
    if not k:
        print("no key: run `python eleven.py setup`, or use your own recording (voice.py words)")
        return
    src = "env ELEVENLABS_API_KEY" if os.environ.get("ELEVENLABS_API_KEY") else KEY_FILE
    print("key found in", src)
    req = urllib.request.Request(API + "/v1/user/subscription", headers={"xi-api-key": k})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
        left = d.get("character_limit", 0) - d.get("character_count", 0)
        print(f"plan: {d.get('tier')}  credits left: {left} of {d.get('character_limit')}")
        if d.get("tier") == "free":
            print("free plan: non-commercial use only, no music generation")
    except urllib.error.HTTPError as e:
        print("key accepted by the server but:", _explain(e.code, e.read().decode(errors="replace")))


def _post(path, body, query=None, timeout=600):
    url = API + path + ("?" + urllib.parse.urlencode(query) if query else "")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"xi-api-key": _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ElevenLabs {path} -> HTTP {e.code}: {_explain(e.code, e.read().decode(errors='replace'))}") from None


def _to_wav(src, dst):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-ar", "48000", "-ac", "1", dst], check=True)
    return dst


# ---------------------------------------------------------------- voices
def voices(search=None):
    q = {"page_size": 50, "include_total_count": "false"}
    if search:
        q["search"] = search
    req = urllib.request.Request(API + "/v2/voices?" + urllib.parse.urlencode(q), headers={"xi-api-key": _key()})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.loads(r.read())
    for v in j.get("voices", []):
        lab = v.get("labels") or {}
        print(f"{v['voice_id']}  {v.get('name','')[:28]:28}  {v.get('category',''):10}  "
              f"{lab.get('gender','')} {lab.get('age','')} {lab.get('accent','')} {lab.get('use_case','') or lab.get('descriptive','')}")


# ---------------------------------------------------------------- narration
def _words_from_alignment(al):
    words, cur, start, prev_e = [], "", None, 0.0
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": round(start, 3), "e": round(prev_e, 3)})
            cur, start = "", None
            continue
        if start is None:
            start = s
        cur += ch
        prev_e = e
    if cur:
        words.append({"w": cur, "s": round(start, 3), "e": round(prev_e, 3)})
    return words


def voice(text, out_dir, voice_id=DEFAULT_VOICE, model=DEFAULT_TTS_MODEL, speed=1.0, stability=0.5, style=0.0):
    """Narration with per-character timestamps -> voice.wav + words.json. One line of the script = one beat;
    lines are joined with a pause-friendly newline so the narrator breathes between beats."""
    os.makedirs(out_dir, exist_ok=True)
    body = {"text": text, "model_id": model,
            "voice_settings": {"stability": stability, "similarity_boost": 0.8, "style": style, "use_speaker_boost": True, "speed": speed}}
    try:
        raw, _ = _post(f"/v1/text-to-speech/{voice_id}/with-timestamps", body, {"output_format": "mp3_44100_128"})
    except RuntimeError as e:
        if model != "eleven_multilingual_v2" and ("model" in str(e).lower() or "422" in str(e)):
            print(f"{model} refused ({e}); retrying with eleven_multilingual_v2")
            body["model_id"] = "eleven_multilingual_v2"
            raw, _ = _post(f"/v1/text-to-speech/{voice_id}/with-timestamps", body, {"output_format": "mp3_44100_128"})
        else:
            raise
    j = json.loads(raw)
    mp3 = os.path.join(out_dir, "voice.mp3")
    with open(mp3, "wb") as f:
        f.write(base64.b64decode(j["audio_base64"]))
    wav = _to_wav(mp3, os.path.join(out_dir, "voice.wav"))
    words = _words_from_alignment(j.get("alignment") or j["normalized_alignment"])
    with open(os.path.join(out_dir, "words.json"), "w") as f:
        json.dump(words, f, indent=0, ensure_ascii=False)
    print(f"{wav}  words: {len(words)}  ~{words[-1]['e'] if words else 0:.1f}s")
    return wav, words


# ---------------------------------------------------------------- sound effects
def sfx_one(prompt, out, seconds=None, loop=False, influence=0.45):
    body = {"text": prompt, "model_id": SFX_MODEL, "prompt_influence": influence, "loop": loop}
    if seconds:
        body["duration_seconds"] = max(0.5, min(30.0, float(seconds)))
    try:
        raw, _ = _post("/v1/sound-generation", body, {"output_format": "mp3_44100_128"})
    except RuntimeError as e:
        if "model" in str(e).lower() or "422" in str(e):
            body["model_id"] = "eleven_text_to_sound_v2"
            raw, _ = _post("/v1/sound-generation", body, {"output_format": "mp3_44100_128"})
        else:
            raise
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as f:
        f.write(raw)
    return out


def cue_key(cue):
    """Same key in eleven.py and assemble.py: a custom prompt wins over the generic kind."""
    return cue.get("prompt") or cue["sfx"]


def _peak_normalize(src, peak_db=-1.0):
    """ElevenLabs sounds come out anywhere from -12 to -50 LUFS. Bring every sound to the same peak so the
    per-cue gains in assemble.py mean something. Writes <src>.wav next to it, returns its file name."""
    out = os.path.splitext(src)[0] + ".wav"
    det = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"max_volume: (-?[\d.]+) dB", det)
    gain = (peak_db - float(m.group(1))) if m else 0.0
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", f"volume={gain:.2f}dB", "-ar", "48000", out], check=True)
    return os.path.basename(out)


def sfx_for_cues(cues_path, sfx_dir, force=False):
    """Generate one sound per distinct cue (kind or custom prompt). Writes sfx_dir/manifest.json {key: file}."""
    cues = json.load(open(cues_path))
    os.makedirs(sfx_dir, exist_ok=True)
    man_path = os.path.join(sfx_dir, "manifest.json")
    manifest = json.load(open(man_path)) if os.path.exists(man_path) else {}
    for c in cues:
        k = cue_key(c)
        if k in manifest and os.path.exists(os.path.join(sfx_dir, manifest[k])) and not force:
            continue
        prompt, dur = SFX_PROMPTS.get(c["sfx"], (c["sfx"].replace("_", " "), 1.2))
        if c.get("prompt"):
            prompt, dur = c["prompt"], c.get("seconds", dur)
        name = c["sfx"] + "_" + hashlib.md5(k.encode()).hexdigest()[:8] + ".mp3"
        print(f"sfx  {k!r:60.60} -> {name}")
        sfx_one(prompt, os.path.join(sfx_dir, name), dur)
        manifest[k] = _peak_normalize(os.path.join(sfx_dir, name))
        with open(man_path, "w") as f:
            json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(f"{len(manifest)} sounds in {sfx_dir}")
    return manifest


# ---------------------------------------------------------------- music
def music(prompt, out, seconds=60, model=MUSIC_MODEL):
    """Instrumental bed. Keep prompts about mood, instruments, tempo; never name artists or songs."""
    body = {"prompt": prompt, "music_length_ms": int(max(3, min(600, seconds)) * 1000), "model_id": model, "force_instrumental": True}
    try:
        raw, _ = _post("/v1/music", body, timeout=900)
    except RuntimeError as e:
        print(f"music: {e}; retrying without force_instrumental")
        body.pop("force_instrumental")
        body["prompt"] = prompt + ". Instrumental only, no vocals."
        raw, _ = _post("/v1/music", body, timeout=900)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as f:
        f.write(raw)
    # generated tracks can end with seconds of silence: cut the silent tail so the length is honest
    tmp = out + ".trim" + os.path.splitext(out)[1]
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-af",
                        "areverse,silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.2,areverse", tmp])
    if r.returncode == 0 and os.path.getsize(tmp) > 1000:
        os.replace(tmp, out)
    got = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                         capture_output=True, text=True).stdout.strip()
    print(f"{out}  ({float(got or 0):.1f}s of music)")
    if got and float(got) < seconds - 1.5:
        print("music is shorter than asked: generate again with a few more --seconds (assemble.py will not loop it)")
    return out


MUSIC_DEFAULT = ("light curious instrumental for a short 3D explainer animation: plucked pizzicato strings, soft marimba, "
                 "gentle kick and shaker, steady 100 bpm, bright and friendly, low dynamics, no build-ups or drops, "
                 "sits quietly under a narrator, ends on a clean final note")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup"); sub.add_parser("check")
    p = sub.add_parser("voices"); p.add_argument("--search")
    p = sub.add_parser("voice"); p.add_argument("script"); p.add_argument("out_dir")
    p.add_argument("--voice", default=DEFAULT_VOICE); p.add_argument("--model", default=DEFAULT_TTS_MODEL)
    p.add_argument("--speed", type=float, default=1.0); p.add_argument("--stability", type=float, default=0.5)
    p.add_argument("--style", type=float, default=0.0)
    p = sub.add_parser("sfx"); p.add_argument("cues"); p.add_argument("sfx_dir"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("sfx-one"); p.add_argument("prompt"); p.add_argument("out"); p.add_argument("--seconds", type=float)
    p = sub.add_parser("music"); p.add_argument("prompt", nargs="?", default=MUSIC_DEFAULT); p.add_argument("out")
    p.add_argument("--seconds", type=float, default=60); p.add_argument("--model", default=MUSIC_MODEL)
    a = ap.parse_args()
    if a.cmd == "setup":
        setup()
    elif a.cmd == "check":
        check()
    elif a.cmd == "voices":
        voices(a.search)
    elif a.cmd == "voice":
        text = "\n".join(l.strip() for l in open(a.script) if l.strip())
        voice(text, a.out_dir, a.voice, a.model, a.speed, a.stability, a.style)
    elif a.cmd == "sfx":
        sfx_for_cues(a.cues, a.sfx_dir, a.force)
    elif a.cmd == "sfx-one":
        print(sfx_one(a.prompt, a.out, a.seconds))
    elif a.cmd == "music":
        music(a.prompt, a.out, a.seconds, a.model)


if __name__ == "__main__":
    main()
