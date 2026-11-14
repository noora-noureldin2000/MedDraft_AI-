from __future__ import annotations

import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
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
    """Verifies that every GroundedField exists verbatim in source text/tables,
    contains zero hallucinated numbers, and aggregates verified quotes for write-once annotation.
    """

    def __init__(
        self,
        page_texts: Dict[int, str],
        tables_json: Optional[List[Dict[str, Any]]] = None,
        pdf_annotator: Optional[Any] = None,
        fuzzy_threshold: float = 95.0,
        evidence: Optional[Any] = None,
        fuzzy_threshold_ocr: Optional[float] = None,
    ):
        self.page_texts = page_texts
        self.tables_json = tables_json or []
        self.annotator = pdf_annotator
        self.fuzzy_threshold = fuzzy_threshold
        self.fuzzy_threshold_ocr = fuzzy_threshold_ocr or 92.0
        self.verified_quotes: List[str] = []
        # Phase B: EvidenceIndex takes precedence when supplied
        self.evidence = evidence

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

    @classmethod
    def extract_numeric_tokens(cls, val: Any) -> List[str]:
        """Extracts all integer and decimal numbers strictly from values (never dictionary keys)."""
        if val is None:
            return []
        if isinstance(val, BaseModel):
            tokens: List[str] = []
            dump = val.model_dump(exclude={"source_table_id", "timepoint", "analysis_population"})
            for v in dump.values():
                tokens.extend(cls.extract_numeric_tokens(v))
            return tokens
        if isinstance(val, dict):
            tokens: List[str] = []
            for v in val.values():
                tokens.extend(cls.extract_numeric_tokens(v))
            return tokens
        if isinstance(val, list):
            tokens: List[str] = []
            for item in val:
                tokens.extend(cls.extract_numeric_tokens(item))
            return tokens

        raw_str = str(val)
        # Remove internal thousands separators (e.g. 1,200 -> 1200)
        raw_str = re.sub(r"(?<=\d),(?=\d{3}\b)", "", raw_str)
        return re.findall(r"\d+(?:\.\d+)?", raw_str)

    def _fuzzy_similarity(self, needle: str, haystack: str) -> float:
        """Calculates substring match score. Prioritizes exact substring containment."""
        if not needle or not haystack:
            return 0.0
        if needle in haystack:
            return 100.0
        if RAPIDFUZZ_AVAILABLE and fuzz is not None:
            return float(fuzz.partial_ratio(needle, haystack))
        matcher = SequenceMatcher(None, needle, haystack)
        match = matcher.find_longest_match(0, len(needle), 0, len(haystack))
        return (match.size / len(needle)) * 100.0 if needle else 0.0

    def _table_search_texts(self, page_no: int, section_header: Optional[str]) -> List[str]:
        """Normalised markdown/record text for tables on *page_no* or matching *section_header*."""
        texts: List[str] = []
        if self.evidence is not None:
            for tbl in self.evidence.tables:
                same_page = tbl.page == page_no
                same_table = bool(section_header) and tbl.table_id == section_header
                if not (same_page or same_table):
                    continue
                table_markdown = self.normalize_text(tbl.markdown)
                table_records = self.normalize_text(json.dumps(tbl.records, ensure_ascii=False))
                if table_markdown:
                    texts.append(table_markdown)
                if table_records:
                    texts.append(table_records)

        for table in self.tables_json:
            same_page = table.get("page") == page_no
            same_table = bool(section_header) and table.get("table_id") == section_header
            if not (same_page or same_table):
                continue
            table_markdown = self.normalize_text(table.get("markdown", ""))
            table_records = self.normalize_text(json.dumps(table.get("records", [])))
            if table_markdown:
                texts.append(table_markdown)
            if table_records:
                texts.append(table_records)
        return texts

    def _build_candidate_search_texts(self, page_no: int, section_header: Optional[str]) -> List[Tuple[str, str]]:
        """Builds (source_label, normalised_text) pairs for quote matching.

        When an EvidenceIndex is supplied it takes precedence, providing
        candidates from every available engine.  The legacy page_texts path
        is used as fallback so existing tests and callers stay green.
        """
        candidates: List[Tuple[str, str]] = []

        if self.evidence is not None:
            # EvidenceIndex path — union of all engines for this page
            for source, text in self.evidence.page_candidates(page_no):
                norm = self.normalize_text(text)
                if norm:
                    candidates.append((source, norm))

            # Table candidates from EvidenceIndex
            for source, text in self.evidence.table_candidates(page=page_no, table_id=section_header):
                norm = self.normalize_text(text)
                if norm:
                    candidates.append((source, norm))

            # Figure candidates (for figure-derived fields only)
            if section_header and str(section_header).startswith("Figure"):
                for source, text in self.evidence.figure_candidates(page=page_no):
                    norm = self.normalize_text(text)
                    if norm:
                        candidates.append((source, norm))

            # Cross-page boundary stitches from EvidenceIndex
            prev_ev = self.evidence.pages.get(page_no - 1)
            curr_ev = self.evidence.pages.get(page_no)
            next_ev = self.evidence.pages.get(page_no + 1)
            if prev_ev and curr_ev and prev_ev.text and curr_ev.text:
                boundary = self.normalize_text(prev_ev.text[-600:] + " " + curr_ev.text[:600])
                candidates.append(("boundary_prev", boundary))
            if curr_ev and next_ev and curr_ev.text and next_ev.text:
                boundary = self.normalize_text(curr_ev.text[-600:] + " " + next_ev.text[:600])
                candidates.append(("boundary_next", boundary))

            # Also include legacy page_texts as additional candidates
            # (ensures backward-compatibility even when evidence is set)
            target_page = self.page_texts.get(page_no, "")
            norm_legacy = self.normalize_text(target_page)
            if norm_legacy:
                candidates.append(("pdfplumber", norm_legacy))

        else:
            # Legacy path — unchanged behaviour
            target_page = self.page_texts.get(page_no, "")
            norm_target = self.normalize_text(target_page)
            if norm_target:
                candidates.append(("pdfplumber", norm_target))

            # Cross-page boundary stitches
            prev_page = self.page_texts.get(page_no - 1, "")
            if prev_page and target_page:
                boundary_prev = self.normalize_text(prev_page[-600:] + " " + target_page[:600])
                candidates.append(("boundary_prev", boundary_prev))

            next_page = self.page_texts.get(page_no + 1, "")
            if next_page and target_page:
                boundary_next = self.normalize_text(target_page[-600:] + " " + next_page[:600])
                candidates.append(("boundary_next", boundary_next))

            table_texts = self._table_search_texts(page_no, section_header)
            for txt in table_texts:
                candidates.append(("table", txt))

        return candidates

    def _known_pages(self) -> set:
        """Return the set of valid page numbers from all sources."""
        pages = set(self.page_texts.keys())
        if self.evidence is not None:
            pages |= set(self.evidence.pages.keys())
        return pages

    def _check_value_sanity(self, value: Any) -> Tuple[bool, Optional[str]]:
        """Run sanity checks on clinical outcome values (events <= total, CI order, quartiles)."""
        if value is None:
            return True, None

        val_dict: Dict[str, Any] = {}
        if isinstance(value, BaseModel):
            val_dict = value.model_dump()
        elif isinstance(value, dict):
            val_dict = value
        elif isinstance(value, str):
            val_dict = {"raw": value}

        # 1. events <= total check in any string field
        for k, v in val_dict.items():
            if isinstance(v, str):
                for match in re.finditer(r"\b(\d+)\s*/\s*(\d+)\b", v):
                    events, total = int(match.group(1)), int(match.group(2))
                    if events > total:
                        return False, f"Sanity check failure in '{k}': events ({events}) > total ({total})."

        # 2. CI lower <= upper check
        ci_str = val_dict.get("confidence_interval_95") or val_dict.get("confidence_interval")
        if isinstance(ci_str, str):
            m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:to|–|-)\s*(-?\d+(?:\.\d+)?)", ci_str)
            if m:
                try:
                    lower = float(m.group(1))
                    upper = float(m.group(2))
                    if lower > upper:
                        return False, f"Sanity check failure: CI lower bound ({lower}) > upper bound ({upper})."
                except ValueError:
                    pass

        # 3. IQR / Quartiles: q1 <= median <= q3
        q1 = val_dict.get("q1")
        med = val_dict.get("median")
        q3 = val_dict.get("q3")
        if q1 is not None and med is not None and q3 is not None:
            try:
                f_q1, f_med, f_q3 = float(q1), float(med), float(q3)
                if not (f_q1 <= f_med <= f_q3):
                    return False, f"Sanity check failure: quartile order violated ({f_q1} <= {f_med} <= {f_q3})."
            except (ValueError, TypeError):
                pass

        return True, None

    def verify_table_claim(
        self,
        table_id: str,
        value: Any,
        row_hint: Optional[str] = None,
        column_hint: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Verify that value tokens appear in the specific table and row."""
        # 1. Run sanity checks
        ok_sanity, err_sanity = self._check_value_sanity(value)
        if not ok_sanity:
            return False, err_sanity

        # 2. table_id must exist
        table_obj: Any = None
        if self.evidence is not None:
            table_obj = self.evidence.get_table(table_id)
        if table_obj is None:
            for t in self.tables_json:
                if t.get("table_id") == table_id:
                    table_obj = t
                    break

        if table_obj is None:
            return False, f"Table '{table_id}' not found in extracted tables."

        records = table_obj.records if hasattr(table_obj, "records") else table_obj.get("records", [])
        markdown = table_obj.markdown if hasattr(table_obj, "markdown") else table_obj.get("markdown", "")

        value_nums = self.extract_numeric_tokens(value)
        if not value_nums:
            return True, None

        # 3. Row matching in records
        if records:
            matched_row = None
            if row_hint:
                norm_hint = self.normalize_text(row_hint)
                best_score = 0.0
                for row in records:
                    row_texts = [self.normalize_text(str(v)) for v in row.values() if v is not None]
                    row_score = max((self._fuzzy_similarity(norm_hint, cell_t) for cell_t in row_texts), default=0.0)
                    if row_score > best_score:
                        best_score = row_score
                        matched_row = row
                if best_score < 50.0:
                    matched_row = None

            if row_hint and matched_row is None:
                return False, f"Row matching '{row_hint}' not found in table '{table_id}'."

            if matched_row is not None:
                row_nums = set(self.extract_numeric_tokens(list(matched_row.values())))
                missing = [n for n in value_nums if n not in row_nums]
                if missing:
                    return False, f"Numbers {missing} from value not found in row '{row_hint}' of table '{table_id}'."
                return True, None

            # If no row_hint, check if any single row contains all value numbers
            found_in_any_row = False
            for row in records:
                row_nums = set(self.extract_numeric_tokens(list(row.values())))
                if all(n in row_nums for n in value_nums):
                    found_in_any_row = True
                    break
            if not found_in_any_row:
                return False, f"Numbers {value_nums} do not co-occur in any single row of table '{table_id}'."
            return True, None

        # Fallback to markdown if records are empty
        if markdown:
            md_nums = set(self.extract_numeric_tokens(markdown))
            missing = [n for n in value_nums if n not in md_nums]
            if missing:
                return False, f"Numbers {missing} not found in markdown of table '{table_id}'."
            return True, None

        return True, None

    def verify_field(self, field_path: str, field: GroundedField[Any]) -> Tuple[bool, Optional[str]]:
        """Verifies a single GroundedField in-place, returning (success, error_message)."""
        if field.status == "NOT_REPORTED":
            field.value = None
            field.verified_in_source = True
            field.verification_note = "Verified as NOT_REPORTED."
            return True, None

        if field.status == "UNCLEAR":
            # Prevent dodging grounding: UNCLEAR is only valid if anchored by a quote demonstrating ambiguity
            if not field.verbatim_quote or len(field.verbatim_quote.strip()) < 4:
                field.verified_in_source = False
                err = (
                    f"[{field_path}] status='UNCLEAR' is rejected without source evidence. "
                    f"Use 'NOT_REPORTED' if data is absent, or 'REPORTED' with exact quote. "
                    f"UNCLEAR is only acceptable when citing contradictory text."
                )
                field.verification_note = err
                return False, err

            known = self._known_pages()
            if not field.page_number or field.page_number not in known:
                field.verified_in_source = False
                err = f"[{field_path}] Invalid page_number ({field.page_number}) for UNCLEAR ambiguity quote."
                field.verification_note = err
                return False, err

            norm_quote = self.normalize_text(field.verbatim_quote)
            candidates = self._build_candidate_search_texts(field.page_number, field.section_header)
            best_score = 0.0
            best_source = None
            for source, cand_text in candidates:
                score = self._fuzzy_similarity(norm_quote, cand_text)
                if score > best_score:
                    best_score = score
                    best_source = source

            # Determine threshold: use lower threshold for OCR-sourced candidates
            threshold = self._effective_threshold(best_source)
            if best_score < threshold:
                field.verified_in_source = False
                err = f"[{field_path}] Ambiguity quote not found on page {field.page_number} (score: {best_score:.1f}%)."
                field.verification_note = err
                return False, err

            field.verified_in_source = True
            field.grounding_source = best_source
            field.match_score = best_score
            field.verification_note = f"Ambiguity documented from source (quote verified, match={best_score:.1f}%)."
            if field.verbatim_quote not in self.verified_quotes:
                self.verified_quotes.append(field.verbatim_quote)
            return True, None

        # Clinical value sanity check (events <= total, CI order, quartiles)
        ok_sanity, err_sanity = self._check_value_sanity(field.value)
        if not ok_sanity:
            field.verified_in_source = False
            field.verification_note = err_sanity
            return False, f"[{field_path}] {err_sanity}"

        # Table-cell verification if source_table_id is specified
        tbl_id = getattr(field.value, "source_table_id", None)
        if isinstance(field.value, dict):
            tbl_id = field.value.get("source_table_id")
        if tbl_id:
            row_h = getattr(field.value, "outcome_name", None) or (
                field.value.get("outcome_name") if isinstance(field.value, dict) else None
            )
            ok_tbl, err_tbl = self.verify_table_claim(tbl_id, field.value, row_hint=row_h)
            if not ok_tbl:
                field.verified_in_source = False
                field.verification_note = err_tbl
                return False, f"[{field_path}] {err_tbl}"

        if not field.verbatim_quote or len(field.verbatim_quote.strip()) < 4:
            field.verified_in_source = False
            err = f"[{field_path}] REPORTED status requires verbatim_quote (minimum 4 characters)."
            field.verification_note = err
            return False, err

        known = self._known_pages()
        if not field.page_number or field.page_number not in known:
            field.verified_in_source = False
            err = f"[{field_path}] Invalid page_number ({field.page_number}). Document has pages {sorted(known)}."
            field.verification_note = err
            return False, err

        norm_quote = self.normalize_text(field.verbatim_quote)
        candidates = self._build_candidate_search_texts(field.page_number, field.section_header)

        best_score = 0.0
        best_source = None
        for source, cand_text in candidates:
            score = self._fuzzy_similarity(norm_quote, cand_text)
            if score > best_score:
                best_score = score
                best_source = source

        threshold = self._effective_threshold(best_source)
        if best_score < threshold:
            field.verified_in_source = False
            err = (
                f"[{field_path}] Verbatim quote not found on page {field.page_number} "
                f"(best match score: {best_score:.1f}% < {threshold}%). "
                f"Ensure quote is an exact character substring."
            )
            field.verification_note = err
            return False, err

        # Numeric exact-match check. The corpus is the quote plus the tables on
        # that page: numbers taken from unrelated prose elsewhere on the page
        # must not launder a fabricated value.
        value_numbers = self.extract_numeric_tokens(field.value)
        if value_numbers:
            corpus = " ".join(
                [norm_quote] + self._table_search_texts(field.page_number, field.section_header)
            )
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

        field.verified_in_source = True
        field.grounding_source = best_source
        field.match_score = best_score
        field.verification_note = f"Verified (match={best_score:.1f}%)"

        # Accumulate quote for single-pass write-once PDF annotation
        if field.verbatim_quote not in self.verified_quotes:
            self.verified_quotes.append(field.verbatim_quote)

        return True, None

    def _effective_threshold(self, source: Optional[str]) -> float:
        """Return the fuzzy threshold appropriate for the matched source.

        OCR-sourced candidates get a lower bar because OCR text is noisier.
        """
        if source and source in ("tesseract", "figure_ocr"):
            return self.fuzzy_threshold_ocr
        return self.fuzzy_threshold

    def save_annotated_pdf(self, output_path: str | Path) -> Optional[str]:
        """Writes all accumulated verified quotes in a single batch pass to destination PDF."""
        if self.annotator is None or not self.verified_quotes:
            return None
        try:
            return self.annotator.highlight_sentences(
                self.verified_quotes,
                output_path=output_path,
            )
        except Exception as exc:
            logger.warning("Failed saving annotated PDF to %s: %s", output_path, exc)
            return None

    def verify_model(self, model: BaseModel) -> List[str]:
        """Recursively validates every GroundedField within a Pydantic model."""
        errors: List[str] = []
        for name in model.__class__.model_fields:
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
                    elif isinstance(item, BaseModel):
                        # Nested models inside a list must still be grounded;
                        # skipping them would silently bypass the contract.
                        errors.extend(self._verify_nested(f"{name}[{idx}]", item))
            elif isinstance(attr, BaseModel):
                sub_errs = self.verify_model(attr)
                errors.extend(sub_errs)
        return errors

    def _verify_nested(self, prefix: str, model: BaseModel) -> List[str]:
        """Verify a nested model that lives inside a list, prefixing error paths."""
        errors: List[str] = []
        for name in model.__class__.model_fields:
            attr = getattr(model, name, None)
            path = f"{prefix}.{name}"
            if isinstance(attr, GroundedField):
                ok, err = self.verify_field(path, attr)
                if not ok and err:
                    errors.append(err)
            elif isinstance(attr, list):
                for idx, item in enumerate(attr):
                    if isinstance(item, GroundedField):
                        ok, err = self.verify_field(f"{path}[{idx}]", item)
                        if not ok and err:
                            errors.append(err)
                    elif isinstance(item, BaseModel):
                        errors.extend(self._verify_nested(f"{path}[{idx}]", item))
            elif isinstance(attr, BaseModel):
                errors.extend(self._verify_nested(path, attr))
        return errors

    def downgrade_unverified_fields(self, model: BaseModel) -> None:
        """Downgrades any REPORTED field failing verification to UNCLEAR."""
        for name in model.__class__.model_fields:
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
                    elif isinstance(item, BaseModel):
                        self._downgrade_nested(f"{name}[{idx}]", item)
            elif isinstance(attr, BaseModel):
                self.downgrade_unverified_fields(attr)

    def _downgrade_nested(self, prefix: str, model: BaseModel) -> None:
        """Mirror downgrade_unverified_fields for models nested inside lists."""
        for name in model.__class__.model_fields:
            attr = getattr(model, name, None)
            path = f"{prefix}.{name}"
            if isinstance(attr, GroundedField) and attr.status == "REPORTED" and not attr.verified_in_source:
                logger.warning("Downgrading unverified field '%s' to UNCLEAR.", path)
                attr.status = "UNCLEAR"
                attr.verification_note = f"DOWNGRADED_AFTER_RETRIES: {attr.verification_note}"
            elif isinstance(attr, list):
                for idx, item in enumerate(attr):
                    if isinstance(item, GroundedField) and item.status == "REPORTED" and not item.verified_in_source:
                        logger.warning("Downgrading unverified field '%s[%d]' to UNCLEAR.", path, idx)
                        item.status = "UNCLEAR"
                        item.verification_note = f"DOWNGRADED_AFTER_RETRIES: {item.verification_note}"
                    elif isinstance(item, BaseModel):
                        self._downgrade_nested(f"{path}[{idx}]", item)
            elif isinstance(attr, BaseModel):
                self._downgrade_nested(path, attr)
