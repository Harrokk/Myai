from core.page_verification import verify_page_content
from modules.internet.fetch import fetch_public_page


def verify_source_page_data(
    url,
    query="",
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
                "Webbsidan kunde inte hämtas.",
            ),
        }

    verification = verify_page_content(
        page,
        query=query,
    )

    return {
        "available": True,
        "page": page,
        "verification": verification,
    }


def format_source_verification(result):
    if not result.get("available"):
        return "Källverifiering kunde inte köras: " + result.get(
            "reason",
            "okänd orsak",
        )

    verification = result["verification"]
    lines = [
        f"Källverifiering: {verification.get('url') or ''}",
        verification["assessment_note"],
        (
            "Transparensscore: "
            f"{verification['transparency_score']:.1f}%"
        ),
        (
            "Evidenssignalscore: "
            f"{verification['evidence_signal_score']:.1f}%"
        ),
    ]

    if verification.get("author"):
        lines.append(
            f"Författare: {verification['author']}"
        )

    if verification.get("published_date"):
        lines.append(
            f"Publiceringsdatum: {verification['published_date']}"
        )

    if verification.get("site_name"):
        lines.append(
            f"Webbplats/utgivare: {verification['site_name']}"
        )

    lines.append(
        "Signaler: "
        + ", ".join(
            f"{key}={'ja' if value else 'nej'}"
            for key, value in verification["signals"].items()
        )
    )

    lines.append("Transparens:")
    lines.extend(
        f"- {reason}"
        for reason in verification["transparency_reasons"]
    )
    lines.append("Evidenssignaler:")
    lines.extend(
        f"- {reason}"
        for reason in verification["evidence_reasons"]
    )

    return "\n".join(lines)


def web_verify_source(url, query=""):
    try:
        return format_source_verification(
            verify_source_page_data(
                url=url,
                query=query,
            )
        )
    except Exception as error:
        return f"Källverifiering misslyckades: {error}"


TOOLS = {
    "web_verify_source": {
        "function": web_verify_source,
        "description": (
            "Hämtar en publik webbsida säkert och bedömer sidans "
            "transparens samt metod-, data-, referens- och osäkerhetssignaler."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    }
}
