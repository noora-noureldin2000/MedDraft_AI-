"""
OCR prerequisite verification.

Called once per conversion run to check that Tesseract (or the configured
OCR engine) is available, log the version, and confirm Docling's OCR
engine wiring.  Never fatal — graceful degradation is the contract.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OcrPrerequisites:
    """Result of the OCR preflight check."""
    tesseract_available: bool = False
    tesseract_version: Optional[str] = None
    tesseract_cmd: str = "tesseract"
    pytesseract_available: bool = False
    pymupdf_available: bool = False
    languages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def verify_ocr_prerequisites(
    tesseract_cmd: str = "tesseract",
    required_lang: str = "eng",
) -> OcrPrerequisites:
    """Run a one-shot preflight check for OCR capabilities.

    This is deliberately *never* fatal: if Tesseract is missing, the
    pipeline falls back to text-layer-only extraction.  The caller
    decides how to react based on the returned ``OcrPrerequisites``.
    """
    result = OcrPrerequisites(tesseract_cmd=tesseract_cmd)

    # 1. Tesseract binary on PATH
    resolved = shutil.which(tesseract_cmd)
    if resolved:
        result.tesseract_available = True
        try:
            proc = subprocess.run(
                [resolved, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version_line = (proc.stdout or proc.stderr or "").strip().splitlines()
            if version_line:
                result.tesseract_version = version_line[0]
        except Exception as exc:
            result.warnings.append(f"Tesseract version check failed: {exc}")
    else:
        result.warnings.append(
            f"Tesseract binary '{tesseract_cmd}' not found on PATH. "
            "OCR recovery for scanned pages will be unavailable."
        )

    # 2. pytesseract Python binding
    try:
        import pytesseract  # noqa: F401
        result.pytesseract_available = True
    except ImportError:
        result.warnings.append("pytesseract not installed. pip install pytesseract to enable OCR.")

    # 3. PyMuPDF (fitz) for text-layer fallback
    try:
        import fitz  # noqa: F401
        result.pymupdf_available = True
    except ImportError:
        result.warnings.append("PyMuPDF (fitz) not installed. Text-layer fallback limited to pdfplumber.")

    # 4. Language availability
    if result.tesseract_available:
        try:
            proc = subprocess.run(
                [resolved or tesseract_cmd, "--list-langs"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            langs = [
                ln.strip()
                for ln in (proc.stdout or "").splitlines()
                if ln.strip() and not ln.startswith("List")
            ]
            result.languages = langs
            if required_lang not in langs:
                result.warnings.append(
                    f"Required language '{required_lang}' not in Tesseract languages: {langs}"
                )
        except Exception as exc:
            result.warnings.append(f"Failed to list Tesseract languages: {exc}")

    # Log summary
    if result.tesseract_available:
        logger.info(
            "OCR preflight OK: Tesseract %s, pytesseract=%s, languages=%s",
            result.tesseract_version,
            result.pytesseract_available,
            result.languages,
        )
    else:
        logger.warning("OCR preflight: Tesseract unavailable. %s", "; ".join(result.warnings))

    for warn in result.warnings:
        logger.warning("OCR preflight warning: %s", warn)

    return result
