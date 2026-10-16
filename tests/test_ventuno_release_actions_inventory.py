"""Release Actions scanner cannot execute hardware, tests conservative metadata."""
from pathlib import Path

from scripts.ventuno_release_actions_inventory import (
    inspect, classify_workflow,
)


def test_simple_main_push_hardware_action_denied():
    src = """on:
  push:
    branches: [main]
jobs:
  physical:
    runs-on: [self-hosted, Linux, ARM64, ventuno-q]
    steps:
      - run: arecord -d 3 /tmp/test.wav
"""
    meta = classify_workflow(src)
    assert meta["unreviewed_main_push_physical"] is True


def test_safe_main_only_static_archived_workflow_not_executable():
    src = """on:
  workflow_dispatch:
jobs:
  noop:
    if: false
    runs-on: ubuntu-24.04
    steps:
      - run: echo 'inert'
"""
    assert classify_workflow(src)["requires_fresh_operator_gate_if_dispatched"] is False


def test_explicit_manual_htp_still_requires_operator():
    src = """on:
  workflow_dispatch:
jobs:
  htp:
    runs-on: [self-hosted, Linux, ARM64, ventuno-q]
    steps:
      - run: qnn-net-run --backend libQnnHtp.so
"""
    meta = classify_workflow(src)
    assert meta["requires_fresh_operator_gate_if_dispatched"] is True
    assert meta["unreviewed_main_push_physical"] is False


def test_full_repo_inventory_does_not_claim_user_consent():
    report = inspect()
    assert report["files_scanned"] >= 148
    assert report["physical_test_authorized"] is False
    assert report["manual_workflow_review_complete"] is False
    assert report["release_deployed"] is False


def test_empty_tree_fails_closed(tmp_path):
    assert inspect(tmp_path)["status"] == "blocked-workflow-inventory-missing"
