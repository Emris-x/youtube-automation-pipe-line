import { NextResponse } from "next/server";
import { ghFetch, setRepoSecret, OWNER, REPO } from "../../../lib/github";
import { checkAppPassword } from "../../../lib/auth";

// The only secrets this route may read the presence of, or write. A fixed
// allowlist: without it, anyone holding the app password could overwrite
// any repo secret by name (YOUTUBE_TOKEN_B64 included).
const KEYS = {
  pexels: "PEXELS_API_KEY",
  pixabay: "PIXABAY_API_KEY",
  groq: "GROQ_API_KEY",
  gemini: "GEMINI_API_KEY",
};

/** Which turbo-engine keys are set. Only ever reports yes/no -- GitHub's
 * API never returns a secret's value, and neither does this. */
export async function GET(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  try {
    const list = await ghFetch(`/repos/${OWNER}/${REPO}/actions/secrets?per_page=100`);
    const names = new Set((list.secrets || []).map((s) => s.name));
    const out = {};
    for (const [id, name] of Object.entries(KEYS)) out[id] = names.has(name);
    return NextResponse.json({ keys: out });
  } catch (e) {
    return NextResponse.json({ error: `Couldn't read key status: ${e.message}` }, { status: 500 });
  }
}

/** Saves one key straight into the repo's encrypted Actions secrets, so
 * it can be set from a phone and never has to be sent to anyone. */
export async function POST(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id, value } = await req.json().catch(() => ({}));
  const name = KEYS[id];
  const clean = typeof value === "string" ? value.trim() : "";
  if (!name) return NextResponse.json({ error: "Unknown key." }, { status: 400 });
  if (clean.length < 10 || clean.length > 300 || /\s/.test(clean)) {
    return NextResponse.json({ error: "That doesn't look like a key -- paste it exactly, no spaces." }, { status: 400 });
  }
  try {
    await setRepoSecret(name, clean);
  } catch (e) {
    return NextResponse.json({ error: `Couldn't save the key: ${e.message}` }, { status: 500 });
  }
  return NextResponse.json({ ok: true, id });
}
