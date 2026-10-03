from core.config import load_settings
from core.internet_client import SearXNGClient


def search_web(
    query,
    limit=5,
    settings=None,
    client=None,
):
    settings = settings or load_settings()
    config = settings.get("internet", {})

    if not config.get("enabled", False):
        return {
            "available": False,
            "reason": "Internetsökning är avstängd i konfigurationen.",
            "results": [],
        }

    provider = (config.get("provider") or "").strip().lower()

    if provider != "searxng":
        return {
            "available": False,
            "reason": (
                "Okänd sökleverantör. För närvarande stöds searxng."
            ),
            "results": [],
        }

    base_url = (config.get("searxng_url") or "").strip()

    if not base_url:
        return {
            "available": False,
            "reason": "Ingen SearXNG-adress är konfigurerad.",
            "results": [],
        }

    max_results = max(
        1,
        min(
            int(config.get("max_results", 5)),
            10,
        ),
    )
    requested = max(1, min(int(limit), max_results))

    active_client = client or SearXNGClient(
        base_url=base_url,
        timeout_seconds=config.get(
            "timeout_seconds",
            15,
        ),
        language=config.get(
            "language",
            "sv-SE",
        ),
    )

    results = active_client.search(
        query,
        limit=requested,
    )

    return {
        "available": True,
        "provider": "searxng",
        "query": query,
        "results": results,
    }


def format_search_results(result):
    if not result.get("available"):
        return "Internetsökning kunde inte köras: " + result.get(
            "reason",
            "okänd orsak",
        )

    results = result.get("results", [])

    if not results:
        return (
            f"Inga sökresultat hittades för: "
            f"{result.get('query') or ''}"
        )

    lines = [
        f"Sökresultat för: {result.get('query') or ''}"
    ]

    for index, item in enumerate(results, start=1):
        lines.append(
            f"{index}. {item.get('title') or 'Utan titel'}"
        )
        lines.append(
            f"   URL: {item.get('url') or ''}"
        )

        snippet = item.get("snippet")

        if snippet:
            lines.append(
                f"   Sammanfattning: {snippet}"
            )

        engines = item.get("engines") or []

        if engines:
            lines.append(
                "   Sökmotor: " + ", ".join(engines)
            )

    return "\n".join(lines)


def internet_search(query, limit=5):
    try:
        return format_search_results(
            search_web(
                query=query,
                limit=limit,
            )
        )
    except Exception as error:
        return f"Internetsökning misslyckades: {error}"


TOOLS = {
    "internet_search": {
        "function": internet_search,
        "description": (
            "Söker på internet via en uttryckligen konfigurerad SearXNG-instans "
            "och returnerar normaliserade titlar, länkar och utdrag."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }
}
