from pathlib import Path
from urllib.parse import urlparse

from core.config import DEFAULT_SETTINGS
from core.config_schema import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    find_unknown_config_keys,
)


_ALLOWED_LLM_PROVIDERS = {
    "ollama",
    "geniex",
}
_ALLOWED_VISION_PROVIDERS = {
    "ollama",
    "geniex",
}
_ALLOWED_FX_PROVIDERS = {
    "ecb",
}
_ALLOWED_ECB_HOSTS = {
    "www.ecb.europa.eu",
    "ecb.europa.eu",
}
_ALLOWED_WEATHER_PROVIDERS = {
    "open_meteo",
}
_ALLOWED_WEATHER_GEOCODING_HOSTS = {
    "geocoding-api.open-meteo.com",
}
_ALLOWED_WEATHER_FORECAST_HOSTS = {
    "api.open-meteo.com",
}


def _issue(level, code, message):
    return {
        "level": level,
        "code": code,
        "message": message,
    }


def _is_loopback_http(url):
    try:
        parsed = urlparse(
            str(url or "")
        )
    except ValueError:
        return False

    return (
        parsed.scheme == "http"
        and parsed.hostname
        in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
    )


def _is_string_list(value):
    return (
        isinstance(
            value,
            list,
        )
        and bool(
            value
        )
        and all(
            isinstance(
                item,
                str,
            )
            and bool(
                item.strip()
            )
            for item in value
        )
    )


def validate_settings(
    settings,
    *,
    require_ventuno_profile=False,
):
    issues = []

    if not isinstance(
        settings,
        dict,
    ):
        return {
            "valid": False,
            "errors": [
                _issue(
                    "error",
                    "settings_not_object",
                    "Konfigurationen måste vara ett objekt.",
                )
            ],
            "warnings": [],
        }

    schema_version = settings.get(
        "schema_version"
    )

    if (
        schema_version
        != CURRENT_CONFIG_SCHEMA_VERSION
    ):
        issues.append(
            _issue(
                "error",
                "unsupported_config_schema",
                (
                    "schema_version måste vara "
                    f"{CURRENT_CONFIG_SCHEMA_VERSION}."
                ),
            )
        )

    unknown_keys = find_unknown_config_keys(
        settings,
        DEFAULT_SETTINGS,
    )

    for path in unknown_keys:
        issues.append(
            _issue(
                "error",
                "unknown_config_key",
                (
                    "Okänd konfigurationsnyckel: "
                    f"{path}"
                ),
            )
        )

    weather = settings.get(
        "weather",
        {},
    )
    weather_enabled = bool(
        weather.get(
            "enabled",
            False,
        )
    )
    weather_provider = str(
        weather.get(
            "provider",
            "open_meteo",
        )
        or ""
    ).strip().lower()

    if weather_provider not in _ALLOWED_WEATHER_PROVIDERS:
        issues.append(
            _issue(
                "error",
                "weather_provider_invalid",
                (
                    "weather.provider måste vara open_meteo."
                ),
            )
        )

    for key, allowed_hosts, code in (
        (
            "geocoding_url",
            _ALLOWED_WEATHER_GEOCODING_HOSTS,
            "weather_geocoding_url_invalid",
        ),
        (
            "forecast_url",
            _ALLOWED_WEATHER_FORECAST_HOSTS,
            "weather_forecast_url_invalid",
        ),
    ):
        raw_url = str(
            weather.get(
                key,
                "",
            )
            or ""
        ).strip()

        try:
            parsed_weather_url = urlparse(
                raw_url
            )
            weather_host = (
                parsed_weather_url.hostname
                or ""
            ).lower()
        except ValueError:
            parsed_weather_url = None
            weather_host = ""

        if (
            parsed_weather_url is None
            or parsed_weather_url.scheme != "https"
            or weather_host not in allowed_hosts
        ):
            issues.append(
                _issue(
                    "error",
                    code,
                    (
                        f"weather.{key} måste vara en "
                        "godkänd https-adress hos Open-Meteo."
                    ),
                )
            )

    weather_language = str(
        weather.get(
            "language",
            "sv",
        )
        or ""
    ).strip().lower()

    if not (
        2
        <= len(
            weather_language
        )
        <= 8
        and all(
            char.isalpha()
            or char in {
                "-",
                "_",
            }
            for char in weather_language
        )
    ):
        issues.append(
            _issue(
                "error",
                "weather_language_invalid",
                (
                    "weather.language måste vara en kort språkkod."
                ),
            )
        )

    try:
        weather_forecast_days = int(
            weather.get(
                "forecast_days",
                3,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        weather_forecast_days = 0

    if not (
        1
        <= weather_forecast_days
        <= 7
    ):
        issues.append(
            _issue(
                "error",
                "weather_forecast_days_invalid",
                (
                    "weather.forecast_days måste vara mellan 1 och 7."
                ),
            )
        )

    if (
        weather_enabled
        and not bool(
            settings.get(
                "internet",
                {},
            ).get(
                "enabled",
                False,
            )
        )
    ):
        issues.append(
            _issue(
                "error",
                "weather_requires_internet",
                (
                    "weather.enabled=true kräver internet.enabled=true."
                ),
            )
        )

    fx = settings.get(
        "fx",
        {},
    )
    fx_enabled = bool(
        fx.get(
            "enabled",
            False,
        )
    )
    fx_provider = str(
        fx.get(
            "provider",
            "ecb",
        )
        or ""
    ).strip().lower()
    fx_target = str(
        fx.get(
            "target_currency",
            "SEK",
        )
        or ""
    ).strip().upper()
    fx_url = str(
        fx.get(
            "ecb_url",
            "",
        )
        or ""
    ).strip()

    if fx_provider not in _ALLOWED_FX_PROVIDERS:
        issues.append(
            _issue(
                "error",
                "fx_provider_invalid",
                (
                    "fx.provider måste vara en stödd provider: "
                    + ", ".join(
                        sorted(
                            _ALLOWED_FX_PROVIDERS
                        )
                    )
                ),
            )
        )

    if fx_target != "SEK":
        issues.append(
            _issue(
                "error",
                "fx_target_currency_invalid",
                (
                    "fx.target_currency måste vara SEK "
                    "för svensk prisjämförelse."
                ),
            )
        )

    try:
        parsed_fx_url = urlparse(
            fx_url
        )
        fx_host = (
            parsed_fx_url.hostname
            or ""
        ).lower()
    except ValueError:
        parsed_fx_url = None
        fx_host = ""

    if (
        parsed_fx_url is None
        or parsed_fx_url.scheme != "https"
        or fx_host not in _ALLOWED_ECB_HOSTS
    ):
        issues.append(
            _issue(
                "error",
                "fx_ecb_url_invalid",
                (
                    "fx.ecb_url måste vara en https-adress "
                    "på ecb.europa.eu."
                ),
            )
        )

    try:
        fx_max_age_days = int(
            fx.get(
                "max_age_days",
                7,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        fx_max_age_days = 0

    if not (
        1
        <= fx_max_age_days
        <= 14
    ):
        issues.append(
            _issue(
                "error",
                "fx_max_age_days_invalid",
                (
                    "fx.max_age_days måste vara mellan 1 och 14."
                ),
            )
        )

    if (
        fx_enabled
        and not bool(
            settings.get(
                "internet",
                {},
            ).get(
                "enabled",
                False,
            )
        )
    ):
        issues.append(
            _issue(
                "error",
                "fx_requires_internet",
                (
                    "fx.enabled=true kräver internet.enabled=true."
                ),
            )
        )

    llm = settings.get(
        "llm",
        {},
    )
    provider = str(
        llm.get(
            "provider",
            "",
        )
    ).strip().lower()

    if provider not in _ALLOWED_LLM_PROVIDERS:
        issues.append(
            _issue(
                "error",
                "invalid_llm_provider",
                (
                    "llm.provider måste vara "
                    "ollama eller geniex."
                ),
            )
        )

    geniex = settings.get(
        "geniex",
        {},
    )

    if provider == "geniex":
        if not _is_loopback_http(
            geniex.get(
                "base_url"
            )
        ):
            issues.append(
                _issue(
                    "error",
                    "geniex_not_loopback",
                    (
                        "GenieX måste använda ett lokalt "
                        "loopback-endpoint i denna profil."
                    ),
                )
            )

        if not str(
            geniex.get(
                "model",
                "",
            )
        ).strip():
            issues.append(
                _issue(
                    "error",
                    "geniex_model_missing",
                    "GenieX-modell saknas.",
                )
            )

    fallback = llm.get(
        "fallback",
        {},
    )
    fallback_enabled = bool(
        fallback.get(
            "enabled",
            False,
        )
    )

    if fallback_enabled:
        fallback_provider = str(
            fallback.get(
                "provider",
                "",
            )
        ).strip().lower()

        if (
            fallback_provider
            not in _ALLOWED_LLM_PROVIDERS
        ):
            issues.append(
                _issue(
                    "error",
                    "invalid_fallback_provider",
                    (
                        "Fallback-provider måste vara "
                        "ollama eller geniex."
                    ),
                )
            )

        if not str(
            fallback.get(
                "model",
                "",
            )
        ).strip():
            issues.append(
                _issue(
                    "error",
                    "fallback_model_missing",
                    (
                        "LLM-fallback är aktiverad men "
                        "reservmodell saknas."
                    ),
                )
            )

    health_aware = fallback.get(
        "health_aware",
        {},
    )

    if (
        health_aware.get(
            "enabled",
            False,
        )
        and not fallback_enabled
    ):
        issues.append(
            _issue(
                "warning",
                "health_aware_inactive",
                (
                    "Health-aware routing är förberedd men "
                    "fallback är avstängd."
                ),
            )
        )

    for key in (
        "failure_threshold",
        "recovery_success_threshold",
    ):
        try:
            value = int(
                health_aware.get(
                    key,
                    1,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            value = 0

        if value < 1:
            issues.append(
                _issue(
                    "error",
                    "invalid_health_threshold",
                    (
                        f"llm.fallback.health_aware.{key} "
                        "måste vara minst 1."
                    ),
                )
            )

    supervisor = settings.get(
        "geniex_supervisor",
        {},
    )

    if supervisor.get(
        "restart_enabled",
        False,
    ):
        command = supervisor.get(
            "restart_command",
            [],
        )

        if not _is_string_list(
            command
        ):
            issues.append(
                _issue(
                    "error",
                    "unsafe_restart_command",
                    (
                        "GenieX restart är aktiverad men "
                        "restart_command är inte en icke-tom "
                        "argumentlista."
                    ),
                )
            )

        if not supervisor.get(
            "enabled",
            False,
        ):
            issues.append(
                _issue(
                    "error",
                    "restart_without_supervisor",
                    (
                        "GenieX restart kan inte vara aktiv "
                        "när supervisorn är avstängd."
                    ),
                )
            )

    ventuno = settings.get(
        "ventuno",
        {},
    )

    if ventuno.get(
        "rpc_write_enabled",
        False,
    ):
        if not ventuno.get(
            "rpc_enabled",
            False,
        ):
            issues.append(
                _issue(
                    "error",
                    "rpc_write_without_rpc",
                    (
                        "STM32 RPC-skrivning kan inte vara "
                        "aktiv när RPC är avstängt."
                    ),
                )
            )

        methods = ventuno.get(
            "rpc_allowed_write_methods",
            [],
        )

        if not _is_string_list(
            methods
        ):
            issues.append(
                _issue(
                    "error",
                    "rpc_write_allowlist_missing",
                    (
                        "RPC-skrivning kräver en icke-tom "
                        "explicit write-allowlist."
                    ),
                )
            )

    if ventuno.get(
        "rpc_enabled",
        False,
    ):
        reads = ventuno.get(
            "rpc_allowed_read_methods",
            [],
        )

        if not _is_string_list(
            reads
        ):
            issues.append(
                _issue(
                    "warning",
                    "rpc_read_allowlist_empty",
                    (
                        "VENTUNO RPC är aktivt men ingen "
                        "read-only metod är allowlistad."
                    ),
                )
            )

    vision = settings.get(
        "vision",
        {},
    )

    if vision.get(
        "enabled",
        False,
    ):
        vision_provider = str(
            vision.get(
                "provider",
                "",
            )
        ).strip().lower()

        if (
            vision_provider
            not in _ALLOWED_VISION_PROVIDERS
        ):
            issues.append(
                _issue(
                    "error",
                    "invalid_vision_provider",
                    (
                        "vision.provider måste vara "
                        "ollama eller geniex."
                    ),
                )
            )

        if not str(
            vision.get(
                "model",
                "",
            )
        ).strip():
            issues.append(
                _issue(
                    "error",
                    "vision_model_missing",
                    (
                        "Vision är aktiverad men modell saknas."
                    ),
                )
            )

    voice = settings.get(
        "voice",
        {},
    )

    if (
        voice.get(
            "release_stt_before_model",
            False,
        )
        and not voice.get(
            "release_microphone_during_inference",
            False,
        )
    ):
        issues.append(
            _issue(
                "warning",
                "stt_release_without_mic_handoff",
                (
                    "STT-modellen frigörs före LLM men "
                    "mikrofon-handoff är inte aktiverad."
                ),
            )
        )

    if require_ventuno_profile:
        if not ventuno.get(
            "enabled",
            False,
        ):
            issues.append(
                _issue(
                    "error",
                    "ventuno_profile_disabled",
                    (
                        "VENTUNO runtime kräver "
                        "ventuno.enabled=true."
                    ),
                )
            )

        if provider != "geniex":
            issues.append(
                _issue(
                    "error",
                    "ventuno_requires_geniex",
                    (
                        "VENTUNO runtimeprofilen måste använda "
                        "GenieX som primär LLM-provider."
                    ),
                )
            )

        assistant = settings.get(
            "assistant",
            {},
        )
        platform = str(
            assistant.get(
                "current_platform",
                "",
            )
        ).lower()

        if "ventuno" not in platform:
            issues.append(
                _issue(
                    "warning",
                    "ventuno_platform_label",
                    (
                        "assistant.current_platform nämner inte "
                        "VENTUNO."
                    ),
                )
            )

    selfdev = settings.get(
        "selfdev",
        {},
    )

    if selfdev.get(
        "promotion_enabled",
        False,
    ) and not selfdev.get(
        "enabled",
        False,
    ):
        issues.append(
            _issue(
                "error",
                "selfdev_promotion_without_selfdev",
                (
                    "Selfdev-promotion kan inte vara aktiv "
                    "när selfdev är avstängt."
                ),
            )
        )

    if (
        selfdev.get(
            "enabled",
            False,
        )
        and not selfdev.get(
            "require_bubblewrap",
            True,
        )
    ):
        issues.append(
            _issue(
                "error",
                "selfdev_requires_bubblewrap",
                (
                    "Aktiverad selfdev kräver Bubblewrap; "
                    "osandboxad host-verifiering är inte tillåten."
                ),
            )
        )

    if not str(
        selfdev.get(
            "workspace_root",
            "",
        )
    ).strip():
        issues.append(
            _issue(
                "error",
                "selfdev_workspace_missing",
                "selfdev.workspace_root saknas.",
            )
        )

    memory = settings.get(
        "memory",
        {},
    )

    try:
        conflict_threshold = float(
            memory.get(
                "conflict_similarity_threshold",
                0.72,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        conflict_threshold = -1.0

    try:
        supersede_threshold = float(
            memory.get(
                "supersede_similarity_threshold",
                0.85,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        supersede_threshold = -1.0

    if not (
        0.0
        <= conflict_threshold
        <= 1.0
    ):
        issues.append(
            _issue(
                "error",
                "memory_conflict_threshold_invalid",
                (
                    "memory.conflict_similarity_threshold "
                    "måste vara mellan 0 och 1."
                ),
            )
        )

    if not (
        0.0
        <= supersede_threshold
        <= 1.0
    ):
        issues.append(
            _issue(
                "error",
                "memory_supersede_threshold_invalid",
                (
                    "memory.supersede_similarity_threshold "
                    "måste vara mellan 0 och 1."
                ),
            )
        )
    elif (
        0.0
        <= conflict_threshold
        <= 1.0
        and supersede_threshold
        < conflict_threshold
    ):
        issues.append(
            _issue(
                "error",
                "memory_supersede_threshold_too_low",
                (
                    "memory.supersede_similarity_threshold "
                    "får inte vara lägre än conflict-threshold."
                ),
            )
        )

    try:
        max_conflict_scan = int(
            memory.get(
                "max_conflict_scan",
                200,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        max_conflict_scan = 0

    if not (
        1
        <= max_conflict_scan
        <= 1000
    ):
        issues.append(
            _issue(
                "error",
                "memory_conflict_scan_invalid",
                (
                    "memory.max_conflict_scan måste vara "
                    "mellan 1 och 1000."
                ),
            )
        )

    try:
        stale_after_days = float(
            memory.get(
                "stale_after_days",
                0,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        stale_after_days = -1.0

    if not (
        0.0
        <= stale_after_days
        <= 36500.0
    ):
        issues.append(
            _issue(
                "error",
                "memory_stale_after_days_invalid",
                (
                    "memory.stale_after_days måste vara "
                    "mellan 0 och 36500."
                ),
            )
        )

    try:
        administration_limit = int(
            memory.get(
                "administration_limit",
                50,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        administration_limit = 0

    if not (
        1
        <= administration_limit
        <= 200
    ):
        issues.append(
            _issue(
                "error",
                "memory_administration_limit_invalid",
                (
                    "memory.administration_limit måste vara "
                    "mellan 1 och 200."
                ),
            )
        )

    try:
        stale_review_days = float(
            memory.get(
                "stale_review_days",
                365,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        stale_review_days = 0.0

    if not (
        1.0
        <= stale_review_days
        <= 36500.0
    ):
        issues.append(
            _issue(
                "error",
                "memory_stale_review_days_invalid",
                (
                    "memory.stale_review_days måste vara "
                    "mellan 1 och 36500."
                ),
            )
        )

    audit_logging = settings.get(
        "audit_logging",
        {},
    )
    audit_enabled = bool(
        audit_logging.get(
            "enabled",
            True,
        )
    )
    audit_required = bool(
        audit_logging.get(
            "require_for_writes",
            True,
        )
    )
    audit_path = str(
        audit_logging.get(
            "path",
            "",
        )
        or ""
    ).strip()

    if audit_required and not audit_enabled:
        issues.append(
            _issue(
                "error",
                "audit_required_but_disabled",
                (
                    "audit_logging.require_for_writes=true "
                    "kräver audit_logging.enabled=true."
                ),
            )
        )

    if audit_enabled and not audit_path:
        issues.append(
            _issue(
                "error",
                "audit_log_path_missing",
                (
                    "audit_logging.enabled=true kräver "
                    "audit_logging.path."
                ),
            )
        )

    try:
        audit_detail_limit = int(
            audit_logging.get(
                "max_detail_chars",
                200,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        audit_detail_limit = 0

    if not (
        32
        <= audit_detail_limit
        <= 2000
    ):
        issues.append(
            _issue(
                "error",
                "audit_detail_limit_invalid",
                (
                    "audit_logging.max_detail_chars måste "
                    "vara mellan 32 och 2000."
                ),
            )
        )

    try:
        audit_recent_limit = int(
            audit_logging.get(
                "recent_limit",
                20,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        audit_recent_limit = 0

    if not (
        1
        <= audit_recent_limit
        <= 50
    ):
        issues.append(
            _issue(
                "error",
                "audit_recent_limit_invalid",
                (
                    "audit_logging.recent_limit måste "
                    "vara mellan 1 och 50."
                ),
            )
        )

    error_logging = settings.get(
        "error_logging",
        {},
    )
    if error_logging.get(
        "enabled",
        True,
    ):
        error_path = str(
            error_logging.get(
                "path",
                "",
            )
            or ""
        ).strip()

        if not error_path:
            issues.append(
                _issue(
                    "error",
                    "error_log_path_missing",
                    (
                        "error_logging.enabled=true kräver "
                        "error_logging.path."
                    ),
                )
            )

        try:
            max_message_chars = int(
                error_logging.get(
                    "max_message_chars",
                    500,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            max_message_chars = 0

        if max_message_chars < 64:
            issues.append(
                _issue(
                    "error",
                    "error_log_message_limit_invalid",
                    (
                        "error_logging.max_message_chars "
                        "måste vara minst 64."
                    ),
                )
            )

        try:
            recent_limit = int(
                error_logging.get(
                    "recent_limit",
                    10,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            recent_limit = 0

        if not (
            1
            <= recent_limit
            <= 50
        ):
            issues.append(
                _issue(
                    "error",
                    "error_log_recent_limit_invalid",
                    (
                        "error_logging.recent_limit "
                        "måste vara mellan 1 och 50."
                    ),
                )
            )

    stability = settings.get(
        "stability_analysis",
        {},
    )
    stability_path = str(
        stability.get(
            "log_path",
            "",
        )
        or ""
    ).strip()

    if not stability_path:
        issues.append(
            _issue(
                "error",
                "stability_log_path_missing",
                "stability_analysis.log_path saknas.",
            )
        )

    try:
        stability_max_records = int(
            stability.get(
                "max_records",
                10_000,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        stability_max_records = 0

    if not (
        1
        <= stability_max_records
        <= 100_000
    ):
        issues.append(
            _issue(
                "error",
                "stability_max_records_invalid",
                (
                    "stability_analysis.max_records måste "
                    "vara mellan 1 och 100000."
                ),
            )
        )

    try:
        stability_target_hours = float(
            stability.get(
                "target_hours",
                72.0,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        stability_target_hours = 0.0

    if not (
        0.1
        <= stability_target_hours
        <= 1_000.0
    ):
        issues.append(
            _issue(
                "error",
                "stability_target_hours_invalid",
                (
                    "stability_analysis.target_hours måste "
                    "vara mellan 0.1 och 1000."
                ),
            )
        )

    try:
        trend_fraction = float(
            stability.get(
                "trend_fraction",
                0.25,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        trend_fraction = 0.0

    if not (
        0.1
        <= trend_fraction
        <= 0.5
    ):
        issues.append(
            _issue(
                "error",
                "stability_trend_fraction_invalid",
                (
                    "stability_analysis.trend_fraction måste "
                    "vara mellan 0.1 och 0.5."
                ),
            )
        )

    try:
        degradation_ratio = float(
            stability.get(
                "latency_degradation_ratio",
                1.25,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        degradation_ratio = 0.0

    if not (
        1.0
        <= degradation_ratio
        <= 10.0
    ):
        issues.append(
            _issue(
                "error",
                "stability_degradation_ratio_invalid",
                (
                    "stability_analysis.latency_degradation_ratio "
                    "måste vara mellan 1.0 och 10.0."
                ),
            )
        )

    diagnostics = settings.get(
        "diagnostics",
        {},
    )

    try:
        runtime_stale_seconds = float(
            diagnostics.get(
                "runtime_stale_seconds",
                30.0,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        runtime_stale_seconds = 0.0

    if not (
        1.0
        <= runtime_stale_seconds
        <= 3600.0
    ):
        issues.append(
            _issue(
                "error",
                "diagnostics_runtime_stale_invalid",
                (
                    "diagnostics.runtime_stale_seconds måste "
                    "vara mellan 1 och 3600."
                ),
            )
        )

    deployment_lock = settings.get(
        "deployment_lock",
        {},
    )
    if deployment_lock.get(
        "required",
        False,
    ) and not str(
        deployment_lock.get(
            "lock_path",
            "",
        )
    ).strip():
        issues.append(
            _issue(
                "error",
                "deployment_lock_path_missing",
                (
                    "deployment_lock.required=true kräver "
                    "deployment_lock.lock_path."
                ),
            )
        )

    for section, key in (
        (
            "geniex_supervisor",
            "state_path",
        ),
        (
            "health",
            "state_path",
        ),
    ):
        raw = str(
            settings.get(
                section,
                {},
            ).get(
                key,
                "",
            )
        ).strip()

        if not raw:
            issues.append(
                _issue(
                    "error",
                    "state_path_missing",
                    f"{section}.{key} saknas.",
                )
            )
        elif Path(
            raw
        ).name in {
            "",
            ".",
            "..",
        }:
            issues.append(
                _issue(
                    "error",
                    "invalid_state_path",
                    f"{section}.{key} är ogiltig.",
                )
            )

    errors = [
        item
        for item in issues
        if item["level"]
        == "error"
    ]
    warnings = [
        item
        for item in issues
        if item["level"]
        == "warning"
    ]

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def require_valid_settings(
    settings,
    *,
    require_ventuno_profile=False,
):
    result = validate_settings(
        settings,
        require_ventuno_profile=(
            require_ventuno_profile
        ),
    )

    if result["valid"]:
        return result

    details = "; ".join(
        item["message"]
        for item in result[
            "errors"
        ]
    )
    raise ValueError(
        "Ogiltig MyAI-konfiguration: "
        + details
    )
