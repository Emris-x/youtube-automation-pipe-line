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

## One-time setup (has to be done by you — can't be automated)

### 1. Anthropic API key (for script writing)
- console.anthropic.com → create an API key
- Repo → Settings → Secrets and variables → Actions → New repository secret
  → name `ANTHROPIC_API_KEY`, paste the key

### 2. YouTube upload access
This is the fiddly one because Google requires an actual browser login once.

1. console.cloud.google.com → new project → enable **YouTube Data API v3**
2. OAuth consent screen → External → add your own Google account as a test user
3. Credentials → Create OAuth client ID → **Desktop app** → download the JSON,
   save it as `client_secret.json` in this project's root (on your own
   computer, NOT committed to git — it's in `.gitignore`)
4. On your computer, with Python installed:
   ```
   pip install -r requirements.txt
   python src/upload.py --authorize
   ```
   This opens a browser, you log in and approve, and it saves `token.json`
   next to `client_secret.json`.
5. Turn both into secrets so GitHub Actions can use them without a browser:
   ```
   base64 -i client_secret.json | tr -d '\n'   # copy this value
   base64 -i token.json | tr -d '\n'            # copy this value
   ```
   Add as repo secrets: `YOUTUBE_CLIENT_SECRET_B64`, `YOUTUBE_TOKEN_B64`

**Known friction point, stated plainly:** while your Google Cloud OAuth
consent screen is in "Testing" status, Google expires refresh tokens after
~7 days — which would quietly break the automation every week. If uploads
start failing after about a week with an auth error, that's what's
happening. Fix: submit the OAuth consent screen for verification (Google
walks you through it; needs a short demo + privacy policy link). I can help
with that step when you hit it — flagging it now so it's not a surprise.

### 3. (Optional, recommended once you've seen a sample) ElevenLabs for a real voice
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
