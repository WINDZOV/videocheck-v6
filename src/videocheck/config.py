"""All tunables live here, in one place, instead of scattered module globals."""
from dataclasses import dataclass, fields
import os


@dataclass
class Config:
    # Folders
    input_folder: str = "videosrc"
    output_empty: str = "empty_videos"
    output_clips: str = "clips"
    output_processed: str = "originals_processed"
    output_corrupted: str = "corrupted"

    # Runtime state files
    progress_file: str = "progress.json"
    hardware_report: str = "hardware_report.json"

    # Detection window
    start_skip: float = 10 * 60
    end_skip: float = 5 * 60
    frame_skip_sec: float = 2

    # Interval logic
    min_interval: float = 3
    merge_gap: float = 90
    pad_before: float = 5
    pad_after: float = 15

    # Model
    model_name: str = "yolov8n.pt"
    conf_threshold: float = 0.5
    target_class_id: int = 0        # COCO class 0 = "person"
    resize_width: int = 640
    resize_height: int = 360

    # ffmpeg
    ffmpeg_timeout: int = 300

    @classmethod
    def from_env(cls, prefix: str = "VIDEOCHECK_") -> "Config":
        """Override any field via VIDEOCHECK_<FIELD_NAME> env vars, e.g.
        VIDEOCHECK_MIN_INTERVAL=5 VIDEOCHECK_MODEL_NAME=yolov8s.pt python -m videocheck
        """
        overrides = {}
        for f in fields(cls):
            env_key = f"{prefix}{f.name.upper()}"
            if env_key not in os.environ:
                continue
            raw = os.environ[env_key]
            overrides[f.name] = f.type(raw) if f.type in (int, float) else raw
        return cls(**overrides)

    def ensure_output_dirs(self) -> None:
        for path in (self.output_empty, self.output_clips,
                     self.output_processed, self.output_corrupted):
            os.makedirs(path, exist_ok=True)
