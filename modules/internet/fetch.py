import re

from core.config import load_settings
from core.public_web_client import PublicWebClient


URL_PATTERN = re.compile(r"https?://[^\\s<>\\"']+", re.IGNORECASE)


def extract_page_url(user_input):
    text = str(user_input or "").strip()
    match = URL_PATTERN.search(text)

    if not match:
        return ""

    return match.group(0).rstrip(".,;:!?)]}")


def fetch_public_page(
    url,
    max_chars=12_000,
    settings=None,
    client=None,
):
    settings = settings or load_settings()
    config = settings.get("internet", {})

    if not config.get("enabled", False):
        return {
            "available": False,
            "reason": "Internetåtkomst är avstängd i konfigurationen.",
        }

    try:
        configured_max = int(config.get("max_page_chars", 20_000))
        max_bytes = int(config.get("max_page_bytes", 1_000_000))
        max_redirects = int(config.get("max_redirects", 5))
        requested_max = int(max_chars)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Internetinställningarna för webbsidor innehåller ogiltiga tal."
        ) from error

    if configured_max < 1 or configured_max > 100_000:
        raise ValueError(
            "internet.max_page_chars måste vara mellan 1 och 100000."
        )

    requested_max = max(1, min(requested_max, configured_max))

    active_client = client or PublicWebClient(
        timeout_seconds=config.get("timeout_seconds", 15),
        max_bytes=max_bytes,
        max_redirects=max_redirects,
    )

    page = active_client.fetch(url)
    text = page.get("text", "")
    truncated = len(text) > requested_max

    return {
        "available": True,
        **page,
        "text": text[:requested_max],
        "truncated": truncated,
        "max_chars": requested_max,
    }


def format_public_page(result):
    if not result.get("available"):
        return "Webbsidan kunde inte hämtas: " + result.get(
            "reason",
            "okänd orsak",
        )

    lines = [
        f"URL: {result.get('final_url') or ''}",
        f"Innehållstyp: {result.get('content_type') or ''}",
    ]

    if result.get("title"):
        lines.append(f"Titel: {result['title']}")

    lines.append("")
    lines.append(result.get("text") or "")

    if result.get("truncated"):
        lines.append("")
        lines.append(
            f"... [avkortat efter {result.get('max_chars')} tecken]"
        )

    return "\n".join(lines)


def web_fetch_text(user_input):
    try:
        url = extract_page_url(user_input)

        if not url:
            return (
                "Webbsidan kunde inte hämtas: "
                "ingen http/https-adress hittades i frågan."
            )

        return format_public_page(fetch_public_page(url=url))
    except Exception as error:
        return f"Webbsidan kunde inte hämtas: {error}"


TOOLS = {
    "web_fetch_text": {
        "function": web_fetch_text,
        "description": (
            "Hämtar läsbar text från en publik http/https-webbsida med skydd "
            "mot privata/lokala IP-adresser, osäkra redirects och för stora "
            "svar. Kräver att användarens fråga innehåller URL:en."
        ),
        "pass_user_input": True,
    }
}
