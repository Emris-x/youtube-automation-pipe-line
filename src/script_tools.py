"""
Script utilities: load a video script JSON, compute per-scene narration text
and rough timing estimates (actual timing comes from TTS word-boundary data
later in the pipeline — this is just for pre-render sanity checks).
"""
import json
import sys

WORDS_PER_SECOND = 2.5  # rough average speaking pace


def load_script(path):
    with open(path, "r") as f:
        return json.load(f)


def full_narration(script):
    """Concatenate all scene text into one block for a single TTS pass."""
    return " ".join(scene["text"] for scene in script["scenes"])


def estimate_duration(script):
    total_words = sum(len(scene["text"].split()) for scene in script["scenes"])
    return round(total_words / WORDS_PER_SECOND, 1)


def scene_breakdown(script):
    rows = []
    for scene in script["scenes"]:
        words = len(scene["text"].split())
        rows.append({
            "id": scene["id"],
            "words": words,
            "est_seconds": round(words / WORDS_PER_SECOND, 1),
            "visual": scene["visual"],
        })
    return rows


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "scripts/video_001.json"
    script = load_script(path)
    print(f"Title: {script['title']}")
    print(f"Estimated total duration: {estimate_duration(script)}s\n")
    for row in scene_breakdown(script):
        print(f"  [{row['id']:10s}] {row['words']:3d} words  ~{row['est_seconds']:5.1f}s  visual={row['visual']}")
