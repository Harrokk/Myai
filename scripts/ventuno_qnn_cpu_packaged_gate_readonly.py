"""Read-only QAIRT CPU backend selector attestation, never executes QNN."""
import json

from scripts.ventuno_qnn_cpu_reference_once import locate_cpu_backend
from scripts.ventuno_v75_elf_fastrpc_readonly import inspect_resolved_skel
from pathlib import Path


def report():
    fixed = Path("/usr/lib/libQnnCpu.so")
    metadata = inspect_resolved_skel(fixed, Path("/usr"))
    selected = locate_cpu_backend()
    return {
        "probe": "ventuno_qnn_cpu_packaged_backend_readonly",
        "cpu_host_file_regular": metadata["file_regular"] is True,
        "cpu_host_is_aarch64": metadata["header_class"] == "aarch64_elf_header",
        "cpu_host_owned_by_qairt_libs": metadata["package_owner"] == "qairt-libs",
        "cpu_backend_selector_passes_strict_gate": selected == fixed,
        "cpu_reference_output_reexecuted": False,
        "htp_or_npu_executed": False,
        "device_node_opened": False,
        "production_modified": False,
        "raw_files_or_inode_exported": False,
    }


if __name__ == "__main__":
    print("MYAI_QNN_CPU_GATE_JSON=" + json.dumps(report(), sort_keys=True))
