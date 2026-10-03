import requests

from core.config import load_settings


def _internet_config(settings=None):
    settings = settings or load_settings()
    internet = settings.get("internet", {})

    try:
        timeout = float(internet.get("timeout_seconds", 15))
        max_results = int(internet.get("max_results", 5))
        safesearch = int(internet.get("safesearch", 1))
    except (TypeError, ValueError) as error:
        raise ValueError("Internetinställningarna innehåller ogiltiga tal.") from error

    if timeout <= 0 or timeout > 120:
        raise ValueError("internet.timeout_seconds måste vara > 0 och <= 120.")

    if max_results <= 0 or max_results > 20:
        raise ValueError("internet.max_results måste vara mellan 1 och 20.")

    if safesearch not in {0, 1, 2}:
        raise ValueError("internet.safesearch måste vara 0, 1 eller 2.")

    return {
        "enabled": bool(internet.get("enabled", False)),
        "provider": str(internet.get("provider") or "searxng").strip().lower(),
        "searxng_url": str(
            internet.get("searxng_url") or "http://localhost:8080"
        ).strip(),
        "timeout_seconds": timeout,
        "max_results": max_results,
        "language": str(internet.get("language") or "sv-SE").strip(),
        "safesearch": safesearch,
    }


def extract_search_query(user_input):
    text = str(user_input or "").strip()

    prefixes = (
        "sök på internet efter ",
        "sök på webben efter ",
        "sök internet efter ",
        "webbsök efter ",
        "search the web for ",
        "search internet for ",
    )

    lowered = text.lower()

    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()

    return text


def _normalize_result(item):
    if not isinstance(item, dict):
        return None

    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()

    if not title or not url:
        return None

    snippet = str(
        item.get("content")
        or item.get("snippet")
        or ""
    ).strip()

    engine = item.get("engine")

    if not engine:
        engines = item.get("engines")

        if isinstance(engines, list) and engines:
            engine = engines[0]

    published = (
        item.get("publishedDate")
        or item.get("published_date")
        or None
    )

    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "engine": str(engine).strip() if engine else None,
        "published_date": str(published).strip() if published else None,
    }


def search_web(query, settings=None, session=requests):
    config = _internet_config(settings)
    query = str(query or "").strip()

    if not config["enabled"]:
        return {
            "success": False,
            "disabled": True,
            "provider": config["provider"],
            "query": query,
            "results": [],
            "error": "Internetsökning är avstängd i konfigurationen.",
        }

    if not query:
        return {
            "success": False,
            "disabled": False,
            "provider": config["provider"],
            "query": query,
            "results": [],
            "error": "Sökfrågan är tom.",
        }

    if config["provider"] != "searxng":
        return {
            "success": False,
            "disabled": False,
            "provider": config["provider"],
            "query": query,
            "results": [],
            "error": f"Internetprovidern stöds inte ännu: {config['provider']}",
        }

    base_url = config["searxng_url"]

    if not base_url:
        return {
            "success": False,
            "disabled": False,
            "provider": "searxng",
            "query": query,
            "results": [],
            "error": "Ingen SearXNG-adress är konfigurerad.",
        }

    endpoint = base_url.rstrip("/") + "/search"

    response = session.get(
        endpoint,
        params={
            "q": query,
            "format": "json",
            "language": config["language"],
            "safesearch": config["safesearch"],
        },
        timeout=config["timeout_seconds"],
    )
    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("SearXNG-svaret är inte ett JSON-objekt.")

    raw_results = payload.get("results", [])

    if not isinstance(raw_results, list):
        raise ValueError("SearXNG-svaret saknar en giltig results-lista.")

    normalized = []

    for item in raw_results:
        result = _normalize_result(item)

        if result is None:
            continue

        normalized.append(result)

        if len(normalized) >= config["max_results"]:
            break

    return {
        "success": True,
        "disabled": False,
        "provider": "searxng",
        "query": query,
        "results": normalized,
        "error": None,
    }


def format_search_results(result):
    if result.get("disabled"):
        return (
            "Internetsökning är avstängd. Aktivera internet.enabled och "
            "konfigurera en SearXNG-endpoint."
        )

    if not result.get("success"):
        return (
            "Internetsökningen misslyckades: "
            + (result.get("error") or "okänt fel")
        )

    results = result.get("results", [])

    if not results:
        return f"Inga sökresultat hittades för: {result.get('query', '')}"

    lines = [
        (
            f"Internetsökning via {result.get('provider')}: "
            f"{result.get('query')}"
        )
    ]

    for index, item in enumerate(results, start=1):
        lines.append(f"{index}. {item['title']}")
        lines.append(f"   {item['url']}")

        if item.get("snippet"):
            lines.append(f"   {item['snippet']}")

        metadata = []

        if item.get("engine"):
            metadata.append(f"motor={item['engine']}")

        if item.get("published_date"):
            metadata.append(f"datum={item['published_date']}")

        if metadata:
            lines.append("   " + ", ".join(metadata))

    lines.append(
        "Sökresultaten är råa kandidater och har ännu inte automatiskt "
        "källgranskats eller tilldelats konfidenspoäng."
    )
    return "\n".join(lines)


def internet_search(user_input):
    try:
        query = extract_search_query(user_input)
        return format_search_results(search_web(query))
    except Exception as error:
        return f"Internetsökningen misslyckades: {error}"


TOOLS = {
    "internet_search": {
        "function": internet_search,
        "description": (
            "Söker på webben via en uttryckligen konfigurerad SearXNG-provider "
            "och returnerar råa sökresultat. Kräver användarens sökfråga."
        ),
        "pass_user_input": True,
    }
}
