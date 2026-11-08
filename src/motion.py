"""
Motion graphics renderer.

Renders one scene (synced to its TTS word-timing) as an MP4 clip using
Pillow for frame drawing + ffmpeg for encoding. Vertical 1080x1920 by
default — Shorts/Reels format gets far more algorithmic push for a brand
new channel than long-form, which matters a lot for early traction.

Three visual themes:

  "terminal" (DEFAULT) — blueprint/hacker-terminal look: black background,
  faint cyan blueprint grid, scanline flicker, monospace type, terminal
  header bar, typewriter-style caption reveal with a blinking cursor.
  This is the channel's locked visual identity — distinct from the
  cartoon-explainer look most tech/AI channels use, built for the
  "explain it through real incidents/breaches" angle.

  "light" — the same terminal layout (grid, header bar, typewriter caption,
  stick figure, icon badges), just re-skinned onto a white/paper
  background with dark ink type instead of phosphor green on black. Same
  bones, different skin — picked by rendering through the TERMINAL_PALETTES
  dict below rather than duplicating all the drawing code.

  "gradient" — the original soft dark-gradient + bold sans caption look
  (kept for anyone who wants it / A-B testing against the terminal look).

Per scene.visual, a motif animates behind/around the caption:
  title_card, bullet_reveal, icon_sequence, bar_chart_animate,
  loop_animation, data_flow, reveal_text, subscribe_animation

Set the theme via the VIDEO_THEME env var, or pass theme= to render_scene.
"""
import functools
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont, ImageFilter

import stickman
import icons as icon_lib
import library
import cast as cast_lib

W, H = 1080, 1920
FPS = 30

THEME = os.environ.get("VIDEO_THEME", "terminal")  # "terminal" (default) | "light" | "gradient"
# Stick-figure character + contextual keyword icon, layered on top of the
# existing abstract motif. "off" restores the old backdrop-only look.
CHARACTERS = os.environ.get("VIDEO_CHARACTERS", "on") != "off"


@functools.lru_cache(maxsize=8)
def _resolve_font(fc_pattern, *hardcoded_fallbacks):
    """Find a font file portably via fontconfig (works across distros/CI
    runners where exact paths differ), falling back to known hardcoded paths,
    then PIL's bundled default as a last resort."""
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", fc_pattern],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if out and os.path.exists(out):
            return out
    except Exception:
        pass
    for path in hardcoded_fallbacks:
        if os.path.exists(path):
            return path
    return None  # caller's ImageFont.truetype will fail -> _font() catches it


FONT_SANS_BOLD = _resolve_font(
    "Poppins:bold", "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
FONT_MONO_BOLD = _resolve_font(
    "Fira Code:bold", "/usr/share/fonts/truetype/firacode/FiraCode-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
)
FONT_MONO_SEMI = _resolve_font(
    "Fira Code:style=SemiBold", "/usr/share/fonts/truetype/firacode/FiraCode-SemiBold.ttf",
    FONT_MONO_BOLD,
)

# Terminal theme: one locked palette (brand consistency) — phosphor green on
# near-black, cyan for blueprint grid lines, amber reserved for warnings/CTAs.
TERM_BG = (6, 10, 8)
TERM_GRID = (0, 180, 190)       # faint cyan blueprint lines
TERM_GREEN = (60, 255, 140)     # primary phosphor text/accent
TERM_GREEN_DIM = (40, 120, 90)  # already-spoken / inactive text
TERM_AMBER = (255, 180, 60)     # CTA / warning accent

# Both "terminal" and "light" share every drawing function below — only the
# colors differ, selected through this dict. A palette needs: bg, grid (full
# strength, used for header divider/motif lines), grid_line (pre-dimmed, used
# for the background grid), ink (primary stroke/text/accent), dim
# (already-spoken / inactive text), revealed (caption words already typed but
# not the active one), accent (CTA/warning), header_bg, vignette (bool),
# vignette_color, scanlines (bool), scanline_color.
TERMINAL_PALETTES = {
    "terminal": dict(
        bg=TERM_BG, grid=TERM_GRID,
        grid_line=tuple(int(c * 0.22) for c in TERM_GRID),
        ink=TERM_GREEN, dim=TERM_GREEN_DIM, revealed=(190, 255, 220),
        accent=TERM_AMBER, header_bg=(14, 20, 18),
        vignette=True, vignette_color=(0, 0, 0),
        scanlines=True, scanline_color=(0, 0, 0),
    ),
    "light": dict(
        bg=(250, 249, 245), grid=(120, 140, 150),
        grid_line=(224, 224, 214),
        ink=(22, 26, 24), dim=(150, 152, 144), revealed=(70, 74, 70),
        accent=(214, 72, 42), header_bg=(236, 235, 228),
        vignette=False, vignette_color=(230, 228, 218),
        scanlines=False, scanline_color=(238, 237, 230),
    ),
}

# Gradient theme (v1) accents, kept for the alt style
GRADIENT_ACCENTS = {
    "title_card": (255, 90, 95),
    "bullet_reveal": (90, 160, 255),
    "icon_sequence": (255, 190, 60),
    "bar_chart_animate": (120, 230, 150),
    "loop_animation": (190, 120, 255),
    "data_flow": (90, 220, 220),
    "reveal_text": (255, 150, 90),
    "subscribe_animation": (255, 90, 170),
}


def _font(size, path):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- gradient (v1)

def _gradient_bg(accent, t):
    img = Image.new("RGB", (W, H), (12, 12, 16))
    draw = ImageDraw.Draw(img)
    cx = W / 2 + math.sin(t * 0.5) * 120
    cy = H * 0.35 + math.cos(t * 0.3) * 80
    max_r = 900
    steps = 40
    for i in range(steps, 0, -1):
        frac = i / steps
        r = max_r * frac
        shade = tuple(int(_lerp(12, accent[c] * 0.35, 1 - frac)) for c in range(3))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=shade)
    return img


def _draw_caption_gradient(draw, active_word_idx, boundaries, accent):
    words = [b["text"] for b in boundaries]
    groups = _wrap_words(words, max_chars=16)
    running, group_idx, local_idx = 0, 0, 0
    for gi, g in enumerate(groups):
        if active_word_idx < running + len(g):
            group_idx, local_idx = gi, active_word_idx - running
            break
        running += len(g)
    group = groups[group_idx] if groups else words
    font = _font(78, FONT_SANS_BOLD)
    space_w = draw.textlength(" ", font=font)
    total_w = sum(draw.textlength(w, font=font) for w in group) + space_w * (len(group) - 1)
    x = (W - total_w) / 2
    y = H * 0.72
    for i, w in enumerate(group):
        color = accent if i == local_idx else (235, 235, 235)
        yy = y - 6 if i == local_idx else y
        draw.text((x, yy), w, font=font, fill=color, stroke_width=6 if i == local_idx else 5, stroke_fill=(0, 0, 0))
        x += draw.textlength(w, font=font) + space_w


# ---------------------------------------------------------------- terminal (default)

def _terminal_bg(t, pal):
    """Themed background: faint blueprint grid + (terminal-only) vignette and
    scanline drift. Same structure for every palette, just different ink."""
    img = Image.new("RGB", (W, H), pal["bg"])
    draw = ImageDraw.Draw(img)

    grid_spacing = 64
    offset = int((t * 8) % grid_spacing)
    for x in range(-offset, W + grid_spacing, grid_spacing):
        draw.line([(x, 0), (x, H)], fill=pal["grid_line"], width=1)
    for y in range(-offset, H + grid_spacing, grid_spacing):
        draw.line([(0, y), (W, y)], fill=pal["grid_line"], width=1)

    if pal["vignette"]:
        vignette = Image.new("L", (W, H), 0)
        vd = ImageDraw.Draw(vignette)
        vd.ellipse([-200, -200, W + 200, H * 0.9], fill=60)
        img = Image.composite(img, Image.new("RGB", (W, H), pal["vignette_color"]), vignette.point(lambda p: 255 - p))

    draw = ImageDraw.Draw(img)
    if pal["scanlines"]:
        for y in range(0, H, 4):
            draw.line([(0, y), (W, y)], fill=pal["scanline_color"], width=1)

    return img


def _terminal_header(draw, t, pal, label="breach_report.sh"):
    """Fake terminal title bar — instantly reads as 'hacker/dev' content."""
    bar_h = 86
    draw.rectangle([0, 0, W, bar_h], fill=pal["header_bg"])
    draw.line([(0, bar_h), (W, bar_h)], fill=pal["grid"], width=2)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([40 + i * 48, bar_h / 2 - 14, 68 + i * 48, bar_h / 2 + 14], fill=c)
    font = _font(32, FONT_MONO_SEMI)
    draw.text((200, bar_h / 2 - 16), f"~/{label}", font=font, fill=pal["dim"])
    # blinking cursor-ish clock dots on the right
    dots = "." * (1 + int(t * 2) % 3)
    draw.text((W - 90, bar_h / 2 - 16), dots, font=font, fill=pal["dim"])


def _wrap_words(words, max_chars=16):
    groups, cur, cur_len = [], [], 0
    for w in words:
        if cur and cur_len + len(w) > max_chars:
            groups.append(cur)
            cur, cur_len = [], 0
        cur.append(w)
        cur_len += len(w) + 1
    if cur:
        groups.append(cur)
    return groups


def _draw_caption_terminal(draw, active_word_idx, boundaries, t, pal):
    """Typewriter caption: a terminal prompt '>' followed by the current
    phrase being 'typed' word by word, brighter ink on the active word
    (with a brief scale-pop the instant it becomes active, so each word
    lands with a bit of punch instead of just appearing), dimmer on
    already-revealed words, with a blinking block cursor."""
    words = [b["text"] for b in boundaries]
    groups = _wrap_words(words, max_chars=16)
    running, group_idx, local_idx = 0, 0, 0
    for gi, g in enumerate(groups):
        if active_word_idx < running + len(g):
            group_idx, local_idx = gi, active_word_idx - running
            break
        running += len(g)
    group = groups[group_idx] if groups else words

    base_size = 64
    font = _font(base_size, FONT_MONO_BOLD)
    prompt = "> "
    prompt_w = draw.textlength(prompt, font=font)

    visible = group[: local_idx + 1]  # typewriter: only reveal up to active word
    space_w = draw.textlength(" ", font=font)
    total_w = prompt_w + sum(draw.textlength(w, font=font) for w in visible) + space_w * max(0, len(visible) - 1)
    x = (W - total_w) / 2
    y = H * 0.72

    draw.text((x, y), prompt, font=font, fill=pal["dim"])
    x += prompt_w

    # time since this word became the active one, for the pop decay
    since_active = t - boundaries[active_word_idx]["offset_s"] if boundaries else 1.0

    for i, w in enumerate(visible):
        is_active = (i == len(visible) - 1)
        color = pal["ink"] if is_active else pal["revealed"]
        if is_active and since_active < 0.14:
            pop_font = _font(int(base_size * (1.0 + 0.22 * (1 - since_active / 0.14))), FONT_MONO_BOLD)
            draw.text((x, y - (pop_font.size - base_size) * 0.4), w, font=pop_font, fill=color)
        else:
            draw.text((x, y), w, font=font, fill=color)
        x += draw.textlength(w, font=font) + space_w

    # blinking block cursor
    if int(t * 2.5) % 2 == 0:
        draw.rectangle([x, y + 6, x + 28, y + 58], fill=pal["ink"])


def _motif_terminal(draw, visual, t, pal):
    cx, cy = W / 2, H * 0.32
    if visual == "icon_sequence":
        for i in range(6):
            ang = t * 1.1 + i * (math.pi / 3)
            r = 220 + 18 * math.sin(t * 2 + i)
            x = cx + r * math.cos(ang)
            y = cy + r * math.sin(ang) * 0.6
            s = 24 + 6 * math.sin(t * 3 + i)
            draw.rectangle([x - s, y - s, x + s, y + s], outline=pal["grid"], width=4)
    elif visual == "bar_chart_animate":
        bars = 7
        base_y = cy + 150
        for i in range(bars):
            phase = (t * 1.4 + i * 0.55) % (2 * math.pi)
            h = 70 + 100 * (0.5 + 0.5 * math.sin(phase))
            x0 = cx - 280 + i * 85
            draw.rectangle([x0, base_y - h, x0 + 48, base_y], outline=pal["ink"], width=4)
            draw.rectangle([x0, base_y - h, x0 + 48, base_y], fill=tuple(int(_lerp(pal["bg"][c], pal["ink"][c], 0.18)) for c in range(3)))
    elif visual == "loop_animation":
        r = 190
        start = (t * 85) % 360
        draw.arc([cx - r, cy - r, cx + r, cy + r], start, start + 240, fill=pal["ink"], width=10)
        draw.arc([cx - r, cy - r, cx + r, cy + r], 0, 360, fill=tuple(int(_lerp(pal["bg"][c], pal["grid"][c], 0.3)) for c in range(3)), width=3)
    elif visual == "data_flow":
        for i in range(12):
            phase = (t * 1.0 + i * 0.3) % 1.0
            y = cy - 230 + phase * 460
            x = cx + 150 * math.sin(phase * math.pi * 2 + i)
            s = 6 + 6 * (1 - abs(0.5 - phase) * 2)
            draw.ellipse([x - s, y - s, x + s, y + s], fill=pal["ink"])
    elif visual == "reveal_text":
        r = 10
        for i in range(8):
            rr = 180 + i * 22 + 10 * math.sin(t * 2)
            alpha = max(0, 1 - i / 8)
            col = tuple(int(_lerp(pal["bg"][c], pal["ink"][c], alpha * 0.25)) for c in range(3))
            draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col, width=2)
    elif visual == "subscribe_animation":
        r = 140 + 22 * math.sin(t * 3)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=pal["accent"], width=8)
        font = _font(46, FONT_MONO_BOLD)
        txt = "./follow --now"
        tw = draw.textlength(txt, font=font)
        draw.text((cx - tw / 2, cy - 26), txt, font=font, fill=pal["accent"])
    elif visual == "title_card":
        r = 300
        draw.arc([cx - r, cy - r, cx + r, cy + r], 0, 300, fill=pal["ink"], width=6)
        draw.arc([cx - r, cy - r, cx + r, cy + r], 320, 360, fill=pal["accent"], width=6)


_BACKDROP_CHAR_CX, _BACKDROP_CHAR_CY = W * 0.24, H * 0.76  # the stickman's anchor when standing on a photo backdrop


def _draw_character_and_icon(draw, scene, boundaries, t, pose, icon_name, pal, backdrop=False):
    """Stick figure acting out the scene's pose, plus a small badge icon for
    whatever the sentence is actually about, when one was detected. Just a
    plain stickman -- no glow effect behind it; the mouth-flap animation
    alone carries the "currently speaking" cue.

    When `backdrop` is True (a real picture fills the frame instead of the
    procedural motif), the figure moves to a lower corner -- out of the
    picture's main subject -- and always uses the "point" pose, so it
    visibly reads as "look at this" rather than overlapping the photo's
    center. The badge icon is skipped there too; the photo already shows
    what the scene is about. (The dark grounding patch behind it that
    makes the plain green linework read as "standing in the scene" rather
    than a flat outline pasted on top is pasted separately, in
    render_scene, before this is called -- it needs to sit under the
    photo's own gradient overlay but it's alpha-blended, which plain
    ImageDraw calls on `draw` can't do.)"""
    if backdrop:
        cx, cy = _BACKDROP_CHAR_CX, _BACKDROP_CHAR_CY
        pose = "point"
    else:
        cx, cy = W / 2, H * 0.58
    talking = stickman.is_speaking(boundaries, t) if boundaries else False

    stickman.draw_stickman(draw, cx, cy, 62, pose, t, talking, pal["ink"], pal["dim"])

    if icon_name and not backdrop:
        bx, by, br = W * 0.80, H * 0.20, 78
        pulse = 1.0 + 0.04 * math.sin(t * 2.2)
        draw.ellipse(
            [bx - br * pulse, by - br * pulse, bx + br * pulse, by + br * pulse],
            outline=pal["grid"], width=3,
        )
        icon_lib.draw_icon(draw, icon_name, bx, by, br * 0.55, pal["ink"], font=_font(44, FONT_MONO_BOLD))


_GROUND_SHADOW_CACHE = None


def _ground_shadow_rgba():
    """Soft dark radial patch, precomputed once and cached, pasted behind
    the stickman whenever it's standing on a photo backdrop -- without it,
    the flat green linework has nothing to visually sit on and reads as a
    transparent outline stapled on top of the photo rather than a
    character actually standing in the scene.

    Built as a real per-pixel radial falloff (computed small, then
    upscaled with BILINEAR for a soft edge) rather than several solid
    ImageDraw ellipses stacked on top of each other -- ImageDraw.ellipse
    overwrites pixels instead of blending them, so a lower-alpha small
    ellipse drawn over a higher-alpha big one made the CENTER more
    transparent than the rim: a flat gray "donut"/tire shape instead of a
    shadow, which is exactly as bad as the outline problem this exists to
    fix."""
    global _GROUND_SHADOW_CACHE
    if _GROUND_SHADOW_CACHE is not None:
        return _GROUND_SHADOW_CACHE
    rw, rh = 460, 520
    sw, sh = 92, 104  # small working res, computed once -- upscaled below
    small = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    cx, cy = sw / 2, sh * 0.56
    rx, ry = sw * 0.46, sh * 0.42
    max_alpha = 130
    for y in range(sh):
        for x in range(sw):
            dx, dy = (x - cx) / rx, (y - cy) / ry
            d = (dx * dx + dy * dy) ** 0.5
            if d >= 1.0:
                continue
            a = int(max_alpha * (1.0 - d) ** 1.6)
            if a > 0:
                small.putpixel((x, y), (3, 5, 4, a))
    _GROUND_SHADOW_CACHE = small.resize((rw, rh), Image.BILINEAR)
    return _GROUND_SHADOW_CACHE


_BACKDROP_MAX_DIM = 1600  # load bigger than the old inset card -- this now fills the whole 1080x1920 frame


def _load_scene_image(path):
    """Loads a library image sized for a full-bleed backdrop and flattens
    it onto a neutral fill (so a transparent PNG doesn't leave a hole once
    it's covering the whole frame, not just sitting in a small card)."""
    try:
        img = Image.open(path).convert("RGBA")
    except Exception as e:
        print(f"[motion] couldn't load library image {path}: {e}")
        return None
    w, h = img.size
    scale = min(_BACKDROP_MAX_DIM / max(w, h), 4.0)  # cap upscaling of a tiny source image
    if scale > 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    flat = Image.new("RGB", img.size, (14, 18, 16))
    flat.paste(img, (0, 0), img)
    return flat


def _backdrop_motion(scene_id):
    """Deterministic per-scene zoom direction + pan drift (from the scene
    id, not random.random()) so repeated renders of the same scene are
    identical, but consecutive scenes with pictures don't all drift the
    same way."""
    seed = sum(ord(c) for c in str(scene_id or "x"))
    zoom_in = seed % 2 == 0
    pan_dx = ((seed * 7) % 7 - 3) / 3.0  # -1..1
    pan_dy = ((seed * 13) % 7 - 3) / 3.0
    return zoom_in, pan_dx, pan_dy


# Ken Burns speed, in zoom-fraction / pan-fraction PER SECOND of scene
# time -- a 1s scene and a 6s scene now move at the same visual speed,
# they just cover different total distances, instead of both always
# traveling the full range regardless of how long they actually run for.
_BACKDROP_ZOOM_RATE_S = 0.018   # +1.8%/s zoom
_BACKDROP_MAX_ZOOM_DELTA = 0.16  # cap even for a long scene
_BACKDROP_PAN_RATE_S = 0.16      # fraction of the available pan room per second

_BACKDROP_OVERLAY_CACHE = None


def _backdrop_overlay_rgba():
    """Dark gradient over the lower half of the frame, precomputed once and
    cached -- it's pixel-identical on every frame of every scene, so
    rebuilding it with a 1920-row Python putpixel() loop on every single
    frame (as the first version of this did) was pure waste."""
    global _BACKDROP_OVERLAY_CACHE
    if _BACKDROP_OVERLAY_CACHE is not None:
        return _BACKDROP_OVERLAY_CACHE
    col = Image.new("RGB", (1, H), (3, 5, 4))
    alpha = Image.new("L", (1, H))
    for y in range(H):
        depth = max(0.0, (y - H * 0.42) / (H * 0.58))
        alpha.putpixel((0, y), int(185 * depth ** 1.3))
    col.putalpha(alpha)
    _BACKDROP_OVERLAY_CACHE = col.resize((W, H), Image.NEAREST)
    return _BACKDROP_OVERLAY_CACHE


def _draw_scene_backdrop(img, scene_image, t, duration, scene_id):
    """Fills the whole frame with the scene's matched picture -- a slow Ken
    Burns zoom + pan instead of a static inset card, so a scene with a real
    picture is the backdrop the stickman stands in front of, not a photo
    stapled onto the terminal background. A dark gradient over the lower
    half keeps the caption and stickman readable regardless of what's in
    the picture. Mutates `img` in place; caller re-wraps it in ImageDraw
    afterward for the caption/stickman/header passes.

    Resizes straight from the source crop region to the final WxH in one
    call (PIL's `box` argument) instead of resizing the whole image up to
    an oversized intermediate and then cropping -- the first version of
    this did a full LANCZOS resize of a (potentially) 1600px image on
    *every frame of the whole scene*, which was slow enough to blow past
    the build's time budget. BILINEAR instead of LANCZOS too: at this
    resize ratio, for a continuously panning/zooming backdrop, the
    difference isn't visible, and it's meaningfully cheaper per frame.

    The zoom/pan amount is rate-limited to a fixed speed per second of
    scene time, not a fixed fraction of the scene's length -- the first
    version always traveled the SAME total distance whether the scene was
    1 second or 6 seconds long, so a short scene panned/zoomed much
    faster, visibly carrying the picture's subject out of frame before
    its line of narration even finished."""
    iw, ih = scene_image.size
    zoom_in, pan_dx, pan_dy = _backdrop_motion(scene_id)
    progress = min(1.0, t / max(duration, 0.1))

    zoom_delta = min(_BACKDROP_MAX_ZOOM_DELTA, _BACKDROP_ZOOM_RATE_S * duration)
    z0, z1 = (1.0, 1.0 + zoom_delta) if zoom_in else (1.0 + zoom_delta, 1.0)
    zoom = _lerp(z0, z1, progress)
    cover = max(W / iw, H / ih) * zoom

    pan_amount = min(1.0, _BACKDROP_PAN_RATE_S * duration)
    src_w, src_h = W / cover, H / cover
    max_off_x, max_off_y = max(0.0, iw - src_w), max(0.0, ih - src_h)
    sx = max(0.0, min(max_off_x, (max_off_x / 2) * (1 + pan_dx * pan_amount * progress)))
    sy = max(0.0, min(max_off_y, (max_off_y / 2) * (1 + pan_dy * pan_amount * progress)))

    frame_img = scene_image.resize((W, H), Image.BILINEAR, box=(sx, sy, sx + src_w, sy + src_h))
    img.paste(frame_img, (0, 0))

    overlay = _backdrop_overlay_rgba()
    img.paste(overlay, (0, 0), overlay)


def render_scene(scene, boundaries, out_path, fps=FPS, theme=None, mode="pictures"):
    theme = theme or THEME
    stickman_mode = mode == "stickman"
    duration = boundaries[-1]["offset_s"] + boundaries[-1]["duration_s"] if boundaries else 3.0
    n_frames = max(1, int(duration * fps))

    frame_dir = out_path + "_frames"
    os.makedirs(frame_dir, exist_ok=True)

    accent = GRADIENT_ACCENTS.get(scene["visual"], (255, 255, 255))
    pose = stickman.pose_for_scene(scene) if CHARACTERS else None
    icon_name = icon_lib.pick_icon_for_text(scene.get("text", "")) if CHARACTERS else None
    pal = TERMINAL_PALETTES.get(theme)

    # Stickman mode never touches the picture library -- no upload gate,
    # no "missing picture" fallback, because there's never a picture to
    # look for in the first place. The stick figures + vector prop ARE
    # the visual.
    scene_image = None
    if pal is not None and not stickman_mode:
        image_path = library.best_match(scene.get("keywords", []), scene.get("text", ""))
        if image_path:
            scene_image = _load_scene_image(image_path)
            if scene_image:
                print(f"[{scene.get('id', '?')}] using library image: {os.path.basename(image_path)}")

    for f in range(n_frames):
        t = f / fps
        active_idx = 0
        for i, b in enumerate(boundaries):
            if b["offset_s"] <= t:
                active_idx = i
            else:
                break

        if pal is not None:
            if scene_image is not None:
                img = Image.new("RGB", (W, H), pal["bg"])
                _draw_scene_backdrop(img, scene_image, t, duration, scene.get("id"))
                if CHARACTERS:
                    shadow = _ground_shadow_rgba()
                    sx = int(_BACKDROP_CHAR_CX - shadow.width / 2)
                    sy = int(_BACKDROP_CHAR_CY - shadow.height * 0.42)
                    img.paste(shadow, (sx, sy), shadow)
                draw = ImageDraw.Draw(img)
                if CHARACTERS:
                    _draw_character_and_icon(draw, scene, boundaries, t, pose, icon_name, pal, backdrop=True)
            else:
                img = _terminal_bg(t, pal)
                draw = ImageDraw.Draw(img)
                if stickman_mode:
                    if CHARACTERS:
                        cast_lib.draw_cast(draw, scene, boundaries, t, duration, pal, icon_name, font=_font(44, FONT_MONO_BOLD))
                else:
                    _motif_terminal(draw, scene["visual"], t, pal)
                    if CHARACTERS:
                        _draw_character_and_icon(draw, scene, boundaries, t, pose, icon_name, pal, backdrop=False)
            _terminal_header(draw, t, pal, scene.get("terminal_label", "breach_report.sh"))
            if boundaries:
                _draw_caption_terminal(draw, active_idx, boundaries, t, pal)
        else:
            img = _gradient_bg(accent, t)
            draw = ImageDraw.Draw(img)
            if boundaries:
                _draw_caption_gradient(draw, active_idx, boundaries, accent)

        img.save(os.path.join(frame_dir, f"f{f:05d}.png"))

    try:
        subprocess.run([
            "ffmpeg", "-y", "-framerate", str(fps),
            "-i", os.path.join(frame_dir, "f%05d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path,
        ], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        # capture_output hides ffmpeg's real error by default — surface it
        # instead of letting the caller see only "exit status 1/127".
        print(f"[motion] ffmpeg failed (exit {e.returncode}):\n{e.stderr.decode(errors='replace')}")
        raise

    for fn in os.listdir(frame_dir):
        os.remove(os.path.join(frame_dir, fn))
    os.rmdir(frame_dir)

    return out_path, duration


if __name__ == "__main__":
    scene = {"visual": sys.argv[1] if len(sys.argv) > 1 else "title_card"}
    with open(sys.argv[2]) as f:
        boundaries = json.load(f)
    out = sys.argv[3] if len(sys.argv) > 3 else "output/scene_test.mp4"
    theme = sys.argv[4] if len(sys.argv) > 4 else None
    path, dur = render_scene(scene, boundaries, out, theme=theme)
    print(f"Rendered {path} ({dur:.1f}s) theme={theme or THEME}")
