# SPDX-License-Identifier: MIT
"""Loopback-only showcase for the local translation workflow."""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from scripts import local_demo
from services import languages, storage, translation_engines
from services.config import integer

PAGE = Path(__file__).resolve().parents[1] / "showcase" / "index.html"
LOG = logging.getLogger(__name__)


def create_app(output_dir=Path("samples/results/local")):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @app.get("/")
    def page():
        return FileResponse(PAGE)

    @app.get("/api/options")
    def options():
        return {"languages": languages.enabled(), "engines": translation_engines.ENGINES}

    @app.post("/api/jobs")
    async def submit(request: Request, filename: str, engine: str = "translator", sourceLanguage: str = ""):
        if (request.headers.get("origin") not in {"http://" + request.headers["host"], None}
                or request.headers.get("x-translation-showcase") != "1"):
            raise HTTPException(403, "Use the loopback showcase page.")
        name = Path(filename)
        if (name.name != filename or name.drive or len(filename) > 200
                or any(c in filename for c in "/\\:\r\n\x00") or name.suffix.lower() not in
                {".docx", ".pptx", ".xlsx", ".pdf"}):
            raise HTTPException(415, "Choose a DOCX, PPTX, XLSX or PDF file.")
        try:
            if sourceLanguage:
                languages.validate(sourceLanguage)
            targets = languages.targets(request.query_params.getlist("targetLanguage"), sourceLanguage)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        if engine not in translation_engines.ENGINES:
            raise HTTPException(400, "Unknown translation engine.")
        limit = min(integer("MAX_DOCUMENT_MB", 40), 40) * 1024 * 1024
        with TemporaryDirectory(prefix="translation-upload-") as directory:
            path = Path(directory) / name
            length = 0
            with path.open("wb") as file:
                async for chunk in request.stream():
                    length += len(chunk)
                    if length > limit:
                        raise HTTPException(413, "Document exceeds configured size limit.")
                    file.write(chunk)
            try:
                return await run_in_threadpool(local_demo.run_file, path, output_dir, sourceLanguage, targets,
                                               engine=engine)
            except Exception as error:
                LOG.error("local translation failed exception=%s", type(error).__name__)
                raise HTTPException(422, "Translation failed; check file and service configuration.") from None

    @app.get("/api/jobs/{job_id}/{language}/{filename}")
    def download(job_id: str, language: str, filename: str):
        if (not storage.valid_job_id(job_id) or language not in languages.enabled()
                or filename in {".", ".."} or any(c in filename for c in "/\\:\r\n\x00")):
            raise HTTPException(404)
        path = output_dir / job_id / language / filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, filename=filename)

    return app


app = create_app()
