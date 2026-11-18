# Reconstruction and logos

With the optional model engine, editable DOCX paragraphs and cells, PPTX shapes and cells, and XLSX string cells are translated in place. The code targets original Office text structures rather than adding slide boxes. The default Office route delegates document modification to Azure Translator; exact layout fidelity depends on the service and input.

Pictures and logos are not sent through an image-replacement workflow. Text baked into pictures remains in the source language. A separate image compositor would need representative OCR accuracy, visual fidelity, and latency measurements before use.

The optional LibreOffice renderer can produce slide previews for visual inspection; it does not certify fit. Open both files in the customer's Office application and compare slide count, fonts, notes, tables, formulas, and images. Inspect longer translations at actual presentation size. Treat PDF order, layout, and font appearance as best-effort.
