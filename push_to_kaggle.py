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

# Note: kernel-metadata.json is generated dynamically below per profile

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
profile = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DJ_PROFILE", "vibration")).lower().strip() or "vibration"
target_tracks = os.environ.get("DJ_TARGET_TRACKS", "")
skip_upload = os.environ.get("DJ_SKIP_UPLOAD", "")

# Dedicated Kaggle kernel per channel profile to allow concurrent runs without cancellation
def _get_kaggle_username():
    k_env = os.environ.get("KAGGLE_USERNAME", "")
    if k_env:
        return k_env.strip()
    k_file = Path.home() / ".kaggle" / "kaggle.json"
    if k_file.exists():
        try:
            with open(k_file, encoding="utf-8") as f:
                u = json.load(f).get("username", "")
                if u:
                    return u.strip()
        except Exception:
            pass
    return "sonuji12345"

kaggle_user = _get_kaggle_username()
kernel_slug = f"music-automat-{profile.replace('_', '-')}"
kernel_title = f"Music Automat {profile.upper().replace('_', ' ')}"
kernel_id = f"{kaggle_user}/{kernel_slug}"

# Write profile-specific kernel metadata
meta = {
    "id": kernel_id,
    "title": kernel_title,
    "code_file": "kaggle_runner.py",
    "language": "python",
    "kernel_type": "script",
    "is_private": "true",
    "enable_gpu": "true" if os.environ.get("ENABLE_GPU", "").lower() in ["true", "1"] else "false",
    "enable_internet": "true",
    "dataset_sources": [],
    "competition_sources": [],
    "kernel_sources": []
}
with open(TEMP_DEPLOY / "kernel-metadata.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)

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

# Pexels & Pixabay keys for footage fetching
pex_key = os.environ.get("PEXELS_API_KEY", "")
pix_key = os.environ.get("PIXABAY_API_KEY", "")
if not pex_key or not pix_key:
    crw_env = ROOT / "CopyRight-Work" / ".env"
    if crw_env.exists():
        for line in crw_env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == "PEXELS_API_KEY" and not pex_key:
                    pex_key = v.strip()
                elif k.strip() == "PIXABAY_API_KEY" and not pix_key:
                    pix_key = v.strip()
if pex_key:
    header += f'os.environ.setdefault("PEXELS_API_KEY", "{pex_key}")\n'
if pix_key:
    header += f'os.environ.setdefault("PIXABAY_API_KEY", "{pix_key}")\n'

if profile:
    header += f'os.environ["DJ_PROFILE"] = "{profile}"\n'
if target_tracks:
    header += f'os.environ["DJ_TARGET_TRACKS"] = "{target_tracks}"\n'
if skip_upload:
    header += f'os.environ["DJ_SKIP_UPLOAD"] = "{skip_upload}"\n'

# Create local code payload to guarantee zero drift from local workspace
import io
import zipfile
import base64

def _build_local_code_payload(root_dir: Path) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in ["src", "config", "CopyRight-Work"]:
            f_path = root_dir / folder
            if f_path.exists():
                for p in f_path.rglob("*"):
                    if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts:
                        if p.suffix.lower() in [".mp4", ".mp3", ".wav", ".mkv", ".webm", ".avi", ".ts", ".jpg", ".png", ".jpeg"]:
                            continue
                        if any(part in ["footage", "output", "temp", "downloads", "temp_deploy"] for part in p.parts):
                            continue
                        if p.name in ["github_token.txt", "client_secrets.json", ".env"]:
                            continue
                        rel_path = p.relative_to(root_dir)
                        zf.write(p, str(rel_path).replace("\\", "/"))
        # Also include cookies.txt if present locally or from GitHub Actions Secrets
        cookies_data = None
        for cname in ["cookies.txt", "config/cookies.txt"]:
            cp = root_dir / cname
            if cp.exists():
                try:
                    cookies_data = cp.read_bytes()
                    break
                except Exception:
                    pass
        if not cookies_data:
            c_env = (os.environ.get("YOUTUBE_COOKIES_B64") or os.environ.get("YOUTUBE_COOKIES") or "").strip()
            if c_env:
                try:
                    cookies_data = base64.b64decode(c_env)
                except Exception:
                    cookies_data = c_env.encode("utf-8")
        if cookies_data:
            zf.writestr("cookies.txt", cookies_data)
            print("✓ Packed cookies.txt into deployment payload for Kaggle!")
    payload_bytes = buf.getvalue()
    print(f"✓ Deployment payload zip size: {len(payload_bytes) / 1024:.1f} KB")
    return base64.b64encode(payload_bytes).decode("ascii")

local_payload = _build_local_code_payload(ROOT)
override_block = f"""
    # ─── AUTO-SYNC LATEST LOCAL CODE (ZERO DRIFT) ───
    import base64, io, zipfile
    _payload = "{local_payload}"
    if _payload:
        print("[2.1/5] Injecting latest local workspace updates (src/ & config/)...", flush=True)
        _zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(_payload)))
        _zf.extractall(WORK_DIR)
        print("✓ Local updates synchronized into workspace!", flush=True)
"""
target_hook = 'print("✓ Git clone successful!", flush=True)'
if target_hook in orig_runner:
    orig_runner = orig_runner.replace(target_hook, target_hook + "\n" + override_block)

with open(TEMP_DEPLOY / "kaggle_runner.py", "w", encoding="utf-8") as f:
    f.write(header + "\n" + orig_runner)

print(f"Deploying private kernel to Kaggle (Kernel ID: {kernel_id})...")
res = subprocess.run(["kaggle", "kernels", "push", "-p", str(TEMP_DEPLOY)], capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print(res.stderr)

shutil.rmtree(TEMP_DEPLOY, ignore_errors=True)

if res.returncode == 0:
    print(f"\n🎉 SUCCESS! KERNEL TRIGGERED ON KAGGLE ({profile.upper()})!")
    print(f"🔗 Direct URL: https://www.kaggle.com/code/{kernel_id}")
    print("Waiting 10 seconds for Kaggle to schedule the kernel...")
    time.sleep(10)
    st = subprocess.run(["kaggle", "kernels", "status", kernel_id], capture_output=True, text=True)
    print(f"Current Kaggle Status: {st.stdout.strip()}")
else:
    sys.exit(res.returncode)
