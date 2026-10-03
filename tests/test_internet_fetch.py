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


def test_extract_page_url_from_natural_language():
    assert fetch.extract_page_url(
        "Läs sidan https://example.com/test?x=1 och sammanfatta."
    ) == "https://example.com/test?x=1"


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


def test_fetch_tool_uses_user_input_url(monkeypatch):
    seen = {}

    monkeypatch.setattr(
        fetch,
        "fetch_public_page",
        lambda url: seen.setdefault("url", url) or {
            "available": False,
            "reason": "test",
        },
    )

    result = fetch.web_fetch_text(
        "Hämta https://example.com/article"
    )

    assert seen["url"] == "https://example.com/article"
    assert "kunde inte hämtas" in result


def test_fetch_tool_requires_url_in_user_input():
    result = fetch.web_fetch_text("Hämta den här sidan.")

    assert "ingen http/https-adress" in result


def test_fetch_tool_is_query_aware():
    assert fetch.TOOLS["web_fetch_text"]["pass_user_input"] is True
