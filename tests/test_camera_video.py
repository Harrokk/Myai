from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from modules.camera import video


class FakeCamera:
    def __init__(self, frames, opened=True):
        self.frames = list(frames)
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)

    def release(self):
        self.released = True


class FakeWriter:
    def __init__(self, opened=True):
        self.opened = opened
        self.frames = []
        self.released = False

    def isOpened(self):
        return self.opened

    def write(self, frame):
        self.frames.append(frame)

    def release(self):
        self.released = True


class FakeCV2:
    CAP_DSHOW = 700

    def __init__(self, camera, writer=None):
        self.camera = camera
        self.writer = writer or FakeWriter()
        self.video_args = None
        self.writer_args = None

    def VideoCapture(self, *args):
        self.video_args = args
        return self.camera

    def VideoWriter_fourcc(self, *args):
        assert args == ("m", "p", "4", "v")
        return 1234

    def VideoWriter(self, *args):
        self.writer_args = args
        return self.writer


def frame(width=640, height=480):
    return SimpleNamespace(shape=(height, width, 3))


def test_default_video_path_is_local_and_unique(tmp_path):
    path = video.default_video_path(
        tmp_path,
        now=datetime(2026, 10, 3, 18, 0, 1, 123456),
    )

    assert path.parent == tmp_path
    assert path.name == "video_20261003_180001_123456.mp4"


def test_record_clip_writes_expected_frames_and_releases(tmp_path, monkeypatch):
    monkeypatch.setattr(video.platform, "system", lambda: "Windows")
    camera = FakeCamera([frame(), frame(), frame()])
    writer = FakeWriter()
    cv2 = FakeCV2(camera, writer)

    result = video.record_clip(
        camera_index=2,
        output_path=tmp_path / "clip.mp4",
        duration_seconds=1,
        fps=3,
        cv2_module=cv2,
    )

    assert result["success"] is True
    assert result["frames"] == 3
    assert result["camera_index"] == 2
    assert cv2.video_args == (2, cv2.CAP_DSHOW)
    assert len(writer.frames) == 3
    assert camera.released is True
    assert writer.released is True


def test_record_clip_reports_camera_open_failure(tmp_path):
    camera = FakeCamera([], opened=False)
    cv2 = FakeCV2(camera)

    result = video.record_clip(
        output_path=tmp_path / "clip.mp4",
        cv2_module=cv2,
    )

    assert result["success"] is False
    assert "öppnas" in result["error"]
    assert camera.released is True


def test_record_clip_reports_short_read_and_releases(tmp_path):
    camera = FakeCamera([frame(), frame()])
    writer = FakeWriter()
    cv2 = FakeCV2(camera, writer)

    result = video.record_clip(
        output_path=tmp_path / "clip.mp4",
        duration_seconds=1,
        fps=3,
        cv2_module=cv2,
    )

    assert result["success"] is False
    assert result["frames"] == 2
    assert "avbröts" in result["error"]
    assert camera.released is True
    assert writer.released is True


def test_record_clip_rejects_invalid_duration():
    try:
        video.record_clip(duration_seconds=0, cv2_module=object())
    except ValueError as error:
        assert "större än 0" in str(error)
    else:
        raise AssertionError("Zero duration should fail")


def test_record_video_from_settings_uses_camera_config(tmp_path, monkeypatch):
    monkeypatch.setattr(video.platform, "system", lambda: "Windows")
    camera = FakeCamera([frame(), frame()])
    cv2 = FakeCV2(camera)

    result = video.record_video_from_settings(
        settings={
            "camera": {
                "default_index": 3,
                "video_dir": str(tmp_path),
                "video_duration_seconds": 1,
                "video_fps": 2,
            }
        },
        cv2_module=cv2,
    )

    assert result["success"] is True
    assert result["camera_index"] == 3
    assert Path(result["path"]).parent == tmp_path


def test_format_video_result_reports_clip():
    text = video.format_video_result(
        {
            "success": True,
            "path": "runtime/video/test.mp4",
            "width": 640,
            "height": 480,
            "frames": 50,
            "fps": 10.0,
        }
    )

    assert "test.mp4" in text
    assert "50 bildrutor" in text


def test_record_video_from_settings_stops_before_opening_disabled_camera():
    class FailCV2:
        def VideoCapture(self, *args):
            raise AssertionError(
                "Avstängd kamera får inte öppnas."
            )

    result = video.record_video_from_settings(
        settings={
            "camera": {
                "enabled": False,
                "default_index": 0,
            }
        },
        cv2_module=FailCV2(),
    )

    assert result["success"] is False
    assert result["disabled"] is True
    assert "avstängd" in result["error"]
