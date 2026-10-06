from pathlib import Path

from core.config import PROJECT_ROOT, load_settings
from core.vision_factory import build_vision_client


CHANGE_PROMPT = (
    "Jämför de två bilderna i den ordning de skickades: den första är äldre "
    "och den andra är nyare. Beskriv endast tydliga visuella förändringar "
    "mellan bilderna. Gissa inte orsak, rörelse, identitet eller händelser "
    "som inte kan fastställas från två stillbilder. "
    "Om ingen tydlig förändring kan ses, svara exakt: INGEN TYDLIG FÖRÄNDRING."
)


def recent_captures(capture_dir=None, count=2):
    directory = (
        Path(capture_dir)
        if capture_dir is not None
        else PROJECT_ROOT / "runtime" / "captures"
    )

    if not directory.exists():
        return []

    candidates = []

    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        candidates.extend(directory.glob(pattern))

    ordered = sorted(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )

    return ordered[-max(1, int(count)):]


def detect_latest_change(
    settings=None,
    client=None,
    capture_dir=None,
):
    settings = settings or load_settings()
    vision = settings.get("vision", {})

    if not vision.get("enabled", False):
        return (
            "Förändringsdetektering är avstängd. Aktivera vision först och "
            "konfigurera en multimodal visionmodell."
        )

    model = (vision.get("model") or "").strip()

    if not model:
        return "Ingen visionmodell är konfigurerad för förändringsdetektering."

    images = recent_captures(capture_dir, count=2)

    if len(images) < 2:
        return (
            "Minst två sparade kamerabilder krävs för att jämföra förändringar."
        )

    active_client = client or build_vision_client(settings)

    timeout = int(vision.get("timeout_seconds", 120))
    answer = active_client.analyze_images(
        images,
        CHANGE_PROMPT,
        timeout=timeout,
    )

    return (
        f"Förändringsanalys: {images[0].name} -> {images[1].name}:\n"
        f"{answer}"
    )


def vision_detect_change():
    try:
        return detect_latest_change()
    except Exception as error:
        return f"Förändringsdetekteringen misslyckades: {error}"


TOOLS = {
    "vision_detect_change": {
        "function": vision_detect_change,
        "description": (
            "Jämför de två senaste kamerabilderna och beskriver tydliga "
            "visuella förändringar utan att gissa orsak eller rörelse."
        ),
    }
}
