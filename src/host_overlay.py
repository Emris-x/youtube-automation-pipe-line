"""
Puts the host character on top of a finished video and makes it react to
the narration.

The host is a library of short transparent gesture clips rendered once from
a 3D model (tools/host/render_gestures.py -> assets/host/<name>/). Every
clip is the same length and starts and ends in the same neutral pose, so
this file's whole job is scheduling: cut the video into clip-length slots,
decide which gesture fits what is being said in each slot, and composite
the chosen clips over the video in one ffmpeg pass.

What is being said, and when, comes from the subtitle file the build already
produced -- no speech recognition and no AI call here.

Usage (standalone, for testing):
    python host_overlay.py <video.mp4> <subtitles.srt> <out.mp4> [host-name]
"""
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOSTS_DIR = os.path.join(HERE, "..", "assets", "host")

TALK = ["talk_a", "talk_b", "talk_c"]

# Checked in this order; first match wins. Deliberately about tech incidents
# (the channel's subject) -- what a presenter would physically react to.
REACTIONS = [
    ("shock", r"\b(crash\w*|outage|offline|went down|took down|breach\w*|hack\w*|stolen|leak\w*|wiped|deleted|destroy\w*|"
              r"billions?|millions?|disaster|catastroph\w*|worst|collapse\w*|panic|chaos|grounded|froze)\b"),
    ("cheer", r"\b(fixed|restored|recovered|solved|patched|back online|rolled back|saved|finally)\b"),
    ("shrug", r"\b(nobody|no one|somehow|apparently|oops|mistake|forgot|typo|accident\w*|by hand|untested|never tested)\b"),
    ("think", r"(\?|\b(why|how come|what if|the question|turns out|the reason|root cause)\b)"),
    ("point", r"\b(look|watch|here'?s|this is|notice|the cause|because|exactly|the lesson|remember)\b"),
    ("nope", r"\b(never|didn'?t|wasn'?t|couldn'?t|wouldn'?t|refused|denied|no backup|not a)\b"),
]
OUTRO_RE = re.compile(r"\b(follow|subscribe|see you|next time|more stories|for more)\b", re.IGNORECASE)

_TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def parse_srt(path):
    """[(start_s, end_s, text), ...] from an .srt file."""
    with open(path, encoding="utf-8", errors="replace") as f:
        blocks = re.split(r"\n\s*\n", f.read().strip())
    cues = []
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            m = _TIME_RE.search(line)
            if m:
                g = [int(x) for x in m.groups()]
                start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                cues.append((start, end, " ".join(lines[i + 1:])))
                break
    return cues


def plan_gestures(cues, duration, slot, available):
    """One gesture name per slot of `slot` seconds. Talking gestures while
    someone is speaking, idle in the gaps, a specific reaction when the words
    in that slot call for one -- but never the same reaction twice running,
    and never two big reactions back to back, so it reads as a presenter
    rather than a twitch."""
    talk = [g for g in TALK if g in available] or ["idle"]
    n = max(1, math.ceil(duration / slot))
    plan, talk_i, last_reaction_slot = [], 0, -9
    for i in range(n):
        t0, t1 = i * slot, (i + 1) * slot
        spoken, text = 0.0, []
        for start, end, cue_text in cues:
            overlap = min(end, t1) - max(start, t0)
            if overlap > 0:
                spoken += overlap
                text.append(cue_text)
        text = " ".join(text)
        if spoken < slot * 0.25:
            plan.append("idle" if "idle" in available else talk[0])
            continue
        choice = None
        if i == 0 and "wave" in available:
            choice = "wave"
        elif i >= n - 2 and OUTRO_RE.search(text) and "wave" in available and "wave" not in plan[1:]:
            choice = "wave"
        elif i - last_reaction_slot >= 2:
            for name, pattern in REACTIONS:
                if name in available and re.search(pattern, text, re.IGNORECASE) and name not in plan[-3:]:
                    choice = name
                    break
        if choice and choice != "wave":
            last_reaction_slot = i
        if not choice:
            choice = talk[talk_i % len(talk)]
            talk_i += 1
        plan.append(choice)
    return plan


def _probe(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
         "-of", "json", video], capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    return info["streams"][0]["width"], info["streams"][0]["height"], float(info["format"]["duration"])


def _decode(clip, w, h):
    """All frames of one gesture clip as a list of raw RGBA byte strings,
    scaled to the size it will be drawn at. `-c:v libvpx-vp9` before -i is
    required: ffmpeg's built-in VP9 decoder silently drops the alpha channel."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", clip, "-vf", f"scale={w}:{h}:flags=lanczos",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True, check=True).stdout
    size = w * h * 4
    return [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]


def layout(video_w, video_h, clip_w, clip_h):
    """Where the host stands, as (x, y, w, h) in video pixels.
    Portrait (Shorts): lower left, feet above the band YouTube covers with
    the title and channel name, clear of the buttons down the right edge.
    Landscape: lower right corner."""
    if video_h >= video_w:
        h = int(video_h * 0.48) // 2 * 2
        w = int(h * clip_w / clip_h) // 2 * 2
        return -int(w * 0.07), int(video_h * 0.83) - h, w, h
    h = int(video_h * 0.60) // 2 * 2
    w = int(h * clip_w / clip_h) // 2 * 2
    return video_w - w + int(w * 0.05), video_h - h, w, h


def add_host(video, srt, out, host="robot"):
    host_dir = os.path.join(HOSTS_DIR, host)
    with open(os.path.join(host_dir, "manifest.json")) as f:
        man = json.load(f)
    available = [g for g in man["gestures"] if os.path.isfile(os.path.join(host_dir, f"{g}.webm"))]
    if not available:
        raise RuntimeError(f"host '{host}' has no gesture clips")

    vw, vh, duration = _probe(video)
    x, y, w, h = layout(vw, vh, man["width"], man["height"])
    fps, slot = man["fps"], man["frames"] / man["fps"]
    cues = parse_srt(srt) if srt and os.path.isfile(srt) else []
    plan = plan_gestures(cues, duration, slot, available)
    print(f"[host] {host}: " + " ".join(plan))

    frames = {g: _decode(os.path.join(host_dir, f"{g}.webm"), w, h) for g in set(plan)}
    for g, fr in frames.items():
        if not fr:
            raise RuntimeError(f"could not decode host clip '{g}'")

    proc = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error",
        "-i", video,
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-filter_complex", f"[0:v][1:v]overlay={x}:{y}:eof_action=pass:format=auto[v]",
        "-map", "[v]", "-map", "0:a?", "-c:a", "copy",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-t", f"{duration:.3f}", "-movflags", "+faststart", out,
    ], stdin=subprocess.PIPE)
    try:
        for g in plan:
            for frame in frames[g]:
                proc.stdin.write(frame)
        proc.stdin.close()
    except BrokenPipeError:
        pass  # ffmpeg stops reading once it has the video's full length
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed while compositing the host")
    return plan


if __name__ == "__main__":
    add_host(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "robot")
