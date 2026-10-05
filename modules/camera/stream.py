import platform
import time

from core.config import load_settings
from modules.camera.capture import (
    _load_cv2,
    camera_enabled,
    configured_camera_index,
)


MAX_STREAM_DURATION_SECONDS = 60.0
MAX_STREAM_FPS = 30.0
MAX_STREAM_FRAMES = 300


def _stream_config(settings):
    camera = settings.get("camera", {})

    enabled = bool(
        camera_enabled(
            settings
        )
        and camera.get(
            "stream_enabled",
            False,
        )
    )

    try:
        duration = float(camera.get("stream_duration_seconds", 5))
        fps = float(camera.get("stream_fps", 2))
        max_frames = int(camera.get("stream_max_frames", 10))
    except (TypeError, ValueError) as error:
        raise ValueError("Kamerastreamens gränser måste vara numeriska.") from error

    if duration <= 0 or duration > MAX_STREAM_DURATION_SECONDS:
        raise ValueError(
            f"stream_duration_seconds måste vara > 0 och <= "
            f"{MAX_STREAM_DURATION_SECONDS:g}."
        )

    if fps <= 0 or fps > MAX_STREAM_FPS:
        raise ValueError(
            f"stream_fps måste vara > 0 och <= {MAX_STREAM_FPS:g}."
        )

    if max_frames <= 0 or max_frames > MAX_STREAM_FRAMES:
        raise ValueError(
            f"stream_max_frames måste vara > 0 och <= "
            f"{MAX_STREAM_FRAMES}."
        )

    target_frames = min(
        max_frames,
        max(1, int(round(duration * fps))),
    )

    return {
        "enabled": enabled,
        "duration_seconds": duration,
        "fps": fps,
        "max_frames": max_frames,
        "target_frames": target_frames,
    }


def run_bounded_stream(
    settings=None,
    cv2_module=None,
    frame_handler=None,
    sleep_fn=time.sleep,
):
    settings = settings or load_settings()
    limits = _stream_config(settings)

    if not limits["enabled"]:
        return {
            "success": False,
            "disabled": True,
            "camera_index": None,
            "frames": 0,
            "width": None,
            "height": None,
            "fps": limits["fps"],
            "target_frames": limits["target_frames"],
            "error": (
                "Kameran eller kamerastreamen är avstängd "
                "i konfigurationen."
            ),
        }

    camera_index = configured_camera_index(settings)
    cv2 = cv2_module or _load_cv2()

    backend = None

    if platform.system().lower() == "windows":
        backend = getattr(cv2, "CAP_DSHOW", None)

    camera = (
        cv2.VideoCapture(camera_index, backend)
        if backend is not None
        else cv2.VideoCapture(camera_index)
    )

    frames_read = 0
    width = None
    height = None
    interval = 1.0 / limits["fps"]

    try:
        if not camera.isOpened():
            return {
                "success": False,
                "disabled": False,
                "camera_index": camera_index,
                "frames": 0,
                "width": None,
                "height": None,
                "fps": limits["fps"],
                "target_frames": limits["target_frames"],
                "error": "Kameran kunde inte öppnas för stream-test.",
            }

        for index in range(limits["target_frames"]):
            ok, frame = camera.read()

            if not ok or frame is None:
                return {
                    "success": False,
                    "disabled": False,
                    "camera_index": camera_index,
                    "frames": frames_read,
                    "width": width,
                    "height": height,
                    "fps": limits["fps"],
                    "target_frames": limits["target_frames"],
                    "error": (
                        "Kamerastreamen slutade leverera bildrutor "
                        f"efter {frames_read} frames."
                    ),
                }

            shape = getattr(frame, "shape", ())

            if len(shape) >= 2:
                height = int(shape[0])
                width = int(shape[1])

            frames_read += 1

            if frame_handler is not None:
                frame_handler(
                    frame,
                    {
                        "index": index,
                        "camera_index": camera_index,
                        "width": width,
                        "height": height,
                    },
                )

            if index + 1 < limits["target_frames"]:
                sleep_fn(interval)

        return {
            "success": True,
            "disabled": False,
            "camera_index": camera_index,
            "frames": frames_read,
            "width": width,
            "height": height,
            "fps": limits["fps"],
            "target_frames": limits["target_frames"],
            "error": None,
        }
    finally:
        camera.release()


def format_stream_result(result):
    if result.get("disabled"):
        return (
            "Kamerastream är avstängd. Aktivera camera.stream_enabled "
            "för ett begränsat stream-test."
        )

    if not result.get("success"):
        return (
            "Kamerastream-testet misslyckades: "
            + (result.get("error") or "okänt fel")
        )

    dimensions = ""

    if result.get("width") and result.get("height"):
        dimensions = f", {result['width']}x{result['height']}"

    return (
        f"Kamerastream-test godkänt: {result['frames']} bildrutor "
        f"vid {result['fps']:.1f} fps{dimensions}, "
        f"kameraindex {result['camera_index']}."
    )


def camera_stream_status():
    try:
        return format_stream_result(run_bounded_stream())
    except Exception as error:
        return f"Kamerastream-testet misslyckades: {error}"


TOOLS = {
    "camera_stream_status": {
        "function": camera_stream_status,
        "description": (
            "Kör ett konfigurerat och hårt begränsat kamerastream-test "
            "och rapporterar om kameran levererar bildrutor stabilt."
        ),
    }
}
