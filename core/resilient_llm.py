class ResilientLLMClient:
    """Primary local LLM with an explicitly configured local fallback."""

    def __init__(
        self,
        primary,
        fallback=None,
        enabled=False,
    ):
        self.primary = primary
        self.fallback = fallback
        self.enabled = bool(
            enabled
            and fallback is not None
        )

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

    def _can_fallback(self):
        return bool(
            self.enabled
            and self.fallback is not None
        )

    def _mark_primary(self):
        self.last_backend = "primary"
        self.last_error = None

    def _mark_fallback(self, error):
        self.last_backend = "fallback"
        self.last_error = str(error)

    def chat(self, messages, timeout=300):
        self._mark_primary()

        try:
            return self.primary.chat(
                messages,
                timeout=timeout,
            )
        except Exception as error:
            if not self._can_fallback():
                raise

            self._mark_fallback(error)

            return self.fallback.chat(
                messages,
                timeout=timeout,
            )

    def chat_stream(self, messages, timeout=300):
        self._mark_primary()
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

        except Exception as error:
            if (
                emitted
                or not self._can_fallback()
            ):
                raise

            self._mark_fallback(error)

        fallback_stream = getattr(
            self.fallback,
            "chat_stream",
            None,
        )

        if callable(fallback_stream):
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

    def status(self):
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
        }
