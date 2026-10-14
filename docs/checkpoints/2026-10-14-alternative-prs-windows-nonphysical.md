# MyAI checkpoint — alternatives reconciled, Windows fallback and nonphysical release boundary

**Date:** 2026-10-14
**Working draft branch:** `dev/compat-guardrail-reconciliation-20261014`
**Draft PR:** [#140](https://github.com/Harrokk/Myai/pull/140), stacked on #139.
**Current baseline:** `dev/combined-static-ci-audit-20261014`, with source-only static audit on each `dev/**` regression run.
**Deployment:** none. Production MyAI/GenieX on VENTUNO and Windows Arduino App Lab remain untouched; auto-promotion remains disabled.

## Older overlapping PR branches resolved at code-review level

- [#117](https://github.com/Harrokk/Myai/pull/117): atomic `save_if_new` and unpredictable workspace temp files. Current main draft path includes `BEGIN IMMEDIATE` in `core/memory.py`, `tempfile.mkstemp` and fsync in workspace writing, plus further symlink/fault-injection tests. **Covered by #119, #120, #122 and later.**
- [#118](https://github.com/Harrokk/Myai/pull/118): atomic journal write and verification of rollback backup hashes. Current path includes crash state `prepared` / `rollback_prepared`, `_write_journal` with HMAC, fsync, backup preflight, no-follow inode snapshot, manual recovery and global mutation lock. **Superseded by #123–#132 and later.**
- [#121](https://github.com/Harrokk/Myai/pull/121): `enqueue_review` transaction serialized using `BEGIN IMMEDIATE`. Current path includes that transaction, fail-closed conflict validation and conflict-union/escalation tests. **Covered by #124 and later.**
- These three older draft PRs remain open as **alternative overlapping branches**. Do **not** cherry-pick or merge them directly into #140. This review establishes functional overlap, not a bit-for-bit independent equivalence proof or a final merge decision.

## New tests and Windows CI

- Four new cases force `_ANCHORED=False` in JSONL utility to exercise the fallback and guard against regressions: Unicode append/rotation, symlink+hardlink refusal, unsafe rotated entry denial and required-durable fsync failure.
- A separate [hosted Windows-only JSONL workflow](../../.github/workflows/windows-jsonl-fallback.yml) fetches exact commit in a disposable GitHub-hosted Windows machine, installs pinned pytest and executes **six selected tests**, not the whole MyAI test suite.
- ARM64 VENTUNO isolated CI for code commit [run 38554228211](https://github.com/Harrokk/Myai/actions/runs/38554228211): **1618 passed, 6 skipped**.
- Final pre-document workflow commit ARM64 [run 38554417399](https://github.com/Harrokk/Myai/actions/runs/38554417399): **1618 passed, 6 skipped, source-only static audit PASS**.
- Actual hosted Windows CI [run 38554417438](https://github.com/Harrokk/Myai/actions/runs/38554417438): **6 passed, 25 deselected**. No local Windows/Arduino App Lab access; no USB, camera, mic or live service operation.
- Six ARM64-skipped optional ONNX/NumPy cases previously checked on hosted x86 as part of **22 passed**: https://github.com/Harrokk/Myai/actions/runs/38520039444.

## Current nonphysical release boundary and next decisions

- Dedicated architecture proposal: [`docs/security/selfdev-privilege-isolation-proposal.md`](../security/selfdev-privilege-isolation-proposal.md).
- HMAC signing key and updates remain in the same operating-system trust boundary in the current implementation. A process with the same UID can modify source/journal/key; same-UID adversarial race prevention is **not proven** by flock+SHA checks.
- Windows source-only fallback has a six-test native Windows spot check, **not** an end-to-end Windows deployment or Arduino App Lab IP troubleshooting.
- Physical power-cut verification and any service/user/OS migration still need a separately authorized deployment/test plan.
- [#110](https://github.com/Harrokk/Myai/pull/110) remains open/draft. No new issue comments were visible at check time. GitHub Support cached-object removal remains unconfirmed; do not merge main or claim purge complete.
- All source patches #112–#140 are draft; no main merge or live VENTUNO changes.
- Static audit's lone manual-review `exec` at `tests/test_ventuno_whisper_base_swedish_comparison.py:202` uses a project-defined metrics helper in a test. The flag remains documented rather than automatically suppressed.

## Finish criteria for repository-only batch

- Older conflicting PRs compared without unsafe merges: done.
- Linux multi-process audit, inode-swaps, permissions and static audit: tested in #136–#139.
- Selected native Windows fallback nonphysical smoke: tested in #140.
- Multi-identity security boundary: **design documented, not implemented or validated as installed**.
- Hardware and GitHub Support-only tasks: remain external blockers; do not silently perform or claim completion.
