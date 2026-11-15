"""
GRACE's "turbo" engine: stock footage matched to the script, burned-in
subtitles, background music, 9:16 or 16:9, and optional LLM script writing.

The functions that do this live in src/turbo/ -- copied from
MoneyPrinterTurbo (https://github.com/harry0703/MoneyPrinterTurbo, MIT,
copyright Harry; see src/turbo/LICENSE) and now part of this repo. This
file is GRACE's side of it: it works out keys, narration and footage search
terms, calls those functions directly, and hands the finished MP4 to the
same upload + history steps the classic engine uses.

What it does, in order:
  1. works out which keys are available (stock footage + optional LLM)
  2. writes the turbo package's config file from them
  3. works out the narration:
       input_mode "script"/"idea" -> scripts/manual_video.json already
           exists (segment_script.py / director.py wrote it); its scene
           texts are the narration, word for word
       input_mode "ai" -> the LLM writes the script from the topic
  4. picks footage search terms (LLM if there is one, else a rule-based
     mapping from GRACE's own keyword tags -- so a pasted script needs no
     LLM key at all)
  5. generates GRACE's own ambient music track for the background
  6. runs the build, copies the result to output/, writes metadata

Env (all set by manual-video.yml):
  SCRIPT_TEXT, VIDEO_TITLE, INPUT_MODE, VIDEO_ASPECT
  PEXELS_API_KEY, PIXABAY_API_KEY           (at least one is required)
  GROQ_API_KEY, GEMINI_API_KEY              (optional; required for "ai")
  HOST ("on"/"off"), HOST_NAME               (host character; default on, "robot")
  TURBO_LLM_MODEL, TURBO_VOICE, TURBO_SUBTITLE_MODE, TURBO_BGM_VOLUME (optional)
"""
import json
import os
import re
import shutil
import sys
import uuid

from icons import _KEYWORD_ICONS, brand_tags
from music import generate_ambient_wav
import host_overlay

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUTPUT_DIR = os.path.join(ROOT, "output")
RESULT_PATH = os.path.join(ROOT, "scripts", "last_result.json")
# Working folder for the turbo package: its config file, downloaded footage
# and per-build task files. Recreated every CI run, never committed.
RUNTIME_DIR = os.path.join(ROOT, "turbo_runtime")
ASSETS_DIR = os.path.join(HERE, "turbo", "_assets")

# Same voice the classic engine is locked to (see tts.py) -- one channel,
# one voice. MoneyPrinterTurbo wants the gender suffix on Edge voice ids.
DEFAULT_VOICE = "en-US-AndrewNeural-Male"

# GRACE keyword tag -> a stock-footage search phrase. Used only when there
# is no LLM key to write search terms; keeps footage on the channel's
# subject (servers, code, breaches) instead of generic scenery.
TAG_TERMS = {
    "plane": "airport terminal",
    "bank": "bank building",
    "hospital": "hospital corridor",
    "server": "server room",
    "laptop": "programmer laptop",
    "phone": "smartphone screen",
    "lock": "hacker computer",
    "shield": "cyber security",
    "globe": "network cables",
    "warning": "error screen",
    "person": "office workers",
}
FALLBACK_TERMS = ["data center", "programming code", "computer screen", "technology"]

# Extra direction for the LLM script writer so auto-written scripts keep the
# series' angle. Only used in "ai" mode.
SERIES_PROMPT = (
    "This is for the YouTube series 'How It Actually Broke': real, documented "
    "tech incidents (outages, breaches, software failures) explained plainly. "
    "Open with a one-sentence hook stating what broke and the scale of it. "
    "Then explain what actually caused it, step by step, in short spoken "
    "sentences. End with the lesson in one line. Use only facts that are "
    "publicly documented; if a detail is uncertain, leave it out. No headings, "
    "no stage directions, no emojis. About 150 to 190 words."
)


class TurboError(Exception):
    pass


def _pick_sources():
    if os.environ.get("PEXELS_API_KEY", "").strip():
        source = "pexels"
    elif os.environ.get("PIXABAY_API_KEY", "").strip():
        source = "pixabay"
    else:
        raise TurboError(
            "No stock-footage key set. Open GRACE > create > keys and add a "
            "free Pixabay key (pixabay.com/api/docs) or Pexels key (pexels.com/api), "
            "then try again."
        )
    if os.environ.get("GROQ_API_KEY", "").strip():
        llm = ("groq", os.environ["GROQ_API_KEY"].strip())
    elif os.environ.get("GEMINI_API_KEY", "").strip():
        llm = ("gemini", os.environ["GEMINI_API_KEY"].strip())
    else:
        llm = None
    return source, llm


def rule_based_terms(text, limit=8):
    """Footage search terms without an LLM: one phrase per GRACE keyword
    category the script actually mentions, in the order they first appear,
    padded with channel-wide defaults so there are always enough clips."""
    low = text.lower()
    hits = []
    for pattern, tag in _KEYWORD_ICONS:
        m = re.search(pattern, low)
        if m and tag in TAG_TERMS:
            hits.append((m.start(), TAG_TERMS[tag]))
    terms = [t for _, t in sorted(hits)]
    for t in FALLBACK_TERMS:
        if len(terms) >= limit:
            break
        if t not in terms:
            terms.append(t)
    return terms[:limit]


def _narration_from_script_json(path):
    with open(path) as f:
        script = json.load(f)
    lines = [s["text"].strip() for s in script.get("scenes", []) if s.get("text", "").strip()]
    if not lines:
        raise TurboError("The script came out empty after cleaning -- nothing to narrate.")
    return script, "\n".join(lines)


def _write_config(source, llm):
    """Writes the turbo package's config.toml for this run. Starts from the
    bundled example (so every setting it expects exists with its default)
    and overrides only what GRACE needs. Must run BEFORE `import turbo`:
    the package reads this file once, at import time."""
    import toml

    with open(os.path.join(ASSETS_DIR, "config.example.toml"), encoding="utf-8") as f:
        cfg = toml.load(f)

    def keys(env_name):
        return [k.strip() for k in os.environ.get(env_name, "").split(",") if k.strip()]

    cfg["log_level"] = "INFO"
    app = cfg.setdefault("app", {})
    app["pexels_api_keys"] = keys("PEXELS_API_KEY")
    app["pixabay_api_keys"] = keys("PIXABAY_API_KEY")
    app["video_source"] = source
    app["subtitle_provider"] = "edge"
    if llm:
        provider, key = llm
        app["llm_provider"] = provider
        app[f"{provider}_api_key"] = key
        model = (os.environ.get("TURBO_LLM_MODEL") or "").strip()
        if model:
            app[f"{provider}_model_name"] = model

    os.makedirs(RUNTIME_DIR, mode=0o700, exist_ok=True)
    path = os.path.join(RUNTIME_DIR, "config.toml")
    with open(path, "w", encoding="utf-8") as f:
        toml.dump(cfg, f)
    os.chmod(path, 0o600)


def _tags_from(terms, text):
    tags = []
    for t in list(terms or []) + brand_tags(text):
        t = str(t).strip().lower()
        if t and t not in tags:
            tags.append(t)
    return tags[:15]


def build(script_json_path):
    input_mode = (os.environ.get("INPUT_MODE") or "script").strip()
    aspect = os.environ.get("VIDEO_ASPECT") or "9:16"
    if aspect not in ("9:16", "16:9", "1:1"):
        aspect = "9:16"
    title = (os.environ.get("VIDEO_TITLE") or "").strip()

    source, llm = _pick_sources()

    # The host character (assets/host/<name>/) presents over the footage.
    # On unless switched off, and only if that host's clips actually exist.
    host_name = (os.environ.get("HOST_NAME") or "robot").strip()
    use_host = (os.environ.get("HOST") or "on").strip() != "off" and os.path.isfile(
        os.path.join(host_overlay.HOSTS_DIR, host_name, "manifest.json"))

    params = {
        "video_source": source,
        "video_aspect": aspect,
        "video_language": "en-US",
        "video_count": 1,
        "voice_name": os.environ.get("TURBO_VOICE") or DEFAULT_VOICE,
        "subtitle_enabled": True,
        "font_name": "BeVietnamPro-Bold.ttf",
        "font_size": 58,
        # 70% down the frame: clear of the Shorts title/buttons overlay that
        # covers the very bottom. With the host on screen the subtitles move
        # up to 36%, above the host's head, so neither covers the other.
        "subtitle_position": "custom",
        "custom_position": 36.0 if use_host else 70.0,
        "subtitle_display_mode": os.environ.get("TURBO_SUBTITLE_MODE") or "sentence",
        "text_fore_color": "#FFFFFF",
        "stroke_color": "#000000",
        "stroke_width": 2.0,
        "video_concat_mode": "sequential",
        "match_materials_to_script": True,
        "video_clip_duration": 4,
    }
    script_meta = None
    narration = ""

    if input_mode == "ai":
        if not llm:
            raise TurboError(
                "Writing the script with AI needs an LLM key. Open GRACE > create > "
                "keys and add a free Groq key (console.groq.com/keys), or paste a "
                "full script instead."
            )
        raw = (os.environ.get("SCRIPT_TEXT") or "").strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        if not lines:
            raise TurboError("No topic given.")
        subject, facts = lines[0], lines[1:]
        prompt = SERIES_PROMPT
        if facts:
            prompt += " Build the script around these facts: " + " | ".join(facts)
        params.update(video_subject=subject, video_script="", paragraph_number=3, video_script_prompt=prompt)
        title = title or subject
    else:
        script_meta, narration = _narration_from_script_json(script_json_path)
        title = title or script_meta.get("title") or narration[:70]
        params.update(video_subject=title, video_script=narration)
        if not llm:
            params["video_terms"] = rule_based_terms(narration)

    # The turbo package reads its config and working folder at import time,
    # so both have to be in place before the imports below.
    _write_config(source, llm)
    os.environ["MPT_HOME"] = RUNTIME_DIR
    from turbo.models.schema import VideoParams
    from turbo.services import task as turbo_task
    from turbo.utils import utils as turbo_utils

    # GRACE's own code-generated ambient track (music.py) as the background
    # music, looped to the video's length by the builder.
    bgm_volume = float(os.environ.get("TURBO_BGM_VOLUME") or 0.25)
    try:
        bgm_name = "grace_ambient.wav"
        generate_ambient_wav(os.path.join(turbo_utils.song_dir(), bgm_name), 60.0)
        params.update(bgm_type="custom", bgm_file=bgm_name, bgm_volume=bgm_volume)
    except Exception as e:
        print(f"[turbo] music generation failed ({e.__class__.__name__}: {e}), continuing without it")
        params.update(bgm_type="")

    print(f"[turbo] source={source} llm={llm[0] if llm else 'none (rule-based terms)'} "
          f"mode={input_mode} aspect={aspect}")
    task_id = str(uuid.uuid4())
    result = turbo_task.start(
        task_id=task_id,
        params=VideoParams(**params),
        stop_at="video",
        allow_server_file_input=True,
    ) or {}
    if not result.get("videos") or result.get("failed_stage"):
        stage = result.get("failed_stage") or "unknown"
        err = result.get("error") or "see the run log for details"
        hint = ""
        if stage == "materials":
            hint = " (no usable footage came back -- check the Pexels key, or try different wording)"
        elif stage in ("script", "terms"):
            hint = " (the LLM call failed -- check the LLM key or its free-tier limit)"
        elif stage == "audio":
            hint = " (voice generation failed -- usually a temporary Edge TTS hiccup; retry)"
        raise TurboError(f"Turbo build failed at '{stage}': {err}{hint}")

    video = result["videos"][0]
    if not os.path.isfile(video):
        video = os.path.join(RUNTIME_DIR, video)
    if not os.path.isfile(video):
        raise TurboError(f"Build reported success but no video file was found ({result['videos'][0]}).")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_name = os.path.splitext(os.path.basename(script_json_path))[0]
    final_path = os.path.join(OUTPUT_DIR, f"{out_name}.mp4")
    shutil.copyfile(video, final_path)

    if use_host:
        # Not allowed to sink the build: if anything about the host fails,
        # the video without it is still a finished video.
        hosted = final_path + ".host.mp4"
        try:
            host_overlay.add_host(final_path, result.get("subtitle_path") or "", hosted, host=host_name)
            os.replace(hosted, final_path)
        except Exception as e:
            print(f"[turbo] host overlay failed ({e.__class__.__name__}: {e}); keeping the video without the host")
            if os.path.exists(hosted):
                os.remove(hosted)

    narration = str(result.get("script") or narration).strip()
    terms = result.get("terms") or []
    if isinstance(terms, str):
        terms = [t.strip() for t in terms.split(",")]
    meta = script_meta or {"niche": "turbo", "scenes": [{"id": "full", "text": narration}]}
    meta["title"] = title[:100]
    meta.setdefault("topic", title)
    meta["engine"] = "turbo"
    if not meta.get("description"):
        first = re.split(r"(?<=[.!?])\s+", narration)[0] if narration else title
        meta["description"] = first[:300]
    if not meta.get("tags"):
        meta["tags"] = _tags_from(terms, narration)
    with open(script_json_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nDone: {final_path}")
    return final_path


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "scripts", "manual_video.json")
    try:
        build(path)
    except TurboError as e:
        os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
        with open(RESULT_PATH, "w") as f:
            json.dump({"error": str(e)[:500]}, f)
        print(f"\n[turbo] {e}", file=sys.stderr)
        sys.exit(1)
