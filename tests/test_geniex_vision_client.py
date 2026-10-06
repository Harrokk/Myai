import base64

import pytest

from core.geniex_vision_client import GenieXVisionClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_geniex_vision_client_sends_openai_multimodal_payload(
    tmp_path,
    monkeypatch,
):
    image = tmp_path / "frame.png"
    image.write_bytes(b"fake-png")
    captured = {}

    def fake_post(
        url,
        json,
        headers,
        timeout,
    ):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "Jag ser en bild."
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "core.geniex_vision_client.requests.post",
        fake_post,
    )

    client = GenieXVisionClient(
        "http://127.0.0.1:18181/v1/",
        "qualcomm/Qwen3-VL-4B-Instruct",
        enabled=True,
        max_tokens=128,
        temperature=0.1,
    )

    answer = client.analyze(
        image,
        "Beskriv bilden",
        timeout=15,
    )

    assert answer == "Jag ser en bild."
    assert captured["url"] == (
        "http://127.0.0.1:18181/v1/chat/completions"
    )
    assert captured["timeout"] == 15
    assert captured["json"]["stream"] is False
    assert captured["json"]["max_tokens"] == 128
    assert captured["json"]["temperature"] == 0.1

    content = captured["json"]["messages"][0]["content"]
    assert content[0] == {
        "type": "text",
        "text": "Beskriv bilden",
    }
    image_url = content[1]["image_url"]["url"]
    assert image_url.startswith(
        "data:image/png;base64,"
    )
    encoded = image_url.split(",", 1)[1]
    assert base64.b64decode(encoded) == b"fake-png"


def test_geniex_vision_client_preserves_multiple_image_order(
    tmp_path,
    monkeypatch,
):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.webp"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    captured = {}

    def fake_post(
        url,
        json,
        headers,
        timeout,
    ):
        captured["json"] = json
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "Skillnad."
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "core.geniex_vision_client.requests.post",
        fake_post,
    )

    client = GenieXVisionClient(
        "http://127.0.0.1:18181/v1",
        "test-vlm",
        enabled=True,
    )
    answer = client.analyze_images(
        [first, second],
        "Jämför",
    )

    assert answer == "Skillnad."
    content = captured["json"]["messages"][0]["content"]
    urls = [
        item["image_url"]["url"]
        for item in content[1:]
    ]
    assert len(urls) == 2
    assert urls[0].startswith("data:image/jpeg;base64,")
    assert urls[1].startswith("data:image/webp;base64,")


def test_geniex_vision_client_accepts_in_memory_jpeg_frames(
    monkeypatch,
):
    captured = {}

    def fake_post(
        url,
        json,
        headers,
        timeout,
    ):
        captured["json"] = json
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "Live."
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "core.geniex_vision_client.requests.post",
        fake_post,
    )

    client = GenieXVisionClient(
        "http://127.0.0.1:18181/v1",
        "test-vlm",
        enabled=True,
    )

    assert client.analyze_bytes(
        [b"jpeg-frame"],
        "Live",
    ) == "Live."

    url = (
        captured["json"]["messages"][0]
        ["content"][1]["image_url"]["url"]
    )
    assert url.startswith(
        "data:image/jpeg;base64,"
    )


def test_geniex_vision_client_fails_closed_when_disabled():
    client = GenieXVisionClient(
        "http://127.0.0.1:18181/v1",
        "test-vlm",
        enabled=False,
    )

    with pytest.raises(
        RuntimeError,
        match="avstängd",
    ):
        client.analyze_bytes(
            [b"frame"],
            "Beskriv",
        )
