"""Adversarial tests for the pure, inspection-only updater request boundary."""

import hashlib
import json

import pytest

from core.selfdev_request_protocol import (
    InspectionRequest, compare_supplied_bytes, parse_inspection_request,
)


NOW = 1_800_000_000


def _payload(**overrides):
    base = {
        "version": 1,
        "action": "inspect_candidate",
        "request_id": "a" * 32,
        "revision": "b" * 40,
        "expires_unix": NOW + 60,
        "files": [
            {"path": "core/example.py", "sha256": hashlib.sha256(b"good").hexdigest()}
        ],
    }
    base.update(overrides)
    return base


def _parse(payload=None):
    value = _payload() if payload is None else payload
    return parse_inspection_request(
        json.dumps(value, separators=(",", ":")).encode("utf-8"),
        now_unix=NOW,
    )


def test_valid_preview_is_explicitly_non_authorizing_and_immutable():
    request = _parse()
    assert isinstance(request, InspectionRequest)
    assert request.action == "inspect_candidate"
    assert request.requires_human_approval is True
    assert request.authorizes_mutation is False
    assert len(request.request_digest) == 64
    with pytest.raises(AttributeError):
        request.authorizes_mutation = True


def test_valid_matching_bytes_never_authorize_promotion():
    result = compare_supplied_bytes(_parse(), {"core/example.py": b"good"})
    assert result.status == "bytes_match_untrusted"
    assert result.inspected_files == 1
    assert result.requires_human_approval is True
    assert result.authorizes_mutation is False


@pytest.mark.parametrize("action", [
    "promote", "rollback", "recover", "migrate", "restart_service",
    "inspect_candidate;promote", "EXEC",
])
def test_mutating_action_names_cannot_enter_inspection_protocol(action):
    with pytest.raises(ValueError):
        _parse(_payload(action=action))


@pytest.mark.parametrize("extra", [
    {"approval": "YES"}, {"command": "rm -rf /"}, {"script": "print('exec')"},
    {"target_root": "/etc"}, {"service": "myai"}, {"signature": "fake"},
])
def test_unknown_fields_including_fake_approval_are_denied(extra):
    with pytest.raises(ValueError):
        _parse(_payload(**extra))


@pytest.mark.parametrize("path", [
    "../core/example.py", "core/../../etc/passwd", "/etc/passwd",
    "runtime/key.txt", ".github/workflows/evil.yml", "core/.hidden.py",
    "core//example.py", "core\\example.py", "core/example.exe",
    "core/example.py/", "core/example.py\x00", "core/./example.py",
    "core/éxample.py", "not-allowed/sample.py",
])
def test_path_canonicalization_denies_escapes_and_ambiguity(path):
    with pytest.raises(ValueError):
        _parse(_payload(files=[{"path": path, "sha256": "0" * 64}]))


def test_case_insensitive_duplicate_paths_are_rejected():
    files = [
        {"path": "core/Example.py", "sha256": "a" * 64},
        {"path": "core/example.py", "sha256": "a" * 64},
    ]
    with pytest.raises(ValueError, match="duplicate"):
        _parse(_payload(files=files))


def test_manifest_must_be_sorted_and_bounded():
    files = [
        {"path": "tests/test_b.py", "sha256": "b" * 64},
        {"path": "core/a.py", "sha256": "a" * 64},
    ]
    with pytest.raises(ValueError, match="canonical"):
        _parse(_payload(files=files))
    many = [
        {"path": f"core/file_{i:03}.py", "sha256": "a" * 64}
        for i in range(33)
    ]
    with pytest.raises(ValueError, match="count"):
        _parse(_payload(files=many))


@pytest.mark.parametrize("bad", [
    b"{", b"{}", b"\xff", b"[]" , b"null",
    b'{"version":1,"version":1}',
    b'{"value":NaN}', b'{"value":Infinity}',
    b"x" * (32 * 1024 + 1),
])
def test_invalid_or_oversize_messages_fail_closed(bad):
    with pytest.raises(ValueError):
        parse_inspection_request(bad, now_unix=NOW)


@pytest.mark.parametrize("expires", [
    NOW - 1, NOW, NOW + 301, True, 1.0, "future",
])
def test_expiration_validation(expires):
    with pytest.raises(ValueError):
        _parse(_payload(expires_unix=expires))


def test_expiry_upper_boundary_is_allowed_but_not_an_authorization():
    request = _parse(_payload(expires_unix=NOW + 300))
    assert request.authorizes_mutation is False


@pytest.mark.parametrize("invalid", [
    "c" * 39, "C" * 40, " " * 40, "z" * 40, "", 1,
])
def test_revisions_must_be_lowercase_full_commit_ids(invalid):
    with pytest.raises(ValueError):
        _parse(_payload(revision=invalid))


@pytest.mark.parametrize("contents,expected", [
    ({}, "blocked_manifest_mismatch"),
    ({"core/example.py": b"bad"}, "blocked_hash_mismatch"),
    ({"core/example.py": "good"}, "blocked_invalid_bytes"),
    ({"core/example.py": b"good", "core/extra.py": b"x"}, "blocked_manifest_mismatch"),
])
def test_hash_matching_is_strict_and_never_reads_files(contents, expected):
    result = compare_supplied_bytes(_parse(), contents)
    assert result.status == expected
    assert result.authorizes_mutation is False


def test_no_filesystem_or_process_execution_is_needed(monkeypatch):
    import builtins
    import os
    import subprocess
    from pathlib import Path

    def blocked(*args, **kwargs):
        raise AssertionError("Pure admission must not use OS resources")

    monkeypatch.setattr(builtins, "open", blocked)
    monkeypatch.setattr(Path, "open", blocked)
    monkeypatch.setattr(os, "system", blocked)
    monkeypatch.setattr(subprocess, "run", blocked)
    request = _parse()
    assert compare_supplied_bytes(request, {"core/example.py": b"good"}).status == (
        "bytes_match_untrusted"
    )


def test_canonical_fingerprint_ignores_json_key_order():
    original = _payload()
    shuffled = dict(reversed(list(original.items())))
    assert _parse(original).request_digest == _parse(shuffled).request_digest


def test_bad_manifest_hash_format_and_extra_manifest_keys_fail():
    with pytest.raises(ValueError):
        _parse(_payload(files=[{"path": "core/example.py", "sha256": "G" * 64}]))
    with pytest.raises(ValueError):
        _parse(_payload(files=[
            {"path": "core/example.py", "sha256": "a" * 64, "mode": "0777"}
        ]))


def test_no_valid_request_is_a_signed_approval():
    request = _parse()
    assert not hasattr(request, "signed_authorization")
    assert not hasattr(request, "allowed_to_deploy")
    assert request.authorizes_mutation is False
