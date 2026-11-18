# SPDX-License-Identifier: MIT
from pathlib import Path

from services import contextual_translation, document_output, docx_document, local_translation, xlsx_document


def translate_text(extracted, source, target, job_id, engine, terms):
    if engine.engine == "translator":
        return local_translation.translate_segments(extracted["segments"], source, target, job_id)
    return contextual_translation.translate(
        extracted["segments"], source, target, terms, job_id,
        model=engine.deployment_name, reasoning_effort=engine.reasoning_effort,
    )


def reconstruct(data, name, segments):
    extension = Path(name).suffix.lower()
    if extension == ".pdf":
        try:
            return document_output.pdf(data, segments), []
        except document_output.LayoutError:
            return document_output.reflow_pdf(segments), ["Translated PDF text did not fit; the PDF was reflowed."]
    if extension == ".pptx":
        return document_output.pptx(data, segments, False, image_sidecar=True), []
    builder = docx_document if extension == ".docx" else xlsx_document
    return builder.rebuild(data, segments), []
