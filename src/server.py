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

# Persistent file-based oauth pending states to survive server restarts/reloads
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

    states = get_oauth_states()
    states[state] = {
        "profile": profile.lower().strip(),
        "verifier": getattr(flow, "code_verifier", None)
    }
    save_oauth_states(states)
    logger.info(f"Initiated OAuth for profile '{profile}' with state '{state}' and verifier: {bool(getattr(flow, 'code_verifier', None))}")

    return RedirectResponse(auth_url)


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

    states = get_oauth_states()
    state_data = states.pop(state, {}) if state else {}
    save_oauth_states(states)

    profile = state_data.get("profile", "nagpuri")
    code_verifier = state_data.get("verifier")

    redirect_uri = "http://localhost:8000/api/channels/oauth2callback"

    try:
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
            logger.warning(f"No code_verifier found for state {state}. Session may have expired or server restarted.")
            # Session expired screen with instant retry button
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Session Expired - Music Automat</title>
                <style>
                    body {{ background: #07090e; color: #fff; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                    .box {{ background: #131926; border: 1px solid rgba(255,255,255,0.12); border-radius: 18px; padding: 36px; max-width: 480px; text-align: center; box-shadow: 0 15px 40px rgba(0,0,0,0.6); }}
                    h2 {{ color: #00e5ff; font-size: 22px; margin-bottom: 12px; }}
                    p {{ color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 24px; }}
                    .btn {{ background: linear-gradient(135deg, #00e5ff 0%, #a855f7 50%, #ff2a85 100%); color: #fff; text-decoration: none; padding: 13px 28px; border-radius: 10px; font-weight: bold; display: inline-block; box-shadow: 0 4px 15px rgba(0,229,255,0.3); transition: transform 0.2s; }}
                    .btn:hover {{ transform: translateY(-2px); }}
                    .home-link {{ display: block; margin-top: 18px; color: #64748b; text-decoration: none; font-size: 13px; }}
                    .home-link:hover {{ color: #cbd5e1; }}
                </style>
            </head>
            <body>
                <div class="box">
                    <h2>⚠️ लॉगिन सत्र समाप्त (Session Expired)</h2>
                    <p>सर्वर अपडेट होने के कारण पिछला ऑथेंटिकेशन टोकन एक्सपायर हो गया था। कृपया नीचे दिए बटन पर क्लिक करके दोबारा लॉगिन करें (यह 5 सेकंड में हो जाएगा):</p>
                    <a href="/api/auth/login?profile={profile}" class="btn">🔄 दोबारा लॉगिन करें (Retry Login)</a>
                    <a href="/" class="home-link">होम पेज पर वापस जाएँ</a>
                </div>
            </body>
            </html>
            """)

        creds = flow.credentials

        # Query YouTube for channel identity
        youtube = build("youtube", "v3", credentials=creds)
        resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()

        items = resp.get("items", [])
        if not items:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"><title>No Channel Found</title></head>
            <body style="background:#07090e;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                <div style="background:#131926;border:1px solid #ff4b4b;border-radius:16px;padding:32px;max-width:480px;text-align:center;">
                    <h2 style="color:#ff5e5e;">⚠️ कोई यूट्यूब चैनल नहीं मिला</h2>
                    <p style="color:#94a3b8;font-size:14px;line-height:1.6;">जिस गूगल अकाउंट से आपने लॉगिन किया है, उस पर कोई YouTube चैनल नहीं बना हुआ है। कृपया वह गूगल अकाउंट चुनें जिस पर आपका चैनल है।</p>
                    <a href="/api/auth/login?profile=""" + profile + """" style="background:#00e5ff;color:#000;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:bold;display:inline-block;margin-top:16px;">दोबारा सही अकाउंट से लॉगिन करें</a>
                </div>
            </body>
            </html>
            """, status_code=400)

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
        logger.info(f"Successfully connected {profile} channel: {snippet.get('title')} ({ch_id})")

        return RedirectResponse(url="/")
    except Exception as e:
        logger.error(f"Error during OAuth callback: {e}", exc_info=True)
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Authentication Error</title>
            <style>
                body {{ background: #07090e; color: #fff; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .box {{ background: #131926; border: 1px solid rgba(255,100,100,0.3); border-radius: 16px; padding: 32px; max-width: 500px; text-align: center; }}
                h2 {{ color: #ff5e5e; margin-bottom: 12px; }}
                p {{ color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 20px; }}
                .err {{ background: rgba(0,0,0,0.5); padding: 10px; border-radius: 8px; font-family: monospace; font-size: 12px; color: #ff9999; margin-bottom: 20px; word-break: break-all; }}
                a {{ background: #00e5ff; color: #000; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; display: inline-block; }}
            </style>
        </head>
        <body>
            <div class="box">
                <h2>⚠️ लॉगिन प्रमाणीकरण में त्रुटि</h2>
                <p>गूगल से टोकन प्राप्त करते समय निम्नलिखित समस्या आई:</p>
                <div class="err">{str(e)}</div>
                <a href="/api/auth/login?profile={profile}">🔄 दोबारा लॉगिन करें</a>
                <br><br>
                <a href="/" style="background:transparent;border:1px solid #475569;color:#cbd5e1;font-size:13px;padding:8px 16px;">होम पेज</a>
            </div>
        </body>
        </html>
        """, status_code=500)


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
