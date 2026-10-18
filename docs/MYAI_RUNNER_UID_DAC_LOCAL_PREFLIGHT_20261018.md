# MyAI runner identity and filesystem preflight — source-only implementation

**Date:** 2026-10-18. **Base:** stacked DRAFT PR #330, `ea6bccffd8a4b3cf51948e3297307c70ea563b64`. **Status:** NOT DEPLOYED / PRODUCTION NO-GO.

## Pass 1: evidence and permission boundaries

The historical self-hosted VENTUNO runner shares the installed MyAI `arduino` trust domain, while DRAFT PR #329 contains a **non-installable** template for an isolated `myai-ci` service. DRAFT PR #330 verified five existing historical branch files with live source references to the production interpreter. GitHub Actions runner registration and runner-group permissions **could not be read through the available GitHub connection**. Nobody has checked a real `myai-ci` OS account or exact live service ACLs on the physical board.

Source file ownership by itself is insufficient: a runner with supplementary `arduino`, `sudo`, `docker`, `audio`, `video`, `render` or other groups could regain device or code access. POSIX DAC can also be bypassed by ACLs, privileges, group inheritance, bind mounts, sudo rules and credentials shared between processes. A systemd unit that declares `User=myai-ci` does not independently prove those boundaries. Correctly blocking an unsafe configuration is more important than guessing it is installed.

## Pass 2: code added in this DRAFT

`scripts/ventuno_runner_uid_acl_preflight.py` is a **standard-library-only** checker with two modes.

- **Default, without arguments:** emits a short, unverified NO-GO JSON report; touches no local systemd, users or filesystem metadata.
- **Optional explicit `--local-readonly`:** reads only two fixed systemd services with a read-only `systemctl show`: the **legacy** `actions.runner.Harrokk-Myai.ventuno-q.service` and proposed `myai-ci-runner-isolated.service` (the latter must carry the strict `myai-ci` hardening policy); enumerates four fixed Unix identity names (`arduino`, proposed `myai-ci`, `myai-runtime`, `myai-updater`) and defined sensitive groups, then performs `lstat` on five fixed directories. It cannot start/stop/restart services, create users, rotate credentials, modify git refs, inspect secrets or dispatch hardware tests. Output contains booleans only, never arbitrary systemd commands, environment variables, usernames in service output, credential values or raw private filesystem paths.

The `parse_systemd_properties` boundary rejects extra/duplicate keys, control characters, invalid UTF-8 and outputs larger than 4096 bytes. A strict source fixture requires:
- an **inactive** legacy runner unit with `UnitFileState=disabled`/`masked`, or a demonstrably absent old unit, **in addition to** the separate new isolated service; a running or enabled legacy unit always blocks the preliminary result;
- hardening flags on the new service including `User=myai-ci`, `Group=myai-ci`, no supplementary groups, `NoNewPrivileges=yes`, `PrivateDevices=yes`, `ProtectHome=yes`, `ProtectSystem=strict`, `UMask=0077` and private runner state;
- four actual distinct Unix UIDs, with CI account in no supplementary/sensitive/shared groups and not root;
- no symlink, missing, world-writable, CI-owned or CI-group-writable installed MyAI directories; separate CI runner state directory exclusively owned by `myai-ci` and mode `0700`.

Only when **both** the old service quarantine and new service configuration agree with the source policy can the script report **preliminary POSIX DAC candidate checks passed**, never true production release. It sets `posix_acl_and_capabilities_verified`, `sudo_and_nested_group_privileges_verified`, `systemd_mount_namespace_and_real_access_verified`, `github_runner_group_and_historical_refs_verified`, `updater_signing_key_acl_verified`, `production_deployment_authorized` and `main_merge_authorized` permanently to `false`. A positive CLI exit code acknowledges only **complete metadata**, not authorization.

The tests use a synthetic, isolated-in-memory fixture and injected read-only executor/user/permission functions. They cover each dangerous service property, missing/overlapping accounts, sensitive and supplementary group exposure, missing/symlinked/misowned/writable directories, duplicate/secret-bearing systemd metadata, fixed command argv/timeouts and default no-probe behavior.

## Physical and GitHub-side checks still required

1. Under an explicitly approved maintenance plan, first restrict the old runner's GitHub runner-group eligibility; otherwise a security push to a historic branch can itself execute under `arduino`.
2. Inspect current, **installed** `systemctl cat/show` configuration, `id`/group membership, `getfacl`, file modes for every ancestor, OS capabilities, mount policy, sudo rules, `/dev` ACL/device node access, existing GitHub credentials and updater signing key ownership. This candidate uses deliberately bounded metadata only and does not replace these tests.
3. Test two actual distinct UIDs in a disposable environment. Verify that the isolated CI UID can neither read signing keys and production memory nor write code, journal, rollback, audio/NPU devices or privileged runner credentials; only safe CI scratch may be mutable.
4. Carefully plan runner re-registration, service migration and rollback before any change to the VENTUNO system. `myai-ci`, `myai-runtime` and `myai-updater` in the script are **future identity proposals**, not a claim that such users exist.
5. Finish independent verifier attestation, SBOM/ABI/licensing and real NPU/audio/eMMC power recovery before any production go/no-go.

**Source tests alone do not close the trust boundary.** No hardware or VENTUNO processes were touched; frozen historical 103-workflow audit evidence was not rewritten, and all changes remain DRAFT.
