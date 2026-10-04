import pytest

from core.geniex_client import GenieXClient


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_geniex_client_returns_message_content(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "ventuno-svar",
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "core.geniex_client.requests.post",
        fake_post,
    )

    client = GenieXClient(
        "http://127.0.0.1:18181/v1/",
        "ai-hub-models/Qwen3-4B-Instruct-2507",
    )

    result = client.chat(
        [{"role": "user", "content": "hej"}],
        timeout=12,
    )

    assert result == "ventuno-svar"
    assert captured["url"] == (
        "http://127.0.0.1:18181/v1/chat/completions"
    )
    assert captured["json"]["model"] == (
        "ai-hub-models/Qwen3-4B-Instruct-2507"
    )
    assert captured["json"]["stream"] is False
    assert captured["headers"]["Authorization"] == "Bearer geniex"
    assert captured["timeout"] == 12


def test_geniex_client_rejects_invalid_response(monkeypatch):
    monkeypatch.setattr(
        "core.geniex_client.requests.post",
        lambda *args, **kwargs: FakeResponse({}),
    )

    client = GenieXClient(
        "http://127.0.0.1:18181/v1",
        "test-model",
    )

    with pytest.raises(ValueError):
        client.chat([{"role": "user", "content": "hej"}])
