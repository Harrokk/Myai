# 2026-11-12: source-only privacy-safe WAV signal-level diagnostic

Operator read-only VENTUNO ALSA controls:
- /proc/asound/cards: card 0 monaco-gertrude, card 1 [X] USB Razer Kraken V3 X.
- /proc/asound/pcm: card 01 device 00 supports playback and capture.
- amixer -c X scontents: Mic Capture 35/35 (100%, +5.00 dB); Auto Gain Control off; no separate Mic capture switch reported. Sidetone off and Speaker 58% playback are not capture mute indicators.

Thus the USB input route remains correct and gain is maximum, not zero.
However, without examining **actual received PCM levels**, these commands
cannot distinguish silence, excessive gain/clipping, hardware mute or model
language/endpointing problems. Do not change gain/AGC blindly.

The isolated App Lab RAM WAV pilot adds a fixed, privacy-safe summary of the
**already captured** in-memory samples before the SDK ASR call:
peak percent of int16 full scale, RMS percent of full scale, and number of
saturated samples (>=32760 abs). No samples, transcript or text leave this
one-shot pilot as app logs. The model service may log its own diagnostics.

No audio file, mic dump, another capture, timer, retry, service stop or
production configuration change. Draft GitHub ARM64 tests are synthetic,
not a physical Razer microphone test. Separate explicit operator permission
is required before importing and running the new pilot once.

Cross-check with 12:32 live RAM WAV log: correct ALSA device selected
plughw:CARD=X,DEV=0 and after capture backend returned empty final with
native 'Non-supported or nn language detected' error. Root cause unproven.
