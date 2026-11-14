#!/usr/bin/env python3
"""
MedDraft_AI - Standalone Medical Research Writing Platform
CLI Entry Point & Pipeline Orchestrator
"""

import sys
import os
import re
import json
import logging
from pathlib import Path
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Add package root to sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from meddraft_ai.core.config import get_config
from meddraft_ai.search.research_orchestrator import ResearchOrchestrator
from meddraft_ai.extraction.pdf_reader import PDFReader
from meddraft_ai.agents.specialists import (
    CoreWriterSpecialist,
    HumanizerSpecialist,
    ProofReaderSpecialist,
    SystematicReviewDiscussionSpecialist,
)
from meddraft_ai.agents.medical_writer_agent import MedicalWriterAgent
from meddraft_ai.core.sr_discussion import (
    audit_discussion,
    check_numeric_fidelity,
    inventory_project,
    read_source_texts,
)
from meddraft_ai.validation.reference_validator import validate_references
from meddraft_ai.export.pandoc_converter import convert_markdown_to_docx

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Injected into the Discussion prompt for systematic reviews and meta-analyses.
# The full contract lives in meddraft_ai/prompts/systematic-review-discussion/;
# this directive names the non-negotiable gates so the draft is auditable.
SR_DISCUSSION_DIRECTIVE = (
    "\n\nApply the systematic-review-discussion skill to this Discussion.\n"
    "- Start by restating the complete workspace inventory and the Master Evidence Summary Table "
    "(included studies and every pooled outcome with estimate, 95% CI, p value, I2).\n"
    "- Discuss every primary outcome, secondary outcome, subgroup, sensitivity analysis, and safety "
    "or laboratory outcome. Group by domain if useful. Never omit a null or unfavourable result. "
    "Mark any outcome that was not pooled as NOT_POOLED or NOT_REPORTED.\n"
    "- Block order: principal findings, time-course efficacy and mechanism, target attainment, "
    "comparison with prior reviews and landmark trials, safety and laboratory profile, clinical "
    "implications and guideline alignment, strengths and limitations, future research, conclusions.\n"
    "- For every outcome domain use Restate, Compare, Interpret. Explain discrepancies by population, "
    "intervention or comparator, methodology, or power and measurement.\n"
    "- Interpret I2 with tau2 and the prediction interval where available. Do not recite heterogeneity "
    "without explaining what it means for applicability.\n"
    "- Calibrate every certainty claim to GRADE: high shows, moderate likely, low may, very low very "
    "uncertain. State explicitly if GRADE was not performed.\n"
    "- Split limitations into study-level and review-level, each as State, Impact, Mitigate. "
    "No apologetic wording.\n"
    "- Make future research specific: population, intervention and comparator, design, outcome, "
    "duration. Never write that more research is needed.\n"
    "- Prose: zero em dashes, no banned AI vocabulary, no study-by-study laundry lists. Cite in the "
    "requested style and never invent, round, or transpose a number."
)

def load_project_context(project_path: Path) -> str:
    """Read project Markdown sources for source-grounded drafting."""
    context_parts = []
    for source_file in sorted(project_path.rglob("*.md")):
        try:
            content = source_file.read_text(encoding="utf-8")
        except OSError as err:
            logging.warning("Could not read project file %s: %s", source_file, err)
            continue
        context_parts.append(f"\n--- PROJECT FILE: {source_file.name} ---\n{content}")
    return "".join(context_parts)


def load_tabular_evidence(project_path: Path, max_chars: int = 60000) -> str:
    """Read CSV/TSV/JSON evidence files (pooled tables) for SR/MA drafting.

    Markdown is already covered by ``load_project_context``. Meta-analysis
    folders commonly store pooled estimates as CSV or JSON, so those formats
    must be visible to the Discussion writer instead of being silently ignored.
    """
    parts: list[str] = []
    budget = max_chars
    for source_file in sorted(project_path.rglob("*")):
        if not source_file.is_file():
            continue
        if source_file.suffix.lower() not in {".csv", ".tsv", ".json"}:
            continue
        if budget <= 0:
            break
        try:
            content = source_file.read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            logging.warning("Could not read data file %s: %s", source_file, err)
            continue
        snippet = content[: min(len(content), budget, 15000)]
        try:
            label = source_file.relative_to(project_path)
        except ValueError:
            label = source_file
        parts.append(f"\n--- DATA FILE: {label} ---\n{snippet}")
        budget -= len(snippet)
    return "".join(parts)


def collect_draft_dois(draft: str) -> set[str]:
    """Return every DOI-shaped token in the draft, punctuation stripped."""
    from meddraft_ai.extraction.citation_tracker import (
        DOI_PATTERN,
        strip_doi_punctuation,
    )
    return {
        doi
        for match in re.finditer(DOI_PATTERN, draft)
        if (doi := strip_doi_punctuation(match.group(0)))
    }


def _unverified_dois(draft: str, citations: list[dict]) -> list[str]:
    """DOIs cited in the draft that no API confirmed."""
    verified = {str(c.get("doi", "")).lower() for c in citations if c.get("doi")}
    return sorted(doi for doi in collect_draft_dois(draft) if doi.lower() not in verified)


def _write_reference_report(report_path: Path, citations: list[dict], unverified: list[str]) -> None:
    report_path.write_text(
        json.dumps(
            {
                "verified": citations,
                "unverified_dois": unverified,
                "note": (
                    "Unverified DOIs may be hallucinated or may have failed "
                    "live API validation; confirm before submission."
                ),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def verify_and_report_references(draft: str, report_path: Path) -> tuple[int, list[str]]:
    """Validate draft references live and persist an auditable report.

    Returns the number of verified references and the DOIs present in the draft
    that no API could confirm. Unverified DOIs are *flagged*, never silently
    removed: a network outage and a hallucinated DOI look identical at this
    layer, so the author decides.
    """
    citations = validate_references(draft)
    unverified = _unverified_dois(draft, citations)
    _write_reference_report(report_path, citations, unverified)
    return len(citations), unverified

@click.command()
@click.option("--topic", default="", help="The medical topic or research question to write about.")
@click.option("--type", "manuscript_type", default="manuscript", type=click.Choice([
    "manuscript", "thesis", "dissertation", "systematic-review", "narrative-review",
    "scoping-review", "meta-analysis", "protocol", "grant-proposal", "clinical-report"
]), help="Type of document to generate.")
@click.option("--sections", default="all", help="Comma-separated list of sections to generate, or 'all'.")
@click.option("--humanize", is_flag=True, default=False, help="Enable Dr. Noora's on-demand humanization pass after drafting.")
@click.option("--search-depth", default=10, type=int, help="Number of studies per database to retrieve.")
@click.option("--citation-style", default="Harvard", type=click.Choice(["Harvard", "Vancouver"]), help="Citation style.")
@click.option("--output-dir", default="./outputs", help="Output directory path.")
@click.option("--output-format", default="both", type=click.Choice(["md", "docx", "both"]), help="Output file format.")
@click.option("--data-file", default=None, help="Path to pre-computed stats JSON or raw dataset.")
@click.option("--pdf-input", default=None, help="Path to reference PDF file(s) for extraction.")
@click.option("--parse-pdf", default=None, help="Extract structured zero-hallucination study JSON from PDF.")
@click.option("--out", default=None, help="Output JSON path for --parse-pdf extraction.")
@click.option("--annotated-pdf", default=None, help="Output highlighted PDF path for --parse-pdf.")
@click.option("--no-ocr", is_flag=True, default=False, help="Disable OCR recovery for scanned pages.")
@click.option("--ocr-lang", default=None, help="OCR language (e.g. eng).")
@click.option("--no-figures", is_flag=True, default=False, help="Disable figure extraction pass.")
@click.option("--reuse-extraction", is_flag=True, default=False, help="Reuse existing extraction if JSON exists.")
@click.option("--coverage", "coverage_path", default=None, help="Output path for coverage.json.")
@click.option("--strict-coverage", is_flag=True, default=False, help="Fail if any section or content page is missing.")
@click.option("--project-dir", default=None, help="Directory containing protocol, results, and discussion notes.")
@click.option("--sr-require", multiple=True, help="Outcome label that the SR/MA Discussion audit must find (repeatable).")
@click.option("--provider", default=None, type=click.Choice(["dual", "simple"]), help="LLM provider mode.")
@click.option("--verbose", is_flag=True, default=False, help="Enable verbose log output.")
def main(
    topic: str,
    manuscript_type: str,
    sections: str,
    humanize: bool,
    search_depth: int,
    citation_style: str,
    output_dir: str,
    output_format: str,
    data_file: str,
    pdf_input: str,
    parse_pdf: str,
    out: str,
    annotated_pdf: str,
    no_ocr: bool,
    ocr_lang: str,
    no_figures: bool,
    reuse_extraction: bool,
    coverage_path: str,
    strict_coverage: bool,
    project_dir: str,
    sr_require: tuple,
    provider: str,
    verbose: bool
):
    """
    MedDraft_AI: Production-Ready Standalone Medical Research Writing Platform.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = get_config()
    if provider:
        config.LLM_PROVIDER = provider

    # Standalone zero-hallucination study extraction workflow
    if parse_pdf:
        target_pdf = Path(parse_pdf)
        if not target_pdf.exists():
            console.print(f"[red]Error: PDF not found: {target_pdf}[/red]")
            return

        json_out = Path(out) if out else (out_path / f"{target_pdf.stem}_extraction.json")
        if reuse_extraction and json_out.exists():
            console.print(f"[green]Reusing existing extraction: {json_out}[/green]")
            return

        console.print(Panel.fit(
            f"[bold cyan]MedDraft_AI — Zero-Hallucination Study Extractor[/bold cyan]\n"
            f"Target PDF: [yellow]{target_pdf.name}[/yellow]",
            border_style="cyan"
        ))

        if no_ocr:
            config.OCR_ENABLED = False
        if ocr_lang:
            config.OCR_LANG = ocr_lang
        if no_figures:
            config.FIGURE_EXTRACTION_ENABLED = False
            config.FIGURE_OCR_ENABLED = False

        from meddraft_ai.extraction import (
            ExtractionEngine,
            SemanticDocumentChunker,
            GroundingVerifier,
            StudyExtractor,
            PDFAnnotator,
        )
        from meddraft_ai.core.llm_client import LLMClient

        llm = LLMClient()
        engine = ExtractionEngine(target_pdf, output_dir=out_path)
        extraction_result = engine.process_pdf_full()
        bundle = extraction_result["bundle"]
        evidence = bundle.evidence

        chunker = SemanticDocumentChunker()
        chunks = chunker.chunk_bundle(bundle)

        annotator = None
        try:
            annotator = PDFAnnotator(target_pdf)
        except Exception as exc:
            console.print(f"[yellow]PDFAnnotator notice: {exc}[/yellow]")

        verifier = GroundingVerifier(
            page_texts=bundle.page_texts,
            tables_json=chunks.get("tables", []),
            pdf_annotator=annotator,
            evidence=evidence,
        )
        extractor = StudyExtractor(
            llm_structured_callable=llm.query_structured,
            verifier=verifier,
            max_retries=2,
        )

        study_doi = extraction_result.get("metadata", {}).get("doi")
        study_pmid = extraction_result.get("metadata", {}).get("pmid")

        study_data = extractor.extract_all(
            study_id=target_pdf.stem,
            semantic_chunks=chunks,
            metadata_doi=study_doi,
            metadata_pmid=study_pmid,
        )

        json_out.write_text(study_data.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[bold green]✨ Auditable study extraction saved to: {json_out}[/bold green]")

        # Coverage manifest
        from meddraft_ai.extraction.coverage import CoverageAuditor
        cov_manifest = CoverageAuditor.audit(
            evidence_index=evidence,
            semantic_chunks=chunks,
            study_schema=study_data,
            pass_budgets=extractor.pass_budgets,
            header_fallbacks=chunker.header_fallbacks,
        )
        cov_out = Path(coverage_path) if coverage_path else (out_path / f"{target_pdf.stem}_coverage.json")
        cov_manifest.save(cov_out)
        console.print(f"[bold green]✨ Coverage manifest saved to: {cov_out}[/bold green]")

        # One-screen coverage summary table
        from rich.table import Table
        summary_tbl = Table(title=f"Extraction Coverage Summary: {target_pdf.name}", show_header=True)
        summary_tbl.add_column("Metric", style="cyan")
        summary_tbl.add_column("Count / Status", style="green")

        summary_tbl.add_row("Total Pages", str(cov_manifest.pages_total))
        summary_tbl.add_row("Pages with Text", str(cov_manifest.pages_with_text))
        summary_tbl.add_row("Pages OCR'd", str(len(cov_manifest.pages_ocr)))
        summary_tbl.add_row("Tables Found", str(cov_manifest.tables.get("found", 0)))
        summary_tbl.add_row("Figures Exported", str(cov_manifest.figures.get("exported", 0)))
        summary_tbl.add_row("Reported Fields", str(cov_manifest.verification.get("reported", 0)))
        summary_tbl.add_row("Downgraded Fields", str(cov_manifest.verification.get("downgraded", 0)))
        summary_tbl.add_row("Extraction Warnings", str(len(study_data.extraction_warnings)))
        console.print(summary_tbl)

        if strict_coverage and cov_manifest.warnings:
            console.print(f"[bold red]Strict coverage failure: {cov_manifest.warnings}[/bold red]")
            sys.exit(1)

        # Write all accumulated verified sentence highlights in a single batch pass
        if annotator and verifier.verified_quotes:
            annotated_out = Path(annotated_pdf) if annotated_pdf else (out_path / f"{target_pdf.stem}_annotated.pdf")
            saved_annotated = verifier.save_annotated_pdf(annotated_out)
            if saved_annotated:
                console.print(f"[bold green]✨ Highlighted proof PDF saved to: {saved_annotated}[/bold green]")

        return

    if not topic:
        topic = click.prompt("Research topic/question")

    console.print(Panel.fit(
        f"[bold cyan]MedDraft_AI — Automated Medical Writing Platform[/bold cyan]\n"
        f"Topic: [yellow]{topic}[/yellow] | Type: [green]{manuscript_type}[/green] | Humanize: [magenta]{humanize}[/magenta]",
        border_style="cyan"
    ))

    evidence_summary = ""
    sr_mode = manuscript_type in ("systematic-review", "meta-analysis")

    # Use the PDF's parent as the project directory when available. This keeps
    # the documented PDF command useful even when the source PDF is accompanied
    # by extracted Markdown files rather than being present locally.
    project_path = Path(project_dir) if project_dir else None
    if project_path is None and pdf_input:
        candidate = Path(pdf_input).parent
        if candidate.exists():
            project_path = candidate

    project_context = ""
    evidence_manifest = ""
    tabular_evidence = ""
    if project_path and project_path.is_dir():
        project_context = load_project_context(project_path)
        source_count = len(list(project_path.rglob("*.md")))
        console.print(f"  Loaded [green]{source_count}[/] project Markdown file(s) from [green]{project_path}[/]")

        # Step 0 of the SR/MA Discussion skill: prove the whole workspace was
        # inspected, and expose CSV/JSON pooled tables that Markdown loading misses.
        if sr_mode:
            inventory = inventory_project([project_path])
            evidence_manifest = inventory.to_markdown()[:8000]
            tabular_evidence = load_tabular_evidence(project_path)
            console.print(
                f"  SR/MA evidence inventory: [green]{len(inventory.files)}[/] file(s) "
                f"across {len(inventory.categories)} categories."
            )

    # --- Step 1: Deep Literature Search ---
    console.print("\n[bold blue]Phase 1: Multi-Stage Literature Search[/bold blue]")
    orchestrator = ResearchOrchestrator()
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task("Querying PubMed, ScienceDirect, Scholar, CrossRef...", total=None)
        papers = orchestrator.deep_search(topic, limit=search_depth)
    
    console.print(f"  Found and deduplicated [green]{len(papers)}[/green] relevant studies.")
    
    evidence_parts = []
    for idx, p in enumerate(papers[:5], start=1):
        evidence_parts.append(f"{idx}. {p.get('title')} ({p.get('year')}) - {p.get('journal')} [DOI: {p.get('doi')}]")
    evidence_summary = "\n".join(evidence_parts)

    # --- Step 1b: Automatic ClinicalTrials.gov enrichment ---
    # The medical-clinicaltrials skill routes itself: bounded lookup only when
    # the topic carries clinical signals (trial/phase/randomized/NCT...).
    try:
        from meddraft_ai.search.clinicaltrials import should_include_trials
        if should_include_trials(topic):
            trials = orchestrator.search_trials(query=topic, limit=5)
            console.print(f"  Found [green]{len(trials)}[/green] registered trial(s) on ClinicalTrials.gov.")
            for t in trials:
                evidence_parts.append(
                    f"T. {t.get('title')} [{t.get('phase')}; {t.get('status')}] "
                    f"NCT: {t.get('nct_id')} {t.get('url')}"
                )
            evidence_summary = "\n".join(evidence_parts)
        else:
            console.print("  No clinical-trial signals in topic; skipping ClinicalTrials.gov lookup.")
    except Exception as exc:
        console.print(f"  [yellow]ClinicalTrials.gov lookup skipped: {exc}[/yellow]")

    # --- Step 2: PDF Ingestion (if provided) ---
    if pdf_input and Path(pdf_input).exists():
        console.print("\n[bold blue]Phase 2: Extracting Text & Metadata from PDF Input[/bold blue]")
        reader = PDFReader(pdf_input)
        pdf_text = reader.read_text()
        evidence_summary += f"\n\nPDF INPUT TEXT:\n{pdf_text[:25000]}"
        console.print(f"  Extracted text from [green]{Path(pdf_input).name}[/green]")

        # --- Step 2b: Automatic secondary/nested citation tracing ---
        # The secondary-citation-extractor skill routes itself: it only runs
        # when the PDF text contains traceable secondary markers (as cited in,
        # bracket/author-date keys + bibliography language).
        try:
            from meddraft_ai.extraction.secondary_citation import (
                SecondaryCitationExtractor,
            )
            if SecondaryCitationExtractor.should_trigger(pdf_text):
                traced = SecondaryCitationExtractor.extract(
                    pdf_text,
                    container_meta=reader.extract_metadata(),
                    citation_style=citation_style,
                    max_claims=5,
                )
                console.print(
                    f"  Traced [green]{len(traced)}[/green] secondary citation(s) "
                    f"to root sources (dual attribution)."
                )
                for item in traced:
                    evidence_summary += (
                        f"\n\nSECONDARY CITATION: {item.in_text_attribution()}\n"
                        f"Claim: {item.claim[:400]}\n"
                        f"Root: {', '.join(item.root.authors) or '?'} — "
                        f"{item.root.title or '?'} "
                        f"({item.root.year or 'n.d.'})"
                        f"{' DOI:' + item.root.doi if item.root.doi else ''}"
                    )
            else:
                console.print("  No secondary/nested citation markers detected; skipping dual tracing.")
        except Exception as exc:
            console.print(f"  [yellow]Secondary citation tracing skipped: {exc}[/yellow]")

    # --- Step 3: Statistical Results Reporting (if data file provided) ---
    stats_narrative = ""
    if data_file and Path(data_file).exists():
        console.print("\n[bold blue]Phase 3: APA Statistical Results Drafting[/bold blue]")
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                stats_json = json.load(f)
            writer = MedicalWriterAgent()
            stats_narrative = writer.write_report(stats_json, topic)
            console.print("  Generated APA 7th statistical Results narrative.")
        except Exception as e:
            console.print(f"  ⚠️ Could not process data file: {e}")

    # --- Step 4: Core Manuscript Drafting ---
    console.print("\n[bold blue]Phase 4: Sequential IMRAD Manuscript Drafting[/bold blue]")
    writer_agent = (
        SystematicReviewDiscussionSpecialist() if sr_mode else CoreWriterSpecialist()
    )
    
    section_list = [
        "Title and Abstract", "Introduction", "Literature Review",
        "Methodology", "Results", "Discussion", "Conclusion & Future Work"
    ] if sections == "all" else [s.strip() for s in sections.split(",")]
    if sections == "all" and manuscript_type in ("thesis", "systematic-review", "meta-analysis") and project_context:
        # These document types are source-grounded: never regenerate protocol
        # or Results text from memory when the authoritative files are present.
        section_list = ["Discussion", "References"]

    manuscript_draft_parts = [f"# {topic.title()}\n"]
    discussion_text = ""

    for sec in section_list:
        console.print(f"  Drafting section: [yellow]{sec}[/yellow]...")
        if sec.lower() == "results" and stats_narrative:
            manuscript_draft_parts.append(f"## {sec}\n\n{stats_narrative}\n")
        else:
            prompt = (
                f"Draft the '{sec}' section for a medical {manuscript_type} on the topic: '{topic}'.\n"
                f"Use citation style: {citation_style}.\n"
                "Use the project files below as the authoritative source for study design, results, notes, and supplied references. "
                "Do not invent data, references, or missing protocol details. For Discussion, answer the research question first, "
                "compare agreeing and conflicting studies, address heterogeneity and limitations, and use the exact required ending "
                "headers: ## Summary, ## Summary of results, ## Conclusions, ## Limitations, ## Recommendations, ## References.\n"
                f"Synthesize the following verified literature evidence:\n{evidence_summary}\n"
                f"PROJECT MATERIALS:\n{project_context}"
            )
            if sr_mode:
                prompt += SR_DISCUSSION_DIRECTIVE
                if evidence_manifest:
                    prompt += f"\n\nWORKSPACE EVIDENCE INVENTORY (Step 0 proof):\n{evidence_manifest}"
                if tabular_evidence:
                    prompt += f"\n\nPOOLED / TABULAR EVIDENCE FILES:\n{tabular_evidence}"

            if sr_mode and sec.lower() == "discussion":
                sec_text = writer_agent.draft(prompt)
                discussion_text = sec_text
            else:
                sec_text = writer_agent.execute(prompt)
            manuscript_draft_parts.append(f"## {sec}\n\n{sec_text}\n")

    full_draft = "\n".join(manuscript_draft_parts)

    # --- Step 4b: SR/MA Discussion quality gate (deterministic) ---
    sr_audit = None
    fidelity = None
    if sr_mode and discussion_text:
        console.print("\n[bold blue]Phase 4b: Systematic-Review Discussion Quality Gate[/bold blue]")
        sr_audit = audit_discussion(
            discussion_text,
            required_outcomes=list(sr_require) or None,
        )
        (out_path / "sr_discussion_audit.json").write_text(
            json.dumps(sr_audit.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        console.print(
            f"  Words: {sr_audit.word_count} | Errors: [red]{len(sr_audit.errors)}[/] | "
            f"Warnings: [yellow]{len(sr_audit.warnings)}[/]"
        )
        for finding in sr_audit.errors[:10]:
            console.print(f"    [red]• {finding.code}: {finding.message}[/red]")
        for finding in sr_audit.warnings[:6]:
            console.print(f"    [yellow]• {finding.code}: {finding.message}[/yellow]")

        if project_path and project_path.is_dir():
            source_texts = read_source_texts([project_path])
            fidelity = check_numeric_fidelity(discussion_text, source_texts)
            (out_path / "sr_discussion_fidelity.json").write_text(
                json.dumps(fidelity.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            console.print(
                f"  Numeric fidelity: {len(fidelity.matched)} matched, "
                f"[yellow]{len(fidelity.unmatched)}[/] token(s) not found in the evidence files."
            )

    # --- Step 5: Proofreading & Scientific Prose Audit ---
    console.print("\n[bold blue]Phase 5: Scientific Prose Audit (5-Pass SciWrite)[/bold blue]")
    proofreader = ProofReaderSpecialist()
    proof_prompt = (
        "Audit and polish this manuscript draft for active voice, clarity, and "
        f"keyword consistency:\n\n{full_draft}"
    )
    if sr_audit and sr_audit.errors:
        gate_lines = "\n".join(
            f"- {finding.code}: {finding.message}" for finding in sr_audit.errors
        )
        proof_prompt += (
            "\n\nThis is a systematic-review Discussion. Resolve these skill-gate errors "
            "without changing any number, statistic, or citation, and without adding new claims:\n"
            f"{gate_lines}"
        )
    full_draft = proofreader.execute(proof_prompt)

    # --- Step 6: References Live Validation ---
    console.print("\n[bold blue]Phase 6: Live Reference Verification[/bold blue]")
    reference_report = out_path / "reference_verification_report.json"
    verified_count, unverified_dois = verify_and_report_references(full_draft, reference_report)
    console.print(f"  Verified [green]{verified_count}[/green] references via CrossRef & PubMed APIs.")
    if unverified_dois:
        console.print(
            f"  [bold red]⚠ {len(unverified_dois)} DOI(s) could not be verified[/bold red] "
            f"(report: {reference_report.name})"
        )
        for doi in unverified_dois[:10]:
            console.print(f"    [red]• {doi}[/red]")

    # --- Step 7: On-demand Humanization Pass ---
    if humanize:
        console.print("\n[bold blue]Phase 7: On-Demand Humanization Pass (Dr. Noora Persona)[/bold blue]")
        humanizer = HumanizerSpecialist()
        full_draft = humanizer.humanize(full_draft)

        # Humanization can alter citation formatting, so verify the final text.
        verified_count, unverified_dois = verify_and_report_references(full_draft, reference_report)
        console.print(
            f"  Final draft reference check returned [green]{verified_count}[/] verified references."
        )
        if unverified_dois:
            console.print(
                f"  [bold red]⚠ {len(unverified_dois)} DOI(s) still unverified[/bold red] "
                f"(report: {reference_report.name})"
            )

    # --- Step 8: Document Export ---
    console.print("\n[bold blue]Phase 8: Exporting Output Documents[/bold blue]")
    safe_title = "_".join(re.sub(r'[^a-zA-Z0-9\s_]', '', topic).split())[:50]
    md_file = out_path / f"{safe_title}_manuscript.md"
    docx_file = out_path / f"{safe_title}_manuscript.docx"

    # The Markdown is the canonical artifact: DOCX export reads it, so it is
    # always written regardless of the requested output format.
    md_file.write_text(full_draft, encoding="utf-8")

    if output_format in ("md", "both"):
        console.print(f"  [green]Markdown manuscript saved: {md_file}[/green]")

    if output_format in ("docx", "both"):
        try:
            convert_markdown_to_docx(md_file, docx_file)
            console.print(f"  [green]DOCX manuscript saved: {docx_file}[/green]")
        except Exception as export_err:
            console.print(f"  [yellow]⚠️ DOCX export failed (Pandoc/python-docx): {export_err}[/yellow]")
            console.print(f"  [green]Markdown saved as fallback: {md_file}[/green]")

    console.print(Panel.fit("[bold green]✨ Manuscript Generation Completed Successfully![/bold green]", border_style="green"))

if __name__ == "__main__":
    main()
