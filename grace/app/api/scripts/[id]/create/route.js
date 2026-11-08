import { NextResponse } from "next/server";
import { checkAppPassword } from "../../../../../lib/auth";
import { dispatchWorkflow, latestRun, REPO_URL } from "../../../../../lib/github";
import { getQueue, updateScript } from "../../../../../lib/scripts";

export async function POST(req, { params }) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const queue = await getQueue();
  const item = queue.scripts.find((s) => s.id === params.id);
  if (!item) return NextResponse.json({ error: "Not found." }, { status: 404 });
  if (item.status !== "queued") {
    return NextResponse.json({ error: `Already ${item.status} — not queued anymore.` }, { status: 409 });
  }

  try {
    await dispatchWorkflow("manual-video.yml", {
      script_text: item.script_text,
      title: item.title || "",
      visual_mode: item.visual_mode === "stickman" ? "stickman" : "pictures",
      input_mode: item.input_mode === "idea" ? "idea" : "script",
    });
  } catch (e) {
    return NextResponse.json({ error: `Couldn't start the build: ${e.message}` }, { status: 500 });
  }

  // Same short poll create-video/route.js uses -- GitHub's dispatch
  // endpoint doesn't hand back a run id directly.
  let run = null;
  for (let i = 0; i < 6; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    run = await latestRun("manual-video.yml").catch(() => null);
    if (run && new Date(run.created_at).getTime() > Date.now() - 30000) break;
  }

  // Marked "created" now, optimistically -- it's dispatched and out of the
  // queue either way; the real build/upload outcome is tracked the normal
  // way in data/history.json (same as any other manual-video.yml run), not
  // by this record. This is just "you've already used this script."
  let updated = item;
  try {
    updated = await updateScript(item.id, {
      status: "created",
      run_id: run ? String(run.id) : null,
      run_url: run ? run.html_url : `${REPO_URL}/actions`,
      dispatched_at: new Date().toISOString(),
    });
  } catch (e) {
    // The build is already running regardless -- don't fail the request
    // over a queue bookkeeping write; just say so.
    return NextResponse.json({
      ok: true,
      started: true,
      run_url: run ? run.html_url : `${REPO_URL}/actions`,
      run_id: run ? run.id : null,
      warning: `Started, but couldn't update the queue entry: ${e.message}`,
    });
  }

  return NextResponse.json({
    ok: true,
    started: true,
    run_url: updated.run_url,
    run_id: updated.run_id,
    script: updated,
  });
}
