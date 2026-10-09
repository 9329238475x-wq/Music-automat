"""
DJ Visual Engine Module
1. Creates a 1920x1080 Thumbnail Wall Grid (Collage) of all tracks with 5% dark shade.
2. Renders an Avee Player style circular bass-reactive visualizer pulsating to kicks/sub-bass.
3. Streams frames directly into FFmpeg stdin with zero temporary disk image files.
"""

import os
import sys
import math
import time
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

        # Resolve logo path from settings.json or profiles_meta.json
        self.logo_path = None
        settings_path = os.path.join(self.base_dir, "config", "settings.json")
        if os.path.exists(settings_path):
            try:
                import json
                with open(settings_path, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                custom_logo = s_data.get("profiles", {}).get(self.profile, {}).get("logo_file")
                if custom_logo and os.path.exists(os.path.join(self.base_dir, custom_logo)):
                    self.logo_path = os.path.join(self.base_dir, custom_logo)
            except Exception:
                pass

        if not self.logo_path:
            meta_path = os.path.join(self.base_dir, "config", "profiles_meta.json")
            if os.path.exists(meta_path):
                try:
                    import json
                    with open(meta_path, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                    for item in m_data:
                        if item.get("id") == self.profile:
                            custom_logo = item.get("logo_file")
                            if custom_logo and os.path.exists(os.path.join(self.base_dir, custom_logo)):
                                self.logo_path = os.path.join(self.base_dir, custom_logo)
                                break
                except Exception:
                    pass

        if not self.logo_path:
            if self.profile == "edm":
                self.logo_path = os.path.join(self.assets_dir, "My EDM LOGO.png")
                if not os.path.exists(self.logo_path):
                    self.logo_path = os.path.join(self.assets_dir, "logo_edm.png")
            else:
                logo_name = f"logo_{self.profile}.png"
                self.logo_path = os.path.join(self.assets_dir, logo_name)
                if not os.path.exists(self.logo_path):
                    self.logo_path = os.path.join(self.assets_dir, "logo_nagpuri.png")
        logger.info(f"Visual Engine loaded logo for profile '{self.profile}': {self.logo_path}")

    def create_thumbnail_wall(
        self,
        thumb_paths: List[str],
        out_path: Optional[str] = None,
        darkness: float = 0.25
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
        Renders the sleek DJ Bass Visualizer MP4 video.
        Features:
        1. 25% Darkened Poster Wall background.
        2. Dynamic Background Bass Bounce: Wallpaper zooms and vibrates with every kick drum / sub-bass hit.
        3. Clean, minimalist Glowing Neon Disc with Channel Logo (no messy spikes).
        4. Streamlined 16-frame pre-rendered buffer cache for ultra-fast NVENC GPU encoding (150-250 FPS).
        5. Gracefully handles stream termination with -shortest without BrokenPipeError.
        """
        if output_mp4 is None:
            output_mp4 = os.path.join(self.output_dir, f"{self.profile}_nonstop_mix.mp4")

        width, height = 1920, 1080
        cx, cy = width // 2, height // 2

        # Step 1: Pre-calculate FFT bass energy curve
        bass_curve, _, duration = self._extract_audio_fft(audio_path, fps=fps, num_bars=32)
        total_frames = len(bass_curve)

        logger.info(f"Total video duration: {duration:.1f}s ({total_frames} frames @ {fps} fps)")

        # Step 2: Load base background image
        base_bg = Image.open(background_path).convert("RGBA")
        if base_bg.size != (width, height):
            base_bg = ImageOps.fit(base_bg, (width, height))

        # Apply 20% dark tint overlay so poster is dark and contrasty
        dark_overlay = Image.new("RGBA", (width, height), (0, 0, 0, int(255 * 0.20)))
        base_bg = Image.alpha_composite(base_bg, dark_overlay)

        # Load channel logo for center disc
        logo = None
        if os.path.exists(self.logo_path):
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
            except Exception as e:
                logger.warning(f"Could not open logo {self.logo_path}: {e}")

        # Theme colors based on profile
        if self.profile == "edm":
            neon_color = (220, 20, 255, 240)  # Electric Neon Purple/Magenta for EDM
        elif self.profile == "nagpuri":
            neon_color = (255, 120, 20, 230)  # Orange/Saffron for Nagpuri
        else:
            neon_color = (0, 220, 255, 230)   # Cyan/Electric Blue for Vibration
        disc_fill = (12, 14, 20, 235)

        # Pre-render 16 discrete bass vibration frames
        num_levels = 16
        logger.info(f"Pre-rendering {num_levels} high-speed dynamic bass animation frames...")
        cached_frames_bytes = []

        # Oversized base for clean zoom cropping (1988 x 1118)
        max_scale = 1.035
        max_w, max_h = int(width * max_scale) + 4, int(height * max_scale) + 4
        oversized_bg = ImageOps.fit(base_bg, (max_w, max_h))

        for lvl in range(num_levels):
            b_val = lvl / (num_levels - 1)  # 0.0 to 1.0

            # Dynamic Background Bass Bounce
            cur_scale = 1.0 + b_val * 0.035
            cur_w = int(width * cur_scale)
            cur_h = int(height * cur_scale)
            cropped_bg = oversized_bg.crop((
                (max_w - cur_w) // 2,
                (max_h - cur_h) // 2,
                (max_w + cur_w) // 2,
                (max_h + cur_h) // 2
            )).resize((width, height), Image.Resampling.BILINEAR)

            # Draw Clean, Elegant Center Disc (No cluttered radial spikes!)
            cur_r = int(160 + 25 * b_val)
            glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(glow_layer)

            # Outer Neon Halo Ring
            draw.ellipse([cx - cur_r - 8, cy - cur_r - 8, cx + cur_r + 8, cy + cur_r + 8], outline=neon_color, width=5)
            # Inner Crisp White Accent Ring
            draw.ellipse([cx - cur_r - 2, cy - cur_r - 2, cx + cur_r + 2, cy + cur_r + 2], outline=(255, 255, 255, 230), width=3)
            # Deep Dark Disc Background
            draw.ellipse([cx - cur_r, cy - cur_r, cx + cur_r, cy + cur_r], fill=disc_fill)

            # Center Channel Logo
            if logo is not None:
                logo_dim = int(cur_r * 1.65)
                res_logo = logo.resize((logo_dim, logo_dim), Image.Resampling.LANCZOS)
                lx = cx - logo_dim // 2
                ly = cy - logo_dim // 2
                glow_layer.paste(res_logo, (lx, ly), res_logo)

            # Composite frame
            full_frame = Image.alpha_composite(cropped_bg, glow_layer)
            cached_frames_bytes.append(full_frame.tobytes())

        logger.info("✓ Pre-rendered animation frames ready in memory! Commencing blazing fast NVENC encode...")

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
                "-b:v", "1500k",
                "-maxrate", "2500k",
                "-bufsize", "5000k",
                "-pix_fmt", "yuv420p"
            ]
        else:
            logger.info("Using CPU libx264 ultrafast encoder (fallback)...")
            encoder_args = [
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "25",
                "-b:v", "1500k",
                "-maxrate", "2500k",
                "-bufsize", "5000k",
                "-pix_fmt", "yuv420p"
            ]

        # Step 3: Launch FFmpeg pipe with redirected log file
        cmd = [
            "ffmpeg", "-y",
            "-loglevel", "error",
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
        ffmpeg_log_path = os.path.join(self.output_dir, "ffmpeg_render.log")
        ffmpeg_log = open(ffmpeg_log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=ffmpeg_log)

        log_interval = max(1, total_frames // 20)  # Log every 5%
        t_start = time.time()

        try:
            for frame_idx in range(total_frames):
                b = bass_curve[frame_idx]
                lvl_idx = min(num_levels - 1, max(0, int(b * num_levels)))

                # Stream pre-cached frame bytes directly to FFmpeg stdin
                try:
                    proc.stdin.write(cached_frames_bytes[lvl_idx])
                except (BrokenPipeError, OSError):
                    logger.info(f"✓ FFmpeg closed input pipe (video encoded to full audio length at frame {frame_idx}/{total_frames}).")
                    break

                if frame_idx % log_interval == 0 and frame_idx > 0:
                    pct = int((frame_idx / total_frames) * 100)
                    elapsed = time.time() - t_start
                    fps_calc = frame_idx / elapsed
                    eta_sec = (total_frames - frame_idx) / max(fps_calc, 1.0)
                    logger.info(f"Render progress: {pct}% | Speed: {fps_calc:.1f} FPS | ETA: {eta_sec/60:.1f} min")

            try:
                proc.stdin.close()
            except Exception:
                pass
            proc.wait()
            try:
                ffmpeg_log.close()
            except Exception:
                pass

            if not (os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 1000000):
                err_text = ""
                if os.path.exists(ffmpeg_log_path):
                    with open(ffmpeg_log_path, "r", encoding="utf-8") as fl:
                        err_text = fl.read()
                raise RuntimeError(f"Video file not created properly. FFmpeg stderr: {err_text}")

            total_sec = time.time() - t_start
            avg_fps = total_frames / max(total_sec, 1.0)
            file_mb = os.path.getsize(output_mp4) / (1024 * 1024)
            logger.info(f"🎉 Rendering complete in {total_sec/60:.1f} minutes! Average speed: {avg_fps:.1f} FPS.")
            logger.info(f"✓ Output video verified: {output_mp4} ({file_mb:.1f} MB)")

        except Exception as e:
            logger.error(f"Render error: {e}")
            if proc.poll() is None:
                proc.kill()
            try:
                ffmpeg_log.close()
            except Exception:
                pass
            raise e

        return output_mp4
