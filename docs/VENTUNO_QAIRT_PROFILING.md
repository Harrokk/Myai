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
