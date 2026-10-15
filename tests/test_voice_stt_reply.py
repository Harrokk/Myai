"""Security regressions for STRICT isolated STT JSON; zero model/audio device use."""
import json

import pytest

from core.voice_stt_reply import decode_stt_reply, MAX_STT_REPLY_BYTES


VALID = b'{"text":"Hej","language":"sv","confidence":null}'


def test_exact_schema_accepts_utf8_swedish_text():
    data = json.dumps({
        "text": "Räknaren är igång",
        "language": "sv", "confidence": None,
    }, ensure_ascii=False).encode("utf-8")
    assert decode_stt_reply(data) == {
        "text": "Räknaren är igång", "language": "sv",
        "confidence": None,
    }


@pytest.mark.parametrize("bad", [
    b'{"text":"approved","text":"delete","language":"sv","confidence":null}',
    b'{"text":"hej","language":"sv","language":"en","confidence":null}',
    b'{"text":"hej","language":"sv","confidence":null,"confidence":1}',
    b'{"text":"hej","language":"sv","confidence":NaN}',
    b'{"text":"hej","language":"sv","confidence":Infinity}',
    b'{"text":"hej","language":"sv","confidence":-Infinity}',
    b'{"text":"hej","language":"sv","confidence":true}',
    b'{"text":"hej","language":"sv","confidence":false}',
    b'{"text":"hej","language":"sv","confidence":0.99}',
    b'{"text":true,"language":"sv","confidence":null}',
    b'{"text":123,"language":"sv","confidence":null}',
    b'{"text":"hej","language":true,"confidence":null}',
    b'{"text":"hej","language":"da","confidence":null}',
    b'{"text":"hej","language":"sv","confidence":null,"audio":"SECRET"}',
    b'{"text":"hej","language":"sv"}',
    b'{"text":"hej","language":"sv","confidence":null',
    b'{"text":"hej","language":"sv","confidence":null}extra',
    b'{"text": "\xff", "language":"sv","confidence":null}',
    b'\xff\xfe{"text":"hej","language":"sv","confidence":null}',
    b'null', b'[]', b'true', b'', b'not-json',
])
def test_invalid_or_ambiguous_json_is_rejected_without_echo(bad):
    with pytest.raises(ValueError) as err:
        decode_stt_reply(bad)
    assert str(err.value) == "Invalid STT reply"
    assert "SECRET" not in str(err.value)


@pytest.mark.parametrize("bad", [
    None, False, "{}", bytearray(VALID),
    b" " * (MAX_STT_REPLY_BYTES + 1),
    json.dumps({"text":"X" * 4097, "language":"sv","confidence":None}).encode(),
])
def test_invalid_type_or_oversize_reply_does_not_reach_json_parser(bad):
    with pytest.raises(ValueError, match="Invalid STT reply"):
        decode_stt_reply(bad)


def test_exact_boundary_of_8192_bytes_is_allowed():
    padded = VALID + b" " * (MAX_STT_REPLY_BYTES - len(VALID))
    assert len(padded) == 8192
    assert decode_stt_reply(padded)["text"] == "Hej"
    with pytest.raises(ValueError):
        decode_stt_reply(padded + b" ")


def test_rejected_json_exception_has_no_raw_child_output():
    suspicious = b'{"text":"SECRET_MIC_AUDIO","text":"danger","language":"sv","confidence":null}'
    with pytest.raises(ValueError) as exc:
        decode_stt_reply(suspicious)
    assert "SECRET" not in str(exc.value)
    assert exc.value.__cause__ is None
