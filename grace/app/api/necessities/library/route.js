import { NextResponse } from "next/server";
import { checkAppPassword } from "../../../../lib/auth";
import { getManifest } from "../../../../lib/library";
import { OWNER, REPO } from "../../../../lib/github";

export async function GET(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const manifest = await getManifest();
  const images = (manifest.images || []).map((img) => ({
    ...img,
    url: `https://raw.githubusercontent.com/${OWNER}/${REPO}/main/${img.path}`,
  }));
  return NextResponse.json({ images });
}
