# MyAI – Real Bubblewrap executed by a separate verifier UID (hosted integration)

**2026-10-18 · Based on DRAFT PR #337, commit 1e0f0871d439b4b343495994d30e68ea00e2f423. Status: TEST-ONLY / PRODUCTION NO-GO.**

## Pass 1: missing security boundary

PR #336 demonstrated kernel SO_PEERCRED, 4 numeric Linux UIDs, Ed25519 and an updater-owned SQLite nonce ledger inside disposable Docker, but used a **synthetic** Bubblewrap field. PR #337 then performed **real Bubblewrap** and checked a distinct network namespace and read-only fixture on a GitHub-hosted Ubuntu runner, but the successful signing was still performed by the same ordinary hosted test identity, not the separated verifier UID. Neither demonstrated both guarantees simultaneously.

The live VENTUNO self-hosted runner uses the historical arduino trust domain. Five verified old-branch source workflow references still target it. The actual GitHub runner group access, Linux installed user/ACL restrictions and physical device configuration have NOT been verified, let alone migrated.

## Pass 2: combined independent execution test

The new **test-only** script scripts/test_hosted_four_uid_real_bwrap.py reuses existing, independently tested boundaries without changing production code:

- Host test runner checks Linux x86, explicitly GitHub-hosted source-only workflow and a disposable privileged root test orchestrator. It runs **only on a GitHub-hosted Ubuntu VM** and refuses Docker, VENTUNO and implicit execution. The workflow uses an exact-SHA read-only source checkout.
- Test root creates four simulated but **real** numeric Unix UIDs (updater 23001, runtime 23002, CI 23003, verifier 23004) by forking and permanently clearing supplementary groups, then setting GID/UID. No user accounts or systemd units are installed. Root controls an isolated temporary directory, and updater/verifier own separate mode 0700 subdirectories.
- The verifier **first drops to UID 23004** and only then generates an ephemeral Ed25519 private key in memory. The private key is never serialized. All other identities are blocked from reading verifier-owned test fixture. A test-only public-key pipe is supplied by the root orchestrator; this is **not a production key-provisioning protocol**.
- The AF_UNIX socket is intentionally mode 0666 so peer authentication is tested directly. The verifier checks the kernel's SO_PEERCRED for updater UID 23001. CI/runtime connections are rejected and a forged updater-sent passed=True field is rejected. A client cannot choose a test command, data path, source bytes or success flag.
- Upon valid updater inspection-only nonce request, the **verifier process under UID 23004 itself** invokes core/selfdev_bwrap_observation.observe on its own trusted fixed synthetic fixture. This launches real /usr/bin/bwrap with unshared namespaces, private proc/dev/tmp, a read-only system and fixture filesystem, bounded subprocess output and timeout. It refuses if the network namespace does not differ from the verifier's, writes to fixture succeed, checksum differs or the subprocess fails. **Only after a passing real sandbox execution** does the verifier sign the canonical Ed25519 observation.
- The separate updater UID reads a test-trusted pinned public key, verifies that signature against expected session, manifest, test-plan and evidence digests, and atomically consumes the updater-issued nonce via SQLite; it rejects replay after closing and reopening its own SQLite database.
- Separate mock-only hosted ARM64 pytest covers mutated observation status, missing Bubblewrap, wrong hash, wrong plan, wrong network isolation, fake signatures in client requests, gate flags, chronological sign-after-verification order and refusal to grant production deployment.

## Controlled environment

.github/workflows/disposable-four-uid-real-bwrap.yml selects the disposable GitHub-hosted ubuntu-22.04 x86 VM and verifies runner.environment=github-hosted, source exact GITHUB_SHA, and a nonroot initiating job. The workflow installs Bubblewrap and a temporary Python cryptography venv on **that VM only**, then uses sudo for the test-root identity in a process that promptly drops to four synthetic UIDs. No host AppArmor/userns relaxation, VENTUNO runner, hardware, production files, real signing keys, selfdev promotion or main merge. If Bubblewrap cannot create the needed namespaces as UID 23004, the integration must **fail closed**.

## Explicit limitations / mandatory blockers

1. The test verifies only **a fixed, synthetic Python AST fixture**, not all MyAI code/tests or the QNN/NPU stack. Trusted test plans, third-party dependencies, SBOM/ABI, release provenance and device capabilities remain unverified.
2. Test-only in-memory Ed25519 keys and root-pipe public-key distribution do **not** establish a production signing identity, persistent secret provisioning, rotation or revocation. A real service must manage kernel credentials and approved key distribution.
3. SO_PEERCRED proves a UID on this one test machine. It does **not** prove physical VENTUNO OS users, ACLs, sudo groups, namespaces, launch/IPC lifetime, secure uptime, systemd or GitHub runner eligibility.
4. SQLite reopen and replay denial do **not** prove crash-safety, eMMC power-loss survival, anti-rollback or independently protected production ledger state.
5. No production promotion code accepts these test-only signatures or IPC results. There is no human-approval integration or production key-provisioning service. Existing selfdev promotion remains disabled / NO-GO.
6. Historic auto-triggered GitHub workflows and live runner privilege access still require authorized GitHub-side isolation before editing those branches. Physical audio/NPU/USB/BLE and power-recovery tests remain.

**Release status: DRAFT/NO-GO.** Full hosted ARM64 suite and the *same exact HEAD* genuine four-UID Bubblewrap test must succeed to complete this source-only milestone. Even green CI cannot approve physical changes.
