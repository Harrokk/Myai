# MyAI – VENTUNO Q, förberedelse för första fysiska USB-röstsamtalet
Date: 2026-10-12
Branch: `dev/routing-boundary-followup`

## Grounded hardware status

- USB capture at ALSA `plughw:1,0`: two-second non-silent
  S16_LE mono 16 kHz microphone sample previously physically verified.
- USB playback at ALSA `plughw:1,0`: Swedish low-volume eSpeak
  phrase previously played and **audibly confirmed by the user**.
- Actual publicly licensed Swedish Whisper transcription has been passed
  via real MyAI VoicePipeline to the existing GenieX server; a Swedish
  WAV synthesized in memory (run `38254119684`).
- The later read-only VENTUNO preflight at
  https://github.com/Harrokk/Myai/actions/runs/38255691684
  measured available RAM **12,905 MiB**, temporary disk **33,922 MiB**,
  confirmed USB capture + playback and two production services active.
  Values can change over time; preflight must be repeated at run time.
- No physical *conversational* microphone -> Whisper -> GenieX ->
  USB speaker cycle has yet been executed.

## New guarded production-independent implementation

1. `scripts/ventuno_usb_dialogue_once.py` is a single-use controller.
   Consent for microphone recording and speaker playback must BOTH be
   explicitly true. A controller instance rejects any second attempt,
   including failed first attempts. Capture is exactly **3 seconds**
   and **96,000 bytes** of 16 kHz mono signed PCM in RAM.
2. Only a tiny list of harmless Swedish test utterances is allowed,
   e.g. `Vad heter du?` or `Hur mår du?`. Whisper silence,
   uncertain/unsupported transcriptions, system commands, unbounded
   model responses and low-RAM conditions are rejected.
3. After the short capture, the isolated Whisper CPU worker receives
   PCM **via stdin** and returns private JSON **via stdout PIPE**.
   Neither PCM nor transcript is written to disk or GitHub logs.
4. The already-running local GenieX model is queried **once** with
   the harmless normalized question and a short-answer budget.
   No tool execution or file mutation is offered to this adapter.
5. Offline Swedish eSpeak NG synthesizes the response. The WAV is
   capped to **4% digital peak** (not a measured loudness guarantee),
   to a short duration and to an in-memory bounded byte count before
   any possible ALSA playback.
6. A fresh USB device/access/service/RAM preflight occurs again before
   the one allowed speaker playback. A USB card-index change stops
   execution instead of guessing the new device.
7. `scripts/ventuno_usb_dialogue_hardware.py` provides the real
   command adapters. All model data/temporary Python environment and
   eSpeak voice packages must be staged beneath a fresh
   `$RUNNER_TEMP/myai-usb-dialog-*` root; the driver refuses active
   production paths and has no automatically running top-level code.
8. Production voice options stay disabled; no `systemctl restart`,
   package installs, changes to mixer settings or writes to the
   live `/home/arduino/MyAI` tree are part of this test.
9. The GitHub Actions workflow
   `.github/workflows/ventuno-usb-dialogue-controller-safety.yml`
   executes **mocked synthetic audio only**, never actual recording,
   live LLM requests, playback or model loading.

## Verification and consent boundary

Earlier synthetic tests passed **70/70** on VENTUNO:
https://github.com/Harrokk/Myai/actions/runs/38258896039

After adding the hardware adapters, the initial expanded regression
suite ran **84 passed, 1 failed** (run `38259484122`).
The failure was a test assertion which incorrectly rejected the
allowlisted literal word `private` in a diagnostic status string.
The test was corrected in commit
`1a6b3a549d31c629754733ca06f5cedce24bab95`.
A fully green rerun needs independent verification; no physical audio
was attempted by either runner.

**Next:**
- Confirm all expanded hardware-adapter safety regressions are green.
- Prepare a one-time dedicated physical runner with strict exact
  authorization gate, staged pinned STT, low-volume Swedish TTS,
  permission checks, isolated temp cleanup and no transcript logs.
- The user should be at the VENTUNO microphone and prepared to say one
  short safe question (`Vad heter du?`) during the brief test window.
- Do **not** auto-run the physical test from an ordinary source push.
  Obtain a clear fresh authorization tied to its exact one-time
  three-second recording **and** one response playback after the
  test is staged. A generic development continuation is not a timed
  microphone capture event.
- Do not enable production handsfree from these component results.

No physical recording or playback was initiated while this new
controller/driver and its tests were created.


## Verified final synthetic hardware adapter regression

After the corrected test assertion, VENTUNO Q self-hosted CI
completed the entire expanded synthetic-only safety suite:

- Commit: `1a6b3a549d31c629754733ca06f5cedce24bab95`
- GitHub Actions run:
  https://github.com/Harrokk/Myai/actions/runs/38259591990
- Job `114846403321`, conclusion: **success**
- **85 passed, 0 failed**; tests include the new hardware ports,
  exact arecord/aplay CLI arguments, private stdin/stdout for Whisper,
  local-only bounded GenieX requests, playback limiting and one-shot
  consent/resource/device guards.
- Services healthy and runner temporary checkout removed.
- No real recording, user speech, speaker playback, model load,
  production settings change or active service restart.

Next action is **not** another unannounced capture. Stage a guarded
human-coordinated physical test and ask the user to be physically
at the device to speak `Vad heter du?` during its exact 3-second
recording interval; the physical test must be opt-in for both recording
and an audible low-volume answer.


## First one-time real voice dialogue attempt (user present)

User confirmed they were physically ready at VENTUNO Q and to say
“Vad heter du?” after the audible cue. After the extra safety
verification (89 tests passed) the exactly-once GitHub job was
authorized:

- Source authorization: `51875a2a7997fa118a09fe6687d3ba95b564ab2e`
- Workflow: `.github/workflows/ventuno-usb-live-dialog-consent-once.yml`
- Run: https://github.com/Harrokk/Myai/actions/runs/38261367044
- Job: `114852411417`, **failure** at the dialogue step only
  (not a service failure).
- All **89** synthetic security tests passed. A read-only preflight
  measured **12,856 MiB** free RAM, ~33,917 MiB free disk, and
  available ALSA USB capture/playback. Live services remained active.
- Pinned ARM64 Whisper Tiny model downloaded/verified, public Swedish
  reference word recognized, and temporary Swedish eSpeak prepared.
- Final preflight checked USB, memory and service state again.
- The one-time dialogue controller issued the low-volume Swedish
  spoken cue and attempted **one physical 3-second recording**. Its
  result reached the transcription decision:
  `recording_attempted=true`,
  `transcription_verified=false`,
  `status=reject-unapproved-or-unclear-test-utterance`.
- No GenieX request or answer speaker playback was made:
  `local_geniex_answer_verified=false`,
  `playback_attempted=false`.
- No waveform, recognized words, response, or audio file was saved
  or uploaded; the temporary pinned Whisper/eSpeak packages were
  removed after the job. Both production services remained running.
- **The exact recognized speech was deliberately discarded**, so
  it cannot be recovered from GitHub logs and the cause cannot be
  identified more precisely from this one-time run. Possible causes
  include an overlapping start cue, mistimed user speech, ASR
  variation, or environmental noise. None is proven.

Do **not** re-run this exact authorized audio job. Its scope was one
attempt and the GitHub job has already executed it.

### Privacy-safe follow-up (without a new recording)

The controller now classifies any future rejected ASR result into
only an allowlisted **category** (empty, spoken cue suspected,
test-question with extra words, unsafe command, short unrelated
utterance, other unmatched). It continues to refuse uncertain
transcriptions and never logs recognized words. The change is
for a separately authorized future test only, **not an excuse to
automatically retry** the user's current recording.

The next test requires a new explicit approval for one physical
recording and optional low-volume spoken answer, ideally after
confirming whether the user heard the cue and had time to ask the
intended question. Preserve production voice disabled.
