import io
from unittest.mock import MagicMock
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from activities.precheck import validate_document
from scripts import local_demo
from services import contextual_translation, docintel_client, docx_document


def docx(extra=""):
    output = io.BytesIO()
    namespace = docx_document.NS["w"]
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml",
                        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                        '<Default Extension="xml" ContentType="application/xml"/>'
                        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                        '</Types>')
        archive.writestr("_rels/.rels",
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                        '</Relationships>')
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{namespace}"><w:body>'
                        '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Hola</w:t></w:r>'
                        '<w:r><w:t> mundo</w:t></w:r></w:p>'
                        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Importe</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                        f'{extra}<w:sectPr/></w:body></w:document>')
        archive.writestr("word/header1.xml", f'<w:hdr xmlns:w="{namespace}"><w:p><w:r><w:t>Cabecera</w:t>'
                        '</w:r></w:p></w:hdr>')
        archive.writestr("word/media/image1.png", b"unchanged-image")
    return output.getvalue()


def mock_document_translation(monkeypatch):
    def translate_document(data, *_args, **_kwargs):
        segments = docx_document.extract(data)["segments"]
        translated = [{**segment, "text": "English " + segment["text"]} for segment in segments]
        return docx_document.rebuild(data, translated), {}

    monkeypatch.setattr(local_demo.local_translation, "translate_document", translate_document)


def test_docx_preserves_package_and_translates_paragraphs_tables_headers():
    original = docx()
    validate_document(original, "source.docx")
    segments = docx_document.extract(original)["segments"]
    assert [s["text"] for s in segments] == ["Hola mundo", "Importe", "Cabecera"]
    translated = [{**s, "text": t} for s, t in zip(segments, ["Hello world", "Amount", "Header"], strict=True)]
    output = docx_document.rebuild(original, translated)
    with ZipFile(io.BytesIO(output)) as archive, ZipFile(io.BytesIO(original)) as source:
        assert archive.namelist() == source.namelist()
        assert archive.read("word/media/image1.png") == source.read("word/media/image1.png")
        root = docx_document.parse(archive.read("word/document.xml"))
        assert len(root.xpath("//w:tbl", namespaces=docx_document.NS)) == 1
        assert len(root.xpath("//w:b", namespaces=docx_document.NS)) == 1
    texts = [s["text"] for s in docx_document.extract(output)["segments"]]
    assert texts == ["Hello world", "Amount", "Header"]


@pytest.mark.parametrize("extra", [
    "<w:p><w:ins><w:r><w:t>Revision</w:t></w:r></w:ins></w:p>",
    '<w:p><w:fldSimple w:instr="PAGE"/></w:p>',
    "<w:p><w:moveFrom><w:r><w:t>Moved out</w:t></w:r></w:moveFrom></w:p>",
    "<w:p><w:moveTo><w:r><w:t>Moved in</w:t></w:r></w:moveTo></w:p>",
    '<w:p><w:moveFromRangeStart w:id="1" w:author="Editor"/></w:p>',
])
def test_docx_rejects_revisions_and_dynamic_fields(extra):
    with pytest.raises(ValueError, match="tracked changes and dynamic fields"):
        validate_document(docx(extra), "source.docx")


def test_docx_preserves_and_rebuilds_tabs_and_manual_line_breaks():
    original = docx(
        "<w:p><w:r><w:t>Uno</w:t><w:tab/><w:t>due</w:t><w:br/>"
        "<w:t>tre</w:t><w:cr/><w:t>quattro</w:t></w:r></w:p>",
    )
    extracted = docx_document.extract(original)["segments"]
    source = next(segment for segment in extracted if segment["text"] == "Uno\tdue\ntre\nquattro")
    rebuilt = docx_document.rebuild(original, [
        {**segment, "text": ("One\tsecond\nthird" if segment["location"] == source["location"]
                             else segment["text"])}
        for segment in extracted
    ])
    translated = next(
        segment for segment in docx_document.extract(rebuilt)["segments"]
        if segment["location"] == source["location"]
    )
    assert translated["text"] == "One\tsecond\nthird"
    with ZipFile(io.BytesIO(rebuilt)) as archive:
        root = docx_document.parse(archive.read("word/document.xml"))
        assert len(root.xpath("//w:tab", namespaces=docx_document.NS)) == 1
        assert len(root.xpath("//w:br", namespaces=docx_document.NS)) == 1
        assert not root.xpath("//w:cr", namespaces=docx_document.NS)


def test_docx_workflow_retains_docx_without_ocr(monkeypatch, tmp_path):
    source = tmp_path / "source.docx"
    source.write_bytes(docx())
    forbidden = MagicMock(side_effect=AssertionError("OCR must not run"))
    monkeypatch.setattr(docintel_client, "extract", forbidden)
    monkeypatch.setattr(contextual_translation, "translate", forbidden)
    mock_document_translation(monkeypatch)
    report = local_demo.run_file(source, tmp_path / "output", source_language="es")
    output = tmp_path / "output" / report["jobId"] / "en" / source.name
    assert report["outputs"][0]["path"] == f"en/{source.name}"
    assert report["status"] == "complete"
    texts = [s["text"] for s in docx_document.extract(output.read_bytes())["segments"]]
    assert all(text.startswith("English") for text in texts)
    forbidden.assert_not_called()


def test_job_writes_each_target_under_original_filename(monkeypatch, tmp_path):
    source = tmp_path / "brief.docx"
    source.write_bytes(docx())
    mock_document_translation(monkeypatch)
    report = local_demo.run_file(source, tmp_path / "output", "en", ["fr", "de", "fr", "en"])
    root = tmp_path / "output" / report["jobId"]
    assert report["targetLanguages"] == ["fr", "de"]
    assert {file.relative_to(root).as_posix() for file in root.glob("*/*")} == {
        "fr/brief.docx", "de/brief.docx",
    }


def test_docx_textbox_text_is_extracted_once_without_duplication():
    extra = ("<w:p><w:r><w:drawing><w:txbxContent><w:p><w:r>"
             "<w:t>Texto interior</w:t></w:r></w:p></w:txbxContent></w:drawing></w:r></w:p>")
    texts = [s["text"] for s in docx_document.extract(docx(extra))["segments"]]
    assert texts.count("Texto interior") == 1
