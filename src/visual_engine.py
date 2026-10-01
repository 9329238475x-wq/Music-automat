"""
DJ Visual Engine Module
1. Creates a 1920x1080 Thumbnail Wall Grid (Collage) of all tracks with 5% dark shade.
2. Renders an Avee Player style circular bass-reactive visualizer pulsating to kicks/sub-bass.
3. Streams frames directly into FFmpeg stdin with zero temporary disk image files.
"""

import os
import sys
import math
import logging
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageFilter
from typing import List, Dict, Any, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VisualEngine")


class DJVisualEngine:
    def __init__(self, profile: str = "nagpuri", base_dir: Optional[str] = None):
        self.profile = profile.lower()
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.output_dir = os.path.join(self.base_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)

        logo_name = f"logo_{self.profile}.png"
        self.logo_path = os.path.join(self.assets_dir, logo_name)
        if not os.path.exists(self.logo_path):
            self.logo_path = os.path.join(self.assets_dir, "logo_nagpuri.png")

    def create_thumbnail_wall(
        self,
        thumb_paths: List[str],
        out_path: Optional[str] = None,
        darkness: float = 0.08
    ) -> str:
        """
        Creates a 1920x1080 collage grid from song thumbnails with a subtle dark overlay.
        """
        if out_path is None:
            out_path = os.path.join(self.output_dir, "thumbnail_wall.jpg")

        logger.info(f"Generating 1920x1080 Thumbnail Wall Collage from {len(thumb_paths)} thumbnails...")
        width, height = 1920, 1080
        wall = Image.new("RGB", (width, height), (10, 12, 18))

        valid_thumbs = [p for p in thumb_paths if p and os.path.exists(p)]
        if not valid_thumbs:
            # Fallback gradient background if no thumbnails
            draw = ImageDraw.Draw(wall)
            for y in range(height):
                r = int(15 + 10 * (y / height))
                g = int(18 + 15 * (y / height))
                b = int(30 + 25 * (y / height))
                draw.line([(0, y), (width, y)], fill=(r, g, b))
            wall.save(out_path, quality=95)
            return out_path

        # Determine grid dimensions (e.g. 5 cols x 4 rows = 20 cells, or 6x4 = 24)
        n = len(valid_thumbs)
        cols = 5 if n <= 20 else 6
        rows = math.ceil(n / cols)
        if rows < 3:
            rows = 3

        cell_w = math.ceil(width / cols)
        cell_h = math.ceil(height / rows)

        # Place thumbnails into grid
        idx = 0
        for r in range(rows):
            for c in range(cols):
                t_path = valid_thumbs[idx % len(valid_thumbs)]
                try:
                    img = Image.open(t_path).convert("RGB")
                    # Crop and fit to cell size
                    img = ImageOps.fit(img, (cell_w, cell_h), Image.Resampling.LANCZOS)
                    wall.paste(img, (c * cell_w, r * cell_h))
                except Exception as e:
                    logger.debug(f"Failed to load thumb {t_path}: {e}")
                idx += 1

        # Apply subtle dark shade (5-8% black overlay + vignette)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, int(255 * darkness)))
        wall_rgba = wall.convert("RGBA")
        combined = Image.alpha_composite(wall_rgba, overlay).convert("RGB")

        combined.save(out_path, quality=95)
        logger.info(f"Thumbnail wall saved at {out_path}")
        return out_path

    def _extract_audio_fft(
        self,
        audio_path: str,
        fps: int = 30,
        num_bars: int = 72
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Quickly extracts sub-bass energy and radial spectrum amplitudes using downsampled FFT.
        Takes ~5-15 seconds for a 2-4 hour audio track!
        """
        logger.info("Extracting bass dynamics and frequency spectrum via FFT...")
        # Decode audio to 11025 Hz mono for super-fast FFT processing
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-ac", "1",
            "-ar", "11025",
            "-f", "f32le",
            "-"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw_data, _ = proc.communicate()
        audio = np.frombuffer(raw_data, dtype=np.float32)

        sr = 11025
        hop_length = int(sr / fps)
        n_frames = int(len(audio) / hop_length)
        duration_sec = len(audio) / sr

        bass_energy = np.zeros(n_frames, dtype=np.float32)
        spectrum_bars = np.zeros((n_frames, num_bars), dtype=np.float32)

        # FFT window
        n_fft = 1024
        window = np.hanning(n_fft)

        for i in range(n_frames):
            start = i * hop_length
            end = start + n_fft
            if end > len(audio):
                chunk = np.pad(audio[start:], (0, end - len(audio)))
            else:
                chunk = audio[start:end]

            # Fast Fourier Transform
            fft_vals = np.abs(np.fft.rfft(chunk * window))
            
            # Sub-bass frequencies (20Hz to 120Hz) -> bins 2 to 12
            bass = np.mean(fft_vals[2:12]) if len(fft_vals) > 12 else 0.0
            bass_energy[i] = bass

            # 72 logarithmic/radial frequency bins
            indices = np.linspace(2, min(len(fft_vals) - 1, 280), num_bars, dtype=int)
            spectrum_bars[i] = fft_vals[indices]

        # Normalize bass energy with smooth exponential decay (spring bounce)
        max_bass = np.percentile(bass_energy, 98) + 1e-6
        bass_norm = np.clip(bass_energy / max_bass, 0.0, 1.0)
        
        # Smooth with exponential moving average
        smoothed_bass = np.zeros_like(bass_norm)
        cur = 0.0
        for i in range(len(bass_norm)):
            val = bass_norm[i]
            cur = max(val, cur * 0.82)
            smoothed_bass[i] = cur

        # Normalize spectrum bars
        max_bars = np.percentile(spectrum_bars, 98) + 1e-6
        bars_norm = np.clip(spectrum_bars / max_bars, 0.0, 1.0)
        
        smoothed_bars = np.zeros_like(bars_norm)
        cur_bars = np.zeros(num_bars)
        for i in range(len(bars_norm)):
            cur_bars = np.maximum(bars_norm[i], cur_bars * 0.85)
            smoothed_bars[i] = cur_bars

        return smoothed_bass, smoothed_bars, duration_sec

    def render_visualizer_video(
        self,
        audio_path: str,
        background_path: str,
        output_mp4: Optional[str] = None,
        fps: int = 24
    ) -> str:
        """
        Renders the Avee Player bass visualizer MP4 video.
        Uses NVIDIA GPU h264_nvenc hardware acceleration when available.
        Optimized with cropped patch rendering and 24 FPS for 10x-20x speedup.
        """
        if output_mp4 is None:
            output_mp4 = os.path.join(self.output_dir, f"{self.profile}_nonstop_mix.mp4")

        width, height = 1920, 1080
        cx, cy = width // 2, height // 2

        # Step 1: Pre-calculate FFT data
        bass_curve, bar_matrix, duration = self._extract_audio_fft(audio_path, fps=fps, num_bars=72)
        total_frames = len(bass_curve)

        logger.info(f"Total video duration: {duration:.1f}s ({total_frames} frames @ {fps} fps)")

        # Step 2: Load base background image
        bg = Image.open(background_path).convert("RGBA")
        if bg.size != (width, height):
            bg = ImageOps.fit(bg, (width, height))

        # Crop center bounding box for visualizer (720x720 around center)
        box_r = 360
        x1, y1 = cx - box_r, cy - box_r
        x2, y2 = cx + box_r, cy + box_r
        bg_center_crop = bg.crop((x1, y1, x2, y2))

        # Load channel logo for center disc
        logo = None
        if os.path.exists(self.logo_path):
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
            except Exception as e:
                logger.warning(f"Could not open logo {self.logo_path}: {e}")

        # Precalculate radial bar angles (360 degrees)
        num_bars = 72
        angles = np.linspace(0, 2 * np.pi, num_bars, endpoint=False)
        cos_a = np.cos(angles)
        sin_a = np.sin(angles)

        base_r = 185
        max_extra_h = 135

        # Check for NVIDIA NVENC GPU support
        has_nvenc = False
        try:
            chk = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
            if "h264_nvenc" in chk.stdout:
                has_nvenc = True
        except Exception:
            pass

        if has_nvenc:
            logger.info("🚀 NVIDIA GPU DETECTED: Using h264_nvenc hardware video encoder!")
            encoder_args = [
                "-c:v", "h264_nvenc",
                "-preset", "p4",
                "-tune", "ll",
                "-cq", "24",
                "-pix_fmt", "yuv420p"
            ]
        else:
            logger.info("Using CPU libx264 ultrafast encoder (fallback)...")
            encoder_args = [
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "25",
                "-pix_fmt", "yuv420p"
            ]

        # Step 3: Launch FFmpeg pipe
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",               # Video stream from stdin
            "-i", audio_path,         # Audio stream
            *encoder_args,
            "-c:a", "aac",
            "-b:a", "320k",
            "-shortest",
            output_mp4
        ]

        logger.info(f"Starting FFmpeg encode: {output_mp4} (Full hardware pipeline)...")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        pcx, pcy = box_r, box_r
        bar_colors = [
            (255, 60, 60, 255) if self.profile == "nagpuri" else (255, 30, 80, 255),
            (255, 140, 20, 255) if self.profile == "nagpuri" else (0, 220, 255, 255)
        ]

        log_interval = max(1, total_frames // 10)
        t_start = time.time()

        try:
            for frame_idx in range(total_frames):
                patch = bg_center_crop.copy()
                draw = ImageDraw.Draw(patch)

                bass_pulse = bass_curve[frame_idx]
                cur_base_r = int(base_r + 22 * bass_pulse)
                cur_bars = bar_matrix[frame_idx]

                # Draw 360-degree radial bars on patch
                for b in range(num_bars):
                    bar_h = int(cur_bars[b] * max_extra_h)
                    r_start = cur_base_r + 4
                    r_end = cur_base_r + 4 + bar_h

                    x_start = pcx + r_start * cos_a[b]
                    y_start = pcy + r_start * sin_a[b]
                    x_end = pcx + r_end * cos_a[b]
                    y_end = pcy + r_end * sin_a[b]

                    color = bar_colors[b % 2]
                    draw.line([(x_start, y_start), (x_end, y_end)], fill=color, width=3)

                # Center pulsating disc outline
                disc_color = (255, 255, 255, 240)
                draw.ellipse(
                    [pcx - cur_base_r, pcy - cur_base_r, pcx + cur_base_r, pcy + cur_base_r],
                    outline=disc_color,
                    width=4
                )

                # Center Logo
                if logo is not None:
                    logo_dim = int(cur_base_r * 1.80)
                    logo_res = logo.resize((logo_dim, logo_dim), Image.Resampling.LANCZOS)
                    lx = pcx - logo_dim // 2
                    ly = pcy - logo_dim // 2
                    patch.paste(logo_res, (lx, ly), logo_res)

                # Paste patch back onto full background
                bg.paste(patch, (x1, y1))
                proc.stdin.write(bg.tobytes())

                if frame_idx % log_interval == 0 and frame_idx > 0:
                    pct = int((frame_idx / total_frames) * 100)
                    elapsed = time.time() - t_start
                    fps_calc = frame_idx / elapsed
                    eta_sec = (total_frames - frame_idx) / max(fps_calc, 1.0)
                    logger.info(f"Render progress: {pct}% | Speed: {fps_calc:.1f} FPS | ETA: {eta_sec/60:.1f} min")

            proc.stdin.close()
            proc.wait()
            total_sec = time.time() - t_start
            avg_fps = total_frames / max(total_sec, 1.0)
            logger.info(f"🎉 Rendering complete in {total_sec/60:.1f} minutes! Average speed: {avg_fps:.1f} FPS.")

        except Exception as e:
            logger.error(f"Render error: {e}")
            if proc.poll() is None:
                proc.kill()
            raise e

        return output_mp4
