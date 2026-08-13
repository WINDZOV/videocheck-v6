import json
import os

from videocheck.progress import JSONFileProgressTracker, NullProgressTracker


def test_null_tracker_never_touches_disk(tmp_path):
    tracker = NullProgressTracker()
    tracker.init(["a.mp4"])
    tracker.update("a.mp4", "detecting", 50)
    tracker.finish("a.mp4", "done", clips=[{"file": "x.mp4"}])
    tracker.close()
    assert list(tmp_path.iterdir()) == []


def test_json_tracker_writes_expected_shape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = "progress.json"
    tracker = JSONFileProgressTracker(path)

    tracker.init(["a.mp4", "b.mp4"])
    tracker.update("a.mp4", "detecting", 40)
    tracker.finish("a.mp4", "done", clips=[{"file": "a_clip_000.mp4"}])
    tracker.finish("b.mp4", "empty")

    with open(path) as f:
        state = json.load(f)

    assert state["total"] == 2
    assert state["done"] == 2
    assert state["clips_found"] == 1
    assert state["empty_count"] == 1
    assert state["videos"]["a.mp4"]["status"] == "done"
    assert state["videos"]["b.mp4"]["status"] == "empty"

    # close() removes the file after its 5s grace sleep — skip that in the
    # unit test by monkeypatching sleep to be instant.
    monkeypatch.setattr("videocheck.progress.time.sleep", lambda _: None)
    tracker.close()
    assert not os.path.exists(path)
