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

## Verified follow-up: runner, skipped dependencies, USB and App Lab (2026-10-14)

- GitHub runner is back online. The formerly queued checkpoint retry succeeded
  on run 38344870738, attempt 2; additional real ARM64 jobs also succeeded.
- In the isolated generic MyAI CI, use `pytest -q -rs` to report skipped
  reasons automatically. This does **not** change test execution or production.
  Change commit: `3cc588399ea55f677b383e67a8b09ed5113a6a94`.
  Successful run: https://github.com/Harrokk/Myai/actions/runs/38516562492
  Result: **1489 passed, 6 skipped**.
- The skips are explained by **missing optional host test dependencies**:
  - `onnx` absent: 2 tests in
    `tests/test_prepare_tiny_qnn_host_sample.py` and 2 tests in
    `tests/test_verify_tiny_qnn_host_sample.py`;
  - `numpy` absent: 2 tests in
    `tests/test_qairt_245_cpu_reference_trial.py`.
  These are not six discovered test failures. The host ONNX numerical-reference
  tests also require `numpy` and may require `onnxruntime` once `onnx`
  is available; do not blindly install/force host-only dependencies on ARM64.
  No persistent dependency installation was performed.
- Read-only USB metadata workflow rerun:
  https://github.com/Harrokk/Myai/actions/runs/38508999336 (attempt 2).
  USB ALSA cards remain **absent**. Card0/device1 capture and card0/device0/2
  playback exist but must not be assumed to be the user's USB headset.
  No audio device was opened or modified.
- New sanitized App Lab connection diagnostic workflow:
  https://github.com/Harrokk/Myai/actions/runs/38516851399
  `global_ipv4_present`, `wifi_ipv4_present`,
  `ipv4_default_route_present`, `default_route_via_wifi`,
  `mdns_udp_5353_bound`, `avahi_daemon_active`,
  `ssh_tcp_22_listening`, `ssh_service_active`, runner service,
  MyAI service and GenieX service were all **true**.
  The diagnostic printed no network addresses, SSIDs, MACs or secrets.
- App Lab on Windows previously returned "invalid board address / invalid IP".
  With the VENTUNO network and local discovery/server services now confirmed
  operational, investigate **Windows mDNS/firewall, client network isolation,
  stale cached IP and client-side App Lab settings** before touching VENTUNO.
  This is a hypothesis, not a proven Windows root cause.
  Arduino troubleshooting for Q family mentions `mdns-discovery.exe`
  firewall permission and UDP/5353 for mDNS discovery.

The production MyAI/GenieX services and runner settings were not changed.
No audio capture/playback, model start, installation, reboot, mDNS reset,
network reconfiguration, or privileged device operation was attempted.
