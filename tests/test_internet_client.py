from core import internet_client


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_searxng_client_normalizes_results(monkeypatch):
    seen = {}

    def fake_get(url, params, timeout, headers):
        seen["url"] = url
        seen["params"] = params
        seen["timeout"] = timeout
        seen["headers"] = headers
        return FakeResponse(
            {
                "results": [
                    {
                        "title": "Resultat 1",
                        "url": "https://example.com/1",
                        "content": "Sammanfattning",
                        "engines": ["duckduckgo"],
                    },
                    {
                        "title": "Resultat 2",
                        "url": "https://example.com/2",
                        "content": "Mer text",
                    },
                ]
            }
        )

    monkeypatch.setattr(
        internet_client.requests,
        "get",
        fake_get,
    )

    client = internet_client.SearXNGClient(
        "https://search.example/",
        timeout_seconds=7,
        language="sv-SE",
    )
    result = client.search("raspberry pi", limit=1)

    assert len(result) == 1
    assert result[0]["title"] == "Resultat 1"
    assert result[0]["url"] == "https://example.com/1"
    assert result[0]["engines"] == ["duckduckgo"]
    assert seen["url"] == "https://search.example/search"
    assert seen["params"]["q"] == "raspberry pi"
    assert seen["params"]["format"] == "json"
    assert seen["timeout"] == 7


def test_searxng_client_requires_query():
    client = internet_client.SearXNGClient(
        "https://search.example"
    )

    try:
        client.search(" ")
    except ValueError as error:
        assert "tom" in str(error)
    else:
        raise AssertionError("Empty query should fail")


def test_searxng_client_skips_results_without_url(monkeypatch):
    monkeypatch.setattr(
        internet_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            {
                "results": [
                    {"title": "Ingen URL"},
                    {
                        "title": "Giltig",
                        "url": "https://example.com",
                    },
                ]
            }
        ),
    )

    client = internet_client.SearXNGClient(
        "https://search.example"
    )
    result = client.search("test")

    assert [item["title"] for item in result] == ["Giltig"]
