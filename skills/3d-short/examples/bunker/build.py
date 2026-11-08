"""Example build with a character: "How a hole becomes a bunker" — timed to the narration through beats.json.

  blender --background --python build.py -- <workdir> [preview|half|full]
<workdir> must contain beats.json (beats.py). Output: <workdir>/render.mp4 + render.sfx.json (SFX cues),
preview mode writes <workdir>/preview/beat_N.png stills instead.
"""
import math
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
import bpy  # noqa: E402
import s3d  # noqa: E402
import human  # noqa: E402
import assets  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
WORK = argv[0]
MODE = argv[1] if len(argv) > 1 else "full"
B = s3d.load_beats(os.path.join(WORK, "beats.json"))
END = B[-1]["fe"] + 45
W = lambda i, word=None, off=0: s3d.when(B, i, word, off)  # noqa: E731

s3d.new_short(seconds=END / 30)
sc = bpy.context.scene
sc.frame_end = END
s3d.backyard()
g = s3d.ground_section(width=18)

FLOOR = -3.2 + 0.08          # container floor (inside)
HOLE = dict(x=0, width=5.0, depth=3.2, back=3.0)

# ---------------------------------------------------------------- beat 0: dig, climb inside, shelter
bob = human.Human("Bob", loc=(-0.7, 1.1, s3d.TOP), facing=20, outfit=human.WORKER, seed=0, shovel=True)
f_dig, f_in = W(0, "dig"), W(0, "inside")
s3d.dig(g, start=f_dig, end=f_in, mound_side=-1, **HOLE)
bob.pose_at(1, "stand")
bob.hold(1, f_dig - 4)
bob.dig(f_dig, f_in, sink_to=-3.2)
bob.pose_at(W(0, "shelter", -4), "thumbs_up")
bob.hold(W(0, "shelter", -4), W(1, "rains"))
s3d.hide_at(bob.shovel, W(0, "shelter", -6))

# ---------------------------------------------------------------- beat 1: rain, walls cave in, he jumps out
f_rain, f_cave = W(1, "rains"), W(1, "cave")
sun = bpy.data.objects["Sun"]
s3d.light_level(sun, f_rain - 6, 1.2, dur=10)
s3d.light_level(sun, W(2), 4.5, dur=14)
bg = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND")
for fr, val in ((f_rain - 6, 0.9), (f_rain + 4, 0.35), (W(2), 0.35), (W(2, None, 14), 0.9)):
    bg.inputs["Strength"].default_value = val
    bg.inputs["Strength"].keyframe_insert("default_value", frame=fr)


def rain(f0, f1, n=700):
    import bmesh
    bm = bmesh.new()
    rng = __import__("random").Random(3)
    for _ in range(n):
        x, y, z = rng.uniform(-5, 5), rng.uniform(0.15, 7), rng.uniform(0, 12)
        L = rng.uniform(0.25, 0.45)
        vs = [bm.verts.new(v) for v in ((x, y, z), (x + 0.008, y, z), (x + 0.008, y, z + L), (x, y, z + L))]
        bm.faces.new(vs)
    me = bpy.data.meshes.new("Rain")
    bm.to_mesh(me)
    o = bpy.data.objects.new("Rain", me)
    sc.collection.objects.link(o)
    m = s3d.mat_emit("RainMat", (0.75, 0.85, 1.0), 0.8)
    o.data.materials.append(m)
    o.visible_shadow = False
    o.location.z = 0
    o.keyframe_insert("location", index=2, frame=f0)
    o.location.z = -6
    o.keyframe_insert("location", index=2, frame=f0 + 9)
    for fc in s3d.fcurves(o):
        if fc.data_path == "location":
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
            fc.modifiers.new("CYCLES")
    s3d._hide_before(o, f0)
    s3d.hide_at(o, f1)
    s3d.marker("rain", f0, gain=-4, seconds=5)
    return o


rain(f_rain, W(2, None, 6))
chunks = []
mud = s3d.tex("brown_mud_02", tile=1.0, tint=(0.75, 0.6, 0.5), fallback=s3d.PAL["topsoil"], name="WetMud")
for i, (x, z, s) in enumerate(((-1.7, -1.3, 0.62), (1.75, -1.6, 0.66), (-1.3, -2.5, 0.55), (1.35, -2.7, 0.6), (-0.3, -2.95, 0.5), (0.6, -2.9, 0.45))):
    c = s3d.rock(f"Mud{i}", s, (x, 1.2, z), mud, seed=40 + i, flat=0.55)
    c.modifiers["Lumpy"].strength = s * 0.6
    s3d.slide_in(c, f_cave + i * 3, offset=(2.2 if x > 0 else -2.2, 0, 1.2), dur=14, sfx="crack" if i == 0 else None)
    chunks.append(c)
bob.act(f_cave - 6, "scared", cycles=1, period=10)
bob.jump(W(1, "you"), W(1, "you", 16), to=(3.5, 1.2, s3d.TOP), height=2.2)
bob.turn(W(1, "you", 16), -25)

# ---------------------------------------------------------------- beat 2: steel shipping container
f_low, f_cont = W(2, "lower"), W(2, "container")
cont = s3d.hollow_box("Container", (4.7, 2.5, 2.5), wall=0.08, loc=(0, 1.32, -3.2 + 1.25),
                      mat=s3d.tex("corrugated_iron_02", tile=1.2, tint=(1.55, 0.62, 0.32), fallback=(0.7, 0.25, 0.12), name="ContainerPaint"))
floor_ = s3d.box("ContainerFloor", (4.5, 2.32, 0.04), (0, 1.32, FLOOR + 0.0), s3d.tex("plank_flooring", tile=1.5, fallback=(0.5, 0.35, 0.2), name="Floorboards"), bevel=0)
floor_.parent = cont
floor_.matrix_parent_inverse = cont.matrix_world.inverted()
land = f_cont - 14
s3d.drop_in(cont, land - 16, height=6.5, dur=16, sfx="heavy")
for c in chunks:
    s3d.shrink_out(c, land - 6, dur=6)
s3d.tag("steel container", (0, -0.12, -0.55), W(2, "steel"), hold=80)
bob.pose_at(f_low, "point_left")
bob.hold(f_low, W(3) - 4)

# ---------------------------------------------------------------- beat 3: hatch + ladder, he climbs down
LX, LY = 1.85, 2.15
f_hatch, f_lad = W(3, "hatch"), W(3, "ladder")
hcut = s3d.box("HatchCut", (0.72, 0.72, 0.5), (LX, LY, -0.7), bevel=0)
hcut.hide_render = True
hcut.display_type = "WIRE"
hcut["s3d_always_hidden"] = 1
hm = cont.modifiers.new("Hatch", "BOOLEAN")
hm.operation, hm.object = "DIFFERENCE", hcut
cont.modifiers.move(len(cont.modifiers) - 1, 1)
hcut.parent = cont
hcut.matrix_parent_inverse = cont.matrix_world.inverted()
hcut.scale = (0.001, 0.001, 0.001)
s3d._key(hcut, f_hatch, scale=True)
hcut.scale = (1, 1, 1)
s3d._key(hcut, f_hatch + 2, scale=True)
lid = s3d.box("HatchLid", (0.75, 0.75, 0.06), (LX, LY, -0.65), s3d.mat_steel(), bevel=0.01)
rim = s3d.box("HatchRim", (0.85, 0.85, 0.05), (LX, LY, -0.68), s3d.mat("HatchDark", (0.04, 0.04, 0.04), rough=0.8), bevel=0.01)
s3d.pop_in(rim, f_hatch, sfx="clank")
s3d.pop_in(lid, f_hatch)
lid.rotation_euler.x = 0
s3d._key(lid, f_hatch + 12, rot=True)
lid.location.y += 0.38
lid.location.z += 0.36
lid.rotation_euler.x = math.radians(-95)
s3d._key(lid, f_hatch + 22, rot=True, loc=True)
lid.location.y -= 0.38
lid.location.z -= 0.36
s3d._key(lid, f_hatch + 12, loc=True)
s3d.tag("hatch", (LX, -0.12, -0.5), f_hatch, hold=60)
lad = s3d.ladder("Ladder", height=3.9, width=0.5, loc=(LX, LY + 0.12, FLOOR))
s3d.slide_in(lad, f_lad, offset=(0, 0, 4.5), dur=16, sfx="clank")
bob.walk(f_hatch, f_lad + 10, to=(2.85, LY - 0.1), face_end=-90)
top = f_lad + 18
bob.jump(top, top + 10, to=(LX, LY - 0.1, s3d.TOP + 0.1), height=0.4)
bob.climb(top + 10, W(4, None, 6), z_from=s3d.TOP + 0.1, z_to=FLOOR, facing=180)

# ---------------------------------------------------------------- beat 4: thick air, coughing
f_air = W(4, "air")
haze_m = s3d.mat("Haze", (0.30, 0.38, 0.12), rough=1.0)
hb = next(n for n in haze_m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
try:
    haze_m.surface_render_method = "BLENDED"
except Exception:
    haze_m.blend_method = "BLEND"
haze = s3d.box("Haze", (4.45, 2.2, 2.3), (0, 1.35, -3.2 + 1.25), haze_m, bevel=0)
haze.visible_shadow = False
for fr, a in ((f_air - 1, 0.0), (f_air + 30, 0.2), (W(5, "surface"), 0.2), (W(5, "surface", 30), 0.0)):
    hb.inputs["Alpha"].default_value = a
    hb.inputs["Alpha"].keyframe_insert("default_value", frame=fr)
s3d.tag("1 hour later", (0, -0.12, -0.6), W(4, "hour", -4), hold=55)
fw = W(4, None, 8)
bob.walk(fw, fw + 30, to=(0.4, 1.05, FLOOR), face_end=40)
bob.act(W(4, "thick"), "cough", cycles=4, period=14)
bob.pose_at(W(4, "thick") + 56, "stand")

# ---------------------------------------------------------------- beat 5: vent pipe up to the surface
f_vent = W(5, "vent")
pipe_m = s3d.mat_steel()
pipe = s3d.origin_to_base(s3d.cylinder("Vent", 0.11, 1.75, (-1.55, 2.0, -0.72 + 0.875), mat=pipe_m, verts=24))
cap = s3d.cylinder("VentCap", 0.2, 0.08, (-1.55, 2.0, 1.1), mat=pipe_m, verts=24)
s3d.grow(pipe, f_vent, dur=24, sfx="clank")
s3d.pop_in(cap, f_vent + 22, sfx="pop")
s3d.tag("vent pipe", (-1.55, -0.12, -0.35), W(5, "pipe"), hold=70)
bob.pose_at(W(5, "surface", 10), "relieved")
bob.hold(W(5, "surface", 10), W(6, None, 4))

# ---------------------------------------------------------------- beat 6: lamp, bed, canned food
f_lamp, f_bed, f_food = W(6, "lamp"), W(6, "bed"), W(6, "canned")
cord = s3d.cylinder("Cord", 0.008, 0.35, (0.2, 1.3, -0.78 - 0.175), mat=s3d.mat("Cord", (0.05, 0.05, 0.05)), verts=8)
bulb_m = s3d.mat_emit("Bulb", (1.0, 0.8, 0.5), 0.0)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.07, location=(0.2, 1.3, -1.18))
bulb = bpy.context.active_object
bulb.data.materials.append(bulb_m)
lamp = s3d.group("Lamp", [cord, bulb])
s3d.pop_in(lamp, f_lamp, sfx="pop")
L = bpy.data.lights.new("LampLight", "POINT")
L.color = (1.0, 0.78, 0.5)
L.energy = 0
L.shadow_soft_size = 0.1
lo = bpy.data.objects.new("LampLight", L)
sc.collection.objects.link(lo)
lo.location = (0.2, 1.1, -1.3)
L.keyframe_insert("energy", frame=f_lamp + 8)
s3d.light_level(lo, f_lamp + 9, 120, dur=2)
s3d.emit_level(bulb_m, f_lamp + 9, 25, dur=2)
s3d.marker("click", f_lamp + 9)
wood = s3d.mat_wood()
bed = s3d.group("Bed", [
    s3d.box("BedFrame", (1.95, 0.95, 0.32), (-1.25, 1.65, FLOOR + 0.16), wood, bevel=0.02),
    s3d.box("Mattress", (1.85, 0.88, 0.18), (-1.25, 1.65, FLOOR + 0.41), s3d.mat("Mattress", (0.92, 0.92, 0.9), rough=0.9), bevel=0.06),
    s3d.box("Blanket", (1.2, 0.92, 0.06), (-0.95, 1.65, FLOOR + 0.52), s3d.mat("Blanket", (0.2, 0.32, 0.55), rough=0.9, noise=0.3), bevel=0.03),
    s3d.box("Pillow", (0.38, 0.6, 0.12), (-1.95, 1.65, FLOOR + 0.56), s3d.mat("Pillow", (0.97, 0.97, 0.97), rough=0.9), bevel=0.05),
], origin="base")
s3d.drop_in(bed, f_bed - 10, height=3.5, dur=12, sfx="wood")
food = []
try:
    cr = assets.model("wooden_crate_01", size=0.75, loc=(1.1, 1.0, FLOOR))
    cans = assets.model("russian_food_cans_01", size=0.35, loc=(1.1, 1.0, FLOOR + 0.4))
    food = [cr, cans]
except Exception as e:
    print("crate/cans unavailable:", e)
    food = [s3d.box("Crate", (0.7, 0.45, 0.4), (1.1, 1.0, FLOOR + 0.2), wood)]
for k, o in enumerate(food):
    s3d.drop_in(o, f_food - 8 + k * 5, height=3.0, dur=10, sfx="wood" if k == 0 else "pop")
bob.pose_at(f_bed, "point_left")
bob.hold(f_bed, W(7) - 14)

# ---------------------------------------------------------------- beat 7: congratulations — he goes to bed
f_c = W(7)
HIP = (-1.15, 1.65, FLOOR + 0.6)
bob.walk(f_c - 16, f_c + 6, to=(HIP[0], HIP[1] - 0.75, FLOOR), face_end=0)
bob.lie(f_c + 34, hip=HIP, head_dir=-1)
bob.hold(f_c + 34, END, breathe=True)
s3d.marker("ding", W(7, "bunker"), gain=-4)

# ---------------------------------------------------------------- camera: one dolly axis, eased moves between beats
cam = s3d.camera_cutaway(target=(-0.6, 0, -0.45), dist=7.6)                    # close on Bob as he starts digging
s3d.cam_move(cam, W(0, "inside"), target=(-0.5, 0, -1.75), dist=7.6, dur=50)     # follow him down
s3d.cam_move(cam, W(1, "cave"), target=(0, 0, -1.6), dist=9.2, dur=24)           # whole hole for the collapse
s3d.cam_move(cam, W(1, "you", 6), target=(0.8, 0, -0.9), dist=10.0, dur=14)      # catch the jump
s3d.cam_move(cam, W(2, None, 4), target=(0.4, 0, -1.4), dist=11.5, dur=24)       # wide for the container drop
s3d.cam_move(cam, W(3, "hatch"), target=(1.3, 0, -0.9), dist=8.4, dur=20)        # hatch + Bob on the lawn
s3d.cam_move(cam, W(3, "climb", 10), target=(1.0, 0, -2.1), dist=7.6, dur=40)    # follow him down the ladder
s3d.cam_move(cam, W(4, "air"), target=(0.4, 0, -2.35), dist=5.7, dur=28)         # close: coughing
s3d.cam_move(cam, W(5, "vent", 6), target=(-0.5, 0, -1.25), dist=9.5, dur=24)    # pipe to the surface
s3d.cam_move(cam, W(6, "lamp"), target=(-0.2, 0, -2.25), dist=7.0, dur=24)       # furnishing
s3d.cam_move(cam, f_c + 48, target=(0, 0, -1.55), dist=10.8, dur=50)             # payoff: pull back

# ---------------------------------------------------------------- output
if MODE == "preview":
    out = os.path.join(WORK, "preview")
    os.makedirs(out, exist_ok=True)
    frames = sorted(set(int(x) for x in os.environ.get("FRAMES", "").split(",") if x) or
                    [W(0, "dig", 30), W(0, "shelter", 6), W(1, "cave", 10), W(1, "you", 8), W(2, "container", 6), W(3, "ladder", 30),
                     W(4, "thick", 4), W(4, "thick", 11), W(5, "surface"), W(6, "canned", 10), W(7, None, 30), W(7, None, 44), W(7, "bunker", 14), END - 2])
    for fr in frames:
        s3d.preview_still(os.path.join(out, f"f{fr:04d}.png"), frame=fr, scale=40)
    s3d.export_markers(os.path.join(WORK, "render.sfx.json"))
else:
    if MODE == "half":
        sc.eevee.taa_render_samples = 16
    s3d.render_mp4(os.path.join(WORK, "render.mp4"), scale=50 if MODE == "half" else 100)
