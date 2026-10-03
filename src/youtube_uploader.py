"""
YouTube Uploader Module
Uploads the rendered Nonstop DJ mix video using YouTube Data API v3.
Attaches full clickable chapter timestamps (tracklist), dynamic tags, and thumbnail.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("YouTubeUploader")


class YouTubeUploader:
    def __init__(self, profile: str = "nagpuri", base_dir: Optional[str] = None):
        self.profile = profile.lower()
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.config_dir = os.path.join(self.base_dir, "config")
        self.settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        path = os.path.join(self.config_dir, "settings.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def get_authenticated_service(self):
        """Constructs authenticated YouTube Data API client from env or token file."""
        client_id = os.environ.get("YOUTUBE_CLIENT_ID")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
        refresh_token = (
            os.environ.get(f"YOUTUBE_REFRESH_TOKEN_{self.profile.upper()}")
            or os.environ.get("YOUTUBE_REFRESH_TOKEN")
        )

        token_uri = "https://oauth2.googleapis.com/token"

        if not (client_id and client_secret and refresh_token):
            # Check local tokens folder
            token_path = os.path.join(self.base_dir, "tokens", f"token_{self.profile}.json")
            if os.path.exists(token_path):
                with open(token_path, "r", encoding="utf-8") as f:
                    t_data = json.load(f)
                    return Credentials.from_authorized_user_info(t_data)
            logger.warning("YouTube OAuth credentials not fully set in environment or token file.")
            return None

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/youtube.upload"]
        )
        try:
            if not creds.valid:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
        except Exception as e:
            logger.warning(f"Failed to refresh YouTube credentials: {e}")
        return build("youtube", "v3", credentials=creds)

    def generate_metadata(self, tracklist_text: str, total_duration_str: str = "2:30:00") -> Dict[str, Any]:
        """
        Generates dynamic, high-CTR viral title, SEO description with Your Queries,
        clickable chapters, and trending hashtags customized for each channel.
        """
        now = datetime.now()
        year = now.year

        if self.profile == "edm":
            # Channel: sumit rmx 2.0 (Mega EDM Collection Profile)
            title = f"NEW TRENDING EDM DJ REMIX {year} 🔥 Electro Dance Nonstop Mix || Sumit Rmx 2.0 ⚡"
            
            description = f"""⚡ NEW TRENDING EDM DJ REMIX {year} - HARD DROP ELECTRO JUKEBOX!
Welcome to Sumit Rmx 2.0! Get ready for the ultimate EDM rush! High-energy festival electro drops, club dance mix, hard bass drops, and non-stop viral EDM remixes mastered in studio-grade 320 kbps HD audio!

⚡ Audio Specs: 320 kbps HD Master | Sub-Bass Boosted +2.5dB | 1080p Avee Bass Visualizer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎵 TRACKLIST & CHAPTERS (CLICK TIMESTAMPS):
{tracklist_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔎 YOUR QUERIES & TOP SEARCHES:
• new edm dj remix {year}
• nonstop edm drop mix {year}
• hard drop edm remix nonstop
• bhojpuri edm dance mix
• trending edm mashup {year}
• electro house dj remix {year}
• club dance mix edm {year}
• bass boosted edm dj song
• sound check edm remix
• festival edm nonstop jukebox
• new viral edm songs {year}
• electro dance drop mix 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏷️ VIRAL HASHTAGS:
#edmdj #edmdrop #edmsong{year} #nonstopedm #electrohouse #clubmix #harddropedm #edmmashup #trendingsong #djremix{year} #bhojpuriedm

⚠️ DISCLAIMER & FAIR USE:
All songs and remixes featured in this nonstop mix belong to their respective original creators, artists, and music labels. This mix is created purely for promotional, cultural, and entertainment purposes. If any artist, label, or copyright holder has any concern regarding any track, please contact us and we will promptly resolve it.
"""
        elif self.profile == "nagpuri":
            # Channel: nagpuri non-stop remix 2.0 (Nagpuri Profile)
            title = f"New Trending Nagpuri DJ Remix {year} 🔥 Nonstop Nagpuri DJ Song || Theth Nagpuri Dance Mix 💃"
            
            description = f"""🎧 NEW TRENDING NAGPURI DJ REMIX {year} - NONSTOP DHAMAKA JUKEBOX!
Welcome to Nagpuri Non-Stop Remix 2.0! Enjoy the most popular and viral Nagpuri DJ Remix songs, non-stop high-energy dance mix with pure 320 kbps HD sound & deep sub-bass boost!

⚡ Audio Specs: 320 kbps HD Master | Sub-Bass Boosted +2.5dB | 1080p Avee Bass Visualizer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎵 TRACKLIST & CHAPTERS (CLICK TIMESTAMPS):
{tracklist_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔎 YOUR QUERIES & TOP SEARCHES:
• new nagpuri dj remix {year}
• nonstop nagpuri dj song {year}
• theth nagpuri dj remix nonstop
• sumit rmx nagpuri song
• nagpuri dance mix dj song
• trending nagpuri dj mashup {year}
• jharkhandi nagpuri dj competition mix
• new nagpuri hit song {year}
• superhit nagpuri nonstop dj
• nagpuri arkestra dj song
• purulia nagpuri dj remix
• nagpuri roadshow dj mix {year}
• top trending nagpuri dj songs
• nagpuri nonstop remix jukebox

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏷️ VIRAL HASHTAGS:
#nagpuridj #newnagpurisong{year} #nonstopnagpuridj #thethnagpuri #sumitrmx #nagpurisong #nagpuridancemix #jharkhandidj #nagpuridjremix #viralnagpurisong #djremix{year} #nagpurisong{year}

⚠️ DISCLAIMER & FAIR USE:
All songs and remixes featured in this nonstop mix belong to their respective original creators, artists, and music labels. This mix is created purely for promotional, cultural, and entertainment purposes. If any artist, label, or copyright holder has any concern regarding any track, please contact us and we will promptly resolve it.
"""
        else:
            # Channel: Sumit RMX 6.0 (Hard Vibration Profile)
            title = f"HARD VIBRATION DJ REMIX {year} 🔊 Monster Bass Boosted Competition Mix || Sumit RMX 6.0"
            
            description = f"""🔊 HARD VIBRATION DJ REMIX {year} - MONSTER SUB-BASS COMPETITION MIX!
Welcome to Sumit RMX 6.0! Feel the extreme sub-bass vibration, hard kick drops, and non-stop roadshow power! Tuned for heavy woofers, competition DJ setups, and bass lovers!

⚡ Audio Specs: 320 kbps HD Master | Sub-Bass Boosted +2.5dB | 1080p Avee Bass Visualizer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎵 TRACKLIST & CHAPTERS (CLICK TIMESTAMPS):
{tracklist_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔎 YOUR QUERIES & TOP SEARCHES:
• hard vibration dj remix {year}
• nonstop hard bass dj competition mix
• full bass boosted nagpuri dj song
• cg hard vibration dj mix
• monster bass sound check {year}
• extreme sub bass dj competition
• speaker phod vibration dj song
• roadshow dj remix nonstop {year}
• fl studio hard vibration mix
• heavy bass nagpuri dj song
• dj vibration sound test
• high voltage bass dj remix
• competition vibration dj song

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏷️ VIRAL HASHTAGS:
#hardvibration #hardbassdj #competitiondj #bassboosted #vibrationdj #nonstopdj #soundcheck #speakerblast #dangerbass #cgdjremix #nagpurivibration #djremix{year}

⚠️ DISCLAIMER & FAIR USE:
All songs and remixes featured in this nonstop mix belong to their respective original creators, artists, and music labels. This mix is created purely for promotional, cultural, and entertainment purposes. If any artist, label, or copyright holder has any concern regarding any track, please contact us and we will promptly resolve it.
"""

        p_settings = self.settings.get("profiles", {}).get(self.profile, {})
        base_tags = p_settings.get("tags", ["dj remix", "nonstop dj"])

        return {
            "title": title[:100],
            "description": description[:4900],
            "tags": base_tags[:30],
            "categoryId": "10"  # Music category
        }

    def upload_video(
        self,
        video_path: str,
        tracklist_path: str,
        thumbnail_path: Optional[str] = None
    ) -> Optional[str]:
        """Uploads the video to YouTube with resumable chunks."""
        youtube = self.get_authenticated_service()
        if not youtube:
            logger.error("Cannot upload: YouTube service authentication failed.")
            return None

        tracklist_text = ""
        if os.path.exists(tracklist_path):
            with open(tracklist_path, "r", encoding="utf-8") as f:
                tracklist_text = f.read().strip()

        meta = self.generate_metadata(tracklist_text)

        body = {
            "snippet": {
                "title": meta["title"],
                "description": meta["description"],
                "tags": meta["tags"],
                "categoryId": meta["categoryId"]
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        logger.info(f"Initiating YouTube upload for: {meta['title']}...")
        media = MediaFileUpload(video_path, chunksize=1024 * 1024 * 16, resumable=True)

        req = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = req.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info(f"Upload progress: {pct}%")

        video_id = response.get("id")
        video_url = f"https://youtu.be/{video_id}"
        logger.info(f"🎉 Successfully uploaded! URL: {video_url}")

        # Set custom thumbnail if provided
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path)
                ).execute()
                logger.info("Custom thumbnail uploaded successfully.")
            except Exception as e:
                logger.warning(f"Thumbnail upload failed: {e}")

        return video_url


if __name__ == "__main__":
    uploader = YouTubeUploader(profile="nagpuri")
    meta = uploader.generate_metadata("00:00:00 - Track 1")
    print(f"Sample Title: {meta['title']}")
