# Disposable three-UID CI/runtime/updater boundary test

**Date:** 2026-10-18. **Base:** DRAFT PR #331, commit dd10d09e594b4e121bc1aa7f1bf0a0114cc8ef88.

**Status: OFF-DEVICE DAC INTEGRATION TEST ONLY — PRODUCTION NO-GO.** No VENTUNO service, account, secret, workspace, code, GitHub runner registration, audio/NPU or physical hardware was touched.

## Pass 1 — what was actually missing

The earlier isolated-UID test (scripts/test_disposable_updater_uid_boundary.py) exercised **two** numeric UIDs: runtime 23002 and privileged updater 23001. DRAFT PR #329 proposed a **third** source-only CI runner (myai-ci), and PR #331 added a mock-only local UID/group/systemd/DAC preflight. A service template and mocked properties do not prove the Linux kernel would deny the **CI** identity attempts to read runtime memory, verifier evidence and signing keys or modify published code, audit and rollback.

The active VENTUNO self-hosted runner's original arduino identity, five confirmed old-branch self-hosted workflow source references and unverified GitHub runner-group policies remain separate blockers. No physical-board test is possible from the hosted environment and no old branch was modified.

## Pass 2 — actual disposable Linux UID checks

scripts/test_disposable_ci_uid_boundary.py runs **only** inside a Docker container in the new .github/workflows/disposable-three-uid-ci-boundary.yml source-only branch push job.

The job enforces runner.environment == github-hosted, requires x86_64 and a checked-out exact GITHUB_SHA. It uses one pinned python:3.12-slim-bookworm image digest (sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258) without treating that digest as independent publisher provenance. Docker uses --network none, --read-only, restricted PIDs/memory/CPU, --cap-drop ALL plus only CHOWN, FOWNER, SETUID, SETGID, no-new-privileges, a volatile /tmp, and **one read-only mounted script**. No repository checkout, Docker socket, actual MyAI codebase, host secret or VENTUNO device is mounted into the container. The GitHub-hosted runner pulls the image before starting the networkless container.

The guarded script explicitly refuses to run unless root **inside Docker**, /.dockerenv and MYAI_DISPOSABLE_UID_TEST=yes exist. It creates only **fake** files under a private temporary root. It forks children, clears all supplementary groups, calls setgid and setuid to get three real numeric Linux UIDs:

| Identity | UID | Intended POSIX DAC permissions tested |
|---|---:|---|
| Source-only CI | 23003 | Reads public code and writes CI-owned scratch; cannot read/write runtime memory, verification record, signing key, updater audit, staged files, rollback or published source |
| Runtime | 23002 | Reads published code and accesses its own fake memory.db; cannot read signing key, forge verification, modify code/staging or read CI-only runner token |
| Updater | 23001 | Reads fake journal key and verification, updates updater-owned staging/release, backup and audit; cannot read CI token or runtime memory |

**19 denied cross-identity operations** are asserted as real kernel PermissionError failures: 11 from CI, 5 from runtime and 3 from updater. Allowed operations are also asserted, so indiscriminately denying every operation cannot produce a green test. Only dummy strings are used as the key, token and memory bytes. The code tests **filesystem access**, not the unpredictability of a token or signing key, nor an actual verifier signature.

tests/test_disposable_ci_uid_boundary_source.py is a separate **no-root/no-fork** regression suite for the Docker-only guard, runner selection, exact SHA, mounted file scope, no network or privileges, negative access assertions and permanent release NO-GO flags. Importing the module does not perform chown or alter users.

## Verification and limits

The branch-scoped GitHub-hosted Docker workflow proves numeric POSIX DAC behavior **only inside that ephemeral container**. The normal hosted ARM64 Python test suite separately checks the new source files. The prior two-UID demonstration, new three-UID demonstration and unit tests do not establish:

- installed VENTUNO getfacl/POSIX ACLs, group memberships, Linux capabilities, sudo or mount namespaces;
- live service startup, runner credentials, online state, access restrictions in GitHub runner groups or old branch availability;
- whether the runtime and updater actually use distinct production UIDs, secure IPC, independently protected verification evidence or a protected signing key;
- physical audio, NPU, camera, Bluetooth, eMMC power interruption/recovery, release rollback or SBOM/native package assurance;
- security/provenance of the pinned third-party container image beyond content-addressed selection.

No workflow was dispatched to a VENTUNO runner; no hardware test, systemd install, service restart or merge to main was performed. **Production deployment, real runner privilege separation and automatic selfdev promotion remain forbidden.**

## Required follow-on gates

1. Authorized GitHub administrator restricts unsafe original runner eligibility *before* touching historic auto-triggered branches and verifies runner-group configuration.
2. Inspect actual installed Linux service users, groups, capabilities and ACLs under an approved read-only physical preflight; reconcile with PR #331 local gate.
3. Implement a proper updater-owned verification identity and trusted provenance/IPC before promoting any generated code. Extend off-device abuse and recovery tests first.
4. Explicit maintenance approval and real VENTUNO fault tests after safety review. Keep the old historical 103-file source manifest immutable and fail-closed.

**Exit criteria for this DRAFT only:** both exact-HEAD GitHub-hosted Docker boundary integration and full GitHub-hosted ARM64 source/tests must pass. Neither is release authorization.
