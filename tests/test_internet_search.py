from modules.internet import search


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "timeout": timeout,
            }
        )
        return FakeResponse(self.payload)


def settings(enabled=True, max_results=5):
    return {
        "internet": {
            "enabled": enabled,
            "provider": "searxng",
            "searxng_url": "http://localhost:8080",
            "timeout_seconds": 12,
            "max_results": max_results,
            "language": "sv-SE",
            "safesearch": 1,
        }
    }


def test_search_is_disabled_without_request():
    class BrokenSession:
        def get(self, *args, **kwargs):
            raise AssertionError("Request should not be sent")

    result = search.search_web(
        "test",
        settings=settings(enabled=False),
        session=BrokenSession(),
    )

    assert result["disabled"] is True


def test_extract_search_query_strips_explicit_prefix():
    assert search.extract_search_query(
        "Sök på internet efter Raspberry Pi 5"
    ) == "Raspberry Pi 5"


def test_searxng_search_normalizes_and_limits_results():
    session = FakeSession(
        {
            "results": [
                {
                    "title": "A",
                    "url": "https://a.example",
                    "content": "Resultat A",
                    "engine": "brave",
                },
                {
                    "title": "B",
                    "url": "https://b.example",
                    "content": "Resultat B",
                    "engines": ["duckduckgo"],
                },
                {
                    "title": "C",
                    "url": "https://c.example",
                },
            ]
        }
    )

    result = search.search_web(
        "raspberry pi",
        settings=settings(max_results=2),
        session=session,
    )

    assert result["success"] is True
    assert [item["title"] for item in result["results"]] == ["A", "B"]
    assert result["results"][1]["engine"] == "duckduckgo"
    assert session.calls[0]["url"] == "http://localhost:8080/search"
    assert session.calls[0]["params"]["q"] == "raspberry pi"
    assert session.calls[0]["params"]["format"] == "json"
    assert session.calls[0]["timeout"] == 12


def test_invalid_results_payload_is_rejected():
    session = FakeSession({"results": "not-a-list"})

    try:
        search.search_web(
            "test",
            settings=settings(),
            session=session,
        )
    except ValueError as error:
        assert "results-lista" in str(error)
    else:
        raise AssertionError("Invalid results should fail")


def test_unsupported_provider_is_explicit():
    result = search.search_web(
        "test",
        settings={
            "internet": {
                "enabled": True,
                "provider": "unknown",
                "max_results": 5,
                "timeout_seconds": 10,
                "safesearch": 1,
            }
        },
        session=FakeSession({}),
    )

    assert result["success"] is False
    assert "stöds inte" in result["error"]


def test_formatter_marks_results_as_raw_unvalidated_candidates():
    text = search.format_search_results(
        {
            "success": True,
            "disabled": False,
            "provider": "searxng",
            "query": "test",
            "results": [
                {
                    "title": "A",
                    "url": "https://a.example",
                    "snippet": "text",
                    "engine": "brave",
                    "published_date": None,
                }
            ],
        }
    )

    assert "A" in text
    assert "https://a.example" in text
    assert "råa kandidater" in text
    assert "ännu inte automatiskt källgranskats" in text
