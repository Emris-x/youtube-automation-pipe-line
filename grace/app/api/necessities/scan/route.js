import { NextResponse } from "next/server";
import { checkAppPassword } from "../../../../lib/auth";
import { splitScenes } from "../../../../lib/scenes";
import { extractKeywords, promptForScene } from "../../../../lib/keywords";
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
    const matches = (manifest.images || [])
      .filter((img) => Array.isArray(img.tags) && img.tags.some((t) => tags.includes(t)))
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
