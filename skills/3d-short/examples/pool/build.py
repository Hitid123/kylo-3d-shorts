"""Example build: "How a hole becomes a pool" — timed to the voiceover through beats.json.

  blender --background --python build.py -- <workdir> [preview|full]
<workdir> must contain beats.json (from beats.py). Output: <workdir>/render.mp4 (+ render.sfx.json)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_scripts(here):
    """The plugin's scripts folder, wherever this build.py was copied to (a project folder, the example itself)."""
    import glob
    for c in (os.environ.get("KYLO_SCRIPTS", ""), os.path.join(here, "..", "..", "scripts"), os.path.join(here, "scripts")):
        if c and os.path.exists(os.path.join(c, "s3d.py")):
            return os.path.abspath(c)
    hits = sorted(glob.glob(os.path.expanduser("~/.claude/plugins/cache/*/kylo-3d-shorts/*/skills/3d-short/scripts")),
                  key=lambda p: [int(x) if x.isdigit() else 0 for x in p.split(os.sep)[-4].split(".")])
    if hits:
        return hits[-1]
    raise SystemExit("set KYLO_SCRIPTS=<plugin>/skills/3d-short/scripts")


sys.path.insert(0, _find_scripts(HERE))
import s3d  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
WORK = argv[0]
MODE = argv[1] if len(argv) > 1 else "full"
B = s3d.load_beats(os.path.join(WORK, "beats.json"))
END = B[-1]["fe"] + 15

s3d.new_short()
import bpy  # noqa: E402
bpy.context.scene.frame_end = END
s3d.backyard()
g = s3d.ground_section(width=18)

# 0 — dig + fill
s3d.dig(g, x=0, width=7, depth=2.6, start=s3d.when(B, 0, "dig"), end=s3d.when(B, 0, "and"))
water_mat = s3d.mat_water()
muddy = s3d.origin_to_base(s3d.box("Water", (6.9, 2.9, 2.2), (0, 1.45, -1.5), water_mat, bevel=0.0))
s3d.grow(muddy, s3d.when(B, 0, "fill"), dur=30)
water_node = next(n for n in water_mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
water_node.inputs["Base Color"].default_value = (0.32, 0.22, 0.10, 1)  # dirty water first

# 1 — mud walls cave in: dirt chunks drop into the water, the hole shakes
chunks = []
for i in range(6):
    c = s3d.box(f"Mud{i}", (0.7, 0.6, 0.5), ((-1) ** i * (2.4 - i * 0.25), 0.4 + i * 0.3, -0.3), s3d.mat("Mud", s3d.PAL["soil"], rough=1.0, noise=0.5), bevel=0.15)
    s3d.drop_in(c, s3d.when(B, 1, "cave", i * 3), height=1.2, dur=12, sfx="crunch")
    chunks.append(c)
s3d.shake(muddy, s3d.when(B, 1, "cave"), dur=14)

# 2 — concrete with rebar; dirty water and mud go away, clean water comes back
f2 = s3d.when(B, 2, "pour")
s3d.shrink_out(muddy, f2 - 6, dur=6)
for c in chunks:
    s3d.shrink_out(c, f2 - 6, dur=6)
parts = [s3d.box("WallL", (0.3, 3.0, 2.6), (-3.4, 1.5, -1.3), s3d.mat_concrete()),
         s3d.box("WallR", (0.3, 3.0, 2.6), (3.4, 1.5, -1.3), s3d.mat_concrete()),
         s3d.box("Floor", (7.1, 3.0, 0.3), (0, 1.5, -2.45), s3d.mat_concrete())]
steel = s3d.mat("Rebar", (0.55, 0.22, 0.08), rough=0.5, metal=0.4)
for x in (-3.4, 3.4):
    for z in (-0.5, -1.2, -1.9):
        parts.append(s3d.cylinder("Rebar", 0.07, 3.06, (x, 1.5, z), rot=(1.5708, 0, 0), mat=steel, verts=16))
concrete = s3d.group("Concrete", parts)
s3d.drop_in(concrete, f2, height=7, dur=16)
s3d.tag("steel bars", loc=(-2.4, -0.1, -0.85), frame=s3d.when(B, 2, "steel"))
clean_mat = s3d.mat_water()
water = s3d.origin_to_base(s3d.box("CleanWater", (6.5, 2.9, 2.0), (0, 1.45, -1.25), clean_mat, bevel=0.0))
s3d.grow(water, s3d.when(B, 2, "steel", 10), dur=28)

# 3 — water turns green
s3d.color_to(clean_mat, (0.12, 0.42, 0.10), s3d.when(B, 3, "green", -8), dur=24)

# 4 — pump + filter on the lawn, pipe into the pool, water clean again
pump = s3d.box("Pump", (0.8, 0.6, 0.6), (5.0, 0.6, 0.3), s3d.mat("PumpBody", (0.15, 0.35, 0.75), rough=0.35, noise=0.1))
s3d.slide_in(pump, s3d.when(B, 4, "pump"), offset=(5, 0, 0))
filt = s3d.cylinder("Filter", 0.38, 1.1, (6.2, 0.6, 0.55), mat=s3d.mat("FilterBody", (0.92, 0.92, 0.9), rough=0.3))
s3d.drop_in(filt, s3d.when(B, 4, "filter"), height=5, dur=14)
s3d.tag("filter", loc=(6.2, 0.15, 1.45), frame=s3d.when(B, 4, "this"))
pipe = s3d.origin_to_base(s3d.cylinder("Pipe", 0.07, 2.4, (4.3, 0.5, -1.9), mat=s3d.mat_steel()))
s3d.grow(pipe, s3d.when(B, 4, "pump", 12), dur=16)
s3d.color_to(clean_mat, (0.10, 0.45, 0.75), s3d.when(B, 4, "this"), dur=30)

# 5 — freezing: ice sheet on top
ice = s3d.box("Ice", (6.5, 2.9, 0.12), (0, 1.45, -0.2), s3d.mat("Ice", (0.85, 0.95, 1.0), rough=0.15), bevel=0.02)
s3d.pop_in(ice, s3d.when(B, 5, "freezing"), dur=10, sfx="crack")

# 6 — heater melts the ice
heater = s3d.box("Heater", (0.9, 0.7, 1.1), (-5.2, 0.6, 0.55), s3d.mat("HeaterBody", (0.85, 0.22, 0.12), rough=0.4, noise=0.1))
s3d.slide_in(heater, s3d.when(B, 6, "heater"), offset=(-5, 0, 0))
s3d.tag("heater", loc=(-5.2, 0.18, 1.4), frame=s3d.when(B, 6, "heater", 8))
s3d.shrink_out(ice, s3d.when(B, 6, "next"), dur=14)

# 7 — ladder + lights, pull back
lad = s3d.ladder("Ladder", height=2.6, width=0.55, loc=(2.6, 0.5, -2.3))
s3d.drop_in(lad, s3d.when(B, 7, "ladder"), height=5, dur=14)
for i, x in enumerate((-2.0, 0.0, 2.0)):
    lt = s3d.cylinder(f"Light{i}", 0.14, 0.04, (x, 0.02, -1.6), rot=(1.5708, 0, 0), mat=s3d.mat_emit("LightGlow", (1.0, 0.95, 0.8), 6.0))
    s3d.pop_in(lt, s3d.when(B, 7, "lights", i * 4), dur=8)

# camera: wide → push into the work → follow the side props → pull back for the payoff
cam = s3d.camera_cutaway(target=(0, 0, -1.4), dist=13)
s3d.cam_move(cam, s3d.when(B, 1, "cave"), target=(0, 0, -1.7), dist=9.5, dur=30)
s3d.cam_move(cam, s3d.when(B, 2, "steel"), target=(-2.2, 0, -1.6), dist=7, dur=24)
s3d.cam_move(cam, s3d.when(B, 3), target=(0, 0, -1.6), dist=9.5, dur=24)
s3d.cam_move(cam, s3d.when(B, 4, "filter"), target=(4.0, 0, -0.8), dist=8, dur=24)
s3d.cam_move(cam, s3d.when(B, 5), target=(0, 0, -1.5), dist=9.5, dur=20)
s3d.cam_move(cam, s3d.when(B, 6, "heater", 6), target=(-3.3, 0, -0.8), dist=8, dur=22)
s3d.cam_move(cam, s3d.when(B, 7, "ladder", 6), target=(0, 0, -1.4), dist=12, dur=30)
s3d.cam_drift(cam, s3d.when(B, 7, "congratulations"), END, amount=0.8)

if MODE == "preview":
    for i, b in enumerate(B):
        s3d.preview_still(os.path.join(WORK, f"prev_{i}.png"), frame=(b["fs"] + b["fe"]) // 2, scale=35)
else:
    s3d.render_mp4(os.path.join(WORK, "render.mp4"), scale=100 if MODE == "full" else 50)
