"""No-network regression: internet tools never reveal raw transport errors."""
from modules.internet import search, research


def test_search_tool_redacts_endpoint_and_token(monkeypatch):
    marker = "Bearer PRIVATE_AUTH_TOKEN /home/arduino/private/account"
    def fail(_query):
        raise RuntimeError(marker)
    monkeypatch.setattr(search, "search_web", fail)
    message = search.internet_search("sök på internet efter test")
    assert message == "Internetsökningen misslyckades: feltext dold."
    assert marker not in message


def test_research_tool_redacts_fetch_failure(monkeypatch):
    marker = "secret DNS peer 10.0.0.2/private"
    def fail(_query):
        raise OSError(marker)
    monkeypatch.setattr(research, "research_top_candidates_data", fail)
    message = research.research_top_three("undersök AI")
    assert message == "Research kunde inte köras: feltext dold."
    assert marker not in message
