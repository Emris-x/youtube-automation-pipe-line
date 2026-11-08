"""
A small library of procedurally-drawn icons, picked automatically by
matching keywords in a scene's narration text — "write an algorithm that
creates drawings that match the story" in its simplest honest form: no image
generation, no API calls, just simple geometric icons selected by what the
sentence is actually about (planes for "airlines grounded", a cross for
"hospitals delayed", a server stack for "server"/"data center", etc).

Icons are drawn with plain PIL primitives (lines, ellipses, rectangles) so
they inherit the same hacker-terminal line-art look as everything else —
no raster assets, nothing to download, nothing that can go stale.
"""
import re

# keyword -> icon-drawing function name, checked in this order (first match
# in the text wins, so put more specific words first).
_KEYWORD_ICONS = [
    (r"\b(airlines?|flights?|planes?|aviation)\b", "plane"),
    (r"\b(banks?|banking|atms?|financ\w*)\b", "bank"),
    (r"\b(hospitals?|surger(y|ies)|patients?|medical)\b", "hospital"),
    (r"\b(servers?|data ?cent(er|re)s?|cloud|backend|router|routers)\b", "server"),
    (r"\b(phones?|mobile|smartphones?|text messages?)\b", "phone"),
    (r"\b(password|login|hack(ed|er|ers)?|breach(ed)?|stolen)\b", "lock"),
    (r"\b(security|encrypt\w*|firewall|protect\w*)\b", "shield"),
    (r"\b(internet|network|offline|dns|online|web(site)?)\b", "globe"),
    (r"\b(million|billion|\$|dollars?|cost|revenue|money)\b", "money"),
    (r"\b(crash(ed)?|froze|failed?|failure|bug|outage|error|broke|broken)\b", "warning"),
    (r"\b(employees?|engineers?|staff|team|office|badge)\b", "person"),
    (r"\b(clock|minutes?|hours?|days?|delay(ed)?)\b", "clock"),
]


def pick_icon_for_text(text):
    """Returns an icon name (str) for the first keyword pattern that matches
    scene text, or None if nothing matches (caller falls back to the
    existing abstract per-visual motif)."""
    low = text.lower()
    for pattern, icon in _KEYWORD_ICONS:
        if re.search(pattern, low):
            return icon
    return None


def matched_keywords(text):
    """All matched trigger words (for populating script JSON's `keywords`
    field) — not just the one icon ultimately drawn."""
    low = text.lower()
    found = []
    for pattern, icon in _KEYWORD_ICONS:
        m = re.search(pattern, low)
        if m:
            found.append(m.group(0))
    return found


_STOPWORD_CAPS = {
    "The", "A", "An", "So", "But", "And", "It", "This", "That", "When", "If",
    "As", "Then", "Now", "Once", "In", "On", "For", "With", "After", "Before",
}


def brand_tags(text):
    """Capitalized words that read as a proper noun / brand name (e.g.
    "Facebook", "AWS"), lowercased -- mirrors grace/lib/keywords.js's
    extractKeywords() proper-noun pass; keep the two in sync by hand. Lets
    a scene mentioning a named company match a library image someone
    tagged with that company's name specifically, not just the generic
    keyword category."""
    tags = []
    at_sentence_start = True
    for w in text.split():
        clean = re.sub(r"[^A-Za-z]", "", w)
        is_start = at_sentence_start
        at_sentence_start = bool(re.search(r"[.!?][\"'\)\]]*$", w))
        if len(clean) < 3 or not clean[0].isupper() or is_start or clean in _STOPWORD_CAPS:
            continue
        tags.append(clean.lower())
    return tags


# ---------------------------------------------------------------- drawing

def _plane(draw, cx, cy, s, color):
    w1 = max(2, int(s // 14))
    w2 = max(2, int(s // 16))
    draw.line([cx - s, cy, cx + s, cy], fill=color, width=w1)
    draw.polygon([(cx + s, cy), (cx + s * 0.4, cy - s * 0.35), (cx + s * 0.4, cy + s * 0.35)], outline=color, width=w2)
    draw.line([cx - s * 0.1, cy, cx - s * 0.5, cy - s * 0.4], fill=color, width=w2)
    draw.line([cx - s * 0.1, cy, cx - s * 0.5, cy + s * 0.4], fill=color, width=w2)


def _bank(draw, cx, cy, s, color):
    w = max(2, int(s // 16))
    draw.line([cx - s, cy + s * 0.6, cx + s, cy + s * 0.6], fill=color, width=w)
    draw.polygon([(cx, cy - s), (cx - s, cy - s * 0.3), (cx + s, cy - s * 0.3)], outline=color, width=w)
    for i in range(4):
        x = cx - s * 0.7 + i * (s * 1.4 / 3)
        draw.line([x, cy - s * 0.2, x, cy + s * 0.55], fill=color, width=w)


def _hospital(draw, cx, cy, s, color):
    w = max(2, int(s // 14))
    draw.rounded_rectangle([cx - s, cy - s, cx + s, cy + s], radius=s * 0.2, outline=color, width=w)
    draw.rectangle([cx - s * 0.18, cy - s * 0.55, cx + s * 0.18, cy + s * 0.55], fill=color)
    draw.rectangle([cx - s * 0.55, cy - s * 0.18, cx + s * 0.55, cy + s * 0.18], fill=color)


def _server(draw, cx, cy, s, color):
    w = max(2, int(s // 16))
    for i in range(3):
        y0 = cy - s + i * (s * 0.75)
        y1 = y0 + s * 0.55
        draw.rounded_rectangle([cx - s, y0, cx + s, y1], radius=s * 0.08, outline=color, width=w)
        draw.ellipse([cx + s * 0.6, y0 + s * 0.2, cx + s * 0.6 + s * 0.14, y0 + s * 0.2 + s * 0.14], fill=color)


def _phone(draw, cx, cy, s, color):
    w = max(2, int(s // 16))
    draw.rounded_rectangle([cx - s * 0.55, cy - s, cx + s * 0.55, cy + s], radius=s * 0.25, outline=color, width=w)
    draw.line([cx - s * 0.25, cy + s * 0.75, cx + s * 0.25, cy + s * 0.75], fill=color, width=w)


def _lock(draw, cx, cy, s, color):
    w = max(2, int(s // 14))
    draw.rounded_rectangle([cx - s * 0.7, cy - s * 0.1, cx + s * 0.7, cy + s, ], radius=s * 0.15, outline=color, width=w)
    draw.arc([cx - s * 0.45, cy - s * 1.1, cx + s * 0.45, cy - s * 0.1], 180, 360, fill=color, width=w)
    draw.ellipse([cx - s * 0.12, cy + s * 0.3, cx + s * 0.12, cy + s * 0.54], fill=color)


def _shield(draw, cx, cy, s, color):
    w = max(2, int(s // 14))
    pts = [
        (cx, cy - s), (cx + s * 0.8, cy - s * 0.55), (cx + s * 0.8, cy + s * 0.15),
        (cx, cy + s), (cx - s * 0.8, cy + s * 0.15), (cx - s * 0.8, cy - s * 0.55),
    ]
    draw.polygon(pts, outline=color, width=w)
    draw.line([cx - s * 0.3, cy, cx - s * 0.05, cy + s * 0.3], fill=color, width=w)
    draw.line([cx - s * 0.05, cy + s * 0.3, cx + s * 0.4, cy - s * 0.3], fill=color, width=w)


def _globe(draw, cx, cy, s, color):
    w = max(2, int(s // 16))
    draw.ellipse([cx - s, cy - s, cx + s, cy + s], outline=color, width=w)
    draw.ellipse([cx - s * 0.4, cy - s, cx + s * 0.4, cy + s], outline=color, width=w)
    draw.line([cx - s, cy, cx + s, cy], fill=color, width=w)
    draw.line([cx - s * 0.85, cy - s * 0.5, cx + s * 0.85, cy - s * 0.5], fill=color, width=max(1, w - 2))
    draw.line([cx - s * 0.85, cy + s * 0.5, cx + s * 0.85, cy + s * 0.5], fill=color, width=max(1, w - 2))


def _money(draw, cx, cy, s, color, font=None):
    w = max(2, int(s // 16))
    draw.ellipse([cx - s, cy - s, cx + s, cy + s], outline=color, width=w)
    if font is not None:
        tw = draw.textlength("$", font=font)
        draw.text((cx - tw / 2, cy - s * 0.65), "$", font=font, fill=color)


def _warning(draw, cx, cy, s, color, font=None):
    w = max(2, int(s // 14))
    draw.polygon([(cx, cy - s), (cx + s, cy + s * 0.8), (cx - s, cy + s * 0.8)], outline=color, width=w)
    if font is not None:
        tw = draw.textlength("!", font=font)
        draw.text((cx - tw / 2, cy - s * 0.1), "!", font=font, fill=color)


def _person(draw, cx, cy, s, color):
    w = max(2, int(s // 14))
    draw.ellipse([cx - s * 0.35, cy - s, cx + s * 0.35, cy - s * 0.3], outline=color, width=w)
    draw.line([cx, cy - s * 0.3, cx, cy + s * 0.5], fill=color, width=w)
    draw.line([cx, cy, cx - s * 0.6, cy + s * 0.2], fill=color, width=w)
    draw.line([cx, cy, cx + s * 0.6, cy + s * 0.2], fill=color, width=w)
    draw.line([cx, cy + s * 0.5, cx - s * 0.4, cy + s], fill=color, width=w)
    draw.line([cx, cy + s * 0.5, cx + s * 0.4, cy + s], fill=color, width=w)


def _clock(draw, cx, cy, s, color):
    w = max(2, int(s // 16))
    draw.ellipse([cx - s, cy - s, cx + s, cy + s], outline=color, width=w)
    draw.line([cx, cy, cx, cy - s * 0.65], fill=color, width=w)
    draw.line([cx, cy, cx + s * 0.45, cy + s * 0.2], fill=color, width=w)


_ICON_FUNCS = {
    "plane": _plane, "bank": _bank, "hospital": _hospital, "server": _server,
    "phone": _phone, "lock": _lock, "shield": _shield, "globe": _globe,
    "money": _money, "warning": _warning, "person": _person, "clock": _clock,
}

# icons that render a glyph and need a font
_NEEDS_FONT = {"money", "warning"}


def draw_icon(draw, name, cx, cy, s, color, font=None):
    fn = _ICON_FUNCS.get(name)
    if fn is None:
        return
    if name in _NEEDS_FONT:
        fn(draw, cx, cy, s, color, font=font)
    else:
        fn(draw, cx, cy, s, color)
