from core import voice_factory


class Recorder:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class AcceleratedRecorder(Recorder):
    pass


def classes():
    return {
        "microphone": {
            "sounddevice": Recorder,
        },
        "vad": {
            "webrtcvad": Recorder,
        },
        "stt": {
            "faster_whisper": Recorder,
            "accelerated": AcceleratedRecorder,
        },
        "tts": {
            "pyttsx3": Recorder,
        },
    }


def settings(enabled=True, tts=False):
    return {
        "voice": {
            "enabled": enabled,
            "tts_enabled": tts,
            "microphone_provider": "sounddevice",
            "vad_provider": "webrtcvad",
            "stt_provider": "faster_whisper",
            "backup_stt_provider": "faster_whisper",
            "tts_provider": "pyttsx3",
            "sample_rate": 16000,
            "channels": 1,
            "sample_width": 2,
            "frame_ms": 20,
            "input_device": None,
            "vad_aggressiveness": 2,
            "stt_model": "small",
            "stt_device": "auto",
            "stt_compute_type": "default",
            "stt_language": "sv",
            "backup_stt_models": [
                "base",
                "medium",
            ],
            "tts_rate": 175,
            "tts_volume": 0.8,
            "tts_voice_id": "voice-1",
            "tts_async": False,
            "tts_stop_timeout_seconds": 1.5,
        }
    }


def test_disabled_voice_builds_no_providers():
    result = voice_factory.build_voice_components(
        settings=settings(enabled=False),
        provider_classes=classes(),
    )

    assert result["enabled"] is False
    assert result["microphone"] is None
    assert result["backup_stt"] == []


def test_factory_builds_configured_local_providers():
    result = voice_factory.build_voice_components(
        settings=settings(),
        provider_classes=classes(),
    )

    assert result["enabled"] is True
    assert result["microphone"].kwargs["sample_rate"] == 16000
    assert result["vad"].kwargs["aggressiveness"] == 2
    assert result["primary_stt"].kwargs["model_name"] == "small"
    assert [
        item.kwargs["model_name"]
        for item in result["backup_stt"]
    ] == ["base", "medium"]
    assert result["tts"] is None


def test_factory_builds_tts_only_when_enabled():
    result = voice_factory.build_voice_components(
        settings=settings(tts=True),
        provider_classes=classes(),
    )

    assert result["tts"].kwargs["rate"] == 175
    assert result["tts"].kwargs["volume"] == 0.8
    assert result["tts"].kwargs["voice_id"] == "voice-1"


def test_unknown_provider_is_rejected():
    value = settings()
    value["voice"]["vad_provider"] = "unknown"

    try:
        voice_factory.build_voice_components(
            settings=value,
            provider_classes=classes(),
        )
    except ValueError as error:
        assert "unknown" in str(error)
    else:
        raise AssertionError("unknown provider should fail")



def test_factory_wraps_tts_when_async_is_enabled():
    value = settings(tts=True)
    value["voice"]["tts_async"] = True
    value["voice"]["tts_stop_timeout_seconds"] = 1.25

    result = voice_factory.build_voice_components(
        settings=value,
        provider_classes=classes(),
    )

    assert type(result["tts"]).__name__ == "InterruptibleTTS"
    assert result["tts"].stop_timeout_seconds == 1.25
    assert result["tts"].provider.kwargs["rate"] == 175



def test_factory_can_use_different_primary_and_backup_stt_providers():
    value = settings()
    value["voice"]["stt_provider"] = "accelerated"
    value["voice"]["backup_stt_provider"] = "faster_whisper"

    result = voice_factory.build_voice_components(
        settings=value,
        provider_classes=classes(),
    )

    assert isinstance(
        result["primary_stt"],
        AcceleratedRecorder,
    )
    assert all(
        isinstance(
            item,
            Recorder,
        )
        and not isinstance(
            item,
            AcceleratedRecorder,
        )
        for item in result["backup_stt"]
    )
