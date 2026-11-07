"""
One-shot orchestrator: pulls the next pending topic, writes the script,
builds the video, uploads it. This is what the GitHub Actions workflow
calls — the whole "post one video" job in one command.

Usage: python src/run_pipeline.py [--no-upload]
"""
import argparse
import json
import os
import sys

import generate_script
import build_video
import upload as upload_mod


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-upload", action="store_true", help="Build the video but skip the YouTube upload step")
    args = parser.parse_args()

    print("=== Step 1/3: generating script ===")
    script_path = generate_script.run()

    print("\n=== Step 2/3: building video ===")
    video_path = build_video.build(script_path)

    print("\n=== Step 3/3: uploading ===")
    if args.no_upload:
        print("Skipped (--no-upload).")
    else:
        with open(script_path) as f:
            script = json.load(f)
        video_id = upload_mod.upload_video(video_path, script)
        print(f"Live at: https://youtube.com/watch?v={video_id}")

    print(f"\nDone. Video: {video_path}  Script: {script_path}")


if __name__ == "__main__":
    main()
