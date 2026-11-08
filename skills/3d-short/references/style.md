# The look (cutaway build shorts)

Measured from published shorts of the format (You Made It, From The Ground Up, Odd Tilt — Oct/Nov 2026) and implemented as defaults in `s3d.py`.

## Frame
- 1080×1920, 30 fps. Keep text and key action inside the centre ~900×1400 px (Shorts UI covers the bottom ~20 % and the right edge).
- The cross-section of the ground is the hero: grass strip on top (~upper third of the frame), layered brown soil below with pebbles; the yard behind (fence, neighbour houses, trees, blue sky) occupies the top ~30 %.
- The hole/structure sits centred, slightly above the frame middle. Never let the bottom of the soil block show (ground depth 16 m by default).

## Light and colour
- Bright clean daylight: one warm sun from front-left-above (shadows fall back-right), soft cool fill from the camera side so the cut face is never black.
- Saturated but not neon: grass vivid green, soil rich dark brown with lighter clay/sand strata, water saturated blue, concrete light grey, steel mid-grey.
- Real materials: photo-scanned soils stacked as strata, plank fence, plaster houses, tiled roofs, corrugated steel — all Poly Haven CC0 via `s3d.tex()`. Flat colours only for small props.
- View transform AgX Medium High Contrast, exposure +0.25 (s3d default; override with `S3D_VIEW`, `S3D_LOOK`, `S3D_EXPOSURE`).
- Light camera depth of field so the backyard is slightly soft and the cut stays the hero.
- Post (assemble.py): faint vignette only. No animated grain (it reads as flicker on phones), no bloom, no colour filters.

## Motion vocabulary (s3d)
| Event in script | Animation | SFX cue |
|---|---|---|
| dig / excavate | `dig()` hole grows down, dirt chunks fly out | dig |
| something placed (container, slab, door) | `drop_in()` falls and bounces once | thud on landing |
| poured / filled (concrete, water, gravel) | `grow(axis="Z")` from the base | pour |
| attached / run (pipe, cable, panel) | `slide_in()` or `grow()` along its length | whoosh |
| small part / label | `pop_in()` with overshoot, `tag()` auto-hides | pop |
| failure (crack, crush, quake) | `shake()`, `squash()` | crack / crunch |
| replaced | `shrink_out()` | — |
| state change (water turns green, metal glows) | `color_to()` | — |

Timing: the visual completes on the noun that names it (`when(B, i, "concrete")`), anticipation 0–6 frames before. Something changes on screen at least every ~2 s.

## Characters
- One recurring little person per short (see `characters.md`): he does the action, suffers the problem, enjoys the fix. Readable silhouettes beat facial detail: big clear poses, held ≥ 0.5 s.
- He is ~1.8 m: keep doors, ladders, beds to scale with him — he is the scale reference for the whole build.

## Camera
- Front view onto the cut face, lens 35 mm, slightly above the action.
- Grammar per short: establishing wide (whole yard + hole) → push in to each new part as it arrives → pull back for the final reveal. Moves are eased dollies/pans on one axis (`cam_move`), 20–40 frames. No orbiting, no handheld wobble, no hard cuts (motion transitions only, ~1 hard cut in 7 at most).
- Hold long enough to read: ≥1.5 s on each new object.

## Labels
- Small dark-grey plates with white text (`tag()`), lowercase, 1–2 words, glued next to the part, visible ~2.5 s.

## Captions (assemble.py)
- 1–3 words per chunk, lowercase, heavy white sans (Montserrat ExtraBold) with thick black outline and soft shadow, centred at ~62 % height, switching on the spoken word.

## Sound
- ElevenLabs narration dominant and even; an ElevenLabs sound on every landing, pour, crack, step, clank, cough; ElevenLabs instrumental music ducked under the voice. Final −14 LUFS, true peak ≤ −1.5 dBTP.

## "Cheap AI 3D" tells to avoid
- Floating or intersecting objects, objects appearing with no motion, sharp unbevelled edges, flat untextured colours, empty background, wrong scale (a 3 m ladder in a 1 m hole), camera orbiting for no reason, the same structure and props in every video, labels that never disappear, garbled text in the scene.

## Preview checklist (before every full render)
1. Start frame already interesting (no empty lawn for >1 s).
2. Every beat still shows its new object clearly, centred, not clipped by the frame edge.
3. Nothing floats, sinks or intersects visibly; scale is believable.
4. Cut face lit, strata and stones readable; grass/sky not washed out; no white boxes (a visible boolean cutter = bug).
5. The character is on the floor (not sinking, not floating), facing where the action is, never hidden behind a prop.
6. Labels readable at phone size and gone before they clutter.
7. Final frame = complete build, wide, calm.
