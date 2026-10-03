import pytest

from modules.internet import price_compare


def offer(**overrides):
    value = {
        "title": "ESP32",
        "store": "Butik",
        "url": "https://example.com/product",
        "product_price_sek": 100,
        "shipping_sek": 29,
        "vat_included": True,
        "vat_sek": None,
        "fees_sek": 0,
        "stock_status": "in_stock",
        "ships_to_sweden": True,
        "delivery_days": 3,
        "seller_reliability": 80,
    }
    value.update(overrides)
    return value


def test_total_price_uses_all_known_costs():
    item = price_compare.normalize_offer(
        offer(
            product_price_sek=100,
            shipping_sek=20,
            vat_included=False,
            vat_sek=25,
            fees_sek=5,
        )
    )

    assert item["total_price_sek"] == 150.0


def test_vat_included_does_not_require_separate_vat():
    item = price_compare.normalize_offer(
        offer(vat_included=True, vat_sek=None)
    )

    assert item["total_price_sek"] == 129.0
    assert "moms" not in item["missing_costs"]


def test_missing_shipping_does_not_assume_zero():
    item = price_compare.normalize_offer(
        offer(shipping_sek=None)
    )

    assert item["total_price_sek"] is None
    assert "frakt" in item["missing_costs"]


def test_compare_sorts_by_total_price():
    result = price_compare.compare_offers_sweden(
        [
            offer(store="Dyrare", product_price_sek=120),
            offer(store="Billigare", product_price_sek=90),
        ]
    )

    assert result["top"][0]["store"] == "Billigare"
    assert result["top"][1]["store"] == "Dyrare"


def test_non_sweden_offer_is_rejected():
    result = price_compare.compare_offers_sweden(
        [
            offer(ships_to_sweden=False),
        ]
    )

    assert result["eligible_count"] == 0
    assert len(result["rejected"]) == 1


def test_out_of_stock_offer_is_rejected():
    result = price_compare.compare_offers_sweden(
        [
            offer(stock_status="out_of_stock"),
        ]
    )

    assert len(result["rejected"]) == 1


def test_unknown_shipping_goes_to_incomplete():
    result = price_compare.compare_offers_sweden(
        [
            offer(shipping_sek=None),
        ]
    )

    assert result["eligible_count"] == 0
    assert len(result["incomplete"]) == 1


def test_low_reliability_goes_to_incomplete():
    result = price_compare.compare_offers_sweden(
        [
            offer(seller_reliability=40),
        ],
        min_seller_reliability=50,
    )

    assert result["eligible_count"] == 0
    assert len(result["incomplete"]) == 1


def test_top_list_is_capped_at_three():
    result = price_compare.compare_offers_sweden(
        [
            offer(store=f"Store {i}", product_price_sek=100 + i)
            for i in range(5)
        ],
        top_n=10,
    )

    assert len(result["top"]) == 3


def test_invalid_negative_cost_is_rejected():
    with pytest.raises(ValueError):
        price_compare.normalize_offer(
            offer(shipping_sek=-1)
        )


def test_tool_declares_offers_parameter():
    schema = price_compare.TOOLS["price_compare_sweden"]["parameters"]

    assert schema["required"] == ["offers"]
