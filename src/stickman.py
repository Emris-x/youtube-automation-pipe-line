"""
A small procedural stick-figure character, drawn with plain PIL line
primitives so it matches the hacker-terminal line-art look exactly (no
raster assets, nothing to download). One consistent character acts out a
pose per scene, synced loosely to the voice via a flapping mouth.

Pose chosen from scene["visual"] (deterministic, no guessing at runtime):
  title_card         -> stand    (confident open stance)
  bullet_reveal       -> point    (gesturing at the explanation)
  icon_sequence       -> point
  bar_chart_animate   -> point
  loop_animation      -> panic    (arms up — things going wrong)
  data_flow           -> walk     (mid-stride — something is moving/spreading)
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
    "data_flow": "walk",
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


def draw_stickman(draw, cx, cy, scale, pose, t, talking, color, dim_color):
    """cx, cy = position of the figure's hip (rough center). scale = head
    radius in px, everything else is proportional to it."""
    s = scale
    w = max(3, int(s * 0.22))

    # idle sway so a static pose still reads as "alive"
    sway = math.sin(t * 1.6) * s * 0.06

    head_cy = cy - s * 3.4
    neck = (cx + sway, cy - s * 2.4)
    hip = (cx, cy)

    # legs
    if pose == "walk":
        stride = math.sin(t * 5.0) * s * 0.9
        draw.line([hip, (cx - stride, cy + s * 2.2)], fill=color, width=w)
        draw.line([hip, (cx + stride, cy + s * 2.2)], fill=color, width=w)
    else:
        bob = math.sin(t * 2.0) * s * 0.05
        draw.line([hip, (cx - s * 0.55, cy + s * 2.2 + bob)], fill=color, width=w)
        draw.line([hip, (cx + s * 0.55, cy + s * 2.2 - bob)], fill=color, width=w)

    # torso
    draw.line([hip, neck], fill=color, width=w)

    # arms, by pose
    shoulder = neck
    if pose == "point":
        draw.line([shoulder, (cx + s * 1.9, cy - s * 2.7)], fill=color, width=w)  # pointing arm, up-right
        draw.line([shoulder, (cx - s * 0.5, cy - s * 1.1)], fill=color, width=w)  # other arm, relaxed
    elif pose == "panic":
        flail = math.sin(t * 8.0) * s * 0.3
        draw.line([shoulder, (cx - s * 1.5 + flail, cy - s * 3.6)], fill=color, width=w)
        draw.line([shoulder, (cx + s * 1.5 - flail, cy - s * 3.6)], fill=color, width=w)
    elif pose == "walk":
        swing = math.sin(t * 5.0) * s * 0.7
        draw.line([shoulder, (cx - swing, cy - s * 0.9)], fill=color, width=w)
        draw.line([shoulder, (cx + swing, cy - s * 0.9)], fill=color, width=w)
    elif pose == "facepalm":
        draw.line([shoulder, (cx + s * 0.4, head_cy + s * 0.2)], fill=color, width=w)  # hand to face
        draw.line([shoulder, (cx - s * 0.6, cy - s * 0.9)], fill=color, width=w)
    elif pose == "wave":
        lift = (math.sin(t * 6.0) + 1) / 2  # 0..1
        draw.line([shoulder, (cx + s * 1.3, cy - s * 2.6 - lift * s * 0.8)], fill=color, width=w)
        draw.line([shoulder, (cx - s * 0.5, cy - s * 1.1)], fill=color, width=w)
    else:  # stand
        draw.line([shoulder, (cx - s * 0.9, cy - s * 0.8)], fill=color, width=w)
        draw.line([shoulder, (cx + s * 0.9, cy - s * 0.8)], fill=color, width=w)

    # head
    head_cx = cx + sway
    draw.ellipse([head_cx - s, head_cy - s, head_cx + s, head_cy + s], outline=color, width=w)

    # eyes (two small dots, slight worry-widen on panic)
    eye_r = s * (0.12 if pose != "panic" else 0.16)
    for ex in (-0.35, 0.35):
        ey = head_cy - s * 0.1
        exx = head_cx + s * ex
        draw.ellipse([exx - eye_r, ey - eye_r, exx + eye_r, ey + eye_r], fill=color)

    # mouth: flaps while talking, otherwise a flat dim line (idle)
    mouth_y = head_cy + s * 0.45
    if talking and (t * 6.0) % 1.0 < 0.5:
        draw.ellipse([head_cx - s * 0.3, mouth_y - s * 0.18, head_cx + s * 0.3, mouth_y + s * 0.18], outline=color, width=max(2, w - 2))
    else:
        draw.line([head_cx - s * 0.28, mouth_y, head_cx + s * 0.28, mouth_y], fill=dim_color, width=max(2, w - 2))
