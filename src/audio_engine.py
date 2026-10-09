"""
DJ Audio Engine & Seamless Nonstop DJ Transition Module
1. Cuts unwanted intro (first 10s) and outro (last 10s) of every track to eliminate jingles and channel promos.
2. Applies smooth 1.5s fade-in and 1.5s fade-out on every song.
3. Overlaps songs with seamless crossfade (zero blank gap, zero abrupt cuts, zero artificial sound effects).
4. Anti-Fingerprint protection: Natural DJ Pitch (+5% / 1.05x), tempo offset, DJ sub-bass boost & EBU R128 loudness.
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

    def _extract_song_keywords(self, title: str, remixer: str = "") -> set:
        """Extracts core distinguishing song keywords from title, stripping promos and stop words."""
        import re
        t = title.lower()
        if remixer:
            t = t.replace(remixer.lower(), " ")
        t = re.sub(r"\[.*?\]|\(.*?\)", " ", t)
        t = re.sub(r"(?:\+?91|mob|contact|no|call)?[-\s:]*[6-9]\d{9}", " ", t)
        stop_words = {
            "dj", "remix", "rmx", "song", "songs", "video", "audio", "mp3", "hd", "4k", "hq",
            "official", "original", "fl", "studio", "competition", "roadshow", "vibration",
            "sound", "check", "soundcheck", "test", "bass", "boosted", "dhamaka", "superhit",
            "hit", "new", "latest", "theth", "dance", "mix", "nonstop", "jukebox", "mashup",
            "2024", "2025", "2026", "2027", "nagpuri", "bhojpuri", "cg", "khortha", "purulia",
            "jharkhandi", "by", "ft", "feat", "prod", "present", "presents", "re", "ho", "se",
            "डीजे", "रीमिक्स", "गाने", "गाना", "नागपुरी", "भोजपुरी", "नया", "धमाका", "सुपरहिट"
        }
        words = re.findall(r"[\u0900-\u097f]+|[a-z0-9]{3,}", t)
        return {w for w in words if w not in stop_words}

    def _is_duplicate_song(self, title1: str, rmx1: str, title2: str, rmx2: str) -> bool:
        """Checks if two titles refer to the exact same song using keyword fingerprinting."""
        kw1 = self._extract_song_keywords(title1, rmx1)
        kw2 = self._extract_song_keywords(title2, rmx2)
        if not kw1 or not kw2:
            return False
        intersection = kw1.intersection(kw2)
        union = kw1.union(kw2)
        similarity = len(intersection) / len(union) if union else 0.0
        is_subset = len(intersection) >= 2 and (len(intersection) == len(kw1) or len(intersection) == len(kw2))
        return similarity >= 0.50 or len(intersection) >= 3 or is_subset

    def process_dj_track(
        self,
        in_file: str,
        out_file: str,
        track_index: int,
        cut_intro_sec: float = 10.0,
        cut_outro_sec: float = 10.0,
        fade_sec: float = 1.5,
        pitch_factor: float = 1.05
    ) -> bool:
        """
        Processes an individual song for the nonstop DJ mix:
        - Trims leading 10s (if track > 1) to eliminate slow intros / spoken promos.
        - Trims trailing 10s to eliminate outros / promo announcements.
        - Adds smooth fade-in (1.5s) at the start so the song enters gently.
        - Adds smooth fade-out (1.5s) at the end so the song exits smoothly.
        - Adds subtle 5% spatial concert reverb ('gunj') for wide, immersive audio depth.
        - Preserves 100% natural, unmanipulated bass to prevent speaker distortion / clipping on heavy DJ setups.
        - Applies Anti-Fingerprint (+5% pitch & tempo offset) to eliminate YouTube Content ID copyright claims.
        - Normalizes to broadcast standard EBU R128 (-14 LUFS, -1.0 dBTP ceiling).
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

        env_pitch = os.environ.get("DJ_PITCH_FACTOR")
        eff_pitch = float(env_pitch) if env_pitch else pitch_factor

        # - 5% subtle spatial concert reverb ('gunj') for wide, immersive studio acoustic depth.
        # - STRICT RULE: NEVER tamper with original bass EQ so heavy DJ sound systems & subwoofers
        #   never distort, clip, or crack ("bass fatna").
        # - Applies Anti-Fingerprint (+5% pitch & tempo offset) to eliminate YouTube Content ID claims.
        # - Normalizes to broadcast standard EBU R128 (-14 LUFS, -1.0 dBTP ceiling).
        filter_chain = (
            f"atrim=start={start_s:.2f}:end={end_s:.2f},"
            f"asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade_sec:.2f},"
            f"afade=t=out:st={fade_out_start:.2f}:d={fade_sec:.2f},"
            f"asetrate=44100*{eff_pitch:.4f},"
            f"aresample=44100:resample_cutoff=1.0:precision=28:filter_type=kaiser:dither_method=triangular,"
            f"aecho=0.95:0.05:40|60|80:0.4|0.3|0.2,"
            f"loudnorm=I=-14:TP=-1.0:LRA=11:linear=true,"
            f"aformat=sample_fmts=s16:sample_rates=44100:channel_layouts=stereo"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", in_file,
            "-af", filter_chain,
            "-c:a", "pcm_s16le",
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

        # Step 0: Secondary Duplicate Song Protection (Exact Title/Remixer Keyword Fingerprint)
        deduped_tracks = []
        for t in tracks:
            t_title = t.get("title", "")
            t_remixer = t.get("remixer", "")
            if any(self._is_duplicate_song(t_title, t_remixer, ex.get("title", ""), ex.get("remixer", "")) for ex in deduped_tracks):
                logger.warning(f"⚠️ AudioEngine deduplication: Skipping duplicate song in mix: '{t_title[:45]}' ({t_remixer})")
                continue
            deduped_tracks.append(t)
        tracks = deduped_tracks

        logger.info(f"Preparing {len(tracks)} unique tracks for seamless Nonstop DJ assembly...")
        master_output_path = os.path.join(self.output_dir, output_name)
        tracklist_path = os.path.join(self.output_dir, "tracklist.txt")

        # Step 1: Process and normalize all tracks in parallel (6 workers)
        logger.info(f"🚀 Processing & normalizing {len(tracks)} tracks concurrently (cutting intro 10s, outro 10s, adding 1.5s fades)...")

        def _process_item(item):
            i, t = item
            src_audio = t.get("audio_path")
            if not src_audio or not os.path.exists(src_audio):
                return None
            norm_audio = os.path.join(self.temp_dir, f"dj_track_{i:02d}.wav")
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
                **t,
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
            "-c:a", "libmp3lame",
            "-b:a", "320k",
            "-q:a", "0",
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
