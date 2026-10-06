import re
import time


_ALLOWED_SOURCE_TOOLS = {
    "vision_analyze",
    "vision_detect_objects",
    "vision_read_text",
    "vision_detect_change",
}

_ALLOWED_TARGET_TOOLS = {
    "research_top_three",
}

_ERROR_MARKERS = (
    "misslyckades:",
    "är avstängd.",
    "ingen visionmodell",
    "ingen sparad kamerabild",
    "minst två sparade kamerabilder krävs",
    "inga säkra objekt",
    "ingen läsbar text",
)

_CONFIRM_PATTERN = re.compile(
    r"FORTSÄTT MED RESEARCH (IR\d+)"
)


def _compact_text(
    value,
    max_chars,
):
    text = " ".join(
        str(
            value
            or ""
        ).split()
    )

    if len(
        text
    ) <= max_chars:
        return text

    return (
        text[
            : max(
                0,
                max_chars
                - 3,
            )
        ]
        + "..."
    )


def _source_payload(
    source_tool,
    result,
    max_chars,
):
    if source_tool not in _ALLOWED_SOURCE_TOOLS:
        return None

    text = str(
        result
        or ""
    ).strip()

    if not text:
        return None

    lowered = text.lower()

    if any(
        marker in lowered
        for marker in _ERROR_MARKERS
    ):
        return None

    if "\n" in text:
        first, rest = text.split(
            "\n",
            1,
        )

        if (
            ":" in first
            and any(
                prefix in first.lower()
                for prefix in (
                    "bildanalys",
                    "objektidentifiering",
                    "textläsning",
                    "förändringsanalys",
                )
            )
        ):
            text = rest

    text = _compact_text(
        text,
        max_chars,
    )

    if not text:
        return None

    return text


class IntermediateResultStore:
    def __init__(
        self,
        *,
        max_pending=5,
        max_query_chars=240,
        max_age_seconds=1800,
        clock=None,
    ):
        self.max_pending = max(
            1,
            min(
                int(
                    max_pending
                ),
                20,
            ),
        )
        self.max_query_chars = max(
            80,
            min(
                int(
                    max_query_chars
                ),
                1000,
            ),
        )
        self.max_age_seconds = max(
            60,
            min(
                int(
                    max_age_seconds
                ),
                86400,
            ),
        )
        self.clock = (
            clock
            or time.monotonic
        )
        self._counter = 0
        self._pending = {}

    def clear(
        self,
    ):
        self._pending.clear()

    def _prune(
        self,
    ):
        now = float(
            self.clock()
        )
        expired = [
            identifier
            for identifier, item
            in self._pending.items()
            if (
                now
                - float(
                    item.get(
                        "created_monotonic",
                        now,
                    )
                )
            )
            > self.max_age_seconds
        ]

        for identifier in expired:
            self._pending.pop(
                identifier,
                None,
            )

        if len(
            self._pending
        ) <= self.max_pending:
            return

        ordered = sorted(
            self._pending.values(),
            key=lambda item: float(
                item.get(
                    "created_monotonic",
                    0.0,
                )
            ),
        )

        for item in ordered[
            : len(
                self._pending
            )
            - self.max_pending
        ]:
            self._pending.pop(
                item[
                    "id"
                ],
                None,
            )

    def create(
        self,
        *,
        source_tool,
        source_result,
        target_tool="research_top_three",
    ):
        self._prune()

        if target_tool not in _ALLOWED_TARGET_TOOLS:
            return None

        payload = _source_payload(
            source_tool,
            source_result,
            self.max_query_chars,
        )

        if payload is None:
            return None

        query = _compact_text(
            payload,
            self.max_query_chars,
        )

        if not query:
            return None

        self._counter += 1
        identifier = (
            f"IR{self._counter}"
        )
        item = {
            "id": identifier,
            "source_tool": source_tool,
            "target_tool": target_tool,
            "query": query,
            "created_monotonic": float(
                self.clock()
            ),
        }
        self._pending[
            identifier
        ] = item
        self._prune()
        return dict(
            item
        )

    def parse_confirmation(
        self,
        user_input,
    ):
        match = _CONFIRM_PATTERN.fullmatch(
            str(
                user_input
                or ""
            ).strip()
        )

        if not match:
            return None

        return match.group(
            1
        )

    def get(
        self,
        identifier,
    ):
        self._prune()
        item = self._pending.get(
            str(
                identifier
                or ""
            )
        )

        if item is None:
            return None

        return dict(
            item
        )

    def consume(
        self,
        identifier,
    ):
        self._prune()
        item = self._pending.pop(
            str(
                identifier
                or ""
            ),
            None,
        )

        if item is None:
            return None

        return dict(
            item
        )

    def public_item(
        self,
        item,
    ):
        if not item:
            return None

        return {
            "id": item.get(
                "id"
            ),
            "source_tool": item.get(
                "source_tool"
            ),
            "next_tool": item.get(
                "target_tool"
            ),
            "query_preview": _compact_text(
                item.get(
                    "query",
                    "",
                ),
                min(
                    self.max_query_chars,
                    160,
                ),
            ),
            "requires_confirmation": True,
            "confirmation_command": (
                "FORTSÄTT MED RESEARCH "
                + str(
                    item.get(
                        "id",
                        "",
                    )
                )
            ),
        }


def dependent_visual_research(
    text,
):
    value = str(
        text
        or ""
    ).lower()

    research = any(
        phrase in value
        for phrase in (
            "researcha",
            "gör research",
            "sök upp",
            "sök på webben",
            "sök på internet",
            "ta reda på mer",
            "undersök vidare",
            "research ",
            "search the web",
            "look up",
            "find out more",
        )
    )
    visual_reference = any(
        phrase in value
        for phrase in (
            "det du ser",
            "det som syns",
            "det i bilden",
            "bilden visar",
            "objekten",
            "objektet",
            "texten i bilden",
            "texten du läser",
            "what you see",
            "what is in the image",
            "the object",
            "the objects",
            "the text in the image",
        )
    )

    return bool(
        research
        and visual_reference
    )
