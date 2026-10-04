from core.geniex_vision_client import GenieXVisionClient
from core.vision_client import VisionClient


def build_vision_client(settings):
    config = settings.get(
        "vision",
        {},
    )
    provider = str(
        config.get(
            "provider",
            "ollama",
        )
    ).strip().lower()
    model = str(
        config.get(
            "model",
            "",
        )
        or ""
    ).strip()
    enabled = bool(
        config.get(
            "enabled",
            False,
        )
    )

    if provider == "ollama":
        return VisionClient(
            url=config.get(
                "url",
                settings.get(
                    "ollama",
                    {},
                ).get(
                    "url",
                    "http://localhost:11434/api/chat",
                ),
            ),
            model=model,
            enabled=enabled,
        )

    if provider == "geniex":
        geniex = settings.get(
            "geniex",
            {},
        )
        return GenieXVisionClient(
            base_url=config.get(
                "url",
                geniex.get(
                    "base_url",
                    "http://127.0.0.1:18181/v1",
                ),
            ),
            model=model,
            enabled=enabled,
            api_key=geniex.get(
                "api_key",
                "geniex",
            ),
            max_tokens=config.get(
                "max_tokens",
                256,
            ),
            temperature=config.get(
                "temperature",
                0.2,
            ),
        )

    raise ValueError(
        f"Okänd vision-provider: {provider}. "
        "Tillåtna värden är ollama och geniex."
    )
