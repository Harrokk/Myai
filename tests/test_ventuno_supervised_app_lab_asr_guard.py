"""Static-only guard checks; never run the script or touch a service."""
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ventuno_supervised_app_lab_asr_guard.sh"


def text():
    return GUARD.read_text(encoding="utf-8")


def test_shell_parses_without_execution():
    proc = subprocess.run(
        ["bash", "-n", str(GUARD)], capture_output=True,
        timeout=5, check=False,
    )
    assert proc.returncode == 0


def test_explicit_armed_operator_control_and_timed_restoration():
    script = text()
    assert "IFS= read -r _" in script
    assert "IFS= read -r -t 600" in script
    assert "trap restore_geniex EXIT" in script
    assert "trap 'exit 130' INT" in script
    assert "trap 'exit 143' TERM" in script
    assert "trap 'exit 129' HUP" in script
    assert script.index("sudo -v") < script.index(
        'sudo systemctl stop "$MODEL_UNIT"'
    )


def test_restrict_service_mutation_to_one_expected_geniex_unit():
    script = text()
    assert "MODEL_UNIT=myai-geniex.service" in script
    assert "MYAI_UNIT=myai-ventuno.service" in script
    assert 'sudo systemctl stop "$MODEL_UNIT"' in script
    assert 'sudo systemctl start "$MODEL_UNIT"' in script
    for forbidden in (
        "systemctl restart", "systemctl daemon-reload",
        "systemctl disable", "systemctl mask", "systemctl enable",
        "myai-ventuno.service stop", "actions.runner.",
    ):
        assert forbidden not in script


def test_no_script_inference_or_audio_capture():
    script = text()
    assert "/dev/snd/pcmC1D0c" in script
    assert "capture-begins" in script
    for forbidden in (
        "arecord ", "aplay ", "ffmpeg ", "pactl ",
        "asr.transcribe(", "App.run(", "geniex serve",
        "arduino-app-cli app start", "docker run",
    ):
        assert forbidden not in script


def test_fail_closed_without_correct_user_device_or_service_health():
    script = text()
    assert '$(uname -m)' in script
    assert '$(id -un)' in script
    assert "! -t 0" in script
    assert "systemctl is-active --quiet" in script
    assert "! -c /dev/snd/pcmC1D0c" in script
    assert "restoration_required=1" in script
    assert "restoration_required=0" in script
