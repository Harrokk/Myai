"""Disabled-by-default synthetic bridge from MyAI VoicePipeline to tiered votes.

A real hardware rollout is intentionally impossible: configuration validation
rejects enabling the flag, no model factory provides trusted pinned bindings,
and CRITICAL actions lack a separate identity/approval channel.

Do not let STT results self-declare model provenance. This module only consumes
TrustedSTTBindings installed by a future audited model factory.
"""
from core.voice_risk_policy import classify_voice_tier
from core.voice_tier_authorization import TieredVoicePermit
from core.voice_tier_identity import TrustedSTTBindings


def _clarify(reason):
    return {
        "status": "clarify",
        "message": "Röstkommandot kunde inte verifieras säkert. Försök igen.",
        "verification_reason": reason,
    }


def process_tiered_utterance(pipeline, audio):
    """Run the staged 1/2/3 policy without granting unverified tools."""
    token = pipeline._stop_token
    if token.is_set():
        return _clarify("session_stopped")
    if not isinstance(audio, bytes) or not audio:
        return _clarify("invalid_pcm")
    if pipeline.pending_confirmation is not None:
        pipeline.pending_confirmation = None
        return _clarify("legacy_confirmation_not_reusable")
    binder = getattr(pipeline, "trusted_stt_bindings", None)
    if not isinstance(binder, TrustedSTTBindings):
        return _clarify("model_provenance_unavailable")
    preview = getattr(pipeline.assistant, "preview_tool_plan", None)
    registry = getattr(pipeline.assistant, "tools", None)
    if not callable(preview) or not isinstance(registry, dict):
        return _clarify("guarded_planner_required")

    if not binder.is_trusted_provider(pipeline.primary_stt):
        return _clarify("primary_model_identity_changed")
    started_at = pipeline.clock()
    try:
        first = pipeline._transcribe(pipeline.primary_stt, audio)
    except Exception:
        return _clarify("primary_stt_failed")
    if token.is_set() or pipeline._stt_deadline_expired(started_at):
        return _clarify("stt_cancelled_or_stale")
    if not first["text"]:
        return _clarify("no_primary_transcript")
    try:
        plan = preview(first["text"])
        decision = classify_voice_tier(first["text"], plan, registry)
    except Exception:
        return _clarify("planning_failed")

    tier = decision["tier"]
    if tier == "blocked" or decision["required_votes"] is None:
        return _clarify("unknown_or_blocked_plan")

    # Echo suppression is allowed to drop an utterance, never to authorize.
    risk = {
        "level": "high" if tier != "low" else "low",
        "tier": tier,
        "tool_plan_checked": True,
        "tool_names": [step["tool"] for step in plan["steps"]],
    }
    echo = pipeline._probable_tts_echo(first["text"], risk)
    if echo is not None:
        return echo

    desired = decision["required_votes"]
    backups = pipeline.backup_stt
    if len(backups) < desired - 1:
        return _clarify("missing_independent_stt")

    observed = [(pipeline.primary_stt, first["text"])]
    for provider in backups[:desired - 1]:
        if token.is_set():
            return _clarify("session_stopped")
        if not binder.is_trusted_provider(provider):
            return _clarify("backup_model_identity_changed")
        try:
            result = pipeline._transcribe(provider, audio)
        except Exception:
            return _clarify("backup_stt_failed")
        if token.is_set() or pipeline._stt_deadline_expired(started_at):
            return _clarify("stt_cancelled_or_stale")
        if tier == "critical" and not result["text"]:
            # A successfully invoked third model may abstain. Errors and
            # missing models cannot masquerade as an abstention.
            observed.append((provider, ""))
            continue
        if classify_voice_tier(result["text"], plan, registry)["tier"] != tier:
            # A second recognizer may have heard a MORE dangerous action.
            # Never silently keep the primary's lower authorization level.
            return _clarify("risk_disagreement")
        observed.append((provider, result["text"]))

    outcome = binder.verify(tier, observed)
    if not outcome.get("accepted"):
        return _clarify("independent_votes_disagree")
    try:
        receipt = TieredVoicePermit(
            transcript=first["text"],
            plan=plan,
            tools=registry,
            model_bindings=binder,
            observations=observed,
            secret=pipeline._plan_attestation_key,
            stop_requested=token.is_set,
            clock=pipeline.clock,
        )
    except Exception:
        return _clarify("receipt_issue_failed")

    if tier == "critical":
        # Separate trusted human identity and approval NOT implemented.
        # Never advertise an executable pending voice confirmation.
        return {
            "status": "clarify",
            "message": "Kritiskt röstkommando spärrat tills separat behörighetskontroll finns.",
            "verification_reason": "critical_external_approval_unavailable",
        }
    if token.is_set() or pipeline._stt_deadline_expired(started_at):
        return _clarify("stt_cancelled_or_stale")

    response = pipeline._respond_and_speak(
        first["text"],
        approved_digest=receipt.plan_digest,
        risk=risk,
        stop_token=token,
        tier_authorizer=receipt.authorize,
    )
    execution = pipeline._public_tool_execution(response)
    incomplete = pipeline._tool_execution_incomplete(response, execution)
    blocked = bool(response.get("tool_dispatch_blocked") or incomplete)
    return {
        "status": "clarify" if blocked else "completed",
        "risk": risk,
        "verification": {
            "tier": tier,
            "support": outcome["support"],
            "required_votes": outcome["required_votes"],
        },
        "assistant": response,
        **({"tool_execution": execution} if execution else {}),
    }
