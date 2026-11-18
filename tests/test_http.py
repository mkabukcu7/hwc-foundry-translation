import asyncio
import base64
import io
import json
from unittest.mock import AsyncMock
from zipfile import ZipFile

import azure.functions as func

from services import jobs_table, storage
from tests.helpers import indexed_functions
from tests.test_intake import principal


def function(name):
    return indexed_functions()[name].get_user_function()


def response_body(response):
    async def collect():
        return b"".join([chunk async for chunk in response.body_iterator])

    return asyncio.run(collect())


def test_submit_returns_only_job_metadata_and_starts_workflow(monkeypatch):
    rows, blobs = [], []
    monkeypatch.setattr(jobs_table, "create", rows.append)
    monkeypatch.setattr(storage, "put", lambda *args: blobs.append(args))
    client = AsyncMock()
    content = b"document content must not enter durable history"
    request = func.HttpRequest("POST", "https://unit/api/jobs", headers={
        **principal(), "content-type": "application/json",
    }, body=json.dumps({
        "fileName": "brief.pdf", "contentBase64": base64.b64encode(content).decode(), "targetLanguages": ["en"],
    }).encode())
    # Unwrap the host's Durable client-binding middleware, supplying an AsyncMock directly.
    response = asyncio.run(function("post_jobs").__wrapped__(request, client))
    assert response.status_code == 202
    payload = json.loads(response.body)
    assert set(payload) == {"jobId", "statusUrl"}
    assert rows[0]["ownerId"] == "user-a"
    assert blobs[0][2] == content
    client.start_new.assert_awaited_once()
    assert "content" not in json.dumps(client.start_new.call_args.args)


def test_job_owner_is_enforced_before_reading_report(monkeypatch):
    job_id = "a" * 32
    monkeypatch.setattr(jobs_table, "get", lambda _: {"ownerId": "another-user", "jobId": job_id})
    request = func.HttpRequest("GET", f"https://unit/api/jobs/{job_id}/report", headers=principal(),
                               route_params={"id": job_id}, body=b"")
    response = asyncio.run(function("get_report")(request))
    assert response.status_code == 404


def test_report_not_ready(monkeypatch):
    job_id = "a" * 32
    monkeypatch.setattr(jobs_table, "get", lambda _: {"ownerId": "user-a", "jobId": job_id})
    request = func.HttpRequest("GET", f"https://unit/api/jobs/{job_id}/report", headers=principal(),
                               route_params={"id": job_id}, body=b"")
    assert asyncio.run(function("get_report")(request)).status_code == 409


def test_result_by_language_and_bundle(monkeypatch):
    job_id = "a" * 32
    files = {"fr/brief.xlsx": b"French sheet", "de/brief.xlsx": b"German sheet"}
    monkeypatch.setattr(jobs_table, "get", lambda _: {
        "ownerId": "user-a", "jobId": job_id, "status": "complete", "fileName": "brief.xlsx",
        "resultPath": "fr/brief.xlsx", "resultContainer": f"target-{job_id}",
    })
    monkeypatch.setattr(storage, "get_json", lambda *_: {"outputs": [
        {"language": path.split("/")[0], "path": path} for path in files
    ]})
    class Blob:
        def __init__(self, path):
            self.size = len(files[path])
        def chunks(self):
            yield files[self.path]
        path = None

    def download_blob(_container, path):
        blob = Blob(path)
        blob.path = path
        return blob

    monkeypatch.setattr(storage, "download", download_blob)
    monkeypatch.setattr(storage, "blob_size", lambda _container, path: len(files[path]))

    def download(params=None):
        request = func.HttpRequest("GET", "https://unit/result", headers=principal(),
                                   route_params={"id": job_id}, params=params, body=b"")
        return asyncio.run(function("get_result")(request))

    selected = download({"lang": "fr"})
    assert response_body(selected) == files["fr/brief.xlsx"]
    assert selected.media_type.endswith("spreadsheetml.sheet")
    assert download({"lang": "es"}).status_code == 404
    bundled = download()
    assert bundled.media_type == "application/zip"
    assert bundled.body_iterator is not None
    with ZipFile(io.BytesIO(response_body(bundled))) as archive:
        assert {name: archive.read(name) for name in archive.namelist()} == files


def test_missing_connections_are_explicit_and_arbitrary_errors_are_redacted(monkeypatch):
    from services.config import ConfigurationError
    job_id = "a" * 32
    request = func.HttpRequest("GET", f"https://unit/api/jobs/{job_id}", headers=principal(),
                               route_params={"id": job_id}, body=b"")

    def missing(_):
        raise ConfigurationError("Missing configuration: STORAGE_TABLE_ENDPOINT")

    monkeypatch.setattr(jobs_table, "get", missing)
    result = asyncio.run(function("get_job")(request))
    assert result.status_code == 503 and b"STORAGE_TABLE_ENDPOINT" in result.body

    def upstream(_):
        raise RuntimeError("secret document excerpt or raw upstream token")

    monkeypatch.setattr(jobs_table, "get", upstream)
    result = asyncio.run(function("get_job")(request))
    assert result.status_code == 503 and b"secret" not in result.body
