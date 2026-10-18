# MyAI: hosted isolation for SSRF and remote source-closeout workflows (2026-10-18)

Source-only security audit following DRAFT PR #327 (`07c94e4066a969913b34fbd909d49b3491fdb8b3`).

## Confirmed issue

Two push-triggered workflows were running untrusted repository Python under the VENTUNO self-hosted `arduino` process identity:

- `.github/workflows/ventuno-web-socket-ssrf-source-audit.yml` (synthetic transport / DNS socket validation)
- `.github/workflows/ventuno-final-source-revision-closeout.yml` (static source revision closeout, which intentionally **cannot authorize** production)

Both invoked tests using `/home/arduino/MyAI/.venv/bin/python`, even though neither needs real hardware. Scratch checkouts and read-only GitHub tokens do not make that safe.

## Change and source-only regressions

- Run only on `ubuntu-24.04-arm` with `runner.environment == github-hosted` and real aarch64 checked before Git checkout.
- Preserve narrow branch push triggers, `permissions: contents: read` and exact SHA checkout.
- Create a disposable, binary-only Python test environment under `$RUNNER_TEMP` (pinned pytest/cryptography plus root requirements).
- Execute every audit module and pytest via that isolated interpreter instead of the installed VENTUNO Python; remove the hosted venv and isolated checkout after use.
- Add tests covering host guard, exact commit, read-only token, no production paths/services, binary-only venv and cleanup. Frozen source identity snapshot untouched because these two workflows were not among its 103 historically inventoried files.

## Boundaries

This is a change to a **DRAFT branch only**. Older Git refs can still contain push-triggered self-hosted jobs and physical runner-group access remains unchanged. Other source-only workflows, hardware-dependent consent policy, process UID isolation and verification provenance remain blocked. Historical 103-file baseline remains fail-closed. No `main` merge, runner dispatch, service control, hardware operation, dependency installation on VENTUNO or live selfdev promotion.

Require exact-HEAD hosted ARM64 full suite. Supply-chain/SBOM/licensing/native ABI and actual physical NPU/audio/power-failure tests remain out of scope.
