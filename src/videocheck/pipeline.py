"""
Orchestration only — no ffmpeg calls, no torch, no file-format knowledge
lives here. It wires together an inspector, a detector, a cutter, and a
progress tracker, all received as dependencies, so this class is trivial to
unit-test with fakes/mocks for each collaborator.
"""
import os

from .clipper import ClipCutter
from .config import Config
from .detector import PersonDetector
from .progress import ProgressTracker
from .video_io import VideoInspector


class VideoPipeline:
    def __init__(self, config: Config, inspector: VideoInspector,
                 detector: PersonDetector, cutter: ClipCutter, progress: ProgressTracker):
        self.config = config
        self.inspector = inspector
        self.detector = detector
        self.cutter = cutter
        self.progress = progress

    def process_one(self, path: str) -> None:
        cfg = self.config
        name = os.path.basename(path)
        print(f"\n▶  {name}")
        self.progress.update(name, "starting", 0)
        self.progress.update(name, "checking", 0)

        duration = self.inspector.get_duration(path)
        err = self.inspector.is_corrupted(path, duration=duration)
        if err:
            dest = os.path.join(cfg.output_corrupted, name)
            os.rename(path, dest)
            self.progress.finish(name, "corrupted", error=err)
            print(f"   → Corrupted — moved to {cfg.output_corrupted}/")
            return

        intervals = self.detector.find_intervals(path, name)

        if not intervals:
            dest = os.path.join(cfg.output_empty, name)
            os.rename(path, dest)
            self.progress.finish(name, "empty")
            print("   → No people found")
            return

        clips = self.cutter.cut(path, intervals, name)
        dest = os.path.join(cfg.output_processed, name)
        os.rename(path, dest)
        self.progress.finish(name, "done", clips=clips)
        print(f"   → {len(clips)} clip(s) saved  |  original → {cfg.output_processed}/")

    def run_folder(self) -> None:
        cfg = self.config
        cfg.ensure_output_dirs()

        files = sorted(
            f for f in os.listdir(cfg.input_folder)
            if os.path.isfile(os.path.join(cfg.input_folder, f))
        )
        if not files:
            print(f"No files found in '{cfg.input_folder}/'.")
            return

        self.progress.init(files)
        print(f"Processing {len(files)} file(s). Open dashboard.html to track progress.\n")

        for f in files:
            path = os.path.join(cfg.input_folder, f)
            try:
                self.process_one(path)
            except RuntimeError as exc:
                if os.path.exists(path):
                    dest = os.path.join(cfg.output_corrupted, f)
                    os.rename(path, dest)
                    print(f"  ☠  {f} moved to {cfg.output_corrupted}/")
                self.progress.finish(f, "corrupted", error=str(exc))
            except Exception as exc:
                self.progress.finish(f, "error", error=str(exc))
                print(f"  ✗  {f}: {exc}")

        self.progress.close()
        print("\n✅  Done.")
