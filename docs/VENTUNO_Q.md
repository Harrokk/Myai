# MyAI on Arduino VENTUNO Q

This note describes the current migration path for Arduino VENTUNO Q / Qualcomm Dragonwing IQ-8275.

## Current safety model

The repository keeps the Windows/Ollama configuration as the default.

The VENTUNO profile is selected explicitly:

```bash
export MYAI_SETTINGS=config/profiles/ventuno_q.json
```

or by running:

```bash
bash scripts/start_ventuno.sh
```

The VENTUNO profile currently:
- selects GenieX for the main LLM
- prepares Qwen3-4B-Instruct-2507
- enables LLM response streaming
- enables microphone release/handoff before heavy inference
- keeps voice input/output globally disabled until hardware validation
- keeps VLM disabled until camera/NPU validation
- enables the VENTUNO platform profile but keeps STM32 RPC disabled
- keeps all STM32 RPC writes disabled
- contains empty RPC method allowlists

## Planned local AI services

Main LLM:

```text
ai-hub-models/Qwen3-4B-Instruct-2507
```

Local GenieX endpoint:

```text
http://127.0.0.1:18181/v1
```

Planned VLM:

```text
qualcomm/Qwen3-VL-4B-Instruct
```

The VLM remains disabled until it is verified on the actual board.

## Read-only preflight

Before starting MyAI on real VENTUNO hardware:

```bash
python3 scripts/ventuno_preflight.py
```

The preflight does not:
- call the STM32
- write GPIO
- actuate hardware
- run LLM/VLM inference

It checks the runtime profile, Linux ARM64, GenieX CLI, local endpoint configuration, Arduino Router Bridge availability, the Router Unix socket and RPC write policy.

## GenieX preparation

When the physical board is available, use the Qualcomm-supported GenieX installation for that image/runtime, then pull the configured model:

```bash
geniex pull ai-hub-models/Qwen3-4B-Instruct-2507
geniex serve
```

Do not automatically upgrade GenieX/QAIRT on a validated MyAI installation. Record and pin the versions that pass the hardware test.

## STM32 / Arduino Router

MyAI uses the official Python bridge package:

```bash
python3 -m pip install -r requirements-ventuno.txt
```

The default Router transport is the protected local Unix socket:

```text
/var/run/arduino-router.sock
```

MyAI's wrapper is fail-closed:
- RPC must be explicitly enabled
- write RPC must be separately enabled
- read and write method names have separate allowlists
- no raw arbitrary method call is exposed as a natural-language tool

The first physical RPC test must be read-only. GPIO/motor writes are deferred until the MCU-side watchdog and explicit safe methods are verified.

## Voice resource handoff

On VENTUNO Q, the profile can stop/release the microphone stream before the LLM/VLM phase and wait 1.5 seconds before inference. The microphone is restarted afterwards.

This keeps listening/ASR and heavy model wake-up from unnecessarily competing for the same platform resources.

The existing `faster-whisper` path remains a fallback. A Qualcomm/Arduino-accelerated Whisper provider is intentionally not hard-coded until a stable documented API has been verified on the physical VENTUNO software image.

## Physical validation boundary

CI validates architecture, parsing, fail-closed policies, streaming, routing and state transitions. It cannot validate:
- Hexagon NPU performance
- QAIRT model compatibility
- GenieX long-duration stability
- real microphone/STT latency
- VLM camera quality
- STM32 Router timing
- temperature, power or throttling
- actual peripheral behavior

Those checks begin only when VENTUNO Q hardware is available.
