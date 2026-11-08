# Kylo 3D Shorts — viral 3D cutaway Shorts in Blender with Claude

A free Claude Code plugin that makes vertical 3D Shorts in the "How a hole becomes a bunker" style — the cross-section build format that took channels like You Made It and From The Ground Up from zero to tens of millions of views in weeks — in **real Blender on your own computer**. No AI video generator, no subscription.

You give Claude an idea. It writes the script with the proven formula, voices it with ElevenLabs, builds and animates the scene in Blender — with a little person who digs, gets scared, climbs down and goes to bed — renders it, then adds ElevenLabs sound effects on every action, ElevenLabs background music, captions and loudness. Out comes an upload-ready 1080×1920 mp4.

```
/kylo-3d-shorts:3d-short How a hole in the backyard becomes a swimming pool
```

## What's inside
- **Script formulas** that work for this niche: the build chain ("If you… / But… / So you… / Congratulations…"), "How you invented X", and the "What happens if you…" explainer — with length and pacing targets.
- **`s3d` Blender library**: photo-scanned soil strata (topsoil, soil, clay, rock) with stones and roots, 3D grass, HDRI sky, textured backyard; animated digging that keeps grass/stones/roots consistent; drop/pop/slide/grow animations with sound cues; labels; eased dolly camera with soft depth of field.
- **`human` characters**: rigged little people (outfits, faces, blinking) with walk, dig, jump, climb, cough, cheer, scared, lie-down and 25+ poses.
- **`mh` realistic people** for "what if" explainers (MPFB / MakeHuman, CC0): facial expressions, hands that land on the nose/throat of the actual body, lying down, an X-ray glass twin with anatomy inside.
- **ElevenLabs**: narration with exact word timings, one generated sound per on-screen action, instrumental music (`scripts/eleven.py`).
- **Poly Haven importer**: real CC0 models, textures and HDRIs, cached locally.
- **Assembly**: 1–3-word captions on the spoken words, sounds on their frames, music ducked under the voice, −14 LUFS.
- **People that move like people** (v1.3): hand gestures are keyed as targets and solved on every frame with ease-in/out, wind-ups and settles; hands that hold each other stay together; breathing, sway and blinks keep holds alive; fast jerky moves are reported before the render.
- **QA before you waste a render**: missing textures, arms through heads, twisted wrists and black/magenta frames are caught automatically (`s3d.qa_gate`, `Person.check`, `qa.py`) with frame numbers and a contact sheet.
- **Reference measurer**: shot lengths, cut rate, palette, loudness, words/s of any short — yours vs. the reference.
- Three complete examples: `skills/3d-short/examples/bunker` (build + little person), `examples/pool` (build) and `examples/whatif` ("What happens if you hold in a sneeze?" — realistic person, X-ray, hospital).

## Install (Claude Code)
```
/plugin marketplace add Hitid123/kylo-3d-shorts
/plugin install kylo-3d-shorts@kylo-3d-shorts
```
Requirements: [Blender](https://www.blender.org/download/) 4.2+ (tested on 5.2), `ffmpeg`, [`uv`](https://docs.astral.sh/uv/), an [ElevenLabs](https://elevenlabs.io) API key (asked at install; paid plan for monetized videos) or your own voice recording, internet for the first build (textures are cached). A machine that runs Blender's EEVEE (Apple Silicon or any modern GPU). For realistic people: the free MPFB extension + MakeHuman CC0 assets (`references/characters.md`). Optional: the Blender MCP connector to watch and tweak the scene live — `claude mcp add blender uvx mcp-for-blender`.

**Voice — pick one:**
- **ElevenLabs key** (Claude voices it, adds sounds and music): the plugin asks for the key when you install it (stored in your keychain; change it with `/plugin configure kylo-3d-shorts@kylo-3d-shorts`). Or run `python3 skills/3d-short/scripts/eleven.py setup` in your terminal. The key needs the Text to Speech, Sound Effects and Music Generation permissions. Never paste keys into a chat.
- **Your own recording**: drop `voice.mp3` into the project folder — Claude transcribes it, times every word and builds the animation to it.

Claude desktop/web: upload the plugin zip under Customize → Plugins. Rendering needs a local Blender, so the full pipeline runs in Claude Code or in a Cowork session on your computer.

## Quick start
1. Ask: `/kylo-3d-shorts:3d-short How a tree becomes a treehouse`.
2. Approve the script; Claude voices it with ElevenLabs (pick a voice or keep the default narrator).
3. Look at the preview stills Claude shows you, then let it render; Claude generates the sounds and the music and assembles the final video.
4. Upload `final.mp4`. Read `skills/3d-short/references/publish.md` first.

## Honest notes
- Views are not guaranteed, and YouTube demonetizes templated mass uploads. Vary your stories and use your own voice.
- From 1 Feb 2027 Shorts pool earnings need 10M Shorts views in 90 days. Check the current rules for your country.
- Only use music you own, generated on a paid ElevenLabs plan, or cleared for YouTube.

## Licence
MIT. Montserrat font: SIL OFL 1.1. Poly Haven assets: CC0. ElevenLabs output: per your ElevenLabs plan.

Made by [@kyloai](https://t.me/kyloai).
