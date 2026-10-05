from copy import deepcopy
from datetime import date

import pytest

from core.config import DEFAULT_SETTINGS
from modules.internet import fx


ECB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope
    xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
    xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-10-05">
      <Cube currency="USD" rate="1.1000"/>
      <Cube currency="GBP" rate="0.9000"/>
      <Cube currency="SEK" rate="11.0000"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""


def settings(
    *,
    enabled=True,
):
    value = deepcopy(
        DEFAULT_SETTINGS
    )
    value["internet"][
        "enabled"
    ] = True
    value["fx"][
        "enabled"
    ] = enabled
    return value


def fake_fetch(
    url,
    settings=None,
):
    return {
        "available": True,
        "requested_url": url,
        "final_url": (
            "https://www.ecb.europa.eu/stats/eurofxref/"
            "eurofxref-daily.xml"
        ),
        "status_code": 200,
        "content_type": "text/xml",
        "title": "",
        "text": ECB_XML,
        "metadata": {},
        "canonical_url": "",
        "external_links": [],
        "redirects": 0,
        "truncated": False,
        "max_chars": 20_000,
    }


def test_parse_ecb_reference_xml_reads_date_and_rates():
    result = fx.parse_ecb_reference_xml(
        ECB_XML
    )

    assert result[
        "reference_date"
    ] == date(
        2026,
        10,
        5,
    )
    assert result[
        "rates_per_eur"
    ][
        "EUR"
    ] == 1.0
    assert result[
        "rates_per_eur"
    ][
        "USD"
    ] == 1.1
    assert result[
        "rates_per_eur"
    ][
        "SEK"
    ] == 11.0


def test_verified_usd_to_sek_uses_ecb_cross_rate():
    quote = fx.get_verified_fx_quote(
        "USD",
        "SEK",
        settings=settings(),
        fetch_function=fake_fetch,
        now=date(
            2026,
            10,
            5,
        ),
    )

    assert quote[
        "available"
    ] is True
    assert quote[
        "verified"
    ] is True
    assert quote[
        "provider"
    ] == "ecb"
    assert quote[
        "pair"
    ] == "USD/SEK"
    assert quote[
        "rate"
    ] == 10.0
    assert quote[
        "reference_date"
    ] == "2026-10-05"
    assert quote[
        "source_url"
    ].startswith(
        "https://www.ecb.europa.eu/"
    )
    assert fx.convert_verified_amount(
        12.5,
        quote,
    ) == 125.0


def test_verified_eur_to_sek_uses_eur_base_rate():
    quote = fx.get_verified_fx_quote(
        "EUR",
        "SEK",
        settings=settings(),
        fetch_function=fake_fetch,
        now=date(
            2026,
            10,
            5,
        ),
    )

    assert quote[
        "rate"
    ] == 11.0


def test_stale_ecb_rate_is_rejected():
    value = settings()
    value["fx"][
        "max_age_days"
    ] = 3

    quote = fx.get_verified_fx_quote(
        "USD",
        "SEK",
        settings=value,
        fetch_function=fake_fetch,
        now=date(
            2026,
            10,
            10,
        ),
    )

    assert quote[
        "available"
    ] is False
    assert quote[
        "verified"
    ] is False
    assert "för gammal" in quote[
        "reason"
    ]


def test_future_ecb_rate_is_rejected():
    quote = fx.get_verified_fx_quote(
        "USD",
        "SEK",
        settings=settings(),
        fetch_function=fake_fetch,
        now=date(
            2026,
            10,
            4,
        ),
    )

    assert quote[
        "available"
    ] is False
    assert "framtiden" in quote[
        "reason"
    ]


def test_redirect_away_from_ecb_is_rejected():
    def bad_fetch(
        url,
        settings=None,
    ):
        result = fake_fetch(
            url,
            settings=settings,
        )
        result[
            "final_url"
        ] = "https://example.com/rates.xml"
        return result

    with pytest.raises(
        ValueError,
        match="ecb.europa.eu",
    ):
        fx.get_verified_fx_quote(
            "USD",
            "SEK",
            settings=settings(),
            fetch_function=bad_fetch,
            now=date(
                2026,
                10,
                5,
            ),
        )


def test_missing_currency_is_not_invented():
    quote = fx.get_verified_fx_quote(
        "CAD",
        "SEK",
        settings=settings(),
        fetch_function=fake_fetch,
        now=date(
            2026,
            10,
            5,
        ),
    )

    assert quote[
        "available"
    ] is False
    assert "CAD" in quote[
        "reason"
    ]


def test_disabled_fx_refuses_non_identity_conversion():
    quote = fx.get_verified_fx_quote(
        "USD",
        "SEK",
        settings=settings(
            enabled=False
        ),
        fetch_function=fake_fetch,
        now=date(
            2026,
            10,
            5,
        ),
    )

    assert quote[
        "available"
    ] is False
    assert quote[
        "verified"
    ] is False


def test_identity_pair_needs_no_external_rate():
    quote = fx.get_verified_fx_quote(
        "SEK",
        "SEK",
        settings=settings(
            enabled=False
        ),
    )

    assert quote[
        "verified"
    ] is True
    assert quote[
        "rate"
    ] == 1.0
    assert quote[
        "provider"
    ] == "identity"


def test_unverified_quote_cannot_convert_amount():
    with pytest.raises(
        ValueError,
        match="Verifierad växelkurs saknas",
    ):
        fx.convert_verified_amount(
            10,
            {
                "available": False,
                "verified": False,
            },
        )
