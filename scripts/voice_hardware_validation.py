from pathlib import Path
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from core.assistant import MyAICore
from core.config import load_settings
from modules.voice.runtime import build_voice_runtime


REPORT_PATH = (
    PROJECT_ROOT
    / "runtime"
    / "voice_hardware_validation_report.json"
)


def save_report(payload):
    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT_PATH.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main():
    settings = load_settings()
    voice = settings.get("voice", {})

    print("=" * 60)
    print("MyAI röst-hårdvaruverifiering")
    print("=" * 60)

    required = {
        "voice.enabled": voice.get("enabled"),
        "microphone_provider": voice.get(
            "microphone_provider"
        ),
        "stt_provider": voice.get("stt_provider"),
        "tts_provider": voice.get("tts_provider"),
    }

    missing = [
        name
        for name, value in required.items()
        if not value
    ]

    if missing:
        payload = {
            "status": "SKIP",
            "reason": (
                "Röstkedjan är inte fullt konfigurerad: "
                + ", ".join(missing)
            ),
        }
        print(payload["reason"])
        save_report(payload)
        return 2

    core = MyAICore(
        settings,
        PROJECT_ROOT,
    )
    core.initialize()

    try:
        runtime = build_voice_runtime(
            core,
            settings,
        )
    except Exception as error:
        payload = {
            "status": "FAIL",
            "reason": (
                "Röstkedjan kunde inte byggas: "
                + str(error)
            ),
        }
        print(payload["reason"])
        save_report(payload)
        return 1

    print()
    print("Konfigurerad röstkedja:")
    print(json.dumps(
        runtime.status(),
        ensure_ascii=False,
        indent=2,
    ))

    try:
        started = runtime.start()
    except Exception as error:
        payload = {
            "status": "FAIL",
            "reason": (
                "Röstkedjan kunde inte startas: "
                + str(error)
            ),
        }
        print(payload["reason"])
        save_report(payload)
        return 1

    if not started.get("started"):
        payload = {
            "status": "FAIL",
            "reason": started.get(
                "reason",
                "Röstkedjan startade inte.",
            ),
            "runtime_status": runtime.status(),
        }
        print(payload["reason"])
        save_report(payload)
        return 1

    print()
    print(
        "Röstkedjan är aktiv. Säg en kort tydlig testfras, "
        "till exempel: 'Säg att rösttestet fungerar.'"
    )
    print(
        "Vänta tills MyAI har svarat eller tills ett fel märks."
    )
    input(
        "Tryck Enter här när testet är färdigt: "
    )

    stop_result = runtime.stop()
    completed = list(
        runtime.completed_results
    )

    successful = [
        item
        for item in completed
        if (
            item.get("session_result")
            and item["session_result"].get("status")
            == "completed"
            and item["session_result"].get(
                "assistant_result"
            )
        )
    ]

    microphone = runtime.microphone
    callback_error = (
        getattr(microphone, "last_error", None)
        if microphone is not None
        else None
    )
    stream_status = (
        getattr(microphone, "last_status", None)
        if microphone is not None
        else None
    )

    if successful and not callback_error:
        last = successful[-1]["session_result"]
        payload = {
            "status": "PASS",
            "completed_utterances": len(completed),
            "accepted_text": (
                last.get("decision", {})
                .get("text")
            ),
            "stt_consensus": last.get(
                "decision"
            ),
            "spoken": last.get("spoken"),
            "tts_error": last.get("tts_error"),
            "stream_status": stream_status,
            "stop_result": stop_result,
        }
        print()
        print("Rösttestet är godkänt.")
        print(
            "Accepterad text:",
            payload["accepted_text"],
        )
        save_report(payload)
        return 0

    payload = {
        "status": "FAIL",
        "reason": (
            callback_error
            or "Inget komplett godkänt yttrande registrerades."
        ),
        "completed_utterances": len(completed),
        "stream_status": stream_status,
        "stop_result": stop_result,
    }
    print()
    print("Rösttestet misslyckades:", payload["reason"])
    save_report(payload)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
