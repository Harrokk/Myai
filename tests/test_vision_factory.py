from copy import deepcopy

import pytest

from core.config import DEFAULT_SETTINGS
from core.geniex_vision_client import GenieXVisionClient
from core.vision_client import VisionClient
from core.vision_factory import build_vision_client


def test_vision_factory_keeps_ollama_default():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["vision"]["enabled"] = True
    settings["vision"]["model"] = "llava"

    client = build_vision_client(
        settings
    )

    assert isinstance(
        client,
        VisionClient,
    )


def test_vision_factory_builds_geniex_client():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["vision"].update(
        {
            "enabled": True,
            "provider": "geniex",
            "url": "http://127.0.0.1:18181/v1",
            "model": "qualcomm/Qwen3-VL-4B-Instruct",
        }
    )

    client = build_vision_client(
        settings
    )

    assert isinstance(
        client,
        GenieXVisionClient,
    )
    assert client.enabled is True
    assert client.model == (
        "qualcomm/Qwen3-VL-4B-Instruct"
    )


def test_vision_factory_rejects_unknown_provider():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["vision"]["provider"] = "unknown"

    with pytest.raises(
        ValueError,
        match="Okänd vision-provider",
    ):
        build_vision_client(
            settings
        )
