"""Ensure vendor stderr is never leaked; only bounded categories escape."""
import json
import pytest

from scripts.ventuno_qnn_error_categories import classify_qnn_output


@pytest.mark.parametrize("raw,expected", [
    (b"FastRPC: Permission denied on /dev/fastrpc-cdsp-secure", "access_denied"),
    (b"Dlopen failed to load library libQnnHtpV75Stub.so", "missing_shared_library"),
    (b"mmap allocation failed: ENOMEM", "memory_allocation_failure"),
    (b"unsupported op Conv2d for graph", "unsupported_graph_or_operation"),
    (b"Fastrpc session failed", "dsp_rpc_transport_failure"),
    (b"failed to load model", "model_or_dlc_load_failure"),
    (b"QNN backend create error", "backend_initialization_failure"),
    (b"unrecognized option --blah", "cli_argument_error"),
])
def test_categories_without_messages(raw, expected):
    result = classify_qnn_output(b"", raw)
    assert expected in result["categories"]
    assert result["raw_text_exported"] is False
    assert raw.decode("ascii") not in json.dumps(result)
    assert "/dev/" not in json.dumps(result)


def test_unknown_messages_remain_unclassified_and_unreported():
    secret = b"PASSWORD=hunter2 /home/private/filename.db"
    result = classify_qnn_output(secret, secret)
    assert result["categories"] == ["unclassified"]
    assert b"PASSWORD" not in json.dumps(result).encode("utf-8")
    assert "filename.db" not in json.dumps(result)


def test_caps_both_streams_and_never_includes_late_sensitive_text():
    result = classify_qnn_output(
        b"x" * 20000 + b"Permission denied",
        b"y" * 19000 + b"ENoMem",
    )
    assert result["categories"] == ["unclassified"]
    assert result["output_capture_read_was_truncated"] is True
    assert result["stdout_sampled_bytes"] == 16384
    assert result["stderr_sampled_bytes"] == 16384


def test_multiple_categories_truncate_to_fixed_list():
    data = b"permission denied; ENOMEM; unsupported op; Fastrpc failed; invalid argument"
    result = classify_qnn_output(data, b"")
    assert len(result["categories"]) <= 4
    assert result["categories"][0] == "access_denied"


@pytest.mark.parametrize("wrong", ["error", None, 12, bytearray(b"oops")])
def test_requires_exact_bytes_to_deny_structured_fake_error(wrong):
    with pytest.raises(TypeError):
        classify_qnn_output(wrong, b"")
