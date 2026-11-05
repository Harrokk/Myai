# STT clipped-capture fail-closed parity — 2026-11-05

The existing exact physical STT synthetic fixture gate rejected `possible-microphone-clipping`. The actual one-shot `OneShotUsbDialog` controller, however, recorded this diagnostic label while enforcing only an RMS minimum through `pcm_signal_ok`. Heavily clipped PCM can have a high RMS, so previously it proceeded to the speech decoder and (conditional on its output) toward the local model and audio output.

The controller now blocks invalid PCM, silence/too-quiet PCM **and possible microphone clipping** before any STT decoder call, using the already implemented coarse signal classification. This harmonizes the offline synthetic validation and actual controller safety boundary without changing the classification threshold, volume, model, microphone device or live voice configuration.

Synthetic regression tests demonstrate fully saturated and partly clipped audio denied without transcription or GenieX/TTS/playback; a normal nonclipped PCM case still completes. The one-shot may not retry once consumed.

This DRAFT is **source only**. The user's prior consent to the microphone-to-headphones loopback was consumed by a successful manual test (user reported hearing their voice). That is not consent to a new live STT microphone recording. No VENTUNO physical audio is accessed here. This is not evidence that Swedish recognition works on live hardware.

Do not merge or deploy without separate review. Critical voice commands and risk-tiered verification remain OFF.
