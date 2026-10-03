from modules.internet import fetch


class FakeClient:
    def fetch(self, url):
        return {
            "requested_url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "title": "Titel",
            "text": "x" * 50,
            "redirects": 0,
        }


def settings(enabled=True):
    return {
        "internet": {
            "enabled": enabled,
            "timeout_seconds": 15,
            "max_page_bytes": 1_000_000,
            "max_page_chars": 20,
            "max_redirects": 5,
        }
    }


def test_fetch_tool_respects_disabled_internet():
    result = fetch.fetch_public_page(
        "https://example.com",
        settings=settings(enabled=False),
        client=FakeClient(),
    )

    assert result["available"] is False


def test_fetch_tool_truncates_to_configured_limit():
    result = fetch.fetch_public_page(
        "https://example.com",
        max_chars=100,
        settings=settings(),
        client=FakeClient(),
    )

    assert result["available"] is True
    assert len(result["text"]) == 20
    assert result["truncated"] is True


def test_formatter_includes_title_and_url():
    result = fetch.fetch_public_page(
        "https://example.com",
        max_chars=10,
        settings=settings(),
        client=FakeClient(),
    )

    text = fetch.format_public_page(result)

    assert "Titel" in text
    assert "https://example.com" in text
    assert "avkortat" in text


def test_fetch_tool_declares_url_parameter():
    schema = fetch.TOOLS["web_fetch_text"]["parameters"]

    assert schema["required"] == ["url"]
