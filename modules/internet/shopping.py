from urllib.parse import urlparse

from core.config import load_settings
from core.page_verification import verify_page_content
from modules.internet.currency import convert_amount_to_sek
from modules.internet.price_compare import compare_offers_sweden, format_price_comparison
from modules.internet.product_offer import extract_offer_page_data
from modules.internet.search import search_web
from modules.internet.seller_vetting import assess_seller_page


def _hostname(url):
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def _convert_money(amount, currency, settings, convert_function):
    if amount is None:
        return None, None

    code = (currency or "").strip().upper()

    if not code:
        return None, "Valuta saknas."

    result = convert_function(
        amount,
        code,
        settings=settings,
    )

    if result.get("available") is False:
        return None, result.get(
            "reason",
            "Valutakonvertering saknas.",
        )

    return result.get("amount_sek"), None


def _prepare_offer(
    raw_offer,
    seller_result,
    settings,
    convert_function,
):
    product_price_sek, product_error = _convert_money(
        raw_offer.get("product_price"),
        raw_offer.get("currency"),
        settings,
        convert_function,
    )

    if raw_offer.get("shipping_sek") is not None:
        shipping_sek = raw_offer["shipping_sek"]
        shipping_error = None
    else:
        shipping_sek, shipping_error = _convert_money(
            raw_offer.get("shipping_value"),
            raw_offer.get("shipping_currency"),
            settings,
            convert_function,
        )

    warnings = []

    if product_error:
        warnings.append(
            "Produktpris kunde inte konverteras: "
            + product_error
        )

    if shipping_error and raw_offer.get("shipping_value") is not None:
        warnings.append(
            "Frakt kunde inte konverteras: "
            + shipping_error
        )

    seller_reliability = None

    if seller_result.get("available"):
        seller_reliability = seller_result.get(
            "seller_reliability"
        )
    else:
        warnings.append(
            "Säljargranskning saknas: "
            + seller_result.get(
                "reason",
                "okänd orsak",
            )
        )

    store = (
        raw_offer.get("store")
        or _hostname(raw_offer.get("url"))
        or "okänd butik"
    )

    prepared = {
        "title": raw_offer.get("title"),
        "store": store,
        "url": raw_offer.get("url"),
        "product_price_sek": product_price_sek,
        "shipping_sek": shipping_sek,
        "vat_included": raw_offer.get("vat_included"),
        "vat_sek": raw_offer.get("vat_sek"),
        "fees_sek": raw_offer.get("fees_sek"),
        "stock_status": raw_offer.get(
            "stock_status",
            "unknown",
        ),
        "ships_to_sweden": raw_offer.get(
            "ships_to_sweden"
        ),
        "delivery_days": raw_offer.get(
            "delivery_days"
        ),
        "seller_reliability": seller_reliability,
        "source_currency": raw_offer.get("currency"),
        "source_product_price": raw_offer.get(
            "product_price"
        ),
        "source_shipping_value": raw_offer.get(
            "shipping_value"
        ),
        "source_shipping_currency": raw_offer.get(
            "shipping_currency"
        ),
        "extraction_source": raw_offer.get("source"),
        "pipeline_warnings": warnings,
    }
    return prepared


def shopping_research_data(
    query,
    urls=None,
    settings=None,
    search_function=None,
    extract_function=None,
    convert_function=None,
):
    settings = settings or load_settings()
    config = settings.get("shopping", {})

    candidate_pages = max(
        1,
        min(
            int(config.get("candidate_pages", 5)),
            10,
        ),
    )
    active_search = search_function or search_web
    active_extract = (
        extract_function or extract_offer_page_data
    )
    active_convert = (
        convert_function or convert_amount_to_sek
    )

    selected_urls = []

    if urls:
        if not isinstance(urls, list):
            raise ValueError("urls måste vara en lista.")

        for value in urls:
            url = str(value).strip()

            if url and url not in selected_urls:
                selected_urls.append(url)

            if len(selected_urls) >= candidate_pages:
                break
    else:
        search_result = active_search(
            query=query,
            limit=candidate_pages,
            settings=settings,
        )

        if not search_result.get("available"):
            return {
                "available": False,
                "reason": search_result.get(
                    "reason",
                    "Produktsökningen kunde inte köras.",
                ),
            }

        for item in search_result.get("results", []):
            url = (item.get("url") or "").strip()

            if url and url not in selected_urls:
                selected_urls.append(url)

            if len(selected_urls) >= candidate_pages:
                break

    prepared_offers = []
    page_results = []

    for url in selected_urls:
        try:
            extracted = active_extract(
                url=url,
                settings=settings,
            )
        except Exception as error:
            page_results.append(
                {
                    "url": url,
                    "status": "failed",
                    "reason": str(error),
                    "offer_count": 0,
                }
            )
            continue

        if not extracted.get("available"):
            page_results.append(
                {
                    "url": url,
                    "status": "unavailable",
                    "reason": extracted.get(
                        "reason",
                        "Produktsidan kunde inte läsas.",
                    ),
                    "offer_count": 0,
                }
            )
            continue

        raw_offers = extracted.get("offers", [])
        page = extracted.get("page", {})

        if page:
            verification = verify_page_content(
                page,
                query=query,
            )
            seller_result = assess_seller_page(
                {
                    "available": True,
                    "page": page,
                    "verification": verification,
                }
            )
        else:
            seller_result = {
                "available": False,
                "reason": (
                    "Hämtad sida saknas i produktutvinningen."
                ),
            }

        for raw_offer in raw_offers:
            prepared_offers.append(
                _prepare_offer(
                    raw_offer,
                    seller_result,
                    settings,
                    active_convert,
                )
            )

        page_results.append(
            {
                "url": extracted.get("url") or url,
                "status": (
                    "parsed"
                    if raw_offers
                    else "no_structured_offer"
                ),
                "offer_count": len(raw_offers),
                "seller_reliability": seller_result.get(
                    "seller_reliability"
                ),
            }
        )

    comparison = compare_offers_sweden(
        prepared_offers,
        top_n=config.get("top_results", 3),
        min_seller_reliability=config.get(
            "min_seller_reliability",
            50.0,
        ),
    )

    return {
        "available": True,
        "query": query,
        "page_count": len(selected_urls),
        "parsed_offer_count": len(prepared_offers),
        "pages": page_results,
        "offers": prepared_offers,
        "comparison": comparison,
        "assessment_note": (
            "Shoppingflödet använder strukturerad produktdata, faktisk "
            "valutakonvertering när sådan krävs och separat säljargranskning. "
            "Saknade kostnader eller leveransuppgifter gissas inte."
        ),
    }


def format_shopping_research(result):
    if not result.get("available"):
        return "Shopping-research kunde inte köras: " + result.get(
            "reason",
            "okänd orsak",
        )

    lines = [
        (
            f"Shopping-research för: {result.get('query') or ''}"
        ),
        (
            f"Genomsökta sidor: {result.get('page_count', 0)} | "
            f"strukturerade erbjudanden: "
            f"{result.get('parsed_offer_count', 0)}"
        ),
        result.get("assessment_note", ""),
        "",
        format_price_comparison(
            result["comparison"]
        ),
    ]

    incomplete_pages = [
        item
        for item in result.get("pages", [])
        if item.get("status") != "parsed"
    ]

    if incomplete_pages:
        lines.append("")
        lines.append(
            f"Sidor utan användbart strukturerat erbjudande: "
            f"{len(incomplete_pages)}."
        )

    return "\n".join(lines)


def shopping_research_sweden(query, urls=None):
    try:
        return format_shopping_research(
            shopping_research_data(
                query=query,
                urls=urls,
            )
        )
    except Exception as error:
        return f"Shopping-research misslyckades: {error}"


TOOLS = {
    "shopping_research_sweden": {
        "function": shopping_research_sweden,
        "description": (
            "Söker eller granskar upp till ett begränsat antal produktsidor, "
            "extraherar strukturerade erbjudanden, konverterar verkliga "
            "valutor till SEK, granskar säljare och kör svensk totalprisjämförelse."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "urls": {"type": "array"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }
}
