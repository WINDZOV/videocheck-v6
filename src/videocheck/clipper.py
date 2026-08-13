"""Cuts detected intervals into clips via ffmpeg stream copy (no re-encode)."""
import os
import subprocess

from .config import Config
from .progress import ProgressTracker
from .video_io import CORRUPTION_MARKERS, VideoInspector


class ClipCutter:
    def __init__(self, inspector: VideoInspector, config: Config, progress: ProgressTracker):
        self.inspector = inspector
        self.config = config
        self.progress = progress

    def cut(self, video_path: str, intervals: list[tuple[float, float]], name: str) -> list[dict]:
        cfg = self.config
        base = os.path.splitext(os.path.basename(video_path))[0]
        clips: list[dict] = []

        video_duration = self.inspector.get_duration(video_path)
        if video_duration is None:
            import cv2
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            video_duration = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / fps
            cap.release()

        for i, (start, end) in enumerate(intervals):
            padded_start = max(0, start - cfg.pad_before)
            padded_end = min(video_duration, end + cfg.pad_after)

            ext = os.path.splitext(video_path)[1]
            fname = f"{base}_clip_{i:03d}{ext}"
            output = os.path.join(cfg.output_clips, fname)

            # -ss BEFORE -i => keyframe-accurate seek with -c copy (fast,
            # no re-encode). -avoid_negative_ts fixes PTS offsets after the
            # seek. -movflags +faststart puts moov atom at the front.
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(padded_start),
                "-i", video_path,
                "-t", str(padded_end - padded_start),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-movflags", "+faststart",
                output,
            ]

            try:
                result = subprocess.run(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    timeout=cfg.ffmpeg_timeout,
                )
            except subprocess.TimeoutExpired:
                print(f"  ⏱  clip {i} timed out after {cfg.ffmpeg_timeout}s — skipping")
                continue

            stderr = result.stderr
            corruption = next((m.decode() for m in CORRUPTION_MARKERS if m in stderr), None)
            if corruption:
                raise RuntimeError(f"Corrupted file detected during cut: {corruption}")

            pct = int((i + 1) / len(intervals) * 100)
            self.progress.update(name, "cutting", pct)

            if result.returncode == 0:
                duration = round(padded_end - padded_start, 1)
                clips.append({
                    "file": fname, "start": round(padded_start, 1),
                    "end": round(padded_end, 1), "duration": duration,
                })
                print(f"  ✂  {fname}  {padded_start:.1f}s–{padded_end:.1f}s  ({duration}s)")
            else:
                print(f"  ⚠  clip {i} failed: {stderr.decode(errors='replace')[-300:]}")

        return clips
