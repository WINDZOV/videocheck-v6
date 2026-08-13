"""VideoCheck — local, hardware-adaptive person-detection clip extractor.

Architecture (each piece is independently swappable/testable):

    backends/   DetectionBackend interface + Cuda/OpenVINO/Cpu implementations
                and a factory that picks one based on hardware_report.json.
    video_io    VideoInspector — duration + corruption checks (ffprobe/ffmpeg).
    detector    PersonDetector — samples frames, calls a backend, returns
                time intervals where the target class was seen.
    clipper     ClipCutter — cuts intervals into clips via ffmpeg stream copy.
    progress    ProgressTracker interface + JSON-file and no-op implementations.
    pipeline    VideoPipeline — wires the above together and walks a folder.
    config      Config dataclass — every tunable in one place, overridable via
                env vars or CLI flags (see cli.py).
"""

__version__ = "0.2.0"
