"""
GRACE's in-video narrator character -- drawn with plain PIL line primitives
so it inherits the exact hacker-terminal line-art look everything else
uses (no raster assets, nothing to download, nothing that goes stale).

v3: bobble-head proportions (bigger head, filled instead of outline-only,
visible ears) and googly eyes (a white sclera circle + a small pupil,
instead of a solid dot) -- modeled after the expressive big-head "stickman
animation" style (character art over an illustrated scene, big round
expressive heads with ears) rather than the earlier minimal blueprint
figure. The fill is a fixed near-white regardless of the per-video accent
color, since it needs to read the same way against the dark hacker-terminal
background and against an uploaded photo backdrop; the outline and
features still use the passed-in `color` so the figure stays tied to
whatever accent color a given video/channel is using.

v2: a real angle-based skeleton animated by keyframes + eased tweening,
instead of v1's per-limb sine formulas. Every pose is a short looping
sequence of named keyframes (limb angles, a torso lean, a vertical bob,
a head tilt) that get interpolated frame to frame with smoothstep easing
-- a real walk/run gait with opposite arm/leg swing and a weight-bearing
bounce, instead of a single continuous wobble. A small expression system
(eyebrows / eyes / mouth, keyed off each pose's "face") rides on top, plus
an idle blink so the character reads as alive even standing still.

Pose chosen from scene["visual"] (deterministic, no guessing at runtime):
  title_card         -> stand    (idle, weight-shifting)
  bullet_reveal       -> point    (gesturing at the explanation)
  icon_sequence       -> point
  bar_chart_animate   -> point
  loop_animation      -> panic    (arms up — things going wrong)
  data_flow           -> run      (something is moving/spreading, fast)
  reveal_text         -> facepalm (the root cause lands)
  subscribe_animation -> wave     (CTA)
"""
import math

POSE_FOR_VISUAL = {
    "title_card": "stand",
    "bullet_reveal": "point",
    "icon_sequence": "point",
    "bar_chart_animate": "point",
    "loop_animation": "panic",
    "data_flow": "run",
    "reveal_text": "facepalm",
    "subscribe_animation": "wave",
}


def pose_for_scene(scene):
    return POSE_FOR_VISUAL.get(scene.get("visual"), "stand")


def is_speaking(boundaries, t):
    """True if some word's [offset, offset+duration) window contains t."""
    for b in boundaries:
        if b["offset_s"] <= t < b["offset_s"] + b["duration_s"]:
            return True
    return False


def _ease(x):
    """Smoothstep -- eases both ends of every tween instead of the linear
    (robotic) interpolation a naive keyframe player would give you."""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _lerp(a, b, t):
    return a + (b - a) * t


def _tween(keyframes, frac):
    """keyframes: a list of (frac, value_dict) pairs, frac strictly
    increasing from 0.0 to 1.0, with the dict at 1.0 equal to the one at
    0.0 so loops land seamlessly. Returns the eased-interpolated dict at
    `frac` (0..1, the current position within one loop of the pose)."""
    for i in range(len(keyframes) - 1):
        f0, v0 = keyframes[i]
        f1, v1 = keyframes[i + 1]
        if f0 <= frac <= f1:
            local = _ease((frac - f0) / (f1 - f0)) if f1 > f0 else 0.0
            return {k: _lerp(v0[k], v1.get(k, v0[k]), local) for k in v0}
    return dict(keyframes[-1][1])


# Each pose loops forever at `cycle_s` seconds per loop (scenes run for an
# arbitrary, unknown duration, so every pose has to sustain indefinitely
# rather than play once). Limb angles are degrees from "hanging straight
# down" (0), positive rotating toward the figure's right -- see
# _limb_point. "bob" is a fraction of the head radius (vertical bounce),
# "lean" is the torso's own angle the same way a limb's is.
POSES = {
    "stand": {
        "cycle_s": 3.4, "face": "neutral",
        "keyframes": [
            (0.00, {"l_arm": -24, "r_arm": 24, "l_leg": -13, "r_leg": 13, "lean": 2, "bob": 0.00, "head_tilt": -3}),
            (0.50, {"l_arm": -18, "r_arm": 30, "l_leg": -16, "r_leg": 10, "lean": -2, "bob": -0.05, "head_tilt": 4}),
            (1.00, {"l_arm": -24, "r_arm": 24, "l_leg": -13, "r_leg": 13, "lean": 2, "bob": 0.00, "head_tilt": -3}),
        ],
    },
    "walk": {
        "cycle_s": 0.86, "face": "neutral",
        "keyframes": [
            (0.00, {"l_arm": 36, "r_arm": -36, "l_leg": -36, "r_leg": 36, "lean": 5, "bob": -0.14, "head_tilt": 0}),
            (0.25, {"l_arm": 0, "r_arm": 0, "l_leg": 0, "r_leg": 0, "lean": 5, "bob": 0.00, "head_tilt": 0}),
            (0.50, {"l_arm": -36, "r_arm": 36, "l_leg": 36, "r_leg": -36, "lean": 5, "bob": -0.14, "head_tilt": 0}),
            (0.75, {"l_arm": 0, "r_arm": 0, "l_leg": 0, "r_leg": 0, "lean": 5, "bob": 0.00, "head_tilt": 0}),
            (1.00, {"l_arm": 36, "r_arm": -36, "l_leg": -36, "r_leg": 36, "lean": 5, "bob": -0.14, "head_tilt": 0}),
        ],
    },
    "run": {
        "cycle_s": 0.42, "face": "urgent",
        "keyframes": [
            (0.00, {"l_arm": 58, "r_arm": -58, "l_leg": -50, "r_leg": 50, "lean": 16, "bob": -0.30, "head_tilt": 0}),
            (0.25, {"l_arm": 8, "r_arm": -8, "l_leg": 8, "r_leg": -8, "lean": 16, "bob": -0.05, "head_tilt": 0}),
            (0.50, {"l_arm": -58, "r_arm": 58, "l_leg": 50, "r_leg": -50, "lean": 16, "bob": -0.30, "head_tilt": 0}),
            (0.75, {"l_arm": -8, "r_arm": 8, "l_leg": -8, "r_leg": 8, "lean": 16, "bob": -0.05, "head_tilt": 0}),
            (1.00, {"l_arm": 58, "r_arm": -58, "l_leg": -50, "r_leg": 50, "lean": 16, "bob": -0.30, "head_tilt": 0}),
        ],
    },
    "point": {
        "cycle_s": 1.7, "face": "alert",
        "keyframes": [
            (0.00, {"l_arm": -16, "r_arm": 104, "l_leg": -13, "r_leg": 13, "lean": -4, "bob": 0.00, "head_tilt": -4}),
            (0.55, {"l_arm": -20, "r_arm": 118, "l_leg": -13, "r_leg": 13, "lean": -4, "bob": -0.07, "head_tilt": -4}),
            (1.00, {"l_arm": -16, "r_arm": 104, "l_leg": -13, "r_leg": 13, "lean": -4, "bob": 0.00, "head_tilt": -4}),
        ],
    },
    "panic": {
        "cycle_s": 0.46, "face": "shock",
        "keyframes": [
            (0.00, {"l_arm": -152, "r_arm": 152, "l_leg": -20, "r_leg": 8, "lean": -4, "bob": -0.08, "head_tilt": -10}),
            (0.50, {"l_arm": -112, "r_arm": 112, "l_leg": -8, "r_leg": 20, "lean": 4, "bob": 0.00, "head_tilt": 10}),
            (1.00, {"l_arm": -152, "r_arm": 152, "l_leg": -20, "r_leg": 8, "lean": -4, "bob": -0.08, "head_tilt": -10}),
        ],
    },
    "facepalm": {
        # the right arm bends at the elbow instead of using a single
        # shoulder-to-hand segment -- a straight line at this angle would
        # run clean through the head (it did, in v2's first pass: looked
        # like a horn, not a hand). r_upper/r_fore replace r_arm for this
        # pose only; draw_stickman bends the arm whenever r_upper is present.
        "cycle_s": 2.4, "face": "facepalm",
        "keyframes": [
            (0.00, {"l_arm": -16, "r_upper": 70, "r_fore": -144, "l_leg": -13, "r_leg": 13, "lean": 0, "bob": 0.00, "head_tilt": 15}),
            (0.55, {"l_arm": -12, "r_upper": 74, "r_fore": -150, "l_leg": -13, "r_leg": 13, "lean": 0, "bob": 0.04, "head_tilt": 19}),
            (1.00, {"l_arm": -16, "r_upper": 70, "r_fore": -144, "l_leg": -13, "r_leg": 13, "lean": 0, "bob": 0.00, "head_tilt": 15}),
        ],
    },
    "wave": {
        "cycle_s": 0.58, "face": "happy",
        "keyframes": [
            (0.00, {"l_arm": -18, "r_arm": 136, "l_leg": -13, "r_leg": 13, "lean": 0, "bob": 0.00, "head_tilt": -4}),
            (0.50, {"l_arm": -18, "r_arm": 178, "l_leg": -13, "r_leg": 13, "lean": 0, "bob": -0.06, "head_tilt": -4}),
            (1.00, {"l_arm": -18, "r_arm": 136, "l_leg": -13, "r_leg": 13, "lean": 0, "bob": 0.00, "head_tilt": -4}),
        ],
    },
}


def _limb_point(origin, length, angle_deg):
    """A point `length` away from `origin`, where angle 0 hangs straight
    down and positive angles rotate toward the figure's right -- shared
    by arms, legs AND the torso (torso is just "a limb" rooted at the hip
    pointing roughly up), so lean/walk/run all move through one formula."""
    ox, oy = origin
    rad = math.radians(angle_deg)
    return ox + length * math.sin(rad), oy + length * math.cos(rad)


def _angle_to(origin, target):
    """The inverse of _limb_point: the angle (in that same "0 = straight
    down, positive = toward the right" convention) from `origin` toward
    `target`, whatever direction that actually is on screen. Lets a limb
    aim at a real point -- another character, a shared prop -- instead of
    only ever following a pose's one baked angle regardless of who or
    what else is in the frame.

    Clamped away from the narrow band around +-180 (straight up): a
    target directly overhead (the floating diagram prop, say) gives an
    angle right around there, and a single straight shoulder-to-hand
    segment at that angle runs clean through the head on its way up --
    the exact "horn, not a hand" bug the facepalm pose's bent elbow was
    built to avoid. There's no elbow bend here, so instead the angle is
    capped short of vertical, which still reads as "pointing up at that"
    (arm raised and angled toward it) without the line crossing the
    skull -- and with v3's bigger bobble head (see module docstring),
    the safe cap is noticeably tighter than it was for the old, smaller
    head: a shoulder-to-hand segment is short relative to the bigger
    head's radius, so even an endpoint that's technically outside the
    head can have most of its length swallowed under it once the head
    (filled, drawn last) paints over everything beneath it. 100 degrees
    leaves a clearly visible stretch of arm outside the head rather than
    just a sliver poking out at the rim."""
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    angle = math.degrees(math.atan2(dx, dy))
    if angle > 100:
        angle = 100
    elif angle < -100:
        angle = -100
    return angle


# Fixed head/ear fill -- deliberately not derived from the channel's
# accent color (see module docstring): a near-white bobble-head reads
# cleanly against both the dark procedural background and an uploaded
# photo backdrop, where a colored or transparent head would either clash
# or disappear.
_SKIN = (240, 236, 224)


def _draw_face(draw, head_cx, head_cy, s, face, talking, t, color, dim_color):
    """Eyebrows + eyes + mouth for the given expression. `talking` always
    overrides the mouth with the flapping talk shape, same as before --
    the face is still clearly mid-sentence regardless of what the pose is
    doing with the rest of the body."""
    w = max(2, int(s * 0.1))

    # idle blink -- a brief height-squash of both eyes every few seconds,
    # so a held pose (stand, point) still reads as alive, not a cutout.
    blink = (t * 0.9) % 4.4
    blinking = blink < 0.12

    brow_sets = {
        "neutral": ((-0.42, -0.08, 0.02), (0.02, -0.08, 0.42)),
        "urgent": ((-0.40, 0.04, -0.02), (-0.02, 0.04, 0.40)),
        "alert": ((-0.42, -0.14, -0.02), (-0.02, -0.14, 0.42)),
        "shock": ((-0.44, -0.22, -0.10), (0.10, -0.22, 0.44)),
        "facepalm": ((-0.36, 0.06, 0.04), (0.04, 0.06, 0.36)),
        "happy": ((-0.40, -0.1, 0.0), (0.0, -0.1, 0.40)),
    }
    (lx0, ly0, lx1), (rx0, ry0, rx1) = brow_sets.get(face, brow_sets["neutral"])
    draw.line([(head_cx + lx0 * s, head_cy + ly0 * s), (head_cx + lx1 * s, head_cy - 0.28 * s)], fill=color, width=w)
    draw.line([(head_cx + rx0 * s, head_cy - 0.28 * s), (head_cx + rx1 * s, head_cy + ry0 * s)], fill=color, width=w)

    eye_y = head_cy - 0.02 * s
    eye_dx = 0.34 * s
    # Bigger than v2's solid dots -- a googly-eye look (white sclera +
    # a smaller dark pupil) instead of a plain filled circle, to match
    # the bobble-head character's bigger, more expressive eyes.
    eye_r = {"shock": 0.26, "alert": 0.20}.get(face, 0.17) * s
    if blinking:
        for ex in (-eye_dx, eye_dx):
            draw.line([(head_cx + ex - eye_r, eye_y), (head_cx + ex + eye_r, eye_y)], fill=color, width=w)
    elif face == "facepalm":
        for ex in (-eye_dx, eye_dx):
            draw.arc([head_cx + ex - eye_r, eye_y - eye_r * 0.5, head_cx + ex + eye_r, eye_y + eye_r * 1.3], 10, 170, fill=color, width=w)
    else:
        pupil_r = eye_r * 0.44
        for ex in (-eye_dx, eye_dx):
            ex_c = head_cx + ex
            draw.ellipse([ex_c - eye_r, eye_y - eye_r, ex_c + eye_r, eye_y + eye_r], fill=_SKIN, outline=color, width=max(2, w - 1))
            draw.ellipse([ex_c - pupil_r, eye_y - pupil_r, ex_c + pupil_r, eye_y + pupil_r], fill=color)

    mouth_y = head_cy + 0.42 * s
    if talking and (t * 6.0) % 1.0 < 0.5:
        draw.ellipse([head_cx - 0.26 * s, mouth_y - 0.16 * s, head_cx + 0.26 * s, mouth_y + 0.16 * s], outline=color, width=max(2, w - 1))
        return
    if talking:
        draw.line([head_cx - 0.24 * s, mouth_y, head_cx + 0.24 * s, mouth_y], fill=dim_color, width=max(2, w - 1))
        return

    if face == "shock":
        draw.ellipse([head_cx - 0.2 * s, mouth_y - 0.2 * s, head_cx + 0.2 * s, mouth_y + 0.2 * s], outline=color, width=max(2, w - 1))
    elif face == "happy":
        draw.arc([head_cx - 0.32 * s, mouth_y - 0.3 * s, head_cx + 0.32 * s, mouth_y + 0.26 * s], 15, 165, fill=color, width=max(2, w - 1))
    elif face == "facepalm":
        draw.line([head_cx - 0.16 * s, mouth_y + 0.04 * s, head_cx + 0.18 * s, mouth_y - 0.04 * s], fill=color, width=max(2, w - 1))
    elif face == "urgent":
        draw.line([head_cx - 0.2 * s, mouth_y, head_cx + 0.2 * s, mouth_y], fill=color, width=max(2, w - 1))
    else:
        draw.arc([head_cx - 0.26 * s, mouth_y - 0.22 * s, head_cx + 0.26 * s, mouth_y + 0.2 * s], 15, 165, fill=color, width=max(2, w - 1))


_MIRROR_KEYS = ("lean", "l_arm", "r_arm", "l_leg", "r_leg", "l_upper", "l_fore", "r_upper", "r_fore", "head_tilt")


def draw_stickman(draw, cx, cy, scale, pose, t, talking, color, dim_color, mirror=False, aim=None):
    """cx, cy = position of the figure's hip (rough center). scale = head
    radius in px, everything else is proportional to it.

    mirror=True flips the figure left-right (a second character facing
    back toward the narrator instead of facing the same way) by negating
    every directional keyframe value before drawing -- every limb/lean/
    tilt angle in POSES is defined as "degrees from straight down,
    positive toward the figure's own right" (see _limb_point), and
    negating that angle reflects each limb about its own origin, which
    for a simple stick figure (all limbs rooted near the hip/neck) reads
    as a clean mirror of the whole figure rather than needing a second,
    separately-authored set of poses.

    aim=(arm_key, (tx, ty)), arm_key "l" or "r": that arm ignores its
    pose's own baked angle and instead points at a real target position
    in frame coordinates (another character, a shared prop), with a
    small idle sway layered on top so it doesn't look frozen. This is
    what lets two characters actually point AT each other / at the same
    thing, rather than each always gesturing at a fixed angle regardless
    of who or what else is on screen."""
    s = scale
    w = max(3, int(s * 0.22))
    joint_r = max(2, int(s * 0.1))

    data = POSES.get(pose, POSES["stand"])
    frac = (t % data["cycle_s"]) / data["cycle_s"] if data["cycle_s"] > 0 else 0.0
    kf = _tween(data["keyframes"], frac)
    if mirror:
        kf = {k: (-v if k in _MIRROR_KEYS else v) for k, v in kf.items()}

    hip = (cx, cy + kf["bob"] * s)
    neck = _limb_point(hip, s * 2.4, 180 + kf["lean"])
    head_cy = neck[1] - s * 1.0
    head_cx = neck[0] + s * 0.012 * kf["head_tilt"]

    if aim:
        arm_key, target = aim
        kf = dict(kf)
        kf[f"{arm_key}_arm"] = _angle_to(neck, target) + 6 * math.sin(t * 1.8)
        kf.pop(f"{arm_key}_upper", None)
        kf.pop(f"{arm_key}_fore", None)

    # legs (from hip)
    l_foot = _limb_point(hip, s * 2.3, kf["l_leg"])
    r_foot = _limb_point(hip, s * 2.3, kf["r_leg"])
    draw.line([hip, l_foot], fill=color, width=w)
    draw.line([hip, r_foot], fill=color, width=w)

    # torso
    draw.line([hip, neck], fill=color, width=w)
    draw.ellipse([hip[0] - joint_r, hip[1] - joint_r, hip[0] + joint_r, hip[1] + joint_r], fill=color)

    # arms (from neck/shoulder). Most poses use one straight shoulder-to-hand
    # segment ("l_arm"/"r_arm") -- those draw now, before the head, same as
    # always. A pose that needs the hand to land ON the head (facepalm)
    # instead supplies "l_upper"/"l_fore" (or the r_ equivalents) for a
    # real bent elbow -- and since v3's head is filled rather than
    # outline-only (module docstring), a resting hand has to be drawn
    # AFTER the head/face, not before, or the now-opaque head simply
    # paints over it. So bent-arm segments are collected here and drawn
    # later, once the head is down. (Straight segments don't need this --
    # they gesture beside the head, not onto it.)
    _pending_bent_arms = []

    def _draw_arm(prefix):
        if f"{prefix}_upper" in kf:
            elbow = _limb_point(neck, s * 1.2, kf[f"{prefix}_upper"])
            hand = _limb_point(elbow, s * 1.0, kf[f"{prefix}_fore"])
            _pending_bent_arms.append((neck, elbow, hand))
            return hand
        hand = _limb_point(neck, s * 1.95, kf[f"{prefix}_arm"])
        draw.line([neck, hand], fill=color, width=w)
        return hand

    l_hand = _draw_arm("l")
    r_hand = _draw_arm("r")
    draw.ellipse([neck[0] - joint_r, neck[1] - joint_r, neck[0] + joint_r, neck[1] + joint_r], fill=color)
    # Hand/elbow joint dots for a bent arm are drawn along with the arm
    # itself below (on top of the head); only a straight arm's hand dot
    # belongs here, underneath.
    for prefix, hand in (("l", l_hand), ("r", r_hand)):
        if f"{prefix}_upper" not in kf:
            draw.ellipse([hand[0] - joint_r * 0.8, hand[1] - joint_r * 0.8, hand[0] + joint_r * 0.8, hand[1] + joint_r * 0.8], fill=color)

    # head -- bigger bobble-head proportions than v2's outline-only circle,
    # filled so it reads solidly against either background, with ears
    # (drawn first so the head's own outline overlaps and seats them
    # cleanly rather than them floating as separate detached circles).
    head_r = s * 1.28
    ear_r = head_r * 0.24
    ear_y = head_cy + head_r * 0.08
    for ex in (-1, 1):
        ear_cx = head_cx + ex * head_r * 0.94
        draw.ellipse([ear_cx - ear_r, ear_y - ear_r, ear_cx + ear_r, ear_y + ear_r], fill=_SKIN, outline=color, width=max(2, w - 1))
    draw.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r], fill=_SKIN, outline=color, width=w)

    _draw_face(draw, head_cx, head_cy, s, data["face"], talking, t, color, dim_color)

    # Now lay any bent (on-face) arm on top, so it reads as a hand resting
    # on the face instead of vanishing under it.
    for neck_pt, elbow, hand in _pending_bent_arms:
        draw.line([neck_pt, elbow], fill=color, width=w)
        draw.line([elbow, hand], fill=color, width=w)
        draw.ellipse([elbow[0] - joint_r * 0.8, elbow[1] - joint_r * 0.8, elbow[0] + joint_r * 0.8, elbow[1] + joint_r * 0.8], fill=color)
        draw.ellipse([hand[0] - joint_r * 0.8, hand[1] - joint_r * 0.8, hand[0] + joint_r * 0.8, hand[1] + joint_r * 0.8], fill=color)
