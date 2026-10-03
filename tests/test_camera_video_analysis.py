from modules.camera import video_analysis


class FakeVisionClient:
    def __init__(self, answer="Ett rum syns under klippet."):
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


def enabled_settings():
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
            "video_sample_count": 5,
        },
    }


def fake_sample(frame_count=5):
    return {
        "success": True,
        "video_path": "runtime/video/test.mp4",
        "frames": [
            {
                "order": index + 1,
                "frame_index": index * 10,
                "path": f"/tmp/frame_{index}.jpg",
            }
            for index in range(frame_count)
        ],
        "error": None,
    }


def test_video_analysis_disabled_does_not_sample():
    called = {"value": False}

    def sampler(settings):
        called["value"] = True
        return fake_sample()

    text = video_analysis.analyze_latest_video(
        settings={
            "vision": {
                "enabled": False,
                "model": "",
            }
        },
        sampler=sampler,
    )

    assert "avstängd" in text
    assert called["value"] is False


def test_video_analysis_requires_model():
    text = video_analysis.analyze_latest_video(
        settings={
            "vision": {
                "enabled": True,
                "model": "",
            }
        },
        sampler=lambda settings: fake_sample(),
    )

    assert "Ingen visionmodell" in text


def test_video_analysis_reports_sampling_failure():
    text = video_analysis.analyze_latest_video(
        settings=enabled_settings(),
        sampler=lambda settings: {
            "success": False,
            "frames": [],
            "error": "Ingen sparad video hittades.",
        },
    )

    assert "Ingen sparad video" in text


def test_video_analysis_uses_sampled_frames_in_order():
    client = FakeVisionClient("Sammanfattning")

    text = video_analysis.analyze_latest_video(
        settings=enabled_settings(),
        client=client,
        sampler=lambda settings: fake_sample(5),
    )

    assert "test.mp4" in text
    assert "5 representativa bildrutor" in text
    assert "Sammanfattning" in text
    assert len(client.calls) == 1
    assert len(client.calls[0]["image_paths"]) == 5
    assert client.calls[0]["image_paths"][0].name == "frame_0.jpg"
    assert client.calls[0]["image_paths"][-1].name == "frame_4.jpg"
    assert client.calls[0]["timeout"] == 40
    assert "inte att du har sett varje bildruta" in client.calls[0]["prompt"]


def test_video_analysis_caps_large_sample_sets_evenly():
    frames = video_analysis._select_analysis_frames(
        fake_sample(20)["frames"],
        max_frames=4,
    )

    assert len(frames) == 4
    assert frames[0]["order"] == 1
    assert frames[-1]["order"] == 20


def test_video_analysis_requires_sampled_frames():
    text = video_analysis.analyze_latest_video(
        settings=enabled_settings(),
        sampler=lambda settings: {
            "success": True,
            "video_path": "runtime/video/test.mp4",
            "frames": [],
            "error": None,
        },
    )

    assert "inga bildrutor" in text


def test_video_analysis_tool_reports_client_failure(monkeypatch):
    def fail():
        raise RuntimeError("testfel")

    monkeypatch.setattr(
        video_analysis,
        "analyze_latest_video",
        fail,
    )

    text = video_analysis.vision_analyze_video()

    assert "misslyckades" in text
    assert "testfel" in text
