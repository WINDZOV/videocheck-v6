"""
Progress reporting behind an interface, so the pipeline never talks to a
file directly. Swap JSONFileProgressTracker for anything else (a websocket
push, a DB row, stdout only, a no-op for tests) without touching pipeline.py.
"""
from abc import ABC, abstractmethod
import json
import os
import time


class ProgressTracker(ABC):
    @abstractmethod
    def init(self, files: list[str]) -> None: ...

    @abstractmethod
    def update(self, name: str, stage: str, pct: int) -> None: ...

    @abstractmethod
    def finish(self, name: str, status: str, clips: list | None = None,
               error: str | None = None) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class NullProgressTracker(ProgressTracker):
    """No-op — for tests, headless batch runs, or scripting."""

    def init(self, files: list[str]) -> None:
        pass

    def update(self, name: str, stage: str, pct: int) -> None:
        pass

    def finish(self, name: str, status: str, clips=None, error=None) -> None:
        pass

    def close(self) -> None:
        pass


class JSONFileProgressTracker(ProgressTracker):
    """Writes progress.json in real time — dashboard.html polls this file."""

    def __init__(self, path: str = "progress.json"):
        self.path = path
        self._state: dict = {}

    def init(self, files: list[str]) -> None:
        self._state = {
            "started_at": time.time(),
            "updated_at": time.time(),
            "finished_at": None,
            "total": len(files),
            "done": 0,
            "clips_found": 0,
            "empty_count": 0,
            "error_count": 0,
            "corrupted_count": 0,
            "current_file": None,
            "current_stage": None,
            "current_pct": 0,
            "videos": {
                f: {"status": "pending", "stage": None, "pct": 0, "clips": [], "error": None}
                for f in files
            },
        }
        self._save()

    def _save(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self._state, f, indent=2)

    def update(self, name: str, stage: str, pct: int) -> None:
        self._state["videos"][name].update(status="running", stage=stage, pct=pct)
        self._state["current_file"] = name
        self._state["current_stage"] = stage
        self._state["current_pct"] = pct
        self._state["updated_at"] = time.time()
        self._save()

    def finish(self, name: str, status: str, clips: list | None = None,
               error: str | None = None) -> None:
        self._state["videos"][name].update(
            status=status, stage=None, pct=100, clips=clips or [], error=error
        )
        self._state["done"] += 1
        self._state["current_file"] = None
        self._state["current_stage"] = None
        self._state["current_pct"] = 0
        if clips:
            self._state["clips_found"] += len(clips)
        if status == "empty":
            self._state["empty_count"] += 1
        elif status == "error":
            self._state["error_count"] += 1
        elif status == "corrupted":
            self._state["corrupted_count"] += 1
        self._state["updated_at"] = time.time()
        self._save()

    def close(self) -> None:
        self._state["finished_at"] = time.time()
        self._state["updated_at"] = time.time()
        self._save()
        time.sleep(5)
        if os.path.exists(self.path):
            os.remove(self.path)
