"""
The "algorithm director" — turns a one-line idea plus a few bullet facts
into a full scene-structured script JSON, with NO AI model call: just
templates, word lists and simple heuristics. Free, deterministic, zero
cost, zero API key.

This is deliberately NOT generate_script.py (which calls the Anthropic API
to write real prose from a topic). That path costs money per script and
needs facts an AI can get right; this path is for when Emris already knows
the facts and just wants the busywork of shaping them into a hook / setup /
points / payoff / CTA structure done for him, for free, every time.

It will write plainer scripts than an AI would — it's a structured
storyteller, not a creative one. Think of it as filling in a template with
the facts you hand it, picking which template based on simple signals
(does a fact have a number in it? a contrast word?), not actually
understanding the story.

Input convention: first non-blank line is the idea/topic; every line after
that is one highlight/fact, in the order they should be told. A line
starting with "ROOT:" (case-insensitive) is used as the payoff/root-cause
line instead of just reusing the last highlight. One line alone (no
highlights given) is treated as both the idea and its only highlight, so a
single sentence still produces a full script rather than erroring out.

  python director.py ../scripts/manual_video.json
"""
import hashlib
import json
import re
import sys

from icons import matched_keywords, brand_tags

MID_VISUALS = ["icon_sequence", "bar_chart_animate", "loop_animation", "data_flow", "bullet_reveal"]
MAX_POINTS = 6

_ROOT_RE = re.compile(r"^\s*root\s*:\s*", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d")
_CONTRAST_WORDS = re.compile(r"\b(but|actually|secretly|turns out|really|instead|never|wasn't|didn't)\b", re.IGNORECASE)

# {idea} is treated as a standalone clause that could be a full sentence
# or a short phrase — every template puts it on its own, never embedded
# mid-sentence as if it were definitely a short noun ("...about {idea}
# skips..."), so the grammar holds up either way the idea line is phrased.
_NUMBER_HOOKS = [
    "{fact} That's not a typo.",
    "{fact} Read that again.",
    "{fact} Here's exactly how that happened.",
]
_CONTRAST_HOOKS = [
    "Here's the part of this story nobody tells you. {idea}",
    "{idea} And it's not the twist you'd expect.",
    "The version most people know skips one thing. {idea}",
]
_DEFAULT_HOOKS = [
    "{idea} Here's the part nobody explains properly.",
    "Here's what you're probably not being told. {idea}",
    "{idea} Here's exactly what that actually means.",
]

_SETUP_TEMPLATES = [
    "Here's the setup. {idea} Simple enough on the surface. That's exactly why it's so easy to get wrong.",
    "Before the twist, here's what you need to know going in. {idea}",
    "Let's set the scene. {idea} Everything after this builds on one fact most people skip.",
]

_POINT_CONNECTORS = [
    "Here's what happens first: {fact}",
    "Then: {fact}",
    "Here's the part most people miss: {fact}",
    "And this is where it gets interesting: {fact}",
    "Next: {fact}",
    "But here's the catch: {fact}",
]

_PAYOFF_TEMPLATES = [
    "So here's the real takeaway: {fact} That's the whole story.",
    "And that's the root of it: {fact} Everything else was just the symptom.",
    "Which brings us to the actual answer: {fact}",
]

_CTA_LINES = [
    "If that actually made sense, follow for one of these every week.",
    "That's the short version — follow for more like this.",
    "If this cleared something up, follow — there's a lot more where that came from.",
    "Follow for one of these every week. The next one's even weirder.",
]


def _clean(line):
    return line.strip()


def _pick(options, seed_text, offset=0):
    """Deterministic-but-varied pick: same idea text always gets the same
    template (so re-running a draft doesn't shuffle it), different ideas
    land on different templates."""
    h = int(hashlib.sha1(seed_text.encode()).hexdigest(), 16)
    return options[(h + offset) % len(options)]


def _pick_rotating(options, seed_text, index):
    """Like _pick, but `index` (the point's position) dominates the choice
    so consecutive points don't land on the same connector phrase by hash
    coincidence — the idea text only shifts *where* the rotation starts."""
    h = int(hashlib.sha1(seed_text.encode()).hexdigest(), 16)
    return options[(h + index) % len(options)]


def _parse(raw_text):
    lines = [_clean(l) for l in raw_text.splitlines()]
    lines = [l for l in lines if l]
    if not lines:
        return "", [], None

    idea = lines[0]
    rest = lines[1:]

    root = None
    highlights = []
    for l in rest:
        m = _ROOT_RE.match(l)
        if m:
            root = l[m.end():].strip()
        else:
            highlights.append(l)

    if not highlights:
        # one line total -- use the idea itself as the only highlight too,
        # so a single sentence still produces a full script.
        highlights = [idea]

    return idea, highlights, root


def _build_hook(idea, highlights):
    numbered = next((h for h in highlights if _NUMBER_RE.search(h)), None)
    contrasty = any(_CONTRAST_WORDS.search(h) for h in highlights)

    if numbered:
        template = _pick(_NUMBER_HOOKS, idea)
        return template.format(fact=numbered, idea=idea)
    if contrasty:
        template = _pick(_CONTRAST_HOOKS, idea)
        return template.format(idea=idea)
    template = _pick(_DEFAULT_HOOKS, idea)
    return template.format(idea=idea)


def idea_to_script(raw_text, title=None, terminal_label="idea.log", visual_mode="pictures"):
    """Same call shape as segment_script.text_to_script, so dispatch_queue.py
    and the manual-video workflow can swap between the two based on which
    input mode a given script/queue entry was written in."""
    idea, highlights, root = _parse(raw_text)
    if not idea:
        raise ValueError("No idea text given.")

    scenes = []
    scenes.append({
        "id": "hook", "text": _build_hook(idea, highlights), "visual": "title_card",
        "keywords": list(dict.fromkeys(matched_keywords(idea) + brand_tags(idea))),
    })

    setup_text = _pick(_SETUP_TEMPLATES, idea).format(idea=idea)
    scenes.append({
        "id": "setup", "text": setup_text, "visual": "bullet_reveal",
        "keywords": list(dict.fromkeys(matched_keywords(setup_text) + brand_tags(setup_text))),
    })

    point_facts = highlights[:MAX_POINTS]
    # the last highlight becomes the payoff below unless an explicit ROOT:
    # line was given, so don't also repeat it as a plain point.
    if not root and len(point_facts) > 1:
        point_facts = point_facts[:-1]

    for i, fact in enumerate(point_facts):
        # seeded by the idea (constant across this script's points) so two
        # different ideas rotate differently, but `i` is the dominant term
        # so consecutive points in the SAME script never repeat a connector.
        connector = _pick_rotating(_POINT_CONNECTORS, idea, i)
        text = connector.format(fact=fact)
        scenes.append({
            "id": f"point{i + 1}", "text": text, "visual": MID_VISUALS[i % len(MID_VISUALS)],
            "keywords": list(dict.fromkeys(matched_keywords(text) + brand_tags(text))),
        })

    payoff_fact = root or highlights[-1]
    payoff_text = _pick(_PAYOFF_TEMPLATES, payoff_fact).format(fact=payoff_fact)
    scenes.append({
        "id": "payoff", "text": payoff_text, "visual": "reveal_text",
        "keywords": list(dict.fromkeys(matched_keywords(payoff_text) + brand_tags(payoff_text))),
    })

    cta_text = _pick(_CTA_LINES, idea, offset=1)
    scenes.append({
        "id": "cta", "text": cta_text, "visual": "subscribe_animation", "keywords": [],
    })

    return {
        "topic": title or idea,
        "niche": "director",
        "terminal_label": terminal_label,
        "title": title or idea[:70].rsplit(" ", 1)[0],
        "description": "",
        "tags": [],
        "visual_mode": visual_mode if visual_mode in ("pictures", "stickman") else "pictures",
        "scenes": scenes,
    }


if __name__ == "__main__":
    import os

    # Same env-var convention as segment_script.py (SCRIPT_TEXT), so the
    # GitHub Actions workflow can pass either a full script or an idea
    # through the same input field depending on input_mode -- the two
    # tools just read it differently.
    env_text = os.environ.get("SCRIPT_TEXT")
    text = env_text if env_text is not None else sys.stdin.read()
    title = os.environ.get("VIDEO_TITLE") or None
    visual_mode = os.environ.get("VIDEO_MODE") or "pictures"
    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    script = idea_to_script(text, title=title, visual_mode=visual_mode)
    if out_path:
        with open(out_path, "w") as f:
            json.dump(script, f, indent=2)
        print(out_path)
    else:
        print(json.dumps(script, indent=2))
