import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
DEPLOY_SRC = ROOT / "kaggle"
TEMP_DEPLOY = ROOT / "temp_deploy"

print("=" * 65)
print("🚀 [MUSIC-AUTOMAT CLOUD TRIGGER] PREPARING PRIVATE KERNEL")
print("=" * 65)

shutil.rmtree(TEMP_DEPLOY, ignore_errors=True)
TEMP_DEPLOY.mkdir(parents=True, exist_ok=True)

# Copy base runner and metadata
shutil.copy(DEPLOY_SRC / "kernel-metadata.json", TEMP_DEPLOY / "kernel-metadata.json")

# Read credentials from environment (GitHub Actions Secrets) or local files
client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
ref_nagpuri = os.environ.get("YOUTUBE_REFRESH_TOKEN_NAGPURI", "")
ref_vibration = os.environ.get("YOUTUBE_REFRESH_TOKEN_VIBRATION", "")
ref_edm = os.environ.get("YOUTUBE_REFRESH_TOKEN_EDM", "")
gmail_pass = os.environ.get("ALERT_GMAIL_APP_PASS", "ziqkkzjwffqnzrgn")

cs_file = ROOT / "client_secrets.json"
if cs_file.exists() and not (client_id and client_secret):
    try:
        with open(cs_file, encoding="utf-8") as f:
            cs = json.load(f)
        key = list(cs.keys())[0]
        client_id = cs[key].get("client_id", "")
        client_secret = cs[key].get("client_secret", "")
    except Exception:
        pass

# Collect all tokens dynamically from tokens/ directory and environment
tokens_map = {}
tokens_dir = ROOT / "tokens"
if tokens_dir.exists():
    for f in tokens_dir.glob("token_*.json"):
        try:
            with open(f, encoding="utf-8") as tf:
                t_data = json.load(tf)
            p_id = t_data.get("profile", f.stem.replace("token_", "")).upper()
            r_tok = t_data.get("refresh_token")
            if r_tok:
                tokens_map[f"YOUTUBE_REFRESH_TOKEN_{p_id}"] = r_tok
        except Exception:
            pass

# Also override/augment from environment secrets
for k, v in os.environ.items():
    if k.startswith("YOUTUBE_REFRESH_TOKEN_") and v:
        tokens_map[k] = v

# Optional pipeline overrides
profile = os.environ.get("DJ_PROFILE", "")
target_tracks = os.environ.get("DJ_TARGET_TRACKS", "")
skip_upload = os.environ.get("DJ_SKIP_UPLOAD", "")

# Read runner code
with open(DEPLOY_SRC / "kaggle_runner.py", encoding="utf-8") as f:
    orig_runner = f.read()

# Prepend injected secrets block
header = f"""# INJECTED PRIVATE CLOUD SECRETS
import os
os.environ.setdefault("YOUTUBE_CLIENT_ID", "{client_id}")
os.environ.setdefault("YOUTUBE_CLIENT_SECRET", "{client_secret}")
os.environ.setdefault("ALERT_GMAIL_APP_PASS", "{gmail_pass}")
os.environ.setdefault("ALERT_GMAIL_RECIPIENT", "9329238475x@gmail.com")
"""
for k, v in tokens_map.items():
    header += f'os.environ.setdefault("{k}", "{v}")\n'

if profile:
    header += f'os.environ["DJ_PROFILE"] = "{profile}"\n'
if target_tracks:
    header += f'os.environ["DJ_TARGET_TRACKS"] = "{target_tracks}"\n'
if skip_upload:
    header += f'os.environ["DJ_SKIP_UPLOAD"] = "{skip_upload}"\n'

with open(TEMP_DEPLOY / "kaggle_runner.py", "w", encoding="utf-8") as f:
    f.write(header + "\n" + orig_runner)

print(f"Deploying private kernel to Kaggle (Kernel ID: sonuji93/music-automat-worker)...")
res = subprocess.run(["kaggle", "kernels", "push", "-p", str(TEMP_DEPLOY)], capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print(res.stderr)

shutil.rmtree(TEMP_DEPLOY, ignore_errors=True)

if res.returncode == 0:
    print("\n🎉 SUCCESS! KERNEL TRIGGERED ON KAGGLE!")
    print("🔗 Direct URL: https://www.kaggle.com/code/sonuji93/music-automat-worker")
    print("Waiting 10 seconds for Kaggle to schedule the kernel...")
    time.sleep(10)
    st = subprocess.run(["kaggle", "kernels", "status", "sonuji93/music-automat-worker"], capture_output=True, text=True)
    print(f"Current Kaggle Status: {st.stdout.strip()}")
else:
    sys.exit(res.returncode)
