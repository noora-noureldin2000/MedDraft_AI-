import re

import pytest
from pathlib import Path
from meddraft_ai.extraction.pdf_reader import PDFReader
from meddraft_ai.extraction.citation_tracker import (
    DOI_PATTERN,
    strip_doi_punctuation,
)

def test_pdf_reader_non_existent():
    with pytest.raises(FileNotFoundError):
        PDFReader("non_existent_file.pdf")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("10.1136/bmj.e075707.", "10.1136/bmj.e075707"),
        ("10.1016/S0140-6736(20)30183-5).", "10.1016/S0140-6736(20)30183-5"),
        # Balanced parentheses are part of the DOI and must be preserved.
        ("10.1016/S0002-9394(02)02220-1", "10.1016/S0002-9394(02)02220-1"),
        ("https://doi.org/10.1038/nature12373;", "https://doi.org/10.1038/nature12373"),
    ],
)
def test_strip_doi_punctuation(raw, expected):
    assert strip_doi_punctuation(raw) == expected


def test_doi_pattern_matches_trailing_punctuation_then_strips_it():
    text = "Significant (doi:10.1016/S0140-6736(20)30183-5). Another 10.1136/bmj.e075707. End."
    dois = [strip_doi_punctuation(m.group(0)) for m in re.finditer(DOI_PATTERN, text)]
    assert dois == ["10.1016/S0140-6736(20)30183-5", "10.1136/bmj.e075707"]
