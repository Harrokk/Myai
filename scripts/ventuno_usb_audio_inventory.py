"""Inventory USB ALSA sound cards on VENTUNO Q without opening audio devices.

Reads bounded /proc/asound/{cards,pcm,cardN/usbid} metadata and checks
/dev/snd device-node type/access via stat and os.access only. No
recording, playback, mixer writes, hardware resets, package installs,
service changes, model loads, raw labels, USB serials or audio data.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

MAX_PROC_BYTES = 16 * 1024
MAX_CARDS = 32
MAX_PAIRS = 48


def _read_metadata(path: Path, limit: int = MAX_PROC_BYTES) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
        if len(data) > limit:
            return None
        return data.decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def _usb_cards(cards_data: str, proc_root: Path) -> list[int]:
    hints = set()
    for line in cards_data.splitlines():
        match = re.match(r"^\s*(\d{1,2})\s+\[[^\]]{1,64}\]\s*:\s*(.*)$", line)
        if match and "usb-audio" in match.group(2).lower():
            hints.add(int(match.group(1)))
    result = []
    for index in range(MAX_CARDS):
        usb_id = _read_metadata(proc_root / f"card{index}" / "usbid", 64)
        has_usb_id = bool(usb_id and re.fullmatch(
            r"[0-9a-fA-F]{4}:[0-9a-fA-F]{4}\s*", usb_id
        ))
        if has_usb_id or index in hints:
            result.append(index)
    return result


def _pcm_pairs(pcm_data: str, category: str) -> list[list[int]]:
    pairs = []
    for line in pcm_data.splitlines():
        match = re.match(r"^\s*(\d{2,3})-(\d{2,3}):", line)
        if match and re.search(r"\b" + category + r"\s+[1-9]\d*\b", line):
            card, device = int(match.group(1)), int(match.group(2))
            if card < MAX_CARDS and device < 100 and [card, device] not in pairs:
                pairs.append([card, device])
                if len(pairs) >= MAX_PAIRS:
                    break
    return pairs


def _node_info(root: Path, pair: list[int], direction: str) -> dict[str, object]:
    card, device = pair
    node = root / f"pcmC{card}D{device}{direction}"
    result: dict[str, object] = {"pair": pair, "character_device": False, "accessible": False}
    try:
        if node.is_symlink():
            return result
        if stat.S_ISCHR(node.stat().st_mode):
            result["character_device"] = True
            result["accessible"] = bool(
                os.access(node, os.R_OK) and os.access(node, os.W_OK)
            )
    except OSError:
        pass
    return result


def inventory_usb_audio(
    proc_root: Path = Path("/proc/asound"),
    snd_root: Path = Path("/dev/snd"),
) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "inconclusive-alsa-metadata",
        "usb_audio_cards": [],
        "usb_capture_pairs": [],
        "usb_playback_pairs": [],
        "usb_duplex_cards": [],
        "capture_device_nodes": [],
        "playback_device_nodes": [],
        "microphone_recorded": False,
        "speaker_playback_started": False,
        "alsa_mixer_modified": False,
        "services_modified": False,
        "voice_production_enabled": False,
        "usable_audio_signal_verified": False,
    }
    cards_data = _read_metadata(proc_root / "cards")
    pcm_data = _read_metadata(proc_root / "pcm")
    if cards_data is None or pcm_data is None:
        return report
    usb_cards = _usb_cards(cards_data, proc_root)
    report["usb_audio_cards"] = usb_cards
    if not usb_cards:
        report["status"] = "no-usb-audio-card-detected"
        return report
    capture = [p for p in _pcm_pairs(pcm_data, "capture") if p[0] in usb_cards]
    playback = [p for p in _pcm_pairs(pcm_data, "playback") if p[0] in usb_cards]
    report["usb_capture_pairs"] = capture
    report["usb_playback_pairs"] = playback
    report["usb_duplex_cards"] = sorted({p[0] for p in capture} & {p[0] for p in playback})
    report["capture_device_nodes"] = [_node_info(snd_root, p, "c") for p in capture]
    report["playback_device_nodes"] = [_node_info(snd_root, p, "p") for p in playback]
    if capture and playback:
        report["status"] = "usb-capture-and-playback-pcm-detected"
    elif capture:
        report["status"] = "usb-capture-only-pcm-detected"
    elif playback:
        report["status"] = "usb-playback-only-pcm-detected"
    else:
        report["status"] = "usb-card-without-pcm-routes"
    return report


def main() -> int:
    report = inventory_usb_audio()
    print("VENTUNO read-only USB ALSA inventory:", json.dumps(report, sort_keys=True))
    print("No microphone opened, sound played, controls changed, or services restarted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
