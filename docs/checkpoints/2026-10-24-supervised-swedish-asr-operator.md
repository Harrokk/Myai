# One supervised Swedish ASR turn — operator instructions (24 October 2026)

The operator has **explicitly approved one five-second Swedish
microphone test**, including a temporary stop and subsequent restart
of `myai-geniex.service`, and says they are physically at VENTUNO Q.
This consent does not authorize continuous microphone monitoring,
TTS, another LLM, background/scheduled capture, additional
microphone sessions or production voice enablement.

## Tested project state

- Native one-shot Arduino App Lab app: `integrations/arduino_app_lab/
  myai_sv_asr_once` (DRAFT PR #363), exactly one
  `arduino:asr` Brick and `language="sv"`.
- Official `whisper-small-quantized` installed and listed as
  `installed` on board; installation action SUCCESS run #39956949300.
- Last hardware-readiness check found USB capture card 1/device 0,
  accessible on host; no proof yet inside App Lab namespace.
- GenieX and MyAI were active in the latest passive real-hardware
  tests; production voice.enabled=false, GenieX watchdog
  restart_enabled=false in reviewed VENTUNO profile.
- Arduino App CLI supports ZIP import with either
  `app.yaml` in ZIP root **or one enclosing folder** and
  the official examples use `bricks: [arduino:asr]`.
- A verified operator packet was packaged locally as
  `MyAI_Ventuno_ASR_Supervised_Test_Kit.zip`; the native app files
  have upstream Git blob SHA
  `2eaa45e607ce8096e1112a5dc8ff42fecd15b0cf` and
  `f5c331aa4a2c18f7f96d91a64b03cf3cbf8d5424`.
  Do not assume the packet is present on VENTUNO filesystem;
  the operator must transfer/download it. GitHub runner never
  sends media or imports/starts the App automatically.

## Operator-only run

1. Import `myai_sv_asr_once` into Arduino App Lab from the
   verified ZIP. Leave it **stopped**. Do not click Run yet.
2. On a local VENTUNO terminal **as the `arduino` user**, run
   `bash scripts/ventuno_supervised_app_lab_asr_guard.sh` from
   a vetted project checkout or transfer the standalone script
   (SHA-256 `c2f904f101eebe614265fe26ced220cbdb83777dc5d8f447ee05e8cc8a95bc2b`
   of the distributed local shell file).
   **NOTE:** verify matching source if using a raw GitHub copy.
3. The guard confirms normal ARM64 user, both services active,
   expected USB ALSA capture pair `1:0`, interactive TTY.
   It then prompts for Enter and `sudo -v` *before* stopping GenieX.
4. The guard sets an EXIT/HUP/TERM/INT handler, runs
   `sudo systemctl stop myai-geniex.service`, and confirms
   it is inactive, leaving MyAI and GitHub runner untouched.
5. While the terminal guard is in its interactive window, click
   **Run exactly once** in App Lab. Watch local logs. Only after
   `MYAI_ASR: capture-begins` say **Vad heter du?** once
   within the next five seconds. The test emits fixed categories,
   never a transcript:
   `reference-recognized`, `other-nonempty-text`,
   `no-final-text`, `unavailable-or-failed`,
   `microphone-release-failed`.
6. Make sure the App Lab app is stopped. Return to the same terminal,
   press Enter to close the test window and automatically restart
   GenieX; verify the message that it is active. The guard
   also ends the window automatically after 600 seconds or
   Ctrl+C/HUP/TERM. If the process is uncleanly killed, the board
   powers down, or sudo fails, the EXIT trap cannot guarantee
   recovery; manually run `sudo systemctl start myai-geniex.service`.
7. Report **only the fixed status code** here. A failure status
   must not trigger an automatic second recording without new
   authorization. Never share raw audio, transcripts, serial
   numbers, tokens or unredacted App Lab service logs.

The guard does **not** open devices, start the app or infer on the NPU.
The operator decides the start moment. App Lab's own ASR Brick may
warm the model at Run even before the five-second capture. Any failed
or busy NPU coexistence is an observed limitation, not reason to
change production configurations while running this pilot.

## Recovery and safety

The runner's unit Restart=no remains unchanged. This test intentionally
does not use the GitHub Actions runner to remotely stop GenieX. The
operator must have a functioning local terminal and can restore the
service out of band. Source-only tests exercise `bash -n` and
static fail-closed guards; no on-board production jobs or recordings
are created by this PR.

Keep DRAFT and do not merge to main until physical result,
no regression and post-test GenieX state are verified.

## STOP — dependency failure found in first real operator attempt, and correction

Operator supplied real host metadata on 2026-10-24:

```text
systemctl is-active myai-ventuno.service myai-geniex.service
active
active

myai-ventuno.service:
Result=success
Requires=... myai-geniex.service ...
After=... myai-geniex.service ...
ActiveState=active
SubState=running

myai-geniex.service:
Result=success
ActiveState=active
SubState=running
```

Under documented systemd semantics, an explicit stop of a service
listed in `Requires=` also stops the requiring service. Therefore
the original guard's promise of stopping **only** GenieX while
leaving MyAI running was incorrect. Actual first local guard attempt:
- SHA-256 validated; initial checks passed.
- User entered confirmation, stopped GenieX.
- MyAI also became inactive, correctly detected by the guard.
- The **old guard restored only GenieX**, leaving MyAI inactive;
  a second invocation was blocked as designed at preflight.
- User explicitly started MyAI again via systemctl and supplied
  statuses for **both services: active/running, Result=success**.
- **NO App Lab ASR capture was made**. This incident provides no
  evidence of native Whisper correctness or incorrectness.

**Corrected draft guard** (same file path on this feature branch,
different Git blob; prior SHA-256 checksum is OBSOLETE):

- One more explicit local opt-in text `JA STOPPA BADDA` is required
  before any service stop. Earlier consent to stopping GenieX
  does not automatically approve intentional MyAI downtime.
- After preflight and sudo validation, the script arms an EXIT/HUP/TERM
  /INT restoration trap **before** its first action.
- Stops **MyAI first**, verifies inactive; stops **GenieX second**,
  verifies inactive. Keeps GitHub runner running.
- Human operator, not the script, launches the five-second App Lab ASR
  diagnostic once, with their awareness and no transcript export.
- Local test window reduced to **180 seconds**. When it ends or aborts,
  restores **GenieX first**, **MyAI second**, independently attempts both
  and checks both active. On sudo timestamp expiration, the trap may
  prompt in the local TTY. Hard kill/power loss and sudo failure still
  cannot guarantee recovery; manual commands remain:
  `sudo systemctl start myai-geniex.service` then
  `sudo systemctl start myai-ventuno.service`.
- New isolated tests replace systemd and sudo with **fake shell functions
  in a temporary COPY** of the guard, never executing any live stop.
  Cases include successful handoff, failure during second stop,
  declined consent and inactive startup preflight.

**NO-GO:** The corrected guard is prepared and tested in CI, but is
**not to be run** until the user explicitly approves pausing *both*
MyAI and GenieX in chat and the operator has the App Lab app imported
and ready. Do not change persistent `Requires=` or `After=`
configuration as part of a test. Prior downloaded ZIP kit and
its guard checksum must no longer be used. Document this as a
superseding correction, not evidence of an audio test pass.

Official systemd Requires semantics:
https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html
