# SPDX-License-Identifier: MIT
from services import glossary


def test_dnt_is_identity_even_when_target_column_is_missing():
    entries = glossary.terms("\ufeffen,fr,dnt\nContoso,,true\nwebinar,webinaire,\n", "en", "de")
    assert glossary.tsv(entries) == b"Contoso\tContoso\n"
    assert entries[0]["action"] == "keep"


def test_reverse_and_missing_source_column():
    csv = "en,fr,dnt\nwebinar,webinaire,\n"
    assert glossary.tsv(glossary.terms(csv, "fr", "en")) == b"webinaire\twebinar\n"
    assert glossary.terms(csv, "de", "en") == []


def test_unsupported_columns_are_ignored_and_logged(caplog):
    entries = glossary.terms("en,pt-PT,unused\nlaunch,lançamento,ignored\n", "en", "pt-PT", "job")
    assert glossary.tsv(entries).decode() == "launch\tlançamento\n"
    assert "jobId=job" in caplog.text
    assert "ignoring" in caplog.text


def test_selection_and_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("GLOSSARY_PATH", str(tmp_path / "default.csv"))
    (tmp_path / "region.csv").write_text("en,fr\nwebinar,webinaire\n", encoding="utf-8-sig")
    assert glossary.load("region").startswith("en,fr")
    monkeypatch.setenv("GLOSSARY_MODE", "none")
    assert glossary.load("region") == ""


def test_packaged_sample_matches_checkout_and_loads_without_repository(monkeypatch, tmp_path):
    root = glossary.APP_ROOT
    sample = root / "glossary" / "sample.csv"
    assert sample.read_bytes() == (root.parent / "glossary" / "sample.csv").read_bytes()
    app_root = tmp_path / "app"
    packaged = app_root / "glossary" / "sample.csv"
    packaged.parent.mkdir(parents=True)
    packaged.write_bytes(sample.read_bytes())
    monkeypatch.setattr(glossary, "APP_ROOT", app_root)
    monkeypatch.delenv("GLOSSARY_PATH", raising=False)
    monkeypatch.delenv("GLOSSARY_MODE", raising=False)
    assert glossary.load("sample") == sample.read_text(encoding="utf-8-sig")
