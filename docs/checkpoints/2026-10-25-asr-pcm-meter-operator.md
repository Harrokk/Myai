# MyAI one-shot ASR PCM observability checkpoint — 25 October 2026

## Verified physical baseline (earlier run)

- VENTUNO Q, user `arduino`, ARM64 and MyAI/GenieX both `active` according to operator logs.
- Razer Kraken V3 X: ALSA capture card 1/device 0; S16_LE capture at 16 kHz supported, microphone mixer capture 100% (+5 dB), physical mic was open.
- Operator reported speaking *Vad heter du?* during the original five-second run; Arduino App Lab logs show `MYAI_ASR: capture-begins` followed by `MYAI_ASR: no-final-text` and ordinary application shutdown; manager shows `failed` but no Python traceback was shared.
- ASR Brick health HTTP 200 does not establish end-to-end audio-to-text operation.

## SDK sources checked

- Arduino `arduino/app-bricks-py` `src/arduino/app_bricks/asr/local_asr.py`: `AutomaticSpeechRecognition.transcribe(duration)` creates session and reader; reader calls `self._source.capture()`, sends its PCM chunks to a bounded queue. Returns empty string if no speech was detected.
- `src/arduino/app_peripherals/microphone/alsa_microphone.py` and `base_microphone.py`: public `ALSAMicrophone` supports pinned `plughw:1,0`, 16k/mono/S16 default; `capture()` returns NumPy PCM samples or None. Caller-owned microphone must be started and stopped by caller.
- `src/arduino/app_utils/app.py`: `StopIteration` exits user loop cleanly. `App.run` manages ASR Brick but does not start/stop explicitly injected microphone.

## Staged code change (no physical deployment)

- Override just `ALSAMicrophone.capture()` in a specific diagnostic subclass, call `super().capture()` ONCE, observe received NumPy samples in memory, forward unchanged to ASR.
- First nonempty buffer triggers `MYAI_ASR: pcm-first-chunk-speak-now`. Unlike previous `capture-begins` this confirms a real PCM buffer arrived, **not** acceptance by the inference server. UI buffering and the five-second clock may still reduce user response time.
- End emits one aggregated privacy-preserving level class (no-pcm / near-silent / low / present) with no PCM, transcript or numeric voice feature persistence. Signal presence cannot distinguish speech from background noise.
- Keep exactly one five-second ASR session, Swedish language fixed, no retries, no default microphone fallback, no production service modifications, no new model/second recording.
- Synthetic tests stub all Arduino imports and real microphone, verify 16-bit PCM math categories, timing message, no text leaks, error and cleanup behavior. Do not invoke the real app in hosted CI.

## Next gate

Hosted ARM64 source-only CI must pass. Keep this DRAFT branch stacked on PR #372. Do not import/run upgraded App without new explicit operator approval for a single microphone capture and intentional temporary downtime of both MyAI and GenieX, per corrected guard. At resumption first verify operator presence, both service states, pinned hardware and app import status. If App Lab shows the older `capture-begins` marker instead of `pcm-first-chunk-speak-now`, the new code has NOT been imported. No physical capture was triggered by this checkpoint.
