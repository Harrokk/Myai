from pathlib import Path
from urllib.parse import urlparse


_ALLOWED_LLM_PROVIDERS = {
    "ollama",
    "geniex",
}
_ALLOWED_VISION_PROVIDERS = {
    "ollama",
    "geniex",
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
