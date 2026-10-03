from modules.camera import objects


class FakeVisionClient:
    def __init__(self, answer="kopp - hög"):
        self.answer = answer
        self.calls = []

    def analyze(self, image_path, prompt, timeout=120):
        self.calls.append(
            {
                "image_path": image_path,
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
            "timeout_seconds": 30,
        },
    }


def test_object_detection_disabled_message(tmp_path):
    text = objects.detect_objects_latest_capture(
        settings={
            "vision": {
                "enabled": False,
                "model": "",
            }
        },
        capture_dir=tmp_path,
    )

    assert "avstängd" in text


def test_object_detection_requires_model(tmp_path):
    text = objects.detect_objects_latest_capture(
        settings={
            "vision": {
                "enabled": True,
                "model": "",
            }
        },
        capture_dir=tmp_path,
    )

    assert "Ingen visionmodell" in text


def test_object_detection_requires_capture(tmp_path):
    text = objects.detect_objects_latest_capture(
        settings=enabled_settings(),
        capture_dir=tmp_path,
    )

    assert "Ingen sparad kamerabild" in text


def test_object_detection_uses_conservative_prompt(tmp_path):
    image = tmp_path / "scene.jpg"
    image.write_bytes(b"image")

    client = FakeVisionClient("stol - hög\nbord - medel")

    text = objects.detect_objects_latest_capture(
        settings=enabled_settings(),
        client=client,
        capture_dir=tmp_path,
    )

    assert "Objektidentifiering av scene.jpg" in text
    assert "stol - hög" in text
    assert len(client.calls) == 1
    assert "Gissa inte" in client.calls[0]["prompt"]
    assert "INGA SÄKRA OBJEKT" in client.calls[0]["prompt"]
    assert client.calls[0]["timeout"] == 30


def test_object_tool_reports_client_failure(monkeypatch):
    def fail():
        raise RuntimeError("testfel")

    monkeypatch.setattr(
        objects,
        "detect_objects_latest_capture",
        fail,
    )

    text = objects.vision_detect_objects()

    assert "misslyckades" in text
    assert "testfel" in text
