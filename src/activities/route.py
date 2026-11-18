# SPDX-License-Identifier: MIT
from hashlib import sha256

from services import jobs_table, storage, translation_engines, translation_work


def reconstruct(job):
    language = job["targetLanguage"]
    container = f"target-{job['jobId']}"
    path = f"{language}/{job['fileName']}"
    if job.get("textTranslation"):
        translated = storage.get_json(job["jobId"], f"translated-{language}")
        content, warnings = translation_work.reconstruct(
            storage.source(job), job["fileName"], translated["translation"]["segments"],
        )
        storage.ensure_container(container)
        storage.put(container, path, content)
        usage = translated["usage"]
    else:
        storage.get(container, path)
        usage, warnings = job["usage"], []
    return {"language": language, "path": path, "usage": usage, "warnings": warnings}


def run(job):
    current = jobs_table.get(job["jobId"])
    engine = translation_engines.config(job.get("engine", "translator"))
    outputs = job["outputs"]
    usage = {}
    for metric in ("charactersCharged", "charactersSubmitted", "inputTokens", "outputTokens", "reasoningTokens"):
        values = [output["usage"].get(metric) for output in outputs]
        usage[metric] = sum(values) if all(value is not None for value in values) else None
    report = {
        "jobId": job["jobId"],
        "sourceFile": job["fileName"],
        "sourceSha256": sha256(storage.source(job)).hexdigest(),
        "sourceLanguage": current.get("detectedLanguage") or job.get("sourceLanguage"),
        "targetLanguages": job["targetLanguages"],
        "engine": engine.engine,
        "model": engine.model_name,
        "deployment": engine.deployment_name,
        "durations": {key.removeprefix("duration_"): value for key, value in current.items()
                      if key.startswith("duration_")},
        "usage": usage,
        "estimatedCostUSD": translation_engines.estimate_cost(
            engine, input_tokens=usage.get("inputTokens"), output_tokens=usage.get("outputTokens"),
            characters=usage.get("charactersCharged"),
        ),
        "warnings": list(dict.fromkeys(warning for output in outputs for warning in output["warnings"])),
        "outputs": outputs,
        "status": "complete",
    }
    storage.put_json(job["jobId"], "report", report)
    jobs_table.update(job["jobId"], reportPath=f"{job['jobId']}/report.json",
                      resultPath=outputs[0]["path"], resultContainer=f"target-{job['jobId']}")
    return {"status": "complete"}
