"""
Scheduled queue dispatcher for the "Scripts" tab: pops one script off
data/scripts_queue.json when the configured schedule (data/schedule.json)
says it's due, and writes it out in exactly the same scene-JSON shape
segment_script.py produces -- so the rest of the pipeline (build_video.py,
upload.py) runs through the identical, already-battle-tested code path the
manual "./create_video" button uses. No separate code path to drift out of
sync with (see Finding 1 in the V2 audit -- two divergent upload paths was
already a real bug once; this doesn't repeat that mistake).

Two invocations in one GitHub Actions job (scripts-queue.yml):
  1. `python dispatch_queue.py <out_script_path>` -- runs first. Decides
     whether a script is due; if so, pops the oldest queued one, marks it
     "building" in the queue (so an overlapping tick can't double-pop it),
     writes the segmented script JSON to out_script_path, and sets the
     `due` / `item_id` GitHub Actions step outputs for later steps' `if:`
     conditions to key off.
  2. `python dispatch_queue.py --finalize` -- runs last (if: always()),
     after build+upload were attempted. Reads BUILD_OUTCOME/UPLOAD_OUTCOME/
     RUN_URL env vars the workflow sets (same convention log_result.py
     uses for the manual workflow) plus scripts/last_result.json (written
     by upload.py) for the error/video_url, and updates both the queue
     entry and data/history.json.
"""
import json
import os
import sys
from datetime import datetime, timezone

import segment_script
import log_result

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "..", "data", "scripts_queue.json")
SCHEDULE_PATH = os.path.join(HERE, "..", "data", "schedule.json")
STATE_PATH = os.path.join(HERE, "..", "scripts", "queue_dispatch_state.json")
RESULT_PATH = os.path.join(HERE, "..", "scripts", "last_result.json")

DEFAULT_SCHEDULE = {"enabled": False, "interval_hours": 24, "last_dispatch_at": None}


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _set_output(name, value):
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"[dispatch_queue] (no GITHUB_OUTPUT set) {name}={value}")


def _pop(out_script_path):
    schedule = {**DEFAULT_SCHEDULE, **_load(SCHEDULE_PATH, {})}
    enabled = bool(schedule.get("enabled"))
    interval_hours = float(schedule.get("interval_hours") or 24)
    last_at = schedule.get("last_dispatch_at")

    queue = _load(QUEUE_PATH, {"scripts": []})
    scripts = queue.get("scripts") or []
    queued = [s for s in scripts if s.get("status") == "queued"]

    if not enabled:
        print("[dispatch_queue] schedule is off -- nothing to do.")
        _set_output("due", "false")
        return
    if not queued:
        print("[dispatch_queue] queue is empty -- nothing to do.")
        _set_output("due", "false")
        return
    if last_at:
        try:
            elapsed_s = (datetime.now(timezone.utc) - datetime.fromisoformat(last_at)).total_seconds()
        except ValueError:
            elapsed_s = interval_hours * 3600  # unparsable timestamp -> treat as due
        if elapsed_s < interval_hours * 3600:
            remaining_h = (interval_hours * 3600 - elapsed_s) / 3600
            print(f"[dispatch_queue] not due yet -- {remaining_h:.1f}h left on a {interval_hours}h schedule.")
            _set_output("due", "false")
            return

    item = queued[0]  # FIFO -- oldest queued script goes first
    item["status"] = "building"
    item["dispatched_at"] = datetime.now(timezone.utc).isoformat()
    _save(QUEUE_PATH, queue)

    schedule["last_dispatch_at"] = datetime.now(timezone.utc).isoformat()
    _save(SCHEDULE_PATH, schedule)

    script = segment_script.text_to_script(item["script_text"], title=item.get("title"))
    _save(out_script_path, script)
    _save(STATE_PATH, {"item_id": item["id"], "title": script["title"]})

    _set_output("due", "true")
    _set_output("item_id", item["id"])
    print(f"[dispatch_queue] popped '{item['id']}' ({script['title']}) -- {len(queued) - 1} left queued.")


def _finalize():
    state = _load(STATE_PATH, None)
    if not state:
        print("[dispatch_queue] nothing was dispatched this run -- skipping finalize.")
        return

    build_ok = os.environ.get("BUILD_OUTCOME") == "success"
    upload_ok = os.environ.get("UPLOAD_OUTCOME") == "success"
    result = _load(RESULT_PATH, {})

    if upload_ok:
        queue_status, failed_step, error, video_url = "created", None, None, result.get("video_url")
    elif not build_ok:
        queue_status, failed_step, error, video_url = "failed", "build", None, None
    else:
        queue_status, failed_step, error, video_url = "failed", "upload", result.get("error"), None

    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = os.environ.get("RUN_URL", "")

    queue = _load(QUEUE_PATH, {"scripts": []})
    for s in queue.get("scripts") or []:
        if s.get("id") == state["item_id"]:
            s["status"] = queue_status
            s["run_id"] = run_id
            s["run_url"] = run_url
            s["video_url"] = video_url
            s["error"] = error
            break
    _save(QUEUE_PATH, queue)

    log_result.append_history_entry({
        "run_id": run_id,
        "run_url": run_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": state.get("title") or "Untitled",
        "status": "uploaded" if upload_ok else "failed",
        "failed_step": failed_step,
        "error": error,
        "video_url": video_url,
        "source": "scripts-queue",
    })

    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)

    print(f"[dispatch_queue] finalized '{state['item_id']}' as {queue_status}.")


if __name__ == "__main__":
    if "--finalize" in sys.argv:
        _finalize()
    else:
        out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "scripts", "manual_video.json")
        _pop(out_path)
