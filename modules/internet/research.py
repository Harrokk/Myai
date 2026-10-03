from core.config import load_settings
from core.source_evaluation import evaluate_candidates
from modules.internet.search import search_web


def research_top_three_data(
    query,
    settings=None,
    search_function=None,
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
    active_search = search_function or search_web

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

    return {
        "available": True,
        "query": query,
        "candidate_count": len(candidates),
        "candidates": evaluated,
        "top": evaluated[:top_results],
        "assessment_note": (
            "Procentsiffrorna är interna heuristiska bedömningar baserade "
            "på sökmetadata och utdrag, inte matematiska sannolikheter."
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
