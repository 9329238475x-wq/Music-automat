"""
Music-Automat Local Account & Management Server
Allows connecting both YouTube channels (Nagpuri & Vibration) via OAuth 2.0.
Saves credentials and exposes API for checking channel status and test running.
"""

import os
import sys
import json
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Server")

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_SECRETS_FILE = BASE_DIR / "client_secrets.json"
TOKENS_DIR = BASE_DIR / "tokens"
TOKENS_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIR = BASE_DIR / "frontend"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

app = FastAPI(title="Music-Automat Hub")

# In-memory oauth pending states: state -> {"profile": profile, "verifier": verifier}
oauth_states = {}


def get_token_file(profile: str) -> Path:
    return TOKENS_DIR / f"token_{profile.lower()}.json"


def load_channel_info(profile: str) -> Dict[str, Any]:
    t_file = get_token_file(profile)
    if not t_file.exists():
        return {"connected": False}
    try:
        data = json.loads(t_file.read_text(encoding="utf-8"))
        data["connected"] = True
        return data
    except Exception as e:
        logger.warning(f"Failed to read token for {profile}: {e}")
        return {"connected": False}


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)


@app.get("/api/status")
async def get_status():
    nagpuri_info = load_channel_info("nagpuri")
    vibration_info = load_channel_info("vibration")
    return {
        "nagpuri": nagpuri_info,
        "vibration": vibration_info,
        "schedule": {
            "morning": "09:06 AM IST (Nagpuri)",
            "evening": "07:00 PM IST (Vibration)"
        }
    }


@app.get("/api/auth/login")
async def auth_login(profile: str = Query("nagpuri"), request: Request = None):
    if not CLIENT_SECRETS_FILE.exists():
        return JSONResponse({"error": "client_secrets.json missing in project root"}, status_code=500)

    # Use exact callback URL matching client_secrets.json
    redirect_uri = f"{request.base_url._url.rstrip('/')}/api/channels/oauth2callback"

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRETS_FILE),
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    auth_url, state = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true"
    )

    oauth_states[state] = {
        "profile": profile.lower(),
        "verifier": getattr(flow, "code_verifier", None)
    }

    return RedirectResponse(auth_url)


@app.get("/api/channels/oauth2callback")
async def oauth2_callback(request: Request, code: str = Query(None), state: str = Query(None)):
    if not code:
        return HTMLResponse("<h3>Authorization error: No code received</h3>", status_code=400)

    state_data = oauth_states.pop(state, {})
    profile = state_data.get("profile", "nagpuri")
    code_verifier = state_data.get("verifier")

    redirect_uri = f"{request.base_url._url.rstrip('/')}/api/channels/oauth2callback"

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRETS_FILE),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
        state=state
    )
    if code_verifier:
        flow.code_verifier = code_verifier

    flow.fetch_token(code=code)
    creds = flow.credentials

    # Query YouTube for channel identity
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()

    items = resp.get("items", [])
    if not items:
        return HTMLResponse("<h3>No YouTube channel found for this Google account!</h3>", status_code=400)

    ch = items[0]
    ch_id = ch["id"]
    snippet = ch.get("snippet", {})
    stats = ch.get("statistics", {})

    token_payload = {
        "profile": profile,
        "channel_id": ch_id,
        "channel_title": snippet.get("title", ""),
        "custom_url": snippet.get("customUrl", ""),
        "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
        "subscriber_count": stats.get("subscriberCount", "0"),
        "video_count": stats.get("videoCount", "0"),
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }

    t_file = get_token_file(profile)
    t_file.write_text(json.dumps(token_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Connected {profile} channel: {snippet.get('title')} ({ch_id})")

    return RedirectResponse(url="/")


@app.post("/api/auth/disconnect")
async def disconnect_channel(profile: str = Query("nagpuri")):
    t_file = get_token_file(profile)
    if t_file.exists():
        t_file.unlink()
        logger.info(f"Disconnected channel profile: {profile}")
    return {"status": "success", "profile": profile}


@app.post("/api/run_mix")
async def trigger_run(profile: str = Query("nagpuri")):
    def _run_bg():
        cmd = [sys.executable, "-m", "src.pipeline", "--profile", profile, "--target-tracks", "3", "--skip-upload"]
        subprocess.run(cmd, cwd=str(BASE_DIR))

    t = threading.Thread(target=_run_bg, daemon=True)
    t.start()
    return {"status": "started", "profile": profile}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.server:app", host="127.0.0.1", port=8000, reload=True)
