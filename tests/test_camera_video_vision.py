from modules.camera import video_vision


class FakeVisionClient:
    def __init__(self, answer="Ett föremål tillkommer mellan samplingarna."):
        self.answer = answer
        self.calls = []

    def analyze_images(self, image_paths, prompt, timeout=120):
        self.calls.append(
            {
                "image_paths": list(image_paths),
                "prompt": prompt,
                "timeout": timeout,
            }
        )
        return self.answer


def enabled_settings(tmp_path):
    return {
        "ollama": {
            "url": "http://localhost:11434/api/chat",
        },
        "vision": {
            "enabled": True,
            "url": "http://localhost:11434/api/chat",
            "model": "vision-test",
            "timeout_seconds": 40,
        },
        "camera": {
            "video_dir": str(tmp_path / "video"),
            "video_frame_dir": str(tmp_path / "frames"),
        },
    }


def prepare_video_and_frames(tmp_path):
    video_dir = tmp_path / "video"
    frame_root = tmp_path / "frames"
    video_dir.mkdir()
    video = video_dir / "clip.mp4"
    video.write_bytes(b"video")

    frame_dir = frame_root / "clip"
    frame_dir.mkdir(parents=True)
    third = frame_dir / "clip_sample_03_frame_000009.jpg"
    first = frame_dir / "clip_sample_01_frame_000000.jpg"
    second = frame_dir / "clip_sample_02_frame_000004.jpg"
    third.write_bytes(b"3")
    first.write_bytes(b"1")
    second.write_bytes(b"2")

    return video, [first, second, third]


def test_latest_video_sample_set_orders_frames(tmp_path):
    video, expected = prepare_video_and_frames(tmp_path)

    result = video_vision.latest_video_sample_set(
        enabled_settings(tmp_path)
    )

    assert result["video_path"] == video
    assert result["frames"] == expected


def test_video_analysis_is_disabled_message(tmp_path):
    text = video_vision.analyze_latest_video_samples(
        settings={
            "vision": {
                "enabled": False,
                "model": "",
            },
            "camera": {
                "video_dir": str(tmp_path / "video"),
                "video_frame_dir": str(tmp_path / "frames"),
            },
        }
    )

    assert "avstängd" in text


def test_video_analysis_requires_model(tmp_path):
    text = video_vision.analyze_latest_video_samples(
        settings={
            "vision": {
                "enabled": True,
                "model": "",
            },
            "camera": {
                "video_dir": str(tmp_path / "video"),
                "video_frame_dir": str(tmp_path / "frames"),
            },
        }
    )

    assert "Ingen visionmodell" in text


def test_video_analysis_requires_video(tmp_path):
    text = video_vision.analyze_latest_video_samples(
        settings=enabled_settings(tmp_path)
    )

    assert "Ingen sparad video" in text


def test_video_analysis_requires_samples(tmp_path):
    settings = enabled_settings(tmp_path)
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    (video_dir / "clip.mp4").write_bytes(b"video")

    text = video_vision.analyze_latest_video_samples(
        settings=settings
    )

    assert "Inga representativa bildrutor" in text


def test_video_analysis_uses_frames_in_chronological_order(tmp_path):
    _, expected = prepare_video_and_frames(tmp_path)
    client = FakeVisionClient("Tydlig förändring.")

    text = video_vision.analyze_latest_video_samples(
        settings=enabled_settings(tmp_path),
        client=client,
    )

    assert "baserad på 3 representativa bildrutor" in text
    assert "Tydlig förändring." in text
    assert len(client.calls) == 1
    assert client.calls[0]["image_paths"] == expected
    assert client.calls[0]["timeout"] == 40
    assert "kronologisk ordning" in client.calls[0]["prompt"]
    assert "gissa inte vad som hände mellan dem" in client.calls[0]["prompt"]


def test_video_analysis_tool_reports_client_failure(monkeypatch):
    def fail():
        raise RuntimeError("testfel")

    monkeypatch.setattr(
        video_vision,
        "analyze_latest_video_samples",
        fail,
    )

    text = video_vision.vision_analyze_video()

    assert "misslyckades" in text
    assert "testfel" in text
