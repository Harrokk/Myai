from copy import deepcopy
import json

import pytest

from core.config import DEFAULT_SETTINGS
from modules.internet import weather


def settings(
    *,
    enabled=True,
    default_location="",
):
    value = deepcopy(
        DEFAULT_SETTINGS
    )
    value["internet"][
        "enabled"
    ] = True
    value["weather"][
        "enabled"
    ] = enabled
    value["weather"][
        "default_location"
    ] = default_location
    return value


def geocoding_payload():
    return {
        "results": [
            {
                "id": 1,
                "name": "Stockholm",
                "latitude": 59.32938,
                "longitude": 18.06871,
                "timezone": "Europe/Stockholm",
                "country_code": "SE",
                "country": "Sverige",
                "admin1": "Stockholms län",
            },
            {
                "id": 2,
                "name": "Stockholm",
                "latitude": 42.0,
                "longitude": -93.0,
                "timezone": "America/Chicago",
                "country_code": "US",
                "country": "USA",
                "admin1": "Iowa",
            },
        ]
    }


def forecast_payload():
    return {
        "latitude": 59.3,
        "longitude": 18.1,
        "timezone": "Europe/Stockholm",
        "timezone_abbreviation": "CEST",
        "current": {
            "time": "2026-10-05T14:00",
            "temperature_2m": 12.3,
            "apparent_temperature": 11.1,
            "precipitation": 0.2,
            "weather_code": 61,
            "wind_speed_10m": 14.0,
        },
        "daily": {
            "time": [
                "2026-10-05",
                "2026-10-06",
                "2026-10-07",
            ],
            "weather_code": [
                61,
                2,
                0,
            ],
            "temperature_2m_max": [
                14.0,
                15.0,
                16.0,
            ],
            "temperature_2m_min": [
                8.0,
                7.0,
                6.0,
            ],
            "precipitation_sum": [
                2.5,
                0.0,
                0.0,
            ],
            "precipitation_probability_max": [
                80,
                20,
                5,
            ],
            "wind_speed_10m_max": [
                22.0,
                18.0,
                12.0,
            ],
        },
    }


def fake_fetch(
    url,
    max_chars=20_000,
    settings=None,
):
    if (
        "geocoding-api.open-meteo.com"
        in url
    ):
        payload = geocoding_payload()
        final_url = url
    elif (
        "api.open-meteo.com"
        in url
    ):
        payload = forecast_payload()
        final_url = url
    else:
        raise AssertionError(
            "unexpected URL"
        )

    return {
        "available": True,
        "requested_url": url,
        "final_url": final_url,
        "status_code": 200,
        "content_type": "application/json",
        "title": "",
        "text": json.dumps(
            payload
        ),
        "metadata": {},
        "canonical_url": "",
        "external_links": [],
        "redirects": 0,
        "truncated": False,
        "max_chars": max_chars,
    }


def test_extract_weather_location_handles_swedish_and_day_word():
    assert weather.extract_weather_location(
        "Vad blir det för väder i Stockholm idag?"
    ) == "Stockholm"
    assert weather.extract_weather_location(
        "Prognos för Uppsala imorgon"
    ) == "Uppsala"


def test_resolve_weather_location_reports_selected_place_and_alternatives():
    result = weather.resolve_weather_location(
        "Stockholm",
        settings=settings(),
        fetch_function=fake_fetch,
    )

    assert result[
        "name"
    ] == "Stockholm"
    assert result[
        "country_code"
    ] == "SE"
    assert result[
        "timezone"
    ] == "Europe/Stockholm"
    assert result[
        "latitude"
    ] == 59.32938
    assert result[
        "alternative_count"
    ] == 1


def test_weather_data_fetches_current_and_three_day_forecast_without_gps():
    result = weather.weather_data(
        "Vad blir det för väder i Stockholm idag?",
        settings=settings(),
        fetch_function=fake_fetch,
    )

    assert result[
        "available"
    ] is True
    assert result[
        "provider"
    ] == "open_meteo"
    assert result[
        "location"
    ][
        "name"
    ] == "Stockholm"
    assert result[
        "current"
    ][
        "temperature_c"
    ] == 12.3
    assert result[
        "current"
    ][
        "description"
    ] == "lätt regn"
    assert len(
        result[
            "daily"
        ]
    ) == 3
    assert result[
        "daily"
    ][
        1
    ][
        "description"
    ] == "delvis molnigt"


def test_weather_uses_explicit_default_location_when_question_has_none():
    result = weather.weather_data(
        "Vad blir det för väder idag?",
        settings=settings(
            default_location="Stockholm",
        ),
        fetch_function=fake_fetch,
    )

    assert result[
        "available"
    ] is True
    assert result[
        "location"
    ][
        "query"
    ] == "Stockholm"


def test_weather_without_location_or_default_refuses_to_guess():
    result = weather.weather_data(
        "Vad blir det för väder idag?",
        settings=settings(),
        fetch_function=fake_fetch,
    )

    assert result[
        "available"
    ] is False
    assert "Ingen plats" in result[
        "reason"
    ]


def test_weather_disabled_returns_before_fetch():
    calls = []

    def should_not_fetch(
        *args,
        **kwargs,
    ):
        calls.append(
            args
        )
        raise AssertionError(
            "fetch should not run"
        )

    result = weather.weather_data(
        "Väder i Stockholm",
        settings=settings(
            enabled=False,
        ),
        fetch_function=should_not_fetch,
    )

    assert result[
        "available"
    ] is False
    assert calls == []


def test_weather_redirect_to_unapproved_host_is_rejected():
    def bad_fetch(
        url,
        max_chars=20_000,
        settings=None,
    ):
        result = fake_fetch(
            url,
            max_chars=max_chars,
            settings=settings,
        )
        result[
            "final_url"
        ] = (
            "https://example.com/weather.json"
        )
        return result

    with pytest.raises(
        ValueError,
        match="otillåten host",
    ):
        weather.resolve_weather_location(
            "Stockholm",
            settings=settings(),
            fetch_function=bad_fetch,
        )


def test_weather_invalid_json_is_rejected():
    def bad_json(
        url,
        max_chars=20_000,
        settings=None,
    ):
        return {
            "available": True,
            "final_url": url,
            "text": "{broken",
        }

    with pytest.raises(
        ValueError,
        match="ogiltig JSON",
    ):
        weather.resolve_weather_location(
            "Stockholm",
            settings=settings(),
            fetch_function=bad_json,
        )


def test_weather_formatter_discloses_resolved_location_and_source():
    result = weather.weather_data(
        "Väder i Stockholm",
        settings=settings(),
        fetch_function=fake_fetch,
    )

    text = weather.format_weather(
        result
    )

    assert "Stockholm" in text
    assert "Europe/Stockholm" in text
    assert "Open-Meteo" in text
    assert "andra träffar" in text


def test_weather_tool_accepts_user_input():
    assert weather.TOOLS[
        "weather_forecast"
    ][
        "pass_user_input"
    ] is True
