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
