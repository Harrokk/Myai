from pathlib import Path

from core.config import PROJECT_ROOT, load_settings
from core.vision_client import VisionClient
from modules.camera.vision import latest_capture


OCR_PROMPT = (
    "Läs av all text som faktiskt är synlig i bilden. "
    "Transkribera så troget som möjligt och bevara radbrytningar när det går. "
    "Gissa inte bokstäver eller ord som inte går att urskilja. "
    "Om ingen läsbar text finns, svara exakt: INGEN LÄSBAR TEXT."
)


def read_text_latest_capture(
    settings=None,
    client=None,
    capture_dir=None,
):
    settings = settings or load_settings()
    vision = settings.get("vision", {})

    if not vision.get("enabled", False):
        return (
            "Textläsning i bild är avstängd. Aktivera vision först och "
            "konfigurera en multimodal visionmodell."
        )

    model = (vision.get("model") or "").strip()

    if not model:
        return "Ingen visionmodell är konfigurerad för textläsning."

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
        OCR_PROMPT,
        timeout=timeout,
    )

    return (
        f"Textläsning av {Path(image_path).name}:\n"
        f"{answer}"
    )


def vision_read_text():
    try:
        return read_text_latest_capture()
    except Exception as error:
        return f"Textläsningen misslyckades: {error}"


TOOLS = {
    "vision_read_text": {
        "function": vision_read_text,
        "description": (
            "Läser text i den senast sparade kamerabilden med den "
            "konfigurerade lokala multimodala visionmodellen."
        ),
    }
}
