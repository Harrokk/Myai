# ASR v2 full_text event root-cause investigation — 2026-11-06

## Physical observation (operator shared)
The **new explicit-microphone App Lab v2** successfully reached `App started` and `MYAI_APP_LAB_ASR_V2: microphone-opened` on VENTUNO. It later emitted `MYAI_APP_LAB_ASR_V2: invalid-final`, performed orderly `App is shutting down`, released 1 peripheral, and printed `App shutdown completed`. This is **not a hanging main.py or a failed ALSA selection**. The App Lab catalog status `failed` cannot be interpreted as an ASR/model crash without additional evidence.

This `invalid-final` was emitted when the first ASR `full_text` event failed in-memory validation, **not** proof that the ASR engine could not transcribe, nor proof that `full_text` was empty. The old code merged empty/type/control/length categories.

## Verified official SDK semantics
Arduino `app-bricks-py` source `src/arduino/app_bricks/asr/local_asr.py` at revision `94f100ee906770e6f469f9edbc615bad895d695e` implements `transcribe_sentence_stream(timeout=N)`. Its sentence generator returns only upon `event.type == "full_text" and event.data.strip()`, i.e., the official code **continues past empty full_text events**. No real recording was done during this source review. The VENTUNO installed SDK has different line numbers, so actual event payload remains unverified until a separately consented test.

## Patch
- A **blank** `full_text` (string only) is ignored without another microphone `start()`, ASR session or `App.run` turn. If the bounded stream ends after blank finals, report `empty-final-only`.
- The first **nonblank** `full_text` is consumed once, with fixed result codes: `invalid-final-type`, `invalid-final-too-long`, `invalid-final-control`, `reference-recognized`, or `other-nonempty-final`. Never print or persist private words.
- The original 8-second stream timeout, 64-event cap, cancellation, `mic.stop()`, and no service or tooling calls remain.
- New fake Arduino tests cover blank followed by real, blank-only, 65 blank events, first malformed nonempty, and privacy.
- User confirmed ALSA card 1/device 0 in VENTUNO host `/proc/asound/{cards,pcm}` for Razer Kraken V3 X.

No physical recording, remote execution, service stop or production config change is authorized by this patch. No legacy voice branch or production MyAI runtime changes.
