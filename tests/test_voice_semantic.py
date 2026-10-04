import json

from core.voice_semantic import SemanticConsensusResolver


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat(self, messages, timeout=60):
        self.calls.append(
            (messages, timeout)
        )
        return self.response


def test_semantic_resolver_accepts_majority_intent():
    llm = FakeLLM(
        json.dumps(
            {
                "same_intent": True,
                "selected_index": 1,
                "supporting_indices": [0, 1],
                "confidence": 0.92,
                "reason": "Två uttrycker samma fråga.",
            }
        )
    )
    resolver = SemanticConsensusResolver(
        llm,
        min_confidence=0.85,
    )

    result = resolver.resolve(
        [
            "Hur mycket minne går åt?",
            "Hur mycket RAM används?",
            "Stäng av datorn",
        ]
    )

    assert result["accepted"] is True
    assert result["text"] == "Hur mycket RAM används?"
    assert result["support"] == 2


def test_semantic_resolver_rejects_low_confidence():
    resolver = SemanticConsensusResolver(
        FakeLLM(
            json.dumps(
                {
                    "same_intent": True,
                    "selected_index": 0,
                    "supporting_indices": [0, 1],
                    "confidence": 0.6,
                    "reason": "Osäkert.",
                }
            )
        ),
        min_confidence=0.85,
    )

    result = resolver.resolve(
        ["A", "A ungefär", "B"]
    )

    assert result["accepted"] is False


def test_semantic_resolver_rejects_invalid_selected_index():
    resolver = SemanticConsensusResolver(
        FakeLLM(
            json.dumps(
                {
                    "same_intent": True,
                    "selected_index": 9,
                    "supporting_indices": [0, 1],
                    "confidence": 0.99,
                    "reason": "bad",
                }
            )
        )
    )

    result = resolver.resolve(
        ["A", "A", "B"]
    )

    assert result["accepted"] is False


def test_semantic_resolver_requires_majority_support():
    resolver = SemanticConsensusResolver(
        FakeLLM(
            json.dumps(
                {
                    "same_intent": True,
                    "selected_index": 0,
                    "supporting_indices": [0],
                    "confidence": 0.99,
                    "reason": "bara en",
                }
            )
        )
    )

    result = resolver.resolve(
        ["A", "B", "C"]
    )

    assert result["accepted"] is False
