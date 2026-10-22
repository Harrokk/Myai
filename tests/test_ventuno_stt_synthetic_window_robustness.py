"""Synthetic 16kHz frame and authorization regressions: NO microphone or model."""
import array
import math
import sys
from pathlib import Path

import pytest

from scripts.ventuno_stt_synthetic_window_robustness import (
    CAPTURE_BYTES, FIXTURE_VARIANTS, build_variants,
    apply_fixed_acoustic_fault,
    inspect_synthetic_window_robustness, perturb_three_second_pcm,
)
from scripts.ventuno_usb_dialogue_once import classify_pcm_activity_layout


def signal():
    samples = array.array("h", [0] * 48000)
    for i in range(6000, 24000):
        samples[i] = 3000
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def active_indices(raw):
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return [i for i, val in enumerate(samples) if val]


def test_empty_or_unapproved_does_no_cpu_or_network_work(tmp_path):
    r=inspect_synthetic_window_robustness(tmp_path)
    assert r["status"]=="not-authorized"
    assert not r["microphone_opened"] and not r["speaker_opened"]
    assert not r["user_audio_used"] and not r["production_modified"]
    assert not r["real_human_speech_robustness_proven"]


@pytest.mark.parametrize("shift,expected_first", [
    (0, 6000), (-250, 2000), (400, 12400),
])
def test_zero_fill_shift_has_precise_expected_synthetic_position(
    shift, expected_first
):
    output=perturb_three_second_pcm(signal(),shift_ms=shift)
    indices=active_indices(output)
    assert len(output)==CAPTURE_BYTES
    assert min(indices)==expected_first
    assert max(indices)==expected_first+17999
    assert output!=b""


def test_gain_25_percent_preserves_positions_and_integer_limits():
    original=signal()
    quiet=perturb_three_second_pcm(original,gain_pct=25)
    before=active_indices(original)
    after=active_indices(quiet)
    assert before==after
    assert quiet!=original
    values=array.array("h")
    values.frombytes(quiet)
    assert max(values)==750


def test_all_variants_are_fixed_pcm_and_no_audio_format_change():
    variants=build_variants(signal())
    assert len(variants)==len(FIXTURE_VARIANTS)==8
    assert all(type(v) is bytes and len(v)==CAPTURE_BYTES for v in variants)
    assert variants[0]==signal()
    assert variants[1]!=signal()
    assert variants[2]!=signal()
    assert variants[3]!=signal()
    assert all(variants[i]!=signal() for i in range(4, 8))
    assert set(classify_pcm_activity_layout(v) for v in variants) <= {
        "no-significant-activity", "early-activity", "middle-activity",
        "late-activity", "distributed-activity", "invalid-pcm",
    }



def rms(raw):
    samples=array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return math.sqrt(sum(v*v for v in samples)/len(samples))


@pytest.mark.parametrize("fault", [
    "noise_snr_12db", "noise_snr_0db", "echo_180ms",
    "onset_muted_700ms",
])
def test_acoustic_faults_deterministic_and_no_format_change(fault):
    original=signal()
    first=apply_fixed_acoustic_fault(original,fault=fault)
    second=apply_fixed_acoustic_fault(original,fault=fault)
    assert first == second and first != original
    assert len(first)==CAPTURE_BYTES
    assert type(first) is bytes


def test_noise_levels_are_bounded_and_zero_db_is_more_disruptive():
    original=signal()
    moderate=apply_fixed_acoustic_fault(original,fault="noise_snr_12db")
    strong=apply_fixed_acoustic_fault(original,fault="noise_snr_0db")
    # The tested noise is not measured microphone noise. Only the relative
    # synthetic amplitude increase is proven by this fixed input.
    diff=lambda x: math.sqrt(sum(
        (a-b)**2 for a,b in zip(decode(original),decode(x))
    ) / 48000)
    assert diff(strong) > diff(moderate) * 3


def decode(raw):
    samples=array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def test_muting_initial_700ms_cuts_actual_synthetic_onset():
    muted=decode(apply_fixed_acoustic_fault(signal(),fault="onset_muted_700ms"))
    assert all(value == 0 for value in muted[:11200])
    assert muted[11200] == 3000
    assert muted[-1] == 0


def test_echo_changes_signal_at_exact_positive_delay():
    source=signal()
    original=decode(source)
    echo=decode(apply_fixed_acoustic_fault(source,fault="echo_180ms"))
    assert echo[6000] == original[6000]
    assert echo[6000 + 180*16] > original[6000 + 180*16]


@pytest.mark.parametrize("bad,fault", [
    (b"", "echo_180ms"), (None, "noise_snr_0db"),
    (bytes(CAPTURE_BYTES-1), "onset_muted_700ms"),
    (bytes(CAPTURE_BYTES), "../bad"),
    (bytes(CAPTURE_BYTES), "microphone"),
])
def test_bad_or_untrusted_noise_sources_are_denied(bad,fault):
    with pytest.raises(ValueError):
        apply_fixed_acoustic_fault(bad,fault=fault)


@pytest.mark.parametrize("raw,shift,gain", [
    (b"",0,100), (bytes(CAPTURE_BYTES-1),0,100),
    (None,0,100), (bytes(CAPTURE_BYTES),True,100),
    (bytes(CAPTURE_BYTES),-251,100),
    (bytes(CAPTURE_BYTES),401,100),
    (bytes(CAPTURE_BYTES),0,1),
    (bytes(CAPTURE_BYTES),0,110),
    (bytes(CAPTURE_BYTES),0,True),
])
def test_unbounded_or_unsafe_shift_input_rejected(raw,shift,gain):
    with pytest.raises(ValueError):
        perturb_three_second_pcm(raw,shift_ms=shift,gain_pct=gain)


def test_no_client_supplied_asr_success_flags_or_device_access():
    import scripts.ventuno_stt_synthetic_window_robustness as mod
    source=Path(mod.__file__).read_text()
    assert 'real_human_speech_robustness_proven": False' in source
    for bad in ('arecord', 'aplay', 'sounddevice', 'pyaudio',
                'SelfDevPromotionManager', 'systemctl start',
                'approved_short_question(', 'subprocess.run('):
        assert bad not in source
    assert 'no_speech_threshold=0.6' not in source
