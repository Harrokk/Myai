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
        # A pre-existing voice session may belong to another controller.
        # Only stop a microphone when this runner actually started it.
        self._owns_session = False

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
        started = self.session.start()
        if started is False:
            # Another controller already owns the microphone. Do not
            # attach a background reader or take over its cleanup.
            self._stop_event.set()
            return False

        self._owns_session = True
        self._thread = threading.Thread(
            target=self._run,
            name="MyAI-VoiceHandsfree",
            daemon=True,
        )
        try:
            self._thread.start()
        except Exception:
            # Thread startup can fail after a successful microphone start.
            # Release only this runner's session, then propagate the
            # original error rather than reporting handsfree as active.
            self._stop_event.set()
            try:
                self.session.stop()
            finally:
                self._owns_session = False
                self._thread = None
            raise
        return True

    def stop(self, timeout=3.0):
        self._stop_event.set()

        if self._owns_session:
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

        if not self.is_running:
            self._owns_session = False

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
                if self._owns_session:
                    self.session.stop()
            except Exception as error:
                if (
                    not self._stop_event.is_set()
                    and self.on_error is not None
                ):
                    self.on_error(error)
            finally:
                self._owns_session = False


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
