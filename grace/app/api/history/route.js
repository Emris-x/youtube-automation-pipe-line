import { NextResponse } from "next/server";
import { listRuns, getRepoJsonFile } from "../../../lib/github";
import { checkAppPassword } from "../../../lib/auth";

// Every workflow that can produce a video and log to data/history.json --
// previously this only polled manual-video.yml, so a run from the
// scheduled daily pipeline or the scripts queue could be correctly logged
// to history.json and still never show up here, because it was never in
// the `runs` list being mapped over in the first place.
const WORKFLOWS = ["manual-video.yml", "daily-video.yml", "scripts-queue.yml"];

export async function GET(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const [runsByWorkflow, logged] = await Promise.all([
    Promise.all(WORKFLOWS.map((wf) => listRuns(wf, 15).catch(() => []))),
    getRepoJsonFile("data/history.json"),
  ]);
  const runs = runsByWorkflow.flat().sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  const byRunId = new Map((logged || []).map((e) => [String(e.run_id), e]));

  const items = runs.map((r) => {
    if (r.status !== "completed") {
      return {
        run_id: r.id,
        run_url: r.html_url,
        title: r.display_title,
        status: r.status === "queued" ? "queued" : "running",
        timestamp: r.created_at,
      };
    }
    const logged_entry = byRunId.get(String(r.id));
    if (logged_entry) return logged_entry;
    // Completed but the log-result step itself didn't manage to log it —
    // fall back to GitHub's own pass/fail verdict so it still shows up.
    return {
      run_id: r.id,
      run_url: r.html_url,
      title: r.display_title,
      status: r.conclusion === "success" ? "uploaded" : "failed",
      failed_step: null,
      error: null,
      video_url: null,
      timestamp: r.updated_at,
    };
  });

  return NextResponse.json({ history: items });
}
