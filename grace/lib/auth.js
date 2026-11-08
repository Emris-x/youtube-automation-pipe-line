import { timingSafeEqual } from "crypto";

/** Constant-time string comparison -- `===` short-circuits on the first
 * mismatched character, which leaks (very slightly, but measurably over
 * enough requests) how many leading characters a guess got right. Doesn't
 * matter much for a single-user personal app, but it's free to do right. */
function safeEqual(a, b) {
  const bufA = Buffer.from(String(a));
  const bufB = Buffer.from(String(b));
  if (bufA.length !== bufB.length) return false;
  return timingSafeEqual(bufA, bufB);
}

/** This app is a personal tool behind one shared password, with no
 * per-user accounts and (deliberately, for now -- see the audit doc) no
 * real distributed rate limiter, since that would need persistent storage
 * (Redis/KV) this project doesn't otherwise have. A wrong guess instead
 * pays a fixed delay before the response goes out: cheap, needs no
 * infrastructure, and still raises the cost of brute-forcing a reasonable
 * password from "trivial" to "impractical" for anyone without the URL
 * already narrowed down to this one unlisted app. */
async function failDelay() {
  await new Promise((r) => setTimeout(r, 400));
  return false;
}

/** Dead simple single-user gate: one shared password, checked against a
 * header the client sends on every API call. No accounts needed — this is
 * a personal tool for one person. */
export async function checkAppPassword(req) {
  const expected = process.env.GRACE_APP_PASSWORD;
  if (!expected) return true; // not configured -> gate disabled
  const got = req.headers.get("x-grace-password") || "";
  if (safeEqual(got, expected)) return true;
  return failDelay();
}

/** Same check, for the two Google OAuth routes — those are plain browser
 * navigations (a clicked link / a redirect), so there's no way to attach
 * the x-grace-password header; the password travels as a query param
 * instead. Without this, anyone with the app's URL could hit
 * /api/auth/google/start directly and connect their own YouTube account,
 * silently hijacking which channel the pipeline uploads to. */
export async function passwordMatches(value) {
  const expected = process.env.GRACE_APP_PASSWORD;
  if (!expected) return true; // not configured -> gate disabled
  if (safeEqual(value || "", expected)) return true;
  return failDelay();
}
