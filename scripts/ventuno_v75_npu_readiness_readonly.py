"""Read-only VENTUNO V75 NPU readiness report before any new HTP inference.

The QAIRT 2.45 repository DLC is not an attested QAIRT 2.46 artifact.
A live GenieX process may race a secondary FastRPC client after any /proc
scan, so no preview can grant concurrent accelerator use. This module
reports explicit NO-GO conditions; it NEVER runs QNN or opens a DSP device.

Only bounded, already reviewed metadata probes are used. No model request,
permission change, package install, service stop, sudo, or vendor raw log.
"""
from __future__ import annotations

import json
from pathlib import Path
import platform

from scripts.qairt_245_dlc_static_audit import DEFAULT_FIXTURE, verify_fixture
from scripts.ventuno_qairt_v75_package_readonly import package_versions
from scripts.ventuno_tiny_qnn_htp_once import (
    LIBS, MIN_AVAILABLE_KIB, _find_libraries, _find_v75_skel_directory,
    assess_geniex_concurrency,
)
from scripts.ventuno_live_qairt_synthetic_once import available_memory_kib
from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, summarize_service,
)
from scripts.ventuno_fastrpc_policy_readonly import report as policy_report


def _installed_minor(record):
    """Only a bounded QAIRT version is recognized, never log arbitrary text."""
    if not isinstance(record, dict) or record.get("status") != "installed":
        return None
    version = record.get("version")
    if not isinstance(version, str) or len(version) > 64:
        return None
    parts = version.split(".", 2)
    if len(parts) < 3 or not all(p.isdecimal() for p in parts[:2]):
        return None
    return ".".join(parts[:2])


def evaluate(packages, libraries, skel_present, service, available_kib,
             fixture, policy, machine):
    """Pure, deterministic, conservative assessment. Never authorizes HTP.

    This release has no independently attested QAIRT-2.46 V75 context/DLC
    and no approved exclusive service-maintenance window. Therefore a
    GO or successful NPU inference must not be inferred from green CI.
    """
    packages = packages if isinstance(packages, dict) else {}
    libraries = libraries if isinstance(libraries, dict) else {}
    service = service if isinstance(service, dict) else {}
    fixture = fixture if isinstance(fixture, dict) else {}
    policy = policy if isinstance(policy, dict) else {}
    nodes = policy.get("nodes", {})
    if not isinstance(nodes, dict):
        nodes = {}
    secure = nodes.get("cdsp_secure", {})
    if not isinstance(secure, dict):
        secure = {}

    rt = _installed_minor(packages.get("qairt-libs"))
    dsp = _installed_minor(packages.get("qairt-dsp-binaries"))
    platform_ok = isinstance(machine, str) and machine.casefold() == "aarch64"
    runtime_246 = rt == "2.46" and dsp == "2.46"
    hostlibs_verified = all(name in libraries for name in LIBS)
    checked_dlc = fixture.get("file_identity_verified") is True
    memory_ok = (
        type(available_kib) is int and available_kib >= MIN_AVAILABLE_KIB
    )
    concurrency = assess_geniex_concurrency(service)
    # Effective access is metadata only, NOT proof of a successful DSP open.
    fastrpc_access = (
        secure.get("character_device") is True
        and secure.get("runner_effective_read_access") is True
        and secure.get("runner_effective_write_access") is True
    )
    blockers = []
    if not platform_ok:
        blockers.append("not_aarch64_target")
    if not runtime_246:
        blockers.append("qairt_246_runtime_pair_unverified")
    if not hostlibs_verified:
        blockers.append("packaged_htp_host_libraries_unverified")
    if skel_present is not True:
        blockers.append("packaged_v75_dsp_skel_unverified")
    if not checked_dlc:
        blockers.append("existing_245_fixture_integrity_unverified")
    # Even valid QAIRT 2.45 bytes do not become a 2.46 HTP model.
    blockers.append("matching_246_htp_artifact_not_attested")
    if not memory_ok:
        blockers.append("available_ram_below_safe_threshold_or_unknown")
    if concurrency == "no_go_existing_geniex_fastrpc_busy":
        blockers.append("existing_geniex_fastrpc_busy")
    elif concurrency == "no_go_geniex_active_concurrent_htp_unsafe":
        blockers.append("active_geniex_concurrency_unsafe")
    else:
        blockers.append("exclusive_htp_maintenance_not_attested")
    if not fastrpc_access:
        blockers.append("runner_fastrpc_device_access_unverified")
    # Separate signed, version-compatible model and vendor-approved
    # exclusive-run procedure are prerequisites for a future new workflow.
    blockers.append("vendor_htp_placement_proof_not_available")

    return {
        "probe": "ventuno_v75_npu_readiness_readonly",
        "status": "no_go",
        "blockers": blockers,
        "runtime_both_qairstack_246": runtime_246,
        "runtime_pair_minor_equal": rt is not None and rt == dsp,
        "host_libraries_all_vendor_packaged": hostlibs_verified,
        "v75_dsp_skel_vendor_packaged": skel_present is True,
        "repository_245_dlc_integrity_verified": checked_dlc,
        "matching_246_htp_artifact_attested": False,
        "available_ram_at_least_safe_threshold": memory_ok,
        "runner_secure_fastrpc_metadata_permits_rw": fastrpc_access,
        "geniex_fastrpc_state": (
            concurrency if concurrency in {
                "no_go_existing_geniex_fastrpc_busy",
                "no_go_geniex_active_concurrent_htp_unsafe",
                "no_go_geniex_service_state_unknown",
            } else "no_go_geniex_service_state_unknown"
        ),
        "exclusive_htp_execution_attested": False,
        "qnn_or_htp_attempted": False,
        "npu_inference_verified": False,
        "npu_operator_placement_measured": False,
        "service_or_packages_modified": False,
        "devices_opened": False,
        "private_paths_or_vendor_logs_emitted": False,
    }


def report():
    """Read metadata only; fail closed when a probe raises an exception."""
    result = evaluate(
        packages=package_versions(),
        libraries=_find_libraries(),
        skel_present=_find_v75_skel_directory() is not None,
        service=summarize_service(Path("/proc"), main_pid_from_systemd()),
        available_kib=available_memory_kib(),
        fixture=verify_fixture(DEFAULT_FIXTURE),
        policy=policy_report(),
        machine=platform.machine(),
    )
    return result


if __name__ == "__main__":
    try:
        outcome = report()
    except Exception:
        # Never reveal raw exception strings, vendor or filesystem paths.
        outcome = {"probe": "ventuno_v75_npu_readiness_readonly",
                   "status": "no_go", "blockers": ["metadata_probe_failed"],
                   "qnn_or_htp_attempted": False,
                   "npu_inference_verified": False,
                   "devices_opened": False,
                   "service_or_packages_modified": False}
    print("MYAI_V75_NPU_READINESS_JSON=" + json.dumps(outcome, sort_keys=True))
