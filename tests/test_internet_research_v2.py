from modules.internet import research


def settings():
    return {
        "research": {
            "candidate_limit": 5,
            "top_n": 3,
            "min_source_reliability": 20,
            "min_information_confidence": 10,
            "min_relevance": 10,
            "warning_penalty_each": 5,
            "max_warning_penalty": 20,
            "weights": {
                "relevance": 0.3,
                "source_reliability": 0.3,
                "information_confidence": 0.3,
                "practicality": 0.1,
            },
        },
        "internet": {
            "enabled": True,
            "provider": "searxng",
            "searxng_url": "http://localhost:8080",
            "timeout_seconds": 15,
            "max_results": 5,
            "language": "sv-SE",
            "safesearch": 1,
            "max_page_bytes": 1_000_000,
            "max_page_chars": 20_000,
            "max_redirects": 5,
        },
    }


def fake_search(query, settings=None):
    return {
        "success": True,
        "disabled": False,
        "provider": "fake",
        "query": query,
        "results": [
            {
                "title": f"Raspberry Pi power report {index}",
                "url": f"https://source{index}.example/report",
                "snippet": "Raspberry Pi power draw measurements under load.",
                "engine": "fake",
                "published_date": "2026-10-03",
            }
            for index in range(1, 6)
        ],
        "error": None,
    }


def fake_fetch(url, settings=None):
    number = int(url.split("source", 1)[1].split(".", 1)[0])
    watts = 10 if number != 2 else 6

    return {
        "available": True,
        "requested_url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "title": f"Raspberry Pi power report {number}",
        "text": (
            "Method and data results with references and limitations. "
            f"Raspberry Pi power draw under load was measured at {watts} W. "
        ) * 30,
        "metadata": {
            "author": f"Author {number}",
            "article:published_time": "2026-10-03",
            "description": "Raspberry Pi power measurements under load",
            "og:site_name": f"Source {number}",
        },
        "canonical_url": url,
        "external_links": ["https://reference.example/evidence"],
        "redirects": 0,
        "truncated": False,
        "max_chars": 20_000,
    }


def test_research_fetches_five_validates_and_returns_top_three():
    result = research.research_top_candidates_data(
        "Raspberry Pi power draw",
        settings=settings(),
        search_function=fake_search,
        fetch_function=fake_fetch,
    )

    assert result["available"] is True
    assert result["candidate_count"] == 5
    assert result["validated_count"] == 5
    assert len(result["top_candidates"]) == 3
    assert result["conflicts"]


def test_research_conflict_reduces_confidence():
    result = research.research_top_candidates_data(
        "Raspberry Pi power draw",
        settings=settings(),
        search_function=fake_search,
        fetch_function=fake_fetch,
    )

    conflicted = [
        item
        for item in result["evaluated_candidates"]
        if item.get("conflict_count")
    ]

    assert conflicted
    assert all(item["warning_flags"] for item in conflicted)


def test_research_excludes_page_that_cannot_be_verified():
    def failing_fetch(url, settings=None):
        if "source3" in url:
            return {
                "available": False,
                "reason": "test failure",
            }
        return fake_fetch(url, settings=settings)

    result = research.research_top_candidates_data(
        "Raspberry Pi power draw",
        settings=settings(),
        search_function=fake_search,
        fetch_function=failing_fetch,
    )

    excluded_urls = {
        item.get("url")
        for item in result["excluded_candidates"]
    }

    assert "https://source3.example/report" in excluded_urls


def test_research_reports_fewer_than_five_candidates():
    def short_search(query, settings=None):
        data = fake_search(query, settings=settings)
        data["results"] = data["results"][:2]
        return data

    result = research.research_top_candidates_data(
        "Raspberry Pi power draw",
        settings=settings(),
        search_function=short_search,
        fetch_function=fake_fetch,
    )

    assert result["candidate_count"] == 2
    assert result["basis_fewer_than_limit"] is True


def test_research_formatter_labels_heuristics():
    result = research.research_top_candidates_data(
        "Raspberry Pi power draw",
        settings=settings(),
        search_function=fake_search,
        fetch_function=fake_fetch,
    )
    text = research.format_research_top_candidates(result)

    assert "Validerat underlag: 5" in text
    assert "Numeriska källkonflikter" in text
    assert "inte sannolikheter" in text


def test_research_tool_is_query_aware():
    assert research.TOOLS["research_top_three"]["pass_user_input"] is True
