from core import page_verification


def page(**overrides):
    value = {
        "requested_url": "https://example.com/article",
        "final_url": "https://example.com/article",
        "title": "Documented study",
        "text": (
            "Methods and methodology. Data and results were measured. "
            "Limitations are discussed. References include "
            "10.1234/example.doi. "
            + "Detailed content " * 150
        ),
        "metadata": {
            "author": "Ada Example",
            "article:published_time": "2026-10-03",
            "description": "A documented study",
            "og:site_name": "Example Research",
        },
        "canonical_url": "https://example.com/article",
        "external_links": [
            "https://other.example/reference",
            "https://third.example/data",
        ],
    }
    value.update(overrides)
    return value


def test_verified_page_detects_transparency_signals():
    result = page_verification.verify_page_content(
        page(),
        query="documented study data",
    )

    assert result["author"] == "Ada Example"
    assert result["published_date"] == "2026-10-03"
    assert result["signals"]["method"] is True
    assert result["signals"]["references"] is True
    assert result["signals"]["doi"] is True
    assert result["signals"]["limitations"] is True
    assert result["transparency_score"] <= 90
    assert result["evidence_signal_score"] <= 85


def test_sparse_page_scores_lower():
    rich = page_verification.verify_page_content(page())
    sparse = page_verification.verify_page_content(
        page(
            title="",
            text="Kort text.",
            metadata={},
            canonical_url="",
            external_links=[],
        )
    )

    assert rich["transparency_score"] > sparse["transparency_score"]
    assert rich["evidence_signal_score"] > sparse["evidence_signal_score"]


def test_page_scores_are_not_truth_probabilities():
    result = page_verification.verify_page_content(page())

    assert "inte en sannolikhet" in result["assessment_note"]


def test_query_overlap_is_reported():
    result = page_verification.verify_page_content(
        page(),
        query="methods data",
    )

    assert result["query_overlap_percent"] > 0
