import os
import sys
import json
import subprocess
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from meddraft_ai.core.config import get_config
from meddraft_ai.search.academic_search import (
    search_pubmed_api,
    search_sciencedirect_api,
    search_google_scholar_api,
    search_crossref_api,
    search_semantic_scholar_api,
    search_europe_pmc,
    search_clinicaltrials_gov,
    search_doaj
)

logger = logging.getLogger(__name__)

def clean_title(title: str) -> str:
    """Normalize paper title for fuzzy comparison."""
    if not title:
        return ""
    title = title.lower().replace('-', ' ')
    title = re.sub(r'[^a-z0-9\s]', '', title)
    return " ".join(title.split())

def title_similarity(t1: str, t2: str) -> float:
    """Calculates Jaccard word similarity between two titles (0.0 to 1.0)."""
    c1 = clean_title(t1)
    c2 = clean_title(t2)
    if not c1 or not c2:
        return 0.0
    w1 = set(c1.split())
    w2 = set(c2.split())
    if not w1 or not w2:
        return 0.0
    return len(w1.intersection(w2)) / len(w1.union(w2))

class ResearchOrchestrator:
    """
    Omni-channel academic literature review and search orchestrator.
    Priority order: PubMed API -> ScienceDirect API -> Google Scholar -> Secondary APIs.
    """

    def __init__(self):
        self.config = get_config()
        self.cli_path = Path(__file__).parent / "browser_engine" / "dist" / "cli.js"
        self.download_dir = self.config.OUTPUT_DIR / "downloaded_papers"
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _call_browser_engine(self, command: str, *args) -> Dict[str, Any]:
        """Calls the Node.js Playwright stealth CLI."""
        node_cmd = ["node", str(self.cli_path), command] + list(args)
        
        try:
            env = os.environ.copy()
            env["BROWSER_HEADLESS"] = "false" if self.config.BROWSER_HEADLESS == False else "true"
            if self.config.BROWSER_PROXY_SERVER:
                env["PROXY_SERVER"] = self.config.BROWSER_PROXY_SERVER
            if self.config.BROWSER_PROXY_USERNAME:
                env["PROXY_USERNAME"] = self.config.BROWSER_PROXY_USERNAME
            if self.config.BROWSER_PROXY_PASSWORD:
                env["PROXY_PASSWORD"] = self.config.BROWSER_PROXY_PASSWORD

            result = subprocess.run(
                node_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                env=env
            )
            
            stdout_lines = result.stdout.strip().split('\n')
            for line in reversed(stdout_lines):
                if line.startswith('{') and line.endswith('}'):
                    return json.loads(line)
            
            return {"success": False, "error": f"No JSON output from browser engine: {result.stdout}"}
        except Exception as e:
            logger.error(f"Browser engine execution exception: {e}")
            return {"success": False, "error": str(e)}

    def search_scholar_stealth(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Searches Google Scholar using the stealth browser engine."""
        res = self._call_browser_engine("scholar-search", query, str(limit))
        if res.get("success"):
            return res.get("results", [])
        return []

    def deep_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Unified, deduplicated search across primary and secondary databases."""
        papers = []

        # 1. PubMed API (Primary)
        try:
            pm_data = json.loads(search_pubmed_api(query, limit=limit))
            for p in pm_data.get("results", []):
                papers.append({
                    "title": p.get("title", ""),
                    "authors": p.get("authors", ""),
                    "year": p.get("year", ""),
                    "journal": p.get("journal", ""),
                    "doi": p.get("doi", ""),
                    "pmid": p.get("pmid", ""),
                    "url": p.get("url", ""),
                    "source": "PubMed API"
                })
        except Exception as e:
            logger.warning(f"PubMed API search failed: {e}")

        # 2. ScienceDirect API (Primary)
        try:
            sd_data = json.loads(search_sciencedirect_api(query, limit=limit))
            for p in sd_data.get("results", []):
                papers.append({
                    "title": p.get("title", ""),
                    "authors": p.get("authors", ""),
                    "year": p.get("year", ""),
                    "journal": p.get("journal", ""),
                    "doi": p.get("doi", ""),
                    "pmid": "",
                    "url": p.get("url", ""),
                    "source": "ScienceDirect API"
                })
        except Exception as e:
            logger.warning(f"ScienceDirect API search failed: {e}")

        # 3. Google Scholar Stealth (Primary Fallback)
        scholar_results = self.search_scholar_stealth(query, limit=limit)
        for p in scholar_results:
            papers.append({
                "title": p.get("title", ""),
                "authors": p.get("authors", ""),
                "year": p.get("year", ""),
                "journal": "",
                "doi": "",
                "pmid": "",
                "url": p.get("url", ""),
                "pdf_url": p.get("pdfLink"),
                "source": "Google Scholar Stealth"
            })

        # 4. Secondary APIs (CrossRef, Semantic Scholar, Europe PMC)
        for search_fn, name in [
            (search_crossref_api, "CrossRef"),
            (search_semantic_scholar_api, "Semantic Scholar"),
            (search_europe_pmc, "Europe PMC")
        ]:
            try:
                sec_data = json.loads(search_fn(query, limit=limit))
                for p in sec_data.get("results", []):
                    papers.append({
                        "title": p.get("title", ""),
                        "authors": p.get("authors", ""),
                        "year": p.get("year", ""),
                        "journal": p.get("journal", ""),
                        "doi": p.get("doi", ""),
                        "pmid": p.get("pmid", ""),
                        "url": p.get("url", ""),
                        "source": name
                    })
            except Exception:
                pass

        # Deduplication and merging
        deduplicated: List[Dict[str, Any]] = []
        for p in papers:
            if not p.get("title"):
                continue
            match_found = False
            for existing in deduplicated:
                if p.get("doi") and existing.get("doi") and p["doi"].lower() == existing["doi"].lower():
                    match_found = True
                elif p.get("pmid") and existing.get("pmid") and p["pmid"] == existing["pmid"]:
                    match_found = True
                elif title_similarity(p["title"], existing["title"]) > 0.85:
                    match_found = True

                if match_found:
                    if not existing.get("doi") and p.get("doi"):
                        existing["doi"] = p["doi"]
                    if not existing.get("pmid") and p.get("pmid"):
                        existing["pmid"] = p["pmid"]
                    if not existing.get("pdf_url") and p.get("pdf_url"):
                        existing["pdf_url"] = p["pdf_url"]
                    existing["source"] = f"{existing['source']} + {p['source']}"
                    break

            if not match_found:
                deduplicated.append(p)

        return deduplicated[:limit]
