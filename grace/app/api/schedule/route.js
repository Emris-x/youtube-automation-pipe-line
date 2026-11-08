import { NextResponse } from "next/server";
import { checkAppPassword } from "../../../lib/auth";
import { getQueue, getSchedule, setSchedule } from "../../../lib/scripts";

export async function GET(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const [schedule, queue] = await Promise.all([getSchedule(), getQueue()]);
  const remaining = queue.scripts.filter((s) => s.status === "queued").length;
  return NextResponse.json({ ...schedule, remaining_queued: remaining });
}

export async function POST(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await req.json();
  const patch = {};
  if (typeof body.enabled === "boolean") patch.enabled = body.enabled;
  if (body.interval_hours != null) {
    const n = Number(body.interval_hours);
    if (!Number.isFinite(n) || n < 1 || n > 168) {
      return NextResponse.json({ error: "interval_hours must be between 1 and 168." }, { status: 400 });
    }
    patch.interval_hours = Math.round(n);
  }
  if (Object.keys(patch).length === 0) {
    return NextResponse.json({ error: "Nothing to update." }, { status: 400 });
  }

  try {
    const updated = await setSchedule(patch);
    const queue = await getQueue();
    const remaining = queue.scripts.filter((s) => s.status === "queued").length;
    return NextResponse.json({ ...updated, remaining_queued: remaining });
  } catch (e) {
    return NextResponse.json({ error: `Couldn't update the schedule: ${e.message}` }, { status: 500 });
  }
}
