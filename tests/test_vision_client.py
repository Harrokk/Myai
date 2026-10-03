import base64

from core import vision_client


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_vision_client_requires_enabled():
    client = vision_client.VisionClient(
        "http://localhost:11434/api/chat",
        "vision-model",
        enabled=False,
    )

    try:
        client.analyze("missing.jpg", "describe")
    except RuntimeError as error:
        assert "avstängd" in str(error)
    else:
        raise AssertionError("VisionClient should refuse disabled state")


def test_vision_client_requires_model():
    client = vision_client.VisionClient(
        "http://localhost:11434/api/chat",
        "",
        enabled=True,
    )

    try:
        client.analyze("missing.jpg", "describe")
    except RuntimeError as error:
        assert "visionmodell" in str(error)
    else:
        raise AssertionError("VisionClient should require model")


def test_vision_client_sends_base64_image(tmp_path, monkeypatch):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"fake-image")
    seen = {}

    def fake_post(url, json, timeout):
        seen["url"] = url
        seen["json"] = json
        seen["timeout"] = timeout
        return FakeResponse(
            {"message": {"content": "Jag ser en testbild."}}
        )

    monkeypatch.setattr(vision_client.requests, "post", fake_post)

    client = vision_client.VisionClient(
        "http://localhost:11434/api/chat",
        "vision-model",
        enabled=True,
    )
    answer = client.analyze(
        image,
        "Beskriv bilden",
        timeout=30,
    )

    assert answer == "Jag ser en testbild."
    assert seen["timeout"] == 30
    assert seen["json"]["model"] == "vision-model"
    assert seen["json"]["messages"][0]["content"] == "Beskriv bilden"
    encoded = seen["json"]["messages"][0]["images"][0]
    assert base64.b64decode(encoded) == b"fake-image"



def test_vision_client_sends_multiple_images_in_order(tmp_path, monkeypatch):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"first-image")
    second.write_bytes(b"second-image")
    seen = {}

    def fake_post(url, json, timeout):
        seen["json"] = json
        return FakeResponse(
            {"message": {"content": "Skillnad hittad."}}
        )

    monkeypatch.setattr(vision_client.requests, "post", fake_post)

    client = vision_client.VisionClient(
        "http://localhost:11434/api/chat",
        "vision-model",
        enabled=True,
    )
    answer = client.analyze_images(
        [first, second],
        "Jämför bilderna",
    )

    assert answer == "Skillnad hittad."
    encoded = seen["json"]["messages"][0]["images"]
    assert len(encoded) == 2
    assert base64.b64decode(encoded[0]) == b"first-image"
    assert base64.b64decode(encoded[1]) == b"second-image"


def test_vision_client_requires_at_least_one_image():
    client = vision_client.VisionClient(
        "http://localhost:11434/api/chat",
        "vision-model",
        enabled=True,
    )

    try:
        client.analyze_images([], "Jämför")
    except ValueError as error:
        assert "Minst en bild" in str(error)
    else:
        raise AssertionError("VisionClient should require an image")



def test_vision_client_sends_in_memory_images(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout):
        seen["json"] = json
        seen["timeout"] = timeout
        return FakeResponse(
            {"message": {"content": "Livebild analyserad."}}
        )

    monkeypatch.setattr(vision_client.requests, "post", fake_post)

    client = vision_client.VisionClient(
        "http://localhost:11434/api/chat",
        "vision-model",
        enabled=True,
    )
    answer = client.analyze_bytes(
        [b"frame-one", bytearray(b"frame-two")],
        "Beskriv livebilderna",
        timeout=15,
    )

    assert answer == "Livebild analyserad."
    encoded = seen["json"]["messages"][0]["images"]
    assert len(encoded) == 2
    assert base64.b64decode(encoded[0]) == b"frame-one"
    assert base64.b64decode(encoded[1]) == b"frame-two"
    assert seen["timeout"] == 15


def test_vision_client_rejects_empty_in_memory_image():
    client = vision_client.VisionClient(
        "http://localhost:11434/api/chat",
        "vision-model",
        enabled=True,
    )

    try:
        client.analyze_bytes([b""], "Beskriv")
    except ValueError as error:
        assert "icke-tomma bytes" in str(error)
    else:
        raise AssertionError("Empty image bytes should fail")
