# MyAI: Arduino App Lab native Swedish ASR pilot

**Source staged only; never launched on VENTUNO Q.** This is a minimal
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
pair with `Microphone(device="plughw:1,0", shared=False,
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
4. Only when `MYAI_ASR: capture-begins` appears in the local
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
