"""Bound, short-lived dispatch receipt for the disabled tiered voice pilot.

This module is intentionally unable to approve CRITICAL tool execution.
That requires a separately authenticated user-approval integration that does
not yet exist. A language model never receives this object or the HMAC key.

The caller must obtain observations from the SAME captured PCM request using
the trusted model instances. This contract remains a source-only prototype.
"""
import math
import threading
import time

from core.voice_plan_attestation import sign_voice_plan, same_voice_plan
from core.voice_risk_policy import classify_voice_tier
from core.voice_tier_identity import TrustedSTTBindings
from core.voice_verification import _canonical


class TieredVoicePermit:
    def __init__(
        self, *, transcript, plan, tools, model_bindings, observations,
        secret, stop_requested, clock=None, ttl_seconds=15.0,
    ):
        if not isinstance(model_bindings, TrustedSTTBindings):
            raise ValueError("untrusted-model-bindings")
        if not callable(stop_requested) or not isinstance(secret, bytes) or len(secret) != 32:
            raise ValueError("invalid-receipt-context")
        if (type(ttl_seconds) not in (int, float)
                or not math.isfinite(ttl_seconds)
                or not 0 < ttl_seconds <= 30):
            raise ValueError("invalid-receipt-lifetime")

        decision = classify_voice_tier(transcript, plan, tools)
        tier = decision["tier"]
        if tier == "blocked":
            raise ValueError("blocked-voice-request")
        evidence = model_bindings.verify(tier, observations)
        if not evidence.get("accepted") or evidence.get("text") != _canonical(transcript):
            raise ValueError("unverified-voice-request")

        digest = sign_voice_plan(plan, tools, secret)
        self._tier = tier
        self._text = transcript
        self._digest = digest
        self._secret = secret
        self._stop_requested = stop_requested
        self._trusted_bindings = model_bindings
        self._evidence_providers = tuple(p for p, _ in observations)
        self._clock = clock or time.monotonic
        self._created_at = self._clock()
        if not isinstance(self._created_at, (int, float)) or not math.isfinite(self._created_at):
            raise ValueError("invalid-monotonic-clock")
        self._ttl = float(ttl_seconds)
        self._used_steps = set()
        self._lock = threading.Lock()

    @property
    def tier(self):
        return self._tier

    @property
    def plan_digest(self):
        """Private per-session attestation; never export to model or logs."""
        return self._digest

    def authorize(self, plan, tools, tool_name, effective_input):
        """Atomic fail-closed per-tool authorization at dispatch time.

        A successful medium receipt still needs the pre-existing HMAC plan
        verifier. A critical receipt alone is never sufficient authorization.
        """
        try:
            with self._lock:
                if self._stop_requested() is not False:
                    return False
                now = self._clock()
                if (not isinstance(now, (int, float))
                        or not math.isfinite(now)
                        or not 0 <= now - self._created_at <= self._ttl):
                    return False
                if not all(
                    self._trusted_bindings.is_trusted_provider(p)
                    for p in self._evidence_providers
                ):
                    return False
                if self._tier == "critical":
                    # Separate user identity/approval has NOT been wired.
                    return False
                if not same_voice_plan(plan, tools, self._secret, self._digest):
                    return False
                current = classify_voice_tier(self._text, plan, tools)
                if current["tier"] != self._tier:
                    return False
                if (not isinstance(tool_name, str) or tool_name in self._used_steps
                        or not isinstance(plan, dict)
                        or not isinstance(plan.get("steps"), list)):
                    return False
                matching = [
                    step for step in plan["steps"]
                    if isinstance(step, dict) and step.get("tool") == tool_name
                ]
                if len(matching) != 1:
                    return False
                tool = tools.get(tool_name)
                if not isinstance(tool, dict):
                    return False
                if tool.get("pass_user_input", False):
                    if (type(effective_input) is not str
                            or effective_input != matching[0].get("input")):
                        return False
                elif effective_input is not None:
                    return False
                # Consume before calling any potentially effectful tool.
                # Duplicate/replayed invocations are rejected.
                self._used_steps.add(tool_name)
                return True
        except Exception:
            return False
