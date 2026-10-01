"""
Kaggle Headless Cloud Runner for Music-Automat
Runs on free Kaggle cloud instances with high-speed internet and zero local resources.
"""

import os
import sys
import subprocess
import shutil

def run_cmd(cmd, check=True):
    print(f"==> Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed with code {res.returncode}")
    return res.returncode

def main():
    print("==================================================")
    print("🚀 Music-Automat Cloud Runner Initializing...")
    print("==================================================")

    # 1. Install & upgrade necessary tools
    run_cmd([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp", "google-api-python-client", "google-auth-oauthlib"])

    # 2. Determine target profile from env or default
    profile = os.environ.get("DJ_PROFILE", "nagpuri").lower()
    target_tracks = int(os.environ.get("DJ_TARGET_TRACKS", "25"))
    skip_upload = os.environ.get("DJ_SKIP_UPLOAD", "0") == "1"

    print(f"Target Profile: {profile.upper()}")
    print(f"Target Tracks: {target_tracks}")
    print(f"Skip Upload: {skip_upload}")

    # 3. Add current directory to PYTHONPATH
    cur_dir = os.path.abspath(os.path.dirname(__file__))
    project_root = os.path.abspath(os.path.join(cur_dir, ".."))
    sys.path.insert(0, project_root)

    # 4. Execute production pipeline
    from src.pipeline import DJProductionPipeline

    pipeline = DJProductionPipeline(profile=profile, base_dir=project_root)
    success = pipeline.run(target_tracks=target_tracks, skip_upload=skip_upload)

    if success:
        print("🎉 Cloud execution completed successfully!")
    else:
        print("❌ Cloud execution encountered errors.")
        sys.exit(1)

if __name__ == "__main__":
    main()
