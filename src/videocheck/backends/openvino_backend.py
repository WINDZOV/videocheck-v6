import os

from .base import DetectionBackend, Detection


class OpenVINOBackend(DetectionBackend):
    """
    Intel/AMD CPU inference via OpenVINO IR. Meaningfully faster than plain
    PyTorch-CPU thanks to graph fusion/quantization, with no GPU required.
    """

    name = "openvino"

    def load(self, model_name: str) -> None:
        from ultralytics import YOLO

        ov_dir = model_name.replace(".pt", "_openvino_model")
        if not os.path.isdir(ov_dir):
            print("[backend:openvino] Exporting model to OpenVINO IR (one-time)...")
            YOLO(model_name).export(format="openvino")
        self._model = YOLO(ov_dir)
        print("[backend:openvino] Using OpenVINO (CPU-optimized) backend.")

    def infer(self, frame) -> list[Detection]:
        results = self._model(frame, verbose=False, max_det=10)
        boxes = results[0].boxes
        return [Detection(int(b.cls[0]), float(b.conf[0])) for b in boxes]
