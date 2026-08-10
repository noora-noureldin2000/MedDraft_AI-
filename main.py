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
    VerifierAndStatsSpecialist,
    ProofReaderSpecialist
)
from meddraft_ai.agents.medical_writer_agent import MedicalWriterAgent
from meddraft_ai.validation.reference_validator import validate_references
from meddraft_ai.export.pandoc_converter import convert_markdown_to_docx

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@click.command()
@click.option("--topic", prompt="Research topic/question", help="The medical topic or research question to write about.")
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
    provider: str,
    verbose: bool
):
    """
    MedDraft_AI: Production-Ready Standalone Medical Research Writing Platform.
    """
    console.print(Panel.fit(
        f"[bold cyan]MedDraft_AI — Automated Medical Writing Platform[/bold cyan]\n"
        f"Topic: [yellow]{topic}[/yellow] | Type: [green]{manuscript_type}[/green] | Humanize: [magenta]{humanize}[/magenta]",
        border_style="cyan"
    ))

    config = get_config()
    if provider:
        config.LLM_PROVIDER = provider

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    evidence_summary = ""

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

    # --- Step 2: PDF Ingestion (if provided) ---
    if pdf_input and Path(pdf_input).exists():
        console.print("\n[bold blue]Phase 2: Extracting Text & Metadata from PDF Input[/bold blue]")
        reader = PDFReader(pdf_input)
        pdf_text = reader.read_text()
        evidence_summary += f"\n\nPDF INPUT TEXT SNIPPET:\n{pdf_text[:3000]}"
        console.print(f"  Extracted text from [green]{Path(pdf_input).name}[/green]")

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
    writer_agent = CoreWriterSpecialist()
    
    section_list = [
        "Title and Abstract", "Introduction", "Literature Review",
        "Methodology", "Results", "Discussion", "Conclusion & Future Work"
    ] if sections == "all" else [s.strip() for s in sections.split(",")]

    manuscript_draft_parts = [f"# {topic.title()}\n"]

    for sec in section_list:
        console.print(f"  Drafting section: [yellow]{sec}[/yellow]...")
        if sec.lower() == "results" and stats_narrative:
            manuscript_draft_parts.append(f"## {sec}\n\n{stats_narrative}\n")
        else:
            prompt = (
                f"Draft the '{sec}' section for a medical {manuscript_type} on the topic: '{topic}'.\n"
                f"Use citation style: {citation_style}.\n"
                f"Synthesize the following verified literature evidence:\n{evidence_summary}"
            )
            sec_text = writer_agent.execute(prompt)
            manuscript_draft_parts.append(f"## {sec}\n\n{sec_text}\n")

    full_draft = "\n".join(manuscript_draft_parts)

    # --- Step 5: Proofreading & Scientific Prose Audit ---
    console.print("\n[bold blue]Phase 5: Scientific Prose Audit (5-Pass SciWrite)[/bold blue]")
    proofreader = ProofReaderSpecialist()
    full_draft = proofreader.execute(f"Audit and polish this manuscript draft for active voice, clarity, and keyword consistency:\n\n{full_draft}")

    # --- Step 6: References Live Validation ---
    console.print("\n[bold blue]Phase 6: Live Reference Verification[/bold blue]")
    citations = validate_references(full_draft)
    console.print(f"  Verified [green]{len(citations)}[/green] references via CrossRef & PubMed APIs.")

    # --- Step 7: On-demand Humanization Pass ---
    if humanize:
        console.print("\n[bold blue]Phase 7: On-Demand Humanization Pass (Dr. Noora Persona)[/bold blue]")
        humanizer = HumanizerSpecialist()
        full_draft = humanizer.humanize(full_draft)

    # --- Step 8: Document Export ---
    console.print("\n[bold blue]Phase 8: Exporting Output Documents[/bold blue]")
    safe_title = "_".join(re.sub(r'[^a-zA-Z0-9\s_]', '', topic).split())[:50]
    md_file = out_path / f"{safe_title}_manuscript.md"
    docx_file = out_path / f"{safe_title}_manuscript.docx"

    # Write markdown once — shared by both md and docx paths
    if output_format in ("md", "both", "docx"):
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
