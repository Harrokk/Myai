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

## Actual VENTUNO read-only result

One-shot job: https://github.com/Harrokk/Myai/actions/runs/39953928159
Source HEAD for job: `b80fcb24f3ce4ae0777093f351460b657ec70732`.
Completed **SUCCESS**, no audio I/O, model loading, Docker exec or
installation. Sanitized results:

- Arduino App CLI binary: **present**; `arduino-app-cli` Debian
  package: **installed**.
- Official Arduino Apps folder and CLI metadata folder: **present**.
  Custom-model folder also present (this is **not** evidence
  `whisper-small-quantized` is installed).
- Docker image listing readable: **yes**; cached
  `arduino/app-bricks/` image: **present**; cached audio service
  image matching `audio-analytics` or `genie-audio`: **present**.
- No currently running Arduino audio-analytics or genie model-runner
  container observed in the image listing at the time checked.
  There was no matching cached dedicated `genie-models-runner`
  image observed. This says nothing about the already active MyAI
  GenieX systemd service, which **remained active**.
- Both `myai-ventuno.service` and `myai-geniex.service` remained
  active.

**Still NOT attested**: installed Whisper Small model, Arduino App Lab
container audio-device mappings, live ASR backend startup and actual
concurrent GenieX/NPU inference. No reason to install a second LLM:
the original voice integration goal is to reuse MyAI's existing Qwen3.

The path to a meaningful live test is a separate **operator-supervised
App Lab readiness check of its downloaded ASR model and container's
ALSA mapping**, followed only after explicit new consent by a single
physical microphone session. The installed stack inventory does not
justify enabling audio, automatic app startup, or network listeners.
