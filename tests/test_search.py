import json
import pytest
from meddraft_ai.search.academic_search import (
    search_pubmed_api,
    search_crossref_api,
    search_semantic_scholar_api,
    search_europe_pmc
)
from meddraft_ai.search.research_orchestrator import clean_title, title_similarity

def test_title_clean_and_similarity():
    t1 = "Impact of SGLT2 Inhibitors in Type 2 Diabetes: A Meta-Analysis"
    t2 = "Impact of sglt2 inhibitors in type 2 diabetes a meta analysis"
    assert clean_title(t1) == clean_title(t2)
    assert title_similarity(t1, t2) > 0.95

def test_pubmed_search():
    res = search_pubmed_api("diabetes", limit=2)
    data = json.loads(res)
    assert "results" in data
    assert data["source"] == "PubMed"

def test_crossref_search():
    res = search_crossref_api("cardiology", limit=2)
    data = json.loads(res)
    assert "results" in data
    assert data["source"] == "CrossRef"

def test_europe_pmc_search():
    res = search_europe_pmc("hypertension", limit=2)
    data = json.loads(res)
    assert "results" in data
    assert data["source"] == "Europe PMC"
