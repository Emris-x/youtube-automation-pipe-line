import { NextResponse } from "next/server";
import { dispatchWorkflow, latestRun, REPO_URL } from "../../../lib/github";
import { checkAppPassword } from "../../../lib/auth";

export async function POST(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { script_text, title, visual_mode, input_mode, engine, aspect, host } = await req.json();
  // "turbo" = MoneyPrinterTurbo (stock footage, subtitles, music);
  // "classic" = GRACE's own stickman / pictures renderer. Classic stays the
  // fallback for any caller that doesn't say, so an older cached copy of
  // the app keeps doing exactly what it did before.
  const eng = engine === "turbo" ? "turbo" : "classic";
  const inputMode = input_mode === "idea" ? "idea" : input_mode === "ai" && eng === "turbo" ? "ai" : "script";
  // An AI-written video only needs a topic, so it can be much shorter than
  // a pasted script.
  const minLength = inputMode === "ai" ? 8 : 20;
  if (!script_text || script_text.trim().length < minLength) {
    return NextResponse.json({ error: inputMode === "ai" ? "Topic looks too short." : "Script looks too short." }, { status: 400 });
  }
  const mode = visual_mode === "stickman" ? "stickman" : "pictures";
  const asp = aspect === "16:9" ? "16:9" : "9:16";

  try {
    await dispatchWorkflow("manual-video.yml", {
      script_text,
      title: title || "",
      visual_mode: mode,
      input_mode: inputMode,
      engine: eng,
      aspect: asp,
      host: host === "off" ? "off" : "on",
    });
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
