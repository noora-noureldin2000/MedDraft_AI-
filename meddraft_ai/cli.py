"""Command-line interface for MedDraft_AI.

Primary usage from the research-surfer skill:

    python -m meddraft_ai refs deep-search "query" --limit 5
    python -m meddraft_ai refs scholar-search "query" --limit 5
    python -m meddraft_ai refs deep-dive "doi_or_pmid_or_json"
    python -m meddraft_ai refs download '{"title": "...", "pdf_url": "..."}'
"""

import argparse
import json
import sys
from typing import List, Optional


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meddraft_ai", description="MedDraft_AI research CLI.")
    sub = parser.add_subparsers(dest="command")

    refs = sub.add_parser("refs", help="Academic literature search & retrieval commands.")
    refs_sub = refs.add_subparsers(dest="refs_command")

    deep = refs_sub.add_parser("deep-search", help="Combined APIs + browser deep search.")
    deep.add_argument("query", help="Search query string.")
    deep.add_argument("--limit", type=int, default=10, help="Max results (default 10).")

    scholar = refs_sub.add_parser("scholar-search", help="Google Scholar stealth browser search.")
    scholar.add_argument("query", help="Search query string.")
    scholar.add_argument("--limit", type=int, default=10, help="Max results (default 10).")

    dive = refs_sub.add_parser("deep-dive", help="Full metadata for a paper: abstract, OA, PMCID.")
    dive.add_argument("identifier", help="DOI, PMID (or PMID:12345), or JSON with doi/pmid/title.")

    download = refs_sub.add_parser("download", help="Download an open-access PDF.")
    download.add_argument("paper", help='JSON string: {"title": "...", "pdf_url": "..."}')
    download.add_argument("--output", default=None, help="Optional output directory.")

    secondary = refs_sub.add_parser(
        "secondary-cite",
        help="Trace nested/secondary citations in a PDF or excerpt to root sources.",
    )
    secondary.add_argument(
        "input",
        help="Path to a PDF file, or a raw text excerpt containing a cited claim.",
    )
    secondary.add_argument(
        "--style",
        default="Harvard",
        choices=["Harvard", "Vancouver"],
        help="Dual-attribution citation style (default: Harvard).",
    )
    secondary.add_argument(
        "--max", type=int, default=10, help="Max claims to trace (default 10)."
    )
    secondary.add_argument(
        "--markdown",
        action="store_true",
        help="Emit the skill's dual-attribution Markdown template instead of JSON.",
    )

    trials = refs_sub.add_parser(
        "trials-search",
        help="Filtered ClinicalTrials.gov search (condition/intervention/phase/status).",
    )
    trials.add_argument("--condition", default="", help="Disease/condition filter.")
    trials.add_argument("--intervention", default="", help="Drug/treatment filter.")
    trials.add_argument("--phase", default="", help="Trial phase filter (e.g. 'Phase 3').")
    trials.add_argument("--status", default="", help="Status filter (e.g. 'Recruiting').")
    trials.add_argument("--term", default="", help="Free-text query term.")
    trials.add_argument("--limit", type=int, default=10, help="Max results (default 10).")

    trial_get = refs_sub.add_parser(
        "trials-get", help="Full ClinicalTrials.gov record by NCT ID."
    )
    trial_get.add_argument("nct_id", help="NCT identifier, e.g. NCT04368728.")

    angles = refs_sub.add_parser(
        "plan-angles",
        help="Draft 3-5 structured Scholar search angles for a topic (search playbook).",
    )
    angles.add_argument("query", help="Research topic string.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command != "refs":
        print(json.dumps({"error": "Unknown command. Use 'refs'."}, indent=2))
        return 1

    try:
        from meddraft_ai.search.research_orchestrator import ResearchOrchestrator
        orchestrator = ResearchOrchestrator()
    except Exception as e:
        print(json.dumps({"error": f"Failed to initialize orchestrator: {e}"}, indent=2))
        return 1

    try:
        if args.refs_command == "deep-search":
            results = orchestrator.deep_search(args.query, limit=args.limit)
            print(json.dumps({"success": True, "count": len(results), "results": results}, indent=2))
        elif args.refs_command == "scholar-search":
            results = orchestrator.search_scholar_stealth(args.query, limit=args.limit)
            print(json.dumps({"success": True, "count": len(results), "results": results}, indent=2))
        elif args.refs_command == "deep-dive":
            result = orchestrator.deep_dive(args.identifier)
            print(json.dumps(result, indent=2))
        elif args.refs_command == "download":
            result = orchestrator.download(args.paper, output_dir=args.output)
            print(json.dumps(result, indent=2))
        elif args.refs_command == "secondary-cite":
            from pathlib import Path
            from meddraft_ai.extraction.secondary_citation import (
                SecondaryCitationExtractor,
            )
            source = args.input
            candidate = Path(source)
            if candidate.exists() and candidate.suffix.lower() == ".pdf":
                from meddraft_ai.extraction.pdf_reader import PDFReader
                text = PDFReader(candidate).read_text()
                meta: dict = {}
                try:
                    meta = PDFReader(candidate).extract_metadata()
                except Exception:
                    meta = {}
                container_meta = {"title": meta.get("title", ""), "author": meta.get("author", "")}
            else:
                text = source
                container_meta = {}
            traced = SecondaryCitationExtractor.extract(
                text,
                container_meta=container_meta,
                citation_style=args.style,
                max_claims=args.max,
            )
            if args.markdown:
                print(SecondaryCitationExtractor.extract_to_markdown(
                    text, container_meta, args.style, args.max
                ))
            else:
                print(json.dumps(
                    {"success": True, "count": len(traced),
                     "results": [c.to_dict() for c in traced]},
                    indent=2, default=str,
                ))
        elif args.refs_command == "trials-search":
            results = orchestrator.search_trials(
                query=args.term,
                condition=args.condition,
                intervention=args.intervention,
                phase=args.phase,
                status=args.status,
                limit=args.limit,
            )
            print(json.dumps({"success": True, "count": len(results), "results": results}, indent=2))
        elif args.refs_command == "trials-get":
            print(json.dumps(orchestrator.get_trial(args.nct_id), indent=2))
        elif args.refs_command == "plan-angles":
            from meddraft_ai.search.search_planner import plan_search_angles
            print(json.dumps(
                {"success": True, "angles": plan_search_angles(args.query)},
                indent=2,
            ))
        else:
            print(json.dumps({"error": "No refs subcommand given. Use deep-search, scholar-search, deep-dive, download, secondary-cite, trials-search, trials-get or plan-angles."}, indent=2))
            return 1
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
