from core.page_verification import verify_page_content


def test_page_verification_detects_transparency_and_evidence_signals():
    page = {
        "requested_url": "https://example.com/report",
        "final_url": "https://example.com/report",
        "title": "Raspberry Pi power study",
        "text": (
            "Method and data results are described here. "
            "References include https://doi.org/10.1234/example. "
            "Limitations and uncertainty are also discussed. "
        ) * 30,
        "metadata": {
            "author": "Ada Example",
            "article:published_time": "2026-10-03",
            "description": "Raspberry Pi power measurements",
            "og:site_name": "Example Research",
        },
        "canonical_url": "https://example.com/report",
        "external_links": [
            "https://other.example/source",
            "https://doi.org/10.1234/example",
        ],
    }

    result = verify_page_content(
        page,
        query="Raspberry Pi power measurements",
    )

    assert result["author"] == "Ada Example"
    assert result["published_date"] == "2026-10-03"
    assert result["signals"]["method"] is True
    assert result["signals"]["data_or_results"] is True
    assert result["signals"]["references"] is True
    assert result["signals"]["doi"] is True
    assert result["signals"]["limitations"] is True
    assert result["transparency_score"] > 50
    assert result["evidence_signal_score"] > 50
    assert result["query_overlap_percent"] > 0


def test_page_verification_stays_conservative_for_thin_page():
    page = {
        "requested_url": "https://example.com",
        "final_url": "https://example.com",
        "title": "",
        "text": "Short marketing claim.",
        "metadata": {},
        "canonical_url": "",
        "external_links": [],
    }

    result = verify_page_content(page, query="independent evidence")

    assert result["transparency_score"] <= 30
    assert result["evidence_signal_score"] <= 25
    assert "inte en sannolikhet" in result["assessment_note"]
