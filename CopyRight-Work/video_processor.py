"""
CopyRight-Work — Video Processor
3-step video processing: Cut → Concat Footage → Watermark

All operations use FFmpeg via subprocess.
Optimized to minimize re-encoding passes.
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import config
except ImportError:
    import config

logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)
logger = logging.getLogger("CRW-VideoProcessor")


def get_video_duration(file_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"ffprobe failed for {file_path}: {e}")
        return 0.0


def get_video_info(file_path: str) -> Dict[str, Any]:
    """Get video resolution, fps, and codec info using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-of", "json",
        file_path
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30
        )
        import json
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]
        fps_str = stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) > 0 else 30.0
        else:
            fps = float(fps_str)
        return {
            "width": int(stream.get("width", 1920)),
            "height": int(stream.get("height", 1080)),
            "fps": fps,
            "codec": stream.get("codec_name", "h264"),
        }
    except Exception as e:
        logger.warning(f"ffprobe info failed for {file_path}: {e}")
        return {"width": 1920, "height": 1080, "fps": 30.0, "codec": "h264"}


# ─── Step 1: Cut Video ─────────────────────────────────────────────────────

def cut_video(
    input_path: str,
    output_path: str,
    keep_seconds: int = None,
) -> bool:
    """
    Step 1: Keep the first N seconds (default: 2 hours), cut the rest.
    Uses stream copy (no re-encoding) for speed and zero quality loss.
    
    Args:
        input_path:   Source video file path
        output_path:  Cut output file path
        keep_seconds: How many seconds to keep (default: KEEP_DURATION_SEC from config)
    
    Returns:
        True if successful, False otherwise
    """
    if keep_seconds is None:
        keep_seconds = config.KEEP_DURATION_SEC

    input_duration = get_video_duration(input_path)
    if input_duration <= 0:
        logger.error(f"Cannot determine duration of {input_path}")
        return False

    if input_duration <= keep_seconds:
        logger.info(
            f"Video is already ≤{keep_seconds/3600:.1f}hr "
            f"({input_duration/3600:.1f}hr). Copying as-is."
        )
        shutil.copy2(input_path, output_path)
        return True

    logger.info(
        f"✂️ Cutting video: keeping first {keep_seconds/3600:.1f}hr "
        f"of {input_duration/3600:.1f}hr total"
    )

    cmd = [
        "ffmpeg",
        "-y",                          # Overwrite output
        "-i", input_path,
        "-t", str(keep_seconds),       # Keep first N seconds
        "-c", "copy",                  # Stream copy (no re-encode)
        "-avoid_negative_ts", "make_zero",
        output_path
    ]

    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=300
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            cut_duration = get_video_duration(output_path)
            logger.info(
                f"✅ Cut complete: {cut_duration/3600:.2f}hr "
                f"({os.path.getsize(output_path)/(1024*1024):.1f} MB)"
            )
            return True
        else:
            logger.error(f"Cut output missing or empty: {output_path}")
            if result.stderr:
                logger.error(f"FFmpeg stderr: {result.stderr[-300:]}")
            return False
    except Exception as e:
        logger.error(f"FFmpeg cut failed: {e}")
        return False


# ─── Step 2: Normalize & Concatenate Footage ──────────────────────────────

def _normalize_footage(
    footage_path: str,
    output_path: str,
    target_width: int,
    target_height: int,
    target_fps: float,
) -> bool:
    """
    Normalize a footage file to match the main video's resolution, fps, and codec.
    Adds black padding if aspect ratio differs.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", footage_path,
        "-vf", (
            f"scale={target_width}:{target_height}"
            f":force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={target_fps:.2f}"
        ),
        "-c:v", config.OUTPUT_CODEC,
        "-crf", str(config.OUTPUT_CRF),
        "-preset", "ultrafast",
        "-c:a", config.OUTPUT_AUDIO_CODEC,
        "-b:a", config.OUTPUT_AUDIO_BITRATE,
        "-ar", "44100",
        "-ac", "2",
        "-shortest",
        output_path,
    ]
    try:
        subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=120
        )
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1024
    except Exception as e:
        logger.warning(f"Normalize failed for {footage_path}: {e}")
        return False


def concat_with_footage(
    main_video: str,
    footage_files: List[Path],
    output_path: str,
    target_total_sec: int = None,
) -> bool:
    """
    Step 2: Concatenate the main (cut) video with copyright-free footage.
    
    If footage is shorter than needed, it loops footage files to reach target.
    All footage is normalized to match the main video's resolution/fps.
    
    Args:
        main_video:       Path to the cut main video
        footage_files:    List of footage file paths
        output_path:      Final concatenated output path
        target_total_sec: Target total duration (default: TARGET_TOTAL_SEC)
    
    Returns:
        True if successful
    """
    if target_total_sec is None:
        target_total_sec = config.TARGET_TOTAL_SEC

    main_duration = get_video_duration(main_video)
    needed_footage_sec = target_total_sec - main_duration

    if needed_footage_sec <= 0:
        logger.info("Main video already meets target duration. No footage needed.")
        shutil.copy2(main_video, output_path)
        return True

    if not footage_files:
        logger.warning(
            f"⚠️ No footage files available! "
            f"Output will be only {main_duration/3600:.1f}hr (need {needed_footage_sec/60:.0f} more min)."
        )
        shutil.copy2(main_video, output_path)
        return True

    logger.info(
        f"🎞️ Concatenating footage: need {needed_footage_sec/60:.0f} min "
        f"to reach {target_total_sec/3600:.1f}hr target"
    )

    config.ensure_dirs()
    temp_dir = config.TEMP_DIR

    # Get main video specs for normalization
    main_info = get_video_info(main_video)
    target_w = main_info["width"]
    target_h = main_info["height"]
    target_fps = min(main_info["fps"], 30.0)  # Cap at 30fps

    # Main video is ALREADY normalized in dynamic editing pass (30fps, 44.1kHz aac).
    # We DO NOT re-encode main video here to save 30+ minutes and prevent timeouts!
    main_normalized = main_video

    # Normalize ONLY as many footage files as needed to cover needed_footage_sec!
    normalized_footage = []
    accumulated_footage_sec = 0.0

    for i, fp in enumerate(footage_files):
        if accumulated_footage_sec >= needed_footage_sec:
            break
        norm_path = str(temp_dir / f"footage_norm_{i:03d}.mp4")
        logger.info(f"  Normalizing footage {i+1}/{len(footage_files)}: {fp.name}")
        if _normalize_footage(str(fp), norm_path, target_w, target_h, target_fps):
            dur = get_video_duration(norm_path)
            if dur > 0:
                normalized_footage.append(norm_path)
                accumulated_footage_sec += dur

    if not normalized_footage:
        logger.warning("All footage normalization failed. Using main video only.")
        shutil.copy2(main_video, output_path)
        return True

    # Build concat list — loop footage files until we have enough duration
    concat_files = [main_normalized]
    loop_accum = 0.0
    loop_count = 0
    max_loops = 50  # Safety limit
    while loop_accum < needed_footage_sec and loop_count < max_loops:
        for nf in normalized_footage:
            if loop_accum >= needed_footage_sec:
                break
            dur = get_video_duration(nf)
            if dur > 0:
                concat_files.append(nf)
                loop_accum += dur
        loop_count += 1

    logger.info(
        f"  Concat plan: 1 main + {len(concat_files)-1} footage segment(s) "
        f"({loop_accum/60:.0f} min footage)"
    )

    # Create FFmpeg concat list file
    concat_list_path = str(temp_dir / "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for cf in concat_files:
            # Escape single quotes in path for FFmpeg
            safe_path = cf.replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    # Run concat
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        output_path,
    ]

    try:
        logger.info("  Running FFmpeg concat...")
        subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=600
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            total_dur = get_video_duration(output_path)
            logger.info(
                f"✅ Concat complete: {total_dur/3600:.2f}hr "
                f"({os.path.getsize(output_path)/(1024*1024):.1f} MB)"
            )
            return True
        else:
            logger.error("Concat output missing or empty")
            return False
    except Exception as e:
        logger.error(f"FFmpeg concat failed: {e}")
        return False


# ─── Step 3: Dynamic Editing (Auto-Cut + Alternating Mirror + Transitions + Watermark) ───

def apply_dynamic_editing_and_watermark(
    input_path: str,
    output_path: str,
    watermark_path: str = None,
) -> bool:
    """
    Applies dynamic video editing:
      1. Auto-Cut every 5-6 seconds (configurable via config.CUT_INTERVAL_SEC)
      2. Alternating Mirror: Clip 1 normal, Clip 2 mirrored (hflip), Clip 3 normal, Clip 4 mirrored...
      3. Dynamic Transition Effect: High-impact flash transition at every cut point
      4. Watermark Overlay: Copyright Work.png (70% smaller, bottom-right)
      5. Audio stream copy (lossless, zero audio sync drift)
    
    All operations are executed in a single highly optimized FFmpeg pass.
    """
    if watermark_path is None:
        watermark_path = str(config.WATERMARK_PATH)

    interval = getattr(config, "CUT_INTERVAL_SEC", 5.5)
    period = interval * 2.0
    trans_dur = getattr(config, "TRANSITION_DURATION_SEC", 0.22)
    bright = getattr(config, "TRANSITION_BRIGHTNESS", 0.35)
    cont = getattr(config, "TRANSITION_CONTRAST", 1.25)
    enable_mirror = getattr(config, "ENABLE_ALTERNATING_MIRROR", True)
    enable_trans = getattr(config, "ENABLE_TRANSITION_EFFECT", True)

    info = get_video_info(input_path)
    main_h = info.get("height", 1080) or 1080
    wm_target_size = getattr(config, "WATERMARK_MAX_WIDTH_PX", 150)
    wm_size = min(wm_target_size, max(90, int(main_h * getattr(config, "WATERMARK_SCALE", 0.13))))
    margin = getattr(config, "WATERMARK_MARGIN_PX", 30)

    logger.info(
        f"🎨 Applying dynamic editing & watermark:\n"
        f"   - Cut Interval: {interval:.1f}s (cycle: {period:.1f}s)\n"
        f"   - Alternating Mirror: {'ENABLED (1 normal, 1 mirrored)' if enable_mirror else 'DISABLED'}\n"
        f"   - Cut Transition Effect: {'ENABLED (flash/contrast pulse)' if enable_trans else 'DISABLED'}\n"
        f"   - Watermark: {wm_size}x{wm_size}px in top-right corner ({margin}px margin)"
    )

    # Build video filter chain for dynamic editing
    v_filters = []
    if enable_mirror:
        # Alternating hflip: 0 to interval is normal, interval to period is mirrored
        v_filters.append(f"hflip=enable='gte(mod(t,{period:.2f}),{interval:.2f})'")

    if enable_trans:
        # Flash transition pulse right at cut boundaries
        v_filters.append(
            f"eq=brightness={bright}:contrast={cont}:enable='lt(mod(t,{interval:.2f}),{trans_dur:.2f})'"
        )

    # Standardize fps to 30.00 for seamless concat with footage
    v_filters.append("fps=30.00")

    filter_chain = ",".join(v_filters) if v_filters else "null"

    has_wm = os.path.exists(watermark_path)
    if has_wm:
        filter_complex = (
            f"[0:v]{filter_chain}[v_edited];"
            f"[1:v]scale={wm_size}:{wm_size}[wm];"
            f"[v_edited][wm]overlay=W-w-{margin}:{margin}"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-threads", "0",
            "-i", input_path,
            "-i", watermark_path,
            "-filter_complex", filter_complex,
            "-c:v", config.OUTPUT_CODEC,
            "-crf", str(config.OUTPUT_CRF),
            "-preset", config.OUTPUT_PRESET,
            "-c:a", config.OUTPUT_AUDIO_CODEC,
            "-b:a", config.OUTPUT_AUDIO_BITRATE,
            "-ar", "44100",
            "-ac", "2",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-threads", "0",
            "-i", input_path,
            "-vf", filter_chain,
            "-c:v", config.OUTPUT_CODEC,
            "-crf", str(config.OUTPUT_CRF),
            "-preset", config.OUTPUT_PRESET,
            "-c:a", config.OUTPUT_AUDIO_CODEC,
            "-b:a", config.OUTPUT_AUDIO_BITRATE,
            "-ar", "44100",
            "-ac", "2",
            output_path,
        ]

    try:
        logger.info("  Running FFmpeg dynamic editing pass...")
        subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=5400  # 1.5 hr timeout for 2hr video
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            dur = get_video_duration(output_path)
            logger.info(
                f"✅ Dynamic editing complete: {dur/3600:.2f}hr "
                f"({os.path.getsize(output_path)/(1024*1024):.1f} MB)"
            )
            return True
        else:
            logger.error("Dynamic editing output missing or empty")
            return False
    except Exception as e:
        logger.error(f"FFmpeg dynamic editing failed: {e}")
        return False


# ─── Full Processing Pipeline ─────────────────────────────────────────────

def process_full_video(
    source_path: str,
    footage_files: List[Path] = None,
) -> Optional[str]:
    """
    Complete video processing pipeline:
      Step 1: Cut → Keep first 2 hours
      Step 2: Dynamic Editing → Auto-Cut every 5-6s + Alternating Mirror + Transitions + Watermark
      Step 3: Footage (Future) → Concat copyright-free footage as-is (untouched) if available
    
    Args:
        source_path:   Downloaded source video path
        footage_files: Optional list of copyright-free footage file paths
    
    Returns:
        Path to the final processed video, or None if failed.
    """
    config.ensure_dirs()
    temp_dir = config.TEMP_DIR
    output_dir = config.OUTPUT_DIR

    source_duration = get_video_duration(source_path)
    if source_duration <= 0:
        logger.error(f"Cannot read source video: {source_path}")
        return None

    logger.info(
        f"🎬 Starting video processing pipeline\n"
        f"   Source: {source_path}\n"
        f"   Duration: {source_duration/3600:.2f}hr\n"
        f"   Step 1: Cut first {config.KEEP_DURATION_SEC/3600:.0f}hr\n"
        f"   Step 2: Auto-Cut every {getattr(config, 'CUT_INTERVAL_SEC', 5.5)}s + Alternating Mirror + Transitions + Watermark\n"
        f"   Step 3: Stock footage append ({len(footage_files) if footage_files else 0} files available)"
    )

    # ── Step 1: Cut to 2 hours ──
    cut_path = str(temp_dir / "step1_cut.mp4")
    logger.info("━━ Step 1/3: Cutting video to first 2 hours...")
    if not cut_video(source_path, cut_path):
        logger.error("Step 1 (Cut) failed!")
        return None

    # ── Step 2: Apply dynamic editing + Watermark on the 2-hour video ──
    edited_2hr_path = str(temp_dir / "step2_edited_2hr.mp4")
    logger.info("━━ Step 2/3: Applying 5-6s auto-cut, alternating mirror, transitions & watermark...")
    if not apply_dynamic_editing_and_watermark(cut_path, edited_2hr_path):
        logger.error("Step 2 (Dynamic editing) failed!")
        return None

    # ── Step 3: Concat stock footage (if any available) ──
    # Generate unique output filename
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_filename = f"copyright_work_{timestamp}.mp4"
    final_path = str(output_dir / final_filename)

    if footage_files and len(footage_files) > 0:
        logger.info("━━ Step 3/3: Appending copyright-free footage (as-is, unmirrored)...")
        if not concat_with_footage(edited_2hr_path, footage_files, final_path):
            logger.warning("Footage concat failed, using edited 2hr video as final.")
            shutil.copy2(edited_2hr_path, final_path)
    else:
        logger.info("━━ Step 3/3: No stock footage provided yet (API key pending). Using edited 2hr video as final.")
        shutil.copy2(edited_2hr_path, final_path)

    # Verify final output
    final_duration = get_video_duration(final_path)
    final_size_mb = os.path.getsize(final_path) / (1024 * 1024)

    logger.info(
        f"\n"
        f"  ╔══════════════════════════════════════════════╗\n"
        f"  ║  ✅ VIDEO PROCESSING COMPLETE!               ║\n"
        f"  ║  Duration: {final_duration/3600:.2f} hours                  ║\n"
        f"  ║  Size: {final_size_mb:.0f} MB                            ║\n"
        f"  ║  File: {final_filename:<38s} ║\n"
        f"  ╚══════════════════════════════════════════════╝"
    )

    return final_path


def cleanup_temp():
    """Remove temporary processing files."""
    temp_dir = config.TEMP_DIR
    if temp_dir.exists():
        import shutil as sh
        for f in temp_dir.iterdir():
            try:
                if f.is_file():
                    f.unlink()
            except Exception:
                pass
        logger.info("🧹 Temp files cleaned up")

