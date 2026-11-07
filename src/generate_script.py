"""
Turns one topic from scripts/topics.json into a full scene-structured script
JSON (scripts/video_<id>.json), ready for build_video.py.

Requires ANTHROPIC_API_KEY (the script-writing step needs a real model to get
the facts right and write a hook that actually lands — a hardcoded template
would either be generic or risk getting incident details wrong, and this
whole project exists to get real results, not filler). Get a key at
console.anthropic.com -> add it as the ANTHROPIC_API_KEY secret in this
repo's GitHub Actions settings (Settings -> Secrets and variables -> Actions).

Series format locked: "How It Actually Broke" — real, documented tech
incidents (outages, breaches, software failures), told as a mystery with a
payoff, in the blueprint/hacker-terminal visual style. Real stakes beat
generic "here's how AI works" explainers for retention, per the research
pass we did before building this (storytelling + specificity + a recurring,
recognizable format are the three levers that actually move completion and
rewatch rate on Shorts).
"""
import json
import os
import sys

TOPICS_PATH = "scripts/topics.json"
OUT_DIR = "scripts"

VALID_VISUALS = [
    "title_card", "bullet_reveal", "icon_sequence", "bar_chart_animate",
    "loop_animation", "data_flow", "reveal_text", "subscribe_animation",
]

SYSTEM_PROMPT = f"""You write scripts for a YouTube Shorts series called "How It Actually Broke" —
60-90 second explainers that take one real, well-documented tech incident
(an outage, breach, or software failure) and explain exactly how it happened,
using only verifiable facts about the incident. No speculation, no invented
dialogue, no invented quotes from real people or companies.

HOOK RULES (the first line is 80% of whether anyone keeps watching):
- Open with a stat, consequence, or irony that creates a genuine curiosity gap —
  never start with "Have you ever wondered..." or "Let's talk about...".
- Good hook patterns: a shocking number stated flat ("$440 million. 45 minutes.
  One software deploy."), a reveal of scale ("One typo took down a fifth of
  the internet."), or a contradiction ("The hackers didn't break any
  encryption. They used the front door.").

STRUCTURE (7-9 scenes, each 15-30 words of narration, second person/direct
address, punchy short sentences, present tense feel even for past events):
  1. id="hook" visual="title_card" — the hook line(s) above
  2. id="setup" visual="bullet_reveal" — what the system/company/product was,
     what it did, why it mattered (so the stakes of it breaking land)
  3-6. id="point1".."point4" (use icon_sequence, bar_chart_animate,
     loop_animation, data_flow across these — vary them) — the actual
     mechanism of the failure, step by step, in the order it really happened
  7. id="payoff" visual="reveal_text" — the root cause stated in one sharp
     sentence, and the real-world consequence/aftermath
  8. id="cta" visual="subscribe_animation" — a one-line tease of a loosely
     related next incident + "follow for the next one"

Also write the upload metadata in the same pass:
- description: 2-4 sentences expanding the hook, factual, plus 6-10 relevant
  hashtags at the end (#Shorts included).
- tags: 10-15 single/short-phrase search tags a viewer searching this
  incident would actually type.

Output ONLY valid JSON matching this exact schema, no prose before or after:
{{
  "topic": "<the incident, plain words>",
  "niche": "tech_incident_explainer",
  "terminal_label": "<a short fake filename like the incident, e.g. crowdstrike_outage.log>",
  "title": "<YouTube title, under 70 chars, states the stakes/number, no clickbait lies>",
  "description": "...",
  "tags": ["...", "..."],
  "scenes": [
    {{"id": "...", "text": "...", "visual": "<one of: {', '.join(VALID_VISUALS)}>", "keywords": ["...", "..."]}}
  ]
}}
"""


def _next_pending_topic():
    with open(TOPICS_PATH) as f:
        data = json.load(f)
    for topic in data["topics"]:
        if topic["status"] == "pending":
            return data, topic
    return data, None


def _mark_done(data, topic_id):
    for topic in data["topics"]:
        if topic["id"] == topic_id:
            topic["status"] = "done"
    with open(TOPICS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def generate_for_topic(topic_title, model=None):
    import anthropic

    model = model or os.environ.get("SCRIPT_MODEL", "claude-sonnet-4-5-20250929")
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Write the script for this incident: {topic_title}"}],
    )
    raw = resp.content[0].text.strip()
    # tolerate accidental markdown fencing
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    script = json.loads(raw)

    # sanity-check visuals so motion.py never chokes on a bad value
    for scene in script["scenes"]:
        if scene["visual"] not in VALID_VISUALS:
            scene["visual"] = "bullet_reveal"

    return script


def run():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY is not set. Get a key at console.anthropic.com and add it as\n"
            "a secret (locally: export ANTHROPIC_API_KEY=... ; in GitHub Actions: repo Settings\n"
            "-> Secrets and variables -> Actions -> New repository secret)."
        )

    data, topic = _next_pending_topic()
    if topic is None:
        sys.exit("No pending topics left in scripts/topics.json — add more.")

    print(f"Generating script for: {topic['title']}")
    script = generate_for_topic(topic["title"])

    out_path = os.path.join(OUT_DIR, f"video_{topic['id']}.json")
    with open(out_path, "w") as f:
        json.dump(script, f, indent=2)

    _mark_done(data, topic["id"])
    print(f"Wrote {out_path}")
    print(out_path)  # last line, easy to capture in CI: `OUT=$(python src/generate_script.py | tail -1)`
    return out_path


if __name__ == "__main__":
    run()
