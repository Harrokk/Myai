from copy import deepcopy


CURRENT_CONFIG_SCHEMA_VERSION = 1


_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
)


def migrate_config_document(
    document,
):
    if not isinstance(
        document,
        dict,
    ):
        raise ValueError(
            "Konfigurationsdokumentet måste vara ett JSON-objekt."
        )

    result = deepcopy(
        document
    )
    raw_version = result.get(
        "schema_version"
    )
    steps = []

    if raw_version is None:
        source_version = 0
    else:
        if isinstance(
            raw_version,
            bool,
        ):
            raise ValueError(
                "schema_version måste vara ett heltal."
            )

        try:
            source_version = int(
                raw_version
            )
        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                "schema_version måste vara ett heltal."
            ) from error

        if str(
            raw_version
        ).strip() != str(
            source_version
        ):
            raise ValueError(
                "schema_version måste vara ett heltal."
            )

    if source_version < 0:
        raise ValueError(
            "schema_version får inte vara negativ."
        )

    if (
        source_version
        > CURRENT_CONFIG_SCHEMA_VERSION
    ):
        raise ValueError(
            (
                "Konfigurationens schema_version är nyare "
                "än denna MyAI-version stöder."
            )
        )

    version = source_version

    if version == 0:
        result[
            "schema_version"
        ] = 1
        steps.append(
            {
                "from_version": 0,
                "to_version": 1,
                "description": (
                    "Lägg till schema_version=1; "
                    "övriga värden lämnas oförändrade."
                ),
            }
        )
        version = 1

    if (
        version
        != CURRENT_CONFIG_SCHEMA_VERSION
    ):
        raise ValueError(
            "Ingen säker migrationsväg finns för konfigurationen."
        )

    return {
        "document": result,
        "source_version": source_version,
        "effective_version": version,
        "changed": bool(
            steps
        ),
        "steps": steps,
    }


def find_unknown_config_keys(
    settings,
    schema,
    *,
    prefix="",
):
    if not isinstance(
        settings,
        dict,
    ) or not isinstance(
        schema,
        dict,
    ):
        return []

    unknown = []

    for key, value in settings.items():
        path = (
            f"{prefix}.{key}"
            if prefix
            else str(
                key
            )
        )

        if key not in schema:
            unknown.append(
                path
            )
            continue

        expected = schema[
            key
        ]

        if (
            isinstance(
                value,
                dict,
            )
            and isinstance(
                expected,
                dict,
            )
        ):
            unknown.extend(
                find_unknown_config_keys(
                    value,
                    expected,
                    prefix=path,
                )
            )

    return sorted(
        set(
            unknown
        )
    )


def _flatten(
    value,
    *,
    prefix="",
):
    if isinstance(
        value,
        dict,
    ):
        result = {}

        for key in sorted(
            value
        ):
            path = (
                f"{prefix}.{key}"
                if prefix
                else str(
                    key
                )
            )
            result.update(
                _flatten(
                    value[
                        key
                    ],
                    prefix=path,
                )
            )

        return result

    return {
        prefix: value
    }


def _safe_diff_value(
    path,
    value,
):
    normalized = str(
        path
        or ""
    ).lower()

    if any(
        part in normalized
        for part in _SENSITIVE_KEY_PARTS
    ):
        return "<redacted>"

    return deepcopy(
        value
    )


def compare_config_profiles(
    left,
    right,
):
    left_flat = _flatten(
        left
    )
    right_flat = _flatten(
        right
    )
    paths = sorted(
        set(
            left_flat
        )
        | set(
            right_flat
        )
    )
    differences = []

    for path in paths:
        left_value = left_flat.get(
            path,
            "<missing>",
        )
        right_value = right_flat.get(
            path,
            "<missing>",
        )

        if left_value == right_value:
            continue

        differences.append(
            {
                "path": path,
                "left": _safe_diff_value(
                    path,
                    left_value,
                ),
                "right": _safe_diff_value(
                    path,
                    right_value,
                ),
            }
        )

    return {
        "difference_count": len(
            differences
        ),
        "differences": differences,
    }
