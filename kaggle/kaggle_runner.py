# -*- coding: utf-8 -*-
"""
Music-Automat Autonomous Unified Cloud Production Pipeline
Kaggle Headless Script Runner (Zero GPU quota required, CPU-only, 100% Free & Unlimited)
"""
import os
import sys
import json
import shutil
import subprocess
import traceback

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

print("=" * 65, flush=True)
print("🚀 [MUSIC-AUTOMAT CLOUD RUNNER] STARTING PRODUCTION PIPELINE", flush=True)
print("=" * 65, flush=True)

try:
    # ─── 1. VERIFY FFMPEG ───
    print("[1/5] Checking FFmpeg availability...", flush=True)
    if not shutil.which("ffmpeg"):
        print("FFmpeg not found in PATH. Installing via apt-get...", flush=True)
        subprocess.run(["apt-get", "update", "-y"], check=True)
        subprocess.run(["apt-get", "install", "-y", "ffmpeg"], check=True)
    ffmpeg_ver = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    first_line = ffmpeg_ver.stdout.split("\n")[0] if ffmpeg_ver.stdout else "FFmpeg available"
    print(f"✓ {first_line}", flush=True)

    # ─── 2. INITIALIZE WORKSPACE & CLONE ───
    print("\n[2/5] Initializing workspace & fetching latest repository...", flush=True)
    WORK_DIR = "/kaggle/working/Music-automat"
    if os.path.exists(WORK_DIR):
        print(f"Removing old workspace {WORK_DIR}...", flush=True)
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    git_url = "https://github.com/9329238475x-wq/Music-automat.git"
    print(f"Cloning {git_url}...", flush=True)
    subprocess.run(["git", "clone", git_url, WORK_DIR], check=True)
    print("✓ Git clone successful!", flush=True)

    # ─── 3. INSTALL PYTHON DEPENDENCIES ───
    print("\n[3/5] Installing cloud dependencies...", flush=True)
    pip_cmd = [
        sys.executable, "-m", "pip", "install", "-q", "--upgrade",
        "yt-dlp[default]",
        "google-api-python-client",
        "google-auth-oauthlib",
        "google-auth-httplib2",
        "pillow",
        "numpy",
        "scipy",
        "opencv-python-headless"
    ]
    subprocess.run(pip_cmd, check=True)
    print("✓ Dependencies verified & ready!", flush=True)

    # ─── 4. CONFIGURE RUNNER & REPOSITORIES ───
    print("\n[4/5] Setting up environment & credentials...", flush=True)
    os.chdir(WORK_DIR)
    sys.path.insert(0, WORK_DIR)

    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    if client_id and client_secret:
        cs_data = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }
        with open(os.path.join(WORK_DIR, "client_secrets.json"), "w", encoding="utf-8") as f:
            json.dump(cs_data, f, indent=2)
        print("✓ Hydrated client_secrets.json", flush=True)

    os.environ["ALERT_GMAIL_APP_PASS"] = os.environ.get("ALERT_GMAIL_APP_PASS") or "ziqkkzjwffqnzrgn"
    os.environ["ALERT_GMAIL_RECIPIENT"] = os.environ.get("ALERT_GMAIL_RECIPIENT") or "9329238475x@gmail.com,bamitbhai554@gmail.com"
    # Hydrate tokens directory for both profiles
    tokens_dir = os.path.join(WORK_DIR, "tokens")
    os.makedirs(tokens_dir, exist_ok=True)
    ref_nag = os.environ.get("YOUTUBE_REFRESH_TOKEN_NAGPURI")
    if ref_nag:
        with open(os.path.join(tokens_dir, "token_nagpuri.json"), "w", encoding="utf-8") as f:
            json.dump({
                "profile": "nagpuri",
                "refresh_token": ref_nag,
                "client_id": client_id,
                "client_secret": client_secret,
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": ["https://www.googleapis.com/auth/youtube.upload"]
            }, f, indent=2)
        print("✓ Hydrated token_nagpuri.json", flush=True)

    ref_vib = os.environ.get("YOUTUBE_REFRESH_TOKEN_VIBRATION")
    if ref_vib:
        with open(os.path.join(tokens_dir, "token_vibration.json"), "w", encoding="utf-8") as f:
            json.dump({
                "profile": "vibration",
                "refresh_token": ref_vib,
                "client_id": client_id,
                "client_secret": client_secret,
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": ["https://www.googleapis.com/auth/youtube.upload"]
            }, f, indent=2)
        print("✓ Hydrated token_vibration.json", flush=True)

    ref_edm = os.environ.get("YOUTUBE_REFRESH_TOKEN_EDM")
    if ref_edm:
        with open(os.path.join(tokens_dir, "token_edm.json"), "w", encoding="utf-8") as f:
            json.dump({
                "profile": "edm",
                "refresh_token": ref_edm,
                "client_id": client_id,
                "client_secret": client_secret,
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": ["https://www.googleapis.com/auth/youtube.upload"]
            }, f, indent=2)
        print("✓ Hydrated token_edm.json", flush=True)

    # Determine profile: check hour or env
    from datetime import datetime
    utc_hour = datetime.utcnow().hour
    # 06:12 AM IST = 00:42 UTC -> utc_hour < 3 -> "edm"
    # 09:06 AM IST = 03:36 UTC -> utc_hour 3 to 9 -> "nagpuri"
    # 07:00 PM IST = 13:30 UTC -> utc_hour 10+ -> "vibration"
    if utc_hour < 3:
        default_profile = "edm"
    elif utc_hour < 10:
        default_profile = "nagpuri"
    else:
        default_profile = "vibration"
    profile = os.environ.get("DJ_PROFILE") or default_profile
    profile = profile.lower()
    # Dynamically resolve target tracks based on profile and channels
    settings_file = os.path.join(WORK_DIR, "config", "settings.json")
    channels_file = os.path.join(WORK_DIR, "config", "channels.json")
    default_tracks = 41 if profile == "edm" else (20 if profile == "nagpuri" else 24)
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                s_data = json.load(f)
                default_tracks = s_data.get("profiles", {}).get(profile, {}).get("target_tracks", default_tracks)
        except Exception:
            pass
    if os.path.exists(channels_file):
        try:
            with open(channels_file, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                if profile in c_data and len(c_data[profile]) > 0:
                    default_tracks = len(c_data[profile])
        except Exception:
            pass

    env_tracks = os.environ.get("DJ_TARGET_TRACKS", "").strip()
    if env_tracks and env_tracks.isdigit() and int(env_tracks) > 0:
        target_tracks = int(env_tracks)
    else:
        target_tracks = default_tracks
    skip_upload = os.environ.get("DJ_SKIP_UPLOAD", "0") == "1"

    print(f"Selected Profile : {profile.upper()} (UTC Hour: {utc_hour})", flush=True)
    print(f"Target Tracks    : {target_tracks}", flush=True)
    print(f"Skip Upload      : {skip_upload}", flush=True)

    # ─── 5. EXECUTE PRODUCTION PIPELINE ───
    print("\n[5/5] Launching autonomous DJ production pipeline...", flush=True)
    from src.pipeline import DJProductionPipeline

    pipeline = DJProductionPipeline(profile=profile, base_dir=WORK_DIR)
    success = pipeline.run(target_tracks=target_tracks, skip_upload=skip_upload)

    if success:
        print("\n🎉 [COMPLETE] Autonomous DJ Remix Pipeline Succeeded!", flush=True)
    else:
        print("\n❌ [FAILED] Pipeline finished with errors.", flush=True)
        sys.exit(1)

except Exception as exc:
    print(f"\n❌ FATAL EXCEPTION: {exc}", flush=True)
    traceback.print_exc()
    sys.exit(1)
