// Mirrors src/segment_script.py's text_to_script() paragraph-splitting
// logic -- kept as a separate JS port (rather than shelling out to Python,
// which Vercel's Node runtime can't do) so GRACE's "necessities" tab can
// scan a script the same way the build pipeline will split it into scenes.
// Keep these two in sync by hand if the splitting rules ever change.

const LABEL_RE = /^\s*(scene\s*[\w-]+|hook|cta|call[\s-]?to[\s-]?action|intro|outro)\s*[:\-–—]\s*/i;

function stripLabel(text) {
  let t = text.replace(LABEL_RE, "").trim();
  const openers = "\"'“‘";
  const closers = "\"'”’";
  if (t.length >= 2 && openers.includes(t[0]) && closers.includes(t[t.length - 1])) {
    t = t.slice(1, -1).trim();
  }
  return t;
}

function chunkByWords(text, maxWords = 22) {
  const words = text.split(/\s+/).filter(Boolean);
  const chunks = [];
  let cur = [];
  for (const w of words) {
    cur.push(w);
    if (cur.length >= maxWords) {
      chunks.push(cur.join(" "));
      cur = [];
    }
  }
  if (cur.length) chunks.push(cur.join(" "));
  return chunks;
}

export function splitScenes(rawText) {
  const raw = (rawText || "").trim();
  if (!raw) return [];
  let paragraphs = raw
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);

  if (paragraphs.length < 3) paragraphs = chunkByWords(raw);

  paragraphs = paragraphs.map(stripLabel).filter(Boolean);

  const n = paragraphs.length;
  return paragraphs.map((text, i) => {
    let id;
    if (i === 0) id = "hook";
    else if (i === n - 1) id = "cta";
    else id = `point${i}`;
    return { id, text };
  });
}
