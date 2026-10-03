from types import SimpleNamespace

from modules.camera import live_vision


class FakeBuffer:
    def __init__(self, data):
        self.data = data

    def tobytes(self):
        return self.data


class FakeCV2:
    def __init__(self):
        self.encoded = []

    def imencode(self, extension, frame):
        self.encoded.append((extension, frame))
        return True, FakeBuffer(
            f"encoded-{frame.name}".encode("utf-8")
        )


class FakeVisionClient:
    def __init__(self, answer="Ett bord och en stol syns."):
        self.answer = answer
        self.calls = []

    def analyze_bytes(self, images, prompt, timeout=120):
        self.calls.append(
            {
                "images": list(images),
                "prompt": prompt,
                "timeout": timeout,
            }
        )
        return self.answer


def enabled_settings():
    return {
        "ollama": {
            "url": "http://localhost:11434/api/chat",
        },
        "vision": {
            "enabled": True,
            "url": "http://localhost:11434/api/chat",
            "model": "vision-test",
            "timeout_seconds": 25,
        },
        "camera": {
            "default_index": 0,
            "stream_enabled": True,
            "stream_duration_seconds": 5,
            "stream_fps": 2,
            "stream_max_frames": 10,
        },
    }


def test_live_vision_requires_enabled_vision():
    called = {"value": False}

    def runner(**kwargs):
        called["value"] = True
        return {"success": True}

    text = live_vision.analyze_live_camera(
        settings={
            "vision": {"enabled": False, "model": ""},
            "camera": {"stream_enabled": True},
        },
        stream_runner=runner,
    )

    assert "avstängd" in text
    assert called["value"] is False


def test_live_vision_requires_stream_enabled():
    settings = enabled_settings()
    settings["camera"]["stream_enabled"] = False

    text = live_vision.analyze_live_camera(settings=settings)

    assert "stream_enabled" in text


def test_live_vision_caps_frames_and_uses_memory_bytes():
    settings = enabled_settings()
    cv2 = FakeCV2()
    client = FakeVisionClient()
    seen = {}

    def runner(settings, cv2_module, frame_handler):
        seen["max_frames"] = settings["camera"]["stream_max_frames"]

        for index in range(seen["max_frames"]):
            frame_handler(
                SimpleNamespace(name=f"frame-{index}"),
                {"index": index},
            )

        return {
            "success": True,
            "frames": seen["max_frames"],
            "error": None,
        }

    text = live_vision.analyze_live_camera(
        settings=settings,
        client=client,
        cv2_module=cv2,
        stream_runner=runner,
    )

    assert seen["max_frames"] == live_vision.MAX_LIVE_VISION_FRAMES
    assert "6 begränsade" in text
    assert len(client.calls[0]["images"]) == 6
    assert client.calls[0]["images"][0] == b"encoded-frame-0"
    assert client.calls[0]["timeout"] == 25
    assert "inte att du har sett en kontinuerlig videoström" in (
        client.calls[0]["prompt"]
    )


def test_live_vision_reports_stream_failure():
    text = live_vision.analyze_live_camera(
        settings=enabled_settings(),
        cv2_module=FakeCV2(),
        stream_runner=lambda **kwargs: {
            "success": False,
            "error": "kamera borta",
        },
    )

    assert "kamera borta" in text


def test_live_vision_reports_encoding_failure():
    class BrokenCV2:
        def imencode(self, extension, frame):
            return False, None

    def runner(settings, cv2_module, frame_handler):
        frame_handler(SimpleNamespace(name="bad"), {"index": 0})
        return {"success": True}

    try:
        live_vision.analyze_live_camera(
            settings=enabled_settings(),
            cv2_module=BrokenCV2(),
            stream_runner=runner,
        )
    except RuntimeError as error:
        assert "JPEG-kodas" in str(error)
    else:
        raise AssertionError("Encoding failure should propagate")


def test_live_vision_tool_reports_failure(monkeypatch):
    def fail():
        raise RuntimeError("testfel")

    monkeypatch.setattr(
        live_vision,
        "analyze_live_camera",
        fail,
    )

    text = live_vision.vision_analyze_live()

    assert "misslyckades" in text
    assert "testfel" in text
