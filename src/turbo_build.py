"""
GRACE's "turbo" engine: builds the video with MoneyPrinterTurbo
(https://github.com/harry0703/MoneyPrinterTurbo, MIT) instead of GRACE's own
motion-graphics renderer.

MoneyPrinterTurbo is NOT copied into this repo. The workflow checks it out
at a pinned commit next to this one and this file drives its command-line
interface, then hands the finished MP4 back to the exact same upload +
history steps the classic engine uses. So everything after "a video file
exists at output/manual_video.mp4" is unchanged.

What it does, in order:
  1. works out which keys are available (stock footage + optional LLM)
  2. writes MoneyPrinterTurbo's config.toml from them
  3. works out the narration:
       input_mode "script"/"idea" -> scripts/manual_video.json already
           exists (segment_script.py / director.py wrote it); its scene
           texts are the narration, word for word
       input_mode "ai" -> the LLM writes the script from the topic
  4. picks footage search terms (LLM if there is one, else a rule-based
     mapping from GRACE's own keyword tags -- so a pasted script needs no
     LLM key at all)
  5. runs the build, copies the result to output/, writes metadata

Env (all set by manual-video.yml):
  SCRIPT_TEXT, VIDEO_TITLE, INPUT_MODE, VIDEO_ASPECT
  MPT_DIR, MPT_PYTHON
  PEXELS_API_KEY, PIXABAY_API_KEY           (at least one is required)
  GROQ_API_KEY, GEMINI_API_KEY              (optional; required for "ai")
  TURBO_LLM_MODEL, TURBO_VOICE, TURBO_SUBTITLE_MODE, TURBO_BGM_VOLUME (optional)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading

from icons import _KEYWORD_ICONS, brand_tags

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUTPUT_DIR = os.path.join(ROOT, "output")
RESULT_PATH = os.path.join(ROOT, "scripts", "last_result.json")

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


_FAIL_LINE_RE = re.compile(r"CLI task failed: .*?stage=([\w-]+), error=(.*)$")


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
            "free Pexels key (pexels.com/api), then try again."
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


def _first_json_object(stdout):
    """The CLI prints exactly one JSON object on stdout, but tolerate stray
    lines around it rather than fail a finished render on a parse error."""
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _resolve_video(path, mpt_dir, task_id):
    candidates = [path, os.path.join(mpt_dir, path)]
    task_dir = os.path.join(mpt_dir, "storage", "tasks", task_id or "")
    candidates.append(os.path.join(task_dir, os.path.basename(path)))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    if os.path.isdir(task_dir):
        finals = sorted(f for f in os.listdir(task_dir) if f.startswith("final") and f.endswith(".mp4"))
        if finals:
            return os.path.join(task_dir, finals[0])
    raise TurboError(f"Build reported success but no video file was found ({path}).")


def _tags_from(terms, text):
    tags = []
    for t in list(terms or []) + brand_tags(text):
        t = str(t).strip().lower()
        if t and t not in tags:
            tags.append(t)
    return tags[:15]


def build(script_json_path):
    mpt_dir = os.path.abspath(os.environ.get("MPT_DIR") or os.path.join(ROOT, ".mpt"))
    mpt_python = os.environ.get("MPT_PYTHON") or sys.executable
    input_mode = (os.environ.get("INPUT_MODE") or "script").strip()
    aspect = os.environ.get("VIDEO_ASPECT") or "9:16"
    if aspect not in ("9:16", "16:9", "1:1"):
        aspect = "9:16"
    title = (os.environ.get("VIDEO_TITLE") or "").strip()

    source, llm = _pick_sources()

    cfg_env = dict(os.environ, TURBO_VIDEO_SOURCE=source)
    if llm:
        cfg_env["TURBO_LLM_PROVIDER"], cfg_env["TURBO_LLM_KEY"] = llm
    subprocess.run([mpt_python, os.path.join(HERE, "turbo_config.py"), mpt_dir], check=True, env=cfg_env)

    cmd = [mpt_python, "cli.py", "--video-source", source, "--video-aspect", aspect]
    script_meta = None

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
        cmd += ["--video-subject", subject, "--video-language", "en-US",
                "--paragraph-number", "3", "--video-script-prompt", prompt]
        title = title or subject
    else:
        script_meta, narration = _narration_from_script_json(script_json_path)
        title = title or script_meta.get("title") or narration[:70]
        cmd += ["--video-script", narration, "--video-subject", title, "--video-language", "en-US"]
        if not llm:
            cmd += ["--video-terms", ",".join(rule_based_terms(narration))]

    cmd += [
        "--voice-name", os.environ.get("TURBO_VOICE") or DEFAULT_VOICE,
        "--bgm-type", "random",
        "--bgm-volume", os.environ.get("TURBO_BGM_VOLUME") or "0.15",
        "--subtitle-enabled",
        "--font-name", "BeVietnamPro-Bold.ttf",
        "--font-size", "58",
        "--subtitle-position", "custom", "--custom-position", "70",
        "--subtitle-display-mode", os.environ.get("TURBO_SUBTITLE_MODE") or "sentence",
        "--text-fore-color", "#FFFFFF", "--stroke-color", "#000000", "--stroke-width", "2",
        "--video-concat-mode", "sequential",
        "--match-materials-to-script",
        "--video-clip-duration", "4",
        "--video-count", "1",
    ]

    print(f"[turbo] source={source} llm={llm[0] if llm else 'none (rule-based terms)'} "
          f"mode={input_mode} aspect={aspect}")
    # stdout is the machine-readable result. stderr is the build log: pass
    # it through to the Actions log line by line, and remember the CLI's own
    # "task failed ... stage=X, error=Y" line -- on a failure with no video
    # it prints no JSON, so that line is the only place the reason appears.
    proc = subprocess.Popen(cmd, cwd=mpt_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out_chunks = []
    reader = threading.Thread(target=lambda: out_chunks.append(proc.stdout.read()), daemon=True)
    reader.start()
    fail_stage = fail_error = None
    for line in proc.stderr:
        sys.stderr.write(line)
        m = _FAIL_LINE_RE.search(line)
        if m:
            fail_stage, fail_error = m.group(1), m.group(2).strip()
    proc.wait()
    reader.join(timeout=10)
    payload = _first_json_object("".join(out_chunks))
    result = (payload or {}).get("result") or {}
    if proc.returncode != 0 or not result.get("videos"):
        stage = result.get("failed_stage") or fail_stage or "unknown"
        err = result.get("error") or fail_error or "see the run log for details"
        hint = ""
        if stage == "materials":
            hint = " (no usable footage came back -- check the Pexels key, or try different wording)"
        elif stage in ("script", "terms"):
            hint = " (the LLM call failed -- check the LLM key or its free-tier limit)"
        elif stage == "audio":
            hint = " (voice generation failed -- usually a temporary Edge TTS hiccup; retry)"
        raise TurboError(f"MoneyPrinterTurbo failed at '{stage}': {err}{hint}")

    video = _resolve_video(result["videos"][0], mpt_dir, (payload or {}).get("task_id"))
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_name = os.path.splitext(os.path.basename(script_json_path))[0]
    final_path = os.path.join(OUTPUT_DIR, f"{out_name}.mp4")
    shutil.copyfile(video, final_path)

    narration = str(result.get("script") or (narration if script_meta else "")).strip()
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
