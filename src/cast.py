"""
Scene choreography for stickman mode.

Stickman mode has no photo library to lean on for "what is this scene
about", so the stick figures themselves have to carry the visual, not
just stand in one spot narrating. This module decides, per scene:

  - whether a second, silent character joins the narrator (a listener/
    conversation partner -- poses that are already "explaining something"
    read naturally as two people, one talking, one being talked at/to)
  - where everyone stands, and whether they actually move during the
    scene (a slow idle drift so standing/talking poses aren't nailed to
    one pixel; a real left-to-right traverse for poses that are already
    about movement, like run/panic)

One character is always "the narrator" -- the only one whose mouth flaps,
driven by the real TTS word boundaries, since there's only one audio
track. Anyone else is a reactive extra: present, posed, maybe moving, but
silent.

It also draws the scene's vector "diagram" prop (icons.py) bigger and
more central than the small corner badge pictures-mode uses -- in
stickman mode this prop IS the diagram, not a decoration next to a photo.
"""
import math

import stickman
import icons as icon_lib

W, H = 1080, 1920

# Poses that already read as "explaining something to someone" get a
# second, silent character to explain it TO, instead of the narrator
# gesturing at empty air.
_TWO_CHARACTER_POSES = {"point"}
# Poses that are already literally about movement get a real traverse
# across the frame instead of pacing in place.
_TRAVERSE_POSES = {"run", "panic"}

_NARRATOR_CY = H * 0.60
_PROP_CX, _PROP_CY, _PROP_R = W * 0.5, H * 0.255, 150


def _idle_drift(t, cycle_s, amount):
    """Slow sine-wave side-to-side pacing -- small enough to still read as
    "standing roughly here, shifting weight" rather than visibly sliding,
    but enough that nothing is ever pinned to one exact pixel for the
    whole scene."""
    return amount * math.sin((t / cycle_s) * 2 * math.pi)


def _traverse(t, duration, span):
    """A one-way walk across `span` px over the scene's full duration --
    for poses about motion (run/panic), the figure actually travels
    somewhere instead of animating its limbs on a fixed spot."""
    progress = min(1.0, t / duration) if duration > 0 else 0.0
    return -span / 2 + span * progress


def draw_cast(draw, scene, boundaries, t, duration, pal, icon_name, font=None):
    """Draws every character plus the scene's vector prop for one frame.
    `t` is the current frame's time within the scene; `duration` is the
    scene's total length (needed for the run/panic traverse, which paces
    itself across the whole scene rather than looping forever)."""
    pose = stickman.pose_for_scene(scene)
    talking = stickman.is_speaking(boundaries, t) if boundaries else False
    two_up = pose in _TWO_CHARACTER_POSES

    if two_up:
        cx = W * 0.36 + _idle_drift(t, 5.0, 16)
        partner_cx = W * 0.68 - _idle_drift(t, 6.2, 16)
    elif pose in _TRAVERSE_POSES:
        cx = W / 2 + _traverse(t, duration, 260)
    else:
        cx = W / 2 + _idle_drift(t, 7.0, 70)
    cy = _NARRATOR_CY
    scale = 56 if two_up else 62

    stickman.draw_stickman(draw, cx, cy, scale, pose, t, talking, pal["ink"], pal["dim"])

    if two_up:
        # a silent listener reacting to the narrator -- a different phase
        # offset (not just mirrored motion) so the two don't move like a
        # single puppet with its reflection.
        stickman.draw_stickman(
            draw, partner_cx, cy, scale, "stand", t + 1.4, False, pal["dim"], pal["dim"], mirror=True,
        )

    if icon_name:
        pulse = 1.0 + 0.05 * math.sin(t * 2.0)
        r = _PROP_R * pulse
        draw.ellipse([_PROP_CX - r, _PROP_CY - r, _PROP_CX + r, _PROP_CY + r], outline=pal["grid"], width=3)
        icon_lib.draw_icon(draw, icon_name, _PROP_CX, _PROP_CY, r * 0.62, pal["ink"], font=font)
