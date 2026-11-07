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


def get_authenticated_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    _materialize_from_env(CLIENT_SECRET_FILE, "YOUTUBE_CLIENT_SECRET_B64")
    _materialize_from_env(TOKEN_FILE, "YOUTUBE_TOKEN_B64")

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
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


def upload_video(video_path, metadata, privacy_status=None):
    privacy_status = privacy_status or os.environ.get("VIDEO_PRIVACY_STATUS", "public")
    from googleapiclient.http import MediaFileUpload

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
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")
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
        upload_video(args.video, meta)
    else:
        parser.print_help()
