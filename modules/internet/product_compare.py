from core.commerce_extraction import (
    extract_offer,
    practical_for_sweden,
)
from core.config import load_settings
from core.source_evaluation import (
    apply_deep_verification,
    evaluate_candidates,
)
from modules.internet.search import search_web
from modules.internet.verify import verify_source_page_data


def compare_products_sweden_data(
    query,
    settings=None,
    search_function=None,
    verify_function=None,
):
    settings = settings or load_settings()
    research_config = settings.get("research", {})
    shopping_config = settings.get("shopping", {})

    candidate_limit = max(
        1,
        min(int(research_config.get("candidate_limit", 5)), 5),
    )
    top_results = max(
        1,
        min(int(shopping_config.get("top_results", 3)), 3),
    )
    min_reliability = float(
        shopping_config.get("min_source_reliability", 50)
    )
    deep_blend = float(
        research_config.get("deep_blend", 0.40)
    )
    weights = research_config.get("weights", {})

    active_search = search_function or search_web
    active_verify = verify_function or verify_source_page_data

    search_query = f"{query} pris Sverige köp"
    search_result = active_search(
        query=search_query,
        limit=candidate_limit,
        settings=settings,
    )

    if not search_result.get("available"):
        return {
            "available": False,
            "reason": search_result.get(
                "reason",
                "Internetsökningen kunde inte köras.",
            ),
            "candidates": [],
            "top": [],
        }

    raw_candidates = list(
        search_result.get("results", [])
    )[:candidate_limit]
    preliminary = evaluate_candidates(
        query,
        raw_candidates,
        weights=weights,
    )

    candidates = []

    for candidate in preliminary:
        item = dict(candidate)

        try:
            verified = active_verify(
                url=candidate.get("url", ""),
                query=query,
                settings=settings,
            )
        except Exception as error:
            item["verification_status"] = "failed"
            item["verification_reason"] = str(error)
            item["offer"] = None
            candidates.append(item)
            continue

        if not verified.get("available"):
            item["verification_status"] = "unavailable"
            item["verification_reason"] = verified.get(
                "reason",
                "Källan kunde inte verifieras.",
            )
            item["offer"] = None
            candidates.append(item)
            continue

        verification = verified.get(
            "verification",
            {},
        )
        item = apply_deep_verification(
            candidate,
            verification,
            weights=weights,
            deep_blend=deep_blend,
        )
        item["verification_status"] = "verified"
        item["offer"] = extract_offer(
            verified.get("page", {})
        )
        candidates.append(item)

    usable = [
        item
        for item in candidates
        if item.get("verification_status") == "verified"
        and practical_for_sweden(item.get("offer") or {})
        and item["source_reliability"]["score"] >= min_reliability
    ]

    usable.sort(
        key=lambda item: (
            item["offer"].get("total_price_sek") is None,
            (
                item["offer"].get("total_price_sek")
                if item["offer"].get("total_price_sek") is not None
                else item["offer"].get("product_price")
            ),
            -item["source_reliability"]["score"],
        )
    )

    return {
        "available": True,
        "query": query,
        "candidate_count": len(raw_candidates),
        "usable_count": len(usable),
        "candidates": candidates,
        "top": usable[:top_results],
        "assessment_note": (
            "Totalpris i SEK visas bara när produktpris, frakt och "
            "momsstatus är kända. Okända värden lämnas okända."
        ),
    }


def _format_optional_bool(value, yes, no):
    if value is True:
        return yes
    if value is False:
        return no
    return "okänt"


def format_product_comparison(result):
    if not result.get("available"):
        return "Prisjämförelse kunde inte köras: " + result.get(
            "reason",
            "okänd orsak",
        )

    lines = [
        f"Prisjämförelse för Sverige: {result.get('query') or ''}",
        (
            f"Bedömda kandidater: {result.get('candidate_count', 0)} | "
            f"praktiskt användbara: {result.get('usable_count', 0)}"
        ),
        result.get("assessment_note", ""),
    ]

    top = result.get("top", [])

    if not top:
        lines.append(
            "Inga alternativ hade tillräckligt komplett och tillförlitligt underlag."
        )
        return "\n".join(lines)

    lines.append("Topp tre:")

    for index, item in enumerate(top, start=1):
        offer = item["offer"]
        lines.append(
            f"{index}. {item.get('title') or offer.get('seller') or 'Alternativ'}"
        )
        lines.append(
            f"   Butik: {offer.get('seller') or 'okänd'}"
        )
        lines.append(
            "   Produktpris: "
            + (
                f"{offer['product_price']:.2f} {offer['currency']}"
                if offer.get("product_price") is not None
                and offer.get("currency")
                else "okänt"
            )
        )
        lines.append(
            "   Frakt: "
            + (
                f"{offer['shipping_sek']:.2f} SEK"
                if offer.get("shipping_sek") is not None
                else "okänd"
            )
        )
        lines.append(
            "   Moms inkluderad: "
            + _format_optional_bool(
                offer.get("vat_included"),
                "ja",
                "nej",
            )
        )
        lines.append(
            "   Lager: "
            + _format_optional_bool(
                offer.get("in_stock"),
                "i lager",
                "slut",
            )
        )
        lines.append(
            "   Leverans till Sverige: "
            + _format_optional_bool(
                offer.get("ships_to_sweden"),
                "ja",
                "nej",
            )
        )
        lines.append(
            "   Leveranstid: "
            + (offer.get("delivery_time") or "okänd")
        )
        lines.append(
            "   Totalpris: "
            + (
                f"{offer['total_price_sek']:.2f} SEK"
                if offer.get("total_price_sek") is not None
                else "okänt"
            )
        )
        lines.append(
            "   Källans tillförlitlighet: "
            f"{item['source_reliability']['score']:.1f}%"
        )
        lines.append(
            "   Informationens konfidens: "
            f"{item['information_confidence']['score']:.1f}%"
        )
        lines.append(
            f"   URL: {offer.get('url') or item.get('url') or ''}"
        )

    return "\n".join(lines)


def product_compare_sweden(query):
    try:
        return format_product_comparison(
            compare_products_sweden_data(query)
        )
    except Exception as error:
        return f"Prisjämförelse misslyckades: {error}"


TOOLS = {
    "product_compare_sweden": {
        "function": product_compare_sweden,
        "description": (
            "Jämför upp till fem produktkandidater för köp från Sverige och "
            "presenterar högst tre praktiskt användbara alternativ med känt "
            "pris-, frakt-, moms-, lager- och leveransunderlag när det finns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }
}
