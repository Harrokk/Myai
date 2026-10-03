from urllib.parse import urlparse

from modules.internet.verify import verify_source_page_data


CONTACT_TERMS = (
    "contact", "kontakt", "kundservice", "customer service",
    "support", "e-post", "email",
)
RETURN_TERMS = (
    "return", "returns", "refund", "retur", "återbetalning",
    "ångerrätt", "right of withdrawal",
)
TERMS_TERMS = (
    "terms", "conditions", "villkor", "köpvillkor",
    "terms and conditions",
)
PRIVACY_TERMS = (
    "privacy", "integritet", "privacy policy",
)
ORG_TERMS = (
    "org.nr", "organisationsnummer", "vat number", "vat no",
    "momsregistreringsnummer", "company number", "registration number",
)
PAYMENT_TERMS = (
    "klarna", "paypal", "visa", "mastercard", "card payment",
    "kortbetalning", "apple pay", "google pay",
)
HIGH_RISK_PAYMENT_TERMS = (
    "bank transfer only",
    "wire transfer only",
    "crypto only",
    "bitcoin only",
    "cryptocurrency only",
)


def _contains(text, terms):
    lowered = (text or "").lower()
    return any(term in lowered for term in terms)


def assess_seller_page(verification_result):
    if not verification_result.get("available"):
        return {
            "available": False,
            "reason": verification_result.get(
                "reason",
                "Säljarens sida kunde inte verifieras.",
            ),
        }

    page = verification_result.get("page", {})
    verification = verification_result.get("verification", {})
    text = page.get("text", "") or ""
    final_url = (
        page.get("final_url")
        or page.get("requested_url")
        or ""
    )
    parsed = urlparse(final_url)

    signals = {
        "https": parsed.scheme == "https",
        "contact": _contains(text, CONTACT_TERMS),
        "returns": _contains(text, RETURN_TERMS),
        "terms": _contains(text, TERMS_TERMS),
        "privacy": _contains(text, PRIVACY_TERMS),
        "organization": _contains(text, ORG_TERMS),
        "normal_payment": _contains(text, PAYMENT_TERMS),
        "high_risk_payment": _contains(
            text,
            HIGH_RISK_PAYMENT_TERMS,
        ),
    }

    score = 20.0
    reasons = [
        "Bedömningen är en intern heuristik och inte en garanti för att säljaren är säker."
    ]

    if signals["https"]:
        score += 10
        reasons.append("Säljsidan använder HTTPS.")
    else:
        reasons.append("HTTPS kunde inte verifieras.")

    transparency = float(
        verification.get(
            "transparency_score",
            0.0,
        )
    )
    score += min(transparency, 90.0) * 0.20
    reasons.append(
        f"Sidans transparenssignal bidrar med {min(transparency, 90.0) * 0.20:.1f} poäng."
    )

    bonuses = (
        ("contact", 8, "Kontakt-/kundserviceinformation hittades."),
        ("returns", 8, "Retur/återbetalningsinformation hittades."),
        ("terms", 8, "Köpvillkor hittades."),
        ("privacy", 5, "Integritetsinformation hittades."),
        ("organization", 10, "Organisations-/VAT-information hittades."),
        ("normal_payment", 8, "Etablerat betalningsalternativ nämns."),
    )

    for signal, points, reason in bonuses:
        if signals[signal]:
            score += points
            reasons.append(reason)

    if signals["high_risk_payment"]:
        score -= 20
        reasons.append(
            "Sidan innehåller formulering om endast banköverföring/krypto; detta är en stark varningssignal."
        )

    if not signals["contact"]:
        reasons.append("Kontakt-/kundserviceinformation kunde inte verifieras.")

    if not signals["returns"]:
        reasons.append("Retur-/återbetalningsinformation kunde inte verifieras.")

    if not signals["terms"]:
        reasons.append("Köpvillkor kunde inte verifieras.")

    score = round(max(10.0, min(score, 85.0)), 1)

    return {
        "available": True,
        "url": final_url,
        "hostname": (parsed.hostname or "").lower(),
        "seller_reliability": score,
        "signals": signals,
        "reasons": reasons,
        "assessment_note": (
            "Säljarpoängen är en heuristisk risk-/transparensbedömning, "
            "inte en garanti för att köp är säkert."
        ),
    }


def vet_seller_url(
    url,
    settings=None,
    verify_function=None,
):
    active_verify = verify_function or verify_source_page_data
    verification_result = active_verify(
        url=url,
        query="butik kontakt retur villkor betalning företag",
        settings=settings,
    )

    return assess_seller_page(
        verification_result
    )


def format_seller_vetting(result):
    if not result.get("available"):
        return "Säljargranskning kunde inte köras: " + result.get(
            "reason",
            "okänd orsak",
        )

    lines = [
        f"Säljargranskning: {result.get('hostname') or result.get('url')}",
        result["assessment_note"],
        (
            "Säljarens interna tillförlitlighetsbedömning: "
            f"{result['seller_reliability']:.1f}%"
        ),
    ]

    lines.extend(
        f"- {reason}"
        for reason in result.get("reasons", [])
    )
    return "\n".join(lines)


def seller_vetting(url):
    try:
        return format_seller_vetting(
            vet_seller_url(url)
        )
    except Exception as error:
        return f"Säljargranskning misslyckades: {error}"


TOOLS = {
    "seller_vetting": {
        "function": seller_vetting,
        "description": (
            "Granskar en publik säljsida med interna heuristiska signaler "
            "för kontakt, retur, villkor, integritet, företagsinformation "
            "och betalningssätt. Resultatet är inte en säkerhetsgaranti."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    }
}
