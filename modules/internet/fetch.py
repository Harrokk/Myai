from core.config import load_settings
from core.public_web_client import PublicWebClient


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

    configured_max = max(
        1,
        min(
            int(config.get("max_page_chars", 20_000)),
            100_000,
        ),
    )
    requested_max = max(
        1,
        min(int(max_chars), configured_max),
    )

    active_client = client or PublicWebClient(
        timeout_seconds=config.get(
            "timeout_seconds",
            15,
        ),
        max_bytes=config.get(
            "max_page_bytes",
            1_000_000,
        ),
        max_redirects=config.get(
            "max_redirects",
            5,
        ),
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
        lines.append(
            f"Titel: {result['title']}"
        )

    lines.append("")
    lines.append(result.get("text") or "")

    if result.get("truncated"):
        lines.append("")
        lines.append(
            f"... [avkortat efter {result.get('max_chars')} tecken]"
        )

    return "\n".join(lines)


def web_fetch_text(url, max_chars=12_000):
    try:
        return format_public_page(
            fetch_public_page(
                url=url,
                max_chars=max_chars,
            )
        )
    except Exception as error:
        return f"Webbsidan kunde inte hämtas: {error}"


TOOLS = {
    "web_fetch_text": {
        "function": web_fetch_text,
        "description": (
            "Hämtar text från en publik http/https-webbsida med skydd mot "
            "privata/lokala IP-adresser, osäkra redirects och för stora svar."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    }
}
