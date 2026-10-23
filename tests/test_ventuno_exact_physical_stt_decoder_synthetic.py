"""Pure synthetic tests of exact production Whisper data-path trial."""
import array
from pathlib import Path

import pytest

from scripts import ventuno_exact_physical_stt_decoder_synthetic as d


def pcm():
    # Synthetic deterministic non-speech PCM; no device access.
    data=array.array("h", [0]*48000)
    data[18000:20000]=array.array("h", [2500]*2000)
    return data.tobytes()


@pytest.mark.parametrize("words,matched,category", [
    ("Vad heter du?", True, "approved"),
    ("vad heter du", True, "approved"),
    ("Vad heter kunden?", False, "other-unmatched-utterance"),
    ("Hej!", False, "unrelated-short-utterance"),
    ("", False, "empty-or-silence"),
    ("Vänta en sekund. Säg: Vad heter du.", False,
     "spoken-cue-echo-suspected"),
])
def test_pinned_fixture_exact_live_classifier_never_exposes_words(
    words,matched,category,
):
    calls=[]
    def decoder(raw):
        calls.append(len(raw))
        return words
    result=d.private_exact_decoder_trial(
        pcm(),variant="clean_piper",decode=decoder,
    )
    assert calls == [96000]
    assert result["accepted_exact_harmless_question"] is matched
    assert result["private_transcript_category"] == category
    assert words not in str(result) if words else True
    assert "transcript" not in result
    assert "raw" not in result


@pytest.mark.parametrize("bad,variant", [
    (b"","clean_piper"),
    (b"x" * 96001,"clean_piper"),
    (None,"clean_piper"),
    (bytes(96000),"unknown"),
    (bytes(96000),None),
])
def test_bad_input_cannot_start_decoder(bad,variant):
    def never(_):
        pytest.fail("decoder invoked for invalid input")
    with pytest.raises(ValueError):
        d.private_exact_decoder_trial(bad, variant=variant, decode=never)


@pytest.mark.parametrize("out", [
    None,True,{}, "x" * 97,
])
def test_invalid_decoder_response_does_not_escape(out):
    with pytest.raises(ValueError):
        d.private_exact_decoder_trial(
            pcm(),variant="clean_piper",decode=lambda _:out,
        )


def test_mid_window_synthetic_shift_keeps_exact_pcm_and_loses_only_tail():
    original=pcm()
    delayed=d.shift_piper_to_middle(original)
    shift=800*16*2
    assert len(delayed)==96000
    assert delayed[:shift]==bytes(shift)
    assert delayed[shift:]==original[:-shift]
    assert d.classify_pcm_activity_layout(delayed)=="middle-activity"


@pytest.mark.parametrize("bad",[b"",bytes(96001),None])
def test_mid_window_shift_rejects_invalid_synthetic_audio(bad):
    with pytest.raises(ValueError):
        d.shift_piper_to_middle(bad)


def test_missing_explicit_synthetic_flag_does_not_load_models(tmp_path):
    result=d.inspect_exact_live_decoder(tmp_path)
    assert result["status"]=="not-authorized"
    assert not result["microphone_opened"]
    assert not result["speaker_opened"]
    assert not result["user_audio_used"]
    assert not result["production_modified"]
    assert not result["authorizes_physical_recording"]
    assert not result["authorizes_physical_playback"]


def test_exact_worker_is_reused_not_modified():
    import scripts.ventuno_usb_dialogue_hardware as hw
    source=Path(d.__file__).read_text()
    assert d._limited_whisper_child is hw._limited_whisper_child
    assert "_limited_whisper_child(root, py, tiny, v)" in source
    assert "_INFERENCE" not in source
    for forbidden in ("arecord", "aplay", "systemctl", "sudo",
                      "answer_one_short_voice_question(", "SelfDevPromotionManager",
                      "audio_device.open", "microphone.read", "open('/dev"):
        assert forbidden not in source
    assert '"raw_pcm_or_transcript_saved": False' in source
    assert '"authorizes_physical_recording": False' in source
