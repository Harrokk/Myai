from modules.internet import verify


def fake_fetch(url, settings=None):
    return {
        "available": True,
        "requested_url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "title": "Study",
        "text": (
            "Methods. Data. Results. References. "
            "Limitations. " + "content " * 250
        ),
        "metadata": {
            "author": "Author",
            "article:published_time": "2026-10-03",
        },
        "canonical_url": url,
        "external_links": [
            "https://reference.example/source",
        ],
        "redirects": 0,
        "truncated": False,
    }


def test_verify_source_page_uses_fetched_page():
    result = verify.verify_source_page_data(
        "https://example.com/article",
        query="study data",
        fetch_function=fake_fetch,
    )

    assert result["available"] is True
    assert result["verification"]["author"] == "Author"
    assert result["verification"]["signals"]["method"] is True


def test_verify_formatter_separates_scores():
    result = verify.verify_source_page_data(
        "https://example.com/article",
        query="study data",
        fetch_function=fake_fetch,
    )
    text = verify.format_source_verification(result)

    assert "Transparensscore" in text
    assert "Evidenssignalscore" in text
    assert "inte en sannolikhet" in text


def test_verify_tool_declares_url_parameter():
    schema = verify.TOOLS["web_verify_source"]["parameters"]

    assert schema["required"] == ["url"]
