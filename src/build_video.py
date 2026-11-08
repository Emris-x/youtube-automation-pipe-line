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
from music import generate_ambient_wav

# Anchored to the repo root (not the shell's cwd) because the GitHub Actions
# workflow does `cd src` before each step — with a plain relative "output",
# this step would write to src/output/ while the upload step (also `cd src`,
# then ../output/...) and the artifact-backup step (repo root, output/...)
# would both look in a different, empty directory.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(_BASE_DIR, "..", "audio")
OUTPUT_DIR = os.path.join(_BASE_DIR, "..", "output")

MUSIC = os.environ.get("VIDEO_MUSIC", "on") != "off"

# Sidechain-ducked under the narration: music stays quiet (threshold near
# the noise floor) and compresses hard+fast whenever the voice is present,
# releasing slowly back up in the gaps between lines. The voice stream is
# split into two copies (asplit) because it's consumed twice -- once as the
# sidechain control signal, once as the actual thing we mix back in --
# and ffmpeg filtergraphs don't allow reusing one link label as two inputs
# without an explicit split.
_MUSIC_FILTER = (
    "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[voice1][voice2];"
    "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.55[mus];"
    "[mus][voice1]sidechaincompress=threshold=0.04:ratio=10:attack=5:release=400[duck];"
    "[voice2][duck]amix=inputs=2:duration=first:dropout_transition=0[aout]"
)


def build(script_path, out_name=None, tts_engine=None, theme=None):
    script = load_script(script_path)
    out_name = out_name or os.path.splitext(os.path.basename(script_path))[0]
    visual_mode = script.get("visual_mode", "pictures")

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

        expected_words = len(scene["text"].split())
        got_words = len(boundaries)
        total_duration_check = boundaries[-1]["offset_s"] + boundaries[-1]["duration_s"] if boundaries else 0.0
        if not boundaries:
            print(f"[{sid}] WARNING: no word timing came back at all — captions will be skipped and this clip will fall back to a flat 3s, likely cutting the audio short")
        elif got_words < expected_words * 0.85:
            print(f"[{sid}] WARNING: only {got_words}/{expected_words} words of the script got timing ({total_duration_check:.1f}s) — the clip may cut off early")
        else:
            print(f"[{sid}] {got_words}/{expected_words} words captured, {total_duration_check:.1f}s")

        print(f"[{sid}] rendering motion graphics...")
        silent_video = os.path.join(OUTPUT_DIR, f"{out_name}_{sid}_silent.mp4")
        _, duration = render_scene(scene, boundaries, silent_video, theme=theme, mode=visual_mode)
        total_duration += duration

        print(f"[{sid}] muxing audio + video...")
        final_scene = os.path.join(OUTPUT_DIR, f"{out_name}_{sid}.mp4")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", silent_video, "-i", audio_path,
                "-c:v", "copy", "-c:a", "aac", "-shortest", final_scene,
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"[{sid}] ffmpeg mux failed (exit {e.returncode}):\n{e.stderr.decode(errors='replace')}")
            raise
        scene_clips.append(final_scene)
        os.remove(silent_video)

    # concat
    concat_list = os.path.join(OUTPUT_DIR, f"{out_name}_concat.txt")
    with open(concat_list, "w") as f:
        for clip in scene_clips:
            f.write(f"file '{os.path.abspath(clip)}'\n")

    final_path = os.path.join(OUTPUT_DIR, f"{out_name}.mp4")
    print("Concatenating scenes into final video...")

    music_path = None
    if MUSIC:
        music_path = os.path.join(AUDIO_DIR, f"{out_name}_music.wav")
        try:
            generate_ambient_wav(music_path, total_duration + 1.0)
            print("[music] generated background ambient track")
        except Exception as e:
            print(f"[music] generation failed ({e.__class__.__name__}: {e}), continuing without it")
            music_path = None

    try:
        if music_path:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_list,
                "-i", music_path,
                "-filter_complex", _MUSIC_FILTER,
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", "-shortest", final_path,
            ], check=True, capture_output=True)
        else:
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
                "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", final_path,
            ], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"[concat] ffmpeg failed (exit {e.returncode}):\n{e.stderr.decode(errors='replace')}")
        if music_path:
            print("[concat] retrying without background music in case the sidechain filter was the problem...")
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
                    "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", final_path,
                ], check=True, capture_output=True)
            except subprocess.CalledProcessError as e2:
                print(f"[concat] plain concat also failed (exit {e2.returncode}):\n{e2.stderr.decode(errors='replace')}")
                raise
        else:
            raise

    # cleanup intermediate scene files
    for clip in scene_clips:
        os.remove(clip)
    os.remove(concat_list)
    if music_path and os.path.exists(music_path):
        os.remove(music_path)

    print(f"\nDone: {final_path}  (~{total_duration:.1f}s)")
    return final_path


if __name__ == "__main__":
    script_path = sys.argv[1] if len(sys.argv) > 1 else "scripts/video_001.json"
    engine = sys.argv[2] if len(sys.argv) > 2 else None  # None = auto (ElevenLabs > edge-tts > espeak)
    theme = sys.argv[3] if len(sys.argv) > 3 else None   # None = terminal (default)
    build(script_path, tts_engine=engine, theme=theme)
