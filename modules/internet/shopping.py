import re
from urllib.parse import urlparse

from core.config import load_settings
from core.page_verification import verify_page_content
from modules.internet.price_compare import (
    compare_sweden_prices,
    format_sweden_price_comparison,
)
from modules.internet.research import metadata_relevance
from modules.internet.search import search_web
from modules.internet.fetch import fetch_public_page


_PRICE_KEYS = (
    "product:price:amount",
    "og:price:amount",
    "price",
)
_CURRENCY_KEYS = (
    "product:price:currency",
    "og:price:currency",
    "pricecurrency",
    "currency",
)
_AVAILABILITY_KEYS = (
    "product:availability",
    "og:availability",
    "availability",
)


def extract_shopping_query(user_input):
    text = str(
        user_input
        or ""
    ).strip()
    lowered = text.lower()
    prefixes = (
        "jämför pris på ",
        "jämför priser på ",
        "prisjämför ",
        "hitta billigaste ",
        "hitta bästa pris på ",
        "sök pris på ",
        "compare price for ",
        "compare prices for ",
        "find cheapest ",
        "find best price for ",
    )

    for prefix in prefixes:
        if lowered.startswith(
            prefix
        ):
            return text[
                len(
                    prefix
                ):
            ].strip()

    return text


def _first_metadata(
    metadata,
    keys,
):
    metadata = (
        metadata
        if isinstance(
            metadata,
            dict,
        )
        else {}
    )

    for key in keys:
        value = metadata.get(
            key
        )

        if value not in (
            None,
            "",
        ):
            return str(
                value
            ).strip()

    return ""


def _money_value(
    value,
):
    if value is None:
        return None

    text = str(
        value
    ).strip()
    text = (
        text.replace(
            "\u00a0",
            " ",
        )
        .replace(
            "SEK",
            "",
        )
        .replace(
            "sek",
            "",
        )
        .replace(
            "kr",
            "",
        )
        .strip()
    )
    text = re.sub(
        r"\s+",
        "",
        text,
    )

    if not text:
        return None

    if (
        "," in text
        and "." in text
    ):
        if text.rfind(
            ","
        ) > text.rfind(
            "."
        ):
            text = text.replace(
                ".",
                "",
            ).replace(
                ",",
                ".",
            )
        else:
            text = text.replace(
                ",",
                "",
            )
    elif "," in text:
        text = text.replace(
            ",",
            ".",
        )

    try:
        amount = float(
            text
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if amount < 0:
        return None

    return round(
        amount,
        2,
    )


def _availability(
    raw,
    text,
):
    value = str(
        raw
        or ""
    ).lower()
    body = str(
        text
        or ""
    ).lower()

    if any(
        phrase in value
        for phrase in (
            "outofstock",
            "out_of_stock",
            "out of stock",
            "soldout",
            "sold out",
        )
    ) or any(
        phrase in body
        for phrase in (
            "slut i lager",
            "ej i lager",
            "out of stock",
            "sold out",
        )
    ):
        return "out_of_stock"

    if any(
        phrase in value
        for phrase in (
            "limited",
            "lowstock",
            "low stock",
        )
    ) or any(
        phrase in body
        for phrase in (
            "begränsat lager",
            "få kvar",
            "limited stock",
            "low stock",
        )
    ):
        return "limited"

    if any(
        phrase in value
        for phrase in (
            "instock",
            "in_stock",
            "in stock",
        )
    ) or any(
        phrase in body
        for phrase in (
            "i lager",
            "finns i lager",
            "in stock",
        )
    ):
        return "in_stock"

    return "unknown"


def _shipping_to_sweden(
    text,
):
    body = str(
        text
        or ""
    ).lower()

    negative = (
        "levererar inte till sverige",
        "skickar inte till sverige",
        "ingen leverans till sverige",
        "does not ship to sweden",
        "no shipping to sweden",
    )
    positive = (
        "leverans till sverige",
        "levererar till sverige",
        "skickar till sverige",
        "frakt till sverige",
        "ships to sweden",
        "shipping to sweden",
        "delivery to sweden",
    )

    if any(
        phrase in body
        for phrase in negative
    ):
        return False

    if any(
        phrase in body
        for phrase in positive
    ):
        return True

    return None


def _shipping_cost(
    text,
):
    body = str(
        text
        or ""
    ).lower()

    if any(
        phrase in body
        for phrase in (
            "fri frakt",
            "gratis frakt",
            "free shipping",
            "shipping: free",
        )
    ):
        return 0.0

    pattern = re.compile(
        r"(?:frakt|shipping|delivery)"
        r"[^\d]{0,30}"
        r"(\d+(?:[\s.]\d{3})*(?:[,.]\d{1,2})?)"
        r"\s*(?:kr|sek)\b",
        re.IGNORECASE,
    )
    match = pattern.search(
        text
        or ""
    )

    if not match:
        return None

    return _money_value(
        match.group(
            1
        )
    )


def _vat_status(
    text,
):
    body = str(
        text
        or ""
    ).lower()

    excluded = (
        "exkl moms",
        "exkl. moms",
        "moms tillkommer",
        "excl vat",
        "excl. vat",
        "excluding vat",
        "plus vat",
    )
    included = (
        "inkl moms",
        "inkl. moms",
        "inklusive moms",
        "moms ingår",
        "incl vat",
        "incl. vat",
        "including vat",
        "vat included",
    )

    if any(
        phrase in body
        for phrase in excluded
    ):
        return False

    if any(
        phrase in body
        for phrase in included
    ):
        return True

    return None


def _vat_amount(
    text,
):
    patterns = (
        r"(?:moms|vat)"
        r"[^\d]{0,20}"
        r"(\d+(?:[\s.]\d{3})*(?:[,.]\d{1,2})?)"
        r"\s*(?:kr|sek)\b",
        r"(\d+(?:[\s.]\d{3})*(?:[,.]\d{1,2})?)"
        r"\s*(?:kr|sek)"
        r"[^\w]{0,10}(?:moms|vat)\b",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text
            or "",
            flags=re.IGNORECASE,
        )

        if match:
            return _money_value(
                match.group(
                    1
                )
            )

    return None


def _additional_fees(
    text,
):
    body = str(
        text
        or ""
    ).lower()

    no_fees = (
        "inga extra avgifter",
        "inga ytterligare avgifter",
        "inga tillkommande avgifter",
        "no additional fees",
        "no extra fees",
        "no hidden fees",
    )

    if any(
        phrase in body
        for phrase in no_fees
    ):
        return (
            True,
            0.0,
        )

    return (
        False,
        None,
    )


def _delivery_days(
    text,
):
    patterns = (
        r"(\d{1,3})\s*[-–]\s*(\d{1,3})"
        r"\s*(?:arbetsdagar|dagar|business days|days)\b",
        r"(?:leverans|delivery)"
        r"[^\d]{0,25}"
        r"(\d{1,3})"
        r"\s*(?:arbetsdagar|dagar|business days|days)\b",
    )

    for index, pattern in enumerate(
        patterns
    ):
        match = re.search(
            pattern,
            text
            or "",
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        minimum = int(
            match.group(
                1
            )
        )
        maximum = (
            int(
                match.group(
                    2
                )
            )
            if index == 0
            else minimum
        )

        return (
            minimum,
            maximum,
        )

    return (
        None,
        None,
    )


def _information_confidence(
    candidate,
):
    weighted = (
        (
            "product_price_sek",
            15,
        ),
        (
            "currency",
            10,
        ),
        (
            "shipping_sek",
            15,
        ),
        (
            "vat_included",
            15,
        ),
        (
            "additional_fees_known",
            10,
        ),
        (
            "ships_to_sweden",
            10,
        ),
        (
            "stock_status",
            15,
        ),
        (
            "delivery_days_min",
            5,
        ),
        (
            "delivery_days_max",
            5,
        ),
    )
    score = 0.0

    for key, points in weighted:
        value = candidate.get(
            key
        )

        if key == "stock_status":
            known = value in {
                "in_stock",
                "limited",
                "out_of_stock",
            }
        elif key == "additional_fees_known":
            known = value is True
        elif key in {
            "vat_included",
            "ships_to_sweden",
        }:
            known = value is not None
        else:
            known = value not in (
                None,
                "",
            )

        if known:
            score += points

    return round(
        min(
            100.0,
            score,
        ),
        1,
    )


def offer_from_page(
    query,
    search_result,
    page,
):
    metadata = (
        page.get(
            "metadata",
            {}
        )
        or {}
    )
    text = str(
        page.get(
            "text",
            ""
        )
        or ""
    )
    verification = verify_page_content(
        page,
        query=query,
    )
    price = _money_value(
        _first_metadata(
            metadata,
            _PRICE_KEYS,
        )
    )
    currency = (
        _first_metadata(
            metadata,
            _CURRENCY_KEYS,
        )
        or "UNKNOWN"
    ).upper()
    availability = _availability(
        _first_metadata(
            metadata,
            _AVAILABILITY_KEYS,
        ),
        text,
    )
    ships = _shipping_to_sweden(
        text
    )
    shipping = _shipping_cost(
        text
    )
    vat_included = _vat_status(
        text
    )
    vat_amount = (
        _vat_amount(
            text
        )
        if vat_included is False
        else None
    )
    fees_known, fees = (
        _additional_fees(
            text
        )
    )
    delivery_min, delivery_max = (
        _delivery_days(
            text
        )
    )
    final_url = (
        page.get(
            "final_url"
        )
        or search_result.get(
            "url"
        )
        or ""
    )
    hostname = (
        urlparse(
            final_url
        ).hostname
        or ""
    )
    seller = (
        _first_metadata(
            metadata,
            (
                "og:site_name",
                "application-name",
            ),
        )
        or hostname
        or "okänd säljare"
    )
    relevance = max(
        metadata_relevance(
            query,
            search_result,
        ),
        verification.get(
            "query_overlap_percent",
            0.0,
        ),
    )
    candidate = {
        "name": (
            search_result.get(
                "title"
            )
            or page.get(
                "title"
            )
            or seller
        ),
        "seller": seller,
        "url": final_url,
        "currency": currency,
        "product_price_sek": (
            price
            if currency == "SEK"
            else None
        ),
        "shipping_sek": shipping,
        "vat_included": (
            vat_included
        ),
        "additional_fees_known": (
            fees_known
        ),
        "additional_fees_sek": (
            fees
        ),
        "ships_to_sweden": ships,
        "stock_status": availability,
        "delivery_days_min": (
            delivery_min
        ),
        "delivery_days_max": (
            delivery_max
        ),
        "source_reliability": round(
            float(
                verification.get(
                    "transparency_score",
                    0.0,
                )
            ),
            1,
        ),
        "relevance": round(
            min(
                100.0,
                relevance,
            ),
            1,
        ),
        "warning_flags": [],
        "critical_warning": False,
        "verification": verification,
        "extraction_scope": (
            "explicit_product_metadata_and_visible_page_text"
        ),
    }

    if (
        vat_included is False
        and vat_amount is not None
    ):
        candidate[
            "vat_amount_sek"
        ] = vat_amount

    candidate[
        "information_confidence"
    ] = _information_confidence(
        candidate
    )
    return candidate


def shopping_compare_data(
    query,
    settings=None,
    search_function=None,
    fetch_function=None,
):
    settings = (
        settings
        or load_settings()
    )
    query = str(
        query
        or ""
    ).strip()

    if not query:
        return {
            "available": False,
            "reason": "Produktfrågan är tom.",
            "query": query,
            "offers": [],
        }

    research_config = settings.get(
        "research",
        {},
    )
    candidate_limit = max(
        1,
        min(
            int(
                research_config.get(
                    "candidate_limit",
                    5,
                )
            ),
            5,
        ),
    )
    active_search = (
        search_function
        or search_web
    )
    active_fetch = (
        fetch_function
        or fetch_public_page
    )
    search_query = (
        query
        + " pris Sverige"
    )

    try:
        search_result = active_search(
            search_query,
            settings=settings,
        )
    except TypeError:
        search_result = active_search(
            query=search_query,
            settings=settings,
        )

    if not search_result.get(
        "success"
    ):
        return {
            "available": False,
            "reason": search_result.get(
                "error",
                "Prisökningen kunde inte köras.",
            ),
            "query": query,
            "search_query": search_query,
            "offers": [],
        }

    offers = []

    for result in list(
        search_result.get(
            "results",
            [],
        )
    )[
        :candidate_limit
    ]:
        url = str(
            result.get(
                "url",
                ""
            )
            or ""
        )

        try:
            try:
                page = active_fetch(
                    url,
                    settings=settings,
                )
            except TypeError:
                page = active_fetch(
                    url
                )
        except Exception as error:
            page = {
                "available": False,
                "reason": (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            }

        if not page.get(
            "available"
        ):
            offers.append(
                {
                    "name": (
                        result.get(
                            "title"
                        )
                        or url
                        or "Okänd kandidat"
                    ),
                    "seller": (
                        urlparse(
                            url
                        ).hostname
                        or "okänd säljare"
                    ),
                    "url": url,
                    "currency": "UNKNOWN",
                    "product_price_sek": None,
                    "shipping_sek": None,
                    "vat_included": None,
                    "additional_fees_known": False,
                    "additional_fees_sek": None,
                    "ships_to_sweden": None,
                    "stock_status": "unknown",
                    "source_reliability": 0.0,
                    "information_confidence": 0.0,
                    "relevance": metadata_relevance(
                        query,
                        result,
                    ),
                    "warning_flags": [
                        (
                            "Säljsidan kunde inte hämtas "
                            "och verifieras."
                        )
                    ],
                    "critical_warning": False,
                    "disqualify": True,
                    "fetch_error": page.get(
                        "reason",
                        "okänt fel",
                    ),
                }
            )
            continue

        offers.append(
            offer_from_page(
                query,
                result,
                page,
            )
        )

    comparison = compare_sweden_prices(
        offers,
        settings=settings,
    )
    comparison.update(
        {
            "available": True,
            "query": query,
            "search_query": (
                search_query
            ),
            "offer_count": len(
                offers
            ),
            "offers": offers,
            "assessment_note": (
                "Produktfakta extraheras endast från explicit "
                "produktmetadata och synlig sidtext. Okänd frakt, "
                "moms, lagerstatus, Sverigeleverans eller avgift "
                "gissas aldrig."
            ),
        }
    )
    return comparison


def format_shopping_comparison(
    result,
):
    if not result.get(
        "available"
    ):
        return (
            "Prisjämförelsen kunde inte köras: "
            + result.get(
                "reason",
                "okänd orsak",
            )
        )

    text = format_sweden_price_comparison(
        result
    )
    return (
        text
        + "\n"
        + result[
            "assessment_note"
        ]
    )


def shopping_compare_sweden(
    user_input,
):
    try:
        query = extract_shopping_query(
            user_input
        )

        if not query:
            return (
                "Prisjämförelsen kunde inte köras: "
                "produktfrågan är tom."
            )

        return format_shopping_comparison(
            shopping_compare_data(
                query
            )
        )
    except Exception as error:
        return (
            "Prisjämförelsen kunde inte köras: "
            f"{error}"
        )


TOOLS = {
    "shopping_compare_sweden": {
        "function": shopping_compare_sweden,
        "description": (
            "Söker upp till fem produkt-/säljsidor, extraherar endast "
            "uttryckligt angivna pris-, frakt-, moms-, lager- och "
            "Sverigeleveransuppgifter, källbedömer erbjudandena och "
            "visar upp till tre billigaste kompletta alternativ."
        ),
        "pass_user_input": True,
    },
}
