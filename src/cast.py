"""
Scene choreography for stickman mode.

Stickman mode has no photo library to lean on for "what is this scene is
about", so the stick figures themselves have to carry the visual, not
just stand in one spot narrating. This module decides, per scene, who
else shares the frame with the narrator and what they're actually doing
-- a silent character just standing next to the narrator was the whole
"generic and dull" problem; everyone else on screen needs their own
reason to be there: pointing at the same thing, reacting a half-beat
behind, or caught up in the same crisis.

One character is always "the narrator" -- the only one whose mouth
flaps, driven by the real TTS word boundaries, since there's only one
audio track. Everyone else is a reactive extra: present, posed, moving,
sometimes pointing at the narrator or at the shared diagram prop, but
silent. Each extra runs on its own time offset (never just `t`) so a
scene with several characters never reads as one puppet cloned -- they
drift, point, and react slightly out of sync with each other.

It also draws the scene's vector "diagram" prop (icons.py) bigger and
more central than the small corner badge pictures-mode uses -- in
stickman mode this prop IS the diagram, not a decoration next to a photo.
"""
import math

import stickman
import icons as icon_lib

W, H = 1080, 1920

_POINT_POSES = {"point"}               # explaining something -- point at the shared diagram, together
_CROWD_POSES = {"panic", "run"}        # the crisis spreads -- more than one person is caught up in it
_REACT_POSES = {"facepalm"}            # the mistake lands -- someone else's reaction too
_WAVE_POSES = {"wave"}                 # CTA -- two people waving reads warmer than one

_NARRATOR_CY = H * 0.60
_PROP_CX, _PROP_CY, _PROP_R = W * 0.5, H * 0.255, 150


def _idle_drift(t, cycle_s, amount):
    """Slow sine-wave side-to-side pacing -- small enough to still read as
    "standing roughly here, shifting weight" rather than visibly sliding,
    but enough that nothing is ever pinned to one exact pixel for the
    whole scene."""
    return amount * math.sin((t / cycle_s) * 2 * math.pi)


def _traverse(t, duration, span, phase=0.0):
    """A one-way walk across `span` px over the scene's full duration --
    for poses about motion (run/panic), a figure actually travels
    somewhere instead of animating its limbs on a fixed spot. `phase`
    offsets where along that walk a given figure starts, so a crowd
    doesn't move in lockstep."""
    progress = min(1.0, t / duration) if duration > 0 else 0.0
    return -span / 2 + span * progress + phase


def draw_cast(draw, scene, boundaries, t, duration, pal, icon_name, font=None):
    """Draws every character plus the scene's vector prop for one frame.
    `t` is the current frame's time within the scene; `duration` is the
    scene's total length (needed for the run/panic traverse, which paces
    itself across the whole scene rather than looping forever)."""
    pose = stickman.pose_for_scene(scene)
    talking = stickman.is_speaking(boundaries, t) if boundaries else False

    if pose in _POINT_POSES:
        _point_scene(draw, pose, talking, t, pal)
    elif pose in _CROWD_POSES:
        _crowd_scene(draw, pose, talking, t, duration, pal)
    elif pose in _REACT_POSES:
        _react_scene(draw, pose, talking, t, pal)
    elif pose in _WAVE_POSES:
        _wave_scene(draw, pose, talking, t, pal)
    else:
        cx = W / 2 + _idle_drift(t, 7.0, 70)
        stickman.draw_stickman(draw, cx, _NARRATOR_CY, 62, pose, t, talking, pal["ink"], pal["dim"])

    if icon_name:
        pulse = 1.0 + 0.05 * math.sin(t * 2.0)
        r = _PROP_R * pulse
        draw.ellipse([_PROP_CX - r, _PROP_CY - r, _PROP_CX + r, _PROP_CY + r], outline=pal["grid"], width=3)
        icon_lib.draw_icon(draw, icon_name, _PROP_CX, _PROP_CY, r * 0.62, pal["ink"], font=font)


def _point_scene(draw, pose, talking, t, pal):
    """Narrator and a silent partner stand either side of the floating
    diagram prop above them and both point UP at it with their near arm
    -- two people visibly reacting to the same thing, not one person
    gesturing at empty air while someone stands next to him doing
    nothing. The partner's own near-arm angle is computed live (see
    stickman.draw_stickman's `aim`) from wherever the prop actually is,
    so this keeps working even if the prop position ever moves."""
    cx = W * 0.34 + _idle_drift(t, 5.0, 16)
    partner_cx = W * 0.68 - _idle_drift(t, 6.2, 16)
    cy = _NARRATOR_CY

    stickman.draw_stickman(
        draw, cx, cy, 62, pose, t, talking, pal["ink"], pal["dim"],
        aim=("r", (_PROP_CX, _PROP_CY)),
    )
    stickman.draw_stickman(
        draw, partner_cx, cy, 56, "stand", t + 1.1, False, pal["dim"], pal["dim"],
        aim=("l", (_PROP_CX, _PROP_CY)),
    )


def _crowd_scene(draw, pose, talking, t, duration, pal):
    """The crisis spreads -- the narrator plus two background figures all
    react or move, each on its own time offset and lane, so it reads as
    a crowd caught up in the same thing rather than one character cloned
    twice. `run` gives everyone an actual one-way traverse across the
    frame (paced to the scene's real duration); `panic` keeps everyone
    rooted in place, just visibly losing it on their own beat."""
    span = 260 if pose == "run" else 0
    narrator_cx = W / 2 + (_traverse(t, duration, span) if span else _idle_drift(t, 0.6, 18))
    stickman.draw_stickman(draw, narrator_cx, _NARRATOR_CY, 62, pose, t, talking, pal["ink"], pal["dim"])

    extras = [(-300, 44, 0.9, 40), (300, 44, 1.6, -40)]
    for dx, scale, time_offset, lane_phase in extras:
        if span:
            ex_cx = W / 2 + dx + _traverse(t, duration, span, phase=lane_phase)
        else:
            ex_cx = W / 2 + dx + _idle_drift(t, 0.5 + time_offset * 0.1, 14)
        stickman.draw_stickman(draw, ex_cx, _NARRATOR_CY + 90, scale, pose, t + time_offset, False, pal["dim"], pal["dim"])


def _react_scene(draw, pose, talking, t, pal):
    """The root cause lands -- a second character facepalms right along
    with the narrator, half a beat behind, like the realization is
    spreading across the room rather than belonging to one person."""
    cx = W * 0.38 + _idle_drift(t, 6.0, 14)
    partner_cx = W * 0.64 - _idle_drift(t, 6.6, 14)
    stickman.draw_stickman(draw, cx, _NARRATOR_CY, 62, pose, t, talking, pal["ink"], pal["dim"])
    stickman.draw_stickman(draw, partner_cx, _NARRATOR_CY, 54, pose, t + 0.6, False, pal["dim"], pal["dim"], mirror=True)


def _wave_scene(draw, pose, talking, t, pal):
    """CTA -- two people waving at each other reads warmer and less like
    a lone announcement than one person waving at the camera alone."""
    cx = W * 0.38 + _idle_drift(t, 4.0, 10)
    partner_cx = W * 0.64 - _idle_drift(t, 4.4, 10)
    stickman.draw_stickman(draw, cx, _NARRATOR_CY, 62, pose, t, talking, pal["ink"], pal["dim"])
    stickman.draw_stickman(draw, partner_cx, _NARRATOR_CY, 54, pose, t + 0.3, False, pal["dim"], pal["dim"], mirror=True)
