from datetime import datetime
from pathlib import Path
import platform
import time

from core.config import PROJECT_ROOT, load_settings
from modules.camera.capture import (
    _load_cv2,
    camera_enabled,
    configured_camera_index,
    resolve_capture_dir,
)


DEFAULT_VIDEO_DIR = PROJECT_ROOT / "runtime" / "video"
MAX_VIDEO_DURATION_SECONDS = 60.0
MAX_VIDEO_FPS = 30.0
MAX_VIDEO_FRAMES = 1800


def default_video_path(video_dir=DEFAULT_VIDEO_DIR, now=None):
    video_dir = Path(video_dir)
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")
    return video_dir / f"video_{timestamp}.mp4"


def record_clip(
    camera_index=0,
    output_path=None,
    duration_seconds=5.0,
    fps=10.0,
    cv2_module=None,
    clock=time.monotonic,
    sleep_fn=time.sleep,
):
    cv2 = cv2_module or _load_cv2()

    try:
        duration = float(duration_seconds)
        frame_rate = float(fps)
    except (TypeError, ValueError) as error:
        raise ValueError("Video duration/fps måste vara numeriska.") from error

    if (
        duration <= 0
        or duration > MAX_VIDEO_DURATION_SECONDS
    ):
        raise ValueError(
            "Video duration måste vara större än 0 och "
            f"högst {MAX_VIDEO_DURATION_SECONDS:g} sekunder."
        )

    if (
        frame_rate <= 0
        or frame_rate > MAX_VIDEO_FPS
    ):
        raise ValueError(
            "Video fps måste vara större än 0 och "
            f"högst {MAX_VIDEO_FPS:g}."
        )

    output = (
        Path(output_path)
        if output_path is not None
        else default_video_path()
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    backend = None

    if platform.system().lower() == "windows":
        backend = getattr(cv2, "CAP_DSHOW", None)

    camera = (
        cv2.VideoCapture(camera_index, backend)
        if backend is not None
        else cv2.VideoCapture(camera_index)
    )
    writer = None

    try:
        if not camera.isOpened():
            return {
                "success": False,
                "camera_index": camera_index,
                "path": None,
                "frames": 0,
                "error": "Kameran kunde inte öppnas för video.",
            }

        ok, first_frame = camera.read()

        if not ok or first_frame is None:
            return {
                "success": False,
                "camera_index": camera_index,
                "path": None,
                "frames": 0,
                "error": "Ingen första videobildruta kunde läsas.",
            }

        shape = getattr(first_frame, "shape", ())

        if len(shape) < 2:
            return {
                "success": False,
                "camera_index": camera_index,
                "path": None,
                "frames": 0,
                "error": "Videobildrutans storlek kunde inte bestämmas.",
            }

        height = int(shape[0])
        width = int(shape[1])
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(output),
            fourcc,
            frame_rate,
            (width, height),
        )

        if hasattr(writer, "isOpened") and not writer.isOpened():
            return {
                "success": False,
                "camera_index": camera_index,
                "path": None,
                "frames": 0,
                "error": "Videofilen kunde inte öppnas för skrivning.",
            }

        frame_target = min(
            MAX_VIDEO_FRAMES,
            max(
                1,
                int(
                    round(
                        duration
                        * frame_rate
                    )
                ),
            ),
        )
        writer.write(
            first_frame
        )
        frames = 1
        started_at = float(
            clock()
        )

        while frames < frame_target:
            deadline = (
                started_at
                + (
                    frames
                    / frame_rate
                )
            )
            delay = (
                deadline
                - float(
                    clock()
                )
            )

            if delay > 0:
                sleep_fn(
                    delay
                )

            ok, frame = camera.read()

            if not ok or frame is None:
                break

            writer.write(
                frame
            )
            frames += 1

        if frames < frame_target:
            return {
                "success": False,
                "camera_index": camera_index,
                "path": str(output),
                "frames": frames,
                "width": width,
                "height": height,
                "fps": frame_rate,
                "duration_seconds": duration,
                "error": (
                    f"Videoinspelningen avbröts efter {frames} av "
                    f"{frame_target} bildrutor."
                ),
            }

        return {
            "success": True,
            "camera_index": camera_index,
            "path": str(output),
            "frames": frames,
            "width": width,
            "height": height,
            "fps": frame_rate,
            "duration_seconds": duration,
            "error": None,
        }
    finally:
        camera.release()

        if writer is not None:
            writer.release()


def record_video_from_settings(
    settings=None,
    cv2_module=None,
):
    settings = settings or load_settings()
    camera = settings.get("camera", {})

    if not camera_enabled(
        settings
    ):
        return {
            "success": False,
            "disabled": True,
            "camera_index": None,
            "path": None,
            "frames": 0,
            "error": (
                "Kameran är avstängd i konfigurationen."
            ),
        }

    index = configured_camera_index(settings)

    video_dir_value = camera.get("video_dir", "runtime/video")
    video_dir = resolve_capture_dir(video_dir_value)

    duration = camera.get("video_duration_seconds", 5)
    fps = camera.get("video_fps", 10)

    return record_clip(
        camera_index=index,
        output_path=default_video_path(video_dir),
        duration_seconds=duration,
        fps=fps,
        cv2_module=cv2_module,
    )


def format_video_result(result):
    if not result.get("success"):
        return (
            "Videoinspelningen misslyckades: "
            + (result.get("error") or "okänt fel")
        )

    return (
        f"Videoklipp sparat lokalt: {result['path']} "
        f"({result['width']}x{result['height']}, "
        f"{result['frames']} bildrutor, {result['fps']:.1f} fps)."
    )


def camera_record_video():
    try:
        return format_video_result(record_video_from_settings())
    except Exception as error:
        return f"Videoinspelningen misslyckades: {error}"


TOOLS = {
    "camera_record_video": {
        "function": camera_record_video,
        "description": (
            "Spelar in ett kort videoklipp från den konfigurerade kameran, "
            "sparar det lokalt och stänger kameran direkt efteråt."
        ),
    }
}
