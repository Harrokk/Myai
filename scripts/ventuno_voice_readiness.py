"""Read-only VENTUNO voice hardware/dependency preflight.

No microphone stream, playback, model download, STT/TTS provider import,
PipeWire/Pulse client connection, service change or hardware access.
Only inspect optional Python package specs and /proc + /dev metadata.
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import stat
from pathlib import Path

VOICE_MODULES = ("sounddevice", "webrtcvad", "faster_whisper", "pyttsx3")
MAX_CARD_TEXT = 16 * 1024
MAX_SND_ENTRIES = 64


def alsa_card_count(path: Path) -> int | None:
    """ALSA-provided card header enumeration, not a capture-device test."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        with path.open("rb") as stream:
            data = stream.read(MAX_CARD_TEXT + 1)
        if len(data) > MAX_CARD_TEXT:
            return None
        lines = data.decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return sum(bool(re.match(r"^\s*[0-9]{1,2}\s+\[", l)) for l in lines)


def snd_device_counts(root: Path) -> dict[str, object]:
    counts: dict[str, object] = {
        "snd_directory_present": False,
        "capture_device_nodes": 0,
        "playback_device_nodes": 0,
        "pcm_control_nodes": 0,
        "scan_complete": False,
    }
    if root.is_symlink() or not root.is_dir():
        return counts
    counts["snd_directory_present"] = True
    try:
        with os.scandir(root) as scan:
            entries = []
            for index, entry in enumerate(scan):
                if index >= MAX_SND_ENTRIES:
                    return counts
                entries.append(entry)
        for entry in entries:
            if entry.is_symlink():
                continue
            try:
                if not stat.S_ISCHR(entry.stat(follow_symlinks=False).st_mode):
                    continue
            except OSError:
                continue
            if re.fullmatch(r"pcmC\d{1,3}D\d{1,3}c", entry.name):
                counts["capture_device_nodes"] += 1
            elif re.fullmatch(r"pcmC\d{1,3}D\d{1,3}p", entry.name):
                counts["playback_device_nodes"] += 1
            elif re.fullmatch(r"controlC\d{1,3}", entry.name):
                counts["pcm_control_nodes"] += 1
        counts["scan_complete"] = True
    except OSError:
        pass
    return counts


def package_spec_presence() -> dict[str, bool]:
    """find_spec top-level names only, without loading audio/model engines."""
    out = {}
    for name in VOICE_MODULES:
        try:
            out[name] = importlib.util.find_spec(name) is not None
        except (ImportError, AttributeError, ValueError):
            out[name] = False
    return out


def readiness(
    packages: dict[str, bool],
    devices: dict[str, object],
    cards: int | None,
    *,
    voice_enabled: bool = False,
    tts_enabled: bool = False,
) -> dict[str, object]:
    capture_nodes = devices.get("capture_device_nodes", 0)
    sound_device_api = bool(packages.get("sounddevice"))
    stt = bool(packages.get("faster_whisper"))
    vad = bool(packages.get("webrtcvad"))
    tts = bool(packages.get("pyttsx3"))
    if voice_enabled or tts_enabled:
        status = "configuration-review-required-voice-requested"
    elif not devices.get("scan_complete"):
        status = "inconclusive-audio-device-metadata"
    elif not capture_nodes:
        status = "no-capture-device-node-seen"
    elif not (sound_device_api and stt and vad and tts):
        status = "audio-node-present-optional-voice-dependencies-missing"
    else:
        status = "candidate-for-authorized-physical-audio-smoke-test"
    return {
        "status": status,
        "alsa_cards_reported": cards,
        "voice_dependencies_present": packages,
        "device_nodes": devices,
        "voice_enabled_in_profile": voice_enabled,
        "tts_enabled_in_profile": tts_enabled,
        "physical_microphone_capture_verified": False,
        "speaker_playback_verified": False,
        "local_stt_model_loaded": False,
        "full_duplex_or_barge_in_verified": False,
        "safe_to_enable_voice_automatically": False,
        "geniex_or_myai_services_changed": False,
    }


def inspect_voice(profile_path: Path,
                  sound_root: Path = Path("/dev/snd"),
                  cards_path: Path = Path("/proc/asound/cards")) -> dict[str, object]:
    # Profile inspection is bounded to a known project file; no live writes.
    try:
        if profile_path.is_symlink() or profile_path.stat().st_size > 64 * 1024:
            raise ValueError("invalid-profile-size")
        cfg = json.loads(profile_path.read_text(encoding="utf-8"))
        voice = cfg.get("voice", {}) if isinstance(cfg, dict) else {}
        if not isinstance(voice, dict):
            voice = {}
        enabled = voice.get("enabled") is True
        tts_enabled = voice.get("tts_enabled") is True
    except (OSError, ValueError, TypeError):
        enabled = tts_enabled = False
    return readiness(
        package_spec_presence(),
        snd_device_counts(sound_root),
        alsa_card_count(cards_path),
        voice_enabled=enabled,
        tts_enabled=tts_enabled,
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "config" / "profiles" / "ventuno_q.json"
    result = inspect_voice(path)
    print("VENTUNO voice readiness inventory (metadata only):",
          json.dumps(result, sort_keys=True))
    print("No microphone, speaker, STT model, TTS engine or GenieX change attempted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
