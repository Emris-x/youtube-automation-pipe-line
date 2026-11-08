import { NextResponse } from "next/server";
import { hasRepoSecret } from "../../../lib/github";
import { checkAppPassword } from "../../../lib/auth";

export async function GET(req) {
  if (!(await checkAppPassword(req))) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const connected = await hasRepoSecret("YOUTUBE_TOKEN_B64");
  return NextResponse.json({ connected });
}
