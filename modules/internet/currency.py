from core.config import load_settings
from core.fx_client import FrankfurterClient


def convert_amount_to_sek(
    amount,
    currency,
    settings=None,
    client=None,
):
    if isinstance(amount, bool) or not isinstance(
        amount,
        (int, float),
    ):
        raise ValueError("Beloppet måste vara ett tal.")

    if amount < 0:
        raise ValueError("Beloppet får inte vara negativt.")

    source = (currency or "").strip().upper()

    if source == "SEK":
        return {
            "amount": round(float(amount), 2),
            "currency": "SEK",
            "amount_sek": round(float(amount), 2),
            "rate": 1.0,
            "rate_date": None,
            "provider": "identity",
        }

    settings = settings or load_settings()
    internet = settings.get("internet", {})
    shopping = settings.get("shopping", {})

    if not internet.get("enabled", False):
        return {
            "available": False,
            "reason": "Internetåtkomst är avstängd; valutakurs kan inte hämtas.",
        }

    provider = (
        shopping.get("fx_provider")
        or "frankfurter"
    ).strip().lower()

    if provider != "frankfurter":
        return {
            "available": False,
            "reason": (
                "Okänd valutakursleverantör. "
                "För närvarande stöds frankfurter."
            ),
        }

    active_client = client or FrankfurterClient(
        base_url=shopping.get(
            "frankfurter_url",
            "https://api.frankfurter.app",
        ),
        timeout_seconds=shopping.get(
            "fx_timeout_seconds",
            10,
        ),
    )
    rate_info = active_client.rate_to_sek(source)
    rate = float(rate_info["rate"])

    return {
        "available": True,
        "amount": round(float(amount), 2),
        "currency": source,
        "amount_sek": round(float(amount) * rate, 2),
        "rate": rate,
        "rate_date": rate_info.get("date"),
        "provider": rate_info.get("provider"),
    }


def currency_to_sek(amount, currency):
    try:
        result = convert_amount_to_sek(
            amount,
            currency,
        )

        if result.get("available") is False:
            return (
                "Valutakonvertering kunde inte köras: "
                + result.get("reason", "okänd orsak")
            )

        return (
            f"{result['amount']:.2f} {result['currency']} = "
            f"{result['amount_sek']:.2f} SEK "
            f"(kurs {result['rate']:.6f}"
            + (
                f", datum {result['rate_date']}"
                if result.get("rate_date")
                else ""
            )
            + ")"
        )
    except Exception as error:
        return f"Valutakonvertering misslyckades: {error}"


TOOLS = {
    "currency_to_sek": {
        "function": currency_to_sek,
        "description": (
            "Konverterar ett belopp till SEK med en faktisk konfigurerad "
            "valutakurskälla. Gissar aldrig en saknad kurs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "currency": {"type": "string"},
            },
            "required": ["amount", "currency"],
            "additionalProperties": False,
        },
    }
}
