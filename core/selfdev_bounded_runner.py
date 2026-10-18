"""Run verifier commands with bounded output and process-group cleanup.

Used only for Linux/POSIX Bubblewrap checks. Untrusted test code cannot force
the parent to buffer unlimited stdout/stderr or leave a timed-out subprocess
group running under its original process-group ID.
"""
import os
import selectors
import signal
import subprocess
import time


MAX_OUTPUT_BYTES = 1_048_576


def run_bounded(command, *, timeout, env, max_output_bytes=MAX_OUTPUT_BYTES):
    if os.name != "posix":
        raise RuntimeError("Säker selfdev-verifiering kräver POSIX processgrupper.")
    if (type(max_output_bytes) is not int
            or not 0 < max_output_bytes <= MAX_OUTPUT_BYTES):
        raise ValueError("Ogiltig gräns för selfdev-processutmatning.")

    deadline = time.monotonic() + float(timeout)
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
        close_fds=True,
    )
    chunks = {"stdout": [], "stderr": []}
    total_bytes = 0
    watcher = selectors.DefaultSelector()
    try:
        watcher.register(process.stdout, selectors.EVENT_READ, "stdout")
        watcher.register(process.stderr, selectors.EVENT_READ, "stderr")
        while watcher.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            for key, _ in watcher.select(remaining):
                chunk = os.read(key.fileobj.fileno(), 65_536)
                if not chunk:
                    watcher.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                total_bytes += len(chunk)
                if total_bytes > max_output_bytes:
                    raise RuntimeError(
                        "Verifieringens processtext överskred säkerhetsgränsen."
                    )
                chunks[key.data].append(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        returncode = process.wait(timeout=remaining)
        return subprocess.CompletedProcess(
            command, returncode,
            stdout=b"".join(chunks["stdout"]).decode("utf-8", "replace"),
            stderr=b"".join(chunks["stderr"]).decode("utf-8", "replace"),
        )
    except BaseException:
        # Bubblewrap and its ordinary children share this dedicated process
        # group. Cleanup applies to overflow, timeout and interruptions.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise
    finally:
        watcher.close()
        if process.stdout and not process.stdout.closed:
            process.stdout.close()
        if process.stderr and not process.stderr.closed:
            process.stderr.close()
