import { NextResponse } from "next/server";
import { checkAppPassword } from "../../../../lib/auth";
import { removeQueuedScript } from "../../../../lib/scripts";

export async function DELETE(req, { params }) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let result;
  try {
    result = await removeQueuedScript(params.id);
  } catch (e) {
    return NextResponse.json({ error: `Couldn't remove it: ${e.message}` }, { status: 500 });
  }
  if (!result.ok) {
    const msg = result.reason === "already_built"
      ? "Already built — it's a record of a real video now, not a draft, so it can't be removed here."
      : "Not found.";
    return NextResponse.json({ error: msg }, { status: result.reason === "already_built" ? 409 : 404 });
  }
  return NextResponse.json({ ok: true });
}
