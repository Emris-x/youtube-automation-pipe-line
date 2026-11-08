import { NextResponse } from "next/server";
import { setRepoSecret } from "../../../../../lib/github";

/**
 * Google redirects here with ?code=... after Emris approves access.
 * We exchange it for a refresh token, shape it exactly like the
 * authorized-user JSON the Python google-auth library expects, and push it
 * straight into the GitHub repo as the YOUTUBE_TOKEN_B64 secret — so the
 * GitHub Action can upload without ever needing a browser.
 */
export async function GET(req) {
  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  const error = url.searchParams.get("error");
  const state = url.searchParams.get("state") || "";

  // CSRF check: `state` must match the random value /start stashed in an
  // httpOnly cookie right before redirecting to Google -- proves this
  // callback is answering a request /start actually issued (which was
  // already password-gated), not a forged redirect someone else crafted
  // and tricked the browser into following. The password itself doesn't
  // travel through this step at all anymore.
  const cookieState = req.cookies.get("grace_oauth_state")?.value;
  const stateOk = cookieState && state && cookieState === state;
  if (!stateOk) {
    return htmlResponse(`This link wasn't started from GRACE itself, or it expired. <a href="/">Try again</a>`, 401);
  }
  if (error) {
    return htmlResponse(`Google said: ${error}. <a href="/">Try again</a>`, 400);
  }
  if (!code) {
    return htmlResponse(`Missing code. <a href="/">Try again</a>`, 400);
  }

  const redirectUri = `${process.env.APP_URL}/api/auth/google/callback`;

  const tokenResp = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: process.env.GOOGLE_CLIENT_ID,
      client_secret: process.env.GOOGLE_CLIENT_SECRET,
      redirect_uri: redirectUri,
      grant_type: "authorization_code",
    }),
  });
  const tokenData = await tokenResp.json();

  if (!tokenResp.ok || !tokenData.refresh_token) {
    return htmlResponse(
      `Google didn't return a refresh token (${JSON.stringify(tokenData)}).<br>` +
      `This usually means the app was already authorized once before without "prompt=consent" — ` +
      `go to <a href="https://myaccount.google.com/permissions" target="_blank">Google Account permissions</a>, ` +
      `remove access for this app, then <a href="/">try connecting again</a>.`,
      400
    );
  }

  // Shape expected by google.oauth2.credentials.Credentials.from_authorized_user_info
  const authorizedUser = {
    type: "authorized_user",
    client_id: process.env.GOOGLE_CLIENT_ID,
    client_secret: process.env.GOOGLE_CLIENT_SECRET,
    refresh_token: tokenData.refresh_token,
  };
  const b64 = Buffer.from(JSON.stringify(authorizedUser)).toString("base64");

  try {
    await setRepoSecret("YOUTUBE_TOKEN_B64", b64);
  } catch (e) {
    return htmlResponse(`Got the YouTube token, but couldn't save it to GitHub: ${e.message}`, 500);
  }

  return htmlResponse(`YouTube connected. You can close this and go back to GRACE. <a href="/">Back to GRACE</a>`, 200);
}

function htmlResponse(message, status) {
  const res = new NextResponse(
    `<!doctype html><html><body style="font-family:sans-serif;background:#060a08;color:#9affc3;padding:2rem;">
      <p>${message}</p>
    </body></html>`,
    { status, headers: { "Content-Type": "text/html" } }
  );
  // One-time use: clear it here so a replayed callback URL (with the same
  // ?state=, say from browser history) can't pass the check a second time.
  res.cookies.delete("grace_oauth_state", { path: "/api/auth/google" });
  return res;
}
