"""human — rigged little people for s3d shorts (no downloads, no add-ons).

    import human
    bob = human.Human("Bob", loc=(-5, 1.2, s3d.TOP), outfit=human.WORKER, face=0)
    bob.walk(1, 40, to=(-1.5, 1.2))                # walks there, turns to face the camera at the end
    bob.dig(40, 120, sink_to=-3.2)                  # shovel loop, sinks with the hole floor
    bob.pose_at(130, "cheer"); bob.hold(130, 160)  # any pose from POSES, held
    bob.climb(200, 260, z_from=s3d.TOP, z_to=-3.1) # ladder, back to camera
    bob.act(300, "cough", cycles=3)                # cough / wave / scared / think / relieved
    bob.lie(400, loc=(-1, 1.6, -2.6))               # lie down (bed)

Design: smooth lofted body parts (skin, shirt, trousers, boots, hair, face) parented to an armature —
rigid parts can't tear or candy-wrap, so every pose is clean. Angles in POSES are degrees:
(forward, outward, twist) per bone — forward = toward where the person faces, outward = away from the body
centre (for spine/neck/head: toward the person's right). Each move also drops an SFX cue for assemble.py.
"""
from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Euler, Vector

import s3d

SKIN = [(0.82, 0.58, 0.45), (0.62, 0.42, 0.30), (0.93, 0.72, 0.60), (0.42, 0.27, 0.18)]
HAIR = [(0.08, 0.05, 0.03), (0.30, 0.18, 0.08), (0.55, 0.40, 0.20), (0.04, 0.04, 0.04)]

WORKER = dict(shirt=(0.10, 0.28, 0.55), pants=(0.22, 0.20, 0.17), shoes=(0.12, 0.08, 0.05), hat="hardhat", hat_color=(0.95, 0.65, 0.05), vest=(0.95, 0.85, 0.1))
CASUAL = dict(shirt=(0.75, 0.15, 0.12), pants=(0.12, 0.18, 0.32), shoes=(0.85, 0.85, 0.85), hat=None)
FARMER = dict(shirt=(0.35, 0.45, 0.25), pants=(0.25, 0.32, 0.50), shoes=(0.20, 0.13, 0.07), hat="cap", hat_color=(0.7, 0.12, 0.1))
SCIENTIST = dict(shirt=(0.92, 0.92, 0.94), pants=(0.15, 0.15, 0.18), shoes=(0.05, 0.05, 0.05), hat=None)

# rest skeleton (character faces -Y, i.e. toward the s3d camera; +X is the person's LEFT)
BONES = {
    #  name          head                 tail                 parent
    "hips":      ((0, 0, 0.94), (0, 0, 1.02), None),
    "spine":     ((0, 0, 1.00), (0, 0, 1.46), "hips"),
    "neck":      ((0, 0, 1.46), (0, 0, 1.56), "spine"),
    "head":      ((0, 0, 1.56), (0, 0, 1.80), "neck"),
    "upper_arm.L": ((0.20, 0, 1.43), (0.225, 0.01, 1.16), "spine"),
    "forearm.L": ((0.225, 0.01, 1.16), (0.24, -0.01, 0.92), "upper_arm.L"),
    "hand.L":    ((0.24, -0.01, 0.92), (0.245, -0.015, 0.80), "forearm.L"),
    "thigh.L":   ((0.095, 0, 0.93), (0.10, 0, 0.51), "hips"),
    "shin.L":    ((0.10, 0, 0.51), (0.10, 0.01, 0.10), "thigh.L"),
    "foot.L":    ((0.10, 0.01, 0.10), (0.10, -0.13, 0.03), "shin.L"),
}
for _k in list(BONES):
    if _k.endswith(".L"):
        h, t, p = BONES[_k]
        BONES[_k[:-2] + ".R"] = ((-h[0], h[1], h[2]), (-t[0], t[1], t[2]), p.replace(".L", ".R") if p and p.endswith(".L") else p)

# ---------------------------------------------------------------- pose library (degrees: forward, outward, twist)
POSES = {
    "stand": {"upper_arm": (0, 4, 0), "forearm": (8, 0, 0), "thigh": (0, 1, 0), "shin": (0, 0, 0)},
    "walk_a": {"thigh.L": (28, 1, 0), "shin.L": (-8, 0, 0), "foot.L": (-10, 0, 0), "thigh.R": (-20, 1, 0), "shin.R": (-30, 0, 0), "foot.R": (15, 0, 0),
               "upper_arm.L": (-22, 6, 0), "upper_arm.R": (24, 6, 0), "forearm": (22, 0, 0), "spine": (4, 0, 4)},
    "walk_pass_a": {"thigh.L": (0, 1, 0), "shin.L": (-5, 0, 0), "thigh.R": (22, 1, 0), "shin.R": (-55, 0, 0), "foot.R": (10, 0, 0),
                    "upper_arm": (0, 6, 0), "forearm": (18, 0, 0), "spine": (4, 0, 0)},
    "walk_b": {"thigh.R": (28, 1, 0), "shin.R": (-8, 0, 0), "foot.R": (-10, 0, 0), "thigh.L": (-20, 1, 0), "shin.L": (-30, 0, 0), "foot.L": (15, 0, 0),
               "upper_arm.R": (-22, 6, 0), "upper_arm.L": (24, 6, 0), "forearm": (22, 0, 0), "spine": (4, 0, -4)},
    "walk_pass_b": {"thigh.R": (0, 1, 0), "shin.R": (-5, 0, 0), "thigh.L": (22, 1, 0), "shin.L": (-55, 0, 0), "foot.L": (10, 0, 0),
                    "upper_arm": (0, 6, 0), "forearm": (18, 0, 0), "spine": (4, 0, 0)},
    # digging (shovel in the right hand): raise -> stab -> lever -> toss
    "dig_raise": {"spine": (10, 0, -15), "upper_arm.R": (55, 12, 0), "forearm.R": (45, 0, 0), "hand.R": (-80, 0, 0), "upper_arm.L": (40, -18, 0), "forearm.L": (60, 0, 0),
                  "thigh": (12, 2, 0), "shin": (-20, 0, 0), "foot": (8, 0, 0), "head": (-10, 0, 0)},
    "dig_stab": {"spine": (32, 0, -5), "upper_arm.R": (40, 8, 0), "forearm.R": (15, 0, 0), "hand.R": (-67, 0, 0), "upper_arm.L": (55, -15, 0), "forearm.L": (30, 0, 0),
                 "thigh.L": (25, 2, 0), "shin.L": (-35, 0, 0), "thigh.R": (-5, 2, 0), "shin.R": (-10, 0, 0), "head": (-18, 0, 0)},
    "dig_lever": {"spine": (24, 0, -10), "upper_arm.R": (25, 10, 0), "forearm.R": (35, 0, 0), "hand.R": (-100, 0, 0), "upper_arm.L": (70, -10, 0), "forearm.L": (40, 0, 0),
                  "thigh": (18, 2, 0), "shin": (-30, 0, 0), "head": (-12, 0, 0)},
    "dig_toss": {"spine": (14, 0, 35), "upper_arm.R": (75, -5, 0), "forearm.R": (25, 0, 0), "hand.R": (-45, 0, 0), "upper_arm.L": (85, 5, 0), "forearm.L": (20, 0, 0),
                 "thigh": (6, 2, 0), "shin": (-10, 0, 0), "head": (-5, 0, 20)},
    "cheer": {"upper_arm": (20, 155, 0), "forearm": (15, 0, 0), "head": (-15, 0, 0), "spine": (-6, 0, 0)},
    "cheer_b": {"upper_arm": (25, 140, 0), "forearm": (40, 0, 0), "head": (-10, 0, 0), "spine": (-4, 0, 0)},
    "wave_a": {"upper_arm.R": (10, 115, 0), "forearm.R": (5, -40, 0), "upper_arm.L": (0, 4, 0), "head": (0, 0, 0)},
    "wave_b": {"upper_arm.R": (10, 115, 0), "forearm.R": (5, 10, 0), "upper_arm.L": (0, 4, 0)},
    "point": {"upper_arm.R": (80, 25, 0), "forearm.R": (5, 0, 0), "head": (0, 0, -15)},
    "point_left": {"upper_arm.L": (80, 25, 0), "forearm.L": (5, 0, 0), "head": (0, 0, 15)},
    "scared": {"spine": (25, 0, 0), "upper_arm": (60, 40, 0), "forearm": (125, 0, 0), "head": (25, 0, 0), "thigh": (35, 6, 0), "shin": (-60, 0, 0), "foot": (20, 0, 0)},
    "think": {"upper_arm.R": (40, -10, 0), "forearm.R": (130, 0, 0), "upper_arm.L": (30, -25, 0), "forearm.L": (95, 0, 0), "head": (-8, 0, 12)},
    "cough_a": {"spine": (40, 0, 0), "upper_arm.R": (55, -15, 0), "forearm.R": (125, 0, 0), "upper_arm.L": (10, 8, 0), "forearm.L": (40, 0, 0), "head": (20, 0, 0), "thigh": (8, 2, 0), "shin": (-12, 0, 0)},
    "cough_b": {"spine": (12, 0, 0), "upper_arm.R": (55, -15, 0), "forearm.R": (125, 0, 0), "upper_arm.L": (10, 8, 0), "forearm.L": (40, 0, 0), "head": (5, 0, 0)},
    "relieved": {"spine": (-10, 0, 0), "upper_arm": (0, 55, 0), "forearm": (20, 0, 0), "head": (-20, 0, 0)},
    "wipe_brow": {"upper_arm.R": (85, -20, 0), "forearm.R": (120, -20, 0), "head": (5, 0, 0), "upper_arm.L": (0, 6, 0)},
    "thumbs_up": {"upper_arm.R": (60, 15, 0), "forearm.R": (80, 0, 0), "hand.R": (0, 0, 90), "head": (-5, 0, -8)},
    "climb_a": {"upper_arm.L": (150, 10, 0), "forearm.L": (30, 0, 0), "upper_arm.R": (115, 10, 0), "forearm.R": (60, 0, 0),
                "thigh.L": (55, 4, 0), "shin.L": (-80, 0, 0), "thigh.R": (20, 4, 0), "shin.R": (-35, 0, 0), "head": (-12, 0, 0)},
    "climb_b": {"upper_arm.R": (150, 10, 0), "forearm.R": (30, 0, 0), "upper_arm.L": (115, 10, 0), "forearm.L": (60, 0, 0),
                "thigh.R": (55, 4, 0), "shin.R": (-80, 0, 0), "thigh.L": (20, 4, 0), "shin.L": (-35, 0, 0), "head": (-12, 0, 0)},
    "jump": {"upper_arm": (-30, 30, 0), "forearm": (30, 0, 0), "thigh": (40, 4, 0), "shin": (-70, 0, 0), "foot": (25, 0, 0), "spine": (10, 0, 0)},
    "crouch": {"spine": (30, 0, 0), "thigh": (75, 8, 0), "shin": (-110, 0, 0), "foot": (35, 0, 0), "upper_arm": (35, 10, 0), "forearm": (40, 0, 0)},
    "sit": {"thigh": (88, 6, 0), "shin": (-88, 0, 0), "upper_arm": (10, 6, 0), "forearm": (50, 0, 0), "spine": (-4, 0, 0)},
    "lie": {"upper_arm.R": (0, 4, 0), "upper_arm.L": (170, 30, 0), "forearm.L": (40, 0, 0), "thigh": (0, 2, 0), "shin": (-6, 0, 0), "head": (-10, 0, -20)},
    "carry": {"upper_arm": (55, -8, 0), "forearm": (40, 0, 0), "spine": (-6, 0, 0)},
    "shrug": {"upper_arm": (10, 25, 0), "forearm": (80, 0, 20), "head": (0, 12, 0)},
}


class Human:
    def __init__(self, name="Bob", loc=(0, 0, s3d.TOP), facing=0.0, outfit=None, skin=None, hair=None, seed=0, scale=1.0, shovel=False):
        self.name = name
        self.rng = random.Random(seed)
        o = dict(CASUAL if outfit is None else outfit)
        self.skin = skin or SKIN[seed % len(SKIN)]
        self.hair = hair or HAIR[seed % len(HAIR)]
        self.arm = self._armature()
        self.arm.scale = (scale,) * 3
        self.parts = []
        self._hs = None
        self._build(o)
        self.shovel = self._shovel() if shovel else None   # built in rest space, before moving the rig
        self.arm.location = loc
        self.arm.rotation_euler = (0, 0, math.radians(facing))
        self.held = {}
        s3d._key(self.arm, 1, loc=True, rot=True)
        self.pose_at(1, "stand")
        self._blinks()

    # ------------------------------------------------------------ build
    def _armature(self):
        ad = bpy.data.armatures.new(self.name + "_rig")
        ob = bpy.data.objects.new(self.name, ad)
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        for n, (h, t, p) in BONES.items():
            b = ad.edit_bones.new(n)
            b.head, b.tail = h, t
            b.roll = 0
        for n, (h, t, p) in BONES.items():
            if p:
                ad.edit_bones[n].parent = ad.edit_bones[p]
                ad.edit_bones[n].use_connect = False
        bpy.ops.object.mode_set(mode="OBJECT")
        ob.show_in_front = True
        # per-bone sign so POSES mean the same thing on every bone ('forward' = toward -Y at rest)
        self.sign = {}
        for b in ad.bones:
            m = b.matrix_local.to_3x3()
            xl, yl, zl = m.col[0], m.col[1], m.col[2]
            fwd = Vector((0, -1, 0))
            side = Vector((1 if b.head_local.x > 0.01 else -1 if b.head_local.x < -0.01 else -1, 0, 0))  # outward; centre bones: person's right (-X)
            fs = 1 if xl.cross(yl).dot(fwd) > 0 else -1
            os_ = 1 if zl.cross(yl).dot(side) > 0 else -1
            self.sign[b.name] = (fs, os_)
            ob.pose.bones[b.name].rotation_mode = "XYZ"
        return ob

    def _mat(self, key, color, rough=0.75, sss=0.0, sheen=0.0):
        n = f"{self.name}_{key}"
        m = bpy.data.materials.get(n)
        if m:
            return m
        m = s3d.mat(n, color, rough=rough, noise=0.12, noise_scale=30)
        b = next(x for x in m.node_tree.nodes if x.type == "BSDF_PRINCIPLED")
        if sss and "Subsurface Weight" in b.inputs:
            b.inputs["Subsurface Weight"].default_value = sss
            b.inputs["Subsurface Radius"].default_value = (0.4, 0.15, 0.08)
        if sheen and "Sheen Weight" in b.inputs:
            b.inputs["Sheen Weight"].default_value = sheen
        return m

    def _part(self, name, bone, me_obj, mat):
        if self._hs and bone == "head":              # bigger, friendlier head (scaled about its centre)
            c, k = self._hs
            me_obj.location = c + (me_obj.location - c) * k
            me_obj.scale = me_obj.scale * k
            if me_obj.type == "MESH" and me_obj.location.length < 1e-6:
                pass
        me_obj.name = f"{self.name}_{name}"
        me_obj.data.materials.clear()
        me_obj.data.materials.append(mat)
        mw = me_obj.matrix_world.copy()
        me_obj.parent = self.arm
        me_obj.parent_type = "BONE"
        me_obj.parent_bone = bone
        bpy.context.view_layer.update()
        me_obj.matrix_world = mw
        self.parts.append(me_obj)
        return me_obj

    def _loft(self, name, a, b, prof, ring=14, sub=2, flat_x=1.0):
        """Smooth tube from a to b; prof = [(t, rx, ry), ...] radii along it; rounded caps."""
        a, b = Vector(a), Vector(b)
        d = (b - a).normalized()
        ref = Vector((1, 0, 0)) if abs(d.x) < 0.9 else Vector((0, 1, 0))
        u = (ref - d * ref.dot(d)).normalized()
        v = d.cross(u)
        bm = bmesh.new()
        rings = []
        for t, rx, ry in prof:
            c = a.lerp(b, t)
            rings.append([bm.verts.new(c + u * (rx * flat_x) * math.cos(k / ring * math.tau) + v * ry * math.sin(k / ring * math.tau)) for k in range(ring)])
        for r0, r1 in zip(rings, rings[1:]):
            for k in range(ring):
                bm.faces.new((r0[k], r0[(k + 1) % ring], r1[(k + 1) % ring], r1[k]))
        for rr, end, sgn in ((rings[0], a, -1), (rings[-1], b, 1)):
            rad = (prof[0][1] if sgn < 0 else prof[-1][1])
            c = bm.verts.new(end + d * sgn * rad * 0.55)
            for k in range(ring):
                f = (rr[k], rr[(k + 1) % ring], c) if sgn > 0 else (rr[(k + 1) % ring], rr[k], c)
                bm.faces.new(f)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        for p in me.polygons:
            p.use_smooth = True
        sm = ob.modifiers.new("Smooth", "SUBSURF")
        sm.levels = 1
        sm.render_levels = sub
        return ob

    def _ellipsoid(self, name, c, r, sub=3):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=14, radius=1, location=c)
        ob = bpy.context.active_object
        ob.name = name
        ob.scale = r
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bpy.ops.object.shade_smooth()
        return ob

    def _build(self, o):
        sk = self._mat("skin", self.skin, rough=0.55, sss=0.12)
        sh = self._mat("shirt", o["shirt"], rough=0.85, sheen=0.3)
        pa = self._mat("pants", o["pants"], rough=0.9, sheen=0.3)
        bo = self._mat("shoes", o["shoes"], rough=0.6)
        ha = self._mat("hair", self.hair, rough=0.7)
        white = self._mat("eyewhite", (0.95, 0.95, 0.93), rough=0.3)
        dark = self._mat("pupil", (0.03, 0.02, 0.02), rough=0.2)
        L = self._loft
        # torso + pelvis
        self._part("torso", "spine", L("t", (0, 0, 0.95), (0, 0, 1.52), [(0, .150, .100), (.2, .148, .098), (.5, .165, .108), (.78, .192, .112), (.92, .175, .100), (1, .07, .05)]), sh)
        self._part("pelvis", "hips", L("p", (0, 0, 0.84), (0, 0, 1.02), [(0, .12, .09), (.35, .158, .102), (1, .152, .100)]), pa)
        self._part("belt", "hips", L("bl", (0, 0, 0.99), (0, 0, 1.025), [(0, .154, .104), (1, .154, .104)], sub=1), self._mat("belt", (0.08, 0.05, 0.03), 0.4))
        if o.get("vest"):
            self._part("vest", "spine", L("v", (0, 0, 1.0), (0, 0, 1.47), [(0, .158, .108), (.5, .172, .116), (.8, .198, .12), (1, .16, .095)], sub=1),
                       self._mat("vest", o["vest"], 0.6))
        self._part("neck", "neck", L("n", (0, 0, 1.47), (0, 0, 1.6), [(0, .048, .048), (1, .044, .044)]), sk)
        # head
        hc = Vector((0, 0.005, 1.675))
        self._hs = (hc, 1.13)
        self._part("head", "head", self._ellipsoid("h", hc, (0.098, 0.108, 0.122)), sk)
        self._part("nose", "head", self._ellipsoid("no", hc + Vector((0, -0.103, -0.012)), (0.016, 0.022, 0.026)), sk)
        for sx in (1, -1):
            self._part("ear", "head", self._ellipsoid("e", hc + Vector((sx * 0.097, 0.01, 0)), (0.012, 0.022, 0.03)), sk)
            ew = self._part("eye", "head", self._ellipsoid("ew", hc + Vector((sx * 0.037, -0.088, 0.018)), (0.019, 0.013, 0.019)), white)
            pu = self._part("pupil", "head", self._ellipsoid("pu", hc + Vector((sx * 0.037, -0.1, 0.018)), (0.0105, 0.006, 0.0115)), dark)
            ew["blink"] = pu["blink"] = 1
            self._part("brow", "head", self._ellipsoid("br", hc + Vector((sx * 0.039, -0.096, 0.05)), (0.022, 0.008, 0.0055)), ha)
        self._part("mouth", "head", self._ellipsoid("m", hc + Vector((0, -0.097, -0.052)), (0.022, 0.006, 0.005)), self._mat("mouth", (0.35, 0.10, 0.08), 0.5))
        hair = self._ellipsoid("hr", hc + Vector((0, 0.012, 0.012)), (0.106, 0.116, 0.128))
        me = hair.data
        bm = bmesh.new()
        bm.from_mesh(me)
        o_ = hair.location  # mesh coords are local to the ellipsoid centre
        kill = [v for v in bm.verts if (v.co.z + o_.z - (hc.z - 0.005)) + 0.75 * (v.co.y + o_.y - hc.y) < 0
                or (v.co.z + o_.z < hc.z + 0.06 and v.co.y + o_.y < hc.y - 0.06)]
        bmesh.ops.delete(bm, geom=kill, context="VERTS")
        bm.to_mesh(me)
        bm.free()
        sol = hair.modifiers.new("Thick", "SOLIDIFY")
        sol.thickness = 0.012
        self._part("hair", "head", hair, ha)
        hat = o.get("hat")
        if hat == "hardhat":
            hm = self._mat("hat", o.get("hat_color", (0.95, 0.65, 0.05)), rough=0.35)
            dome = self._ellipsoid("hat", hc + Vector((0, 0.008, 0.03)), (0.118, 0.13, 0.13))
            bm = bmesh.new()
            bm.from_mesh(dome.data)
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z + dome.location.z < hc.z + 0.035], context="VERTS")
            bm.to_mesh(dome.data)
            bm.free()
            dome.modifiers.new("Thick", "SOLIDIFY").thickness = 0.01
            self._part("hat", "head", dome, hm)
            self._part("brim", "head", L("brim", hc + Vector((0, 0.0, 0.03)), hc + Vector((0, 0.0, 0.045)), [(0, .128, .142), (1, .128, .142)], ring=24, sub=1), hm)
        elif hat == "cap":
            hm = self._mat("hat", o.get("hat_color", (0.7, 0.1, 0.1)), rough=0.8)
            dome = self._ellipsoid("cap", hc + Vector((0, 0.01, 0.035)), (0.11, 0.12, 0.11))
            bm = bmesh.new()
            bm.from_mesh(dome.data)
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z + dome.location.z < hc.z + 0.04], context="VERTS")
            bm.to_mesh(dome.data)
            bm.free()
            self._part("cap", "head", dome, hm)
            self._part("visor", "head", self._ellipsoid("vi", hc + Vector((0, -0.12, 0.045)), (0.075, 0.06, 0.008)), hm)
        self._hs = None
        # arms / legs (both sides)
        for s in ("L", "R"):
            sx = 1 if s == "L" else -1
            ua, fa, hd = BONES[f"upper_arm.{s}"], BONES[f"forearm.{s}"], BONES[f"hand.{s}"]
            self._part("upperarm", f"upper_arm.{s}", L("ua", ua[0], ua[1], [(0, .052, .052), (1, .040, .040)]), sk)
            sleeve_end = Vector(ua[0]).lerp(Vector(ua[1]), 0.55)
            self._part("sleeve", f"upper_arm.{s}", L("sl", Vector(ua[0]) + Vector((0, 0, 0.01)), sleeve_end, [(0, .062, .062), (1, .052, .052)]), sh)
            self._part("forearm", f"forearm.{s}", L("fa", fa[0], fa[1], [(0, .040, .040), (1, .031, .030)]), sk)
            hcn = Vector(hd[0]).lerp(Vector(hd[1]), 0.55)
            self._part("hand", f"hand.{s}", self._ellipsoid("hd", hcn, (0.022, 0.042, 0.062)), sk)
            self._part("thumb", f"hand.{s}", self._ellipsoid("th", hcn + Vector((-sx * 0.004, -0.04, 0.02)), (0.014, 0.014, 0.03)), sk)
            th, shn, ft = BONES[f"thigh.{s}"], BONES[f"shin.{s}"], BONES[f"foot.{s}"]
            self._part("thigh", f"thigh.{s}", L("th", th[0], th[1], [(0, .078, .082), (.5, .07, .072), (1, .056, .058)]), pa)
            self._part("shin", f"shin.{s}", L("sh", shn[0], shn[1], [(0, .056, .058), (.35, .052, .055), (1, .044, .046)]), pa)
            self._part("shoe", f"foot.{s}", self._ellipsoid("ft", (sx * 0.10, -0.045, 0.045), (0.05, 0.13, 0.048)), bo)
            self._part("sole", f"foot.{s}", L("so", (sx * 0.10, 0.07, 0.012), (sx * 0.10, -0.165, 0.012), [(0, .045, .01), (.5, .05, .01), (1, .04, .01)], sub=1), self._mat("sole", (0.05, 0.05, 0.05), 0.8))

    def _shovel(self):
        st = s3d.mat("Steel", (0.5, 0.52, 0.55), rough=0.35, metal=1.0, noise=0.2)
        wd = s3d.mat("ShovelWood", (0.55, 0.36, 0.18), rough=0.6, noise=0.3)
        hb = BONES["hand.R"]
        hc = Vector(hb[0]).lerp(Vector(hb[1]), 0.55)
        handle = s3d.cylinder("shovel_handle", 0.017, 1.15, (hc.x, hc.y - 0.01, hc.z - 0.15), mat=wd, verts=12)
        grip = s3d.cylinder("shovel_grip", 0.016, 0.12, (hc.x, hc.y - 0.01, hc.z + 0.43), rot=(0, math.radians(90), 0), mat=wd, verts=10)
        blade = s3d.box("shovel_blade", (0.22, 0.03, 0.28), (hc.x, hc.y - 0.01, hc.z - 0.84), st, bevel=0.01)
        sb = blade.modifiers.new("Bend", "SIMPLE_DEFORM")
        sb.deform_method = "BEND"
        sb.angle = math.radians(25)
        sb.deform_axis = "Z"
        g = s3d.group(self.name + "_shovel", [handle, grip, blade])
        mw = g.matrix_world.copy()
        g.parent = self.arm
        g.parent_type = "BONE"
        g.parent_bone = "hand.R"
        bpy.context.view_layer.update()
        g.matrix_world = mw
        return g

    def _blinks(self):
        sc = bpy.context.scene
        eyes = [p for p in self.parts if p.get("blink")]
        f = 20 + self.rng.randint(0, 40)
        while f < sc.frame_end:
            for e in eyes:
                e.scale = (1, 1, 1)
                e.keyframe_insert("scale", frame=f)
                e.scale = (1, 1, 0.08)
                e.keyframe_insert("scale", frame=f + 2)
                e.scale = (1, 1, 1)
                e.keyframe_insert("scale", frame=f + 4)
            f += 75 + self.rng.randint(0, 80)

    # ------------------------------------------------------------ posing
    def _apply(self, spec):
        pb = self.arm.pose.bones
        for b in pb:
            b.rotation_euler = (0, 0, 0)
        for key, ang in spec.items():
            names = [key] if key in pb else [f"{key}.L", f"{key}.R"]
            for n in names:
                if n not in pb:
                    continue
                fs, os_ = self.sign[n]
                f_, o_, t_ = ang
                pb[n].rotation_euler = Euler((math.radians(f_) * fs, math.radians(t_), math.radians(o_) * os_), "XYZ")

    def pose_at(self, frame, pose, blend=None):
        """Key a pose (name from POSES or a dict). blend=(other_pose, 0..1) mixes two poses."""
        spec = dict(POSES[pose]) if isinstance(pose, str) else dict(pose)
        if blend:
            other = POSES[blend[0]] if isinstance(blend[0], str) else blend[0]
            k = blend[1]
            keys = set(spec) | set(other)
            spec = {n: tuple(a * (1 - k) + b * k for a, b in zip(spec.get(n, (0, 0, 0)), other.get(n, (0, 0, 0)))) for n in keys}
        base = dict(POSES["stand"])
        base.update(spec) if pose != "stand" else None
        self._apply(base)
        for b in self.arm.pose.bones:
            b.keyframe_insert("rotation_euler", frame=frame)
        self._last = (frame, base)

    def hold(self, f0, f1, breathe=True):
        """Keep the current pose from f0 to f1 with a little breathing so nobody freezes."""
        if not hasattr(self, "_last"):
            return
        spec = self._last[1]
        f = f0
        k = 0
        while f < f1:
            s = dict(spec)
            sp = s.get("spine", (0, 0, 0))
            hd = s.get("head", (0, 0, 0))
            amp = 1.6 if breathe else 0
            s["spine"] = (sp[0] + (amp if k % 2 else -amp) * 0.6, sp[1], sp[2])
            s["head"] = (hd[0] + (amp if k % 2 else 0), hd[1], hd[2] + (2 if k % 4 == 1 else -2 if k % 4 == 3 else 0))
            self._apply(s)
            for b in self.arm.pose.bones:
                b.keyframe_insert("rotation_euler", frame=f)
            f += 22
            k += 1
        self._apply(spec)
        for b in self.arm.pose.bones:
            b.keyframe_insert("rotation_euler", frame=f1)

    def place(self, frame, loc=None, facing=None):
        """Key root position / facing (degrees: 0 = camera, 90 = walking toward +X, 180 = back to camera)."""
        if loc is not None:
            self.arm.location = loc
        if facing is not None:
            self.arm.rotation_euler = (0, 0, math.radians(facing))
        s3d._key(self.arm, frame, loc=True, rot=True)

    def turn(self, frame, facing, dur=8):
        s3d._key(self.arm, frame, rot=True)
        self.arm.rotation_euler = (0, 0, math.radians(facing))
        s3d._key(self.arm, frame + dur, rot=True)

    # ------------------------------------------------------------ actions
    def walk(self, f0, f1, to, face_end=0.0, step=15, sfx=True):
        """Walk from the current spot to `to` (x, y[, z]) between f0 and f1; legs cycle every `step` frames."""
        start = self.arm.location.copy()
        end = Vector((to[0], to[1], to[2] if len(to) > 2 else start.z))
        d = end - start
        heading = math.degrees(math.atan2(d.x, -d.y)) if d.length > 0.01 else face_end
        self.place(f0, start, None)
        self.turn(f0, heading, dur=5)
        seq = ["walk_a", "walk_pass_a", "walk_b", "walk_pass_b"]
        f, i = f0, 0
        while f < f1:
            self.pose_at(f, seq[i % 4])
            if sfx and i % 2 == 0 and i % 4 == 0:
                s3d.marker("step", f, gain=-6)
            f += step // 2
            i += 1
        # bob + travel
        n = max(1, (f1 - f0) // (step // 2))
        for k in range(n + 1):
            fr = f0 + k * (f1 - f0) / n
            p = start.lerp(end, k / n)
            p.z += 0.025 if k % 2 else 0.0
            self.arm.location = p
            self.arm.keyframe_insert("location", frame=int(round(fr)))
        self.pose_at(f1, "stand")
        self.turn(f1, face_end, dur=8)

    def dig(self, f0, f1, sink_to=None, cycle=24):
        """Shovel loop (raise, stab, lever, toss). sink_to = z of the hole floor reached at f1."""
        f = f0
        while f + cycle <= f1:
            self.pose_at(f, "dig_raise")
            self.pose_at(f + int(cycle * 0.3), "dig_stab")
            self.pose_at(f + int(cycle * 0.55), "dig_lever")
            self.pose_at(f + int(cycle * 0.8), "dig_toss")
            s3d.marker("dig", f + int(cycle * 0.3), gain=-4)
            f += cycle
        self.pose_at(f1, "stand")
        if sink_to is not None:
            self.place(f0)
            p = self.arm.location.copy()
            p.z = sink_to
            self.place(f1, p)

    def act(self, f0, kind, cycles=2, period=16):
        """Repeated gesture: cough, wave, cheer, scared (shaking), think."""
        pairs = {"cough": ("cough_a", "cough_b"), "wave": ("wave_a", "wave_b"), "cheer": ("cheer", "cheer_b"),
                 "scared": ("scared", "scared"), "climb": ("climb_a", "climb_b")}
        a, b = pairs.get(kind, (kind, kind))
        f = f0
        for c in range(cycles):
            self.pose_at(f, a)
            self.pose_at(f + period // 2, b)
            if kind == "cough":
                s3d.marker("cough", f, gain=-2)
            f += period
        if kind == "scared":
            for k in range(cycles * period // 3):
                self.arm.location.x += 0.012 * (1 if k % 2 else -1)
                self.arm.keyframe_insert("location", frame=f0 + k * 3)
        return f

    def jump(self, f0, f1, to, height=1.0):
        """Arc from here to `to` (x, y, z) — e.g. scrambling out of a hole."""
        a = self.arm.location.copy()
        b = Vector(to)
        mid = (a + b) / 2 + Vector((0, 0, height))
        self.place(f0, a)
        self.pose_at(f0, "crouch")
        self.pose_at(f0 + 3, "jump")
        self.arm.location = mid
        self.arm.keyframe_insert("location", frame=(f0 + f1) // 2)
        self.place(f1, b)
        self.pose_at(f1, "crouch")
        self.pose_at(f1 + 6, "stand")
        s3d.marker("step", f1, gain=-2)

    def climb(self, f0, f1, z_from, z_to, rung=0.3, facing=180):
        """Climb a ladder (back to the camera by default) from z_from to z_to."""
        p = self.arm.location.copy()
        p.z = z_from
        self.place(f0, p, facing)
        n = max(2, int(abs(z_to - z_from) / rung))
        for k in range(n + 1):
            fr = f0 + int((f1 - f0) * k / n)
            self.pose_at(fr, "climb_a" if k % 2 == 0 else "climb_b")
            p.z = z_from + (z_to - z_from) * k / n
            self.arm.location = p
            self.arm.keyframe_insert("location", frame=fr)
            if k % 2 == 0:
                s3d.marker("clank", fr, gain=-10)
        self.pose_at(f1 + 4, "stand")

    def lie(self, frame, hip, head_dir=-1, sit=10, dur=16):
        """Sit on the edge, then lie back (bed, bench). `hip` = (x, y, z) where the hips rest when lying
        (z = mattress top + 0.1). Walk him to (hip.x, hip.y - 0.75, floor) first. head_dir=-1 puts the head at -X.
        Rotation is slerped and the hips stay on the mattress, so he lies down instead of flipping."""
        hip = Vector(hip)
        H = Vector((0, 0, 0.94))                       # hips in rig space
        f1, f2 = frame - dur - sit, frame - dur
        stand_root = self.arm.location.copy()
        q0 = Euler((0, 0, 0)).to_quaternion()
        q1 = Euler((math.radians(-90), 0, math.radians(90 * -head_dir))).to_quaternion()
        sit_hip = Vector((hip.x, hip.y - 0.28, hip.z - 0.02))
        self.place(f1, stand_root, 0)
        self.pose_at(f1, "stand")
        self.place(f2, sit_hip - H, 0)
        self.pose_at(f2, "sit")
        n = 6
        for k in range(1, n + 1):
            t = k / n
            te = t * t * (3 - 2 * t)
            q = q0.slerp(q1, te)
            hp = sit_hip.lerp(hip, te)
            self.arm.rotation_euler = q.to_euler("XYZ", self.arm.rotation_euler)
            self.arm.location = hp - q @ H
            fr = f2 + int(round(dur * t))
            s3d._key(self.arm, fr, loc=True, rot=True)
            self.pose_at(fr, "sit", blend=("lie", te))
        s3d.marker("wood", f2, gain=-8)

    def hide_until(self, frame):
        s3d._hide_before(self.arm, frame)

    def hide_from(self, frame):
        s3d.hide_at(self.arm, frame)
