"""
DJ Audio Engine & Smooth Wooosh Transition Module
Normalizes all audio tracks with EBU R128 loudness.
Applies smooth 'Wooosh' riser transitions between every song.
Produces the continuous master mix and timestamped YouTube chapter tracklist.
"""

import os
import sys
import json
import logging
import subprocess
from typing import List, Dict, Any, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AudioEngine")


class DJAudioEngine:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.wooosh_path = os.path.join(self.assets_dir, "wooosh.wav")
        self.output_dir = os.path.join(self.base_dir, "output")
        self.temp_dir = os.path.join(self.output_dir, "temp_audio")
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_audio_duration(self, file_path: str) -> float:
        """Gets exact audio duration using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(res.stdout.strip())
        except Exception as e:
            logger.warning(f"ffprobe duration failed for {file_path}: {e}")
            return 0.0

    def _format_timestamp(self, seconds: float) -> str:
        """Formats seconds into HH:MM:SS format for YouTube chapters."""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

    def normalize_track(self, in_file: str, out_file: str) -> bool:
        """Normalizes audio to 44.1kHz stereo with EBU R128 (-14 LUFS, -1.0 dBTP)."""
        cmd = [
            "ffmpeg", "-y",
            "-i", in_file,
            "-af", "loudnorm=I=-14:TP=-1.0:LRA=11,aformat=sample_fmts=s16:sample_rates=44100:channel_layouts=stereo",
            "-b:a", "320k",
            out_file
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return res.returncode == 0 and os.path.exists(out_file)

    def assemble_nonstop_mix(
        self,
        tracks: List[Dict[str, Any]],
        crossfade_sec: float = 1.5,
        output_name: str = "master_mix.mp3"
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        """
        Stitches all tracks with smooth 'Wooosh' transition sound at every song cut.
        Generates master MP3 and exact YouTube tracklist.
        """
        if not tracks:
            raise ValueError("No tracks provided to assemble.")

        logger.info(f"Preparing {len(tracks)} tracks for seamless Nonstop assembly...")
        master_output_path = os.path.join(self.output_dir, output_name)
        tracklist_path = os.path.join(self.output_dir, "tracklist.txt")

        # Step 1: Normalize all tracks in parallel (6 workers)
        from concurrent.futures import ThreadPoolExecutor
        logger.info(f"🚀 Normalizing {len(tracks)} tracks concurrently (6 workers)...")

        def _process_norm(item):
            i, t = item
            src_audio = t.get("audio_path")
            if not src_audio or not os.path.exists(src_audio):
                return None
            norm_audio = os.path.join(self.temp_dir, f"norm_{i:02d}.mp3")
            if not os.path.exists(norm_audio):
                logger.info(f"[{i}/{len(tracks)}] Normalizing audio: {t['title'][:35]}...")
                ok = self.normalize_track(src_audio, norm_audio)
                if not ok:
                    norm_audio = src_audio
            dur = self._get_audio_duration(norm_audio)
            if dur > 10.0:
                t_copy = dict(t)
                t_copy["norm_path"] = norm_audio
                t_copy["exact_duration"] = dur
                return (i, t_copy)
            return None

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(_process_norm, enumerate(tracks, 1)))

        normalized_tracks = [res[1] for res in results if res is not None]

        if not normalized_tracks:
            raise RuntimeError("No tracks successfully normalized.")

        # Step 2: Build FFmpeg filter graph for sequential acrossfade and wooosh sound insertion
        logger.info(f"Constructing seamless crossfaded mix with 'Wooosh' transitions...")

        # Calculate exact chapter timestamps
        current_time = 0.0
        chapters = []
        tracklist_lines = []

        for idx, t in enumerate(normalized_tracks):
            ts = self._format_timestamp(current_time)
            title = t.get("title", f"Track {idx+1}")
            remixer = t.get("remixer", "")
            credit_line = f"{title} [{remixer}]" if remixer else title
            line = f"{ts} - {idx+1}. {credit_line}"
            tracklist_lines.append(line)
            chapters.append({
                "index": idx + 1,
                "timestamp": ts,
                "seconds": current_time,
                "title": title,
                "remixer": remixer
            })

            # Next track starts at (current_time + dur - crossfade_sec)
            dur = t["exact_duration"]
            current_time += (dur - crossfade_sec) if idx < len(normalized_tracks) - 1 else dur

        # Write tracklist.txt
        with open(tracklist_path, "w", encoding="utf-8") as f:
            f.write("\n".join(tracklist_lines))
        logger.info(f"Saved tracklist ({len(chapters)} songs) to {tracklist_path}")

        # Step 3: Run FFmpeg concatenation with acrossfade
        inputs = []
        for t in normalized_tracks:
            inputs.extend(["-i", t["norm_path"]])

        # Construct acrossfade chain
        filter_parts = []
        prev_label = "0:a"
        for i in range(1, len(normalized_tracks)):
            next_input = f"{i}:a"
            out_label = f"m{i}"
            filter_parts.append(
                f"[{prev_label}][{next_input}]acrossfade=d={crossfade_sec}:c1=tri:c2=tri[{out_label}]"
            )
            prev_label = out_label

        # Now overlay Wooosh sound at every transition point if wooosh.wav exists
        final_audio_label = prev_label
        has_wooosh = os.path.exists(self.wooosh_path)

        if has_wooosh and len(normalized_tracks) > 1:
            wooosh_input_idx = len(normalized_tracks)
            inputs.extend(["-i", self.wooosh_path])
            
            # Create delayed instances of wooosh at each boundary
            wooosh_labels = []
            for ch_idx, ch in enumerate(chapters[1:], 1):
                delay_ms = int(ch["seconds"] * 1000)
                w_lbl = f"w{ch_idx}"
                filter_parts.append(
                    f"[{wooosh_input_idx}:a]adelay={delay_ms}|{delay_ms},volume=0.9[{w_lbl}]"
                )
                wooosh_labels.append(w_lbl)

            # Mix base crossfaded mix with all wooosh instances
            mix_inputs = "".join([f"[{prev_label}]"] + [f"[{w}]" for w in wooosh_labels])
            filter_parts.append(
                f"{mix_inputs}amix=inputs={len(wooosh_labels) + 1}:normalize=0[final_mix]"
            )
            final_audio_label = "final_mix"

        filter_complex = ";".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{final_audio_label}]",
            "-b:a", "320k",
            "-ar", "44100",
            master_output_path
        ]

        logger.info(f"Rendering master nonstop audio mix (this takes ~1-3 minutes)...")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            logger.error(f"FFmpeg assembly failed: {res.stderr[-500:]}")
            # Fallback simple concat if acrossfade chain hit filter limits
            self._fallback_concat(normalized_tracks, master_output_path)

        total_dur = self._get_audio_duration(master_output_path)
        logger.info(f"Master mix ready! Duration: {self._format_timestamp(total_dur)} ({master_output_path})")

        return master_output_path, tracklist_path, chapters

    def _fallback_concat(self, tracks: List[Dict[str, Any]], out_path: str):
        """Fallback concatenation using concat demuxer if filter graph exceeds arguments."""
        list_file = os.path.join(self.temp_dir, "concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for t in tracks:
                f.write(f"file '{t['norm_path']}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c:a", "libmp3lame",
            "-b:a", "320k",
            out_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


if __name__ == "__main__":
    engine = DJAudioEngine()
    print("DJAudioEngine initialized and ready.")
