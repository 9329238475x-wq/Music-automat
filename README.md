# 🎧 Music-Automat: 24/7 Autonomous Indian DJ Remix Pipeline

**100% Free Cloud-Powered Production Pipeline (Kaggle + GitHub Actions)**  
Automatically compiles, visualizes, and uploads daily **2 to 4+ Hour Nonstop DJ Remix Mixes** across two distinct channels:
1. **Nagpuri Normal DJ Remix Channel** (21 Regional Source Channels)
2. **Hard Vibration DJ Remix Channel** (23 Hard-Bass & CG Source Channels)

---

## ⚡ Key Highlights
- **100% Cloud Execution (Kaggle):** Runs headless on free Kaggle kernels with 16 GB RAM and high-speed internet. 0% of your local PC CPU or internet bandwidth is used.
- **24-48h Fresh Track Monitor:** Monitors all 44 DJ channels using `yt-dlp` flat-playlist scraping (consumes **0 YouTube API quota**).
- **320 kbps Studio Master & Smooth 'Wooosh' Transition:** Every track change features a smooth, cinematic 'Wooosh' riser sweep transition with EBU R128 loudness normalization (`-14 LUFS`, `-1.0 dBTP`).
- **Thumbnail Wall Collage (1920x1080):** Automatically stitches all song thumbnails into a grid with a subtle 5-8% dark shade background.
- **Avee Player Circular Bass-Reactive Visualizer:** 360-degree radial spectrum bars pulsating dynamically to sub-bass and kick drums (20Hz-120Hz) with center channel logo.
- **Auto YouTube Upload:** Uploads via YouTube Data API v3 with full clickable tracklist timestamps, tags, and custom thumbnail.

---

## 📁 Repository Structure
```
Music-automat/
├── .github/
│   └── workflows/
│       └── run_dj_pipeline.yml      # GitHub Actions auto-cron & manual dispatch
├── assets/
│   ├── wooosh.wav                   # Cinematic stereo Wooosh transition effect
│   ├── logo_nagpuri.png             # Channel emblem for Nagpuri profile
│   └── logo_vibration.png           # Channel emblem for Vibration profile
├── config/
│   ├── channels.json                # Master database of all 44 source channels
│   └── settings.json                # Audio, visualizer, and rendering configuration
├── kaggle/
│   ├── kaggle_runner.py             # Headless cloud entrypoint
│   └── kernel-metadata.json         # Kaggle kernel configuration
├── src/
│   ├── scraper.py                   # 24-48h yt-dlp track & thumbnail scraper
│   ├── audio_engine.py              # EBU R128 normalizer, 'Wooosh' crossfader & tracklist
│   ├── visual_engine.py             # Thumbnail wall collage + Avee Player visualizer
│   ├── youtube_uploader.py          # YouTube Data API v3 uploader
│   └── pipeline.py                  # Master pipeline orchestrator
├── channal.md                       # Complete list of 44 channels with handles & links
└── requirements.txt                 # Dependencies
```

---

## ⚙️ Configuration & Secrets

Add the following Secrets to your GitHub repository (**Settings > Secrets and variables > Actions > Repository secrets**):

| Secret Name | Description |
|---|---|
| `KAGGLE_USERNAME` | Your Kaggle account username |
| `KAGGLE_KEY` | Your Kaggle API key (from kaggle.json) |
| `YOUTUBE_CLIENT_ID` | Google Cloud Console OAuth 2.0 Client ID |
| `YOUTUBE_CLIENT_SECRET` | Google Cloud Console OAuth 2.0 Client Secret |
| `YOUTUBE_REFRESH_TOKEN_NAGPURI` | OAuth 2.0 Refresh Token for Nagpuri Channel |
| `YOUTUBE_REFRESH_TOKEN_VIBRATION` | OAuth 2.0 Refresh Token for Vibration Channel |

---

## 🚀 How It Runs

### 1. Fully Autonomous Schedule (Daily Hands-Free)
- **11:30 AM IST (06:00 UTC):** Runs daily **Nagpuri Normal Remix** mix.
- **05:30 PM IST (12:00 UTC):** Runs daily **Hard Vibration Remix** mix.

### 2. Manual One-Click Trigger (GitHub Actions)
1. Go to **Actions** tab on GitHub.
2. Select **Run Autonomous DJ Remix Pipeline**.
3. Click **Run workflow**, choose your profile (`nagpuri` or `vibration`), and click the green button.
