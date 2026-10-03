import requests

from core.assistant import MyAICore
from core.config import PROJECT_ROOT, load_settings
from core.device_registry import (
    DeviceRegistry,
    format_configuration_prompt,
    format_device_records,
)
from core.hardware_monitor import (
    HardwareMonitor,
    format_hardware_changes,
)


SETTINGS = load_settings()
CORE = MyAICore(
    SETTINGS,
    PROJECT_ROOT,
)

# Kompatibilitetsalias medan projektet byggs om stegvis.
TOOLS = CORE.tools
MEMORY = CORE.memory
LLM = CORE.llm
OLLAMA_URL = CORE.ollama_url
MODEL = CORE.model
DEVICE_REGISTRY = DeviceRegistry()
VOICE_SESSION = None


def _create_voice_session():
    # Importeras medvetet först när användaren faktiskt begär röstläge.
    from core.voice_session import VoiceSession

    return VoiceSession(
        CORE,
        settings=SETTINGS,
    )


def get_voice_session(factory=None):
    global VOICE_SESSION

    if VOICE_SESSION is None:
        builder = factory or _create_voice_session
        VOICE_SESSION = builder()

    return VOICE_SESSION


def voice_status_text():
    configured = SETTINGS.get(
        "voice",
        {},
    ).get("enabled", False)

    if VOICE_SESSION is None:
        return (
            "Röstläge: "
            + ("konfigurerat men inte startat" if configured else "avstängt")
            + " (ingen röstsession skapad)."
        )

    status = VOICE_SESSION.status()

    if not status.get("enabled"):
        return "Röstläge: avstängt."

    running = (
        "aktivt"
        if status.get("running")
        else "stoppat"
    )
    return (
        f"Röstläge: {running} | "
        f"mikrofon={status.get('microphone')} | "
        f"VAD={status.get('vad')} | "
        f"STT={status.get('primary_stt')} | "
        f"backup-STT={status.get('backup_stt_count', 0)} | "
        f"TTS={status.get('tts') or 'av'}"
    )


def stop_voice_session():
    if VOICE_SESSION is None:
        return False

    return bool(
        VOICE_SESSION.stop()
    )


def _print_hardware_changes(changes):
    text = format_hardware_changes(changes)

    if not text:
        return

    new_unknown = DEVICE_REGISTRY.observe_changes(changes)

    print()
    print("[Hårdvara]")
    print(text)

    if new_unknown:
        print()
        print("Nya okända enheter registrerades:")
        print(format_device_records(new_unknown))
        print()

        for record in new_unknown:
            print(format_configuration_prompt(record))
            print()

    print()


def _print_hardware_watch_error(error):
    print()
    print("[Hårdvaruövervakning]")
    print(f"Fel: {error}")
    print()


HARDWARE_MONITOR = HardwareMonitor(
    interval_seconds=SETTINGS.get(
        "hardware_watch",
        {},
    ).get("interval_seconds", 10),
    on_change=_print_hardware_changes,
    on_error=_print_hardware_watch_error,
)


print(f"Verktyg laddade: {len(TOOLS)}")

for tool_name in TOOLS:
    print(f" - {tool_name}")


def main():
    CORE.initialize()

    if SETTINGS.get("hardware_watch", {}).get("enabled", True):
        HARDWARE_MONITOR.start()
    print(f"Verktyg laddade: {len(TOOLS)}")
    print()
    print("==========================================")
    print(f"              {SETTINGS['assistant']['name']}")
    print("==========================================")
    print()
    print(f"Modell:          {MODEL}")
    print(f"Motor:           {SETTINGS['assistant']['engine']}")
    print(f"GPU:             {SETTINGS['assistant']['gpu']}")
    print(f"Långtidsminne:   {SETTINGS['assistant']['memory_label']}")
    print(f"Framtida mål:    {SETTINGS['assistant']['future_target']}")
    print()
    print("Kommandon:")
    print("  /memory        Visa långtidsminne")
    print("  /remember X    Spara X i minnet")
    print("  /clear         Rensa samtalets korttidsminne")
    print("  /watch         Visa hårdvaruövervakningens status")
    print("  /watch on      Starta hårdvaruövervakning")
    print("  /watch off     Stoppa hårdvaruövervakning")
    print("  /devices       Visa registrerade enheter")
    print("  /devices unknown  Visa okända enheter")
    print("  /device approve ID  Godkänn och spara en ny enhet")
    print("  /device reject ID   Avvisa konfiguration av en ny enhet")
    print("  /device known ID    Kompatibilitetskommando: markera som känd")
    print("  /voice         Visa röstlägets status")
    print("  /voice once    Lyssna efter ett yttrande och svara")
    print("  /voice stop    Stoppa pågående röstsession/TTS")
    print("  /exit          Avsluta")
    print()

    while True:
        try:
            user_input = input("Du: ").strip()

        except KeyboardInterrupt:
            HARDWARE_MONITOR.stop()
            stop_voice_session()
            print()
            print("Avslutar.")
            break

        if not user_input:
            continue

        if user_input.lower() == "/exit":
            HARDWARE_MONITOR.stop()
            stop_voice_session()
            print("Avslutar.")
            break

        if user_input.lower() == "/voice":
            print(voice_status_text())
            print()
            continue

        if user_input.lower() == "/voice stop":
            stopped = stop_voice_session()

            if stopped:
                print("Röstsessionen stoppades.")
            else:
                print("Ingen aktiv röstsession behövde stoppas.")

            print()
            continue

        if user_input.lower() == "/voice once":
            try:
                session = get_voice_session()

                if not session.enabled:
                    print(
                        "Röstläge är avstängt i konfigurationen. "
                        "Ingen mikrofon startades."
                    )
                    print()
                    continue

                print("Lyssnar efter ett yttrande...")

                try:
                    result = session.run_once()
                finally:
                    session.stop()

                voice_result = result.get(
                    "voice_result",
                    {},
                )

                if result.get("status") == "utterance_complete":
                    transcript = voice_result.get(
                        "transcript"
                    )

                    if transcript:
                        print(f"Du (röst): {transcript}")

                    if voice_result.get("status") == "clarify":
                        print(
                            voice_result.get(
                                "message",
                                "Röstkommandot behöver förtydligas.",
                            )
                        )
                    else:
                        answer = (
                            voice_result.get(
                                "assistant",
                                {},
                            ).get("answer")
                        )

                        if answer:
                            print("AI:")
                            print(answer)
                else:
                    print(
                        result.get(
                            "message",
                            "Ingen komplett talfras registrerades.",
                        )
                    )
            except Exception as error:
                print("Röstsessionen kunde inte köras:")
                print(error)

            print()
            continue

        if user_input.lower() == "/watch":
            status = (
                "aktiv"
                if HARDWARE_MONITOR.is_running
                else "stoppad"
            )
            print(
                "Hårdvaruövervakning:",
                status,
                f"({HARDWARE_MONITOR.interval_seconds:g} s intervall)",
            )
            print()
            continue

        if user_input.lower() == "/watch on":
            started = HARDWARE_MONITOR.start()

            if started:
                print("Hårdvaruövervakningen startades.")
            elif HARDWARE_MONITOR.is_running:
                print("Hårdvaruövervakningen är redan aktiv.")
            else:
                print("Hårdvaruövervakningen kunde inte startas.")

            print()
            continue

        if user_input.lower() == "/watch off":
            HARDWARE_MONITOR.stop()
            print("Hårdvaruövervakningen stoppades.")
            print()
            continue

        if user_input.lower() == "/devices":
            records = DEVICE_REGISTRY.list_records()
            print()
            print("========== ENHETSREGISTER ==========")
            print(format_device_records(records))
            print("====================================")
            print()
            continue

        if user_input.lower() == "/devices unknown":
            records = DEVICE_REGISTRY.list_records(known=False)
            print()
            print("========== OKÄNDA ENHETER ==========")
            print(format_device_records(records))
            print("====================================")
            print()
            continue

        if user_input.lower().startswith("/device approve "):
            device_id = user_input[len("/device approve "):].strip()

            if not device_id:
                print("Ange ett enhets-id.")
                print()
                continue

            try:
                record = DEVICE_REGISTRY.approve_configuration(device_id)
                print(
                    "Enheten godkändes och konfigurationen sparades:",
                    record.get("label") or record.get("name"),
                )
            except KeyError:
                print("Enhets-id hittades inte i registret.")

            print()
            continue

        if user_input.lower().startswith("/device reject "):
            device_id = user_input[len("/device reject "):].strip()

            if not device_id:
                print("Ange ett enhets-id.")
                print()
                continue

            try:
                record = DEVICE_REGISTRY.reject_configuration(device_id)
                print(
                    "Enheten avvisades:",
                    record.get("label") or record.get("name"),
                )
            except KeyError:
                print("Enhets-id hittades inte i registret.")

            print()
            continue

        if user_input.lower().startswith("/device known "):
            device_id = user_input[len("/device known "):].strip()

            if not device_id:
                print("Ange ett enhets-id.")
                print()
                continue

            try:
                record = DEVICE_REGISTRY.mark_known(device_id)
                print(
                    "Enheten markerades som känd:",
                    record.get("label") or record.get("name"),
                )
            except KeyError:
                print("Enhets-id hittades inte i registret.")

            print()
            continue

        if user_input.lower() == "/clear":
            CORE.clear_conversation()
            print("Korttidsminnet för samtalet är rensat.")
            print()
            continue

        if user_input.lower().startswith("/remember "):
            memory_content = user_input[len("/remember "):].strip()

            if memory_content:
                MEMORY.save("manual", memory_content)
                print("Sparat i långtidsminnet.")
            else:
                print("Inget innehåll att spara.")

            print()
            continue

        if user_input.lower() == "/memory":
            memories = MEMORY.get_all()

            print()
            print("========== LÅNGTIDSMINNE ==========")

            if not memories:
                print("Inget minne sparat.")
            else:
                for memory in memories:
                    memory_id, category, content, created_at = memory
                    print(f"{memory_id}. [{category}] {content}")

            print("===================================")
            print()
            continue

        try:
            print()
            print("AI tänker...")
            print()

            result = CORE.respond(user_input)

            if result["tools"]:
                print("Verktyg:")

                for tool in result["tools"]:
                    print(f" - {tool}")

                print()

            print("AI:")
            print(result["answer"])
            print()

        except requests.exceptions.ConnectionError:
            print()
            print("Kunde inte ansluta till Ollama.")
            print()

        except Exception as error:
            print()
            print("Ett fel uppstod:")
            print(error)
            print()


if __name__ == "__main__":
    main()