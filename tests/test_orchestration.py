from datetime import datetime, timedelta, timezone

import pytest

from orchestrator import run


class Context:
    current_utc_datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def get_input(self):
        return {"jobId": "a" * 32, "targetLanguages": ["en"]}

    def call_activity_with_retry(self, name, retry, data):
        return name, data

    def call_activity(self, name, data):
        return name, data

    def create_timer(self, at):
        return "timer", at


def advance(generator, value=None):
    return generator.send(value)


def test_success_and_durable_backoff():
    ctx = Context()
    iterator = run(ctx)
    assert next(iterator)[0] == "precheck"
    assert advance(iterator, {})[0] == "prepare"
    assert advance(iterator, {"sourceLanguage": "de"}) == (
        "translate_start", {"jobId": "a" * 32, "sourceLanguage": "de",
                            "targetLanguages": ["en"], "targetLanguage": "en"},
    )
    assert advance(iterator, {"operationUrl": "https://unit"})[0] == "translate_poll"
    delays = []
    for _ in range(6):
        timer = advance(iterator, {"status": "Running"})
        assert timer[0] == "timer"
        delays.append((timer[1] - ctx.current_utc_datetime).total_seconds())
        ctx.current_utc_datetime = timer[1]
        assert advance(iterator)[0] == "translate_poll"
    assert delays == [2, 4, 8, 16, 30, 30]
    assert advance(iterator, {"status": "Succeeded"})[0] == "reconstruct"
    assert advance(iterator, {})[0] == "route"
    assert advance(iterator, {"status": "complete"})[0] == "notify"
    with pytest.raises(StopIteration) as done:
        advance(iterator, {})
    assert done.value.value["status"] == "complete"


def test_timeout_stops_polling_at_30_minutes_and_persists_failure():
    ctx = Context()
    iterator = run(ctx)
    next(iterator)
    advance(iterator, {})
    advance(iterator, {})
    advance(iterator, {"operationUrl": "https://unit"})
    start = ctx.current_utc_datetime
    while True:
        timer = advance(iterator, {"status": "Running"})
        ctx.current_utc_datetime = timer[1]
        operation = advance(iterator)
        if operation[0] == "record_failure":
            break
        assert operation[0] == "translate_poll"
    assert (ctx.current_utc_datetime - start).total_seconds() == 1800
    with pytest.raises(TimeoutError):
        advance(iterator, {})


def test_success_reported_after_deadline_is_not_accepted():
    ctx = Context()
    iterator = run(ctx)
    next(iterator)
    advance(iterator, {})
    advance(iterator, {})
    advance(iterator, {"operationUrl": "https://unit"})
    ctx.current_utc_datetime += timedelta(minutes=31)
    assert advance(iterator, {"status": "Succeeded"})[0] == "record_failure"
    with pytest.raises(TimeoutError):
        advance(iterator, {})
