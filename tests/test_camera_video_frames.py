from pathlib import Path
from types import SimpleNamespace

from modules.camera import video_frames


class FakeCapture:
    def __init__(self, frames, opened=True):
        self.frames = list(frames)
        self.opened = opened
        self.position = 0
        self.released = False
        self.set_calls = []

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return len(self.frames)

    def set(self, prop, value):
        self.position = int(value)
        self.set_calls.append((prop, int(value)))
        return True

    def read(self):
        if self.position < 0 or self.position >= len(self.frames):
            return False, None
        return True, self.frames[self.position]

    def release(self):
        self.released = True


class FakeCV2:
    CAP_PROP_FRAME_COUNT = 7
    CAP_PROP_POS_FRAMES = 1

    def __init__(self, capture, write_ok=True):
        self.capture = capture
        self.write_ok = write_ok
        self.saved = []

    def VideoCapture(self, path):
        self.opened_path = path
        return self.capture

    def imwrite(self, path, frame):
        self.saved.append((path, frame))
        return self.write_ok


def make_frame(name):
    return SimpleNamespace(name=name)


def test_sample_frame_indices_spans_entire_video():
    assert video_frames.sample_frame_indices(10, 3) == [0, 4, 9]


def test_sample_frame_indices_caps_at_total_frames():
    assert video_frames.sample_frame_indices(3, 5) == [0, 1, 2]


def test_sample_frame_indices_single_uses_middle():
    assert video_frames.sample_frame_indices(9, 1) == [4]


def test_latest_video_returns_newest(tmp_path):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"1")
    second.write_bytes(b"2")

    first.touch()
    second.touch()

    result = video_frames.latest_video(tmp_path)

    assert result is not None
    assert result.name in {"first.mp4", "second.mp4"}


def test_extract_video_frames_saves_even_samples(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    frames = [make_frame(str(index)) for index in range(10)]
    capture = FakeCapture(frames)
    cv2 = FakeCV2(capture)

    result = video_frames.extract_video_frames(
        video_path=video_path,
        output_dir=tmp_path / "samples",
        sample_count=3,
        cv2_module=cv2,
    )

    assert result["success"] is True
    assert [item["frame_index"] for item in result["frames"]] == [0, 4, 9]
    assert len(cv2.saved) == 3
    assert capture.released is True


def test_extract_video_frames_reports_open_failure(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    capture = FakeCapture([], opened=False)
    cv2 = FakeCV2(capture)

    result = video_frames.extract_video_frames(
        video_path=video_path,
        output_dir=tmp_path / "samples",
        sample_count=3,
        cv2_module=cv2,
    )

    assert result["success"] is False
    assert "öppnas" in result["error"]
    assert capture.released is True


def test_extract_video_frames_reports_write_failure(tmp_path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    capture = FakeCapture([make_frame("a")])
    cv2 = FakeCV2(capture, write_ok=False)

    result = video_frames.extract_video_frames(
        video_path=video_path,
        output_dir=tmp_path / "samples",
        sample_count=1,
        cv2_module=cv2,
    )

    assert result["success"] is False
    assert "sparas" in result["error"]
    assert capture.released is True


def test_sample_latest_video_uses_settings(tmp_path):
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    clip = video_dir / "clip.mp4"
    clip.write_bytes(b"video")

    frames = [make_frame(str(index)) for index in range(4)]
    capture = FakeCapture(frames)
    cv2 = FakeCV2(capture)

    result = video_frames.sample_latest_video_from_settings(
        settings={
            "camera": {
                "video_dir": str(video_dir),
                "video_frame_dir": str(tmp_path / "frames"),
                "video_sample_count": 2,
            }
        },
        cv2_module=cv2,
    )

    assert result["success"] is True
    assert len(result["frames"]) == 2
    assert Path(result["output_dir"]).parent == tmp_path / "frames"


def test_sample_latest_video_reports_missing_video(tmp_path):
    result = video_frames.sample_latest_video_from_settings(
        settings={
            "camera": {
                "video_dir": str(tmp_path / "missing"),
                "video_frame_dir": str(tmp_path / "frames"),
                "video_sample_count": 3,
            }
        }
    )

    assert result["success"] is False
    assert "Ingen sparad video" in result["error"]
