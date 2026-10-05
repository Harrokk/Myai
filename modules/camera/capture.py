from datetime import datetime
from pathlib import Path
import platform

from core.config import PROJECT_ROOT, load_settings
DEFAULT_CAPTURE_DIR = PROJECT_ROOT / "runtime" / "captures"


def _load_cv2():
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError(
            "Kamerabildtagning kräver OpenCV. "
            "Installera requirements-camera.txt."
        ) from error

    return cv2


def default_capture_path(capture_dir=DEFAULT_CAPTURE_DIR, now=None):
    capture_dir = Path(capture_dir)
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")
    return capture_dir / f"capture_{timestamp}.jpg"


def resolve_capture_dir(value=None):
    path = Path(value or "runtime/captures")

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


def camera_enabled(
    settings,
):
    return bool(
        settings.get(
            "camera",
            {},
        ).get(
            "enabled",
            True,
        )
    )


def configured_camera_index(settings):
    camera = settings.get("camera", {})
    value = camera.get("default_index", 0)

    try:
        index = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("camera.default_index måste vara ett heltal.") from error

    if index < 0:
        raise ValueError("camera.default_index får inte vara negativt.")

    return index


def capture_frame(
    camera_index=0,
    output_path=None,
    cv2_module=None,
):
    """Ta en enda bildruta och stäng kameran direkt efteråt."""
    cv2 = cv2_module or _load_cv2()
    output = (
        Path(output_path)
        if output_path is not None
        else default_capture_path()
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

    try:
        if not camera.isOpened():
            return {
                "success": False,
                "camera_index": camera_index,
                "path": None,
                "error": "Kameran kunde inte öppnas.",
            }

        ok, frame = camera.read()

        if not ok or frame is None:
            return {
                "success": False,
                "camera_index": camera_index,
                "path": None,
                "error": "Ingen bildruta kunde läsas från kameran.",
            }

        if not cv2.imwrite(str(output), frame):
            return {
                "success": False,
                "camera_index": camera_index,
                "path": None,
                "error": "Bildfilen kunde inte sparas.",
            }

        shape = getattr(frame, "shape", ())
        height = int(shape[0]) if len(shape) >= 2 else None
        width = int(shape[1]) if len(shape) >= 2 else None

        return {
            "success": True,
            "camera_index": camera_index,
            "path": str(output),
            "width": width,
            "height": height,
            "error": None,
        }
    finally:
        camera.release()


def capture_from_settings(
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
            "error": (
                "Kameran är avstängd i konfigurationen."
            ),
        }

    index = configured_camera_index(settings)
    capture_dir = resolve_capture_dir(
        camera.get("capture_dir", "runtime/captures")
    )
    output = default_capture_path(capture_dir)

    return capture_frame(
        camera_index=index,
        output_path=output,
        cv2_module=cv2_module,
    )


def format_capture_result(result):
    if not result.get("success"):
        return (
            "Kamerabilden kunde inte tas: "
            + (result.get("error") or "okänt fel")
        )

    dimensions = ""

    if result.get("width") and result.get("height"):
        dimensions = (
            f" ({result['width']}x{result['height']} pixlar)"
        )

    return (
        f"Kamerabild sparad lokalt: {result['path']}"
        f"{dimensions}."
    )


def camera_capture():
    try:
        return format_capture_result(capture_from_settings())
    except Exception as error:
        return f"Kamerabilden kunde inte tas: {error}"


TOOLS = {
    "camera_capture": {
        "function": camera_capture,
        "description": (
            "Tar en enda stillbild från standardkameran, sparar den lokalt "
            "under runtime/captures och stänger kameran direkt."
        ),
    }
}
