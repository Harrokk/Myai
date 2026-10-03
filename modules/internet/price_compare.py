from copy import deepcopy


VALID_STOCK = {
    "in_stock",
    "preorder",
    "out_of_stock",
    "unknown",
}


def _number_or_none(value, field):
    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise ValueError(f"{field} måste vara ett tal eller null.")

    if value < 0:
        raise ValueError(f"{field} får inte vara negativt.")

    return round(float(value), 2)


def normalize_offer(offer):
    if not isinstance(offer, dict):
        raise ValueError("Varje erbjudande måste vara ett objekt.")

    product_price = _number_or_none(
        offer.get("product_price_sek"),
        "product_price_sek",
    )
    shipping = _number_or_none(
        offer.get("shipping_sek"),
        "shipping_sek",
    )
    vat = _number_or_none(
        offer.get("vat_sek"),
        "vat_sek",
    )
    fees = _number_or_none(
        offer.get("fees_sek"),
        "fees_sek",
    )

    vat_included = offer.get("vat_included")

    if vat_included not in {True, False, None}:
        raise ValueError("vat_included måste vara true, false eller null.")

    stock = (offer.get("stock_status") or "unknown").strip().lower()

    if stock not in VALID_STOCK:
        raise ValueError(
            "stock_status måste vara in_stock, preorder, "
            "out_of_stock eller unknown."
        )

    ships_to_sweden = offer.get("ships_to_sweden")

    if ships_to_sweden not in {True, False, None}:
        raise ValueError(
            "ships_to_sweden måste vara true, false eller null."
        )

    reliability = offer.get("seller_reliability")

    if reliability is not None:
        reliability = _number_or_none(
            reliability,
            "seller_reliability",
        )
        reliability = max(0.0, min(reliability, 100.0))

    missing_costs = []

    if product_price is None:
        missing_costs.append("produktpris")

    if shipping is None:
        missing_costs.append("frakt")

    if vat_included is True:
        effective_vat = 0.0
    elif vat is None:
        effective_vat = None
        missing_costs.append("moms")
    else:
        effective_vat = vat

    if fees is None:
        missing_costs.append("avgifter")

    total = None

    if not missing_costs:
        total = round(
            product_price
            + shipping
            + effective_vat
            + fees,
            2,
        )

    warnings = []

    if ships_to_sweden is False:
        warnings.append("Levererar inte till Sverige.")
    elif ships_to_sweden is None:
        warnings.append("Leverans till Sverige är inte verifierad.")

    if stock == "out_of_stock":
        warnings.append("Produkten är slut i lager.")
    elif stock == "unknown":
        warnings.append("Lagerstatus är okänd.")
    elif stock == "preorder":
        warnings.append("Produkten är förbeställning.")

    if missing_costs:
        warnings.append(
            "Totalpris kan inte beräknas; saknar "
            + ", ".join(missing_costs)
            + "."
        )

    if reliability is None:
        warnings.append("Säljarens tillförlitlighet är inte bedömd.")

    normalized = deepcopy(offer)
    normalized.update(
        {
            "product_price_sek": product_price,
            "shipping_sek": shipping,
            "vat_sek": vat,
            "fees_sek": fees,
            "vat_included": vat_included,
            "stock_status": stock,
            "ships_to_sweden": ships_to_sweden,
            "seller_reliability": reliability,
            "total_price_sek": total,
            "missing_costs": missing_costs,
            "warnings": warnings,
        }
    )
    return normalized


def compare_offers_sweden(
    offers,
    top_n=3,
    min_seller_reliability=50.0,
):
    if not isinstance(offers, list):
        raise ValueError("offers måste vara en lista.")

    if len(offers) > 20:
        raise ValueError("Högst 20 erbjudanden får jämföras åt gången.")

    normalized = [
        normalize_offer(offer)
        for offer in offers
    ]

    eligible = []
    incomplete = []
    rejected = []

    for offer in normalized:
        reliability = offer.get("seller_reliability")
        reliable_enough = (
            reliability is not None
            and reliability >= float(min_seller_reliability)
        )
        practical = (
            offer.get("ships_to_sweden") is True
            and offer.get("stock_status") == "in_stock"
        )
        total_known = offer.get("total_price_sek") is not None

        if practical and total_known and reliable_enough:
            eligible.append(offer)
        elif offer.get("ships_to_sweden") is False or (
            offer.get("stock_status") == "out_of_stock"
        ):
            rejected.append(offer)
        else:
            incomplete.append(offer)

    eligible.sort(
        key=lambda item: (
            item["total_price_sek"],
            -item["seller_reliability"],
        )
    )

    top_n = max(1, min(int(top_n), 3))

    return {
        "offer_count": len(normalized),
        "eligible_count": len(eligible),
        "top": eligible[:top_n],
        "incomplete": incomplete,
        "rejected": rejected,
        "assessment_note": (
            "Topplistan innehåller endast alternativ med känt totalpris, "
            "verifierad leverans till Sverige, lagerstatus in_stock och "
            "tillräcklig säljarbedömning."
        ),
    }


def format_price_comparison(result):
    lines = [
        (
            f"Prisjämförelse: {result['offer_count']} alternativ, "
            f"{result['eligible_count']} fullt jämförbara."
        ),
        result["assessment_note"],
    ]

    top = result.get("top", [])

    if top:
        lines.append("Topp tre för Sverige:")

        for index, offer in enumerate(top, start=1):
            lines.append(
                f"{index}. {offer.get('title') or 'Produkt'} - "
                f"{offer.get('store') or 'okänd butik'}"
            )
            lines.append(
                f"   Totalpris: {offer['total_price_sek']:.2f} SEK"
            )
            lines.append(
                f"   Produkt: {offer['product_price_sek']:.2f} SEK | "
                f"frakt: {offer['shipping_sek']:.2f} SEK | "
                f"moms: {0.0 if offer['vat_included'] else offer['vat_sek']:.2f} SEK | "
                f"avgifter: {offer['fees_sek']:.2f} SEK"
            )

            if offer.get("delivery_days") is not None:
                lines.append(
                    f"   Leverans: cirka {offer['delivery_days']} dagar"
                )

            lines.append(
                "   Säljarens tillförlitlighet: "
                f"{offer['seller_reliability']:.1f}%"
            )

            if offer.get("url"):
                lines.append(f"   URL: {offer['url']}")
    else:
        lines.append(
            "Inga alternativ uppfyllde alla krav för en säker totalprisjämförelse."
        )

    if result.get("incomplete"):
        lines.append(
            f"Ofullständiga/ej verifierade alternativ: "
            f"{len(result['incomplete'])}."
        )

    if result.get("rejected"):
        lines.append(
            f"Bortsorterade alternativ: {len(result['rejected'])}."
        )

    return "\n".join(lines)


def price_compare_sweden(
    offers,
    top_n=3,
    min_seller_reliability=50.0,
):
    try:
        return format_price_comparison(
            compare_offers_sweden(
                offers,
                top_n=top_n,
                min_seller_reliability=min_seller_reliability,
            )
        )
    except Exception as error:
        return f"Prisjämförelsen misslyckades: {error}"


TOOLS = {
    "price_compare_sweden": {
        "function": price_compare_sweden,
        "description": (
            "Jämför strukturerade produkterbjudanden för köp till Sverige "
            "och rankar högst tre efter känt totalpris när leverans, lager "
            "och säljarens tillförlitlighet är tillräckligt verifierade."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "offers": {"type": "array"},
                "top_n": {"type": "integer"},
                "min_seller_reliability": {"type": "number"},
            },
            "required": ["offers"],
            "additionalProperties": False,
        },
    }
}
