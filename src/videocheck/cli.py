"""
Entry point. This is the one place in the codebase that constructs concrete
classes — everywhere else only sees interfaces (DetectionBackend,
ProgressTracker). That's what makes swapping pieces later (a new backend, a
different progress sink, batch mode without a dashboard) a one-line change
here instead of a rewrite.
"""
import argparse

from .backends import get_backend
from .clipper import ClipCutter
from .config import Config
from .detector import PersonDetector
from .pipeline import VideoPipeline
from .progress import JSONFileProgressTracker, NullProgressTracker
from .video_io import VideoInspector


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="videocheck", description=__doc__)
    p.add_argument("--input", dest="input_folder", help="Folder to scan (default: videosrc)")
    p.add_argument("--no-dashboard", action="store_true",
                    help="Skip writing progress.json (headless/batch mode)")
    p.add_argument("--model", dest="model_name", help="YOLO model file (default: yolov8n.pt)")
    p.add_argument("--conf", dest="conf_threshold", type=float,
                    help="Detection confidence threshold 0-1 (default: 0.5)")
    p.add_argument("--serve", action="store_true",
                    help="Launch VideoCheck as an app (upload videos, start runs, "
                         "download clips) instead of processing whatever is already "
                         "in the input folder and exiting. Opens as a native desktop "
                         "window by default")
    p.add_argument("--browser", action="store_true",
                    help="With --serve: open in a regular browser tab instead of a "
                         "native desktop window")
    p.add_argument("--port", type=int, default=8765, help="Web UI port (default: 8765)")
    p.add_argument("--no-browser", action="store_true",
                    help="With --serve --browser: don't auto-open a browser tab")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    config = Config.from_env()
    if args.input_folder:
        config.input_folder = args.input_folder
    if args.model_name:
        config.model_name = args.model_name
    if args.conf_threshold is not None:
        config.conf_threshold = args.conf_threshold

    progress = NullProgressTracker() if args.no_dashboard else JSONFileProgressTracker(config.progress_file)

    backend = get_backend(config.hardware_report)
    backend.load(config.model_name)

    inspector = VideoInspector(ffmpeg_timeout=config.ffmpeg_timeout)
    detector = PersonDetector(backend, inspector, config, progress)
    cutter = ClipCutter(inspector, config, progress)
    pipeline = VideoPipeline(config, inspector, detector, cutter, progress)

    if args.serve and args.browser:
        from .server import run_server
        run_server(pipeline, config, port=args.port, open_browser=not args.no_browser)
    elif args.serve:
        from .desktop import run_desktop
        run_desktop(pipeline, config, port=args.port)
    else:
        pipeline.run_folder()


if __name__ == "__main__":
    main()
