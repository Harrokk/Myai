from core import commerce_extraction


def page(text="", metadata=None):
    return {
        "requested_url": "https://shop.example/product",
        "final_url": "https://shop.example/product",
        "text": text,
        "metadata": metadata or {},
    }


def test_offer_uses_product_metadata_price():
    offer = commerce_extraction.extract_offer(
        page(
            text=(
                "Fri frakt. Inkl moms. I lager. "
                "Levererar till Sverige. 2-4 vardagar."
            ),
            metadata={
                "product:price:amount": "199,90",
                "product:price:currency": "SEK",
                "og:site_name": "Testbutiken",
            },
        )
    )

    assert offer["product_price"] == 199.90
    assert offer["currency"] == "SEK"
    assert offer["shipping_sek"] == 0
    assert offer["vat_included"] is True
    assert offer["in_stock"] is True
    assert offer["ships_to_sweden"] is True
    assert offer["total_price_sek"] == 199.90
    assert offer["seller"] == "Testbutiken"


def test_offer_extracts_sek_price_and_shipping_from_text():
    offer = commerce_extraction.extract_offer(
        page(
            text=(
                "Pris 249 kr. Frakt 49 kr. "
                "Inkl. moms. I lager. Frakt till Sverige."
            )
        )
    )

    assert offer["product_price"] == 249
    assert offer["shipping_sek"] == 49
    assert offer["total_price_sek"] == 298


def test_total_price_stays_unknown_when_vat_unknown():
    offer = commerce_extraction.extract_offer(
        page(
            text=(
                "Pris 249 kr. Frakt 49 kr. "
                "I lager. Leverans till Sverige."
            )
        )
    )

    assert offer["total_price_sek"] is None


def test_out_of_stock_and_no_sweden_delivery_are_detected():
    offer = commerce_extraction.extract_offer(
        page(
            text=(
                "199 kr. Inkl moms. Slut i lager. "
                "Levererar inte till Sverige."
            )
        )
    )

    assert offer["in_stock"] is False
    assert offer["ships_to_sweden"] is False
    assert commerce_extraction.practical_for_sweden(offer) is False


def test_non_sek_offer_is_not_practical_for_sweden():
    offer = commerce_extraction.extract_offer(
        page(
            text="In stock.",
            metadata={
                "product:price:amount": "20",
                "product:price:currency": "EUR",
            },
        )
    )

    assert commerce_extraction.practical_for_sweden(offer) is False


def test_product_price_before_shipping_label_is_not_shipping():
    offer = commerce_extraction.extract_offer(
        page(
            text=(
                "Pris 160 kr. Frakt beräknas i kassan. "
                "Inkl moms. I lager. Leverans till Sverige."
            )
        )
    )

    assert offer["product_price"] == 160
    assert offer["shipping_sek"] is None
    assert offer["total_price_sek"] is None
