"""Source-only synthetic tiered receipt-to-dispatch contract tests."""
import hashlib
import pytest

from core.voice_model_provenance import verify_stt_model_files

from core.voice_plan_attestation import allow_voice_dispatch, same_voice_plan
from core.voice_tier_authorization import TieredVoicePermit
from core.voice_tier_identity import TrustedSTTBindings


class STT:
    def __init__(self, model_name):
        self.model_name = model_name

    def transcribe(self, audio):
        return "unused"


class Clock:
    def __init__(self):
        self.now = 1.0

    def __call__(self):
        return self.now


def evidence(tmp_path):
    providers = []
    records = []
    for key, family in (("p", "parakeet"), ("c", "canary"),
                        ("w", "whisper")):
        root = tmp_path / family
        root.mkdir()
        data = ("synthetic " + family).encode()
        path = root / "weights.bin"
        path.write_bytes(data)
        path.chmod(0o444)
        root.chmod(0o555)
        bundle = verify_stt_model_files(
            root, family=family,
            expected_sha256={"weights.bin": hashlib.sha256(data).hexdigest()},
        )
        provider = STT(bundle.root)
        providers.append(provider)
        records.append({"key": key, "provider": provider, "bundle": bundle})
    return TrustedSTTBindings(records), providers


def tools(effect="read_only", *, risk_tier=None, names=("ram_status",)):
    values = {}
    for name in names:
        safety = {"effect": effect, "voice_confirmation_required": False}
        if risk_tier is not None:
            safety["voice_risk_tier"] = risk_tier
        values[name] = {
            "function": lambda: None,
            "pass_user_input": False,
            "safety": safety,
        }
    return values


def build(
    tmp_path, text="Visa RAM", tier="low", *,
    registry=None, names=("ram_status",),
):
    clock = Clock()
    cancelled = {"value": False}
    secret = b"x" * 32
    registry = registry if registry is not None else tools(names=names)
    plan = {"steps": [{"tool": name, "input": None} for name in names]}
    bindings, providers = evidence(tmp_path)
    count = {"low": 1, "medium": 2, "critical": 3}[tier]
    observations = [(p, text) for p in providers[:count]]
    permit = TieredVoicePermit(
        transcript=text,
        plan=plan,
        tools=registry,
        model_bindings=bindings,
        observations=observations,
        secret=secret,
        stop_requested=lambda: cancelled["value"],
        clock=clock,
    )
    def verifier(p, t):
        return same_voice_plan(p, t, secret, permit.plan_digest)
    verifier.voice_stop_requested = lambda: cancelled["value"]
    verifier.voice_tiered_enabled = True
    verifier.voice_tier_authorize = permit.authorize
    return permit, plan, registry, verifier, clock, cancelled


def invoke(plan, registry, verifier, name="ram_status"):
    return allow_voice_dispatch(
        plan, registry, name, registry[name], None, verifier,
    )


def test_low_trusted_one_stt_authorizes_safe_read(tmp_path):
    permit, plan, registry, verifier, _, _ = build(tmp_path,)
    assert permit.tier == "low"
    assert invoke(plan, registry, verifier) is True


def test_low_one_time_receipt_rejects_second_dispatch(tmp_path):
    _, plan, registry, verifier, _, _ = build(tmp_path,)
    assert invoke(plan, registry, verifier) is True
    assert invoke(plan, registry, verifier) is False


def test_medium_two_distinct_families_can_authorize_reversible(tmp_path):
    registry = tools("reversible", risk_tier="medium", names=("set_volume",))
    permit, plan, registry, verifier, _, _ = build(tmp_path,
        "Ändra ljudvolym", "medium", registry=registry, names=("set_volume",),
    )
    assert permit.tier == "medium"
    assert invoke(plan, registry, verifier, "set_volume") is True


def test_medium_replay_is_blocked(tmp_path):
    registry = tools("reversible", risk_tier="medium", names=("set_volume",))
    _, plan, registry, verifier, _, _ = build(tmp_path,
        "Ändra ljudvolym", "medium", registry=registry, names=("set_volume",),
    )
    assert invoke(plan, registry, verifier, "set_volume")
    assert invoke(plan, registry, verifier, "set_volume") is False


def test_critical_must_fail_until_separate_approval_is_implemented(tmp_path):
    registry = tools("destructive", risk_tier="critical", names=("remove_file",))
    permit, plan, registry, verifier, _, _ = build(tmp_path,
        "Radera filen", "critical", registry=registry, names=("remove_file",),
    )
    assert permit.tier == "critical"
    assert invoke(plan, registry, verifier, "remove_file") is False


def test_tampered_critical_plan_cannot_use_old_low_receipt(tmp_path):
    _, plan, registry, verifier, _, _ = build(tmp_path,)
    registry["ram_status"]["safety"]["effect"] = "destructive"
    assert invoke(plan, registry, verifier) is False


def test_late_dispatch_is_rejected(tmp_path):
    _, plan, registry, verifier, clock, _ = build(tmp_path,)
    clock.now += 16
    assert invoke(plan, registry, verifier) is False


def test_clock_rollback_is_rejected(tmp_path):
    _, plan, registry, verifier, clock, _ = build(tmp_path,)
    clock.now = -1
    assert invoke(plan, registry, verifier) is False


def test_stop_revokes_unused_receipt(tmp_path):
    _, plan, registry, verifier, _, cancelled = build(tmp_path,)
    cancelled["value"] = True
    assert invoke(plan, registry, verifier) is False


def test_plan_argument_change_denied(tmp_path):
    _, plan, registry, verifier, _, _ = build(tmp_path,)
    plan["steps"][0]["input"] = "tampered"
    assert invoke(plan, registry, verifier) is False


def test_tool_callback_swap_denied(tmp_path):
    _, plan, registry, verifier, _, _ = build(tmp_path,)
    registry["ram_status"]["function"] = lambda: "different"
    assert invoke(plan, registry, verifier) is False


def test_unknown_tool_added_after_receipt_denied(tmp_path):
    _, plan, registry, verifier, _, _ = build(tmp_path,)
    registry["evil"] = {
        "function": lambda: None,
        "pass_user_input": False,
        "safety": {"effect": "destructive", "voice_confirmation_required": False},
    }
    plan["steps"].append({"tool": "evil", "input": None})
    assert invoke(plan, registry, verifier) is False


def test_wrong_tool_or_missing_registry_cannot_execute(tmp_path):
    _, plan, registry, verifier, _, _ = build(tmp_path,)
    assert allow_voice_dispatch(
        plan, registry, "cpu_status", registry["ram_status"], None, verifier,
    ) is False


def test_mismatched_primary_transcript_does_not_issue_receipt(tmp_path):
    bind, providers = evidence(tmp_path)
    with pytest.raises(ValueError, match="unverified-voice-request"):
        TieredVoicePermit(
            transcript="Anslut till headset B",
            plan={"steps": []},
            tools={},
            model_bindings=bind,
            observations=[
                (providers[0], "Anslut till headset A"),
                (providers[1], "Anslut till headset A"),
            ],
            secret=b"x" * 32,
            stop_requested=lambda: False,
        )


def test_duplicate_family_or_provider_never_creates_receipt(tmp_path):
    bind, providers = evidence(tmp_path)
    with pytest.raises(ValueError, match="unverified-voice-request"):
        TieredVoicePermit(
            transcript="Anslut till headset",
            plan={"steps": []},
            tools={},
            model_bindings=bind,
            observations=[
                (providers[0], "Anslut till headset"),
                (providers[0], "Anslut till headset"),
            ],
            secret=b"x" * 32,
            stop_requested=lambda: False,
        )


def test_unknown_plan_metadata_blocks_receipt_issue(tmp_path):
    bind, providers = evidence(tmp_path)
    with pytest.raises(ValueError, match="blocked-voice-request"):
        TieredVoicePermit(
            transcript="Status",
            plan={"steps": [{"tool": "mystery"}]},
            tools={"mystery": {
                "function": lambda: None,
                "safety": {"effect": "read_only"},
            }},
            model_bindings=bind,
            observations=[(providers[0], "Status")],
            secret=b"x" * 32,
            stop_requested=lambda: False,
        )
