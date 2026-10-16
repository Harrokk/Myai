"""Safe categorical diagnosis of isolated native Python imports."""
import json
import subprocess

from scripts import ventuno_native_voice_import_report as probe


def done(status=0, out=None, err=""):
    if out is None:
        out = '{"ok":true,"rss_kib":10240}'
    return subprocess.CompletedProcess([], status, stdout=out, stderr=err)


def test_six_clean_native_imports_never_claim_audio_ready():
    result = probe.probe(
        executable="/isolated/python",
        runner=lambda *_a, **_kw: done(),
    )
    assert result["status"] == "six-native-package-imports-verified"
    assert result["native_imports_all_succeeded"] is True
    assert result["microphone_or_speaker_opened"] is False
    assert result["stt_model_instantiated"] is False
    assert result["physical_test_authorized"] is False


def test_known_system_portaudio_missing_is_explicit_blocker():
    seen = []
    def runner(args, **kwargs):
        seen.append(args[-1])
        if args[-1] == "sounddevice":
            return done(1, "", "OSError: PortAudio library not found")
        return done()
    result = probe.probe(executable="/isolated/python", runner=runner)
    assert seen == list(probe.MODULES)
    assert result["status"] == "blocked-system-portaudio"
    assert result["five_non_audio_imports_succeeded"] is True
    assert result["native_imports_all_succeeded"] is False


def test_unexpected_exception_is_not_downgraded_to_portaudio():
    def runner(args, **kwargs):
        return done(1, "", "PRIVATE_PATH /home/secret/invalid-so")
    result = probe.probe(executable="/isolated/python", runner=runner)
    assert result["status"] == "blocked-other-native-imports"
    assert "PRIVATE_PATH" not in json.dumps(result)


def test_timeout_never_claims_success():
    timeout = subprocess.TimeoutExpired(cmd=["python"], timeout=1)
    result = probe.classify("av", timeout)
    assert result["status"] == "timeout"


def test_invalid_native_success_report_is_denied():
    assert probe.classify("av", done(0, "not-json"))["status"] == "bad-import-report"
    assert probe.classify("non-allowlisted", done())["status"] == "blocked-unknown-module"
