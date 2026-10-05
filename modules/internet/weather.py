import json
import re
from urllib.parse import urlencode, urlparse

from core.config import load_settings
from modules.internet.fetch import fetch_public_page


_ALLOWED_GEOCODING_HOSTS = {
    "geocoding-api.open-meteo.com",
}
_ALLOWED_FORECAST_HOSTS = {
    "api.open-meteo.com",
}

_WEATHER_CODE_SV = {
    0: "klart",
    1: "mest klart",
    2: "delvis molnigt",
    3: "mulet",
    45: "dimma",
    48: "rimfrostsdimma",
    51: "lätt duggregn",
    53: "måttligt duggregn",
    55: "kraftigt duggregn",
    56: "lätt underkylt duggregn",
    57: "kraftigt underkylt duggregn",
    61: "lätt regn",
    63: "måttligt regn",
    65: "kraftigt regn",
    66: "lätt underkylt regn",
    67: "kraftigt underkylt regn",
    71: "lätt snöfall",
    73: "måttligt snöfall",
    75: "kraftigt snöfall",
    77: "snökorn",
    80: "lätta regnskurar",
    81: "måttliga regnskurar",
    82: "kraftiga regnskurar",
    85: "lätta snöbyar",
    86: "kraftiga snöbyar",
    95: "åska",
    96: "åska med lätt hagel",
    99: "åska med kraftigt hagel",
}


def _validate_endpoint(
    url,
    allowed_hosts,
    *,
    label,
):
    try:
        parsed = urlparse(
            str(
                url
                or ""
            )
        )
    except ValueError as error:
        raise ValueError(
            f"{label} har ogiltig URL."
        ) from error

    host = (
        parsed.hostname
        or ""
    ).lower()

    if parsed.scheme != "https":
        raise ValueError(
            f"{label} måste använda https."
        )

    if host not in allowed_hosts:
        raise ValueError(
            f"{label} använder otillåten host."
        )

    return str(
        url
    )


def _fetch_json(
    url,
    *,
    settings,
    fetch_function,
    allowed_hosts,
    label,
):
    _validate_endpoint(
        url,
        allowed_hosts,
        label=label,
    )

    try:
        page = fetch_function(
            url,
            max_chars=20_000,
            settings=settings,
        )
    except TypeError:
        page = fetch_function(
            url
        )

    if not page.get(
        "available"
    ):
        raise ValueError(
            page.get(
                "reason",
                f"{label} kunde inte hämtas.",
            )
        )

    final_url = (
        page.get(
            "final_url"
        )
        or url
    )
    _validate_endpoint(
        final_url,
        allowed_hosts,
        label=label,
    )

    try:
        payload = json.loads(
            page.get(
                "text",
                ""
            )
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError(
            f"{label} returnerade ogiltig JSON."
        ) from error

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            f"{label} returnerade oväntat JSON-format."
        )

    if payload.get(
        "error"
    ):
        raise ValueError(
            str(
                payload.get(
                    "reason",
                    f"{label} returnerade ett fel.",
                )
            )
        )

    return (
        payload,
        final_url,
    )


def extract_weather_location(
    user_input,
):
    text = " ".join(
        str(
            user_input
            or ""
        ).strip().split()
    )

    patterns = (
        r"vädret?\s+i\s+(.+)",
        r"väder\s+i\s+(.+)",
        r"prognos(?:en)?\s+(?:för|i)\s+(.+)",
        r"weather\s+in\s+(.+)",
        r"forecast\s+(?:for|in)\s+(.+)",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        location = match.group(
            1
        ).strip(
            " .?!"
        )
        location = re.sub(
            (
                r"\s+(?:idag|i dag|imorgon|i morgon|"
                r"today|tomorrow)$"
            ),
            "",
            location,
            flags=re.IGNORECASE,
        ).strip()

        if location:
            return location

    return ""


def resolve_weather_location(
    location,
    *,
    settings=None,
    fetch_function=None,
):
    settings = (
        settings
        or load_settings()
    )
    config = settings.get(
        "weather",
        {},
    )
    name = str(
        location
        or ""
    ).strip()

    if not name:
        raise ValueError(
            "Platsnamn saknas för väderfrågan."
        )

    base_url = _validate_endpoint(
        config.get(
            "geocoding_url",
            "",
        ),
        _ALLOWED_GEOCODING_HOSTS,
        label="Open-Meteo geokodning",
    )
    language = str(
        config.get(
            "language",
            "sv",
        )
        or "sv"
    ).strip().lower()

    query = urlencode(
        {
            "name": name,
            "count": 5,
            "language": language,
            "format": "json",
        }
    )
    url = (
        base_url
        + "?"
        + query
    )
    active_fetch = (
        fetch_function
        or fetch_public_page
    )
    payload, final_url = _fetch_json(
        url,
        settings=settings,
        fetch_function=active_fetch,
        allowed_hosts=_ALLOWED_GEOCODING_HOSTS,
        label="Open-Meteo geokodning",
    )
    results = payload.get(
        "results",
        []
    )

    if not isinstance(
        results,
        list,
    ) or not results:
        raise ValueError(
            f"Ingen plats hittades för {name}."
        )

    selected = results[
        0
    ]

    if not isinstance(
        selected,
        dict,
    ):
        raise ValueError(
            "Geokodningen returnerade ogiltig platsdata."
        )

    try:
        latitude = float(
            selected[
                "latitude"
            ]
        )
        longitude = float(
            selected[
                "longitude"
            ]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "Geokodningen saknar giltiga koordinater."
        ) from error

    if not (
        -90.0
        <= latitude
        <= 90.0
        and -180.0
        <= longitude
        <= 180.0
    ):
        raise ValueError(
            "Geokodningen returnerade koordinater utanför giltigt intervall."
        )

    return {
        "query": name,
        "name": str(
            selected.get(
                "name",
                name,
            )
        ),
        "admin1": str(
            selected.get(
                "admin1",
                "",
            )
            or ""
        ),
        "country": str(
            selected.get(
                "country",
                "",
            )
            or ""
        ),
        "country_code": str(
            selected.get(
                "country_code",
                "",
            )
            or ""
        ),
        "timezone": str(
            selected.get(
                "timezone",
                "",
            )
            or ""
        ),
        "latitude": latitude,
        "longitude": longitude,
        "geocoding_source_url": final_url,
        "alternative_count": max(
            0,
            len(
                results
            )
            - 1,
        ),
    }


def _weather_description(
    code,
):
    try:
        number = int(
            code
        )
    except (
        TypeError,
        ValueError,
    ):
        return "okänt väder"

    return _WEATHER_CODE_SV.get(
        number,
        f"väderkod {number}",
    )


def _first_daily_value(
    daily,
    key,
):
    values = daily.get(
        key,
        []
    )

    if not isinstance(
        values,
        list,
    ) or not values:
        return None

    return values[
        0
    ]


def fetch_weather_forecast(
    resolved_location,
    *,
    settings=None,
    fetch_function=None,
):
    settings = (
        settings
        or load_settings()
    )
    config = settings.get(
        "weather",
        {},
    )

    if not config.get(
        "enabled",
        False,
    ):
        return {
            "available": False,
            "reason": (
                "Väderfunktionen är avstängd i konfigurationen."
            ),
        }

    if not settings.get(
        "internet",
        {},
    ).get(
        "enabled",
        False,
    ):
        return {
            "available": False,
            "reason": (
                "Väderfunktionen kräver internet.enabled=true."
            ),
        }

    base_url = _validate_endpoint(
        config.get(
            "forecast_url",
            "",
        ),
        _ALLOWED_FORECAST_HOSTS,
        label="Open-Meteo forecast",
    )

    try:
        forecast_days = int(
            config.get(
                "forecast_days",
                3,
            )
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "weather.forecast_days måste vara ett heltal."
        ) from error

    forecast_days = max(
        1,
        min(
            forecast_days,
            7,
        ),
    )
    query = urlencode(
        {
            "latitude": resolved_location[
                "latitude"
            ],
            "longitude": resolved_location[
                "longitude"
            ],
            "current": (
                "temperature_2m,apparent_temperature,"
                "precipitation,weather_code,wind_speed_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,"
                "temperature_2m_min,precipitation_sum,"
                "precipitation_probability_max,"
                "wind_speed_10m_max"
            ),
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "timezone": "auto",
            "forecast_days": forecast_days,
        }
    )
    url = (
        base_url
        + "?"
        + query
    )
    active_fetch = (
        fetch_function
        or fetch_public_page
    )
    payload, final_url = _fetch_json(
        url,
        settings=settings,
        fetch_function=active_fetch,
        allowed_hosts=_ALLOWED_FORECAST_HOSTS,
        label="Open-Meteo forecast",
    )
    current = payload.get(
        "current",
        {}
    )
    daily = payload.get(
        "daily",
        {}
    )

    if not isinstance(
        current,
        dict,
    ) or not isinstance(
        daily,
        dict,
    ):
        raise ValueError(
            "Väder-API:t saknar current/daily-data."
        )

    daily_times = daily.get(
        "time",
        []
    )
    daily_rows = []

    if isinstance(
        daily_times,
        list,
    ):
        for index, day in enumerate(
            daily_times[
                :forecast_days
            ]
        ):
            def value(
                key,
            ):
                values = daily.get(
                    key,
                    []
                )

                if (
                    isinstance(
                        values,
                        list,
                    )
                    and index
                    < len(
                        values
                    )
                ):
                    return values[
                        index
                    ]

                return None

            daily_rows.append(
                {
                    "date": day,
                    "weather_code": value(
                        "weather_code"
                    ),
                    "description": (
                        _weather_description(
                            value(
                                "weather_code"
                            )
                        )
                    ),
                    "temperature_max_c": value(
                        "temperature_2m_max"
                    ),
                    "temperature_min_c": value(
                        "temperature_2m_min"
                    ),
                    "precipitation_sum_mm": value(
                        "precipitation_sum"
                    ),
                    "precipitation_probability_max_percent": value(
                        "precipitation_probability_max"
                    ),
                    "wind_speed_max_kmh": value(
                        "wind_speed_10m_max"
                    ),
                }
            )

    return {
        "available": True,
        "provider": "open_meteo",
        "source_url": final_url,
        "timezone": str(
            payload.get(
                "timezone",
                resolved_location.get(
                    "timezone",
                    "",
                ),
            )
            or ""
        ),
        "timezone_abbreviation": str(
            payload.get(
                "timezone_abbreviation",
                "",
            )
            or ""
        ),
        "location": resolved_location,
        "current": {
            "time": current.get(
                "time"
            ),
            "temperature_c": current.get(
                "temperature_2m"
            ),
            "apparent_temperature_c": current.get(
                "apparent_temperature"
            ),
            "precipitation_mm": current.get(
                "precipitation"
            ),
            "weather_code": current.get(
                "weather_code"
            ),
            "description": _weather_description(
                current.get(
                    "weather_code"
                )
            ),
            "wind_speed_kmh": current.get(
                "wind_speed_10m"
            ),
        },
        "daily": daily_rows,
        "today": (
            daily_rows[
                0
            ]
            if daily_rows
            else {
                "weather_code": _first_daily_value(
                    daily,
                    "weather_code",
                ),
                "description": _weather_description(
                    _first_daily_value(
                        daily,
                        "weather_code",
                    )
                ),
            }
        ),
    }


def weather_data(
    user_input,
    *,
    settings=None,
    fetch_function=None,
):
    settings = (
        settings
        or load_settings()
    )
    config = settings.get(
        "weather",
        {},
    )

    if not config.get(
        "enabled",
        False,
    ):
        return {
            "available": False,
            "reason": (
                "Väderfunktionen är avstängd i konfigurationen."
            ),
        }

    explicit = extract_weather_location(
        user_input
    )
    location = (
        explicit
        or str(
            config.get(
                "default_location",
                "",
            )
            or ""
        ).strip()
    )

    if not location:
        return {
            "available": False,
            "reason": (
                "Ingen plats angavs och weather.default_location är tom."
            ),
        }

    resolved = resolve_weather_location(
        location,
        settings=settings,
        fetch_function=fetch_function,
    )
    return fetch_weather_forecast(
        resolved,
        settings=settings,
        fetch_function=fetch_function,
    )


def _fmt(
    value,
    suffix="",
):
    if value is None:
        return "saknas"

    return (
        str(
            value
        )
        + suffix
    )


def format_weather(
    result,
):
    if not result.get(
        "available"
    ):
        return (
            "Vädret kunde inte hämtas: "
            + result.get(
                "reason",
                "okänd orsak",
            )
        )

    location = result.get(
        "location",
        {}
    )
    place_parts = [
        location.get(
            "name",
            "",
        ),
        location.get(
            "admin1",
            "",
        ),
        location.get(
            "country",
            "",
        ),
    ]
    place = ", ".join(
        part
        for part in place_parts
        if part
    )
    current = result.get(
        "current",
        {}
    )
    lines = [
        (
            f"Väder för {place or 'vald plats'} "
            f"({result.get('timezone') or 'okänd tidszon'}):"
        ),
        (
            "Nu: "
            f"{current.get('description', 'okänt väder')}, "
            + _fmt(
                current.get(
                    "temperature_c"
                ),
                " °C",
            )
            + " (känns som "
            + _fmt(
                current.get(
                    "apparent_temperature_c"
                ),
                " °C",
            )
            + "), vind "
            + _fmt(
                current.get(
                    "wind_speed_kmh"
                ),
                " km/h",
            )
            + ", nederbörd "
            + _fmt(
                current.get(
                    "precipitation_mm"
                ),
                " mm",
            )
            + "."
        ),
    ]

    daily = result.get(
        "daily",
        [],
    )

    if daily:
        lines.append(
            "Prognos:"
        )

        for item in daily:
            lines.append(
                (
                    f"- {item.get('date')}: "
                    f"{item.get('description', 'okänt väder')}, "
                    + _fmt(
                        item.get(
                            "temperature_min_c"
                        ),
                        " °C",
                    )
                    + " till "
                    + _fmt(
                        item.get(
                            "temperature_max_c"
                        ),
                        " °C",
                    )
                    + ", nederbörd "
                    + _fmt(
                        item.get(
                            "precipitation_sum_mm"
                        ),
                        " mm",
                    )
                    + ", max sannolikhet "
                    + _fmt(
                        item.get(
                            "precipitation_probability_max_percent"
                        ),
                        "%",
                    )
                    + "."
                )
            )

    if location.get(
        "alternative_count",
        0
    ):
        lines.append(
            (
                "Platsen löstes automatiskt från geokodning; "
                f"{location['alternative_count']} andra träffar fanns."
            )
        )

    lines.append(
        "Källa: Open-Meteo."
    )
    return "\n".join(
        lines
    )


def weather_forecast(
    user_input,
):
    try:
        return format_weather(
            weather_data(
                user_input
            )
        )
    except Exception as error:
        return (
            "Vädret kunde inte hämtas: "
            f"{error}"
        )


TOOLS = {
    "weather_forecast": {
        "function": weather_forecast,
        "description": (
            "Hämtar aktuell väderstatus och kort prognos för en "
            "angiven plats eller weather.default_location via "
            "Open-Meteo. Kräver ingen GPS-hårdvara."
        ),
        "pass_user_input": True,
    },
}
