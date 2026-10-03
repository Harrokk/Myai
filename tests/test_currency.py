from modules.internet import currency


class FakeFX:
    def rate_to_sek(self, code):
        assert code == "EUR"
        return {
            "base": "EUR",
            "target": "SEK",
            "rate": 11.25,
            "date": "2026-10-03",
            "provider": "frankfurter",
        }


def settings(enabled=True):
    return {
        "internet": {
            "enabled": enabled,
        },
        "shopping": {
            "fx_provider": "frankfurter",
            "frankfurter_url": "https://fx.example",
            "fx_timeout_seconds": 10,
        },
    }


def test_sek_is_identity_without_network():
    result = currency.convert_amount_to_sek(
        100,
        "SEK",
        settings=settings(enabled=False),
        client=object(),
    )

    assert result["amount_sek"] == 100
    assert result["rate"] == 1.0


def test_currency_conversion_uses_real_rate_object():
    result = currency.convert_amount_to_sek(
        10,
        "EUR",
        settings=settings(),
        client=FakeFX(),
    )

    assert result["amount_sek"] == 112.5
    assert result["rate_date"] == "2026-10-03"


def test_currency_conversion_requires_internet_for_non_sek():
    result = currency.convert_amount_to_sek(
        10,
        "EUR",
        settings=settings(enabled=False),
        client=FakeFX(),
    )

    assert result["available"] is False
    assert "avstängd" in result["reason"]


def test_negative_amount_is_rejected():
    try:
        currency.convert_amount_to_sek(
            -1,
            "EUR",
            settings=settings(),
            client=FakeFX(),
        )
    except ValueError as error:
        assert "negativt" in str(error)
    else:
        raise AssertionError("negative amount should fail")


def test_currency_tool_declares_parameters():
    schema = currency.TOOLS["currency_to_sek"]["parameters"]

    assert schema["required"] == ["amount", "currency"]
