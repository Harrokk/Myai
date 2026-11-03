from pathlib import Path
from core.config import load_settings
from core.voice_output import InterruptibleTTS
from core.voice_stt_process import IsolatedFasterWhisperSTT
from core.voice_stt_persistent import PersistentFasterWhisperSTT
from modules.voice.sherpa_onnx_provider import SherpaOnnxParakeetSTT
from modules.voice.sherpa_silero_segments import SherpaSileroSegments
from modules.voice.piper_alma_provider import PiperAlmaTTS
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
        "sherpa_silero_segments": SherpaSileroSegments,
    },
    "stt": {
        "faster_whisper": FasterWhisperSTT,
        "sherpa_onnx_parakeet": SherpaOnnxParakeetSTT,
    },
    "tts": {
        "pyttsx3": Pyttsx3TTS,
        "piper_alma": PiperAlmaTTS,
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
    backup_stt_name = config.get(
        "backup_stt_provider",
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
    backup_stt_class = _provider_class(
        "stt",
        backup_stt_name,
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
    if vad_name == "sherpa_silero_segments":
        # Silero emits *segments*; it is not a WebRTC per-frame provider.
        # Prevent accidental use with old STT worker/confirmation semantics.
        if stt_name != "sherpa_onnx_parakeet":
            raise ValueError("Silero segment VAD requires Parakeet pilot")
        if (config.get("sample_rate", 16000) != 16000
                or config.get("channels", 1) != 1
                or config.get("frame_ms", 20) != 20
                or config.get("sample_width", 2) != 2):
            raise ValueError("Silero requires 16-kHz mono PCM16 with 20-ms frames")
        model_path = config.get("silero_model_path", "")
        if not isinstance(model_path, str) or not model_path:
            raise ValueError("Silero requires explicit local model path")
        vad = vad_class(
            model_path=model_path,
            context_padding_ms=config.get("silero_context_padding_ms", 300),
        )
    else:
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
    isolate_stt = config.get("stt_process_isolation_enabled", False)
    if type(isolate_stt) is not bool:
        raise ValueError("Invalid STT isolation toggle")
    persistent = config.get("stt_persistent_worker_enabled", False)
    if type(persistent) is not bool:
        raise ValueError("Invalid persistent STT toggle")
    if persistent and not isolate_stt:
        raise ValueError("Persistent STT requires process isolation")
    if isolate_stt:
        # No arbitrary provider classes or model/plugin paths in worker.
        if stt_class is not FasterWhisperSTT or backup_stt_class is not FasterWhisperSTT:
            raise ValueError("STT isolation supports built-in FasterWhisper only")
        timeout = config.get("stt_process_timeout_seconds", 45.0)
        isolation_kwargs = {
            "timeout_seconds": timeout,
            "cpu_seconds": config.get("stt_child_cpu_seconds", 0),
            "virtual_memory_mib": config.get(
                "stt_child_virtual_memory_mib", 0
            ),
        }
        if persistent:
            provider_type = PersistentFasterWhisperSTT
            isolation_kwargs["max_utterances"] = config.get(
                "stt_persistent_worker_max_utterances", 4
            )
        else:
            provider_type = IsolatedFasterWhisperSTT
    else:
        provider_type = stt_class
        isolation_kwargs = {}

    primary_stt = provider_type(
        model_name=config.get("stt_model", "small"),
        **common_stt,
        **isolation_kwargs,
    )

    backup_stt_type = provider_type if isolate_stt else backup_stt_class
    backup_stt = [
        backup_stt_type(
            model_name=model_name, **common_stt, **isolation_kwargs,
        )
        for model_name in config.get("backup_stt_models", [])
    ]

    tts = None

    if config.get("tts_enabled", False):
        tts_class = _provider_class(
            "tts",
            tts_name,
            classes,
        )
        tts_kwargs = {
            "rate": config.get("tts_rate", 180),
            "volume": config.get("tts_volume", 1.0),
            "voice_id": config.get("tts_voice_id") or None,
        }
        if tts_name == "piper_alma":
            model = tts_kwargs["voice_id"]
            output = config.get("tts_output_device")
            if (not isinstance(model, str) or not Path(model).is_absolute()
                    or Path(model).name != "sv_SE-alma-medium.onnx"):
                raise ValueError("Piper requires an explicit absolute local Swedish voice")
            if not ((type(output) is int and output >= 0)
                    or (isinstance(output, str) and 0 < len(output) <= 120)):
                raise ValueError("Piper requires an explicitly selected sound output device")
            tts_kwargs["output_device"] = output
        raw_tts = tts_class(**tts_kwargs)

        if config.get(
            "tts_async",
            True,
        ):
            tts = InterruptibleTTS(
                raw_tts,
                stop_timeout_seconds=config.get(
                    "tts_stop_timeout_seconds",
                    2.0,
                ),
            )
        else:
            tts = raw_tts

    return {
        "enabled": True,
        "microphone": microphone,
        "vad": vad,
        "primary_stt": primary_stt,
        "backup_stt": backup_stt,
        "tts": tts,
    }
