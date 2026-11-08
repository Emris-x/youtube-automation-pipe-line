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


def _draw_character_and_icon(draw, scene, boundaries, t, pose, icon_name, pal):
    """Stick figure acting out the scene's pose, plus a small badge icon for
    whatever the sentence is actually about, when one was detected. A soft
    glow pulses behind the figure's head while it's actually speaking, so
    the sync to the voice reads at a glance, not just via the mouth flap."""
    cx, cy = W / 2, H * 0.58
    talking = stickman.is_speaking(boundaries, t) if boundaries else False

    if talking:
        glow_cx, glow_cy = cx, cy - 62 * 3.4
        glow_r = 62 * 1.5 + 10 * math.sin(t * 10.0)
        for i in range(3, 0, -1):
            rr = glow_r * (1 + i * 0.22)
            col = tuple(int(_lerp(pal["bg"][c], pal["ink"][c], 0.10 / i)) for c in range(3))
            draw.ellipse([glow_cx - rr, glow_cy - rr, glow_cx + rr, glow_cy + rr], fill=col)

    stickman.draw_stickman(draw, cx, cy, 62, pose, t, talking, pal["ink"], pal["dim"])

    if icon_name:
        bx, by, br = W * 0.80, H * 0.20, 78
        pulse = 1.0 + 0.04 * math.sin(t * 2.2)
        draw.ellipse(
            [bx - br * pulse, by - br * pulse, bx + br * pulse, by + br * pulse],
            outline=pal["grid"], width=3,
        )
        icon_lib.draw_icon(draw, icon_name, bx, by, br * 0.55, pal["ink"], font=_font(44, FONT_MONO_BOLD))


def render_scene(scene, boundaries, out_path, fps=FPS, theme=None):
    theme = theme or THEME
    duration = boundaries[-1]["offset_s"] + boundaries[-1]["duration_s"] if boundaries else 3.0
    n_frames = max(1, int(duration * fps))

    frame_dir = out_path + "_frames"
    os.makedirs(frame_dir, exist_ok=True)

    accent = GRADIENT_ACCENTS.get(scene["visual"], (255, 255, 255))
    pose = stickman.pose_for_scene(scene) if CHARACTERS else None
    icon_name = icon_lib.pick_icon_for_text(scene.get("text", "")) if CHARACTERS else None
    pal = TERMINAL_PALETTES.get(theme)

    for f in range(n_frames):
        t = f / fps
        active_idx = 0
        for i, b in enumerate(boundaries):
            if b["offset_s"] <= t:
                active_idx = i
            else:
                break

        if pal is not None:
            img = _terminal_bg(t, pal)
            draw = ImageDraw.Draw(img)
            _motif_terminal(draw, scene["visual"], t, pal)
            if CHARACTERS:
                _draw_character_and_icon(draw, scene, boundaries, t, pose, icon_name, pal)
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
