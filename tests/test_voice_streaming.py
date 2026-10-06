import threading
import time

from core.voice_streaming import (
    SentenceChunkBuffer,
    StreamingTTSCoordinator,
)


class BlockingTTS:
    def __init__(self):
        self.spoken = []
        self.release = threading.Event()
        self.stopped = False

    def speak(self, text):
        self.spoken.append(text)
        self.release.wait(timeout=0.2)

    def stop(self):
        self.stopped = True
        self.release.set()
        return True


def test_sentence_buffer_emits_complete_sentences_across_chunks():
    buffer = SentenceChunkBuffer(
        min_chars=5,
        max_chars=100,
    )

    first = buffer.feed(
        "Det här är första"
    )
    second = buffer.feed(
        " meningen. Här kommer"
    )
    third = buffer.feed(
        " den andra!"
    )

    assert first == []
    assert second == [
        "Det här är första meningen."
    ]
    assert third == [
        "Här kommer den andra!"
    ]
    assert buffer.flush() == []


def test_sentence_buffer_forces_long_segment_without_punctuation():
    buffer = SentenceChunkBuffer(
        min_chars=10,
        max_chars=20,
    )

    segments = buffer.feed(
        "detta är en ganska lång text utan slut"
    )

    assert segments
    assert all(
        len(item) <= 20
        for item in segments
    )


def test_streaming_tts_preserves_sentence_order():
    tts = BlockingTTS()
    tts.release.set()
    coordinator = StreamingTTSCoordinator(
        tts,
        min_chars=5,
        max_chars=100,
    )

    coordinator.feed(
        "Första meningen. Andra"
    )
    coordinator.feed(
        " meningen."
    )
    coordinator.finish()

    assert coordinator.wait(timeout=1)
    assert tts.spoken == [
        "Första meningen.",
        "Andra meningen.",
    ]


def test_streaming_tts_stop_interrupts_and_clears_queue():
    tts = BlockingTTS()
    coordinator = StreamingTTSCoordinator(
        tts,
        min_chars=5,
        max_chars=100,
        stop_timeout_seconds=0.5,
    )

    coordinator.feed(
        "Första meningen. Andra meningen."
    )

    deadline = time.time() + 1

    while not tts.spoken and time.time() < deadline:
        time.sleep(0.01)

    assert coordinator.stop() is True
    assert tts.stopped is True
    assert tts.spoken == [
        "Första meningen."
    ]
