# SPDX-License-Identifier: MIT
import base64
import binascii
import json
import re
from email import policy
from email.parser import BytesParser
from urllib.parse import urlparse

import requests

from services import languages, translation_engines
from services.config import credential, integer, required


class IntakeError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def filename(value):
    if not isinstance(value, str) or not value or len(value) > 200 or any(c in value for c in "/\\:\r\n\x00"):
        raise IntakeError("fileName must be a plain filename, at most 200 characters")
    if not value.lower().endswith((".pdf", ".pptx", ".docx", ".xlsx")):
        raise IntakeError("Only .docx, .pptx, .xlsx and .pdf are supported; convert legacy or macro-enabled files first", 415)
    stem, extension = value.rsplit(".", 1)
    return f"{stem}.{extension.lower()}"


def fields(data):
    source = data.get("sourceLanguage", "")
    user = data.get("userId", "")
    engine = data.get("engine", "translator")
    name = data.get("glossaryName", "")
    try:
        if source != "":
            languages.validate(source)
        targets = languages.targets(data.get("targetLanguages", [data.get("targetLanguage")]), source)
    except ValueError as error:
        raise IntakeError(str(error)) from None
    if engine not in translation_engines.ENGINES:
        raise IntakeError("Engine must be translator or llm")
    if not isinstance(name, str) or (name and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name)):
        raise IntakeError("glossaryName must contain only letters, digits, hyphens or underscores")
    if not isinstance(user, str) or len(user) > 128:
        raise IntakeError("userId must be a string of at most 128 characters")
    return {"targetLanguages": targets, "sourceLanguage": source, "userId": user,
            "engine": engine, "glossaryName": name}


def document_limit(content_type: str) -> int:
    if content_type.lower().startswith("application/json"):
        name, default = "MAX_BASE64_MB", 10
    elif content_type.lower().startswith("multipart/form-data"):
        name, default = "MAX_MULTIPART_MB", 40
    else:
        raise IntakeError("Use application/json or multipart/form-data", 415)
    return min(integer(name, default), integer("MAX_DOCUMENT_MB", 40), 40) * 1024 * 1024


def body_limit(content_type: str) -> tuple[int, str]:
    limit = document_limit(content_type)
    if content_type.lower().startswith("application/json"):
        return (limit * 4 // 3) + 16384, "Base64 document exceeds configured limit"
    return limit + 65536, "Multipart document exceeds configured limit"


def decode(body: bytes | bytearray, content_type: str):
    max_body, error = body_limit(content_type)
    if len(body) > max_body:
        raise IntakeError(error, 413)
    limit = document_limit(content_type)
    if content_type.lower().startswith("application/json"):
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError()
            name = filename(data["fileName"])
            content = base64.b64decode(data["contentBase64"], validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as error:
            if isinstance(error, IntakeError):
                raise
            raise IntakeError("JSON requires fileName and valid contentBase64") from error
    else:
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        if not message.is_multipart() or message.defects:
            raise IntakeError("Malformed multipart request")
        data, content, name = {}, None, None
        for part in message.iter_parts():
            if part.is_multipart():
                raise IntakeError("Nested multipart parts are not supported")
            field = part.get_param("name", header="content-disposition")
            if field == "file":
                if content is not None:
                    raise IntakeError("Supply exactly one file")
                name, content = filename(part.get_filename()), part.get_payload(decode=True)
            elif field in {"targetLanguages", "targetLanguage", "sourceLanguage", "userId", "engine",
                           "glossaryName"}:
                value = part.get_payload(decode=True)
                if len(value) > 1024 or field in data:
                    raise IntakeError("Invalid or duplicated multipart field")
                try:
                    data[field] = value.decode("utf-8")
                    if field == "targetLanguages":
                        data[field] = json.loads(data[field])
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise IntakeError("Multipart fields must be UTF-8; targetLanguages must be a JSON array") from None
        if content is None:
            raise IntakeError("Multipart request requires a file part")
    if not content:
        raise IntakeError("Document is empty")
    if len(content) > limit:
        raise IntakeError("Document exceeds configured size limit", 413)
    return {"fileName": name, **fields(data)}, content


def from_url(data, graph_token=None):
    url = data.get("url", "")
    if not isinstance(url, str):
        raise IntakeError("url must be an HTTPS SharePoint/OneDrive file URL")
    parsed = urlparse(url)
    hosts = {h.strip().lower() for h in required("SHAREPOINT_HOSTS").split(",")}
    if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username or parsed.port:
        raise IntakeError("URL must be HTTPS on a configured SharePoint/OneDrive tenant host")
    token = graph_token or credential().get_token("https://graph.microsoft.com/.default").token
    share = "u!" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    graph_url = f"https://graph.microsoft.com/v1.0/shares/{share}/driveItem"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(graph_url, headers=headers, timeout=30, allow_redirects=False)
    if response.status_code != 200:
        raise IntakeError("Graph could not resolve the file; check delegated/app permissions", 502)
    meta = response.json()
    name = filename(meta["name"])
    limit = min(integer("MAX_DOCUMENT_MB", 40), 40) * 1024 * 1024
    if meta.get("size", limit + 1) > limit:
        raise IntakeError("SharePoint file exceeds document size limit", 413)
    response = requests.get(graph_url + "/content", headers=headers, timeout=60,
                            allow_redirects=False, stream=True)
    if response.status_code == 302:
        download = response.headers["Location"]
        destination = urlparse(download)
        if (destination.scheme != "https" or destination.hostname not in hosts
                or destination.username or destination.port):
            raise IntakeError("Graph download host is not allowlisted; configure SHAREPOINT_HOSTS", 502)
        response.close()
        # Never forward the Graph bearer token to a pre-authenticated download URL.
        response = requests.get(download, timeout=60, allow_redirects=False, stream=True)
    if response.status_code != 200:
        response.close()
        raise IntakeError("Graph file download failed", 502)
    result = bytearray()
    with response:
        for chunk in response.iter_content(65536):
            result.extend(chunk)
            if len(result) > limit:
                raise IntakeError("Downloaded file exceeds document size limit", 413)
    if not result:
        raise IntakeError("Downloaded file is empty")
    return {"fileName": name, **fields(data)}, bytes(result)
