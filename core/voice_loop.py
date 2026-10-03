import threading


class ContinuousVoiceLoop:
    def __init__(
        self,
        session,
        on_result=None,
        on_error=None,
    ):
        self.session = session
        self.on_result = on_result
        self.on_error = on_error
        self._stop_event = threading.Event()
        self._thread = None
        self.utterance_count = 0
        self.timeout_count = 0
        self.error_count = 0

    @property
    def is_running(self):
        return bool(
            self._thread
            and self._thread.is_alive()
        )

    def start(self):
        if self.is_running:
            return False

        if not self.session.enabled:
            raise RuntimeError(
                "Röstläge är avstängt i konfigurationen."
            )

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="MyAI-VoiceLoop",
            daemon=True,
        )
        self._thread.start()
        return True

    def _run(self):
        try:
            self.session.start()

            while not self._stop_event.is_set():
                try:
                    result = self.session.run_once()
                except Exception as error:
                    if self._stop_event.is_set():
                        break

                    self.error_count += 1

                    if self.on_error is not None:
                        self.on_error(error)

                    continue

                status = result.get("status")

                if status == "utterance_complete":
                    self.utterance_count += 1

                    if self.on_result is not None:
                        self.on_result(result)

                elif status == "timeout":
                    self.timeout_count += 1

                elif status == "disabled":
                    break
        finally:
            self.session.stop()

    def stop(self, timeout=3.0):
        was_running = self.is_running
        self._stop_event.set()

        try:
            self.session.stop()
        except Exception as error:
            self.error_count += 1

            if self.on_error is not None:
                self.on_error(error)

        thread = self._thread

        if (
            thread is not None
            and thread is not threading.current_thread()
        ):
            thread.join(
                timeout=max(
                    0.0,
                    float(timeout),
                )
            )

        return (
            was_running
            and not self.is_running
        )

    def status(self):
        return {
            "running": self.is_running,
            "utterances": self.utterance_count,
            "timeouts": self.timeout_count,
            "errors": self.error_count,
        }
