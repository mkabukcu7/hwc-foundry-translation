# SPDX-License-Identifier: MIT
from services import extraction, glossary, jobs_table, languages, storage, translation_engines
from services.translator_client import Translator


def run(job):
    engine = translation_engines.config(job.get("engine", "translator"))
    extracted = extraction.extract(storage.source(job), job["fileName"], job["jobId"])
    text = "\n".join(segment["text"] for segment in extracted["segments"])
    language = languages.validate(job.get("sourceLanguage") or Translator().detect(text, job["jobId"]))
    targets = languages.targets(job["targetLanguages"], language)
    text_mode = engine.engine == "llm" or job["fileName"].lower().endswith(".pdf")
    glossary_targets = []
    terms_by_target = {}
    if engine.engine == "llm" or not text_mode:
        raw = glossary.load(job.get("glossaryName", ""), job["jobId"])
        for target in targets:
            terms = glossary.terms(raw, language, target, job["jobId"])
            terms_by_target[target] = terms
            if terms and not text_mode:
                storage.put("glossaries", f"{job['jobId']}/{target}.tsv", glossary.tsv(terms),
                            "text/tab-separated-values; charset=utf-8")
                glossary_targets.append(target)
    if text_mode:
        storage.put_json(job["jobId"], "prepared", {"extraction": extracted, "terms": terms_by_target})
    jobs_table.update(job["jobId"], detectedLanguage=language)
    return {"sourceLanguage": language, "targetLanguages": targets, "glossaryTargets": glossary_targets}
