"""End-to-end synthetic VoicePipeline tiered routing; never opens audio or tools."""
from core.voice_pipeline import VoicePipeline
from core.voice_plan_attestation import allow_voice_dispatch
from core.voice_tier_identity import TrustedSTTBindings


class STT:
    def __init__(self, text, on_transcribe=None):
        self.text = text
        self.calls = 0
        self.on_transcribe = on_transcribe

    def transcribe(self, audio):
        self.calls += 1
        if self.on_transcribe is not None:
            self.on_transcribe()
        return {"text": self.text, "confidence": None}


class FakeCore:
    def __init__(self, name="ram_status", effect="read_only", tier=None):
        self.calls = []
        self.name = name
        self.drift = False
        safety = {
            "effect": effect, "voice_confirmation_required": False,
        }
        if tier is not None:
            safety["voice_risk_tier"] = tier
        self.tools = {
            name: {
                "function": lambda: None,
                "pass_user_input": False,
                "safety": safety,
            },
        }

    def preview_tool_plan(self, text):
        self.calls.append("preview")
        if self.drift and len(self.calls) > 1:
            self.tools[self.name]["safety"]["effect"] = "destructive"
        return {"steps": [{"tool": self.name, "input": None}]}

    def respond_voice(self, text, *, plan_verifier):
        self.calls.append("respond_voice")
        plan = self.preview_tool_plan(text)
        allowed = allow_voice_dispatch(
            plan, self.tools, self.name, self.tools[self.name],
            None, plan_verifier,
        )
        self.calls.append("allowed" if allowed else "blocked")
        return {
            "answer": "synthetic" if allowed else "blocked",
            "tool_dispatch_blocked": not allowed,
            "tool_execution_status": "completed" if allowed else "not_started",
            "tools": [self.name],
        }


def make_pipeline(
    utterance="Visa RAM", *,
    effect="read_only", tier=None, backups=(),
    primary=None, assistant=None, binder=True,
):
    first = primary if primary is not None else STT(utterance)
    reserve = [STT(v) for v in backups]
    core = assistant if assistant is not None else FakeCore(
        effect=effect, tier=tier,
        name="set_volume" if effect == "reversible" else (
            "remove_file" if effect == "destructive" else "ram_status"
        ),
    )
    entries = [("p", first, "parakeet", "a")]
    if len(reserve) >= 1:
        entries.append(("c", reserve[0], "canary", "b"))
    if len(reserve) >= 2:
        entries.append(("w", reserve[1], "whisper", "c"))
    if binder:
        bindings = TrustedSTTBindings([
            {"key": key, "provider": model, "family": family,
             "sha256": ch * 64}
            for key, model, family, ch in entries
        ])
    else:
        bindings = None
    pipe = VoicePipeline(
        core, first,
        backup_stt=reserve,
        trusted_stt_bindings=bindings,
        settings={"voice": {
            "risk_tiered_verification_enabled": True,
            "tts_enabled": False,
            "stt_observed_budget_seconds": 45,
        }},
    )
    return pipe, core, first, reserve


def test_simple_read_uses_only_primary_and_authorizes_allowlist():
    pipe, core, first, reserve = make_pipeline()
    result = pipe.process_utterance(b"synthetic")
    assert result["status"] == "completed"
    assert result["verification"]["tier"] == "low"
    assert first.calls == 1
    assert "allowed" in core.calls


def test_medium_reversible_change_uses_two_independent_models():
    pipe, core, first, reserve = make_pipeline(
        "Ändra ljudvolym", effect="reversible", tier="medium",
        backups=("Ändra ljudvolym",),
    )
    result = pipe.process_utterance(b"synthetic")
    assert result["status"] == "completed"
    assert result["verification"]["tier"] == "medium"
    assert reserve[0].calls == 1
    assert "allowed" in core.calls


def test_medium_disagreement_blocks_without_calling_assistant():
    pipe, core, _, reserve = make_pipeline(
        "Ändra ljudvolym", effect="reversible", tier="medium",
        backups=("Sänk mikrofonvolym",),
    )
    result = pipe.process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert result["verification_reason"] in {
        "risk_disagreement", "independent_votes_disagree",
    }
    assert "respond_voice" not in core.calls


def test_missing_medium_backup_cannot_downgrade_to_low():
    pipe, core, _, _ = make_pipeline(
        "Ändra ljudvolym", effect="reversible", tier="medium",
    )
    result = pipe.process_utterance(b"synthetic")
    assert result["verification_reason"] == "missing_independent_stt"
    assert "respond_voice" not in core.calls


def test_critical_unanimity_without_separate_approval_still_blocks():
    pipe, core, first, reserve = make_pipeline(
        "Radera filen", effect="destructive",
        backups=("Radera filen", "Radera filen"),
    )
    result = pipe.process_utterance(b"synthetic")
    assert result["verification_reason"] == "critical_external_approval_unavailable"
    assert first.calls == 1
    assert all(s.calls == 1 for s in reserve)
    assert "respond_voice" not in core.calls


def test_harmless_first_transcript_cannot_authorize_dangerous_plan():
    pipe, core, first, reserve = make_pipeline(
        "Vad är klockan", effect="destructive",
    )
    result = pipe.process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert "respond_voice" not in core.calls


def test_planned_tool_drift_is_blocked_at_dispatch_boundary():
    core = FakeCore()
    core.drift = True
    pipe, core, _, _ = make_pipeline(assistant=core)
    result = pipe.process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert core.calls[-1] == "blocked"


def test_missing_trusted_binding_does_not_touch_microphone_or_stt():
    pipe, core, first, _ = make_pipeline(binder=False)
    result = pipe.process_utterance(b"synthetic")
    assert result["verification_reason"] == "model_provenance_unavailable"
    assert first.calls == 0
    assert core.calls == []


def test_stop_during_primary_stt_revokes_followup():
    first = STT("Visa RAM")
    pipe, core, _, _ = make_pipeline(primary=first)
    first.on_transcribe = pipe.cancel_pending
    result = pipe.process_utterance(b"synthetic")
    assert result["verification_reason"] == "stt_cancelled_or_stale"
    assert "respond_voice" not in core.calls


def test_bad_toggle_never_uses_legacy_path():
    pipe, core, first, _ = make_pipeline()
    pipe.settings["voice"]["risk_tiered_verification_enabled"] = "yes"
    result = pipe.process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert first.calls == 0


def test_no_preview_or_tool_registry_cannot_authorize_tiered_action():
    pipe, core, first, _ = make_pipeline()
    core.preview_tool_plan = None
    result = pipe.process_utterance(b"synthetic")
    assert result["verification_reason"] == "guarded_planner_required"
    assert first.calls == 0
