# Characters (scripts/human.py)

Little rigged people built from smooth body parts (skin, shirt, trousers, boots, hair, face with blinking eyes) on an armature. No downloads, no add-ons, works headless. Rigid parts on bones = every pose is clean, nothing tears.

```python
import human
bob = human.Human("Bob", loc=(-0.7, 1.1, s3d.TOP), facing=20, outfit=human.WORKER, seed=0, shovel=True)
```
- `outfit`: `WORKER` (hard hat, hi-vis vest), `CASUAL`, `FARMER` (cap), `SCIENTIST`, or your own dict `shirt/pants/shoes/hat/hat_color/vest`.
- `seed` picks skin tone and hair colour; `scale` for kids (0.7).
- `facing` in degrees: 0 = toward the camera, 90 = toward +X, 180 = back to the camera.
- The camera looks at the cut face from y < 0, so keep people at y ≈ 0.6–2.2 (inside the hole/room or on the lawn).

## Actions (all take frames; call them in time order)
| Call | What happens | Sound cue |
|---|---|---|
| `walk(f0, f1, to=(x, y[, z]), face_end=0)` | turns, walks with arm swing and bob, turns to `face_end` | step |
| `dig(f0, f1, sink_to=z)` | shovel loop raise → stab → lever → toss; sinks with the hole floor | dig |
| `jump(f0, f1, to=(x, y, z), height)` | crouch, arc, land (scramble out of a hole, hop onto a ladder) | step |
| `climb(f0, f1, z_from, z_to)` | ladder climb, back to camera | clank |
| `act(f0, kind, cycles, period)` | `cough`, `wave`, `cheer`, `scared` (trembles), `climb` | cough… |
| `pose_at(frame, name)` + `hold(f0, f1)` | any pose from `POSES`, held with breathing | — |
| `turn(frame, facing)` / `place(frame, loc, facing)` | re-orient / teleport between cuts | — |
| `lie(frame, loc=(feet x, y, mattress top + 0.1), head_dir=-1)` | sits then lies on his back (bed, hammock) | — |
| `hide_until(f)` / `hide_from(f)` | enter / leave the story | — |

Poses in `POSES`: stand, walk_*, dig_*, cheer, wave_*, point, point_left, scared, think, cough_*, relieved, wipe_brow, thumbs_up, climb_*, jump, crouch, sit, lie, carry, shrug. Add your own: `{"bone": (forward, outward, twist)}` in degrees, bones = hips, spine, neck, head, upper_arm/forearm/hand/thigh/shin/foot (`.L`/`.R`, or without suffix for both sides). "Forward" is where the person faces; "outward" is away from the body.

## Directing tips
- Every beat: what does the person *do* or *feel*? Problem beats = he suffers (coughs, gets wet, gets scared), fix beats = relief / thumbs up.
- Big readable poses, held ≥ 15 frames; at phone size the face is ~50 px, so the body tells the story.
- Feet on the floor: lawn = `s3d.TOP`, a room floor = its inner floor height. Check stills for sinking/floating.
- He enters a room through something that exists (ladder, door, hatch) — never through walls.
- Props in hands: `shovel=True` (right hand). For other props, parent them to `bob.arm` with `parent_type="BONE"`, `parent_bone="hand.R"` (see `_shovel()` in human.py).


# Realistic people (scripts/mh.py — MPFB / MakeHuman, CC0)

For "what if" / body explainers use realistic humans instead of the little people. They come from MPFB (the MakeHuman add-on for Blender) and its CC0 asset pack.

Install once (ask the user before downloading; ~43 MB + ~270 MB, any OS):
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/setup_people.py --check   # what is there
python3 ${CLAUDE_SKILL_DIR}/scripts/setup_people.py           # installs MPFB + unpacks the MakeHuman CC0 assets
```

Make a character once (a separate Blender run, cached as a .blend):
```bash
"$BLENDER" -b --python scripts/mh.py -- make guy.blend '{"name": "guy", "shirt": [0.78, 0.06, 0.03]}'
```
Options: `gender` 0..1, `age` 0..1 (0.5 ≈ 25 y), `muscle`, `weight`, `height`, `skin` (e.g. `young_african_male/young_african_male.mhmat`), `hair` (`short02/short02.mhclo`, `""` = bald), `eyebrows`, `clothes` (list of .mhclo), `shirt` colour for the plain tee. Never copy another channel's recurring character (same face + outfit).

Use it in build.py (no MPFB needed there):
```python
p = mh.Person("guy.blend", loc=(0, 3.6, s3d.TOP), facing=0, name="guy")   # load as many copies as you need
p.pose(1, "idle"); p.face(1, "neutral")
p.pose(130, "pinch_nose", dur=9, pitch=-6); p.face(150, "squeeze")
p.jolt(600)                                       # held sneeze / hit
p.face(665, "shock", dur=3); p.pose(670, "grab_throat", dur=7)
p.anchor("throat", frame)                         # world position of nose_tip / mouth / throat / eyes / chest
```
- Named poses: `idle`, `pinch_nose`, `cover_mouth`, `grab_throat`, `elbow_sneeze`, `point`, `fist_press` (side = the fist, `press=0..1`), `interlace` (fingers laced, `ext=0..1` pushes the arms out), `hands_up` (`sides="LR"`).
- Your own pose: `p.act(frame, setup, dur=8, pitch=..)` where `setup(p)` calls `p.arm(...)`, `p.fingers(...)` — head/chest are set first, then the arms are solved, then keyed. Or by hand: `p.begin(f, dur)` → `look/arm/fingers` → `p.key(f)`. Arm targets in rig space: `p.rig.matrix_world @ Vector((x, y, z))`; use `p.A["chest"].z` / `p.anchor("throat")` so the pose fits any body.
- `fingers(side, curl, thumb, spread, only=(2,))`: curl 0..1, spread 0..1 fans the fingers.
- Call `pose`/`face`/`act` in time order; `dur` = frames of easing into the pose (0–1 for a hard cut).
- `pitch` (+ chin down), `yaw`, `roll`, `spine` (+ bend forward), `lean` move head and chest with any pose.
- Low level: `arm(side, wrist_world, elbow_hint, hand_dir, palm, elbow=None)` (two-bone IK on this body), `fingers(side, curl, thumb, only=(2,))`, `look(...)`, `move(frame, loc, rot)`.
- Lying down: rotate the rig `(-90, 0, -90)` and put it on the mattress (see the ward in `examples/whatif`).
- X-ray twin: load a second copy, give the body a glass material, remove its `Delete.*` mask modifiers (they hide skin under clothes), hide clothes/hair/eyes, keep the teeth as bone, parent organs to its bones (`examples/whatif`). Rest-pose coordinates are right only for bones the pose doesn't move (head, neck, spine); for anything on the arms/hands place the part at the POSED bone position (`rig.matrix_world @ pb[name].head` after `scene.frame_set(f)`) before parenting it to that bone.
- Put every extra zone (X-ray void, rooms) far from the backyard, e.g. y = -30: the yard's far lawn starts at y = 6.5 and shows through a void that overlaps it.
- `check()` covers arms vs head/face/neck/chest, forearm vs forearm, hand vs hand, wrist twist and folded elbows. It does not know your props: hands on objects you check by eye in the stills.
