# Official Arduino Whisper Small install — explicit operator approval, 2026-10-23

The user explicitly approved inspecting an alternative App Lab model directory
and installing the official Whisper Small (quantized, about 343 MB) if absent.
This approval is **only** for model metadata inspection/installation; it
does **not** authorize any physical audio, ASR inference, model startup,
app launch, second language model or production configuration changes.

Source of official CLI call:
- https://github.com/arduino/arduino-app-cli/blob/main/cmd/arduino-app-cli/model/install.go
  `arduino-app-cli model install whisper-small-quantized` invokes the
  bundled `ai-hub-handler`, rather than any bespoke shell downloader.
- https://github.com/arduino/arduino-app-cli/blob/main/cmd/arduino-app-cli/model/list.go
  `model list` uses Arduino's own models index and a temporary
  models-downloader container to read actual installation state.
- https://github.com/arduino/arduino-app-cli/blob/main/internal/orchestrator/config/config.go
  `MODELS_PATH` may override the documented
  `/var/lib/arduino-app-cli/models` directory.

The GitHub Actions workflow in this branch is intentionally a **single-use**
approved run, tied to one exact preceding checkpoint SHA and one exact commit
message. It checks the Arduino CLI model listing first, using only redacted
JSON status. If already installed it skips any download; if absent and host
resource and production-service safety gates pass, it invokes only the
official Arduino model installer for the one allowlisted catalog ID. No
arbitrary URL is supplied, no MyAI repository checkout is installed, no
background microphone activation or second GenieX/Qwen is attempted.

Preflight gates: VENTUNO ARM64 normal runner user, current MyAI and GenieX
units active, free disk and RAM reserves, exact model ID declared by
the installed CLI, no pre-existing model download in progress, and safe
effective model root. Postflight: independent official model listing,
sanitized status report, both production services still active.
Timeouts/error handling are fail-closed, never automatically force a
partial download retry or delete existing model files.

**Caveats:** A successful install is not a demonstration that the
Whisper ASR model has ever run on the NPU or that the App Lab container
can access the previous microphone. A separate supervised consented
audio pilot is required. Do not start that here. Keep PR DRAFT.
