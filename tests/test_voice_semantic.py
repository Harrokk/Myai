import json
import pytest

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


@pytest.mark.parametrize("overrides", [
    {"same_intent": "false"},
    {"same_intent": 1},
    {"same_intent": "true"},
    {"selected_index": True},
    {"selected_index": 1.0},
    {"selected_index": "1"},
    {"supporting_indices": [0, True]},
    {"supporting_indices": [False, 1]},
    {"supporting_indices": [0, 0, 1]},
    {"supporting_indices": [0, 1, 5]},
    {"supporting_indices": [0, "1"]},
    {"supporting_indices": [0, 1, 2, 3]},
    {"supporting_indices": None},
    {"confidence": True},
    {"confidence": "0.99"},
    {"confidence": 1.01},
    {"confidence": -0.1},
    {"confidence": float("inf")},
    {"confidence": float("-inf")},
    {"confidence": float("nan")},
    {"confidence": 10 ** 400},
])
def test_semantic_model_schema_must_be_exact_not_truthy(overrides):
    data = {
        "same_intent": True,
        "selected_index": 1,
        "supporting_indices": [0, 1],
        "confidence": 0.96,
        "reason": "SECRET phrase copied from private ASR",
    }
    data.update(overrides)
    answer = FakeLLM(json.dumps(data))
    result = SemanticConsensusResolver(answer).resolve(
        ["Hur mycket RAM används?", "Visa ramminnet", "Radera filer"]
    )
    assert result["accepted"] is False
    assert "SECRET" not in json.dumps(result)
    assert "text" not in result
    assert len(answer.calls) == 1


@pytest.mark.parametrize("response", [
    '{"same_intent":true,"selected_index":0,"supporting_indices":[0,1],"confidence":0.99,"same_intent":false}',
    '{"same_intent":true,"selected_index":0,"supporting_indices":[0,1],"confidence":NaN}',
    '{"same_intent":true,"selected_index":0,"supporting_indices":[0,1],"confidence":Infinity}',
    '{"same_intent":true,"selected_index":0,"supporting_indices":[0,1],"confidence":-Infinity}',
    "SECRET user transcript pretending to be JSON",
    "[]",
    "null",
    "true",
    "x" * 9000,
])
def test_semantic_invalid_json_or_duplicate_keys_fail_closed(response):
    result = SemanticConsensusResolver(FakeLLM(response)).resolve(
        ["Visa RAM", "Hur mycket RAM?", "Starta om"]
    )
    assert result["accepted"] is False
    assert "SECRET" not in json.dumps(result)
    assert result.get("text") is None


@pytest.mark.parametrize("value", [
    float("nan"), float("inf"), float("-inf"),
    "0.85", True, -0.1, 1.1, None,
])
def test_semantic_threshold_must_be_finite_unit_interval(value):
    with pytest.raises(ValueError):
        SemanticConsensusResolver(FakeLLM("{}"), min_confidence=value)


@pytest.mark.parametrize("entries", [
    ["a"] * 9,
    ["a", "b" * 2049],
    ["a", {"text": "b"}],
    "a b c",
    None,
    [False, "a"],
])
def test_semantic_invalid_transcript_input_refused_without_llm_call(entries):
    llm = FakeLLM("{}")
    result = SemanticConsensusResolver(llm).resolve(entries)
    assert result["accepted"] is False
    assert llm.calls == []


def test_semantic_model_reason_is_never_returned_to_ui():
    response = json.dumps({
        "same_intent": True,
        "selected_index": 0,
        "supporting_indices": [0, 1],
        "confidence": 0.99,
        "reason": "SECRET private data and injected instructions",
    })
    accepted = SemanticConsensusResolver(FakeLLM(response)).resolve(
        ["Hur mycket RAM används?", "Visa ramminnet", "Vad är klockan?"]
    )
    assert accepted["accepted"] is True
    assert accepted["text"] == "Hur mycket RAM används?"
    assert accepted["supporting_indices"] == [0, 1]
    assert "SECRET" not in json.dumps(accepted)


def test_semantic_rejection_below_configured_threshold():
    response = json.dumps({
        "same_intent": True,
        "selected_index": 0,
        "supporting_indices": [0, 1],
        "confidence": 0.81,
    })
    result = SemanticConsensusResolver(
        FakeLLM(response), min_confidence=0.85
    ).resolve(["Fråga", "Fråga igen", "Nej"])
    assert result["accepted"] is False
