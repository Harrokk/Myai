"""Bounded, nonblocking, duplex pipes for one-shot isolated STT.

subprocess.communicate() collects unlimited stdout before the caller can
inspect MAX_REPLY_BYTES. A compromised/buggy native decoder could emit
megabytes while delaying its exit. Pump stdin and stdout concurrently with
nonblocking Linux/POSIX pipes; never buffer more than MAX_REPLY_BYTES+1.
The parent is responsible for killing/reaping its owned process group
after *every* failure (deadline, oversized frame, broken pipe, child exit).
"""
from __future__ import annotations

import os
import selectors
import time


class OversizedSTTOutput(RuntimeError):
    """Fixed public error category, no private child data."""


def exchange_bounded(proc, audio, *, deadline, max_reply_bytes,
                     clock=time.monotonic):
    """Send fixed bounded PCM, receive raw EOF-terminated answer.

    No subprocess is started here. A single absolute deadline covers
    both directions, including a child that refuses stdin, emits endless
    data or exits while a pipe is still open.
    """
    if (type(audio) is not bytes or not 0 < len(audio) <= 2 * 1024 * 1024
            or type(max_reply_bytes) is not int
            or not 0 < max_reply_bytes <= 8192):
        raise ValueError("Invalid isolated STT pipe contract")
    if (getattr(proc, "stdin", None) is None
            or getattr(proc, "stdout", None) is None):
        raise RuntimeError("Invalid isolated STT pipe handles")

    try:
        stdin_fd = proc.stdin.fileno()
        stdout_fd = proc.stdout.fileno()
        os.set_blocking(stdin_fd, False)
        os.set_blocking(stdout_fd, False)
        output = bytearray()
        sent = 0
        with selectors.DefaultSelector() as selector:
            # Register stdout before stdin to drain rapidly-spamming
            # children promptly and detect the output cap first.
            selector.register(stdout_fd, selectors.EVENT_READ)
            selector.register(stdin_fd, selectors.EVENT_WRITE)
            while selector.get_map():
                remaining = deadline - clock()
                if remaining <= 0:
                    raise TimeoutError("Isolated STT process deadline exceeded")
                events = selector.select(remaining)
                if not events:
                    raise TimeoutError("Isolated STT process deadline exceeded")
                for key, _ in events:
                    if key.fd == stdout_fd:
                        # At most MAX+1 raw bytes, never an unbounded read.
                        length = min(65536, max_reply_bytes + 1 - len(output))
                        data = os.read(stdout_fd, length)
                        if data:
                            output.extend(data)
                            if len(output) > max_reply_bytes:
                                raise RuntimeError("Isolated STT output exceeds limit")
                        else:
                            selector.unregister(stdout_fd)
                    else:
                        if sent == len(audio):
                            selector.unregister(stdin_fd)
                            proc.stdin.close()
                        else:
                            written = os.write(
                                stdin_fd,
                                memoryview(audio)[sent:sent + 65536],
                            )
                            if written <= 0:
                                raise RuntimeError("Isolated STT child input stalled")
                            sent += written
                            if sent == len(audio):
                                selector.unregister(stdin_fd)
                                proc.stdin.close()
        return bytes(output)
    except TimeoutError:
        raise
    except (OSError, ValueError) as exc:
        # Do not surface pipe numbers or native OS messages to voice UI.
        raise RuntimeError("Isolated STT pipe transfer failed") from None
