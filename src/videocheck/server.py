"""
Local web UI: drag-and-drop videos in, click Start, watch live progress,
download the resulting clips — all from the browser instead of manually
shuffling files into videosrc/ and reading raw JSON.

This is deliberately just a thin HTTP front door: it talks to the same
VideoPipeline / Config used by the headless CLI (cli.py --no-serve mode).
No pipeline logic lives here — only routing, file upload/download, and
kicking off pipeline.run_folder() in a background thread.
"""
import json
import os
import threading
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file

from .config import Config
from .pipeline import VideoPipeline

# dashboard.html lives at the project root when running from source, or
# packaged alongside this module when installed — try both.
_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "dashboard.html",
    Path(__file__).resolve().parent / "dashboard.html",
]
DASHBOARD_HTML = next((p for p in _CANDIDATES if p.exists()), _CANDIDATES[0])

ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mpeg", ".mpg", ".mov", ".avi"}


class _RunState:
    """Guards against starting a second run while one is already in progress."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False


def create_app(pipeline: VideoPipeline, config: Config) -> Flask:
    app = Flask(__name__)
    state = _RunState()

    @app.get("/")
    def index():
        if not DASHBOARD_HTML.exists():
            return "dashboard.html not found next to the project.", 500
        return DASHBOARD_HTML.read_text(encoding="utf-8")

    @app.get("/api/videos")
    def list_videos():
        os.makedirs(config.input_folder, exist_ok=True)
        files = sorted(
            f for f in os.listdir(config.input_folder)
            if os.path.isfile(os.path.join(config.input_folder, f))
        )
        return jsonify(files)

    @app.post("/api/upload")
    def upload():
        uploaded = request.files.getlist("video")
        if not uploaded:
            return jsonify({"error": "no files received"}), 400

        os.makedirs(config.input_folder, exist_ok=True)
        saved, skipped = [], []
        for f in uploaded:
            name = os.path.basename(f.filename or "")
            ext = os.path.splitext(name)[1].lower()
            if not name or ext not in ALLOWED_EXTENSIONS:
                skipped.append(name)
                continue
            f.save(os.path.join(config.input_folder, name))
            saved.append(name)
        return jsonify({"saved": saved, "skipped": skipped})

    @app.post("/api/start")
    def start():
        with state.lock:
            if state.running:
                return jsonify({"error": "a run is already in progress"}), 409
            state.running = True

        def _run():
            try:
                pipeline.run_folder()
            finally:
                with state.lock:
                    state.running = False

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"started": True})

    @app.get("/api/progress")
    def progress():
        if not os.path.exists(config.progress_file):
            return jsonify({"running": state.running})
        with open(config.progress_file) as fh:
            data = json.load(fh)
        data["running"] = state.running
        return jsonify(data)

    @app.get("/api/clips")
    def clips():
        folder = config.output_clips
        if not os.path.isdir(folder):
            return jsonify([])
        files = sorted(f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)))
        return jsonify([
            {"name": f, "size": os.path.getsize(os.path.join(folder, f))}
            for f in files
        ])

    @app.get("/api/download/<path:filename>")
    def download(filename):
        folder = os.path.abspath(config.output_clips)
        target = os.path.abspath(os.path.join(folder, filename))
        # Prevent path traversal outside the clips folder.
        if not target.startswith(folder + os.sep) or not os.path.isfile(target):
            abort(404)
        return send_file(target, as_attachment=True)

    return app


def run_server(pipeline: VideoPipeline, config: Config,
                host: str = "127.0.0.1", port: int = 8765,
                open_browser: bool = True) -> None:
    app = create_app(pipeline, config)
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"VideoCheck web UI running at {url}  (Ctrl+C to stop)")
    app.run(host=host, port=port, debug=False)
