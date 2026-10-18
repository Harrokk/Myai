# MyAI security review: isolate three nonphysical GitHub audits (2026-10-18)

**Base:** green DRAFT PR #326 at `cd67c1f9e0d50c20dba3dfd9d41850b303f17d13`. GitHub source-only change. No active VENTUNO instance, runner service, production venv, device, microphone, NPU or selfdev promotion was used.

## Pass 1: existing production-UID boundary violation

These three *nonphysical* audit workflows run a branch-controlled checkout on `runs-on: [self-hosted, Linux, ARM64, ventuno-q]`:

1. `.github/workflows/ventuno-exception-privacy-manual-audit.yml`
2. `.github/workflows/ventuno-external-actions-pin-audit.yml`
3. `.github/workflows/ventuno-manual-audit-dependency-and-consent.yml`

Each has a branch-specific push trigger. Each uses the VENTUNO `arduino` account, checks out an exact commit, then executes project scripts and tests. Each invokes `/home/arduino/MyAI/.venv/bin/python`, the interpreter in the **installed production environment**. Source-only intent, read-only GitHub token and an exact commit do not isolate executing code from OS permissions, secrets or installed packages. No observed breach or installed-code mutation is claimed.

## Pass 2: bounded remediation

The three workflows now:

- run exclusively on disposable `ubuntu-24.04-arm` and fail *before checkout* unless `runner.environment == github-hosted` and `uname -m == aarch64`;
- retain the original branch-scoped push trigger, `permissions: contents: read`, exact `GITHUB_SHA` checkout validation and private scratch-directory lifecycle;
- use a fresh `$RUNNER_TEMP` Python venv, with binary-only dependencies installed from `requirements.txt` plus pinned test essentials;
- execute source analyzers and tests through **that hosted venv**, never the installed VENTUNO Python or `systemctl`;
- remove the isolated venv and scratch workspace in the cleanup step.

New tests require the hosted runner, environment guard before fetching untrusted source, exact checkout, disposable interpreter, preserved read-only token, absence of installed-machine paths and explicit removal. The untouched historical `config/ventuno_manual_workflow_git_oids_20261016.json` is not rewritten to misrepresent previous approval.

## Important limitations / release NO-GO

- This changes **three source files on the new DRAFT branch**, not the already existing copies in their historical trigger branches, `main`, or GitHub's self-hosted runner-group policies. An old branch may retain its previously dangerous workflow and continue to run if runner access remains enabled. To close the entire privilege boundary, constrain/disable the production runner's automatic access and migrate each relevant historical branch.
- Other self-hosted GitHub Actions workflows (roughly 129 of 172 files in the prior inventory) still require per-job trigger, command, UID, filesystem and device review. Physical read-only and state-changing diagnostics must not be blindly migrated to hosted VMs.
- Disposable hosted runners do not establish cryptographic provenance of `verification.json` and do not solve same-UID filesystem forgery on the board. Independent production user separation and trusted verification evidence are separate release gates.
- The immutable historical 103-file source identity baseline remains fail-closed; no approval reset, merge, deployment, installation or live promotion is performed.
- Full supply-chain/SBOM/licenses/ABI and real NPU/audio/power-loss recovery remain open.

**Exit criterion:** exact final HEAD hosted ARM64 source-only CI must pass; a green build validates this DRAFT source tree only and is not production authorization.
