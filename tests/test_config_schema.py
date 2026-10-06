import json
from copy import deepcopy

import pytest

from core.config import (
    DEFAULT_SETTINGS,
    load_settings,
    load_settings_with_metadata,
)
from core.config_schema import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    compare_config_profiles,
    find_unknown_config_keys,
    migrate_config_document,
)


def test_legacy_unversioned_config_migrates_only_in_memory(
    tmp_path,
):
    path = (
        tmp_path
        / "legacy.json"
    )
    original = {
        "ollama": {
            "model": "legacy-model",
        }
    }
    path.write_text(
        json.dumps(
            original
        ),
        encoding="utf-8",
    )
    before = path.read_bytes()

    loaded = load_settings_with_metadata(
        path
    )

    assert loaded[
        "settings"
    ][
        "schema_version"
    ] == CURRENT_CONFIG_SCHEMA_VERSION
    assert loaded[
        "settings"
    ][
        "ollama"
    ][
        "model"
    ] == "legacy-model"
    assert loaded[
        "metadata"
    ][
        "source_version"
    ] == 0
    assert loaded[
        "metadata"
    ][
        "migration_changed"
    ] is True
    assert path.read_bytes() == before


def test_future_config_schema_is_rejected(
    tmp_path,
):
    path = (
        tmp_path
        / "future.json"
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": (
                    CURRENT_CONFIG_SCHEMA_VERSION
                    + 1
                )
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="nyare",
    ):
        load_settings(
            path
        )


def test_non_integer_schema_version_is_rejected():
    with pytest.raises(
        ValueError,
        match="heltal",
    ):
        migrate_config_document(
            {
                "schema_version": "1",
            }
        )


def test_unknown_nested_config_key_is_detected():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "voice"
    ][
        "stt_langauge"
    ] = "sv"

    unknown = find_unknown_config_keys(
        settings,
        DEFAULT_SETTINGS,
    )

    assert unknown == [
        "voice.stt_langauge",
    ]


def test_profile_comparison_reports_effective_differences():
    left = deepcopy(
        DEFAULT_SETTINGS
    )
    right = deepcopy(
        DEFAULT_SETTINGS
    )
    right[
        "llm"
    ][
        "provider"
    ] = "geniex"

    result = compare_config_profiles(
        left,
        right,
    )

    assert result[
        "difference_count"
    ] == 1
    assert result[
        "differences"
    ][
        0
    ][
        "path"
    ] == "llm.provider"


def test_profile_comparison_redacts_sensitive_values():
    left = deepcopy(
        DEFAULT_SETTINGS
    )
    right = deepcopy(
        DEFAULT_SETTINGS
    )
    left[
        "geniex"
    ][
        "api_key"
    ] = "secret-left"
    right[
        "geniex"
    ][
        "api_key"
    ] = "secret-right"

    result = compare_config_profiles(
        left,
        right,
    )
    item = next(
        value
        for value in result[
            "differences"
        ]
        if value[
            "path"
        ]
        == "geniex.api_key"
    )

    assert item[
        "left"
    ] == "<redacted>"
    assert item[
        "right"
    ] == "<redacted>"
    assert "secret-left" not in str(
        result
    )
    assert "secret-right" not in str(
        result
    )


def test_schema_v1_gpu_field_migrates_to_compute_accelerator():
    migrated = migrate_config_document(
        {
            "schema_version": 1,
            "assistant": {
                "gpu": "Legacy accelerator",
            },
        }
    )

    assert migrated[
        "effective_version"
    ] == 2
    assert migrated[
        "document"
    ][
        "assistant"
    ][
        "compute_accelerator"
    ] == "Legacy accelerator"
    assert (
        "gpu"
        not in migrated[
            "document"
        ][
            "assistant"
        ]
    )
