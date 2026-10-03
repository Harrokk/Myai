from urllib.parse import urljoin

from modules.internet.fetch import fetch_public_page


AVAILABILITY_MAP = {
    "instock": "in_stock",
    "outofstock": "out_of_stock",
    "preorder": "preorder",
    "presale": "preorder",
}


def _type_values(node):
    value = node.get("@type")

    if isinstance(value, list):
        return {
            str(item).lower()
            for item in value
        }

    if value is None:
        return set()

    return {str(value).lower()}


def _walk_json_ld(value):
    if isinstance(value, dict):
        yield value

        for child in value.values():
            yield from _walk_json_ld(child)

    elif isinstance(value, list):
        for child in value:
            yield from _walk_json_ld(child)


def _number(value):
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return round(float(value), 2)

    text = str(value).strip().replace(" ", "")
    text = text.replace(",", ".")

    try:
        return round(float(text), 2)
    except ValueError:
        return None


def _availability(value):
    if not value:
        return "unknown"

    token = str(value).rstrip("/").split("/")[-1].lower()
    return AVAILABILITY_MAP.get(token, "unknown")


def _seller_name(value):
    if isinstance(value, dict):
        return (
            value.get("name")
            or value.get("legalName")
            or ""
        )

    if isinstance(value, str):
        return value

    return ""


def _days_from_quantitative(value):
    if value is None:
        return None

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    if not isinstance(value, dict):
        return None

    unit = str(
        value.get("unitCode")
        or value.get("unitText")
        or ""
    ).strip().lower()

    if unit not in {"d", "day", "days", "dag", "dagar"}:
        return None

    maximum = _number(
        value.get(
            "maxValue",
            value.get("value"),
        )
    )
    minimum = _number(value.get("minValue"))

    if maximum is not None:
        return maximum

    return minimum


def _delivery_days_from_details(detail):
    if not isinstance(detail, dict):
        return None

    delivery = detail.get("deliveryTime")

    if not isinstance(delivery, dict):
        return None

    handling = _days_from_quantitative(
        delivery.get("handlingTime")
    )
    transit = _days_from_quantitative(
        delivery.get("transitTime")
    )

    values = [
        value
        for value in (handling, transit)
        if value is not None
    ]

    if not values:
        return None

    return round(sum(values), 1)


def _return_policy_data(value):
    if not isinstance(value, dict):
        return None

    types = _type_values(value)

    if "merchantreturnpolicy" not in types and not any(
        key in value
        for key in (
            "returnPolicyCategory",
            "merchantReturnDays",
            "returnMethod",
            "returnFees",
        )
    ):
        return None

    return {
        "category": value.get("returnPolicyCategory"),
        "return_days": _number(
            value.get("merchantReturnDays")
        ),
        "return_method": value.get("returnMethod"),
        "return_fees": value.get("returnFees"),
        "applicable_country": value.get(
            "applicableCountry"
        ),
    }


def _shipping_data(offer):
    details = offer.get("shippingDetails")

    if isinstance(details, dict):
        details = [details]

    if not isinstance(details, list):
        return {
            "shipping_value": None,
            "shipping_currency": None,
            "shipping_sek": None,
            "ships_to_sweden": None,
        }

    best_value = None
    best_currency = None
    shipping_sek = None
    ships_to_sweden = None
    delivery_days = None

    for detail in details:
        if not isinstance(detail, dict):
            continue

        destinations = detail.get("shippingDestination")

        if isinstance(destinations, dict):
            destinations = [destinations]

        if isinstance(destinations, list):
            countries = set()

            for destination in destinations:
                if not isinstance(destination, dict):
                    continue

                country = (
                    destination.get("addressCountry")
                    or destination.get("name")
                )

                if isinstance(country, dict):
                    country = (
                        country.get("name")
                        or country.get("identifier")
                    )

                if country:
                    countries.add(str(country).upper())

            if {"SE", "SWE", "SWEDEN", "SVERIGE"} & countries:
                ships_to_sweden = True

        detail_delivery_days = _delivery_days_from_details(
            detail
        )

        if detail_delivery_days is not None:
            if (
                delivery_days is None
                or detail_delivery_days < delivery_days
            ):
                delivery_days = detail_delivery_days

        rate = detail.get("shippingRate")

        if isinstance(rate, dict):
            currency = (
                rate.get("priceCurrency")
                or rate.get("currency")
                or ""
            ).upper() or None
            value = _number(
                rate.get("value", rate.get("price"))
            )

            if value is not None and (
                best_value is None or value < best_value
            ):
                best_value = value
                best_currency = currency

            if currency == "SEK" and value is not None:
                if shipping_sek is None or value < shipping_sek:
                    shipping_sek = value

    return {
        "shipping_value": best_value,
        "shipping_currency": best_currency,
        "shipping_sek": shipping_sek,
        "ships_to_sweden": ships_to_sweden,
        "delivery_days": delivery_days,
    }


def _price_data(offer):
    currency = (
        offer.get("priceCurrency")
        or ""
    ).upper()
    price = _number(offer.get("price"))
    vat_included = None

    specification = offer.get("priceSpecification")

    if isinstance(specification, list):
        specification = next(
            (
                item
                for item in specification
                if isinstance(item, dict)
            ),
            None,
        )

    if isinstance(specification, dict):
        if price is None:
            price = _number(
                specification.get(
                    "price",
                    specification.get("value"),
                )
            )

        if not currency:
            currency = (
                specification.get("priceCurrency")
                or specification.get("currency")
                or ""
            ).upper()

        vat_value = specification.get(
            "valueAddedTaxIncluded"
        )

        if isinstance(vat_value, bool):
            vat_included = vat_value

    return {
        "price": price,
        "currency": currency or None,
        "vat_included": vat_included,
    }


def extract_product_offers(page):
    structured = page.get("structured_data") or []
    products = []
    standalone_offers = []

    for root in structured:
        for node in _walk_json_ld(root):
            types = _type_values(node)

            if "product" in types:
                products.append(node)

            if "offer" in types or "aggregateoffer" in types:
                standalone_offers.append(node)

    extracted = []

    for product in products:
        offers = product.get("offers")

        if isinstance(offers, dict):
            offers = [offers]

        if not isinstance(offers, list):
            offers = []

        for offer in offers:
            if not isinstance(offer, dict):
                continue

            extracted.append(
                _normalize_offer(
                    offer,
                    product=product,
                    page=page,
                )
            )

    if not extracted:
        for offer in standalone_offers:
            extracted.append(
                _normalize_offer(
                    offer,
                    product=None,
                    page=page,
                )
            )

    return extracted


def _normalize_offer(offer, product, page):
    price_data = _price_data(offer)
    shipping = _shipping_data(offer)
    return_policy = _return_policy_data(
        offer.get("hasMerchantReturnPolicy")
        or (product or {}).get("hasMerchantReturnPolicy")
    )
    availability = _availability(
        offer.get("availability")
    )
    seller = _seller_name(
        offer.get("seller")
        or (product or {}).get("brand")
    )
    title = (
        (product or {}).get("name")
        or offer.get("name")
        or page.get("title")
        or "Produkt"
    )
    page_url = page.get("final_url") or page.get(
        "requested_url",
        "",
    )
    offer_url = offer.get("url")

    if offer_url:
        offer_url = urljoin(page_url, str(offer_url))
    else:
        offer_url = page_url

    return {
        "title": str(title).strip(),
        "store": str(seller).strip(),
        "url": offer_url,
        "product_price": price_data["price"],
        "currency": price_data["currency"],
        "shipping_value": shipping["shipping_value"],
        "shipping_currency": shipping["shipping_currency"],
        "shipping_sek": shipping["shipping_sek"],
        "vat_included": price_data["vat_included"],
        "vat_sek": None,
        "fees_sek": None,
        "stock_status": availability,
        "ships_to_sweden": shipping["ships_to_sweden"],
        "delivery_days": shipping["delivery_days"],
        "return_policy": return_policy,
        "seller_reliability": None,
        "source": "json_ld",
    }


def extract_offer_page_data(
    url,
    settings=None,
    fetch_function=None,
):
    active_fetch = fetch_function or fetch_public_page
    page = active_fetch(
        url=url,
        settings=settings,
    )

    if not page.get("available"):
        return {
            "available": False,
            "reason": page.get(
                "reason",
                "Produktsidan kunde inte hämtas.",
            ),
            "offers": [],
        }

    offers = extract_product_offers(page)

    return {
        "available": True,
        "url": page.get("final_url") or url,
        "page": page,
        "offers": offers,
        "structured_offer_count": len(offers),
    }


def format_offer_page(result):
    if not result.get("available"):
        return "Produktdata kunde inte hämtas: " + result.get(
            "reason",
            "okänd orsak",
        )

    offers = result.get("offers", [])

    if not offers:
        return (
            "Ingen strukturerad Product/Offer-data hittades på sidan. "
            "MyAI gissar därför inte pris eller lagerstatus."
        )

    lines = [
        f"Strukturerade erbjudanden: {len(offers)}"
    ]

    for index, offer in enumerate(offers, start=1):
        price = offer.get("product_price")
        currency = offer.get("currency") or "okänd valuta"
        price_text = (
            f"{price:.2f} {currency}"
            if price is not None
            else "pris saknas"
        )
        lines.append(
            f"{index}. {offer.get('title')} | {price_text} | "
            f"lager={offer.get('stock_status')}"
        )
        lines.append(
            f"   Sverige-leverans: {offer.get('ships_to_sweden')}"
        )

    return "\n".join(lines)


def web_product_offer(url):
    try:
        return format_offer_page(
            extract_offer_page_data(url)
        )
    except Exception as error:
        return f"Produktdata kunde inte hämtas: {error}"


TOOLS = {
    "web_product_offer": {
        "function": web_product_offer,
        "description": (
            "Hämtar en publik produktsida säkert och extraherar strukturerad "
            "schema.org Product/Offer-data utan att gissa saknade värden."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    }
}
