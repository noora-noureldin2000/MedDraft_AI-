"""
Figure OCR with image preprocessing and consensus scoring across multi-PSM modes.

Rather than a fragile "longest OCR wins" heuristic (which frequently selects
noisy junk on charts/plots), this module:
1. Preprocesses figure images: Grayscale + 2x Lanczos upscale + autocontrast
2. Runs Tesseract across multiple PSM modes (3: auto, 6: uniform block, 11: sparse text)
3. Evaluates consensus: scores each candidate by token overlap with other candidates
   and alphanumeric density.
4. Persists per-figure txt files and `{doc}_figure_ocr.json`.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from meddraft_ai.extraction.evidence import FigureEvidence

logger = logging.getLogger(__name__)


def select_consensus_candidate(candidates: List[str]) -> str:
    """Select the best candidate among multi-PSM outputs using consensus and density.

    Scoring criteria:
    - Token overlap with other candidates (consensus agreement)
    - Alphanumeric density (discourages repeating punctuation / noise artefacts)
    """
    valid = [c.strip() for c in candidates if c and c.strip()]
    if not valid:
        return ""
    if len(valid) == 1:
        return valid[0]

    # Tokenise each candidate into alphanumeric tokens
    token_sets = [set(re.findall(r"[a-zA-Z0-9]+(?:\.[0-9]+)?", c.lower())) for c in valid]

    scores: List[float] = []
    for i, text in enumerate(valid):
        tokens_i = token_sets[i]
        if not tokens_i:
            scores.append(0.0)
            continue

        # 1. Consensus overlap with other candidate token sets
        overlap_score = 0.0
        for j, tokens_j in enumerate(token_sets):
            if i != j and tokens_j:
                intersection = tokens_i & tokens_j
                union = tokens_i | tokens_j
                overlap_score += (len(intersection) / len(union)) if union else 0.0

        # 2. Alphanumeric density: ratio of letters/digits to total length
        total_len = len(text)
        alnum_count = sum(1 for ch in text if ch.isalnum())
        density = (alnum_count / total_len) if total_len > 0 else 0.0

        # Penalise extreme short or extremely long garbage strings
        length_penalty = 1.0
        if alnum_count < 3:
            length_penalty = 0.1

        composite = (overlap_score * 0.7 + density * 0.3) * length_penalty
        scores.append(composite)

    best_idx = max(range(len(scores)), key=lambda idx: scores[idx])
    return valid[best_idx]


class FigureOCR:
    """Multi-PSM figure OCR extractor with consensus selection."""

    PSM_MODES: List[int] = [3, 6, 11]

    def __init__(
        self,
        tesseract_cmd: str = "tesseract",
        lang: str = "eng",
        output_dir: Optional[Path] = None,
    ):
        self.tesseract_cmd = tesseract_cmd
        self.lang = lang
        self.output_dir = output_dir

    def preprocess_image(self, img_path: Path):
        """Grayscale, 2x Lanczos upscale, and autocontrast enhancement."""
        try:
            from PIL import Image, ImageOps
            with Image.open(img_path) as img:
                # Convert to grayscale
                gray = img.convert("L")
                # 2x Upscale with Lanczos filter
                new_size = (gray.width * 2, gray.height * 2)
                upscaled = gray.resize(new_size, Image.Resampling.LANCZOS)
                # Autocontrast
                enhanced = ImageOps.autocontrast(upscaled)
                return enhanced
        except Exception as exc:
            logger.debug("Image preprocessing failed for %s: %s", img_path, exc)
            try:
                from PIL import Image
                return Image.open(img_path)
            except Exception:
                return None

    def ocr_single_figure(self, figure: FigureEvidence) -> FigureEvidence:
        """Runs multi-PSM OCR on a single figure, populating candidates and consensus text."""
        img_p = Path(figure.image_path)
        if not img_p.exists():
            logger.debug("Figure image not found: %s", img_p)
            return figure

        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        except ImportError:
            logger.debug("pytesseract unavailable; skipping figure OCR")
            return figure

        processed_img = self.preprocess_image(img_p)
        if processed_img is None:
            return figure

        candidates: List[str] = []
        for psm in self.PSM_MODES:
            try:
                config = f"--oem 3 --psm {psm}"
                text = pytesseract.image_to_string(processed_img, lang=self.lang, config=config)
                if text and text.strip():
                    candidates.append(text.strip())
            except Exception as exc:
                logger.debug("Tesseract PSM %d failed on %s: %s", psm, img_p.name, exc)

        figure.ocr_candidates = candidates
        figure.ocr_text = select_consensus_candidate(candidates)

        # Optionally persist individual figure text
        if self.output_dir:
            txt_path = self.output_dir / f"{img_p.stem}.ocr.txt"
            try:
                txt_path.write_text(figure.ocr_text, encoding="utf-8")
            except Exception:
                pass

        return figure

    def process_all(
        self,
        figures: List[FigureEvidence],
        doc_name: str = "document",
    ) -> List[FigureEvidence]:
        """Process all figures and persist summary JSON."""
        processed: List[FigureEvidence] = []
        for fig in figures:
            processed.append(self.ocr_single_figure(fig))

        if self.output_dir:
            summary_path = self.output_dir / f"{doc_name}_figure_ocr.json"
            summary_data = {
                "document": doc_name,
                "figures_count": len(figures),
                "figures": [
                    {
                        "figure_id": f.figure_id,
                        "page": f.page,
                        "image_path": f.image_path,
                        "caption": f.caption,
                        "ocr_text": f.ocr_text,
                        "candidate_count": len(f.ocr_candidates),
                    }
                    for f in processed
                ],
            }
            try:
                summary_path.write_text(
                    json.dumps(summary_data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning("Failed to save figure OCR summary: %s", exc)

        return processed
