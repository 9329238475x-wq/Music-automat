# -*- coding: utf-8 -*-
"""
Music-Automat Local Account & Management Server
- Live Google OAuth 2.0 Token Health Verification (Detects expired tokens instantly)
- 7-Day Countdown Timer for Testing Mode
- 1-Click Sync to GitHub Repository Secrets (PyNaCl libsodium encryption)
- Cloudflare Tunnel & Mobile Remote Access Integration
"""

import os
import sys
import json
import time
import socket
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

import requests
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI, Request, Query, Body, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.github_sync import (
    sync_all_secrets_to_github,
    get_stored_github_token,
    save_github_token,
    get_repo_owner_name,
    get_manual_secrets_dump
)

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
TOOLS_DIR = BASE_DIR / "tools"
CLOUDFLARED_EXE = TOOLS_DIR / "cloudflared.exe"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

app = FastAPI(title="Music-Automat Multi-Channel Hub")

# Global state for tunnel and token verification caching
PUBLIC_TUNNEL_URL: Optional[str] = None
TOKEN_HEALTH_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 45  # Re-verify with Google every 45s unless forced

OAUTH_STATES_FILE = TOKENS_DIR / "oauth_pending_states.json"


def get_oauth_states() -> Dict[str, Any]:
    if OAUTH_STATES_FILE.exists():
        try:
            return json.loads(OAUTH_STATES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_oauth_states(states: Dict[str, Any]):
    try:
        OAUTH_STATES_FILE.write_text(json.dumps(states, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to persist oauth states: {e}")


def get_token_file(profile: str) -> Path:
    return TOKENS_DIR / f"token_{profile.lower().strip()}.json"


def get_local_lan_ip() -> str:
    """Find local network IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def start_tunnel_background():
    """Launch Cloudflare Quick Tunnel in background if binary exists."""
    global PUBLIC_TUNNEL_URL
    if not CLOUDFLARED_EXE.exists():
        logger.info("Cloudflared binary not found; skipping automatic tunnel.")
        return

    def _worker():
        global PUBLIC_TUNNEL_URL
        import re
        cmd = [str(CLOUDFLARED_EXE), "tunnel", "--url", "http://127.0.0.1:8000"]
        logger.info("Starting Cloudflare Quick Tunnel...")
        try:
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
            for line in proc.stderr:
                match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", line)
                if match:
                    PUBLIC_TUNNEL_URL = match.group(0)
                    logger.info("=" * 65)
                    logger.info(f"🌍 CLOUDFLARE PUBLIC TUNNEL ACTIVE: {PUBLIC_TUNNEL_URL}")
                    logger.info(f"📱 MOBILE ACCESS URL: {PUBLIC_TUNNEL_URL}")
                    logger.info("=" * 65)
                    break
        except Exception as e:
            logger.warning(f"Cloudflare tunnel error: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# Launch tunnel upon startup
start_tunnel_background()


def check_token_health(profile: str, data: Dict[str, Any], file_mtime: float, force: bool = False) -> Dict[str, Any]:
    """
    Real-time Google OAuth Token Verification & 7-Day Countdown Engine.
    Queries Google OAuth endpoint to guarantee the refresh token is truly alive.
    """
    now = time.time()
    cache_key = profile.lower().strip()

    if not force and cache_key in TOKEN_HEALTH_CACHE:
        cached = TOKEN_HEALTH_CACHE[cache_key]
        if now - cached.get("checked_at", 0) < CACHE_TTL_SECONDS:
            # Recompute countdown based on current time
            connected_at = cached.get("connected_at", file_mtime)
            age_sec = max(0, now - connected_at)
            SEVEN_DAYS = 7 * 24 * 3600
            seconds_left = max(0, SEVEN_DAYS - age_sec)
            cached["seconds_left"] = int(seconds_left)
            cached["days_left"] = int(seconds_left // 86400)
            cached["hours_left"] = int((seconds_left % 86400) // 3600)
            cached["mins_left"] = int((seconds_left % 3600) // 60)
            return cached

    connected_at = data.get("connected_at", file_mtime)
    age_sec = max(0, now - connected_at)
    SEVEN_DAYS = 7 * 24 * 3600
    seconds_left = max(0, SEVEN_DAYS - age_sec)
    days_left = int(seconds_left // 86400)
    hours_left = int((seconds_left % 86400) // 3600)
    mins_left = int((seconds_left % 3600) // 60)

    token_uri = data.get("token_uri", "https://oauth2.googleapis.com/token")
    client_id = data.get("client_id", "")
    client_secret = data.get("client_secret", "")
    refresh_token = data.get("refresh_token", "")

    if not (client_id and client_secret and refresh_token):
        res = {
            "is_valid": False,
            "mode": "invalid",
            "badge": "❌ टोकन डेटा अधूरा",
            "seconds_left": 0,
            "days_left": 0,
            "hours_left": 0,
            "mins_left": 0,
            "connected_at": connected_at,
            "error_msg": "Missing client credentials or refresh token",
            "checked_at": now
        }
        TOKEN_HEALTH_CACHE[cache_key] = res
        return res

    # Live verification ping with Google OAuth API
    try:
        resp = requests.post(token_uri, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }, timeout=6)

        if resp.status_code == 200:
            # Token is 100% active and working
            if age_sec > SEVEN_DAYS:
                # Survived 7 days -> Application is Published / In Production!
                badge = "👑 परमानेंट एक्टिव (No 7-Day Limit)"
                mode = "production"
            else:
                badge = f"⏳ {days_left} दिन {hours_left} घंटे बाकी"
                mode = "testing"

            res = {
                "is_valid": True,
                "mode": mode,
                "badge": badge,
                "seconds_left": int(seconds_left),
                "days_left": days_left,
                "hours_left": hours_left,
                "mins_left": mins_left,
                "connected_at": connected_at,
                "error_msg": None,
                "checked_at": now
            }
        else:
            # Token revoked or expired by Google!
            err_json = {}
            try:
                err_json = resp.json()
            except Exception:
                pass
            err_desc = err_json.get("error_description", resp.text)
            logger.warning(f"Token expired for {profile}: {err_desc}")
            res = {
                "is_valid": False,
                "mode": "expired",
                "badge": "⚠️ टोकन एक्सपायर (7-दिन पूरे)",
                "seconds_left": 0,
                "days_left": 0,
                "hours_left": 0,
                "mins_left": 0,
                "connected_at": connected_at,
                "error_msg": err_desc,
                "checked_at": now
            }
    except Exception as e:
        # Fallback in case of temporary network timeout
        logger.warning(f"Network error checking token for {profile}: {e}")
        is_val = seconds_left > 0
        res = {
            "is_valid": is_val,
            "mode": "testing" if is_val else "expired",
            "badge": f"⏳ {days_left} दिन {hours_left} घंटे बाकी" if is_val else "⚠️ टोकन एक्सपायर (ऑफलाइन)",
            "seconds_left": int(seconds_left),
            "days_left": days_left,
            "hours_left": hours_left,
            "mins_left": mins_left,
            "connected_at": connected_at,
            "error_msg": f"नेटवर्क चेक विफल: {str(e)}",
            "checked_at": now
        }

    TOKEN_HEALTH_CACHE[cache_key] = res
    return res


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


def load_channel_info(profile: str, force_verify: bool = False) -> Dict[str, Any]:
    t_file = get_token_file(profile)
    if not t_file.exists():
        return {
            "connected": False,
            "is_expired": False,
            "health": {
                "is_valid": False,
                "badge": "डिसकनेक्टेड",
                "mode": "disconnected",
                "seconds_left": 0
            }
        }
    try:
        data = json.loads(t_file.read_text(encoding="utf-8"))
        mtime = os.path.getmtime(t_file)
        health = check_token_health(profile, data, mtime, force=force_verify)

        # Real connection state: only connected if Google says valid!
        is_really_connected = health.get("is_valid", False)
        data["connected"] = is_really_connected
        data["is_expired"] = not is_really_connected and health.get("mode") == "expired"
        data["health"] = health
        return data
    except Exception as e:
        logger.warning(f"Failed to read token for {profile}: {e}")
        return {
            "connected": False,
            "is_expired": False,
            "health": {
                "is_valid": False,
                "badge": "रीड एरर",
                "mode": "error",
                "seconds_left": 0
            }
        }


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)


@app.get("/api/status")
async def get_status(force: bool = False):
    profiles = load_profiles_meta()
    enriched_profiles = []
    connected_count = 0
    expired_count = 0

    for p in profiles:
        pid = p["id"]
        t_info = load_channel_info(pid, force_verify=force)
        item = dict(p)
        item["connected"] = t_info.get("connected", False)
        item["is_expired"] = t_info.get("is_expired", False)
        item["health"] = t_info.get("health", {})

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
            if item["is_expired"]:
                expired_count += 1
            item["channel_title"] = t_info.get("channel_title") or item.get("name")
            item["custom_url"] = t_info.get("custom_url") or f"@{pid}_channel"
            item["channel_id"] = t_info.get("channel_id", "")
            item["thumbnail"] = t_info.get("thumbnail", "")
            item["subscriber_count"] = t_info.get("subscriber_count", "-")
            item["video_count"] = t_info.get("video_count", "-")
            item["refresh_token"] = ""
        enriched_profiles.append(item)

    owner, repo = get_repo_owner_name()
    gh_token = get_stored_github_token()

    return {
        "profiles": enriched_profiles,
        "total_channels": len(enriched_profiles),
        "connected_count": connected_count,
        "expired_count": expired_count,
        "network": {
            "local_url": "http://localhost:8000",
            "lan_url": f"http://{get_local_lan_ip()}:8000",
            "tunnel_url": PUBLIC_TUNNEL_URL
        },
        "github": {
            "repo": f"{owner}/{repo}",
            "has_token": bool(gh_token)
        }
    }


@app.post("/api/channels/verify_all")
async def verify_all_tokens():
    """Force real-time re-verification of all channel tokens."""
    TOKEN_HEALTH_CACHE.clear()
    return await get_status(force=True)


class SyncGitHubRequest(BaseModel):
    token: Optional[str] = None


@app.post("/api/github/sync_secrets")
async def api_sync_secrets(req: SyncGitHubRequest = Body(default_factory=SyncGitHubRequest)):
    """Uploads active channel refresh tokens directly to GitHub Actions Secrets."""
    res = sync_all_secrets_to_github(gh_token=req.token)
    if not res.get("success") and res.get("error_type") == "NO_TOKEN":
        return JSONResponse(status_code=400, content=res)
    elif not res.get("success"):
        return JSONResponse(status_code=500, content=res)
    return res


@app.get("/api/github/manual_secrets")
async def api_manual_secrets():
    """Provides key-value pairs for 1-click clipboard copying."""
    dump = get_manual_secrets_dump()
    return {"secrets": dump}


class SaveGitHubTokenRequest(BaseModel):
    token: str


@app.post("/api/github/save_token")
async def api_save_github_token(req: SaveGitHubTokenRequest):
    if not req.token.strip():
        raise HTTPException(status_code=400, detail="Token cannot be empty")
    save_github_token(req.token)
    owner, repo = get_repo_owner_name()
    return {"status": "success", "repo": f"{owner}/{repo}"}


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

    t_file = get_token_file(clean_id)
    if t_file.exists():
        t_file.unlink()
    TOKEN_HEALTH_CACHE.pop(clean_id, None)

    logger.info(f"Deleted profile: {clean_id}")
    return {"status": "success", "deleted_profile": clean_id}


@app.get("/api/auth/login")
async def auth_login(profile: str = Query("nagpuri"), request: Request = None):
    if not CLIENT_SECRETS_FILE.exists():
        return JSONResponse({"error": "client_secrets.json missing in project root"}, status_code=500)

    # Use standard localhost redirect URI
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

    states = get_oauth_states()
    states[state] = {
        "profile": profile.lower().strip(),
        "verifier": getattr(flow, "code_verifier", None)
    }
    save_oauth_states(states)
    logger.info(f"Initiated OAuth for profile '{profile}' with state '{state}'")

    return RedirectResponse(auth_url)


def process_token_exchange(code: str, state: Optional[str] = None, profile_override: Optional[str] = None) -> Dict[str, Any]:
    """
    Exchanges authorization code for YouTube refresh token and channel metadata.
    Supports both automated browser callback and manual mobile code submission.
    """
    states = get_oauth_states()
    state_data = states.pop(state, {}) if state else {}
    save_oauth_states(states)

    profile = profile_override or state_data.get("profile", "nagpuri")
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
        flow.fetch_token(code=code, code_verifier=code_verifier)
    else:
        # Fallback if verifier wasn't preserved across restarts
        try:
            flow.fetch_token(code=code)
        except Exception:
            flow.fetch_token(code=code, code_verifier=code_verifier)

    creds = flow.credentials
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()

    items = resp.get("items", [])
    if not items:
        raise ValueError("इस गूगल अकाउंट पर कोई YouTube चैनल नहीं मिला।")

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
        "scopes": creds.scopes,
        "connected_at": time.time()
    }

    t_file = get_token_file(profile)
    t_file.write_text(json.dumps(token_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    TOKEN_HEALTH_CACHE.pop(profile, None)
    logger.info(f"Connected {profile} channel: {snippet.get('title')} ({ch_id})")
    return token_payload


class SubmitCallbackRequest(BaseModel):
    callback_data: str
    profile: Optional[str] = None


@app.post("/api/channels/submit_callback")
async def api_submit_callback(req: SubmitCallbackRequest):
    """
    Mobile OAuth Helper: Allows pasting the redirect URL or code from phone
    to seamlessly connect channels when Google redirects to localhost.
    """
    raw = req.callback_data.strip()
    code = None
    state = None

    if "code=" in raw:
        query_part = raw.split("?", 1)[1] if "?" in raw else raw
        params = parse_qs(query_part)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
    elif "&" in raw:
        params = parse_qs(raw)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
    else:
        code = raw

    if not code:
        raise HTTPException(status_code=400, detail="दिए गए टेक्स्ट या लिंक में 'code' नहीं मिला।")

    try:
        payload = process_token_exchange(code=code, state=state, profile_override=req.profile)
        return {
            "status": "success",
            "profile": payload.get("profile"),
            "channel_title": payload.get("channel_title")
        }
    except Exception as e:
        logger.error(f"Mobile callback exchange failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"कनेक्ट विफल: {str(e)}")


@app.get("/api/channels/oauth2callback")
async def oauth2_callback(request: Request, code: str = Query(None), state: str = Query(None), error: str = Query(None)):
    if error:
        logger.warning(f"OAuth error from Google: {error}")
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><title>Login Error</title></head>
        <body style="background:#07090e;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="background:#131926;border:1px solid #ff4b4b;border-radius:16px;padding:32px;max-width:480px;text-align:center;">
                <h2 style="color:#ff5e5e;">⚠️ गूगल लॉगिन रद्द या अस्वीकृत</h2>
                <p style="color:#94a3b8;font-size:14px;line-height:1.6;">गूगल द्वारा एरर: {error}</p>
                <a href="/" style="background:#00e5ff;color:#000;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:bold;display:inline-block;margin-top:16px;">होम पेज पर जाएँ</a>
            </div>
        </body>
        </html>
        """, status_code=400)

    if not code:
        return HTMLResponse("<h3>Authorization error: No code received</h3>", status_code=400)

    try:
        process_token_exchange(code=code, state=state)
        return RedirectResponse(url="/")
    except Exception as e:
        logger.error(f"Error during OAuth callback: {e}", exc_info=True)
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><title>Auth Error</title></head>
        <body style="background:#07090e;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="background:#131926;border:1px solid #ff4b4b;border-radius:16px;padding:32px;max-width:500px;text-align:center;">
                <h2 style="color:#ff5e5e;">⚠️ लॉगिन में त्रुटि</h2>
                <p style="color:#94a3b8;font-size:14px;">{str(e)}</p>
                <a href="/" style="background:#00e5ff;color:#000;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:bold;display:inline-block;margin-top:16px;">होम पेज</a>
            </div>
        </body>
        </html>
        """, status_code=500)


@app.post("/api/auth/disconnect")
async def disconnect_channel(profile: str = Query("nagpuri")):
    clean_id = profile.lower().strip()
    t_file = get_token_file(clean_id)
    if t_file.exists():
        t_file.unlink()
    TOKEN_HEALTH_CACHE.pop(clean_id, None)
    logger.info(f"Disconnected channel profile: {clean_id}")
    return {"status": "success", "profile": clean_id}


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
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=True)
