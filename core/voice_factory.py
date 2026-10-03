from core.config import load_settings
from modules.voice.providers import (
    FasterWhisperSTT,
    Pyttsx3TTS,
    SoundDeviceMicrophone,
    WebRTCVADProvider,
)


DEFAULT_CLASSES = {
    "microphone": {
        "sounddevice": SoundDeviceMicrophone,
    },
    "vad": {
        "webrtcvad": WebRTCVADProvider,
    },
    "stt": {
        "faster_whisper": FasterWhisperSTT,
    },
    "tts": {
        "pyttsx3": Pyttsx3TTS,
    },
}


def _provider_class(kind, name, classes):
    provider = (
        classes.get(kind, {})
        .get(name)
    )

    if provider is None:
        raise ValueError(
            f"Okänd voice-provider för {kind}: {name}"
        )

    return provider


def build_voice_components(
    settings=None,
    provider_classes=None,
):
    settings = settings or load_settings()
    config = settings.get("voice", {})

    if not config.get("enabled", False):
        return {
            "enabled": False,
            "microphone": None,
            "vad": None,
            "primary_stt": None,
            "backup_stt": [],
            "tts": None,
        }

    classes = (
        provider_classes
        or DEFAULT_CLASSES
    )

    microphone_name = config.get(
        "microphone_provider",
        "sounddevice",
    )
    vad_name = config.get(
        "vad_provider",
        "webrtcvad",
    )
    stt_name = config.get(
        "stt_provider",
        "faster_whisper",
    )
    tts_name = config.get(
        "tts_provider",
        "pyttsx3",
    )

    microphone_class = _provider_class(
        "microphone",
        microphone_name,
        classes,
    )
    vad_class = _provider_class(
        "vad",
        vad_name,
        classes,
    )
    stt_class = _provider_class(
        "stt",
        stt_name,
        classes,
    )

    microphone = microphone_class(
        sample_rate=config.get(
            "sample_rate",
            16000,
        ),
        channels=config.get(
            "channels",
            1,
        ),
        frame_ms=config.get(
            "frame_ms",
            20,
        ),
        device=config.get(
            "input_device"
        ),
    )
    vad = vad_class(
        aggressiveness=config.get(
            "vad_aggressiveness",
            2,
        ),
        sample_rate=config.get(
            "sample_rate",
            16000,
        ),
    )

    common_stt = {
        "device": config.get(
            "stt_device",
            "auto",
        ),
        "compute_type": config.get(
            "stt_compute_type",
            "default",
        ),
        "language": config.get(
            "stt_language",
            "sv",
        ),
        "sample_rate": config.get(
            "sample_rate",
            16000,
        ),
        "channels": config.get(
            "channels",
            1,
        ),
        "sample_width": config.get(
            "sample_width",
            2,
        ),
    }
    primary_stt = stt_class(
        model_name=config.get(
            "stt_model",
            "small",
        ),
        **common_stt,
    )

    backup_stt = [
        stt_class(
            model_name=model_name,
            **common_stt,
        )
        for model_name in config.get(
            "backup_stt_models",
            [],
        )
    ]

    tts = None

    if config.get("tts_enabled", False):
        tts_class = _provider_class(
            "tts",
            tts_name,
            classes,
        )
        tts = tts_class(
            rate=config.get(
                "tts_rate",
                180,
            ),
            volume=config.get(
                "tts_volume",
                1.0,
            ),
            voice_id=(
                config.get("tts_voice_id")
                or None
            ),
        )

    return {
        "enabled": True,
        "microphone": microphone,
        "vad": vad,
        "primary_stt": primary_stt,
        "backup_stt": backup_stt,
        "tts": tts,
    }
