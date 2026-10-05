import pytest

from core.resilient_llm import ResilientLLMClient


class FakeClient:
    def __init__(
        self,
        name,
        model,
        *,
        chat_value=None,
        chat_error=None,
        stream_values=None,
        stream_error_before=False,
        stream_error_after=False,
    ):
        self.provider_name = name
        self.model = model
        self.url = f"http://{name}"
        self.chat_value = chat_value
        self.chat_error = chat_error
        self.stream_values = list(
            stream_values or []
        )
        self.stream_error_before = stream_error_before
        self.stream_error_after = stream_error_after
        self.chat_calls = 0
        self.stream_calls = 0

    def chat(self, messages, timeout=300):
        self.chat_calls += 1

        if self.chat_error is not None:
            raise self.chat_error

        return self.chat_value

    def chat_stream(self, messages, timeout=300):
        self.stream_calls += 1

        if self.stream_error_before:
            raise RuntimeError(
                "primary stream failed before token"
            )

        for value in self.stream_values:
            yield value

        if self.stream_error_after:
            raise RuntimeError(
                "primary stream failed after token"
            )


def test_chat_uses_primary_when_healthy():
    primary = FakeClient(
        "geniex",
        "primary",
        chat_value="primär",
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        chat_value="reserv",
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
    )

    assert client.chat([]) == "primär"
    assert fallback.chat_calls == 0
    assert client.status()["active_backend"] == "primary"
    assert client.status()["last_error"] is None


def test_chat_falls_back_on_primary_failure():
    primary = FakeClient(
        "geniex",
        "primary",
        chat_error=RuntimeError("npu-fel"),
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        chat_value="reserv",
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
    )

    assert client.chat([]) == "reserv"
    status = client.status()
    assert status["active_backend"] == "fallback"
    assert "npu-fel" in status["last_error"]


def test_disabled_fallback_propagates_primary_failure():
    primary = FakeClient(
        "geniex",
        "primary",
        chat_error=RuntimeError("npu-fel"),
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        chat_value="reserv",
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=False,
    )

    with pytest.raises(
        RuntimeError,
        match="npu-fel",
    ):
        client.chat([])

    assert fallback.chat_calls == 0


def test_stream_falls_back_only_before_first_token():
    primary = FakeClient(
        "geniex",
        "primary",
        stream_error_before=True,
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        stream_values=[
            "Reserv ",
            "svar",
        ],
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
    )

    assert list(
        client.chat_stream([])
    ) == [
        "Reserv ",
        "svar",
    ]
    assert client.status()["active_backend"] == "fallback"


def test_stream_does_not_mix_fallback_after_partial_primary_output():
    primary = FakeClient(
        "geniex",
        "primary",
        stream_values=["Primär "],
        stream_error_after=True,
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        stream_values=["Reserv"],
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
    )

    stream = client.chat_stream([])

    assert next(stream) == "Primär "

    with pytest.raises(
        RuntimeError,
        match="after token",
    ):
        next(stream)

    assert fallback.stream_calls == 0



def test_programming_errors_do_not_trigger_fallback():
    primary = FakeClient(
        "geniex",
        "primary",
        chat_error=TypeError("kodfel"),
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        chat_value="reserv",
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
    )

    with pytest.raises(
        TypeError,
        match="kodfel",
    ):
        client.chat([])

    assert fallback.chat_calls == 0



class SequencePolicy:
    def __init__(self, choices):
        self.choices = iter(
            choices
        )
        self.last_reason = "policy"
        self.fallback_notes = []
        self.primary_notes = []

    def choose_backend(
        self,
        current_backend,
    ):
        choice = next(
            self.choices
        )
        self.last_reason = (
            f"choose {choice}"
        )
        return choice

    def note_fallback_activation(
        self,
        reason,
    ):
        self.fallback_notes.append(
            reason
        )

    def note_primary_restored(
        self,
        reason,
    ):
        self.primary_notes.append(
            reason
        )

    def status(self):
        return {
            "enabled": True,
            "last_reason": self.last_reason,
        }


def test_health_policy_can_bypass_primary_and_use_fallback_directly():
    primary = FakeClient(
        "geniex",
        "primary",
        chat_value="primär",
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        chat_value="reserv",
    )
    policy = SequencePolicy(
        ["fallback"]
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
        backend_policy=policy,
    )

    assert client.chat([]) == "reserv"
    assert primary.chat_calls == 0
    assert fallback.chat_calls == 1
    assert client.status()["active_backend"] == "fallback"
    assert policy.fallback_notes == [
        "choose fallback"
    ]


def test_health_policy_restores_primary_after_fallback():
    primary = FakeClient(
        "geniex",
        "primary",
        chat_value="primär",
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        chat_value="reserv",
    )
    policy = SequencePolicy(
        [
            "fallback",
            "primary",
        ]
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
        backend_policy=policy,
    )

    assert client.chat([]) == "reserv"
    assert client.chat([]) == "primär"
    assert primary.chat_calls == 1
    assert fallback.chat_calls == 1
    assert client.status()["active_backend"] == "primary"
    assert policy.primary_notes == [
        "choose primary"
    ]


def test_repeated_fallback_calls_do_not_restart_recovery_epoch():
    primary = FakeClient(
        "geniex",
        "primary",
        chat_value="primär",
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        chat_value="reserv",
    )
    policy = SequencePolicy(
        [
            "fallback",
            "fallback",
        ]
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
        backend_policy=policy,
    )

    assert client.chat([]) == "reserv"
    assert client.chat([]) == "reserv"
    assert len(
        policy.fallback_notes
    ) == 1


def test_health_policy_can_bypass_primary_stream():
    primary = FakeClient(
        "geniex",
        "primary",
        stream_values=[
            "Primär",
        ],
    )
    fallback = FakeClient(
        "geniex",
        "fallback",
        stream_values=[
            "Reserv ",
            "stream",
        ],
    )
    policy = SequencePolicy(
        ["fallback"]
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
        backend_policy=policy,
    )

    assert list(
        client.chat_stream([])
    ) == [
        "Reserv ",
        "stream",
    ]
    assert primary.stream_calls == 0
    assert fallback.stream_calls == 1
