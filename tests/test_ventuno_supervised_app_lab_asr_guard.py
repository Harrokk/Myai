"""The physical guard is NEVER run here: simulations replace hardware/systemd.

The test executes a temporary copy, with shell functions that fully intercept
sudo/systemctl and with no real USB, model, Docker or service access.
"""
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ventuno_supervised_app_lab_asr_guard.sh"


def source():
    return GUARD.read_text(encoding="utf-8")


def test_syntax_only_never_runs_live_guard():
    result = subprocess.run(["bash", "-n", str(GUARD)], capture_output=True,
                            timeout=5, check=False)
    assert result.returncode == 0


def test_known_required_dependency_and_safe_stop_start_order():
    s = source()
    assert "MODEL_UNIT=myai-geniex.service" in s
    assert "MYAI_UNIT=myai-ventuno.service" in s
    assert s.index('sudo systemctl stop "$MYAI_UNIT"') < s.index(
        'sudo systemctl stop "$MODEL_UNIT"'
    )
    assert s.index('sudo -n systemctl start "$MODEL_UNIT"') < s.index(
        'sudo -n systemctl start "$MYAI_UNIT"'
    )
    assert "trap restore_services EXIT" in s
    assert s.index("restoration_required=1") < s.index(
        'sudo systemctl stop "$MYAI_UNIT"'
    )


def test_explicit_fresh_both_service_consent_before_sudo_and_stop():
    s = source()
    assert "JA STOPPA BADDA" in s
    assert s.index("if [[ \"$consent\" != 'JA STOPPA BADDA' ]]") < s.index("sudo -v")
    assert s.index("sudo -v") < s.index('sudo systemctl stop "$MYAI_UNIT"')
    assert "IFS= read -r -t 180" in s
    assert "trap 'exit 130' INT" in s
    assert "trap 'exit 143' TERM" in s
    assert "trap 'exit 129' HUP" in s


def test_guard_never_executes_audio_or_ai_or_mutates_other_services():
    s = source()
    for forbidden in (
        "arecord ", "aplay ", "ffmpeg ", "pactl ", "App.run(",
        "asr.transcribe(", "arduino-app-cli app start", "docker run",
        "systemctl restart", "systemctl daemon-reload",
        "systemctl disable", "systemctl mask", "systemctl enable",
    ):
        assert forbidden not in s
    assert "GitHub-runnern lämnas orörd" in s
    assert "MYAI_ASR: pcm-first-chunk-speak-now" in s
    assert "MYAI_ASR: capture-begins" not in s
    assert "! -c /dev/snd/pcmC1D0c" in s
    assert "! -t 0" in s


def _mock_script(tmp_path, *, genie_stop_fails=False, myai_active=True):
    """A safe, temporary, explicitly modified COPY, not the live guard."""
    s = source()
    tmp_path.joinpath("pcm.txt").write_text("01-00: USB : capture 1\n")
    tmp_path.joinpath("myai-ventuno.service").write_text("active") if myai_active else None
    tmp_path.joinpath("myai-geniex.service").write_text("active")
    tmp_path.joinpath("calls.log").write_text("")
    s = s.replace(
        'if [[ "$(uname -m)" != aarch64 || "$(id -un)" != arduino || ! -t 0 ]]; then',
        "if false; then",
    )
    s = s.replace(
        'if ! command -v sudo >/dev/null 2>&1 || ! command -v systemctl >/dev/null 2>&1; then',
        "if false; then",
    )
    s = s.replace("/dev/snd/pcmC1D0c", "/dev/null")
    s = s.replace("/proc/asound/pcm", str(tmp_path / "pcm.txt"))
    assertions = (
        'if false; then',
        "! -c /dev/null",
        str(tmp_path / "pcm.txt"),
    )
    assert all(x in s for x in assertions)
    failure_clause = (
        'if [[ "$name" == "myai-geniex.service" ]]; then return 1; fi'
        if genie_stop_fails else ":"
    )
    fake = f"""
FAKE_DIR={shlex.quote(str(tmp_path))}
systemctl() {{
    local command="$1"
    shift
    case "$command" in
      is-active)
        [[ "$1" == --quiet ]] || return 19
        [[ -f "$FAKE_DIR/$2" ]]
        ;;
      stop)
        local name="$1"
        printf 'stop %s\\n' "$name" >> "$FAKE_DIR/calls.log"
        rm -f "$FAKE_DIR/$name"
        {failure_clause}
        ;;
      start)
        local name="$1"
        printf 'start %s\\n' "$name" >> "$FAKE_DIR/calls.log"
        : > "$FAKE_DIR/$name"
        ;;
      *) return 19 ;;
    esac
}}
sudo() {{
    if [[ "$1" == -v ]]; then return 0; fi
    if [[ "$1" == -n ]]; then shift; fi
    "$@"
}}
"""
    s = s.replace("set -Eeuo pipefail\n", "set -Eeuo pipefail\n" + fake, 1)
    path = tmp_path / "guard-mock.sh"
    path.write_text(s)
    return path


def test_simulated_supervised_one_turn_stops_and_restores_both(tmp_path):
    path = _mock_script(tmp_path)
    result = subprocess.run(
        ["bash", str(path)],
        input="\nJA STOPPA BADDA\n\n",
        text=True, capture_output=True, timeout=8, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "myai-ventuno.service").exists()
    assert (tmp_path / "myai-geniex.service").exists()
    assert (tmp_path / "calls.log").read_text().splitlines() == [
        "stop myai-ventuno.service", "stop myai-geniex.service",
        "start myai-geniex.service", "start myai-ventuno.service",
    ]
    assert "GenieX och MyAI är åter aktiva." in result.stdout


def test_simulated_failed_genie_stop_still_restores_both(tmp_path):
    path = _mock_script(tmp_path, genie_stop_fails=True)
    result = subprocess.run(
        ["bash", str(path)], input="\nJA STOPPA BADDA\n",
        text=True, capture_output=True, timeout=8,
    )
    assert result.returncode != 0
    assert (tmp_path / "myai-ventuno.service").exists()
    assert (tmp_path / "myai-geniex.service").exists()
    assert (tmp_path / "calls.log").read_text().splitlines() == [
        "stop myai-ventuno.service", "stop myai-geniex.service",
        "start myai-geniex.service", "start myai-ventuno.service",
    ]


def test_simulated_refused_consent_never_stops_any_service(tmp_path):
    path = _mock_script(tmp_path)
    result = subprocess.run(
        ["bash", str(path)], input="\nNEJ\n",
        text=True, capture_output=True, timeout=8,
    )
    assert result.returncode != 0
    assert (tmp_path / "myai-ventuno.service").exists()
    assert (tmp_path / "myai-geniex.service").exists()
    assert (tmp_path / "calls.log").read_text() == ""


def test_simulated_inactive_initial_service_never_calls_sudo(tmp_path):
    path = _mock_script(tmp_path, myai_active=False)
    result = subprocess.run(
        ["bash", str(path)], input="", text=True,
        capture_output=True, timeout=8,
    )
    assert result.returncode != 0
    assert (tmp_path / "calls.log").read_text() == ""


def test_mock_script_keeps_source_github_commands_out_of_runtime():
    s = source()
    assert "restoration_required=0" in s
    assert "restoration_required=1" in s
    assert "sudo -n systemctl start" in s
    assert 'if ! sudo systemctl start "$MODEL_UNIT"' in s
    assert 'if ! sudo systemctl start "$MYAI_UNIT"' in s
