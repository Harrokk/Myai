"""Two-process private AF_UNIX rehearsal, all synthetic/off-device."""
import os
import socket

import pytest

from core import app_lab_private_process_rehearsal as stage


@pytest.mark.skipif(os.name != "posix" or os.getuid() == 0
                    or not hasattr(socket, "SO_PEERCRED"),
                    reason="non-root Linux with SO_PEERCRED required")
def test_two_real_processes_exchange_one_signed_swedish_reply():
    assert stage.rehearse_two_private_processes(enabled=True) == {
        "status": "test-passed",
        "processes": 2,
        "private_endpoint_removed": True,
    }


@pytest.mark.skipif(os.name != "posix" or os.getuid() == 0
                    or not hasattr(socket, "SO_PEERCRED"),
                    reason="non-root Linux with SO_PEERCRED required")
@pytest.mark.parametrize("mode", ["blocked", "uncertain"])
def test_unsafe_fake_myai_replies_withheld_across_processes(mode):
    assert stage.rehearse_two_private_processes(
        enabled=True, mode=mode,
    ) == {"status": "test-withheld", "processes": 2,
          "private_endpoint_removed": True}


@pytest.mark.skipif(os.name != "posix" or os.getuid() == 0
                    or not hasattr(socket, "SO_PEERCRED"),
                    reason="non-root Linux with SO_PEERCRED required")
def test_different_inherited_secret_is_rejected_before_fake_dispatch():
    assert stage.rehearse_two_private_processes(
        enabled=True, mode="bad-client-key",
    ) == {"status": "authentication-test-passed",
          "private_endpoint_removed": True}


def test_disabled_default_has_zero_socket_process_or_key_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled stage must have no effects")
    monkeypatch.setattr(stage.secrets, "token_bytes", forbidden)
    monkeypatch.setattr(stage.subprocess, "Popen", forbidden)
    monkeypatch.setattr(stage.tempfile, "TemporaryDirectory", forbidden)
    assert stage.rehearse_two_private_processes() == {"status": "disabled"}


@pytest.mark.parametrize("mode", ["production", "online", None, 0, [], ""])
def test_untrusted_modes_are_rejected_before_key_generation(monkeypatch, mode):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid mode cannot generate keys")
    monkeypatch.setattr(stage.secrets, "token_bytes", forbidden)
    assert stage.rehearse_two_private_processes(
        enabled=True, mode=mode,
    ) == {"status": "invalid-test-mode"}


def test_cannot_inject_a_real_myai_service_or_arbitrary_text():
    with pytest.raises(TypeError):
        stage.rehearse_two_private_processes(
            enabled=True, assistant=object(),
        )
    with pytest.raises(TypeError):
        stage.rehearse_two_private_processes(
            enabled=True, text="Delete every file",
        )


def test_child_requires_explicit_bootstrap_mode():
    assert stage._main([]) == 2
    assert stage._main(["--start-service"]) == 2


def test_bootstrap_requires_fifo_descriptor():
    with pytest.raises(ValueError, match="pipe"):
        stage._read_bootstrap(0)
