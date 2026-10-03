from core.config import load_settings
from core.source_conflicts import (
    apply_conflict_penalties,
    detect_numeric_conflicts,
)
from core.source_evaluation import (
    apply_deep_verification,
    evaluate_candidates,
)
from modules.internet.search import search_web
from modules.internet.verify import verify_source_page_data


def research_top_three_data(
    query,
    settings=None,
    search_function=None,
    verify_function=None,
):
    settings = settings or load_settings()
    config = settings.get("research", {})

    candidate_limit = max(
        1,
        min(int(config.get("candidate_limit", 5)), 5),
    )
    top_results = max(
        1,
        min(int(config.get("top_results", 3)), 3),
    )
    weights = config.get("weights", {})
    deep_enabled = bool(
        config.get("deep_verification_enabled", False)
    )
    deep_blend = float(
        config.get("deep_blend", 0.40)
    )
    active_search = search_function or search_web
    active_verify = (
        verify_function or verify_source_page_data
    )

    search_result = active_search(
        query=query,
        limit=candidate_limit,
        settings=settings,
    )

    if not search_result.get("available"):
        return {
            "available": False,
            "reason": search_result.get(
                "reason",
                "Internetsökningen kunde inte köras.",
            ),
            "candidates": [],
            "top": [],
        }

    candidates = list(search_result.get("results", []))[:candidate_limit]
    evaluated = evaluate_candidates(
        query,
        candidates,
        weights=weights,
    )

    verified_count = 0
    final_candidates = []

    for candidate in evaluated:
        if not deep_enabled:
            item = dict(candidate)
            item["deep_verification_status"] = "disabled"
            final_candidates.append(item)
            continue

        try:
            verification_result = active_verify(
                url=candidate.get("url", ""),
                query=query,
                settings=settings,
            )
        except Exception as error:
            item = dict(candidate)
            item["deep_verification_status"] = "failed"
            item["deep_verification_reason"] = str(error)
            final_candidates.append(item)
            continue

        if not verification_result.get("available"):
            item = dict(candidate)
            item["deep_verification_status"] = "unavailable"
            item["deep_verification_reason"] = (
                verification_result.get(
                    "reason",
                    "Djupverifiering saknas.",
                )
            )
            final_candidates.append(item)
            continue

        verification = verification_result.get(
            "verification",
            {},
        )
        item = apply_deep_verification(
            candidate,
            verification,
            weights=weights,
            deep_blend=deep_blend,
        )
        verified_count += 1
        final_candidates.append(item)

    conflict_penalty = float(
        config.get("conflict_penalty", 10.0)
    )
    conflicts = detect_numeric_conflicts(
        final_candidates,
        relative_tolerance=float(
            config.get("conflict_relative_tolerance", 0.05)
        ),
    )
    final_candidates = apply_conflict_penalties(
        final_candidates,
        conflicts,
        weights=weights,
        penalty_per_conflict=conflict_penalty,
    )

    return {
        "available": True,
        "query": query,
        "candidate_count": len(candidates),
        "deep_verification_enabled": deep_enabled,
        "deep_verified_count": verified_count,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
        "candidates": final_candidates,
        "top": final_candidates[:top_results],
        "assessment_note": (
            "Procentsiffrorna är interna heuristiska bedömningar, inte "
            "matematiska sannolikheter. När djupverifiering lyckas blandas "
            "sidans transparens- och evidenssignaler in i slutpoängen."
        ),
    }


def format_research_top_three(result):
    if not result.get("available"):
        return "Research kunde inte köras: " + result.get(
            "reason",
            "okänd orsak",
        )

    count = result.get("candidate_count", 0)
    lines = [
        f"Validerat underlag: {count} kandidat(er).",
        result.get("assessment_note", ""),
    ]

    if count < 5:
        lines.append(
            "Underlaget innehåller färre än fem kandidater."
        )

    conflict_count = result.get("conflict_count", 0)

    if conflict_count:
        lines.append(
            f"Varning: {conflict_count} numerisk konflikt(er) hittades mellan oberoende domäner."
        )

    top = result.get("top", [])

    if not top:
        lines.append("Ingen kandidat kunde rankas.")
        return "\n".join(lines)

    lines.append("Topp tre:")

    for index, item in enumerate(top, start=1):
        lines.append(
            f"{index}. {item.get('title') or 'Utan titel'}"
        )
        lines.append(
            f"   URL: {item.get('url') or ''}"
        )
        lines.append(
            "   Källans tillförlitlighet: "
            f"{item['source_reliability']['score']:.1f}%"
        )
        lines.append(
            "   Informationens konfidens: "
            f"{item['information_confidence']['score']:.1f}%"
        )
        lines.append(
            f"   Relevans: {item['relevance']:.1f}%"
        )
        lines.append(
            f"   Intern totalscore: {item['combined_score']:.1f}"
        )

        status = item.get(
            "deep_verification_status",
            "disabled",
        )

        if status == "verified":
            verification = item.get(
                "deep_verification",
                {},
            )
            lines.append(
                "   Djupverifiering: ja | "
                f"transparens {verification.get('transparency_score', 0):.1f}% | "
                f"evidenssignaler {verification.get('evidence_signal_score', 0):.1f}%"
            )
        elif status in {"failed", "unavailable"}:
            lines.append(
                "   Djupverifiering: nej | "
                + item.get(
                    "deep_verification_reason",
                    "ingen verifieringsdata",
                )
            )
        else:
            lines.append(
                "   Djupverifiering: avstängd"
            )

        conflict_count = item.get("conflict_count", 0)

        if conflict_count:
            lines.append(
                f"   Konflikter: {conflict_count} tydlig numerisk konflikt(er) med andra domäner"
            )

    return "\n".join(lines)


def research_top_three(query):
    try:
        return format_research_top_three(
            research_top_three_data(query)
        )
    except Exception as error:
        return f"Research misslyckades: {error}"


TOOLS = {
    "research_top_three": {
        "function": research_top_three,
        "description": (
            "Söker upp till fem internetkandidater, gör separata interna "
            "procentbedömningar av källtillförlitlighet och informationskonfidens "
            "och presenterar de tre starkaste återstående resultaten."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }
}
