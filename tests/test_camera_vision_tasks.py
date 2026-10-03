from modules.camera import vision_tasks


def test_read_text_uses_conservative_prompt(monkeypatch):
    seen = {}

    def fake_analyze(prompt):
        seen["prompt"] = prompt
        return "ABC 123"

    monkeypatch.setattr(
        vision_tasks,
        "analyze_latest_capture",
        fake_analyze,
    )

    result = vision_tasks.vision_read_text()

    assert result == "ABC 123"
    assert "oläsligt" in seen["prompt"]
    assert "gissa" in seen["prompt"]


def test_detect_objects_uses_uncertainty_prompt(monkeypatch):
    seen = {}

    def fake_analyze(prompt):
        seen["prompt"] = prompt
        return "Stol, bord"

    monkeypatch.setattr(
        vision_tasks,
        "analyze_latest_capture",
        fake_analyze,
    )

    result = vision_tasks.vision_detect_objects()

    assert result == "Stol, bord"
    assert "osäkra observationer" in seen["prompt"]
    assert "Gissa inte" in seen["prompt"]


def test_read_text_reports_failure(monkeypatch):
    def fail(prompt):
        raise RuntimeError("testfel")

    monkeypatch.setattr(
        vision_tasks,
        "analyze_latest_capture",
        fail,
    )

    result = vision_tasks.vision_read_text()

    assert "testfel" in result


def test_detect_objects_reports_failure(monkeypatch):
    def fail(prompt):
        raise RuntimeError("testfel")

    monkeypatch.setattr(
        vision_tasks,
        "analyze_latest_capture",
        fail,
    )

    result = vision_tasks.vision_detect_objects()

    assert "testfel" in result
