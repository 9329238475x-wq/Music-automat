"""
Master DJ Remix Production Pipeline Orchestrator
Coordinates scraping, audio mastering with 'Wooosh' transitions, 
Avee Player visualizer rendering, and YouTube auto-uploading.
"""

import os
import sys
import time
import argparse
import logging
import shutil
from typing import Optional

from src.scraper import DJScraper
from src.audio_engine import DJAudioEngine
from src.visual_engine import DJVisualEngine
from src.youtube_uploader import YouTubeUploader
from src.notifier import send_upload_success_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Pipeline")


class DJProductionPipeline:
    def __init__(self, profile: str = "nagpuri", base_dir: Optional[str] = None):
        self.profile = profile.lower()
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.output_dir = os.path.join(self.base_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)

        self.scraper = DJScraper(profile=self.profile, base_dir=self.base_dir)
        self.audio_engine = DJAudioEngine(base_dir=self.base_dir)
        self.visual_engine = DJVisualEngine(profile=self.profile, base_dir=self.base_dir)
        self.uploader = YouTubeUploader(profile=self.profile, base_dir=self.base_dir)

    def run(self, target_tracks: int = 0, skip_upload: bool = False) -> bool:
        if not target_tracks or target_tracks <= 0:
            target_tracks = self.settings.get("profiles", {}).get(self.profile, {}).get("target_tracks", len(self.scraper.channels))
        start_time = time.time()
        logger.info(f"==================================================")
        logger.info(f"Starting Autonomous DJ Pipeline | Profile: {self.profile.upper()}")
        logger.info(f"Target Tracks: {target_tracks} | Skip Upload: {skip_upload}")
        logger.info(f"==================================================")

        # -----------------------------------------------------------------
        # STEP 1: Scrape & Download Fresh 320 kbps Remix Tracks
        # -----------------------------------------------------------------
        logger.info("[STEP 1/4] Discovering and downloading fresh DJ tracks...")
        tracks = self.scraper.download_tracks(target_count=target_tracks)
        if not tracks or len(tracks) < 2:
            logger.error("Insufficient tracks downloaded to compile a nonstop mix.")
            return False

        logger.info(f"Step 1 Complete: {len(tracks)} tracks ready.")

        # -----------------------------------------------------------------
        # STEP 2: Audio Normalization & Smooth 'Wooosh' Transition Assembly
        # -----------------------------------------------------------------
        logger.info("[STEP 2/4] Assembling Nonstop mix with smooth 'Wooosh' transitions...")
        audio_out_name = f"{self.profile}_master_mix.mp3"
        master_audio_path, tracklist_path, chapters = self.audio_engine.assemble_nonstop_mix(
            tracks=tracks,
            crossfade_sec=1.5,
            output_name=audio_out_name
        )

        logger.info(f"Step 2 Complete: Master audio assembled ({master_audio_path}).")

        # -----------------------------------------------------------------
        # STEP 3: Thumbnail Wall Collage & Avee Player Bass Visualizer
        # -----------------------------------------------------------------
        logger.info("[STEP 3/4] Generating Thumbnail Wall and Avee Player Visualizer...")
        thumb_paths = [t.get("thumb_path") for t in tracks if t.get("thumb_path")]
        bg_wall_path = os.path.join(self.output_dir, f"{self.profile}_thumbnail_wall.jpg")
        self.visual_engine.create_thumbnail_wall(thumb_paths, out_path=bg_wall_path, darkness=0.25)

        video_out_name = f"{self.profile}_nonstop_mix.mp4"
        final_video_path = os.path.join(self.output_dir, video_out_name)
        self.visual_engine.render_visualizer_video(
            audio_path=master_audio_path,
            background_path=bg_wall_path,
            output_mp4=final_video_path,
            fps=24
        )

        logger.info(f"Step 3 Complete: Full video rendered ({final_video_path}).")

        # -----------------------------------------------------------------
        # STEP 4: YouTube Data API Auto-Upload
        # -----------------------------------------------------------------
        if skip_upload:
            logger.info("[STEP 4/4] Upload skipped (--skip-upload set).")
        else:
            logger.info("[STEP 4/4] Uploading video to YouTube...")
            video_url = self.uploader.upload_video(
                video_path=final_video_path,
                tracklist_path=tracklist_path,
                thumbnail_path=bg_wall_path
            )
            if video_url:
                logger.info(f"🎉 Pipeline Succeeded! Video live at: {video_url}")
                # Send email notification
                send_upload_success_email(
                    video_title=f"NONSTOP {self.profile.upper()} DJ REMIX",
                    youtube_url=video_url,
                    profile=self.profile,
                    channel_name=f"{self.profile.capitalize()} DJ Channel",
                    duration_str="2-4 Hours Nonstop",
                    track_count=len(tracks)
                )
            else:
                logger.warning("Upload step did not return video URL (check credentials).")

        # Cleanup temporary audio files
        temp_dir = os.path.join(self.output_dir, "temp_audio")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

        elapsed = time.time() - start_time
        logger.info(f"Pipeline finished in {elapsed/60:.1f} minutes.")
        return True


def main():
    parser = argparse.ArgumentParser(description="Autonomous Nonstop DJ Remix Pipeline")
    parser.add_argument(
        "--profile",
        choices=["nagpuri", "vibration"],
        default="nagpuri",
        help="Target channel profile: 'nagpuri' or 'vibration'"
    )
    parser.add_argument(
        "--target-tracks",
        type=int,
        default=0,
        help="Number of tracks to include in mix (default: from profile settings)"
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Render video without uploading to YouTube"
    )
    args = parser.parse_args()

    pipeline = DJProductionPipeline(profile=args.profile)
    success = pipeline.run(target_tracks=args.target_tracks, skip_upload=args.skip_upload)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
