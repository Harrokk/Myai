"""Opt-in READ-ONLY Qualcomm AI Hub catalog check on a trusted x86 host.

Without --confirm-readonly-api this module neither imports qai_hub nor
touches credentials, network or any external service. When explicitly
enabled on x86, the only permitted client calls are get_frameworks()
and get_devices(name="Arduino VENTUNO Q", os="24.04"). It cannot upload a model,
submit a job, create a context, download SDKs or run QNN/HTP.

SDK authenticity, SSL trust and local token configuration must be
reviewed separately. No raw API responses, exceptions, paths, other
device names, credentials or account details are ever printed.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import importlib
import io
import json
import platform
import re

TARGET = "Arduino VENTUNO Q"
TARGET_OS = "24.04"
MINOR = "2.46"
MAX_FRAMEWORKS = 256
MAX_DEVICES = 32
VERSION_RE = re.compile(r"^[0-9]{1,3}(?:\.[0-9]{1,12}){2,4}$")


class _DiscardText(io.TextIOBase):
    """Discard SDK diagnostic messages without retaining tokens in RAM."""

    def write(self, value):
        return len(value)

    def flush(self):
        pass


def blank_result():
    return {
        "probe": "ventuno_qai_hub_live_catalog_readonly_optin",
        "status": "no_go_readonly_api_not_authorized",
        "query_attempted": False,
        "query_completed": False,
        "get_frameworks_returned": False,
        "source_is_injected_client_not_attested": False,
        "exact_arduino_ventuno_q_in_device_list": None,
        "exact_ubuntu_2404_target_verified": False,
        "qairt_246_in_returned_frameworks": None,
        "qairt_246_version_record_consistent": None,
        "live_qairt_246_catalog_reported": False,
        "exact_target_qairt_246_compile_link_eligibility_verified": False,
        "htp_operator_support_verified": False,
        "model_or_context_uploaded": False,
        "cloud_job_submitted": False,
        "qnn_or_npu_executed": False,
        "ventuno_accessed_or_modified": False,
        "raw_responses_errors_or_credentials_exported": False,
    }


def classify_frameworks(frameworks):
    """Check exact QAIRT api_version and bounded full_version, no raw output."""
    try:
        if type(frameworks) not in (list, tuple) or not 1 <= len(frameworks) <= MAX_FRAMEWORKS:
            return "invalid_catalog", None, None
        matched = []
        for entry in frameworks:
            name = getattr(entry, "name", None)
            minor = getattr(entry, "api_version", None)
            full = getattr(entry, "full_version", None)
            if not isinstance(name, str) or not isinstance(minor, str):
                return "invalid_catalog", None, None
            if name == "QAIRT" and minor == MINOR:
                if type(full) is not str or VERSION_RE.fullmatch(full) is None:
                    return "invalid_catalog", None, None
                matched.append(full.startswith(MINOR + "."))
        if len(matched) > 1:
            return "ambiguous_version", None, None
        if not matched:
            return "valid", False, None
        return "valid", True, matched[0]
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return "invalid_catalog", None, None


def classify_devices(devices):
    """Require one unique named Ubuntu 24.04 device, not a proxy or family."""
    try:
        if type(devices) not in (list, tuple) or len(devices) > MAX_DEVICES:
            return None
        if not devices:
            return False
        names_and_os = [
            (getattr(item, "name", None), getattr(item, "os", None))
            for item in devices
        ]
        if any(type(name) is not str or type(os_version) is not str
               for name, os_version in names_and_os):
            return None
        # The client request filters by both fields; reject unexpected
        # broader results or duplicate names instead of silently accepting.
        if len(names_and_os) > 1:
            return None
        return names_and_os[0] == (TARGET, TARGET_OS)
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return None


def run_readonly_query(*, confirm: bool = False, client_factory=None,
                       machine: str | None = None):
    out = blank_result()
    machine = platform.machine() if machine is None else machine
    if machine.lower() not in {"x86_64", "amd64"}:
        out["status"] = "no_go_host_must_be_x86"
        return out
    if confirm is not True:
        return out
    out["query_attempted"] = True
    # Any caller-supplied factory is untrusted test/fixture material,
    # even if it implements the exact Qualcomm API methods and responds
    # with plausible Framework and Device objects. Never mark this live.
    injected_client = client_factory is not None
    out["source_is_injected_client_not_attested"] = injected_client
    try:
        # Even API diagnostics can contain service/account details. Never
        # print client output, even if a dependency unexpectedly logs.
        with redirect_stdout(_DiscardText()), redirect_stderr(_DiscardText()):
            if client_factory is None:
                hub = importlib.import_module("qai_hub")
                client_factory = hub.Client
            client = client_factory()
            frameworks = client.get_frameworks()
            devices = client.get_devices(name=TARGET, os=TARGET_OS)
    except Exception:
        out["status"] = "no_go_readonly_api_query_failed"
        return out

    out["get_frameworks_returned"] = True
    state, listed, consistent = classify_frameworks(frameworks)
    board = classify_devices(devices)
    out["exact_arduino_ventuno_q_in_device_list"] = board
    out["exact_ubuntu_2404_target_verified"] = board is True
    out["qairt_246_in_returned_frameworks"] = listed
    out["qairt_246_version_record_consistent"] = consistent
    if state != "valid" or board is None:
        out["status"] = "no_go_untrusted_or_ambiguous_service_response"
        return out
    out["query_completed"] = True
    if not listed:
        out["status"] = "no_go_qairt_246_not_in_returned_catalog"
    elif consistent is not True:
        out["status"] = "no_go_qairt_246_version_metadata_inconsistent"
    elif board is not True:
        out["status"] = "no_go_exact_arduino_ventuno_q_not_listed"
    elif injected_client:
        # Synthetically supplied API objects are NOT an authenticated
        # observation of current Qualcomm service availability.
        out["status"] = "injected_catalog_fixture_only_not_live_verified"
    else:
        # SDK instantiated on a separately authorized host. This is only
        # a read-only observation, NOT cloud compile/link eligibility.
        out["live_qairt_246_catalog_reported"] = True
        out["status"] = "read_only_catalog_and_target_listed_htp_unverified"
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-readonly-api", action="store_true",
                        help="Explicitly permit ONLY get_frameworks and get_devices")
    args = parser.parse_args()
    result = run_readonly_query(confirm=args.confirm_readonly_api)
    print("MYAI_QAI_LIVE_CATALOG_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if not args.confirm_readonly_api else (
        0 if result["query_completed"] else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
