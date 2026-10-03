class SoundDeviceMicrophone:
    """Valbar fysisk mikrofonkälla för mono PCM16-ramar."""

    def __init__(
        self,
        controller,
        sample_rate=16000,
        frame_ms=20,
        device=None,
        sounddevice_module=None,
        result_callback=None,
    ):
        self.controller = controller
        self.sample_rate = int(sample_rate)
        self.frame_ms = float(frame_ms)
        self.device = device
        self.sounddevice_module = sounddevice_module
        self.result_callback = result_callback
        self.stream = None
        self.last_result = None
        self.last_error = None
        self.last_status = None

        if self.sample_rate <= 0:
            raise ValueError("Sample rate måste vara positiv.")

        if self.frame_ms <= 0:
            raise ValueError("Ramstorlek i ms måste vara positiv.")

        frame_samples = (
            self.sample_rate * self.frame_ms / 1000.0
        )

        if not frame_samples.is_integer():
            raise ValueError(
                "Sample rate och frame_ms ger inte ett helt antal samples."
            )

        self.frame_samples = int(frame_samples)
        self.frame_bytes = self.frame_samples * 2

    def _load_sounddevice(self):
        if self.sounddevice_module is not None:
            return self.sounddevice_module

        try:
            import sounddevice
        except ImportError as error:
            raise RuntimeError(
                "Mikrofoninmatning kräver sounddevice. "
                "Installera requirements-voice-input.txt."
            ) from error

        self.sounddevice_module = sounddevice
        return sounddevice

    def _audio_callback(
        self,
        indata,
        frames,
        time_info,
        status,
    ):
        del time_info

        if status:
            self.last_status = str(status)

        try:
            audio = bytes(indata)

            if int(frames) != self.frame_samples:
                raise ValueError(
                    "Mikrofoncallback gav fel antal samples: "
                    f"{frames}, förväntade {self.frame_samples}."
                )

            if len(audio) != self.frame_bytes:
                raise ValueError(
                    "Mikrofoncallback gav fel PCM16-storlek: "
                    f"{len(audio)} byte, förväntade {self.frame_bytes}."
                )

            result = self.controller.process_frame(
                audio
            )
            self.last_result = result
            self.last_error = None

            if self.result_callback is not None:
                self.result_callback(result)
        except Exception as error:
            self.last_error = str(error)

    def start(self):
        if self.stream is not None:
            return False

        sounddevice = self._load_sounddevice()
        kwargs = {
            "samplerate": self.sample_rate,
            "blocksize": self.frame_samples,
            "channels": 1,
            "dtype": "int16",
            "callback": self._audio_callback,
        }

        if self.device not in (None, ""):
            kwargs["device"] = self.device

        self.stream = sounddevice.RawInputStream(
            **kwargs
        )
        self.stream.start()
        return True

    def stop(self):
        stream = self.stream

        if stream is None:
            return False

        self.stream = None

        try:
            stream.stop()
        finally:
            stream.close()

        return True

    def __enter__(self):
        self.start()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        del exc_type, exc_value, traceback
        self.stop()
        return False


def build_microphone(
    controller,
    settings,
    sounddevice_module=None,
    result_callback=None,
):
    config = settings.get("voice", {})
    provider = (
        config.get("microphone_provider") or ""
    ).strip().lower()

    if not provider:
        return None

    if provider != "sounddevice":
        raise ValueError(
            f"Okänd mikrofonprovider: {provider}"
        )

    device = config.get(
        "microphone_device",
        None,
    )

    if device == "":
        device = None

    return SoundDeviceMicrophone(
        controller=controller,
        sample_rate=config.get(
            "vad_sample_rate",
            16000,
        ),
        frame_ms=config.get(
            "vad_frame_ms",
            20,
        ),
        device=device,
        sounddevice_module=sounddevice_module,
        result_callback=result_callback,
    )
