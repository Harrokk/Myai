"""No physical calls in native distro metadata tests."""
from types import SimpleNamespace
from scripts import ventuno_voice_native_library_readonly as read


def test_all_libs_present_from_fully_mocked_lookups():
    found = []
    def finder(name):
        found.append(name)
        return "SYNTHETIC_LIB"
    output = read.inspect(
        finder=finder,
        command=lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout="install ok installed",
        ),
    )
    assert set(found) == {"portaudio", "espeak", "asound"}
    assert output["portaudio_library_found"]
    assert output["distro_portaudio_package_installed"]
    assert output["microphone_or_speaker_opened"] is False
    assert output["shared_library_loaded"] is False


def test_missing_portaudio_does_not_throw_or_allow_execution():
    result = read.inspect(
        finder=lambda name: None if name == "portaudio" else "FAKE",
        command=lambda *a, **kw: SimpleNamespace(
            returncode=1, stdout="PRIVATE_PKG_INFORMATION",
        ),
    )
    assert not result["portaudio_library_found"]
    assert not result["distro_portaudio_package_installed"]
    assert "PRIVATE" not in str(result)
    assert result["system_package_installed"] is False
