import { getRepoFile, putRepoFile } from "./github";

export const MANIFEST_PATH = "images/library/manifest.json";

/** The full image library manifest: { images: [{id, filename, path, tags, title, created_at}, ...] } */
export async function getManifest() {
  const file = await getRepoFile(MANIFEST_PATH);
  if (!file) return { images: [] };
  try {
    const parsed = JSON.parse(file.text);
    if (!Array.isArray(parsed.images)) return { images: [] };
    return parsed;
  } catch {
    return { images: [] };
  }
}

/** Appends entries to the manifest with a read-modify-write, retrying once
 * if another write raced it (GitHub rejects a PUT with a stale sha). */
export async function addManifestEntries(entries) {
  let lastErr;
  for (let attempt = 0; attempt < 2; attempt++) {
    const file = await getRepoFile(MANIFEST_PATH);
    const manifest = file ? (() => { try { return JSON.parse(file.text); } catch { return { images: [] }; } })() : { images: [] };
    if (!Array.isArray(manifest.images)) manifest.images = [];
    manifest.images.push(...entries);
    const content = Buffer.from(JSON.stringify(manifest, null, 2)).toString("base64");
    try {
      await putRepoFile(MANIFEST_PATH, content, `GRACE: add ${entries.length} image(s) to library`, file?.sha);
      return manifest;
    } catch (e) {
      lastErr = e;
      // sha mismatch (someone else wrote in between) -> retry once with a fresh read
    }
  }
  throw lastErr;
}

export function nextImageId(manifest) {
  let max = 0;
  for (const img of manifest.images || []) {
    const m = /^img_(\d+)$/.exec(img.id || "");
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return `img_${String(max + 1).padStart(4, "0")}`;
}

export function slugify(s) {
  return String(s || "image")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 40) || "image";
}
