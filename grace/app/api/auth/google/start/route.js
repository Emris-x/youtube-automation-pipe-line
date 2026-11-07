import { NextResponse } from "next/server";

export async function GET(req) {
  const redirectUri = `${process.env.APP_URL}/api/auth/google/callback`;
  const params = new URLSearchParams({
    client_id: process.env.GOOGLE_CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "https://www.googleapis.com/auth/youtube.upload",
    access_type: "offline", // required to get a refresh_token
    prompt: "consent",      // required to get a refresh_token on every connect, not just the first
  });
  return NextResponse.redirect(`https://accounts.google.com/o/oauth2/v2/auth?${params}`);
}
