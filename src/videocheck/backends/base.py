"""
The interface every detection backend must satisfy. Anything that can load
a model and return detections for a frame can be plugged in here — the rest
of the codebase (detector.py, pipeline.py) only ever talks to this interface,
never to torch/ultralytics/openvino directly.

Adding a new backend (Apple MPS, TensorRT, a remote inference API, a mock for
tests...) means writing one small class here and registering it in
factory.py — nothing else in the project changes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Detection:
    class_id: int
    confidence: float


class DetectionBackend(ABC):
    """One backend = one way of turning a frame into a list of Detections."""

    name: str = "base"

    @abstractmethod
    def load(self, model_name: str) -> None:
        """Load/prepare the model. Called once before any infer() calls."""
        raise NotImplementedError

    @abstractmethod
    def infer(self, frame) -> list[Detection]:
        """Run detection on a single BGR frame (numpy array)."""
        raise NotImplementedError
