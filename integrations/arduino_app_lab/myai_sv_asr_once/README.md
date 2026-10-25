# MyAI: Arduino App Lab native Swedish ASR pilot

**Revised source staged only; the upgraded PCM-meter version has not been run on VENTUNO Q.** The previous one-shot implementation did run on 24 October 2026 but returned `no-final-text` despite the operator speaking Swedish. This is a minimal
variation on [Arduino's official ASR streaming example](https://github.com/arduino/app-bricks-examples/blob/main/bricks/arduino/asr/04_stream_mic_transcription/python/main.py)
but uses the even simpler supported `transcribe(duration=5)` API. It does
**not** connect to MyAI's LLM or its production services.

## Why this diagnostic

The prior custom Whisper **Tiny CPU** path rejected several real
recordings, despite microphone energy and operator-confirmed speech.
This pilot uses the official `whisper-small-quantized` QNN/Hexagon ASR
model with explicit `language="sv"`. The official Arduino model
catalogue includes Swedish in the ASR supported-languages list.

This App contains just **one Brick** (`arduino:asr`), so it does
not start another Qwen/GenieX model, cannot reach MyAI's tools,
does not launch a web UI/listener and cannot play speaker audio.

## Critical operator checks found in upstream App Lab SDK

Arduino's default ASR microphone is the first plugged microphone, not a
persistent identity. This source pins the previously used USB ALSA capture
pair with a subclass of `ALSAMicrophone(device="plughw:1,0", shared=False,
auto_reconnect=False)` and passes that device explicitly to
`AutomaticSpeechRecognition(mic=mic, language="sv")`. This source
identity was verified on the *previous* MyAI physical smoke, but App
Lab's container device map can differ. **Re-check the USB microphone
identity and the ALSA card index in the actual App Lab container first.**
If the pair is wrong or unavailable, the app must stop; do not silently
select another microphone.

A second important first-party lifecycle detail: **`App.run()`
starts the ASR Brick and its model warmup before the user-loop**.
If ASR constructs its own default microphone, it starts that microphone
at Brick startup. **But when a microphone is injected by the caller,
the Arduino SDK deliberately does NOT start or stop that microphone**.
This pilot therefore calls `mic.start()` itself inside its single-use
user-loop, before `asr.transcribe(duration=5)`, and always attempts
`mic.stop()` afterward. A failed release cannot be reported as a pass.
Clicking **Run** can already load the ASR model onto the NPU during
warmup, even before `capture-begins`. Confirm fresh microphone consent
and GenieX/NPU resource coexistence before clicking Run.

With `shared=False`, another application attempting to capture from
the same device will fail rather than share the private audio stream.
`auto_reconnect=False` prevents automatic device reconnection. The
actual exclusivity and device identity remain unverified until a
separately approved App Lab installation inspection. Upstream Arduino
SDK log behavior must also be reviewed before sharing any error output.

## How to run LATER, only with fresh explicit physical approval

1. Open Arduino App Lab with VENTUNO Q attached. Import/copy
   `myai_sv_asr_once` as an App. Inspect `app.yaml`: it requests only
   `arduino:asr`.
2. In the ASR Brick's AI Models view, confirm
   `Whisper Small (quantized)` is installed; a missing model may
   require a separately approved download. Do not enable a second LLM.
3. Ensure mic and power are ready, check that the existing production
   MyAI voice listener is disabled, and obtain a fresh single-use
   microphone consent. Click **Run** once to start the diagnostic.
4. Only when `MYAI_ASR: pcm-first-chunk-speak-now` appears in the local
   App Lab terminal, say **Vad heter du?** one time within five seconds.
5. Read only its fixed result code:
   `reference-recognized`, `other-nonempty-text`,
   `no-final-text` or `unavailable-or-failed`.
   No transcript or recognized words will be shown, stored or sent
   to GitHub. App lifecycle ends after one turn; do **not** click
   Run a second time without fresh authorization.

The phrase equality test here measures basic Swedish recognition
performance and **does not** constrain MyAI's conversation vocabulary.
We can then use the source-only bridge from PRs #361 and #362 to
accept ordinary questions.

## Integration decision

Arduino's current `arduino:llm` default for VENTUNO Q is
`genie:qwen3_4b_instruct_2507`, but it is a separate App Lab service.
Our active MyAI GenieX service remains on host loopback.
We have **not established** that both Qwen instances may safely run
together or that App Lab container `127.0.0.1` reaches host loopback.
Do not bind MyAI's GenieX service to `0.0.0.0` or start App Lab LLM
until separate resource/security checks are complete.

Arduino's built-in TTS catalog at the reviewed revision lists Piper
English/Italian/German and Melo English/Spanish/Chinese, but no
Swedish voice. Keep the previously verified Swedish eSpeak staging
as an interim fallback; choose a natural Swedish TTS only after
checking licensing, voice quality and available compute.

**NO-GO**: automatic audio activation, new model download, service
restart, self-hosted GitHub jobs, settings edits or deployment
until separately authorized.

## 25 October 2026 follow-up: no-final-text despite spoken Swedish

The first actual operator-supervised test produced `MYAI_ASR: capture-begins`,
`MYAI_ASR: no-final-text`, and ordinary one-shot shutdown. The operator
confirmed that they spoke the reference phrase with the physical mic unmuted.
VENTUNO enumerated USB Razer Kraken V3 X (ALSA card 1/device 0);
`amixer` indicated 100% mic capture and no visible capture-mute toggle.
The USB device supports 16 kHz/S16_LE capture. The ASR service responded to
HTTP health checks, but no audio levels or accepted PCM chunks were observed
by the prior app; a successful ASR HTTP health status is not an inference
verification.

### Changes in the upgraded pilot (NOT yet executed on hardware)

- A subclass of the Arduino SDK's public `ALSAMicrophone` reads the *same*
  PCM chunks ASR's reader consumes, through `super().capture()`. There is
  NO extra capture pass, temporary WAV, archived audio, network upload or
  text logging.
- `microphone-open-asr-pending` reports the microphone open but **not**
  an active ASR recording; `pcm-first-chunk-speak-now` reports when the
  first nonempty PCM buffer was read from the source. This is closer to
  the live audio timing, but **does not prove the inference WebSocket
  has accepted that data**. The short five-second ASR clock may begin
  slightly before this marker. Output buffering in Arduino App Lab could
  also delay display.
- At session end emit ONE coarse, numerical-content-free summary:
  `pcm-level-no-pcm`, `pcm-level-near-silent`,
  `pcm-level-low` or `pcm-level-present`, based on input RMS/peak.
  `present` proves signal amplitude but NOT that the signal is speech,
  correctly timed or accepted by the model.
- Preserve original `reference-recognized`, `other-nonempty-text`,
  `no-final-text`, `unavailable-or-failed`, and
  `microphone-release-failed` outcome codes. Never print transcript,
  PCM content or SDK exception details. Continue to stop mic in `finally`
  and let `App.run` stop on `StopIteration`.
- No production voice enablement, model replacement, service/unit changes,
  new dependencies or hardware trigger.

Nine synthetic, side-effect-free tests cover PCM level boundaries,
real one-pass capture interception, first-frame marker, phrase matching,
no transcript leaks, no audio read on test import, one-shot cleanup
and errors.

### Operator constraints

**Do not run this new revision automatically.** The prior consent applied
to the earlier completed attempt; a repeat must be a newly approved,
physically supervised test. Verify both MyAI and GenieX are active and the
Razer USB device is still exactly card 1/device 0. The separate corrected
service guard from DRAFT PR #372 is needed to stop MyAI before GenieX and
restore GenieX before MyAI. The earlier original guard is unsafe and
obsolete. Avoid reimporting/restarting this App while production uses
the accelerator. Do not ask the operator to speak until the local
`pcm-first-chunk-speak-now` status appears. If the five-second window
has already ended by that time, treat it as a timing failure and do
not automatically re-record.
