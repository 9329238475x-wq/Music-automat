"""
DJ Track Scraper & Downloader Module
Scrapes fresh (12-48h) remix tracks from curated channels using yt-dlp.
STRICT RULES:
1. STRICTLY 1 SONG PER CHANNEL (Never 2 songs from the same channel).
2. Freshness priority (12h first, skips channels with no recent uploads).
3. 5x Parallel multi-threaded downloading at 320 kbps MP3.
"""

import os
import sys
import json
import time
import logging
import subprocess
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Scraper")


class DJScraper:
    def __init__(self, profile: str = "nagpuri", base_dir: Optional[str] = None):
        self.profile = profile.lower()
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.config_dir = os.path.join(self.base_dir, "config")
        self.data_dir = os.path.join(self.base_dir, "data")
        self.downloads_dir = os.path.join(self.base_dir, "downloads", self.profile)
        os.makedirs(self.downloads_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)

        self.history_file = os.path.join(self.data_dir, f"history_{self.profile}.json")
        self.history = self._load_history()

        self.channels = self._load_channels()
        self.settings = self._load_settings()

    def _load_channels(self) -> List[Dict[str, str]]:
        path = os.path.join(self.config_dir, "channels.json")
        if not os.path.exists(path):
            logger.error(f"Channels file not found at {path}")
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(self.profile, [])

    def _load_settings(self) -> Dict[str, Any]:
        path = os.path.join(self.config_dir, "settings.json")
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_history(self) -> List[str]:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read history: {e}")
        return []

    def _save_history(self):
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.history[-1000:], f, indent=2)

    def _scan_single_channel(self, ch: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Scans a single channel for its latest video.
        Enforces:
        - At most 1 song from this channel.
        - Skips if older than freshness threshold.
        - Skips shorts and long mixes.
        """
        name = ch.get("name", "Unknown")
        url = ch.get("url", "")
        if not url and ch.get("handle"):
            url = f"https://www.youtube.com/{ch['handle']}"
        videos_url = f"{url.rstrip('/')}/videos"

        cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android,web",
            "--dump-json",
            "--playlist-end", "2",
            "--no-warnings",
            "--quiet",
            videos_url
        ]

        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
            if proc.returncode != 0 or not proc.stdout.strip():
                return None

            lines = [line.strip() for line in proc.stdout.strip().split("\n") if line.strip()]
            for line in lines:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue

                vid_id = entry.get("id")
                if not vid_id or vid_id in self.history:
                    continue

                title = entry.get("title", "")
                duration = float(entry.get("duration") or 0.0)

                # Filter out Shorts (< 100s) and full 1-2 hour nonstop mixes (> 14 mins / 840s)
                if duration < 100.0 or duration > 840.0:
                    continue

                # Check timestamp age
                now_ts = time.time()
                video_ts = entry.get("timestamp") or 0
                age_hours = (now_ts - video_ts) / 3600.0 if video_ts else 999.0

                # Skip if older than 72 hours (3 days)
                if age_hours > 72.0:
                    logger.debug(f"Skipping {name}: Latest upload is {age_hours:.1f}h old.")
                    return None

                # Found the 1 best song for this channel! Return immediately (STRICT 1 PER CHANNEL)
                return {
                    "id": vid_id,
                    "title": title,
                    "duration": duration,
                    "age_hours": age_hours,
                    "remixer": name,
                    "channel_url": url,
                    "url": f"https://www.youtube.com/watch?v={vid_id}"
                }

        except Exception as e:
            logger.debug(f"Error checking channel {name}: {e}")
        return None

    def discover_fresh_videos(self) -> List[Dict[str, Any]]:
        """
        Inspects all channels concurrently with strict 1-song-per-channel enforcement.
        Ranks by freshness (12h uploads prioritized first).
        """
        logger.info(f"Scanning {len(self.channels)} channels for {self.profile} profile (Parallel Scanner)...")
        candidates = []

        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_ch = {executor.submit(self._scan_single_channel, ch): ch for ch in self.channels}
            for future in as_completed(future_to_ch):
                res = future.result()
                if res is not None:
                    candidates.append(res)

        # STRICT GUARANTEE: Exactly 1 song per channel (each candidate is from a unique remixer)
        seen_remixers = set()
        unique_candidates = []
        for c in candidates:
            if c["remixer"] not in seen_remixers:
                seen_remixers.add(c["remixer"])
                unique_candidates.append(c)

        # Sort: Freshest first (uploaded < 12h at top, then 24h, etc.)
        unique_candidates.sort(key=lambda x: x["age_hours"])

        within_12 = sum(1 for c in unique_candidates if c["age_hours"] <= 12.0)
        within_24 = sum(1 for c in unique_candidates if c["age_hours"] <= 24.0)

        logger.info(
            f"✅ Found {len(unique_candidates)} unique tracks from {len(unique_candidates)} different channels! "
            f"({within_12} within 12h, {within_24} within 24h)"
        )
        return unique_candidates

    def _download_single_track(self, item: Tuple[int, int, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        idx, total, track = item
        vid_id = track["id"]
        out_prefix = os.path.join(self.downloads_dir, f"track_{idx:02d}_{vid_id}")
        audio_out = f"{out_prefix}.mp3"
        thumb_out = f"{out_prefix}.jpg"

        if os.path.exists(audio_out) and os.path.exists(thumb_out):
            logger.info(f"[{idx}/{total}] Already cached: {track['title'][:40]}")
            track["audio_path"] = audio_out
            track["thumb_path"] = thumb_out
            return track

        cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android,web",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "320k",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "-o", f"{out_prefix}.%(ext)s",
            "--no-playlist",
            "--no-warnings",
            "--quiet",
            track["url"]
        ]

        logger.info(f"[{idx}/{total}] Downloading ({track['remixer']}): {track['title'][:35]}...")
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            if os.path.exists(audio_out):
                track["audio_path"] = audio_out
                actual_thumb = None
                for ext in [".jpg", ".webp", ".png"]:
                    p = f"{out_prefix}{ext}"
                    if os.path.exists(p):
                        actual_thumb = p
                        break
                track["thumb_path"] = actual_thumb
                return track
            else:
                err_msg = res.stderr[:150].strip() if res.stderr else "Unknown error"
                logger.warning(f"Download failed for {vid_id}: {err_msg}")
        except Exception as e:
            logger.error(f"Error downloading {vid_id}: {e}")
        return None

    def download_tracks(self, target_count: int = 25) -> List[Dict[str, Any]]:
        """Downloads selected tracks concurrently at 320 kbps using ThreadPoolExecutor."""
        candidates = self.discover_fresh_videos()
        if not candidates:
            logger.error("No valid candidates found.")
            return []

        selected = candidates[:target_count]
        logger.info(f"🚀 Starting PARALLEL download of {len(selected)} unique tracks from {len(selected)} different channels...")

        items = [(i, len(selected), track) for i, track in enumerate(selected, 1)]
        downloaded_tracks = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_track = {executor.submit(self._download_single_track, item): item for item in items}
            for future in as_completed(future_to_track):
                res = future.result()
                if res and res.get("audio_path"):
                    downloaded_tracks.append(res)
                    self.history.append(res["id"])

        self._save_history()
        logger.info(f"✅ Successfully downloaded {len(downloaded_tracks)} unique tracks from {len(downloaded_tracks)} channels.")
        return downloaded_tracks


if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "nagpuri"
    scraper = DJScraper(profile=profile)
    tracks = scraper.download_tracks(target_count=3)
    print(f"Downloaded {len(tracks)} test tracks.")
