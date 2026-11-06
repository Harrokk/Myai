# App Lab v2 — read-only USB microphone preflight — 2026-11-06

The operator confirms that the Arduino App Lab ASR model Whisper Small (quantized) is already installed. This is **operator-reported UI state**, not a measured successful ASR session and not proof the correct USB microphone will be chosen.

Source verification of the upstream Arduino app-bricks-py `Microphone(device=None)` implementation (vendor commit `94f100ee906770e6f469f9edbc615bad895d695e`) shows default selection prioritizes USB devices. When more than one USB microphone is present, the selected device can vary. Since the new ASR v2 official pilot currently uses the SDK default mic, **do not start the pilot unless the operator validates which mic it will use**.

The script `integrations/arduino_app_lab/asr_v2_official_pilot/preflight_readonly.py` performs a read-only metadata inventory using `/proc/asound/pcm` and USB card `usbid` markers and queries only the current `is-active` state of `myai-ventuno.service` and `myai-geniex.service`. It never opens `/dev/snd`, records audio, loads a model, contacts a network, stops/restarts a service or changes MyAI. No raw ALSA name, serial or file path appears in the report. Even the 'exactly one' classification is *not* permission to capture or assume a particular microphone.

Synthetic-only tests prove one USB capture, multiple devices, missing markers, symlinked metadata, unknown service state, no sensitive strings and no service commands. This PR adds no execution in GitHub workflow on VENTUNO and no changes to `python/main.py` or the active profile.

A later operator-controlled **read-only** check can be run on VENTUNO after transferring the file separately; its output can be shared. A later **physical** test of App Lab requires distinct explicit consent to record, plus any service-pause approval if services conflict. The original legacy voice archive and existing production runtime remain untouched.
