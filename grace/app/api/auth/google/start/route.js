import { NextResponse } from "next/server";
import { passwordMatches } from "../../../../../lib/auth";

export async function GET(req) {
  const url = new URL(req.url);
  const pw = url.searchParams.get("pw") || "";
  if (!passwordMatches(pw)) {
    return new NextResponse("Wrong or missing password.", { status: 401 });
  }

  const redirectUri = `${process.env.APP_URL}/api/auth/google/callback`;
  const params = new URLSearchParams({
    client_id: process.env.GOOGLE_CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "https://www.googleapis.com/auth/youtube.upload",
    access_type: "offline", // required to get a refresh_token
    prompt: "consent",      // required to get a refresh_token on every connect, not just the first
    // Round-tripped back to us by Google untouched — doubles as CSRF
    // protection and as how the callback re-checks the app password,
    // since a browser redirect can't carry a custom header.
    state: pw,
  });
  return NextResponse.redirect(`https://accounts.google.com/o/oauth2/v2/auth?${params}`);
}
