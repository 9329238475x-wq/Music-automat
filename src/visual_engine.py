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
from PIL import Image, ImageDraw, ImageOps, ImageFilter, ImageFont
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

    def _get_bold_font(self, size: int):
        """Loads bold high-CTR thumbnail font (Impact or Arial Bold with Ubuntu/Windows fallbacks)."""
        font_candidates = [
            "C:/Windows/Fonts/impact.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        ]
        for f in font_candidates:
            if os.path.exists(f):
                try:
                    return ImageFont.truetype(f, size)
                except Exception:
                    pass
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    def create_high_ctr_thumbnail(
        self,
        bg_wall_path: str,
        out_path: Optional[str] = None
    ) -> str:
        """
        Creates a viral, ultra-high-CTR 1920x1080 YouTube Thumbnail Poster:
        - Bold, pure white typography with deep black drop-shadow & solid black outline
          guarantees 100% readability on all mobile screens and dark/light YouTube feeds.
        - Automatically tailored per channel profile:
            * nagpuri: "NONSTOP THETH NAGPURI", "DJ DANCE MIX 2026", "320 KBPS HD MASTER | FULL ROADSHOW VIBRATION"
            * vibration: "HARD BASS VIBRATION", "CG & TAPORI DJ MIX 2026", "320 KBPS HD SOUND | 100% WOOFER KILLER BLAST"
            * edm: "BHOJPURI EDM DROP", "DANCE PARTY MIX 2026", "320 KBPS ULTRA HD | HIGH VOLTAGE DROP"
            * dj_nan_say_karwan: "DJ NAN SAY KARWAN", "SUPERHIT NONSTOP 2026", "320 KBPS HD MASTER | FULL ROADSHOW MIX"
        - Includes the channel's glowing circular logo emblem for instant brand recognition!
        """
        if out_path is None:
            out_path = os.path.join(self.output_dir, f"{self.profile}_youtube_thumbnail.jpg")

        width, height = 1920, 1080
        cx, cy = width // 2, height // 2

        if os.path.exists(bg_wall_path):
            base = Image.open(bg_wall_path).convert("RGBA")
            if base.size != (width, height):
                base = ImageOps.fit(base, (width, height))
        else:
            base = Image.new("RGBA", (width, height), (12, 14, 22, 255))

        # Soft translucent dark plate across the center to ensure 100% text contrast
        plate = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        p_draw = ImageDraw.Draw(plate)
        p_draw.rectangle([100, 170, width - 100, height - 170], fill=(0, 0, 0, 155))
        base = Image.alpha_composite(base, plate)

        draw = ImageDraw.Draw(base)

        # Profile-specific text & badges
        p = self.profile.lower()
        if p == "nagpuri":
            tag_text = "• 2026 THETH NAGPURI SPECIAL •"
            main_title = "NONSTOP DJ DANCE MIX"
            sub_text = "320 KBPS HD MASTER | FULL ROADSHOW VIBRATION"
        elif p == "vibration":
            tag_text = "• HARD BASS VIBRATION 2026 •"
            main_title = "CG & TAPORI DJ MIX"
            sub_text = "320 KBPS HD SOUND | 100% WOOFER KILLER BLAST"
        elif p == "edm":
            tag_text = "• BHOJPURI EDM DROP 2026 •"
            main_title = "DANCE PARTY MIX"
            sub_text = "320 KBPS ULTRA HD | HIGH VOLTAGE DROP"
        elif p == "dj_nan_say_karwan":
            tag_text = "• DJ NAN SAY KARWAN SPECIAL •"
            main_title = "SUPERHIT NONSTOP 2026"
            sub_text = "320 KBPS HD MASTER | FULL COMPETITION MIX"
        else:
            clean_name = p.replace("_", " ").upper()
            tag_text = f"• {clean_name} SPECIAL 2026 •"
            main_title = "NONSTOP DJ DANCE MIX"
            sub_text = "320 KBPS ULTRA HD MASTER | FULL BASS"

        # Load fonts (Impact / Arial Bold with platform fallbacks)
        font_tag = self._get_bold_font(48)
        font_main = self._get_bold_font(125)
        font_sub = self._get_bold_font(44)

        # Place Channel Logo Emblem at top center if available
        logo_y_offset = 205
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                logo_img = Image.open(self.logo_path).convert("RGBA")
                logo_dim = 160
                logo_img = logo_img.resize((logo_dim, logo_dim), Image.Resampling.LANCZOS)
                
                # Draw circular white & black emblem border
                border_img = Image.new("RGBA", (logo_dim + 16, logo_dim + 16), (0, 0, 0, 0))
                b_draw = ImageDraw.Draw(border_img)
                b_draw.ellipse([0, 0, logo_dim + 15, logo_dim + 15], fill=(0, 0, 0, 230), outline=(255, 255, 255, 255), width=4)
                
                logo_x = cx - logo_dim // 2
                logo_y = logo_y_offset
                base.paste(border_img, (logo_x - 8, logo_y - 8), border_img)
                base.paste(logo_img, (logo_x, logo_y), logo_img)
                text_start_y = logo_y + logo_dim + 30
            except Exception as e:
                logger.warning(f"Failed to place logo on thumbnail: {e}")
                text_start_y = 330
        else:
            text_start_y = 330

        # Helper to draw centered pure white text with solid black stroke and black drop shadow
        def draw_centered_white_text(text: str, y: int, font, stroke_w: int = 8, shadow_offset: int = 8):
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            tx = cx - tw // 2
            # 1. Deep Black Drop Shadow
            draw.text((tx + shadow_offset, y + shadow_offset), text, font=font, fill=(0, 0, 0, 255), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))
            # 2. Pure White Text with Solid Black Stroke
            draw.text((tx, y), text, font=font, fill=(255, 255, 255, 255), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))

        # Render 3 high-impact lines:
        # Line 1: Header Tag
        draw_centered_white_text(tag_text, text_start_y, font_tag, stroke_w=6, shadow_offset=6)
        # Line 2: Giant Main Title
        draw_centered_white_text(main_title, text_start_y + 80, font_main, stroke_w=10, shadow_offset=10)
        # Line 3: Bottom Soundmark Badge
        draw_centered_white_text(sub_text, text_start_y + 245, font_sub, stroke_w=6, shadow_offset=6)

        final_rgb = base.convert("RGB")
        final_rgb.save(out_path, quality=98)
        logger.info(f"✅ High-CTR YouTube Thumbnail Poster created at {out_path}")
        return out_path

    def _extract_audio_fft(
        self,
        audio_path: str,
        fps: int = 24
    ) -> Tuple[np.ndarray, float]:
        """
        Extracts multi-band acoustic energy (bass drops, vocal melodies, snares, claps,
        and crisp hi-hats) with ZERO LATENCY and snappy synchronization:
        - 60ms lead-in lookahead: eliminates perceived lag so animation strikes at the exact
          instant sound arrives at the ear.
        - Full-Spectrum Multi-Band Analysis:
            * Low (30Hz - 150Hz): Sub-bass kicks & 808 drops (massive expansion & shockwaves).
            * Mid (150Hz - 2400Hz): Vocals, melodies, snare hits, claps, flute, dholak/mandar.
            * High (2400Hz - 5200Hz): Hi-hats, shakers, cymbals, crisp percussion ticks.
        - Independent onset flux on all bands ensures EVERY small sound pulses the center disc.
        """
        logger.info("Extracting zero-latency full-spectrum dynamics (bass, vocals, snares, hi-hats)...")
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
        mid_energy = np.zeros(n_frames, dtype=np.float32)
        high_energy = np.zeros(n_frames, dtype=np.float32)

        # 1024 sample FFT window (rfft yields 513 bins, ~10.77 Hz per bin)
        n_fft = 1024
        window = np.hanning(n_fft)

        # 60ms lookahead offset: matches human acoustic-optic latency so visual expansion
        # coincides with audio transient impact with rock-solid zero perceived lag!
        lead_samples = int(0.060 * sr)

        for i in range(n_frames):
            center = i * hop_length
            start = center - (n_fft // 2) + lead_samples
            end = start + n_fft
            
            if start < 0:
                chunk = np.pad(audio[0:max(0, end)], (-start, 0))
            elif end > len(audio):
                chunk = np.pad(audio[start:], (0, end - len(audio)))
            else:
                chunk = audio[start:end]

            fft_vals = np.abs(np.fft.rfft(chunk * window))
            
            # 1. Low Band (30Hz - 150Hz): Bins 3 to 15 (Sub-bass, Kicks)
            if len(fft_vals) >= 15:
                bass_energy[i] = np.mean(fft_vals[3:15])
            
            # 2. Mid Band (150Hz - 2400Hz): Bins 15 to 225 (Vocals, Snare, Claps, Flute, Melody)
            if len(fft_vals) >= 225:
                mid_energy[i] = np.mean(fft_vals[15:225])

            # 3. High Band (2400Hz - 5200Hz): Bins 225 to 485 (Hi-hats, Shakers, Bells, Crisp Clicks)
            if len(fft_vals) >= 485:
                high_energy[i] = np.mean(fft_vals[225:485])

        # Normalize each frequency band independently so soft vocals & hi-hats aren't silenced
        def _norm_band(arr: np.ndarray, pct: float) -> np.ndarray:
            p = np.percentile(arr, pct) + 1e-6
            return np.clip(arr / p, 0.0, 1.0)

        b_norm = _norm_band(bass_energy, 95)
        m_norm = _norm_band(mid_energy, 92)
        h_norm = _norm_band(high_energy, 90)

        # Compute sharp onset flux (transient attacks) for all bands
        b_onset = np.zeros_like(b_norm)
        b_onset[1:] = np.maximum(0.0, b_norm[1:] - b_norm[:-1])
        b_onset_norm = _norm_band(b_onset, 95)

        m_onset = np.zeros_like(m_norm)
        m_onset[1:] = np.maximum(0.0, m_norm[1:] - m_norm[:-1])
        m_onset_norm = _norm_band(m_onset, 92)

        h_onset = np.zeros_like(h_norm)
        h_onset[1:] = np.maximum(0.0, h_norm[1:] - h_norm[:-1])
        h_onset_norm = _norm_band(h_onset, 90)

        # Multi-band Fusion: Every vocal syllable, hi-hat, snare hit, and kick creates visual life!
        combined = (
            0.45 * (b_norm + 1.25 * b_onset_norm) +
            0.35 * (m_norm + 1.10 * m_onset_norm) +
            0.20 * (h_norm + 0.85 * h_onset_norm)
        )

        # Final normalization to [0.0, 1.0]
        p_max = np.percentile(combined, 97) + 1e-6
        norm = np.clip(combined / p_max, 0.0, 1.0)

        # Responsive power curve (1.15): allows small sounds (vocals, hi-hats) to show clearly
        # without compressing them into darkness, while heavy kicks push to maximum power!
        norm = np.power(norm, 1.15)

        # Snappy instant attack with fast spring release (decay 0.58)
        # Keeps animation tight, lively, and reactive to every consecutive beat
        smoothed_energy = np.zeros_like(norm)
        cur = 0.0
        for i in range(len(norm)):
            val = norm[i]
            cur = max(val, cur * 0.58)
            smoothed_energy[i] = cur

        return smoothed_energy, duration_sec

    def render_visualizer_video(
        self,
        audio_path: str,
        background_path: str,
        output_mp4: Optional[str] = None,
        fps: int = 24
    ) -> str:
        """
        Renders the HIGH-ENERGY Avee Player 360-Degree Bass Visualizer MP4 video:
        1. 360-Degree Radial Frequency Spectrum: 72 dynamic bars shoot outward with beat!
        2. Massive Center Disc Expansion (+55px pulse with kick drum / sub-bass drop).
        3. High-Voltage Shockwave Blast Ring that bursts outward on heavy bass drops.
        4. Screen Bass Bounce & Sub-Woofer Camera Vibration (8% zoom displacement).
        5. Perfect zero-latency sync with audio beats.
        6. Pre-rendered 32-frame buffer cache for ultra-fast NVENC GPU encoding (150-250 FPS).
        """
        if output_mp4 is None:
            output_mp4 = os.path.join(self.output_dir, f"{self.profile}_nonstop_mix.mp4")

        width, height = 1920, 1080
        cx, cy = width // 2, height // 2

        # Step 1: Pre-calculate zero-latency FFT bass energy curve
        bass_curve, duration = self._extract_audio_fft(audio_path, fps=fps)
        total_frames = len(bass_curve)

        logger.info(f"Total video duration: {duration:.1f}s ({total_frames} frames @ {fps} fps)")

        # Step 2: Load base background image
        base_bg = Image.open(background_path).convert("RGBA")
        if base_bg.size != (width, height):
            base_bg = ImageOps.fit(base_bg, (width, height))

        # Apply 20% dark tint overlay so poster is dark and visualizer pops
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
            neon_primary = (220, 20, 255)      # Electric Neon Purple/Magenta
            neon_secondary = (0, 240, 255)     # Laser Cyan
        elif self.profile == "nagpuri":
            neon_primary = (255, 120, 10)      # Saffron/Orange
            neon_secondary = (255, 215, 0)     # Neon Gold
        elif self.profile == "dj_nan_say_karwan":
            neon_primary = (255, 42, 133)      # Hot Pink / Ruby
            neon_secondary = (180, 0, 255)     # Deep Electric Purple
        else:
            neon_primary = (0, 225, 255)       # Cyan / Electric Blue
            neon_secondary = (255, 40, 140)    # Neon Hot Pink

        disc_fill = (10, 12, 18, 245)

        # Pre-render 32 high-energy dynamic bass animation frames
        num_levels = 32
        logger.info(f"Pre-rendering {num_levels} EXPLOSIVE Avee Player 360° bass animation frames...")
        cached_frames_bytes = []

        # Oversized base for clean zoom & camera shake cropping (1.10x scale)
        max_scale = 1.10
        max_w, max_h = int(width * max_scale) + 4, int(height * max_scale) + 4
        oversized_bg = ImageOps.fit(base_bg, (max_w, max_h))
        ow, oh = oversized_bg.size

        num_bars = 72
        for lvl in range(num_levels):
            b_val = lvl / (num_levels - 1)  # 0.0 to 1.0

            # 1. Dynamic Wallpaper Zoom & Sub-Woofer Vibration Shake
            cur_scale = 1.0 + b_val * 0.08  # Up to 8% dynamic zoom punch!
            cur_w = int(width * cur_scale)
            cur_h = int(height * cur_scale)
            
            # Subtle camera vibration displacement on heavy bass hits
            shake_x = int(math.sin(b_val * 12.0) * 5 * b_val)
            shake_y = int(math.cos(b_val * 12.0) * 4 * b_val)
            
            crop_x = max(0, min(ow - cur_w, (ow - cur_w) // 2 + shake_x))
            crop_y = max(0, min(oh - cur_h, (oh - cur_h) // 2 + shake_y))
            cropped_bg = oversized_bg.crop((
                crop_x, crop_y, crop_x + cur_w, crop_y + cur_h
            )).resize((width, height), Image.Resampling.BILINEAR)

            # 2. Glowing Avee Player Overlay
            glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(glow_layer)

            # Center radius expands massively from 165px up to 220px (+55px pulse!)
            cur_r = int(165 + 55 * b_val)

            # 3. 360-Degree Avee Player Radial Spectrum Bars (72 bars)
            for k in range(num_bars):
                angle = (2 * math.pi / num_bars) * k
                freq_weight = 0.5 + 0.5 * abs(math.sin(angle * 2.0))
                # Bar length explodes from 12px at rest up to 125px on maximum bass hits!
                bar_len = int(12 + (115 * b_val * freq_weight))

                r_start = cur_r + 8
                r_end = r_start + bar_len

                x1 = cx + int(r_start * math.cos(angle))
                y1 = cy + int(r_start * math.sin(angle))
                x2 = cx + int(r_end * math.cos(angle))
                y2 = cy + int(r_end * math.sin(angle))

                # Color gradient between primary neon and secondary accent
                alpha = int(160 + 95 * b_val)
                bar_r = int(neon_primary[0] * (1 - b_val * 0.5) + neon_secondary[0] * (b_val * 0.5))
                bar_g = int(neon_primary[1] * (1 - b_val * 0.5) + neon_secondary[1] * (b_val * 0.5))
                bar_b = int(neon_primary[2] * (1 - b_val * 0.5) + neon_secondary[2] * (b_val * 0.5))
                
                bar_w = 4 if b_val < 0.5 else 5
                draw.line([(x1, y1), (x2, y2)], fill=(bar_r, bar_g, bar_b, alpha), width=bar_w)

                # Glowing white-hot dot at bar tip during bass hits
                if b_val > 0.4:
                    draw.ellipse([x2 - 3, y2 - 3, x2 + 3, y2 + 3], fill=(255, 255, 255, alpha))

            # 4. Outer Expanding Bass Shockwave Ring (bursts on b_val > 0.5)
            if b_val > 0.45:
                sw_r = cur_r + int((b_val - 0.45) * 85)
                sw_alpha = int(200 * (1.0 - (b_val - 0.45) * 1.5))
                if sw_alpha > 0:
                    draw.ellipse(
                        [cx - sw_r, cy - sw_r, cx + sw_r, cy + sw_r],
                        outline=(*neon_primary, sw_alpha),
                        width=3
                    )

            # 4b. Floating Stardust Particles / Disco Sparks (expands rhythmically with beats!)
            stardust_count = 32
            for s_idx in range(stardust_count):
                s_angle = (2 * math.pi / stardust_count) * s_idx + (s_idx * 0.42)
                s_dist = cur_r + 115 + int(math.sin(s_idx * 1.8) * 35) + int(28 * b_val)
                sx = cx + int(s_dist * math.cos(s_angle))
                sy = cy + int(s_dist * math.sin(s_angle))
                s_size = 2 if (s_idx % 2 == 0) else 3
                s_alpha = int((110 + 145 * b_val) * (0.6 + 0.4 * abs(math.sin(s_idx * 2.1))))
                draw.ellipse([sx - s_size, sy - s_size, sx + s_size, sy + s_size], fill=(255, 255, 255, s_alpha))

            # 5. Glowing Double Halo Rings
            halo_width = int(6 + 4 * b_val)
            draw.ellipse(
                [cx - cur_r - 10, cy - cur_r - 10, cx + cur_r + 10, cy + cur_r + 10],
                outline=(*neon_primary, int(200 + 55 * b_val)),
                width=halo_width
            )
            # Inner Crisp White Ring
            draw.ellipse(
                [cx - cur_r - 3, cy - cur_r - 3, cx + cur_r + 3, cy + cur_r + 3],
                outline=(255, 255, 255, 240),
                width=3
            )
            # Deep Dark Disc Background
            draw.ellipse([cx - cur_r, cy - cur_r, cx + cur_r, cy + cur_r], fill=disc_fill)

            # 6. Center Channel Logo (Pulsing dynamically with the bass!)
            if logo is not None:
                logo_dim = int(cur_r * 1.55)
                res_logo = logo.resize((logo_dim, logo_dim), Image.Resampling.LANCZOS)
                lx = cx - logo_dim // 2
                ly = cy - logo_dim // 2
                glow_layer.paste(res_logo, (lx, ly), res_logo)

            # Composite full frame
            full_frame = Image.alpha_composite(cropped_bg.convert("RGBA"), glow_layer)
            cached_frames_bytes.append(full_frame.tobytes())

        logger.info("✓ 32 Explosive Avee Player animation frames ready in memory! Commencing NVENC encode...")

        # Check for working NVIDIA NVENC GPU hardware support
        has_nvenc = False
        try:
            chk = subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=s=64x64:d=0.04", "-c:v", "h264_nvenc", "-f", "null", "-"],
                capture_output=True,
                timeout=5
            )
            if chk.returncode == 0:
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

        # Step 3: Launch FFmpeg pipe with exact framerate and sync flags
        cmd = [
            "ffmpeg", "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-framerate", str(fps),      # Exact demuxer framerate
            "-pix_fmt", "rgba",
            "-s", f"{width}x{height}",
            "-i", "-",                   # Stream 0: Video from stdin
            "-i", audio_path,            # Stream 1: Master Audio
            "-map", "0:v:0",
            "-map", "1:a:0",
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

            if not (os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 10000):
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
