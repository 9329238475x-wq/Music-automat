# 🎧 Music-Automat: System Architecture & Agent Rules

## 1. Project Overview
- **Name:** Music-Automat (24/7 Autonomous Indian DJ Remix Pipeline & Multi-Channel Studio Hub)
- **Primary Channels / Profiles:**
  - `nagpuri`: Nonstop Theth Nagpuri DJ Dance Mix (21 source channels, 320 kbps HD master)
  - `vibration`: Hard Vibration & CG Tapori DJ Mix (23 hard-bass & vibration source channels)
  - `edm`: Bhojpuri EDM Drop Special (50 verified EDM drop sources)
  - Custom profiles dynamically added via Studio Hub.

## 2. Core Architecture
- **Scraper (`src/scraper.py`):** Uses `yt-dlp` flat-playlist scraping (consumes 0 YouTube API quota).
- **Audio Engine (`src/audio_engine.py`):** EBU R128 loudness normalizer (-14 LUFS, -1.0 dBTP), 320 kbps MP3 master, cinematic smooth 'Wooosh' transitions.
- **Visual Engine (`src/visual_engine.py`):** 1920x1080 Thumbnail Wall grid collage + 360-degree Avee Player circular bass-reactive spectrum visualizer with channel center emblem.
- **Local Hub & Remote Server (`src/server.py`):**
  - FastAPI server bound to `0.0.0.0:8000` (started via `start_local.bat`).
  - Real-time Google OAuth 2.0 token health verification (pings Google to detect expired/revoked tokens).
  - 7-Day Countdown timer for Testing mode tokens.
  - Cloudflare Quick Tunnel (`tools/cloudflared.exe`) providing worldwide HTTPS access for mobile control.
- **GitHub Sync Engine (`src/github_sync.py`):**
  - Uses `PyNaCl` libsodium encryption to directly push channel refresh tokens to GitHub Repository Secrets (`YOUTUBE_REFRESH_TOKEN_NAGPURI`, `YOUTUBE_REFRESH_TOKEN_VIBRATION`, `YOUTUBE_REFRESH_TOKEN_EDM`, etc.).
- **Cloud Runner (`push_to_kaggle.py` & `kaggle/kaggle_runner.py`):**
  - 100% headless execution on Kaggle Dual T4 GPU kernels triggered via GitHub Actions cron or manual dispatch.

## 3. Communication Guidelines
- Always communicate with the user in **Hindi written in Devanagari script (हिंदी देवनागरी लिपि)**.
- Be supportive, friendly, direct, and explain technical steps clearly.
- Never commit credentials (`tokens/`, `client_secrets.json`, `config/github_token.txt`) to Git repository.
