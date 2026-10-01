"""
DJ Audio Engine & Seamless Nonstop DJ Transition Module
1. Cuts unwanted intro (first 10s) and outro (last 10s) of every track to eliminate jingles and channel promos.
2. Applies smooth 1.5s fade-in and 1.5s fade-out on every song.
3. Overlaps songs with seamless crossfade (zero blank gap, zero abrupt cuts, zero artificial sound effects).
4. Anti-Fingerprint protection: Micro-pitch (+2.5%), tempo offset, DJ sub-bass boost & EBU R128 loudness.
5. Produces master continuous 320 kbps MP3 and clickable YouTube tracklist chapters.
"""

import os
import sys
import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AudioEngine")


class DJAudioEngine:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.output_dir = os.path.join(self.base_dir, "output")
        self.temp_dir = os.path.join(self.output_dir, "temp_audio")
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_audio_duration(self, file_path: str) -> float:
        """Gets exact audio duration in seconds using ffprobe."""
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
            logger.warning(f"ffprobe duration check failed for {file_path}: {e}")
            return 0.0

    def _format_timestamp(self, seconds: float) -> str:
        """Formats seconds into HH:MM:SS format for YouTube chapter tracklist."""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

    def process_dj_track(
        self,
        in_file: str,
        out_file: str,
        track_index: int,
        cut_intro_sec: float = 10.0,
        cut_outro_sec: float = 10.0,
        fade_sec: float = 1.5
    ) -> bool:
        """
        Processes an individual song for the nonstop DJ mix:
        - Trims leading 10s (if track > 1) to eliminate slow intros / spoken promos.
        - Trims trailing 10s to eliminate outros / promo announcements.
        - Adds smooth fade-in (1.5s) at the start so the song enters gently.
        - Adds smooth fade-out (1.5s) at the end so the song exits smoothly.
        - Applies Anti-Fingerprint (+2.5% pitch & tempo offset, +2.5 dB sub-bass boost around 60Hz, +1.5 dB treble).
        - Normalizes to broadcast standard EBU R128 (-14 LUFS, -1.0 dBTP).
        """
        raw_dur = self._get_audio_duration(in_file)
        if raw_dur < 25.0:
            logger.warning(f"Track too short ({raw_dur:.1f}s), skipping trim: {in_file}")
            start_s = 0.0
            end_s = raw_dur
        else:
            # Track 1 starts from 0s for a natural mix opener; subsequent tracks skip intro 10s
            start_s = cut_intro_sec if track_index > 1 else 0.0
            end_s = max(start_s + 15.0, raw_dur - cut_outro_sec)

        trimmed_len = end_s - start_s
        fade_out_start = max(0.0, trimmed_len - fade_sec)

        filter_chain = (
            f"atrim=start={start_s:.2f}:end={end_s:.2f},"
            f"asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade_sec:.2f},"
            f"afade=t=out:st={fade_out_start:.2f}:d={fade_sec:.2f},"
            f"asetrate=44100*1.025,"
            f"aresample=44100,"
            f"equalizer=f=60:width_type=h:width=50:g=2.5,"
            f"treble=g=1.5,"
            f"loudnorm=I=-14:TP=-1.0:LRA=11,"
            f"aformat=sample_fmts=s16:sample_rates=44100:channel_layouts=stereo"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", in_file,
            "-af", filter_chain,
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
        Assembles all tracks into a continuous, seamless nonstop DJ mix:
        - 10s intro trimmed, 10s outro trimmed.
        - Smooth 1.5s crossfade between every track (zero blank gap, zero abrupt cuts, NO wooosh).
        - Generates exact clickable YouTube chapters for the description.
        """
        if not tracks:
            raise ValueError("No tracks provided to assemble.")

        logger.info(f"Preparing {len(tracks)} tracks for seamless Nonstop DJ assembly...")
        master_output_path = os.path.join(self.output_dir, output_name)
        tracklist_path = os.path.join(self.output_dir, "tracklist.txt")

        # Step 1: Process and normalize all tracks in parallel (6 workers)
        logger.info(f"🚀 Processing & normalizing {len(tracks)} tracks concurrently (cutting intro 10s, outro 10s, adding 1.5s fades)...")

        def _process_item(item):
            i, t = item
            src_audio = t.get("audio_path")
            if not src_audio or not os.path.exists(src_audio):
                return None
            norm_audio = os.path.join(self.temp_dir, f"dj_track_{i:02d}.mp3")
            if not os.path.exists(norm_audio):
                logger.info(f"[{i}/{len(tracks)}] Processing DJ track: {t['title'][:35]}...")
                ok = self.process_dj_track(
                    in_file=src_audio,
                    out_file=norm_audio,
                    track_index=i,
                    cut_intro_sec=10.0,
                    cut_outro_sec=10.0,
                    fade_sec=crossfade_sec
                )
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
            results = list(executor.map(_process_item, enumerate(tracks, 1)))

        processed_tracks = [res[1] for res in results if res is not None]

        if not processed_tracks:
            raise RuntimeError("No tracks successfully processed.")

        logger.info(f"✅ {len(processed_tracks)} tracks processed with Anti-Fingerprint and DJ fades.")

        # Step 2: Build exact chapter timestamps
        current_time = 0.0
        chapters = []
        tracklist_lines = []

        for idx, t in enumerate(processed_tracks):
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
            current_time += (dur - crossfade_sec) if idx < len(processed_tracks) - 1 else dur

        with open(tracklist_path, "w", encoding="utf-8") as f:
            f.write("\n".join(tracklist_lines))
        logger.info(f"Saved tracklist ({len(chapters)} songs) to {tracklist_path}")

        # Step 3: Run FFmpeg acrossfade concatenation
        inputs = []
        for t in processed_tracks:
            inputs.extend(["-i", t["norm_path"]])

        filter_parts = []
        prev_label = "0:a"
        for i in range(1, len(processed_tracks)):
            next_input = f"{i}:a"
            out_label = f"m{i}"
            # Smooth quarter-sine crossfade between outgoing fade-out and incoming fade-in
            filter_parts.append(
                f"[{prev_label}][{next_input}]acrossfade=d={crossfade_sec:.2f}:c1=qsin:c2=qsin[{out_label}]"
            )
            prev_label = out_label

        filter_complex = ";".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{prev_label}]",
            "-b:a", "320k",
            "-ar", "44100",
            master_output_path
        ]

        logger.info(f"Rendering seamless nonstop DJ mix (smooth transitions, zero gaps)...")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            logger.error(f"FFmpeg acrossfade failed: {res.stderr[-500:]}")
            self._fallback_concat(processed_tracks, master_output_path)

        total_dur = self._get_audio_duration(master_output_path)
        logger.info(f"🎉 Master Nonstop DJ Mix Ready! Total Duration: {self._format_timestamp(total_dur)} ({master_output_path})")

        return master_output_path, tracklist_path, chapters

    def _fallback_concat(self, tracks: List[Dict[str, Any]], out_path: str):
        """Fallback concatenation using concat demuxer if filter graph exceeds limits."""
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
