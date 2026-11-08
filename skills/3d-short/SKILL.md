---
name: 3d-short
description: Make a vertical 3D animated Short in real Blender with ElevenLabs narration, music and sound effects — either the viral "How a hole becomes a bunker" cutaway build (You Made It, From The Ground Up, Odd Tilt) with little people, or a realistic "What happens if you…" explainer in the ZackD Films style (realistic person, X-ray anatomy, hard cuts) — script, voice, 3D build, camera, render, captions, sound and final mp4. Use when the user asks for a 3D short, a "how X becomes Y" / "how you invented X" / "what if" animation, a cutaway/cross-section build video, or a ZackD-style 3D explainer.
---

# 3D cutaway Shorts in Blender + ElevenLabs

You produce a finished 9:16 Short in one of two looks:
- **Cutaway build** — a place gets built step by step in a cross-section of the ground, each step answering a problem ("But when it rains, the mud walls cave in. So you lower a steel container."). An optional little person lives the story (`human.py`). Example: `examples/bunker`, `examples/pool`. Look: `references/style.md`.
- **"What if" explainer** — a realistic person (`mh.py`, MPFB/MakeHuman) in close-ups, hard cuts to X-ray views inside the body, a real case if there is one. Example: `examples/whatif` ("What happens if you hold in a sneeze?"). Look: `references/style-explainer.md`.

Everything is real 3D rendered in Blender on the user's machine; ElevenLabs makes the voice, the music and every sound effect.

All paths below are relative to this skill folder: `${CLAUDE_SKILL_DIR}` (in a plugin also `${CLAUDE_PLUGIN_ROOT}/skills/3d-short`).

## Before you start (once per machine)

1. Blender 4.2+ (tested on 5.2): `python3 ${CLAUDE_SKILL_DIR}/scripts/find_blender.py` prints the binary. If missing, tell the user to install it from blender.org (or Steam) and stop.
2. `ffmpeg` on PATH, and `uv` (or a Python with `pillow numpy`).
3. ElevenLabs key — the plugin asks for it in its install dialog (`/plugin configure kylo-3d-shorts@kylo-3d-shorts` to change it; stored in the OS keychain and copied to `~/.config/kylo-3d-shorts/elevenlabs.key` at session start). Alternatives: `python3 ${CLAUDE_SKILL_DIR}/scripts/eleven.py setup` in the user's own terminal, or `ELEVENLABS_API_KEY` in the environment. `eleven.py check` tells whether a key is there and which permission is missing (the key needs Text to Speech, Sound Effects, Music Generation). Never ask the user to paste a key into chat. No key? The user can record the voice instead (step 2B). A monetized channel needs a paid ElevenLabs plan (free = non-commercial, no music).
4. Internet on the first build: textures and props come from Poly Haven (CC0) and are cached in `~/.cache/kylo-3d-shorts`. Offline, every material falls back to a procedural one.
5. Realistic people (only for the "what if" look): `python3 ${CLAUDE_SKILL_DIR}/scripts/setup_people.py --check`; if missing, ask the user (downloads ~310 MB, unpacks to ~370 MB) and run it without `--check`.
6. Optional: the Blender MCP connector (`claude mcp add blender uvx mcp-for-blender`) to see and tweak the live scene. The pipeline works headless without it.

## The pipeline

Work in a project folder the user can see, e.g. `./shorts/<slug>/`. Keep the user in the loop at the checkpoints marked ✋.

### 1. Script ✋
Read `references/script.md`. Pick the formula (build chain, "how you invented", or "what if"), then write `script.txt`: **one beat per line**, 7–10 beats, 80–190 words (≈35–75 s at 2.6–2.8 words/s). Every beat must name something you can show, and give the character something to do. Show the script to the user and wait for approval. Facts must be true — never invent numbers.

### 2. Voice + timings
Pick the voice source (ask once if unclear):
- **A. ElevenLabs (default when a key is set)** — Claude generates the narration:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/eleven.py voices --search narrator        # pick a voice (default: calm deep narrator)
python3 ${CLAUDE_SKILL_DIR}/scripts/eleven.py voice script.txt . [--voice ID] # -> voice.wav + words.json (exact word timings)
python3 ${CLAUDE_SKILL_DIR}/scripts/beats.py script.txt words.json beats.json
```
- **B. The user's own recording** — they drop `voice.mp3` (or .wav/.m4a) into the project folder; script.txt is optional:
```bash
uv run --with mlx-whisper python ${CLAUDE_SKILL_DIR}/scripts/voice.py words voice.mp3 .   # -> words.json, voice.wav (+ script.txt)
python3 ${CLAUDE_SKILL_DIR}/scripts/beats.py script.txt words.json beats.json
```
  (`--with faster-whisper` instead of mlx-whisper off Apple Silicon.) Check the line breaks of the generated script.txt: one line = one beat.
- **C. No voice yet** (preview the animation first): `python3 ${CLAUDE_SKILL_DIR}/scripts/voice.py plan script.txt .` estimates `words.json` from the text; build and preview with it, then do A or B and rebuild — everything re-times itself.

### 3. Build the scene
Read the look for the format (`references/style.md` for builds, `references/style-explainer.md` for "what if"), `references/build.md` (s3d API) and `references/characters.md` (people). Copy the closest example into the project as `build.py` — `examples/bunker` (build + little person), `examples/pool` (build), `examples/whatif` (realistic person + X-ray) — and rewrite it for this script. For a build:
- the world: `s3d.new_short()`, `s3d.backyard()`, `g = s3d.ground_section()` — photo-scanned soil strata, stones, roots, 3D lawn, HDRI sky;
- one visible change per beat, landing on the word that names it: `s3d.when(B, i, "container")`;
- the character acts every beat: `bob.dig(...)`, `bob.act(f, "scared")`, `bob.climb(...)`, `bob.lie(...)` — he shows the problem before the fix arrives;
- each move passes `prompt="..."` when the moment deserves its own sound ("huge steel container slams into a dirt pit"); generic cues (thud, pop, clank, dig, rain…) already have good ElevenLabs prompts;
- camera: wide → push in on each new part → pull back for the payoff; one straight dolly axis, eased, never orbit;
- props: procedural (`s3d.box/cylinder/hollow_box/ladder/rock`), photo materials `s3d.tex("corrugated_iron_02", tint=...)`, real CC0 models `assets.model("wooden_crate_01", size=0.75, loc=...)`.

For a "what if": one zone per kind of view (real place, X-ray void, a ward/room…) placed far apart in the same scene; one camera per shot bound to timeline markers (hard cuts) with a slow push-in; the person's face and hands act every shot (`face()`, `pose()`); inside views show the mechanism with glowing particles, swelling, colour changes landing on the words.

### 4. Look at it ✋ (QA is mandatory)
```bash
BLENDER=$(python3 ${CLAUDE_SKILL_DIR}/scripts/find_blender.py)
"$BLENDER" --background --python build.py -- . preview      # stills at key moments -> preview/f####.png + "QA:" lines
uv run --with pillow --with numpy python ${CLAUDE_SKILL_DIR}/scripts/qa.py preview/   # magenta/black frames + qa_sheet.jpg
```
Three layers of checks, all must be clean:
1. **Scene** (`s3d.qa_gate`, printed as `QA:` lines, and it blocks `render_mp4`): missing textures (they render MAGENTA), empty image nodes, no camera, visible boolean cutters.
2. **Poses** (`Person.check()` for every realistic person, passed to `render_mp4(qa=...)`): an arm or hand through the head/face/neck/chest, a wrist twisted against the forearm, a folded elbow — with frame numbers. Fix the pose (different target, `elbow=`, `dur`, camera angle) and rebuild.
3. **Pixels** (`qa.py` + your eyes): open `qa_sheet.jpg` and every still; check hands touch what they should (no fingers inside faces), faces read at phone size, nothing floats or intersects, the look list in `style.md` / `style-explainer.md`.
Show the user 3–4 stills before the long render. Never move a character `.blend` with external textures — `mh.py make` packs them.

### 5. Render
```bash
"$BLENDER" --background --python build.py -- . half    # 540x960 draft to check motion (~0.4 s/frame on Apple Silicon)
"$BLENDER" --background --python build.py -- . full    # 1080x1920 final (EEVEE, ~2-3 s/frame)
```
Run long renders in the background and tell the user the ETA. Each render writes `render.sfx.json` (every sound cue with its frame). After the `half` render run `qa.py render.mp4 --every 0.5` and open the sheet: motion bugs (an arm sweeping through the body between two good poses, a frozen shot, a pop) only show up here.

### 6. Sound + assemble ✋
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/eleven.py sfx render.sfx.json sfx/                 # one sound per distinct cue, cached
python3 ${CLAUDE_SKILL_DIR}/scripts/eleven.py music "<mood, instruments, tempo>" music.mp3 --seconds <length+2>
uv run --with pillow --with numpy python ${CLAUDE_SKILL_DIR}/scripts/assemble.py \
  --video render.mp4 --voice voice.wav --words words.json --sfx render.sfx.json --sfx-lib sfx/ --music music.mp3 --out final.mp4 \
  [--style explainer]      # small sentence-case captions low in the frame for the "what if" look
```
Music prompt: describe mood/instruments/tempo for the story (curious plucks for builds, low tension for disasters); never name artists or songs. assemble.py adds 1–3-word captions on the spoken words, drops every sound on its frame, ducks the music under the voice, adds a light vignette and normalises to −14 LUFS. Run `qa.py final.mp4` once more, open the sheet, and listen-check levels (ffmpeg ebur128) before handing it over.

### 7. Publish notes
Give the user a title (formula in `references/script.md`) and the rules in `references/publish.md`: fully animated 3D does not need the "altered or synthetic" label; disclose a synthetic voice if the platform asks; vary stories (templated mass uploads are what YouTube demonetizes).

## Optional: copy the numbers of a reference channel
`python3 ${CLAUDE_SKILL_DIR}/scripts/measure.py reference.mp4 [words.json]` prints shot lengths, cut rate, palette, brightness and loudness. Run it on your own render too — the difference is your to-do list.

## Rules
- Never claim real facts you didn't verify; never copy another channel's script, title or characters.
- No brand logos or real people in the scene.
- Always look at preview stills before rendering the whole thing.
- Spending ElevenLabs credits: tell the user what you are about to generate (voice, N sounds, music length) before the first call in a project.
- Tell the user honestly when something looks off rather than shipping it.
