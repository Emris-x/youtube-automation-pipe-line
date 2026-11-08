# Kaggle showpiece mode — EXPERIMENTAL, UNVERIFIED

This folder is the start of a free, optional "cartoon showpiece" mode for
GRACE: real AI-generated character video instead of stickman/photo mode,
running on Kaggle's free GPU tier (not GitHub Actions — GitHub's free
runners have no GPU at all, no model changes that).

**Status: built, not yet tested on a real GPU.** This sandbox has no GPU
and no Kaggle account access, so nothing here has actually been run. Two
files, both careful adaptations of real, working code I read directly
(not guessed from summaries), but adaptations are exactly the kind of
change that needs a real run to catch what reading the code can't:

- `wan_fast.py` — a copy of [ai-influencer-studio](https://github.com/ItxAsim/ai-influencer-studio)'s
  `wan.py` (MIT), pointed at FastVideo's distilled `FastWan2.2-TI2V-5B`
  checkpoint (Apache-2.0) at 8 steps instead of the regular model's 40.
  **The open question:** that distilled model was only trained and
  benchmarked by its own authors for text-to-video. A public demo proves
  it *runs* as image-to-video too, but nobody's confirmed the *output
  quality* holds up for that use — it might look great, or it might not,
  and I have no way to tell you which without actually generating a clip.

- `musetalk_lipsync.py` — swaps [MuseTalk](https://github.com/TMElyralab/MuseTalk)
  (MIT, commercially clear) in for LatentSync as the lip-sync step.
  MuseTalk's own benchmark (an 8s clip in ~5 min on a weak 4GB-VRAM laptop
  GPU) suggests a real speedup over LatentSync's "1-3 min per second" on
  the same free T4 — but independent write-ups say its visual fidelity is
  a touch softer than LatentSync's. A real trade-off, not a free upgrade.

Neither file is wired into the studio's `pipeline.py` yet — on purpose.
Wiring in untested code and calling it done would mean the first real
feedback on whether this works comes from a video you're trying to
actually publish, which isn't where you want to find out.

## What "making it work" actually requires from here

I can write and reason about this code carefully, but I cannot execute a
single step of it — no GPU, no Kaggle login, no way to look at a
generated frame and judge if a face looks right. That part needs a real
run, and that's unavoidable: no amount of further reading or code review
substitutes for actually seeing output.

## How to actually test this (15–20 minutes on your free Kaggle GPU)

1. Open [ai-influencer-studio](https://kaggle.com/kernels/welcome?src=https://github.com/ItxAsim/ai-influencer-studio/blob/main/influencer_studio.ipynb)
   in Kaggle (Accelerator: GPU T4, Internet: On), run it once as normal
   through "Character" so you have a `start.png` for a locked character.
2. Upload `wan_fast.py` into the Kaggle session's `studio/` folder
   (replacing nothing — it's a new file alongside the existing `wan.py`).
3. From a notebook cell, run it directly against that character's
   `start.png`, a short test prompt, and one seed — same arguments
   `wan.py` already takes:
   ```
   !python studio/wan_fast.py --image <path>/start.png --prompt prompt.txt \
     --negative negative.txt --seeds 42 --out /tmp/fast_test/
   ```
4. **Just look at the output clip.** Does the character stay recognizable
   and still? Does it look like it's breathing/moving naturally, or does
   it warp? That's the whole test for this step.
5. If it looks usable, upload `musetalk_lipsync.py`, point it at that
   same clip plus any short voice.wav from the studio, and look at the
   mouth sync the same way.

## What I need back to actually finish this

Send me what happened at step 4 (and 5) — a description, a screenshot, or
the clip itself. Real failures (a stack trace, a warped face, wrong
timing) are exactly what turns this from "a careful guess" into working
code — I can fix a concrete bug immediately once I can see it, the same
way the espeak-ng fallback and the aim-arm/facepalm regressions earlier
in this project only got fixed once there was a real failure to look at.

## What's still completely unaddressed

- **Kaggle's ~30 GPU-hours/week cap** vs. your actual posting cadence —
  real math, not done yet, needs your numbers (videos/week, target length).
- **No automation handoff.** Kaggle is a notebook session, not something
  GitHub Actions can dispatch and walk away from the way `manual-video.yml`
  does today. Whether that gap can be closed (Kaggle does have an API for
  triggering kernel runs) or stays a manual step is unresearched.
- This mode produces a single character's talking clip — it is not merged
  into GRACE's own `build_video.py`/`motion.py` pipeline (captions, CTA
  card, YouTube upload) in any way yet. That stitching is a separate,
  real piece of work for after the AI-generation half is confirmed to
  actually look good.
