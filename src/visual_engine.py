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
        fps: int = 30
    ) -> str:
        """
        Renders the complete Avee Player bass visualizer MP4 video.
        Streams raw frames straight into FFmpeg stdin.
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

        # Step 3: Launch FFmpeg pipe
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",               # Video stream from stdin
            "-i", audio_path,         # Audio stream
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "24",
            "-c:a", "aac",
            "-b:a", "320k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            output_mp4
        ]

        logger.info(f"Starting FFmpeg encode: {output_mp4} (Zero temp disk images)...")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        # Step 4: Render & stream frames
        report_step = max(fps * 30, 300)

        for frame_idx in range(total_frames):
            frame = bg.copy()
            draw = ImageDraw.Draw(frame)

            # Pulsing bass scale
            b_val = bass_curve[frame_idx]
            pulse_r = base_r + b_val * 24.0

            # Spectrum bars
            b_amps = bar_matrix[frame_idx]
            bar_heights = b_amps * max_extra_h

            x1 = cx + pulse_r * cos_a
            y1 = cy + pulse_r * sin_a
            x2 = cx + (pulse_r + bar_heights) * cos_a
            y2 = cy + (pulse_r + bar_heights) * sin_a

            # Draw radial bars with vibrant neon cyan & magenta
            for j in range(num_bars):
                color = (0, 225, 255, 240) if j % 2 == 0 else (255, 60, 180, 240)
                draw.line([(x1[j], y1[j]), (x2[j], y2[j])], fill=color, width=5)

            # Outer glowing ring around disc
            draw.ellipse(
                [cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r],
                outline=(0, 230, 255, 255),
                width=4
            )

            # Center logo
            if logo:
                logo_size = int(pulse_r * 1.90)
                l_resized = logo.resize((logo_size, logo_size), Image.Resampling.BILINEAR)
                frame.paste(
                    l_resized,
                    (cx - logo_size // 2, cy - logo_size // 2),
                    l_resized
                )

            # Write raw RGBA buffer to FFmpeg stdin
            try:
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                logger.error("FFmpeg stdin pipe broken prematurely.")
                break

            if frame_idx % report_step == 0 or frame_idx == total_frames - 1:
                pct = (frame_idx / total_frames) * 100
                logger.info(f"Encoding Progress: {pct:.1f}% ({frame_idx}/{total_frames} frames)")

        proc.stdin.close()
        proc.wait()

        if proc.returncode == 0 and os.path.exists(output_mp4):
            logger.info(f"Video render complete: {output_mp4}")
            return output_mp4
        else:
            err = proc.stderr.read().decode("utf-8", errors="ignore")
            logger.error(f"FFmpeg error: {err[-500:]}")
            raise RuntimeError("FFmpeg video rendering failed.")


if __name__ == "__main__":
    engine = DJVisualEngine(profile="nagpuri")
    print("DJVisualEngine initialized and ready.")
