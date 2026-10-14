# MyAI – unattended test execution and safe boundaries

Date: 2026-10-14
Branch: dev/routing-boundary-followup
Machine: real Arduino VENTUNO Q / self-hosted ARM64 GitHub Actions runner
Scope: user authorized all non-present tests ONLY if they do not impede future tests.

## Verified successfully completed, real VENTUNO results

**Full isolated MyAI unit regression suite:**
- GitHub Actions 38508914228: **1489 passed, 6 skipped**.
- GitHub Actions 38508999338: **1489 passed, 6 skipped**.
- GitHub Actions 38509110349: **1489 passed, 6 skipped**.
- GitHub Actions 38509228505: **1489 passed, 6 skipped**.
- All returned success. Python sources also passed compileall.
- These unit tests ran from disposable GitHub runner source, **not**
  production /home/arduino/MyAI.
- The 6 skipped tests have NOT been individually justified as safe
  to force; don't bypass their skip conditions automatically.

**Independent non-invasive live read-only matrix:**
- Run https://github.com/Harrokk/Myai/actions/runs/38508914285
- **69 passed**, no failures.
- Valid production VENTUNO profile; GenieX is default; automatic
  LLM fallback, voice, TTS, handsfree, camera, location, self-development,
  self-promotion and write-capable RPC/Excel remain disabled.
- Both myai-ventuno.service and myai-geniex.service active.
- Available memory **14002 MiB**; free disk **30587 MiB**
  at time of measurement; adequate for staged experiments.
- Ollama binary installed; loopback API unavailable because
  Ollama was not started. Do not start automatically for this test.

**Read-only post-reboot ALSA/USB investigation:**
- Run https://github.com/Harrokk/Myai/actions/runs/38508999336
- /proc/asound cards and pcm metadata readable.
- **No USB sound card reported** by card*/usbid metadata.
- Non-USB PCM available: card0/device0 playback, card0/device1
  capture, card0/device2 playback (node access permitted).
- Previous test's expected **USB card1/device0 capture/playback
  routes are ABSENT**. Voice dialogue readiness correctly returns
  `blocked-usb-reenumerated-or-inaccessible`.
- Do **not** assume card0 nodes are the user's USB headset.
- This cannot distinguish disconnection, power, enumeration, driver
  or different USB hardware until a permitted local examination.
- No microphones, speakers, ALSA streams, mixer controls or physical
  devices were opened/reset/changed.

**Previously verified natural-Swedish model trials:**
- Run https://github.com/Harrokk/Myai/actions/runs/38507835110
- One pinned public human-spoken utterance "Hur mår du?" from Shtooka/
  Wikimedia Commons: Tiny **0/4 exact**, Base **0/4 exact** across
  beams and capture shape; Base beam5 closer, still not exact.
- 55/55 focused safety tests in this run; all temporary model wheels
  and PCM discarded.
- The different phrase and single voice do not establish general
  Swedish recognition accuracy.
- Synthetic Piper Alma "Vad heter du?" earlier 8/8 exact
  (run https://github.com/Harrokk/Myai/actions/runs/38284679674).
- No permanently deployed changes from these model trials.

**Public multi-clip provenance exploration (not an ASR result):**
- Initial attempt run 38509110615 blocked on Wikimedia archive URL
  encoding check; corrected in source.
- Corrected attempt https://github.com/Harrokk/Myai/actions/runs/38509228560
  was blocked by **HTTP 429 rate limit** from the Wikimedia
  public API. This is not an STT error and is not a failed inference.
- Do not repeatedly retry while rate-limited; don't download bulk
  Common Voice archives, bypass licensing, or use unpinned assets.
- No further human clips were verified, benchmarked or staged in
  this attempt. No user data involved.

## Work that must remain deferred or separately authorized

1. User microphone recording, live speaker playback and sound-level
   tests require fresh explicit one-shot user authorization and
   presence; previous one-shot grants are consumed.
2. Repairing/disconnecting/re-enumerating USB cards, opening devices,
   ALSA write operations and enabling voice automation would change
   future hardware test conditions. Leave them alone.
3. No service restart, systemd edits, runner boot/retry changes or
   reboot. User explicitly postponed the runner work.
4. No production GenieX/Ollama runtime switch, installation, NPU
   library modification, model download into persistent directories,
   persistent voice changes, sandbox policy relaxation, or self-update.
5. Tests that may persist memory records, invoke untrusted physical
   tools, write locations or trigger automation are not automatically
   authorized by this unattended test request.
6. Do not force pytest's six skips without a separate safe review of
   their actual conditions.

## Remaining safe unattended opportunities

- Classify the six skipped unit tests by reason before running any.
- Use another independently licensed, transcription-verified public
  human Swedish sample *after* Wikimedia 429 resolves, with immutable
  SHA and strict size checks; keep all audio/model files transient.
- In particular prioritize exactly "Vad heter du?" from more than one
  natural voice; Forvo's recordings should not be downloaded unless
  rights explicitly permit the exact use.
- Continue code review, security regressions, isolated simulation and
  no-device unit tests without changing production. Avoid repeatedly
  rerunning already passing identical tests just to create CI volume.

## Production preservation and reproducibility

All new automated workflows run only for specific newly added test
workflow files on dev/routing-boundary-followup; no timers and no
permanent services added. Existing generic MyAI CI on dev pushes runs
automatically and is non-production checkout. No branch merge to main.
Active production stack, installed models, secrets and audio left
unchanged. This is a checkpoint, not a promotion to production.
