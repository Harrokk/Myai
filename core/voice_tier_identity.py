"""Trusted STT provenance binding for the disabled tiered voice pilot.

The factory must have independently verified the actual model files before
supplying these records; this object does not hash or load weights. Text from
an STT result never determines which model is credited for the vote.
"""
import re

from core.voice_verification import verify_tiered_transcripts


_SHA = re.compile(r"[0-9a-f]{64}\Z")


class TrustedSTTBindings:
    def __init__(self, records):
        if not isinstance(records, (list, tuple)) or not 1 <= len(records) <= 3:
            raise ValueError("invalid-trusted-model-count")
        self._models = {}
        self._providers = {}
        families = set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("invalid-model-record")
            key = record.get("key")
            provider = record.get("provider")
            family = record.get("family")
            sha = record.get("sha256")
            if (not isinstance(key, str) or not 0 < len(key) <= 64
                    or not re.fullmatch(r"[a-z][a-z0-9_-]*", key)
                    or key in self._models or provider is None
                    or not callable(getattr(provider, "transcribe", None))
                    or not isinstance(family, str)
                    or not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", family)
                    or family in families or not isinstance(sha, str)
                    or not _SHA.fullmatch(sha)):
                raise ValueError("invalid-or-duplicate-trusted-model")
            if any(provider is old for old in self._providers.values()):
                raise ValueError("duplicate-provider-object")
            families.add(family)
            self._models[key] = {
                "family": family,
                "revision": "sha256:" + sha,
            }
            self._providers[key] = provider

    def verify(self, tier, observations):
        """Credit only the exact registered provider objects for this request.

        Observations are (provider, text) pairs produced by the trusted
        orchestrator from one audio capture. Raw STT metadata cannot appoint
        its own family, key or SHA. Duplicate and absent votes fail closed.
        """
        if not isinstance(observations, (list, tuple)):
            return {"accepted": False, "reason": "invalid-observations"}
        votes = []
        for observation in observations:
            if not isinstance(observation, tuple) or len(observation) != 2:
                return {"accepted": False, "reason": "invalid-observation"}
            provider, text = observation
            matched = [
                key for key, registered in self._providers.items()
                if registered is provider
            ]
            if len(matched) != 1:
                return {"accepted": False, "reason": "untrusted-provider"}
            if not isinstance(text, str):
                return {"accepted": False, "reason": "invalid-transcript"}
            votes.append({"model_key": matched[0], "text": text})
        return verify_tiered_transcripts(tier, votes, self._models)
