# SPDX-License-Identifier: MIT
import pytest

from services.config import ConfigurationError
from services.translation_engines import ENGINES, config, estimate_cost


def test_default_and_optional_engine(monkeypatch):
    assert ENGINES == ("translator", "llm")
    assert config().engine == "translator"
    monkeypatch.delenv("TRANSLATION_MODEL_NAME", raising=False)
    with pytest.raises(ConfigurationError, match="TRANSLATION_MODEL_NAME"):
        config("llm")
    monkeypatch.setenv("TRANSLATION_MODEL_NAME", "test")
    monkeypatch.setenv("FOUNDRY_MODEL_ENDPOINT", "https://example.test/openai/v1/")
    monkeypatch.delenv("TRANSLATION_REASONING_EFFORT", raising=False)
    assert config("llm").reasoning_effort == "low"
    assert config("llm").deployment_name == "test"


def test_cost_requires_actual_usage_and_configured_rates(monkeypatch):
    monkeypatch.setenv("TRANSLATOR_CHARACTER_RATE", "")
    assert estimate_cost(config(), characters=10_000) is None
    monkeypatch.setenv("TRANSLATOR_CHARACTER_RATE", "12")
    assert estimate_cost(config()) is None
    assert estimate_cost(config(), characters=250_000) == 3
    monkeypatch.setenv("TRANSLATION_MODEL_NAME", "test")
    monkeypatch.setenv("FOUNDRY_MODEL_ENDPOINT", "https://example.test/openai/v1/")
    monkeypatch.setenv("LLM_INPUT_RATE", "2")
    monkeypatch.setenv("LLM_OUTPUT_RATE", "4")
    assert estimate_cost(config("llm"), input_tokens=100_000, output_tokens=200_000) == 1
