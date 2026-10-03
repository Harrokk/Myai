from copy import deepcopy

from modules.internet.evaluation import select_top_candidates


ACCEPTED_STOCK = {"in_stock", "limited"}


def _money(value, field):
    try:
        amount = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} måste vara ett numeriskt SEK-belopp.") from error

    if amount < 0:
        raise ValueError(f"{field} får inte vara negativt.")

    return round(amount, 2)


def _delivery_text(candidate):
    minimum = candidate.get("delivery_days_min")
    maximum = candidate.get("delivery_days_max")

    if minimum is None and maximum is None:
        return None

    try:
        minimum = int(minimum) if minimum is not None else None
        maximum = int(maximum) if maximum is not None else None
    except (TypeError, ValueError) as error:
        raise ValueError("Leveransdagar måste vara heltal.") from error

    if minimum is not None and minimum < 0:
        raise ValueError("delivery_days_min får inte vara negativt.")

    if maximum is not None and maximum < 0:
        raise ValueError("delivery_days_max får inte vara negativt.")

    if minimum is not None and maximum is not None and maximum < minimum:
        raise ValueError("delivery_days_max får inte vara mindre än minimum.")

    if minimum is not None and maximum is not None:
        return f"{minimum}-{maximum} dagar"

    if minimum is not None:
        return f"från {minimum} dagar"

    return f"upp till {maximum} dagar"


def normalize_price_candidate(candidate):
    if not isinstance(candidate, dict):
        raise ValueError("Priskandidaten måste vara ett objekt/dict.")

    item = deepcopy(candidate)
    warnings = item.get("warning_flags", [])

    if warnings is None:
        warnings = []
    elif isinstance(warnings, str):
        warnings = [warnings]
    elif not isinstance(warnings, (list, tuple)):
        raise ValueError("warning_flags måste vara en lista med texter.")

    warnings = [str(value).strip() for value in warnings if str(value).strip()]
    price_reasons = []

    currency = str(item.get("currency") or "SEK").upper().strip()

    if currency != "SEK":
        price_reasons.append("priset är inte verifierat i SEK")
        warnings.append(f"valuta {currency} kräver extern växelkurs")

    product_raw = item.get("product_price_sek")

    if product_raw is None:
        product_price = None
        price_reasons.append("produktpris saknas")
    else:
        product_price = _money(product_raw, "product_price_sek")

    shipping_raw = item.get("shipping_sek")

    if shipping_raw is None:
        shipping = None
        price_reasons.append("frakt till Sverige är inte verifierad")
    else:
        shipping = _money(shipping_raw, "shipping_sek")

    vat_included = item.get("vat_included")

    if vat_included is True:
        vat_amount = 0.0
    elif vat_included is False:
        vat_raw = item.get("vat_amount_sek")

        if vat_raw is None:
            vat_amount = None
            price_reasons.append("momsbelopp saknas")
        else:
            vat_amount = _money(vat_raw, "vat_amount_sek")
    else:
        vat_amount = None
        price_reasons.append("momsstatus är inte verifierad")

    fees_known = item.get("additional_fees_known") is True

    if not fees_known:
        extra_fees = None
        price_reasons.append("eventuella extra avgifter är inte verifierade")
    else:
        extra_fees = _money(
            item.get("additional_fees_sek", 0),
            "additional_fees_sek",
        )

    ships_to_sweden = item.get("ships_to_sweden")

    if ships_to_sweden is not True:
        if ships_to_sweden is False:
            price_reasons.append("säljaren levererar inte till Sverige")
        else:
            price_reasons.append("leverans till Sverige är inte verifierad")

    stock_status = str(item.get("stock_status") or "unknown").lower().strip()

    if stock_status not in ACCEPTED_STOCK:
        if stock_status == "out_of_stock":
            price_reasons.append("produkten är slut i lager")
        else:
            price_reasons.append("lagerstatus är inte tillräckligt verifierad")

    delivery_text = _delivery_text(item)

    total_complete = all(
        value is not None
        for value in (
            product_price,
            shipping,
            vat_amount,
            extra_fees,
        )
    )

    total = (
        round(
            product_price + shipping + vat_amount + extra_fees,
            2,
        )
        if total_complete
        else None
    )

    practicality = 100.0

    if stock_status == "limited":
        practicality -= 10.0

    if delivery_text is None:
        practicality -= 10.0

    if price_reasons:
        practicality = min(practicality, 30.0)

    item.update(
        {
            "currency": currency,
            "product_price_sek": product_price,
            "shipping_sek": shipping,
            "vat_included": vat_included,
            "vat_amount_sek": vat_amount,
            "additional_fees_known": fees_known,
            "additional_fees_sek": extra_fees,
            "ships_to_sweden": ships_to_sweden,
            "stock_status": stock_status,
            "delivery_text": delivery_text,
            "total_price_sek": total,
            "total_price_complete": total_complete and not price_reasons,
            "practicality": max(0.0, practicality),
            "warning_flags": warnings,
            "price_exclusion_reasons": price_reasons,
            "disqualify": bool(item.get("disqualify", False) or price_reasons),
        }
    )

    return item


def compare_sweden_prices(candidates, settings=None):
    normalized = [
        normalize_price_candidate(candidate)
        for candidate in candidates
    ]

    evaluated = select_top_candidates(
        normalized,
        settings=settings,
    )

    eligible = [
        item
        for item in evaluated["evaluated_candidates"]
        if item["eligible"]
        and item.get("total_price_complete")
        and item.get("total_price_sek") is not None
    ]

    eligible.sort(
        key=lambda item: (
            item["total_price_sek"],
            -item["selection_score"],
            -item["source_reliability"],
            -item["information_confidence"],
        )
    )

    top = eligible[: evaluated["top_n"]]

    result = dict(evaluated)
    result["top_candidates"] = top
    result["ranking_mode"] = "lowest_complete_total_after_validation"
    return result


def format_sweden_price_comparison(result):
    top = result.get("top_candidates", [])
    evaluated_count = result.get("evaluated_count", 0)
    candidate_limit = result.get("candidate_limit", 5)

    if result.get("basis_fewer_than_limit"):
        lines = [
            f"Underlag: {evaluated_count} kandidater, färre än målet "
            f"{candidate_limit}."
        ]
    elif result.get("truncated_input"):
        lines = [
            f"Underlag: de första {candidate_limit} av "
            f"{result.get('input_count', evaluated_count)} kandidater."
        ]
    else:
        lines = [f"Underlag: {evaluated_count} kandidater."]

    lines.append(
        "Toppalternativ efter validering, sorterade på lägsta verifierbara "
        "totalpris:"
    )

    if not top:
        lines.append("- Inga kandidater hade tillräckligt komplett underlag.")
    else:
        for index, item in enumerate(top, start=1):
            seller = item.get("seller") or item.get("name") or "okänd säljare"
            vat_text = (
                "moms inkluderad"
                if item.get("vat_included") is True
                else f"moms {item.get('vat_amount_sek', 0):.2f} SEK"
            )
            delivery = item.get("delivery_text") or "leveranstid okänd"
            lines.append(
                f"{index}. {seller}: total {item['total_price_sek']:.2f} SEK "
                f"(produkt {item['product_price_sek']:.2f}, "
                f"frakt {item['shipping_sek']:.2f}, {vat_text}, "
                f"övriga avgifter {item['additional_fees_sek']:.2f}) | "
                f"lager {item['stock_status']} | {delivery} | "
                f"källa {item['source_reliability']:.1f}% | "
                f"info {item['information_confidence']:.1f}%"
            )

            if item.get("url"):
                lines.append(f"   {item['url']}")

    excluded = result.get("excluded_candidates", [])

    if excluded:
        lines.append("Bortsorterade:")

        for item in excluded:
            reasons = list(item.get("price_exclusion_reasons", []))
            reasons.extend(item.get("exclusion_reasons", []))
            reasons = list(dict.fromkeys(reasons))
            lines.append(
                f"- {item.get('seller') or item['name']}: "
                + ", ".join(reasons or ["otillräckligt underlag"])
            )

    lines.append(
        "Totalpriset används endast när pris, frakt, momsstatus och kända "
        "extra avgifter är verifierbara. Urvalspoängen är en intern "
        "heuristik, inte en sannolikhetsgaranti."
    )
    return "\n".join(lines)
