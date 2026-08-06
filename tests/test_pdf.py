import pytest
from pathlib import Path
from meddraft_ai.extraction.pdf_reader import PDFReader

def test_pdf_reader_non_existent():
    with pytest.raises(FileNotFoundError):
        PDFReader("non_existent_file.pdf")
