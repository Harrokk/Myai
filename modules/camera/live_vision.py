from core.config import load_settings
from core.vision_factory import build_vision_client
from modules.camera.capture import _load_cv2
from modules.camera.stream import run_bounded_stream


MAX_LIVE_VISION_FRAMES = 6

LIVE_VISION_PROMPT = (
    "Du får ett litet antal bildrutor från en kort och begränsad livekamera-"
    "session i kronologisk ordning. Beskriv endast sådant som faktiskt stöds "
    "av bildrutorna. Markera tydlig osäkerhet. "
    "Påstå inte att du har sett en kontinuerlig videoström mellan frames. "
    "Gissa inte ljud, identitet, avsikt, orsak eller händelser som inte kan "
    "fastställas visuellt från de här bildrutorna."
)


def analyze_live_camera(
    settings=None,
    client=None,
    cv2_module=None,
    stream_runner=None,
):
    settings = settings or load_settings()
    vision = settings.get("vision", {})

    if not vision.get("enabled", False):
        return (
            "Live-vision är avstängd eftersom visionanalys inte är aktiverad."
        )

    model = (vision.get("model") or "").strip()

    if not model:
        return "Ingen visionmodell är konfigurerad för live-vision."

    camera = dict(settings.get("camera", {}))

    if not camera.get("stream_enabled", False):
        return (
            "Live-vision är avstängd eftersom camera.stream_enabled är false."
        )

    try:
        configured_max = int(
            camera.get("stream_max_frames", MAX_LIVE_VISION_FRAMES)
        )
    except (TypeError, ValueError) as error:
        raise ValueError("camera.stream_max_frames måste vara ett heltal.") from error

    camera["stream_max_frames"] = min(
        MAX_LIVE_VISION_FRAMES,
        max(1, configured_max),
    )

    active_settings = dict(settings)
    active_settings["camera"] = camera

    cv2 = cv2_module or _load_cv2()
    encoded_frames = []

    def handle_frame(frame, metadata):
        ok, buffer = cv2.imencode(".jpg", frame)

        if not ok:
            raise RuntimeError(
                f"Liveframe {metadata.get('index')} kunde inte JPEG-kodas."
            )

        encoded_frames.append(buffer.tobytes())

    runner = stream_runner or run_bounded_stream
    stream_result = runner(
        settings=active_settings,
        cv2_module=cv2,
        frame_handler=handle_frame,
    )

    if not stream_result.get("success"):
        return (
            "Live-vision kunde inte samla bildrutor: "
            + (stream_result.get("error") or "okänt streamfel")
        )

    if not encoded_frames:
        return "Live-vision kunde inte samla några analyserbara bildrutor."

    active_client = client or build_vision_client(settings)

    timeout = int(vision.get("timeout_seconds", 120))
    answer = active_client.analyze_bytes(
        encoded_frames,
        LIVE_VISION_PROMPT,
        timeout=timeout,
    )

    return (
        f"Live-vision baserad på {len(encoded_frames)} begränsade "
        f"kameraframes:\n{answer}"
    )


def vision_analyze_live():
    try:
        return analyze_live_camera()
    except Exception as error:
        return f"Live-vision misslyckades: {error}"


TOOLS = {
    "vision_analyze_live": {
        "function": vision_analyze_live,
        "description": (
            "Analyserar ett litet, hårt begränsat urval av liveframes direkt "
            "från den konfigurerade kameran utan automatisk disksparning."
        ),
    }
}
