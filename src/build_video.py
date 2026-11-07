"""
Full pipeline: script.json -> finished MP4.

For each scene: TTS -> word timing -> motion graphics render -> mux audio+video.
Then concatenate all scenes into the final vertical explainer video.
"""
import json
import os
import subprocess
import sys

from script_tools import load_script
from tts import generate as tts_generate
from motion import render_scene

# Anchored to the repo root (not the shell's cwd) because the GitHub Actions
# workflow does `cd src` before each step — with a plain relative "output",
# this step would write to src/output/ while the upload step (also `cd src`,
# then ../output/...) and the artifact-backup step (repo root, output/...)
# would both look in a different, empty directory.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(_BASE_DIR, "..", "audio")
OUTPUT_DIR = os.path.join(_BASE_DIR, "..", "output")


def build(script_path, out_name=None, tts_engine=None, theme=None):
    script = load_script(script_path)
    out_name = out_name or os.path.splitext(os.path.basename(script_path))[0]

    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    scene_clips = []
    total_duration = 0.0

    for scene in script["scenes"]:
        sid = scene["id"]
        print(f"[{sid}] generating voiceover...")
        audio_path = os.path.join(AUDIO_DIR, f"{out_name}_{sid}.mp3")
        timing_path = os.path.join(AUDIO_DIR, f"{out_name}_{sid}_timing.json")
        boundaries = tts_generate(scene["text"], audio_path, timing_path, tts_engine)

        print(f"[{sid}] rendering motion graphics...")
        silent_video = os.path.join(OUTPUT_DIR, f"{out_name}_{sid}_silent.mp4")
        _, duration = render_scene(scene, boundaries, silent_video, theme=theme)
        total_duration += duration

        print(f"[{sid}] muxing audio + video...")
        final_scene = os.path.join(OUTPUT_DIR, f"{out_name}_{sid}.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", silent_video, "-i", audio_path,
            "-c:v", "copy", "-c:a", "aac", "-shortest", final_scene,
        ], check=True, capture_output=True)
        scene_clips.append(final_scene)
        os.remove(silent_video)

    # concat
    concat_list = os.path.join(OUTPUT_DIR, f"{out_name}_concat.txt")
    with open(concat_list, "w") as f:
        for clip in scene_clips:
            f.write(f"file '{os.path.abspath(clip)}'\n")

    final_path = os.path.join(OUTPUT_DIR, f"{out_name}.mp4")
    print("Concatenating scenes into final video...")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", final_path,
    ], check=True, capture_output=True)

    # cleanup intermediate scene files
    for clip in scene_clips:
        os.remove(clip)
    os.remove(concat_list)

    print(f"\nDone: {final_path}  (~{total_duration:.1f}s)")
    return final_path


if __name__ == "__main__":
    script_path = sys.argv[1] if len(sys.argv) > 1 else "scripts/video_001.json"
    engine = sys.argv[2] if len(sys.argv) > 2 else None  # None = auto (ElevenLabs > edge-tts > espeak)
    theme = sys.argv[3] if len(sys.argv) > 3 else None   # None = terminal (default)
    build(script_path, tts_engine=engine, theme=theme)
