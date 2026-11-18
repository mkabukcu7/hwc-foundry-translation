# SPDX-License-Identifier: MIT
import os
from dataclasses import dataclass
from math import isfinite

from services.config import ConfigurationError, required

ENGINES = ("translator", "llm")


@dataclass(frozen=True)
class EngineConfig:
    engine: str
    model_name: str
    deployment_name: str | None = None
    reasoning_effort: str | None = None


def config(engine="translator"):
    if engine == "translator":
        return EngineConfig(engine, "Azure Translator NMT")
    if engine != "llm":
        raise ConfigurationError("Engine must be translator or llm")
    deployment = required("TRANSLATION_MODEL_NAME")
    required("FOUNDRY_MODEL_ENDPOINT")
    effort = os.getenv("TRANSLATION_REASONING_EFFORT", "").strip() or "low"
    if effort not in {"none", "low", "medium", "high"}:
        raise ConfigurationError("TRANSLATION_REASONING_EFFORT must be none, low, medium, or high")
    return EngineConfig(engine, deployment, deployment, effort)


def _rate(name):
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        rate = float(value)
    except ValueError:
        raise ConfigurationError(f"{name} must be a finite nonnegative number") from None
    if not isfinite(rate) or rate < 0:
        raise ConfigurationError(f"{name} must be a finite nonnegative number")
    return rate


def estimate_cost(engine, *, input_tokens=None, output_tokens=None, characters=None):
    if engine.engine == "translator":
        rate = _rate("TRANSLATOR_CHARACTER_RATE")
        return characters * rate / 1_000_000 if rate is not None and characters is not None else None
    input_rate, output_rate = _rate("LLM_INPUT_RATE"), _rate("LLM_OUTPUT_RATE")
    if any(value is None for value in (input_rate, output_rate, input_tokens, output_tokens)):
        return None
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
