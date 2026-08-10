"""
Tests for academic search functions (meddraft_ai/search/academic_search.py).

H-12 fix: all external HTTP calls are mocked — no live API requests.
All tests run offline, instantly, and deterministically.

test-guard compliance:
  - Rule 2: mocked at the urllib / requests boundary only
  - Rule 3: one scenario per test; data-driven for variants
  - Rule 5: names describe scenario and expected outcome
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO

from meddraft_ai.search.academic_search import (
    search_pubmed_api,
    search_crossref_api,
    search_europe_pmc,
)
from meddraft_ai.search.research_orchestrator import clean_title, title_similarity


# ---------------------------------------------------------------------------
# Pure logic tests (no I/O) — always run
# ---------------------------------------------------------------------------

class TestCleanTitleAndSimilarity:
    def test_clean_title_removes_punctuation_and_lowercases(self):
        t1 = "Impact of SGLT2 Inhibitors in Type 2 Diabetes: A Meta-Analysis"
        t2 = "Impact of sglt2 inhibitors in type 2 diabetes a meta analysis"
        assert clean_title(t1) == clean_title(t2)

    def test_title_similarity_near_identical_strings(self):
        t1 = "Dapagliflozin and Cardiovascular Outcomes"
        t2 = "Dapagliflozin and Cardiovascular Outcomes"
        assert title_similarity(t1, t2) > 0.95

    def test_title_similarity_different_strings_returns_low_score(self):
        assert title_similarity("diabetes", "oncology treatment") < 0.5


# ---------------------------------------------------------------------------
# PubMed — mocked HTTP (H-12 fix)
# ---------------------------------------------------------------------------

PUBMED_MOCK_RESPONSE = {
    "esearchresult": {
        "idlist": ["12345678"]
    }
}

PUBMED_SUMMARY_MOCK = {
    "result": {
        "uids": ["12345678"],
        "12345678": {
            "uid": "12345678",
            "title": "Effects of SGLT2 inhibitors on glycemic control",
            "source": "New England Journal of Medicine",
            "pubdate": "2023",
            "authors": [{"name": "Smith J"}],
            "articleids": [{"idtype": "doi", "value": "10.1056/test"}],
        }
    }
}


class TestSearchPubmedApiWithMock:
    def _make_mock_urlopen(self, payloads: list[dict]):
        """Return a context manager mock that yields successive responses."""
        call_count = [0]

        class FakeResponse:
            def __init__(self, data):
                self._data = json.dumps(data).encode()

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        def side_effect(req, timeout=None):
            idx = call_count[0]
            call_count[0] += 1
            return FakeResponse(payloads[idx % len(payloads)])

        return side_effect

    def test_returns_pubmed_source_on_success(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=self._make_mock_urlopen([PUBMED_MOCK_RESPONSE, PUBMED_SUMMARY_MOCK]),
        ):
            result = search_pubmed_api("diabetes", limit=1)
        data = json.loads(result)
        assert data["source"] == "PubMed"
        assert "results" in data

    def test_returns_empty_results_on_api_error(self):
        """When the network call raises, the function returns a JSON error envelope."""
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = search_pubmed_api("diabetes", limit=1)
        data = json.loads(result)
        assert data["source"] == "PubMed"
        assert data["count"] == 0


# ---------------------------------------------------------------------------
# CrossRef — mocked HTTP (H-12 fix, M-03 fix verification)
# ---------------------------------------------------------------------------

CROSSREF_MOCK_RESPONSE = {
    "message": {
        "items": [
            {
                "title": ["Test Article Title"],
                "author": [{"given": "Jane", "family": "Doe"}],
                "container-title": ["Journal of Medicine"],
                "published-print": {"date-parts": [[2023]]},
                "DOI": "10.1234/test",
                "URL": "https://doi.org/10.1234/test",
            }
        ]
    }
}

CROSSREF_NULL_AUTHOR_RESPONSE = {
    "message": {
        "items": [
            {
                "title": ["No Author Article"],
                # author key is present but explicitly None (M-03 regression test)
                "author": None,
                "container-title": ["Journal X"],
                "published-print": {"date-parts": [[2022]]},
                "DOI": "10.9999/noauthor",
                "URL": "https://doi.org/10.9999/noauthor",
            }
        ]
    }
}


class TestSearchCrossrefApiWithMock:
    def _urlopen_returning(self, payload: dict):
        class FakeResp:
            def read(self):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        return lambda *a, **kw: FakeResp()

    def test_returns_crossref_source_on_success(self):
        with patch("urllib.request.urlopen", self._urlopen_returning(CROSSREF_MOCK_RESPONSE)):
            result = search_crossref_api("cardiology", limit=1)
        data = json.loads(result)
        assert data["source"] == "CrossRef"
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Test Article Title"

    def test_null_author_field_does_not_raise_type_error(self):
        """M-03 fix: author=None must be treated as empty list, not raise TypeError."""
        with patch("urllib.request.urlopen", self._urlopen_returning(CROSSREF_NULL_AUTHOR_RESPONSE)):
            result = search_crossref_api("any query", limit=1)
        data = json.loads(result)
        assert data["count"] == 1
        # Authors should be empty string or empty list result, not an error
        assert data["results"][0]["authors"] == ""

    def test_returns_error_envelope_on_network_failure(self):
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            result = search_crossref_api("oncology", limit=1)
        data = json.loads(result)
        assert "error" in data
        assert data["count"] == 0


# ---------------------------------------------------------------------------
# Europe PMC — mocked HTTP (H-12 fix)
# ---------------------------------------------------------------------------

EUROPE_PMC_MOCK = {
    "resultList": {
        "result": [
            {
                "pmid": "99999999",
                "title": "Hypertension and RAAS inhibitors",
                "authorString": "Jones A, Smith B",
                "journalTitle": "Heart Journal",
                "pubYear": "2023",
                "doi": "10.1111/hyp.test",
                "isOpenAccess": "Y",
            }
        ]
    }
}


class TestSearchEuropePmcWithMock:
    def test_returns_europe_pmc_source(self):
        class FakeResp:
            def read(self):
                return json.dumps(EUROPE_PMC_MOCK).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", lambda *a, **kw: FakeResp()):
            result = search_europe_pmc("hypertension", limit=1)
        data = json.loads(result)
        assert data["source"] == "Europe PMC"
        assert data["count"] >= 1
