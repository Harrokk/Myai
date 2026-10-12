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
