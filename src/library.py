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

from icons import _KEYWORD_ICONS

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(_BASE_DIR, "..", "images", "library")
MANIFEST_PATH = os.path.join(LIBRARY_DIR, "manifest.json")

# The fixed category tags (plane, bank, server, ...) vs. brand/proper-noun
# tags (facebook, equifax, ...) -- mirrors grace/lib/keywords.js's
# CATEGORY_TAGS. A scene and a library image sharing only ONE generic
# category tag (e.g. both happen to mention "security") isn't a real
# content match -- it's how an unrelated old picture from a totally
# different script used to get reused. A match now needs either a shared
# brand tag, or at least two shared category tags.
_CATEGORY_TAGS = {icon for _, icon in _KEYWORD_ICONS}


def load_manifest():
    try:
        with open(MANIFEST_PATH) as f:
            data = json.load(f)
        images = data.get("images", [])
        return images if isinstance(images, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def best_match(scene_keywords, scene_text=None, manifest=None):
    """Returns the absolute path to the best-matching library image for a
    scene, or None if nothing matches.

    Checks for an exact scene-text match first -- a picture uploaded via
    the necessities tab for this literal scene is a certain match,
    regardless of how many (if any) keyword tags the scene triggered.
    Without this, a scene with only one generic category keyword (or none
    at all -- common for narration with no proper noun or category word in
    it) could never clear the tag-overlap heuristic below even right after
    being uploaded specifically for it.

    Falls back to tag overlap ("best" = most overlapping tags, requiring a
    shared brand tag or 2+ shared category tags -- a single shared
    category tag alone is how an unrelated old picture from a totally
    different script used to get reused); ties go to whichever comes
    first in the manifest (oldest)."""
    manifest = load_manifest() if manifest is None else manifest
    if not manifest:
        return None

    text_norm = (scene_text or "").strip().lower()
    if text_norm:
        for entry in manifest:
            if str(entry.get("scene_text") or "").strip().lower() == text_norm:
                path = os.path.join(_BASE_DIR, "..", entry["path"])
                if os.path.exists(path):
                    return path

    if not scene_keywords:
        return None

    kw = {str(k).lower() for k in scene_keywords}
    best, best_score = None, 0
    for entry in manifest:
        tags = {str(t).lower() for t in entry.get("tags", [])}
        overlap = tags & kw
        if not overlap:
            continue
        # a single shared category tag (e.g. both just mention "security")
        # is too weak to count -- require a shared brand tag, or 2+ shared
        # category tags, before this counts as a real match at all.
        has_brand_overlap = bool(overlap - _CATEGORY_TAGS)
        if not has_brand_overlap and len(overlap) < 2:
            continue
        score = len(overlap) + (10 if has_brand_overlap else 0)  # prefer brand matches
        if score > best_score:
            best_score, best = score, entry

    if best is None:
        return None
    path = os.path.join(_BASE_DIR, "..", best["path"])
    return path if os.path.exists(path) else None
