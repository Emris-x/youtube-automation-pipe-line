import { NextResponse } from "next/server";
import { checkAppPassword } from "../../../lib/auth";
import { getQueue, addScripts, nextScriptId } from "../../../lib/scripts";

// Splits a bulk paste into individual scripts on a line that's just "---"
// (optionally surrounded by whitespace) on its own -- lets you drop in a
// whole batch (e.g. 10 pre-written scripts for the week) in one paste
// instead of one API call per script. A paste with no "---" at all is
// just one script.
function splitBulk(text) {
  return text
    .split(/\n[ \t]*---[ \t]*\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export async function GET(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const queue = await getQueue();
  return NextResponse.json({ scripts: queue.scripts });
}

export async function POST(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await req.json();
  const rawTexts = Array.isArray(body.scripts)
    ? body.scripts.map((s) => String(s || "").trim()).filter(Boolean)
    : splitBulk(String(body.script_text || ""));

  const texts = rawTexts.filter((t) => t.length >= 20);
  if (texts.length === 0) {
    return NextResponse.json({ error: "No script text found (each script needs at least ~20 characters)." }, { status: 400 });
  }

  const visualMode = body.visual_mode === "stickman" ? "stickman" : "pictures";
  // "script": script_text is a finished script. "idea": script_text is a
  // one-line idea + bullet facts for the free rule-based director (director.py)
  // to shape into a script -- no AI call, zero cost.
  const inputMode = body.input_mode === "idea" ? "idea" : "script";

  const queue = await getQueue();
  let nextId = nextScriptId(queue);
  const entries = texts.map((script_text) => {
    const id = nextId;
    nextId = `s_${String(parseInt(id.slice(2), 10) + 1).padStart(4, "0")}`;
    return {
      id,
      title: body.title && texts.length === 1 ? body.title : null, // a shared title only makes sense for a single script
      script_text,
      input_mode: inputMode,
      visual_mode: visualMode, // used by the "create now" button; scheduled auto-dispatch uses the schedule's own mode instead
      status: "queued",
      created_at: new Date().toISOString(),
    };
  });

  try {
    await addScripts(entries);
  } catch (e) {
    return NextResponse.json({ error: `Couldn't save to the queue: ${e.message}` }, { status: 500 });
  }

  return NextResponse.json({ ok: true, added: entries.length, scripts: entries });
}
