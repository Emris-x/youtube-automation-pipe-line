import { NextResponse } from "next/server";
import { listRuns, getRepoJsonFile } from "../../../lib/github";
import { checkAppPassword } from "../../../lib/auth";

export async function GET(req) {
  if (!checkAppPassword(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const [runs, logged] = await Promise.all([
    listRuns("manual-video.yml", 15).catch(() => []),
    getRepoJsonFile("data/history.json"),
  ]);

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
