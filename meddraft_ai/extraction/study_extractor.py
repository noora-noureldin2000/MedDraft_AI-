from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from meddraft_ai.extraction.grounding_verifier import GroundingVerifier
from meddraft_ai.extraction.schemas import (
    CrossSectionAudit,
    DiscussionPassSchema,
    FigurePassSchema,
    GroundedField,
    MethodsPassSchema,
    OutcomeMeasure,
    ResultsPassSchema,
    StudyExtractionSchema,
)
from meddraft_ai.prompts.study_extraction_prompts import (
    DISCUSSION_SYSTEM_PROMPT,
    FIGURE_SYSTEM_PROMPT,
    METHODS_SYSTEM_PROMPT,
    RESULTS_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StudyExtractor:
    """Orchestrates multi-pass IMRaD clinical study data extraction with deterministic
    verbatim quote grounding, budgeted map-reduce, and self-correction retry loops.
    """

    def __init__(
        self,
        llm_structured_callable: Callable[[str, str, Type[T]], T],
        verifier: GroundingVerifier,
        max_retries: int = 2,
        budget: Optional[int] = None,
        overlap_units: Optional[int] = None,
    ):
        self.call_llm = llm_structured_callable
        self.verifier = verifier
        self.max_retries = max_retries

        from meddraft_ai.core.config import get_config
        cfg = get_config()
        self.budget = budget or cfg.PASS_INPUT_TOKEN_BUDGET
        self.overlap_units = overlap_units or cfg.PASS_OVERLAP_UNITS
        self.extraction_warnings: List[str] = []
        self.pass_budgets: Dict[str, int] = {}

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count conservatively (chars / 3.5)."""
        if not text:
            return 0
        return int(len(text) / 3.5)

    @staticmethod
    def _pack_units(units: List[str], budget: int, overlap_units: int = 2) -> List[str]:
        """Pack atomic text/table blocks into sub-contexts within the token budget.

        Uses whole atomic units (paragraphs, tables) so neither a sentence nor a
        table row is cut in half. Overlap is measured in whole units.
        """
        if not units:
            return [""]

        sub_contexts: List[str] = []
        current_units: List[str] = []
        current_chars = 0
        budget_chars = int(budget * 3.5)

        i = 0
        while i < len(units):
            unit = units[i]
            unit_chars = len(unit)

            if current_chars + unit_chars > budget_chars and current_units:
                sub_contexts.append("\n\n".join(current_units))
                step_back = min(overlap_units, len(current_units))
                current_units = current_units[-step_back:] if step_back > 0 else []
                current_chars = sum(len(u) for u in current_units)

            current_units.append(unit)
            current_chars += unit_chars
            i += 1

        if current_units:
            sub_contexts.append("\n\n".join(current_units))

        return sub_contexts

    def _build_atomic_units(
        self,
        chunks: List[Dict[str, Any]],
        tables: Optional[List[Dict[str, Any]]] = None,
        figures: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """Convert chunks, tables, and figures into indivisible text units."""
        units: List[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            page = chunk.get("page", "UNKNOWN")
            section = str(chunk.get("section", "UNKNOWN")).upper()
            text = chunk.get("text", "")
            units.append(f"--- [CHUNK {idx} | PAGE {page} | SECTION: {section}] ---\n{text}")

        if tables:
            seen_tables = set()
            for tbl in tables:
                table_id = tbl.get("table_id", "Unknown_Table")
                if table_id in seen_tables:
                    continue
                seen_tables.add(table_id)
                page_no = tbl.get("page", "UNKNOWN")
                caption = tbl.get("caption", "")
                md = tbl.get("markdown", "")
                records = json.dumps(tbl.get("records", []), ensure_ascii=False)
                units.append(
                    f"--- [TABLE ID: {table_id} | PAGE {page_no}] ---\n"
                    f"Caption: {caption}\n"
                    f"Markdown Grid:\n{md}\n"
                    f"Records JSON:\n{records}"
                )

        if figures:
            seen_figs = set()
            for fig in figures:
                fig_id = fig.get("figure_id", "Unknown_Figure")
                if fig_id in seen_figs:
                    continue
                seen_figs.add(fig_id)
                page_no = fig.get("page", "UNKNOWN")
                caption = fig.get("caption", "")
                ocr_text = fig.get("ocr_text", "")
                units.append(
                    f"--- [FIGURE ID: {fig_id} | PAGE {page_no}] ---\n"
                    f"Caption: {caption}\n"
                    f"Consensus OCR Text: {ocr_text}"
                )

        return units

    def format_source_context(
        self,
        chunks: List[Dict[str, Any]],
        tables: Optional[List[Dict[str, Any]]] = None,
        figures: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Formats semantic text chunks and structured tables with explicit page headers."""
        lines = ["=== SOURCE TEXT CHUNKS ==="]
        for idx, chunk in enumerate(chunks, start=1):
            page = chunk.get("page", "UNKNOWN")
            section = str(chunk.get("section", "UNKNOWN")).upper()
            text = chunk.get("text", "")
            lines.append(f"\n--- [CHUNK {idx} | PAGE {page} | SECTION: {section}] ---\n{text}")

        if tables:
            lines.append("\n\n=== STRUCTURED TABLES ===")
            seen_tables = set()
            for tbl in tables:
                table_id = tbl.get("table_id", "Unknown_Table")
                if table_id in seen_tables:
                    continue
                seen_tables.add(table_id)
                page_no = tbl.get("page", "UNKNOWN")
                caption = tbl.get("caption", "")
                md = tbl.get("markdown", "")
                records = json.dumps(tbl.get("records", []), ensure_ascii=False)
                lines.append(
                    f"\n--- [TABLE ID: {table_id} | PAGE {page_no}] ---\n"
                    f"Caption: {caption}\n"
                    f"Markdown Grid:\n{md}\n"
                    f"Records JSON:\n{records}\n"
                )

        if figures:
            lines.append("\n\n=== EXTRACTED FIGURES ===")
            seen_figs = set()
            for fig in figures:
                fig_id = fig.get("figure_id", "Unknown_Figure")
                if fig_id in seen_figs:
                    continue
                seen_figs.add(fig_id)
                page_no = fig.get("page", "UNKNOWN")
                caption = fig.get("caption", "")
                ocr_text = fig.get("ocr_text", "")
                lines.append(
                    f"\n--- [FIGURE ID: {fig_id} | PAGE {page_no}] ---\n"
                    f"Caption: {caption}\n"
                    f"Consensus OCR Text: {ocr_text}\n"
                )

        return "\n".join(lines)

    def _run_single_pass(
        self,
        pass_name: str,
        system_prompt: str,
        source_context: str,
        schema_cls: Type[T],
    ) -> T:
        """Executes a single extraction pass with retry loop."""
        user_prompt = (
            f"Extract the `{schema_cls.__name__}` schema from the following clinical study chunks.\n\n"
            f"{source_context}"
        )

        result_model: Optional[T] = None

        for attempt in range(1, self.max_retries + 2):
            logger.info("[%s] Extraction attempt %d/%d...", pass_name, attempt, self.max_retries + 1)
            result_model = self.call_llm(system_prompt, user_prompt, schema_cls)

            verification_errors = self.verifier.verify_model(result_model)
            if not verification_errors:
                logger.info("[%s] All fields passed grounding verification!", pass_name)
                return result_model

            logger.warning("[%s] Attempt %d had %d verification failure(s).", pass_name, attempt, len(verification_errors))

            if attempt <= self.max_retries:
                user_prompt = self._build_retry_prompt(source_context, result_model, verification_errors)

        assert result_model is not None
        self.verifier.downgrade_unverified_fields(result_model)
        return result_model

    def run_verified_pass(
        self,
        pass_name: str,
        system_prompt: str,
        source_context: str,
        schema_cls: Type[T],
        raw_units: Optional[List[str]] = None,
    ) -> T:
        """Executes an extraction pass with budgeted map-reduce when content exceeds limits."""
        est_tokens = self._estimate_tokens(source_context)
        self.pass_budgets[pass_name] = est_tokens

        # Within budget or single-unit: execute directly
        if est_tokens <= self.budget or not raw_units:
            return self._run_single_pass(pass_name, system_prompt, source_context, schema_cls)

        # Budgeted Map-Reduce
        sub_contexts = self._pack_units(raw_units, budget=self.budget, overlap_units=self.overlap_units)
        logger.info(
            "[%s] Content (%d tokens) exceeds budget (%d). Executing %d sub-passes.",
            pass_name, est_tokens, self.budget, len(sub_contexts),
        )

        sub_models: List[T] = []
        for idx, sub_ctx in enumerate(sub_contexts, start=1):
            sub_name = f"{pass_name}_SUB_{idx}"
            model = self._run_single_pass(sub_name, system_prompt, sub_ctx, schema_cls)
            sub_models.append(model)

        merged_model = self._merge_models(sub_models, schema_cls)

        # Re-verify once post-merge
        re_errors = self.verifier.verify_model(merged_model)
        if re_errors:
            logger.warning("[%s] Post-merge verification had %d issue(s). Downgrading.", pass_name, len(re_errors))
            self.verifier.downgrade_unverified_fields(merged_model)

        return merged_model

    def _merge_models(self, models: List[T], schema_cls: Type[T]) -> T:
        """Merges sub-pass extraction models with deduplication and conflict logging."""
        if not models:
            raise ValueError("No models to merge.")
        if len(models) == 1:
            return models[0]

        merged_dict: Dict[str, Any] = {}

        for field_name in schema_cls.model_fields:
            first_val = getattr(models[0], field_name)

            if isinstance(first_val, list):
                # Outcomes list merging
                merged_list: List[Any] = []
                seen_outcomes: Dict[Any, Any] = {}

                for m in models:
                    items = getattr(m, field_name, [])
                    for item in items:
                        if hasattr(item, "value") and isinstance(item.value, OutcomeMeasure):
                            om = item.value
                            norm_name = GroundingVerifier.normalize_text(om.outcome_name)
                            om_key = (norm_name, om.timepoint, om.analysis_population, om.source_table_id)

                            if om_key in seen_outcomes:
                                existing = seen_outcomes[om_key]
                                if existing.value.intervention_result != om.intervention_result:
                                    self.extraction_warnings.append(
                                        f"Conflict in outcome '{om.outcome_name}': "
                                        f"'{existing.value.intervention_result}' vs '{om.intervention_result}'"
                                    )
                                if not existing.verified_in_source and item.verified_in_source:
                                    seen_outcomes[om_key] = item
                            else:
                                seen_outcomes[om_key] = item
                        else:
                            merged_list.append(item)

                if seen_outcomes:
                    merged_dict[field_name] = list(seen_outcomes.values())
                else:
                    deduped: List[Any] = []
                    seen_simple = set()
                    for m in models:
                        for it in getattr(m, field_name, []):
                            it_s = str(it)
                            if it_s not in seen_simple:
                                seen_simple.add(it_s)
                                deduped.append(it)
                    merged_dict[field_name] = deduped

            elif isinstance(first_val, GroundedField):
                best_field = first_val
                reported_vals = []
                for m in models:
                    f = getattr(m, field_name)
                    if f.status == "REPORTED":
                        reported_vals.append(f)
                    if f.verified_in_source and not best_field.verified_in_source:
                        best_field = f
                    elif f.status == "REPORTED" and best_field.status != "REPORTED":
                        best_field = f

                if len(reported_vals) > 1:
                    v0 = reported_vals[0].value
                    for rv in reported_vals[1:]:
                        if rv.value != v0:
                            self.extraction_warnings.append(
                                f"Conflict in field '{field_name}': '{v0}' vs '{rv.value}'"
                            )
                merged_dict[field_name] = best_field
            else:
                merged_dict[field_name] = first_val

        return schema_cls.model_validate(merged_dict)

    def _build_retry_prompt(self, source_context: str, model: BaseModel, errors: List[str]) -> str:
        """Builds concise self-correction instructions addressing specific verification errors."""
        error_bullets = "\n".join(f"- {err}" for err in errors)
        return (
            f"{source_context}\n\n"
            f"=== PREVIOUS EXTRACTION ATTEMPT ===\n"
            f"{model.model_dump_json(indent=2)}\n\n"
            f"=== VERIFICATION FAILURES TO FIX ===\n"
            f"{error_bullets}\n\n"
            f"CORRECTION INSTRUCTIONS:\n"
            f"1. For each failing field listed above, provide an EXACT character-for-character quote from the specified page, "
            f"ensure all numbers in `value` exist verbatim in the quote/table without rounding, "
            f"or set `status='NOT_REPORTED'` if unsupported.\n"
            f"2. Keep already verified fields unchanged."
        )

    def extract_all(
        self,
        study_id: str,
        semantic_chunks: Dict[str, List[Dict[str, Any]]],
        metadata_doi: Optional[str] = None,
        metadata_pmid: Optional[str] = None,
    ) -> StudyExtractionSchema:
        """Runs the complete 4-pass IMRaD extraction and verification pipeline."""
        abstract_chunks = semantic_chunks.get("abstract_intro", [])
        methods_chunks = semantic_chunks.get("methods", [])
        results_chunks = semantic_chunks.get("results", [])
        discussion_chunks = semantic_chunks.get("discussion", [])
        tables = semantic_chunks.get("tables", [])
        figures = semantic_chunks.get("figures", [])

        all_text_chunks = abstract_chunks + methods_chunks + results_chunks + discussion_chunks

        # Pass 1: Methods
        methods_units = self._build_atomic_units(abstract_chunks + methods_chunks) or self._build_atomic_units(all_text_chunks)
        methods_context = self.format_source_context((abstract_chunks + methods_chunks) or all_text_chunks)
        methods_data = self.run_verified_pass(
            "PASS_1_METHODS",
            METHODS_SYSTEM_PROMPT,
            methods_context,
            MethodsPassSchema,
            raw_units=methods_units,
        )

        # Pass 2: Results & Tables
        results_units = self._build_atomic_units((abstract_chunks + results_chunks) or all_text_chunks, tables=tables)
        results_context = self.format_source_context((abstract_chunks + results_chunks) or all_text_chunks, tables=tables)
        results_data = self.run_verified_pass(
            "PASS_2_RESULTS",
            RESULTS_SYSTEM_PROMPT,
            results_context,
            ResultsPassSchema,
            raw_units=results_units,
        )

        # Pass 2b: Figure Pass
        extracted_figures: List[FigurePassSchema] = []
        if figures:
            logger.info("Executing Pass 2b: Figure extraction on %d figure(s)...", len(figures))
            for fig in figures:
                fig_id = fig.get("figure_id", "Figure")
                caption = fig.get("caption", "")
                ocr_t = fig.get("ocr_text", "")
                img_p = fig.get("image_path")
                fig_prompt = (
                    f"Extract data from Figure ID: {fig_id}\n"
                    f"Caption: {caption}\n"
                    f"Consensus OCR text from plot: {ocr_t}\n"
                )
                try:
                    if hasattr(self.call_llm, "__self__") and hasattr(self.call_llm.__self__, "query_structured"):
                        fig_data = self.call_llm.__self__.query_structured(
                            FIGURE_SYSTEM_PROMPT,
                            fig_prompt,
                            FigurePassSchema,
                            image_paths=[img_p] if img_p else None,
                        )
                    else:
                        fig_data = self.call_llm(FIGURE_SYSTEM_PROMPT, fig_prompt, FigurePassSchema)
                    if fig_data:
                        extracted_figures.append(fig_data)
                except Exception as fig_exc:
                    logger.debug("Figure extraction failed for %s: %s", fig_id, fig_exc)

        # Pass 3: Discussion
        discussion_units = self._build_atomic_units((discussion_chunks + abstract_chunks) or all_text_chunks)
        discussion_context = self.format_source_context((discussion_chunks + abstract_chunks) or all_text_chunks)
        discussion_data = self.run_verified_pass(
            "PASS_3_DISCUSSION",
            DISCUSSION_SYSTEM_PROMPT,
            discussion_context,
            DiscussionPassSchema,
            raw_units=discussion_units,
        )

        # Pass 4: Cross-Section Audit (Deterministically verified)
        audit_prompt = (
            f"=== VERIFIED METHODS ===\n{methods_data.model_dump_json(indent=2)}\n\n"
            f"=== VERIFIED RESULTS ===\n{results_data.model_dump_json(indent=2)}\n\n"
            f"=== VERIFIED DISCUSSION ===\n{discussion_data.model_dump_json(indent=2)}"
        )
        audit_data = self.run_verified_pass(
            "PASS_4_CROSS_SECTION_AUDIT",
            SYNTHESIS_SYSTEM_PROMPT,
            audit_prompt,
            CrossSectionAudit,
        )

        return StudyExtractionSchema(
            study_id=study_id,
            metadata_doi=metadata_doi,
            metadata_pmid=metadata_pmid,
            methods=methods_data,
            results=results_data,
            discussion=discussion_data,
            semantic_audit=audit_data,
            figures=extracted_figures,
            extraction_warnings=self.extraction_warnings,
        )
