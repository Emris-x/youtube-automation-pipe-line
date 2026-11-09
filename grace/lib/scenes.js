// Mirrors src/segment_script.py's text_to_script() paragraph-splitting
// logic -- kept as a separate JS port (rather than shelling out to Python,
// which Vercel's Node runtime can't do) so GRACE's "necessities" tab can
// scan a script the same way the build pipeline will split it into scenes.
// Keep these two in sync by hand if the splitting rules ever change.

// Labels where the rest of the paragraph IS meant to be spoken -- just the
// label word itself gets dropped. `\s*` around the separator already
// reaches across a newline, so a label sitting on its own line above the
// text it introduces is handled the same as one sharing the line.
const STRIP_LABEL_RE =
  /^\s*(scene\s*[\w-]+|hook|cta|call[\s-]?to[\s-]?action|intro|outro|narration|dialogue|[\w'’]+\s+dialogue)\s*[:\-–—]\s*/i;

// Labels where the WHOLE paragraph is a stage direction or spec line, never
// spoken narration -- "Visual: ..." is describing the shot, not dialogue.
const DROP_LABEL_RE =
  /^\s*(visual|on[\s-]?screen\s*text|end|format|duration|tone|visual\s*style|style|camera|sfx|sound\s*effects?|music)\s*[:\-–—]/i;

// A paragraph of several short "Label: value" lines (Format:/Duration:/...)
// is a spec block, not narration, even when no single label matches the
// list above.
const KV_LINE_RE = /^\s*[A-Za-z][A-Za-z \t]{1,24}:\s*\S/;

// A trailing "(0-7s)"-style timecode is an unambiguous heading signal.
const TIMECODE_TAIL_RE = /\(\s*\d+\s*[–-]\s*\d+\s*s\s*\)\s*$/i;

function isSpecBlock(paragraph) {
  const lines = paragraph.split("\n").filter((l) => l.trim());
  if (lines.length < 2) return false;
  const kv = lines.filter((l) => KV_LINE_RE.test(l)).length;
  return kv >= Math.max(2, Math.ceil(lines.length / 2));
}

function isBareHeading(text) {
  // Short-and-unpunctuated is NOT a heading signal by itself -- this
  // project's narration is often short and punctuation-free on purpose.
  // Mostly-uppercase IS safe: real narration is essentially never written
  // in all caps, but a leftover scene title reliably is.
  if (!text) return true;
  if (TIMECODE_TAIL_RE.test(text)) return true;
  const letters = text.replace(/[^A-Za-z]/g, "");
  const isMostlyUpper = letters.length >= 3 && letters === letters.toUpperCase() && letters !== letters.toLowerCase();
  return isMostlyUpper && text.split(/\s+/).filter(Boolean).length <= 8;
}

function isDocumentTitle(paragraph, index, title) {
  if (index > 1) return false;
  const stripped = paragraph.trim().replace(/^["'“”‘’]|["'“”‘’]$/g, "");
  if (title && stripped.toLowerCase() === title.trim().toLowerCase()) return true;
  const words = paragraph.split(/\s+/).filter(Boolean);
  const letters = paragraph.replace(/[^A-Za-z]/g, "");
  const isAllCaps = letters.length >= 3 && letters === letters.toUpperCase() && letters !== letters.toLowerCase();
  return isAllCaps && words.length <= 5 && !/\d/.test(paragraph);
}

function stripLabel(text) {
  let t = text.replace(STRIP_LABEL_RE, "").trim();
  const openers = "\"'“‘";
  const closers = "\"'”’";
  if (t.length >= 2 && openers.includes(t[0]) && closers.includes(t[t.length - 1])) {
    t = t.slice(1, -1).trim();
  }
  return t;
}

function cleanParagraphs(paragraphs, title) {
  const kept = [];
  paragraphs.forEach((para, i) => {
    if (DROP_LABEL_RE.test(para) || isSpecBlock(para) || isDocumentTitle(para, i, title)) return;
    const cleaned = stripLabel(para);
    if (!cleaned || isBareHeading(cleaned)) return;
    kept.push(cleaned);
  });
  return kept;
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

export function splitScenes(rawText, title) {
  const raw = (rawText || "").trim();
  if (!raw) return [];
  let paragraphs = raw
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);

  // Only re-chunk when no real scene breaks were given at all (one
  // blank-line-free blob) -- checked on the ORIGINAL paragraph count, not
  // the cleaned one, so a short script that legitimately cleans down to 1-2
  // real beats doesn't get thrown away and blindly re-chunked.
  if (paragraphs.length < 3) paragraphs = chunkByWords(raw);

  const cleaned = cleanParagraphs(paragraphs, title);
  paragraphs = cleaned.length ? cleaned : paragraphs;

  const n = paragraphs.length;
  return paragraphs.map((text, i) => {
    let id;
    if (i === 0) id = "hook";
    else if (i === n - 1) id = "cta";
    else id = `point${i}`;
    return { id, text };
  });
}
