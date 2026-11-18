# SPDX-License-Identifier: MIT
from datetime import timedelta

from azure.durable_functions import Blueprint, DurableOrchestrationContext, RetryOptions

from services.translator_client import TERMINAL

bp = Blueprint()


def run(context: DurableOrchestrationContext):
    job = context.get_input()
    retry = RetryOptions(5000, 3)
    try:
        yield context.call_activity_with_retry("precheck", retry, job)
        prepared = yield context.call_activity_with_retry("prepare", retry, job)
        job = {**job, **prepared}
        outputs = []
        for language in job["targetLanguages"]:
            target = {**job, "targetLanguage": language}
            # Avoid automatic retries around a non-idempotent POST.
            operation = yield context.call_activity("translate_start", target)
            target = {**target, **operation}
            if not target.get("textTranslation"):
                result = yield from wait_for_batch(context, retry, target)
                target = {**target, "usage": result.get("usage", {})}
            outputs.append((yield context.call_activity_with_retry("reconstruct", retry, target)))
        job = {**job, "outputs": outputs}
        routed = yield context.call_activity_with_retry("route", retry, job)
        yield context.call_activity_with_retry("notify", retry, {**job, "finalStatus": routed["status"]})
        return {"jobId": job["jobId"], "status": routed["status"]}
    except Exception:
        # Only metadata goes into orchestration failure history; diagnostics are correlated by jobId.
        yield context.call_activity("record_failure", {"jobId": job["jobId"]})
        raise


def wait_for_batch(context, retry, job):
    deadline = context.current_utc_datetime + timedelta(minutes=30)
    delay = 2
    while context.current_utc_datetime < deadline:
        status = yield context.call_activity_with_retry("translate_poll", retry, job)
        if context.current_utc_datetime > deadline:
            break
        if status["status"] in TERMINAL:
            if status["status"] != "Succeeded":
                raise RuntimeError("Translation did not succeed")
            return status
        now = context.current_utc_datetime
        if now >= deadline:
            break
        yield context.create_timer(min(now + timedelta(seconds=delay), deadline))
        delay = min(delay * 2, 30)
    raise TimeoutError("Translation exceeded 30 minutes")


@bp.orchestration_trigger(context_name="context")
def translation_orchestrator(context: DurableOrchestrationContext):
    return (yield from run(context))
