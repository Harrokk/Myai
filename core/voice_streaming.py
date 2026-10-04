import queue
import re
import threading
import time


_SENTENCE_PATTERN = re.compile(
    r"^(.+?[.!?]+)(?=\s|$)",
    re.DOTALL,
)


class SentenceChunkBuffer:
    def __init__(
        self,
        min_chars=24,
        max_chars=220,
    ):
        self.min_chars = max(
            1,
            int(min_chars),
        )
        self.max_chars = max(
            self.min_chars,
            int(max_chars),
        )
        self._buffer = ""

    @property
    def pending_text(self):
        return self._buffer

    def _forced_segment(self):
        if len(self._buffer) < self.max_chars:
            return None

        cut = self._buffer.rfind(
            " ",
            self.min_chars,
            self.max_chars + 1,
        )

        if cut < self.min_chars:
            cut = self.max_chars

        value = self._buffer[:cut].strip()
        self._buffer = self._buffer[cut:].lstrip()
        return value or None

    def feed(self, chunk):
        value = str(chunk or "")

        if not value:
            return []

        self._buffer += value
        segments = []

        while self._buffer:
            match = _SENTENCE_PATTERN.match(
                self._buffer
            )

            if match is not None:
                candidate = match.group(1).strip()

                if len(candidate) >= self.min_chars:
                    segments.append(candidate)
                    self._buffer = self._buffer[
                        match.end():
                    ].lstrip()
                    continue

            forced = self._forced_segment()

            if forced is not None:
                segments.append(forced)
                continue

            break

        return segments

    def flush(self):
        value = self._buffer.strip()
        self._buffer = ""

        if not value:
            return []

        return [value]


class StreamingTTSCoordinator:
    def __init__(
        self,
        tts,
        clock=None,
        min_chars=24,
        max_chars=220,
        stop_timeout_seconds=2.0,
    ):
        self.tts = tts
        self.clock = clock or time.monotonic
        self.stop_timeout_seconds = max(
            0.0,
            float(stop_timeout_seconds),
        )
        self.buffer = SentenceChunkBuffer(
            min_chars=min_chars,
            max_chars=max_chars,
        )
        self.started_at = None
        self.last_error = None
        self.spoken_segments = []

        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = None
        self._finished = False
        self._sentinel = object()
        self._lock = threading.Lock()

    @property
    def is_running(self):
        thread = self._thread
        return bool(
            thread
            and thread.is_alive()
        )

    def _ensure_worker(self):
        with self._lock:
            if (
                self._thread is not None
                and self._thread.is_alive()
            ):
                return

            self._thread = threading.Thread(
                target=self._run,
                name="MyAI-StreamingTTS",
                daemon=True,
            )
            self._thread.start()

    def _enqueue(self, text):
        value = str(text or "").strip()

        if (
            not value
            or self._finished
            or self._stop_event.is_set()
        ):
            return False

        if self.started_at is None:
            self.started_at = self.clock()

        self._ensure_worker()
        self._queue.put(value)
        return True

    def feed(self, chunk):
        if (
            self._finished
            or self._stop_event.is_set()
        ):
            return []

        segments = self.buffer.feed(chunk)

        for segment in segments:
            self._enqueue(segment)

        return segments

    def finish(self):
        if self._finished:
            return False

        for segment in self.buffer.flush():
            self._enqueue(segment)

        self._finished = True

        if self._thread is not None:
            self._queue.put(
                self._sentinel
            )

        return True

    def _run(self):
        while not self._stop_event.is_set():
            item = self._queue.get()

            if item is self._sentinel:
                break

            if self._stop_event.is_set():
                break

            try:
                self.tts.speak(item)

                wait = getattr(
                    self.tts,
                    "wait",
                    None,
                )

                if callable(wait):
                    wait()

                self.spoken_segments.append(
                    item
                )
            except Exception as error:
                self.last_error = error
                self._stop_event.set()
                break

    def wait(self, timeout=None):
        thread = self._thread

        if thread is None:
            return True

        if thread is threading.current_thread():
            return False

        thread.join(timeout=timeout)
        return not thread.is_alive()

    def stop(self):
        self._stop_event.set()
        self._finished = True
        self.buffer.flush()

        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

        stop = getattr(
            self.tts,
            "stop",
            None,
        )

        if callable(stop):
            stop()

        if self._thread is not None:
            self._queue.put(
                self._sentinel
            )
            self.wait(
                timeout=self.stop_timeout_seconds
            )

        return not self.is_running
