# Private STT triage after operator physical test — 2026-11-05

The operator ran a separately approved local 3-second Swedish Whisper Tiny test on VENTUNO Q and shared the sanitized output: literal "Vad heter du?" recognized NO, class "different words", decode including model initialization 2.87 seconds. The audio passed the test's PCM length, RMS and clipping gates, and the worker generated nonempty words, but the private words were immediately discarded. No content can be recovered or inferred.

This DRAFT adds the pure source-only helper scripts/ventuno_private_stt_failure_diagnostics.py. It categorizes a future, separately approved one-shot result using fixed labels: exact literal, harmless allowed alias but nonliteral, instruction echo, extra words, unsafe/control, unrelated, silence or invalid. Existing PCM coarse signal and early/middle/late activity labels are reused. It never exports recognized words, waveform or a similarity text and never authorizes a retry or command.

New tests are 100% synthetic. This patch does not capture microphone sound, play audio, call GenieX, touch VENTUNO services, deploy, merge or enable voice. Previous one-shot consent is not reusable for a new recording. Later local integration must be separately reviewed and consented to.

Do not interpret source-only regression tests as live Swedish speech recognition success.
