// Mirrors src/icons.py's _KEYWORD_ICONS -- keep these two lists in sync by
// hand. The Python one picks which procedural icon badge the build renders
// for a scene; this one drives GRACE's "necessities" tab: tagging scenes so
// uploaded/generated library images can be matched to them by keyword.
export const KEYWORD_CATEGORIES = [
  { re: /\b(airlines?|flights?|planes?|aviation)\b/i, tag: "plane" },
  { re: /\b(banks?|banking|atms?|financ\w*)\b/i, tag: "bank" },
  { re: /\b(hospitals?|surger(y|ies)|patients?|medical)\b/i, tag: "hospital" },
  { re: /\b(servers?|data ?cent(er|re)s?|cloud|backend|router|routers)\b/i, tag: "server" },
  { re: /\b(phones?|mobile|smartphones?|text messages?)\b/i, tag: "phone" },
  { re: /\b(password|login|hack(ed|er|ers)?|breach(ed)?|stolen)\b/i, tag: "lock" },
  { re: /\b(security|encrypt\w*|firewall|protect\w*)\b/i, tag: "shield" },
  { re: /\b(internet|network|offline|dns|online|web(site)?)\b/i, tag: "globe" },
  { re: /\b(million|billion|\$|dollars?|cost|revenue|money)\b/i, tag: "money" },
  { re: /\b(crash(ed)?|froze|failed?|failure|bug|outage|error|broke|broken)\b/i, tag: "warning" },
  { re: /\b(employees?|engineers?|staff|team|office|badge)\b/i, tag: "person" },
  { re: /\b(clock|minutes?|hours?|days?|delay(ed)?)\b/i, tag: "clock" },
];

export const CATEGORY_TAGS = new Set(KEYWORD_CATEGORIES.map((k) => k.tag));

/** Mirrors src/library.py's best_match: a single shared category tag
 * (e.g. both just mention "security") is too weak to count as a real
 * picture match -- it's how an unrelated old picture from a totally
 * different script used to get reused. Needs a shared brand tag, or 2+
 * shared category tags. */
export function isRealMatch(sceneTags, imageTags) {
  const overlap = imageTags.filter((t) => sceneTags.includes(t));
  if (overlap.length === 0) return false;
  const hasBrandOverlap = overlap.some((t) => !CATEGORY_TAGS.has(t));
  return hasBrandOverlap || overlap.length >= 2;
}

// Common sentence-starters we don't want mistaken for brand/proper nouns
// just because they're capitalized at the start of a scene.
const STOPWORD_CAPS = new Set([
  "The", "A", "An", "So", "But", "And", "It", "This", "That", "When", "If",
  "As", "Then", "Now", "Once", "In", "On", "For", "With", "After", "Before",
]);

/** Returns a dedup'd list of tags for a scene's text: both the fixed
 * keyword categories (same ones icons.py matches on) and any capitalized
 * words that read as a proper noun / brand name (e.g. "Facebook", "AWS"),
 * lowercased, so "when you say Facebook" pulls Facebook-tagged library
 * images specifically, not just the generic category. */
export function extractKeywords(text) {
  const tags = new Set();
  for (const { re, tag } of KEYWORD_CATEGORIES) {
    if (re.test(text)) tags.add(tag);
  }

  const words = (text || "").split(/\s+/);
  let atSentenceStart = true; // true for the first word, and right after . ! ?
  words.forEach((w) => {
    const clean = w.replace(/[^A-Za-z]/g, "");
    const isSentenceStart = atSentenceStart;
    atSentenceStart = /[.!?]["')\]]*$/.test(w); // next word starts a new sentence

    if (clean.length < 3) return;
    if (!/^[A-Z]/.test(clean)) return;
    if (isSentenceStart) return; // sentence-start capitalization isn't necessarily a proper noun
    if (STOPWORD_CAPS.has(clean)) return;
    tags.add(clean.toLowerCase());
  });

  return Array.from(tags);
}

export const PROMPT_STYLE =
  "flat vector illustration, minimal line art, plain solid white background, " +
  "no text, no watermark, no logos copied from real brands, muted limited " +
  "color palette, consistent clean 2D style, centered subject, simple shapes";

/** One ready-to-paste image prompt per scene, all sharing the same style
 * line so a video's pictures look like they belong together. Brand/proper
 * nouns get a specific nudge toward "recognizable but original" art
 * instead of a literal trademarked logo copy. */
export function promptForScene(text, tags) {
  const brand = tags.find((t) => !CATEGORY_TAGS.has(t));
  let subject;
  if (brand) {
    const Brand = brand.charAt(0).toUpperCase() + brand.slice(1);
    subject = `a scene evoking ${Brand} -- an original, non-trademarked icon or illustration that reads as "${Brand}" without copying their real logo`;
  } else {
    subject = text.length > 90 ? `${text.slice(0, 90).trim()}...` : text;
  }
  return `${PROMPT_STYLE} -- scene: ${subject}`;
}
