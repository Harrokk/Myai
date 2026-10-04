from core import memory_policy


def settings():
    return {
        "memory": {
            "auto_save_threshold": 80,
            "review_threshold": 55,
        }
    }


def test_explicit_remember_request_is_save_candidate():
    result = memory_policy.assess_memory_candidate(
        "Kom ihåg att jag föredrar korta svar.",
        settings=settings(),
    )

    assert result["action"] == "save"
    assert result["category"] in {
        "explicit",
        "preference",
    }
    assert result["content"] == (
        "jag föredrar korta svar."
    )


def test_preference_without_explicit_request_is_review_candidate():
    result = memory_policy.assess_memory_candidate(
        "Jag föredrar modulär kod framför stora monoliter.",
        settings=settings(),
    )

    assert result["action"] == "review"
    assert result["category"] == "preference"


def test_from_now_on_rule_can_be_saved():
    result = memory_policy.assess_memory_candidate(
        "Från och med nu ska alltid prisjämförelser använda fem kandidater.",
        settings=settings(),
    )

    assert result["action"] == "save"
    assert result["category"] == "rule"


def test_temporary_question_is_ignored():
    result = memory_policy.assess_memory_candidate(
        "Vad är vädret idag?",
        settings=settings(),
    )

    assert result["action"] == "ignore"


def test_sensitive_explicit_memory_request_is_blocked():
    result = memory_policy.assess_memory_candidate(
        "Kom ihåg att mitt lösenord är hunter2.",
        settings=settings(),
    )

    assert result["action"] == "ignore"
    assert result["sensitive"] is True
    assert result["content"] == ""


def test_api_key_signal_is_sensitive():
    assert memory_policy.contains_sensitive_memory_data(
        "Min API-nyckel är abc123"
    ) is True


def test_repeated_preference_increases_score():
    first = memory_policy.assess_memory_candidate(
        "Jag föredrar modulär kod.",
        settings=settings(),
    )
    repeated = memory_policy.assess_memory_candidate(
        "Jag föredrar modulär kod.",
        settings=settings(),
        prior_messages=[
            "Jag föredrar modulär kod.",
        ],
    )

    assert repeated["score"] > first["score"]


def test_empty_text_is_ignored():
    result = memory_policy.assess_memory_candidate(
        "   ",
        settings=settings(),
    )

    assert result["action"] == "ignore"
    assert result["score"] == 0
