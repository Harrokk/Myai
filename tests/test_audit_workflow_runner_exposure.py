"""Unprivileged tests of conservative CI runner exposure inventory."""
from pathlib import Path
import pytest
from scripts.audit_workflow_runner_exposure import summarize_source, inventory


def test_auto_self_hosted_reference_is_review_lead_not_a_pass():
    s = """name: unsafe
on:
  push:
    branches: [main]
jobs:
  demo:
    runs-on: [self-hosted, linux, ventuno-q]
    permissions:
      contents: write
"""
    r = summarize_source("unsafe.yml", s)
    assert r["risk"] == "REVIEW_AUTO_SELF_HOSTED"
    assert r["auto_triggers"] == ["push"]
    assert r["self_hosted_runner_reference"] is True
    assert r["push_scope"] == "EXPLICIT_BRANCHES"
    assert r["push_branches"] == ["main"]
    assert r["write_permissions_declared"] is True


def test_pure_hosted_and_manual_selfhosted_are_distinguished():
    hosted = """on:
  push:
jobs:
  test:
    runs-on: ubuntu-24.04
permissions:
  contents: read
"""
    manual = """on:
  workflow_dispatch:
jobs:
  manual:
    runs-on: [self-hosted, ventuno-q]
"""
    assert summarize_source("h.yml", hosted)["risk"] == (
        "NO_STATIC_SELF_HOSTED_RUNNER_INDICATION"
    )
    r = summarize_source("m.yml", manual)
    assert r["risk"] == "REVIEW_MANUAL_SELF_HOSTED"
    assert r["manual_triggers"] == ["workflow_dispatch"]


def test_dynamic_runner_requires_human_review():
    expr = chr(36) + "{{ matrix.runner }}"
    s = 'on: [push]\njobs:\n  x:\n    runs-on: ' + expr + '\n'
    r = summarize_source("dynamic.yml", s)
    assert r["risk"] == "REVIEW_DYNAMIC_RUNNER"


def test_no_trigger_and_comments_do_not_prove_auto_execution():
    s = """# on: [push]
on:
  workflow_dispatch:
jobs:
  test:
    # runs-on: [self-hosted, ventuno-q]
    runs-on: ubuntu-22.04
"""
    r = summarize_source("notes.yml", s)
    assert r["auto_triggers"] == []
    assert not r["self_hosted_runner_reference"]


def test_local_report_is_read_only_and_never_calls_device(tmp_path):
    directory = tmp_path / "workflows"
    directory.mkdir()
    (directory / "a.yml").write_text(
        "on: [push]\njobs:\n  t:\n    runs-on: [self-hosted, ventuno-q]\n"
    )
    (directory / "b.yaml").write_text(
        "on: [workflow_dispatch]\njobs:\n  t:\n    runs-on: ubuntu-24.04\n"
    )
    before = [x.read_bytes() for x in sorted(directory.iterdir())]
    out = inventory(directory)
    after = [x.read_bytes() for x in sorted(directory.iterdir())]
    assert before == after
    assert out["total_workflows"] == 2
    assert out["auto_self_hosted_leads"] == 1
    assert not out["historical_branches_checked"]
    assert not out["runner_group_admin_settings_verified"]
    assert not out["production_deployment_authorized"]


def test_symlinks_and_invalid_workflow_root_are_rejected(tmp_path):
    original = tmp_path / "original.yml"
    original.write_text("on: [push]\n")
    directory = tmp_path / "workflows"
    directory.mkdir()
    (directory / "external.yml").symlink_to(original)
    with pytest.raises(ValueError):
        inventory(directory)
    with pytest.raises(ValueError):
        inventory(tmp_path / "missing")


def test_repository_current_head_has_workflows_but_no_admin_claim():
    root = Path(__file__).resolve().parents[1]
    report = inventory(root / ".github/workflows")
    assert report["total_workflows"] >= 1
    assert report["status"] == (
        "SOURCE_ONLY_INVENTORY_NOT_ADMIN_SECURITY_ASSERTION"
    )
    assert report["historical_branches_checked"] is False
    assert report["runner_group_admin_settings_verified"] is False
    assert report["physical_ventuno_touched"] is False
