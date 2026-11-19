# Glossary format

The default is `glossary/sample.csv` locally and the copy in `src/glossary/` on Azure. Use UTF-8 (a BOM is accepted). Each column header is a configured language code. Optional `dnt=true` keeps the source value for any target. Unsupported columns are ignored with a warning.

```csv
en,fr,de,dnt
Contoso,,,true
webinar,webinaire,Webinar,
```

Select a CSV by base name with `glossaryName`, set `GLOSSARY_PATH` to an alternate default file, or set `GLOSSARY_MODE=none` to disable terminology. Place named CSVs beside the default file. For deployment, include them under `src/glossary/` and keep the two sample copies in sync. To add a language, enable its code in `SUPPORTED_LANGUAGES` and add a column with that code.

The local showcase lists CSV files from the `glossary/` folder and lets you select one for each run. Use the file's base name, for example `brand.csv` appears as `brand`. Glossaries are applied to Office Translator jobs and supplied as terminology guidance to the Foundry engine. PDF text translation does not apply the glossary.

| Source term | Target equivalent | DNT (`true` or blank) |
|---|---|---|
| `<source>` | `<target>` | |
| `<brand>` | | `true` |

The Office Translator path uses a two-column TSV per source-target pair. The LLM receives selections as guidance, not a guarantee. Translator Text on the PDF path does not apply the glossary.
