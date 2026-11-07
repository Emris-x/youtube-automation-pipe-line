"""
YouTube upload via the YouTube Data API v3.

This step needs YOUR OWN Google OAuth credentials — that's a one-time setup
only you can do, because it requires logging into your Google account in a
browser and granting consent. I can't do that step for you from here.

One-time setup (10 min):
  1. console.cloud.google.com -> new project -> enable "YouTube Data API v3"
  2. OAuth consent screen -> External -> add your own Google account as a test user
  3. Credentials -> Create OAuth client ID -> Desktop app -> download as client_secret.json
     Put it in this project's root folder.
  4. Run this script once locally (`python src/upload.py --authorize`) — it opens
     a browser, you approve, and it saves a reusable token.json next to it.
  5. After that, every future run (including from a scheduled task) uploads
     automatically with no browser needed, using the saved token.
"""
import argparse
import os

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"


def _materialize_from_env(path, b64_env_var):
    """In CI there's no disk continuity between runs, so client_secret.json
    and token.json travel as base64 repo secrets and get written to disk
    at job start. Locally, the real files just sit here already."""
    if os.path.exists(path):
        return
    b64 = os.environ.get(b64_env_var)
    if b64:
        import base64
        with open(path, "w") as f:
            f.write(base64.b64decode(b64).decode("utf-8"))


def _get_token_from_grace():
    """GRACE (the companion app) owns the Google OAuth flow and keeps the
    refresh token server-side, so the Action never needs client_secret.json
    or token.json at all — it just asks GRACE for a fresh access token each
    run. Preferred path when GRACE_TOKEN_URL + GRACE_API_SECRET are set."""
    url = os.environ.get("GRACE_TOKEN_URL")
    secret = os.environ.get("GRACE_API_SECRET")
    if not (url and secret):
        return None
    import requests
    resp = requests.get(url, headers={"Authorization": f"Bearer {secret}"}, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_authenticated_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    access_token = _get_token_from_grace()
    if access_token:
        creds = Credentials(token=access_token)
        return build("youtube", "v3", credentials=creds)

    _materialize_from_env(CLIENT_SECRET_FILE, "YOUTUBE_CLIENT_SECRET_B64")
    _materialize_from_env(TOKEN_FILE, "YOUTUBE_TOKEN_B64")

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.refresh_token:
            # A token loaded from the authorized_user JSON GRACE wrote has a
            # refresh_token but no access token yet, so `expired` is False
            # (there's no expiry to compare against) even though it still
            # needs refreshing before first use. Refresh whenever a
            # refresh_token is present, not only when expired is True.
            creds.refresh(Request())
        else:
            # No valid token and nothing to refresh -> needs the one-time
            # browser consent. This can't happen headlessly in CI; if it
            # does, the token secret is missing/expired and needs redoing.
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def _check_video_is_real(video_path):
    """Sanity-check the render before spending an upload attempt on it —
    a missing, empty, or zero-duration file fails fast with a clear reason
    instead of crashing deep inside the YouTube client or uploading garbage."""
    if not os.path.exists(video_path):
        raise RuntimeError(f"Build didn't produce a video file at {video_path}")
    if os.path.getsize(video_path) < 1024:
        raise RuntimeError(f"{video_path} is suspiciously small ({os.path.getsize(video_path)} bytes) — likely a broken render")

    import subprocess
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    try:
        duration = float(probe.stdout.strip())
    except (ValueError, TypeError):
        raise RuntimeError(f"ffprobe couldn't read a duration from {video_path} — file is likely corrupt")
    if duration < 1.0:
        raise RuntimeError(f"{video_path} has a {duration:.2f}s duration — too short to be a real video")


def upload_video(video_path, metadata, privacy_status=None):
    privacy_status = privacy_status or os.environ.get("VIDEO_PRIVACY_STATUS", "public")
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    _check_video_is_real(video_path)

    youtube = get_authenticated_service()
    body = {
        "snippet": {
            "title": metadata.get("title") or metadata.get("chosen_title"),
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": "28",  # Science & Technology
        },
        "status": {"privacyStatus": privacy_status},
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    attempt = 0
    max_attempts = 5
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
        except HttpError as e:
            # 5xx and 429 are worth retrying (transient); 4xx like a bad
            # request or expired auth won't fix itself on retry.
            retryable = e.resp.status in (429, 500, 502, 503, 504)
            attempt += 1
            if not retryable or attempt >= max_attempts:
                raise
            wait = min(2 ** attempt, 30)
            print(f"Upload hiccup (HTTP {e.resp.status}), retrying in {wait}s... (attempt {attempt}/{max_attempts})")
            import time
            time.sleep(wait)

    print(f"Done: https://youtube.com/watch?v={response['id']}")
    return response["id"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorize", action="store_true", help="Run one-time browser auth")
    parser.add_argument("--video", help="Path to video file to upload")
    parser.add_argument("--metadata", help="Path to metadata JSON")
    args = parser.parse_args()

    if args.authorize:
        get_authenticated_service()
        print("Authorized. token.json saved — future runs won't need a browser.")
    elif args.video and args.metadata:
        import json
        with open(args.metadata) as f:
            meta = json.load(f)
        result_path = os.path.join(os.path.dirname(args.metadata) or ".", "last_result.json")
        try:
            video_id = upload_video(args.video, meta)
            with open(result_path, "w") as f:
                json.dump(
                    {"video_id": video_id, "video_url": f"https://youtube.com/watch?v={video_id}"},
                    f,
                )
        except Exception as e:
            with open(result_path, "w") as f:
                json.dump({"error": str(e)[:500]}, f)
            raise
    else:
        parser.print_help()
