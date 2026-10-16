"""Read-only distro shared library metadata for the disposable voice stage.

Never loads a library, opens an ALSA device, downloads a package, runs dpkg
installation or changes the device; all output is sanitized booleans.
"""
from __future__ import annotations
import ctypes.util
import json
import subprocess


LIBRARIES = {"portaudio": "portaudio", "espeak": "espeak", "alsa": "asound"}


def inspect(finder=None, command=None):
    finder = finder or ctypes.util.find_library
    command = command or subprocess.run
    libraries = {}
    for label, lib in LIBRARIES.items():
        try:
            libraries[label] = finder(lib) is not None
        except (OSError, ValueError, TypeError):
            libraries[label] = False
    try:
        proc = command(
            ["dpkg-query", "-W", "-f=${Status}", "libportaudio2"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            timeout=4, check=False,
        )
        distro_portaudio_installed = (
            proc.returncode == 0 and
            proc.stdout.strip() == "install ok installed"
        )
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        distro_portaudio_installed = False
    return {
        "status": "read-only-native-library-metadata",
        "portaudio_library_found": libraries["portaudio"],
        "espeak_library_found": libraries["espeak"],
        "alsa_library_found": libraries["alsa"],
        "distro_portaudio_package_installed": distro_portaudio_installed,
        "shared_library_loaded": False,
        "system_package_downloaded": False,
        "system_package_installed": False,
        "microphone_or_speaker_opened": False,
        "npu_started": False,
    }


if __name__ == "__main__":
    print("MYAI_VOICE_NATIVE_LIBRARIES_JSON=" + json.dumps(inspect(), sort_keys=True))
