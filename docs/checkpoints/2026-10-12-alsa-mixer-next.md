# MyAI VENTUNO Q – read-only ALSA capture troubleshooting (2026-10-12)

Branch: `dev/routing-boundary-followup`
Production installation: `/home/arduino/MyAI` – **do not modify**
GitHub Actions runner: `self-hosted, Linux, ARM64, ventuno-q`

## Evidence from existing physical tests

- One-time plughw:0,1 capture attempt run `38242810988`:
  job `114789340362` **failure** at the two-second capture step,
  `status=alsa-capture-nonzero`. Safety checks before/after passed.
  No valid 64,000-byte PCM result was established.
- Follow-up metadata run `38243160507`, job `114790479297`:
  **success**; capture node accessible for runner, substream status
  `closed` at inspection. Does not prove the ALSA capture interface
  accepts requested parameters.
- Full regression run `38243160191`: completed successfully (the
  documented checkpoint states **1,167 passed, 6 skipped**).

These are **older verified runs**, not results of the latest changes.

## Implemented since then

1. `scripts/ventuno_microphone_smoke.py`: a failed ALSA subprocess
   yields an allowlisted `alsa_error_category`, not raw stderr,
   recording content or device labels. No additional capture invoked
   by this source change.
2. `tests/test_ventuno_microphone_smoke.py`: tests failure categories
   and suppression of potentially private stderr.
3. `scripts/ventuno_alsa_mixer_probe.py`: **read-only** `amixer -c 0
   scontents`; reports only aggregate capture switch/volume counts,
   never labels or raw mixer output; no microphone stream opens.
4. `tests/test_ventuno_alsa_mixer_probe.py`: test cases for
   no recording, privacy, parse behavior and fail-closed conditions.
5. `.github/workflows/ventuno-alsa-mixer-readonly.yml`: isolated
   runner checkout, targeted unit tests, read-only mixer inventory,
   service checks and guarded cleanup.
6. `docs/VENTUNO_VOICE_BRINGUP.md`: engineering notes updated.

Latest documentation checkpoint references source changes culminating in
`023d13e7d75be92563ebd51c77a6207ad3ce7c6e`.

## Important unresolved verification

A separate explicit one-time microphone authorization commit
`1736cd38838fe8ed8be8f4f63d5a2220123e8ed9` was pushed.
Its **result has not been verified in this conversation**; do not
interpret commit existence as a successful recording.

The GitHub connector currently available exposes run details by
**known run ID**, but does not list push-triggered workflow runs.
Therefore the newer microphone run, mixer-probe run, targeted tests
and current full development test suite are **not yet verified**.
Do not mark them as passed or run an additional audio capture merely
because their outcome is unavailable.

## Next safe action

1. Locate latest `VENTUNO ALSA mixer capture controls read-only`
   workflow run in GitHub Actions UI, note run ID, retrieve job steps/logs.
2. Require targeted tests and the read-only query to succeed.
3. Interpret `no-capture-controls-exposed` or
   `mixer-query-failed` as **inconclusive**, not as a healthy microphone.
4. If capture switches report off or volume zero, prepare a
   manual, reversible mixer-routing plan – **do not write controls
   automatically**.
5. If mixer controls appear sensible, continue with read-only routing
   and driver metadata before considering another separately authorized
   capture attempt.
6. Keep GenieX and MyAI running; do not activate
   `voice.enabled`, `tts_enabled` or `handsfree_enabled`
   automatically. Avoid new model installs and speaker playback.

This checkpoint is documentation only. No running service or physical
audio device was changed.


## Guard against false-positive mixer status

A subsequent source review identified a false-positive risk: an ALSA capture
mixer control can be enumerated without readable switch or level values.
Previously, that case could produce `capture-control-metadata-readable`
although no actual level or switch reading was available.

The read-only mixer probe now returns
`capture-controls-without-level-readings` in that case, and a regression
test was added. Source commits: `1a3224b` (classification) and `9b13878`
(test). A small local isolated logic check passed for the no-controls,
no-readings and switch-off branches. **Full CI / real mixer results still
remain unverified**, and no audio was recorded.


## Verified mixer reading on VENTUNO Q (2026-10-12)

We solved the workflow-observability blocker without extending privileges
on the production device. The read-only workflow now posts a narrowly
scoped **GitHub commit status** (requires `statuses: write` in CI;
no production service configuration is changed). The status carries
only predefined diagnostic categories/counts and links to its run.

Successful VENTUNO runs:

- `38246902076`: **9 targeted tests passed**. ALSA returned 37
  capture-related controls, but the original parser found no values.
- `38247122857`: **9 targeted tests passed**. An anonymized
  output-structure probe established all 37 control blocks contain
  percentage tokens, all 37 contain channel rows, and 3 blocks contain
  on/off tokens. Zero blocks used the original expected
  `: Capture` value-row format.
- `38247293898`: **12 targeted tests passed** after adding support
  for alternate ALSA channel-value rows. Actual value readings emerged.
- `38247327122`: **14 targeted tests passed**, after adding tests
  that exclude playback-only channel values from capture counts.
  Its final mixer report:

  - Capture-related mixer controls: **37**.
  - Capture switch observations: **6 on, 0 off**.
  - Capture volume percentage observations: **32 above zero,
    8 equal to zero**.
  - Read-only inventory status: `some-capture-volumes-report-zero`.
  - No recorded audio, speaker playback, mixer writes or production
    service restart by this workflow.

**Caution:** These are counts of observations, not necessarily unique
controls. A mixer can have more than one channel per control. Some
inactive capture routes may legitimately be zero; this does not prove
the active microphone path is muted or identify the cause of the
earlier `alsa-capture-nonzero` failure.

Latest verified targeted-tests commit: `0b8dfe1415cf2ec4f7a484d4b88f6823522732b2`.
This is **not** a substitute for verifying the full MyAI test suite.

## Safest next troubleshooting boundary

1. Inspect only the ALSA card and capture-path topology/routing
   metadata to associate mixer controls with the actual `hw:0,1`
   path; keep control labels and raw output out of CI logs.
2. Do not infer that changing any of the zero-level controls will
   correct capture.
3. Make no mixer writes, audio recordings, system service changes, or
   voice-enable toggles without a separately documented plan.
4. Once the active path is identified, stage a reversible manual change
   only if evidence requires one, and require fresh opt-in for any
   subsequent physical microphone capture.

No new microphone recording was performed during these investigations.
