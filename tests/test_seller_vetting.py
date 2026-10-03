from modules.internet import seller_vetting


def verification(text, transparency=70, url="https://shop.example/product"):
    return {
        "available": True,
        "page": {
            "final_url": url,
            "text": text,
        },
        "verification": {
            "transparency_score": transparency,
        },
    }


def test_transparent_seller_scores_above_sparse_seller():
    rich = seller_vetting.assess_seller_page(
        verification(
            "Kontakt kundservice retur återbetalning köpvillkor "
            "integritet organisationsnummer Klarna Visa Mastercard."
        )
    )
    sparse = seller_vetting.assess_seller_page(
        verification("Produkt till salu.", transparency=30)
    )

    assert rich["seller_reliability"] > sparse["seller_reliability"]


def test_high_risk_payment_signal_reduces_score():
    normal = seller_vetting.assess_seller_page(
        verification(
            "Kontakt retur villkor integritet organisationsnummer PayPal."
        )
    )
    risky = seller_vetting.assess_seller_page(
        verification(
            "Kontakt retur villkor integritet organisationsnummer "
            "bank transfer only."
        )
    )

    assert normal["seller_reliability"] > risky["seller_reliability"]
    assert risky["signals"]["high_risk_payment"] is True


def test_score_is_capped_below_guarantee_level():
    result = seller_vetting.assess_seller_page(
        verification(
            "Kontakt kundservice retur refund villkor terms privacy "
            "organisationsnummer VAT number Klarna PayPal Visa Mastercard."
        ),
    )

    assert result["seller_reliability"] <= 85


def test_failed_verification_is_unavailable():
    result = seller_vetting.assess_seller_page(
        {
            "available": False,
            "reason": "blocked",
        }
    )

    assert result["available"] is False
    assert result["reason"] == "blocked"


def test_vet_seller_uses_source_verification():
    seen = {}

    def fake_verify(url, query, settings=None):
        seen["url"] = url
        seen["query"] = query
        return verification(
            "Kontakt retur villkor organisationsnummer PayPal.",
            url=url,
        )

    result = seller_vetting.vet_seller_url(
        "https://shop.example/item",
        verify_function=fake_verify,
    )

    assert result["available"] is True
    assert seen["url"] == "https://shop.example/item"
    assert "retur" in seen["query"]


def test_tool_declares_url_parameter():
    schema = seller_vetting.TOOLS["seller_vetting"]["parameters"]

    assert schema["required"] == ["url"]
