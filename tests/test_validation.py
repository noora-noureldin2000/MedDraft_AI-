import pytest
from meddraft_ai.validation.reference_validator import validate_doi, validate_pmid, validate_references

def test_validate_doi_valid():
    res = validate_doi("10.1056/NEJMoa1902681")
    assert res.get("verified") is True
    title = res.get("title") or ""
    assert "Dapagliflozin" in title or res.get("doi") == "10.1056/NEJMoa1902681"

def test_validate_pmid_valid():
    res = validate_pmid("31535829")
    assert res.get("verified") is True
    assert res.get("pmid") == "31535829"

def test_validate_references_in_text():
    text = "As shown in recent studies (10.1056/NEJMoa1902681 and PMID: 31535829), SGLT2 inhibitors reduce risk."
    citations = validate_references(text)
    assert len(citations) >= 1
