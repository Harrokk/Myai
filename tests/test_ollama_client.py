import pytest

from core.ollama_client import OllamaClient


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_ollama_client_returns_message_content(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(
            {"message": {"content": "test-svar"}}
        )

    monkeypatch.setattr(
        "core.ollama_client.requests.post",
        fake_post,
    )

    client = OllamaClient(
        "http://localhost:11434/api/chat",
        "qwen3:8b",
    )

    result = client.chat(
        [{"role": "user", "content": "hej"}],
        timeout=12,
    )

    assert result == "test-svar"
    assert captured["json"]["model"] == "qwen3:8b"
    assert captured["timeout"] == 12


def test_ollama_client_rejects_invalid_response(monkeypatch):
    monkeypatch.setattr(
        "core.ollama_client.requests.post",
        lambda *args, **kwargs: FakeResponse({}),
    )

    client = OllamaClient("http://test", "test-model")

    with pytest.raises(ValueError):
        client.chat([{"role": "user", "content": "hej"}])


class FakeStreamingResponse:
    def __init__(self, lines):
        self.lines = lines
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=True):
        return iter(self.lines)

    def close(self):
        self.closed = True


def test_ollama_client_streams_json_lines(monkeypatch):
    captured = {}
    response = FakeStreamingResponse(
        [
            '{"message":{"content":"Hej"},"done":false}',
            '{"message":{"content":" där"},"done":false}',
            '{"message":{"content":""},"done":true}',
        ]
    )

    def fake_post(url, json, timeout, stream):
        captured["json"] = json
        captured["stream"] = stream
        return response

    monkeypatch.setattr(
        "core.ollama_client.requests.post",
        fake_post,
    )

    client = OllamaClient(
        "http://localhost:11434/api/chat",
        "qwen3:8b",
    )

    chunks = list(
        client.chat_stream(
            [{"role": "user", "content": "hej"}],
            timeout=9,
        )
    )

    assert chunks == ["Hej", " där"]
    assert captured["stream"] is True
    assert captured["json"]["stream"] is True
    assert response.closed is True
