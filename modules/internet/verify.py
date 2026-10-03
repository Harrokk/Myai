from core.page_verification import verify_page_content
from modules.internet.fetch import extract_page_url, fetch_public_page


def _query_without_url(user_input, url):
    return str(user_input or "").replace(url, " ").strip()


def scores_from_verification(verification):
    source_reliability = min(
        85.0,
        round(
            verification["transparency_score"] * 0.85
            + verification["evidence_signal_score"] * 0.15,
            1,
        ),
    )
    information_confidence = min(
        75.0,
        round(
            verification["evidence_signal_score"] * 0.85
            + verification["query_overlap_percent"] * 0.15,
            1,
        ),
    )

    return {
        "source_reliability": source_reliability,
        "information_confidence": information_confidence,
    }


def verify_source_page(
    url,
    query="",
    settings=None,
    client=None,
):
    page = fetch_public_page(
        url,
        settings=settings,
        client=client,
    )

    if not page.get("available"):
        return {
            "available": False,
            "reason": page.get("reason", "Webbsidan kunde inte hämtas."),
        }

    verification = verify_page_content(page, query=query)

    scores = scores_from_verification(verification)

    return {
        "available": True,
        "url": page.get("final_url") or url,
        "title": page.get("title") or "",
        "source_reliability": scores["source_reliability"],
        "information_confidence": scores["information_confidence"],
        "verification": verification,
        "assessment_scope": "single_fetched_page_heuristic",
        "assessment_note": (
            "Källans tillförlitlighet och informationens konfidens är "
            "konservativa interna heuristiker baserade på en hämtad sida. "
            "De är inte sannolikheter eller garantier och inkluderar ännu "
            "inte oberoende bekräftelse från andra källor."
        ),
    }


def format_source_verification(result):
    if not result.get("available"):
        return "Källgranskningen kunde inte köras: " + result.get(
            "reason",
            "okänd orsak",
        )

    verification = result["verification"]
    lines = [
        f"URL: {result.get('url') or ''}",
    ]

    if result.get("title"):
        lines.append(f"Titel: {result['title']}")

    lines.extend(
        [
            (
                "Källans tillförlitlighet: "
                f"{result['source_reliability']:.1f}%"
            ),
            (
                "Informationens konfidens: "
                f"{result['information_confidence']:.1f}%"
            ),
            (
                "Transparenssignaler: "
                f"{verification['transparency_score']:.1f}/100"
            ),
            (
                "Evidenssignaler: "
                f"{verification['evidence_signal_score']:.1f}/100"
            ),
            (
                "Frågeöverlapp: "
                f"{verification['query_overlap_percent']:.1f}%"
            ),
            result["assessment_note"],
        ]
    )

    return "\n".join(lines)


def source_verify_page(user_input):
    try:
        url = extract_page_url(user_input)

        if not url:
            return (
                "Källgranskningen kunde inte köras: "
                "ingen http/https-adress hittades i frågan."
            )

        query = _query_without_url(user_input, url)
        return format_source_verification(
            verify_source_page(url, query=query)
        )
    except Exception as error:
        return f"Källgranskningen kunde inte köras: {error}"


TOOLS = {
    "source_verify_page": {
        "function": source_verify_page,
        "description": (
            "Hämtar och granskar en publik webbsida och gör separata, "
            "konservativa heuristiska bedömningar av källtillförlitlighet "
            "och informationskonfidens utifrån sidans metadata och "
            "evidenssignaler."
        ),
        "pass_user_input": True,
    }
}
