from pathlib import Path

from core.config import PROJECT_ROOT, load_settings
from core.vision_client import VisionClient
from modules.camera.vision import latest_capture


OBJECT_PROMPT = (
    "Identifiera de objekt som faktiskt syns i bilden. "
    "Lista bara objekt som har tydligt visuellt stöd. "
    "För varje objekt, ange en försiktig konfidensnivå: hög, medel eller låg. "
    "Gissa inte dolda objekt, märken, personer eller detaljer som inte går att se. "
    "Om inga objekt kan identifieras säkert, svara exakt: INGA SÄKRA OBJEKT."
)


def detect_objects_latest_capture(
    settings=None,
    client=None,
    capture_dir=None,
):
    settings = settings or load_settings()
    vision = settings.get("vision", {})

    if not vision.get("enabled", False):
        return (
            "Objektidentifiering är avstängd. Aktivera vision först och "
            "konfigurera en multimodal visionmodell."
        )

    model = (vision.get("model") or "").strip()

    if not model:
        return "Ingen visionmodell är konfigurerad för objektidentifiering."

    image_path = latest_capture(
        capture_dir
        if capture_dir is not None
        else PROJECT_ROOT / "runtime" / "captures"
    )

    if image_path is None:
        return (
            "Ingen sparad kamerabild hittades. Ta en bild först med "
            "camera_capture."
        )

    active_client = client or VisionClient(
        url=vision.get(
            "url",
            settings.get("ollama", {}).get(
                "url",
                "http://localhost:11434/api/chat",
            ),
        ),
        model=model,
        enabled=True,
    )

    timeout = int(vision.get("timeout_seconds", 120))
    answer = active_client.analyze(
        image_path,
        OBJECT_PROMPT,
        timeout=timeout,
    )

    return (
        f"Objektidentifiering av {Path(image_path).name}:\n"
        f"{answer}"
    )


def vision_detect_objects():
    try:
        return detect_objects_latest_capture()
    except Exception as error:
        return f"Objektidentifieringen misslyckades: {error}"


TOOLS = {
    "vision_detect_objects": {
        "function": vision_detect_objects,
        "description": (
            "Identifierar synliga objekt i den senast sparade kamerabilden "
            "med den konfigurerade lokala multimodala visionmodellen."
        ),
    }
}
