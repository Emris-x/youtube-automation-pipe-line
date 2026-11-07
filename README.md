# YouTube Automation Pipeline

**Series: "How It Actually Broke"** — real, documented tech incidents (outages,
breaches, software failures) explained in 60-90 seconds, blueprint/hacker-terminal
visual style, vertical (Shorts). Script → voiceover → synced motion graphics →
upload, runs on a schedule via GitHub Actions.

## What's in here

```
src/
  generate_script.py   topic -> full scene script (needs ANTHROPIC_API_KEY)
  tts.py                script text -> voiceover + word timing
  motion.py             word timing -> motion graphics clip (terminal theme)
  build_video.py        runs tts+motion per scene, assembles final MP4
  upload.py             uploads finished video to YouTube
  run_pipeline.py        runs all of the above in one command
scripts/
  topics.json           queue of incidents to turn into videos
  video_*.json           generated scripts land here
.github/workflows/
  daily-video.yml        the schedule that runs it all automatically
```

## GRACE — the phone app

`grace/` is a small Next.js PWA, deployed to Vercel at
**https://grace-app-emris-xs-projects.vercel.app** (also aliased to
grace-app-three.vercel.app), linked to this repo so every push to `main`
redeploys it. It's the normal way to use this project from a phone:

1. Open the URL, unlock with the password (`GRACE_APP_PASSWORD`, set in Vercel)
2. Tap **connect YouTube** once — Google login happens right there, no
   desktop needed. GRACE writes the resulting token straight into this
   repo's `YOUTUBE_TOKEN_B64` secret itself.
3. Paste a script (blank line between each scene), tap **./create_video** —
   that fires the `manual-video.yml` workflow below and hands back a link
   to watch it build and upload.

GRACE needs its own one-time setup, below — once that's done, everything
after is phone-only, no computer required for any step.

## One-time setup (has to be done by you — can't be automated)

### 1. Google OAuth client (for GRACE's "connect YouTube" button)
1. console.cloud.google.com → new project → enable **YouTube Data API v3**
2. OAuth consent screen → External → add your own Google account as a test user
3. Credentials → Create OAuth client ID → **Web application** (not Desktop)
   → Authorized redirect URI:
   `https://grace-app-emris-xs-projects.vercel.app/api/auth/google/callback`
4. Send me the Client ID and Client Secret it gives you — I'll set them as
   `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in GRACE's Vercel project.

**Known friction point, stated plainly:** while the OAuth consent screen is
in "Testing" status, Google expires the connection after ~7 days — you'd
need to tap "connect YouTube" again weekly. Fix: submit the consent screen
for verification (Google walks you through it; needs a short demo +
privacy policy link). I can help with that when you get there.

### 2. A GitHub token (so GRACE can trigger builds and save the YouTube connection)
1. github.com → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token
2. Repository access → Only select repositories → `youtube-automation-pipe-line`
3. Permissions → **Actions: Read and write**, **Secrets: Read and write**
4. Send me the token — I'll set it as `GITHUB_PAT` in GRACE's Vercel project.

### 3. Pick a password for GRACE itself
Any phone-typeable password — tell me what you want and I'll set it as
`GRACE_APP_PASSWORD`. (Skippable, but then the app has no gate at all.)

### 4. (Optional) Anthropic API key — only if you want auto-written scripts back
Since you're writing scripts yourself, this isn't needed. If you change
your mind later: console.anthropic.com → create a key → add as the
`ANTHROPIC_API_KEY` repo secret → the original `daily-video.yml` schedule
(topic queue → AI script → video, no typing) becomes usable again.

### 5. (Optional, recommended once you've heard a sample) ElevenLabs for a real voice
- elevenlabs.io → free tier API key
- Add as repo secret `ELEVENLABS_API_KEY` — `tts.py` picks it up automatically
  and uses it instead of edge-tts. Until then, edge-tts (free, no key) is
  used automatically and sounds decent — just not as good as ElevenLabs.

## Running it

**Locally** (needs real internet for edge-tts/ElevenLabs + YouTube upload):
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
python src/run_pipeline.py            # generate -> build -> upload
python src/run_pipeline.py --no-upload   # just build, skip uploading
```

**On GitHub Actions:** once the secrets above are set, it runs automatically
on the schedule in `.github/workflows/daily-video.yml` (currently daily —
edit the cron line to change it), or trigger it manually from the repo's
Actions tab → "Daily Video" → "Run workflow" (there's an `upload: false`
option there for a dry run that builds but doesn't post).

## Adding more topics

Edit `scripts/topics.json`, add entries with `"status": "pending"`. The
pipeline always takes the first pending one and flips it to `"done"` after.
Keep the incidents real and specific — that specificity is most of what
makes the hook work; it's also a hard requirement, since the script writer
is told to only use verifiable facts.

## Honest limits

- **No guarantee of income or views.** YouTube Partner Program requires
  1,000 subscribers + (4,000 watch hours or 10M Shorts views/year) before
  any ad revenue is possible at all. This pipeline gets you consistent
  posting; whether any given video gets traction depends on the hook, the
  topic's real-world pull, and the algorithm, same as any channel.
- **Don't switch the voice or visual theme once you've posted a few
  videos** — consistency is what builds channel recognition; the code
  supports swapping both, but do it before video #1, not every few videos.
- **Track what works.** Check YouTube Studio's analytics (retention curve,
  especially the first 3 seconds) weekly and feed what you learn back into
  `generate_script.py`'s hook rules or `scripts/topics.json`'s ordering.
