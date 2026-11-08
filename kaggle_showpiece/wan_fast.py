"""
EXPERIMENTAL -- NOT YET VERIFIED ON A REAL GPU. See README.md in this folder
before running this.

A modified copy of ai-influencer-studio's wan.py (ItxAsim/ai-influencer-studio,
MIT) pointed at FastVideo's distilled FastWan2.2-TI2V-5B-FullAttn-Diffusers
checkpoint (Apache-2.0) instead of the regular Wan2.2-TI2V-5B weights, with
far fewer inference steps (8 by default instead of 40).

Why: the regular model takes ~20 min per 5s take on a free Kaggle T4. The
distilled model is published and benchmarked by its own authors ONLY for
text-to-video, at 3-4 steps. A public community demo (HuggingFace Space
"KingNish/wan2-2-fast") does feed it an image via diffusers'
WanImageToVideoPipeline and gets video out -- so the code path exists and
runs -- but neither FastVideo's own docs nor that demo confirm the OUTPUT
quality for image-conditioned generation specifically. The distillation
was trained on the text-only path; image conditioning might work fine
(the underlying architecture supports it) or might degrade in ways nobody
has measured, because the model's authors never tested or claimed that use.

This file is a best-effort, careful adaptation, not a verified one. I have
no GPU in the environment I wrote this in, so I could not run it even
once. Treat every number in it (step count, guidance scale, whether 8
steps is enough) as a starting guess to tune once you see real output,
not a tested default.

  python wan_fast.py --image start.png --prompt prompt.txt --negative negative.txt --seeds 42 7 --out takes/
"""

import argparse
import gc
import os
import time
from pathlib import Path

import torch
from diffusers import WanImageToVideoPipeline
from diffusers.utils import export_to_video
from PIL import Image

# FullAttn-Diffusers build: a plain diffusers checkpoint (no GGUF quantization
# step needed, unlike the regular model's wan.py) -- simpler to load, but
# also means no Q8 memory savings, so VRAM headroom is less than the GGUF
# path had. Unverified whether this fits comfortably on a free T4's 16GB
# alongside everything else Kaggle already has resident.
FAST_MODEL = "FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers"
DTYPE = torch.float16  # T4/P100 have no fast bf16, same reasoning as the original wan.py
WIDTH, HEIGHT = 480, 832
NUM_FRAMES, FPS = 121, 24
DEFAULT_STEPS = 8  # FastVideo's own demo uses 3-4 for pure T2V; image conditioning is unverified, so this starts higher as a safety margin -- tune down only after checking real output quality.


def load_pipe():
    pipe = WanImageToVideoPipeline.from_pretrained(FAST_MODEL, torch_dtype=DTYPE)
    pipe.enable_model_cpu_offload()
    if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_tiling"):
        pipe.vae.enable_tiling()
    return pipe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    todo = [s for s in args.seeds if not (out / f"take_seed{s}.mp4").exists()]
    if not todo:
        print("all takes already made")
        return

    img = Image.open(args.image).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    prompt = Path(args.prompt).read_text()
    negative = Path(args.negative).read_text()

    pipe = load_pipe()

    for seed in todo:
        t0 = time.time()
        print(f"take seed {seed}: generating ({args.steps} steps, FastWan2.2)...", flush=True)
        with torch.no_grad():
            frames = pipe(
                image=img, prompt=prompt, negative_prompt=negative,
                height=HEIGHT, width=WIDTH, num_frames=NUM_FRAMES, num_inference_steps=args.steps,
                guidance_scale=args.guidance, generator=torch.Generator("cuda").manual_seed(seed),
            ).frames[0]
        export_to_video(frames, str(out / f"take_seed{seed}.mp4"), fps=FPS)
        gc.collect()
        torch.cuda.empty_cache()
        print(f"take seed {seed}: done in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
