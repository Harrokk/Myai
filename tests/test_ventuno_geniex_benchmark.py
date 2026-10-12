from scripts.ventuno_geniex_benchmark import aggregate_timings, numeric_timing


def test_numeric_timing_accepts_only_finite_bounded_numbers():
    assert numeric_timing({
        "timings": {
            "prompt_n": 38,
            "prompt_ms": 103.175,
            "prompt_per_second": 368.306,
            "predicted_n": 2,
            "predicted_ms": 64.902,
            "predicted_per_second": 30.815,
            "strange": "secret",
        }
    }) == {
        "prompt_n": 38.0,
        "prompt_ms": 103.17,
        "prompt_per_second": 368.31,
        "predicted_n": 2.0,
        "predicted_ms": 64.9,
        "predicted_per_second": 30.82,
    }


def test_numeric_timing_rejects_invalid():
    assert numeric_timing({"timings": None}) == {}
    assert numeric_timing({"timings": {"prompt_n": True, "predicted_n": -3}}) == {}


def test_median_decode_rate_ignores_tiny_generations():
    samples = [
        {"prompt_per_second": 330.0, "predicted_per_second": 40.0, "predicted_n": 1},
        {"prompt_per_second": 360.0, "predicted_per_second": 28.0, "predicted_n": 70},
        {"prompt_per_second": 390.0, "predicted_per_second": 32.0, "predicted_n": 82},
    ]
    assert aggregate_timings(samples) == {
        "median_prompt_per_second": 360.0,
        "median_predicted_per_second": 30.0,
    }
