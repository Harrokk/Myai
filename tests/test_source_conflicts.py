from core import source_conflicts


def candidate(url, text):
    return {
        "title": "Battery test",
        "url": url,
        "snippet": text,
        "relevance": 80.0,
        "source_reliability": {"score": 70.0, "reasons": []},
        "information_confidence": {"score": 70.0, "reasons": []},
        "combined_score": 75.0,
    }


def test_detects_numeric_conflict_across_domains():
    items = [
        candidate(
            "https://one.example/a",
            "Battery runtime under load was measured at 10 hours.",
        ),
        candidate(
            "https://two.example/b",
            "Battery runtime under load was measured at 6 hours.",
        ),
    ]

    # unsupported unit should not create false positives yet
    assert source_conflicts.detect_numeric_conflicts(items) == []


def test_detects_supported_unit_conflict():
    items = [
        candidate(
            "https://one.example/a",
            "Power draw under load was measured at 10 W.",
        ),
        candidate(
            "https://two.example/b",
            "Power draw under load was measured at 6 W.",
        ),
    ]

    result = source_conflicts.detect_numeric_conflicts(items)

    assert len(result) == 1
    assert result[0]["unit"] == "w"
    assert result[0]["first_value"] == 10.0
    assert result[0]["second_value"] == 6.0


def test_same_domain_does_not_count_as_independent_conflict():
    items = [
        candidate(
            "https://same.example/a",
            "Power draw under load was 10 W.",
        ),
        candidate(
            "https://same.example/b",
            "Power draw under load was 6 W.",
        ),
    ]

    assert source_conflicts.detect_numeric_conflicts(items) == []


def test_small_difference_within_tolerance_is_not_conflict():
    items = [
        candidate(
            "https://one.example/a",
            "Power draw under load was 10 W.",
        ),
        candidate(
            "https://two.example/b",
            "Power draw under load was 9.7 W.",
        ),
    ]

    assert source_conflicts.detect_numeric_conflicts(items) == []


def test_conflict_penalty_lowers_information_confidence():
    items = [
        candidate(
            "https://one.example/a",
            "Power draw under load was 10 W.",
        ),
        candidate(
            "https://two.example/b",
            "Power draw under load was 6 W.",
        ),
    ]
    conflicts = source_conflicts.detect_numeric_conflicts(items)
    weights = {
        "relevance": 0.40,
        "source_reliability": 0.35,
        "information_confidence": 0.25,
    }

    result = source_conflicts.apply_conflict_penalties(
        items,
        conflicts,
        weights,
        penalty_per_conflict=10,
    )

    assert all(
        item["information_confidence"]["score"] == 60.0
        for item in result
    )
    assert all(item["conflict_count"] == 1 for item in result)
