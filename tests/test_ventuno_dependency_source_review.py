"""No installers/network: inspect local dependency texts and mock old floors."""
from scripts import ventuno_dependency_source_review as dep


def _scratch(tmp_path):
    for filename in dep.REQUIREMENTS:
        data = (dep.ROOT / filename).read_text(encoding="utf-8")
        (tmp_path / filename).write_text(data, encoding="utf-8")
    return tmp_path


def _voice_stub(monkeypatch):
    monkeypatch.setattr(
        dep.voice_lock, "inspect",
        lambda root: {"source_lock_consistent": True, "pinned_wheel_records": 28}
    )


def test_source_dependencies_policy_and_explicit_unsafe_release_flags():
    report = dep.inspect()
    assert report["source_policy_checked"] is True
    assert report["patched_http_minimums"] is True
    assert report["hashed_arm64_voice_wheels"] == 28
    assert report["installed_versions_examined"] is False
    assert report["transitive_dependency_security_checked"] is False
    assert report["production_dependency_lock_complete"] is False
    assert report["production_install_authorized"] is False


def test_old_requests_minimum_and_old_urllib3_fail_closed(tmp_path, monkeypatch):
    _voice_stub(monkeypatch)
    root = _scratch(tmp_path)
    file = root / "requirements.txt"
    baseline = file.read_text()
    file.write_text(baseline.replace("requests>=2.33.0", "requests>=2.32.0"))
    assert dep.inspect(root)["patched_http_minimums"] is False
    file.write_text(baseline.replace("urllib3>=2.8.0", "urllib3>=2.7.0"))
    assert dep.inspect(root)["source_policy_checked"] is False


def test_direct_url_or_duplicate_requirement_fails_closed(tmp_path, monkeypatch):
    _voice_stub(monkeypatch)
    root = _scratch(tmp_path)
    f = root / "requirements.txt"
    f.write_text(f.read_text() + "https://example.invalid/something.whl\n")
    assert dep.inspect(root)["status"] == "blocked-source-dependency-policy"
    f.write_text("requests>=2.33.0,<3\nurllib3>=2.8.0,<3\nurllib3==2.8.0\n")
    assert dep.inspect(root)["source_policy_checked"] is False


def test_manifest_symlink_or_missing_file_does_not_pass(tmp_path, monkeypatch):
    _voice_stub(monkeypatch)
    root = _scratch(tmp_path)
    (root / "requirements-camera.txt").unlink()
    assert dep.inspect(root)["source_policy_checked"] is False
    (root / "requirements-camera.txt").symlink_to(dep.ROOT / "requirements-camera.txt")
    assert dep.inspect(root)["source_policy_checked"] is False


def test_version_floor_parser_not_confused_by_only_upper_bound():
    assert dep._version_floor("<3") is None
    assert dep._version_floor(">=2.33.0,<3") == (2, 33, 0)
    assert dep._version_floor(">=2.32.5,<3") == (2, 32, 5)
    assert dep._version_floor("==2.34.2") == (2, 34, 2)
