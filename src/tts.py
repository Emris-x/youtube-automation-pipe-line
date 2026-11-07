"""
Voiceover generation.

Default engine: edge-tts — free, no API key, natural neural voice. Needs
open internet (works on GitHub Actions, your own laptop, a VPS). It will
NOT work inside Claude's sandboxed dev environment, which has no route to
Microsoft's speech endpoint — that's expected, not a bug.

Automatic fallback: espeak-ng — fully offline, no network, but robotic.
Used automatically when edge-tts can't reach the network (e.g. while
testing inside the sandbox), so the pipeline never just stops working.

VOICE IS LOCKED to en-US-GuyNeural. Don't change this per-video — switching
voice mid-channel measurably hurts audience retention/recognition. If you
want a different voice, change EDGE_VOICE once, for the whole channel,
before you post video #1 — not after.

Want ElevenLabs instead (even more natural, paid beyond free tier)? Add
your API key as the ELEVENLABS_API_KEY secret/env var — generate() will use
it automatically when present, before falling back to edge-tts.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import wave
import contextlib

VOICE_ENGINE = "edge"  # "edge" (online, natural, default) | "elevenlabs" | "espeak" (offline fallback)

EDGE_VOICE = "en-US-GuyNeural"  # LOCKED — see module docstring
EDGE_RATE = "+8%"

ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # "Rachel" default

ESPEAK_VOICE = "en-us"
ESPEAK_SPEED = "165"


def _split_words(text):
    return re.findall(r"\S+", text)


async def _generate_edge(text, out_audio, out_timing):
    import edge_tts
    # edge-tts changed its default `boundary` mode to "SentenceBoundary" in
    # a recent release (ours used to rely on the old default of
    # "WordBoundary"). Without this explicit arg, no WordBoundary chunks
    # are ever emitted, boundaries ends up empty, render_scene falls back
    # to a hardcoded 3s clip, and captions silently don't draw at all
    # (both gated on `if boundaries:`) — this was the real cause of the
    # captionless, ~3-second-per-scene, audio-gets-cut-off bug.
    communicate = edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE, boundary="WordBoundary")
    boundaries = []
    with open(out_audio, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                boundaries.append({
                    "text": chunk["text"],
                    "offset_s": chunk["offset"] / 10_000_000,
                    "duration_s": chunk["duration"] / 10_000_000,
                })
    with open(out_timing, "w") as f:
        json.dump(boundaries, f, indent=2)
    return boundaries


def _generate_elevenlabs(text, out_audio, out_timing):
    """Uses ElevenLabs' timestamp endpoint so captions stay word-synced."""
    import base64
    import requests

    api_key = os.environ["ELEVENLABS_API_KEY"]
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/with-timestamps"
    resp = requests.post(
        url,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_turbo_v2_5"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    audio_bytes = base64.b64decode(data["audio_base64"])
    with open(out_audio, "wb") as f:
        f.write(audio_bytes)

    # Build word boundaries from ElevenLabs' character-level alignment
    chars = data["alignment"]["characters"]
    starts = data["alignment"]["character_start_times_seconds"]
    ends = data["alignment"]["character_end_times_seconds"]

    boundaries = []
    cur_word, cur_start = "", None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur_word:
                boundaries.append({"text": cur_word, "offset_s": cur_start, "duration_s": e - cur_start})
                cur_word, cur_start = "", None
        else:
            if cur_start is None:
                cur_start = s
            cur_word += ch
    if cur_word:
        boundaries.append({"text": cur_word, "offset_s": cur_start, "duration_s": ends[-1] - cur_start})

    with open(out_timing, "w") as f:
        json.dump(boundaries, f, indent=2)
    return boundaries


def _generate_espeak(text, out_audio, out_timing):
    wav_path = out_audio.replace(".mp3", ".wav") if out_audio.endswith(".mp3") else out_audio
    subprocess.run(
        ["espeak-ng", "-v", ESPEAK_VOICE, "-s", ESPEAK_SPEED, "-w", wav_path, text],
        check=True,
    )
    with contextlib.closing(wave.open(wav_path, "rb")) as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        total_duration = frames / float(rate)

    words = _split_words(text)
    weights = [len(w) + 1 for w in words]
    total_weight = sum(weights)

    boundaries = []
    t = 0.0
    for w, wt in zip(words, weights):
        dur = total_duration * (wt / total_weight)
        boundaries.append({"text": w, "offset_s": round(t, 3), "duration_s": round(dur, 3)})
        t += dur

    with open(out_timing, "w") as f:
        json.dump(boundaries, f, indent=2)

    if out_audio.endswith(".mp3") and wav_path != out_audio:
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", out_audio],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"[tts] ffmpeg mp3 conversion failed (exit {e.returncode}):\n{e.stderr.decode(errors='replace')}")
            raise
    return boundaries


def generate(text, out_audio, out_timing, engine=None):
    """engine=None -> auto: ElevenLabs if key present, else edge-tts,
    falling back to espeak if the network path isn't reachable (sandbox)."""
    if engine is None:
        if os.environ.get("ELEVENLABS_API_KEY"):
            engine = "elevenlabs"
        else:
            engine = VOICE_ENGINE

    if engine == "elevenlabs":
        return _generate_elevenlabs(text, out_audio, out_timing)

    if engine == "edge":
        try:
            return asyncio.run(_generate_edge(text, out_audio, out_timing))
        except Exception as e:
            print(f"[tts] edge-tts failed ({e.__class__.__name__}: {e}), falling back to espeak for this run")
            return _generate_espeak(text, out_audio, out_timing)

    if engine == "espeak":
        return _generate_espeak(text, out_audio, out_timing)

    raise ValueError(f"Unknown engine: {engine}")


if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else "This is a test of the voiceover system."
    out_audio = sys.argv[2] if len(sys.argv) > 2 else "audio/test.mp3"
    out_timing = sys.argv[3] if len(sys.argv) > 3 else "audio/test_timing.json"
    engine = sys.argv[4] if len(sys.argv) > 4 else None
    boundaries = generate(text, out_audio, out_timing, engine)
    print(f"Wrote {out_audio} with {len(boundaries)} word boundaries -> {out_timing}")
