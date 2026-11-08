import { NextResponse } from "next/server";
import { dispatchWorkflow, latestRun, REPO_URL } from "../../../lib/github";
import { checkAppPassword } from "../../../lib/auth";

export async function POST(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { script_text, title, visual_mode } = await req.json();
  if (!script_text || script_text.trim().length < 20) {
    return NextResponse.json({ error: "Script looks too short." }, { status: 400 });
  }
  const mode = visual_mode === "stickman" ? "stickman" : "pictures";

  try {
    await dispatchWorkflow("manual-video.yml", { script_text, title: title || "", visual_mode: mode });
  } catch (e) {
    return NextResponse.json({ error: `Couldn't start the build: ${e.message}` }, { status: 500 });
  }

  // GitHub's dispatch endpoint doesn't hand back a run id directly, so we
  // poll briefly for the run that just appeared.
  let run = null;
  for (let i = 0; i < 6; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    run = await latestRun("manual-video.yml").catch(() => null);
    if (run && new Date(run.created_at).getTime() > Date.now() - 30000) break;
  }

  return NextResponse.json({
    started: true,
    run_url: run ? run.html_url : `${REPO_URL}/actions`,
    run_id: run ? run.id : null,
  });
}
