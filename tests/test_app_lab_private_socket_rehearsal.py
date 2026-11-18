"""Real AF_UNIX filesystem socket, ephemeral secret and synthetic MyAI.

No VENTUNO, App Lab, GenieX, model, microphone, live TTS or persistence.
"""
import os
from pathlib import Path
import socket

import pytest

from core import app_lab_private_socket_rehearsal as rehearsal


@pytest.mark.skipif(os.name != "posix" or os.getuid() == 0 or
                    not hasattr(socket, "SO_PEERCRED"),
                    reason="non-root Linux kernel peer credentials required")
def test_real_owned_private_socket_full_synthetic_answer():
    result = rehearsal.rehearse_one_private_turn(enabled=True)
    assert result == {
        "status": "test-passed",
        "reply": {
            "status": "ready",
            "answer": "Solceller omvandlar ljus till elektricitet.",
        },
        "private_endpoint_removed": True,
    }


@pytest.mark.skipif(os.name != "posix" or os.getuid() == 0 or
                    not hasattr(socket, "SO_PEERCRED"),
                    reason="non-root Linux kernel peer credentials required")
@pytest.mark.parametrize("mode", ["blocked", "uncertain"])
def test_unsafe_synthetic_myai_reply_is_withheld(mode):
    result = rehearsal.rehearse_one_private_turn(enabled=True, mode=mode)
    assert result == {
        "status": "test-withheld",
        "reply": {"status": "withheld"},
        "private_endpoint_removed": True,
    }


def test_disabled_rehearsal_performs_no_socket_or_key_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No socket/file/key use in disabled mode")
    monkeypatch.setattr(rehearsal.tempfile, "TemporaryDirectory", forbidden)
    monkeypatch.setattr(rehearsal.secrets, "token_bytes", forbidden)
    monkeypatch.setattr(rehearsal.socket, "socket", forbidden)
    assert rehearsal.rehearse_one_private_turn() == {"status": "disabled"}


@pytest.mark.parametrize("bad", ["production", "other", [], False])
def test_non_fixture_modes_rejected_before_creating_key(monkeypatch, bad):
    def forbidden(*args, **kwargs):
        raise AssertionError("No key use for invalid fixture mode")
    monkeypatch.setattr(rehearsal.secrets, "token_bytes", forbidden)
    assert rehearsal.rehearse_one_private_turn(
        enabled=True, mode=bad,
    ) == {"status": "invalid-rehearsal-mode"}


def test_rehearsal_cannot_accept_external_core_argument():
    with pytest.raises(TypeError):
        rehearsal.rehearse_one_private_turn(
            enabled=True, core=object(),
        )


@pytest.mark.skipif(os.name != "posix" or os.getuid() == 0 or
                    not hasattr(socket, "SO_PEERCRED"),
                    reason="non-root Linux kernel peer credentials required")
def test_stop_state_prevents_model_dispatch():
    assert rehearsal.rehearse_one_private_turn(
        enabled=True, stop_requested=lambda: True,
    )["status"] != "test-passed"


def test_stop_probe_must_be_callable():
    assert rehearsal.rehearse_one_private_turn(
        enabled=True, stop_requested=True,
    ) == {"status": "invalid-stop-probe"}
