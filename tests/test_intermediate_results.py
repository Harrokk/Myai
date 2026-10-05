from core.intermediate_results import (
    IntermediateResultStore,
    dependent_visual_research,
)


def test_visual_research_dependency_detection():
    assert dependent_visual_research(
        "Researcha det du ser."
    ) is True
    assert dependent_visual_research(
        "Sök upp objekten på webben."
    ) is True
    assert dependent_visual_research(
        "Researcha Raspberry Pi 5."
    ) is False


def test_intermediate_store_creates_bounded_one_shot_research_candidate():
    store = IntermediateResultStore(
        max_pending=5,
        max_query_chars=80,
        max_age_seconds=1800,
        clock=lambda: 10.0,
    )

    item = store.create(
        source_tool="vision_analyze",
        source_result=(
            "Bildanalys av capture.jpg:\n"
            + (
                "En röd industrikontakt med fyra stift. "
                * 20
            )
        ),
        target_tool="research_top_three",
    )

    assert item is not None
    assert item[
        "id"
    ] == "IR1"
    assert len(
        item[
            "query"
        ]
    ) <= 80
    assert "Bildanalys av" not in item[
        "query"
    ]

    public = store.public_item(
        item
    )
    assert public[
        "confirmation_command"
    ] == "FORTSÄTT MED RESEARCH IR1"
    assert public[
        "requires_confirmation"
    ] is True

    consumed = store.consume(
        "IR1"
    )
    assert consumed[
        "id"
    ] == "IR1"
    assert store.get(
        "IR1"
    ) is None


def test_intermediate_store_rejects_failed_or_empty_vision_results():
    store = IntermediateResultStore(
        clock=lambda: 10.0,
    )

    assert store.create(
        source_tool="vision_analyze",
        source_result=(
            "Visionanalysen misslyckades: modell saknas"
        ),
    ) is None
    assert store.create(
        source_tool="vision_read_text",
        source_result="INGEN LÄSBAR TEXT",
    ) is None
    assert store.create(
        source_tool="cpu_status",
        source_result="CPU 10%",
    ) is None


def test_intermediate_store_expires_old_candidates():
    now = [
        0.0
    ]
    store = IntermediateResultStore(
        max_age_seconds=60,
        clock=lambda: now[
            0
        ],
    )
    item = store.create(
        source_tool="vision_detect_objects",
        source_result=(
            "Objektidentifiering av capture.jpg:\n"
            "kontakt, kabel"
        ),
    )
    assert store.get(
        item[
            "id"
        ]
    ) is not None

    now[
        0
    ] = 61.0

    assert store.get(
        item[
            "id"
        ]
    ) is None


def test_confirmation_parser_requires_exact_uppercase_command():
    store = IntermediateResultStore()

    assert store.parse_confirmation(
        "FORTSÄTT MED RESEARCH IR12"
    ) == "IR12"
    assert store.parse_confirmation(
        "fortsätt med research IR12"
    ) is None
    assert store.parse_confirmation(
        "FORTSÄTT MED RESEARCH IR12 tack"
    ) is None


def test_pending_limit_keeps_newest_candidates():
    clock = [
        0.0
    ]
    store = IntermediateResultStore(
        max_pending=2,
        clock=lambda: clock[
            0
        ],
    )

    ids = []

    for index in range(
        3
    ):
        clock[
            0
        ] = float(
            index
        )
        item = store.create(
            source_tool="vision_analyze",
            source_result=(
                f"Bildanalys av x.jpg:\nobjekt {index}"
            ),
        )
        ids.append(
            item[
                "id"
            ]
        )

    assert store.get(
        ids[
            0
        ]
    ) is None
    assert store.get(
        ids[
            1
        ]
    ) is not None
    assert store.get(
        ids[
            2
        ]
    ) is not None
