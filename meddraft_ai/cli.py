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
        else:
            print(json.dumps({"error": "No refs subcommand given. Use deep-search, scholar-search, deep-dive or download."}, indent=2))
            return 1
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
