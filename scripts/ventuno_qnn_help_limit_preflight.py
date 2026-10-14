"""Compare QNN --help startup with and without previous child resource limits.

No model/HTP parameters, no DLC, QNN contexts, remoteproc interaction,
inference, service modification or output/log content is read/exported.
Both runs have identical minimal environment; only child rlimits differ.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from scripts.ventuno_tiny_qnn_htp_once import (
    _child_limits, _find_libraries, _find_v75_skel_directory,
)

HELP_TIMEOUT = 7


def classify_help(program, environment, cwd, *, restrict):
    before = time.monotonic()
    try:
        completed = subprocess.run(
            [program, "--help"],
            cwd=cwd, env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, timeout=HELP_TIMEOUT,
            check=False, preexec_fn=_child_limits if restrict else None,
        )
        result = "exit_zero" if completed.returncode == 0 else "exit_nonzero"
    except subprocess.TimeoutExpired:
        result = "timeout"
    except OSError:
        result = "launch_error"
    return {"result": result, "wall_seconds": round(time.monotonic() - before, 3)}


def inspect_help_limits():
    report = {
        "probe": "qnn_help_only_resource_limit_preflight",
        "status": "no_go",
        "restricted_help": None,
        "unrestricted_help": None,
        "model_loaded": False,
        "htp_backend_invoked": False,
        "inference_attempted": False,
        "production_modified": False,
    }
    executable = shutil.which("qnn-net-run")
    libraries = _find_libraries()
    dsp = _find_v75_skel_directory()
    if not executable or dsp is None or len(libraries) < 3:
        report["status"] = "no_go_required_files_not_found"
        return report
    dirs = sorted({str(path.parent) for path in libraries.values()})
    env = {
        "PATH": "/usr/bin:/bin",
        "LD_LIBRARY_PATH": ":".join(dirs),
        "ADSP_LIBRARY_PATH": str(dsp),
        "QNN_LOG_LEVEL": "ERROR",
    }
    with tempfile.TemporaryDirectory(
        prefix="myai-qnn-help-only-", dir=os.environ.get("RUNNER_TEMP", "/tmp")
    ) as folder:
        os.chmod(folder, 0o700)
        env["HOME"] = folder
        report["restricted_help"] = classify_help(
            executable, env, folder, restrict=True)
        report["unrestricted_help"] = classify_help(
            executable, env, folder, restrict=False)
    if report["restricted_help"]["result"] == "exit_zero":
        report["status"] = "limits_do_not_block_qnn_help"
    elif report["unrestricted_help"]["result"] == "exit_zero":
        report["status"] = "resource_limit_affects_qnn_help"
    else:
        report["status"] = "both_help_startups_inconclusive"
    return report


if __name__ == "__main__":
    print("MYAI_QNN_HELP_LIMIT_RESULT_JSON=" +
          json.dumps(inspect_help_limits(), sort_keys=True))
