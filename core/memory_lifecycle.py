import re
from difflib import SequenceMatcher

from core.memory_policy import normalize_memory_text


REPLACEMENT_PHRASES = (
    "från och med nu",
    "hädanefter",
    "ändra standard",
    "ändra till",
    "ersätt",
    "ersätt med",
    "istället för",
    "i stället för",
    "inte längre",
    "ska nu",
    "min nya standard",
    "uppdatera till",
    "from now on",
    "replace with",
    "instead of",
    "no longer",
    "new default",
)

_TOPIC_STOPWORDS = {
    "jag",
    "du",
    "det",
    "den",
    "de",
    "är",
    "och",
    "att",
    "har",
    "kan",
    "vill",
    "med",
    "som",
    "för",
    "på",
    "en",
    "ett",
    "min",
    "mitt",
    "mina",
    "från",
    "och",
    "med",
    "nu",
    "ska",
    "alltid",
    "använd",
    "använda",
    "ändra",
    "ändrat",
    "standard",
    "nya",
    "ny",
    "ersätt",
    "ersätta",
    "istället",
    "stället",
    "inte",
    "längre",
    "kom",
    "ihåg",
    "spara",
    "föredrar",
    "prefer",
    "prefererar",
    "from",
    "now",
    "on",
    "always",
    "use",
    "replace",
    "instead",
    "new",
    "default",
    "en",
    "ett",
    "två",
    "tre",
    "fyra",
    "fem",
    "sex",
    "sju",
    "åtta",
    "nio",
    "tio",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
}


def has_replacement_signal(
    text,
):
    normalized = normalize_memory_text(
        text
    )

    return any(
        phrase in normalized
        for phrase in REPLACEMENT_PHRASES
    )


def _topic_tokens(
    text,
):
    normalized = normalize_memory_text(
        text
    )
    words = re.findall(
        r"[a-zåäö]+",
        normalized,
    )

    return {
        word
        for word in words
        if (
            len(
                word
            )
            >= 2
            and word
            not in _TOPIC_STOPWORDS
        )
    }


def _conflict_score(
    candidate_category,
    candidate_content,
    existing,
):
    candidate_tokens = _topic_tokens(
        candidate_content
    )
    existing_tokens = _topic_tokens(
        existing.get(
            "content",
            "",
        )
    )

    if (
        not candidate_tokens
        or not existing_tokens
    ):
        return 0.0

    shared = (
        candidate_tokens
        & existing_tokens
    )

    if len(
        shared
    ) < 2:
        return 0.0

    overlap = (
        len(
            shared
        )
        / min(
            len(
                candidate_tokens
            ),
            len(
                existing_tokens
            ),
        )
    )
    candidate_key = " ".join(
        sorted(
            candidate_tokens
        )
    )
    existing_key = " ".join(
        sorted(
            existing_tokens
        )
    )
    sequence = SequenceMatcher(
        None,
        candidate_key,
        existing_key,
    ).ratio()
    score = max(
        overlap,
        sequence,
    )

    existing_category = str(
        existing.get(
            "category",
            "",
        )
        or ""
    ).strip().lower()
    candidate_category = str(
        candidate_category
        or ""
    ).strip().lower()

    if (
        candidate_category
        and existing_category
        and candidate_category
        != existing_category
        and "explicit"
        not in {
            candidate_category,
            existing_category,
        }
    ):
        score *= 0.85

    return round(
        min(
            1.0,
            max(
                0.0,
                score,
            ),
        ),
        4,
    )


def find_memory_conflicts(
    candidate_category,
    candidate_content,
    active_records,
    *,
    threshold=0.72,
    limit=5,
):
    minimum = min(
        1.0,
        max(
            0.0,
            float(
                threshold
            ),
        ),
    )
    results = []

    for item in (
        active_records
        or []
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        score = _conflict_score(
            candidate_category,
            candidate_content,
            item,
        )

        if score < minimum:
            continue

        results.append(
            {
                "id": item.get(
                    "id"
                ),
                "category": item.get(
                    "category"
                ),
                "content": item.get(
                    "content"
                ),
                "score": score,
            }
        )

    results.sort(
        key=lambda item: (
            -float(
                item.get(
                    "score",
                    0.0,
                )
            ),
            -int(
                item.get(
                    "id",
                    0,
                )
                or 0
            ),
        )
    )

    return results[
        : max(
            1,
            min(
                int(
                    limit
                ),
                20,
            ),
        )
    ]


def apply_memory_lifecycle(
    memory_store,
    decision,
    *,
    original_text,
    settings=None,
):
    config = (
        settings
        or {}
    ).get(
        "memory",
        {},
    )
    outcome = {
        "saved": False,
        "lifecycle_action": "none",
        "superseded_memory_id": None,
        "new_memory_id": None,
        "requires_review": False,
        "conflicts": [],
    }

    if (
        decision.get(
            "action"
        )
        != "save"
        or decision.get(
            "sensitive"
        )
        or not decision.get(
            "content"
        )
    ):
        return outcome

    save_if_new = getattr(
        memory_store,
        "save_if_new",
        None,
    )

    if not callable(
        save_if_new
    ):
        return outcome

    if not config.get(
        "lifecycle_enabled",
        True,
    ):
        outcome[
            "saved"
        ] = bool(
            save_if_new(
                decision.get(
                    "category",
                    "other",
                ),
                decision[
                    "content"
                ],
            )
        )
        outcome[
            "lifecycle_action"
        ] = (
            "saved"
            if outcome[
                "saved"
            ]
            else "duplicate"
        )
        return outcome

    list_active = getattr(
        memory_store,
        "list_active_records",
        None,
    )
    supersede = getattr(
        memory_store,
        "supersede",
        None,
    )

    if not (
        callable(
            list_active
        )
        and callable(
            supersede
        )
    ):
        outcome[
            "saved"
        ] = bool(
            save_if_new(
                decision.get(
                    "category",
                    "other",
                ),
                decision[
                    "content"
                ],
            )
        )
        outcome[
            "lifecycle_action"
        ] = (
            "saved_legacy_store"
            if outcome[
                "saved"
            ]
            else "duplicate"
        )
        return outcome

    contains = getattr(
        memory_store,
        "contains",
        None,
    )

    if callable(
        contains
    ) and contains(
        decision.get(
            "category",
            "other",
        ),
        decision[
            "content"
        ],
    ):
        outcome[
            "lifecycle_action"
        ] = "duplicate"
        return outcome

    conflict_threshold = float(
        config.get(
            "conflict_similarity_threshold",
            0.72,
        )
    )
    supersede_threshold = float(
        config.get(
            "supersede_similarity_threshold",
            0.85,
        )
    )
    candidates = list_active(
        limit=config.get(
            "max_conflict_scan",
            200,
        )
    )
    conflicts = find_memory_conflicts(
        decision.get(
            "category",
            "other",
        ),
        decision[
            "content"
        ],
        candidates,
        threshold=conflict_threshold,
        limit=5,
    )
    outcome[
        "conflicts"
    ] = conflicts

    replacement = has_replacement_signal(
        original_text
    )
    strong = [
        item
        for item in conflicts
        if float(
            item.get(
                "score",
                0.0,
            )
        )
        >= supersede_threshold
    ]

    if (
        replacement
        and config.get(
            "auto_supersede_explicit_updates",
            True,
        )
        and len(
            strong
        )
        == 1
    ):
        old_id = strong[
            0
        ].get(
            "id"
        )

        if old_id is not None:
            new_id = supersede(
                old_id,
                decision.get(
                    "category",
                    "other",
                ),
                decision[
                    "content"
                ],
            )
            outcome.update(
                {
                    "saved": True,
                    "lifecycle_action": "superseded",
                    "superseded_memory_id": int(
                        old_id
                    ),
                    "new_memory_id": int(
                        new_id
                    ),
                    "requires_review": False,
                }
            )
            return outcome

    if conflicts:
        outcome[
            "requires_review"
        ] = True
        outcome[
            "lifecycle_action"
        ] = (
            "ambiguous_replacement"
            if replacement
            else "possible_conflict"
        )
        return outcome

    outcome[
        "saved"
    ] = bool(
        save_if_new(
            decision.get(
                "category",
                "other",
            ),
            decision[
                "content"
            ],
        )
    )
    outcome[
        "lifecycle_action"
    ] = (
        "saved"
        if outcome[
            "saved"
        ]
        else "duplicate"
    )
    return outcome
