"""Smooth acting for mh.Person: key the TARGETS (where each wrist is, where the hand points, which way the palm
faces, finger curl, head/chest, face), interpolate them with a monotone cubic, then solve the IK on EVERY frame.

Why: keying solved bone rotations and letting Blender interpolate them makes hands that hold each other drift
apart between keys, and two keys 6 frames apart look like a snap. Here contacts hold on every frame, moves have
ease-in/ease-out (or a quick snap only where you put two keys close together), and a small breathing / sway /
blink layer keeps the person alive during holds.

    import acting as A
    tl = A.Timeline(person)
    tl.key(1,  A.lace(person, ext=0.0), look=dict(pitch=12))
    tl.key(40, A.lace(person, ext=1.0), look=dict(pitch=4), face=dict(lids=-0.6))
    tl.cut(72)                       # last frame of the shot: hold it, jump at the next key
    tl.bake()

Everything is in RIG space (x = his left, -y = in front of him, z = up, metres from his feet). Heights of the
ready-made gestures follow the body (p.A["chest"].z), so they fit tall and short people.

Ready-made gestures (each returns {"L": hand, "R": hand}; mix them: g = A.idle(p); g["R"] = A.palm_up(p, "R")):
    idle(p)                         arms down, soft elbows
    lace(p, ext, grip)              fingers laced, palms out; ext 0 at the chest .. 1 arms pushed out (crack them all)
    unlace(p)                       hands just let go, palms down in front of the belly (use between lace and idle)
    fist_top(p, F, close, cover, press, pop)   fist F, the other hand on top pressing (crack one hand)
    palm_up(p, side) / palm_side(p, side)      look at your hand / the middle key of turning a fist palm-up
    pinch_nose(p, side) / near_nose(p, side)    thumb + hooked index on the nose (near = about to pinch, rubbing)
    cover_mouth(p, side)                        flat hand over the mouth (never together with pinch_nose: the hands collide)
    elbow_up(p, side) -> elbow_sneeze(p, side)  arm folds up, then the crook of the elbow in front of the nose
    grab_throat(p, side)                        hand wrapped round the front of the neck
Your own: A.hand(wrist, elbow_hint, hand_dir, palm, curl, thumb, spread, mcp, rel=False, fc=None) in rig space.
rel=True pins the hand to the HEAD (given in the rest pose; it moves and turns with the head, so a hand pinching the
nose stays on the nose through a sneeze jolt). fc = curl of index/middle/ring/pinky if they differ.

Rules that keep it human:
  * a move takes 8-15 frames, a wind-up before a push 6-10, a snap (the pop itself) 2-3; hold 10+ frames after
  * two keys closer than ~6 frames on a big move = a jerk; bake() prints fast hand moves so you can check them
  * turning a palm over (180 deg) needs a middle key (palm_side) or the hand takes the short way through the body
  * put tl.cut(f) on the last frame of every shot so nothing smears across a hard cut
"""
import math
import random

import bpy
from mathutils import Matrix, Quaternion, Vector

SIDE = {"L": 1.0, "R": -1.0}
LOOK_KEYS = ("pitch", "yaw", "roll", "spine", "lean")
FACE_KEYS = ("jaw", "lids", "brows", "lips")
HAND_SCALARS = ("thumb", "spread", "mcp", "relw")


# ------------------------------------------------------------------ hand frames
def frame_q(hand_dir, palm):
    """Quaternion of the hand frame: Y = hand direction, X = palm normal (orthogonalised), Z = X x Y."""
    y = Vector(hand_dir).normalized()
    x = Vector(palm)
    x = (x - y * x.dot(y)).normalized()
    z = x.cross(y)
    return Matrix((x, y, z)).transposed().to_quaternion()


def q_dirs(q):
    m = q.normalized().to_matrix()
    return m.col[1].copy(), m.col[0].copy()


def finger_curls(curl, cascade=0.07):
    """Natural per-finger curl from one value: index a bit straighter than the pinky."""
    return [max(-0.2, min(1.3, curl + cascade * (fi - 3) * (1.0 - min(1.0, max(0.0, curl))))) for fi in (2, 3, 4, 5)]


def hand(w, hint, hand_dir, palm, curl=0.2, thumb=0.15, spread=0.1, mcp=0.0, rel=False, fc=None):
    return dict(w=Vector(w), hint=Vector(hint), q=frame_q(hand_dir, palm), fc=list(fc) if fc else finger_curls(curl),
                thumb=thumb, spread=spread, mcp=mcp, relw=1.0 if rel else 0.0)


def shoulder(p, s):
    if not hasattr(p, "_acting_S"):
        bpy.context.view_layer.update()
        p._acting_S = {x: p.rig.data.bones[f"upperarm01.{x}"].head_local.copy() for x in "LR"}
    return p._acting_S[s]


# ------------------------------------------------------------------ gestures (rig space). Each returns {"L": hand, "R": hand}
def chest(p):
    return p.A["chest"].z


def idle_hand(p, s, curl=0.22):
    sx = SIDE[s]
    w = shoulder(p, s) + Vector((0.07 * sx, -0.085, -0.515))      # elbows a little soft, hands a bit forward
    return hand(w, (0.2 * sx, 0.6, 0.0), (0.04 * sx, -0.12, -1.0), (-sx, 0.3, 0.0), curl=curl, thumb=0.15, spread=0.08)


def idle(p, curl=0.22):
    return {s: idle_hand(p, s, curl) for s in "LR"}


def lace(p, ext=0.0, grip=0.0):
    """Fingers laced, palms out (thumbs down, wrists bent back). ext 0 = hands in front of the chest,
    1 = arms pushed straight out (the stretch that cracks every knuckle); ext > 1 = the little extra shove."""
    out = {}
    e = min(ext, 1.0)
    for s in "LR":
        sx = SIDE[s]
        d = 0.124 - 0.004 * e                                     # wrist half-distance: fingers interlock to the webbing
        w = (d * sx, -0.25 - 0.25 * ext, chest(p) - 0.113 + 0.07 * ext + (0.0055 if s == "L" else -0.0055))  # half a finger apart
        out[s] = hand(w, (0.55 * sx, 0.3 - 0.2 * e, -1.0), (-sx, -0.05 + 0.05 * e, -0.03), (0.0, -1.0, -0.15),
                      curl=0.20 - 0.10 * e + grip, thumb=0.40, spread=0.10, mcp=-0.30 * max(0.0, ext - 0.6))
    return out


def fist_at(p):
    """Default place of fist_top: in front of the lower chest (rig space)."""
    return (0.0, -0.36, chest(p) - 0.10)


def fist_top(p, F="R", close=1.0, cover=1.0, press=0.0, pop=0.0, at=None):
    """One hand makes a fist (palm down, knuckles forward); the other hand comes down on top of it and presses the
    folded fingers, the usual way to crack all four at once.
    close: 0 open hand .. 1 fist;  cover: 0 the top hand hovers above .. 1 resting on the fist;
    press: 0..1 squeeze;  pop: 0..1 the moment the joints give (fist flexes, top hand sinks a few mm)."""
    C = "L" if F == "R" else "R"
    fx, cx = SIDE[F], SIDE[C]
    P = Vector(at if at is not None else fist_at(p)) + Vector((0.0, 0.015 * press, -0.022 * press - 0.012 * pop))
    tilt = 0.10 * press + 0.16 * pop                               # the fist bends down under the push
    hdF = Vector((0.28 * cx, -1.0, -0.04 - tilt)).normalized()
    wF = P - hdF * 0.085
    out = {F: hand(wF, (fx * (0.75 + 0.6 * press), 0.35, -1.0), hdF, (0.0, -0.12, -1.0),
                   curl=0.25 + 0.75 * close + 0.12 * press + 0.10 * pop, thumb=0.25 + 0.45 * close, spread=0.0)}
    mcp_row = wF + hdF * 0.112                                     # the knuckles of the fist
    hdC = Vector((-0.62 * cx, -1.0, -0.20 - 0.08 * press)).normalized()
    top = 0.040 - 0.008 * press - 0.006 * pop                      # palm centre above the knuckles (hand thickness)
    lift = (1.0 - cover)
    palm_c = mcp_row + Vector((0.08 * cx * lift, 0.010 + 0.03 * lift, top + 0.035 * lift))
    wC = palm_c - hdC * 0.065
    out[C] = hand(wC, (cx * (0.8 + 0.6 * press), 0.3, -1.0), hdC, (0.05 * cx, 0.0, -1.0),
                  curl=0.20 + 0.30 * cover + 0.08 * press, thumb=0.30, spread=0.05)
    return out


def unlace(p, curl=0.3):
    """Hands just let go after the laced stretch: apart, palms down, in front of the belly."""
    return {s: hand((0.15 * SIDE[s], -0.30, chest(p) - 0.25), (0.5 * SIDE[s], 0.4, -1.0), (-0.35 * SIDE[s], -1.0, -0.35),
                    (0.0, 0.1, -1.0), curl=curl, thumb=0.2, spread=0.15) for s in "LR"}


def palm_up(p, s, at=None, curl=0.35):
    """Hand held up in front of him, palm up, fingers a bit curled: 'looking at my hand'."""
    sx = SIDE[s]
    at = at or (0.08 * sx, -0.33, chest(p) - 0.09)
    return hand(at, (0.6 * sx, 0.4, -1.0), (0.35 * -sx, -1.0, 0.25), (0.0, 0.15, 1.0), curl=curl, thumb=0.2, spread=0.15)


def palm_side(p, s, at=None, curl=0.6):
    """Halfway between a fist (palm down) and palm up: thumb up, palm facing in. Use as the middle key of a turn."""
    sx = SIDE[s]
    at = at or (0.07 * sx, -0.35, chest(p) - 0.11)
    return hand(at, (0.6 * sx, 0.4, -1.0), (0.3 * -sx, -1.0, 0.1), (-sx, 0.0, 0.0), curl=curl, thumb=0.3, spread=0.05)


def _nose_hand(p, s, dy, dz, fc, thumb):
    """Thumb on the near side of the nose, index hooked round the far nostril, other fingers loosely curled in front
    of the mouth (palm towards the face). Pinned to the head, so it stays on the nose through a sneeze jolt."""
    sx = SIDE[s]
    w = p.A["nose_tip"] + Vector((-0.02 * sx, dy, dz))
    return hand(w, (0.5 * sx, -0.2, -1.0), (-0.18 * sx, 0.30, 1.0), (-0.3 * sx, 1.0, 0.0), thumb=thumb, spread=0.0, fc=fc, rel=True)


def pinch_nose(p, s="R"):
    """Pinch the nose shut (checked in close-up: no finger reaches the eyes)."""
    return _nose_hand(p, s, -0.062, -0.112, [0.72, 0.9, 1.0, 1.05], 0.3)


def near_nose(p, s="R"):
    """Hand at the nose, not pinching yet: a nose that itches, rubbing it, the moment before the pinch."""
    return _nose_hand(p, s, -0.087, -0.122, [0.55, 0.8, 0.95, 1.0], 0.2)


def cover_mouth(p, s="L"):
    """Flat hand over the mouth."""
    sx = SIDE[s]
    w = p.A["mouth"] + Vector((0.03 * sx, -0.065, -0.085))
    return hand(w, (0.5 * sx, -0.3, -1.0), (-0.5 * sx, 0.2, 1.0), (0.0, 1.0, 0.0), curl=0.12, thumb=0.2, spread=0.05, rel=True)


def grab_throat(p, s="R"):
    """Hand wrapped round the front of the neck, fingers towards the far side (the throat does not turn with the head)."""
    sx = SIDE[s]
    w = p.A["throat"] + Vector((0.06 * sx, -0.045, -0.03))
    return hand(w, (0.5 * sx, -0.2, -1.0), (-0.8 * sx, 0.5, 0.3), (0.2 * sx, 1.0, 0.1), curl=0.55, thumb=0.1, spread=0.05)


def arm_lengths(p, s):
    B = p.rig.data.bones
    S, E, W = (B[f"{n}.{s}"].head_local for n in ("upperarm01", "lowerarm01", "wrist"))
    return (E - S).length, (W - E).length


def _elbow_at(p, s, T, fdir, hd, palm, curl, thumb):
    """Wrist target and elbow hint that put the elbow joint as close to T as the upper arm reaches (exact lengths,
    so the IK lands the elbow there), forearm along fdir."""
    S = shoulder(p, s)
    a, b = arm_lengths(p, s)
    E = S + (Vector(T) - S).normalized() * a
    W = E + Vector(fdir).normalized() * b
    return hand(W, E - (S + W) / 2, hd, palm, curl=curl, thumb=thumb, spread=0.05)


def elbow_sneeze(p, s="R"):
    """Sneeze into the elbow: crook of the elbow in front of the nose and mouth, forearm across the face to the other
    side, hand hanging loose. Not pinned to the head - pitch the head forward (pitch ~13, spine ~9) to bury the face without going through the arm."""
    sx = SIDE[s]
    T = p.A["nose_tip"] + Vector((0.0, -0.08, -0.04))
    return _elbow_at(p, s, T, (-0.95 * sx, 0.75, 0.05), (-0.75 * sx, 0.45, -0.45), (0.0, 1.0, -0.4), 0.25, 0.2)


def elbow_up(p, s="R"):
    """The arm folding up on the way to elbow_sneeze (and back down): elbow in front of the chest, hand at the
    other shoulder. Key it between idle and elbow_sneeze so the forearm never sweeps across the face."""
    sx = SIDE[s]
    T = p.A["nose_tip"] + Vector((0.07 * sx, -0.20, -0.30))
    return _elbow_at(p, s, T, (-0.75 * sx, 0.25, 0.6), (-0.75 * sx, 0.25, 0.6), (0.0, 1.0, -0.3), 0.4, 0.3)


def wipe_nose(p, s="R"):
    """Kept for old plans: now the same safe shape as near_nose."""
    return near_nose(p, s)


# ------------------------------------------------------------------ interpolation
def _flatten(state):
    flat = {}
    for s in "LR":
        h = state["hands"][s]
        for i in range(3):
            flat[f"{s}.w{i}"] = h["w"][i]
            flat[f"{s}.h{i}"] = h["hint"][i]
        for i in range(4):
            flat[f"{s}.q{i}"] = h["q"][i]
        for k in HAND_SCALARS:
            flat[f"{s}.{k}"] = h[k]
        for i in range(4):
            flat[f"{s}.fc{i}"] = h["fc"][i]
    for k in LOOK_KEYS:
        flat["look." + k] = state["look"].get(k, 0.0)
    for k in FACE_KEYS:
        flat["face." + k] = state["face"].get(k, 0.0)
    return flat


def _mono(xs, ys):
    """Fritsch-Carlson monotone cubic tangents (no overshoot between keys, zero speed at the ends and at turns)."""
    n = len(xs)
    if n < 2:
        return [0.0] * n
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [0.0] * n
    for i in range(1, n - 1):
        m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2
    for i in range(n - 1):
        if abs(d[i]) < 1e-12:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        if a * a + b * b > 9:
            t = 3 / math.sqrt(a * a + b * b)
            m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    return m


def _herm(xs, ys, ms, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = max(j for j in range(len(xs) - 1) if xs[j] <= x)
    h = xs[i + 1] - xs[i]
    t = (x - xs[i]) / h
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * ms[i] + (-2 * t3 + 3 * t2) * ys[i + 1]
            + (t3 - t2) * h * ms[i + 1])


# ------------------------------------------------------------------ timeline
class Timeline:
    def __init__(self, person, seed=1, life=1.0):
        self.p = person
        self.keys = []          # (frame, state)
        self.cuts = []
        self.rnd = random.Random(seed)
        self.life = life
        self.ph = [self.rnd.random() * math.tau for _ in range(8)]
        self.tremble = []       # (f0, f1, amount)

    def key(self, frame, hands, look=None, face=None):
        prev = self.keys[-1][1] if self.keys else None
        lk = dict(prev["look"]) if prev else {k: 0.0 for k in LOOK_KEYS}
        fc = dict(prev["face"]) if prev else {k: 0.0 for k in FACE_KEYS}
        if look is not None:
            lk = {k: 0.0 for k in LOOK_KEYS}
            lk.update(look)
        if face is not None:
            fc = {k: 0.0 for k in FACE_KEYS}
            fc.update(face)
        hs = {s: dict(h) for s, h in hands.items()}
        if prev:                                    # keep each hand quaternion in the same hemisphere as before
            for s in "LR":
                if hs[s]["q"].dot(prev["hands"][s]["q"]) < 0:
                    hs[s]["q"] = -hs[s]["q"]
        self.keys.append((frame, dict(hands=hs, look=lk, face=fc)))
        self.keys.sort(key=lambda k: k[0])
        return self

    def hold(self, frame, look=None, face=None):
        """Repeat the last pose at `frame` (optionally with a new look/face)."""
        return self.key(frame, self.keys[-1][1]["hands"], look=look, face=face)

    def shake(self, f0, f1, amount=1.0):
        """Effort tremble of the hands (mm-scale, ~9 Hz) between f0 and f1."""
        self.tremble.append((f0, f1, amount))

    def cut(self, frame):
        """Last frame of a shot: the pose holds after it and jumps at the next key (no smear across a cut)."""
        self.cuts.append(frame)
        return self

    # ----- evaluation
    def _segments(self):
        segs, cur = [], []
        cuts = sorted(self.cuts)
        for f, st in self.keys:
            if cur and any(cur[-1][0] <= c < f for c in cuts):
                segs.append(cur)
                cur = []
            cur.append((f, st))
        if cur:
            segs.append(cur)
        return segs

    def _life(self, f):
        ph, L = self.ph, self.life
        s = lambda per, k: math.sin(math.tau * f / per + ph[k])  # noqa: E731
        return dict(pitch=L * (0.9 * s(83, 0) + 0.45 * s(37, 1)), yaw=L * (1.4 * s(131, 2) + 0.5 * s(53, 3)),
                    roll=L * 0.7 * s(101, 4), spine=L * 0.9 * s(118, 5), lean=L * 0.45 * s(149, 6))

    def _blink(self, f):
        if not hasattr(self, "_blinks"):
            r = random.Random(self.rnd.random())
            self._blinks, t = [], 18
            while t < 5000:
                self._blinks.append(t)
                t += r.randint(70, 120)
        for b in self._blinks:
            if b <= f < b + 7:
                return (1.0, 1.0, 0.9, 0.55, 0.25, 0.08, 0.0)[int(f - b)]
        return 0.0

    def _trem(self, f):
        v = Vector((0, 0, 0))
        for f0, f1, a in self.tremble:
            if f0 <= f <= f1:
                env = min(1.0, (f - f0) / 6.0, (f1 - f) / 4.0 + 0.0001)
                v += Vector((math.sin(f * 1.9), math.sin(f * 2.3 + 1), math.sin(f * 1.7 + 2))) * 0.0018 * a * max(0.0, env)
        return v

    def bake(self):
        p = self.p
        segs = self._segments()
        hidden = [o for o in p.parts if not o.hide_viewport]
        for o in hidden:                      # 15x faster depsgraph updates while solving
            o.hide_viewport = True
        ad = p.rig.animation_data
        saved = ad.action if ad else None
        if ad:
            ad.action = None
        frames, self._wrists = {}, {}
        for seg in segs:
            xs = [f for f, _ in seg]
            flats = [_flatten(st) for _, st in seg]
            names = list(flats[0].keys())
            tang = {n: _mono(xs, [fl[n] for fl in flats]) for n in names}
            for f in range(xs[0], xs[-1] + 1):
                v = {n: (_herm(xs, [fl[n] for fl in flats], tang[n], f) if len(xs) > 1 else flats[0][n]) for n in names}
                frames[f] = self._solve(f, v)
        if ad:
            ad.action = saved
        for n in p._touched:
            p.pb[n].scale = (1.0, 1.0, 1.0)
        for o in hidden:
            o.hide_viewport = False
        self.report = self._speed_report(segs)
        for line in self.report:
            print("acting:", line)
        # write keys; q and -q are the same rotation, but keys that flip sign interpolate through a zero
        # quaternion (the hand collapses / smears into spikes under motion blur) -> keep every bone's sign continuous
        last = {}
        for f in sorted(frames):
            for n, q in frames[f].items():
                if n in last and q.dot(last[n]) < 0:
                    q = -q
                last[n] = q
                p.pb[n].rotation_quaternion = q
                p.pb[n].keyframe_insert("rotation_quaternion", frame=f)
        ends = {seg[-1][0] for seg in segs}
        for fc in _fcurves(p.rig):
            for k in fc.keyframe_points:
                k.interpolation = "CONSTANT" if int(round(k.co.x)) in ends else "BEZIER"
                k.handle_left_type = k.handle_right_type = "AUTO_CLAMPED"
        return sorted(frames)

    def _speed_report(self, segs, limit=0.045):
        """Hands moving faster than `limit` m per frame (~1.4 m/s) outside a deliberate snap read as a jerk."""
        out = []
        for seg in segs:
            xs = [f for f, _ in seg]
            snaps = [(a, b) for a, b in zip(xs, xs[1:]) if b - a <= 3]
            run = None
            for f in range(xs[0] + 1, xs[-1] + 1):
                sp = max((self._wrists[f][s] - self._wrists[f - 1][s]).length for s in "LR")
                fast = sp > limit and not any(a - 1 <= f <= b + 1 for a, b in snaps)
                if fast:
                    run = [run[0] if run else f, f, max(sp, run[2] if run else 0)]
                elif run:
                    out.append(f"fast hand move, frames {run[0]}-{run[1]} ({run[2] * 100:.1f} cm/frame): "
                               f"spread the keys or add an in-between unless it is meant as a snap")
                    run = None
            if run:
                out.append(f"fast hand move, frames {run[0]}-{run[1]} ({run[2] * 100:.1f} cm/frame)")
        return out

    def _solve(self, f, v):
        p = self.p
        for n in p._touched:                  # the solver starts from the last pose: float error in scale would
            p.pb[n].scale = (1.0, 1.0, 1.0)   # compound over hundreds of frames (x7 hands) -> clean it every frame
            p.pb[n].location = (0.0, 0.0, 0.0)
        lf = self._life(f)
        look = {k: v["look." + k] + lf[k] for k in LOOK_KEYS}
        for f0, f1, a in self.tremble:                    # effort tremble also shakes the head (and hands pinned to it)
            if f0 <= f <= f1:
                env = max(0.0, min(1.0, (f - f0) / 6.0, (f1 - f) / 4.0))
                look["pitch"] += math.sin(f * 2.1) * 0.9 * a * env
                look["roll"] += math.sin(f * 2.7 + 1.3) * 0.7 * a * env
                look["spine"] += math.sin(f * 1.6 + 0.4) * 0.4 * a * env
        p.look(**look)
        tr = self._trem(f)
        drift = Vector((math.sin(f / 23.0 + self.ph[7]), math.sin(f / 31.0), math.sin(f / 19.0 + 1))) * 0.0015 * self.life
        Mh = p.pb["head"].matrix @ p._rest["head"].inverted()      # head motion since the rest pose (rig space)
        Rh = Mh.to_quaternion()
        for s in "LR":
            rw = max(0.0, min(1.0, v[f"{s}.relw"]))
            w = Vector([v[f"{s}.w{i}"] for i in range(3)])
            hint = Vector([v[f"{s}.h{i}"] for i in range(3)])
            q = Quaternion([v[f"{s}.q{i}"] for i in range(4)]).normalized()
            if rw > 0:                                              # pinned to the head
                w = w.lerp(Mh @ w, rw)
                hint = hint.lerp(Rh @ hint, rw)
                q = q.slerp(Rh @ q, rw)
            w = w + tr * (1 - rw) + drift * (1 - rw)
            hd, palm = q_dirs(q)
            p.arm(s, p.rig.matrix_world @ w, elbow_hint=hint, hand_dir=hd, palm=palm)
            shape(p, s, None, v[f"{s}.thumb"], v[f"{s}.spread"], v[f"{s}.mcp"], fc=[v[f"{s}.fc{i}"] for i in range(4)])
        self._wrists[f] = {s: p.pb[f"wrist.{s}"].head.copy() for s in "LR"}
        face = {k: v["face." + k] for k in FACE_KEYS}
        b = self._blink(f)
        if b:
            face["lids"] = face["lids"] + (-1.0 - face["lids"]) * b
        p._face_bones(**face)
        bpy.context.view_layer.update()
        return {n: p.pb[n].rotation_quaternion.copy() for n in p._touched}


def shape(p, s, curl, thumb=0.15, spread=0.0, mcp=0.0, cascade=0.07, fc=None):
    """Natural finger curl: index a bit straighter than the pinky, knuckle/middle/tip joints in real proportions.
    mcp < 0 bends the big knuckles backwards (the stretched, about-to-crack look)."""
    fan = {2: -1.0, 3: -0.3, 4: 0.4, 5: 1.0}
    curls = fc if fc is not None else finger_curls(curl, cascade)
    for fi in (2, 3, 4, 5):
        c = curls[fi - 2]
        for j, (k, extra) in enumerate(((84, 30 * mcp), (96, 0.0), (68, 0.0)), start=1):
            q = Quaternion((1, 0, 0), math.radians(k * c + extra))
            if j == 1 and spread:
                q = Quaternion((0, 0, 1), math.radians(12 * spread * fan[fi] * -SIDE[s])) @ q
            n = f"finger{fi}-{j}.{s}"
            p.pb[n].rotation_quaternion = q
            p._touched.add(n)
    # thumb: base joint swings across the palm and flexes (0.7 = tucked under the index/middle like in a real fist),
    # the two outer joints just bend. The old mh.fingers() thumb swung the other way and stuck out under the fist.
    t = thumb
    for j, q in ((1, Quaternion((0, 0, 1), math.radians(-SIDE[s] * 57 * t)) @ Quaternion((1, 0, 0), math.radians(100 * t))),
                 (2, Quaternion((1, 0, 0), math.radians(36 * t))), (3, Quaternion((1, 0, 0), math.radians(43 * t)))):
        n = f"finger1-{j}.{s}"
        p.pb[n].rotation_quaternion = q
        p._touched.add(n)


def _fcurves(obj):
    ad = obj.animation_data
    if not ad or not ad.action:
        return []
    try:
        return list(ad.action.fcurves)
    except AttributeError:
        return [fc for layer in ad.action.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]


def apply(p, hands):
    """Pose the arms and fingers right now from a gesture dict (no keys) - used by mh.Person.pose().
    Hands pinned to the head (rel=True) follow the head as it is posed now (call look() first)."""
    Mh = p.pb["head"].matrix @ p._rest["head"].inverted()
    Rh = Mh.to_quaternion()
    for s, h in hands.items():
        w, hint, q = h["w"], h["hint"], h["q"]
        if h.get("relw", 0) > 0:
            w, hint, q = Mh @ w, Rh @ hint, Rh @ q
        hd, palm = q_dirs(q)
        p.arm(s, p.rig.matrix_world @ w, elbow_hint=hint, hand_dir=hd, palm=palm)
        shape(p, s, None, h["thumb"], h["spread"], h["mcp"], fc=h["fc"])
