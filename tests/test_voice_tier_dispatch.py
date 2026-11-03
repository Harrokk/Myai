"""Fail-closed tier dispatch gate tests, without executing any real tools."""
from core.voice_plan_attestation import allow_voice_dispatch


def _case(effect="read_only", name="ram_status"):
    registry = {
        name: {
            "function": lambda: None,
            "safety": {
                "effect": effect,
                "voice_confirmation_required": False,
            },
            "pass_user_input": False,
        }
    }
    plan = {"steps": [{"tool": name, "input": None}]}
    return plan, registry, registry[name]


def _verifier(*, tiered=False, authorized=None, stopped=False):
    def verify(_plan, _tools):
        return True
    verify.voice_stop_requested = lambda: stopped
    verify.voice_tiered_enabled = tiered
    if authorized is not None:
        verify.voice_tier_authorize = authorized
    return verify


def _allows(plan, registry, tool, verifier, name="ram_status"):
    return allow_voice_dispatch(
        plan, registry, name, tool, None, verifier,
    )


def test_old_read_only_contract_stays_unchanged_with_tier_disabled():
    plan, registry, tool = _case()
    assert _allows(plan, registry, tool, _verifier()) is True


def test_new_tier_mode_does_not_allow_missing_authorizer():
    plan, registry, tool = _case()
    assert _allows(plan, registry, tool, _verifier(tiered=True)) is False


def test_new_tier_mode_rejects_negative_receipt():
    plan, registry, tool = _case()
    verifier = _verifier(
        tiered=True,
        authorized=lambda *_: False,
    )
    assert _allows(plan, registry, tool, verifier) is False


def test_new_tier_mode_calls_receipt_at_dispatch_boundary():
    plan, registry, tool = _case()
    called = []
    def authorize(p, t, name, actual_input):
        called.append((p is plan, t is registry, name, actual_input))
        return True
    verifier = _verifier(tiered=True, authorized=authorize)
    assert _allows(plan, registry, tool, verifier) is True
    assert called == [(True, True, "ram_status", None)]


def test_new_tier_mode_blocks_authorizer_exception():
    plan, registry, tool = _case()
    def broken(*_):
        raise RuntimeError("private secret never echoed")
    assert _allows(plan, registry, tool, _verifier(
        tiered=True, authorized=broken,
    )) is False


def test_stop_revokes_even_an_authorized_read_only_action():
    plan, registry, tool = _case()
    assert _allows(plan, registry, tool, _verifier(
        tiered=True, authorized=lambda *_: True, stopped=True,
    )) is False


def test_invalid_tiered_toggle_fails_closed():
    plan, registry, tool = _case()
    verifier = _verifier()
    verifier.voice_tiered_enabled = "yes"
    assert _allows(plan, registry, tool, verifier) is False


def test_tier_receipt_does_not_bypass_original_plan_verifier_for_writes():
    plan, registry, tool = _case("write", "dangerous_action")
    def deny(_plan, _tools):
        return False
    deny.voice_stop_requested = lambda: False
    deny.voice_tiered_enabled = True
    deny.voice_tier_authorize = lambda *_: True
    assert _allows(plan, registry, tool, deny, "dangerous_action") is False


def test_tier_receipt_does_not_override_missing_tool_metadata():
    plan, registry, tool = _case()
    broken_tool = {"function": lambda: None}
    assert _allows(plan, registry, broken_tool, _verifier(
        tiered=True, authorized=lambda *_: True,
    )) is False
