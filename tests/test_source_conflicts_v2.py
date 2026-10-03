from core import source_conflicts


def candidate(url, text, confidence=70.0):
    return {
        "name": url,
        "title": "Power test",
        "url": url,
        "snippet": "",
        "page_text": text,
        "relevance": 80.0,
        "source_reliability": 70.0,
        "information_confidence": confidence,
        "warning_flags": [],
    }


def test_detects_supported_unit_conflict_across_domains():
    items = [
        candidate(
            "https://one.example/a",
            "Raspberry Pi power draw under load was measured at 10 W.",
        ),
        candidate(
            "https://two.example/b",
            "Raspberry Pi power draw under load was measured at 6 watt.",
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


def test_conflict_penalty_lowers_numeric_information_confidence():
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

    result = source_conflicts.apply_conflict_penalties(
        items,
        conflicts,
        penalty_per_conflict=10,
    )

    assert all(item["information_confidence"] == 60.0 for item in result)
    assert all(item["conflict_count"] == 1 for item in result)
    assert all(item["warning_flags"] for item in result)
