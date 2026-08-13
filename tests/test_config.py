import os

from videocheck.config import Config


def test_defaults():
    cfg = Config()
    assert cfg.input_folder == "videosrc"
    assert cfg.min_interval == 3


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("VIDEOCHECK_MIN_INTERVAL", "7")
    monkeypatch.setenv("VIDEOCHECK_MODEL_NAME", "yolov8s.pt")
    cfg = Config.from_env()
    assert cfg.min_interval == 7
    assert cfg.model_name == "yolov8s.pt"
    # untouched fields keep their default
    assert cfg.merge_gap == 90
