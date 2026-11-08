import { getRepoFile, putRepoFile } from "./github";

export const QUEUE_PATH = "data/scripts_queue.json";
export const SCHEDULE_PATH = "data/schedule.json";

const DEFAULT_SCHEDULE = { enabled: false, interval_hours: 24, last_dispatch_at: null, visual_mode: "pictures" };

function parseJsonFile(file, fallback) {
  if (!file) return fallback;
  try {
    return JSON.parse(file.text);
  } catch {
    return fallback;
  }
}

/** The full scripts queue: { scripts: [{id, title, script_text, status, ...}] }.
 * status is one of "queued" (waiting), "building" (a scheduled tick just
 * popped it and a build is in flight), "created" (built, at least a video
 * exists), "failed" (the dispatched build/upload didn't make it). */
export async function getQueue() {
  const file = await getRepoFile(QUEUE_PATH);
  const parsed = parseJsonFile(file, { scripts: [] });
  if (!Array.isArray(parsed.scripts)) parsed.scripts = [];
  return parsed;
}

/** Appends new queued scripts with a read-modify-write, retrying once on a
 * sha conflict -- same pattern as library.js's addManifestEntries. */
export async function addScripts(entries) {
  let lastErr;
  for (let attempt = 0; attempt < 2; attempt++) {
    const file = await getRepoFile(QUEUE_PATH);
    const queue = parseJsonFile(file, { scripts: [] });
    if (!Array.isArray(queue.scripts)) queue.scripts = [];
    queue.scripts.push(...entries);
    const content = Buffer.from(JSON.stringify(queue, null, 2)).toString("base64");
    try {
      await putRepoFile(QUEUE_PATH, content, `GRACE: queue ${entries.length} script(s)`, file?.sha);
      return queue;
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr;
}

/** Patches one queue entry by id (status, run info, ...) with the same
 * read-modify-write + retry-once pattern. Returns the updated entry, or
 * null if no entry with that id exists. */
export async function updateScript(id, patch) {
  let lastErr;
  for (let attempt = 0; attempt < 2; attempt++) {
    const file = await getRepoFile(QUEUE_PATH);
    const queue = parseJsonFile(file, { scripts: [] });
    if (!Array.isArray(queue.scripts)) queue.scripts = [];
    const idx = queue.scripts.findIndex((s) => s.id === id);
    if (idx === -1) return null;
    queue.scripts[idx] = { ...queue.scripts[idx], ...patch };
    const content = Buffer.from(JSON.stringify(queue, null, 2)).toString("base64");
    try {
      await putRepoFile(QUEUE_PATH, content, `GRACE: update script ${id}`, file?.sha);
      return queue.scripts[idx];
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr;
}

/** Removes one still-queued script by id. Refuses to remove anything once
 * it's been built (status !== "queued") -- that's a record of a real
 * video now, not a draft to discard. */
export async function removeQueuedScript(id) {
  let lastErr;
  for (let attempt = 0; attempt < 2; attempt++) {
    const file = await getRepoFile(QUEUE_PATH);
    const queue = parseJsonFile(file, { scripts: [] });
    if (!Array.isArray(queue.scripts)) queue.scripts = [];
    const entry = queue.scripts.find((s) => s.id === id);
    if (!entry) return { ok: false, reason: "not_found" };
    if (entry.status !== "queued") return { ok: false, reason: "already_built" };
    queue.scripts = queue.scripts.filter((s) => s.id !== id);
    const content = Buffer.from(JSON.stringify(queue, null, 2)).toString("base64");
    try {
      await putRepoFile(QUEUE_PATH, content, `GRACE: remove queued script ${id}`, file?.sha);
      return { ok: true };
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr;
}

export function nextScriptId(queue) {
  let max = 0;
  for (const s of queue.scripts || []) {
    const m = /^s_(\d+)$/.exec(s.id || "");
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return `s_${String(max + 1).padStart(4, "0")}`;
}

export async function getSchedule() {
  const file = await getRepoFile(SCHEDULE_PATH);
  return { ...DEFAULT_SCHEDULE, ...parseJsonFile(file, {}) };
}

export async function setSchedule(patch) {
  let lastErr;
  for (let attempt = 0; attempt < 2; attempt++) {
    const file = await getRepoFile(SCHEDULE_PATH);
    const current = { ...DEFAULT_SCHEDULE, ...parseJsonFile(file, {}) };
    const next = { ...current, ...patch };
    const content = Buffer.from(JSON.stringify(next, null, 2)).toString("base64");
    try {
      await putRepoFile(SCHEDULE_PATH, content, "GRACE: update schedule", file?.sha);
      return next;
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr;
}
