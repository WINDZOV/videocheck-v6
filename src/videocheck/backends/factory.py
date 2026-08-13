"""
Picks a DetectionBackend instance based on what preinstall.py detected
(hardware_report.json) and what's actually importable right now — the
report can go stale (e.g. the report says "openvino" but the package was
never installed), so we double-check with a real import before committing.
"""
import json
import os

from .base import DetectionBackend
from .cpu_backend import CpuBackend
from .cuda_backend import CudaBackend
from .openvino_backend import OpenVINOBackend

# Registry: adding a backend to this dict is the only wiring a new backend
# needs beyond writing the class itself.
_REGISTRY: dict[str, type[DetectionBackend]] = {
    "cuda": CudaBackend,
    "openvino": OpenVINOBackend,
    "cpu": CpuBackend,
}


def _read_profile(hardware_report_path: str) -> str | None:
    if not os.path.exists(hardware_report_path):
        return None
    try:
        with open(hardware_report_path) as f:
            return json.load(f).get("profile")
    except Exception:
        return None


def get_backend(hardware_report_path: str = "hardware_report.json") -> DetectionBackend:
    try:
        import torch
        if torch.cuda.is_available():
            return _REGISTRY["cuda"]()
    except ImportError:
        pass

    profile = _read_profile(hardware_report_path)
    if profile in _REGISTRY and profile != "cuda":
        if profile == "openvino":
            try:
                import openvino  # noqa: F401
                return _REGISTRY["openvino"]()
            except ImportError:
                print("[backend factory] openvino not installed — falling back to cpu.")
                print("  Tip: python preinstall.py --install")
        else:
            return _REGISTRY[profile]()

    return _REGISTRY["cpu"]()
