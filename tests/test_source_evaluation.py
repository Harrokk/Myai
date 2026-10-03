from core import source_evaluation


def candidate(
    title,
    url,
    snippet,
    engines=None,
    published_date=None,
):
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "engines": engines or [],
        "published_date": published_date,
    }


def test_source_reliability_is_capped_for_metadata_only():
    result = source_evaluation.source_reliability(
        candidate(
            "Detailed official-looking title",
            "https://example.com/report",
            "x" * 200,
            engines=["a", "b"],
            published_date="2026-10-03",
        )
    )

    assert result["score"] <= 80
    assert result["scope"] == "preliminary_metadata"


def test_shortener_scores_lower_than_normal_https_domain():
    normal = source_evaluation.source_reliability(
        candidate(
            "Title",
            "https://example.com/report",
            "Useful snippet " * 10,
        )
    )
    short = source_evaluation.source_reliability(
        candidate(
            "Title",
            "https://bit.ly/test",
            "Useful snippet " * 10,
        )
    )

    assert normal["score"] > short["score"]


def test_relevance_rewards_query_terms():
    relevant = source_evaluation.relevance_score(
        "raspberry pi power",
        candidate(
            "Raspberry Pi power measurement",
            "https://example.com",
            "Power telemetry for Raspberry Pi.",
        ),
    )
    irrelevant = source_evaluation.relevance_score(
        "raspberry pi power",
        candidate(
            "Cooking pasta",
            "https://example.com",
            "Recipe and ingredients.",
        ),
    )

    assert relevant > irrelevant


def test_cross_domain_corroboration_increases_confidence():
    first = candidate(
        "Raspberry Pi power issue",
        "https://one.example/a",
        "Raspberry Pi power supply voltage warning under heavy load.",
    )
    second = candidate(
        "Pi power supply warning",
        "https://two.example/b",
        "Raspberry Pi power supply voltage warning can appear under heavy load.",
    )

    with_corroboration = source_evaluation.information_confidence(
        first,
        [first, second],
    )
    without_corroboration = source_evaluation.information_confidence(
        first,
        [first],
    )

    assert with_corroboration["score"] > without_corroboration["score"]
    assert "two.example" in with_corroboration["corroborating_domains"]


def test_same_domain_is_not_independent_corroboration():
    first = candidate(
        "Power issue",
        "https://same.example/a",
        "Raspberry Pi power supply voltage warning under heavy load.",
    )
    second = candidate(
        "Power issue copy",
        "https://same.example/b",
        "Raspberry Pi power supply voltage warning under heavy load.",
    )

    result = source_evaluation.information_confidence(
        first,
        [first, second],
    )

    assert result["corroborating_domains"] == []


def test_evaluate_candidates_sorts_by_combined_score():
    items = [
        candidate(
            "Cooking",
            "https://food.example",
            "Pasta recipe.",
        ),
        candidate(
            "Raspberry Pi power",
            "https://tech.example",
            "Raspberry Pi power voltage and current telemetry " * 4,
            published_date="2026-10-03",
        ),
    ]

    result = source_evaluation.evaluate_candidates(
        "Raspberry Pi power",
        items,
    )

    assert result[0]["title"] == "Raspberry Pi power"
