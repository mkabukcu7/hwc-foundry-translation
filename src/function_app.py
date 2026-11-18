# SPDX-License-Identifier: MIT
import asyncio
import json
import logging
import time
import uuid
from functools import wraps
from pathlib import PurePosixPath
from urllib.parse import quote

import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError
from azure.durable_functions import DFApp
from azurefunctions.extensions.http.fastapi import JSONResponse, Request, Response, StreamingResponse
from zipstream import ZipStream

from activities import notify, precheck, prepare, route, translate
from orchestrator import bp
from services import auth, intake, jobs_table, retention, storage
from services.config import ConfigurationError, ExternalServiceError
from services.local_translation import DOCUMENT_TYPES

app = DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)  # Entra Easy Auth, not function keys.
app.register_functions(bp)
log = logging.getLogger("translation")


def response(body, status=200):
    return JSONResponse(body, status_code=status)


def request_url(req) -> str:
    url = req.url
    if isinstance(url, str):
        return url
    return str(url)


def route_id(req) -> str:
    route_params = getattr(req, "route_params", None)
    if route_params and route_params.get("id"):
        return route_params["id"]
    path = request_url(req).split("?", 1)[0].rstrip("/")
    return path.rsplit("/", 1)[-1]


def query_param(req, name):
    if hasattr(req, "query_params"):
        return req.query_params.get(name)
    return getattr(req, "params", {}).get(name)


def base_url(req) -> str:
    return request_url(req).split("?", 1)[0]

async def read_body(req: Request, limit: int, error: str) -> bytearray:
    if hasattr(req, "get_body"):
        data = req.get_body()
        if len(data) > limit:
            raise intake.IntakeError(error, 413)
        return data
    data = bytearray()
    async for chunk in req.stream():
        if len(data) + len(chunk) > limit:
            raise intake.IntakeError(error, 413)
        data.extend(chunk)
    return data


def http_errors(handler):
    @wraps(handler)
    async def wrapped(*args, **kwargs):
        try:
            return await handler(*args, **kwargs)
        except intake.IntakeError as error:
            return response({"error": str(error)}, error.status)
        except ResourceNotFoundError:
            return response({"error": "Job or result not found"}, 404)
        except ConfigurationError as error:
            correlation = uuid.uuid4().hex
            log.error("jobId=%s configuration_error=%s", correlation, error)
            return response({"error": str(error), "correlationId": correlation}, 503)
        except Exception as error:
            # Never return or log upstream exceptions that may include document content/tokens.
            correlation = uuid.uuid4().hex
            log.error("jobId=%s http_failure exception=%s", correlation, type(error).__name__)
            return response({"error": "Request failed; check service configuration",
                             "correlationId": correlation}, 503)
    return wrapped


async def submit(req, durable_client, owner_id, metadata, content):
    job_id = uuid.uuid4().hex
    job = {"jobId": job_id, "ownerId": owner_id, **metadata,
           "sourcePath": f"{job_id}/{metadata['fileName']}",
           "direction": f"{metadata['sourceLanguage'] or 'auto'}->{','.join(metadata['targetLanguages'])}"}
    await asyncio.to_thread(jobs_table.create, job)
    try:
        await asyncio.to_thread(storage.put, "source", job["sourcePath"], content)
        await durable_client.start_new("translation_orchestrator", job_id, job)
    except Exception:
        await asyncio.to_thread(jobs_table.update, job_id, status="failed",
                                error="Submission failed; retry with a new job")
        raise
    base = base_url(req).rsplit("/jobs", 1)[0]
    return response({"jobId": job_id, "statusUrl": f"{base}/jobs/{job_id}"}, 202)


@app.route(route="jobs", methods=["POST"])
@app.durable_client_input(client_name="client")
@http_errors
async def post_jobs(req: Request, client):
    owner_id = auth.owner(req.headers)
    content_type = req.headers.get("content-type", "")
    body = await read_body(req, *intake.body_limit(content_type))
    metadata, content = intake.decode(body, content_type)
    return await submit(req, client, owner_id, metadata, content)


@app.route(route="jobs/from-url", methods=["POST"])
@app.durable_client_input(client_name="client")
@http_errors
async def post_from_url(req: Request, client):
    owner_id = auth.owner(req.headers)
    raw = await read_body(req, 16384, "URL request is too large")
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError()
    except ValueError as error:
        raise intake.IntakeError("Supply a JSON object with url and targetLanguages") from error
    metadata, content = await asyncio.to_thread(intake.from_url, body, req.headers.get("x-graph-token"))
    return await submit(req, client, owner_id, metadata, content)


def owned_job(req):
    caller = auth.owner(req.headers)
    # The Functions HTTP proxy may not populate Starlette path parameters.
    job_id = route_id(req)
    if not storage.valid_job_id(job_id):
        raise intake.IntakeError("Invalid job ID")
    job = jobs_table.get(job_id)
    if job["ownerId"] != caller:
        raise intake.IntakeError("Job not found", 404)
    return job


@app.route(route="jobs/{id}", methods=["GET"])
@http_errors
async def get_job(req: Request):
    job = await asyncio.to_thread(owned_job, req)
    exposed = ("jobId", "userId", "fileName", "direction", "status", "step", "createdAt", "updatedAt",
               "error")
    result = {key: job.get(key) for key in exposed}
    base = base_url(req).rstrip("/")
    if job.get("reportPath"):
        result["reportUrl"], result["resultUrl"] = base + "/report", base + "/result"
        report = await asyncio.to_thread(storage.get_json, job["jobId"], "report")
        result.update({key: report[key] for key in (
            "durations", "warnings", "usage", "estimatedCostUSD", "outputs", "sourceLanguage", "targetLanguages",
        )
                       if key in report})
    return response(result)


@app.route(route="jobs/{id}/report", methods=["GET"])
@http_errors
async def get_report(req: Request):
    job = await asyncio.to_thread(owned_job, req)
    if not job.get("reportPath"):
        return response({"error": "Report is not ready"}, 409)
    report = await asyncio.to_thread(storage.get, "reports", job["reportPath"])
    return Response(report, media_type="application/json")


@app.route(route="jobs/{id}/result", methods=["GET"])
@http_errors
async def get_result(req: Request):
    job = await asyncio.to_thread(owned_job, req)
    if not job.get("resultPath") or job["status"] != "complete":
        return response({"error": "Result is not ready"}, 409)
    report = await asyncio.to_thread(storage.get_json, job["jobId"], "report")
    outputs = report["outputs"]
    language = query_param(req, "lang")
    if language is not None:
        outputs = [output for output in outputs if output["language"] == language]
    if not outputs:
        return response({"error": "No result for the requested language"}, 404)
    container = job["resultContainer"]
    if len(outputs) == 1:
        download = await asyncio.to_thread(storage.download, container, outputs[0]["path"])
        content = download.chunks()
        size = await asyncio.to_thread(storage.blob_size, container, outputs[0]["path"])
        name = job["fileName"]
        mime = DOCUMENT_TYPES.get(PurePosixPath(name).suffix.lower(), "application/pdf")
    else:
        archive = ZipStream(sized=True)

        def blob_chunks(path):
            yield from storage.download(container, path).chunks()

        for output in outputs:
            path = output["path"]
            blob_size = await asyncio.to_thread(storage.blob_size, container, path)
            archive.add(blob_chunks(path), path, size=blob_size)
        content = archive
        size = None
        name, mime = f"translation-{job['jobId']}.zip", "application/zip"

    def safe_chunks():
        try:
            yield from content
        except Exception as error:
            log.error("jobId=%s result_stream_failed exception=%s", job["jobId"], type(error).__name__)
            raise ExternalServiceError("Result stream interrupted") from None

    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}"}
    if size is not None:
        headers["Content-Length"] = str(size)
    return StreamingResponse(safe_chunks(), media_type=mime, headers=headers)


def register_activity(name, operation):
    @app.function_name(name=name)
    @app.activity_trigger(input_name="job")
    def activity(job: dict):
        job_id = job["jobId"]
        started = time.monotonic()
        jobs_table.update(job_id, step=name, status="running", error="")
        log.info("jobId=%s step=%s started", job_id, name)
        try:
            result = operation(job)
        except Exception as error:
            safe = isinstance(error, (ConfigurationError, ExternalServiceError))
            detail = str(error) if safe or (name == "precheck" and isinstance(error, ValueError)) else (
                f"{name} failed ({type(error).__name__}); check Azure connections and protected reports")
            log.error("jobId=%s step=%s exception=%s reason=%s", job_id, name, type(error).__name__, detail)
            jobs_table.update(job_id, status="failed", error=detail)
            raise RuntimeError(detail) from None
        duration = time.monotonic() - started
        current = jobs_table.get(job_id)
        jobs_table.update(job_id, **{f"duration_{name}": current.get(f"duration_{name}", 0) + duration})
        log.info("jobId=%s step=%s duration=%.3f", job_id, name, duration)
        return result


for _name, _operation in {
    "precheck": precheck.run, "prepare": prepare.run,
    "translate_start": translate.start, "translate_poll": translate.poll,
    "reconstruct": route.reconstruct, "route": route.run, "notify": notify.run,
}.items():
    register_activity(_name, _operation)


@app.activity_trigger(input_name="job")
def record_failure(job: dict):
    current = jobs_table.get(job["jobId"])
    jobs_table.update(job["jobId"], status="failed",
                      error=current.get("error") or "Pipeline failed or timed out; inspect jobId-correlated logs")


@app.timer_trigger(schedule="0 0 3 * * *", arg_name="timer", run_on_startup=False)
def cleanup_retention(timer: func.TimerRequest):
    count = retention.cleanup()
    log.info("jobId=retention deletedContainers=%s", count)
