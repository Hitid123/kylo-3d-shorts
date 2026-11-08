# Building the scene with s3d

`scripts/s3d.py` is a plain Python module for Blender. Load it in a build script:
```python
import os, sys
sys.path.insert(0, "<skill>/scripts")   # in the example: relative to the build file
import s3d, assets, human                # assets = Poly Haven CC0 models/textures/HDRIs, human = characters
B = s3d.load_beats("beats.json")
s3d.new_short(seconds=40)                # wipes the file: 1080x1920, 30 fps, EEVEE raytraced, AgX, HDRI sky + sun + fill
```
With the Blender MCP connected you can run the same code live through `execute_blender_code` (add the scripts folder to `sys.path` first) and use `look` to check it.

## Coordinates
- Metres. X = left/right, Z = up, lawn surface z = `s3d.TOP` (0.03).
- The camera looks along +Y; the visible cut face of the ground is the plane **y = 0**. Put things *inside* the ground at y between 0 and ~3 (so their front faces line up with the cut), things on the lawn at y ≈ 0.4–2, the fence at y = 6, houses beyond.
- Boxes are created centred on `loc`; use `origin_to_base(o)` before `grow(o, axis="Z")` so it fills from the bottom.

## API
| Function | What it does |
|---|---|
| `new_short(res, fps, seconds, sky)` | fresh scene; HDRI sky (Poly Haven id) + sun + fill |
| `backyard(width)` | textured plank fence, 3 plaster houses with tiled gable roofs, trees, CC0 shrubs, lawn |
| `ground_section(width, depth)` | photo-scanned soil strata (topsoil, soil, clay, rock), stones, roots, lawn slab, 3D grass blades; returns soil |
| `dig(soil, x, width, depth, start, end, back, mound_side)` | animated hole (boolean); grass over it, stones and roots inside vanish in step with the cut; dirt mound grows; clods fly; `dig` cue |
| `rock(name, size, loc, material)` | irregular stone / mud lump |
| `box(name, size, loc, mat, bevel)` | bevelled box (size = full dimensions) |
| `cylinder(name, radius, depth, loc, rot, mat)` | smooth bevelled cylinder |
| `hollow_box(name, size, wall, loc, mat)` | room/container with the front wall removed |
| `ladder(name, height, width, loc)` | procedural steel ladder |
| `group(name, objs)` | parent under an empty to animate together |
| `label(text, loc)` / `tag(text, loc, frame, hold)` | grey plate with white text; tag auto-hides |
| `drop_in(o, frame, height, dur, sfx, prompt)` | falls + bounce, impact cue on landing (`sfx="heavy"` for big metal) |
| `pop_in(o, frame, dur)` | scale from 0 with overshoot |
| `slide_in(o, frame, offset, dur)` | glide in from an offset |
| `grow(o, frame, axis, dur)` | grow along an axis from the origin |
| `shake(o, frame)`, `squash(o, frame)` | failure moments |
| `shrink_out(o, frame)` / `hide_at(o, frame)` | remove something being replaced |
| `light_level(light, frame, watts)` / `emit_level(mat, frame, strength)` | lamps switching on, sun dimming for rain |
| `marker(kind, frame, prompt, gain, seconds)` | any extra sound cue; `prompt` = custom ElevenLabs description |
| `color_to(mat, rgb, frame, dur)` | animate a material colour |
| `camera_cutaway(target, dist)` / `cam_move(cam, frame, target, dist, dur)` / `cam_drift(cam, start, end)` | the camera grammar |
| `when(B, i, word, offset)` | frame where `word` is spoken in beat `i` |
| `preview_still(path, frame, scale)` / `render_mp4(path, scale)` | stills / H.264 render + `.sfx.json` |
| `tex(polyhaven_id, tile, tint)` | photo PBR material (object-space mapping, never swims), procedural fallback offline |
| materials: `mat(name, rgb, rough, metal, noise)`, `mat_soil/concrete/metal_white/steel/wood/water`, `mat_emit` | |
| `PAL` | the palette (grass, soil, clay, concrete, water, ...) |

## Recipes
- **Container / room underground**: `hollow_box("Container", (4.7, 2.5, 2.5), loc=(0, 1.32, -1.95), mat=s3d.tex("corrugated_iron_02", tile=1.2, tint=(1.55, 0.62, 0.32)))`, `drop_in(..., sfx="heavy")` on "container". Children of a dropped group appear with it; cutters stay hidden (`obj["s3d_always_hidden"] = 1` for your own cutters).
- **Hatch in a roof**: boolean cutter parented to the container, scale 0 → 1 on "hatch"; lid box rotates open. See `examples/bunker/build.py`.
- **Rain**: one mesh of thin emissive streaks moving down with a CYCLES modifier, sun `light_level` down and world strength down for the beat (example in the bunker build).
- **Bad air / smoke**: a box with an alpha-animated BLENDED material inside the room.
- **Concrete shell**: two wall boxes + floor box in a `group`, `drop_in` or `grow` each; rebar = thin cylinders along Y poking through the cut face (`rot=(1.5708, 0, 0)`), rust colour.
- **Pipe to the surface**: `origin_to_base(cylinder(...))` then `grow(axis="Z")`; elbows as a second short cylinder rotated 90°.
- **Solar panels on the lawn**: thin dark-blue boxes tilted 30° (`rot=(0.5, 0, 0)`) on two thin legs, `slide_in` from the side.
- **Water**: `mat_water()`, `origin_to_base` + `grow`; murky/algae via `color_to`.
- **Gravel / sand fill**: `grow` a box with a noisy grey/beige `mat(noise=0.8, noise_scale=30)`.
- **Blast door / hatch**: thick box `slide_in` with `offset=(0, 0, 3)` and a `thud`.
- **Escape shaft**: second `dig()` beside the first, then `grow` a gravel box in it.

## Performance
- EEVEE at 1080×1920: ~2–3 s/frame on Apple Silicon with the full world (grass, textures, raytracing); a 40 s short renders in ~45–60 min. Do drafts at `half` with 16 samples (~0.4 s/frame).
- Textures are 2k and cached after the first build; the lawn is ~60k blades built with numpy in under a second.
- Many `dig()` booleans or high-poly scans slow everything; keep imported models at 1k textures and < 200k faces.
- Booleans use the EXACT solver; if a hole flickers, make the cutter slightly larger than the cut object.
