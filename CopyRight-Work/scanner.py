"""
CopyRight-Work — Channel Scanner
Scans source channels to find 2hr+ videos uploaded within the last 3 days.
Uses direct HTTP fetch + ytInitialData JSON parsing (zero API quota).
Fallback: yt-dlp --flat-playlist.
"""

import json
import logging
import re
import sys
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from . import config
except ImportError:
    import config

logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
logger = logging.getLogger("CRW-Scanner")


class VideoScanner:
    """Scans copy_right_work source channels for 2hr+ videos."""

    def __init__(self):
        self.channels = self._load_channels()
        self.history = self._load_history()

    def _load_channels(self) -> List[Dict[str, str]]:
        """Load channel list from channels.json under copy_right_work key."""
        path = config.CHANNELS_JSON
        if not path.exists():
            logger.error(f"channels.json not found: {path}")
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            channels = data.get(config.PROFILE_KEY, [])
            logger.info(f"Loaded {len(channels)} source channels for '{config.PROFILE_KEY}'")
            return channels
        except Exception as e:
            logger.error(f"Failed to load channels.json: {e}")
            return []

    def _load_history(self) -> List[str]:
        """Load previously processed video IDs."""
        if config.HISTORY_FILE.exists():
            try:
                with open(config.HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    # ─── YouTube Page Parsing ─────────────────────────────────────────────

    @staticmethod
    def _parse_relative_time_to_hours(text: str) -> float:
        """Parse YouTube's relative time text (e.g. '2 days ago') to hours."""
        if not text:
            return 99999.0
        tl = text.lower()
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(sec|second|s\b|min|minute|m\b|hr|hour|h\b|day|d\b|week|w\b|month|year)',
            tl
        )
        if not m:
            return 99999.0
        val = float(m.group(1))
        unit = m.group(2)
        if unit in ['s', 'sec', 'second']:
            return val / 3600.0
        elif unit in ['m', 'min', 'minute']:
            return val / 60.0
        elif unit in ['h', 'hr', 'hour']:
            return val
        elif unit in ['d', 'day']:
            return val * 24.0
        elif unit in ['w', 'week']:
            return val * 24.0 * 7.0
        elif unit in ['month']:
            return val * 24.0 * 30.0
        elif unit in ['year']:
            return val * 24.0 * 365.0
        return 99999.0

    @staticmethod
    def _parse_duration_to_seconds(dur_str: str) -> float:
        """Parse duration string (e.g. '2:15:30', '135 min') to seconds."""
        if not dur_str:
            return 0.0
        # HH:MM:SS or MM:SS format
        m_time = re.search(r'(\d+):(\d{2})(?::(\d{2}))?', dur_str)
        if m_time:
            parts = [p for p in m_time.groups() if p is not None]
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
        # "X min Y sec" format
        m_min = re.search(r'(\d+)\s*min', dur_str.lower())
        m_sec = re.search(r'(\d+)\s*sec', dur_str.lower())
        dur = 0.0
        if m_min:
            dur += float(m_min.group(1)) * 60
        if m_sec:
            dur += float(m_sec.group(1))
        # Accessibility label: "X hours, Y minutes, Z seconds"
        m_hrs = re.search(r'(\d+)\s*hour', dur_str.lower())
        if m_hrs:
            dur += float(m_hrs.group(1)) * 3600
        return dur

    @staticmethod
    def _parse_views_to_int(view_str: str) -> int:
        """Parse view count string to integer."""
        if not view_str:
            return 0
        vs = str(view_str).lower().replace(',', '')
        m = re.search(r'([\d.]+)\s*([kmb])?', vs)
        if not m:
            return 0
        val = float(m.group(1))
        mult = m.group(2)
        if mult == 'k':
            return int(val * 1000)
        if mult == 'm':
            return int(val * 1000000)
        if mult == 'b':
            return int(val * 1000000000)
        return int(val)

    def _fetch_channel_videos_native(self, videos_url: str) -> List[Dict[str, Any]]:
        """
        Direct HTTP fetch of YouTube channel /videos page.
        Parses ytInitialData JSON for video metadata.
        Zero API quota, ~0.3s response time.
        """
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
        }
        req = urllib.request.Request(videos_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=config.SCAN_TIMEOUT) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            logger.debug(f"HTTP fetch failed for {videos_url}: {e}")
            return []

        # Extract ytInitialData JSON
        m = re.search(r'ytInitialData\s*=\s*({.*?});</script>', html)
        if not m:
            m = re.search(r'var ytInitialData = ({.*?});', html)
        if not m:
            return []

        try:
            data = json.loads(m.group(1))
        except Exception:
            return []

        # Recursive finder for both lockupViewModel and videoRenderer
        def find_items(obj):
            if isinstance(obj, dict):
                if 'lockupViewModel' in obj:
                    yield ('lockup', obj['lockupViewModel'])
                if 'videoRenderer' in obj:
                    yield ('renderer', obj['videoRenderer'])
                for v in obj.values():
                    yield from find_items(v)
            elif isinstance(obj, list):
                for item in obj:
                    yield from find_items(item)

        results = []
        for it_type, it in find_items(data):
            vid_id = None
            title = None
            time_text = None
            dur_str = None
            views = 0

            if it_type == 'lockup':
                vid_id = it.get('contentId')
                meta = it.get('metadata', {}).get('lockupMetadataViewModel', {})
                title = meta.get('title', {}).get('content')
                rows = meta.get('metadata', {}).get('contentMetadataViewModel', {}).get('metadataRows', [])
                for r in rows:
                    for p in r.get('metadataParts', []):
                        acc = p.get('accessibilityLabel', '')
                        txt = p.get('text', {}).get('content', '')
                        if 'ago' in acc or 'ago' in txt:
                            time_text = acc or txt
                        if 'view' in acc or 'view' in txt:
                            views = self._parse_views_to_int(acc or txt)
                dur_str = it.get('rendererContext', {}).get(
                    'accessibilityContext', {}
                ).get('label', '')

            elif it_type == 'renderer':
                vid_id = it.get('videoId')
                title = it.get('title', {}).get('runs', [{}])[0].get('text')
                time_text = it.get('publishedTimeText', {}).get('simpleText')
                dur_str = it.get('lengthText', {}).get('simpleText')
                views = self._parse_views_to_int(
                    it.get('viewCountText', {}).get('simpleText', '')
                )

            if vid_id and title:
                age_h = self._parse_relative_time_to_hours(time_text)
                dur_sec = self._parse_duration_to_seconds(dur_str)
                results.append({
                    'id': vid_id,
                    'title': title,
                    'age_hours': age_h,
                    'duration_sec': dur_sec,
                    'view_count': views,
                })
                if len(results) >= config.SCAN_MAX_VIDEOS_PER_CHANNEL:
                    break

        return results

    def _fetch_channel_videos_ytdlp(self, videos_url: str) -> List[Dict[str, Any]]:
        """Fallback: yt-dlp flat-playlist scan (metadata only, no download)."""
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--flat-playlist",
            "--js-runtimes", "node",
            "--extractor-args", "youtube:player_client=android,mweb",
            "--ignore-errors",
            "--print", "%(id)s\t%(duration)s\t%(view_count)s\t%(title)s",
            "--playlist-end", "8",
            "--no-warnings",
            videos_url
        ]
        try:
            proc = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=30
            )
            if not proc.stdout or not proc.stdout.strip():
                return []
            items = []
            for line in proc.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 4:
                    vid_id = parts[0].strip()
                    dur_s = self._parse_duration_to_seconds(parts[1].strip())
                    vc = self._parse_views_to_int(parts[2].strip())
                    t = parts[3].strip()
                    if vid_id and t:
                        items.append({
                            'id': vid_id,
                            'title': t,
                            'age_hours': 12.0,  # yt-dlp flat-playlist doesn't give upload date
                            'duration_sec': dur_s,
                            'view_count': vc,
                        })
            return items
        except Exception as e:
            logger.debug(f"yt-dlp fallback scan failed: {e}")
            return []

    # ─── Single Channel Scan ─────────────────────────────────────────────

    def _scan_single_channel(
        self, ch: Dict[str, str], max_age_hours: float
    ) -> Dict[str, Any]:
        """
        Scans one channel for 2hr+ qualifying videos AND collects all videos within 48h
        for finding the most-viewed description.
        """
        name = ch.get("name", "Unknown")
        url = ch.get("url", "")
        if not url and ch.get("handle"):
            url = f"https://www.youtube.com/{ch['handle']}"
        if not url.endswith("/videos"):
            videos_url = f"{url.rstrip('/')}/videos"
        else:
            videos_url = url

        # Primary: Direct HTML parser
        items = self._fetch_channel_videos_native(videos_url)
        # Fallback: yt-dlp flat-playlist
        if not items:
            items = self._fetch_channel_videos_ytdlp(videos_url)

        if not items:
            logger.debug(f"[SKIP] {name}: No videos found")
            return {"qualifying": [], "recent_48h": []}

        qualifying = []
        recent_48h = []
        for it in items:
            vid_id = it.get("id", "").strip()
            dur_sec = it.get("duration_sec", 0)
            age_h = it.get("age_hours", 99999.0)

            v_info = {
                'id': vid_id,
                'title': it.get('title', ''),
                'duration_sec': dur_sec,
                'age_hours': age_h,
                'view_count': it.get('view_count', 0),
                'channel_name': name,
                'channel_handle': ch.get('handle', ''),
                'url': f"https://www.youtube.com/watch?v={vid_id}",
            }

            # Collect any video within 2 days (48 hours) for description copying
            if age_h <= 48.0:
                recent_48h.append(v_info)

            # Skip if already processed in history
            if vid_id in self.history:
                continue

            # Duration filter: must be 2hr+ (7200 seconds)
            if dur_sec < config.MIN_VIDEO_DURATION_SEC:
                continue

            # Age filter (can be bypassed in extended mode)
            if max_age_hours > 0 and age_h > max_age_hours:
                continue

            qualifying.append(v_info)

        if qualifying:
            logger.info(
                f"[HIT] {name}: Found {len(qualifying)} qualifying 2hr+ video(s)"
            )
        else:
            logger.debug(f"[SKIP] {name}: No 2hr+ videos within {max_age_hours}hr")

        return {"qualifying": qualifying, "recent_48h": recent_48h}

    # ─── Main Scan ────────────────────────────────────────────────────────

    def scan_channels(self) -> Optional[Dict[str, Any]]:
        """
        Main scan entry point:
          1. Finds the latest 2hr+ video to download & edit.
          2. Finds the highest-viewed video in the last 2 days (48hr) across all channels.
          3. Copies the full viral description from that top video.
        
        Returns:
            Info dict of chosen video with 'description' attached, or None.
        """
        if not self.channels:
            logger.error("No source channels loaded!")
            return None

        def _parallel_scan(channels, max_age_hours):
            all_qualifying = []
            all_recent_48h = []
            with ThreadPoolExecutor(max_workers=config.SCAN_WORKERS) as executor:
                futures = {
                    executor.submit(self._scan_single_channel, ch, max_age_hours): ch
                    for ch in channels
                }
                for future in as_completed(futures):
                    try:
                        res = future.result()
                        if res:
                            all_qualifying.extend(res.get("qualifying", []))
                            all_recent_48h.extend(res.get("recent_48h", []))
                    except Exception as exc:
                        logger.debug(f"Scan error: {exc}")
            return all_qualifying, all_recent_48h

        # ── Stage 1: Within 3 days ──
        logger.info(
            f"━━ Stage 1: Scanning {len(self.channels)} channels "
            f"(last {config.MAX_AGE_HOURS}hr, 2hr+ duration)..."
        )
        candidates, recent_48h = _parallel_scan(self.channels, config.MAX_AGE_HOURS)

        chosen = None
        if candidates:
            # Sort by age (most recent first)
            candidates.sort(key=lambda x: x['age_hours'])
            chosen = candidates[0]
            logger.info(
                f"✅ Stage 1 SUCCESS: Found {len(candidates)} candidate(s). "
                f"Choosing latest for video: \"{chosen['title'][:50]}\" "
                f"({chosen['duration_sec']/3600:.1f}hr, "
                f"{chosen['age_hours']:.1f}hr ago) "
                f"from [{chosen['channel_name']}]"
            )
        else:
            # ── Stage 2: Extended scan (no time limit) ──
            logger.info(
                "⚠️ Stage 1 found nothing. "
                "Stage 2: Extended scan (no time limit, all channels)..."
            )
            candidates, ext_48h = _parallel_scan(self.channels, 0)
            if ext_48h:
                recent_48h.extend(ext_48h)

            if candidates:
                candidates.sort(key=lambda x: x['age_hours'])
                chosen = candidates[0]
                logger.info(
                    f"✅ Stage 2 SUCCESS: Found {len(candidates)} candidate(s). "
                    f"Choosing latest for video: \"{chosen['title'][:50]}\" "
                    f"({chosen['duration_sec']/3600:.1f}hr, "
                    f"{chosen['age_hours']:.1f}hr ago) "
                    f"from [{chosen['channel_name']}]"
                )

        if not chosen:
            logger.error("❌ No 2hr+ video found in any channel (both stages failed).")
            return None

        # ── Description: Copy from highest viewed video in last 2 days (48h) ──
        viral_video = None
        if recent_48h:
            viral_video = max(recent_48h, key=lambda x: x.get("view_count", 0))
            logger.info(
                f"🔥 Most-viewed video in last 2 days (48h):\n"
                f"   Title:   \"{viral_video['title'][:55]}\"\n"
                f"   Views:   {viral_video.get('view_count', 0):,}\n"
                f"   Age:     {viral_video.get('age_hours', 0):.1f}h ago\n"
                f"   Channel: {viral_video.get('channel_name')}"
            )
        else:
            viral_video = chosen
            logger.info("ℹ️ No separate 48h video found for description. Using chosen video.")

        logger.info(f"📋 Fetching full description from viral video ({viral_video['url']})...")
        copied_desc = fetch_video_description(viral_video["url"])

        if copied_desc:
            chosen["description"] = copied_desc
            chosen["desc_source_title"] = viral_video["title"]
            chosen["desc_source_views"] = viral_video.get("view_count", 0)
            chosen["desc_source_channel"] = viral_video.get("channel_name", "")
            logger.info(f"✅ Successfully copied full description ({len(copied_desc)} characters)!")
        else:
            logger.warning("Could not fetch description from viral video. Using fallback.")
            chosen["description"] = f"{chosen['title']}\n\nUploaded via DJ JAY LAL BARBASPUR"

        return chosen


def fetch_video_description(video_url: str) -> str:
    """Fetches full description of a YouTube video using yt-dlp with cookies."""
    cookie_path = config.get_cookie_path()
    cookie_args = ["--cookies", cookie_path] if cookie_path else []
    cmd = [
        sys.executable, "-m", "yt_dlp",
        *cookie_args,
        "--skip-download",
        "--no-warnings",
        "--quiet",
        "-j",
        video_url
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
        if res.stdout:
            data = json.loads(res.stdout)
            return data.get("description", "").strip()
    except Exception as e:
        logger.warning(f"Failed to fetch description from {video_url}: {e}")
    return ""

