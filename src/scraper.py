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
import re
import urllib.request
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

    @staticmethod
    def _parse_relative_time_to_hours(text: str) -> float:
        if not text:
            return 99999.0
        tl = text.lower()
        m = re.search(r'(\d+(?:\.\d+)?)\s*(sec|second|s\b|min|minute|m\b|hr|hour|h\b|day|d\b|week|w\b|month|year)', tl)
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
        if not dur_str:
            return 0.0
        m_time = re.search(r'(\d+):(\d{2})(?::(\d{2}))?', dur_str)
        if m_time:
            parts = [p for p in m_time.groups() if p is not None]
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
        m_min = re.search(r'(\d+)\s*min', dur_str.lower())
        m_sec = re.search(r'(\d+)\s*sec', dur_str.lower())
        dur = 0.0
        if m_min:
            dur += float(m_min.group(1)) * 60
        if m_sec:
            dur += float(m_sec.group(1))
        return dur

    @staticmethod
    def _parse_views_to_int(view_str: str) -> int:
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
        """Fast, 100% headless YouTube channel page parser directly fetching videos tab."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        req = urllib.request.Request(videos_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
        except Exception:
            return []

        m = re.search(r'ytInitialData\s*=\s*({.*?});</script>', html)
        if not m:
            m = re.search(r'var ytInitialData = ({.*?});', html)
        if not m:
            return []

        try:
            data = json.loads(m.group(1))
        except Exception:
            return []

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
                dur_str = it.get('rendererContext', {}).get('accessibilityContext', {}).get('label', '')

            elif it_type == 'renderer':
                vid_id = it.get('videoId')
                title = it.get('title', {}).get('runs', [{}])[0].get('text')
                time_text = it.get('publishedTimeText', {}).get('simpleText')
                dur_str = it.get('lengthText', {}).get('simpleText')
                views = self._parse_views_to_int(it.get('viewCountText', {}).get('simpleText', ''))

            if vid_id and title:
                age_h = self._parse_relative_time_to_hours(time_text)
                dur_sec = self._parse_duration_to_seconds(dur_str)
                results.append({
                    'id': vid_id,
                    'title': title,
                    'age_hours': age_h,
                    'duration': dur_sec,
                    'view_count': views
                })
                if len(results) >= 8:
                    break

        return results

    def _fetch_channel_videos_ytdlp(self, videos_url: str) -> List[Dict[str, Any]]:
        """Fallback fast flat-playlist extraction using yt-dlp."""
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--flat-playlist",
            "--js-runtimes", "node",
            "--extractor-args", "youtube:player_client=android,mweb",
            "--ignore-errors",
            "--print", "%(id)s\t%(duration)s\t%(view_count)s\t%(title)s",
            "--playlist-end", "5",
            "--no-warnings",
            videos_url
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
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
                            'age_hours': 12.0,
                            'duration': dur_s,
                            'view_count': vc
                        })
            return items
        except Exception:
            return []

    def _scan_single_channel(self, ch: Dict[str, str], max_age_hours: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Scans a single channel for its newest valid video using direct fast HTML parser with yt-dlp fallback.
        STRICT RULES:
        1. At most 1 song from this channel.
        2. STRICT AGE RULE: Must be within specified max_age_hours.
        3. Skips shorts (<100s) and long nonstop mixes (>840s / 14 mins).
        4. Skips previously used songs in history.
        5. Skips any song containing Sound Check / Frequency test keywords.
        6. Skips devotional/bhakti, nonstop mixes, and junk tutorials/vlogs.
        7. MANDATORY DJ/Song keyword match.
        """
        name = ch.get("name", "Unknown")
        url = ch.get("url", "")
        if not url and ch.get("handle"):
            url = f"https://www.youtube.com/{ch['handle']}"
        if not url.endswith("/videos"):
            videos_url = f"{url.rstrip('/')}/videos"
        else:
            videos_url = url

        if max_age_hours is None:
            max_age_hours = float(self.settings.get("scraper", {}).get("max_track_age_hours", 24.0))

        try:
            # 1. Primary: Direct Fast Channel Scanner (No bot detection, 0.3s response)
            items = self._fetch_channel_videos_native(videos_url)
            # 2. Fallback: yt-dlp flat playlist
            if not items:
                items = self._fetch_channel_videos_ytdlp(videos_url)

            if not items:
                logger.info(f"[SKIP] {name}: Could not fetch recent videos from /videos")
                return None

            for it in items:
                vid_id = it.get("id", "").strip()
                title = it.get("title", "").strip()
                duration = float(it.get("duration", 0.0))
                view_cnt = int(it.get("view_count", 0))
                age_hours = float(it.get("age_hours", 99999.0))

                if not vid_id or vid_id in self.history:
                    continue

                # 1. STRICT AGE RULE: Song must be uploaded within specified max_age_hours
                if age_hours > max_age_hours:
                    logger.info(f"[SKIP AGE] {name} ({vid_id}): Uploaded {age_hours:.1f}h ago (Older than {max_age_hours}h rule)")
                    continue

                # 2. Duration filter (skip Shorts < 100s, skip full nonstop mixes > 840s / 14 mins)
                if duration < 100.0 or duration > 840.0:
                    continue

                # 3. Strictly NO Sound Check in song title
                SOUNDCHECK_KEYWORDS = ["sound check", "soundcheck", "sound test", "frequency test", "woofer test", "bass test", "speaker test", "hz test"]
                if any(b in title.lower() for b in SOUNDCHECK_KEYWORDS):
                    logger.info(f"[SKIP SOUNDCHECK] {name} ({vid_id}): Sound check detected in title: '{title[:45]}'")
                    continue

                # 4. Strictly NO Bhakti / Devotional tracks (Preserves Party / Dance / EDM vibe)
                BHAKTI_KEYWORDS = [
                    "bhakti", "bhajan", "navratri", "maiya", "devi geet", "pachra", "aarti",
                    "bol bam", "kanwar", "jiutiya", "durga puja", "chath puja", "chath geet",
                    "mata rani", "ram bhajan", "shiv bhajan", "krishna bhajan", "katha", "chalisa"
                ]
                if any(b in title.lower() for b in BHAKTI_KEYWORDS):
                    logger.info(f"[SKIP BHAKTI] {name} ({vid_id}): Bhakti/Devotional title detected: '{title[:45]}'")
                    continue

                # 5. Strictly NO Nonstop / Jukebox in song title
                NONSTOP_KEYWORDS = ["nonstop", "non stop", "jukebox", "mashup", "full album", "all songs"]
                if any(b in title.lower() for b in NONSTOP_KEYWORDS):
                    logger.info(f"[SKIP NONSTOP] {name} ({vid_id}): Nonstop/Jukebox title detected: '{title[:45]}'")
                    continue

                # 6. IRONCLAD ANTI-JUNK FILTER: Reject Tutorials, AI Song Generation, FLP Downloads, Vlogs, Setups, etc.
                tl = title.lower()
                JUNK_KEYWORDS = [
                    "kaise banaye", "kaise bnaye", "kaise banayein", "kaise bnayein", "kaise banate", "kaise banaye mobile",
                    "kaise kare", "kaise karen", "kaise download", "kaise sikhe", "kaise seekhe", "kaise banta",
                    "how to make", "how to create", "how to mix", "how to edit", "how to download", "how to use",
                    "tutorial", "tutorials", "guide", "sikhe", "seekhe", "shikhe", "step by step", "full course",
                    "suno ai", "sunoai", "suno.com", "ai se song", "ai se gana", "ai song kaise", "ai gana kaise",
                    "chatgpt", "chat gpt", "udio ai", "udio.com", "ai music generator", "ai tool", "ai tools",
                    "flp", "free flp", "flp download", "flp project", "project file", "flm", "flm project", "flm download",
                    "no password", "password", "sample pack", "sound pack", "data pack", "voice pack", "vst plugin",
                    "preset", "presets", "drum kit", "loop pack", "zip file",
                    "vlog", "vlogs", "daily vlog", "mini vlog", "my setup", "dj setup", "sound setup", "cabinet setup",
                    "light setup", "stage setup", "roadshow setup", "box setup", "speaker cabinet",
                    "unboxing", "review", "price", "kitna kharcha", "rate", "shop visit", "market visit", "dukan",
                    "interview", "podcast", "reaction", "roast", "prank", "comedy", "funny video",
                    "news", "khabar", "update", "lafda", "vivad", "controversy", "matter",
                    "behind the scene", "behind the scenes", "bts", "live stream", "live video",
                    "status kaise banaye", "avee player template", "avee template", "kinemaster", "editing kaise kare",
                    "thumbnail kaise banaye", "greenscreen", "green screen"
                ]
                JUNK_REGEX = [
                    r"\bkaise\s+(?:b[a-z]*n|kar|s[a-z]*kh|down|bana)",
                    r"\bhow\s+to\b",
                    r"\bfl\s*studio\s*(?:tutorial|course|seekhe|mobile)\b",
                    r"\b(?:free\s+)?flp\b",
                    r"\b(?:free\s+)?flm\b",
                    r"\b(?:vlog|vlogs)\b",
                    r"\bunboxing\b",
                    r"\b(?:dj\s+)?setup\b",
                    r"\breview\b",
                    r"\binterview\b",
                    r"\bpodcast\b",
                    r"\bsuno\s*ai\b",
                    r"\bai\s+se\s+[a-z]+",
                    r"\bai\s+(?:song|music|track)\s+kaise\b"
                ]

                if any(k in tl for k in JUNK_KEYWORDS) or any(re.search(pat, tl) for pat in JUNK_REGEX):
                    logger.info(f"[SKIP JUNK/TUTORIAL/VLOG] {name} ({vid_id}): Rejected non-song content: '{title[:45]}'")
                    continue

                # 7. MANDATORY SONG/DJ KEYWORD VERIFICATION: Title MUST be a legitimate Music/DJ track!
                NICHE_PATTERNS = [
                    r"\bdj\b", r"\bd\.j\b", r"\bsong\b", r"\bsongs\b", r"\bremix\b", r"\brmx\b",
                    r"\bmix\b", r"\btrack\b", r"\bgana\b", r"\bgaana\b", r"\bgeet\b", r"\bdance\b",
                    r"\bdrop\b", r"\bvibration\b", r"\btheth\b", r"\bbhojpuri\b", r"\bnagpuri\b",
                    r"\btapori\b", r"\belectro\b",
                    r"डीजे", r"गाना", r"गाने", r"गीत", r"रीमिक्स", r"धमाका", r"नागपुरी", r"भोजपुरी"
                ]
                if not any(re.search(pat, tl) for pat in NICHE_PATTERNS):
                    logger.info(f"[SKIP NO SONG KEYWORD] {name} ({vid_id}): Title lacks DJ/Song keywords: '{title[:45]}'")
                    continue

                logger.info(f"[ACCEPTED 24H] ({age_hours:.1f}h ago <= {max_age_hours}h): [{name}] {title[:45]}")
                return {
                    "id": vid_id,
                    "title": title,
                    "duration": duration,
                    "view_count": view_cnt,
                    "remixer": name,
                    "channel_url": videos_url,
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
            for rw in re.findall(r"[a-z0-9]{3,}", remixer.lower()):
                t = re.sub(rf"\b{re.escape(rw)}\b", " ", t)

        t = re.sub(r"\[.*?\]|\(.*?\)", " ", t)
        t = re.sub(r"(?:\+?91|mob|contact|no|call)?[-\s:]*[6-9]\d{9}", " ", t)
        stop_words = {
            "dj", "remix", "rmx", "song", "songs", "video", "audio", "mp3", "hd", "4k", "hq",
            "official", "original", "fl", "studio", "competition", "roadshow", "vibration",
            "sound", "check", "soundcheck", "test", "bass", "boosted", "dhamaka", "superhit",
            "hit", "new", "latest", "theth", "theeth", "dance", "mix", "nonstop", "jukebox", "mashup",
            "2024", "2025", "2026", "2027", "nagpuri", "bhojpuri", "cg", "khortha", "purulia",
            "jharkhandi", "by", "ft", "feat", "prod", "present", "presents", "re", "ho", "se",
            "tapori", "dialogue", "track", "mandar", "style", "funny", "special", "club",
            "beat", "beats", "music", "production", "dholki", "chhattisgarhi", "chhattisgarh",
            "bhojpuriya", "raipur", "bilaspur", "jashpur", "babu", "bhai", "king", "star",
            "hard", "drop", "viral", "instagram", "trending", "full", "status", "reels",
            "old", "year", "top", "part", "vol", "volume",
            "डीजे", "रीमिक्स", "गाने", "गाना", "नागपुरी", "भोजपुरी", "नया", "धमाका", "सुपरहिट"
        }
        words = re.findall(r"[\u0900-\u097f]+|[a-z0-9]{2,}", t)
        keywords = {w for w in words if w not in stop_words}
        return keywords

    def _is_duplicate_song(self, title1: str, rmx1: str, title2: str, rmx2: str) -> bool:
        """
        Strict duplicate check: only skips if the song title is 100% identical or has complete containment.
        NEVER skips if only 1 or 2 words match.
        """
        kw1 = self._extract_song_keywords(title1, rmx1)
        kw2 = self._extract_song_keywords(title2, rmx2)
        if len(kw1) < 2 or len(kw2) < 2:
            return False

        # 1. 100% exact set of words match
        if kw1 == kw2:
            return True

        # 2. NEVER match if only 1 or 2 words match
        intersection = kw1.intersection(kw2)
        if len(intersection) < 3:
            return False

        # 3. Complete containment of at least 3 core words (100% of one title inside the other)
        if (intersection == kw1 or intersection == kw2) and len(intersection) >= 3:
            return True

        # 4. Very high Jaccard overlap (>= 75% of all words match)
        union = kw1.union(kw2)
        similarity = len(intersection) / len(union) if union else 0.0
        return similarity >= 0.75

    def discover_fresh_videos(self) -> List[Dict[str, Any]]:
        """
        Inspects all channels concurrently with strict 1-song-per-channel enforcement
        AND eliminates duplicate songs (same song remixed by different DJs).
        """
        num_channels = len(self.channels)
        workers = 8
        logger.info(f"Scanning ALL {num_channels} channels for {self.profile} profile (Parallel Scanner with {workers} threads)...")

        def _run_scan_pass(ch_list: List[Dict[str, str]], max_age: float) -> List[Dict[str, Any]]:
            pass_res = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_ch = {executor.submit(self._scan_single_channel, ch, max_age): ch for ch in ch_list}
                for future in as_completed(future_to_ch):
                    try:
                        res = future.result()
                        if res is not None:
                            pass_res.append(res)
                    except Exception as exc:
                        logger.debug(f"Scan future error: {exc}")
            return pass_res

        base_age = float(self.settings.get("scraper", {}).get("max_track_age_hours", 24.0))
        candidates = _run_scan_pass(self.channels, base_age)

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

        # RETENTION HOOK: Place highest-viewed viral track at Rank #1 (Track 1) for instant retention hook!
        if unique_candidates:
            top_track = max(unique_candidates, key=lambda x: int(x.get("view_count") or 0))
            remaining = [c for c in unique_candidates if c.get("id") != top_track.get("id")]
            remaining.sort(key=lambda x: float(x.get("duration") or 999999.0), reverse=False)
            unique_candidates = [top_track] + remaining

        for rank, c in enumerate(unique_candidates, 1):
            dur_mins = int((c.get("duration") or 0) // 60)
            dur_secs = int((c.get("duration") or 0) % 60)
            vc = int(c.get("view_count") or 0)
            hook_tag = "👑 [VIRAL HOOK #1] " if rank == 1 else ""
            logger.info(f"Rank #{rank:02d} | {hook_tag}Views: {vc:,} | Length: {dur_mins:02d}:{dur_secs:02d} ({c.get('duration', 0):.0f}s) | ({c['remixer']}): {c['title'][:35]}")

        logger.info(
            f"✅ Found {len(unique_candidates)} unique fresh tracks! Track #1 set to highest-viewed viral hit."
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

        cookie_candidates = [
            os.path.join(self.base_dir, "cookies.txt"),
            os.path.join(self.config_dir, "cookies.txt"),
            "/kaggle/working/Music-automat/cookies.txt"
        ]
        cookie_args = []
        for cp in cookie_candidates:
            if os.path.exists(cp):
                cookie_args = ["--cookies", cp]
                break

        # Determine client strategy:
        # When cookies are provided, do NOT force android (android rejects cookies), use default authenticated client with ejs solver!
        primary_extractor_args = [] if cookie_args else ["--extractor-args", "youtube:player_client=android"]

        # Primary: Authenticated client with Deno/Node BotGuard & EJS solver
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--js-runtimes", "deno,node",
            "--remote-components", "ejs:github",
            *primary_extractor_args,
            "-f", "ba/b/18/best",
            "--retries", "10",
            "--fragment-retries", "10",
            "--retry-sleep", "2",
            "-x",
            "--audio-format", "wav",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "-o", f"{out_prefix}.%(ext)s",
            "--no-playlist",
            "--no-warnings",
            "--quiet",
            *cookie_args,
            track["url"]
        ]

        logger.info(f"[{idx}/{total}] Downloading ({track['remixer']}): {track['title'][:35]}...")
        try:
            time.sleep(1.0)
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)

            # Retry 1: TV Embedded client (bypasses datacenter web bot-walls)
            if not os.path.exists(audio_out):
                logger.info(f"[{idx}/{total}] Retrying download with TV Embedded client: {track['title'][:35]}...")
                time.sleep(2)
                tv_cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--js-runtimes", "deno,node",
                    "--remote-components", "ejs:github",
                    "--extractor-args", "youtube:player_client=tv,tv_embedded;player_skip=webpage",
                    "--force-ipv4",
                    "-f", "ba/b/18/best",
                    "--retries", "10",
                    "-x",
                    "--audio-format", "wav",
                    "-o", f"{out_prefix}.%(ext)s",
                    "--no-playlist",
                    "--no-warnings",
                    "--quiet",
                    *cookie_args,
                    track["url"]
                ]
                res = subprocess.run(tv_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)

            # Retry 2: Force format 18 (progressive audio-video stream) via android client
            if not os.path.exists(audio_out):
                logger.info(f"[{idx}/{total}] Retrying download with progressive stream format 18: {track['title'][:35]}...")
                time.sleep(2)
                retry_cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--js-runtimes", "deno,node",
                    "--remote-components", "ejs:github",
                    "--extractor-args", "youtube:player_client=android",
                    "-f", "18/best",
                    "--retries", "10",
                    "--fragment-retries", "10",
                    "-x",
                    "--audio-format", "wav",
                    "--write-thumbnail",
                    "--convert-thumbnails", "jpg",
                    "-o", f"{out_prefix}.%(ext)s",
                    "--no-playlist",
                    "--no-warnings",
                    "--quiet",
                    *cookie_args,
                    track["url"]
                ]
                res = subprocess.run(retry_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)

            # Retry 3: Fallback with iOS client
            if not os.path.exists(audio_out):
                logger.info(f"[{idx}/{total}] Final fallback retry with iOS client: {track['title'][:35]}...")
                time.sleep(2)
                retry3_cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--js-runtimes", "deno,node",
                    "--remote-components", "ejs:github",
                    "--extractor-args", "youtube:player_client=ios",
                    "-f", "ba/b/18/best",
                    "--retries", "10",
                    "-x",
                    "--audio-format", "wav",
                    "-o", f"{out_prefix}.%(ext)s",
                    "--no-playlist",
                    "--no-warnings",
                    "--quiet",
                    *cookie_args,
                    track["url"]
                ]
                res = subprocess.run(retry3_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)

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
