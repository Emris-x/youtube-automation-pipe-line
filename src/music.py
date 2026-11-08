"""
Zero-cost procedural ambient background music -- a looping low pad, a
gentle rhythmic pulse, and sparse high notes, all in a minor key, synthesized
from scratch with pure Python (stdlib `wave` + `math` only -- no numpy, no
audio libraries, no network call, no cost per video).

It's mixed under the narration in build_video.py via ffmpeg's
sidechaincompress filter, so the music automatically ducks down whenever
someone's actually talking instead of fighting the voice, then swells back
up in the gaps. Code-made ambient, not a produced track -- good enough to
stop the videos sounding dry, swap in real music later if you want.
"""
import math
import random
import struct
import wave

SAMPLE_RATE = 22050  # plenty for a background pad; keeps the pure-Python
# synthesis loop fast. ffmpeg resamples to 44100 when mixing anyway.

# A-minor-ish interval ratios off a low root -- root, minor third, fourth,
# minor seventh. Picked for "tense but not cheesy" per the brief, not an
# exact scale -- these are the four pad voices plus their octave-up echoes
# for the sparse high notes.
ROOT_HZ = 110.0  # A2
PAD_RATIOS = [1.0, 1.1892, 1.3348, 1.4983]
HIGH_RATIOS = [2 * r for r in PAD_RATIOS]


def generate_ambient_wav(path, duration_s, seed=0):
    """Writes a mono 16-bit WAV of length duration_s to path. Deterministic
    per seed (same seed -> same track) so a re-run of the same scene isn't
    randomly different for no reason."""
    rng = random.Random(seed)
    n = max(1, int(duration_s * SAMPLE_RATE))
    samples = [0.0] * n
    two_pi = 2 * math.pi

    # layer 1: slow swelling pad across all four interval voices
    for ratio in PAD_RATIOS:
        freq = ROOT_HZ * ratio
        phase = rng.uniform(0, two_pi)
        swell_phase = rng.uniform(0, two_pi)
        w = two_pi * freq / SAMPLE_RATE
        sw = two_pi * 0.045 / SAMPLE_RATE  # ~22s swell cycle
        for i in range(n):
            swell = 0.5 + 0.5 * math.sin(i * sw + swell_phase)
            samples[i] += 0.045 * swell * math.sin(i * w + phase)

    # layer 2: soft rhythmic pulse on the root, pluck-like decay each beat
    pulse_period_s = 1.8
    period_samples = pulse_period_s * SAMPLE_RATE
    w = two_pi * ROOT_HZ / SAMPLE_RATE
    for i in range(n):
        phase_in_beat = (i % period_samples) / period_samples
        env = math.exp(-4.0 * phase_in_beat)
        samples[i] += 0.03 * env * math.sin(i * w)

    # layer 3: sparse high notes, randomly timed, short plucked envelope
    t = 0.0
    while t < duration_s:
        t += rng.uniform(2.5, 6.0)
        if t >= duration_s:
            break
        freq = ROOT_HZ * rng.choice(HIGH_RATIOS)
        note_len = rng.uniform(0.8, 1.6)
        start_i = int(t * SAMPLE_RATE)
        note_n = int(note_len * SAMPLE_RATE)
        w = two_pi * freq / SAMPLE_RATE
        for j in range(note_n):
            i = start_i + j
            if i >= n:
                break
            frac = j / note_n
            env = math.sin(math.pi * min(1.0, frac)) * math.exp(-1.2 * frac * note_len)
            samples[i] += 0.028 * env * math.sin(j * w)

    peak = max(0.0001, max(abs(s) for s in samples))
    scale = min(1.0, 0.82 / peak)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        buf = bytearray(2 * n)
        for i, s in enumerate(samples):
            v = int(max(-1.0, min(1.0, s * scale)) * 32767)
            struct.pack_into("<h", buf, i * 2, v)
        wf.writeframes(bytes(buf))

    return path


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "test_music.wav"
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    generate_ambient_wav(out, dur)
    print(f"wrote {out} ({dur}s)")
