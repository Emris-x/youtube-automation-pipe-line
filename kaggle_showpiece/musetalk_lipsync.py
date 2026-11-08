"""
EXPERIMENTAL -- NOT YET VERIFIED ON A REAL GPU. See README.md in this folder
before running this.

A drop-in alternative to ai-influencer-studio's pipeline.py `lipsync()` step,
swapping TMElyralab/MuseTalk (MIT, commercially clear for both code and
weights) in place of LatentSync. Verified against MuseTalk's real
scripts/inference.py argument list and config format (read directly from
the cloned repo), not guessed from a README summary -- but never actually
run, because I have no GPU here.

MuseTalk's own benchmark: an 8-second clip in ~5 minutes on a 4GB-VRAM
laptop GPU (fp16) -- weaker hardware than a free Kaggle T4. LatentSync
(what the studio currently uses) needs roughly 8-24 minutes for the same
8 seconds per its own "1-3 min/sec" figure. If that benchmark holds on a
T4 too, this is a real multi-times speedup on the lip-sync step alone.
Independent reviews suggest MuseTalk's visual fidelity is a touch softer
than LatentSync's -- a real trade-off, not a free upgrade.

Usage (matches pipeline.py's lipsync() generator signature so it can be
swapped in with one line -- see README.md):

  from musetalk_lipsync import lipsync_musetalk
  for log_text, result_path in lipsync_musetalk(video_dir, take_paths, keep_seconds):
      ...
"""

import shutil
import subprocess
from pathlib import Path

import yaml

from media import duration, fit_to_audio  # reuses the studio's own helper, unchanged

MUSETALK = Path("/tmp/MuseTalk")


def _stream(cmd, cwd=None):
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        if line:
            tail = (tail + [line])[-15:]
            yield line
    if p.wait():
        raise RuntimeError(f"step failed (exit {p.returncode}). Last output:\n" + "\n".join(tail))


def _ensure_musetalk():
    if (MUSETALK / ".ready").exists():
        return
    yield "Installing MuseTalk (first time only)..."
    for line in _stream(
        f"rm -rf {MUSETALK} && git clone -q https://github.com/TMElyralab/MuseTalk.git {MUSETALK} && "
        f"cd {MUSETALK} && uv venv -q -p 3.10 .venv && uv pip install -q -p .venv -r requirements.txt && "
        # download_weights.sh pulls the UNet, VAE and Whisper checkpoints into
        # models/ -- same convention as the studio's own LatentSync installer.
        f"bash download_weights.sh"
    ):
        yield line
    (MUSETALK / ".ready").touch()


def lipsync_musetalk(video_dir, take_paths, keep_seconds, fp16=True, version="v15"):
    """Generator yielding (log_line, result_path_or_None) -- same shape as
    pipeline.py's lipsync(), so it's a one-line swap in pipeline.py:
        from musetalk_lipsync import lipsync_musetalk as lipsync
    instead of the module's own lipsync function, IF this has actually been
    verified to work first. Do not wire this in blind."""
    vd = Path(video_dir)
    if not take_paths:
        raise RuntimeError("Pick at least one take.")

    yield "Chaining the takes to the length of the voice...", None
    keep = {p: keep_seconds for p in take_paths} if keep_seconds else None
    fit_to_audio(vd / "voice.wav", take_paths, vd / "lipsync_input.mp4", vd / "lipsync_voice.wav", keep=keep)

    for line in _ensure_musetalk():
        yield line, None

    # MuseTalk's inference.py takes a YAML of {task_name: {video_path,
    # audio_path}} rather than CLI flags per-file -- write a single-task
    # config pointing at the files fit_to_audio just produced.
    task_cfg = vd / "musetalk_task.yaml"
    task_cfg.write_text(yaml.dump({
        "grace_task": {
            "video_path": str((vd / "lipsync_input.mp4").resolve()),
            "audio_path": str((vd / "lipsync_voice.wav").resolve()),
        }
    }))

    result_dir = vd / "musetalk_out"
    result_dir.mkdir(exist_ok=True)
    model_dir = MUSETALK / ("models/musetalkV15" if version == "v15" else "models/musetalk")
    unet_name = "unet.pth" if version == "v15" else "pytorch_model.bin"

    yield f"Lip-syncing {duration(vd / 'lipsync_voice.wav'):.0f}s with MuseTalk...", None
    cmd = (
        f"{MUSETALK}/.venv/bin/python scripts/inference.py "
        f'--inference_config "{task_cfg.resolve()}" --result_dir "{result_dir.resolve()}" '
        f"--unet_model_path {model_dir}/{unet_name} --unet_config {model_dir}/musetalk.json "
        f"--whisper_dir {MUSETALK}/models/whisper --version {version} --fps 24"
        + (" --use_float16" if fp16 else "")
    )
    for line in _stream(cmd, cwd=MUSETALK):
        yield line, None

    # inference.py names its output after the task key -- find it rather
    # than assume an exact filename, since that convention isn't guaranteed
    # to be stable across MuseTalk versions.
    outputs = list(result_dir.glob("**/grace_task*.mp4"))
    if not outputs:
        raise RuntimeError(f"MuseTalk finished but no output video was found under {result_dir}")
    out = vd / "lipsync.mp4"
    shutil.copy(outputs[0], out)

    for f in ("lipsync_input.mp4", "lipsync_voice.wav"):
        (vd / f).unlink(missing_ok=True)
    yield "Lip-sync done.", str(out)
