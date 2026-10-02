# -*- coding: utf-8 -*-
"""
Music-Automat Local Account & Management Server
Allows connecting multiple YouTube channels dynamically via OAuth 2.0.
Saves credentials, manages custom channel profiles, instructions, and test runs.
"""

import os
import sys
import json
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from fastapi import FastAPI, Request, Query, Body, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
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
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIR = BASE_DIR / "frontend"
PROFILES_META_FILE = CONFIG_DIR / "profiles_meta.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

app = FastAPI(title="Music-Automat Multi-Channel Hub")

# In-memory oauth pending states: state -> {"profile": profile, "verifier": verifier}
oauth_states: Dict[str, Dict[str, Any]] = {}


def get_token_file(profile: str) -> Path:
    return TOKENS_DIR / f"token_{profile.lower().strip()}.json"


def load_profiles_meta() -> List[Dict[str, Any]]:
    if not PROFILES_META_FILE.exists():
        default_profiles = [
            {
                "id": "nagpuri",
                "name": "Sumit Rmx 2.0 (Nagpuri)",
                "tag": "नागपुरी DJ Remix",
                "schedule": "09:06 AM IST",
                "color": "cyan",
                "accent_hex": "#00e5ff",
                "instructions": "रीजनल नागपुरी, ठेठ DJ, शादी-पार्टी डांस रिमिक्स (नॉर्मल बास) - 20 सोर्स चैनल्स से ताज़ा ट्रैक लेकर 320 kbps HD मिक्स बनाना।",
                "logo_file": "assets/logo_nagpuri.png",
                "is_default": True
            },
            {
                "id": "vibration",
                "name": "Nagpuri Non-Stop Remix 2.0 (Vibration)",
                "tag": "हार्ड वाइब्रेशन DJ",
                "schedule": "07:00 PM IST",
                "color": "pink",
                "accent_hex": "#ff2a85",
                "instructions": "कंपटीशन हार्ड वाइब्रेशन, बास बूस्टेड, छत्तीसगढ़ी / नागपुरी / भोजपुरी डीजे मिक्स (24 सोर्स चैनल्स) - हेवी वूफर और डीजे कंपटीशन लवर्स के लिए।",
                "logo_file": "assets/logo_vibration.png",
                "is_default": True
            },
            {
                "id": "edm",
                "name": "EDM DJ Remix (Mega EDM Collection)",
                "tag": "EDM Drop Mix",
                "schedule": "06:12 AM IST",
                "color": "purple",
                "accent_hex": "#d200ff",
                "instructions": "EDM ड्रॉप मिक्स, इलेक्ट्रो डांस, क्लब मैशअप, भोजपुरी ईडीएम, ट्रान्स डांस मिक्स (41 सोर्स चैनल्स) - सेंटर में 'My EDM LOGO.png' एनीमेशन।",
                "logo_file": "assets/My EDM LOGO.png",
                "is_default": True
            }
        ]
        PROFILES_META_FILE.write_text(json.dumps(default_profiles, indent=2, ensure_ascii=False), encoding="utf-8")
        return default_profiles

    try:
        return json.loads(PROFILES_META_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Error loading profiles_meta.json: {e}")
        return []


def save_profiles_meta(profiles: List[Dict[str, Any]]) -> None:
    PROFILES_META_FILE.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")


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
    profiles = load_profiles_meta()
    enriched_profiles = []
    connected_count = 0

    for p in profiles:
        pid = p["id"]
        t_info = load_channel_info(pid)
        item = dict(p)
        item["connected"] = t_info.get("connected", False)
        if item["connected"]:
            connected_count += 1
            item["channel_title"] = t_info.get("channel_title", item.get("name"))
            item["custom_url"] = t_info.get("custom_url", "")
            item["channel_id"] = t_info.get("channel_id", "")
            item["thumbnail"] = t_info.get("thumbnail", "")
            item["subscriber_count"] = t_info.get("subscriber_count", "0")
            item["video_count"] = t_info.get("video_count", "0")
            item["refresh_token"] = t_info.get("refresh_token", "")
        else:
            item["channel_title"] = item.get("name")
            item["custom_url"] = f"@{pid}_channel"
            item["channel_id"] = ""
            item["thumbnail"] = ""
            item["subscriber_count"] = "-"
            item["video_count"] = "-"
            item["refresh_token"] = ""
        enriched_profiles.append(item)

    return {
        "profiles": enriched_profiles,
        "total_channels": len(enriched_profiles),
        "connected_count": connected_count
    }


class AddChannelRequest(BaseModel):
    id: str
    name: str
    tag: Optional[str] = "DJ Remix"
    schedule: Optional[str] = "12:00 PM IST"
    instructions: Optional[str] = ""
    accent_hex: Optional[str] = "#00e5ff"
    color: Optional[str] = "cyan"


@app.post("/api/channels/add")
async def add_channel(req: AddChannelRequest):
    # Sanitize ID
    clean_id = req.id.lower().strip().replace(" ", "_")
    clean_id = "".join([c for c in clean_id if c.isalnum() or c == "_"])
    if not clean_id:
        raise HTTPException(status_code=400, detail="Invalid channel ID")

    profiles = load_profiles_meta()
    for p in profiles:
        if p["id"] == clean_id:
            raise HTTPException(status_code=400, detail=f"Channel with ID '{clean_id}' already exists")

    new_profile = {
        "id": clean_id,
        "name": req.name.strip() or f"Channel {clean_id.upper()}",
        "tag": req.tag.strip() or "DJ Remix",
        "schedule": req.schedule.strip() or "12:00 PM IST",
        "color": req.color or "cyan",
        "accent_hex": req.accent_hex or "#00e5ff",
        "instructions": req.instructions.strip() or "नया चैनल - ऑटोमेटेड नॉनस्टॉप डीजे मिक्स।",
        "logo_file": f"assets/logo_{clean_id}.png",
        "is_default": False
    }

    profiles.append(new_profile)
    save_profiles_meta(profiles)

    # Initialize empty list in config/channels.json if needed
    channels_json_path = CONFIG_DIR / "channels.json"
    if channels_json_path.exists():
        try:
            cj = json.loads(channels_json_path.read_text(encoding="utf-8"))
            if clean_id not in cj:
                cj[clean_id] = []
                channels_json_path.write_text(json.dumps(cj, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not update channels.json for new profile {clean_id}: {e}")

    logger.info(f"Added new channel profile: {clean_id} ({new_profile['name']})")
    return {"status": "success", "profile": new_profile}


class UpdateInstructionsRequest(BaseModel):
    profile_id: str
    instructions: str
    schedule: Optional[str] = None


@app.post("/api/channels/update_instructions")
async def update_instructions(req: UpdateInstructionsRequest):
    profiles = load_profiles_meta()
    found = False
    for p in profiles:
        if p["id"] == req.profile_id.lower().strip():
            p["instructions"] = req.instructions.strip()
            if req.schedule:
                p["schedule"] = req.schedule.strip()
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="Profile not found")

    save_profiles_meta(profiles)
    logger.info(f"Updated instructions for profile: {req.profile_id}")
    return {"status": "success", "profile_id": req.profile_id}


@app.post("/api/channels/delete")
async def delete_channel(profile: str = Query(...)):
    clean_id = profile.lower().strip()
    profiles = load_profiles_meta()
    updated = [p for p in profiles if p["id"] != clean_id]

    if len(updated) == len(profiles):
        raise HTTPException(status_code=404, detail="Channel not found")

    save_profiles_meta(updated)

    # Remove token file if present
    t_file = get_token_file(clean_id)
    if t_file.exists():
        t_file.unlink()

    logger.info(f"Deleted profile: {clean_id}")
    return {"status": "success", "deleted_profile": clean_id}


@app.get("/api/auth/login")
async def auth_login(profile: str = Query("nagpuri"), request: Request = None):
    if not CLIENT_SECRETS_FILE.exists():
        return JSONResponse({"error": "client_secrets.json missing in project root"}, status_code=500)

    # Use exact callback URL matching client_secrets.json
    redirect_uri = "http://localhost:8000/api/channels/oauth2callback"

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
        "profile": profile.lower().strip(),
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

    redirect_uri = "http://localhost:8000/api/channels/oauth2callback"

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
    t_file = get_token_file(profile.lower().strip())
    if t_file.exists():
        t_file.unlink()
        logger.info(f"Disconnected channel profile: {profile}")
    return {"status": "success", "profile": profile}


@app.post("/api/run_mix")
async def trigger_run(profile: str = Query("nagpuri")):
    def _run_bg():
        cmd = [sys.executable, "-m", "src.pipeline", "--profile", profile.lower().strip(), "--target-tracks", "3", "--skip-upload"]
        subprocess.run(cmd, cwd=str(BASE_DIR))

    t = threading.Thread(target=_run_bg, daemon=True)
    t.start()
    return {"status": "started", "profile": profile}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.server:app", host="127.0.0.1", port=8000, reload=True)
