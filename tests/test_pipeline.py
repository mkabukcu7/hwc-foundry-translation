import io
import json
from unittest.mock import MagicMock

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from reportlab.pdfgen import canvas

from activities.precheck import validate_document
from services import storage
from services.translator_client import Translator, payload
from tests.helpers import indexed_functions


def pdf(pages=1):
    output = io.BytesIO()
    doc = canvas.Canvas(output)
    for _ in range(pages):
        doc.drawString(50, 50, "Contoso Marketing")
        doc.showPage()
    doc.save()
    return output.getvalue()


def test_pdf_rejects_encrypted_and_copy_restricted():
    validate_document(pdf(), "x.pdf")
    doc, output = PdfWriter(), io.BytesIO()
    doc.append(PdfReader(io.BytesIO(pdf())))
    doc.encrypt("", "owner", permissions_flag=UserAccessPermissions.PRINT, algorithm="AES-256")
    doc.write(output)
    secured = output.getvalue()
    with pytest.raises(ValueError, match="copy-restricted"):
        validate_document(secured, "x.pdf")
    doc, output = PdfWriter(), io.BytesIO()
    doc.append(PdfReader(io.BytesIO(pdf())))
    doc.encrypt("user", "owner", algorithm="AES-256")
    doc.write(output)
    secured = output.getvalue()
    with pytest.raises(ValueError, match="Encrypted"):
        validate_document(secured, "x.pdf")


def test_image_validation_accepts_supported_formats_and_rejects_mismatches():
    for extension, image_format in (("jpg", "JPEG"), ("png", "PNG"), ("bmp", "BMP"), ("tiff", "TIFF")):
        output = io.BytesIO()
        Image.new("RGB", (100, 100), "white").save(output, format=image_format)
        validate_document(output.getvalue(), f"marketing.{extension}")
    jpeg = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(jpeg, format="JPEG")
    with pytest.raises(ValueError, match="does not match"):
        validate_document(jpeg.getvalue(), "marketing.png")
    with pytest.raises(ValueError, match="Invalid or unsupported image"):
        validate_document(b"not an image", "marketing.png")
    with pytest.raises(ValueError, match="dimensions"):
        output = io.BytesIO()
        Image.new("RGB", (40, 100), "white").save(output, format="PNG")
        validate_document(output.getvalue(), "small.png")


def test_tiff_validation_bounds_every_frame_and_aggregate_pixels(monkeypatch):
    output = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(
        output, format="TIFF", save_all=True,
        append_images=[Image.new("RGB", (100, 100), "black")],
    )
    image = output.getvalue()
    monkeypatch.setattr("activities.precheck.MAX_IMAGE_FRAMES", 1)
    with pytest.raises(ValueError, match="frame count"):
        validate_document(image, "multipage.tiff")

    monkeypatch.setattr("activities.precheck.MAX_IMAGE_FRAMES", 10)
    monkeypatch.setattr("activities.precheck.MAX_TOTAL_IMAGE_PIXELS", 15_000)
    with pytest.raises(ValueError, match="decoded pixel count"):
        validate_document(image, "multipage.tiff")

    output = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(
        output, format="TIFF", save_all=True,
        append_images=[Image.new("RGB", (20, 100), "black")],
    )
    with pytest.raises(ValueError, match="dimensions"):
        validate_document(output.getvalue(), "multipage.tiff")


def test_translator_request_exact_options_and_autodetect():
    body = payload("https://a/source/a.pptx", "https://a/target/a.pptx", "fr")
    assert body["options"] == {"translateTextWithinImage": False}
    assert "language" not in body["inputs"][0]["source"]
    assert "pdfDocumentIntelligence" not in json.dumps(body)
    assert body["inputs"][0]["storageType"] == "File"
    assert body["inputs"][0]["targets"][0]["targetUrl"].endswith("/a.pptx")


def test_translator_refreshes_tokens_and_rejects_foreign_operations(monkeypatch):
    monkeypatch.setenv("TRANSLATOR_ENDPOINT", "https://translator.example")
    adapter = Translator()
    with pytest.raises(ValueError, match="Unexpected"):
        adapter.poll("https://evil.example/translator/document/batches/id", "a" * 32)


def test_app_indexes_expected_routes_and_activities():
    functions = indexed_functions().values()
    names = {f.get_function_name() for f in functions}
    assert {"precheck", "prepare", "translate_start", "translate_poll", "reconstruct", "route",
            "notify", "translation_orchestrator", "post_jobs", "get_report", "get_result"} <= names


def test_target_requires_exactly_one_document(monkeypatch):
    client = MagicMock()
    client.get_container_client.return_value.list_blobs.return_value = []
    monkeypatch.setattr(storage, "client", lambda: client)
    with pytest.raises(ValueError, match="one translated"):
        storage.target({"jobId": "a" * 32, "fileName": "test.pdf"})
