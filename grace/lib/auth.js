/** Dead simple single-user gate: one shared password, checked against a
 * header the client sends on every API call. No accounts needed — this is
 * a personal tool for one person. */
export function checkAppPassword(req) {
  const expected = process.env.GRACE_APP_PASSWORD;
  if (!expected) return true; // not configured -> gate disabled
  const got = req.headers.get("x-grace-password");
  return got === expected;
}
