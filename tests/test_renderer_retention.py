import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from renderer.app import app
from scripts.showcase import create_app
from services import retention, storage
from services.config import ReconstructionError


def test_renderer_validates_issuer_audience_and_application_role(monkeypatch):
    import renderer.app as module
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant")
    monkeypatch.setenv("RENDERER_CLIENT_ID", "renderer")
    monkeypatch.setattr(module, "PyJWKClient", lambda _: SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())
    ))
    client = TestClient(app)
    assert client.post("/render", content=b"x").status_code == 401
    claims = {"iss": "https://login.microsoftonline.com/tenant/v2.0", "aud": "renderer",
              "exp": int(time.time()) + 60, "iat": int(time.time()), "roles": []}
    token = jwt.encode(claims, key, algorithm="RS256")
    assert client.post("/render", content=b"x", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    claims["roles"] = ["Renderer.Invoke"]
    token = jwt.encode(claims, key, algorithm="RS256")
    assert client.post("/render", content=b"x", headers={"Authorization": f"Bearer {token}"}).status_code == 415
    assert client.get("/healthz").status_code == 200


def test_retention_deletes_only_expired_application_targets(monkeypatch):
    now = datetime(2026, 3, 20, tzinfo=timezone.utc)
    client = MagicMock()
    old = now - timedelta(days=15)
    client.list_containers.return_value = [
        SimpleNamespace(name="target-" + "a" * 32, last_modified=old),
        SimpleNamespace(name="target-" + "b" * 32, last_modified=now),
        SimpleNamespace(name="target-not-an-application-job", last_modified=old),
    ]
    client.get_container_client.return_value.list_blobs.return_value = []
    monkeypatch.setattr(storage, "client", lambda: client)
    assert retention.cleanup(now) == 1
    client.delete_container.assert_called_once_with("target-" + "a" * 32)


def test_showcase_lists_recent_local_results(tmp_path):
    job_id = "a" * 32
    report = {
        "jobId": job_id,
        "status": "complete",
        "sourceFile": "brief.docx",
        "sourceLanguage": "en",
        "targetLanguages": ["fr"],
        "outputs": [],
    }
    directory = tmp_path / job_id
    directory.mkdir()
    (directory / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "not-a-job").mkdir()
    (tmp_path / "not-a-job" / "report.json").write_text(json.dumps({"jobId": "invalid"}),
                                                        encoding="utf-8")

    client = TestClient(create_app(tmp_path), base_url="http://localhost")
    assert client.get("/api/jobs").json() == {"jobs": [report]}


def test_showcase_lists_glossaries(monkeypatch, tmp_path):
    import scripts.showcase as showcase

    monkeypatch.setattr(showcase.glossary, "available", lambda: ["sample", "brand"])
    client = TestClient(create_app(tmp_path), base_url="http://localhost")
    assert client.get("/api/options").json()["glossaries"] == ["sample", "brand"]


def test_showcase_exposes_safe_reconstruction_errors(monkeypatch, tmp_path):
    import scripts.showcase as showcase

    monkeypatch.setattr(showcase, "run_in_threadpool", lambda *_args, **_kwargs: _raise(
        ReconstructionError("Translated text cannot be reconstructed safely.")
    ))
    client = TestClient(create_app(tmp_path), base_url="http://localhost")
    response = client.post(
        "/api/jobs?filename=brief.pdf&targetLanguage=fr",
        content=b"pdf",
        headers={"X-Translation-Showcase": "1"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Translated text cannot be reconstructed safely."}


def _raise(error):
    raise error
