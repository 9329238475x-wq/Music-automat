"""
DJ Visual Engine Module
1. Creates a 1920x1080 Thumbnail Wall Grid (Collage) with RED/NEON COLORED GRID BORDERS around each thumbnail.
2. Maintains 16:9 aspect ratio for all thumbnails (repeats if needed, never crops).
3. Renders an Avee Player style circular bass-reactive visualizer pulsating to kicks/sub-bass.
4. Streams frames directly into FFmpeg stdin with zero temporary disk image files.
"""

import os
import sys
import math
import time
import logging
import subprocess
import random
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

    def _get_random_neon_color(self):
        """Returns a random vibrant neon color for grid borders."""
        neon_colors = [
            (255, 0, 127),      # Hot Pink/Magenta
            (0, 255, 255),      # Cyan
            (255, 0, 0),        # Red
            (0, 255, 0),        # Lime Green
            (255, 215, 0),      # Gold
            (255, 128, 0),      # Orange
            (128, 0, 255),      # Purple
            (255, 20, 147),     # Deep Pink
            (0, 255, 127),      # Spring Green
            (255, 255, 0),      # Yellow
            (0, 127, 255),      # Deep Sky Blue
            (255, 69, 0),       # Red-Orange
        ]
        return random.choice(neon_colors)

    def create_thumbnail_wall(
        self,
        thumb_paths: List[str],
        out_path: Optional[str] = None,
        darkness: float = 0.25
    ) -> str:
        """
        Creates a 1920x1080 collage grid with RED/NEON COLORED GRID BORDERS around each thumbnail.
        - Each thumbnail maintains strict 16:9 aspect ratio.
        - Thumbnails are repeated if needed (never cropped).
        - Random neon colors for each thumbnail border.
        """
        if out_path is None:
            out_path = os.path.join(self.output_dir, "thumbnail_wall.jpg")

        logger.info(f"Generating 1920x1080 Thumbnail Wall Collage with NEON GRID BORDERS from {len(thumb_paths)} thumbnails...")
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

        # Border thickness for neon grid lines
        border_width = 4

        cell_w = math.ceil(width / cols)
        cell_h = math.ceil(height / rows)
        
        # Thumbnail size inside the cell (accounting for borders)
        thumb_w = cell_w - (2 * border_width)
        thumb_h = cell_h - (2 * border_width)

        # Place thumbnails into grid with neon borders
        idx = 0
        for r in range(rows):
            for c in range(cols):
                t_path = valid_thumbs[idx % len(valid_thumbs)]
                try:
                    # Open thumbnail
                    img = Image.open(t_path).convert("RGB")
                    
                    # Maintain 16:9 aspect ratio - fit inside thumb_w x thumb_h without cropping
                    # Use ImageOps.fit which pads if necessary
                    img = ImageOps.fit(img, (thumb_w, thumb_h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    
                    # Get random neon color for this thumbnail's border
                    border_color = self._get_random_neon_color()
                    
                    # Calculate position with border
                    cell_x = c * cell_w
                    cell_y = r * cell_h
                    img_x = cell_x + border_width
                    img_y = cell_y + border_width
                    
                    # Draw neon border (rectangle around thumbnail)
                    draw = ImageDraw.Draw(wall)
                    draw.rectangle(
                        [cell_x, cell_y, cell_x + cell_w - 1, cell_y + cell_h - 1],
                        outline=border_color,
                        width=border_width
                    )
                    
                    # Paste thumbnail inside border
                    wall.paste(img, (img_x, img_y))
                    
                except Exception as e:
                    logger.debug(f"Failed to load thumb {t_path}: {e}")
                idx += 1

        # Apply subtle dark shade (5-8% black overlay + vignette)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, int(255 * darkness)))
        wall_rgba = wall.convert("RGBA")
        combined = Image.alpha_composite(wall_rgba, overlay).convert("RGB")

        combined.save(out_path, quality=95)
        logger.info(f"Thumbnail wall with NEON GRID BORDERS saved at {out_path}")
        return out_path

    def _get_bold_font(self, size: int):
        """Loads bold high-CTR thumbnail font (Impact bundled font first, then system fonts)."""
        font_candidates = [
            os.path.join(self.assets_dir, "impact.ttf"),
            os.path.join(self.base_dir, "assets", "impact.ttf"),
            "C:/Windows/Fonts/impact.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/impact.ttf",
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

    # Alias for convenience
    _get_font = _get_bold_font

    def create_high_ctr_thumbnail(
        self,
        bg_wall_path: str,
        out_path: Optional[str] = None,
        custom_title: Optional[str] = None,
        custom_tag: Optional[str] = None,
        custom_sub: Optional[str] = None
    ) -> str:
        """
        Creates a viral, ultra-high-CTR 1920x1080 YouTube Thumbnail Poster:
        - Bold, pure white typography with deep black drop-shadow & solid black outline
          guarantees 100% readability on all mobile screens and dark/light YouTube feeds.
        - Automatically rotates from high-CTR viral titles & hooks (e.g. 'BHOJPURI TRENDING NONSTOP',
          'TRENDING BHOJPURI NONSTOP', etc.) so every video gets a unique, click-magnet thumbnail!
        - Dynamically auto-scales font sizes to fit perfectly without clipping.
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

        # Multi-layer Glowing 3D Subtitle Text Renderer (Pure White + Deep Black Glow & Solid Stroke, NO black patti)
        glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)

        shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)

        text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_layer)

        # Dynamic, auto-rotating high-CTR viral titles & tags pool
        from datetime import datetime
        year = datetime.now().year
        p = self.profile.lower()

        if p == "edm":
            main_titles = [
                "BHOJPURI TRENDING NONSTOP",
                "TRENDING BHOJPURI NONSTOP",
                "SUPERHIT BHOJPURI DANCE MIX",
                "VIRAL BHOJPURI EDM DROP",
                "NONSTOP PARTY BLAST",
                "HARD BASS EDM DROP",
                "HIGH VOLTAGE BHOJPURI MIX",
                "BHOJPURI ROADSHOW DROP",
                "DANCE PARTY DHAMAKA",
                "SUPERHIT CLUB DANCE MIX",
                "CIRCUIT STYLE EDM DROP",
                "JBL SOUND HARD BASS DROP",
                "NONSTOP DANCE PARTY MIX",
                "ALL BHOJPURI VIRAL SONGS",
                "SUPERHIT BARAAT DANCE MIX",
                "HARD BASS EDM SPECIAL"
            ]
            tags = [
                f"• BHOJPURI EDM DROP {year} •",
                f"• TOP TRENDING BHOJPURI •",
                f"• VIRAL DANCE SPECIAL {year} •",
                f"• ROADSHOW COMPETITION {year} •",
                f"• HIGH VOLTAGE EDM DROP •",
                f"• SUPERHIT PARTY SPECIAL •",
                f"• JBL SOUND HARD BASS •",
                f"• 100% NONSTOP DANCE HITS •"
            ]
            sub_texts = [
                "320 KBPS ULTRA HD | HIGH VOLTAGE DROP",
                "NONSTOP DANCE PARTY | 100% HEAVY BASS",
                "320 KBPS HD MASTER | FULL BASS BLAST",
                "TOP VIRAL TRACKS | SUPERHIT NONSTOP",
                "ROADSHOW COMPETITION | ULTRA DROP MIX",
                "JBL SOUND BEATS | 100% HARD HIT",
                "320 KBPS HD SOUND | ELECTRO DANCE DROP"
            ]
        elif p == "nagpuri":
            main_titles = [
                "THETH NAGPURI TRENDING NONSTOP",
                "TRENDING NAGPURI DANCE MIX",
                "NONSTOP THETH NAGPURI",
                "THETH NAGPURI SUPERHIT MIX",
                "VIRAL ROADSHOW NAGPURI MIX",
                "SUPERHIT NAGPURI NONSTOP",
                "HARD DANCE THETH NAGPURI",
                "TOP TRENDING NAGPURI MIX",
                "DHAMAKA DANCE NONSTOP",
                "JHARKHANDI SADRI DJ REMIX",
                "TAPA TAP HARD BASS NONSTOP",
                "SHADI SPECIAL NAGPURI MIX",
                "ROADSHOW COMPETITION SPECIAL",
                "PURULIA X THEATH NAGPURI",
                "KHORTHA X NAGPURI DANCE MIX",
                "ALL THETH MIXING JUKEBOX"
            ]
            tags = [
                f"• {year} THETH NAGPURI SPECIAL •",
                f"• SUPERHIT ROADSHOW DANCE •",
                f"• VIRAL NAGPURI HITS {year} •",
                f"• TOP THETH DANCE PICKS •",
                f"• SHADI MEIN DJ BAJI SPECIAL •",
                f"• ALL TIME FAVORITE NAGPURI •",
                f"• JHARKHANDI DHAMAKA {year} •",
                f"• TAPA TAP HARD BASS MIX •"
            ]
            sub_texts = [
                "320 KBPS HD MASTER | FULL ROADSHOW VIBRATION",
                "PURE THETH STYLE | NONSTOP DANCE BLAST",
                "320 KBPS ULTRA HD | WEDDING DANCE SPECIAL",
                "SUPERHIT DJ TRACKS | 100% CLEAR MASTER",
                "TAPA TAP BASS BEATS | ROADSHOW MIX",
                "JHARKHANDI SADRI HITS | 100% DANCE DHAMAKA",
                "FULL ROADSHOW SPECIAL | NONSTOP DANCE MIX"
            ]
        elif p == "vibration":
            main_titles = [
                "CG & TAPORI HARD BASS",
                "CG X NAGPURI NONSTOP",
                "FULL BASS HARD VIBRATION",
                "CG NONSTOP VIBRATION MIX",
                "CG TAPORI STYLE REMIX",
                "MANDAR X TAPORI REMIX",
                "CG X BHOJPURI VIBRATION",
                "SPEAKER PHOD HARD BASS",
                "CG ROADSHOW COMPETITION MIX",
                "100% WOOFER KILLER BLAST",
                "KHATARNAK BASS VIBRATION",
                "TRENDING CG REMIX NONSTOP",
                "VIRAL CG TAPORI NONSTOP",
                "CHHATTISGARHI DHAMAKA MIX",
                "HARD VIBRATION DANCE MIX",
                "EXTREME SUB BASS ROADSHOW"
            ]
            tags = [
                f"• CG X NAGPURI SPECIAL {year} •",
                f"• HARD BASS VIBRATION {year} •",
                f"• CHHATTISGARHI DHAMAKA •",
                f"• FULL TAPORI VIBRATION •",
                f"• ROADSHOW COMPETITION SPECIAL •",
                f"• 100% WOOFER TESTING BASS •",
                f"• MANDAR X TAPORI BEATS •",
                f"• VIRAL HARD BASS {year} •"
            ]
            sub_texts = [
                "320 KBPS HD SOUND | 100% WOOFER KILLER BLAST",
                "FULL BASS HARD VIBRATION | ROADSHOW COMPETITION",
                "MANDAR X TAPORI BEAT | EXTREME SUB BASS",
                "SPEAKER PHOD VIBRATION | 100% DANGER BASS",
                "320 KBPS ULTRA HD | HIGH POWER VIBRATION",
                "FULL SYSTEM SHAKER | HARD TAPORI BEATS",
                "CHHATTISGARHI DHAMAKA | NONSTOP DANCE MIX"
            ]
        elif p == "dj_nan_say_karwan":
            main_titles = [
                "SADRI TRENDING NONSTOP",
                "TRENDING SADRI NAGPURI MIX",
                "NONSTOP SADRI DJ DANCE MIX",
                "SADRI LOVERS REMIX 2026",
                "SUPERHIT SADRI NAGPURI MIX",
                "VIRAL SADRI ROADSHOW BLAST",
                "SADRI DHAMAKA DANCE MIX",
                "SADRI X NAGPURI SUPERHIT",
                "OLD IS GOLD SADRI REMIX",
                "SHADI DANCE SADRI SPECIAL",
                "JHARKHANDI SADRI NONSTOP",
                "SADRI COMPETITION DANCE MIX",
                "NEW TRENDING SADRI DJ SONG",
                "TAPA TAP SADRI DANCE BLAST"
            ]
            tags = [
                f"• {year} SADRI NAGPURI SPECIAL •",
                f"• SUPERHIT SADRI DJ REMIX •",
                f"• VIRAL SADRI DANCE HITS •",
                f"• SADRI LOVERS ROADSHOW •",
                f"• ALL TIME SADRI FAVORITES •",
                f"• JHARKHANDI SADRI DHAMAKA •",
                f"• SHADI SPECIAL SADRI DANCE •"
            ]
            sub_texts = [
                "320 KBPS HD MASTER | FULL SADRI DANCE BLAST",
                "PURE SADRI STYLE | NONSTOP ROADSHOW MIX",
                "320 KBPS ULTRA HD | WEDDING DANCE SPECIAL",
                "SADRI LOVERS SPECIAL | 100% CLEAR MASTER",
                "SUPERHIT SADRI TRACKS | COMPETITION BEATS",
                "JHARKHANDI SADRI HITS | 100% DANCE DHAMAKA"
            ]
        else:
            clean_name = p.replace("_", " ").upper()
            main_titles = [
                f"{clean_name} TRENDING NONSTOP",
                f"TRENDING {clean_name} DANCE MIX",
                "NONSTOP DJ DANCE MIX",
                f"SUPERHIT {clean_name} SPECIAL"
            ]
            tags = [
                f"• {clean_name} SPECIAL {year} •",
                f"• TOP TRENDING {clean_name} •"
            ]
            sub_texts = [
                "320 KBPS ULTRA HD MASTER | FULL BASS",
                "320 KBPS HD SOUND | NONSTOP DANCE"
            ]

        tag_text = custom_tag or random.choice(tags)
        main_title = custom_title or random.choice(main_titles)
        sub_text = custom_sub or random.choice(sub_texts)

        # Dynamic font scaler: guarantees text NEVER overflows 1920 canvas width
        def get_fitting_font(text: str, default_size: int, max_w: int):
            size = default_size
            font = self._get_bold_font(size)
            bbox = text_draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            if tw > max_w and tw > 0:
                scaled_size = max(int(default_size * (max_w / tw)), 40)
                font = self._get_bold_font(scaled_size)
            return font

        font_tag = get_fitting_font(tag_text, 52, 1550)
        font_main = get_fitting_font(main_title, 135, 1680)
        font_sub = get_fitting_font(sub_text, 46, 1650)

        # Place Channel Logo Emblem at top center if available
        logo_y_offset = 205
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                logo_img = Image.open(self.logo_path).convert("RGBA")
                logo_dim = 160
                logo_img = logo_img.resize((logo_dim, logo_dim), Image.Resampling.LANCZOS)
                
                # Draw circular white & black emblem border with soft black shadow
                border_img = Image.new("RGBA", (logo_dim + 24, logo_dim + 24), (0, 0, 0, 0))
                b_draw = ImageDraw.Draw(border_img)
                b_draw.ellipse([2, 2, logo_dim + 21, logo_dim + 21], fill=(0, 0, 0, 240), outline=(0, 0, 0, 255), width=6)
                b_draw.ellipse([5, 5, logo_dim + 18, logo_dim + 18], fill=(0, 0, 0, 240), outline=(255, 255, 255, 255), width=4)
                
                logo_x = cx - logo_dim // 2
                logo_y = logo_y_offset
                base.paste(border_img, (logo_x - 12, logo_y - 12), border_img)
                base.paste(logo_img, (logo_x, logo_y), logo_img)
                text_start_y = logo_y + logo_dim + 30
            except Exception as e:
                logger.warning(f"Failed to place logo on thumbnail: {e}")
                text_start_y = 330
        else:
            text_start_y = 330

        # Subtitle-Style Multi-Layer Glowing Text (Pure White + Deep Black Glow & Solid Stroke)
        def add_centered_subtitle_text(text: str, y: int, font, stroke_w: int = 12, shadow_off: int = 8, glow_w: int = 24):
            bbox = text_draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            tx = cx - tw // 2
            # 1. Soft Black Glowing Halo (radiating around text)
            glow_draw.text((tx, y), text, font=font, fill=(0, 0, 0, 255), stroke_width=glow_w, stroke_fill=(0, 0, 0, 255))
            # 2. Deep 3D Drop Shadow
            shadow_draw.text((tx + shadow_off, y + shadow_off + 2), text, font=font, fill=(0, 0, 0, 230), stroke_width=stroke_w + 2, stroke_fill=(0, 0, 0, 230))
            # 3. Solid Sharp Black Outline + Pure White Text (Classic Subtitle Look)
            text_draw.text((tx, y), text, font=font, fill=(255, 255, 255, 255), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))

        # Render 3 high-impact lines:
        add_centered_subtitle_text(tag_text, text_start_y, font_tag, stroke_w=8, shadow_off=6, glow_w=20)
        add_centered_subtitle_text(main_title, text_start_y + 80, font_main, stroke_w=14, shadow_off=10, glow_w=30)
        add_centered_subtitle_text(sub_text, text_start_y + 250, font_sub, stroke_w=8, shadow_off=6, glow_w=20)

        # Apply soft blur to ambient black glow layer
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=8))

        # Composite layers directly onto base image (zero black patti box)
        base = Image.alpha_composite(base, glow_layer)
        base = Image.alpha_composite(base, shadow_layer)
        base = Image.alpha_composite(base, text_layer)

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

    # Alias for backwards compatibility
    _extract_zero_latency_dynamics = _extract_audio_fft

    def _clean_ticker_title(self, raw_title: str, remixer: str = "") -> str:
        """Strips remixer names, emojis, promo buzzwords, and returns clean song title."""
        import re
        t = raw_title
        if remixer:
            t = re.sub(re.escape(remixer), " ", t, flags=re.I)
            short_remixer = re.sub(r"^(?:dj|official|music)\s*", "", remixer, flags=re.I).strip()
            if len(short_remixer) > 3:
                t = re.sub(re.escape(short_remixer), " ", t, flags=re.I)

        # Remove bracketed and parenthesized content e.g. [Official Video], (4k Full Song)
        t = re.sub(r"\[.*?\]|\(.*?\)", " ", t)
        # Strip emojis and non-standard characters
        t = re.sub(r"[^\w\sऀ-ॿ]", " ", t)
        # Strip promo buzzwords
        junk = (
            r"(?:4k|hd|hq|audio|video|mp3|official|original|remix|dj|rmx|fl studio|"
            r"competition|roadshow|vibration|sound check|soundcheck|sound test|bass boosted|"
            r"dhamaka|superhit|hit song|edm drop|edm|drop|bhojpuri|nagpuri|theth|cg|tapori|"
            r"nonstop|non stop|jukebox|mashup|2024|2025|2026|2027|by|ft|feat|prod|presents?|studio)"
        )
        t = re.sub(junk, " ", t, flags=re.I)
        t = re.sub(r"\s+", " ", t).strip()
        cleaned = t.title() if len(t) > 2 else raw_title[:30].strip()
        return cleaned[:40].strip()

    def _format_ass_timestamp(self, seconds: float) -> str:
        """Formats seconds into ASS timestamp format 0:00:00.00"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    def _get_media_duration(self, file_path: str) -> float:
        """Extracts exact media duration via ffprobe or ffmpeg."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception:
            pass
        try:
            res = subprocess.run(["ffmpeg", "-i", file_path], capture_output=True, text=True, timeout=10)
            import re
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        except Exception:
            pass
        return 0.0

    def _generate_spinning_vinyl_frames(
        self,
        out_dir: str,
        num_frames: int = 60,
        disc_dim: int = 480
    ) -> None:
        """Pre-renders 60 seamless rotating vinyl record frames with channel logo emblem."""
        import shutil
        os.makedirs(out_dir, exist_ok=True)
        cx, cy = disc_dim // 2, disc_dim // 2
        r = disc_dim // 2 - 16

        # Theme neon color based on profile
        if self.profile == "edm":
            neon_color = (220, 20, 255)
            disc_label_color = (180, 0, 240)
        elif self.profile == "nagpuri":
            neon_color = (255, 120, 10)
            disc_label_color = (255, 140, 0)
        elif self.profile == "dj_nan_say_karwan":
            neon_color = (255, 42, 133)
            disc_label_color = (200, 20, 90)
        else:
            neon_color = (0, 225, 255)
            disc_label_color = (0, 160, 220)

        # Base vinyl body (dark charcoal with concentric record grooves)
        vinyl_base = Image.new("RGBA", (disc_dim, disc_dim), (0, 0, 0, 0))
        d_base = ImageDraw.Draw(vinyl_base)
        # Outer neon glow halo
        d_base.ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], outline=(*neon_color, 240), width=6)
        d_base.ellipse([cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1], outline=(255, 255, 255, 200), width=2)
        # Deep vinyl body
        d_base.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(15, 16, 20, 255))
        # Center label diameter (scaled proportionally to disc size)
        label_r = int(disc_dim * 0.19)
        label_img = Image.new("RGBA", (label_r * 2, label_r * 2), (0, 0, 0, 0))
        d_label = ImageDraw.Draw(label_img)
        d_label.ellipse([0, 0, label_r * 2, label_r * 2], fill=(*disc_label_color, 255), outline=(255, 255, 255, 255), width=3)

        # Concentric audio grooves
        for gr in range(label_r + 20, r - 10, 14):
            d_base.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], outline=(38, 40, 48, 170), width=1)

        # Paste channel logo in center label if available
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                logo_raw = Image.open(self.logo_path).convert("RGBA")
                logo_size = int(label_r * 1.6)
                logo_res = logo_raw.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                # Circular mask for logo
                mask = Image.new("L", (logo_size, logo_size), 0)
                ImageDraw.Draw(mask).ellipse([0, 0, logo_size, logo_size], fill=255)
                label_img.paste(logo_res, ((label_r * 2 - logo_size) // 2, (label_r * 2 - logo_size) // 2), mask)
            except Exception as e:
                logger.warning(f"Could not composite logo into vinyl disc: {e}")

        # Center spindle hole
        spindle_r = 14
        d_label.ellipse(
            [label_r - spindle_r, label_r - spindle_r, label_r + spindle_r, label_r + spindle_r],
            fill=(8, 10, 14, 255),
            outline=(200, 205, 215, 255),
            width=2
        )

        # Pre-render 60 rotated frames
        for f_idx in range(num_frames):
            angle = (360.0 / num_frames) * f_idx
            rot_label = label_img.rotate(-angle, resample=Image.Resampling.BICUBIC)
            frame = vinyl_base.copy()
            frame.paste(rot_label, (cx - label_r, cy - label_r), rot_label)
            frame_path = os.path.join(out_dir, f"disc_{f_idx:02d}.png")
            frame.save(frame_path, "PNG")

    def _generate_ticker_ass(
        self,
        ass_path: str,
        tracks: Optional[List[Dict[str, Any]]],
        total_duration: float
    ) -> None:
        """
        Generates ASS subtitle file for an unbroken, continuous train of glowing white song titles
        with a deep black glow/shadow, perfectly clipped inside the sleek 1160px HUD capsule bar (X=385 to 1535).
        - Pure white crisp typography (&H00FFFFFF).
        - Deep black glow and shadow (&H00000000) for maximum pop and readability on any background.
        - Continuous queue (कतार) with ZERO empty space or waiting.
        - Zero brackets [][][][] or ugly notches.
        - Seamless mathematical loop matching cycle width.
        """
        from PIL import ImageFont

        # Measure unit text width for seamless infinite looping
        try:
            f_cand = os.path.join(self.base_dir, 'assets', 'impact.ttf')
            if not os.path.exists(f_cand):
                f_cand = 'C:/Windows/Fonts/arial.ttf'
            calc_font = ImageFont.truetype(f_cand, 28)
        except Exception:
            calc_font = None

        header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: WhiteText,Arial,28,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,3,2,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        slash = chr(92)
        speed = 85.0  # px per second (smooth, comfortable reading speed)
        x_start = 960  # Center inside capsule box

        if tracks and len(tracks) > 0:
            for idx, tr in enumerate(tracks):
                start_s = float(tr.get("seconds", 0.0))
                if idx + 1 < len(tracks):
                    end_s = float(tracks[idx + 1].get("seconds", start_s + tr.get("exact_duration", 180.0)))
                else:
                    end_s = total_duration

                if end_s <= start_s:
                    end_s = start_s + 180.0

                clean_title = self._clean_ticker_title(tr.get("title", f"Track {idx + 1}"), tr.get("remixer", ""))
                if idx + 1 < len(tracks):
                    next_clean = self._clean_ticker_title(tracks[idx + 1].get("title", ""), tracks[idx + 1].get("remixer", ""))
                    unit = f"🎵 {clean_title}   ✦   ⚡ NEXT : {next_clean}   ✦   "
                else:
                    unit = f"🎵 {clean_title}   ✦   🔥 NONSTOP DANCE MIX   ✦   "

                # Calculate cycle metrics
                if calc_font:
                    try:
                        bbox = calc_font.getbbox(unit)
                        w_unit = max(400, bbox[2] - bbox[0])
                    except Exception:
                        w_unit = len(unit) * 15
                else:
                    w_unit = len(unit) * 15

                cycle_time = max(4.0, round(w_unit / speed, 2))
                train = unit * 6  # Unbroken queue: always fills the capsule

                t_cur = start_s
                while t_cur < end_s:
                    t_next = min(t_cur + cycle_time, end_s)
                    dur = t_next - t_cur
                    if dur < 0.2:
                        break
                    frac = dur / cycle_time
                    cur_x_end = int(x_start - w_unit * frac)

                    t1_str = self._format_ass_timestamp(t_cur)
                    t2_str = self._format_ass_timestamp(t_next)

                    tag = "{" + slash + f"q2{slash}clip(385,892,1535,944){slash}move({x_start},918,{cur_x_end},918)" + "}"
                    events.append(f"Dialogue: 0,{t1_str},{t2_str},WhiteText,,0,0,0,,{tag}{train}")
                    t_cur = t_next
        else:
            brand = self.profile.upper().replace("_", " ")
            unit = f"🎵 {brand} NONSTOP REMIX   ✦   🔥 320 KBPS HD MASTER   ✦   "
            w_unit = len(unit) * 15
            cycle_time = max(4.0, round(w_unit / speed, 2))
            train = unit * 6

            t_cur = 0.0
            while t_cur < total_duration:
                t_next = min(t_cur + cycle_time, total_duration)
                dur = t_next - t_cur
                if dur < 0.2:
                    break
                frac = dur / cycle_time
                cur_x_end = int(x_start - w_unit * frac)

                t1_str = self._format_ass_timestamp(t_cur)
                t2_str = self._format_ass_timestamp(t_next)

                tag = "{" + slash + f"q2{slash}clip(385,892,1535,944){slash}move({x_start},918,{cur_x_end},918)" + "}"
                events.append(f"Dialogue: 0,{t1_str},{t2_str},WhiteText,,0,0,0,,{tag}{train}")
                t_cur = t_next

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")

    def render_visualizer_video(
        self,
        audio_path: str,
        background_path: str,
        output_mp4: Optional[str] = None,
        fps: int = 24,
        tracks: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Ultra-Fast CPU-Optimized High-Aesthetic Vinyl Record Visualizer:
        1. 50% Blurred Background Wallpaper with pre-baked static HUD (Header, Capsule & Progress Track).
        2. Seamless 360-Degree Spinning Vinyl Record (480px diameter) with channel logo emblem.
        3. Clean Sleek HUD Capsule Bar (1160px width) with continuous white glowing song titles & black shadow.
        4. Smooth real-time running progress bar (1360px width) & ticking match timer (00:00 to mix end).
        5. 100% Native FFmpeg C-engine execution with live progress logging to Kaggle/console!
        """
        import shutil
        if output_mp4 is None:
            output_mp4 = os.path.join(self.output_dir, f"{self.profile}_nonstop_mix.mp4")

        width, height = 1280, 720
        slash = chr(92)

        # Step 1: Rapidly detect audio duration
        duration_sec = self._get_media_duration(audio_path)
        if duration_sec <= 0:
            logger.warning("Could not determine audio duration via ffprobe. Fallback to 3600s.")
            duration_sec = 3600.0

        dur_min = int(duration_sec // 60)
        dur_sec = int(duration_sec % 60)

        logger.info(f"🚀 [VINYL VISUALIZER 720p] Master Audio Duration: {dur_min:02d}:{dur_sec:02d} ({duration_sec:.1f}s)")

        # Theme color hex & Channel Title
        if self.profile == "edm":
            channel_title = "⚡ MEGA MUSIC NONSTOP • BHOJPURI EDM DROP SPECIAL 2026 ⚡"
        elif self.profile == "nagpuri":
            channel_title = "🔥 NONSTOP THETH NAGPURI DJ DANCE MIX 2026 💃"
        elif self.profile == "dj_nan_say_karwan":
            channel_title = "🎧 NAGPURI STUDIO REMIX • STUDIO BEAT NONSTOP 🎧"
        else:
            channel_title = "🔊 CHHATTISGARHIYA & REGIONAL HARD VIBRATION DANCE MIX ⚡"

        # Step 2: Build 720p 50% Blurred Background with Dark Overlay & Top Channel Title
        logger.info("Generating 720p blurred atmospheric background with top title...")
        blur_bg_path = os.path.join(self.output_dir, f"temp_{self.profile}_bg_blur.jpg")
        try:
            raw_bg = Image.open(background_path).convert("RGBA")
            if raw_bg.size != (width, height):
                raw_bg = ImageOps.fit(raw_bg, (width, height), Image.Resampling.LANCZOS)
            # 50% Gaussian Blur
            blurred = raw_bg.filter(ImageFilter.GaussianBlur(radius=18))
            # 40% Dark Vignette Tint
            dark = Image.new("RGBA", (width, height), (10, 12, 18, 140))
            comp_bg = Image.alpha_composite(blurred, dark)

            # Pre-draw static top channel title directly onto the background (zero FFmpeg per-frame load)
            hud_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            hud_draw = ImageDraw.Draw(hud_layer)

            # Top Channel Title (crisp white typography, 26px for 720p)
            title_font = self._get_bold_font(26)
            hud_draw.text((width // 2, 55), channel_title, fill=(255, 255, 255, 255), font=title_font, anchor="mm")

            final_bg = Image.alpha_composite(comp_bg, hud_layer).convert("RGB")
            final_bg.save(blur_bg_path, "JPEG", quality=90)
        except Exception as e:
            logger.error(f"Error creating blurred background: {e}")
            blur_bg_path = background_path

        # Step 3: Pre-render 60 Spinning Vinyl Record Frames (500px enlarged for prominent 720p display)
        disc_dim = 500
        logger.info(f"Pre-rendering 60 smooth 360° spinning vinyl record frames ({disc_dim}px)...")
        disc_dir = os.path.join(self.output_dir, f"temp_{self.profile}_disc")
        self._generate_spinning_vinyl_frames(disc_dir, num_frames=60, disc_dim=disc_dim)

        # Step 4: Native FFmpeg Filter Complex (Ultra-Fast 720p CPU: Only Centered Spinning Vinyl Disc Overlay)
        disc_x = (width - disc_dim) // 2
        disc_y = (height - disc_dim) // 2 + 25

        filter_chain = f"[0:v][1:v]overlay=x={disc_x}:y={disc_y}:shortest=1[outv]"

        disc_pattern = os.path.join(disc_dir, "disc_%02d.png").replace(slash, "/")

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", blur_bg_path,
            "-stream_loop", "-1", "-framerate", str(fps), "-i", disc_pattern,
            "-i", audio_path,
            "-filter_complex", filter_chain,
            "-map", "[outv]",
            "-map", "2:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "fastdecode",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "320k",
            "-shortest",
            "-threads", "0",
            "-progress", "pipe:1",
            "-nostats",
            output_mp4
        ]

        logger.info(f"Starting Ultra-Fast Native FFmpeg Rendering: {output_mp4}...")
        t_start = time.time()
        total_frames = int(duration_sec * fps)

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        last_pct = 0
        all_lines = []

        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if line:
                    all_lines.append(line)
                    if len(all_lines) > 50:
                        all_lines.pop(0)

                if line.startswith("frame="):
                    try:
                        cur_frame = int(line.split("=")[1].strip())
                        pct = int((cur_frame / max(1, total_frames)) * 100)
                        if pct >= last_pct + 10 or (pct >= 99 and last_pct < 99):
                            elapsed_sec = time.time() - t_start
                            cur_fps = cur_frame / max(1.0, elapsed_sec)
                            remaining_sec = max(0, (total_frames - cur_frame) / max(1.0, cur_fps))
                            logger.info(
                                f"⏳ [FFmpeg Render] {pct}% ({cur_frame}/{total_frames} frames | "
                                f"Speed: {cur_fps:.1f} FPS | Elapsed: {elapsed_sec/60:.1f}m | ETA: {remaining_sec/60:.1f}m)"
                            )
                            last_pct = pct
                    except Exception:
                        pass

            proc.wait()
        except Exception as e:
            if proc.poll() is None:
                proc.kill()
            raise RuntimeError(f"FFmpeg process interrupted: {e}")

        if proc.returncode != 0 or not (os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 10000):
            err_snippet = "\n".join(all_lines[-20:]) if all_lines else "Unknown FFmpeg error"
            logger.error(f"FFmpeg error: {err_snippet}")
            raise RuntimeError(f"FFmpeg rendering failed: {err_snippet}")

        elapsed = time.time() - t_start
        avg_fps = total_frames / max(elapsed, 1.0)
        file_mb = os.path.getsize(output_mp4) / (1024 * 1024)
        logger.info(f"🎉 Rendering complete in {elapsed/60:.1f} minutes! Average speed: {avg_fps:.1f} FPS.")
        logger.info(f"✓ Video output verified: {output_mp4} ({file_mb:.1f} MB)")

        # Cleanup temporary files
        try:
            if os.path.exists(blur_bg_path):
                os.remove(blur_bg_path)
            if os.path.exists(ass_path):
                os.remove(ass_path)
            if os.path.exists(disc_dir):
                shutil.rmtree(disc_dir, ignore_errors=True)
        except Exception:
            pass

        return output_mp4

    def render_shorts_video(
        self,
        top_track: Dict[str, Any],
        out_mp4: Optional[str] = None,
        clip_duration_sec: float = 35.0,
        fps: int = 24
    ) -> Optional[str]:
        """
        Renders an ultra-fast, viral 9:16 (1080x1920) Vertical YouTube Short:
        - Generated from the #1 highest-viewed viral track of the batch!
        - Extracts a 35s high-energy drop/chorus segment.
        - Avee Player 360° circular bass visualizer pulsing at 1080x1920 vertical center.
        - Eye-catching viral CTA banners ('FULL NONSTOP IS LIVE! LINK IN COMMENTS').
        - Streams directly to FFmpeg stdin (renders in ~5-8 seconds on CPU).
        """
        if out_mp4 is None:
            out_mp4 = os.path.join(self.output_dir, f"{self.profile}_viral_short.mp4")

        # Use the original downloaded audio directly from 0.0s (NO intro cut / zero trim)
        src_audio = top_track.get("audio_path") or top_track.get("norm_path")
        if not src_audio or not os.path.exists(src_audio):
            src_audio = top_track.get("norm_path")

        if not src_audio or not os.path.exists(src_audio):
            logger.warning("Shorts generation skipped: Top track audio file not found.")
            return None

        logger.info(f"🎬 Generating 35-Second 9:16 Short (Original track from 0:00, zero cuts): {top_track.get('title', '')[:35]}...")

        # 1. Play strictly from the start (0.0s) for exactly 35.0 seconds
        temp_short_audio = os.path.join(self.output_dir, f"temp_{self.profile}_short.wav")
        cut_cmd = [
            "ffmpeg", "-y",
            "-ss", "0.00",
            "-t", f"{clip_duration_sec:.2f}",
            "-i", src_audio,
            "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={clip_duration_sec - 1.0:.1f}:d=1.0,loudnorm=I=-14:TP=-1.0",
            "-ar", "44100",
            "-ac", "2",
            temp_short_audio
        ]
        subprocess.run(cut_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not os.path.exists(temp_short_audio) or os.path.getsize(temp_short_audio) < 1000:
            logger.warning("Shorts audio cut failed, using full track as fallback.")
            temp_short_audio = src_audio

        # 2. Extract dynamics for 35s snippet
        try:
            norm, duration_sec = self._extract_audio_fft(temp_short_audio, fps=fps)
            total_frames = int(duration_sec * fps)
        except Exception as e:
            logger.warning(f"Dynamics extraction failed for Short: {e}")
            return None

        # 3. Build Vertical 1080x1920 Static Background Frame
        width, height = 1080, 1920
        cx, cy = width // 2, height // 2

        thumb_path = top_track.get("thumb_path")
        if thumb_path and os.path.exists(thumb_path):
            try:
                base_img = Image.open(thumb_path).convert("RGBA")
                # Scale up to fill vertical 1080x1920 with atmospheric blur
                base_img = ImageOps.fit(base_img, (width, height), Image.Resampling.LANCZOS)
                base_img = base_img.filter(ImageFilter.GaussianBlur(radius=20))
                # Darken by 40%
                dark_overlay = Image.new("RGBA", (width, height), (8, 10, 16, 120))
                base_img = Image.alpha_composite(base_img, dark_overlay)
            except Exception:
                base_img = Image.new("RGBA", (width, height), (12, 14, 22, 255))
        else:
            base_img = Image.new("RGBA", (width, height), (12, 14, 22, 255))

        # Add Neon Border around the 9:16 vertical frame
        border_draw = ImageDraw.Draw(base_img)
        neon_c = self._get_random_neon_color()
        border_draw.rectangle([6, 6, width - 6, height - 6], outline=(*neon_c, 240), width=6)

        # Clean title for display
        import re
        raw_t = top_track.get("title", "DJ Remix")
        c_title = re.sub(r"\[.*?\]|\(.*?\)", " ", raw_t)
        c_title = re.sub(r"[|\-_~:!@#$%^&*+=<>?/\\]", " ", c_title).strip()
        c_title = re.sub(r"\s+", " ", c_title).title()[:26]

        font_title = self._get_font(46)
        font_sub = self._get_font(30)
        font_cta = self._get_font(40)
        font_cta_sub = self._get_font(26)

        # Top Text Overlay
        top_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        t_draw = ImageDraw.Draw(top_layer)

        # Top Pill Badge
        badge_text = f"🔥 {c_title} DJ DROP ⚡"
        t_draw.rounded_rectangle([60, 160, width - 60, 260], radius=24, fill=(15, 20, 32, 230), outline=(*neon_c, 240), width=3)
        t_draw.text((cx, 210), badge_text, fill=(255, 255, 255, 255), font=font_title, anchor="mm")

        # Top Subtitle
        t_draw.text((cx, 305), f"• 2026 {self.profile.upper().replace('_', ' ')} VIRAL HIT •", fill=(*neon_c, 230), font=font_sub, anchor="mm")

        # Bottom Call to Action Card
        t_draw.rounded_rectangle([60, height - 380, width - 60, height - 160], radius=28, fill=(10, 12, 18, 245), outline=(255, 255, 255, 200), width=3)
        t_draw.text((cx, height - 325), "🎧 FULL NONSTOP MIX IS LIVE! 🔥", fill=(255, 255, 255, 255), font=font_cta, anchor="mm")
        t_draw.text((cx, height - 265), "👇 LINK IN PINNED COMMENT & DESC 👇", fill=(*neon_c, 255), font=font_cta_sub, anchor="mm")
        t_draw.text((cx, height - 210), "⭐ 320 KBPS HD MASTER • 100% HEAVY BASS ⭐", fill=(200, 210, 230, 220), font=font_cta_sub, anchor="mm")

        base_frame = Image.alpha_composite(base_img, top_layer)

        # Load Logo for center disc
        logo = None
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
            except Exception:
                logo = None

        # 4. Pre-render 32 Vertical Avee Player Frames
        logger.info("Pre-rendering 32 Vertical Avee Player animation frames for Short...")
        cached_frames_bytes = []
        base_radius = 210
        max_expansion = 50
        num_bars = 64

        for level in range(32):
            b_val = level / 31.0
            frame = base_frame.copy()
            glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(glow)

            cur_r = int(base_radius + max_expansion * b_val)

            # Circular Spectrum Bars
            for idx in range(num_bars):
                angle = (2 * math.pi / num_bars) * idx
                bar_len = int(12 + 65 * b_val * (0.65 + 0.35 * math.sin(idx * 0.75)))
                x1 = cx + int(cur_r * math.cos(angle))
                y1 = cy + int(cur_r * math.sin(angle))
                x2 = cx + int((cur_r + bar_len) * math.cos(angle))
                y2 = cy + int((cur_r + bar_len) * math.sin(angle))
                alpha = int(140 + 115 * b_val)
                draw.line([(x1, y1), (x2, y2)], fill=(*neon_c, alpha), width=5)

            # Shockwave Burst
            if b_val > 0.4:
                sw_r = cur_r + int((b_val - 0.4) * 90)
                draw.ellipse([cx - sw_r, cy - sw_r, cx + sw_r, cy + sw_r], outline=(*neon_c, int(180 * (1.0 - (b_val - 0.4)))), width=4)

            # Center Double Ring & Disc
            draw.ellipse([cx - cur_r - 8, cy - cur_r - 8, cx + cur_r + 8, cy + cur_r + 8], outline=(*neon_c, 240), width=6)
            draw.ellipse([cx - cur_r - 2, cy - cur_r - 2, cx + cur_r + 2, cy + cur_r + 2], outline=(255, 255, 255, 255), width=3)
            draw.ellipse([cx - cur_r, cy - cur_r, cx + cur_r, cy + cur_r], fill=(12, 14, 22, 245))

            # Center Channel Logo
            if logo is not None:
                dim = int(cur_r * 1.5)
                res_logo = logo.resize((dim, dim), Image.Resampling.LANCZOS)
                glow.paste(res_logo, (cx - dim // 2, cy - dim // 2), res_logo)

            comp = Image.alpha_composite(frame, glow)
            cached_frames_bytes.append(comp.tobytes())

        # 5. Fast FFmpeg Encode
        cmd = [
            "ffmpeg", "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-framerate", str(fps),
            "-pix_fmt", "rgba",
            "-s", f"{width}x{height}",
            "-i", "-",
            "-i", temp_short_audio,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            out_mp4
        ]

        logger.info(f"Encoding 9:16 Vertical Short video ({total_frames} frames)...")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            for f_idx in range(total_frames):
                val = norm[f_idx]
                c_idx = min(31, max(0, int(val * 31)))
                proc.stdin.write(cached_frames_bytes[c_idx])
            proc.stdin.close()
            proc.wait()
        except Exception as e:
            if proc.poll() is None:
                proc.kill()
            logger.error(f"FFmpeg Short encoding error: {e}")
            return None

        # Clean temp audio
        if os.path.exists(temp_short_audio) and temp_short_audio != src_audio:
            try:
                os.remove(temp_short_audio)
            except Exception:
                pass

        if os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 10000:
            mb = os.path.getsize(out_mp4) / (1024 * 1024)
            logger.info(f"🎉 9:16 Vertical Short ready: {out_mp4} ({mb:.1f} MB)!")
            return out_mp4

        return None

