from .base import DetectionBackend, Detection


class CpuBackend(DetectionBackend):
    """Last-resort fallback: plain ultralytics YOLO on CPU. Always works,
    slowest option — used when there's no GPU and OpenVINO isn't installed."""

    name = "cpu"

    def load(self, model_name: str) -> None:
        from ultralytics import YOLO

        self._model = YOLO(model_name)
        self._model.to("cpu")
        print("[backend:cpu] No GPU/OpenVINO available — using plain CPU (slow).")

    def infer(self, frame) -> list[Detection]:
        results = self._model(frame, verbose=False, max_det=10)
        boxes = results[0].boxes
        return [Detection(int(b.cls[0]), float(b.conf[0])) for b in boxes]
