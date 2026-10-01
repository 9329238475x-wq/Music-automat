"""
DJ Track Scraper & Downloader Module
Scrapes fresh (24-48h) remix tracks from curated channels using yt-dlp.
Extracts 320 kbps MP3 audio and high-resolution thumbnail posters.
"""

import os
import sys
import json
import time
import logging
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

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

    def discover_fresh_videos(self, max_per_channel: int = 5) -> List[Dict[str, Any]]:
        """Inspects /videos of each channel using yt-dlp flat-playlist (0 YouTube API Quota)."""
        candidates = []
        now = datetime.utcnow()
        cutoff_date = (now - timedelta(days=3)).strftime("%Y%m%d")

        logger.info(f"Scanning {len(self.channels)} channels for {self.profile} profile...")

        for idx, ch in enumerate(self.channels, 1):
            name = ch.get("name", "Unknown")
            url = ch.get("url", "")
            if not url and ch.get("handle"):
                url = f"https://www.youtube.com/{ch['handle']}"
            videos_url = f"{url.rstrip('/')}/videos"

            cmd = [
                "yt-dlp",
                "--extractor-args", "youtube:player_client=android,web",
                "--flat-playlist",
                "--dump-single-json",
                "--playlist-end", str(max_per_channel),
                "--no-warnings",
                "--quiet",
                videos_url
            ]

            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
                if proc.returncode != 0 or not proc.stdout.strip():
                    continue

                info = json.loads(proc.stdout)
                entries = info.get("entries") or []

                for entry in entries:
                    vid_id = entry.get("id")
                    if not vid_id or vid_id in self.history:
                        continue

                    title = entry.get("title", "")
                    duration = entry.get("duration") or 0.0
                    upload_date = entry.get("upload_date") or ""

                    # Filter out Shorts (< 60s) and full 1-2 hour nonstop mixes (> 14 mins)
                    if duration < 100 or duration > 900:
                        continue

                    # If upload_date is provided, check cutoff (or fallback to recent)
                    is_fresh = (upload_date >= cutoff_date) if upload_date else True

                    candidates.append({
                        "id": vid_id,
                        "title": title,
                        "duration": duration,
                        "upload_date": upload_date,
                        "remixer": name,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "is_fresh": is_fresh
                    })
            except Exception as e:
                logger.debug(f"Error checking channel {name}: {e}")
                continue

            if idx % 5 == 0 or idx == len(self.channels):
                logger.info(f"Scanned {idx}/{len(self.channels)} channels. Found {len(candidates)} candidates.")

        # Sort fresh tracks first, then recent
        candidates.sort(key=lambda x: (x["is_fresh"], x["upload_date"]), reverse=True)
        return candidates

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

        logger.info(f"[{idx}/{total}] Downloading: {track['title'][:40]}...")
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
        from concurrent.futures import ThreadPoolExecutor, as_completed
        candidates = self.discover_fresh_videos()
        if not candidates:
            logger.error("No valid candidates found.")
            return []

        selected = candidates[:target_count]
        logger.info(f"🚀 Starting PARALLEL download of {len(selected)} tracks (5 concurrent workers)...")

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
        logger.info(f"✅ Successfully downloaded {len(downloaded_tracks)} tracks in parallel.")
        return downloaded_tracks


if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "nagpuri"
    scraper = DJScraper(profile=profile)
    tracks = scraper.download_tracks(target_count=3)
    print(f"Downloaded {len(tracks)} test tracks.")
