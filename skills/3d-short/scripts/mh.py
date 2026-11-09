"""mh — realistic people for shorts (MPFB = MakeHuman for Blender, CC0 assets).

Two halves:

1. make (a separate Blender run with the MPFB extension enabled) builds a character once and saves it:
       "$BLENDER" -b --python mh.py -- make guy.blend '{"name": "guy", "shirt": [0.85, 0.2, 0.12]}'
   Options (all optional): name, gender 0..1, age 0..1 (0.5 = 25 y), muscle, weight, height, skin,
   eyes, hair ("" = bald), eyebrows, clothes [list], shirt [r,g,b] (recolours the plain tee), phenotype {}.

2. Person (inside build.py, no MPFB needed) appends that .blend and animates it:
       p = mh.Person("guy.blend", loc=(0, 0, 0), facing=0)       # facing 0 = looks at -Y (towards the camera)
       p.pose(1, "idle"); p.pose(40, "pinch_nose"); p.face(40, "squeeze")
       p.pose(70, "grab_throat", hold=20); p.face(70, "shock")
   Every pose/face call keys the bones it touches at `frame` (eased, held from the previous key).
   Arm poses are solved here (two-bone IK + hand orientation), so hands land on the nose/throat/mouth
   of THIS body whatever its proportions.

Install once:  blender --online-mode --command extension install mpfb --enable
               + unzip makehuman_system_assets_cc0.zip (files.makehumancommunity.org, CC0) into
               ~/Library/Application Support/Blender/<ver>/extensions/.user/blender_org/mpfb/data
"""
from __future__ import annotations

import json
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

# ------------------------------------------------------------------ 1. make
DEFAULT = {
    "name": "guy",
    "gender": 1.0, "age": 0.55, "muscle": 0.6, "weight": 0.55, "height": 0.55,
    "skin": "young_caucasian_male/young_caucasian_male.mhmat",
    "eyes": "brown",
    "hair": "short02/short02.mhclo",
    "eyebrows": "eyebrow001/eyebrow001.mhclo",
    "eyelashes": "eyelashes01/eyelashes01.mhclo",
    "teeth": "teeth_base/teeth_base.mhclo",
    "clothes": ["male_casualsuit06/male_casualsuit06.mhclo", "shoes01/shoes01.mhclo"],
    "shirt": [0.78, 0.06, 0.03],
    "phenotype": {},
}


def _recolor_shirt(obj, color):
    """male_casualsuit06 = white tee (with a small logo) + jeans in one texture. Everything that is not
    denim blue becomes a plain tee of `color` (no logos on screen); the normal map keeps the folds."""
    for slot in obj.material_slots:
        m = slot.material
        if not m or not m.use_nodes:
            continue
        nt = m.node_tree
        img = next((n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image and "diffuse" in n.image.name.lower()), None)
        if img is None:
            continue
        links = [l for l in nt.links if l.from_node == img and l.from_socket.name == "Color"]
        hsv = nt.nodes.new("ShaderNodeSeparateColor")
        hsv.mode = "HSV"
        nt.links.new(img.outputs["Color"], hsv.inputs[0])
        def op(kind, a, b=None, v=None):
            n = nt.nodes.new("ShaderNodeMath")
            n.operation = kind
            for i, x in enumerate((a, b)):
                if x is None:
                    continue
                if isinstance(x, (int, float)):
                    n.inputs[i].default_value = x
                else:
                    nt.links.new(x, n.inputs[i])
            return n.outputs[0]
        jeans = op("MULTIPLY", op("MULTIPLY", op("GREATER_THAN", hsv.outputs[0], 0.48),
                                  op("LESS_THAN", hsv.outputs[0], 0.78)),
                   op("GREATER_THAN", hsv.outputs[1], 0.3))
        shade = op("ADD", 0.93, 0.0)
        tee = nt.nodes.new("ShaderNodeMix")
        tee.data_type = "RGBA"
        tee.blend_type = "MULTIPLY"
        tee.inputs["Factor"].default_value = 1.0
        tee.inputs["A"].default_value = (*color, 1)
        nt.links.new(shade, tee.inputs["B"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(jeans, mix.inputs["Factor"])
        nt.links.new(tee.outputs["Result"], mix.inputs["A"])
        nt.links.new(img.outputs["Color"], mix.inputs["B"])
        for l in links:
            nt.links.new(mix.outputs["Result"], l.to_socket)


def make(out_path, opts=None):
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService  # noqa: needs MPFB
    o = dict(DEFAULT)
    o.update(opts or {})
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    s = HumanService.get_default_deserialization_settings()
    info = HumanService._create_default_human_info_dict()
    info.update(rig="default", name=o["name"],
                eyes="high-poly/high-poly.mhclo",
                eyebrows=o["eyebrows"], eyelashes=o["eyelashes"], teeth=o["teeth"], tongue="",
                hair=o["hair"] or "", skin_mhmat=o["skin"], skin_material_type="ENHANCED_SSS",
                clothes=list(o["clothes"]))
    ph = info["phenotype"]
    for k in ("gender", "age", "muscle", "weight", "height"):
        ph[k] = o[k]
    ph.update(o.get("phenotype") or {})
    body = HumanService.deserialize_from_dict(info, s)
    rig = body.parent
    if o.get("shirt"):
        for c in rig.children:
            if "casualsuit06" in c.name:
                _recolor_shirt(c, o["shirt"])
    # one collection = one character, easy to append
    col = bpy.data.collections.new("MH_" + o["name"])
    bpy.context.scene.collection.children.link(col)
    for ob in [rig] + list(rig.children):
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        col.objects.link(ob)
    rig["mh_name"] = o["name"]
    try:                                   # self-contained: textures travel with the .blend
        bpy.ops.file.pack_all()
    except Exception as e:
        print("mh: pack_all failed, textures stay external:", e)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_path))
    print("mh: saved", out_path)


# ------------------------------------------------------------------ 2. Person
FPS = 30
_SIDE = {"L": 1.0, "R": -1.0}


def _ease_all(rig):
    ad = rig.animation_data
    if not ad or not ad.action:
        return
    try:
        curves = ad.action.fcurves
    except AttributeError:   # Blender 5 layered actions
        curves = [fc for layer in ad.action.layers for strip in layer.strips
                  for bag in strip.channelbags for fc in bag.fcurves]
    for fc in curves:
        for k in fc.keyframe_points:
            k.interpolation = "BEZIER"
            k.handle_left_type = k.handle_right_type = "AUTO_CLAMPED"


class Person:
    """A realistic rigged person appended from a .blend made by `make`."""

    def __init__(self, blend, loc=(0, 0, 0), facing=0.0, name=None):
        with bpy.data.libraries.load(os.path.abspath(blend), link=False) as (src, dst):
            dst.collections = [c for c in src.collections if c.startswith("MH_")][:1]
        col = dst.collections[0]
        if name:
            col.name = "MH_" + name
        bpy.context.scene.collection.children.link(col)
        self.col = col
        self.rig = next(o for o in col.objects if o.type == "ARMATURE")
        self.body = max((o for o in col.objects if o.type == "MESH" and ".body" in o.name), key=lambda o: len(o.data.vertices))
        self.parts = [o for o in col.objects if o.type == "MESH"]
        self.rig.location = loc
        self.rig.rotation_euler = (0, 0, math.radians(facing))
        self.pb = self.rig.pose.bones
        for p in self.pb:
            p.rotation_mode = "QUATERNION"
        self._touched: set[str] = set()
        bpy.context.view_layer.update()
        self._rest = {b.name: b.matrix_local.copy() for b in self.rig.data.bones}
        self._anchors()
        self._base = {p.name: Quaternion() for p in self.pb}
        self.relax()                      # arms down instead of the A-pose
        self._base = {p.name: p.rotation_quaternion.copy() for p in self.pb}

    # ---------- anchors (rest pose, rig space) on THIS body
    def _anchors(self):
        R = self._rest
        h = lambda n: R[n].to_translation()
        eye_l, eye_r = h("eye.L"), h("eye.R")
        mid = (eye_l + eye_r) / 2
        iod = (eye_l - eye_r).length                    # inter-ocular distance scales the face
        self.A = {
            "nose": mid + Vector((0, -0.75 * iod, -0.62 * iod)),
            "nose_tip": mid + Vector((0, -0.95 * iod, -0.65 * iod)),
            "mouth": h("oris01") + Vector((0, -0.01, 0.004)),
            "chin": h("special04") + Vector((0, -0.04, -0.03)),
            "throat": h("neck02") + Vector((0, -0.075, -0.01)),
            "ear.L": mid + Vector((1.25 * iod, 0.08, -0.02)),
            "ear.R": mid + Vector((-1.25 * iod, 0.08, -0.02)),
            "chest": h("spine01") + Vector((0, -0.13, 0)),
            "eyes": mid,
        }
        self.head_bone = "head"
        # refine nose / mouth / throat from the actual skin surface (rest pose, rig space)
        try:
            dg = bpy.context.evaluated_depsgraph_get()
            ev = self.body.evaluated_get(dg)
            me = ev.to_mesh()
            T = self.rig.matrix_world.inverted() @ self.body.matrix_world
            V = [T @ v.co for v in me.vertices]
            # head volume (skull + face) from the vertices the head/face bones move, for check()
            gi = {g.index for g in self.body.vertex_groups if g.name in self._HEAD_GROUPS(self.rig)}
            hv = [V[v.index] for v in me.vertices if any(g.group in gi and g.weight > 0.5 for g in v.groups)]
            if len(hv) > 50:
                lo = Vector((min(v.x for v in hv), min(v.y for v in hv), min(v.z for v in hv)))
                hi = Vector((max(v.x for v in hv), max(v.y for v in hv), max(v.z for v in hv)))
                self._head_ell = ((lo + hi) / 2, (hi - lo) / 2)
            ev.to_mesh_clear()
            def front(z0, z1, xw=0.008):
                s = [v for v in V if abs(v.x) < xw and z0 <= v.z <= z1]
                return min(s, key=lambda v: v.y) if s else None
            ez = mid.z
            n = front(ez - 0.075, ez - 0.01)
            if n is not None:
                self.A["nose_tip"] = n.copy()
                self.A["nose"] = n + Vector((0, 0.02, 0.012))
            mz = h("oris01").z
            m = front(mz - 0.02, mz + 0.008)
            if m is not None:
                self.A["mouth"] = m.copy()
            jaw_tail = self.rig.data.bones["jaw"].tail_local
            tz = jaw_tail.z - 0.045
            t = front(tz - 0.004, tz + 0.004, xw=0.012)
            if t is not None:
                self.A["throat"] = t.copy()
        except Exception as e:  # pragma: no cover
            print("mh: mesh anchors skipped:", e)

    @staticmethod
    def _HEAD_GROUPS(rig):
        """Head bone + every face bone (all descendants of 'head')."""
        hb = rig.data.bones.get("head")
        return {"head"} | ({b.name for b in hb.children_recursive} if hb else set())

    def anchor(self, name, frame=None):
        """World position of a body landmark (follows the head if the head moved)."""
        if frame is not None:
            bpy.context.scene.frame_set(frame)
        p = self.A[name]
        if name in ("throat", "chest"):
            return self.rig.matrix_world @ p
        hb = self.pb["head"]
        rest = self._rest["head"]
        return self.rig.matrix_world @ (hb.matrix @ rest.inverted() @ p)

    # ---------- low-level posing (rig space)
    def _upd(self):
        bpy.context.view_layer.update()

    def _set_world_rot(self, name, rot3):
        """Give bone `name` this rig-space orientation (3x3), keeping its head where it is."""
        p = self.pb[name]
        self._upd()
        M = rot3.to_quaternion().to_matrix().to_4x4()   # pure rotation: float error must not creep into bone scale
        p.scale = (1.0, 1.0, 1.0)
        M.translation = p.matrix.to_translation()
        p.matrix = M
        self._upd()
        self._touched.add(name)

    def _aim(self, name, target_dir, through=None):
        """Rotate bone so the vector head->`through` bone head (or its own Y) points along target_dir (rig space)."""
        p = self.pb[name]
        self._upd()
        cur = p.matrix.to_3x3()
        if through:
            v = self.pb[through].matrix.to_translation() - p.matrix.to_translation()
        else:
            v = cur.col[1]
        q = v.normalized().rotation_difference(Vector(target_dir).normalized())
        self._set_world_rot(name, q.to_matrix() @ cur)

    def _orient(self, name, y_dir, ref_local, ref_world):
        """Bone Y along y_dir and its local axis `ref_local` as close as possible to ref_world."""
        p = self.pb[name]
        self._upd()
        cur = p.matrix.to_3x3()
        q1 = cur.col[1].normalized().rotation_difference(Vector(y_dir).normalized())
        m1 = q1.to_matrix() @ cur
        y = m1.col[1].normalized()
        a = (m1 @ Vector(ref_local)).normalized()
        b = Vector(ref_world).normalized()
        a_p = (a - y * a.dot(y)).normalized()
        b_p = (b - y * b.dot(y)).normalized()
        if a_p.length > 1e-4 and b_p.length > 1e-4:
            ang = a_p.angle(b_p)
            if a_p.cross(b_p).dot(y) < 0:
                ang = -ang
            m1 = Quaternion(y, ang).to_matrix() @ m1
        self._set_world_rot(name, m1)

    def _reset(self, names):
        for n in names:
            self.pb[n].rotation_quaternion = self._base[n]
        self._upd()

    def arm(self, side, wrist, elbow_hint=(0, 0.3, -1), hand_dir=None, palm=None, elbow=None):
        """Two-bone IK: put the wrist of arm `side` ('L'/'R') at `wrist` (WORLD point).
        elbow_hint: rig-space direction the elbow should bulge towards. hand_dir/palm: rig-space hand direction
        and palm normal (optional)."""
        s = side
        sh, el, wr = f"upperarm01.{s}", f"lowerarm01.{s}", f"wrist.{s}"
        self._reset([sh, f"upperarm02.{s}", el, f"lowerarm02.{s}", wr])
        inv = self.rig.matrix_world.inverted()
        W = inv @ Vector(wrist)
        S = self.pb[sh].matrix.to_translation()
        E0 = self.pb[el].matrix.to_translation()
        W0 = self.pb[wr].matrix.to_translation()
        a, b = (E0 - S).length, (W0 - E0).length
        d = W - S
        L = min(d.length, (a + b) * 0.999)
        d = d.normalized()
        # elbow position: law of cosines, bend plane from the hint
        cos_a = (a * a + L * L - b * b) / (2 * a * L)
        sin_a = math.sqrt(max(0.0, 1 - cos_a * cos_a))
        hint = Vector(elbow_hint).normalized()
        perp = (hint - d * hint.dot(d))
        if perp.length < 1e-4:
            perp = Vector((0, 0, -1)) - d * d.z
        perp.normalize()
        E = S + d * (a * cos_a) + perp * (a * sin_a)
        Wt = S + d * L
        if elbow is not None:            # explicit elbow point (world): upper arm towards it, forearm towards the wrist
            E = S + (inv @ Vector(elbow) - S).normalized() * a
            Wt = E + (W - E).normalized() * b
        self._aim(sh, E - S, through=el)
        self._aim(el, Wt - E, through=wr)
        if hand_dir is not None:
            self._hand(s, hand_dir, palm)
            # a real forearm turns (pronation/supination), the wrist does not: move the twist into the forearm
            # bones, then re-aim the hand, so the skin never wrings like a candy wrapper
            t = self._wrist_twist(s)
            if abs(t) > math.radians(8):
                t = max(-math.radians(170), min(math.radians(170), t))
                for n, k in ((f"lowerarm01.{s}", 0.5), (f"lowerarm02.{s}", 0.5)):
                    p_ = self.pb[n]
                    p_.rotation_quaternion = p_.rotation_quaternion @ Quaternion((0, 1, 0), t * k)
                self._upd()
                self._hand(s, hand_dir, palm)
        for n in (sh, f"upperarm02.{s}", el, f"lowerarm02.{s}", wr):
            self._touched.add(n)

    def _hand(self, s, hand_dir, palm):
        wr = f"wrist.{s}"
        if palm is not None:
            # wrist.L/R: local X points out of the BACK of the hand (-X = palm), mirrored per side
            self._orient(wr, hand_dir, (1.0 if s == "L" else -1.0, 0, 0), palm)
        else:
            self._aim(wr, hand_dir)

    def _wrist_twist(self, s):
        """Twist (radians) of the wrist relative to the forearm around the forearm axis, vs. the rest pose."""
        self._upd()
        la, wr = f"lowerarm02.{s}", f"wrist.{s}"
        R = self._rest
        rest_rel = (R[la].to_3x3().inverted() @ R[wr].to_3x3())
        cur_rel = (self.pb[la].matrix.to_3x3().inverted() @ self.pb[wr].matrix.to_3x3())
        q = (cur_rel @ rest_rel.inverted()).to_quaternion()
        return 2 * math.atan2(q.y, q.w)

    def fingers(self, side, curl=0.0, thumb=0.0, spread=0.0, only=None):
        """Curl fingers (0 open .. 1 fist) around their local X; thumb curls separately; spread 0..1 fans them out."""
        fan = {2: -1.0, 3: -0.3, 4: 0.4, 5: 1.0}
        for f in (2, 3, 4, 5):
            if only and f not in only:
                continue
            for j in (1, 2, 3):
                n = f"finger{f}-{j}.{side}"
                q = Quaternion((1, 0, 0), math.radians(80 * curl * (0.8 if j == 1 else 1.0)))
                if j == 1 and spread:
                    q = Quaternion((0, 0, 1), math.radians(12 * spread * fan[f] * -_SIDE[side])) @ q
                self.pb[n].rotation_quaternion = q
                self._touched.add(n)
        # thumb: the base joint swings ACROSS the palm and flexes (0.7 = tucked under the index like in a real fist);
        # before 1.3 it swung outwards and stuck out under every fist
        t = thumb
        for j, q in ((1, Quaternion((0, 0, 1), math.radians(-_SIDE[side] * 57 * t)) @ Quaternion((1, 0, 0), math.radians(100 * t))),
                     (2, Quaternion((1, 0, 0), math.radians(36 * t))), (3, Quaternion((1, 0, 0), math.radians(43 * t)))):
            n = f"finger1-{j}.{side}"
            self.pb[n].rotation_quaternion = q
            self._touched.add(n)
        self._upd()

    def look(self, pitch=0.0, yaw=0.0, roll=0.0, spine=0.0, lean=0.0):
        """Head/neck/spine in degrees. pitch + = chin down (nod), yaw + = turn to his left, roll + = tilt to his left,
        spine + = bend forward at the chest, lean + = bend to his left."""
        q = lambda x, y, z: (Quaternion((1, 0, 0), math.radians(x)) @ Quaternion((0, 1, 0), math.radians(y))
                             @ Quaternion((0, 0, 1), math.radians(z)))
        for n, k in (("neck01", 0.25), ("neck02", 0.25), ("neck03", 0.2), ("head", 0.3)):
            self.pb[n].rotation_quaternion = q(pitch * k, yaw * k, -roll * k)
            self._touched.add(n)
        for n, k in (("spine03", 0.3), ("spine02", 0.35), ("spine01", 0.35)):
            self.pb[n].rotation_quaternion = q(spine * k, 0, -lean * k)
            self._touched.add(n)
        self._upd()

    # ---------- face (bones of the MakeHuman default rig)
    FACES = {
        # jaw (deg, + open), lids (-1 shut .. 0 normal .. 1 wide), brows (-1 frown .. 1 raised), lips (-1 pressed .. 1 open)
        "neutral": dict(jaw=0, lids=0, brows=0, lips=0),
        "squeeze": dict(jaw=0, lids=-0.85, brows=-0.8, lips=-1),
        "pre_sneeze": dict(jaw=9, lids=-0.55, brows=0.6, lips=0.4),
        "sneeze": dict(jaw=13, lids=-1, brows=-0.9, lips=0.6),
        "shock": dict(jaw=12, lids=1, brows=1, lips=0.6),
        "pain": dict(jaw=6, lids=-0.6, brows=-0.9, lips=0.3),
        "worried": dict(jaw=2, lids=0.3, brows=0.8, lips=0),
        "relief": dict(jaw=3, lids=-0.25, brows=0.3, lips=0.2),
        "puff": dict(jaw=0, lids=0.2, brows=0.5, lips=-1),
        "sleep": dict(jaw=1, lids=-1, brows=0, lips=0),
    }

    def _face_bones(self, jaw=0.0, lids=0.0, brows=0.0, lips=0.0):
        P = self.pb
        def setq(n, axis, deg):
            P[n].rotation_quaternion = Quaternion(axis, math.radians(deg))
            self._touched.add(n)
        setq("jaw", (1, 0, 0), jaw)
        up = -32 * -lids if lids < 0 else 22 * lids       # upper lid: - closes, + opens wide
        lo = 14 * -lids if lids < 0 else -6 * lids
        for s in "LR":
            setq(f"orbicularis03.{s}", (1, 0, 0), up)
            setq(f"orbicularis04.{s}", (1, 0, 0), lo)
            setq(f"oculi01.{s}", (0, 0, 1), 10 * brows * _SIDE[s])
            setq(f"oculi02.{s}", (0, 0, 1), 8 * brows * _SIDE[s])
        setq("oris01", (1, 0, 0), -6 * lips)
        setq("oris02", (1, 0, 0), 6 * lips)
        self._upd()

    def face(self, frame, expr="neutral", hold=0, dur=6, **over):
        self._begin(frame, dur)
        f = dict(self.FACES[expr])
        f.update(over)
        self._face_bones(**f)
        self.key(frame, hold)

    # ---------- named body poses
    def relax(self):
        for s in "LR":
            sx = _SIDE[s]
            S = self.rig.matrix_world @ self.pb[f"upperarm01.{s}"].matrix.to_translation()
            w = S + self.rig.matrix_world.to_3x3() @ Vector((0.07 * sx, -0.06, -0.55))
            self.arm(s, w, elbow_hint=(0.2 * sx, 0.6, 0), hand_dir=(0.05 * sx, -0.05, -1))
            self.fingers(s, curl=0.18, thumb=0.1)

    def _to_world_dir(self, v):
        return Vector(v)

    def pose(self, frame, name="idle", hold=0, side="R", dur=10, **kw):
        """Named poses, reached at `frame` after `dur` frames of easing. Call poses in time order.
        side picks the active hand for one-handed poses; pitch/yaw/roll/spine/lean set the head and chest."""
        self._begin(frame, dur)
        s = side
        o = "L" if s == "R" else "R"
        sx = _SIDE[s]
        M = self.rig.matrix_world.to_3x3()
        # head and chest first: the arm solver then aims at the nose/throat where they really are
        self.look(**{k: kw.get(k, 0) for k in ("pitch", "yaw", "roll", "spine", "lean")})
        cz = self.A["chest"].z
        if name in ("idle", "relax"):
            self.relax()
        elif name in ("pinch_nose", "near_nose", "cover_mouth", "grab_throat", "elbow_sneeze", "elbow_up"):
            # the same checked gestures as acting.py (thumb + hooked index on the nose, elbow crook placed with the
            # real arm lengths...); hands on the face follow the head that look() just turned
            import acting
            acting.apply(self, {s: getattr(acting, name)(self, s)})
        elif name == "fist_press":
            # side = the fist (palm down); the other hand comes down on top and presses: cracking one hand.
            # For a whole crack (squeeze -> pop -> relax) with hands that stay together use acting.Timeline.
            import acting
            acting.apply(self, acting.fist_top(self, s, press=kw.get("press", 0.0), pop=kw.get("pop", 0.0)))
        elif name == "interlace":
            # fingers laced, palms out; ext 0 = at the chest, 1 = arms pushed forward (crack them all)
            import acting
            acting.apply(self, acting.lace(self, kw.get("ext", 1.0)))
        elif name == "hands_up":
            # hand(s) raised beside the face, palm to the camera (show a hand, surrender, X-ray of a hand)
            R = self.rig.matrix_world
            for q in kw.get("sides", s):
                qx = _SIDE[q]
                self.arm(q, R @ Vector((0.20 * qx, -0.28, cz + 0.067)), elbow_hint=(0.5 * qx, 0.3, -1),
                         hand_dir=(0.06 * qx, -0.15, 1), palm=(0, -1, 0))
                self.fingers(q, curl=0.05, thumb=0.0)
        elif name == "point":
            S = self.rig.matrix_world @ self.pb[f"upperarm01.{s}"].matrix.to_translation()
            w = S + M @ Vector((0.25 * sx, -0.5, 0.05))
            self.arm(s, w, elbow_hint=(0.3 * sx, 0, -1), hand_dir=(0.3 * sx, -1, 0.1))
            self.fingers(s, curl=0.85, thumb=0.6)
            self.fingers(s, curl=0.0, only=(2,))
        else:
            raise ValueError(f"unknown pose {name}")
        if name in ("pinch_nose", "near_nose", "cover_mouth", "grab_throat", "elbow_sneeze", "elbow_up", "point") and not kw.get("keep_other"):
            self.arms_down(o)          # the free hand goes down (keep_other=True leaves it where it was)
        self.key(frame, hold)

    def begin(self, frame, dur=10):
        """Start a custom pose: begin(f, dur) -> look()/arm()/fingers() -> key(f). Same easing as pose()."""
        self._begin(frame, dur)

    def act(self, frame, setup, dur=10, hold=0, **look):
        """Custom pose in one call: `setup(person)` positions arms/fingers; head/chest (pitch, yaw, roll, spine,
        lean) are set first so the arm solver sees the final chest. Example:
            def wave(p): p.arm("R", p.rig.matrix_world @ Vector((-0.3, -0.2, 1.7)), hand_dir=(0, 0, 1), palm=(0, -1, 0))
            guy.act(120, wave, dur=8, pitch=-5)"""
        self._begin(frame, dur)
        self.look(**{k: look.get(k, 0) for k in ("pitch", "yaw", "roll", "spine", "lean")})
        setup(self)
        self.key(frame, hold)

    def arms_down(self, side):
        sx = _SIDE[side]
        S = self.rig.matrix_world @ self.pb[f"upperarm01.{side}"].matrix.to_translation()
        w = S + self.rig.matrix_world.to_3x3() @ Vector((0.07 * sx, -0.06, -0.55))
        self.arm(side, w, elbow_hint=(0.2 * sx, 0.6, 0), hand_dir=(0.05 * sx, -0.05, -1))
        self.fingers(side, curl=0.18, thumb=0.1)

    # ---------- QA: catch broken poses before rendering
    def check(self, start, end, step=2, shots=None):
        """Scan frames and return a list of problems: an arm or hand going through the head, neck or chest,
        a wrist twisted like a candy wrapper, a fully locked or reversed elbow. `shots` = [(f0, f1), ...] to only
        check frames where this person is on screen. Run it in preview mode and fix every line before rendering."""
        sc = bpy.context.scene
        bones = self.rig.data.bones
        R = self._rest
        hh, ht = bones["head"].head_local, bones["head"].tail_local
        iod = (R["eye.L"].to_translation() - R["eye.R"].to_translation()).length
        head_r = 1.45 * iod                      # sphere a bit inside the skull: touching the face is allowed
        probs, seen = [], set()

        def seg_dist(p, a, b):
            ab = b - a
            t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
            return (a + ab * t - p).length

        def on_screen(f):
            return shots is None or any(a <= f <= b for a, b in shots)

        for f in range(start, end + 1, step):
            if not on_screen(f):
                continue
            sc.frame_set(f)
            P = lambda n: self.pb[n].head.copy()           # noqa: E731  (rig space, posed)
            T = lambda n: self.pb[n].tail.copy()           # noqa: E731
            hc = P("head") + (T("head") - P("head")) * 0.35 + Vector((0, 0.01, 0))
            neck_a, neck_b = P("neck01"), P("head")
            chest_a, chest_b = P("spine03"), P("neck01")
            hmi = (self.pb["head"].matrix @ R["head"].inverted()).inverted()   # posed -> rest, head space
            for s in "LR":
                parts = {"upper arm": (P(f"upperarm01.{s}"), P(f"lowerarm01.{s}")),
                         "forearm": (P(f"lowerarm01.{s}"), P(f"wrist.{s}")),
                         "hand": (P(f"wrist.{s}"), P(f"finger3-1.{s}"))}
                for part, (a, b) in parts.items():
                    # head + face volume: an ellipsoid fitted to this body's head vertices (rest), moved with the head
                    ell = getattr(self, "_head_ell", None)
                    if ell:
                        c, ax = ell
                        shrink = 0.72 if part == "hand" else 0.82     # hands may touch the face, not sink in
                        worst = 9.0
                        for q in (0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.0):
                            pr = hmi @ a.lerp(b, q) - c
                            worst = min(worst, math.sqrt((pr.x / ax.x) ** 2 + (pr.y / ax.y) ** 2 + (pr.z / ax.z) ** 2))
                        if worst < shrink:
                            probs.append((f, f"{s} {part} goes through the head/face (depth {(shrink - worst) * 100:.0f}%)"))
                    else:
                        d = min(seg_dist(hc, a, b), (a - hc).length, (b - hc).length)
                        if d < head_r - 0.01:
                            probs.append((f, f"{s} {part} goes through the head ({(head_r - d) * 100:.0f} cm deep)"))
                    if part != "hand":
                        for q in (0.25, 0.5, 0.75):
                            x = a.lerp(b, q)
                            if seg_dist(x, neck_a, neck_b) < 0.035:
                                probs.append((f, f"{s} {part} goes through the neck"))
                                break
                            if part == "forearm" and seg_dist(x, chest_a, chest_b) < 0.075:
                                probs.append((f, f"{s} forearm goes through the chest"))
                                break
                if s == "L":   # the two arms against each other (laced fingers may touch, forearms may not cross through)
                    fl = (P("lowerarm01.L"), P("wrist.L"))
                    fr = (P("lowerarm01.R"), P("wrist.R"))
                    dmin = min(seg_dist(fl[0].lerp(fl[1], q), *fr) for q in (0.0, 0.25, 0.5, 0.75, 1.0))
                    if dmin < 0.03:
                        probs.append((f, f"forearms go through each other ({(0.03 - dmin) * 100:.0f} cm)"))
                    hl = (P("wrist.L"), P("finger3-1.L"))
                    hr = (P("wrist.R"), P("finger3-1.R"))
                    dh = min(seg_dist(hl[0].lerp(hl[1], q), *hr) for q in (0.0, 0.5, 1.0))
                    if dh < 0.008:
                        probs.append((f, f"hands go through each other ({(0.008 - dh) * 1000:.0f} mm)"))
                tw = abs(math.degrees(self._wrist_twist(s)))
                if tw > 60:
                    probs.append((f, f"{s} wrist twisted {tw:.0f} deg against the forearm (skin wrings)"))
                u = (P(f"lowerarm01.{s}") - P(f"upperarm01.{s}")).normalized()
                v = (P(f"wrist.{s}") - P(f"lowerarm01.{s}")).normalized()
                bend = math.degrees(u.angle(v))
                if bend > 165:
                    probs.append((f, f"{s} elbow folded {bend:.0f} deg (forearm inside the upper arm)"))
        out = []
        key = lambda m: re.sub(r"[\d.]+", "#", m)  # noqa: E731
        for f, msg in probs:                # collapse runs of the same problem, keep the worst wording
            if out and key(out[-1][1]) == key(msg) and f - out[-1][2] <= step:
                out[-1] = (out[-1][0], max(out[-1][1], msg, key=lambda m: float((re.findall(r"[\d.]+", m) or ["0"])[0])), f)
                continue
            out.append((f, msg, f))
        return [f"{self.col.name[3:]}: frames {a}-{b}: {m}" for a, m, b in out]

    # ---------- keys
    def _begin(self, frame, dur):
        """Hold the animated state until frame - dur, then stop the action from overriding the bones while
        the new pose is solved (key() re-attaches it). The new pose starts from the state at `frame`."""
        sc = bpy.context.scene
        ad = self.rig.animation_data
        if ad and ad.action:
            if dur and frame - dur >= 1:
                sc.frame_set(frame - dur)
                self._insert(frame - dur)
            sc.frame_set(frame)
            self._act = ad.action
            snap = {p.name: p.rotation_quaternion.copy() for p in self.pb}
            ad.action = None
            for p in self.pb:
                p.rotation_quaternion = snap[p.name]
            self._upd()

    def _insert(self, frame):
        for n in self._touched:
            self.pb[n].keyframe_insert("rotation_quaternion", frame=frame)

    def key(self, frame, hold=0):
        act = getattr(self, "_act", None)
        if act is not None:
            snap = {n: self.pb[n].rotation_quaternion.copy() for n in self._touched}
            self.rig.animation_data.action = act
            self._act = None
            for n, q in snap.items():
                self.pb[n].rotation_quaternion = q
        self._insert(frame)
        if hold:
            self._insert(frame + hold)
        _ease_all(self.rig)

    def key_all(self, frame):
        """Key every bone touched so far at `frame` (call once at frame 1 so later poses blend from it)."""
        self.key(frame)

    def move(self, frame, loc=None, rot=None, dur=12):
        """Move/turn the whole person (rig object). rot = (x, y, z) degrees."""
        r = self.rig
        r.keyframe_insert("location", frame=frame - dur)
        r.keyframe_insert("rotation_euler", frame=frame - dur)
        if loc is not None:
            r.location = loc
        if rot is not None:
            r.rotation_euler = tuple(math.radians(a) for a in rot)
        r.keyframe_insert("location", frame=frame)
        r.keyframe_insert("rotation_euler", frame=frame)
        _ease_all(r)

    def jolt(self, frame, amount=1.0):
        """Sneeze/pop jerk: head and chest snap forward and come back."""
        for f, k in ((frame - 3, -0.4), (frame, 1.0), (frame + 6, 0.35), (frame + 14, 0.0)):
            self._begin(f, 0)
            self.look(pitch=22 * k * amount, spine=14 * k * amount)
            self.key(f)


if __name__ == "__main__" and "--" in sys.argv:
    args = sys.argv[sys.argv.index("--") + 1:]
    if args and args[0] == "make":
        make(args[1], json.loads(args[2]) if len(args) > 2 else None)
