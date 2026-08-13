"""
Finds the time intervals in a video where the target class (default:
"person") appears. Talks only to the DetectionBackend interface — it has no
idea whether that's CUDA, OpenVINO, or CPU underneath.
"""
import cv2

from .backends.base import DetectionBackend
from .config import Config
from .progress import ProgressTracker
from .video_io import VideoInspector


class PersonDetector:
    def __init__(self, backend: DetectionBackend, inspector: VideoInspector,
                 config: Config, progress: ProgressTracker):
        self.backend = backend
        self.inspector = inspector
        self.config = config
        self.progress = progress

    def find_intervals(self, video_path: str, name: str) -> list[tuple[float, float]]:
        cfg = self.config
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        duration = self.inspector.get_duration(video_path)
        if duration is None:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps

        start_sec = cfg.start_skip
        end_sec = max(start_sec, duration - cfg.end_skip)

        # A SINGLE seek to the start is fine — seeking is only expensive when
        # done repeatedly. For inter-frame-coded video (H.264/H.265, typical
        # for security/dashcam footage), seeking to an arbitrary timestamp
        # forces the decoder back to the nearest keyframe and forward-decodes
        # from there every time. Doing that once per sample (the old
        # approach) turns a sequential decode into thousands of tiny
        # rewind-and-replay operations — that's almost always the real
        # bottleneck, not the GPU.
        #
        # Instead: seek once, then walk forward sequentially. cap.grab()
        # advances one frame without the color-conversion/copy cost of
        # cap.read(), so skipped frames are cheap; only sampled frames pay
        # the full read+resize+infer cost.
        cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)

        frames_per_sample = max(1, round(fps * cfg.frame_skip_sec))
        total_samples = max(1, int((end_sec - start_sec) / cfg.frame_skip_sec))

        intervals: list[tuple[float, float]] = []
        current: list[float] | None = None
        last_pct = -1
        sample_idx = 0
        frame_counter = 0

        self.progress.update(name, "detecting", 0)

        while True:
            current_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if current_sec >= end_sec:
                break

            take_sample = frame_counter % frames_per_sample == 0
            if take_sample:
                ret, frame = cap.read()
            else:
                ret = cap.grab()
                frame = None
            if not ret:
                break
            frame_counter += 1

            if not take_sample:
                continue

            t_used = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            frame = cv2.resize(frame, (cfg.resize_width, cfg.resize_height))
            detections = self.backend.infer(frame)

            target_found = any(
                d.class_id == cfg.target_class_id and d.confidence >= cfg.conf_threshold
                for d in detections
            )

            if target_found:
                current = [t_used, t_used] if current is None else [current[0], t_used]
            elif current is not None:
                if current[1] - current[0] >= cfg.min_interval:
                    intervals.append(tuple(current))
                current = None

            sample_idx += 1
            pct = min(99, int(sample_idx / total_samples * 100))
            if pct != last_pct:
                self.progress.update(name, "detecting", pct)
                last_pct = pct

        if current is not None and current[1] - current[0] >= cfg.min_interval:
            intervals.append(tuple(current))

        cap.release()
        return self._merge(intervals)

    def _merge(self, intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
        merged: list[tuple[float, float]] = []
        for iv in intervals:
            if not merged or iv[0] - merged[-1][1] > self.config.merge_gap:
                merged.append(iv)
            else:
                merged[-1] = (merged[-1][0], iv[1])
        return merged
