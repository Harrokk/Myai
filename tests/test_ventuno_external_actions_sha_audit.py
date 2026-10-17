"""Fail-closed, network-free synthetic tests for external Actions pinning."""
from scripts import ventuno_external_actions_sha_audit as review


def _write(tmp_path, *, uses):
    root = tmp_path / ".github/workflows"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.yml").write_text(
        "name: sample\non: push\njobs:\n  safe:\n"
        "    runs-on: ubuntu-latest\n    steps:\n"
        + "\n".join("      - uses: " + target for target in uses) + "\n",
        encoding="utf-8",
    )
    return root


def test_checked_in_workflows_reference_only_commit_pinned_actions():
    r = review.inspect()
    assert r["status"] == "external-action-refs-sha-pinned-not-release-ready"
    assert r["external_refs_pinned"] is True
    assert r["workflow_files_inspected"] >= 160
    assert r["external_immutable_refs"] == 3
    assert r["unreviewed_references"] == []
    assert r["production_release_authorized"] is False
    assert r["third_party_action_security_attested"] is False


def test_mutable_tags_or_dynamic_actions_never_clear(tmp_path):
    _write(tmp_path, uses=[
        "actions/checkout@v4",
        "actions/setup-python@" + "$" + "{{ inputs.tag }}",
    ])
    result = review.inspect(tmp_path)
    assert result["external_refs_pinned"] is False
    assert len(result["unreviewed_references"]) == 2


def test_valid_commit_oid_and_docker_image_digest_are_immutable(tmp_path):
    _write(tmp_path, uses=[
        "actions/checkout@" + "a" * 40,
        "docker://ghcr.io/example/action@sha256:" + "b" * 64,
    ])
    r = review.inspect(tmp_path)
    assert r["external_refs_pinned"] is True
    assert r["external_immutable_refs"] == 2


def test_docker_tag_or_incomplete_oid_is_denied(tmp_path):
    _write(tmp_path, uses=["docker://example/action:latest",
                          "actions/checkout@" + "c" * 39])
    assert review.inspect(tmp_path)["external_refs_pinned"] is False


def test_missing_or_symlinked_workflow_fails(tmp_path):
    assert review.inspect(tmp_path)["external_refs_pinned"] is False
    base = _write(tmp_path, uses=["actions/checkout@" + "a" * 40])
    file = base / "a.yml"
    file.unlink()
    file.symlink_to(tmp_path / "untracked.yml")
    report = review.inspect(tmp_path)
    assert report["external_refs_pinned"] is False
    assert report["unreviewed_references"][0]["reason"] == "untrusted-workflow-file"


def test_parent_traversal_in_local_action_is_denied(tmp_path):
    _write(tmp_path, uses=["./../untrusted-action"])
    report = review.inspect(tmp_path)
    assert report["external_refs_pinned"] is False
    assert report["unreviewed_references"][0]["reason"] == "unsafe-local-action-path"
