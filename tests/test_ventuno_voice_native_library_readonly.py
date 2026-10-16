"""No native library opened, privacy-safe static resolution only."""
from scripts import ventuno_voice_native_library_readonly as lib


def test_ala_portaudio_missing_fails_closed():
    report = lib.inspect(finder=lambda name: "libasound.so.2" if name == "asound" else None)
    assert report["status"] == "blocked-portaudio-library-name-unavailable"
    assert report["alsa_loader_name_available"] is True
    assert report["portaudio_loader_name_available"] is False
    assert report["native_abi_execution_verified"] is False
    assert report["microphone_opened"] is False


def test_portaudio_present_still_does_not_authorize_opening_device():
    report = lib.inspect(finder=lambda name: "lib" + name + ".so")
    assert report["status"] == "portaudio-library-name-resolvable"
    assert report["shared_library_opened"] is False
    assert report["speaker_opened"] is False
    assert report["system_packages_modified"] is False
