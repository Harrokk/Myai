from modules.camera import change


class FakeVisionClient:
    def __init__(self, answer="En stol har tillkommit."):
        self.answer = answer
        self.calls = []

    def analyze_images(self, image_paths, prompt, timeout=120):
        self.calls.append(
            {
                "image_paths": list(image_paths),
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
            "timeout_seconds": 50,
        },
    }


def test_recent_captures_returns_two_newest_in_order(tmp_path):
    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    third = tmp_path / "c.jpg"

    first.write_bytes(b"a")
    second.write_bytes(b"b")
    third.write_bytes(b"c")

    first.touch()
    second.touch()
    third.touch()

    result = change.recent_captures(tmp_path, count=2)

    assert len(result) == 2
    assert result[-1].name in {"b.jpg", "c.jpg"}


def test_change_detection_disabled_message(tmp_path):
    text = change.detect_latest_change(
        settings={
            "vision": {
                "enabled": False,
                "model": "",
            }
        },
        capture_dir=tmp_path,
    )

    assert "avstängd" in text


def test_change_detection_requires_two_images(tmp_path):
    (tmp_path / "one.jpg").write_bytes(b"one")

    text = change.detect_latest_change(
        settings=enabled_settings(),
        capture_dir=tmp_path,
    )

    assert "Minst två" in text


def test_change_detection_uses_two_images_and_no_inference_prompt(tmp_path):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    client = FakeVisionClient("Bordet är nu tomt.")

    text = change.detect_latest_change(
        settings=enabled_settings(),
        client=client,
        capture_dir=tmp_path,
    )

    assert "Förändringsanalys" in text
    assert "Bordet är nu tomt." in text
    assert len(client.calls) == 1
    assert len(client.calls[0]["image_paths"]) == 2
    assert "Gissa inte orsak" in client.calls[0]["prompt"]
    assert "INGEN TYDLIG FÖRÄNDRING" in client.calls[0]["prompt"]
    assert client.calls[0]["timeout"] == 50


def test_change_tool_reports_client_failure(monkeypatch):
    def fail():
        raise RuntimeError("testfel")

    monkeypatch.setattr(
        change,
        "detect_latest_change",
        fail,
    )

    text = change.vision_detect_change()

    assert "misslyckades" in text
    assert "testfel" in text
