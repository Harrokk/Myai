"""QAIRT 2.46 small HTP basic-profile execution contract, metadata-only.

Qualcomm documents: qnn-net-run --profiling_level basic captures a QNN
profile; qnn-profile-viewer --reader libQnnHtpProfilingReader.so reads it.
These are two distinct processes. Neither existing GenieX token timings
nor a profile reader executable prove NPU op placement.

The previous tiny DLC (QAIRT 2.45) produced the known native output on
QAIRT 2.46's QNN CPU backend, but previous HTP launches failed to init.
This report inventories the *canonical vendor-owned* HTP libs and
profiler reader, the SHA-attested tiny fixture, live GenieX concurrency
and actual installed help flags. NEVER executes QNN or parses private logs.

Profiling an independent HTP graph remains NO-GO while the live GenieX
service or service state could acquire FastRPC asynchronously. Any future
executable profile workflow MUST require an approved exclusive window,
exact model/native input, verified host/DSP library provenance, a bounded
one-shot capture, viewer decode, and separate NPU placement evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
import platform
import shutil

from scripts.qairt_245_dlc_static_audit import DEFAULT_FIXTURE, verify_fixture
from scripts.qairt_dlc_forward_compatibility import evaluate_forward_compatibility
from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, summarize_service,
)
from scripts.ventuno_live_qairt_synthetic_once import available_memory_kib
from scripts.ventuno_qairt_v75_package_readonly import package_versions
from scripts.ventuno_v75_npu_readiness_readonly import _installed_minor
from scripts.ventuno_tiny_qnn_htp_once import (
    LIBS, _find_libraries, _find_v75_skel_directory,
    _help_flags, assess_geniex_concurrency,
)
from scripts.ventuno_v75_elf_fastrpc_readonly import inspect_resolved_skel

READERS = (
    ("/usr/lib/libQnnHtpProfilingReader.so", "usr_lib"),
    ("/usr/lib/aarch64-linux-gnu/libQnnHtpProfilingReader.so", "multiarch"),
)
NETRUN_FLAGS = frozenset({
    "--model", "--backend", "--dlc_path", "--input_list",
    "--output_dir", "--use_native_input_files",
    "--use_native_output_files", "--profiling_level",
})
VIEWER_FLAGS = frozenset({"--input_log", "--reader"})
INPUT_BYTES = 64
MIN_RAM_KIB = 8 * 1048576


def attest_packaged_htp_reader(inspector=inspect_resolved_skel):
    """Do not follow arbitrary user paths or trust GenieX-cache libraries."""
    available = {}
    for path, label in READERS:
        evidence = inspector(Path(path), Path("/usr"))
        available[label] = (
            evidence.get("path_inside_usr") is True
            and evidence.get("file_regular") is True
            and evidence.get("header_class") == "aarch64_elf_header"
            and evidence.get("package_owner") == "qairt-libs"
            and evidence.get("library_file_header_read") is True
        )
    return available


def classify(packages, verified_fixture, hostlibs, skel, reader,
             netrun_flags, viewer_flags, geniex, free_kib, machine):
    """Always fail closed for HTP execution while proof is incomplete.

    The profile *toolchain* may be ready even when HTP execution is not.
    Crucially never allow absence of a live FastRPC descriptor to imply
    durable exclusivity: GenieX can lazily open one after a scan.
    """
    packages = packages if isinstance(packages, dict) else {}
    fixture = verified_fixture if isinstance(verified_fixture, dict) else {}
    hostlibs = hostlibs if isinstance(hostlibs, dict) else {}
    reader = reader if isinstance(reader, dict) else {}
    # Never echo caller-supplied keys or paths from vendor metadata. Only
    # two fixed, owned library-root classifications can leave this probe.
    reader = {
        label: reader.get(label) is True
        for label in ("usr_lib", "multiarch")
    }
    runtime = _installed_minor(packages.get("qairt-libs"))
    dsp = _installed_minor(packages.get("qairt-dsp-binaries"))
    ver246 = runtime == "2.46" and dsp == "2.46"
    sha_verified = fixture.get("file_identity_verified") is True
    forward = evaluate_forward_compatibility(
        "2.45", runtime if runtime == dsp else None,
        source_sha_verified=sha_verified,
    )
    libs_verified = all(name in hostlibs for name in LIBS)
    reader_verified = any(value is True for value in reader.values())
    netrun_flags = (netrun_flags if isinstance(netrun_flags, (set, frozenset))
                    else frozenset())
    viewer_flags = (viewer_flags if isinstance(viewer_flags, (set, frozenset))
                    else frozenset())
    qnn_flags_ok = NETRUN_FLAGS.issubset(netrun_flags)
    viewer_flags_ok = VIEWER_FLAGS.issubset(viewer_flags)
    enough_ram = type(free_kib) is int and free_kib >= MIN_RAM_KIB
    busy = assess_geniex_concurrency(geniex)

    preflight = []
    if machine != "aarch64":
        preflight.append("not_ventuno_arm64")
    if not ver246:
        preflight.append("installed_qairt_246_pair_unverified")
    if not forward["compatible_runtime_minor"]:
        preflight.append("qnn_dlc_forward_format_unverified")
    if not libs_verified:
        preflight.append("packaged_htp_host_library_missing")
    if skel is not True:
        preflight.append("packaged_v75_dsp_skel_missing")
    if not reader_verified:
        preflight.append("packaged_htp_profile_reader_missing")
    if not qnn_flags_ok:
        preflight.append("installed_netrun_basic_capture_flags_missing")
    if not viewer_flags_ok:
        preflight.append("installed_profile_viewer_reader_flags_missing")
    if not enough_ram:
        preflight.append("available_ram_below_threshold_or_unverified")
    if busy:
        preflight.append(busy)
    # Runtime operator acceptance, actual successfully captured vendor log,
    # exclusive quiet window, and causal HTP placement are NOT attested.
    preflight.extend((
        "exclusive_vendor_approved_htp_window_not_attested",
        "tiny_qnn_v75_htp_backend_initialization_not_verified",
        "qnn_htp_profile_log_and_placement_not_verified",
    ))
    return {
        "probe": "ventuno_tiny_htp_basic_profile_contract_readonly",
        "status": "no_go_htp_profiling_requires_exclusive_verified_run",
        "blockers": preflight,
        "runtime_pair_is_246": ver246,
        "sha_attested_16004_byte_tiny_dlc": sha_verified,
        "dlc_format_forward_compatible": forward["compatible_runtime_minor"],
        "packaged_htp_host_libraries_verified": libs_verified,
        "packaged_v75_dsp_skel_verified": skel is True,
        "packaged_htp_reader_found": reader_verified,
        "packaged_reader_locations": reader,
        "netrun_basic_capture_cli_supported": qnn_flags_ok,
        "viewer_htp_reader_cli_supported": viewer_flags_ok,
        "sample_native_input_bytes": INPUT_BYTES,
        "ram_threshold_met": enough_ram,
        "geniex_concurrency_status": busy,
        "cli_profile_capture_is_not_npu_proof": True,
        "upstream_geniex_optrace_requires_248_but_netrun_basic_separate": True,
        "source_model_cpu_backend_reference_verified_before": True,
        "htp_backend_initialization_succeeded": False,
        "htp_profile_log_generated": False,
        "vendor_htp_reader_executed": False,
        "htp_per_operator_placement_verified": False,
        "npu_execution_measured": False,
        "model_or_device_file_opened": False,
        "qnn_or_htp_executed": False,
        "systemd_service_or_permissions_modified": False,
        "personal_or_vendor_log_data_exported": False,
    }


def report():
    reader = attest_packaged_htp_reader()
    program = shutil.which("qnn-net-run")
    viewer = shutil.which("qnn-profile-viewer")
    return classify(
        packages=package_versions(),
        verified_fixture=verify_fixture(DEFAULT_FIXTURE),
        hostlibs=_find_libraries(),
        skel=_find_v75_skel_directory() is not None,
        reader=reader,
        netrun_flags=_help_flags(program) if program else frozenset(),
        viewer_flags=_help_flags(viewer) if viewer else frozenset(),
        geniex=summarize_service(Path("/proc"), main_pid_from_systemd()),
        free_kib=available_memory_kib(),
        machine=platform.machine().lower(),
    )


if __name__ == "__main__":
    try:
        evidence = report()
    except Exception:
        evidence = {
            "probe": "ventuno_tiny_htp_basic_profile_contract_readonly",
            "status": "no_go_readonly_probe_exception",
            "qnn_or_htp_executed": False,
            "model_or_device_file_opened": False,
            "systemd_service_or_permissions_modified": False,
            "npu_execution_measured": False,
            "personal_or_vendor_log_data_exported": False,
        }
    print("MYAI_TINY_HTP_BASIC_PROFILE_CONTRACT_JSON=" +
          json.dumps(evidence, sort_keys=True))
