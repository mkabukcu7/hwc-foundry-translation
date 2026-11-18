# SPDX-License-Identifier: MIT
"""Translate a document without starting the Functions host."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from activities.precheck import validate_document
from services import (
    extraction,
    glossary,
    languages,
    local_translation,
    translation_engines,
    translation_work,
)
from services.translator_client import Translator


def translate_file(data, name, source, target, job_id, engine, extracted, terms):
    extension = Path(name).suffix.lower()
    if engine.engine == "translator" and extension != ".pdf":
        return local_translation.translate_document(
            data, name, glossary.tsv(terms), source, target, job_id, engine=engine,
        )
    translated, usage = translation_work.translate_text(extracted, source, target, job_id, engine, terms)
    content, warnings = translation_work.reconstruct(data, name, translated["segments"])
    return content, {**usage, "warnings": warnings}


def run_file(source, output_dir, source_language=None, target_languages=("en",), *,
             engine="translator", glossary_name="", job_id=None, progress=lambda _: None):
    job_id = job_id or uuid4().hex
    if source_language:
        languages.validate(source_language)
    target_languages = languages.targets(target_languages, source_language)
    raw_glossary = (glossary.load(glossary_name, job_id)
                    if engine == "llm" or source.suffix.lower() != ".pdf" else "")
    data = source.read_bytes()
    durations = {}
    started = perf_counter()
    progress("precheck")
    validate_document(data, source.name)
    durations["precheck"] = perf_counter() - started
    settings = translation_engines.config(engine)
    started = perf_counter()
    progress("prepare")
    extracted = extraction.extract(data, source.name, job_id)
    text = "\n".join(segment["text"] for segment in extracted["segments"])
    source_language = languages.validate(source_language or Translator().detect(text, job_id))
    target_languages = languages.targets(target_languages, source_language)
    durations["prepare"] = perf_counter() - started
    directory = output_dir / job_id
    directory.mkdir(parents=True, exist_ok=False)
    outputs, warnings = [], []
    started = perf_counter()
    for target in target_languages:
        progress("translate")
        result, usage = translate_file(
            data, source.name, source_language, target, job_id, settings, extracted,
            glossary.terms(raw_glossary, source_language, target, job_id),
        )
        cost = translation_engines.estimate_cost(
            settings, input_tokens=usage.get("inputTokens"), output_tokens=usage.get("outputTokens"),
            characters=usage.get("charactersCharged"),
        )
        destination = directory / target / source.name
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(result)
        warnings.extend(usage.get("warnings", []))
        outputs.append({"language": target, "path": f"{target}/{source.name}", "usage": usage,
                        "estimatedCostUSD": cost})
    durations["translate"] = perf_counter() - started
    costs = [output["estimatedCostUSD"] for output in outputs]
    report = {
        "jobId": job_id, "status": "complete", "sourceFile": source.name,
        "sourceSha256": sha256(data).hexdigest(), "sourceLanguage": source_language,
        "targetLanguages": list(target_languages), "engine": engine,
        "deployment": settings.deployment_name, "model": settings.model_name,
        "durations": durations, "warnings": warnings, "outputs": outputs,
        "estimatedCostUSD": sum(costs) if all(cost is not None for cost in costs) else None,
    }
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("samples/results/local"))
    parser.add_argument("--source-language")
    parser.add_argument("--target-languages", nargs="+", required=True)
    parser.add_argument("--engine", choices=translation_engines.ENGINES, default="translator")
    parser.add_argument("--glossary-name", default="")
    args = parser.parse_args()
    report = run_file(args.input, args.output_dir, args.source_language, args.target_languages,
                      engine=args.engine, glossary_name=args.glossary_name)
    print(json.dumps({"jobId": report["jobId"], "status": report["status"]}))


if __name__ == "__main__":
    main()
