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
        return build("youtube", "v3", credentials=creds)

    def generate_metadata(self, tracklist_text: str, total_duration_str: str = "2:30:00") -> Dict[str, Any]:
        """Generates dynamic, SEO-optimized title, description, and tags."""
        now = datetime.now()
        month_name = now.strftime("%B")
        year = now.year

        p_settings = self.settings.get("profiles", {}).get(self.profile, {})
        base_tags = p_settings.get("tags", ["dj remix", "nonstop dj"])

        if self.profile == "nagpuri":
            title = f"NONSTOP NAGPURI DJ REMIX {year} 🔥 {month_name} Dhamaka Dance Mix 💃 New Theth Nagpuri DJ Mashup"
            desc_intro = f"""🎧 NONSTOP NAGPURI DJ REMIX {year} - THE ULTIMATE DANCE COLLECTION!
Welcome to the best non-stop Nagpuri DJ Remix playlist featuring the hottest regional tracks of Jharkhand, Bihar & CG!

⚡ High Quality 320 kbps Sound | Full Bass Boosted | Smooth Transitions
"""
        else:
            title = f"HARD VIBRATION DJ REMIX {year} 🔊 Full Bass Boosted Competition Mix 🔥 Nonstop CG & Nagpuri DJ"
            desc_intro = f"""🔊 HARD VIBRATION DJ REMIX {year} - COMPETITION BASS BLAST!
Feel the earth-shaking sub-bass and extreme kick vibration in this non-stop competition DJ remix mix!

⚡ Ultra Hard Bass | 320 kbps Audio | Avee Player Bass Reactive Visualizer
"""

        description = f"""{desc_intro}
━━━━━━━━━━━━━━━━━━━━━━━━━━
🎵 TRACKLIST & CHAPTERS:
{tracklist_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ DISCLAIMER & CREDITS:
All songs and remixes featured in this mix are the property of their respective remix artists and creators listed in the tracklist above. 
This mix is compiled for promotional and entertainment purposes only. 
If any producer, artist or label has an issue with this upload, please contact us and we will resolve it immediately.

#DJRemix #{self.profile.capitalize()}DJ #NonstopDJ #DJMix{year} #BassBoosted
"""

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
