# -*- coding: utf-8 -*-
"""
GitHub Secrets & Config Synchronization Engine
Syncs OAuth refresh tokens directly to GitHub Repository Secrets
using GitHub REST API and libsodium (PyNaCl) encryption.
"""

import os
import sys
import json
import logging
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests
from nacl import encoding, public

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GitHubSync")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
TOKENS_DIR = BASE_DIR / "tokens"
GITHUB_TOKEN_FILE = CONFIG_DIR / "github_token.txt"
CLIENT_SECRETS_FILE = BASE_DIR / "client_secrets.json"

DEFAULT_REPO = "9329238475x-wq/Music-automat"


def get_stored_github_token() -> str:
    """Read stored GitHub Personal Access Token if available."""
    if GITHUB_TOKEN_FILE.exists():
        try:
            return GITHUB_TOKEN_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return os.environ.get("GITHUB_TOKEN", "").strip()


def save_github_token(token: str) -> None:
    """Persist GitHub Personal Access Token locally."""
    clean_token = token.strip()
    GITHUB_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    GITHUB_TOKEN_FILE.write_text(clean_token, encoding="utf-8")


def get_repo_owner_name() -> Tuple[str, str]:
    """Extract owner and repo name from git origin or fallback."""
    try:
        import subprocess
        res = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(BASE_DIR), capture_output=True, text=True)
        out = res.stdout.strip()
        if "github.com" in out:
            # Handle https://github.com/owner/repo.git or git@github.com:owner/repo.git
            part = out.split("github.com")[-1].lstrip("/:").removesuffix(".git")
            parts = part.split("/")
            if len(parts) >= 2:
                return parts[0], parts[1]
    except Exception:
        pass
    parts = DEFAULT_REPO.split("/")
    return parts[0], parts[1]


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """Encrypt secret using NaCl SealedBox (required by GitHub Actions Secrets API)."""
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def get_repo_public_key(owner: str, repo: str, gh_token: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fetch repository public key from GitHub API.
    Returns (key_id, public_key_b64, error_message).
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key"
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("key_id"), data.get("key"), None
        elif resp.status_code == 401:
            return None, None, "GitHub Token अमान्य (Invalid/Unauthorized) है।"
        elif resp.status_code == 404:
            return None, None, f"रिपॉजिटरी {owner}/{repo} नहीं मिली या टोकन के पास repo/secrets परमिशन नहीं है।"
        else:
            return None, None, f"GitHub API त्रुटि: HTTP {resp.status_code} - {resp.text}"
    except Exception as e:
        return None, None, f"कनेक्शन एरर: {str(e)}"


def set_repo_secret(owner: str, repo: str, secret_name: str, secret_value: str, key_id: str, pub_key: str, gh_token: str) -> Tuple[bool, str]:
    """Upload encrypted secret to GitHub Actions repository."""
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{secret_name}"
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        encrypted_value = encrypt_secret(pub_key, secret_value)
        payload = {
            "encrypted_value": encrypted_value,
            "key_id": key_id
        }
        resp = requests.put(url, headers=headers, json=payload, timeout=12)
        if resp.status_code in (201, 204):
            return True, "सफलतापूर्वक अपडेट किया गया"
        return False, f"HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, str(e)


def sync_all_secrets_to_github(gh_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Collects all active OAuth tokens from tokens/ and pushes them directly
    to GitHub Actions Secrets.
    """
    token_to_use = gh_token.strip() if gh_token else get_stored_github_token()
    if not token_to_use:
        return {
            "success": False,
            "error_type": "NO_TOKEN",
            "message": "GitHub Personal Access Token दर्ज नहीं है। कृपया पहले GitHub टोकन सेट करें।"
        }

    owner, repo = get_repo_owner_name()
    key_id, pub_key, err = get_repo_public_key(owner, repo, token_to_use)
    if err or not key_id or not pub_key:
        return {
            "success": False,
            "error_type": "KEY_FETCH_FAILED",
            "message": err or "पब्लिक की नहीं मिल सकी।"
        }

    # Gather all tokens to push
    secrets_to_push = {}

    # 1. Channel refresh tokens
    if TOKENS_DIR.exists():
        for f in TOKENS_DIR.glob("token_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                profile = data.get("profile", f.stem.replace("token_", "")).upper()
                ref_tok = data.get("refresh_token")
                if ref_tok:
                    secret_key = f"YOUTUBE_REFRESH_TOKEN_{profile}"
                    secrets_to_push[secret_key] = ref_tok
            except Exception as e:
                logger.warning(f"Error parsing {f.name}: {e}")

    # 2. Client ID and Secret if present
    if CLIENT_SECRETS_FILE.exists():
        try:
            cs = json.loads(CLIENT_SECRETS_FILE.read_text(encoding="utf-8"))
            k = list(cs.keys())[0]
            cid = cs[k].get("client_id")
            csec = cs[k].get("client_secret")
            if cid:
                secrets_to_push["YOUTUBE_CLIENT_ID"] = cid
            if csec:
                secrets_to_push["YOUTUBE_CLIENT_SECRET"] = csec
        except Exception as e:
            logger.warning(f"Error reading client secrets: {e}")

    if not secrets_to_push:
        return {
            "success": False,
            "error_type": "NO_SECRETS",
            "message": "कोई रीफ्रेश टोकन नहीं मिला! कृपया पहले कम से कम एक चैनल लॉगिन करें।"
        }

    # Push all gathered secrets
    results = {}
    success_count = 0
    failed_count = 0

    for s_name, s_val in secrets_to_push.items():
        ok, msg = set_repo_secret(owner, repo, s_name, s_val, key_id, pub_key, token_to_use)
        results[s_name] = {"success": ok, "message": msg}
        if ok:
            success_count += 1
        else:
            failed_count += 1

    # Persist valid token
    if gh_token:
        save_github_token(gh_token)

    return {
        "success": failed_count == 0,
        "repo": f"{owner}/{repo}",
        "total": len(secrets_to_push),
        "success_count": success_count,
        "failed_count": failed_count,
        "details": results,
        "message": f"सफलतापूर्वक {success_count}/{len(secrets_to_push)} सीक्रेट्स GitHub ({owner}/{repo}) में पुश कर दिए गए!"
    }


def get_manual_secrets_dump() -> Dict[str, str]:
    """Returns key-value pairs of all current tokens for 1-click manual copy."""
    dump = {}
    if TOKENS_DIR.exists():
        for f in TOKENS_DIR.glob("token_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                profile = data.get("profile", f.stem.replace("token_", "")).upper()
                ref_tok = data.get("refresh_token")
                if ref_tok:
                    dump[f"YOUTUBE_REFRESH_TOKEN_{profile}"] = ref_tok
            except Exception:
                pass
    if CLIENT_SECRETS_FILE.exists():
        try:
            cs = json.loads(CLIENT_SECRETS_FILE.read_text(encoding="utf-8"))
            k = list(cs.keys())[0]
            dump["YOUTUBE_CLIENT_ID"] = cs[k].get("client_id", "")
            dump["YOUTUBE_CLIENT_SECRET"] = cs[k].get("client_secret", "")
        except Exception:
            pass
    return dump
