from modules.internet import product_offer


def page(structured_data):
    return {
        "available": True,
        "requested_url": "https://shop.example/p/1",
        "final_url": "https://shop.example/p/1",
        "title": "Fallback title",
        "structured_data": structured_data,
    }


def test_extracts_product_offer_price_and_stock():
    result = product_offer.extract_product_offers(
        page(
            [
                {
                    "@context": "https://schema.org",
                    "@type": "Product",
                    "name": "ESP32 Dev Board",
                    "offers": {
                        "@type": "Offer",
                        "price": "129.90",
                        "priceCurrency": "SEK",
                        "availability": "https://schema.org/InStock",
                        "seller": {
                            "@type": "Organization",
                            "name": "Example Store",
                        },
                    },
                }
            ]
        )
    )

    assert len(result) == 1
    offer = result[0]
    assert offer["title"] == "ESP32 Dev Board"
    assert offer["product_price"] == 129.90
    assert offer["currency"] == "SEK"
    assert offer["stock_status"] == "in_stock"
    assert offer["store"] == "Example Store"


def test_extracts_vat_flag_from_price_specification():
    result = product_offer.extract_product_offers(
        page(
            [
                {
                    "@type": "Product",
                    "name": "Sensor",
                    "offers": {
                        "@type": "Offer",
                        "priceSpecification": {
                            "@type": "PriceSpecification",
                            "price": 100,
                            "priceCurrency": "SEK",
                            "valueAddedTaxIncluded": True,
                        },
                    },
                }
            ]
        )
    )

    assert result[0]["product_price"] == 100.0
    assert result[0]["vat_included"] is True


def test_extracts_explicit_sweden_shipping_rate():
    result = product_offer.extract_product_offers(
        page(
            [
                {
                    "@type": "Product",
                    "name": "Sensor",
                    "offers": {
                        "@type": "Offer",
                        "price": 100,
                        "priceCurrency": "SEK",
                        "shippingDetails": {
                            "@type": "OfferShippingDetails",
                            "shippingRate": {
                                "@type": "MonetaryAmount",
                                "value": 39,
                                "currency": "SEK",
                            },
                            "shippingDestination": {
                                "@type": "DefinedRegion",
                                "addressCountry": "SE",
                            },
                        },
                    },
                }
            ]
        )
    )

    assert result[0]["shipping_sek"] == 39.0
    assert result[0]["ships_to_sweden"] is True


def test_missing_shipping_remains_unknown():
    result = product_offer.extract_product_offers(
        page(
            [
                {
                    "@type": "Product",
                    "name": "Sensor",
                    "offers": {
                        "@type": "Offer",
                        "price": 100,
                        "priceCurrency": "SEK",
                    },
                }
            ]
        )
    )

    assert result[0]["shipping_sek"] is None
    assert result[0]["ships_to_sweden"] is None


def test_non_sek_offer_preserves_currency_without_conversion():
    result = product_offer.extract_product_offers(
        page(
            [
                {
                    "@type": "Product",
                    "name": "Sensor",
                    "offers": {
                        "@type": "Offer",
                        "price": "10.50",
                        "priceCurrency": "EUR",
                    },
                }
            ]
        )
    )

    assert result[0]["product_price"] == 10.5
    assert result[0]["currency"] == "EUR"


def test_no_structured_data_does_not_guess():
    result = product_offer.extract_product_offers(
        page([])
    )

    assert result == []


def test_extract_offer_page_data_uses_safe_fetch():
    def fake_fetch(url, settings=None):
        return page(
            [
                {
                    "@type": "Offer",
                    "name": "Standalone offer",
                    "price": 50,
                    "priceCurrency": "SEK",
                }
            ]
        )

    result = product_offer.extract_offer_page_data(
        "https://shop.example/p/1",
        fetch_function=fake_fetch,
    )

    assert result["available"] is True
    assert result["structured_offer_count"] == 1


def test_tool_declares_url_parameter():
    schema = product_offer.TOOLS["web_product_offer"]["parameters"]

    assert schema["required"] == ["url"]


def test_non_sek_shipping_preserves_value_and_currency():
    result = product_offer.extract_product_offers(
        page(
            [
                {
                    "@type": "Product",
                    "name": "Sensor",
                    "offers": {
                        "@type": "Offer",
                        "price": 10,
                        "priceCurrency": "EUR",
                        "shippingDetails": {
                            "@type": "OfferShippingDetails",
                            "shippingRate": {
                                "@type": "MonetaryAmount",
                                "value": 5,
                                "currency": "EUR",
                            },
                            "shippingDestination": {
                                "@type": "DefinedRegion",
                                "addressCountry": "SE",
                            },
                        },
                    },
                }
            ]
        )
    )

    assert result[0]["shipping_value"] == 5.0
    assert result[0]["shipping_currency"] == "EUR"
    assert result[0]["shipping_sek"] is None
    assert result[0]["ships_to_sweden"] is True


def test_extracts_structured_delivery_days():
    result = product_offer.extract_product_offers(
        page(
            [
                {
                    "@type": "Product",
                    "name": "Sensor",
                    "offers": {
                        "@type": "Offer",
                        "price": 100,
                        "priceCurrency": "SEK",
                        "shippingDetails": {
                            "@type": "OfferShippingDetails",
                            "shippingDestination": {
                                "@type": "DefinedRegion",
                                "addressCountry": "SE",
                            },
                            "deliveryTime": {
                                "@type": "ShippingDeliveryTime",
                                "handlingTime": {
                                    "@type": "QuantitativeValue",
                                    "minValue": 1,
                                    "maxValue": 2,
                                    "unitCode": "DAY",
                                },
                                "transitTime": {
                                    "@type": "QuantitativeValue",
                                    "minValue": 2,
                                    "maxValue": 4,
                                    "unitCode": "DAY",
                                },
                            },
                        },
                    },
                }
            ]
        )
    )

    assert result[0]["delivery_days"] == 6.0


def test_delivery_days_remain_unknown_for_non_day_units():
    result = product_offer.extract_product_offers(
        page(
            [
                {
                    "@type": "Product",
                    "name": "Sensor",
                    "offers": {
                        "@type": "Offer",
                        "price": 100,
                        "priceCurrency": "SEK",
                        "shippingDetails": {
                            "@type": "OfferShippingDetails",
                            "deliveryTime": {
                                "@type": "ShippingDeliveryTime",
                                "transitTime": {
                                    "@type": "QuantitativeValue",
                                    "value": 48,
                                    "unitCode": "HUR",
                                },
                            },
                        },
                    },
                }
            ]
        )
    )

    assert result[0]["delivery_days"] is None


def test_extracts_structured_return_policy():
    result = product_offer.extract_product_offers(
        page(
            [
                {
                    "@type": "Product",
                    "name": "Sensor",
                    "offers": {
                        "@type": "Offer",
                        "price": 100,
                        "priceCurrency": "SEK",
                        "hasMerchantReturnPolicy": {
                            "@type": "MerchantReturnPolicy",
                            "applicableCountry": "SE",
                            "returnPolicyCategory": (
                                "https://schema.org/MerchantReturnFiniteReturnWindow"
                            ),
                            "merchantReturnDays": 30,
                            "returnMethod": "https://schema.org/ReturnByMail",
                            "returnFees": "https://schema.org/FreeReturn",
                        },
                    },
                }
            ]
        )
    )

    policy = result[0]["return_policy"]
    assert policy["return_days"] == 30.0
    assert policy["applicable_country"] == "SE"
