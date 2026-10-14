"""Strict allowlisted QNN error categories from NEVER-EXPORTED child bytes.

Classifies bounded vendor stdout/stderr in memory. No log fragments,
device paths, process IDs, error messages, user strings, or environment
variables escape. Generic messages yield "unclassified" instead.
"""
import re

MAX_CAPTURE_READ = 16384
MAX_CATEGORIES = 4
CATEGORY_PATTERNS = (
    ("access_denied", (
        rb"\bpermission denied\b", rb"\beacces\b", rb"\baccess denied\b",
        rb"\boperation not permitted\b", rb"\berrno\s*(?:13|1)\b",
    )),
    ("missing_shared_library", (
        rb"cannot open shared object", rb"dlopen.{0,60}(?:fail|error)",
        rb"library.{0,60}(?:missing|not found)",
    )),
    ("memory_allocation_failure", (
        rb"\bout of memory\b", rb"\bstd::bad_alloc\b", rb"\benomem\b",
        rb"cannot allocate memory", rb"mmap.{0,40}fail",
    )),
    ("unsupported_graph_or_operation", (
        rb"unsupported.{0,50}(?:op|operation|graph|node|quant)",
        rb"(?:op|operation|graph).{0,50}not supported",
    )),
    ("dsp_rpc_transport_failure", (
        rb"fastrpc.{0,60}(?:fail|error)",
        rb"(?:fail|error).{0,60}fastrpc",
        rb"adsprpc.{0,60}(?:fail|error)",
        rb"remoteproc.{0,60}(?:fail|error)",
        rb"\bdsp transport\b",
    )),
    ("model_or_dlc_load_failure", (
        rb"(?:load|parse).{0,60}dlc.{0,30}(?:fail|error)",
        rb"(?:fail|error).{0,50}(?:load|parse).{0,50}dlc",
        rb"failed to load model",
    )),
    ("backend_initialization_failure", (
        rb"backend.{0,70}(?:init|create).{0,40}(?:fail|error)",
        rb"(?:fail|error).{0,60}(?:initialize|create).{0,30}backend",
    )),
    ("cli_argument_error", (
        rb"\bunrecognized option\b", rb"\binvalid argument\b",
        rb"\bunknown option\b", rb"\binvalid value for\b",
    )),
)


def classify_qnn_output(stdout, stderr):
    """Return only enumerated categories, never untrusted source text."""
    if type(stdout) is not bytes or type(stderr) is not bytes:
        raise TypeError("Expected bounded raw vendor output bytes.")
    joined = (stdout[:MAX_CAPTURE_READ] + b"\n" + stderr[:MAX_CAPTURE_READ]).lower()
    findings = []
    for category, patterns in CATEGORY_PATTERNS:
        if any(re.search(pattern, joined, flags=re.DOTALL) for pattern in patterns):
            findings.append(category)
        if len(findings) >= MAX_CATEGORIES:
            break
    return {
        "categories": findings or ["unclassified"],
        "stdout_sampled_bytes": min(len(stdout), MAX_CAPTURE_READ),
        "stderr_sampled_bytes": min(len(stderr), MAX_CAPTURE_READ),
        "output_capture_read_was_truncated":
            len(stdout) > MAX_CAPTURE_READ or len(stderr) > MAX_CAPTURE_READ,
        "raw_text_exported": False,
        "path_or_identifier_exported": False,
    }
