import { NextResponse } from "next/server";
import { checkAppPassword } from "../../../../lib/auth";
import { putRepoFile, OWNER, REPO } from "../../../../lib/github";
import { getManifest, addManifestEntries, nextImageId, slugify } from "../../../../lib/library";

const MAX_BYTES = 4 * 1024 * 1024; // keep uploads well under Vercel's request body limit
const ALLOWED_EXT = new Set(["png", "jpg", "jpeg", "webp"]);

export async function POST(req) {
  if (!checkAppPassword(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { filename, data_base64, tags, title, scene_text } = await req.json();
  if (!data_base64) return NextResponse.json({ error: "No image data." }, { status: 400 });
  if (!Array.isArray(tags) || tags.length === 0) {
    return NextResponse.json({ error: "Needs at least one tag to be findable later." }, { status: 400 });
  }

  // strip a data: URL prefix if the browser sent one (data:image/png;base64,....)
  const base64 = data_base64.includes(",") ? data_base64.split(",")[1] : data_base64;
  const approxBytes = Math.floor((base64.length * 3) / 4);
  if (approxBytes > MAX_BYTES) {
    return NextResponse.json({ error: `Image too large (${(approxBytes / 1024 / 1024).toFixed(1)}MB, max 4MB) — resize it and try again.` }, { status: 400 });
  }

  const extFromName = filename && filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
  const ext = ALLOWED_EXT.has(extFromName) ? extFromName : "png";
  const slug = slugify(tags[0]);

  // Computing the next id from a manifest snapshot and then PUTting a brand
  // new file isn't atomic: if a second upload lands (e.g. the user uploads
  // a picture for another scene a moment later, before this one's manifest
  // write has landed), both requests can compute the SAME id from the same
  // stale snapshot and collide on the same path. GitHub's Contents API
  // rejects a no-sha PUT to a path that already exists (422), which used to
  // surface as "upload failed" and leave that scene uncovered. Retry with a
  // freshly-read id instead of giving up on the first collision.
  let id, path;
  let lastErr;
  for (let attempt = 0; attempt < 4; attempt++) {
    const manifest = await getManifest();
    id = nextImageId(manifest);
    path = `images/library/${id}_${slug}.${ext}`;
    try {
      await putRepoFile(path, base64, `GRACE: add library image ${id} (${tags.join(", ")})`);
      lastErr = null;
      break;
    } catch (e) {
      lastErr = e;
      if (!/422/.test(e.message)) break; // a real error (e.g. permissions) -- don't loop on it
    }
  }
  if (lastErr) {
    return NextResponse.json({ error: `Couldn't save the image to the repo: ${lastErr.message}` }, { status: 500 });
  }

  const entry = {
    id,
    filename: `${id}_${slug}.${ext}`,
    path,
    tags: tags.map((t) => String(t).toLowerCase()),
    title: title || "",
    // The exact scene text this was uploaded for, when the upload came
    // from the necessities tab (not set for anything uploaded another
    // way). Lets matching recognize "this picture was uploaded
    // specifically for this scene" with certainty, instead of relying on
    // tag-overlap heuristics alone -- a scene with only one generic
    // category tag (common when nothing proper-noun-y is in the text)
    // would otherwise never clear the stricter heuristic even right after
    // being uploaded for exactly that scene.
    scene_text: scene_text ? String(scene_text).trim() : "",
    created_at: new Date().toISOString(),
  };

  try {
    await addManifestEntries([entry]);
  } catch (e) {
    return NextResponse.json(
      { error: `Image saved, but the library index failed to update: ${e.message}`, image: entry },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true, image: { ...entry, url: `https://raw.githubusercontent.com/${OWNER}/${REPO}/main/${entry.path}` } });
}
