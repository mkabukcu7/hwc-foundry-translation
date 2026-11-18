# SPDX-License-Identifier: MIT
from services import jobs_table, storage, translation_engines, translation_work
from services.translator_client import TERMINAL, Translator


def start(job):
    target = job["targetLanguage"]
    engine = translation_engines.config(job.get("engine", "translator"))
    if engine.engine == "llm" or job["fileName"].lower().endswith(".pdf"):
        prepared = storage.get_json(job["jobId"], "prepared")
        translated, usage = translation_work.translate_text(
            prepared["extraction"], job["sourceLanguage"], job["targetLanguage"], job["jobId"],
            engine, prepared["terms"].get(target, []),
        )
        storage.put_json(job["jobId"], f"translated-{target}", {"translation": translated, "usage": usage})
        return {"textTranslation": True}
    current = jobs_table.get(job["jobId"])
    operation_key = f"operationUrl_{target.replace('-', '_')}"
    if current.get(operation_key):
        return {"operationUrl": current[operation_key]}
    storage.ensure_container(f"target-{job['jobId']}")
    operation = Translator().submit(
        job, storage.url("source", job["sourcePath"]),
        storage.url(f"target-{job['jobId']}", f"{target}/{job['fileName']}"),
        storage.url("glossaries", f"{job['jobId']}/{target}.tsv") if target in job["glossaryTargets"] else None,
    )
    jobs_table.update(job["jobId"], **{operation_key: operation})
    return {"operationUrl": operation}


def poll(job):
    translator = Translator()
    status = translator.poll(job["operationUrl"], job["jobId"])
    state = status["status"]
    if state not in TERMINAL:
        return {"status": state}
    documents = translator.documents(job["operationUrl"], job["jobId"])
    storage.put_json(job["jobId"], f"translation-{job['targetLanguage']}", {"batch": status, "documents": documents})
    chars = [document.get("characterCharged") for document in documents]
    if state != "Succeeded" or not documents or any(d["status"] != "Succeeded" for d in documents):
        raise ValueError("Translator failed one or more documents; see protected translation status report")
    return {"status": state, "usage": {"charactersCharged": sum(chars) if all(c is not None for c in chars) else None,
                                       "glossaryApplied": job["targetLanguage"] in job["glossaryTargets"]}}
