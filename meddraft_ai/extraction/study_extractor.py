from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from meddraft_ai.extraction.grounding_verifier import GroundingVerifier
from meddraft_ai.extraction.schemas import (
    CrossSectionAudit,
    DiscussionPassSchema,
    MethodsPassSchema,
    ResultsPassSchema,
    StudyExtractionSchema,
)
from meddraft_ai.prompts.study_extraction_prompts import (
    DISCUSSION_SYSTEM_PROMPT,
    METHODS_SYSTEM_PROMPT,
    RESULTS_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StudyExtractor:
    """Orchestrates multi-pass IMRaD clinical study data extraction with deterministic
    verbatim quote grounding and self-correction retry loops.
    """

    def __init__(
        self,
        llm_structured_callable: Callable[[str, str, Type[T]], T],
        verifier: GroundingVerifier,
        max_retries: int = 2,
    ):
        self.call_llm = llm_structured_callable
        self.verifier = verifier
        self.max_retries = max_retries

    def format_source_context(
        self,
        chunks: List[Dict[str, Any]],
        tables: Optional[List[Dict[str, Any]]] = None,
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
            for tbl in tables:
                table_id = tbl.get("table_id", "Unknown_Table")
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

        return "\n".join(lines)

    def run_verified_pass(
        self,
        pass_name: str,
        system_prompt: str,
        source_context: str,
        schema_cls: Type[T],
    ) -> T:
        """Executes an extraction pass with deterministic verification and self-correction retries."""
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

        all_text_chunks = abstract_chunks + methods_chunks + results_chunks + discussion_chunks

        # Pass 1: Methods
        methods_context = self.format_source_context((abstract_chunks + methods_chunks) or all_text_chunks)
        methods_data = self.run_verified_pass("PASS_1_METHODS", METHODS_SYSTEM_PROMPT, methods_context, MethodsPassSchema)

        # Pass 2: Results & Tables
        results_context = self.format_source_context((abstract_chunks + results_chunks) or all_text_chunks, tables=tables)
        results_data = self.run_verified_pass("PASS_2_RESULTS", RESULTS_SYSTEM_PROMPT, results_context, ResultsPassSchema)

        # Pass 3: Discussion
        discussion_context = self.format_source_context((discussion_chunks + abstract_chunks) or all_text_chunks)
        discussion_data = self.run_verified_pass("PASS_3_DISCUSSION", DISCUSSION_SYSTEM_PROMPT, discussion_context, DiscussionPassSchema)

        # Pass 4: Cross-Section Audit
        audit_prompt = (
            f"=== VERIFIED METHODS ===\n{methods_data.model_dump_json(indent=2)}\n\n"
            f"=== VERIFIED RESULTS ===\n{results_data.model_dump_json(indent=2)}\n\n"
            f"=== VERIFIED DISCUSSION ===\n{discussion_data.model_dump_json(indent=2)}"
        )
        audit_data = self.call_llm(SYNTHESIS_SYSTEM_PROMPT, audit_prompt, CrossSectionAudit)

        return StudyExtractionSchema(
            study_id=study_id,
            metadata_doi=metadata_doi,
            metadata_pmid=metadata_pmid,
            methods=methods_data,
            results=results_data,
            discussion=discussion_data,
            semantic_audit=audit_data,
        )
