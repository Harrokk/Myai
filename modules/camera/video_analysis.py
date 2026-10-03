from pathlib import Path

from core.config import load_settings
from core.vision_client import VisionClient
from modules.camera.video_frames import (
    sample_frame_indices,
    sample_latest_video_from_settings,
)


MAX_ANALYSIS_FRAMES = 8

VIDEO_ANALYSIS_PROMPT = (
    "Du får ett litet antal representativa bildrutor från en video i "
    "kronologisk ordning. Sammanfatta endast sådant som faktiskt stöds av "
    "de här bildrutorna. Beskriv återkommande objekt, tydliga förändringar "
    "och en försiktig övergripande scenbeskrivning. "
    "Påstå inte att du har sett varje bildruta i videon. "
    "Gissa inte ljud, motiv, identitet, orsak, exakt rörelse eller händelser "
    "som inte kan fastställas från de samplade bilderna. "
    "Markera viktig osäkerhet tydligt."
)


def _select_analysis_frames(frames, max_frames=MAX_ANALYSIS_FRAMES):
    if not frames:
        return []

    limit = max(1, int(max_frames))

    if len(frames) <= limit:
        return list(frames)

    indices = sample_frame_indices(len(frames), limit)
    return [frames[index] for index in indices]


def analyze_latest_video(
    settings=None,
    client=None,
    sampler=None,
):
    settings = settings or load_settings()
    vision = settings.get("vision", {})

    if not vision.get("enabled", False):
        return (
            "Videoanalys är avstängd. Aktivera vision först och konfigurera "
            "en multimodal visionmodell."
        )

    model = (vision.get("model") or "").strip()

    if not model:
        return "Ingen visionmodell är konfigurerad för videoanalys."

    sample_function = sampler or sample_latest_video_from_settings
    sampled = sample_function(settings=settings)

    if not sampled.get("success"):
        return (
            "Videoanalysen kunde inte förberedas: "
            + (sampled.get("error") or "okänt samplingsfel")
        )

    frames = _select_analysis_frames(sampled.get("frames", []))

    if not frames:
        return "Videoanalysen kunde inte förberedas: inga bildrutor hittades."

    image_paths = [Path(item["path"]) for item in frames]

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
    answer = active_client.analyze_images(
        image_paths,
        VIDEO_ANALYSIS_PROMPT,
        timeout=timeout,
    )

    video_name = Path(
        sampled.get("video_path") or "okänd video"
    ).name

    return (
        f"Videoanalys av {video_name} baserad på "
        f"{len(image_paths)} representativa bildrutor:\n"
        f"{answer}"
    )


def vision_analyze_video():
    try:
        return analyze_latest_video()
    except Exception as error:
        return f"Videoanalysen misslyckades: {error}"


TOOLS = {
    "vision_analyze_video": {
        "function": vision_analyze_video,
        "description": (
            "Analyserar representativa bildrutor från den senast sparade "
            "videon med den konfigurerade lokala multimodala visionmodellen."
        ),
    }
}
