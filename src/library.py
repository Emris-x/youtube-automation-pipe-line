"""
Loads the image library GRACE's "necessities" tab writes to
(images/library/manifest.json + the image files alongside it) and matches a
scene's keywords to the best available picture, so motion.py can draw a
real, script-specific image instead of (or alongside) the procedural
circle/bar motif -- "houses, people, a Facebook logo" instead of the same
recycled abstract shapes every video.

No match found -> motion.py falls back to the existing procedural motif, so
a scene is never left blank just because the library doesn't have a picture
for it yet.
"""
import json
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(_BASE_DIR, "..", "images", "library")
MANIFEST_PATH = os.path.join(LIBRARY_DIR, "manifest.json")


def load_manifest():
    try:
        with open(MANIFEST_PATH) as f:
            data = json.load(f)
        images = data.get("images", [])
        return images if isinstance(images, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def best_match(scene_keywords, manifest=None):
    """Returns the absolute path to the best-matching library image for a
    scene's keywords, or None if nothing matches. "Best" = most overlapping
    tags; ties go to whichever comes first in the manifest (oldest)."""
    if not scene_keywords:
        return None
    manifest = load_manifest() if manifest is None else manifest
    if not manifest:
        return None

    kw = {str(k).lower() for k in scene_keywords}
    best, best_score = None, 0
    for entry in manifest:
        tags = {str(t).lower() for t in entry.get("tags", [])}
        score = len(tags & kw)
        if score > best_score:
            best_score, best = score, entry

    if best is None:
        return None
    path = os.path.join(_BASE_DIR, "..", best["path"])
    return path if os.path.exists(path) else None
