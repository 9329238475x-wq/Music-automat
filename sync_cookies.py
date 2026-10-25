# -*- coding: utf-8 -*-
"""
Helper script to sync local cookies.txt directly to GitHub Repository Secrets
so Kaggle headless runners can authenticate with YouTube and bypass bot-walls.
"""
import os
import sys
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.github_sync import (
    get_stored_github_token,
    get_repo_owner_name,
    get_repo_public_key,
    set_repo_secret
)


def sync_cookies_to_github():
    print("=" * 60)
    print("🍪 [MUSIC-AUTOMAT] SYNC COOKIES.TXT TO GITHUB SECRETS")
    print("=" * 60)

    # Find cookies file
    cookie_file = None
    for candidate in [ROOT / "cookies.txt", ROOT / "config" / "cookies.txt"]:
        if candidate.exists():
            cookie_file = candidate
            break

    if not cookie_file:
        print("❌ Error: 'cookies.txt' फ़ाइल नहीं मिली!")
        print("कृपया अपने ब्राउज़र से यूट्यूब कुकीज़ एक्सपोर्ट करके 'c:\\Music-automat\\cookies.txt' नाम से सेव करें।")
        return False

    raw_bytes = cookie_file.read_bytes()
    if len(raw_bytes) < 50:
        print("❌ Error: 'cookies.txt' फ़ाइल खाली या बहुत छोटी है!")
        return False

    b64_cookies = base64.b64encode(raw_bytes).decode("ascii")
    print(f"✓ Found 'cookies.txt' ({len(raw_bytes)} bytes)")

    # Read GitHub token
    gh_token = get_stored_github_token()
    if not gh_token:
        print("❌ Error: GitHub Token नहीं मिला! 'config/github_token.txt' चेक करें।")
        return False

    owner, repo = get_repo_owner_name()
    print(f"Connecting to GitHub repository: {owner}/{repo}...")

    key_id, pub_key, err = get_repo_public_key(owner, repo, gh_token)
    if err:
        print(f"❌ Error getting public key: {err}")
        return False

    print("Encrypting cookies with libsodium and pushing secret 'YOUTUBE_COOKIES_B64'...")
    ok, msg = set_repo_secret(
        owner=owner,
        repo=repo,
        secret_name="YOUTUBE_COOKIES_B64",
        secret_value=b64_cookies,
        key_id=key_id,
        pub_key=pub_key,
        gh_token=gh_token
    )

    if ok:
        print("\n🎉 सफलता! (SUCCESS!)")
        print("✅ 'YOUTUBE_COOKIES_B64' GitHub Repository Secrets में सेव हो गया है!")
        print("अब Kaggle पर कभी भी 'Sign in to confirm you're not a bot' एरर नहीं आएगा।")
        return True
    else:
        print(f"❌ Failed to set secret: {msg}")
        return False


if __name__ == "__main__":
    sync_cookies_to_github()
