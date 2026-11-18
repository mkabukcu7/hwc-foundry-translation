# SPDX-License-Identifier: MIT
from datetime import datetime

from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

from activities.precheck import validate_document
from samples.generate_local_samples import CAMPAIGN, generate


def test_fictional_office_samples(tmp_path):
    generate(tmp_path)
    assert sorted(path.suffix for path in tmp_path.iterdir()) == [".docx", ".pptx", ".xlsx"]
    for path in tmp_path.iterdir():
        validate_document(path.read_bytes(), path.name)
    brief = Document(tmp_path / "campaign_brief_en.docx")
    assert brief.paragraphs[1].text == CAMPAIGN
    assert brief.tables[0].cell(0, 0).text == "Channel"
    assert len(brief.inline_shapes) == 1
    assert brief.sections[0].header.paragraphs[0].text == "Contoso Marketing"
    assert brief.sections[0].footer.paragraphs[0].text == "Internal campaign brief"
    deck = Presentation(tmp_path / "campaign_deck_en.pptx")
    assert len(deck.slides) == 5 and deck.slides[0].shapes.title.text == CAMPAIGN
    assert any(shape.has_table for shape in deck.slides[2].shapes)
    assert any(hasattr(shape, "image") for shape in deck.slides[3].shapes)
    assert "registration reminder" in deck.slides[4].notes_slide.notes_text_frame.text
    book = load_workbook(tmp_path / "campaign_plan_en.xlsx")
    assert book.sheetnames == ["Campaign", "Channels"]
    assert book.active["A1"].value == CAMPAIGN
    assert book.active["C5"].value == "=SUM(C3:C4)"
    assert isinstance(book.active["B3"].value, datetime)
