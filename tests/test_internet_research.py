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
            "deep_verification_enabled": False,
            "deep_blend": 0.40,
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


def deep_settings():
    value = settings()
    value["research"]["deep_verification_enabled"] = True
    return value


def fake_verify(url, query, settings):
    index = int(
        url.split("source", 1)[1].split(".", 1)[0]
    )
    transparency = 40 + index * 10
    evidence = 35 + index * 10

    return {
        "available": True,
        "verification": {
            "url": url,
            "transparency_score": transparency,
            "evidence_signal_score": evidence,
            "assessment_note": "test",
        },
    }


def test_deep_research_verifies_all_five_candidates():
    result = research.research_top_three_data(
        "Raspberry Pi power",
        settings=deep_settings(),
        search_function=fake_search,
        verify_function=fake_verify,
    )

    assert result["deep_verification_enabled"] is True
    assert result["deep_verified_count"] == 5
    assert all(
        item["deep_verification_status"] == "verified"
        for item in result["candidates"]
    )


def test_deep_verification_can_reorder_candidates():
    def uneven_verify(url, query, settings):
        index = int(
            url.split("source", 1)[1].split(".", 1)[0]
        )
        strong = index == 5
        return {
            "available": True,
            "verification": {
                "url": url,
                "transparency_score": 90 if strong else 10,
                "evidence_signal_score": 85 if strong else 10,
                "assessment_note": "test",
            },
        }

    result = research.research_top_three_data(
        "Raspberry Pi power",
        settings=deep_settings(),
        search_function=fake_search,
        verify_function=uneven_verify,
    )

    assert result["top"][0]["url"].startswith(
        "https://source5.example"
    )
    assert (
        result["top"][0]["source_reliability"]["preliminary_score"]
        <= result["top"][0]["source_reliability"]["score"]
    )


def test_failed_deep_verification_keeps_preliminary_score():
    def failing_verify(url, query, settings):
        raise RuntimeError("fetch failed")

    result = research.research_top_three_data(
        "Raspberry Pi power",
        settings=deep_settings(),
        search_function=fake_search,
        verify_function=failing_verify,
    )

    assert result["deep_verified_count"] == 0
    assert all(
        item["deep_verification_status"] == "failed"
        for item in result["candidates"]
    )
    assert all(
        "preliminary_score"
        not in item["source_reliability"]
        for item in result["candidates"]
    )


def test_deep_research_formatter_reports_verification():
    result = research.research_top_three_data(
        "Raspberry Pi power",
        settings=deep_settings(),
        search_function=fake_search,
        verify_function=fake_verify,
    )

    text = research.format_research_top_three(result)

    assert "Djupverifiering: ja" in text
    assert "transparens" in text
    assert "evidenssignaler" in text


def conflict_settings():
    value = settings()
    value["research"]["conflict_penalty"] = 12
    value["research"]["conflict_relative_tolerance"] = 0.05
    return value


def conflict_search(query, limit, settings):
    return {
        "available": True,
        "query": query,
        "results": [
            {
                "title": "Power test A",
                "url": "https://one.example/report",
                "snippet": "Raspberry Pi power draw under load was measured at 10 W.",
                "engines": ["engine"],
                "published_date": "2026-10-03",
            },
            {
                "title": "Power test B",
                "url": "https://two.example/report",
                "snippet": "Raspberry Pi power draw under load was measured at 6 W.",
                "engines": ["engine"],
                "published_date": "2026-10-03",
            },
            {
                "title": "General notes",
                "url": "https://three.example/report",
                "snippet": "Raspberry Pi power measurements and thermal notes.",
                "engines": ["engine"],
                "published_date": "2026-10-03",
            },
        ],
    }


def test_research_detects_numeric_conflicts():
    result = research.research_top_three_data(
        "Raspberry Pi power draw",
        settings=conflict_settings(),
        search_function=conflict_search,
    )

    assert result["conflict_count"] == 1
    affected = [
        item
        for item in result["candidates"]
        if item["conflict_count"] == 1
    ]
    assert len(affected) == 2
    assert all(
        item["information_confidence"]["score"]
        < 75
        for item in affected
    )


def test_research_formatter_warns_about_conflicts():
    result = research.research_top_three_data(
        "Raspberry Pi power draw",
        settings=conflict_settings(),
        search_function=conflict_search,
    )

    text = research.format_research_top_three(result)

    assert "numerisk konflikt" in text
