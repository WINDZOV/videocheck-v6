"""
Everything that inspects a video file without decoding frames for detection:
duration lookup and corruption scanning. Kept separate from PersonDetector
so it can be reused (or unit-tested) independently — e.g. a future "just
validate this folder" command wouldn't need to import torch/ultralytics at all.
"""
import os
import subprocess

CORRUPTION_MARKERS = [
    b"indicated by an EBML",
    b"invalid as first byte of an EBML",
    b"Invalid data found when processing input",
    b"moov atom not found",
    b"could not find codec parameters",
    b"error while decoding MB",
    b"broken bitstream",
]


class VideoInspector:
    def __init__(self, ffmpeg_timeout: int = 300):
        self.ffmpeg_timeout = ffmpeg_timeout

    def get_duration(self, video_path: str) -> float | None:
        """
        ffprobe is far more reliable than OpenCV's frame count for MP4/H.264,
        where the moov atom can sit at the end of the file.
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            return float(result.stdout.strip())
        except Exception:
            return None

    def is_corrupted(self, video_path: str, duration: float | None = None) -> str | None:
        """
        Fast full-file scan using `ffmpeg -c copy` (no decoding) — reads every
        packet without decoding, catching EBML/container errors anywhere in
        the file quickly. Timeout scales with duration so long videos aren't
        falsely flagged.
        """
        if duration and duration > 0:
            timeout = max(self.ffmpeg_timeout, int(duration * 0.5))
        else:
            file_size = os.path.getsize(video_path)
            timeout = max(self.ffmpeg_timeout, int(file_size / (10 * 1024 * 1024)))

        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-v", "error",
                    "-err_detect", "ignore_err",
                    "-i", video_path,
                    "-c", "copy",
                    "-f", "null", "-",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
            stderr = result.stderr
        except subprocess.TimeoutExpired:
            return "Corruption check timed out — file likely corrupted or truncated"

        for marker in CORRUPTION_MARKERS:
            if marker in stderr:
                return stderr.decode(errors="replace").split("\n")[0]
        return None
