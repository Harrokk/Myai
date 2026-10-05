from types import SimpleNamespace

from modules.camera import stream


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


class FakeCV2:
    CAP_DSHOW = 700

    def __init__(self, camera):
        self.camera = camera
        self.video_args = None

    def VideoCapture(self, *args):
        self.video_args = args
        return self.camera


def frame(width=640, height=480):
    return SimpleNamespace(shape=(height, width, 3))


def enabled_settings(**overrides):
    camera = {
        "default_index": 0,
        "stream_enabled": True,
        "stream_duration_seconds": 2,
        "stream_fps": 2,
        "stream_max_frames": 10,
    }
    camera.update(overrides)
    return {"camera": camera}


def test_stream_is_disabled_by_default():
    result = stream.run_bounded_stream(
        settings={"camera": {}},
        cv2_module=object(),
    )

    assert result["success"] is False
    assert result["disabled"] is True
    assert "avstängd" in result["error"]


def test_stream_limits_target_frames():
    config = stream._stream_config(
        enabled_settings(
            stream_duration_seconds=10,
            stream_fps=10,
            stream_max_frames=7,
        )
    )

    assert config["target_frames"] == 7


def test_stream_rejects_excessive_limits():
    try:
        stream._stream_config(
            enabled_settings(stream_duration_seconds=1000)
        )
    except ValueError as error:
        assert "stream_duration_seconds" in str(error)
    else:
        raise AssertionError("Excessive duration should fail")


def test_bounded_stream_reads_target_and_releases(monkeypatch):
    monkeypatch.setattr(stream.platform, "system", lambda: "Windows")
    camera = FakeCamera([frame(), frame(), frame(), frame()])
    cv2 = FakeCV2(camera)
    handled = []
    sleeps = []

    result = stream.run_bounded_stream(
        settings=enabled_settings(),
        cv2_module=cv2,
        frame_handler=lambda frame, meta: handled.append(meta),
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )

    assert result["success"] is True
    assert result["frames"] == 4
    assert result["width"] == 640
    assert result["height"] == 480
    assert camera.released is True
    assert cv2.video_args == (0, cv2.CAP_DSHOW)
    assert len(handled) == 4
    assert len(sleeps) == 3


def test_bounded_stream_reports_open_failure():
    camera = FakeCamera([], opened=False)
    cv2 = FakeCV2(camera)

    result = stream.run_bounded_stream(
        settings=enabled_settings(),
        cv2_module=cv2,
        sleep_fn=lambda seconds: None,
    )

    assert result["success"] is False
    assert "öppnas" in result["error"]
    assert camera.released is True


def test_bounded_stream_reports_early_frame_failure():
    camera = FakeCamera([frame()])
    cv2 = FakeCV2(camera)

    result = stream.run_bounded_stream(
        settings=enabled_settings(),
        cv2_module=cv2,
        sleep_fn=lambda seconds: None,
    )

    assert result["success"] is False
    assert result["frames"] == 1
    assert "slutade leverera" in result["error"]
    assert camera.released is True


def test_stream_formatter_reports_success():
    text = stream.format_stream_result(
        {
            "success": True,
            "disabled": False,
            "camera_index": 2,
            "frames": 8,
            "width": 1280,
            "height": 720,
            "fps": 2.0,
            "target_frames": 8,
            "error": None,
        }
    )

    assert "8 bildrutor" in text
    assert "1280x720" in text
    assert "kameraindex 2" in text


def test_stream_requires_camera_enabled_even_if_stream_enabled():
    result = stream.run_bounded_stream(
        settings={
            "camera": {
                "enabled": False,
                "stream_enabled": True,
                "stream_duration_seconds": 2,
                "stream_fps": 2,
                "stream_max_frames": 10,
            }
        },
        cv2_module=object(),
    )

    assert result["success"] is False
    assert result["disabled"] is True
    assert "avstängd" in result["error"]
