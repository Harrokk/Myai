"""Verified STT provenance binding for opt-in tiered voice authorization.

A raw SHA string is never sufficient identity evidence: each model must be
backed by a verified, local, read-only bundle created by the audited loader.
No model receives permission to self-report its own identity.
"""
import re

from core.voice_model_provenance import VerifiedSTTModel
from core.voice_verification import verify_tiered_transcripts


class TrustedSTTBindings:
    def __init__(self, records):
        if not isinstance(records, (list, tuple)) or not 1 <= len(records) <= 3:
            raise ValueError("invalid-trusted-model-count")
        self._models = {}
        self._providers = {}
        self._bundles = {}
        families = set()
        for record in records:
            if not isinstance(record, dict) or set(record) != {
                "key", "provider", "bundle"
            }:
                raise ValueError("invalid-model-record")
            key = record.get("key")
            provider = record.get("provider")
            bundle = record.get("bundle")
            if (not isinstance(key, str) or not 0 < len(key) <= 64
                    or not re.fullmatch(r"[a-z][a-z0-9_-]*", key)
                    or key in self._models or provider is None
                    or not callable(getattr(provider, "transcribe", None))
                    or type(bundle) is not VerifiedSTTModel
                    or not bundle.is_current()
                    or getattr(provider, "model_name", None) != bundle.root
                    or bundle.family in families):
                raise ValueError("invalid-or-duplicate-trusted-model")
            if any(provider is old for old in self._providers.values()):
                raise ValueError("duplicate-provider-object")
            families.add(bundle.family)
            self._models[key] = {
                "family": bundle.family,
                "revision": bundle.revision,
            }
            self._providers[key] = provider
            self._bundles[key] = bundle

    def is_trusted_provider(self, provider):
        return any(
            p is provider and self._bundles[key].is_current()
            and getattr(provider, "model_name", None) == self._bundles[key].root
            for key, p in self._providers.items()
        )

    def verify(self, tier, observations):
        """Credit only real registered provider instances and current files.

        Rechecks read-only model metadata after each inference. Native model
        loaders must independently use the validated paths; Python identity
        alone is not a hardware or code-execution trust boundary.
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
            if (not self._bundles[matched[0]].is_current()
                    or getattr(provider, "model_name", None)
                       != self._bundles[matched[0]].root):
                return {"accepted": False, "reason": "model-files-changed"}
            if not isinstance(text, str):
                return {"accepted": False, "reason": "invalid-transcript"}
            votes.append({"model_key": matched[0], "text": text})
        return verify_tiered_transcripts(tier, votes, self._models)
