from copy import deepcopy
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from core.config import load_settings
from core.voice_activity import VoiceActivityGate
from core.voice_factory import build_voice_components


REPORT_PATH = (
    PROJECT_ROOT
    / "runtime"
    / "voice_hardware_validation_report.json"
)


def main():
    settings = load_settings()
    validation_settings = deepcopy(settings)
    voice = validation_settings.setdefault(
        "voice",
        {},
    )
    voice["enabled"] = True

    print("=" * 60)
    print("MyAI röst-hårdvaruverifiering")
    print("=" * 60)
    print(
        "Provider:",
        voice.get("microphone_provider"),
        "/",
        voice.get("vad_provider"),
        "/",
        voice.get("stt_provider"),
    )
    print(
        "STT-modell:",
        voice.get("stt_model"),
    )
    print()

    try:
        components = build_voice_components(
            validation_settings
        )
    except Exception as error:
        print("Kunde inte bygga röstproviders:")
        print(error)
        print()
        print(
            "Installera vid behov:"
        )
        print(
            "python -m pip install -r requirements-voice.txt"
        )
        return 1

    microphone = components["microphone"]
    vad = components["vad"]
    stt = components["primary_stt"]
    tts = components["tts"]

    gate = VoiceActivityGate(
        start_speech_frames=voice.get(
            "vad_start_speech_frames",
            2,
        ),
        end_silence_frames=voice.get(
            "vad_end_silence_frames",
            3,
        ),
        max_frames=voice.get(
            "vad_max_frames",
            500,
        ),
    )

    print(
        "När mikrofonen startar: säg en kort svensk mening "
        "och var sedan tyst."
    )
    input("Tryck Enter för att börja lyssna: ")

    frames = []
    overflow_count = 0
    started = False

    try:
        microphone.start()

        while True:
            item = microphone.read_frame()
            frame = item["frame"]

            if item.get("overflowed"):
                overflow_count += 1

            decision = vad.is_speech(frame)
            event = gate.feed(
                frame,
                decision,
            )

            if event is None:
                continue

            if event["type"] == "speech_started":
                started = True
                print("Tal upptäckt...")
                continue

            if event["type"] == "utterance_complete":
                frames = event["frames"]
                print(
                    "Yttrandet avslutades:",
                    event["reason"],
                )
                break
    finally:
        microphone.stop()

    if not started or not frames:
        print("Ingen användbar talaktivitet fångades.")
        return 1

    audio = b"".join(frames)

    print()
    print("Transkriberar lokalt...")

    try:
        transcript = stt.transcribe(audio)
    except Exception as error:
        print("STT misslyckades:")
        print(error)
        return 1

    text = transcript.get("text", "").strip()

    print("Transkription:")
    print(text or "(tom)")
    print()

    result = {
        "microphone": {
            "provider": voice.get(
                "microphone_provider"
            ),
            "overflow_count": overflow_count,
        },
        "vad": {
            "provider": voice.get(
                "vad_provider"
            ),
            "frames": len(frames),
        },
        "stt": {
            "provider": voice.get(
                "stt_provider"
            ),
            "model": voice.get(
                "stt_model"
            ),
            "text": text,
            "language": transcript.get(
                "language"
            ),
        },
        "tts": {
            "enabled": bool(tts),
            "provider": voice.get(
                "tts_provider"
            ),
        },
    }

    if tts is not None:
        print("Spelar ett kort TTS-test...")
        try:
            tts.speak(
                "Det här är ett rösttest från MyAI."
            )
            result["tts"]["success"] = True
        except Exception as error:
            result["tts"]["success"] = False
            result["tts"]["error"] = str(error)
            print("TTS misslyckades:")
            print(error)

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT_PATH.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Rapport sparad:")
    print(REPORT_PATH)

    if not text:
        print("Verifieringen underkändes: tom transkription.")
        return 1

    if (
        tts is not None
        and result["tts"].get("success") is False
    ):
        print("Verifieringen har TTS-fel.")
        return 1

    print("Röst-hårdvaruverifieringen är godkänd.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
