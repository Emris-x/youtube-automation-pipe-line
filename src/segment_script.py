"""
Turns plain text (what Emris types into GRACE) into a scene-structured
script JSON — no AI call, zero cost, since scripts are being written by
hand now.

Input convention: separate each scene with a blank line. First scene is
treated as the hook, last as the call-to-action; everything in between
cycles through the motion graphics visual types. If there's no blank line
at all (one big paragraph), it's auto-split into ~20-word chunks instead,
so a lazily-pasted script still works.
"""
import json
import re
import sys

from icons import matched_keywords

MID_VISUALS = ["icon_sequence", "bar_chart_animate", "loop_animation", "data_flow", "bullet_reveal"]

# Matches a leading stage-direction label like "Scene one:", "Scene 3 -",
# "Hook:", "CTA:", "Call to action:", "Intro:" — people (and Claude, when
# dictating a sample script by voice) naturally write scripts with these,
# but they're directions, not dialogue, and were being read aloud verbatim.
_LABEL_RE = re.compile(
    r"^\s*(scene\s*[\w-]+|hook|cta|call[\s-]?to[\s-]?action|intro|outro)\s*[:\-–—]\s*",
    re.IGNORECASE,
)


def _strip_label(text):
    text = _LABEL_RE.sub("", text, count=1).strip()
    # drop a pair of wrapping quotes left over once the label's gone, e.g.
    # `Scene one: "One software update..."` -> `One software update...`
    if len(text) >= 2 and text[0] in "\"'“‘" and text[-1] in "\"'”’":
        text = text[1:-1].strip()
    return text


def _chunk_by_words(text, max_words=22):
    words = text.split()
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def text_to_script(raw_text, title=None, terminal_label="script.log"):
    raw_text = raw_text.strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw_text) if p.strip()]

    if len(paragraphs) < 3:
        # no real scene breaks given -> auto-chunk the whole thing
        paragraphs = _chunk_by_words(raw_text)

    paragraphs = [_strip_label(p) for p in paragraphs]
    paragraphs = [p for p in paragraphs if p]  # a label-only paragraph can strip to nothing

    scenes = []
    n = len(paragraphs)
    for i, para in enumerate(paragraphs):
        if i == 0:
            sid, visual = "hook", "title_card"
        elif i == n - 1:
            sid, visual = "cta", "subscribe_animation"
        else:
            sid = f"point{i}"
            visual = MID_VISUALS[(i - 1) % len(MID_VISUALS)]
        scenes.append({"id": sid, "text": para, "visual": visual, "keywords": matched_keywords(para)})

    first_line = paragraphs[0][:70].rsplit(" ", 1)[0]
    return {
        "topic": title or first_line,
        "niche": "manual",
        "terminal_label": terminal_label,
        "title": title or first_line,
        "description": "",
        "tags": [],
        "scenes": scenes,
    }


if __name__ == "__main__":
    import os

    # Prefer SCRIPT_TEXT env var (how GitHub Actions passes it, to dodge
    # shell-quoting issues with pasted text) — fall back to stdin for local use.
    env_text = os.environ.get("SCRIPT_TEXT")
    text = env_text if env_text is not None else sys.stdin.read()
    title = os.environ.get("VIDEO_TITLE") or None
    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    script = text_to_script(text, title=title)
    if out_path:
        with open(out_path, "w") as f:
            json.dump(script, f, indent=2)
        print(out_path)
    else:
        print(json.dumps(script, indent=2))
