"""Offline unit tests: NO calls to the real GenieX service in pytest."""

import json
import os
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from scripts import ventuno_live_qairt_synthetic_once as module


BACKEND = {
    "status": "backend-associated-with-service",
    "runtime_backend_evidence": True,
    "fast_rpc_secure_fd_open": True,
    "mapped_libraries": {"libQnnHtp.so": True},
}


def test_only_confirmed_htp_and_secure_fastrpc_can_pass_gate():
    assert module.backend_gate(BACKEND, 4 * 1048576) == (
        "ready_for_single_synthetic_request"
    )
    for override in (
        {"status": "inconclusive"},
        {"fast_rpc_secure_fd_open": False},
        {"runtime_backend_evidence": False},
        {"mapped_libraries": {"libQnnHtp.so": False}},
    ):
        evidence = {**BACKEND, **override}
        assert module.backend_gate(evidence, 4 * 1048576).startswith("no_go_")
    assert module.backend_gate(BACKEND, None).startswith("no_go_")
    assert module.backend_gate(BACKEND, 10).startswith("no_go_")


def test_model_identity_is_pinned_to_expected_quantized_qualcomm_stack():
    valid = "qualcomm/Qwen3-4B-Instruct-2507:W4A16"
    assert module._model_id({"data": [{"id": valid}]}) == valid
    for label in ("other/Qwen3:W4A16", "qualcomm/Another", "", None):
        assert module._model_id({"data": [{"id": label}]}) is None
    assert module._model_id({"data": [{"id": valid}, {"id": valid}]}) is None


def test_only_sanitized_numeric_timings_can_escape():
    sample = module._safe_sample({
        "choices": [{"message": {"content": "sensitive-never-log"}}],
        "usage": {"completion_tokens": 6, "prompt_tokens": 12},
        "timings": {"predicted_per_second": 12.5, "prompt_per_second": 100.0},
    }, 0.4)
    assert sample["response_nonempty"] is True
    assert sample["returned_text_logged"] is False
    assert sample["completion_tokens"] == 6
    assert "sensitive" not in json.dumps(sample)
    with pytest.raises(ValueError):
        module._safe_sample({"choices": [{"message": {"content": ""}}]}, 0.2)


def test_bounded_response_rejects_large_http_result():
    class Response:
        def read(self, maximum):
            return b"x" * maximum
    with pytest.raises(ValueError, match="too_large"):
        module._read_json(Response())


def test_no_live_request_without_explicit_authorization(monkeypatch):
    monkeypatch.delenv("MYAI_ALLOW_SYNTHETIC_GENIEX_REQUEST", raising=False)
    monkeypatch.setattr(module, "main_pid_from_systemd", lambda: 123)
    monkeypatch.setattr(module, "summarize_service", lambda *args: BACKEND)
    monkeypatch.setattr(module, "available_memory_kib", lambda: 4 * 1048576)
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: (
        pytest.fail("Unauthorized live HTTP request attempted")
    ))
    result = module.probe()
    assert result["status"] == "no_go_no_explicit_synthetic_request_authorization"
    assert result["sample"] is None


def test_synthetic_request_has_exactly_one_bounded_prompt(monkeypatch):
    model = "qualcomm/Qwen3-4B-Instruct-2507:W4A16"
    sent = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, n):
            return json.dumps({
                "choices": [{"message": {"content": "12"}}],
                "usage": {"completion_tokens": 4},
                "timings": {"predicted_per_second": 24.0},
            }).encode()
    def fake_urlopen(request, timeout):
        assert request.full_url == "http://127.0.0.1:18181/v1/chat/completions"
        assert timeout <= 30
        payload = json.loads(request.data)
        assert payload["max_tokens"] == 24
        assert payload["stream"] is False
        assert payload["messages"] == [{
            "role": "user", "content": module.SYNTHETIC_PROMPT,
        }]
        sent.append(payload)
        return Response()
    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    outcome = module.run_one_synthetic_request(model)
    assert len(sent) == 1
    assert outcome["returned_text_logged"] is False
    assert outcome["response_nonempty"] is True
