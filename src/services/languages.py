# SPDX-License-Identifier: MIT
import os

from services.config import ConfigurationError

DEFAULT = "en,fr,de,es,it,pt,pt-PT,nl,pl,sv,da,nb,fi"
LATIN_CODES = frozenset(DEFAULT.split(",")) | {
    "af", "bs", "ca", "cs", "cy", "et", "eu", "fil", "ga", "gl", "hr", "hu", "id", "is",
    "lt", "lv", "ms", "mt", "ro", "sk", "sl", "sq", "sr-Latn", "sw", "tr", "vi",
}


def enabled():
    codes = tuple(dict.fromkeys(code.strip() for code in os.getenv("SUPPORTED_LANGUAGES", DEFAULT).split(",")))
    if not codes or any(code not in LATIN_CODES for code in codes):
        raise ConfigurationError("SUPPORTED_LANGUAGES must contain approved Latin-script Translator codes")
    return codes


def validate(code):
    codes = enabled()
    if not isinstance(code, str) or code not in codes:
        raise ValueError(f"Language '{code}' is not enabled in phase 1. Enabled: {','.join(codes)}.")
    return code


def targets(values, source=None):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 10:
        raise ValueError("Supply between 1 and 10 target languages.")
    result = list(dict.fromkeys(validate(code) for code in values))
    result = [code for code in result if code != source]
    if not result:
        raise ValueError("Supply a target language different from the source language.")
    return result
