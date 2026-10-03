import re
from urllib.parse import urlparse


PRICE_META_KEYS = (
    "product:price:amount",
    "og:price:amount",
    "price",
)

CURRENCY_META_KEYS = (
    "product:price:currency",
    "og:price:currency",
    "pricecurrency",
)


def _first(metadata, keys):
    metadata = metadata or {}

    for key in keys:
        value = metadata.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    return ""


def _parse_number(value):
    text = str(value or "").strip()
    text = text.replace("\xa0", " ").replace(" ", "")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    return float(text)


def _extract_sek_price(text):
    patterns = (
        r"\b(?:SEK)\s*(\d{1,7}(?:[\s.]\d{3})*(?:[,.]\d{1,2})?)",
        r"\b(\d{1,7}(?:[\s.]\d{3})*(?:[,.]\d{1,2})?)\s*(?:kr|SEK)\b",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text or "",
            flags=re.IGNORECASE,
        )

        if match:
            try:
                return round(_parse_number(match.group(1)), 2)
            except ValueError:
                continue

    return None


def _extract_shipping_sek(text):
    lowered = (text or "").lower()

    if any(
        phrase in lowered
        for phrase in (
            "fri frakt",
            "gratis frakt",
            "free shipping",
        )
    ):
        return 0.0

    patterns = (
        r"(?:frakt|shipping)[^\d]{0,20}(\d{1,6}(?:[\s.]\d{3})*(?:[,.]\d{1,2})?)\s*(?:kr|sek)",
        r"(\d{1,6}(?:[\s.]\d{3})*(?:[,.]\d{1,2})?)\s*(?:kr|sek)[^\n]{0,20}(?:frakt|shipping)",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text or "",
            flags=re.IGNORECASE,
        )

        if match:
            try:
                return round(_parse_number(match.group(1)), 2)
            except ValueError:
                continue

    return None


def _vat_status(text):
    lowered = (text or "").lower()

    excluded = (
        "exkl moms",
        "exkl. moms",
        "exklusive moms",
        "excl vat",
        "excluding vat",
    )
    included = (
        "inkl moms",
        "inkl. moms",
        "inklusive moms",
        "inkl vat",
        "including vat",
        "vat included",
    )

    if any(phrase in lowered for phrase in excluded):
        return False

    if any(phrase in lowered for phrase in included):
        return True

    return None


def _stock_status(text):
    lowered = (text or "").lower()

    negative = (
        "slut i lager",
        "ej i lager",
        "inte i lager",
        "out of stock",
        "sold out",
    )
    positive = (
        "i lager",
        "finns i lager",
        "in stock",
        "lagerstatus: lager",
    )

    if any(phrase in lowered for phrase in negative):
        return False

    if any(phrase in lowered for phrase in positive):
        return True

    return None


def _sweden_delivery_status(text):
    lowered = (text or "").lower()

    negative = (
        "levererar inte till sverige",
        "skickar inte till sverige",
        "does not ship to sweden",
        "no shipping to sweden",
    )
    positive = (
        "levererar till sverige",
        "leverans till sverige",
        "frakt till sverige",
        "skickar till sverige",
        "ships to sweden",
        "shipping to sweden",
        "delivery to sweden",
    )

    if any(phrase in lowered for phrase in negative):
        return False

    if any(phrase in lowered for phrase in positive):
        return True

    return None


def _delivery_time(text):
    patterns = (
        r"\b(\d+)\s*[-–]\s*(\d+)\s*(vardagar|arbetsdagar|dagar|business days|days)\b",
        r"\b(\d+)\s*(vardagar|arbetsdagar|dagar|business days|days)\b",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text or "",
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(0)

    return None


def extract_offer(page):
    metadata = page.get("metadata", {}) or {}
    text = page.get("text", "") or ""
    final_url = page.get("final_url") or page.get("requested_url") or ""

    price = None
    currency = _first(metadata, CURRENCY_META_KEYS).upper() or None
    price_source = None

    meta_price = _first(metadata, PRICE_META_KEYS)

    if meta_price:
        try:
            price = round(_parse_number(meta_price), 2)
            price_source = "metadata"
        except ValueError:
            price = None

    if price is None:
        price = _extract_sek_price(text)

        if price is not None:
            currency = "SEK"
            price_source = "page_text"

    shipping = _extract_shipping_sek(text)
    vat_included = _vat_status(text)
    in_stock = _stock_status(text)
    ships_to_sweden = _sweden_delivery_status(text)
    delivery_time = _delivery_time(text)

    site_name = _first(
        metadata,
        ("og:site_name", "application-name"),
    )
    hostname = (urlparse(final_url).hostname or "").lower()
    seller = site_name or hostname or None

    total_price_sek = None

    if (
        price is not None
        and currency == "SEK"
        and shipping is not None
        and vat_included is True
    ):
        total_price_sek = round(price + shipping, 2)

    return {
        "seller": seller,
        "url": final_url,
        "product_price": price,
        "currency": currency,
        "shipping_sek": shipping,
        "vat_included": vat_included,
        "in_stock": in_stock,
        "ships_to_sweden": ships_to_sweden,
        "delivery_time": delivery_time,
        "total_price_sek": total_price_sek,
        "price_source": price_source,
    }


def practical_for_sweden(offer):
    if offer.get("product_price") is None:
        return False

    if offer.get("currency") != "SEK":
        return False

    if offer.get("in_stock") is False:
        return False

    if offer.get("ships_to_sweden") is False:
        return False

    return True
