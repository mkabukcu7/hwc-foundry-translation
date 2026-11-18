# HWC marketing document translation

Translate one DOCX, PPTX, XLSX, or PDF into up to ten target languages. The default engine is Azure Translator. An optional Microsoft Foundry deployment translates extracted text through the Responses API. There is no automated quality gate.

```text
Client → Entra-protected API → Durable Functions
  → precheck → prepare → translate per target → reconstruct → report → notify
  → <language>/<original-file-name>, report.json
```

Default `SUPPORTED_LANGUAGES`: `en,fr,de,es,it,pt,pt-PT,nl,pl,sv,da,nb,fi`. Change the comma-separated list in `.env` for local runs or the Function App setting for Azure. Codes must be in the [Latin-script allowlist](./src/services/languages.py).

## Local showcase

1. Install Python 3.11 and Azure CLI. Sign in with `az login` using an identity authorized on the Translator and Document Intelligence resources.
2. Run `py -3.11 -m venv .venv` and `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`.
3. Copy `.env.sample` to `.env`. Set `PYTHON_EXECUTABLE` to the virtual environment's Python and fill in the service endpoints. Leave Foundry settings blank if unused.
4. Generate the fictional Office documents with `.\.venv\Scripts\python.exe samples\generate_local_samples.py`.
5. Run `.\scripts\run-showcase.ps1`, open `http://localhost:8765`, upload a file, and select the target languages. The showcase runs locally without Durable Functions; it waits for the translation request to finish.

## Configuration and Azure setup

| Settings | Purpose |
|---|---|
| `TRANSLATOR_ENDPOINT`, `DOCINTEL_ENDPOINT` | Translator and PDF extraction |
| `SUPPORTED_LANGUAGES` | Enabled source and target codes |
| `FOUNDRY_MODEL_ENDPOINT`, `TRANSLATION_MODEL_NAME`, `TRANSLATION_REASONING_EFFORT` | Optional Responses deployment |
| `GLOSSARY_MODE`, `GLOSSARY_PATH` | Static terminology or disabled |
| `TRANSLATOR_CHARACTER_RATE`, `LLM_INPUT_RATE`, `LLM_OUTPUT_RATE` | Optional USD rates per million units |
| `API_CLIENT_ID`, `API_ALLOWED_AUDIENCE`, `SHAREPOINT_HOSTS` | API audience and approved URL download hosts |
| `MAX_BASE64_MB`, `MAX_MULTIPART_MB`, `MAX_DOCUMENT_MB` | Intake size limits |
| `SLIDE_RENDER_URL`, `SLIDE_RENDER_SCOPE` | Optional remote rendering and token audience |

The deployment entry point is `azd up`. Before running it, register the API in Entra as described in the [Copilot Studio guide](./docs/copilot-studio-setup.md), select your subscription and region, and set `API_CLIENT_ID` and `API_ALLOWED_AUDIENCE` in the azd environment. Foundry is off by default; enabling it also requires a supported model, version and SKU. After deployment, smoke-test user authentication and both translation directions before enabling customer traffic. No live deployment was validated for this release.

Reports contain available usage and timings by target, plus output paths. Translator usage is measured in characters; model usage is measured in input and output tokens. Rates are optional: leave them blank for unknown estimates. These estimates are not Azure invoices and exclude infrastructure and extraction charges.

## Limitations

- Phase 1 is Latin-script only. `ja`, `ko`, `zh-Hans`, `ar`, and other out-of-scope codes require a later phase.
- Text baked into images is not translated. No replacement boxes are added over pictures. Verify logos and images on representative outputs.
- Branded layouts need a human visual check. Longer text can overflow or wrap differently.
- PDF is reconstructed, not pixel-perfect. The Translator glossary is not applied on the PDF OCR path.
- Large batches may hit SharePoint write throttling. Retry writes independently and honor backoff.
- The HTTP result endpoint streams single files and streamed ZIP bundles. Verify network/proxy streaming behavior separately against the deployed host.

See [architecture](./docs/architecture.md), [glossary format](./docs/glossary-format.md), and [reconstruction and logos](./docs/reconstruction-and-logos.md).
