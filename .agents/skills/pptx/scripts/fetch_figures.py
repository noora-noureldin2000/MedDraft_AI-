#!/usr/bin/env python
"""Fill figure slots with sourced, licence-checkable images.

Two modes:

Blueprint mode (the deck workflow)::

    python fetch_figures.py --blueprint deck.json
    # reads every {"kind": "figure", "query": ...} slide, downloads one image
    # per slot into figures/, sets slide["image_path"], adds a credit line, and
    # rewrites the blueprint so deck_builder.py can embed the files.

One-off mode::

    python fetch_figures.py --query "gingival sulcus histology" --out-dir figures

The search uses MedDraft's provider chain: SerpApi -> Google Custom Search ->
Brave -> bundled Playwright fallback. Exhausted free tiers are skipped by the
local quota ledger, so a deck does not burn one provider's quota when another
still has room. Every image gets a JSON provenance sidecar with the source page
and the exact query, so attribution survives after the URLs rot.

Run ``python -m meddraft_ai.cli refs image-providers`` to see what is configured.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from blueprint_io import read_json  # noqa: E402
from meddraft_ai.search.image_fetch import (  # noqa: E402
    DEFAULT_EXCLUDE_TERMS,
    fetch_figures,
    slugify,
)

LOGGER = logging.getLogger("fetch_figures")


def _figure_specs_from_blueprint(blueprint: dict[str, Any], base_dir: Path, *, refresh: bool) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for index, slide in enumerate(blueprint.get("slides") or [], start=1):
        if not isinstance(slide, dict) or str(slide.get("kind")) != "figure":
            continue
        query = str(slide.get("query") or "").strip()
        if not query:
            LOGGER.warning("Figure slide %s has no query; skipped.", index)
            continue
        existing = str(slide.get("image_path") or "").strip()
        if existing and not refresh:
            candidate = Path(existing)
            if not candidate.is_absolute():
                candidate = base_dir / candidate
            if candidate.is_file():
                LOGGER.info("Figure slide %s already has %s; skipped (use --refresh).", index, existing)
                continue
        spec: dict[str, Any] = {
            "id": str(slide.get("id") or f"slide-{index:02d}-{slugify(slide.get('title') or query)}"),
            "title": slide.get("title"),
            "query": query,
        }
        for key in ("required_terms", "exclude_terms", "preferred_hosts"):
            if slide.get(key):
                spec[key] = slide[key]
        spec["_slide_index"] = index
        specs.append(spec)
    return specs


def _apply_results(
    blueprint: dict[str, Any],
    figures: Sequence[dict[str, Any]],
    base_dir: Path,
) -> int:
    """Write image_path/credit back into figure slides. Returns slides updated."""
    by_index = {
        int(item["_slide_index"]): item
        for item in figures
        if item.get("_slide_index") is not None
    }
    updated = 0
    for index, slide in enumerate(blueprint.get("slides") or [], start=1):
        item = by_index.get(index)
        if not item:
            continue
        path = Path(item["path"])
        try:
            relative = path.relative_to(base_dir)
        except ValueError:
            relative = path
        slide["image_path"] = relative.as_posix()
        slide["figure_query"] = item.get("query")
        slide["figure_provider"] = item.get("provider")
        slide["figure_sha256"] = item.get("sha256")
        if item.get("context_url"):
            slide["context_url"] = item["context_url"]
        if not str(slide.get("credit") or "").strip():
            source = item.get("context_url") or item.get("image_url") or ""
            slide["credit"] = f"Source: {source}" if source else "Sourced figure; verify licence."
        if not str(slide.get("caption") or "").strip() and item.get("title"):
            slide["caption"] = item["title"]
        updated += 1
    return updated


def _flatten(specs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip CLI-only keys before handing specs to the library."""
    return [{k: v for k, v in spec.items() if not k.startswith("_")} for spec in specs]


def _print_table(result: dict[str, Any]) -> None:
    figures = result.get("figures") or []
    for item in figures:
        print(
            f"OK  {item['id']}: {item.get('width')}x{item.get('height')} "
            f"{item.get('provider')} -> {item['path']}"
        )
    for failure in result.get("failures") or []:
        print(f"FAIL {failure.get('id')}: {failure.get('error')}", file=sys.stderr)
    print(
        f"\n{result.get('count', 0)} figure(s), {result.get('failed', 0)} failure(s); "
        f"providers: {result.get('providers') or {}}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--blueprint", help="Blueprint JSON with figure slides to fill.")
    parser.add_argument("--query", action="append", default=[], help="One-off image query (repeatable).")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Image directory (default: <blueprint dir>/figures, or ./figures).",
    )
    parser.add_argument("--limit", type=int, default=6, help="Candidates to try per figure (max 10).")
    parser.add_argument("--provider-order", default=None, help="serpapi,google_cse,brave,browser")
    parser.add_argument("--safe-search", default="active", choices=["active", "off"])
    parser.add_argument("--require-term", action="append", default=[], help="Term that should appear (repeatable).")
    parser.add_argument(
        "--exclude-term",
        action="append",
        default=None,
        help=f"Disqualifying term (default: {', '.join(DEFAULT_EXCLUDE_TERMS)}).",
    )
    parser.add_argument("--prefer-host", action="append", default=[], help="Preferred source host (repeatable).")
    parser.add_argument("--min-width", type=int, default=800, help="Reject narrower images (default 800).")
    parser.add_argument("--min-height", type=int, default=600, help="Reject shorter images (default 600).")
    parser.add_argument("--timeout", type=float, default=None, help="Per-request timeout in seconds.")
    parser.add_argument("--refresh", action="store_true", help="Replace figure slides that already have an image.")
    parser.add_argument("--dry-run", action="store_true", help="Search and list candidates without downloading.")
    parser.add_argument("--no-write", action="store_true", help="Do not rewrite the blueprint.")
    parser.add_argument("--out-blueprint", default=None, help="Write the filled blueprint here.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown image blocks.")
    parser.add_argument("--json", action="store_true", help="Emit the full JSON envelope.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.blueprint and not args.query:
        parser.error("use --blueprint or at least one --query")

    blueprint: dict[str, Any] | None = None
    base_dir = Path.cwd()
    if args.blueprint:
        blueprint_path = Path(args.blueprint)
        try:
            blueprint = read_json(blueprint_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"error: cannot read blueprint: {exc}", file=sys.stderr)
            return 2
        base_dir = blueprint_path.parent

    out_dir = Path(args.out_dir) if args.out_dir else base_dir / "figures"

    specs: list[dict[str, Any]] = []
    if blueprint is not None:
        specs.extend(_figure_specs_from_blueprint(blueprint, base_dir, refresh=args.refresh))
    for query in args.query:
        specs.append({"id": slugify(query), "query": query, "title": query})

    if not specs:
        print(json.dumps({"success": True, "figures": [], "failures": [], "note": "nothing to fetch"}, indent=2))
        return 0

    result = fetch_figures(
        _flatten(specs),
        out_dir,
        limit=args.limit,
        provider_order=args.provider_order,
        safe_search=args.safe_search,
        required_terms=args.require_term or None,
        exclude_terms=args.exclude_term if args.exclude_term is not None else DEFAULT_EXCLUDE_TERMS,
        preferred_hosts=args.prefer_host or None,
        min_width=args.min_width,
        min_height=args.min_height,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )

    # Re-attach the slide index for blueprint write-back (ids are unique per slide).
    if blueprint is not None and not args.dry_run:
        index_by_id = {
            str(spec["id"]): spec["_slide_index"]
            for spec in specs
            if spec.get("_slide_index") is not None
        }
        for item in result.get("figures") or []:
            if item.get("id") in index_by_id:
                item["_slide_index"] = index_by_id[item["id"]]
        updated = _apply_results(blueprint, result.get("figures") or [], base_dir)
        result["blueprint_slides_updated"] = updated
        if updated and not args.no_write:
            target = Path(args.out_blueprint) if args.out_blueprint else Path(args.blueprint)
            target.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False), encoding="utf-8")
            result["blueprint_written"] = str(target)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.markdown:
        for item in result.get("figures") or []:
            print(f"![{item.get('title') or item['id']}]({item.get('image_url')})")
            print(f"\nSource: {item.get('context_url') or 'n/a'}\n")
    else:
        _print_table(result)

    return 0 if not result.get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
