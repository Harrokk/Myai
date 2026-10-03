from pathlib import Path

from core.config import PROJECT_ROOT, load_settings
from core.vision_client import VisionClient


DEFAULT_PROMPT = (
    "Beskriv vad som syns i bilden. Var tydlig med osäkerhet och "
    "hitta inte på detaljer som inte går att se."
)


def latest_capture(capture_dir=None):
    directory = (
        Path(capture_dir)
        if capture_dir is not None
        else PROJECT_ROOT / "runtime" / "captures"
    )

    if not directory.exists():
        return None

    candidates = []

    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        candidates.extend(directory.glob(pattern))

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )


def analyze_latest_capture(
    prompt=DEFAULT_PROMPT,
    settings=None,
    client=None,
    capture_dir=None,
):
    settings = settings or load_settings()
    vision = settings.get("vision", {})

    if not vision.get("enabled", False):
        return (
            "Visionanalys är avstängd. Aktivera den först och konfigurera "
            "en multimodal visionmodell."
        )

    model = (vision.get("model") or "").strip()

    if not model:
        return "Ingen visionmodell är konfigurerad."

    image_path = latest_capture(capture_dir)

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
        prompt,
        timeout=timeout,
    )

    return (
        f"Bildanalys av {image_path.name}:\n"
        f"{answer}"
    )


def vision_analyze():
    try:
        return analyze_latest_capture()
    except Exception as error:
        return f"Visionanalysen misslyckades: {error}"


TOOLS = {
    "vision_analyze": {
        "function": vision_analyze,
        "description": (
            "Analyserar den senast sparade kamerabilden med en uttryckligen "
            "konfigurerad multimodal visionmodell."
        ),
    }
}
