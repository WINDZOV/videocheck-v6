from .base import DetectionBackend, Detection


class CudaBackend(DetectionBackend):
    """NVIDIA GPU inference via plain ultralytics YOLO on CUDA."""

    name = "cuda"

    def load(self, model_name: str) -> None:
        from ultralytics import YOLO
        import torch

        self._model = YOLO(model_name)
        self._model.to("cuda")
        print(f"[backend:cuda] Using GPU: {torch.cuda.get_device_name(0)}")

    def infer(self, frame) -> list[Detection]:
        results = self._model(frame, verbose=False, max_det=10)
        boxes = results[0].boxes
        return [Detection(int(b.cls[0]), float(b.conf[0])) for b in boxes]
