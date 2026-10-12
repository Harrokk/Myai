# VENTUNO Q — QAIRT/HTP profiling status

Last verified: 2026-10-12. Development branch: `dev/routing-boundary-followup`.

## Observations (GitHub Actions, self-hosted VENTUNO Q)

- The live GenieX service responds through `127.0.0.1:18181/v1` and generates nonempty responses.
- GenieX has mapped `libQnnHtp.so`, `libQnnHtpV75Stub.so`, `libQnnSystem.so` and `libcdsprpc.so`.
- GenieX has an open descriptor to `/dev/fastrpc-cdsp-secure`.
- Qualcomm `remoteproc` exposes three running remote processors.
- Only GPU `devfreq` telemetry was found; the checked paths expose no separate NPU busy/frequency counters.
- Linux trace event inventories are permission restricted for the self-hosted runner; **do not** elevate runner privileges just for diagnostics.
- `qnn-net-run`, `qnn-profile-viewer`, `qnn-context-binary-utility`, and `snpe-net-run` are already installed in `/usr/bin`.
- QAIRT's `libQnnHtpProfilingReader.so`, `libQnnHtpOptraceProfilingReader.so`, `libQnnChrometraceProfilingReader.so` and `libQnnJsonProfilingReader.so` are available in the bundled GenieX QAIRT HTP directory.
- The installed `qnn-net-run --help` accepts `--profiling_level` and `--profiling_option` (`optrace`); `qnn-profile-viewer --help` accepts `--input_log` and `--reader`.
- The installed `geniex serve --help` exposes `--compute`, `--qairt-lib` and `--log`; **no direct QNN profiling flag** was observed in the relevant help lines.

Supporting workflow: `.github/workflows/ventuno-diagnostics.yml`.
Checks above ran without changing the installed GenieX service or changing clocks/driver parameters.

## Profiling preflight (2026-10-12)

Implemented in `scripts/ventuno_qairt_profile_preflight.py` and run on VENTUNO
by the diagnostic workflow; pure functions have regression tests.

Observed from the live device:

- API model: `qualcomm/Qwen3-4B-Instruct-2507:W4A16`.
- Physical usable memory exposed to Linux: 15,285 MiB total, **6,516.7 MiB available**
  at the moment of sampling. These numbers vary with system load.
- GenieX process count: one; its **host RSS: 447.5 MiB**. This is **not**
  the total memory footprint of the HTP/NPU graphs or shared allocations.
- The known GenieX cache root contains **four `.bin` files**; sizes of the
  largest files: 1,013.7, 742.1, 632.2 and 632.2 MiB. No cached GGUF was found
  in that checked root. The inspection reads metadata only, not binary contents.
- The QNN viewer, net-run and context utility are present.
- The `geniex serve --help` command did not expose a QNN profile-session flag.
- Full regression suite: **874 passed**. Preflight and services checks also passed.

### Decision / safety gate

**Do not** start another instance of the installed 4B QAIRT model while live
GenieX remains active merely to measure NPU utilization. Linux host RSS does not
bound the additional memory used by NPU graph loading; the available-memory
number alone does not establish safe concurrent capacity.

The existing model cache's context binaries are not by themselves a reproducible
`qnn-net-run` profiling scenario. Such a run also needs compatible graph
selection, tensor shapes and input-list files. For **optrace/per-layer** profiling
of a serialized QNN context, Qualcomm's profiling guide additionally requires
generating an optrace-instrumented context binary. No attempt was made to rewrite
or load the cached binaries.

A direct NPU timing profile of **this model** therefore remains pending. Next
allowed progress without a maintenance window is read-only identification of
the graph/input metadata and an exact, reproducible profile procedure. A model
restart or temporary service pause must be separately agreed and must include
a health-check and rollback plan.

## Assessment

The NPU route is strongly supported by the running QAIRT model and the HTP/FastRPC process evidence. Qualcomm documents that **GenieX QAIRT models run on the NPU only**. This is a runtime-path conclusion, **not** a direct measurement of HTP execution cycles, utilization percentage or per-layer timing.

The presence of QNN profiling tools does **not** imply that those tools can attach to an already-running GenieX process. QNN profile sessions need to be enabled by the process initiating model execution or by a separate compatible `qnn-net-run` invocation.

## Next safe profiling stage

1. Review whether the installed GenieX/QAIRT interface has an explicit, supported profiling flag/API for its existing model service (without changing service configuration).
2. If not, prepare an **isolated** reproducible QNN profiling experiment using a compatible model/context and correctly shaped inputs, with `--profiling_level basic` or `detailed` and `qnn-profile-viewer`. Verify the model format and available memory before trying to load anything.
3. Avoid a second concurrent load of the Qwen3-4B QAIRT model on the 16 GB VENTUNO Q while the live MyAI/GenieX services are active; it may cause memory pressure or disrupt the assistant.
4. A temporary service-stop / maintenance window or alternate smaller test model would require an explicit deployment/test decision. Do not silently stop services, alter live model configurations or give the runner root access.
5. Report actual HTP profile events/cycles separately from host-side latency and CPU time. If no direct measurement is available, mark it as inconclusive.

## Vendor references

- GenieX QAIRT is NPU-only: https://github.com/qualcomm/GenieX/blob/main/docs/en/get-started/platforms.mdx
- QNN HTP profile definitions: https://docs.qualcomm.com/nav/home/api-rst_file_include_QNN_HTP_QnnHtpProfile_h.html?product=924033590759186372
- QNN profiler tooling guidance: https://github.com/qualcomm/qai-appbuilder/blob/main/tools/skills/qai-runner-skill/references/profiling.md

## Profiling-method verification and baseline (2026-10-12)

The user authorized a controlled temporary pause of MyAI/GenieX **once the test
method was verified**. We deliberately did **not** stop services during this
stage: the preconditions needed for direct QNN profiling of the existing model
are not yet met. The tests therefore ran safely against the live GenieX API.

Read-only feasibility inspection:
- `qnn-net-run --help` supports `--retrieve_context`, `--input_list`,
  `--profiling_level` and `--profiling_option`.
- `qnn-context-binary-utility --help` exposes `--context_binary`.
- GenieX `infer --help` and `serve --help` exposed no direct QNN profile
  capture option in their relevant flag inventories.
- The installed model's cache contains `geniex.json`,
  `htp_backend_ext_config.json`, and `config.json` alongside four large
  `.bin` files; the probe printed only structural key names (never values).
- These do **not** supply a verified `qnn-net-run` input-list, graph
  selection, tensor shapes or a documented way to enable an in-process QNN
  profile session for the live GenieX server.
- See `scripts/ventuno_qnn_profile_feasibility.py`, with unit tests.

### Existing server's measured throughput (not HTP occupancy)

The OpenAI-compatible GenieX response includes numeric `usage` and `timings`
fields, so `scripts/ventuno_geniex_benchmark.py` ran **three serial**
128-token responses using the already-running server (no second model).
A particular 2026-10-12 test yielded:

| Run | Prompt token/s | Decode token/s | Wall time (s) |
|---|---:|---:|---:|
| 1 | 862.50 | 16.21 | 8.08 |
| 2 | 459.00 | 16.38 | 7.99 |
| 3 | 373.98 | 14.75 | 8.89 |
| **Median** | **459.00** | **16.21** | — |

All three generations reported 128 generated tokens. Load, context state,
sampling overhead and warm-up can affect numbers. These are **end-to-end
model timings**, not actual HTP cycles, NPU utilization or per-layer timing.
All original MyAI/GenieX services remained active. **880 regression tests
passed** for this code state.

### Fail-closed go/no-go for a maintenance profiling window

A temporary stop of the active services is **NO-GO** until:
1. A QNN profiling command is demonstrated from an independent, compatible
   context and valid input-list, or a supported GenieX in-process capture
   method is found. The cached 4B model cannot be assumed runnable in
   `qnn-net-run` with arbitrary text input.
2. Additional memory/temporary disk requirements and executable timeouts
   are measured without concurrent loading of the 4B model.
3. An explicit rollback procedure is prepared: record unit states, stop
   dependent `myai-geniex-watchdog` and `myai-ventuno` before
   `myai-geniex`, carry out one bounded profiling test, then restart the
   original services and verify both the GenieX `/v1/models` API and MyAI
   heartbeat. Always restore services on failure/interruption; preserve
   configs and model files unchanged.
4. The operator has a safe, **authorized** way to control those systemd
   services; do not grant GitHub runner broad sudo privileges.
5. A recovery path exists if QNN blocks or the OS is rebooted.

Neither a stop nor any change to the live model/service was attempted.
Never interpret success of a preflight or throughput benchmark as a
successful direct HTP profiling session.


## QNN context metadata and synthetic-input readiness (2026-10-12)

A resource-bounded inspection of a **632.2 MiB** context binary in the
existing GenieX cache succeeded using the installed
`qnn-context-binary-utility --context_binary ... --json_file ...` tool.
The probe uses a temporary output folder, a 22-second timeout and Linux
memory/CPU/file-size limits. It never starts `qnn-net-run`, loads a second
LLM into GenieX or changes the live systemd units.

The binary reports:

- **10 QNN graphs**.
- Every graph has **28 inputs** and **25 outputs**.
- In every graph, the input types are **24
  `QNN_DATATYPE_UFIXED_POINT_8`** tensors and **4
  `QNN_DATATYPE_UFIXED_POINT_16`** tensors.
- No input tensor has unresolved dimensions or native byte length.
- Estimated total native input-buffer sizes across the 10 graphs range from
  approximately **9.78 MiB to 95.99 MiB**, depending on graph.
- Per-graph metadata reports `sharedWeightsSize = 614,834,176` bytes
  (about 586.35 MiB) in this serialized context. The repeated figure
  **must not be added across graphs as independent memory allocations**.
  These values describe the serialized graph structures and do not provide
  a direct measurement of live HTP utilization or allocations.

`scripts/ventuno_qnn_context_metadata.py` now generates a **temporary,
synthetic, native-dtype input fixture** for the smallest eligible graph,
validates sizes and the QNN `tensor_name:=raw_file` input-list structure,
and automatically deletes all generated input files. On the VENTUNO,
**graph index 5, 28 inputs, 9.78 MiB, 29 temporary files** passed this
validation. Nine focused preflight tests and the regular diagnostic
systemd tests passed.

**Critical limitation:** The fixture has zero-initialized quantized input
buffers. It is suitable for interface/size validation, **not**
semantically valid Qwen generation or an accuracy check. No
`qnn-net-run` execution has been performed. The current context
contains 10 graphs and the model bundle has four separate context
binaries; the exact multi-graph / weight-sharing load and selection
procedure must be validated before any attempt to execute a graph or
interrupt live GenieX.

For native QNN input files, see:
https://github.com/google-ai-edge/LiteRT/blob/main/litert/vendors/qualcomm/doc/LITERT_QNN_NATIVE_RUN.md

For context metadata utility usage, see:
https://github.com/qualcomm/qai-appbuilder/blob/main/tools/convert/dlc2bin/README.md

### Next controlled execution gate

A maintenance-window trial can be considered **only after** the installed
`qnn-net-run` graph-selection and context/weight-sharing flags are
verified against the bundled QAIRT v2.45 runtime, including any required
backend configuration and `ADSP_LIBRARY_PATH`. If there is no supported
way to execute a single chosen graph without all the other contexts,
stop and use a smaller independent profiling fixture instead. Never
silently interrupt the live model just to try unknown flags.

A valid QNN profiling run must produce a profiling log that
`qnn-profile-viewer` can read; otherwise report **profiling inconclusive**.
Keep duration/memory limits, ensure the watchdog does not restart a
maintenance-stopped service, restore services on every exit path, and
verify GenieX's API plus MyAI heartbeat after restoration.

## QNN graph-selection CLI gate (2026-10-12)

A dedicated fail-closed check was added as `scripts/ventuno_qnn_cli_gate.py`, with
six focused tests in `tests/test_ventuno_qnn_cli_gate.py`. It executes only
`qnn-net-run --help`, without loading a model, touching services, or reading
model data.

On the VENTUNO Q, the installed CLI exposed `--backend`,
`--retrieve_context`, `--input_list`, `--profiling_level`,
`--profiling_option`, `--config_file` and native-input flags.
It exposed **no explicit graph-selection flag** from the checked common
spellings. All six gate tests and the VENTUNO diagnostics passed.

**Gate result: NO-GO** for a direct profiling attempt using an arbitrarily
chosen graph from the cached multi-graph Qwen context. Absence of a CLI flag
does not rule out supported graph selection through QNN configuration or the
vendor API; this has not yet been demonstrated.

Do not interrupt the live GenieX service or invoke `qnn-net-run` against
these cached contexts based solely on the synthetic input preflight.
The next safe investigation is to verify graph selection and weight sharing
against the installed QAIRT v2.45 documentation or vendor source, and use a
separate, smaller profiling fixture if single-graph execution is unsupported.
The profile status remains **unverified**.

## Multi-graph skip and HTP weight-sharing verification (2026-10-12)

New device-side checks on the self-hosted VENTUNO Q confirmed:

1. The **installed** `qnn-net-run --help` explains that `--input_list`
   accepts comma-separated per-graph input-list entries and the literal
   `__` to **skip execution** of a graph. There is still no explicit
   graph-name selector among the inspected CLI flags. This reconciles the
   previous "no graph selector" result: the CLI has a potential skip-based
   selection route, but this is not a demonstrated runtime execution
   of a chosen cached GenieX graph.
2. `scripts/ventuno_qnn_cli_gate.py` now has a pure,
   fail-closed `build_single_graph_input_list_arg()` helper. It validates
   graph count/index and safe argument structure without running QNN.
   A synthetic ten-graph plan selected index **5** and skipped the other
   **nine** positions. It does not establish that metadata index 5 matches
   the execution position of the same graph in the loaded context.
3. `scripts/ventuno_qnn_weight_sharing_inventory.py` searches only
   allowlisted, bounded cached HTP configuration files. Exactly **one**
   matching config was inspected and it **declared weight sharing enabled**.
   The output contains aggregate booleans/status counts only, never paths,
   other configuration values, model contents or credentials.
   **A cached declaration does not prove that the running GenieX service
   actually applied the setting**.
4. New focused tests for skip-plan construction and weight-sharing
   inventory passed on VENTUNO; the overall CI and diagnostics runs also
   completed successfully for their respective checked commits.

### Supported API versus unverified bundle execution

Qualcomm documents `QnnGraph_retrieve(context, graphName, ...)` for retrieving
a graph from a loaded/cached QNN context. HTP's context API defines
weight sharing and multi-context resource-sharing options. This SDK API
capability is separate from the CLI `__` selection syntax. Neither
feature proves that the **four linked GenieX context binaries** can be
loaded, selected and profiled independently by `qnn-net-run`.

Qualcomm's LLM onboarding documentation describes linking autoregressive
variants of model parts into shared-weight QNN contexts and having Genie
coordinate those parts. This is why treating a single cached context or an
isolated zero-filled graph as a complete Qwen3 LLM is unsafe.

The cached 4B context graphs' **28 inputs** include state-related tensors.
The synthetic native-dtype fixture is for file/shape checks only, **not**
a semantically valid token-generation step or an accuracy test.

**Safety decision remains NO-GO for model execution or service pause.**
The next gate is to establish, from vendor-compatible runtime
documentation/source and bounded metadata inspection, the exact
multi-context load order, graph-slot mapping, required backend
configuration and memory lifetime. Prefer an independent small
profiling fixture before attempting an installed 4B bundle trial.
A controlled maintenance-window experiment still requires a reviewed
restart/rollback procedure and explicit operational approval; do not
elevate the GitHub runner or interrupt GenieX automatically.

References:
- QNN `QnnGraph_retrieve`: https://docs.qualcomm.com/nav/home/api-rst_file_include_QNN_QnnGraph_h.html?product=924033590759186372
- HTP context weight sharing API: https://github.com/qualcomm/geniex-qairt-plugin/blob/main/qnn-api/include/HTP/QnnHtpContext.h
- QAIRT multi-graph input-list syntax: https://docs.radxa.com/en/dragon/q8b/app-dev/npu-dev/qairt-tools
- Qualcomm LLM compile/link and shared-weight contexts: https://github.com/qualcomm/ai-hub-models/blob/main/tutorials/llm/onboarding.md

## Four-context graph metadata inventory (2026-10-12)

A new read-only, bounded device-side inventory runs as
`scripts/ventuno_qnn_bundle_inventory.py` with regression coverage
in `tests/test_ventuno_qnn_bundle_inventory.py`.

The VENTUNO Q run completed successfully and inspected **all four** cached
QNN context binaries sequentially. For safety, the tool uses Qualcomm's
metadata-only utility, strict per-process CPU/address-space/file limits,
a timeout per context, a Linux available-memory threshold, temporary JSON
files deleted after reading, and an unambiguous four-binary/one-manifest gate.
It never starts `qnn-net-run` or a second GenieX instance, and logs no raw
model-file paths, graph names, tensor names, manifest values or generated
prompts.

Inventory slots are sorted by file size (then path) **for stable reporting
only**. These are not model execution slots:

| Inventory slot | Alias | Context MiB | Graphs | Inputs/outputs per graph |
| --- | --- | ---: | ---: | --- |
| 0 | A | 632.2 | 10 | 28 / 25 |
| 1 | B | 632.2 | 10 | 28 / 25 |
| 2 | C | 742.1 | 10 | 1 / 1 |
| 3 | D | 1013.7 | 10 | 28 / 25 |

The allowlisted `ModelFile`/`ExtraFiles` fields in `geniex.json`
referenced each candidate exactly once. The order in which those fields
yielded candidate references was **D, C, A, B** (inventory slots 3, 2, 0, 1).
This is **manifest reference order**, not evidence that GenieX actually
loads, invokes or frees contexts in that sequence. The four binaries
contain a total of **40 serialized QNN graphs**.

A cautious graph-IO comparison found potential directed matches
between contexts **C→A**, **A→B** and **B→D**, with 50 matching
input/output signature pairs for each candidate context-level link.
These matches use tensor name, QNN datatype and static dimensions
internally; the raw names are not logged. Name/shape matches alone do
not prove data transfer, tensor lifetimes, execution order, or successful
cross-context replay. No inferred link is a green light for profiling.

The inventory reports graph-name fingerprints to correlate metadata
without revealing model graph identifiers, and marks every graph's
runtime slot as **unverified**. It does not claim that the graph order
stored in serialized metadata corresponds exactly to
`qnn-net-run --input_list` graph ordering.

**Result:** Four-context inventory is complete at the structural
metadata level, but the runtime sequence, inter-context scheduling,
shared HTP weight lifecycle and exact graph-slot binding remain
**unproven**. The profiling/no-service-pause gate is unchanged.

CI evidence:
- Four-context diagnostics: https://github.com/Harrokk/Myai/actions/runs/38212086214
- Full regression suite for the inventory integration: **926 passed**,
  https://github.com/Harrokk/Myai/actions/runs/38212086166

### Next decision gate

Verify GenieX's documented QNN model/extra-context load and invocation
semantics, and determine whether any **non-inferential** startup or
profiling metadata can establish ordering. If a direct profiling
experiment later becomes necessary, first prepare a compatible small
standalone context with valid native inputs, safe resource limits,
service rollback and an explicit maintenance plan. No automatic
`qnn-net-run` execution against the cached Qwen3 contexts.

## GenieX context load-list configuration cross-check (2026-10-12)

Qualcomm's open-source GenieX QAIRT plugin, specifically
`core/src/llm/llm_spec_loader.cpp` in
`modelConfigFromDirectory()`, reads the ordered
`dialog.engine.model.binary.ctx-bins` array from `genie_config.json`
into `ModelConfig.model_paths` when the configuration is present.
For multi-engine bundles it chooses a target engine instead of mixing
target and draft contexts. When no context list is available, the
implementation has a separate lexically sorted `*.bin` fallback.
This makes **`genie_config.json` a more relevant source of model
context order than `geniex.json`'s `ModelFile`/`ExtraFiles`
download references**.

The safe inventory now parses just this allowlisted JSON structure,
matches every relative path to a previously discovered candidate, and
logs inventory slot numbers only. On the real VENTUNO Q it returned:

- Status: **complete-declared-order**.
- Listed context inventory slots: **[2, 0, 1, 3]**, or **C → A → B → D**.
- All four references were resolved uniquely.
- This configured order agrees with the previously observed
  candidate output/input tensor matches C→A, A→B, B→D.
- The separate `geniex.json` manifest reference order
  **[3, 2, 0, 1]** must **not** be used as an execution-order source.

**Interpretation:** We have verified the cached configuration's intended
context-list order and its consistency with structural data-flow
hints. We have **not** observed which loader implementation/version
the live GenieX process invoked, its graph execution schedule,
the exact mapping of metadata graph indices to execution input-list slots,
or actual NPU cycles. No process tracing, extra model load, service
interruption or privileged access was performed.

Upstream source (vendor):
https://github.com/qualcomm/geniex-qairt-plugin/blob/main/core/src/llm/llm_spec_loader.cpp

Read-only diagnostic step:
https://github.com/Harrokk/Myai/actions/runs/38212471426

**Maintenance profiling remains NO-GO** until an independently
reproducible, resource-bounded QAIRT profile method and rollback plan are
ready. Do not treat a four-item config list alone as permission to
stop production GenieX or execute one of the 4B cached contexts.

## Live GenieX backend attestation and vendor graph indexing (2026-10-12)

The new `scripts/ventuno_geniex_runtime_attestation.py` samples only
`systemctl show ... MainPID` and bounded read-only `/proc` fields for
the systemd-owned GenieX process (and its descendants). It **does not**
read raw process command lines, environment variables, model contents,
config values or credentials, and it does not attach to a process.

The successful VENTUNO Q diagnostics reported:

- `service_mainpid_present: true`, **one** GenieX process.
- `libQnnHtp.so`, `libQnnHtpV75Stub.so` and `libQnnSystem.so`
  mapped in that live process.
- `/dev/fastrpc-cdsp-secure` open by that process.
- `runtime_backend_evidence: true`.
- **`actual_context_order_proven: false`**,
  **`actual_graph_execution_proven: false`** and
  **`direct_htp_profiling_verified: false`**.

These are strong runtime process/backend association observations,
**not measured HTP accelerator utilization or proof of graph
execution on the NPU**. A library may be mapped without executing
its kernels, and opening FastRPC is not a layer-level profile.
A missing optional library in maps does not negate the positive
QNN/HTP/FastRPC observations.

The Qualcomm QAIRT plugin's
`QnnApi::createFromBinaryHtp()` parses each cached binary in
`cachedBinariesPathVec` index order, builds global graph records,
maps each graph to its source context, then creates HTP contexts
from binaries and retrieves each graph by name via `graphRetrieve`.
For this observed **C → A → B → D** `ctx-bins` declaration and ten
metadata graphs per context, the conservative vendor-code **candidate**
global graph intervals are:

| Declared context | Candidate global graph indices |
| --- | --- |
| C | 0–9 |
| A | 10–19 |
| B | 20–29 |
| D | 30–39 |

The code now derives these ranges only when all four contexts have
complete, uniquely resolved config references and equal valid graph
counts. Tests reject malformed or ambiguous mappings. The installed
GenieX executable has **not** been tied to an exact build of that
upstream source and the graph list may be scheduled by token/decode
stage rather than in index order. In particular, this mapping **does
not** establish how `qnn-net-run --input_list` numbers graphs.

Vendor reference:
https://github.com/qualcomm/geniex-qairt-plugin/blob/main/qnn-api/src/QnnApi.cpp

Device run:
https://github.com/Harrokk/Myai/actions/runs/38213095650

### Standalone, nonproduction NPU profiling plan — currently gated

The installed `qnn-net-run --help` offers the usual
`--retrieve_context`, `--profiling_level`, native-I/O flags, and
**`--retrieve_context_list`**; the latter alone provides no proof
that it understands GenieX's four linked, weight-sharing Qwen3
context binaries. The CLI's `__` graph-skip convention also must
not be mistaken for the QAIRT plugin's global graph numbering.

For a **new, small, independent, known-good QAIRT context** (not any
of the active GenieX cache files), a future maintenance test can
follow this *illustrative, deliberately incomplete* form, only once
its real context and native input-list are validated:

```bash
# REFERENCE ONLY -- do not execute with production cached Qwen contexts.
qnn-net-run --backend /path/to/libQnnHtp.so \
  --retrieve_context /separate/test/context.bin \
  --input_list /separate/test/valid_input_list.txt \
  --output_dir /separate/temporary/output \
  --use_native_input_files --use_native_output_files \
  --profiling_level basic

# Only if qnn-net-run produced a valid profile log:
qnn-profile-viewer --input_log /separate/temporary/output/qnn-profiling-data.log
```

This is **not a ready-to-run command**: paths are placeholders, and
required QAIRT/HTP version compatibility, DSP-side shared libraries,
environment, valid input tensors, free-memory budget, context model
provenance, profiling semantics and result correctness need verification
first. Limit runtime, address space, disk writes, and one-context
memory use. First test a tiny standalone profile without stopping
production, *only if* it fits proven spare capacity and a compatible
isolated sample is available.

A controlled 4B production-cache profiler remains **NO-GO** until
an independently verified multi-context replay method and explicit
service recovery/maintenance authorization exist. Never automatically
load a second 4B Qwen model, restart the production GenieX service,
elevate runner privileges, or claim that API token/s proves NPU cycles.

Relevant native tensor I/O format:
https://github.com/google-ai-edge/LiteRT/blob/main/litert/vendors/qualcomm/doc/LITERT_QNN_NATIVE_RUN.md

## Independent tiny QAIRT profiling fixture: toolchain preflight (2026-10-12)

A bounded, **read-only** probe now runs in the self-hosted diagnostics:
`scripts/ventuno_qnn_microprofile_inventory.py` plus twelve focused
safety/privacy regression tests. It searches only configured SDK example
directories for files no larger than 32 MiB, following no symlinks; it
does not open model payloads, download files, run a converter, start QNN
inference, print discovered paths or alter production services.

**Measured on VENTUNO Q:**

| QAIRT component | Availability on VENTUNO |
| --- | --- |
| `qnn-net-run` | Available |
| `qnn-profile-viewer` | Available |
| `qnn-context-binary-utility` | Available |
| `qnn-context-binary-generator` | Available |
| `qnn-onnx-converter` | **Not on PATH** |
| `qnn-model-lib-generator` | **Not on PATH** |
| `qnn-dlc-quantizer` | **Not on PATH** |
| Small independent SDK sample model (searched roots) | **None found** |

One configured SDK root was present; 2 directories and 33 files were
inspected without hitting traversal limits. Absence from **those roots**
does **not** establish that no compatible small example exists anywhere
else on disk. The active GenieX 4B cache was **not** considered a
standalone test candidate.

The inventory result is:
`no-go-separate-prepared-sample-required` and
`npu_profiling_go: false`. Device diagnostics:
https://github.com/Harrokk/Myai/actions/runs/38217969530

### Host-only preparation candidate

`scripts/prepare_tiny_qnn_host_sample.py` defines a **small, fixed,
deterministic ONNX graph** with 1 × 1 × 8 × 8 floating-point input,
Q/DQ quantization nodes, a 3 × 3 convolution and ReLU. It is an
**ONNX source fixture**, not a QNN serialized HTP binary.
It writes an ONNX file, 256-byte floating-point input file,
draft `input_list.txt` and a machine-readable manifest that sets every
QNN conversion/runtime/profiling result to **false**.

The creation step is intended **only for a separate development host**:

```text
# On a separate development PC with Python and the onnx package:
python scripts/prepare_tiny_qnn_host_sample.py --output-dir ./tiny_qnn_fixture

# It creates:
#   tiny_qdq_conv.onnx
#   input.raw
#   input_list.txt
#   fixture_metadata.json
```

The actual ONNX filename generated is **`tiny_qdq_conv.onnx`**
(`QDQ`, quantize/dequantize). It is deliberately not a runnable
HTP command. The generator refuses ARM device execution, refuses to
overwrite an existing directory, and refuses model-cache/runtime
destinations. All generated inputs are synthetic; no prompts or user
data are used.

**Important:** The on-device test environment has no Python `onnx`
package, so CI validates only the generator's standard-library
safety/data logic. The optional ONNX export-and-`onnx.checker` tests
were **skipped**, not passed. The full test suite showed
**964 passed, 2 skipped**; end-to-end ONNX graph validation awaits a
separate host with the `onnx` package.

After creating the ONNX file on a separate host with a **compatible
QAIRT 2.45 toolchain**, the remaining controlled preparation stages are:

1. Use the matching `qnn-onnx-converter` to convert the tiny ONNX/QDQ
   graph to QNN-generated source and weights. Check that the installed
   converter actually supports these ops and quantization; do not
   assume a successful conversion or HTP placement.
2. Use the matching `qnn-model-lib-generator` and target toolchain
   to produce a model library; prepare a standalone **HTP v75**
   context with compatible `qnn-context-binary-generator`.
   Confirm architecture, hardware backend, stub/skel and backend
   extension config rather than guessing flags.
3. Inspect the resulting context with
   `qnn-context-binary-utility`. Require an expected small, independent
   single-graph model and exact native input tensor names, shapes,
   datatypes and quantization; the generated ONNX float input file
   **cannot automatically be assumed compatible** with the converted
   QNN native input datatype.
4. Only with a verified, independent context and valid input set:
   review a bounded, isolated `qnn-net-run --profiling_level basic`
   experiment. Protect memory, HTP resource contention, transient
   storage and live GenieX responsiveness. A successful inference
   alone is not proof of HTP execution; collect and inspect actual
   QNN profiling logs and backend placement evidence.

No QNN generation, NPU execution, profiler collection or production
GenieX interruption was performed by this stage.

Source guidance:
- Qualcomm QAIRT HTP context generation and profiling:
  https://docs.qualcomm.com/nav/home/htp_auto_tutorial_3_la_gvm.html?product=924033590759186372
- Native QNN input dtypes and `qnn-net-run` usage:
  https://github.com/google-ai-edge/LiteRT/blob/main/litert/vendors/qualcomm/doc/LITERT_QNN_NATIVE_RUN.md

## Host ONNX microfixture export and numerical verification completed (2026-10-12)

The **independent GitHub-hosted x86_64** workflow now successfully exports
the synthetic `tiny_qdq_conv.onnx` from
`scripts/prepare_tiny_qnn_host_sample.py` and checks it using
`scripts/verify_tiny_qnn_host_sample.py`.

Workflow: https://github.com/Harrokk/Myai/actions/runs/38219747737

- Environment: Ubuntu 24.04, Python venv, pinned
  `numpy==1.26.4`, `onnx==1.17.0`,
  `onnxruntime==1.20.1`, `pytest==8.3.5`.
- Host-specific tests: **12 passed**, no skipped host tests.
- `onnx.checker.check_model(full_check=True)`: **passed**.
- `onnxruntime` with **CPUExecutionProvider only** executed the model;
  results exactly matched an independent NumPy Q/DQ + 3×3 Conv + ReLU
  calculation within `atol=1e-7`.
- Output tensor: `float32 [1, 1, 8, 8]`, with **27 nonzero values**
  out of 64. The originally too-coarse output quantization was corrected
  to `y_scale=1/512`, preventing an all-zero test result.
- Raw input: 256 bytes, deterministic `float32 [1, 1, 8, 8]`.
- Actual ONNX size: **608 bytes**.
- ONNX SHA-256:
  `e347c2197d3006e32eec580c85a6eb2c0cbd460150d4a72ae80e9d78573b94f9`.
- CPU reference output SHA-256:
  `b4dc4e231b1f89b8675bff35d9c9eb896b773f038b681af1e05ab43b4dfe76b7`.
- A four-file verified synthetic sample bundle (ONNX, raw input,
  input list, provenance JSON) was reassembled and SHA-256 verified
  from the successful job's bounded export log.
  Bundle SHA-256:
  `f7a74fae41a2c0373b7934e07ca4956f9c4324cd51d7915e9777c008771a2e11`.
  The model source and host workflow remain checked into the development
  branch, so the fixture can be rebuilt independently.
- Complete VENTUNO test run for this code state: **967 passed, 4 skipped**.
  The skipped cases require host-only ONNX packages and never ran on
  the live ARM device.

**Three problems were detected and corrected during actual host testing:**
an escaped newline unintentionally commented out the requested ONNX IR 8
assignment; the older ONNX `ReferenceEvaluator` did not implement
the model's opset 13 DQ operator; and a directly invoked validation script
lacked its Python package import path. Tests now run through ONNX Runtime
CPU and invoke scripts as Python modules. A first version of the host workflow
failed before job startup when using `actions/upload-artifact`; the
working workflow deliberately uses no upload action and exposes only a
strictly bounded, synthetic archive in its build logs.

**Critical distinction:** All of this is **ONNX model correctness on a
host CPU**, not proof of conversion to QAIRT 2.45, validation of converted
QNN native quantized tensor encodings, context construction, HTP v75 graph
placement or direct NPU profiling. No QNN converter, `qnn-net-run`,
`qnn-context-binary-generator` or production GenieX service was invoked
by the hosted workflow.

### Next gated QAIRT conversion step

A **separate host** must have an appropriately licensed and compatible
QAIRT 2.45 toolchain with ONNX converter/model-library generator, or a
validated alternative `qairt-converter`/DLC route. The VENTUNO device
currently has `qnn-context-binary-generator` and runtime tools but
not the ONNX converter or model-library generator on its PATH. The tiny
ONNX bundle is safe for *host conversion research* only; it is not yet
ready for native `qnn-net-run` on VENTUNO Q.

Conversion should not be automated against production without:
verified SDK version and target ABI, verified HTP v75 graph support,
correct output tensor quantization/input mapping, an independent small
context, memory budget, and a bounded profiling/recovery plan. No automatic
service interruptions or second 4B model loads.

## QAIRT 2.45 converter and direct-DLC route validation (2026-10-12)

An additional bounded metadata-only probe runs on the real VENTUNO Q:
`scripts/ventuno_qairt_converter_inventory.py`, with
`tests/test_ventuno_qairt_converter_inventory.py`. It explicitly
tests the installed `qnn-context-binary-generator --help` and
`qnn-net-run --help`, and scans allowlisted SDK directories
without reading model files or displaying private paths.

**Measured device results:**

- Two SDK-related roots inspected, three directories and 34 files;
  scan finished without limits or read errors.
- SDK/backend library names visible:
  `libQnnHtp.so`, `libQnnHtpV75Skel.so`,
  `libQnnHtpV75Stub.so`, `libQnnSystem.so`.
- `qnn-onnx-converter` and `qnn-model-lib-generator`
  **not found on PATH or in these bounded roots**.
- `qnn-context-binary-generator --help` supports
  **`--dlc_path`**, `--model`, `--backend`,
  `--binary_file`, `--config_file` and profiling flags.
  `qnn-net-run --help` also contains `--dlc_path`.
- Status: **`dlc-loading-option-present-but-dlc-creation-unverified`**,
  not a positive executable NPU profile.

Qualcomm documentation describes two relevant host preparation approaches:
1. ONNX → `qnn-onnx-converter` → model source/weights →
   `qnn-model-lib-generator` → HTP context generator.
2. An independently prepared, compatible QNN DLC →
   `qnn-context-binary-generator --dlc_path` → context.

Neither method is executable at present with the accessible files:
**there is no verified small QNN model library, standalone converted
DLC, nor locally available ONNX/DLC conversion toolchain.** The
presence of the `--dlc_path` flag alone is not evidence that the
ONNX file is a DLC or that the HTP supports its operators. The live
Qwen3 context files must **not** be re-used.

Source references:
- Qualcomm QNN development workflow / Windows native and WSL host
  toolchain: https://docs.qualcomm.com/nav/home/QNN_general_overview.html?product=924033590759186372
- Qualcomm HTP context generator examples:
  https://docs.qualcomm.com/nav/home/htp_auto_optimization.html?product=924033590759186372
- Qualcomm multi-stage HTP context generation and `--dlc_path` support:
  https://docs.qualcomm.com/nav/home/lora_v3_overview.html?product=924033590759186372

VENTUNO Q successful device diagnostic:
https://github.com/Harrokk/Myai/actions/runs/38220630410

### Ready-to-check SDK acquisition gate for a separate development host

`scripts/qairt_host_toolchain_preflight.py` provides a **read-only**
toolchain/fixture identity check for a separately installed, authorized
QAIRT SDK. It supports x86_64 Linux and Windows SDK file layouts;
some Windows distributions place `qnn-model-lib-generator` under
`aarch64-windows-msvc` rather than
`x86_64-windows-msvc`. It checks filenames only, never executes
SDK tools.

Example on a development Windows PC after legitimately installing
the matching QAIRT SDK and placing the verified synthetic ONNX fixture
in its own nonproduction directory:

```powershell
python -m scripts.qairt_host_toolchain_preflight --host windows `
    --sdk-root 'C:\Path\To\Authorized\QAIRT\SDK' `
    --fixture-dir 'C:\Path\To\tiny_qnn_fixture'
```

Example for x86_64 Linux / WSL:

```bash
python3 -m scripts.qairt_host_toolchain_preflight \
  --host linux \
  --sdk-root /path/to/authorized/qairt-sdk \
  --fixture-dir /path/to/tiny_qnn_fixture
```

Before a conversion can be approved, confirm the SDK is genuinely
compatible with the device's **QAIRT 2.45** runtime, verify target ABI,
QNN HTP v75 backend and matching DSP skeleton, validate operator and
quantization support, then run a separately bounded conversion and
inspect the resulting graph. No SDK binaries are bundled in MyAI.

The same preflight ran on GitHub's isolated x86_64 runner and confirmed
the **source ONNX SHA-256 matches the previously verified fixture**,
while the QAIRT host converter SDK is **absent**. It correctly returned
`sdk-not-supplied` and left conversion/profile claims false:

https://github.com/Harrokk/Myai/actions/runs/38220986724

**Next hard dependency:** acquire/access a supported QAIRT 2.45
host-side ONNX or DLC conversion toolchain from an authorized Qualcomm
distribution. Without that, neither a valid independent QNN context
nor a truthful direct HTP profile can be produced. No automatic
installation, production service pause or new model loading is
authorized by this preflight.
