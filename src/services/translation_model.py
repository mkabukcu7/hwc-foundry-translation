# SPDX-License-Identifier: MIT
import json
import os
from pathlib import Path
from time import perf_counter

from azure.identity import get_bearer_token_provider
from openai import OpenAI

from services.config import ExternalServiceError, credential, integer, required

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "contextual_translation.schema.json"


def invoke_translation_model(data, instructions, job_id, *, model=None, reasoning_effort=None):
    model = model or required("TRANSLATION_MODEL_NAME")
    effort = reasoning_effort or os.getenv("TRANSLATION_REASONING_EFFORT", "low")
    started = perf_counter()
    with OpenAI(
        base_url=required("FOUNDRY_MODEL_ENDPOINT"),
        api_key=get_bearer_token_provider(credential(), "https://ai.azure.com/.default"),
        timeout=integer("TRANSLATION_TIMEOUT_SECONDS", 180),
        max_retries=0,
    ) as client:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=json.dumps(data, ensure_ascii=False),
            reasoning={"effort": effort},
            text={"format": {"type": "json_schema", "name": "translation",
                             "schema": json.loads(SCHEMA.read_text(encoding="utf-8")), "strict": True}},
            max_output_tokens=integer("TRANSLATION_MAX_OUTPUT_TOKENS", 8192),
            metadata={"jobId": job_id},
            extra_headers={"x-ms-client-request-id": job_id},
            store=False,
        )
    if response.status != "completed" or not response.output_text:
        raise ExternalServiceError(f"Translation model did not return a complete response; jobId={job_id}")
    try:
        result = json.loads(response.output_text)
    except ValueError:
        raise ExternalServiceError(f"Translation model returned invalid JSON; jobId={job_id}") from None
    usage = response.usage
    details = usage.output_tokens_details if usage else None
    return result, {
        "model": model,
        "responseModel": response.model,
        "inputTokens": usage.input_tokens if usage else None,
        "outputTokens": usage.output_tokens if usage else None,
        "reasoningTokens": details.reasoning_tokens if details else None,
        "durationSeconds": perf_counter() - started,
    }
