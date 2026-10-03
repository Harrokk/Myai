from pathlib import Path

from modules.camera import vision


class FakeVisionClient:
    def __init__(self):
        self.calls = []

    def analyze(self, image_path, prompt, timeout=120):
        self.calls.append(
            {
                "image_path": Path(image_path),
                "prompt": prompt,
                "timeout": timeout,
            }
        )
        return "En stol och ett bord."


def settings(enabled=True, model="vision-model"):
    return {
        "ollama": {
            "url": "http://localhost:11434/api/chat",
        },
        "vision": {
            "enabled": enabled,
            "model": model,
            "url": "http://localhost:11434/api/chat",
            "timeout_seconds": 45,
        },
    }


def test_latest_capture_returns_newest_file(tmp_path):
    older = tmp_path / "older.jpg"
    newer = tmp_path / "newer.jpg"
    older.write_bytes(b"a")
    newer.write_bytes(b"b")
    older.touch()
    newer.touch()

    older_stat = older.stat()
    newer_stat = newer.stat()

    if older_stat.st_mtime_ns == newer_stat.st_mtime_ns:
        older.rename(tmp_path / "a_older.jpg")
        older = tmp_path / "a_older.jpg"

    result = vision.latest_capture(tmp_path)

    assert result is not None
    assert result.name in {"newer.jpg", "a_older.jpg"}


def test_latest_capture_returns_none_when_empty(tmp_path):
    assert vision.latest_capture(tmp_path) is None


def test_analysis_is_disabled_by_default(tmp_path):
    text = vision.analyze_latest_capture(
        settings=settings(enabled=False),
        capture_dir=tmp_path,
    )

    assert "avstängd" in text


def test_analysis_requires_model(tmp_path):
    text = vision.analyze_latest_capture(
        settings=settings(model=""),
        capture_dir=tmp_path,
    )

    assert "Ingen visionmodell" in text


def test_analysis_requires_existing_capture(tmp_path):
    text = vision.analyze_latest_capture(
        settings=settings(),
        capture_dir=tmp_path,
    )

    assert "Ta en bild först" in text


def test_analysis_uses_latest_capture_and_configured_timeout(tmp_path):
    image = tmp_path / "capture.jpg"
    image.write_bytes(b"image")
    client = FakeVisionClient()

    text = vision.analyze_latest_capture(
        settings=settings(),
        client=client,
        capture_dir=tmp_path,
    )

    assert "capture.jpg" in text
    assert "En stol och ett bord." in text
    assert client.calls[0]["image_path"] == image
    assert client.calls[0]["timeout"] == 45
