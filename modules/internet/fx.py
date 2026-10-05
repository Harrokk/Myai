from copy import deepcopy
from datetime import date, datetime, timezone
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from core.config import load_settings
from modules.internet.fetch import fetch_public_page


ECB_ALLOWED_HOSTS = {
    "www.ecb.europa.eu",
    "ecb.europa.eu",
}


def _currency_code(
    value,
):
    code = str(
        value
        or ""
    ).strip().upper()

    if (
        len(
            code
        )
        != 3
        or not code.isalpha()
    ):
        raise ValueError(
            "Valutakod måste bestå av tre bokstäver."
        )

    return code


def _reference_date(
    value,
):
    try:
        return date.fromisoformat(
            str(
                value
            )
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "ECB-feed saknar giltigt referensdatum."
        ) from error


def parse_ecb_reference_xml(
    text,
):
    try:
        root = ET.fromstring(
            str(
                text
                or ""
            )
        )
    except ET.ParseError as error:
        raise ValueError(
            "ECB-feed innehåller ogiltig XML."
        ) from error

    reference = None
    rates = {
        "EUR": 1.0,
    }

    for element in root.iter():
        attributes = element.attrib

        if (
            reference is None
            and attributes.get(
                "time"
            )
        ):
            reference = _reference_date(
                attributes[
                    "time"
                ]
            )

        currency = attributes.get(
            "currency"
        )
        rate = attributes.get(
            "rate"
        )

        if not (
            currency
            and rate
        ):
            continue

        code = _currency_code(
            currency
        )

        try:
            number = float(
                rate
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                (
                    "ECB-feed innehåller ogiltig kurs "
                    f"för {code}."
                )
            ) from error

        if number <= 0:
            raise ValueError(
                (
                    "ECB-feed innehåller icke-positiv kurs "
                    f"för {code}."
                )
            )

        rates[
            code
        ] = number

    if reference is None:
        raise ValueError(
            "ECB-feed saknar referensdatum."
        )

    if len(
        rates
    ) <= 1:
        raise ValueError(
            "ECB-feed saknar valutakurser."
        )

    return {
        "reference_date": reference,
        "rates_per_eur": rates,
    }


def _today_utc(
    now=None,
):
    if now is None:
        return datetime.now(
            timezone.utc
        ).date()

    if isinstance(
        now,
        datetime,
    ):
        return now.date()

    if isinstance(
        now,
        date,
    ):
        return now

    raise ValueError(
        "now måste vara date eller datetime."
    )


def _validate_ecb_url(
    url,
):
    parsed = urlparse(
        str(
            url
            or ""
        )
    )
    host = (
        parsed.hostname
        or ""
    ).lower()

    if parsed.scheme != "https":
        raise ValueError(
            "ECB FX-källa måste använda https."
        )

    if host not in ECB_ALLOWED_HOSTS:
        raise ValueError(
            "ECB FX-källa måste ligga på ecb.europa.eu."
        )

    return str(
        url
    )


def _call_fetch(
    fetch_function,
    url,
    settings,
):
    try:
        return fetch_function(
            url,
            settings=settings,
        )
    except TypeError:
        return fetch_function(
            url
        )


def get_verified_fx_quote(
    source_currency,
    target_currency="SEK",
    *,
    settings=None,
    fetch_function=None,
    now=None,
):
    settings = (
        settings
        or load_settings()
    )
    config = settings.get(
        "fx",
        {},
    )
    source = _currency_code(
        source_currency
    )
    target = _currency_code(
        target_currency
    )

    if source == target:
        return {
            "available": True,
            "verified": True,
            "provider": "identity",
            "pair": (
                f"{source}/{target}"
            ),
            "source_currency": source,
            "target_currency": target,
            "rate": 1.0,
            "reference_date": None,
            "age_days": 0,
            "source_url": None,
            "source_rate_per_eur": None,
            "target_rate_per_eur": None,
            "assessment_note": (
                "Ingen valutakonvertering behövs."
            ),
        }

    if not config.get(
        "enabled",
        False,
    ):
        return {
            "available": False,
            "verified": False,
            "reason": (
                "Verifierad växelkurs är avstängd i konfigurationen."
            ),
            "source_currency": source,
            "target_currency": target,
        }

    provider = str(
        config.get(
            "provider",
            "ecb",
        )
        or ""
    ).strip().lower()

    if provider != "ecb":
        return {
            "available": False,
            "verified": False,
            "reason": (
                f"FX-provider stöds inte: {provider or 'saknas'}."
            ),
            "source_currency": source,
            "target_currency": target,
        }

    url = _validate_ecb_url(
        config.get(
            "ecb_url",
            "",
        )
    )
    active_fetch = (
        fetch_function
        or fetch_public_page
    )
    page = _call_fetch(
        active_fetch,
        url,
        settings,
    )

    if not page.get(
        "available"
    ):
        return {
            "available": False,
            "verified": False,
            "reason": page.get(
                "reason",
                "ECB-kursen kunde inte hämtas.",
            ),
            "source_currency": source,
            "target_currency": target,
        }

    final_url = (
        page.get(
            "final_url"
        )
        or url
    )
    _validate_ecb_url(
        final_url
    )
    parsed = parse_ecb_reference_xml(
        page.get(
            "text",
            "",
        )
    )
    reference = parsed[
        "reference_date"
    ]
    today = _today_utc(
        now
    )
    age_days = (
        today
        - reference
    ).days

    try:
        max_age_days = int(
            config.get(
                "max_age_days",
                7,
            )
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "fx.max_age_days måste vara ett heltal."
        ) from error

    if age_days < 0:
        return {
            "available": False,
            "verified": False,
            "reason": (
                "ECB-kursens referensdatum ligger i framtiden."
            ),
            "source_currency": source,
            "target_currency": target,
            "reference_date": reference.isoformat(),
        }

    if age_days > max_age_days:
        return {
            "available": False,
            "verified": False,
            "reason": (
                "ECB-kursen är för gammal för konvertering."
            ),
            "source_currency": source,
            "target_currency": target,
            "reference_date": reference.isoformat(),
            "age_days": age_days,
        }

    rates = parsed[
        "rates_per_eur"
    ]

    if source not in rates:
        return {
            "available": False,
            "verified": False,
            "reason": (
                f"ECB-feed saknar kurs för {source}."
            ),
            "source_currency": source,
            "target_currency": target,
            "reference_date": reference.isoformat(),
        }

    if target not in rates:
        return {
            "available": False,
            "verified": False,
            "reason": (
                f"ECB-feed saknar kurs för {target}."
            ),
            "source_currency": source,
            "target_currency": target,
            "reference_date": reference.isoformat(),
        }

    source_per_eur = float(
        rates[
            source
        ]
    )
    target_per_eur = float(
        rates[
            target
        ]
    )
    rate = (
        target_per_eur
        / source_per_eur
    )

    return {
        "available": True,
        "verified": True,
        "provider": "ecb",
        "pair": (
            f"{source}/{target}"
        ),
        "source_currency": source,
        "target_currency": target,
        "rate": round(
            rate,
            10,
        ),
        "reference_date": (
            reference.isoformat()
        ),
        "age_days": age_days,
        "source_url": final_url,
        "source_rate_per_eur": (
            source_per_eur
        ),
        "target_rate_per_eur": (
            target_per_eur
        ),
        "assessment_note": (
            "ECB:s euroreferenskurser används som informationsdata. "
            "Detta är inte ett transaktionspris eller en garanti för "
            "den kurs som en bank eller betalningsleverantör erbjuder."
        ),
    }


def convert_verified_amount(
    amount,
    quote,
):
    try:
        value = float(
            amount
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "Beloppet måste vara numeriskt."
        ) from error

    if value < 0:
        raise ValueError(
            "Beloppet får inte vara negativt."
        )

    if not isinstance(
        quote,
        dict,
    ) or not quote.get(
        "available"
    ) or not quote.get(
        "verified"
    ):
        raise ValueError(
            "Verifierad växelkurs saknas."
        )

    try:
        rate = float(
            quote[
                "rate"
            ]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "Verifierad växelkurs saknar giltig rate."
        ) from error

    if rate <= 0:
        raise ValueError(
            "Verifierad växelkurs måste vara positiv."
        )

    return round(
        value
        * rate,
        2,
    )


def copy_quote(
    quote,
):
    return deepcopy(
        quote
    )
