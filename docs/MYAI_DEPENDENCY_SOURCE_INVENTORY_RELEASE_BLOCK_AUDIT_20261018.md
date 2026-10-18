# MyAI – broad source-level dependency review (2026-10-18)

Base: DRAFT PR #323, commit `e18126dbab6b70c0e1cca6d1daf37a3a648f2c16`. This is a source-only review, not a claim of installed dependency attestation or a release.

## Pass 1: scope and independent inventory

The seven directly declared Python requirement manifests were reviewed independently of the script's own success flag:

| File | Direct requirements | Unlocked version intervals |
| --- | ---: | ---: |
| requirements.txt | 3 | 3 |
| requirements-ventuno.txt | 1 | 0 |
| requirements-voice.txt | 5 | 5 |
| requirements-bluetooth.txt | 1 | 0 |
| requirements-camera.txt | 1 | 1 |
| requirements-excel.txt | 1 | 1 |
| requirements-gps.txt | 1 | 1 |
| **Total** | **13** | **11** |

The only exact direct pins in those seven files are `arduino-router-bridge==0.5.0` and `bleak==3.0.2`; none of the 13 manifest lines contains an artifact hash.

The separate CPython 3.12/aarch64 voice lock contains **28 distinct wheel names and SHA-256 rows**. Independent line-by-line comparisons found **28 matching textual pins and no mismatch** between `config/voice_arm64_cp312_wheels.lock.json` and `requirements-voice-arm64-hashed.lock`. The JSON flag `complete_dependency_closure: true` is **self-declared**; matching two files does not prove package metadata closure, license suitability, PyPI artifact provenance or safe installed binaries. The wheel filenames include native packages, so a compatible filename does not prove a usable native ABI or working QAIRT/NPU/audio stack.

The existing `scripts/ventuno_dependency_source_review.py` validates manifest grammar and minimum `requests` / `urllib3` floors but explicitly records that it did **not** query live advisories, audit installed versions, review licenses, attest native ABI or create a complete production dependency lock. Existing code reads installed version metadata in a separate read-only probe; no physical installed inventory was performed during this review.

GitHub-hosted ARM64 CI installs test dependencies from unconstrained transitive resolution and root version intervals. Success tests the resolver's candidate at run time, **not** a reproducible full production installation. Historical CI workflows and self-hosted trigger inventory also remain partially unreviewed (172 workflow source files present).

## Pass 2: safety decision and bounded change

**Confirmed semantic defect:** the successful source-only dependency checker reported status `source-dependency-policy-checked-release-unlocked` while the same JSON explicitly set `production_install_authorized: false` and `production_dependency_lock_complete: false`. Such contradictory machine-readable text is unsafe for an external gate that may parse the status string.

Change it to `source-dependency-policy-checked-production-blocked`, preserving existing source consistency flags and exit status for callers. A regression test requires this exact blocked-production label and the unchanged false release flags.

## What must be completed before closing the *production* dependency gate

1. Resolve and pin direct **and transitive** dependencies for all enabled profiles on the exact CPython 3.12/aarch64 target, with hashes for every selected wheel. Validate the graph against wheel METADATA, not a JSON declaration alone. Pip's `--require-hashes` mode requires complete pinned and hashed transitive requirements.
2. Independently verify wheel digests and trusted origins (and native package compatibility), identify third-party upstream artifacts, and retain evidence of acquisition and verification.
3. Generate SBOM(s), inventory licenses and license obligations, scan vulnerabilities with an explicitly dated advisory snapshot, and review OS/native/Qualcomm SDK/firmware dependencies. No vulnerability-free or license-approved conclusion is made here.
4. Compare a read-only VENTUNO installed inventory with reviewed resolutions, after OS/UID boundaries and native ABI checks have been authorized. Separate test venvs must not change active production.
5. Finish inventory of all workflow triggers, package installation commands, service UIDs, privilege boundaries and self-hosted runner exposure. Existing historical manual-workflow source-identity authorization remains blocked.

## Verdict

**Source-level manifest/lock consistency review: completed for the files listed above. Production dependency/supply-chain approval: BLOCKED.** No `main` merge, dependency installation, live selfdev promotion, physical NPU/audio checks or deployment is authorized by this DRAFT.
