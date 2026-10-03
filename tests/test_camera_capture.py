from datetime import datetime
from types import SimpleNamespace

from modules.camera import capture


class FakeCamera:
    def __init__(self, opened=True, read_ok=True, frame=None):
        self.opened = opened
        self.read_ok = read_ok
        self.frame = frame
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        return self.read_ok, self.frame

    def release(self):
        self.released = True


class FakeCV2:
    CAP_DSHOW = 700

    def __init__(self, camera, write_ok=True):
        self.camera = camera
        self.write_ok = write_ok
        self.video_args = None
        self.saved_path = None

    def VideoCapture(self, *args):
        self.video_args = args
        return self.camera

    def imwrite(self, path, frame):
        self.saved_path = path
        return self.write_ok


def test_default_capture_path_is_unique_and_local(tmp_path):
    path = capture.default_capture_path(
        tmp_path,
        now=datetime(2026, 10, 3, 5, 20, 1, 123456),
    )

    assert path.parent == tmp_path
    assert path.name == "capture_20261003_052001_123456.jpg"


def test_capture_frame_saves_and_releases_camera(tmp_path, monkeypatch):
    monkeypatch.setattr(capture.platform, "system", lambda: "Windows")
    frame = SimpleNamespace(shape=(720, 1280, 3))
    camera = FakeCamera(frame=frame)
    cv2 = FakeCV2(camera)
    output = tmp_path / "photo.jpg"

    result = capture.capture_frame(
        camera_index=0,
        output_path=output,
        cv2_module=cv2,
    )

    assert result["success"] is True
    assert result["path"] == str(output)
    assert result["width"] == 1280
    assert result["height"] == 720
    assert camera.released is True
    assert cv2.video_args == (0, cv2.CAP_DSHOW)
    assert cv2.saved_path == str(output)


def test_capture_frame_releases_camera_when_open_fails(tmp_path):
    camera = FakeCamera(opened=False)
    cv2 = FakeCV2(camera)

    result = capture.capture_frame(
        output_path=tmp_path / "photo.jpg",
        cv2_module=cv2,
    )

    assert result["success"] is False
    assert "öppnas" in result["error"]
    assert camera.released is True


def test_capture_frame_reports_read_failure(tmp_path):
    camera = FakeCamera(read_ok=False, frame=None)
    cv2 = FakeCV2(camera)

    result = capture.capture_frame(
        output_path=tmp_path / "photo.jpg",
        cv2_module=cv2,
    )

    assert result["success"] is False
    assert "bildruta" in result["error"]
    assert camera.released is True


def test_capture_frame_reports_write_failure(tmp_path):
    frame = SimpleNamespace(shape=(480, 640, 3))
    camera = FakeCamera(frame=frame)
    cv2 = FakeCV2(camera, write_ok=False)

    result = capture.capture_frame(
        output_path=tmp_path / "photo.jpg",
        cv2_module=cv2,
    )

    assert result["success"] is False
    assert "sparas" in result["error"]
    assert camera.released is True


def test_format_capture_result_reports_saved_image():
    text = capture.format_capture_result(
        {
            "success": True,
            "path": "runtime/captures/test.jpg",
            "width": 640,
            "height": 480,
        }
    )

    assert "test.jpg" in text
    assert "640x480" in text


def test_missing_opencv_is_reported(monkeypatch):
    def missing():
        raise RuntimeError("OpenCV saknas")

    monkeypatch.setattr(capture, "_load_cv2", missing)

    text = capture.camera_capture()

    assert "OpenCV saknas" in text
