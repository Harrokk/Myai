# Expired audio-consent workflow quarantine — 2026-11-04

Stacks as an unmerged DRAFT on PR #396 at commit `80affd877844bc95b9d53e03f2bc98397a16fb31`. This is a **source-only** safety change. No self-hosted runner, microphone or VENTUNO service is invoked by this PR.

## Findings
Three additional historical push-triggered self-hosted VENTUNO audio workflows from October 22–23 still had a GitHub job guard based on `github.run_attempt == 1` and an **old literal commit-message match** (sometimes also an old `github.event.before` check). A commit message is not durable or fresh authorization to record a person, and an old consent must not become valid when a branch changes again.

Workflows quarantined **in this DRAFT tree only**:
- `.github/workflows/ventuno-one-consented-voice-smoke-20261022.yml`
- `.github/workflows/ventuno-consented-acoustic-metadata-smoke-20261023.yml`
- `.github/workflows/ventuno-consented-cue-smoke-20261023.yml`

Their sole `dialogue` device jobs now contain `if: false`; any future audio request must use a separate, bounded, explicitly approved workflow. The prephysical source gate now requires **six** historical audio jobs to remain inert (the three earlier October 12 workflows plus these three), and regression tests cover all six reactivation attempts and missing/symlinked guard failures.

## Important limits
GitHub Actions workflows are executed from their own ref and event. **Adding these disabled versions to a DRAFT branch does not disable copies of those workflow files on pre-existing historical branches or the default branch.** The code must be deliberately propagated by a separately reviewed change before it can protect other refs; no merge performed here.

This does NOT use the user's current 5-second recording + playback consent to authorize the old STT/GenieX dialogue jobs. A recorder plus direct playback is a different scope. Prior GitHub tooling prevented creating a new direct physical audio job; do not bypass that restriction by invoking a broader legacy audio workflow. Current production risk-tier voice stays OFF, critical commands denied.

## Validation
Require the exact-HEAD hosted ARM64 suite and source-only safety gate to pass. Check in particular that six historical audio jobs are inert, that replaying their old literal commit messages cannot affect the new DRAFT source, and that no VENTUNO runner job was triggered.
