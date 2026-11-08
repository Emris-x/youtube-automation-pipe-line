"""
One-shot orchestrator: pulls the next pending topic, writes the script,
builds the video, uploads it. This is what the GitHub Actions workflow
calls — the whole "post one video" job in one command.

Unlike manual-video.yml (three separate workflow steps, each with its own
`id:` and continue-on-error, so log_result.py can read SEGMENT_OUTCOME /
BUILD_OUTCOME / UPLOAD_OUTCOME as env vars after the fact), this runs all
three stages as one Python process. So this writes its own history entry
directly via log_result.append_history_entry() in a finally block, instead
of relying on a separate logging step the way the manual workflow does --
previously this path logged nothing at all, so a scheduled run was
invisible in GRACE's history whether it succeeded or failed.

Usage: python src/run_pipeline.py [--no-upload]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import generate_script
import build_video
import upload as upload_mod
import log_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-upload", action="store_true", help="Build the video but skip the YouTube upload step")
    args = parser.parse_args()

    title = "Untitled"
    status, failed_step, error, video_url = "failed", "segment", None, None

    try:
        print("=== Step 1/3: generating script ===")
        script_path = generate_script.run()
        with open(script_path) as f:
            script = json.load(f)
        title = script.get("title") or script.get("chosen_title") or title
        failed_step = "build"

        print("\n=== Step 2/3: building video ===")
        video_path = build_video.build(script_path)
        failed_step = "upload"

        print("\n=== Step 3/3: uploading ===")
        if args.no_upload:
            print("Skipped (--no-upload).")
            status, failed_step = "built", None
        else:
            video_id = upload_mod.upload_video(video_path, script)
            video_url = f"https://youtube.com/watch?v={video_id}"
            status, failed_step = "uploaded", None
            print(f"Live at: {video_url}")

        print(f"\nDone. Video: {video_path}  Script: {script_path}")
    except Exception as e:
        error = str(e)[:500]
        print(f"\nFailed at stage '{failed_step}': {error}", file=sys.stderr)
        raise
    finally:
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        log_result.append_history_entry({
            "run_id": run_id,
            "run_url": f"https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "status": status,
            "failed_step": failed_step,
            "error": error,
            "video_url": video_url,
            "source": "daily-video.yml",
        })


if __name__ == "__main__":
    main()
