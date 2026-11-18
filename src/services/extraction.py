# SPDX-License-Identifier: MIT
from pathlib import Path

from services import docintel_client, docx_document, pptx_extract, xlsx_document


def extract(data: bytes, filename: str, job_id: str = "") -> dict:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        result = docintel_client.extract(data, positioned=True, job_id=job_id)
    elif extension == ".pptx":
        result = pptx_extract.extract(data, editable_only=True)
    elif extension == ".xlsx":
        result = xlsx_document.extract(data)
    else:
        result = docx_document.extract(data)
    if not any(segment["text"].strip() for segment in result["segments"]):
        raise ValueError("Document contains no extractable text")
    return result
