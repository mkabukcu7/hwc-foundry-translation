# SPDX-License-Identifier: MIT
import csv
import io
import logging
import os
import re
from pathlib import Path

from services import languages
from services.config import ConfigurationError

LOG = logging.getLogger(__name__)
APP_ROOT = Path(__file__).resolve().parents[1]


def available():
    if os.getenv("GLOSSARY_MODE", "static") == "none":
        return []
    configured = os.getenv("GLOSSARY_PATH")
    local = APP_ROOT.parent / "glossary"
    packaged = APP_ROOT / "glossary"
    directory = Path(configured).parent if configured else local if local.is_dir() else packaged
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.csv")
                  if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", path.stem))


def load(name="", job_id=""):
    mode = os.getenv("GLOSSARY_MODE", "static")
    if mode == "none":
        return ""
    if mode != "static":
        raise ConfigurationError("GLOSSARY_MODE must be none or static")
    configured = os.getenv("GLOSSARY_PATH")
    local = APP_ROOT.parent / "glossary" / "sample.csv"
    packaged = APP_ROOT / "glossary" / "sample.csv"
    default = Path(configured) if configured else local if local.is_file() else packaged
    if name and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("Invalid glossary name")
    path = default.with_name(f"{name}.csv") if name else default
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        LOG.warning("jobId=%s glossary_unreadable", job_id)
        raise ConfigurationError("The selected glossary is unavailable or not UTF-8") from None


def terms(data, source, target, job_id=""):
    if not data:
        return []
    reader = csv.DictReader(io.StringIO(data.removeprefix("\ufeff")), strict=True)
    headers = reader.fieldnames or []
    if not headers or len(headers) != len(set(headers)):
        raise ValueError("Glossary must have a unique header for each language code")
    if set(headers) - {*languages.enabled(), "dnt"}:
        LOG.warning("jobId=%s glossary contains columns outside SUPPORTED_LANGUAGES; ignoring them", job_id)
    if source not in headers:
        return []
    result = {}
    for row in reader:
        source_text = (row.get(source) or "").strip()
        keep = (row.get("dnt") or "").strip().casefold() == "true"
        target_text = source_text if keep else (row.get(target) or "").strip()
        if not source_text or not target_text:
            continue
        if any(c in source_text or c in target_text for c in "\t\r\n"):
            raise ValueError("Glossary terms cannot contain tabs or line breaks")
        result[source_text] = {"term": source_text, "target": target_text, "action": "keep" if keep else "map"}
    return list(result.values())


def tsv(entries):
    return "".join(f"{entry['term']}\t{entry['target']}\n" for entry in entries).encode("utf-8")
