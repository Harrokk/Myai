# Read-only Arduino App Lab installation inspection — October 23, 2026

After PR #364 verified host ALSA USB capture pair 1:0, >=10 GiB
available RAM and active MyAI/GenieX services, the remaining useful
non-invasive question is whether App Lab and its native image stack
already exist on the *board*.

A one-time GitHub Action will query only command presence, dpkg package
metadata, whether documented directories exist, and `docker ps` /
`docker image ls` **listing-only** metadata (if the current runner user
is authorized to query Docker). Output is intentionally just category
flags; **no container names, model names, command lines, serial numbers,
environment variables, volumes, mount contents, device node opens,
Docker exec/inspect, network probes, or transcript**.

Doc basis: https://github.com/arduino/arduino-app-cli/blob/main/docs/user-documentation.md
documents `/home/arduino/ArduinoApps`,
`/var/lib/arduino-app-cli`,
`/home/arduino/.arduino-bricks/models` (the latter only *custom*
models, **not** a trustworthy indicator for built-in Whisper).
The first-party Arduino App Lab ASR Brick uses
`whisper-small-quantized` and targets `audio-analytics-runner`,
and the built-in Qwen3-4B LLM Brick uses a distinct
`genie-models-runner` container. The MyAI production GenieX API at
`127.0.0.1:18181` does not imply App Lab is connected to it.

Interpret results **conservatively**: presence of an App Lab CLI binary
or Docker image does not establish that App Lab is currently running,
its model is downloaded, that the ASR Brick can access the physical
microphone in its namespace, or that a second Qwen process can run
beside MyAI GenieX. An absent Docker listing due to permissions is
**inconclusive**, not proof of absence.

Do not launch App Lab, load Whisper, operate microphone/speaker,
stop any service, install packages, or alter host/container networking
without separate authorization. Any physical test still needs a new
single-use explicit approval. Keep DRAFT and NO-GO for main.
