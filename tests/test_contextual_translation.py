import pytest

from services import contextual_translation
from services.config import ExternalServiceError


class CharacterEncoding:
    @staticmethod
    def encode(text):
        return list(text)


def invoke_payloads(monkeypatch, response_factory):
    seen = []

    def invoke(payload, _prompt, job_id, **options):
        seen.append((payload, job_id))
        return response_factory(payload), {
            "model": "test-deployment", "responseModel": "test-deployment",
            "inputTokens": 12, "outputTokens": 8, "durationSeconds": 0.1,
        }

    monkeypatch.setattr(contextual_translation, "invoke_translation_model", invoke)
    monkeypatch.setattr(contextual_translation, "encoding", lambda: CharacterEncoding())
    return seen


def test_direct_translation_sends_context_and_validates_segment_ids(monkeypatch):
    seen = invoke_payloads(monkeypatch, lambda payload: {
        "translations": [{
            "id": segment["id"], "text": f"Translated {segment['source']}",
            "decision": "translated", "rationale": "Glossary applied",
        } for segment in payload["segments"]],
    })
    monkeypatch.setenv("TRANSLATION_CONTEXT_TOKENS", "3000")
    segments = [
        {"text": "Le webinaire commence.", "role": "paragraph", "location": "paragraph:1"},
        {"text": "Participez au webinaire.", "role": "paragraph", "location": "paragraph:2"},
        {"text": "Fine.", "role": "paragraph", "location": "paragraph:3"},
    ]
    terms = [{"term": "webinaire", "type": "term", "action": "map", "target": "webinar"}]

    result, usage = contextual_translation.translate(
        segments, "fr", "en", terms, "job-1",
    )

    payload, job_id = seen[0]
    assert job_id == "job-1"
    assert payload["sourceLanguage"] == "fr" and payload["targetLanguage"] == "en"
    assert payload["segments"][1]["location"] == "paragraph:2"
    assert any(item["context"] == "Le webinaire commence." for item in payload["context"]["documentContext"])
    assert payload["context"]["terms"] == terms
    assert result["segments"][1]["text"] == "Translated Participez au webinaire."
    assert usage["model"] == "test-deployment" and usage["inputTokens"] == 12
    assert usage["reasoningTokens"] is None


def test_translation_passes_selected_model_and_reasoning_to_responses(monkeypatch):
    calls = []

    def invoke(payload, _prompt, job_id, **options):
        calls.append((job_id, options))
        return {"translations": [{
            "id": item["id"], "text": "Translation", "decision": "translated", "rationale": "Direct translation",
        } for item in payload["segments"]]}, {
            "model": options["model"], "responseModel": options["model"],
            "inputTokens": 2, "outputTokens": 3, "reasoningTokens": 1, "durationSeconds": .1,
        }

    monkeypatch.setattr(contextual_translation, "invoke_translation_model", invoke)
    monkeypatch.setattr(contextual_translation, "encoding", lambda: CharacterEncoding())
    _, usage = contextual_translation.translate(
        [{"text": "source"}], "it", "en", [], "job-engine",
        model="test-deployment", reasoning_effort="medium",
    )
    assert calls == [("job-engine", {"model": "test-deployment", "reasoning_effort": "medium"})]
    assert usage["reasoningTokens"] == 1


@pytest.mark.parametrize("response", [
    {"translations": [{"id": "segment-2", "text": "x", "decision": "translated", "rationale": ""}]},
    {"translations": [{"id": "segment-1", "text": "x", "decision": "translated"}]},
])
def test_rejects_missing_or_invalid_model_results(monkeypatch, response):
    invoke_payloads(monkeypatch, lambda _payload: response)

    with pytest.raises(ExternalServiceError):
        contextual_translation.translate(
            [{"text": "source"}], "it", "en", [], "job-3",
        )


def test_rejects_empty_translation_text(monkeypatch):
    invoke_payloads(monkeypatch, lambda _payload: {"translations": [
        {"id": "segment-1", "text": "  ", "decision": "translated", "rationale": ""},
    ]})

    with pytest.raises(ExternalServiceError, match="empty text"):
        contextual_translation.translate(
            [{"text": "source"}], "it", "en", [], "job-5",
        )
