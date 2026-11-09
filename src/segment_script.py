"""
Turns plain text (what Emris types into GRACE) into a scene-structured
script JSON — no AI call, zero cost, since scripts are being written by
hand now.

Input convention: separate each scene with a blank line. First scene is
treated as the hook, last as the call-to-action; everything in between
cycles through the motion graphics visual types. If there's no blank line
at all (one big paragraph), it's auto-split into ~20-word chunks instead,
so a lazily-pasted script still works.

A plainly-typed script (one narration line per paragraph) is the common
case and needs none of what follows. But a script pasted from a
screenplay-style template -- a title block, "Format:/Duration:/Tone:"
spec lines, "SCENE 1 — THE OFFER (7-15s)" headers, "Visual: ..." stage
direction, "Narration:"/"Seller's Dialogue:" labels -- used to get every
one of those paragraphs spoken aloud verbatim right along with the real
narration, because the splitter had no idea any of it wasn't dialogue.
What follows exists to tell those apart: some labels just get their
prefix stripped (the words after "Narration:" ARE meant to be spoken),
others mean drop the whole paragraph (a "Visual:" line is describing the
shot, never meant to be heard), and a couple of general heuristics catch
a bare scene heading or a run of spec lines even when the label wording
doesn't match anything on the list.
"""
import json
import re
import sys

from icons import matched_keywords, brand_tags

MID_VISUALS = ["icon_sequence", "bar_chart_animate", "loop_animation", "data_flow", "bullet_reveal"]

# These labels mean "the rest of this paragraph IS meant to be spoken, just
# drop the label word itself" -- "Narration:", "Scene 2:", "Seller's
# Dialogue:" all introduce real lines. `\s*` around the separator already
# reaches across a newline, so "Narration:\n\"quote\"" (label on its own
# line, text below it) is handled the same as "Narration: quote" on one.
_STRIP_LABEL_RE = re.compile(
    r"^\s*(scene\s*[\w-]+|hook|cta|call[\s-]?to[\s-]?action|intro|outro|"
    r"narration|dialogue|[\w'’]+\s+dialogue)\s*[:\-–—]\s*",
    re.IGNORECASE,
)

# These labels mean the WHOLE paragraph is a stage direction or spec line,
# never spoken narration -- "Visual: an ancient town square..." is
# describing the shot, not a line of dialogue, however narration-shaped it
# reads.
_DROP_LABEL_RE = re.compile(
    r"^\s*(visual|on[\s-]?screen\s*text|end|format|duration|tone|"
    r"visual\s*style|style|camera|sfx|sound\s*effects?|music)\s*[:\-–—]",
    re.IGNORECASE,
)

# A paragraph made of several short "Label: value" lines (Format:/Duration:/
# Tone:/Visual Style:/...) is a spec block, not narration, even though no
# single line's label is on the drop list above -- catches a template's
# metadata header without needing to name every field a person might use.
_KV_LINE_RE = re.compile(r"^\s*[A-Za-z][A-Za-z \t]{1,24}:\s*\S")

# A bare "SCENE 1 — THE STRANGE SELLER (0–7s)" heading, once the "SCENE 1 —"
# part above is stripped, leaves "THE STRANGE SELLER (0–7s)" behind -- a
# title, not a sentence. A trailing (12-34s)-style timecode is a dead
# giveaway; short and punctuation-free is the fallback signal, since real
# narration almost always has a comma or a period somewhere in it.
_TIMECODE_TAIL_RE = re.compile(r"\(\s*\d+\s*[–\-]\s*\d+\s*s\s*\)\s*$", re.IGNORECASE)


def _is_spec_block(paragraph):
    lines = [l for l in paragraph.splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    kv_lines = sum(1 for l in lines if _KV_LINE_RE.match(l))
    return kv_lines >= max(2, (len(lines) + 1) // 2)


def _is_bare_heading(text):
    """A trailing (0-7s)-style timecode is an unambiguous heading signal on
    its own. Short-and-unpunctuated is NOT, by itself -- this project's own
    style is short, punchy, often punctuation-free sentences ("440 million
    dollars in 45 minutes"), so that combination is normal narration, not a
    heading. Mostly-uppercase IS a safe second signal: real narration is
    essentially never written in all caps, but a leftover scene title
    ("THE STRANGE SELLER") reliably is."""
    if not text:
        return True
    if _TIMECODE_TAIL_RE.search(text):
        return True
    letters = re.sub(r"[^A-Za-z]", "", text)
    is_mostly_upper = len(letters) >= 3 and letters.isupper()
    return is_mostly_upper and len(text.split()) <= 8


def _is_document_title(paragraph, index, title):
    """Catches a leading "GRACE VIDEO SCRIPT" slug line, or a title line
    that just repeats the title already given separately (the title field,
    or GRACE's own VIDEO_TITLE input) -- only checked for the first couple
    of paragraphs, so a short early SENTENCE of real narration never gets
    caught by this."""
    if index > 1:
        return False
    stripped = paragraph.strip().strip("\"'“”‘’")
    if title and stripped.lower() == title.strip().lower():
        return True
    words = paragraph.split()
    letters_only = re.sub(r"[^A-Za-z]", "", paragraph)
    is_all_caps = letters_only.isupper() and len(letters_only) >= 3
    return is_all_caps and len(words) <= 5 and not re.search(r"\d", paragraph)


def _strip_label(text):
    text = _STRIP_LABEL_RE.sub("", text, count=1).strip()
    # drop a pair of wrapping quotes left over once the label's gone, e.g.
    # `Scene one: "One software update..."` -> `One software update...`
    if len(text) >= 2 and text[0] in "\"'“‘" and text[-1] in "\"'”’":
        text = text[1:-1].strip()
    return text


def _clean_paragraphs(paragraphs, title=None):
    kept = []
    for i, para in enumerate(paragraphs):
        if _DROP_LABEL_RE.match(para) or _is_spec_block(para) or _is_document_title(para, i, title):
            continue
        cleaned = _strip_label(para)
        if not cleaned or _is_bare_heading(cleaned):
            continue
        kept.append(cleaned)
    return kept


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


def text_to_script(raw_text, title=None, terminal_label="script.log", visual_mode="pictures"):
    raw_text = raw_text.strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw_text) if p.strip()]

    # Only re-chunk when no real scene breaks were given in the first place
    # (one giant blank-line-free paragraph) -- that's what this threshold is
    # actually for. It must be checked on the ORIGINAL paragraph count, not
    # the cleaned one: a short, tightly-written script can legitimately
    # clean down to just 1 or 2 real beats, and that's correct, not a sign
    # the splitter failed and needs to fall back to blind word-chunking.
    if len(paragraphs) < 3:
        paragraphs = _chunk_by_words(raw_text)
    paragraphs = _clean_paragraphs(paragraphs, title=title) or paragraphs

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
        keywords = list(dict.fromkeys(matched_keywords(para) + brand_tags(para)))  # dedupe, keep order
        scenes.append({"id": sid, "text": para, "visual": visual, "keywords": keywords})

    first_line = paragraphs[0][:70].rsplit(" ", 1)[0]
    return {
        "topic": title or first_line,
        "niche": "manual",
        "terminal_label": terminal_label,
        "title": title or first_line,
        "description": "",
        "tags": [],
        # "pictures" (default): library photos, with the upload gate.
        # "stickman": no library lookup at all -- stick figures + drawn
        # vector props carry every scene, fully hands-off.
        "visual_mode": visual_mode if visual_mode in ("pictures", "stickman") else "pictures",
        "scenes": scenes,
    }


if __name__ == "__main__":
    import os

    # Prefer SCRIPT_TEXT env var (how GitHub Actions passes it, to dodge
    # shell-quoting issues with pasted text) — fall back to stdin for local use.
    env_text = os.environ.get("SCRIPT_TEXT")
    text = env_text if env_text is not None else sys.stdin.read()
    title = os.environ.get("VIDEO_TITLE") or None
    visual_mode = os.environ.get("VIDEO_MODE") or "pictures"
    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    script = text_to_script(text, title=title, visual_mode=visual_mode)
    if out_path:
        with open(out_path, "w") as f:
            json.dump(script, f, indent=2)
        print(out_path)
    else:
        print(json.dumps(script, indent=2))
