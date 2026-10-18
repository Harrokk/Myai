# MyAI: VENTUNO self-hosted workflow privilege inventory (2026-10-18)

**Base:** source-only DRAFT PR #324, commit `b7cf559ecefa993b4a90b5a885ca498079426a2b`. No on-device runner action, install, merge or workflow_dispatch was invoked.

## Pass 1 – source inventory

Enumerated all **172 workflow files** in the exact Git tree and inspected their runner declarations. Approximately **129** include `runs-on: [self-hosted, Linux, ARM64, ventuno-q]` on this development chain (including workflows that also have GitHub-hosted jobs). Many have branch-specific `on: push` triggers. This is a static source count, not proof that any given historical branch's workflow has executed or that a runner is currently online.

Confirmed examples of a **push-triggered, branch-controlled checkout and execution under the production arduino UID**:

- `.github/workflows/ventuno-exception-privacy-manual-audit.yml` – `push` on `dev/manual-audit-error-redaction-20261016`; uses `[self-hosted, Linux, ARM64, ventuno-q]`, checks `id -un == arduino`, executes scripts from the fetched branch via `/usr/bin/python3` and test code using `/home/arduino/MyAI/.venv/bin/python`.
- `.github/workflows/ventuno-external-actions-pin-audit.yml` – `push` on `dev/manual-audit-actions-sha-pinning-20261017`; uses the same production UID and installed Python venv for checkout-controlled pytest code.
- `.github/workflows/ventuno-manual-audit-dependency-and-consent.yml` – `push` on `dev/manual-audit-historical-device-gates-20261016`; runs fetched source audits and pytest from the active VENTUNO interpreter.
- `.github/workflows/ventuno-voice-proc-audit.yml` – separate hosted stage plus a physical `ventuno-source-only` job using the self-hosted runner under `on: push` / `workflow_dispatch`.

These are **source-only tests by declared intent**, but temporary checkouts are not operating-system sandboxes; a malicious or buggy test can execute with its service user's ordinary filesystem rights. `permissions: contents: read` limits the GitHub token, not the Linux UID. `timeout-minutes` limits job duration, not filesystem rights. Exact-SHA fetching improves source identity but not runtime isolation.

## Pass 2 – containment decision

**Confirmed release blocker:** Automatic development-branch jobs should not run untrusted source under an account that also owns active MyAI code, runtime data, credentials, devices or services.

Classify every self-hosted workflow into (A) pure static/source-only, to migrate to disposable hosted runner; (B) physically necessary read-only probe, to keep on device only with an independent consent gate and a minimal dedicated UID; and (C) state-mutating hardware probe, to require explicit locally authorized maintenance and recovery plans. Apply source identity, exact runner/service UID/permissions, triggers, script content, filesystem access, installed-venv access, environment and cleanup assessment **per job**, not only per filename.

Restrict runner-group and OS permissions before resuming production self-hosted tests. Branch-specific push filtering is *not* an independent privilege boundary. Do not auto-edit all 129 jobs to hosted: genuine physical probes would become meaningless or could fail in unsafe ways. Preserve the immutable historical 103-workflow source baseline and its existing drift blocker; source revisions require a new, separately reviewed authorization.

## NO-GO and next work

This is a first complete **runner-target inventory**, not a full semantic review of every step in all 172 workflow files. Individual trigger/UID and command reviews, physical board runner service policy, separate verification UID, source-verification provenance, full dependency/SBOM/license/native ABI and real NPU/audio/power-loss checks remain open. The DRAFT change documents a confirmed risk but does **not** mitigate the older executable workflows in existing Git refs.

No main merge, no runner dispatch, no live MyAI promotion, no hardware mutation or installation was performed.
