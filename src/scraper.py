"""
DJ Track Scraper & Downloader Module
Scrapes the latest fresh remix tracks from curated channels using yt-dlp.
STRICT RULES:
1. STRICTLY 1 SONG PER CHANNEL (Never 2 songs from the same channel).
2. Parallel fast scanner across all channels (ThreadPoolExecutor).
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
        Scans a single channel for its newest valid video using fast yt-dlp metadata.
        STRICT RULES:
        1. At most 1 song from this channel.
        2. STRICT 24-HOUR RULE: If no video was uploaded within the last 24 hours, SKIP channel entirely!
        3. Skips shorts (<100s) and long nonstop mixes (>840s / 14 mins).
        4. Skips previously used songs in history.
        5. Skips any song containing Sound Check / Frequency test keywords.
        """
        name = ch.get("name", "Unknown")
        url = ch.get("url", "")
        if not url and ch.get("handle"):
            url = f"https://www.youtube.com/{ch['handle']}"
        videos_url = f"{url.rstrip('/')}/videos"

        # Configurable max age rule (STRICT 11 HOURS DEFAULT)
        max_age_hours = float(self.settings.get("scraper", {}).get("max_track_age_hours", 24.0))

        cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android",
            "--ignore-errors",
            "--print", "%(id)s\t%(duration)s\t%(view_count)s\t%(timestamp)s\t%(title)s",
            "--playlist-end", "3",
            "--no-warnings",
            "--quiet",
            videos_url
        ]

        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
            if not proc.stdout or not proc.stdout.strip():
                logger.info(f"[SKIP] {name}: Could not fetch recent videos.")
                return None

            lines = proc.stdout.strip().splitlines()
            now_ts = time.time()

            for line in lines:
                parts = line.split("	")
                if len(parts) < 5:
                    continue

                vid_id = parts[0].strip()
                dur_str = parts[1].strip()
                vc_str = parts[2].strip()
                ts_str = parts[3].strip()
                title = parts[4].strip()

                if not vid_id or vid_id in self.history:
                    continue

                # 1. STRICT 24-HOUR RULE: Song must be uploaded within last 11 hours!
                try:
                    timestamp = float(ts_str) if ts_str and ts_str != "None" else 0.0
                except (ValueError, TypeError):
                    timestamp = 0.0

                if timestamp <= 0.0:
                    continue

                age_hours = (now_ts - timestamp) / 3600.0
                if age_hours > max_age_hours:
                    logger.info(f"[SKIP AGE] {name} ({vid_id}): Uploaded {age_hours:.1f}h ago (Older than {max_age_hours}h rule)")
                    continue

                # 2. Duration filter (skip Shorts < 100s, skip full nonstop mixes > 840s / 14 mins)
                try:
                    duration = float(dur_str) if dur_str and dur_str != "None" else 0.0
                except (ValueError, TypeError):
                    duration = 0.0

                if duration < 100.0 or duration > 840.0:
                    continue

                # 3. Strictly NO Sound Check in song title
                if any(b in title.lower() for b in ["sound check", "soundcheck", "sound test", "frequency test", "woofer test"]):
                    logger.info(f"[SKIP SOUNDCHECK] {name} ({vid_id}): Sound check detected in title")
                    continue

                # 4. Strictly NO Bhakti / Devotional tracks (Preserves Party / Dance / EDM vibe)
                BHAKTI_KEYWORDS = ["bhakti", "bhajan", "navratri", "maiya", "devi geet", "pachra", "aarti", "bol bam", "kanwar", "jiutiya", "durga puja", "chath puja", "chath geet"]
                if any(b in title.lower() for b in BHAKTI_KEYWORDS):
                    logger.info(f"[SKIP BHAKTI] {name} ({vid_id}): Bhakti/Devotional title detected")
                    continue

                # 5. Strictly NO Nonstop / Jukebox in song title
                NONSTOP_KEYWORDS = ["nonstop", "non stop", "jukebox", "mashup"]
                if any(b in title.lower() for b in NONSTOP_KEYWORDS):
                    logger.info(f"[SKIP NONSTOP] {name} ({vid_id}): Nonstop/Jukebox title detected")
                    continue

                # 4. Valid fresh song found within 11 hours!
                try:
                    view_cnt = int(vc_str) if vc_str and vc_str != "None" else 0
                except (ValueError, TypeError):
                    view_cnt = 0

                logger.info(f"[ACCEPTED 24H] ({age_hours:.1f}h ago <= {max_age_hours}h): [{name}] {title[:45]}")
                return {
                    "id": vid_id,
                    "title": title,
                    "duration": duration,
                    "view_count": view_cnt,
                    "remixer": name,
                    "channel_url": url,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "age_hours": age_hours
                }

            logger.info(f"[SKIP CHANNEL] '{name}': No fresh upload within the last {max_age_hours} hours.")

        except Exception as e:
            logger.debug(f"Error checking channel {name}: {e}")
        return None

    def _extract_song_keywords(self, title: str, remixer: str = "") -> set:
        """Extracts core distinguishing song keywords from title, stripping promos and stop words."""
        import re
        t = title.lower()
        if remixer:
            t = t.replace(remixer.lower(), " ")
        t = re.sub(r"\[.*?\]|\(.*?\)", " ", t)
        t = re.sub(r"(?:\+?91|mob|contact|no|call)?[-\s:]*[6-9]\d{9}", " ", t)
        stop_words = {
            "dj", "remix", "rmx", "song", "songs", "video", "audio", "mp3", "hd", "4k", "hq",
            "official", "original", "fl", "studio", "competition", "roadshow", "vibration",
            "sound", "check", "soundcheck", "test", "bass", "boosted", "dhamaka", "superhit",
            "hit", "new", "latest", "theth", "dance", "mix", "nonstop", "jukebox", "mashup",
            "2024", "2025", "2026", "2027", "nagpuri", "bhojpuri", "cg", "khortha", "purulia",
            "jharkhandi", "by", "ft", "feat", "prod", "present", "presents", "re", "ho", "se",
            "डीजे", "रीमिक्स", "गाने", "गाना", "नागपुरी", "भोजपुरी", "नया", "धमाका", "सुपरहिट"
        }
        words = re.findall(r"[\u0900-\u097f]+|[a-z0-9]{3,}", t)
        keywords = {w for w in words if w not in stop_words}
        return keywords

    def _is_duplicate_song(self, title1: str, rmx1: str, title2: str, rmx2: str) -> bool:
        """Checks if two titles refer to the exact same song using keyword fingerprinting."""
        kw1 = self._extract_song_keywords(title1, rmx1)
        kw2 = self._extract_song_keywords(title2, rmx2)
        if not kw1 or not kw2:
            return False
        intersection = kw1.intersection(kw2)
        union = kw1.union(kw2)
        similarity = len(intersection) / len(union) if union else 0.0
        is_subset = len(intersection) >= 2 and (len(intersection) == len(kw1) or len(intersection) == len(kw2))
        return similarity >= 0.50 or len(intersection) >= 3 or is_subset

    def discover_fresh_videos(self) -> List[Dict[str, Any]]:
        """
        Inspects all channels concurrently with strict 1-song-per-channel enforcement
        AND eliminates duplicate songs (same song remixed by different DJs).
        """
        logger.info(f"Scanning {len(self.channels)} channels for {self.profile} profile (Parallel Scanner)...")
        candidates = []

        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_ch = {executor.submit(self._scan_single_channel, ch): ch for ch in self.channels}
            for future in as_completed(future_to_ch):
                res = future.result()
                if res is not None:
                    candidates.append(res)

        # STRICT GUARANTEE: Exactly 1 song per channel AND 0 duplicate songs in mix!
        seen_remixers = set()
        seen_channel_urls = set()
        unique_candidates = []
        for c in candidates:
            # 1. Remixer & Channel URL check: strictly 1 song per channel (case-insensitive & trimmed)
            norm_remixer = c["remixer"].strip().lower()
            norm_url = c.get("channel_url", "").strip().lower().rstrip("/")
            if norm_remixer in seen_remixers or (norm_url and norm_url in seen_channel_urls):
                logger.info(f"[SKIP DUPLICATE CHANNEL] '{c['remixer']}' already represented.")
                continue

            # 2. Song Title duplicate check: check against all already accepted tracks
            is_dup = False
            for existing in unique_candidates:
                if self._is_duplicate_song(c["title"], c["remixer"], existing["title"], existing["remixer"]):
                    logger.info(
                        f"[SKIP DUPLICATE SONG] '{c['title'][:40]}' ({c['remixer']}) matches '{existing['title'][:40]}' ({existing['remixer']}) -> Skipping to prevent repeat song!"
                    )
                    is_dup = True
                    break

            if is_dup:
                continue

            seen_remixers.add(norm_remixer)
            if norm_url:
                seen_channel_urls.add(norm_url)
            unique_candidates.append(c)

        # SORT BY DURATION ASCENDING: Shortest track length at the very top (Track 1, 2, 3...)
        unique_candidates.sort(key=lambda x: float(x.get("duration") or 999999.0), reverse=False)
        for rank, c in enumerate(unique_candidates, 1):
            dur_mins = int((c.get("duration") or 0) // 60)
            dur_secs = int((c.get("duration") or 0) % 60)
            logger.info(f"Rank #{rank:02d} | Length: {dur_mins:02d}:{dur_secs:02d} ({c.get('duration', 0):.0f}s) | ({c['remixer']}): {c['title'][:40]}")

        logger.info(
            f"✅ Found {len(unique_candidates)} unique fresh tracks sorted by shortest track length first from {len(unique_candidates)} channels!"
        )
        return unique_candidates

    def _download_single_track(self, item: Tuple[int, int, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        idx, total, track = item
        vid_id = track["id"]
        out_prefix = os.path.join(self.downloads_dir, f"track_{idx:02d}_{vid_id}")
        audio_out = f"{out_prefix}.wav"
        thumb_out = f"{out_prefix}.jpg"

        if os.path.exists(audio_out) and os.path.exists(thumb_out):
            logger.info(f"[{idx}/{total}] Already cached: {track['title'][:40]}")
            track["audio_path"] = audio_out
            track["thumb_path"] = thumb_out
            return track

        cmd = [
            "yt-dlp",
            "--js-runtimes", "node",
            "--extractor-args", "youtube:player_client=android,web,tv",
            "-x",
            "--audio-format", "wav",
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
            # If failed, retry with ios client
            if not os.path.exists(audio_out):
                time.sleep(2)
                retry_cmd = list(cmd)
                retry_cmd[4] = "youtube:player_client=tv_embedded,mweb"
                res = subprocess.run(retry_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)

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

    def download_tracks(self, target_count: int | None = None) -> List[Dict[str, Any]]:
        """Downloads selected tracks concurrently at 320 kbps using ThreadPoolExecutor."""
        candidates = self.discover_fresh_videos()
        if not candidates:
            logger.error("No valid candidates found.")
            return []

        if target_count is not None and target_count > 0:
            selected = candidates[:target_count]
        else:
            selected = candidates
        logger.info(f"🚀 Starting PARALLEL download of {len(selected)} unique tracks from {len(selected)} different channels...")

        items = [(i, len(selected), track) for i, track in enumerate(selected, 1)]
        downloaded_tracks = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_track = {}
            for item in items:
                future_to_track[executor.submit(self._download_single_track, item)] = item
                time.sleep(1.5)  # Anti-Bot: human jitter delay prevents YouTube 429 rate limits
            for future in as_completed(future_to_track):
                res = future.result()
                if res and res.get("audio_path"):
                    downloaded_tracks.append(res)
                    self.history.append(res["id"])

        # Preserve strict ascending order by track length so shortest songs play first!
        downloaded_tracks.sort(key=lambda x: float(x.get("duration") or 999999.0), reverse=False)
        self._save_history()
        logger.info(f"✅ Successfully downloaded {len(downloaded_tracks)} unique tracks (ordered by length: shortest to longest).")
        return downloaded_tracks


if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "nagpuri"
    scraper = DJScraper(profile=profile)
    tracks = scraper.download_tracks(target_count=3)
    print(f"Downloaded {len(tracks)} test tracks.")
