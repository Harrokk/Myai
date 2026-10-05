from modules.internet import shopping


def settings():
    return {
        "schema_version": 1,
        "research": {
            "candidate_limit": 5,
            "top_n": 3,
            "min_source_reliability": 40,
            "min_information_confidence": 40,
            "min_relevance": 40,
            "warning_penalty_each": 5,
            "max_warning_penalty": 20,
            "weights": {
                "relevance": 0.30,
                "source_reliability": 0.30,
                "information_confidence": 0.30,
                "practicality": 0.10,
            },
        },
        "internet": {
            "enabled": True,
            "provider": "searxng",
            "searxng_url": "http://localhost:8080",
            "timeout_seconds": 15,
            "max_results": 5,
            "language": "sv-SE",
            "safesearch": 1,
        },
    }


def fake_search(
    query,
    settings=None,
):
    prices = [
        130,
        90,
        110,
        100,
        140,
    ]

    return {
        "success": True,
        "disabled": False,
        "provider": "fake",
        "query": query,
        "results": [
            {
                "title": (
                    f"Widget Pro butik {index}"
                ),
                "url": (
                    f"https://store{index}.example/widget"
                ),
                "snippet": (
                    "Widget Pro köp pris Sverige lager"
                ),
                "engine": "fake",
                "published_date": None,
                "_price": price,
            }
            for index, price in enumerate(
                prices,
                start=1,
            )
        ],
        "error": None,
    }


def fake_fetch(
    url,
    settings=None,
):
    number = int(
        url.split(
            "store",
            1,
        )[1].split(
            ".",
            1,
        )[0]
    )
    prices = {
        1: 130,
        2: 90,
        3: 110,
        4: 100,
        5: 140,
    }
    price = prices[
        number
    ]
    text = (
        "Widget Pro säljs i lager. "
        "Leverans till Sverige. "
        "Frakt 20 kr. "
        "Priset är inkl moms. "
        "Inga extra avgifter. "
        "Leverans 2-4 dagar. "
    ) * 20

    return {
        "available": True,
        "requested_url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "title": (
            f"Widget Pro butik {number}"
        ),
        "text": text,
        "metadata": {
            "og:site_name": (
                f"Butik {number}"
            ),
            "description": (
                "Widget Pro köp pris Sverige"
            ),
            "product:price:amount": str(
                price
            ),
            "product:price:currency": "SEK",
            "product:availability": "in stock",
        },
        "canonical_url": url,
        "external_links": [],
        "redirects": 0,
        "truncated": False,
        "max_chars": 20_000,
    }


def test_extract_shopping_query_removes_price_prefix():
    assert shopping.extract_shopping_query(
        "Jämför pris på Widget Pro"
    ) == "Widget Pro"


def test_offer_from_page_extracts_only_explicit_commercial_facts():
    search_result = fake_search(
        "Widget Pro",
        settings(),
    )[
        "results"
    ][
        0
    ]
    page = fake_fetch(
        search_result[
            "url"
        ]
    )

    offer = shopping.offer_from_page(
        "Widget Pro",
        search_result,
        page,
    )

    assert offer[
        "product_price_sek"
    ] == 130.0
    assert offer[
        "currency"
    ] == "SEK"
    assert offer[
        "shipping_sek"
    ] == 20.0
    assert offer[
        "vat_included"
    ] is True
    assert offer[
        "additional_fees_known"
    ] is True
    assert offer[
        "additional_fees_sek"
    ] == 0.0
    assert offer[
        "ships_to_sweden"
    ] is True
    assert offer[
        "stock_status"
    ] == "in_stock"
    assert offer[
        "delivery_days_min"
    ] == 2
    assert offer[
        "delivery_days_max"
    ] == 4
    assert offer[
        "information_confidence"
    ] == 100.0


def test_shopping_searches_five_and_returns_three_cheapest_complete():
    result = shopping.shopping_compare_data(
        "Widget Pro",
        settings=settings(),
        search_function=fake_search,
        fetch_function=fake_fetch,
    )

    assert result[
        "available"
    ] is True
    assert result[
        "offer_count"
    ] == 5
    assert [
        item[
            "seller"
        ]
        for item in result[
            "top_candidates"
        ]
    ] == [
        "Butik 2",
        "Butik 4",
        "Butik 3",
    ]
    assert [
        item[
            "total_price_sek"
        ]
        for item in result[
            "top_candidates"
        ]
    ] == [
        110.0,
        120.0,
        130.0,
    ]
    assert (
        result[
            "search_query"
        ]
        == "Widget Pro pris Sverige"
    )


def test_missing_shipping_is_not_guessed_and_offer_is_excluded():
    def no_shipping(
        url,
        settings=None,
    ):
        page = fake_fetch(
            url,
            settings=settings,
        )
        page[
            "text"
        ] = (
            "Widget Pro i lager. "
            "Leverans till Sverige. "
            "Priset är inkl moms. "
            "Inga extra avgifter. "
            "Leverans 2-4 dagar. "
        ) * 20
        return page

    result = shopping.shopping_compare_data(
        "Widget Pro",
        settings=settings(),
        search_function=lambda query, settings=None: {
            **fake_search(
                query,
                settings,
            ),
            "results": fake_search(
                query,
                settings,
            )[
                "results"
            ][
                :1
            ],
        },
        fetch_function=no_shipping,
    )

    assert result[
        "top_candidates"
    ] == []
    excluded = result[
        "excluded_candidates"
    ][
        0
    ]
    assert excluded[
        "shipping_sek"
    ] is None
    assert any(
        "frakt till Sverige"
        in reason
        for reason in excluded[
            "price_exclusion_reasons"
        ]
    )


def test_non_sek_offer_is_never_silently_converted():
    search_result = fake_search(
        "Widget Pro",
        settings(),
    )[
        "results"
    ][
        0
    ]
    page = fake_fetch(
        search_result[
            "url"
        ]
    )
    page[
        "metadata"
    ][
        "product:price:currency"
    ] = "EUR"

    offer = shopping.offer_from_page(
        "Widget Pro",
        search_result,
        page,
    )

    assert offer[
        "currency"
    ] == "EUR"
    assert offer[
        "product_price_sek"
    ] is None


def test_unfetchable_page_is_disqualified_not_invented():
    def failing_fetch(
        url,
        settings=None,
    ):
        return {
            "available": False,
            "reason": "synthetic fetch error",
        }

    result = shopping.shopping_compare_data(
        "Widget Pro",
        settings=settings(),
        search_function=lambda query, settings=None: {
            **fake_search(
                query,
                settings,
            ),
            "results": fake_search(
                query,
                settings,
            )[
                "results"
            ][
                :1
            ],
        },
        fetch_function=failing_fetch,
    )

    assert result[
        "top_candidates"
    ] == []
    assert result[
        "offers"
    ][
        0
    ][
        "disqualify"
    ] is True
    assert result[
        "offers"
    ][
        0
    ][
        "product_price_sek"
    ] is None


def test_formatter_explains_conservative_extraction():
    result = shopping.shopping_compare_data(
        "Widget Pro",
        settings=settings(),
        search_function=fake_search,
        fetch_function=fake_fetch,
    )

    text = shopping.format_shopping_comparison(
        result
    )

    assert "Toppalternativ" in text
    assert "gissas aldrig" in text
    assert "110.00 SEK" in text


def test_shopping_tool_is_query_aware():
    assert shopping.TOOLS[
        "shopping_compare_sweden"
    ][
        "pass_user_input"
    ] is True


def fx_settings():
    value = settings()
    value["fx"] = {
        "enabled": True,
        "provider": "ecb",
        "ecb_url": (
            "https://www.ecb.europa.eu/stats/eurofxref/"
            "eurofxref-daily.xml"
        ),
        "target_currency": "SEK",
        "max_age_days": 7,
    }
    return value


def eur_search(
    query,
    settings=None,
):
    return {
        "success": True,
        "disabled": False,
        "provider": "fake",
        "query": query,
        "results": [
            {
                "title": "Widget Euro Shop",
                "url": "https://euro.example/widget",
                "snippet": "Widget Pro price Sweden",
                "engine": "fake",
                "published_date": None,
            }
        ],
        "error": None,
    }


def eur_fetch(
    url,
    settings=None,
):
    text = (
        "Widget Pro in stock. "
        "Ships to Sweden. "
        "Shipping 10 EUR. "
        "Price including VAT. "
        "No additional fees. "
        "Delivery 2-4 days. "
    ) * 20

    return {
        "available": True,
        "requested_url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "title": "Widget Euro Shop",
        "text": text,
        "metadata": {
            "og:site_name": "Euro Shop",
            "description": "Widget Pro price Sweden",
            "product:price:amount": "100",
            "product:price:currency": "EUR",
            "product:availability": "in stock",
        },
        "canonical_url": url,
        "external_links": [],
        "redirects": 0,
        "truncated": False,
        "max_chars": 20_000,
    }


def verified_eur_quote(
    source,
    target,
    settings=None,
):
    assert source == "EUR"
    assert target == "SEK"
    return {
        "available": True,
        "verified": True,
        "provider": "ecb",
        "pair": "EUR/SEK",
        "source_currency": "EUR",
        "target_currency": "SEK",
        "rate": 11.0,
        "reference_date": "2026-10-05",
        "age_days": 0,
        "source_url": (
            "https://www.ecb.europa.eu/stats/eurofxref/"
            "eurofxref-daily.xml"
        ),
    }


def test_verified_fx_makes_complete_eur_offer_rankable():
    result = shopping.shopping_compare_data(
        "Widget Pro",
        settings=fx_settings(),
        search_function=eur_search,
        fetch_function=eur_fetch,
        fx_function=verified_eur_quote,
    )

    assert len(
        result[
            "top_candidates"
        ]
    ) == 1
    item = result[
        "top_candidates"
    ][
        0
    ]
    assert item[
        "original_currency"
    ] == "EUR"
    assert item[
        "currency"
    ] == "SEK"
    assert item[
        "fx_converted"
    ] is True
    assert item[
        "product_price_sek"
    ] == 1100.0
    assert item[
        "shipping_sek"
    ] == 110.0
    assert item[
        "total_price_sek"
    ] == 1210.0
    assert item[
        "fx_conversion"
    ][
        "provider"
    ] == "ecb"


def test_missing_verified_fx_keeps_foreign_offer_excluded():
    def missing_quote(
        source,
        target,
        settings=None,
    ):
        return {
            "available": False,
            "verified": False,
            "source_currency": source,
            "target_currency": target,
            "reason": "synthetic no quote",
        }

    result = shopping.shopping_compare_data(
        "Widget Pro",
        settings=fx_settings(),
        search_function=eur_search,
        fetch_function=eur_fetch,
        fx_function=missing_quote,
    )

    assert result[
        "top_candidates"
    ] == []
    item = result[
        "evaluated_candidates"
    ][
        0
    ]
    assert item[
        "currency"
    ] == "EUR"
    assert item[
        "product_price_sek"
    ] is None
    assert any(
        "Verifierad växelkurs"
        in warning
        for warning in item[
            "warning_flags"
        ]
    )


def test_same_foreign_currency_reuses_one_verified_quote():
    calls = []

    def two_search(
        query,
        settings=None,
    ):
        data = eur_search(
            query,
            settings=settings,
        )
        data[
            "results"
        ] = [
            {
                **data[
                    "results"
                ][
                    0
                ],
                "title": "Euro Shop 1",
                "url": "https://euro1.example/widget",
            },
            {
                **data[
                    "results"
                ][
                    0
                ],
                "title": "Euro Shop 2",
                "url": "https://euro2.example/widget",
            },
        ]
        return data

    def quote(
        source,
        target,
        settings=None,
    ):
        calls.append(
            (
                source,
                target,
            )
        )
        return verified_eur_quote(
            source,
            target,
            settings=settings,
        )

    result = shopping.shopping_compare_data(
        "Widget Pro",
        settings=fx_settings(),
        search_function=two_search,
        fetch_function=eur_fetch,
        fx_function=quote,
    )

    assert len(
        result[
            "top_candidates"
        ]
    ) == 2
    assert calls == [
        (
            "EUR",
            "SEK",
        )
    ]
