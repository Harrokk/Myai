"""No-network regression: internet tools never reveal raw transport errors."""
from modules.internet import search, research, shopping, weather, verify


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



def test_shopping_tool_hides_raw_offer_backend_error(monkeypatch):
    marker = "SHOP_API_KEY_BEWARE"
    def fail(_query):
        raise RuntimeError(marker)
    monkeypatch.setattr(shopping, "shopping_compare_data", fail)
    result = shopping.shopping_compare_sweden("jämför butiker för elektronik")
    assert result == "Prisjämförelsen kunde inte köras: feltext dold."
    assert marker not in result


def test_weather_tool_hides_network_error_and_location(monkeypatch):
    marker = "/home/arduino/private/home-geolocation"
    def fail(_input):
        raise OSError(marker)
    monkeypatch.setattr(weather, "weather_data", fail)
    message = weather.weather_forecast("väder i Stockholm")
    assert message == "Vädret kunde inte hämtas: feltext dold."
    assert marker not in message


def test_source_verification_tool_hides_raw_peer_ip_and_token(monkeypatch):
    marker = "private Peer 10.0.0.1 Authorization: secret"
    def fail(*args, **kwargs):
        raise RuntimeError(marker)
    monkeypatch.setattr(verify, "verify_source_page", fail)
    text = verify.source_verify_page("kontrollera https://example.com/test")
    assert text == "Källgranskningen kunde inte köras: feltext dold."
    assert marker not in text
