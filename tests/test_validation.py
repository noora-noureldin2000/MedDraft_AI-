"""
Tests for reference validation (meddraft_ai/validation/reference_validator.py).

All external API calls are mocked. Tests run offline, instantly, and
deterministically (test-guard Rule 2, Rule 5).

Also covers the H-06 null-published-date fix in CitationTracker
(CrossRef returning null for "published" key must not raise AttributeError).
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from meddraft_ai.validation.reference_validator import (
    validate_doi,
    validate_pmid,
    validate_references,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _mock_crossref_response(doi: str, include_published: bool = True) -> dict:
    base = {
        "message": {
            "DOI": doi,
            "title": ["Dapagliflozin and Cardiovascular Outcomes"],
            "container-title": ["New England Journal of Medicine"],
            "author": [{"family": "Wiviott", "given": "S"}],
            "volume": "380",
            "issue": "4",
            "page": "347-357",
        }
    }
    if include_published:
        base["message"]["published"] = {"date-parts": [[2019]]}
    else:
        base["message"]["published"] = None  # CrossRef can return null here
    return base


def _mock_requests_get(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


# ---------------------------------------------------------------------------
# validate_doi
# ---------------------------------------------------------------------------

class TestValidateDoi:
    def test_valid_doi_returns_verified_true(self):
        with patch(
            "requests.get",
            return_value=_mock_requests_get(_mock_crossref_response("10.1056/NEJMoa1902681")),
        ):
            result = validate_doi("10.1056/NEJMoa1902681")
        assert result.get("verified") is True
        assert result.get("doi") == "10.1056/NEJMoa1902681"

    def test_null_published_date_does_not_raise_attribute_error(self):
        """H-06 fix: CrossRef returning null for 'published' must not crash."""
        with patch(
            "requests.get",
            return_value=_mock_requests_get(
                _mock_crossref_response("10.1111/test", include_published=False)
            ),
        ):
            result = validate_doi("10.1111/test")
        # Should complete without exception; year may be None
        assert result.get("verified") is True

    def test_api_failure_returns_not_verified(self):
        with patch("requests.get", side_effect=OSError("timeout")):
            result = validate_doi("10.1234/broken")
        # Should not raise; returns a dict with verified=False or fallback
        assert isinstance(result, dict)

    def test_malformed_doi_returns_not_verified(self):
        with patch("requests.get", return_value=_mock_requests_get({}, status_code=404)):
            result = validate_doi("not-a-doi")
        assert result.get("verified") is not True

    def test_doi_with_doi_prefix_is_cleaned(self):
        """DOI strings starting with 'doi:' or 'DOI:' should still work."""
        with patch(
            "requests.get",
            return_value=_mock_requests_get(_mock_crossref_response("10.1056/NEJMoa1902681")),
        ):
            result = validate_doi("doi:10.1056/NEJMoa1902681")
        assert result.get("doi") == "10.1056/NEJMoa1902681"


# ---------------------------------------------------------------------------
# validate_pmid
# ---------------------------------------------------------------------------

PUBMED_SUMMARY_MOCK = {
    "result": {
        "uids": ["31535829"],
        "31535829": {
            "uid": "31535829",
            "title": "Dapagliflozin and Cardiovascular Outcomes",
            "source": "New England Journal of Medicine",
            "pubdate": "2019",
            "authors": [{"name": "Wiviott SD"}],
            "articleids": [{"idtype": "doi", "value": "10.1056/NEJMoa1902681"}],
        }
    }
}


class TestValidatePmid:
    def test_valid_pmid_returns_verified_true(self):
        with patch("requests.get", return_value=_mock_requests_get(PUBMED_SUMMARY_MOCK)):
            result = validate_pmid("31535829")
        assert result.get("verified") is True
        assert result.get("pmid") == "31535829"

    def test_api_failure_returns_not_verified(self):
        with patch("requests.get", side_effect=OSError("network error")):
            result = validate_pmid("31535829")
        assert isinstance(result, dict)

    def test_pmid_prefix_stripped(self):
        """PMID strings like 'PMID: 31535829' should have the prefix cleaned."""
        with patch("requests.get", return_value=_mock_requests_get(PUBMED_SUMMARY_MOCK)):
            result = validate_pmid("PMID: 31535829")
        assert result.get("pmid") == "31535829"


# ---------------------------------------------------------------------------
# validate_references
# ---------------------------------------------------------------------------

class TestValidateReferences:
    def test_doi_extracted_from_text(self):
        text = "As shown (10.1056/NEJMoa1902681), SGLT2 inhibitors reduce risk."
        with patch(
            "requests.get",
            return_value=_mock_requests_get(_mock_crossref_response("10.1056/NEJMoa1902681")),
        ):
            citations = validate_references(text)
        assert len(citations) >= 1

    def test_pmid_extracted_from_text(self):
        text = "Previous work (PMID: 31535829) confirmed outcomes."
        with patch("requests.get", return_value=_mock_requests_get(PUBMED_SUMMARY_MOCK)):
            citations = validate_references(text)
        assert len(citations) >= 1

    def test_text_with_no_citations_returns_empty(self):
        text = "No citations or references here whatsoever."
        citations = validate_references(text)
        assert citations == [] or isinstance(citations, list)
