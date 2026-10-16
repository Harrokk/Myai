"""Passive native voice library provenance, without dlopen or audio capture."""
import ctypes.util
import json
import re
import subprocess

LIBRARIES = ("portaudio", "asound", "espeak", "espeak-ng")


def inspect(finder=None, apt_runner=None):
    finder = finder or ctypes.util.find_library
    apt_runner = apt_runner or subprocess.run
    found = {}
    for name in LIBRARIES:
        try:
            library = finder(name)
        except (OSError, ValueError, TypeError):
            library = None
        found[name] = type(library) is str and len(library) > 0
    available = False
    queried = False
    try:
        output = apt_runner(
            ["apt-cache", "policy", "libportaudio2"],
            capture_output=True, text=True, check=False, timeout=4,
        )
        queried = output.returncode == 0
        match = re.search(
            r"(?m)^\s*Candidate:\s*([^\s]+)\s*$",
            output.stdout if queried else "",
        )
        available = bool(match and match.group(1) != "(none)")
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        pass
    return {
        "status": (
            "portaudio-library-name-resolvable"
            if found["portaudio"]
            else "blocked-portaudio-library-name-unavailable"
        ),
        "portaudio_distro_candidate_available": available,
        "portaudio_apt_metadata_readonly_checked": queried,
        "portaudio_loader_name_available": found["portaudio"],
        "alsa_loader_name_available": found["asound"],
        "espeak_loader_name_available": found["espeak"],
        "espeakng_loader_name_available": found["espeak-ng"],
        "shared_library_opened": False,
        "device_enumerated": False,
        "microphone_opened": False,
        "speaker_opened": False,
        "system_packages_modified": False,
        "native_abi_execution_verified": False,
    }


if __name__ == "__main__":
    print("MYAI_PORTAUDIO_LIBRARY_READONLY_JSON=" +
          json.dumps(inspect(), sort_keys=True))
