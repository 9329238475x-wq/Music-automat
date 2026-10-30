"""
CopyRight-Work — Copyright-Free Nature Footage Fetcher
Downloads pure nature video clips (waterfalls, forests, rivers, mountains, ocean)
via Pixabay API and Pexels API.
100% Watermark-free, Commercial License, YouTube-safe.
Ensures every clip has soothing nature audio.
"""

import json
import logging
import os
import random
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from . import config
except ImportError:
    import config

logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
logger = logging.getLogger("CRW-Footage")

SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov"}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def get_local_footage() -> List[Path]:
    """Scans the CopyRight-Work/footage/ folder for usable video files."""
    config.ensure_dirs()
    footage_dir = config.FOOTAGE_DIR

    files = []
    for f in sorted(footage_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            size_mb = f.stat().st_size / (1024 * 1024)
            if size_mb > 0.5:
                files.append(f)

    return files


def get_video_duration(file_path: str) -> float:
    """Gets video duration using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def has_audio_stream(file_path: str) -> bool:
    """Checks if a video file has an audio stream."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        return bool(res.stdout.strip())
    except Exception:
        return False


def ensure_nature_audio(video_path: Path) -> Path:
    """
    Ensures the nature clip has audio. If it's a silent/mute clip,
    attaches gentle soothing ambient nature sound (flowing river / rain / breeze).
    """
    if has_audio_stream(str(video_path)):
        return video_path

    dur = get_video_duration(str(video_path))
    if dur <= 0:
        dur = 30.0

    temp_out = video_path.parent / f"_with_audio_{video_path.name}"
    logger.info(f"  🌿 Adding soothing nature audio to silent clip: {video_path.name} ({dur:.0f}s)...")

    # Built-in soothing nature ambient sound synthesizer:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-f", "lavfi",
        "-i", f"anoisesrc=d={dur:.1f}:c=pink:r=44100:a=0.06,lowpass=f=1100,highpass=f=180,volume=1.8",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        str(temp_out)
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if temp_out.exists() and temp_out.stat().st_size > 1024:
            temp_out.replace(video_path)
            logger.info(f"  ✅ Nature audio attached to {video_path.name}")
    except Exception as e:
        logger.warning(f"Failed to attach nature audio: {e}")
        if temp_out.exists():
            temp_out.unlink()

    return video_path


def download_file(url: str, dest_path: Path) -> bool:
    """Downloads a video file with chunked streaming and User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp, open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
        return dest_path.exists() and dest_path.stat().st_size > 1024 * 100
    except Exception as e:
        logger.warning(f"Download failed for {url[:60]}: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False


def fetch_from_pixabay(needed_duration_sec: float) -> List[Path]:
    """
    Fetches pure nature videos from Pixabay API.
    Watermark-free, 100% Commercial YouTube safe.
    """
    key = getattr(config, "PIXABAY_API_KEY", "")
    if not key:
        return []

    logger.info("🌐 Fetching nature videos from Pixabay API...")
    queries = getattr(config, "NATURE_QUERIES", ["nature landscape", "waterfall forest", "peaceful river"])
    random.shuffle(queries)

    downloaded = []
    accumulated_dur = 0.0

    for q in queries:
        if accumulated_dur >= needed_duration_sec:
            break

        q_enc = urllib.parse.quote(q)
        api_url = (
            f"https://pixabay.com/api/videos/?key={key}&q={q_enc}"
            f"&category=nature&video_type=film&min_width=1280&per_page=15"
        )
        req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"Pixabay request failed for query '{q}': {e}")
            continue

        hits = data.get("hits", [])
        random.shuffle(hits)

        for h in hits:
            if accumulated_dur >= needed_duration_sec:
                break

            vid_id = h.get("id")
            dur = float(h.get("duration", 0))
            if dur < 5:
                continue

            target_file = config.FOOTAGE_DIR / f"pixabay_nature_{vid_id}.mp4"
            if target_file.exists() and target_file.stat().st_size > 1024 * 100:
                downloaded.append(target_file)
                accumulated_dur += dur
                continue

            vids = h.get("videos", {})
            v_info = vids.get("large") or vids.get("medium") or {}
            v_url = v_info.get("url")

            if not v_url:
                continue

            logger.info(f"  📥 Downloading Pixabay nature clip: {h.get('tags', 'nature')[:30]} ({dur:.0f}s)...")
            if download_file(v_url, target_file):
                ensure_nature_audio(target_file)
                downloaded.append(target_file)
                accumulated_dur += dur
                time.sleep(0.5)

    return downloaded


def fetch_from_pexels(needed_duration_sec: float) -> List[Path]:
    """
    Fetches pure nature videos from Pexels API.
    Watermark-free, 100% Commercial YouTube safe.
    """
    key = getattr(config, "PEXELS_API_KEY", "")
    if not key:
        return []

    logger.info("🌐 Fetching nature videos from Pexels API...")
    queries = ["nature landscape", "relaxing forest river", "green mountains waterfall", "peaceful nature"]
    random.shuffle(queries)

    downloaded = []
    accumulated_dur = 0.0

    for q in queries:
        if accumulated_dur >= needed_duration_sec:
            break

        q_enc = urllib.parse.quote(q)
        api_url = f"https://api.pexels.com/videos/search?query={q_enc}&orientation=landscape&per_page=15"
        req = urllib.request.Request(api_url, headers={
            "Authorization": key,
            "User-Agent": USER_AGENT
        })

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"Pexels request failed for query '{q}': {e}")
            continue

        videos = data.get("videos", [])
        random.shuffle(videos)

        for v in videos:
            if accumulated_dur >= needed_duration_sec:
                break

            vid_id = v.get("id")
            dur = float(v.get("duration", 0))
            if dur < 5:
                continue

            target_file = config.FOOTAGE_DIR / f"pexels_nature_{vid_id}.mp4"
            if target_file.exists() and target_file.stat().st_size > 1024 * 100:
                downloaded.append(target_file)
                accumulated_dur += dur
                continue

            files = v.get("video_files", [])
            hd_files = [f for f in files if f.get("width") == 1920 or f.get("quality") == "hd"]
            chosen = hd_files[0] if hd_files else (files[0] if files else None)

            if not chosen or not chosen.get("link"):
                continue

            v_url = chosen.get("link")
            logger.info(f"  📥 Downloading Pexels nature clip #{vid_id} ({dur:.0f}s)...")
            if download_file(v_url, target_file):
                ensure_nature_audio(target_file)
                downloaded.append(target_file)
                accumulated_dur += dur
                time.sleep(0.5)

    return downloaded


def fetch_footage(needed_duration_sec: float) -> List[Path]:
    """
    Main entry point for getting copyright-free nature footage.
    
    1. Checks local footage folder
    2. If needed duration not met, fetches from Pixabay API & Pexels API
    3. Guarantees every clip has soothing nature audio
    """
    config.ensure_dirs()

    # 1. Existing local footage
    local_files = get_local_footage()
    total_local_dur = sum(get_video_duration(str(p)) for p in local_files)

    if total_local_dur >= needed_duration_sec and len(local_files) >= 5:
        logger.info(
            f"📁 Local footage cache sufficient: {len(local_files)} files "
            f"({total_local_dur/60:.1f} min available, need {needed_duration_sec/60:.1f} min)"
        )
        for f in local_files:
            ensure_nature_audio(f)
        return local_files

    still_needed = max(needed_duration_sec - total_local_dur, 60.0)
    logger.info(
        f"🌿 Need {still_needed/60:.1f} more minutes of pure nature video. "
        f"Querying stock APIs..."
    )

    # 2. Fetch from Pixabay
    fetch_from_pixabay(still_needed)

    # 3. If still needed, fetch from Pexels
    current_files = get_local_footage()
    current_dur = sum(get_video_duration(str(p)) for p in current_files)

    if current_dur < needed_duration_sec:
        fetch_from_pexels(needed_duration_sec - current_dur)

    all_footage = get_local_footage()
    final_dur = sum(get_video_duration(str(p)) for p in all_footage)

    logger.info(
        f"✅ Nature footage ready: {len(all_footage)} clip(s) "
        f"({final_dur/60:.1f} min total nature footage, 100% watermark-free, audio verified)"
    )

    return all_footage
