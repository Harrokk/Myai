from modules.internet import evaluation


def candidate(
    name,
    relevance=80,
    source=80,
    confidence=80,
    practicality=80,
    **extra,
):
    item = {
        "name": name,
        "relevance": relevance,
        "source_reliability": source,
        "information_confidence": confidence,
        "practicality": practicality,
    }
    item.update(extra)
    return item


def test_five_candidates_produce_top_three():
    result = evaluation.select_top_candidates(
        [
            candidate("A", 95, 95, 95, 90),
            candidate("B", 90, 90, 90, 90),
            candidate("C", 85, 85, 85, 85),
            candidate("D", 70, 70, 70, 70),
            candidate("E", 60, 60, 60, 60),
        ],
        settings={},
    )

    assert result["evaluated_count"] == 5
    assert [item["name"] for item in result["top_candidates"]] == [
        "A",
        "B",
        "C",
    ]


def test_source_reliability_and_information_confidence_stay_separate():
    result = evaluation.evaluate_candidate(
        candidate(
            "Source",
            source=92,
            confidence=61,
        ),
        settings={},
    )

    assert result["source_reliability"] == 92.0
    assert result["information_confidence"] == 61.0
    assert result["source_reliability"] != result["information_confidence"]


def test_low_confidence_candidate_is_excluded():
    result = evaluation.select_top_candidates(
        [
            candidate("Weak", confidence=20),
            candidate("Strong", confidence=90),
        ],
        settings={},
    )

    assert [item["name"] for item in result["top_candidates"]] == [
        "Strong"
    ]
    assert result["excluded_candidates"][0]["name"] == "Weak"
    assert "informationskonfidens" in (
        result["excluded_candidates"][0]["exclusion_reasons"][0]
    )


def test_critical_warning_excludes_candidate():
    result = evaluation.evaluate_candidate(
        candidate(
            "Risky",
            critical_warning=True,
            warning_flags=["oklar avsändare"],
        ),
        settings={},
    )

    assert result["eligible"] is False
    assert "kritisk varningssignal" in result["exclusion_reasons"]


def test_warning_penalty_can_change_order():
    clean = candidate("Clean", relevance=85, source=85, confidence=85)
    warned = candidate(
        "Warned",
        relevance=90,
        source=90,
        confidence=90,
        warning_flags=["varning 1", "varning 2"],
    )

    result = evaluation.select_top_candidates(
        [warned, clean],
        settings={},
    )

    assert result["top_candidates"][0]["name"] == "Clean"
    assert (
        result["evaluated_candidates"][0]["warning_penalty"]
        == 10.0
    )


def test_fewer_than_five_is_reported():
    result = evaluation.select_top_candidates(
        [candidate("A"), candidate("B")],
        settings={},
    )

    assert result["basis_fewer_than_limit"] is True
    assert result["evaluated_count"] == 2


def test_more_than_limit_is_truncated_explicitly():
    items = [candidate(str(index)) for index in range(7)]

    result = evaluation.select_top_candidates(items, settings={})

    assert result["input_count"] == 7
    assert result["evaluated_count"] == 5
    assert result["truncated_input"] is True


def test_practicality_is_optional_and_weights_renormalize():
    item = candidate("No practicality")
    del item["practicality"]

    result = evaluation.evaluate_candidate(item, settings={})

    assert result["practicality"] is None
    assert result["selection_score"] == 80.0


def test_invalid_score_is_rejected():
    try:
        evaluation.evaluate_candidate(
            candidate("Bad", relevance=120),
            settings={},
        )
    except ValueError as error:
        assert "relevance" in str(error)
    else:
        raise AssertionError("Out-of-range score should fail")


def test_configurable_weights_affect_selection():
    settings = {
        "research": {
            "weights": {
                "relevance": 0,
                "source_reliability": 1,
                "information_confidence": 0,
                "practicality": 0,
            }
        }
    }

    result = evaluation.select_top_candidates(
        [
            candidate("High relevance", relevance=100, source=60),
            candidate("High source", relevance=60, source=95),
        ],
        settings=settings,
    )

    assert result["top_candidates"][0]["name"] == "High source"


def test_formatter_states_internal_heuristic_not_probability():
    result = evaluation.select_top_candidates(
        [candidate("A")],
        settings={},
    )

    text = evaluation.format_top_candidates(result)

    assert "färre än målet" in text
    assert "intern heuristik" in text
    assert "inte en matematisk sannolikhet" in text
