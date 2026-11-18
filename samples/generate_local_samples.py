# SPDX-License-Identifier: MIT
import io
from datetime import date
from pathlib import Path

from docx import Document
from docx.shared import Inches
from openpyxl import Workbook
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches as SlideInches

OUT = Path(__file__).parent / "out"
CAMPAIGN = "Contoso Marketing spring wellbeing campaign"


def logo():
    buffer = io.BytesIO()
    image = Image.new("RGB", (240, 160), "#e8f4ec")
    draw = ImageDraw.Draw(image)
    draw.ellipse((45, 28, 148, 131), fill="#27674a")
    draw.ellipse((101, 42, 205, 145), fill="#75ba86")
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def generate(output=OUT):
    output.mkdir(parents=True, exist_ok=True)
    brief = Document()
    brief.sections[0].header.paragraphs[0].text = "Contoso Marketing"
    brief.sections[0].footer.paragraphs[0].text = "Internal campaign brief"
    brief.add_picture(logo(), width=Inches(1.25))
    brief.add_heading(CAMPAIGN, 0)
    brief.add_heading("Campaign goals", 1)
    brief.add_paragraph("Invite employees to a wellbeing webinar and share practical resources.")
    table = brief.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Channel", "Action"
    table.cell(1, 0).text, table.cell(1, 1).text = "Newsletter", "Register for the webinar"
    brief.save(output / "campaign_brief_en.docx")

    deck = Presentation()
    for title in (CAMPAIGN, "Campaign goals", "Campaign channels", "Campaign artwork", "Next steps"):
        slide = deck.slides.add_slide(deck.slide_layouts[1 if title == "Campaign goals" else 5])
        slide.shapes.title.text = title
    bullets = deck.slides[1].placeholders[1].text_frame
    bullets.text = "Share wellbeing resources\nInvite employees to a webinar"
    table = deck.slides[2].shapes.add_table(2, 2, *map(SlideInches, (1, 2, 7, 2))).table
    table.cell(0, 0).text, table.cell(0, 1).text = "Channel", "Action"
    table.cell(1, 0).text, table.cell(1, 1).text = "Newsletter", "Register"
    deck.slides[3].shapes.add_picture(logo(), SlideInches(2), SlideInches(2), width=SlideInches(5))
    deck.slides[4].notes_slide.notes_text_frame.text = "Share the registration reminder with country teams."
    deck.save(output / "campaign_deck_en.pptx")

    workbook = Workbook()
    plan = workbook.active
    plan.title = "Campaign"
    plan.append([CAMPAIGN])
    plan.append(["Action", "Date", "Planned signups"])
    plan.append(["Webinar", date(2027, 4, 12), 30])
    plan.append(["Reminder", date(2027, 4, 19), 20])
    plan.append(["Total", None, "=SUM(C3:C4)"])
    workbook.create_sheet("Channels").append(["Channel", "Newsletter"])
    workbook.save(output / "campaign_plan_en.xlsx")


if __name__ == "__main__":
    generate()
