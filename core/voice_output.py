import threading


class InterruptibleTTS:
    def __init__(
        self,
        provider,
        stop_timeout_seconds=2.0,
    ):
        self.provider = provider
        self.stop_timeout_seconds = max(
            0.0,
            float(stop_timeout_seconds),
        )
        self._lock = threading.Lock()
        self._thread = None
        self.last_error = None

    @property
    def is_speaking(self):
        with self._lock:
            thread = self._thread

        return bool(
            thread
            and thread.is_alive()
        )

    def _run(self, text):
        current = threading.current_thread()

        try:
            self.provider.speak(text)
        except Exception as error:
            self.last_error = error
        finally:
            with self._lock:
                if self._thread is current:
                    self._thread = None

    def speak(self, text):
        value = str(text or "").strip()

        if not value:
            return False

        if self.is_speaking:
            stopped = self.stop()

            if not stopped and self.is_speaking:
                raise RuntimeError(
                    "Föregående TTS kunde inte avbrytas."
                )

        self.last_error = None
        thread = threading.Thread(
            target=self._run,
            args=(value,),
            name="MyAI-TTS",
            daemon=True,
        )

        with self._lock:
            self._thread = thread

        thread.start()
        return True

    def stop(self):
        with self._lock:
            thread = self._thread

        if thread is None or not thread.is_alive():
            return False

        stop = getattr(
            self.provider,
            "stop",
            None,
        )

        if callable(stop):
            stop()

        if (
            thread is not threading.current_thread()
            and self.stop_timeout_seconds > 0
        ):
            thread.join(
                timeout=self.stop_timeout_seconds
            )

        return not thread.is_alive()

    def wait(self, timeout=None):
        with self._lock:
            thread = self._thread

        if thread is None:
            return True

        if thread is threading.current_thread():
            return False

        thread.join(timeout=timeout)
        return not thread.is_alive()

    def status(self):
        return {
            "is_speaking": self.is_speaking,
            "last_error": (
                str(self.last_error)
                if self.last_error is not None
                else None
            ),
            "provider": type(
                self.provider
            ).__name__,
        }
