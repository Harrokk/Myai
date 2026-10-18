# MyAI – proposed isolated GitHub CI runner (source-only security review)

Date: 2026-10-18. Base: passing DRAFT PR #328, commit `2ab2af27c5193ad4dcd9e17922f4dcda0ab1d4ee`.

**Status: REVIEW ONLY / PRODUCTION NO-GO.** This change creates no OS account, does not install or start services, does not move runner credentials, does not alter GitHub runner-group permissions, and does not touch VENTUNO hardware.

## Pass 1 – current trust boundary

The historical VENTUNO runner service uses the production `arduino` identity and was configured under `/home/arduino/actions-runner`. MyAI's installed code and venv have also been accessible to branch-controlled GitHub workflow checks using the `arduino` interpreter. Branch-specific `on: push` plus an exact `GITHUB_SHA` checkout **does not restrict local OS process permissions**. Even the prior hosted-source workflow changes in DRAFT PR #327–328 do not update existing copies on historical branches and are not a centrally enforced runner-group access policy.

This breaks the intended separation between untrusted CI tests, the MyAI runtime, selfdev staging, code promotion, signing keys, audio/NPU device access and GitHub runner credentials.

## Pass 2 – non-installable candidate and validation

Proposed `deploy/systemd/myai-ci-runner-isolated.service.example` demonstrates a separate, *source-only* GitHub runner account `myai-ci` installed in `/var/lib/myai-ci-runner`, deliberately outside `/home/arduino`. It includes `ProtectHome=yes`, `ProtectSystem=strict`, `StateDirectory=myai-ci-runner`, `NoNewPrivileges=yes`, `PrivateDevices=yes`, `PrivateTmp=yes`, zero ambient/bounding Linux capabilities, `RestrictSUIDSGID=yes`, `UMask=0077`, protection of kernel/tunable/control-group interfaces, `TasksMax=64` and `Restart=no`. There is intentionally **no [Install] section** and the file's `.example` suffix prevents it being a ready-to-enable unit.

The source-only verifier `scripts/ventuno_ci_runner_uid_policy.py` demands exact, unambiguous template directives. Duplicate `User` or `ExecStart`, broad writable paths, unwanted supplementary groups, changed device/privilege protection, implicit activation sections and arbitrary additional keys fail closed. It also performs an advisory inventory of workflow source references to self-hosted runners. This scan is **not a complete YAML/expression semantics review** and does not assert runner policy safety.

Regression tests cover guarded in-repository template inspection, 14 privilege-weakening mutations, seven unexpected/duplicate directives, a tiny synthetic mixed runner inventory, symlink rejection and missing source behavior.

## Separate on-device migration and enforcement gates – NOT executed

1. **Quarantine original runner access first.** Review the repo/org GitHub runner configuration and all historical refs/workflow triggers. Remove unreviewed automatic development-branch access to any runner that can affect the installed MyAI tree. A DRAFT source change alone does *not* close this window. GitHub-side control needs authorized account action, not an invented local workflow flag.
2. **Inventory the installed board without changing it.** Record the actual systemd runner unit, UID/GID/supplementary groups, file ACLs, real paths, environment/secrets, runner updater behavior, enabled services, shared groups and device rules. `stat` mode bits alone are not sufficient if ACLs, capabilities or sudo rules grant more privileges. Verify the current MyAI runtime/updater account layout independently.
3. **Provision a distinct CI account** with no membership in `arduino`, `audio`, `video`, `dialout`, `sudo`, `docker` or other sensitive groups. Create a new GitHub runner registration with fresh scoped credentials, segregated to safe source-only work. The proposed service is a design artifact, not a production installation recipe; first test its systemd compatibility and GitHub auto-update behavior on a disposable device or VM.
4. **Verify no access to production state** under the actual dedicated UID. Explicitly test denied reads/writes for MyAI release, selfdev journal signing keys, rollback, runtime databases, device nodes, systemd services and runner credentials of other instances; verify that safe test workspaces remain usable. Use POSIX DAC, ACL, mount policies, service user and runner-group access controls together.
5. **Separate real hardware jobs.** A source-only runner with `PrivateDevices=yes` must not be used for physical microphone, NPU, BLE or power-loss tests. Those require a separately approved, temporary maintenance path and explicit device-specific authorization.
6. **Recover and roll back without rewriting live code.** Inventory backups before any migration, run a cold restart/reconnect test, verify that old self-hosted refs can no longer start against the production UID, and obtain separate operator approval before removing the legacy registration. Do not regenerate signing keys or trust old verification JSON as proof of execution.

## What this PR can and cannot prove

The CI suite can prove only that the *staged source template* and its pure validator satisfy the specified policy. It cannot prove that a VENTUNO systemd unit is installed, any accounts exist, that GitHub runner groups enforce branch isolation, that ACL/capability/device permissions match the proposal, or that the live runner is reachable. This does not authenticate `verification.json` against a same-UID writer, solve production updater separation, certify SBOM/licensing/native ABI or complete physical NPU/audio/eMMC recovery.

The frozen 103-workflow historical source evidence remains unchanged and fail-closed. **No main merge, live promotion, hardware run, service restart or production release is authorized.**
