import { NextResponse } from "next/server";
import { checkAppPassword } from "../../../../lib/auth";
import { splitScenes } from "../../../../lib/scenes";
import { extractKeywords, promptForScene, isRealMatch } from "../../../../lib/keywords";
import { getManifest } from "../../../../lib/library";
import { OWNER, REPO } from "../../../../lib/github";

function rawUrl(path) {
  return `https://raw.githubusercontent.com/${OWNER}/${REPO}/main/${path}`;
}

export async function POST(req) {
  if (!checkAppPassword(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { script_text } = await req.json();
  if (!script_text || script_text.trim().length < 10) {
    return NextResponse.json({ error: "Paste a script first." }, { status: 400 });
  }

  const scenes = splitScenes(script_text);
  const manifest = await getManifest();

  const result = scenes.map((scene) => {
    const tags = extractKeywords(scene.text);
    const sceneTextNorm = (scene.text || "").trim().toLowerCase();
    // A picture uploaded for this exact scene text (via the necessities
    // tab, just now or in an earlier session) is a certain match --
    // checked before the tag-overlap heuristic, which can't tell "this was
    // deliberately uploaded for this scene" from "this old picture
    // happens to share one generic tag" when a scene only has a single
    // category keyword and nothing else distinctive in it.
    const exact = (manifest.images || []).filter(
      (img) => img.scene_text && String(img.scene_text).trim().toLowerCase() === sceneTextNorm
    );
    const heuristic = (manifest.images || []).filter(
      (img) => !exact.includes(img) && Array.isArray(img.tags) && isRealMatch(tags, img.tags)
    );
    const matches = [...exact, ...heuristic]
      .slice(0, 6)
      .map((img) => ({ id: img.id, path: img.path, filename: img.filename, url: rawUrl(img.path) }));

    return {
      id: scene.id,
      text: scene.text,
      tags,
      prompt: promptForScene(scene.text, tags),
      matches,
      covered: matches.length > 0,
    };
  });

  return NextResponse.json({ scenes: result });
}
