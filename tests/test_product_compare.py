from modules.internet import product_compare


def settings():
    return {
        "research": {
            "candidate_limit": 5,
            "top_results": 3,
            "deep_blend": 0.40,
            "weights": {
                "relevance": 0.40,
                "source_reliability": 0.35,
                "information_confidence": 0.25,
            },
        },
        "shopping": {
            "top_results": 3,
            "min_source_reliability": 50,
        },
    }


def fake_search(query, limit, settings):
    return {
        "available": True,
        "results": [
            {
                "title": f"ESP32 offer {index}",
                "url": f"https://shop{index}.example/esp32",
                "snippet": "ESP32 board price Sweden shop offer",
                "engines": ["engine"],
                "published_date": "2026-10-03",
            }
            for index in range(1, 6)
        ],
    }


def fake_verify(url, query, settings):
    index = int(
        url.split("shop", 1)[1].split(".", 1)[0]
    )
    prices = {
        1: (220, 0),
        2: (180, 40),
        3: (210, 0),
        4: (160, None),
        5: (230, 20),
    }
    price, shipping = prices[index]

    if shipping is None:
        shipping_text = "Frakt beräknas i kassan."
    elif shipping == 0:
        shipping_text = "Fri frakt."
    else:
        shipping_text = f"Frakt {shipping} kr."

    return {
        "available": True,
        "page": {
            "requested_url": url,
            "final_url": url,
            "title": f"ESP32 offer {index}",
            "text": (
                f"Pris {price} kr. {shipping_text} "
                "Inkl moms. I lager. Leverans till Sverige. "
                "2-4 vardagar. Methods data results references limitations."
            ),
            "metadata": {
                "og:site_name": f"Shop {index}",
            },
            "external_links": [],
        },
        "verification": {
            "url": url,
            "transparency_score": 75,
            "evidence_signal_score": 70,
            "assessment_note": "test",
        },
    }


def test_product_comparison_returns_three_and_prefers_known_total():
    result = product_compare.compare_products_sweden_data(
        "ESP32",
        settings=settings(),
        search_function=fake_search,
        verify_function=fake_verify,
    )

    assert result["candidate_count"] == 5
    assert len(result["top"]) == 3
    totals = [
        item["offer"]["total_price_sek"]
        for item in result["top"]
    ]
    assert totals == [210, 220, 220]


def test_unknown_shipping_does_not_create_total_price():
    result = product_compare.compare_products_sweden_data(
        "ESP32",
        settings=settings(),
        search_function=fake_search,
        verify_function=fake_verify,
    )

    candidate = next(
        item
        for item in result["candidates"]
        if "shop4.example" in item["url"]
    )

    assert candidate["offer"]["shipping_sek"] is None
    assert candidate["offer"]["total_price_sek"] is None


def test_comparison_formatter_marks_unknown_values():
    result = product_compare.compare_products_sweden_data(
        "ESP32",
        settings=settings(),
        search_function=fake_search,
        verify_function=fake_verify,
    )
    text = product_compare.format_product_comparison(result)

    assert "Prisjämförelse för Sverige" in text
    assert "Totalpris" in text
    assert "Källans tillförlitlighet" in text


def test_product_compare_tool_requires_query():
    schema = product_compare.TOOLS[
        "product_compare_sweden"
    ]["parameters"]

    assert schema["required"] == ["query"]
