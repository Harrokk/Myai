"""Pure, offline QAIRT QNN-DLC format compatibility evidence.

Qualcomm AI Hub documentation states that a QNN DLC produced using a given
QAIRT version is compatible with *newer* QAIRT runtime versions.
https://workbench.aihub.qualcomm.com/docs/hub/compile_examples.html
https://workbench.aihub.qualcomm.com/docs/hub/api.html

This is a FORMAT/runtime version contract, NOT proof that an individual
operator is accepted by Hexagon V75, that a model was run, or that any
graph was placed on the NPU. A CPU backend parity run is separate evidence.
"""
from __future__ import annotations

import re

_MINOR_RE = re.compile(r"^([0-9]{1,2})[.]([0-9]{1,3})$")
KNOWN_SOURCE_MINOR = "2.45"


def evaluate_forward_compatibility(source_minor, runtime_minor,
                                   *, source_sha_verified=False):
    """Conservative vendor-policy classification; never grants HTP execution.

    Require exact major/minor strings and an attested local DLC. Do not
    extrapolate compatibility across a major-version boundary or infer
    physical HTP operator support from a generic DLC format promise.
    """
    observed = {
        "format_forward_compatibility": "unverified",
        "vendor_dlc_forward_compatibility_policy_applied": False,
        "source_dlc_identity_verified": source_sha_verified is True,
        "compatible_runtime_minor": False,
        "htp_v75_operator_compatibility_verified": False,
        "htp_or_npu_executed": False,
        "qnn_cpu_inference_executed": False,
        "backend_initialization_verified": False,
        "npu_placement_verified": False,
    }
    if source_sha_verified is not True:
        observed["format_forward_compatibility"] = "no_go_unverified_dlc_bytes"
        return observed
    if type(source_minor) is not str or type(runtime_minor) is not str:
        observed["format_forward_compatibility"] = "no_go_version_unavailable"
        return observed
    source = _MINOR_RE.fullmatch(source_minor)
    target = _MINOR_RE.fullmatch(runtime_minor)
    if source is None or target is None:
        observed["format_forward_compatibility"] = "no_go_malformed_minor"
        return observed
    source_major, source_sub = map(int, source.groups())
    target_major, target_sub = map(int, target.groups())
    if source_major != 2 or target_major != source_major:
        observed["format_forward_compatibility"] = "no_go_cross_major_unverified"
        return observed
    if target_sub < source_sub:
        observed["format_forward_compatibility"] = "no_go_older_runtime"
        return observed
    observed["vendor_dlc_forward_compatibility_policy_applied"] = True
    observed["compatible_runtime_minor"] = True
    observed["format_forward_compatibility"] = (
        "documented_dlc_format_compatibility_not_htp_proof"
    )
    return observed
