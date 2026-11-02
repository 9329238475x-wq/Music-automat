"""
CopyRight-Work — Video Downloader
Downloads the selected video (audio+video) using yt-dlp.
4-tier client retry strategy matching the main scraper pattern.
"""

import logging
import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from . import config
except ImportError:
    import config

logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
logger = logging.getLogger("CRW-Downloader")


def download_video(video_info: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Downloads a complete video (audio+video merged) using yt-dlp.
    
    4-Tier retry strategy:
      1. Default client with BotGuard + EJS solver
      2. TV Embedded client
      3. Android client with format 18 (progressive)
      4. iOS client fallback
    
    Args:
        video_info: Dict with keys: id, url, title, channel_name
    
    Returns:
        Dict with 'video_path' and 'thumb_path', or None if all retries fail.
    """
    config.ensure_dirs()

    vid_id = video_info.get("id", "unknown")
    url = video_info.get("url", "")
    title = video_info.get("title", "Unknown")

    if not url:
        logger.error(f"No URL provided for video {vid_id}")
        return None

    out_prefix = str(config.DOWNLOADS_DIR / f"source_{vid_id}")
    video_out = f"{out_prefix}.mp4"
    thumb_out = f"{out_prefix}.jpg"

    # Check if already downloaded
    if os.path.exists(video_out) and os.path.getsize(video_out) > 1024 * 1024:
        logger.info(f"Already downloaded: {title[:50]}...")
        return {
            "video_path": video_out,
            "thumb_path": thumb_out if os.path.exists(thumb_out) else None,
        }

    # Cookie args
    cookie_path = config.get_cookie_path()
    cookie_args = ["--cookies", cookie_path] if cookie_path else []

    # Fallback format: includes progressive stream 18 if separate streams unavailable
    fallback_format = f"{config.VIDEO_FORMAT}/18/best"

    logger.info(f"📥 Downloading video: \"{title[:60]}\" [{vid_id}]...")

    def _log_err(tier_num: int, res: subprocess.CompletedProcess):
        if res.returncode != 0 and res.stderr:
            err_lines = [l.strip() for l in res.stderr.splitlines() if l.strip() and not l.strip().startswith("See https://")]
            msg = " | ".join(err_lines[-2:]) if err_lines else res.stderr[-200:].strip()
            logger.warning(f"  Tier {tier_num} notice: {msg[:250]}")

    # ── Tier 1: Browser Impersonation (Chrome) + TLS Fingerprint Bypasser via curl-cffi ──
    logger.info("  Tier 1: Browser Impersonation (Chrome) + BotGuard solver...")
    cmd_tier1 = [
        sys.executable, "-m", "yt_dlp",
        "--impersonate", "chrome",
        "--js-runtimes", "deno,node",
        "--remote-components", "ejs:github",
        "-f", fallback_format,
        "--retries", str(config.DOWNLOAD_RETRIES),
        "--fragment-retries", str(config.DOWNLOAD_RETRIES),
        "--retry-sleep", "2",
        "--merge-output-format", "mp4",
        "--write-thumbnail",
        "--convert-thumbnails", "jpg",
        "-o", f"{out_prefix}.%(ext)s",
        "--no-playlist",
        "--no-warnings",
        *cookie_args,
        url,
    ]
    try:
        time.sleep(1.0)
        res = subprocess.run(
            cmd_tier1, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=config.DOWNLOAD_TIMEOUT
        )
        _log_err(1, res)
    except subprocess.TimeoutExpired:
        logger.warning("  Tier 1: Timeout expired")
    except Exception as e:
        logger.warning(f"  Tier 1: Error - {e}")

    # ── Tier 2: Android Direct API (Zero BotGuard, player_skip=webpage) ──
    if not _video_exists(video_out):
        logger.info("  Tier 2: Android client direct API (Bypass BotGuard)...")
        cmd_tier2 = [
            sys.executable, "-m", "yt_dlp",
            "--js-runtimes", "deno,node",
            "--remote-components", "ejs:github",
            "--extractor-args", "youtube:player_client=android;player_skip=webpage",
            "-f", fallback_format,
            "--retries", str(config.DOWNLOAD_RETRIES),
            "--fragment-retries", str(config.DOWNLOAD_RETRIES),
            "--merge-output-format", "mp4",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "-o", f"{out_prefix}.%(ext)s",
            "--no-playlist",
            "--no-warnings",
            url,
        ]
        try:
            time.sleep(2)
            res = subprocess.run(
                cmd_tier2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=config.DOWNLOAD_TIMEOUT
            )
            _log_err(2, res)
        except Exception as e:
            logger.warning(f"  Tier 2: Error - {e}")

    # ── Tier 3: Progressive format 18 single-stream fallback (Chrome impersonated) ──
    if not _video_exists(video_out):
        logger.info("  Tier 3: Progressive stream format 18 fallback (Chrome impersonated)...")
        cmd_tier3 = [
            sys.executable, "-m", "yt_dlp",
            "--impersonate", "chrome",
            "-f", "18/best",
            "--retries", str(config.DOWNLOAD_RETRIES),
            "--merge-output-format", "mp4",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "-o", f"{out_prefix}.%(ext)s",
            "--no-playlist",
            "--no-warnings",
            *cookie_args,
            url,
        ]
        try:
            time.sleep(2)
            res = subprocess.run(
                cmd_tier3, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=config.DOWNLOAD_TIMEOUT
            )
            _log_err(3, res)
        except Exception as e:
            logger.warning(f"  Tier 3: Error - {e}")

    # ── Tier 4: Safari / iOS fallback ──
    if not _video_exists(video_out):
        logger.info("  Tier 4: Safari / iOS fallback...")
        cmd_tier4 = [
            sys.executable, "-m", "yt_dlp",
            "--impersonate", "safari",
            "-f", fallback_format,
            "--retries", str(config.DOWNLOAD_RETRIES),
            "--merge-output-format", "mp4",
            "-o", f"{out_prefix}.%(ext)s",
            "--no-playlist",
            "--no-warnings",
            url,
        ]
        try:
            time.sleep(2)
            res = subprocess.run(
                cmd_tier4, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=config.DOWNLOAD_TIMEOUT
            )
            _log_err(4, res)
        except Exception as e:
            logger.warning(f"  Tier 4: Error - {e}")

    # ── Check result ──
    if _video_exists(video_out):
        size_mb = os.path.getsize(video_out) / (1024 * 1024)
        logger.info(f"✅ Download successful: {video_out} ({size_mb:.1f} MB)")

        # Find thumbnail (may have different extension)
        actual_thumb = None
        for ext in [".jpg", ".webp", ".png"]:
            p = f"{out_prefix}{ext}"
            if os.path.exists(p):
                actual_thumb = p
                break

        return {
            "video_path": video_out,
            "thumb_path": actual_thumb,
        }
    else:
        # Check if downloaded as different extension (e.g. .mkv, .webm)
        for ext in [".mkv", ".webm", ".mp4"]:
            alt_path = f"{out_prefix}{ext}"
            if os.path.exists(alt_path) and os.path.getsize(alt_path) > 1024 * 1024:
                logger.info(f"✅ Downloaded as {ext}: {alt_path}")
                return {
                    "video_path": alt_path,
                    "thumb_path": thumb_out if os.path.exists(thumb_out) else None,
                }

        logger.error(f"❌ All 4 download tiers failed for: {title[:50]} [{vid_id}]")
        return None


def _video_exists(path: str) -> bool:
    """Check if video file exists and is non-trivially sized (>1MB)."""
    return os.path.exists(path) and os.path.getsize(path) > 1024 * 1024

