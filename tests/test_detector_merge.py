from videocheck.backends.base import DetectionBackend, Detection
from videocheck.config import Config
from videocheck.detector import PersonDetector
from videocheck.progress import NullProgressTracker


class FakeBackend(DetectionBackend):
    """A backend that never touches torch/ultralytics — pure test double."""
    name = "fake"

    def load(self, model_name: str) -> None:
        pass

    def infer(self, frame):
	# never used directly in these tests
        return []  


def _detector(merge_gap: float = 90) -> PersonDetector:
    cfg = Config(merge_gap=merge_gap)
    return PersonDetector(FakeBackend(), inspector=None, config=cfg, progress=NullProgressTracker())


def test_merge_joins_close_intervals():
    d = _detector(merge_gap=10)
    merged = d._merge([(0, 5), (8, 12), (30, 40)])
    assert merged == [(0, 12), (30, 40)]


def test_merge_keeps_far_intervals_separate():
    d = _detector(merge_gap=5)
    merged = d._merge([(0, 5), (20, 25)])
    assert merged == [(0, 5), (20, 25)]


def test_merge_empty_input():
    d = _detector()
    assert d._merge([]) == []
