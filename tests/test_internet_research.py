from modules.internet import research


def settings():
    return {
        "internet": {
            "enabled": True,
            "provider": "searxng",
            "searxng_url": "https://search.example",
            "timeout_seconds": 15,
            "max_results": 5,
            "language": "sv-SE",
        },
        "research": {
            "candidate_limit": 5,
            "top_results": 3,
            "weights": {
                "relevance": 0.40,
                "source_reliability": 0.35,
                "information_confidence": 0.25,
            },
        },
    }


def fake_search(query, limit, settings):
    return {
        "available": True,
        "query": query,
        "results": [
            {
                "title": f"Raspberry Pi power {index}",
                "url": f"https://source{index}.example/report",
                "snippet": (
                    "Raspberry Pi power voltage telemetry "
                    "under load with measurements and notes."
                ),
                "engines": ["engine"],
                "published_date": "2026-10-03",
            }
            for index in range(1, 6)
        ],
    }


def test_research_uses_five_candidates_and_returns_three():
    result = research.research_top_three_data(
        "Raspberry Pi power",
        settings=settings(),
        search_function=fake_search,
    )

    assert result["available"] is True
    assert result["candidate_count"] == 5
    assert len(result["top"]) == 3


def test_research_formatter_labels_scores_as_internal():
    result = research.research_top_three_data(
        "Raspberry Pi power",
        settings=settings(),
        search_function=fake_search,
    )

    text = research.format_research_top_three(result)

    assert "Källans tillförlitlighet" in text
    assert "Informationens konfidens" in text
    assert "interna heuristiska" in text


def test_research_reports_fewer_than_five_candidates():
    def short_search(query, limit, settings):
        data = fake_search(query, limit, settings)
        data["results"] = data["results"][:2]
        return data

    result = research.research_top_three_data(
        "Raspberry Pi power",
        settings=settings(),
        search_function=short_search,
    )
    text = research.format_research_top_three(result)

    assert result["candidate_count"] == 2
    assert "färre än fem" in text


def test_research_tool_declares_query_parameter():
    schema = research.TOOLS["research_top_three"]["parameters"]

    assert schema["required"] == ["query"]
