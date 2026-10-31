"""
CopyRight-Work Pipeline — Configuration
All configurable values for the copy_right_work pipeline.
"""

import os
from pathlib import Path

# === Paths ===
BASE_DIR = Path(__file__).parent                              # CopyRight-Work/
PROJECT_ROOT = BASE_DIR.parent                                # c:\Music-automat
CHANNELS_JSON = PROJECT_ROOT / "config" / "channels.json"
WATERMARK_PATH = PROJECT_ROOT / "assets" / "Copyright Work.png"
DOWNLOADS_DIR = BASE_DIR / "downloads"
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"
HISTORY_FILE = BASE_DIR / "history.json"
FOOTAGE_DIR = BASE_DIR / "footage"                            # Local footage folder (manual/API)

# Cookie paths (same priority order as main scraper)
COOKIE_CANDIDATES = [
    PROJECT_ROOT / "cookies.txt",
    PROJECT_ROOT / "config" / "cookies.txt",
    Path("/kaggle/working/Music-automat/cookies.txt"),
]

# === Scanner Settings ===
PROFILE_KEY = "copy_right_work"             # channels.json में key
MAX_AGE_HOURS = 72                          # 3 दिन = 72 घंटे
MIN_VIDEO_DURATION_SEC = 7200               # 2 घंटे = 7200 सेकंड (filter: 2hr+)
SCAN_WORKERS = 4                            # Concurrent scanning threads
SCAN_TIMEOUT = 12                           # HTTP request timeout (seconds)
SCAN_MAX_VIDEOS_PER_CHANNEL = 10            # Max videos to parse per channel page

# === Video Processing ===
KEEP_DURATION_SEC = 7200                    # पहले 2 घंटे रखना (cut point)
TARGET_TOTAL_SEC = 10800                    # कुल 3 घंटे+ बनाना (10800 = 3hr minimum)
WATERMARK_MAX_WIDTH_PX = 150                # कोने का सही लोगो साइज़ (~140-150px, यूजर के सर्कल अनुसार)
WATERMARK_SCALE = 0.13                      # वीडियो हाइट का 13% (~140px on 1080p)
WATERMARK_MARGIN_PX = 30                    # कोने से gap (pixels)
WATERMARK_OPACITY = 0.85                    # Watermark transparency

# === Dynamic Editing Settings (Auto-Cut + Alternating Mirror + Transitions) ===
CUT_INTERVAL_SEC = 5.5                      # हर 5-6 सेकंड (5.5s) में ऑटो कट
TRANSITION_DURATION_SEC = 0.22              # कट पर ट्रांजिशन फ्लैश की अवधि
TRANSITION_BRIGHTNESS = 0.35                # ट्रांजिशन फ्लैश ब्राइटनेस बूस्ट
TRANSITION_CONTRAST = 1.25                  # ट्रांजिशन फ्लैश कंट्रास्ट
ENABLE_ALTERNATING_MIRROR = True            # एक क्लिप सामान्य, अगली क्लिप मिरर (hflip)
ENABLE_TRANSITION_EFFECT = True             # हर कट पर डायनेमिक ट्रांजिशन इफ़ेक्ट

# === Download Settings (Full HD 1080p Priority) ===
VIDEO_FORMAT = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
DOWNLOAD_TIMEOUT = 900                      # 15 min timeout for Full HD video download
DOWNLOAD_RETRIES = 10

# === Output Video Encoding ===
OUTPUT_CODEC = "libx264"
OUTPUT_CRF = 23
OUTPUT_PRESET = "ultrafast"                # CPU पर 300+ fps अल्ट्राफास्ट एन्कोडिंग
OUTPUT_AUDIO_CODEC = "aac"
OUTPUT_AUDIO_BITRATE = "192k"

# === Environment Loading (.env) ===
def _load_env_files():
    candidates = [
        BASE_DIR / ".env",
        PROJECT_ROOT / ".env",
        Path(r"D:\Sicreat-automation\.env"),
    ]
    for env_path in candidates:
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k and v and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass

_load_env_files()

# === Footage API Settings (Pure Nature Videos) ===
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
NATURE_QUERIES = [
    "nature landscape",
    "waterfall forest",
    "peaceful river nature",
    "mountain landscape",
    "relaxing green forest",
    "ocean waves sunset",
]

# === Logging ===
LOG_FORMAT = "%(asctime)s [%(levelname)s] [CopyRight-Work] %(message)s"


def get_cookie_path() -> str:
    """Returns the first existing cookie file path, or empty string."""
    for cp in COOKIE_CANDIDATES:
        if cp.exists():
            return str(cp)
    return ""


def ensure_dirs():
    """Create all required directories."""
    for d in [DOWNLOADS_DIR, TEMP_DIR, OUTPUT_DIR, FOOTAGE_DIR]:
        d.mkdir(parents=True, exist_ok=True)

