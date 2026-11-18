# SPDX-License-Identifier: MIT
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services import local_translation, translation_engines
from services.config import ExternalServiceError


def test_office_request_submits_glossary(monkeypatch):
    request = Mock(return_value=SimpleNamespace(content=b"PK result", headers={}))
    monkeypatch.setattr(local_translation, "request", request)
    result, usage = local_translation.translate_document(
        b"PK source", "brief.docx", b"event\tatelier\n", "en", "fr", "job",
        engine=translation_engines.config("translator"),
    )
    assert result == b"PK result"
    assert usage["glossaryApplied"]
    assert usage["charactersCharged"] is None
    _, kwargs = request.call_args
    assert kwargs["files"]["glossary"][1] == b"event\tatelier\n"
    assert kwargs["params"]["sourceLanguage"] == "en"
    assert kwargs["params"]["targetLanguage"] == "fr"


@pytest.mark.parametrize("meter", [None, "0", "7"])
def test_text_meter_is_distinct_from_input_length(monkeypatch, meter):
    headers = {"X-Metered-Usage": meter} if meter is not None else {}
    response = Mock(headers=headers, **{"json.return_value": [{"translations": [{"to": "fr", "text": "Bonjour"}]}]})
    monkeypatch.setattr(local_translation, "request", Mock(return_value=response))
    result, usage = local_translation.translate_segments(
        [{"text": "Hello", "location": "p1"}], "en", "fr", "job",
    )
    assert result["segments"] == [{"text": "Bonjour", "location": "p1"}]
    assert usage["charactersSubmitted"] == 5
    assert usage["charactersCharged"] == (int(meter) if meter is not None else None)


def test_invalid_text_result_fails_closed(monkeypatch):
    response = Mock(**{"json.return_value": [{"translations": [{"to": "de", "text": "Hallo"}]}]})
    monkeypatch.setattr(local_translation, "request", Mock(return_value=response))
    with pytest.raises(ExternalServiceError, match="unexpected"):
        local_translation.translate_segments([{"text": "Hello"}], "en", "fr", "job")


def test_office_size_limit_is_checked_before_network(monkeypatch):
    request = Mock()
    monkeypatch.setattr(local_translation, "request", request)
    with pytest.raises(ValueError, match="10 MB"):
        local_translation.translate_document(
            b"x" * (10 * 1024 * 1024 + 1), "brief.docx", b"", "en", "fr", "job",
            engine=translation_engines.config("translator"),
        )
    request.assert_not_called()
