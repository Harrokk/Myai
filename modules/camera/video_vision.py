from pathlib import Path

from core.config import PROJECT_ROOT, load_settings
from core.vision_client import VisionClient
from modules.camera.capture import resolve_capture_dir
from modules.camera.video_frames import latest_video


VIDEO_SUMMARY_PROMPT = (
    "Bilderna är representativa bildrutor från samma videoklipp och skickas "
    "i kronologisk ordning från tidigast till senast. Sammanfatta vad som "
    "faktiskt är synligt över klippet. Beskriv tydliga förändringar mellan "
    "samplingarna, men gissa inte vad som hände mellan dem. Gissa inte "
    "orsak, identitet, avsikt eller rörelse som inte stöds av bilderna. "
    "Var tydlig med att underlaget är samplingar och inte varje videobildruta."
)


def latest_video_sample_set(settings=None):
    settings = settings or load_settings()
    camera = settings.get("camera", {})

    video_dir = resolve_capture_dir(
        camera.get("video_dir", "runtime/video")
    )
    frame_root = resolve_capture_dir(
        camera.get("video_frame_dir", "runtime/video_frames")
    )

    video_path = latest_video(video_dir)

    if video_path is None:
        return {
            "video_path": None,
            "frame_dir": None,
            "frames": [],
        }

    frame_dir = frame_root / video_path.stem

    if not frame_dir.exists():
        return {
            "video_path": video_path,
            "frame_dir": frame_dir,
            "frames": [],
        }

    frames = sorted(
        frame_dir.glob(f"{video_path.stem}_sample_*_frame_*.jpg"),
        key=lambda path: path.name,
    )

    return {
        "video_path": video_path,
        "frame_dir": frame_dir,
        "frames": frames,
    }


def analyze_latest_video_samples(
    settings=None,
    client=None,
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

    sample_set = latest_video_sample_set(settings)
    video_path = sample_set["video_path"]
    frames = sample_set["frames"]

    if video_path is None:
        return "Ingen sparad video hittades."

    if not frames:
        return (
            "Inga representativa bildrutor hittades för den senaste videon. "
            "Kör camera_sample_video_frames först."
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
    answer = active_client.analyze_images(
        frames,
        VIDEO_SUMMARY_PROMPT,
        timeout=timeout,
    )

    return (
        f"Videoanalys av {Path(video_path).name} "
        f"baserad på {len(frames)} representativa bildrutor:\n"
        f"{answer}"
    )


def vision_analyze_video():
    try:
        return analyze_latest_video_samples()
    except Exception as error:
        return f"Videoanalysen misslyckades: {error}"


TOOLS = {
    "vision_analyze_video": {
        "function": vision_analyze_video,
        "description": (
            "Analyserar representativa, kronologiskt ordnade bildrutor från "
            "den senast sparade videon med den konfigurerade visionmodellen."
        ),
    }
}
