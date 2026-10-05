RECOVERABLE_LLM_ERRORS = (
    RuntimeError,
    ValueError,
    TimeoutError,
    ConnectionError,
    OSError,
)


class ResilientLLMClient:
    """Primary local LLM with an explicitly configured local fallback."""

    def __init__(
        self,
        primary,
        fallback=None,
        enabled=False,
        recoverable_errors=RECOVERABLE_LLM_ERRORS,
        backend_policy=None,
    ):
        self.primary = primary
        self.fallback = fallback
        self.enabled = bool(
            enabled
            and fallback is not None
        )
        self.backend_policy = backend_policy

        self.provider_name = getattr(
            primary,
            "provider_name",
            "unknown",
        )
        self.model = getattr(
            primary,
            "model",
            "",
        )
        self.url = getattr(
            primary,
            "url",
            "",
        )

        self.last_backend = "primary"
        self.last_error = None
        self.last_routing_reason = (
            "initial primary backend"
        )
        self.recoverable_errors = tuple(
            recoverable_errors
        )

    def _can_fallback(self):
        return bool(
            self.enabled
            and self.fallback is not None
        )

    def _policy_backend(self):
        if (
            not self._can_fallback()
            or self.backend_policy is None
        ):
            return self.last_backend

        choose = getattr(
            self.backend_policy,
            "choose_backend",
            None,
        )

        if not callable(
            choose
        ):
            return self.last_backend

        desired = str(
            choose(
                self.last_backend
            )
        ).strip().lower()

        if desired not in {
            "primary",
            "fallback",
        }:
            desired = (
                self.last_backend
            )

        reason = getattr(
            self.backend_policy,
            "last_reason",
            "",
        )

        if reason:
            self.last_routing_reason = (
                str(reason)
            )

        return desired

    def _notify_policy_fallback(
        self,
        reason,
    ):
        if self.backend_policy is None:
            return

        notify = getattr(
            self.backend_policy,
            "note_fallback_activation",
            None,
        )

        if callable(
            notify
        ):
            notify(
                reason
            )

    def _notify_policy_primary(
        self,
        reason,
    ):
        if self.backend_policy is None:
            return

        notify = getattr(
            self.backend_policy,
            "note_primary_restored",
            None,
        )

        if callable(
            notify
        ):
            notify(
                reason
            )

    def _mark_primary(
        self,
        reason=None,
    ):
        changed = (
            self.last_backend
            != "primary"
        )
        self.last_backend = "primary"
        self.last_error = None

        if reason:
            self.last_routing_reason = (
                str(reason)
            )

        if changed:
            self._notify_policy_primary(
                self.last_routing_reason
            )

    def _mark_fallback(
        self,
        error=None,
        reason=None,
    ):
        changed = (
            self.last_backend
            != "fallback"
        )
        self.last_backend = "fallback"

        if error is not None:
            self.last_error = str(
                error
            )

        if reason:
            self.last_routing_reason = (
                str(reason)
            )

        if changed:
            self._notify_policy_fallback(
                self.last_routing_reason
            )

    def _fallback_chat(
        self,
        messages,
        timeout,
        *,
        reason,
    ):
        if not self._can_fallback():
            raise RuntimeError(
                "Fallback-backend är inte tillgänglig."
            )

        self._mark_fallback(
            reason=reason
        )
        return self.fallback.chat(
            messages,
            timeout=timeout,
        )

    def chat(self, messages, timeout=300):
        desired = self._policy_backend()

        if (
            desired == "fallback"
            and self._can_fallback()
        ):
            return self._fallback_chat(
                messages,
                timeout,
                reason=self.last_routing_reason,
            )

        self._mark_primary(
            reason=self.last_routing_reason
        )

        try:
            return self.primary.chat(
                messages,
                timeout=timeout,
            )
        except self.recoverable_errors as error:
            if not self._can_fallback():
                raise

            self._mark_fallback(
                error,
                reason=(
                    "primary request failed; fallback used"
                ),
            )

            return self.fallback.chat(
                messages,
                timeout=timeout,
            )

    def _fallback_stream(
        self,
        messages,
        timeout,
        *,
        reason,
    ):
        if not self._can_fallback():
            raise RuntimeError(
                "Fallback-backend är inte tillgänglig."
            )

        self._mark_fallback(
            reason=reason
        )
        fallback_stream = getattr(
            self.fallback,
            "chat_stream",
            None,
        )

        if callable(
            fallback_stream
        ):
            yield from fallback_stream(
                messages,
                timeout=timeout,
            )
            return

        value = self.fallback.chat(
            messages,
            timeout=timeout,
        )

        if value:
            yield value

    def chat_stream(self, messages, timeout=300):
        desired = self._policy_backend()

        if (
            desired == "fallback"
            and self._can_fallback()
        ):
            yield from self._fallback_stream(
                messages,
                timeout,
                reason=self.last_routing_reason,
            )
            return

        self._mark_primary(
            reason=self.last_routing_reason
        )
        emitted = False

        stream = getattr(
            self.primary,
            "chat_stream",
            None,
        )

        try:
            if callable(stream):
                for chunk in stream(
                    messages,
                    timeout=timeout,
                ):
                    if chunk:
                        emitted = True
                        yield chunk
                return

            value = self.primary.chat(
                messages,
                timeout=timeout,
            )

            if value:
                emitted = True
                yield value
            return

        except self.recoverable_errors as error:
            if (
                emitted
                or not self._can_fallback()
            ):
                raise

            self._mark_fallback(
                error,
                reason=(
                    "primary stream failed before first token; fallback used"
                ),
            )

        yield from self._fallback_stream(
            messages,
            timeout,
            reason=self.last_routing_reason,
        )

    def status(self):
        policy_status = {}

        if self.backend_policy is not None:
            status = getattr(
                self.backend_policy,
                "status",
                None,
            )

            if callable(
                status
            ):
                policy_status = dict(
                    status()
                )

        return {
            "enabled": self.enabled,
            "active_backend": self.last_backend,
            "primary_provider": getattr(
                self.primary,
                "provider_name",
                "unknown",
            ),
            "primary_model": getattr(
                self.primary,
                "model",
                "",
            ),
            "fallback_provider": (
                getattr(
                    self.fallback,
                    "provider_name",
                    "unknown",
                )
                if self.fallback is not None
                else None
            ),
            "fallback_model": (
                getattr(
                    self.fallback,
                    "model",
                    "",
                )
                if self.fallback is not None
                else None
            ),
            "last_error": self.last_error,
            "routing_reason": (
                self.last_routing_reason
            ),
            "health_aware": (
                policy_status
            ),
        }
