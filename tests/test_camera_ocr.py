from modules.camera import ocr


class FakeVisionClient:
    def __init__(self, answer="TESTTEXT"):
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
            "timeout_seconds": 45,
        },
    }


def test_ocr_is_disabled_by_default_message(tmp_path):
    settings = {
        "vision": {
            "enabled": False,
            "model": "",
        }
    }

    text = ocr.read_text_latest_capture(
        settings=settings,
        capture_dir=tmp_path,
    )

    assert "avstängd" in text


def test_ocr_requires_configured_model(tmp_path):
    settings = {
        "vision": {
            "enabled": True,
            "model": "",
        }
    }

    text = ocr.read_text_latest_capture(
        settings=settings,
        capture_dir=tmp_path,
    )

    assert "Ingen visionmodell" in text


def test_ocr_requires_existing_capture(tmp_path):
    text = ocr.read_text_latest_capture(
        settings=enabled_settings(),
        capture_dir=tmp_path,
    )

    assert "Ingen sparad kamerabild" in text


def test_ocr_uses_latest_capture_and_strict_prompt(tmp_path):
    old = tmp_path / "old.jpg"
    new = tmp_path / "new.jpg"
    old.write_bytes(b"old")
    new.write_bytes(b"new")

    old.touch()
    new.touch()

    client = FakeVisionClient("Rad 1\nRad 2")

    text = ocr.read_text_latest_capture(
        settings=enabled_settings(),
        client=client,
        capture_dir=tmp_path,
    )

    assert "Textläsning av" in text
    assert "Rad 1" in text
    assert len(client.calls) == 1
    assert "Gissa inte" in client.calls[0]["prompt"]
    assert "INGEN LÄSBAR TEXT" in client.calls[0]["prompt"]
    assert client.calls[0]["timeout"] == 45


def test_ocr_tool_reports_client_failure(monkeypatch):
    def fail():
        raise RuntimeError("testfel")

    monkeypatch.setattr(
        ocr,
        "read_text_latest_capture",
        fail,
    )

    text = ocr.vision_read_text()

    assert "misslyckades" in text
    assert "testfel" in text
