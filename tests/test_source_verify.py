from modules.internet import verify


class FakeClient:
    def fetch(self, url):
        return {
            "requested_url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "title": "Raspberry Pi report",
            "text": (
                "Method, data, results, references and limitations. "
                "Raspberry Pi power measurement. "
            ) * 40,
            "metadata": {
                "author": "Ada Example",
                "article:published_time": "2026-10-03",
                "description": "Power measurements",
            },
            "canonical_url": url,
            "external_links": ["https://other.example/source"],
            "redirects": 0,
        }


def settings(enabled=True):
    return {
        "internet": {
            "enabled": enabled,
            "timeout_seconds": 15,
            "max_page_bytes": 1_000_000,
            "max_page_chars": 20_000,
            "max_redirects": 5,
        }
    }


def test_verify_source_page_returns_separate_conservative_scores():
    result = verify.verify_source_page(
        "https://example.com/report",
        query="Raspberry Pi power",
        settings=settings(),
        client=FakeClient(),
    )

    assert result["available"] is True
    assert 0 <= result["source_reliability"] <= 85
    assert 0 <= result["information_confidence"] <= 75
    assert result["assessment_scope"] == "single_fetched_page_heuristic"
    assert "inte sannolikheter" in result["assessment_note"]


def test_verify_source_page_respects_disabled_internet():
    result = verify.verify_source_page(
        "https://example.com/report",
        settings=settings(enabled=False),
        client=FakeClient(),
    )

    assert result["available"] is False


def test_source_verify_page_extracts_url_and_formats(monkeypatch):
    seen = {}

    monkeypatch.setattr(
        verify,
        "verify_source_page",
        lambda url, query="": {
            "available": True,
            "url": seen.setdefault("url", url),
            "title": "Test",
            "source_reliability": 60.0,
            "information_confidence": 50.0,
            "verification": {
                "transparency_score": 60.0,
                "evidence_signal_score": 50.0,
                "query_overlap_percent": 40.0,
            },
            "assessment_note": "heuristik",
        },
    )

    text = verify.source_verify_page(
        "Granska källan https://example.com/report om Raspberry Pi."
    )

    assert seen["url"] == "https://example.com/report"
    assert "Källans tillförlitlighet: 60.0%" in text
    assert "Informationens konfidens: 50.0%" in text


def test_source_verify_tool_is_query_aware():
    assert verify.TOOLS["source_verify_page"]["pass_user_input"] is True
