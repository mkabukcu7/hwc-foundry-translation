import io
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from activities.precheck import validate_document
from services import xlsx_document
from services.docx_document import parse


def xlsx():
    output = io.BytesIO()
    namespace = xlsx_document.S[1:-1]
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml",
                        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                        '<Default Extension="xml" ContentType="application/xml"/>'
                        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
                        '</Types>')
        archive.writestr("_rels/.rels",
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                        '</Relationships>')
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{namespace}" '
                        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                        '<sheets><sheet name="Ventas" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels",
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
                        '</Relationships>')
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="{namespace}" count="2" uniqueCount="1">'
                        '<si><r><rPr><b/></rPr><t>Hola</t></r><r><t> mundo</t></r></si></sst>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{namespace}">'
                        '<cols><col min="1" max="4" width="25" customWidth="1"/></cols>'
                        '<sheetData><row r="1">'
                        '<c r="A1" t="s"><v>0</v></c>'
                        '<c r="B1" t="inlineStr"><is><t>Importe</t></is></c>'
                        '<c r="C1"><v>123.45</v></c>'
                        '<c r="D1"><f>C1*2</f><v>246.9</v></c>'
                        '<c r="E1" t="str"><f>"Hola"</f><v>Hola</v></c>'
                        '</row><row r="2"><c r="A2" t="s"><v>0</v></c></row></sheetData>'
                        '<mergeCells count="1"><mergeCell ref="B2:C2"/></mergeCells></worksheet>')
        archive.writestr("xl/media/image1.png", b"unchanged-artwork")
    return output.getvalue()


def test_xlsx_preserves_formulas_numbers_styles_merges_and_package():
    original = xlsx()
    validate_document(original, "source.xlsx")
    segments = xlsx_document.extract(original)["segments"]
    assert [s["text"] for s in segments] == ["Hola mundo", "Importe", "Hola mundo"]
    translated = [{**s, "text": t} for s, t in zip(segments, ["Hello world", "Amount", "=SUM(A1)"], strict=True)]
    output = xlsx_document.rebuild(original, translated)
    with ZipFile(io.BytesIO(output)) as result, ZipFile(io.BytesIO(original)) as source:
        assert result.namelist() == source.namelist()
        for name in source.namelist():
            if name != "xl/worksheets/sheet1.xml":
                assert result.read(name) == source.read(name)
        root = parse(result.read("xl/worksheets/sheet1.xml"))
        ns = {"s": xlsx_document.S[1:-1]}
        assert root.xpath("string(//s:c[@r='C1']/s:v)", namespaces=ns) == "123.45"
        assert root.xpath("string(//s:c[@r='D1']/s:f)", namespaces=ns) == "C1*2"
        assert root.xpath("string(//s:c[@r='E1']/s:v)", namespaces=ns) == "Hola"
        assert root.xpath("string(//s:mergeCell/@ref)", namespaces=ns) == "B2:C2"
        assert root.xpath("string(//s:c[@r='A2']/@t)", namespaces=ns) == "inlineStr"
        assert not root.xpath("//s:c[@r='A2']/s:f", namespaces=ns)
        assert root.xpath("//s:c[@r='A1']//s:b", namespaces=ns)
    assert [s["text"] for s in xlsx_document.extract(output)["segments"]] == ["Hello world", "Amount", "=SUM(A1)"]


def test_xlsx_rejects_missing_duplicate_unknown_and_oversized_results():
    original = xlsx()
    segments = xlsx_document.extract(original)["segments"]
    for bad in [segments[:-1], segments + [segments[0]],
                [{**s, "cell": "Z99"} for s in segments],
                [{**s, "text": "x" * 32768} for s in segments]]:
        with pytest.raises(ValueError):
            xlsx_document.rebuild(original, bad)


def test_xlsx_rejects_macros_disguised_as_xlsx():
    output = io.BytesIO(xlsx())
    with ZipFile(output, "a") as archive:
        archive.writestr("xl/vbaProject.bin", b"not-supported")
    with pytest.raises(ValueError, match="Macro"):
        validate_document(output.getvalue(), "source.xlsx")


def test_xlsx_translates_multiple_sheets_without_changing_dates_booleans_or_formulas():
    output = io.BytesIO(xlsx())
    namespace = xlsx_document.S[1:-1]
    with ZipFile(output, "a") as archive:
        archive.writestr("xl/worksheets/sheet2.xml", f'<worksheet xmlns="{namespace}"><sheetData><row r="1">'
                        '<c r="A1" t="inlineStr"><is><t>Segunda hoja</t></is></c>'
                        '<c r="B1" t="d"><v>2026-11-12</v></c>'
                        '<c r="C1" t="b"><v>1</v></c>'
                        '<c r="D1" t="s"><f>IF(C1,A1,"")</f><v>0</v></c>'
                        '</row></sheetData></worksheet>')
    segments = xlsx_document.extract(output.getvalue())["segments"]
    assert len(segments) == 4
    result = xlsx_document.rebuild(output.getvalue(), [{**s, "text": "Translation"} for s in segments])
    with ZipFile(io.BytesIO(result)) as archive:
        root = parse(archive.read("xl/worksheets/sheet2.xml"))
        ns = {"s": namespace}
        assert root.xpath("string(//s:c[@r='B1']/s:v)", namespaces=ns) == "2026-11-12"
        assert root.xpath("string(//s:c[@r='C1']/s:v)", namespaces=ns) == "1"
        assert root.xpath("string(//s:c[@r='D1']/s:v)", namespaces=ns) == "0"
        assert root.xpath("string(//s:c[@r='D1']/s:f)", namespaces=ns) == 'IF(C1,A1,"")'
    assert len(xlsx_document.extract(result)["segments"]) == 4
