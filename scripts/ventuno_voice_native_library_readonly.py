"""Passive native voice library provenance, without dlopen or audio capture."""
import ctypes.util
import json

LIBRARIES = ("portaudio", "asound", "espeak", "espeak-ng")


def inspect(finder=None):
    finder = finder or ctypes.util.find_library
    found = {}
    for name in LIBRARIES:
        try:
            library = finder(name)
        except (OSError, ValueError, TypeError):
            library = None
        found[name] = type(library) is str and len(library) > 0
    return {
        "status": (
            "portaudio-library-name-resolvable"
            if found["portaudio"]
            else "blocked-portaudio-library-name-unavailable"
        ),
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
