"""
Appends one entry to data/history.json describing how this GRACE run went —
so GRACE can show a History list instead of going silent after a video is
requested. Run by manual-video.yml as an `if: always()` step, after every
attempt, success or failure.

Reads outcomes from env vars the workflow sets (SEGMENT_OUTCOME,
BUILD_OUTCOME, UPLOAD_OUTCOME), plus whatever scripts/manual_video.json and
scripts/last_result.json happen to contain from this same run.
"""
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(HERE, "..", "data", "history.json")
METADATA_PATH = os.path.join(HERE, "..", "scripts", "manual_video.json")
RESULT_PATH = os.path.join(HERE, "..", "scripts", "last_result.json")

MAX_ENTRIES = 100


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def append_history_entry(entry):
    """Prepend one entry to data/history.json. Shared by both callers:
    manual-video.yml invokes this file's CLI (main(), below) after each of
    its separate workflow steps; run_pipeline.py (the daily/scheduled path,
    which runs generate->build->upload as one Python process rather than
    separate steps with their own outcome tracking) calls this directly so
    scheduled runs show up in GRACE's history too -- they didn't before."""
    history = _load_json(HISTORY_PATH, [])
    history.insert(0, entry)
    history = history[:MAX_ENTRIES]

    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def main():
    segment_ok = os.environ.get("SEGMENT_OUTCOME") == "success"
    build_ok = os.environ.get("BUILD_OUTCOME") == "success"
    upload_ok = os.environ.get("UPLOAD_OUTCOME") == "success"

    error = None
    if upload_ok:
        status, failed_step = "uploaded", None
    elif not segment_ok:
        status, failed_step = "failed", "segment"
    elif not build_ok:
        status, failed_step = "failed", "build"
    else:
        status, failed_step = "failed", "upload"

    metadata = _load_json(METADATA_PATH, {})
    result = _load_json(RESULT_PATH, {})
    if failed_step == "upload":
        error = result.get("error")

    entry = {
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_url": os.environ.get("RUN_URL", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": metadata.get("title") or os.environ.get("VIDEO_TITLE") or "Untitled",
        "status": status,
        "failed_step": failed_step,
        "error": error,
        "video_url": result.get("video_url") if upload_ok else None,
    }

    append_history_entry(entry)

    print(f"Logged run as {status}" + (f" (failed at: {failed_step})" if failed_step else ""))


if __name__ == "__main__":
    main()
