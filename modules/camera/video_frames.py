from pathlib import Path

from core.config import PROJECT_ROOT, load_settings
from modules.camera.capture import _load_cv2, resolve_capture_dir


DEFAULT_VIDEO_DIR = PROJECT_ROOT / "runtime" / "video"
DEFAULT_FRAME_DIR = PROJECT_ROOT / "runtime" / "video_frames"
MAX_VIDEO_SAMPLE_COUNT = 12


def latest_video(video_dir=None):
    directory = (
        Path(video_dir)
        if video_dir is not None
        else DEFAULT_VIDEO_DIR
    )

    if not directory.exists():
        return None

    candidates = []

    for pattern in ("*.mp4", "*.avi", "*.mov", "*.mkv"):
        candidates.extend(directory.glob(pattern))

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )


def sample_frame_indices(total_frames, count):
    try:
        total = int(total_frames)
        requested = int(count)
    except (TypeError, ValueError) as error:
        raise ValueError("Antal videobildrutor måste vara heltal.") from error

    if total <= 0:
        raise ValueError("Videon rapporterar inga användbara bildrutor.")

    if requested <= 0:
        raise ValueError("Antal samplingsbilder måste vara större än 0.")

    if requested > MAX_VIDEO_SAMPLE_COUNT:
        raise ValueError(
            "Antal samplingsbilder får vara högst "
            f"{MAX_VIDEO_SAMPLE_COUNT}."
        )

    actual = min(total, requested)

    if actual == 1:
        return [total // 2]

    last = total - 1
    return [
        round(index * last / (actual - 1))
        for index in range(actual)
    ]


def extract_video_frames(
    video_path,
    output_dir,
    sample_count=5,
    cv2_module=None,
):
    cv2 = cv2_module or _load_cv2()
    path = Path(video_path)

    if not path.exists() or not path.is_file():
        return {
            "success": False,
            "video_path": str(path),
            "output_dir": None,
            "total_frames": 0,
            "frames": [],
            "error": f"Videofilen finns inte: {path}",
        }

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(path))

    try:
        if not capture.isOpened():
            return {
                "success": False,
                "video_path": str(path),
                "output_dir": str(output),
                "total_frames": 0,
                "frames": [],
                "error": "Videofilen kunde inte öppnas.",
            }

        total_frames = int(
            round(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        )

        try:
            indices = sample_frame_indices(
                total_frames,
                sample_count,
            )
        except ValueError as error:
            return {
                "success": False,
                "video_path": str(path),
                "output_dir": str(output),
                "total_frames": total_frames,
                "frames": [],
                "error": str(error),
            }

        saved = []

        for order, frame_index in enumerate(indices, start=1):
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()

            if not ok or frame is None:
                return {
                    "success": False,
                    "video_path": str(path),
                    "output_dir": str(output),
                    "total_frames": total_frames,
                    "frames": saved,
                    "error": (
                        f"Bildruta {frame_index} kunde inte läsas "
                        "från videon."
                    ),
                }

            frame_path = (
                output
                / f"{path.stem}_sample_{order:02d}_frame_{frame_index:06d}.jpg"
            )

            if not cv2.imwrite(str(frame_path), frame):
                return {
                    "success": False,
                    "video_path": str(path),
                    "output_dir": str(output),
                    "total_frames": total_frames,
                    "frames": saved,
                    "error": (
                        f"Bildruta {frame_index} kunde inte sparas."
                    ),
                }

            saved.append(
                {
                    "order": order,
                    "frame_index": frame_index,
                    "path": str(frame_path),
                }
            )

        return {
            "success": True,
            "video_path": str(path),
            "output_dir": str(output),
            "total_frames": total_frames,
            "frames": saved,
            "error": None,
        }
    finally:
        capture.release()


def sample_latest_video_from_settings(
    settings=None,
    cv2_module=None,
):
    settings = settings or load_settings()
    camera = settings.get("camera", {})

    video_dir = resolve_capture_dir(
        camera.get("video_dir", "runtime/video")
    )
    frame_root = resolve_capture_dir(
        camera.get("video_frame_dir", "runtime/video_frames")
    )
    sample_count = camera.get("video_sample_count", 5)

    video_path = latest_video(video_dir)

    if video_path is None:
        return {
            "success": False,
            "video_path": None,
            "output_dir": None,
            "total_frames": 0,
            "frames": [],
            "error": "Ingen sparad video hittades.",
        }

    output_dir = frame_root / video_path.stem

    return extract_video_frames(
        video_path=video_path,
        output_dir=output_dir,
        sample_count=sample_count,
        cv2_module=cv2_module,
    )


def format_video_frame_result(result):
    if not result.get("success"):
        return (
            "Bildrutor kunde inte plockas ut ur videon: "
            + (result.get("error") or "okänt fel")
        )

    frames = result.get("frames", [])

    lines = [
        (
            f"{len(frames)} representativa bildrutor sparades från "
            f"{Path(result['video_path']).name}."
        ),
        f"Videons rapporterade bildrutor: {result['total_frames']}.",
    ]

    for item in frames:
        lines.append(
            f"- frame {item['frame_index']}: {item['path']}"
        )

    return "\n".join(lines)


def camera_sample_video_frames():
    try:
        return format_video_frame_result(
            sample_latest_video_from_settings()
        )
    except Exception as error:
        return (
            "Bildrutor kunde inte plockas ut ur videon: "
            f"{error}"
        )


TOOLS = {
    "camera_sample_video_frames": {
        "function": camera_sample_video_frames,
        "description": (
            "Plockar ut ett konfigurerat antal jämnt fördelade "
            "representativa bildrutor från den senast sparade videon."
        ),
    }
}
