# VENTUNO built-in Whisper Small model-file evidence

**2026-10-23 source-only revision + one consent-independent, passive host
metadata inventory.** No physical audio, ASR inference, model loads or
downloads, application launch, Docker container process or service writes.

Upstream sources:
- https://github.com/arduino/arduino-app-cli/blob/main/internal/orchestrator/config/config.go
  uses `MODELS_PATH` override or default `/var/lib/arduino-app-cli/models`.
- https://github.com/arduino/app-bricks-py/blob/main/models/models-list.yaml
  declares the VENTUNO model `whisper-small-quantized`, under repository
  `audio-analytics/asr` and directory
  `whisper_small_quantized-voice_ai-w8a16-qualcomm_qcs8275`.
- https://github.com/arduino/app-bricks-py/blob/main/containers/bricks/models-downloader/src/list_models.py
  describes `models.yaml` as a *best-effort cached listing* and
  `.download` as an in-progress/interrupted download marker.
  A valid model folder must hold non-bookkeeping content.
  Neither a catalog entry nor a cached listing proves an inferable model.

**Critical upstream discovery:** Arduino's model-listing API
(`ModelsIndex.listModels() -> Handlers.getModelsInfo() -> runListAction()`)
actually starts a `models-downloader` Docker container. Therefore
clicking the AI Models screen / calling the API may launch a temporary
container. This is different from passively reading file metadata.
This check intentionally **does not call the listing API**.

One-time probe checks only exact default-path directory types, for
non-bookkeeping entries (bounded), download marker, metadata-record
presence and cache listing presence. It does not open/read user files,
read contents of model weights, export directory names, or print secrets.

**No-go interpretation:** If the expected model directory and payload
are present with no download marker, this is at most
`filesystem-model-candidate-not-inference-proof`.
It does *not* prove valid hashes, file completeness, App Lab container
mounts, DSP/NPU compatibility, or concurrent GenieX/ASR model load.
If absent, it only establishes absence from the *default* model path;
`MODELS_PATH` can change it. The App Lab process itself remains untouched.

Keep PR DRAFT, no microphone or App Lab/Genie startup.

## Actual host result (single pass)

Run: https://github.com/Harrokk/Myai/actions/runs/39955460757
Executed source SHA: `794e7ce1b5a3961f00b07b43055a852b94a016ae`
Completed **SUCCESS** with zero audio, model, Docker or service changes.

- Default Arduino model root **exists**.
- Subrepository `audio-analytics/asr` **not present** at default root.
- Exact quantized Whisper Small directory **not present** at default root.
- Default-root `models.yaml` materialized listing **not present**.
- Both production MyAI and GenieX systemd services remained **active**.
- Status: `no-complete-model-evidence-at-default-path`.

This is evidence of **absence at the documented default model path**,
not proof of universal absence or failure to support Swedish. The
Arduino CLI's `MODELS_PATH` environment override has **not** been
inspected. Also note the cached Docker image containing the ASR service
is distinct from its 343MB model artifact; a cached audio image does
not contain or attest the model.

**Next action requiring explicit user approval**: inspect App Lab's
own configured model location without exposing environment secrets or
install/load the official model using supported Arduino tooling, then
verify the correct USB microphone mapping in App Lab and run one
separately approved physical ASR test. No unofficial downloads, no
second Qwen LLM instance and no production config changes.
