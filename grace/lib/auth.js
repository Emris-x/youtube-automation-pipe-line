/** Dead simple single-user gate: one shared password, checked against a
 * header the client sends on every API call. No accounts needed — this is
 * a personal tool for one person. */
export function checkAppPassword(req) {
  const expected = process.env.GRACE_APP_PASSWORD;
  if (!expected) return true; // not configured -> gate disabled
  const got = req.headers.get("x-grace-password");
  return got === expected;
}

/** Same check, for the two Google OAuth routes — those are plain browser
 * navigations (a clicked link / a redirect), so there's no way to attach
 * the x-grace-password header; the password travels as a query param /
 * OAuth `state` instead. Without this, anyone with the app's URL could hit
 * /api/auth/google/start directly and connect their own YouTube account,
 * silently hijacking which channel the pipeline uploads to. */
export function passwordMatches(value) {
  const expected = process.env.GRACE_APP_PASSWORD;
  if (!expected) return true; // not configured -> gate disabled
  return value === expected;
}
