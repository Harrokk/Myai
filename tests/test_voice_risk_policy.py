"""Synthetic security contracts for the opt-in three-tier voice risk catalogue.

No microphone, file mutation, network connection or tool invocation.
"""
import pytest

from core.voice_risk_policy import classify_voice_tier, tier_at_least


def tool(effect="read_only", tier=None, confirmation=False):
    safety = {
        "effect": effect,
        "voice_confirmation_required": confirmation,
    }
    if tier is not None:
        safety["voice_risk_tier"] = tier
    return {"function": lambda: None, "safety": safety}


def decision(transcript, steps=(), registry=None):
    return classify_voice_tier(
        transcript,
        {"steps": [{"tool": name} for name in steps]},
        {} if registry is None else registry,
    )


def test_ordinary_chat_needs_one_voice():
    d = decision("Vad är klockan?")
    assert d["tier"] == "low"
    assert d["required_votes"] == 1
    assert d["requires_confirmation"] is False


def test_real_allowlisted_read_only_tool_can_remain_low():
    d = decision(
        "Visa RAM-status", ["ram_status"],
        {"ram_status": tool()},
    )
    assert d["tier"] == "low"
    assert d["required_votes"] == 1


@pytest.mark.parametrize("spoken", [
    "radera filen", "installera paket", "styr GPIO17",
    "ändra kod", "stäng av datorn", "skicka en commit",
    "fabriksåterställ systemet",
])
def test_critical_phrases_never_become_low(spoken):
    d = decision(spoken)
    assert d["tier"] == "critical"
    assert d["required_votes"] == 3
    assert d["requires_confirmation"] is True


@pytest.mark.parametrize("spoken", [
    "anslut till hörlurarna",
    "koppla från bluetooth",
    "ta en bild",
])
def test_medium_phrases_are_not_low(spoken):
    d = decision(spoken)
    assert d["tier"] == "medium"
    assert d["required_votes"] == 2


def test_explicit_reversible_operation_is_medium():
    d = decision(
        "Ändra ljudvolym", ["set_volume"],
        {"set_volume": tool("reversible", tier="medium")},
    )
    assert d["tier"] == "medium"


def test_generic_write_cannot_be_downgraded_by_metadata():
    d = decision(
        "Skriv om filen", ["workspace_write"],
        {"workspace_write": tool("write", tier="medium")},
    )
    assert d["tier"] == "critical"
    assert d["requires_confirmation"] is True


def test_unknown_tool_is_blocked_even_if_it_claims_read_only():
    d = decision("Status", ["unreviewed_tool"],
                 {"unreviewed_tool": tool("read_only")})
    assert d["tier"] == "blocked"
    assert d["required_votes"] is None


def test_missing_metadata_is_blocked():
    assert decision("Status", ["ram_status"], {"ram_status": {}})["tier"] == "blocked"


def test_confirmation_on_read_only_escalates():
    d = decision("Visa CPU", ["cpu_status"],
                 {"cpu_status": tool(confirmation=True)})
    assert d["tier"] == "critical"


def test_effect_is_unknown_and_must_block():
    assert decision("Starta aktivitet", ["foo"],
                    {"foo": tool("unknown")})["tier"] == "blocked"


@pytest.mark.parametrize("steps", [
    None,
    {},
    {"steps": "ram_status"},
    {"steps": [None]},
    {"steps": [{"tool": "ram_status"}] * 2},
    {"steps": [{"tool": "ram_status"}] * 17},
])
def test_invalid_plans_are_blocked(steps):
    result = classify_voice_tier(
        "Visa RAM", steps, {"ram_status": tool()},
    )
    assert result["tier"] == "blocked"


def test_unknown_and_invalid_safety_tier_blocked():
    d = decision(
        "Koppla till enhet", ["connect"],
        {"connect": tool("connect", tier="low")},
    )
    assert d["tier"] == "critical"


def test_missing_or_empty_input_blocks():
    d = decision("")
    assert d["tier"] == "blocked"


def test_risk_comparison_cannot_lower_or_accept_invalid_tier():
    assert tier_at_least("critical", "medium") is True
    assert tier_at_least("medium", "critical") is False
    assert tier_at_least("blocked", "low") is False
    assert tier_at_least("garbage", "low") is False
