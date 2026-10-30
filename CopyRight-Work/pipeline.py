"""
CopyRight-Work — Main Pipeline Orchestrator
DJ JAY LAL BARBASPUR (@raghuofficial420)

Complete automated flow:
  Step 1: SCAN    → 2hr+ वीडियो ढूंढो (3 दिन में, fallback extended)
  Step 2: DOWNLOAD → पूरी वीडियो उतारो (audio+video)
  Step 3: PROCESS  → Cut 2hr + Footage 3hr+ + Watermark
  Step 4: UPLOAD   → YouTube "DJ JAY LAL BARBASPUR" चैनल पर अपलोड
  Step 5: CLEANUP  → Temp files हटाओ

Usage:
  python -m CopyRight-Work.pipeline                  # Full pipeline
  python -m CopyRight-Work.pipeline --skip-upload     # Process only, no upload
  python -m CopyRight-Work.pipeline --scan-only       # Scan only, show what's available
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root and CRW dir to path
_crw_dir = Path(__file__).parent
_project_root = _crw_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_crw_dir) not in sys.path:
    sys.path.insert(0, str(_crw_dir))

try:
    from . import config
    from .scanner import VideoScanner
    from .downloader import download_video
    from .footage_fetcher import fetch_footage
    from .video_processor import process_full_video, cleanup_temp
except ImportError:
    import config
    from scanner import VideoScanner
    from downloader import download_video
    from footage_fetcher import fetch_footage
    from video_processor import process_full_video, cleanup_temp

logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
logger = logging.getLogger("CRW-Pipeline")


class CopyRightWorkPipeline:
    """Main pipeline for the copy_right_work channel."""

    def __init__(self):
        config.ensure_dirs()
        self.history_file = config.HISTORY_FILE

    def _load_history(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self, history):
        # Keep last 200 entries
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history[-200:], f, indent=2)

    def run(self, skip_upload: bool = False, scan_only: bool = False) -> bool:
        """
        Execute the full CopyRight-Work pipeline.
        
        Args:
            skip_upload: If True, process video but don't upload to YouTube
            scan_only:   If True, only scan channels and report results
        
        Returns:
            True if pipeline completed successfully
        """
        start_time = datetime.now()
        logger.info(
            f"\n"
            f"  ╔══════════════════════════════════════════════════╗\n"
            f"  ║  🎬 CopyRight-Work Pipeline Starting             ║\n"
            f"  ║  Channel: DJ JAY LAL BARBASPUR                   ║\n"
            f"  ║  Profile: {config.PROFILE_KEY:<38s}  ║\n"
            f"  ║  Time: {start_time.strftime('%Y-%m-%d %H:%M:%S IST'):<41s} ║\n"
            f"  ╚══════════════════════════════════════════════════╝"
        )

        # ════════════════════════════════════════════════════════
        # STEP 1: SCAN — Find 2hr+ video
        # ════════════════════════════════════════════════════════
        logger.info("═══ STEP 1/5: SCANNING CHANNELS ═══")
        scanner = VideoScanner()
        video_info = scanner.scan_channels()

        if not video_info:
            logger.error(
                "❌ Pipeline ABORTED: No qualifying 2hr+ video found "
                "in any source channel."
            )
            return False

        logger.info(
            f"  Selected: \"{video_info['title'][:60]}\"\n"
            f"  Channel:  {video_info['channel_name']}\n"
            f"  Duration: {video_info['duration_sec']/3600:.1f}hr\n"
            f"  Age:      {video_info['age_hours']:.1f}hr ago\n"
            f"  URL:      {video_info['url']}"
        )

        if scan_only:
            logger.info("🔍 Scan-only mode. Pipeline stops here.")
            return True

        # ════════════════════════════════════════════════════════
        # STEP 2: DOWNLOAD — Get full video
        # ════════════════════════════════════════════════════════
        logger.info("═══ STEP 2/5: DOWNLOADING VIDEO ═══")
        download_result = download_video(video_info)

        if not download_result or not download_result.get("video_path"):
            logger.error("❌ Pipeline ABORTED: Video download failed.")
            return False

        source_video_path = download_result["video_path"]
        source_thumb_path = download_result.get("thumb_path")
        logger.info(f"  Downloaded: {source_video_path}")

        # ════════════════════════════════════════════════════════
        # STEP 3: PROCESS — Cut + Footage + Watermark
        # ════════════════════════════════════════════════════════
        logger.info("═══ STEP 3/5: PROCESSING VIDEO ═══")

        # Get footage files
        needed_footage_sec = config.TARGET_TOTAL_SEC - config.KEEP_DURATION_SEC
        footage_files = fetch_footage(needed_footage_sec)

        # Run the 3-step video processor
        final_video_path = process_full_video(source_video_path, footage_files)

        if not final_video_path:
            logger.error("❌ Pipeline ABORTED: Video processing failed.")
            return False

        logger.info(f"  Final video: {final_video_path}")

        # ════════════════════════════════════════════════════════
        # STEP 4: UPLOAD — YouTube upload & Email Notification
        # ════════════════════════════════════════════════════════
        if skip_upload:
            logger.info("═══ STEP 4/5: UPLOAD SKIPPED (--skip-upload) ═══")
        else:
            logger.info("═══ STEP 4/5: UPLOADING TO YOUTUBE ═══")
            uploaded_url = self._upload_to_youtube(
                video_path=final_video_path,
                video_info=video_info,
                thumbnail_path=source_thumb_path,
            )
            if not uploaded_url:
                logger.error("❌ Upload failed. Video is saved locally.")
            else:
                # Dispatch Gmail VIP notification to user
                self._send_notification_email(
                    video_title=video_info.get("title", "Video"),
                    video_url=uploaded_url,
                    video_path=final_video_path,
                )

        # ════════════════════════════════════════════════════════
        # STEP 5: CLEANUP + HISTORY
        # ════════════════════════════════════════════════════════
        logger.info("═══ STEP 5/5: CLEANUP ═══")

        # Save to history
        history = self._load_history()
        history.append(video_info["id"])
        self._save_history(history)
        logger.info(f"  Video ID {video_info['id']} added to history")

        # Clean temp files
        cleanup_temp()

        # ════════════════════════════════════════════════════════
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"\n"
            f"  ╔══════════════════════════════════════════════════╗\n"
            f"  ║  ✅ PIPELINE COMPLETE!                            ║\n"
            f"  ║  Source: {video_info['title'][:40]:<40s} ║\n"
            f"  ║  Output: {Path(final_video_path).name:<40s} ║\n"
            f"  ║  Time taken: {elapsed/60:.1f} minutes                     ║\n"
            f"  ╚══════════════════════════════════════════════════╝"
        )
        return True

    def _upload_to_youtube(
        self,
        video_path: str,
        video_info: dict,
        thumbnail_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Upload the final video to YouTube using YouTube Data API v3:
          1. Title: Exact original title from the downloaded video (≤95 chars)
          2. Description: Full description copied from highest-viewed video in last 2 days (≤4900 chars)
          3. Thumbnail: Exact original thumbnail from downloaded video
          4. Returns video_url on success, None on failure.
        """
        try:
            from src.youtube_uploader import YouTubeUploader
        except ImportError:
            logger.error(
                "Cannot import YouTubeUploader from src/. "
                "Make sure you're running from the project root."
            )
            return None

        try:
            uploader = YouTubeUploader(
                profile=config.PROFILE_KEY,
                base_dir=str(config.PROJECT_ROOT)
            )

            youtube = uploader.get_authenticated_service()
            if not youtube:
                logger.error("YouTube authentication failed for copy_right_work profile.")
                return None

            # 1. Exact Original Title (safe truncated to 95 chars)
            raw_title = video_info.get("title", "Video").strip()
            title = raw_title[:92] + "..." if len(raw_title) > 95 else raw_title

            # 2. Description copied from most viral video in last 2 days
            description = video_info.get("description", "").strip()
            if not description:
                description = f"{title}\n\nUploaded via DJ JAY LAL BARBASPUR"

            # YouTube API limit: 5000 characters
            if len(description) > 4900:
                description = description[:4900]

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": [],
                    "categoryId": "24",  # Entertainment category
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                },
            }

            logger.info(f"  Uploading: \"{title[:60]}\"...")
            logger.info(f"  Description length: {len(description)} chars")

            # Resumable upload
            from googleapiclient.http import MediaFileUpload

            media = MediaFileUpload(
                video_path,
                chunksize=1024 * 1024 * 16,  # 16 MB chunks
                resumable=True,
            )
            req = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = req.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    logger.info(f"  Upload progress: {pct}%")

            video_id = response.get("id")
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"✅ Upload successful! URL: {video_url}")

            # 3. Exact Original Thumbnail
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    logger.info(f"  Setting original thumbnail: {Path(thumbnail_path).name}...")
                    thumb_media = MediaFileUpload(thumbnail_path)
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=thumb_media,
                    ).execute()
                    logger.info("  ✅ Original thumbnail set successfully")
                except Exception as e:
                    logger.warning(f"  Thumbnail upload failed (non-critical): {e}")

            return video_url

        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None

    def _send_notification_email(self, video_title: str, video_url: str, video_path: str):
        """Dispatches an executive dark-mode confirmation email with the new video link to Gmail."""
        try:
            from src.notifier import send_upload_success_email
            from .video_processor import get_video_duration

            dur_sec = get_video_duration(video_path)
            hrs = int(dur_sec // 3600)
            mins = int((dur_sec % 3600) // 60)
            secs = int(dur_sec % 60)
            dur_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"

            logger.info("📧 Dispatching Gmail upload confirmation email...")
            send_upload_success_email(
                video_title=video_title,
                youtube_url=video_url,
                profile="copy_right_work",
                channel_name="DJ JAY LAL BARBASPUR",
                duration_str=dur_str,
                track_count=1,
                recipient_email="9329238475x@gmail.com"
            )
            logger.info("✅ Gmail confirmation email successfully delivered to 9329238475x@gmail.com!")
        except Exception as e:
            logger.warning(f"Could not send email notification: {e}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="CopyRight-Work Pipeline — DJ JAY LAL BARBASPUR"
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Process video but don't upload to YouTube"
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Only scan channels and report findings"
    )
    args = parser.parse_args()

    pipeline = CopyRightWorkPipeline()
    success = pipeline.run(
        skip_upload=args.skip_upload,
        scan_only=args.scan_only,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

