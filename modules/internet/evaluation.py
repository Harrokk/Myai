from copy import deepcopy

from core.config import load_settings


DEFAULT_RESEARCH = {
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
}


def _score(value, field):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} måste vara ett tal mellan 0 och 100.") from error

    if number < 0 or number > 100:
        raise ValueError(f"{field} måste vara mellan 0 och 100.")

    return number


def _research_config(settings=None):
    settings = settings or load_settings()
    configured = settings.get("research", {})
    config = deepcopy(DEFAULT_RESEARCH)

    for key, value in configured.items():
        if key == "weights" and isinstance(value, dict):
            config["weights"].update(value)
        else:
            config[key] = value

    try:
        candidate_limit = int(config["candidate_limit"])
        top_n = int(config["top_n"])
        min_source = _score(
            config["min_source_reliability"],
            "min_source_reliability",
        )
        min_info = _score(
            config["min_information_confidence"],
            "min_information_confidence",
        )
        min_relevance = _score(
            config["min_relevance"],
            "min_relevance",
        )
        warning_each = float(config["warning_penalty_each"])
        max_warning = float(config["max_warning_penalty"])
    except (TypeError, ValueError) as error:
        if isinstance(error, ValueError) and "måste" in str(error):
            raise
        raise ValueError("Research-konfigurationen innehåller ogiltiga tal.") from error

    if candidate_limit < 1 or candidate_limit > 20:
        raise ValueError("research.candidate_limit måste vara mellan 1 och 20.")

    if top_n < 1 or top_n > candidate_limit:
        raise ValueError("research.top_n måste vara mellan 1 och candidate_limit.")

    if warning_each < 0 or max_warning < 0:
        raise ValueError("Varningsavdrag får inte vara negativa.")

    weights = {}

    for key in (
        "relevance",
        "source_reliability",
        "information_confidence",
        "practicality",
    ):
        try:
            value = float(config["weights"].get(key, 0))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Vikten {key} måste vara numerisk.") from error

        if value < 0:
            raise ValueError(f"Vikten {key} får inte vara negativ.")

        weights[key] = value

    if sum(weights.values()) <= 0:
        raise ValueError("Minst en research-vikt måste vara större än 0.")

    return {
        "candidate_limit": candidate_limit,
        "top_n": top_n,
        "min_source_reliability": min_source,
        "min_information_confidence": min_info,
        "min_relevance": min_relevance,
        "warning_penalty_each": warning_each,
        "max_warning_penalty": max_warning,
        "weights": weights,
    }


def _candidate_warnings(candidate):
    warnings = candidate.get("warning_flags", [])

    if warnings is None:
        return []

    if isinstance(warnings, str):
        warnings = [warnings]

    if not isinstance(warnings, (list, tuple)):
        raise ValueError("warning_flags måste vara en lista med texter.")

    return [str(item).strip() for item in warnings if str(item).strip()]


def _evaluate_candidate(candidate, config):
    if not isinstance(candidate, dict):
        raise ValueError("Varje kandidat måste vara ett objekt/dict.")

    name = str(candidate.get("name") or "").strip()

    if not name:
        raise ValueError("Varje kandidat måste ha ett namn.")

    relevance = _score(candidate.get("relevance"), "relevance")
    source_reliability = _score(
        candidate.get("source_reliability"),
        "source_reliability",
    )
    information_confidence = _score(
        candidate.get("information_confidence"),
        "information_confidence",
    )

    practicality_raw = candidate.get("practicality")
    practicality = (
        _score(practicality_raw, "practicality")
        if practicality_raw is not None
        else None
    )

    warnings = _candidate_warnings(candidate)
    exclusion_reasons = []

    if bool(candidate.get("disqualify", False)):
        exclusion_reasons.append("uttryckligen diskvalificerad")

    if bool(candidate.get("critical_warning", False)):
        exclusion_reasons.append("kritisk varningssignal")

    if source_reliability < config["min_source_reliability"]:
        exclusion_reasons.append(
            "källtillförlitlighet under miniminivå"
        )

    if information_confidence < config["min_information_confidence"]:
        exclusion_reasons.append(
            "informationskonfidens under miniminivå"
        )

    if relevance < config["min_relevance"]:
        exclusion_reasons.append("relevans under miniminivå")

    values = {
        "relevance": relevance,
        "source_reliability": source_reliability,
        "information_confidence": information_confidence,
        "practicality": practicality,
    }

    weighted_sum = 0.0
    weight_sum = 0.0

    for key, value in values.items():
        if value is None:
            continue

        weight = config["weights"][key]

        if weight <= 0:
            continue

        weighted_sum += value * weight
        weight_sum += weight

    if weight_sum <= 0:
        raise ValueError("Kandidaten saknar poäng med aktiv vikt.")

    base_score = weighted_sum / weight_sum
    warning_penalty = min(
        config["max_warning_penalty"],
        len(warnings) * config["warning_penalty_each"],
    )
    selection_score = max(
        0.0,
        min(100.0, base_score - warning_penalty),
    )

    result = deepcopy(candidate)
    result.update(
        {
            "name": name,
            "relevance": round(relevance, 1),
            "source_reliability": round(source_reliability, 1),
            "information_confidence": round(
                information_confidence,
                1,
            ),
            "practicality": (
                round(practicality, 1)
                if practicality is not None
                else None
            ),
            "warning_flags": warnings,
            "warning_penalty": round(warning_penalty, 1),
            "selection_score": round(selection_score, 1),
            "eligible": not exclusion_reasons,
            "exclusion_reasons": exclusion_reasons,
        }
    )
    return result


def evaluate_candidate(candidate, settings=None):
    return _evaluate_candidate(
        candidate,
        _research_config(settings),
    )


def select_top_candidates(candidates, settings=None):
    config = _research_config(settings)
    pool = list(candidates)
    considered = pool[: config["candidate_limit"]]

    evaluated = [
        _evaluate_candidate(candidate, config)
        for candidate in considered
    ]

    eligible = [
        candidate
        for candidate in evaluated
        if candidate["eligible"]
    ]

    eligible.sort(
        key=lambda item: (
            item["selection_score"],
            item["information_confidence"],
            item["source_reliability"],
            item["relevance"],
        ),
        reverse=True,
    )

    top = eligible[: config["top_n"]]
    excluded = [
        candidate
        for candidate in evaluated
        if not candidate["eligible"]
    ]

    return {
        "input_count": len(pool),
        "candidate_limit": config["candidate_limit"],
        "evaluated_count": len(evaluated),
        "truncated_input": len(pool) > config["candidate_limit"],
        "basis_fewer_than_limit": (
            len(evaluated) < config["candidate_limit"]
        ),
        "top_n": config["top_n"],
        "top_candidates": top,
        "excluded_candidates": excluded,
        "evaluated_candidates": evaluated,
    }


def format_top_candidates(result):
    evaluated_count = result.get("evaluated_count", 0)
    candidate_limit = result.get("candidate_limit", 5)
    top = result.get("top_candidates", [])
    excluded = result.get("excluded_candidates", [])

    lines = []

    if result.get("basis_fewer_than_limit"):
        lines.append(
            f"Underlag: {evaluated_count} kandidater, färre än målet "
            f"{candidate_limit}."
        )
    elif result.get("truncated_input"):
        lines.append(
            f"Underlag: de första {candidate_limit} av "
            f"{result.get('input_count', evaluated_count)} inkomna kandidater."
        )
    else:
        lines.append(f"Underlag: {evaluated_count} kandidater.")

    lines.append("Toppalternativ:")

    if not top:
        lines.append("- Inga kandidater klarade valideringskraven.")
    else:
        for index, candidate in enumerate(top, start=1):
            practicality = candidate.get("practicality")
            practical_text = (
                f", praktik {practicality:.1f}%"
                if practicality is not None
                else ""
            )
            lines.append(
                f"{index}. {candidate['name']} — urval "
                f"{candidate['selection_score']:.1f}/100, "
                f"källa {candidate['source_reliability']:.1f}%, "
                f"info {candidate['information_confidence']:.1f}%, "
                f"relevans {candidate['relevance']:.1f}%"
                f"{practical_text}"
            )

    if excluded:
        lines.append("Bortsorterade:")

        for candidate in excluded:
            reasons = ", ".join(candidate["exclusion_reasons"])
            lines.append(f"- {candidate['name']}: {reasons}")

    lines.append(
        "Urvalspoängen är en intern heuristik för jämförelse och är inte "
        "en matematisk sannolikhet eller garanti för att uppgifterna är sanna."
    )

    return "\n".join(lines)
