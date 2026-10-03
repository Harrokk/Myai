from modules.voice import consensus


def settings():
    return {
        "voice": {
            "primary_confidence_threshold": 0.80,
            "consensus_confidence_threshold": 0.75,
            "high_risk_confidence_threshold": 0.90,
            "agreement_threshold": 0.72,
            "uncertain_word_limit": 1,
            "max_interpretations": 3,
            "redundant_for_high_risk": True,
        }
    }


def transcript(text, confidence=0.95, uncertain_words=0):
    return {
        "text": text,
        "confidence": confidence,
        "uncertain_words": uncertain_words,
    }


def test_similar_phrasings_reach_high_similarity():
    score = consensus.transcript_similarity(
        "Hur mycket RAM använder datorn?",
        "Hur mycket ram använder min dator?",
    )

    assert score >= 0.72


def test_high_confidence_low_risk_primary_is_accepted():
    result = consensus.choose_transcript_consensus(
        [
            transcript(
                "Hur mycket RAM använder datorn?",
                confidence=0.95,
            )
        ],
        settings(),
    )

    assert result["status"] == "accepted"
    assert result["risk"] == "normal"


def test_low_confidence_primary_requests_more_stt():
    result = consensus.choose_transcript_consensus(
        [
            transcript(
                "Hur mycket RAM använder datorn?",
                confidence=0.50,
            )
        ],
        settings(),
    )

    assert result["status"] == "needs_more"


def test_high_risk_primary_requires_redundancy():
    result = consensus.choose_transcript_consensus(
        [
            transcript(
                "Radera filen rapport.txt",
                confidence=0.99,
            )
        ],
        settings(),
    )

    assert result["status"] == "needs_more"
    assert result["risk"] == "high"


def test_two_similar_interpretations_can_form_consensus():
    result = consensus.choose_transcript_consensus(
        [
            transcript(
                "Hur mycket RAM använder datorn?",
                0.93,
            ),
            transcript(
                "Hur mycket ram använder min dator?",
                0.91,
            ),
            transcript(
                "Vilket väder blir det?",
                0.88,
            ),
        ],
        settings(),
    )

    assert result["status"] == "accepted"
    assert result["agreement_count"] == 2


def test_risky_disagreement_requests_clarification():
    result = consensus.choose_transcript_consensus(
        [
            transcript(
                "Radera filen rapport.txt",
                0.98,
            ),
            transcript(
                "Läs filen rapport.txt",
                0.98,
            ),
            transcript(
                "Skapa filen rapport.txt",
                0.98,
            ),
        ],
        settings(),
    )

    assert result["status"] == "clarify"
    assert result["risk"] == "high"


def test_uncertain_words_trigger_redundant_stt():
    result = consensus.needs_redundant_stt(
        transcript(
            "Visa status",
            confidence=0.95,
            uncertain_words=1,
        ),
        settings(),
    )

    assert result is True


def test_hardware_mutation_is_high_risk():
    assert (
        consensus.command_risk(
            "Aktivera GPIO17 och starta motorn"
        )
        == "high"
    )


def test_read_only_hardware_question_is_not_high_risk():
    assert (
        consensus.command_risk(
            "Hur varm är min GPU?"
        )
        == "normal"
    )


def test_high_risk_consensus_requires_same_action():
    result = consensus.choose_transcript_consensus(
        [
            transcript(
                "Radera filen rapport.txt",
                0.96,
            ),
            transcript(
                "Radera rapport.txt",
                0.95,
            ),
            transcript(
                "Läs filen rapport.txt",
                0.97,
            ),
        ],
        settings(),
    )

    assert result["status"] == "accepted"
    assert result["risk"] == "high"
    assert result["agreement_count"] == 2
    assert "Radera" in result["text"]


def test_action_signature_distinguishes_file_operations():
    assert consensus.command_action_signature(
        "Radera filen rapport.txt"
    ) == "delete"
    assert consensus.command_action_signature(
        "Läs filen rapport.txt"
    ) == "file_read"
    assert consensus.command_action_signature(
        "Skapa filen rapport.txt"
    ) == "file_create"
