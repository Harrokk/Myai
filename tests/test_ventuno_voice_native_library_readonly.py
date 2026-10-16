"""No native library opened, privacy-safe static resolution only."""
from types import SimpleNamespace

from scripts import ventuno_voice_native_library_readonly as lib

def apt_result(version):
    return lambda *_a, **_k: SimpleNamespace(
        returncode=0, stdout=f"libportaudio2:\\n  Installed: (none)\\n  Candidate: {version}\\n"
    )


def test_ala_portaudio_missing_fails_closed():
    report = lib.inspect(finder=lambda name: "libasound.so.2" if name == "asound" else None,
                         apt_runner=apt_result("19.6.0-1"))
    assert report["status"] == "blocked-portaudio-library-name-unavailable"
    assert report["alsa_loader_name_available"] is True
    assert report["portaudio_loader_name_available"] is False
    assert report["native_abi_execution_verified"] is False
    assert report["microphone_opened"] is False


def test_portaudio_present_still_does_not_authorize_opening_device():
    report = lib.inspect(finder=lambda name: "lib" + name + ".so",
                         apt_runner=apt_result("(none)"))
    assert report["status"] == "portaudio-library-name-resolvable"
    assert report["shared_library_opened"] is False
    assert report["speaker_opened"] is False
    assert report["system_packages_modified"] is False


def test_apt_candidate_metadata_only_does_not_mean_package_installed():
    report = lib.inspect(finder=lambda _: None, apt_runner=apt_result("19.6.0-1"))
    assert report["portaudio_distro_candidate_available"] is True
    assert report["portaudio_loader_name_available"] is False
    assert report["system_packages_modified"] is False


def test_apt_none_candidate_fails_closed():
    report = lib.inspect(finder=lambda _: None, apt_runner=apt_result("(none)"))
    assert report["portaudio_distro_candidate_available"] is False
    assert report["native_abi_execution_verified"] is False
