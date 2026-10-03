from modules.internet import search


class FakeClient:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, query, limit=5):
        self.calls.append((query, limit))
        return self.results[:limit]


def settings(enabled=True, url="https://search.example"):
    return {
        "internet": {
            "enabled": enabled,
            "provider": "searxng",
            "searxng_url": url,
            "timeout_seconds": 15,
            "max_results": 5,
            "language": "sv-SE",
        }
    }


def test_search_is_disabled_by_default_policy():
    result = search.search_web(
        "test",
        settings=settings(enabled=False),
    )

    assert result["available"] is False
    assert "avstängd" in result["reason"]


def test_search_requires_configured_url():
    result = search.search_web(
        "test",
        settings=settings(url=""),
    )

    assert result["available"] is False
    assert "SearXNG" in result["reason"]


def test_search_respects_configured_max_results():
    client = FakeClient(
        [
            {
                "title": str(i),
                "url": f"https://example.com/{i}",
                "snippet": "",
                "engines": [],
                "published_date": None,
            }
            for i in range(10)
        ]
    )

    result = search.search_web(
        "test",
        limit=9,
        settings=settings(),
        client=client,
    )

    assert result["available"] is True
    assert len(result["results"]) == 5
    assert client.calls == [("test", 5)]


def test_search_formatter_lists_url_and_snippet():
    text = search.format_search_results(
        {
            "available": True,
            "query": "test",
            "results": [
                {
                    "title": "Titel",
                    "url": "https://example.com",
                    "snippet": "Kort text",
                    "engines": ["engine"],
                }
            ],
        }
    )

    assert "Titel" in text
    assert "https://example.com" in text
    assert "Kort text" in text


def test_search_tool_declares_parameters():
    schema = search.TOOLS["internet_search"]["parameters"]

    assert "query" in schema["required"]
    assert schema["properties"]["limit"]["type"] == "integer"
