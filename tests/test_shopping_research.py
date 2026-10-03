from modules.internet import shopping


def settings():
    return {
        "shopping": {
            "candidate_pages": 5,
            "top_results": 3,
            "min_seller_reliability": 50,
        },
        "internet": {
            "enabled": True,
        },
    }


def fake_search(query, limit, settings):
    return {
        "available": True,
        "results": [
            {"url": "https://one.example/p"},
            {"url": "https://two.example/p"},
        ],
    }


def fake_extract(url, settings=None):
    store = "One Store" if "one." in url else "Two Store"
    price = 10 if "one." in url else 9

    return {
        "available": True,
        "url": url,
        "page": {
            "requested_url": url,
            "final_url": url,
            "title": store,
            "text": (
                "Kontakt retur villkor integritet organisationsnummer "
                "Klarna Product details."
            ),
            "metadata": {
                "description": "Product details",
                "og:site_name": store,
            },
            "canonical_url": url,
            "external_links": [],
        },
        "offers": [
            {
                "title": "ESP32",
                "store": store,
                "url": url,
                "product_price": price,
                "currency": "EUR",
                "shipping_value": 2,
                "shipping_currency": "EUR",
                "shipping_sek": None,
                "vat_included": True,
                "vat_sek": None,
                "fees_sek": 0,
                "stock_status": "in_stock",
                "ships_to_sweden": True,
                "source": "json_ld",
            }
        ],
    }


def fake_convert(amount, currency, settings=None):
    assert currency == "EUR"
    return {
        "available": True,
        "amount": amount,
        "currency": currency,
        "amount_sek": round(amount * 11, 2),
        "rate": 11,
        "rate_date": "2026-10-03",
        "provider": "test",
    }


def test_shopping_research_combines_search_extract_fx_and_vetting():
    result = shopping.shopping_research_data(
        "ESP32",
        settings=settings(),
        search_function=fake_search,
        extract_function=fake_extract,
        convert_function=fake_convert,
    )

    assert result["available"] is True
    assert result["page_count"] == 2
    assert result["parsed_offer_count"] == 2
    assert result["offers"][0]["product_price_sek"] == 110
    assert result["offers"][0]["shipping_sek"] == 22
    assert result["offers"][0]["seller_reliability"] >= 50
    assert result["comparison"]["eligible_count"] == 2
    assert result["comparison"]["top"][0]["store"] == "Two Store"


def test_explicit_urls_skip_search():
    def fail_search(*args, **kwargs):
        raise AssertionError("search should not be used")

    result = shopping.shopping_research_data(
        "ESP32",
        urls=["https://one.example/p"],
        settings=settings(),
        search_function=fail_search,
        extract_function=fake_extract,
        convert_function=fake_convert,
    )

    assert result["page_count"] == 1
    assert result["parsed_offer_count"] == 1


def test_failed_page_does_not_abort_other_pages():
    def sometimes_extract(url, settings=None):
        if "one." in url:
            raise RuntimeError("fetch failed")
        return fake_extract(url, settings=settings)

    result = shopping.shopping_research_data(
        "ESP32",
        settings=settings(),
        search_function=fake_search,
        extract_function=sometimes_extract,
        convert_function=fake_convert,
    )

    assert result["available"] is True
    assert result["parsed_offer_count"] == 1
    assert result["pages"][0]["status"] == "failed"


def test_unknown_currency_keeps_offer_incomplete():
    def bad_extract(url, settings=None):
        result = fake_extract(url, settings=settings)
        result["offers"][0]["currency"] = None
        return result

    result = shopping.shopping_research_data(
        "ESP32",
        urls=["https://one.example/p"],
        settings=settings(),
        extract_function=bad_extract,
        convert_function=fake_convert,
    )

    assert result["offers"][0]["product_price_sek"] is None
    assert result["comparison"]["eligible_count"] == 0


def test_missing_fees_remain_incomplete():
    def no_fee_extract(url, settings=None):
        result = fake_extract(url, settings=settings)
        result["offers"][0]["fees_sek"] = None
        return result

    result = shopping.shopping_research_data(
        "ESP32",
        urls=["https://one.example/p"],
        settings=settings(),
        extract_function=no_fee_extract,
        convert_function=fake_convert,
    )

    assert result["comparison"]["eligible_count"] == 0
    assert "avgifter" in result["comparison"]["incomplete"][0]["missing_costs"]


def test_tool_declares_query_and_optional_urls():
    schema = shopping.TOOLS["shopping_research_sweden"]["parameters"]

    assert schema["required"] == ["query"]
    assert schema["properties"]["urls"]["type"] == "array"
