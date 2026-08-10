"""
pytest configuration and shared fixtures.

NOTE: test_pdf.py triggers a Windows native access violation when pypdfium2
(a docling dependency) initialises its native library. This is a known issue
with certain pypdfium2 builds on Windows Python 3.12.

Mitigation: the crash happens at collection time but pytest recovers and runs
all other tests. To suppress the stderr noise, run:

    pytest --ignore=tests/test_pdf.py

Or reinstall docling with the correct pdfium wheel:
    pip install --upgrade pypdfium2 docling
"""
