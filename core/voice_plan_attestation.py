"""Private per-session binding of voice preview to actual dispatch plan.

The signature covers selected tool steps, inputs, mutable safety metadata
and callable identity. Only exact matching plans can reuse high-risk
spoken consent. This is NOT a user-identity credential or a replacement
for per-tool permission checks. Do not export signatures or HMAC keys.
"""
import hashlib
import hmac
import json


def sign_voice_plan(plan, tools, secret):
    if not isinstance(plan, dict) or not isinstance(tools, dict):
        raise ValueError("invalid-tool-plan")
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) > 16:
        raise ValueError("invalid-tool-steps")
    if not isinstance(secret, bytes) or len(secret) != 32:
        raise ValueError("invalid-private-key")
    safety = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("invalid-plan-step")
        name = step.get("tool")
        if not isinstance(name, str) or not name:
            raise ValueError("invalid-tool-name")
        metadata = tools.get(name)
        if not isinstance(metadata, dict):
            raise ValueError("missing-tool-metadata")
        callback = metadata.get("function")
        safety.append({
            "tool": name,
            "safety": metadata.get("safety", {}),
            # A swapped callback is not equivalent even if it claims
            # the same name/effect/input. Internal object IDs are HMACed,
            # never directly exposed or used as durable identifiers.
            "callable_id": id(callback) if callable(callback) else None,
        })
    try:
        serialized = json.dumps({
            "steps": steps,
            "safety": safety,
        }, sort_keys=True, ensure_ascii=False,
           separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("unserializable-tool-plan") from error
    if len(serialized) > 32768:
        raise ValueError("oversized-tool-plan")
    return hmac.new(secret, serialized, hashlib.sha256).hexdigest()


def same_voice_plan(plan, tools, secret, approved_digest):
    if not isinstance(approved_digest, str) or len(approved_digest) != 64:
        return False
    try:
        current = sign_voice_plan(plan, tools, secret)
    except (ValueError, TypeError, AttributeError, KeyError):
        return False
    return hmac.compare_digest(current, approved_digest)
