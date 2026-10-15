from __future__ import annotations

import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel
from meddraft_ai.extraction.schemas import GroundedField

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    fuzz = None  # type: ignore[assignment]
    RAPIDFUZZ_AVAILABLE = False


class GroundingVerifier:
    """Verifies that every GroundedField exists verbatim in source text/tables
    and contains zero hallucinated or rounded numbers.
    """

    def __init__(
        self,
        page_texts: Dict[int, str],
        tables_json: Optional[List[Dict[str, Any]]] = None,
        pdf_annotator: Optional[Any] = None,
        fuzzy_threshold: float = 90.0,
    ):
        self.page_texts = page_texts
        self.tables_json = tables_json or []
        self.annotator = pdf_annotator
        self.fuzzy_threshold = fuzzy_threshold

    @staticmethod
    def normalize_text(text: str) -> str:
        """Applies robust character normalisation for PDF text comparison."""
        if not text:
            return ""
        text = unicodedata.normalize("NFC", text)
        text = text.replace("\u00ad", "")  # Soft hyphen
        text = re.sub(r"-\s*\n\s*", "", text)  # Hyphenated line break
        text = (
            text.replace("–", "-")
            .replace("—", "-")
            .replace("−", "-")
            .replace("’", "'")
            .replace("“", '"')
            .replace("”", '"')
            .replace("\u00a0", " ")
        )
        return re.sub(r"\s+", " ", text).strip().lower()

    @staticmethod
    def extract_numeric_tokens(val: Any) -> List[str]:
        """Extracts all integer and decimal numbers from structured value or string."""
        if val is None:
            return []
        if isinstance(val, BaseModel):
            dump = val.model_dump(exclude={"source_table_id", "timepoint", "analysis_population"})
            raw_str = json.dumps(dump)
        elif isinstance(val, (list, dict)):
            raw_str = json.dumps(val)
        else:
            raw_str = str(val)

        # Remove internal thousands separators (e.g. 1,200 -> 1200)
        raw_str = re.sub(r"(?<=\d),(?=\d{3}\b)", "", raw_str)
        return re.findall(r"\d+(?:\.\d+)?", raw_str)

    def _fuzzy_similarity(self, needle: str, haystack: str) -> float:
        """Calculates partial substring similarity score between needle and haystack."""
        if not needle or not haystack:
            return 0.0
        if needle in haystack:
            return 100.0
        if RAPIDFUZZ_AVAILABLE and fuzz is not None:
            return float(fuzz.partial_ratio(needle, haystack))
        matcher = SequenceMatcher(None, needle, haystack)
        match = matcher.find_longest_match(0, len(needle), 0, len(haystack))
        return (match.size / len(needle)) * 100.0 if needle else 0.0

    def _build_candidate_search_texts(self, page_no: int, section_header: Optional[str]) -> List[str]:
        """Builds page text, cross-page boundary windows, and table texts."""
        candidates: List[str] = []
        target_page = self.page_texts.get(page_no, "")
        norm_target = self.normalize_text(target_page)
        if norm_target:
            candidates.append(norm_target)

        # Cross-page boundary stitches (tail of prev + head of curr; tail of curr + head of next)
        prev_page = self.page_texts.get(page_no - 1, "")
        if prev_page and target_page:
            boundary_prev = self.normalize_text(prev_page[-600:] + " " + target_page[:600])
            candidates.append(boundary_prev)

        next_page = self.page_texts.get(page_no + 1, "")
        if next_page and target_page:
            boundary_next = self.normalize_text(target_page[-600:] + " " + next_page[:600])
            candidates.append(boundary_next)

        # Table content on that page or matching section header
        for tbl in self.tables_json:
            tbl_page = tbl.get("page")
            tbl_id = tbl.get("table_id")
            if tbl_page == page_no or (section_header and tbl_id == section_header):
                tbl_md = self.normalize_text(tbl.get("markdown", ""))
                tbl_records = self.normalize_text(json.dumps(tbl.get("records", [])))
                if tbl_md:
                    candidates.append(tbl_md)
                if tbl_records:
                    candidates.append(tbl_records)

        return candidates

    def verify_field(self, field_path: str, field: GroundedField[Any]) -> Tuple[bool, Optional[str]]:
        """Verifies a single GroundedField in-place, returning (success, error_message)."""
        if field.status == "NOT_REPORTED":
            field.value = None
            field.verified_in_source = True
            field.verification_note = "Verified as NOT_REPORTED."
            return True, None

        if field.status == "UNCLEAR":
            field.verified_in_source = False
            field.verification_note = "Marked UNCLEAR."
            return True, None

        if not field.verbatim_quote or len(field.verbatim_quote.strip()) < 4:
            field.verified_in_source = False
            err = f"[{field_path}] REPORTED status requires verbatim_quote (minimum 4 characters)."
            field.verification_note = err
            return False, err

        if not field.page_number or field.page_number not in self.page_texts:
            field.verified_in_source = False
            err = f"[{field_path}] Invalid page_number ({field.page_number}). Document has pages {sorted(self.page_texts.keys())}."
            field.verification_note = err
            return False, err

        norm_quote = self.normalize_text(field.verbatim_quote)
        candidates = self._build_candidate_search_texts(field.page_number, field.section_header)

        best_score = max((self._fuzzy_similarity(norm_quote, cand) for cand in candidates), default=0.0)

        if best_score < self.fuzzy_threshold:
            field.verified_in_source = False
            err = (
                f"[{field_path}] Verbatim quote not found on page {field.page_number} "
                f"(best match score: {best_score:.1f}% < {self.fuzzy_threshold}%). "
                f"Ensure quote is an exact character substring."
            )
            field.verification_note = err
            return False, err

        # Numeric exact-match check
        value_numbers = self.extract_numeric_tokens(field.value)
        if value_numbers:
            corpus = norm_quote + " " + " ".join(candidates)
            corpus_numbers: Set[str] = set(self.extract_numeric_tokens(corpus))
            missing_nums = [n for n in value_numbers if n not in corpus_numbers]

            if missing_nums:
                field.verified_in_source = False
                err = (
                    f"[{field_path}] Numeric fidelity failure: numbers {missing_nums} in extracted value "
                    f"do not appear in quote or table on page {field.page_number}. Do not round or calculate numbers."
                )
                field.verification_note = err
                return False, err

        # Success: annotate if annotator available
        if self.annotator is not None:
            try:
                self.annotator.highlight_sentences([field.verbatim_quote])
            except Exception as exc:
                logger.debug("PDFAnnotator highlight skipped: %s", exc)

        field.verified_in_source = True
        field.verification_note = f"Verified (match={best_score:.1f}%)"
        return True, None

    def verify_model(self, model: BaseModel) -> List[str]:
        """Recursively validates every GroundedField within a Pydantic model."""
        errors: List[str] = []
        for name, field_info in model.__class__.model_fields.items():
            attr = getattr(model, name, None)
            if isinstance(attr, GroundedField):
                ok, err = self.verify_field(name, attr)
                if not ok and err:
                    errors.append(err)
            elif isinstance(attr, list):
                for idx, item in enumerate(attr):
                    if isinstance(item, GroundedField):
                        ok, err = self.verify_field(f"{name}[{idx}]", item)
                        if not ok and err:
                            errors.append(err)
            elif isinstance(attr, BaseModel):
                sub_errs = self.verify_model(attr)
                errors.extend(sub_errs)
        return errors

    def downgrade_unverified_fields(self, model: BaseModel) -> None:
        """Downgrades any REPORTED field failing verification to UNCLEAR."""
        for name, field_info in model.__class__.model_fields.items():
            attr = getattr(model, name, None)
            if isinstance(attr, GroundedField) and attr.status == "REPORTED" and not attr.verified_in_source:
                logger.warning("Downgrading unverified field '%s' to UNCLEAR to preserve zero-hallucination contract.", name)
                attr.status = "UNCLEAR"
                attr.verification_note = f"DOWNGRADED_AFTER_RETRIES: {attr.verification_note}"
            elif isinstance(attr, list):
                for idx, item in enumerate(attr):
                    if isinstance(item, GroundedField) and item.status == "REPORTED" and not item.verified_in_source:
                        logger.warning("Downgrading unverified field '%s[%d]' to UNCLEAR.", name, idx)
                        item.status = "UNCLEAR"
                        item.verification_note = f"DOWNGRADED_AFTER_RETRIES: {item.verification_note}"
            elif isinstance(attr, BaseModel):
                self.downgrade_unverified_fields(attr)
