from types import SimpleNamespace

from modules.camera import camera


def test_windows_json_single_camera_is_normalized():
    result = camera._normalize_windows_json(
        '{"Class":"Camera","FriendlyName":"USB Camera",'
        '"InstanceId":"USB\\\\VID_1234","Status":"OK"}'
    )

    assert len(result) == 1
    assert result[0]["name"] == "USB Camera"
    assert result[0]["status"] == "OK"
    assert result[0]["source"] == "windows-pnp"


def test_windows_json_multiple_cameras_are_normalized():
    result = camera._normalize_windows_json(
        '['
        '{"Class":"Camera","FriendlyName":"Front","InstanceId":"A","Status":"OK"},'
        '{"Class":"Image","FriendlyName":"Capture","InstanceId":"B","Status":"OK"}'
        ']'
    )

    assert [item["name"] for item in result] == ["Front", "Capture"]


def test_windows_inventory_uses_pnp(monkeypatch):
    monkeypatch.setattr(camera.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        camera,
        "_run",
        lambda command: SimpleNamespace(
            returncode=0,
            stdout=(
                '{"Class":"Camera","FriendlyName":"Webcam",'
                '"InstanceId":"CAM1","Status":"OK"}'
            ),
            stderr="",
        ),
    )

    result = camera.get_camera_inventory()

    assert result[0]["id"] == "CAM1"


def test_linux_inventory_reads_video4linux_names(tmp_path, monkeypatch):
    root = tmp_path / "video4linux"
    video0 = root / "video0"
    video1 = root / "video1"
    video0.mkdir(parents=True)
    video1.mkdir()
    (video0 / "name").write_text("Pi Camera", encoding="utf-8")
    (video1 / "name").write_text("USB Webcam", encoding="utf-8")

    monkeypatch.setattr(camera.platform, "system", lambda: "Linux")
    monkeypatch.setattr(camera, "LINUX_VIDEO_ROOT", root)

    result = camera.get_camera_inventory()

    assert [item["name"] for item in result] == [
        "Pi Camera",
        "USB Webcam",
    ]
    assert result[0]["id"] == "/dev/video0"


def test_empty_camera_inventory_is_explicit():
    text = camera.format_camera_inventory([])

    assert "Inga kameror" in text


def test_camera_formatter_lists_identifiers():
    text = camera.format_camera_inventory(
        [
            {
                "category": "Camera",
                "name": "Webcam",
                "id": "CAM1",
                "status": "OK",
                "source": "test",
            }
        ]
    )

    assert "Webcam" in text
    assert "CAM1" in text
