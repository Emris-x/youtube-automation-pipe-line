import { randomBytes } from "crypto";
import { NextResponse } from "next/server";
import { passwordMatches } from "../../../../../lib/auth";

export async function GET(req) {
  const url = new URL(req.url);
  const pw = url.searchParams.get("pw") || "";
  if (!(await passwordMatches(pw))) {
    return new NextResponse("Wrong or missing password.", { status: 401 });
  }

  // A real random, single-use CSRF token -- NOT the app password. The
  // password was previously round-tripped as `state` itself: it worked as
  // a password re-check on the callback, but it's not what `state` is for
  // (an unguessable value proving the callback answers THIS browser's
  // request, not just that the caller knows the shared password -- and
  // reusing the password this way means it travels through Google's OAuth
  // redirect and shows up in server/proxy logs along the way). The random
  // value below goes in `state`; the password check already happened
  // above, before we ever redirect to Google, so there's nothing left for
  // the callback to re-verify except that `state` round-tripped intact.
  const state = randomBytes(24).toString("base64url");

  const redirectUri = `${process.env.APP_URL}/api/auth/google/callback`;
  const params = new URLSearchParams({
    client_id: process.env.GOOGLE_CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "https://www.googleapis.com/auth/youtube.upload",
    access_type: "offline", // required to get a refresh_token
    prompt: "consent",      // required to get a refresh_token on every connect, not just the first
    state,
  });
  const res = NextResponse.redirect(`https://accounts.google.com/o/oauth2/v2/auth?${params}`);
  // httpOnly + Secure + SameSite=Lax: sent back to us on the top-level GET
  // redirect Google sends the browser on, unreadable from any page script,
  // and short-lived (the whole OAuth round trip takes under a minute).
  res.cookies.set("grace_oauth_state", state, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    maxAge: 600,
    path: "/api/auth/google",
  });
  return res;
}
