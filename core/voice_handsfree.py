import threading


class VoiceHandsfreeRunner:
    def __init__(
        self,
        session,
        on_result=None,
        on_error=None,
        max_wait_frames=None,
    ):
        self.session = session
        self.on_result = on_result
        self.on_error = on_error
        self.max_wait_frames = max_wait_frames
        self._stop_event = threading.Event()
        self._thread = None

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
        self.session.start()
        self._thread = threading.Thread(
            target=self._run,
            name="MyAI-VoiceHandsfree",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, timeout=3.0):
        self._stop_event.set()

        try:
            self.session.stop()
        except Exception as error:
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

        return not self.is_running

    def _run(self):
        try:
            while not self._stop_event.is_set():
                try:
                    result = self.session.run_once(
                        max_wait_frames=self.max_wait_frames,
                    )
                except Exception as error:
                    if self._stop_event.is_set():
                        break

                    if self.on_error is not None:
                        self.on_error(error)

                    break

                if self._stop_event.is_set():
                    break

                status = result.get("status")

                if status == "timeout":
                    continue

                if status == "disabled":
                    break

                voice_result = result.get(
                    "voice_result",
                    {},
                )

                if voice_result.get("status") == "ignored_echo":
                    continue

                if self.on_result is not None:
                    self.on_result(result)
        finally:
            try:
                self.session.stop()
            except Exception as error:
                if (
                    not self._stop_event.is_set()
                    and self.on_error is not None
                ):
                    self.on_error(error)


def format_handsfree_result(result):
    if result.get("status") != "utterance_complete":
        return result.get(
            "message",
            "Röstsessionen gav inget komplett yttrande.",
        )

    voice_result = result.get(
        "voice_result",
        {},
    )

    voice_status = voice_result.get("status")

    if voice_status == "ignored_echo":
        return ""

    if voice_status in {
        "clarify",
        "confirmation_required",
        "confirmation_cancelled",
        "confirmation_expired",
    }:
        return voice_result.get(
            "message",
            "Röstkommandot behöver förtydligas.",
        )

    transcript = voice_result.get(
        "transcript"
    )
    answer = (
        voice_result.get(
            "assistant",
            {},
        ).get("answer")
    )

    lines = []

    if transcript:
        lines.append(
            f"Du (röst): {transcript}"
        )

    if answer:
        lines.append("AI:")
        lines.append(answer)

    return "\n".join(lines) or (
        "Röstyttrandet behandlades utan textsvar."
    )
