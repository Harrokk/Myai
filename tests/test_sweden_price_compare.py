from modules.internet import price_compare


def offer(
    name,
    price=100,
    shipping=20,
    vat_included=True,
    vat_amount=None,
    fees=0,
    fees_known=True,
    stock="in_stock",
    ships=True,
    source=80,
    confidence=80,
    relevance=80,
    delivery_min=2,
    delivery_max=5,
    **extra,
):
    item = {
        "name": name,
        "seller": name,
        "url": f"https://example.test/{name}",
        "currency": "SEK",
        "product_price_sek": price,
        "shipping_sek": shipping,
        "vat_included": vat_included,
        "additional_fees_known": fees_known,
        "additional_fees_sek": fees,
        "stock_status": stock,
        "ships_to_sweden": ships,
        "source_reliability": source,
        "information_confidence": confidence,
        "relevance": relevance,
        "delivery_days_min": delivery_min,
        "delivery_days_max": delivery_max,
    }

    if vat_amount is not None:
        item["vat_amount_sek"] = vat_amount

    item.update(extra)
    return item


def test_total_price_when_vat_is_included():
    item = price_compare.normalize_price_candidate(
        offer("A", price=100, shipping=25, fees=5)
    )

    assert item["total_price_sek"] == 130.0
    assert item["total_price_complete"] is True
    assert item["disqualify"] is False


def test_total_price_with_separate_vat():
    item = price_compare.normalize_price_candidate(
        offer(
            "A",
            price=100,
            shipping=20,
            vat_included=False,
            vat_amount=30,
            fees=5,
        )
    )

    assert item["total_price_sek"] == 155.0
    assert item["vat_amount_sek"] == 30.0


def test_unknown_vat_disqualifies_offer():
    item = price_compare.normalize_price_candidate(
        offer(
            "A",
            vat_included=None,
        )
    )

    assert item["disqualify"] is True
    assert item["total_price_complete"] is False
    assert "momsstatus" in item["price_exclusion_reasons"][0]


def test_unknown_extra_fees_disqualify_offer():
    item = price_compare.normalize_price_candidate(
        offer("A", fees_known=False)
    )

    assert item["disqualify"] is True
    assert any(
        "extra avgifter" in reason
        for reason in item["price_exclusion_reasons"]
    )


def test_non_sweden_shipping_disqualifies_offer():
    item = price_compare.normalize_price_candidate(
        offer("A", ships=False)
    )

    assert item["disqualify"] is True
    assert any(
        "inte till Sverige" in reason
        for reason in item["price_exclusion_reasons"]
    )


def test_out_of_stock_disqualifies_offer():
    item = price_compare.normalize_price_candidate(
        offer("A", stock="out_of_stock")
    )

    assert item["disqualify"] is True
    assert any(
        "slut i lager" in reason
        for reason in item["price_exclusion_reasons"]
    )


def test_non_sek_currency_is_not_silently_converted():
    item = price_compare.normalize_price_candidate(
        offer("A", currency="EUR")
    )

    assert item["disqualify"] is True
    assert item["currency"] == "EUR"
    assert any(
        "inte verifierat i SEK" in reason
        for reason in item["price_exclusion_reasons"]
    )


def test_three_cheapest_reliable_offers_are_selected():
    result = price_compare.compare_sweden_prices(
        [
            offer("Too risky", price=20, source=20),
            offer("A", price=80),
            offer("B", price=90),
            offer("C", price=100),
            offer("D", price=110),
        ],
        settings={},
    )

    assert [item["name"] for item in result["top_candidates"]] == [
        "A",
        "B",
        "C",
    ]
    assert any(
        item["name"] == "Too risky"
        for item in result["excluded_candidates"]
    )


def test_price_comparison_preserves_fewer_than_five_flag():
    result = price_compare.compare_sweden_prices(
        [offer("A"), offer("B")],
        settings={},
    )

    assert result["basis_fewer_than_limit"] is True
    assert len(result["top_candidates"]) == 2


def test_limited_stock_reduces_practicality_but_can_remain_eligible():
    item = price_compare.normalize_price_candidate(
        offer("A", stock="limited")
    )

    assert item["disqualify"] is False
    assert item["practicality"] == 90.0


def test_formatter_shows_total_and_confidence():
    result = price_compare.compare_sweden_prices(
        [offer("A", price=100, shipping=15)],
        settings={},
    )

    text = price_compare.format_sweden_price_comparison(result)

    assert "115.00 SEK" in text
    assert "källa 80.0%" in text
    assert "info 80.0%" in text
    assert "intern heuristik" in text
