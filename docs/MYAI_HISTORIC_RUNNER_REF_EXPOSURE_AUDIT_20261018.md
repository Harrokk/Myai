# MyAI – historic runner Git refs: production access still exposed

**Date:** 2026-10-18 · **Source base:** DRAFT PR #329 `9a14e96e961da8dbfb25ac1fb48fb4b36d14b3b1`. **Status:** SOURCE REVIEW ONLY / PRODUCTION NO-GO.

## First pass – five confirmed historic branch files

We queried the **existing GitHub branch refs**, not merely the newly staged DRAFT candidate. On 2026-10-18 each of these still had `runs-on: [self-hosted, Linux, ARM64, ventuno-q]` **and** a reference to the installed `/home/arduino/MyAI/.venv/bin/python`:

| Historical branch | Workflow | Git blob SHA |
|---|---|---|
| `dev/manual-audit-error-redaction-20261016` | `ventuno-exception-privacy-manual-audit.yml` | `c743b18a3e1c6f5e4cfcb556f5797dd63c9bd21f` |
| `dev/manual-audit-actions-sha-pinning-20261017` | `ventuno-external-actions-pin-audit.yml` | `c32d32d4ad3815f918922de13e5e7e1ff43c8e1e` |
| `dev/manual-audit-historical-device-gates-20261016` | `ventuno-manual-audit-dependency-and-consent.yml` | `548209900a36b6aa756d626e667930d882aa06a3` |
| `dev/manual-full-files-and-dns-ssrf-20261017` | `ventuno-web-socket-ssrf-source-audit.yml` | `5bcb4e24fd0880ec9844488e88a7e13cc9f72ba7` |
| `dev/ventuno-audit-source-closeout-20261016` | `ventuno-final-source-revision-closeout.yml` | `9f0ef1d59364c3a04f0b6fdcef874bf87820122b` |

This **confirms source-code exposure** and triggers in these refs, but does **not** prove those workflows ran, the runner is online, or GitHub currently authorizes the branches to use its runner group. The GitHub connector permitted public branch source reads but did **not** expose administrative runner inventory or repository Actions permissions endpoints. Accordingly those states are **unverified**, not assumed safe. The first page of branch enumeration contained 100 branches; the above five examples are **not an exhaustive branch or trigger count**.

## Second pass – source-only safety gate

`config/ventuno_historical_runner_ref_exposure_20261018.json` preserves the five observed `branch + workflow + Git blob` identities as a **dated, unsigned observation**. It deliberately asserts `production_runner_access_policy_verified: false`, `historical_branch_current_execution_state_verified: false`, and `production_release_authorized: false`.

`scripts/ventuno_runner_ref_exposure.py` validates that observation against the exact five expected records. It also inventories the candidate checkout's workflow files and conservatively categorizes runner selectors:

- Known, literal hosted labels (such as `ubuntu-24.04-arm`) are source hints only.
- Literal `self-hosted`, `ventuno-q`, arrays, variable/JSON expressions, group mappings, multiline or empty selectors are all **possible self-hosted or unknown exposure**, not automatic clearance.
- `push`, `workflow_run`, `workflow_call`, `schedule`, `repository_dispatch` and ambiguous events remain possible automatic/indirect exposure. `workflow_dispatch` alone is merely a manual-only **source hint**, never approval.
- A job calling a reusable workflow without an in-file `runs-on` is opaque and flagged. This script is **not** a full GitHub Actions YAML/expression/called-action evaluator.
- Invalid manifests, symlinks, unexpectedly large or malformed source files, and missing inventory fail closed.
- The normal CLI prints an auditable NO-GO source report and exits 0 only when its **source inventory is complete**. `--strict-production` **always returns non-zero**, because offline source inspection cannot attest GitHub runner-group permissions or legacy-runner de-registration. `runner_exposure_closed` and `production_deployment_authorized` are always false.

Regression tests ensure bad historical-evidence edits, dynamic selectors, indirect triggers and symlink replacement never turn an unsafe source scan into release approval.

## Why we did NOT modify the five historic branches

A normal `push` on a historical branch can itself trigger its self-hosted VENTUNO job. Even a well-intended workflow-only security commit could therefore execute on the production `arduino` account before being blocked. This review only creates a **new stacked DRAFT branch** and never writes to the historical refs or dispatches a workflow on a VENTUNO runner.

## Required future containment (separate authorized administration)

1. Restrict, temporarily disable, or remove production-runner eligibility at GitHub repository/organization runner-group registration level before modifying unsafe historic refs. Verify using the relevant authorized administrator UI/API and audit logs.
2. Capture a fresh exhaustive `refs/heads/*` workflow source inventory, matching each trigger and job, including reusable workflow and dynamic runner label semantics. Compare GitHub-side run history and group access. **Do not** assume a historical branch is inert because the new candidate branch is safe.
3. Migrate source-only work to disposable hosted runners; reserve device-specific tests for a separate explicit, least-privilege hardware maintenance process. Independently plan `myai-ci` user, runner credential scope and source/device/secret ACL checks.
4. Physically validate two Unix identities, install paths, systemd and GitHub runner-group constraints before on-board changes. Verify no shared writable production source, journal integrity key, memory, rollback or signing credentials.
5. Require separate physical NPU/audio/power-loss and dependency/SBOM/license/ABI clearance. No source CI success authorizes `main` merge or live selfdev promotion.

The historical frozen 103-workflow manifest is preserved unchanged and remains fail-closed. **No VENTUNO modification, runner dispatch, merge, release or production authorization.**
