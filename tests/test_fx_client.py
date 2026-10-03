from core import fx_client


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_frankfurter_client_reads_sek_rate(monkeypatch):
    seen = {}

    def fake_get(url, params, timeout, headers):
        seen["url"] = url
        seen["params"] = params
        return FakeResponse(
            {
                "amount": 1.0,
                "base": "EUR",
                "date": "2026-10-03",
                "rates": {"SEK": 11.25},
            }
        )

    monkeypatch.setattr(
        fx_client.requests,
        "get",
        fake_get,
    )

    client = fx_client.FrankfurterClient(
        "https://fx.example/"
    )
    result = client.rate_to_sek("eur")

    assert result["rate"] == 11.25
    assert result["date"] == "2026-10-03"
    assert seen["url"] == "https://fx.example/latest"
    assert seen["params"] == {
        "from": "EUR",
        "to": "SEK",
    }


def test_sek_identity_rate_does_not_call_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(
        fx_client.requests,
        "get",
        fail,
    )

    client = fx_client.FrankfurterClient()
    result = client.rate_to_sek("SEK")

    assert result["rate"] == 1.0
    assert result["provider"] == "identity"


def test_invalid_currency_code_is_rejected():
    client = fx_client.FrankfurterClient()

    try:
        client.rate_to_sek("EURO")
    except ValueError as error:
        assert "trebokstavskod" in str(error)
    else:
        raise AssertionError("invalid currency should fail")
