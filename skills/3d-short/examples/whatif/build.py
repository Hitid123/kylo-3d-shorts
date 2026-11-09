"""Example "What if" short in the realistic explainer look: "What happens if you hold in a sneeze?"

  blender --background --python build.py -- <workdir> [preview|half|full]

<workdir> needs beats.json (beats.py). The character is made once with MPFB (mh.py make) into
<workdir>/guy.blend; later builds reuse it. Output: render.mp4 + render.sfx.json, or preview/f####.png.

The look (what makes these read as "realistic 3D explainer" and not "toy"):
  * a realistic person in close-ups (85 mm, f/2.8, the background melts), bright daylight, saturated tee;
  * an X-ray view whenever the story goes inside the body: glass-blue skin on a dark navy void, wet red organs,
    glowing particles for air/blood, the camera in profile so the anatomy reads;
  * hard cuts every 2-5 s between real view and X-ray, each shot with a slow push-in;
  * one clear thing happens per shot, on the word that names it.
Facts in script.txt: BMJ Case Reports 2018 ("Snap, crackle and pop: when sneezing leads to crackling in the neck").
"""
import math
import os
import random
import subprocess
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


SCRIPTS = _find_scripts(HERE)
sys.path.insert(0, SCRIPTS)
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
import s3d  # noqa: E402
import mh  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
WORK = os.path.abspath(argv[0])
MODE = argv[1] if len(argv) > 1 else "full"
B = s3d.load_beats(os.path.join(WORK, "beats.json"))
END = B[-1]["fe"] + 30
W = lambda i, word=None, off=0: s3d.when(B, i, word, off)  # noqa: E731
rnd = random.Random(3)

# ---------------------------------------------------------------- the character (made once, cached)
GUY = os.path.join(WORK, "guy.blend")
if not os.path.exists(GUY):
    subprocess.run([bpy.app.binary_path, "-b", "--python", os.path.join(SCRIPTS, "mh.py"), "--", "make", GUY,
                    '{"name": "guy", "shirt": [0.78, 0.06, 0.03]}'], check=True)

s3d.new_short(seconds=END / 30, sun_elev=40, sun_azim=-25)
sc = bpy.context.scene
sc.frame_end = END
sc.render.motion_blur_shutter = 0.4
try:
    sc.view_settings.look = os.environ.get("S3D_LOOK", "AgX - Punchy")   # saturated, the explainer look
except TypeError:
    pass

PARK = Vector((0, 3.6, s3d.TOP))
XRAY = Vector((60, -30, 0))     # far from the backyard (its far lawn starts at y = 6.5)
WARD = Vector((-60, -30, 0))

# ================================================================= zone 1: the park (real view)
s3d.backyard()
s3d.ground_section(width=18, stones=0, roots=0)
guy = mh.Person(GUY, loc=PARK, facing=0, name="guy")

# ================================================================= zone 2: X-ray studio
xr = mh.Person(GUY, loc=XRAY, facing=0, name="xray")


def mat_glass_skin():
    m = bpy.data.materials.new("XrayGlass")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 2.0
    nt.links.new(lw.outputs["Facing"], pw.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.18, 0.55, 1.0, 1)
    em.inputs["Strength"].default_value = 2.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    add.inputs[1].default_value = 0.03
    nt.links.new(pw.outputs[0], add.inputs[0])
    nt.links.new(add.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND"), ("use_backface_culling", True)):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    return m


GLASS = mat_glass_skin()
BONE = s3d.mat("XrayBone", (0.92, 0.88, 0.80), rough=0.35)
for o in xr.parts:
    if o == xr.body:
        for mod in list(o.modifiers):            # show the whole body, not only what the tee leaves bare
            if mod.type == "MASK" and mod.name.startswith("Delete"):
                o.modifiers.remove(mod)
        o.data.materials.clear()
        o.data.materials.append(GLASS)
    elif "teeth" in o.name:
        o.data.materials.clear()
        o.data.materials.append(BONE)
    else:
        o.hide_render = True
        o.hide_viewport = True

# dark navy void around the X-ray person (it also blocks the daylight)
bpy.ops.mesh.primitive_uv_sphere_add(radius=4.0, location=XRAY + Vector((0, 0, 1.3)), segments=48, ring_count=24)
void = bpy.context.active_object
void.name = "XrayVoid"
void.data.materials.append(s3d.mat_emit("Void", (0.010, 0.030, 0.085), 1.0))
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.flip_normals()
bpy.ops.object.mode_set(mode="OBJECT")


def light(name, kind, loc, energy, size=1.0, color=(1, 1, 1), aim=None):
    d = bpy.data.lights.new(name, kind)
    d.energy = energy
    d.color = color
    if kind == "AREA":
        d.size = size
    o = bpy.data.objects.new(name, d)
    sc.collection.objects.link(o)
    o.location = loc
    if aim is not None:
        o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


light("XKey", "AREA", XRAY + Vector((1.2, -0.6, 1.9)), 60, 1.0, (1.0, 0.92, 0.88), aim=XRAY + Vector((0, 0, 1.45)))
light("XRim", "AREA", XRAY + Vector((-0.9, 0.9, 1.8)), 40, 1.0, (0.6, 0.8, 1.0), aim=XRAY + Vector((0, 0, 1.45)))

# ---------- anatomy, in the X-ray person's rig space (from this body's real landmarks)
R = xr.rig.matrix_world
N = xr.A["nose_tip"]
MO = xr.A["mouth"]
TH = xr.A["throat"]
bones = {b.name: b for b in xr.rig.data.bones}
hz = bones["head"].head_local.z            # skull base
cz = bones["clavicle.L"].head_local.z      # top of the chest


def P(x, y, z):
    return Vector((x, y, z))


NASAL = [N + P(0, 0.012, -0.010), N + P(0, 0.045, -0.006), P(0, N.y + 0.088, N.z - 0.004), P(0, -0.066, N.z - 0.012)]
ORAL = [MO + P(0, 0.008, 0.0), P(0, MO.y + 0.05, MO.z + 0.004), P(0, -0.072, MO.z - 0.004)]
PHARYNX = [P(0, -0.066, N.z - 0.012), P(0, -0.060, MO.z - 0.012), P(0, -0.056, TH.z + 0.03), P(0, -0.060, TH.z - 0.005),
           P(0, -0.056, cz - 0.01), P(0, -0.046, cz - 0.08), P(0, -0.038, cz - 0.15)]
CARINA = PHARYNX[-1]
BRONCHI = [[CARINA, CARINA + P(s * 0.035, 0.0, -0.035), CARINA + P(s * 0.07, 0.01, -0.08)] for s in (-1, 1)]

AIRWAY = s3d.mat("Airway", (0.42, 0.015, 0.015), rough=0.22)
ab = next(n for n in AIRWAY.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
ab.inputs["Emission Color"].default_value = (1.0, 0.15, 0.05, 1)
ab.inputs["Emission Strength"].default_value = 0.0
for k in ("Subsurface Weight",):
    if k in ab.inputs:
        ab.inputs[k].default_value = 0.3


def tube(name, pts, radius, mat, parent_bone):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 6
    cu.use_fill_caps = True
    sp = cu.splines.new("NURBS")
    sp.points.add(len(pts) - 1)
    for p_, v in zip(sp.points, pts):
        p_.co = (v.x, v.y, v.z, 1)
    sp.use_endpoint_u = True
    sp.order_u = 3
    o = bpy.data.objects.new(name, cu)
    sc.collection.objects.link(o)
    o.data.materials.append(mat)
    attach(o, parent_bone, R)
    return o


def attach(o, bone, local=None):
    """Parent to a bone of the X-ray rig keeping o's rig-space placement."""
    wm = local @ o.matrix_basis if local is not None else o.matrix_basis.copy()
    o.parent = xr.rig
    o.parent_type = "BONE"
    o.parent_bone = bone
    bpy.context.view_layer.update()
    o.matrix_world = wm


tube("NasalPassage", NASAL, 0.0075, AIRWAY, "head")
tube("OralPassage", ORAL, 0.008, AIRWAY, "head")
pharynx = tube("Pharynx", PHARYNX, 0.0115, AIRWAY, "spine01")
for i, br in enumerate(BRONCHI):
    tube(f"Bronchus{i}", br, 0.0065, AIRWAY, "spine01")

LUNG = s3d.mat("Lung", (0.70, 0.12, 0.13), rough=0.35)
lb = next(n for n in LUNG.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
lb.inputs["Alpha"].default_value = 0.6
for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
    try:
        setattr(LUNG, attr, val)
    except Exception:
        pass
for s in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=32, ring_count=16)
    lu = bpy.context.active_object
    lu.name = f"Lung{s}"
    lu.scale = (0.065, 0.06, 0.115)
    lu.location = R @ (CARINA + P(s * 0.085, 0.015, -0.085))
    bpy.ops.object.shade_smooth()
    lu.data.materials.append(LUNG)
    attach(lu, "spine01")

# vertebrae: neck (follows the neck bones) + upper back
neck_line = [bones["neck03"].tail_local, bones["neck03"].head_local, bones["neck02"].head_local,
             bones["neck01"].head_local, bones["spine01"].tail_local]
for i in range(9):
    t = i / 8
    z = hz - 0.01 - t * (hz - cz + 0.12)
    y = -0.012 + 0.03 * max(0, (cz - z) / 0.15) + 0.004 * math.sin(t * 3)
    v = s3d.box(f"Vert{i}", (0.032, 0.026, 0.013), (0, 0, 0), BONE, bevel=0.004)
    v.location = R @ P(0, y, z)
    attach(v, "spine01" if z < cz else "neck02")

# ---------- air particles: rush up from the lungs and pile up in the throat (nowhere to go)
AIRM = s3d.mat_emit("AirGlow", (0.6, 0.9, 1.0), 14.0)
path = list(reversed(PHARYNX))  # carina -> nasopharynx


def along(u):
    """Point on the airway polyline, u in 0..1 from carina to the back of the nose."""
    segs = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
    lens = [(b_ - a_).length for a_, b_ in segs]
    d = u * sum(lens)
    for (a_, b_), L in zip(segs, lens):
        if d <= L:
            return a_.lerp(b_, d / L)
        d -= L
    return path[-1]


f_air = W(2, "comes")
f_stuck = W(2, "nowhere")
f_spike = W(3, "spikes")
particles = []
for k in range(70):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=0.0035 + rnd.random() * 0.003, subdivisions=2)
    a = bpy.context.active_object
    a.name = f"Air{k}"
    a.data.materials.append(AIRM)
    a.parent = xr.rig
    jitter = lambda: P((rnd.random() - 0.5) * 0.012, (rnd.random() - 0.5) * 0.012, 0)  # noqa: E731
    t0 = f_air - 6 + rnd.randint(0, 26)
    a.location = along(0.0) + jitter() + P(0, 0, -0.02)
    a.scale = (0, 0, 0)
    a.keyframe_insert("scale", frame=t0 - 1)
    a.scale = (1, 1, 1)
    a.keyframe_insert("scale", frame=t0)
    a.keyframe_insert("location", frame=t0)
    u_end = 0.55 + rnd.random() * 0.45
    a.location = along(u_end) + jitter()
    a.keyframe_insert("location", frame=t0 + 16 + rnd.randint(0, 8))
    # trapped: jitter around the throat until the tear
    f = t0 + 26
    while f < W(6) + 20:
        a.location = along(0.45 + rnd.random() * 0.5) + jitter()
        a.keyframe_insert("location", frame=f)
        f += 5 + rnd.randint(0, 5)
    particles.append(a)

# blocked exits: red pulses at the nostrils and the lips
STOP = s3d.mat_emit("StopGlow", (1.0, 0.08, 0.03), 0.0)
stops = []
for name, pt in (("StopNose", NASAL[0]), ("StopMouth", ORAL[0])):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.012, segments=24, ring_count=12)
    st = bpy.context.active_object
    st.name = name
    st.scale = (1, 0.5, 1)
    st.data.materials.append(STOP)
    st.location = R @ pt
    attach(st, "head")
    stops.append(st)
for st in stops:                      # only exists while the exits are blocked
    st.scale = (0, 0, 0)
    st.keyframe_insert("scale", frame=f_stuck - 5)
    st.scale = (1, 0.5, 1)
    st.keyframe_insert("scale", frame=f_stuck - 3)
    st.keyframe_insert("scale", frame=f_spike + 48)
    st.scale = (0, 0, 0)
    st.keyframe_insert("scale", frame=f_spike + 52)
se = STOP.node_tree.nodes["Emission"].inputs["Strength"]
for f, v in ((f_stuck - 4, 2), (f_stuck + 2, 9), (f_stuck + 10, 2), (f_stuck + 16, 9), (f_stuck + 24, 2), (f_spike + 40, 2), (f_spike + 50, 2)):
    se.default_value = v
    se.keyframe_insert("default_value", frame=f)

# pressure: the throat swells and glows
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=32, ring_count=16)
bulge = bpy.context.active_object
bulge.name = "PressureBulge"
bpy.ops.object.shade_smooth()
bulge.data.materials.append(AIRWAY)
bulge.location = R @ P(0, -0.058, (MO.z + TH.z) / 2 - 0.01)
attach(bulge, "spine01")
r0 = 0.0105
bulge.scale = (r0, r0, 0.03)
bulge.keyframe_insert("scale", frame=f_spike - 30)
for f, k in ((f_spike - 6, 1.6), (f_spike, 2.05), (f_spike + 6, 1.85), (f_spike + 12, 2.15), (f_spike + 20, 1.95), (f_spike + 30, 2.2)):
    bulge.scale = (r0 * k, r0 * k * 0.9, 0.03 + 0.012 * (k - 1))
    bulge.keyframe_insert("scale", frame=f)
ee = ab.inputs["Emission Strength"]
for f, v in ((f_spike - 30, 0.0), (f_spike, 1.6), (f_spike + 8, 0.9), (f_spike + 16, 1.8), (W(4), 1.4), (W(6), 1.4), (W(6) + 40, 0.5)):
    ee.default_value = v
    ee.keyframe_insert("default_value", frame=f)

# the tear (back wall of the throat) and the air leaking into the neck and chest
f_tear = W(6, "torn")
f_leak = W(6, "leaked")
TEAR = s3d.mat_emit("TearGlow", (1.0, 0.35, 0.08), 8.0)
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=24, ring_count=12)
tear = bpy.context.active_object
tear.name = "Tear"
tear.data.materials.append(TEAR)
tear.location = R @ P(0, -0.0455, TH.z + 0.025)
attach(tear, "spine01")
tear.scale = (0, 0, 0)
tear.keyframe_insert("scale", frame=f_tear - 2)
tear.scale = (0.006, 0.002, 0.016)
tear.keyframe_insert("scale", frame=f_tear + 3)

BUB = bpy.data.materials.new("Bubble")
BUB.use_nodes = True
bnt = BUB.node_tree
bnt.nodes.clear()
bo = bnt.nodes.new("ShaderNodeOutputMaterial")
blw = bnt.nodes.new("ShaderNodeLayerWeight")
blw.inputs["Blend"].default_value = 0.25
bem = bnt.nodes.new("ShaderNodeEmission")
bem.inputs["Color"].default_value = (0.75, 0.92, 1.0, 1)
bem.inputs["Strength"].default_value = 5.0
btr = bnt.nodes.new("ShaderNodeBsdfTransparent")
bmx = bnt.nodes.new("ShaderNodeMixShader")
bnt.links.new(blw.outputs["Facing"], bmx.inputs[0])
bnt.links.new(btr.outputs[0], bmx.inputs[1])
bnt.links.new(bem.outputs[0], bmx.inputs[2])
bnt.links.new(bmx.outputs[0], bo.inputs[0])
for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
    try:
        setattr(BUB, attr, val)
    except Exception:
        pass
src = P(0, -0.044, TH.z + 0.025)
for k in range(110):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=16, ring_count=8)
    b_ = bpy.context.active_object
    b_.name = f"Leak{k}"
    bpy.ops.object.shade_smooth()
    b_.data.materials.append(BUB)
    b_.parent = xr.rig
    late = k > 45                                   # the later ones travel down into the chest
    if late:
        dst = P((rnd.random() - 0.5) * 0.24, -0.09 + rnd.random() * 0.09, cz - 0.02 - rnd.random() * 0.17)
    else:
        dst = P((rnd.random() - 0.5) * 0.10, -0.075 + rnd.random() * 0.10, TH.z - 0.05 + rnd.random() * 0.11)
    t0 = f_leak - 8 + int((k / 110) * 60) + rnd.randint(0, 8)
    size = 0.0025 + rnd.random() * 0.0045
    b_.location = src
    b_.scale = (0, 0, 0)
    b_.keyframe_insert("scale", frame=t0)
    b_.keyframe_insert("location", frame=t0)
    b_.scale = (size, size, size)
    b_.keyframe_insert("scale", frame=t0 + 8)
    b_.location = dst
    b_.keyframe_insert("location", frame=t0 + 24 + rnd.randint(0, 16))

# ================================================================= zone 3: the hospital ward
WALL = s3d.mat("WardWall", (0.70, 0.82, 0.80), rough=0.8)
FLOOR = s3d.mat("WardFloor", (0.78, 0.78, 0.76), rough=0.35, noise=0.2, noise_scale=3)
WHITE = s3d.mat("WardWhite", (0.92, 0.93, 0.94), rough=0.5)
SHEET = s3d.mat("Sheet", (0.86, 0.90, 0.95), rough=0.85, noise=0.15, noise_scale=12)
BLANKET = s3d.mat("Blanket", (0.35, 0.55, 0.78), rough=0.9, noise=0.2, noise_scale=20)
STEEL = s3d.mat("WardSteel", (0.75, 0.76, 0.78), rough=0.25, metal=1.0)
wx, wy = WARD.x, WARD.y
s3d.box("WardFloor", (7, 7, 0.1), (wx, wy, -0.05), FLOOR, bevel=0)
s3d.box("WardBack", (7, 0.1, 3.2), (wx, wy + 1.4, 1.6), WALL, bevel=0)
s3d.box("WardLeft", (0.1, 7, 3.2), (wx - 2.6, wy, 1.6), WALL, bevel=0)
s3d.box("WardRight", (0.1, 7, 3.2), (wx + 2.8, wy, 1.6), WALL, bevel=0)
s3d.box("WardCeil", (7, 7, 0.1), (wx, wy, 3.2), WHITE, bevel=0)
s3d.box("WardFront", (7, 0.1, 3.2), (wx, wy - 3.4, 1.6), WALL, bevel=0)
win = s3d.box("WardWindow", (1.6, 0.02, 1.1), (wx + 1.3, wy + 1.34, 1.75), s3d.mat_emit("WindowLight", (0.75, 0.88, 1.0), 2.0), bevel=0)
MATTRESS_TOP = 0.66
bed_x0, bed_len = wx - 1.2, 2.05
s3d.box("BedFrame", (bed_len + 0.1, 1.0, 0.12), (bed_x0 + bed_len / 2, wy, 0.46), WHITE, bevel=0.02)
for dx in (0.05, bed_len - 0.05):
    for dy in (-0.45, 0.45):
        s3d.cylinder("BedLeg", 0.025, 0.42, (bed_x0 + dx, wy + dy, 0.21), mat=STEEL, verts=16)
s3d.box("BedHead", (0.06, 1.0, 0.55), (bed_x0 + bed_len + 0.03, wy, 0.75), WHITE, bevel=0.02)
s3d.box("Mattress", (bed_len, 0.94, 0.14), (bed_x0 + bed_len / 2, wy, MATTRESS_TOP - 0.07), SHEET, bevel=0.05)
s3d.box("Pillow", (0.38, 0.62, 0.12), (bed_x0 + bed_len - 0.25, wy, MATTRESS_TOP + 0.05), SHEET, bevel=0.05)

ward = mh.Person(GUY, loc=(0, 0, 0), name="ward")
# lying on his back, head on the pillow (+X), face up
ward.rig.rotation_euler = (math.radians(-90), 0, math.radians(-90))
ward.rig.location = (bed_x0 + 0.12, wy, MATTRESS_TOP + 0.115)
bpy.context.view_layer.update()
s3d.box("Blanket", (1.25, 1.0, 0.07), (bed_x0 + 0.66, wy, MATTRESS_TOP + 0.21), BLANKET, bevel=0.03)

# feeding tube: nostril -> taped to the cheek -> up to the bag on the drip stand
nose_w = ward.anchor("nose_tip")
stand = Vector((bed_x0 + bed_len - 0.2, wy + 0.75, 0))
s3d.cylinder("DripPole", 0.012, 1.9, stand + Vector((0, 0, 0.95)), mat=STEEL, verts=16)
s3d.box("DripBase", (0.35, 0.35, 0.03), stand + Vector((0, 0, 0.02)), STEEL, bevel=0.01)
s3d.box("DripHook", (0.25, 0.012, 0.012), stand + Vector((0, 0, 1.88)), STEEL, bevel=0)
BAG = s3d.mat("FeedBag", (0.95, 0.92, 0.80), rough=0.2)
bag = s3d.box("FeedBag", (0.13, 0.04, 0.22), stand + Vector((0.08, 0, 1.70)), BAG, bevel=0.03)
TUBE = s3d.mat("TubeMat", (0.95, 0.90, 0.70), rough=0.2)
cu = bpy.data.curves.new("FeedTube", "CURVE")
cu.dimensions = "3D"
cu.bevel_depth = 0.003
sp = cu.splines.new("NURBS")
pts = [nose_w + Vector((0, 0, 0.004)), nose_w + Vector((-0.03, 0.06, 0.03)), nose_w + Vector((-0.02, 0.13, 0.03)),
       nose_w + Vector((0.05, 0.3, 0.25)), stand + Vector((0.08, -0.02, 1.2)), stand + Vector((0.08, 0, 1.58))]
sp.points.add(len(pts) - 1)
for p_, v in zip(sp.points, pts):
    p_.co = (*v, 1)
sp.use_endpoint_u = True
sp.order_u = 3
tube_o = bpy.data.objects.new("FeedTube", cu)
sc.collection.objects.link(tube_o)
cu.materials.append(TUBE)
s3d.box("Tape", (0.035, 0.03, 0.004), nose_w + Vector((-0.025, 0.06, 0.03)), WHITE, bevel=0.002)
# heart monitor
mon = Vector((bed_x0 + bed_len + 0.25, wy - 0.75, 1.35))
s3d.cylinder("MonPole", 0.015, 1.3, (mon.x, mon.y, 0.65), mat=STEEL, verts=12)
s3d.box("Monitor", (0.08, 0.32, 0.26), mon, s3d.mat("MonBody", (0.18, 0.19, 0.21), rough=0.4), bevel=0.015)
s3d.box("MonScreen", (0.005, 0.27, 0.2), mon + Vector((-0.042, 0, 0)), s3d.mat_emit("MonScreen", (0.02, 0.12, 0.06), 1.5), bevel=0)
pulse = s3d.box("MonLine", (0.004, 0.24, 0.006), mon + Vector((-0.046, 0, 0.02)), s3d.mat_emit("MonLine", (0.2, 1.0, 0.4), 8.0), bevel=0)
light("WardKey", "AREA", (wx + 1.3, wy + 0.6, 2.2), 70, 1.6, (1.0, 0.97, 0.92), aim=(bed_x0 + 1.6, wy, MATTRESS_TOP))
light("WardFill", "AREA", (wx - 0.6, wy - 2.4, 2.6), 45, 2.5, (0.9, 0.95, 1.0), aim=(bed_x0 + 1.6, wy, MATTRESS_TOP))
light("WardCeil", "AREA", (wx, wy, 3.05), 50, 2.0, (1.0, 0.98, 0.95), aim=(wx, wy, 0))

# ================================================================= the acting
f0 = 1
# beat 0 — the sneeze is coming (real, close-up)
guy.pose(f0, "idle")
guy.face(f0, "neutral")
guy.face(W(0, "hold"), "worried", dur=10)
guy.pose(W(0, "sneeze") - 4, "idle", pitch=-8, dur=14)
guy.face(W(0, "sneeze"), "pre_sneeze", dur=10)
guy.pose(B[0]["fe"] - 2, "idle", pitch=-15, spine=-4, dur=20)
guy.face(B[0]["fe"] - 2, "pre_sneeze", dur=14, jaw=12, lids=-0.75)
s3d.marker("whoosh", W(0, "sneeze") - 6, prompt="man inhales sharply twice before a sneeze, ah... ah...", gain=-2, seconds=2.5)
# beat 1 — pinch the nose, shut the mouth
guy.pose(W(1, "pinch"), "pinch_nose", dur=9, pitch=-6)
guy.face(W(1, "pinch"), "pre_sneeze", dur=6, jaw=4, lids=-0.6)
guy.face(W(1, "shut"), "squeeze", dur=6)
s3d.marker("click", W(1, "pinch"), prompt="fingers squeeze a nose shut, soft skin squish, close up", gain=-6)
s3d.marker("click", W(1, "shut"), prompt="lips press together, muffled hum, close up", gain=-8)
# beats 4-5 — the real case: held sneeze, then the pop
guy.pose(W(4) + 1, "pinch_nose", dur=1, pitch=-4)
guy.face(W(4) + 1, "squeeze", dur=1)
guy.face(W(4, "exactly") - 6, "puff", dur=6)
guy.jolt(W(4, "exactly") + 2, amount=0.8)
guy.face(W(4, "exactly") + 6, "squeeze", dur=4)
s3d.marker("pop", W(4, "exactly") + 2, prompt="muffled stifled sneeze held in with closed mouth, body jerks", gain=-2)
f_pop = W(5, "pop")
guy.face(f_pop, "shock", dur=3)
guy.pose(f_pop + 4, "grab_throat", dur=7, pitch=-4)
guy.face(f_pop + 30, "pain", dur=10)
s3d.marker("pop", f_pop, prompt="sharp wet pop inside a neck, close up, body horror", gain=0)
# beat 8 — this time he lets it out (into the elbow)
f8 = W(8)
guy.pose(f8 + 1, "idle", dur=1, pitch=-6)
guy.face(f8 + 1, "worried", dur=1)
cm, f_out = W(8, "comes"), W(8, "out")
# the arm folds up first (elbow_up), then the crook goes in front of the nose: no swing across the chest, no fist on the cheek.
# The sneeze itself is the head going down into the elbow (pitch), not the arm moving (a bigger pitch puts the face into the forearm).
guy.face(cm + 4, "pre_sneeze", dur=10, jaw=12, lids=-0.75)
guy.pose(cm + 14, "elbow_up", side="R", dur=24, pitch=-14, spine=-4)
guy.pose(f_out - 6, "elbow_sneeze", side="R", dur=10, pitch=-10, spine=-3)
guy.pose(f_out - 1, "elbow_sneeze", side="R", dur=5, pitch=9, spine=8)
guy.face(f_out - 1, "sneeze", dur=4)
guy.pose(f_out + 12, "elbow_sneeze", side="R", dur=13, pitch=3, spine=2)
guy.face(f_out + 12, "squeeze", dur=8)
guy.pose(f_out + 22, "elbow_up", side="R", dur=10, pitch=0)
guy.face(f_out + 22, "relief", dur=10)
guy.pose(f_out + 44, "idle", dur=22, pitch=-2)
s3d.marker("whoosh", f_out - 3, prompt="loud natural man sneeze into his elbow, ah-choo", gain=0, seconds=1.5)

# X-ray twin: pinching the whole time, tenses at the spike, grabs the throat after the pop
xr.pose(1, "pinch_nose", dur=0, pitch=-4)
xr.face(1, "squeeze", dur=0)
xr.jolt(f_spike, amount=0.35)
xr.pose(W(6), "idle", dur=1, pitch=-3)
xr.face(W(6), "pain", dur=1)
s3d.marker("whoosh", W(2), prompt="deep cinematic whoosh transition into an x-ray view", gain=-6)
s3d.marker("whoosh", f_air, prompt="rush of air forced up through a narrow tube, pressure building", gain=-4, seconds=2.5)
s3d.marker("heavy", f_spike, prompt="low tense rumble with creaking stretching rubber, pressure about to burst", gain=-4, seconds=3)
s3d.marker("whoosh", W(6), prompt="deep cinematic whoosh transition into an x-ray view", gain=-6)
s3d.marker("crack", f_tear, prompt="small wet tear of soft tissue, close up", gain=-2)
s3d.marker("pour", f_leak, prompt="tiny air bubbles fizzing and spreading under skin", gain=-6, seconds=4)

# hospital: resting, breathing, the monitor beeps
ward.pose(1, "idle", dur=0)
ward.face(1, "neutral", dur=0, lids=-0.35, brows=0.2)
ward.face(W(7, "healed"), "relief", dur=20)
for f in range(W(7), W(8), 24):
    pulse.scale = (1, 1, 1)
    pulse.keyframe_insert("scale", frame=f)
    pulse.scale = (1, 1, 9)
    pulse.keyframe_insert("scale", frame=f + 2)
    pulse.scale = (1, 1, 1)
    pulse.keyframe_insert("scale", frame=f + 5)
s3d.marker("ding", W(7), prompt="hospital heart monitor beeping slowly, quiet ward ambience", gain=-8, seconds=4)

# ================================================================= cameras: hard cuts, slow push-ins
CAMS = []


def shot(name, start, target, frm, lens=85, fstop=2.8, push=0.08, end=None, rise=0.0):
    """A camera at target+frm (world offset) looking at target; pushes in by `push` of the distance."""
    c = bpy.data.cameras.new(name)
    c.lens = lens
    c.clip_start = 0.02
    c.dof.use_dof = True
    c.dof.aperture_fstop = fstop
    o = bpy.data.objects.new(name, c)
    sc.collection.objects.link(o)
    t = Vector(target)
    o.location = t + Vector(frm)
    o.rotation_euler = (t - o.location).to_track_quat("-Z", "Y").to_euler()
    c.dof.focus_distance = (t - o.location).length
    o.keyframe_insert("location", frame=start)
    c.dof.keyframe_insert("focus_distance", frame=start)
    end = end or start + 120
    o.location = t + Vector(frm) * (1 - push) + Vector((0, 0, rise))
    c.dof.focus_distance = (t - o.location).length
    o.keyframe_insert("location", frame=end)
    c.dof.keyframe_insert("focus_distance", frame=end)
    for fc in s3d.fcurves(o) + s3d.fcurves(c):
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    m = sc.timeline_markers.new(name, frame=start)
    m.camera = o
    CAMS.append(o)
    return o


EYES = guy.anchor("eyes", 1)
THROAT = guy.anchor("throat", 1)
XE = xr.anchor("eyes", 1)
XT = xr.anchor("throat", 1)
shot("CamHook", 1, EYES + Vector((0, 0, -0.04)), (0.18, -0.95, 0.02), lens=85, push=0.12, end=B[1]["fs"])
shot("CamPinch", B[1]["fs"], EYES + Vector((0, 0, -0.10)), (0.75, -1.25, 0.05), lens=70, push=0.08, end=B[2]["fs"])
shot("CamXrayWide", B[2]["fs"], XE + Vector((0, 0.03, -0.17)), (1.05, -0.05, 0.0), lens=50, fstop=8, push=0.10, end=B[3]["fs"])
shot("CamXrayThroat", B[3]["fs"], XT + Vector((0, 0.02, 0.03)), (0.55, -0.12, 0.02), lens=60, fstop=8, push=0.12, end=B[4]["fs"])
shot("CamCase", B[4]["fs"], EYES + Vector((0, 0, -0.22)), (-0.55, -1.75, 0.0), lens=55, push=0.10, end=B[5]["fs"])
shot("CamPop", B[5]["fs"], (EYES + THROAT) / 2, (0.25, -0.85, 0.02), lens=85, push=0.10, end=B[6]["fs"])
shot("CamXrayTear", B[6]["fs"], XT + Vector((0, 0.03, -0.05)), (0.95, -0.15, 0.03), lens=55, fstop=8, push=0.16, end=B[7]["fs"])
WE = ward.anchor("eyes", 1)
shot("CamWard", B[7]["fs"], WE + Vector((-0.12, 0.05, -0.03)), (-0.25, -0.95, 0.38), lens=50, fstop=3.5, push=0.10, end=B[8]["fs"])
shot("CamLetItOut", B[8]["fs"], EYES + Vector((0, 0, -0.12)), (0.65, -1.3, 0.04), lens=70, push=0.08, end=END)
# a little shake on the pop
cp = CAMS[5]
for f, dx in ((f_pop - 1, 0), (f_pop + 1, 0.012), (f_pop + 3, -0.009), (f_pop + 5, 0.005), (f_pop + 8, 0)):
    sc.frame_set(f)
    base = cp.matrix_world.to_translation()
    cp.location.x = base.x + dx
    cp.keyframe_insert("location", index=0, frame=f)

# ================================================================= QA (poses + scene) — fix every line before rendering
seg = lambda i: (B[i]["fs"], B[i + 1]["fs"] if i + 1 < len(B) else END)  # noqa: E731
QA = (guy.check(1, END, shots=[seg(i) for i in (0, 1, 4, 5, 8)]) +
      xr.check(1, END, shots=[seg(i) for i in (2, 3, 6)]) +
      ward.check(1, END, shots=[seg(7)]))

# ================================================================= output
if MODE == "preview":
    s3d.qa_gate(QA, abort=False)
    out = os.path.join(WORK, "preview")
    os.makedirs(out, exist_ok=True)
    frames = sorted(set(int(x) for x in os.environ.get("FRAMES", "").split(",") if x) or
                    [60, B[0]["fe"] - 4, W(1, "shut", 8), f_stuck + 4, f_spike + 14, W(4, "exactly") + 2, f_pop + 14,
                     f_leak + 40, W(7, "healed"), f_out, END - 4])
    for fr in frames:
        s3d.preview_still(os.path.join(out, f"f{fr:04d}.png"), frame=fr, scale=40)
    s3d.export_markers(os.path.join(WORK, "render.sfx.json"))
else:
    if MODE == "half":
        sc.eevee.taa_render_samples = 16
    s3d.render_mp4(os.path.join(WORK, "render.mp4"), scale=50 if MODE == "half" else 100, qa=QA)
