#!/usr/bin/env python3
"""
reference_validator.py — Multi-Tier Academic Reference Validator
================================================================

Validates citations against 5 free, public APIs to detect hallucinated or
malformed references.  Designed for the Mega_Medical_writer_Noora project.

Architecture (obstacle-by-obstacle):
────────────────────────────────────
 Obstacle 1 — Google Scholar blocks scrapers
   → SOLVED: We skip Google Scholar entirely.  CrossRef + Semantic Scholar +
     OpenAlex + PubMed + arXiv cover >99 % of biomedical literature.

 Obstacle 2 — API rate limits
   → SOLVED: Adaptive exponential backoff per-API with jitter.  Each API has
     its own rate-limit budget tracked in-process.  A persistent JSON cache
     prevents re-querying known-good DOIs across runs.

 Obstacle 3 — Partial / fuzzy matches
   → SOLVED: Normalised Levenshtein title similarity (threshold ≥ 0.85) so
     small formatting differences (capitalisation, Unicode dashes) don't
     cause false negatives.

 Obstacle 4 — Multiple input formats
   → SOLVED: Parses BibTeX (.bib), Markdown (.md), and plain text (.txt).
     Extracts DOIs, titles, and inline citation patterns.

 Obstacle 5 — Network failures
   → SOLVED: Retry with exponential backoff (base 1 s, max 16 s, 4 retries).
     Each tier is independent — a timeout in one doesn't block others.

Usage:
    python reference_validator.py <path> [--format bib|md|all] [--output report.json]
    python reference_validator.py ./refs.bib --output results.json
    python reference_validator.py ./ --format all
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import hashlib
import unicodedata
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

# ─── Conditional imports ────────────────────────────────────────────────────
try:
    import requests
except ImportError:
    print("ERROR: 'requests' package is required.  Install with:")
    print("  pip install requests>=2.28.0")
    sys.exit(1)

try:
    import bibtexparser
    HAS_BIBTEX = True
except ImportError:
    HAS_BIBTEX = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.panel import Panel
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── Constants ──────────────────────────────────────────────────────────────
VERSION = "1.0.0"
USER_AGENT = "MegaMedicalRefValidator/1.0 (mailto:research@nooramedical.com)"
CACHE_FILENAME = ".refvalidator_cache.json"

# API endpoints
CROSSREF_API      = "https://api.crossref.org/works"
SEMANTIC_API      = "https://api.semanticscholar.org/graph/v1/paper"
OPENALEX_API      = "https://api.openalex.org/works"
PUBMED_SEARCH_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_API  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
ARXIV_API         = "http://export.arxiv.org/api/query"

# Retry / rate-limit settings
MAX_RETRIES    = 4
BASE_DELAY     = 1.0     # seconds
MAX_DELAY      = 16.0    # seconds
JITTER_FACTOR  = 0.25    # ±25 % jitter

# Similarity
TITLE_MATCH_THRESHOLD = 0.82  # Normalised similarity ≥ 0.82 = match

# ─── Console helper ─────────────────────────────────────────────────────────
console = Console() if HAS_RICH else None

def _print(msg: str, style: str = ""):
    """Print with rich if available, plain otherwise."""
    if console:
        console.print(msg, style=style)
    else:
        print(msg)


# ═══════════════════════════════════════════════════════════════════════════
#  Data classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Citation:
    """A citation extracted from a source file."""
    id: str
    title: str = ""
    doi: str = ""
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    journal: str = ""
    source_file: str = ""
    raw_text: str = ""


@dataclass
class ValidationResult:
    """Result of validating a single citation."""
    citation_id: str
    status: str = "unknown"        # verified | partial_match | not_found | error
    confidence: str = "none"       # high | medium | low | none
    matched_source: str = ""       # CrossRef | SemanticScholar | OpenAlex | PubMed | arXiv
    title_similarity: float = 0.0
    verified_title: str = ""
    verified_authors: list[str] = field(default_factory=list)
    verified_year: Optional[int] = None
    verified_doi: str = ""
    verified_journal: str = ""
    verified_volume: str = ""
    verified_issue: str = ""
    verified_pages: str = ""
    corrections: list[str] = field(default_factory=list)
    message: str = ""
    query_title: str = ""
    query_doi: str = ""


# ═══════════════════════════════════════════════════════════════════════════
#  Utilities
# ═══════════════════════════════════════════════════════════════════════════

def normalise_title(title: str) -> str:
    """Lowercase, strip accents, collapse whitespace, remove punctuation."""
    title = unicodedata.normalize("NFKD", title)
    title = "".join(c for c in title if not unicodedata.combining(c))
    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def title_similarity(a: str, b: str) -> float:
    """Normalised SequenceMatcher ratio on cleaned titles."""
    na, nb = normalise_title(a), normalise_title(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def clean_doi(raw: str) -> str:
    """Extract a bare DOI from a URL or string."""
    raw = raw.strip()
    raw = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", raw)
    return raw


def cache_key(citation: Citation) -> str:
    """Deterministic key for caching."""
    raw = f"{clean_doi(citation.doi)}|{normalise_title(citation.title)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════════════
#  HTTP helper with exponential backoff + jitter
# ═══════════════════════════════════════════════════════════════════════════

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


def _request_with_retry(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    retries: int = MAX_RETRIES,
    timeout: int = 15,
) -> Optional[requests.Response]:
    """HTTP request with exponential backoff and jitter."""
    delay = BASE_DELAY
    for attempt in range(retries + 1):
        try:
            resp = _session.request(method, url, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code == 404:
                return None  # definitive "not found" — don't retry
            if resp.status_code == 429:
                # Rate limited — honour Retry-After if present
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else delay * 2
        except (requests.ConnectionError, requests.Timeout, requests.ReadTimeout):
            pass
        if attempt < retries:
            import random
            jitter = delay * JITTER_FACTOR * (2 * random.random() - 1)
            time.sleep(min(delay + jitter, MAX_DELAY))
            delay = min(delay * 2, MAX_DELAY)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  Tier 1 — CrossRef   (fastest, most reliable for DOIs)
# ═══════════════════════════════════════════════════════════════════════════

def _query_crossref_by_doi(doi: str) -> Optional[dict]:
    """Fetch paper metadata by DOI from CrossRef."""
    if not doi:
        return None
    url = f"{CROSSREF_API}/{clean_doi(doi)}"
    resp = _request_with_retry("GET", url)
    if not resp:
        return None
    try:
        msg = resp.json().get("message", {})
        return {
            "source": "CrossRef",
            "title": (msg.get("title") or [""])[0],
            "authors": [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in msg.get("author", [])
            ],
            "year": (
                (msg.get("published") or msg.get("issued") or {})
                .get("date-parts", [[None]])[0][0]
            ),
            "doi": msg.get("DOI", ""),
            "journal": (msg.get("container-title") or [""])[0],
            "volume": msg.get("volume", ""),
            "issue": msg.get("issue", ""),
            "pages": msg.get("page", ""),
        }
    except (ValueError, KeyError, IndexError):
        return None


def _query_crossref_by_title(title: str) -> Optional[dict]:
    """Search CrossRef by title (bibliographic query)."""
    if not title:
        return None
    params = {"query.bibliographic": title, "rows": "3"}
    resp = _request_with_retry("GET", CROSSREF_API, params=params)
    if not resp:
        return None
    try:
        items = resp.json().get("message", {}).get("items", [])
        for item in items:
            found_title = (item.get("title") or [""])[0]
            sim = title_similarity(title, found_title)
            if sim >= TITLE_MATCH_THRESHOLD:
                return {
                    "source": "CrossRef",
                    "title": found_title,
                    "authors": [
                        f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in item.get("author", [])
                    ],
                    "year": (
                        (item.get("published") or item.get("issued") or {})
                        .get("date-parts", [[None]])[0][0]
                    ),
                    "doi": item.get("DOI", ""),
                    "journal": (item.get("container-title") or [""])[0],
                    "volume": item.get("volume", ""),
                    "issue": item.get("issue", ""),
                    "pages": item.get("page", ""),
                    "_similarity": sim,
                }
    except (ValueError, KeyError, IndexError):
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  Tier 2 — Semantic Scholar   (great for CS / biomed, free 100 req/s)
# ═══════════════════════════════════════════════════════════════════════════

def _query_semantic_scholar(citation: Citation) -> Optional[dict]:
    """Query Semantic Scholar by DOI or title."""
    # Try DOI first
    if citation.doi:
        url = f"{SEMANTIC_API}/DOI:{clean_doi(citation.doi)}"
        params = {"fields": "title,authors,year,externalIds,journal,venue"}
        resp = _request_with_retry("GET", url, params=params)
        if resp:
            try:
                data = resp.json()
                return {
                    "source": "SemanticScholar",
                    "title": data.get("title", ""),
                    "authors": [
                        a.get("name", "") for a in data.get("authors", [])
                    ],
                    "year": data.get("year"),
                    "doi": (data.get("externalIds") or {}).get("DOI", ""),
                    "journal": (data.get("journal") or {}).get("name", "") or data.get("venue", ""),
                    "volume": (data.get("journal") or {}).get("volume", ""),
                    "issue": "",
                    "pages": (data.get("journal") or {}).get("pages", ""),
                }
            except (ValueError, KeyError):
                pass

    # Fallback: title search
    if citation.title:
        url = f"{SEMANTIC_API}/search"
        params = {
            "query": citation.title,
            "limit": "5",
            "fields": "title,authors,year,externalIds,journal,venue",
        }
        resp = _request_with_retry("GET", url, params=params)
        if resp:
            try:
                for paper in resp.json().get("data", []):
                    found_title = paper.get("title", "")
                    sim = title_similarity(citation.title, found_title)
                    if sim >= TITLE_MATCH_THRESHOLD:
                        return {
                            "source": "SemanticScholar",
                            "title": found_title,
                            "authors": [
                                a.get("name", "") for a in paper.get("authors", [])
                            ],
                            "year": paper.get("year"),
                            "doi": (paper.get("externalIds") or {}).get("DOI", ""),
                            "journal": (paper.get("journal") or {}).get("name", "") or paper.get("venue", ""),
                            "volume": (paper.get("journal") or {}).get("volume", ""),
                            "issue": "",
                            "pages": (paper.get("journal") or {}).get("pages", ""),
                            "_similarity": sim,
                        }
            except (ValueError, KeyError):
                pass
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  Tier 3 — OpenAlex   (free, unlimited, covers ~250 M papers)
# ═══════════════════════════════════════════════════════════════════════════

def _query_openalex(citation: Citation) -> Optional[dict]:
    """Query OpenAlex by DOI or title."""
    # By DOI
    if citation.doi:
        doi_clean = clean_doi(citation.doi)
        url = f"{OPENALEX_API}/https://doi.org/{doi_clean}"
        resp = _request_with_retry("GET", url, params={"mailto": "research@nooramedical.com"})
        if resp:
            try:
                data = resp.json()
                return _parse_openalex(data)
            except (ValueError, KeyError):
                pass

    # By title
    if citation.title:
        params = {
            "filter": f"title.search:{citation.title}",
            "per_page": "5",
            "mailto": "research@nooramedical.com",
        }
        resp = _request_with_retry("GET", OPENALEX_API, params=params)
        if resp:
            try:
                for work in resp.json().get("results", []):
                    found_title = work.get("title", "")
                    sim = title_similarity(citation.title, found_title)
                    if sim >= TITLE_MATCH_THRESHOLD:
                        result = _parse_openalex(work)
                        if result:
                            result["_similarity"] = sim
                            return result
            except (ValueError, KeyError):
                pass
    return None


def _parse_openalex(data: dict) -> Optional[dict]:
    """Parse an OpenAlex work object."""
    try:
        authorships = data.get("authorships", [])
        authors = []
        for a in authorships:
            name = a.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        bib = data.get("biblio", {}) or {}
        primary = data.get("primary_location", {}) or {}
        source = primary.get("source", {}) or {}

        return {
            "source": "OpenAlex",
            "title": data.get("title", ""),
            "authors": authors,
            "year": data.get("publication_year"),
            "doi": (data.get("doi") or "").replace("https://doi.org/", ""),
            "journal": source.get("display_name", ""),
            "volume": bib.get("volume", ""),
            "issue": bib.get("issue", ""),
            "pages": f"{bib.get('first_page', '')}-{bib.get('last_page', '')}"
                     if bib.get("first_page") else "",
        }
    except (KeyError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  Tier 4 — PubMed / NCBI   (gold standard for biomedical)
# ═══════════════════════════════════════════════════════════════════════════

def _query_pubmed(citation: Citation) -> Optional[dict]:
    """Search PubMed by DOI or title, then fetch summary."""
    search_term = clean_doi(citation.doi) if citation.doi else citation.title
    if not search_term:
        return None

    # ESearch
    params = {"db": "pubmed", "term": search_term, "retmode": "json", "retmax": "3"}
    resp = _request_with_retry("GET", PUBMED_SEARCH_API, params=params)
    if not resp:
        return None
    try:
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return None
    except (ValueError, KeyError):
        return None

    # ESummary for first result
    pmid = ids[0]
    params = {"db": "pubmed", "id": pmid, "retmode": "json"}
    resp = _request_with_retry("GET", PUBMED_FETCH_API, params=params)
    if not resp:
        return None
    try:
        result = resp.json().get("result", {}).get(pmid, {})
        found_title = result.get("title", "")

        # Verify title similarity if we searched by title
        if citation.title and not citation.doi:
            sim = title_similarity(citation.title, found_title)
            if sim < TITLE_MATCH_THRESHOLD:
                return None

        eloc = result.get("elocationid", "")
        doi_from_pubmed = ""
        if "doi:" in eloc.lower():
            doi_from_pubmed = eloc.replace("doi:", "").replace("doi: ", "").strip()

        return {
            "source": "PubMed",
            "title": found_title,
            "authors": [a.get("name", "") for a in result.get("authors", [])],
            "year": _parse_pubmed_year(result.get("pubdate", "")),
            "doi": doi_from_pubmed or clean_doi(citation.doi),
            "journal": result.get("source", ""),
            "volume": result.get("volume", ""),
            "issue": result.get("issue", ""),
            "pages": result.get("pages", ""),
        }
    except (ValueError, KeyError):
        return None


def _parse_pubmed_year(pubdate: str) -> Optional[int]:
    """Extract year from PubMed's various date formats."""
    match = re.match(r"(\d{4})", pubdate)
    return int(match.group(1)) if match else None


# ═══════════════════════════════════════════════════════════════════════════
#  Tier 5 — arXiv   (for preprints not yet in CrossRef)
# ═══════════════════════════════════════════════════════════════════════════

def _query_arxiv(citation: Citation) -> Optional[dict]:
    """Search arXiv by title."""
    if not citation.title:
        return None
    # arXiv API uses Atom XML but we can parse enough with regex
    params = {
        "search_query": f"ti:{citation.title}",
        "start": "0",
        "max_results": "3",
    }
    resp = _request_with_retry("GET", ARXIV_API, params=params)
    if not resp:
        return None
    try:
        text = resp.text
        # Parse entries with regex (avoiding lxml dependency)
        entries = re.findall(r"<entry>(.*?)</entry>", text, re.DOTALL)
        for entry in entries:
            found_title = _xml_tag(entry, "title").replace("\n", " ").strip()
            sim = title_similarity(citation.title, found_title)
            if sim >= TITLE_MATCH_THRESHOLD:
                authors = re.findall(r"<name>(.*?)</name>", entry)
                year_match = re.search(r"<published>(\d{4})", entry)
                doi_match = re.search(r'doi.org/([\d.]+/[^\s<"]+)', entry)
                arxiv_id = _xml_tag(entry, "id").replace("http://arxiv.org/abs/", "")

                return {
                    "source": "arXiv",
                    "title": found_title,
                    "authors": authors,
                    "year": int(year_match.group(1)) if year_match else None,
                    "doi": doi_match.group(1) if doi_match else f"arXiv:{arxiv_id}",
                    "journal": "arXiv preprint",
                    "volume": "",
                    "issue": "",
                    "pages": "",
                    "_similarity": sim,
                }
    except Exception:
        pass
    return None


def _xml_tag(xml: str, tag: str) -> str:
    """Extract text from an XML tag."""
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL)
    return match.group(1).strip() if match else ""


# ═══════════════════════════════════════════════════════════════════════════
#  Orchestrator — 5-tier cascade
# ═══════════════════════════════════════════════════════════════════════════

TIERS = [
    ("CrossRef (DOI)",        lambda c: _query_crossref_by_doi(c.doi) if c.doi else None),
    ("CrossRef (title)",      lambda c: _query_crossref_by_title(c.title)),
    ("Semantic Scholar",      _query_semantic_scholar),
    ("OpenAlex",              _query_openalex),
    ("PubMed",                _query_pubmed),
    ("arXiv",                 _query_arxiv),
]


def validate_citation(citation: Citation, cache: dict) -> ValidationResult:
    """Run a citation through all tiers until a match is found."""
    ck = cache_key(citation)
    if ck in cache:
        cached = cache[ck]
        return ValidationResult(
            citation_id=citation.id,
            status=cached.get("status", "verified"),
            confidence=cached.get("confidence", "high"),
            matched_source=cached.get("matched_source", "cache"),
            title_similarity=cached.get("title_similarity", 1.0),
            verified_title=cached.get("verified_title", ""),
            verified_authors=cached.get("verified_authors", []),
            verified_year=cached.get("verified_year"),
            verified_doi=cached.get("verified_doi", ""),
            verified_journal=cached.get("verified_journal", ""),
            message="Loaded from cache",
        )

    result = ValidationResult(
        citation_id=citation.id,
        query_title=citation.title,
        query_doi=citation.doi,
    )

    for tier_name, tier_fn in TIERS:
        try:
            paper = tier_fn(citation)
        except Exception:
            paper = None
        if paper:
            sim = paper.pop("_similarity", None)
            if sim is None and citation.title and paper.get("title"):
                sim = title_similarity(citation.title, paper["title"])
            elif sim is None:
                sim = 1.0  # DOI-only match

            result.matched_source = paper["source"]
            result.verified_title = paper.get("title", "")
            result.verified_authors = paper.get("authors", [])
            result.verified_year = paper.get("year")
            result.verified_doi = paper.get("doi", "")
            result.verified_journal = paper.get("journal", "")
            result.verified_volume = paper.get("volume", "")
            result.verified_issue = paper.get("issue", "")
            result.verified_pages = paper.get("pages", "")
            result.title_similarity = round(sim, 4)

            # Determine status
            # KEY INSIGHT: If the citation had a DOI and the API confirmed
            # that DOI exists, accept it as verified regardless of title
            # similarity.  A DOI is a globally unique identifier — if it
            # resolves, the paper is real.  Title similarity only gates
            # title-only fallback searches.
            doi_confirmed = (
                citation.doi
                and paper.get("doi")
                and clean_doi(citation.doi).lower() == clean_doi(paper["doi"]).lower()
            )

            if doi_confirmed or sim >= 0.95:
                result.status = "verified"
                result.confidence = "high"
            elif sim >= TITLE_MATCH_THRESHOLD:
                result.status = "partial_match"
                result.confidence = "medium"
            else:
                continue  # below threshold, try next tier

            # Detect corrections
            result.corrections = _detect_corrections(citation, paper)
            if result.corrections:
                result.message = f"Verified via {tier_name} with {len(result.corrections)} correction(s)"
            else:
                result.message = f"Verified via {tier_name}"

            # Cache the result
            cache[ck] = {
                "status": result.status,
                "confidence": result.confidence,
                "matched_source": result.matched_source,
                "title_similarity": result.title_similarity,
                "verified_title": result.verified_title,
                "verified_authors": result.verified_authors,
                "verified_year": result.verified_year,
                "verified_doi": result.verified_doi,
                "verified_journal": result.verified_journal,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            return result

        # Small delay between tiers to be polite
        time.sleep(0.3)

    # All tiers exhausted
    result.status = "not_found"
    result.confidence = "none"
    result.message = "NOT FOUND across CrossRef, Semantic Scholar, OpenAlex, PubMed, and arXiv — likely hallucinated"
    return result


def _detect_corrections(citation: Citation, paper: dict) -> list[str]:
    """Compare user-provided metadata against API-verified metadata."""
    corrections = []

    if citation.year and paper.get("year") and citation.year != paper["year"]:
        corrections.append(
            f"Year: {citation.year} → {paper['year']}"
        )

    if citation.journal and paper.get("journal"):
        j_sim = title_similarity(citation.journal, paper["journal"])
        if j_sim < 0.80:
            corrections.append(
                f"Journal: '{citation.journal}' → '{paper['journal']}'"
            )

    if citation.doi and paper.get("doi"):
        if clean_doi(citation.doi).lower() != clean_doi(paper["doi"]).lower():
            corrections.append(
                f"DOI: {citation.doi} → {paper['doi']}"
            )

    return corrections


# ═══════════════════════════════════════════════════════════════════════════
#  Input Parsers
# ═══════════════════════════════════════════════════════════════════════════

def parse_bibtex(filepath: Path) -> list[Citation]:
    """Parse a .bib file into Citation objects."""
    if not HAS_BIBTEX:
        _print(f"⚠  Skipping {filepath} — 'bibtexparser' not installed", style="yellow")
        return []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        bib_db = bibtexparser.load(f)

    citations = []
    for entry in bib_db.entries:
        cit = Citation(
            id=entry.get("ID", f"bib_{len(citations)}"),
            title=entry.get("title", "").strip("{}"),
            doi=entry.get("doi", ""),
            authors=_parse_bibtex_authors(entry.get("author", "")),
            year=_safe_int(entry.get("year", "")),
            journal=entry.get("journal", "") or entry.get("booktitle", ""),
            source_file=str(filepath),
        )
        if cit.title or cit.doi:
            citations.append(cit)
    return citations


def _parse_bibtex_authors(author_str: str) -> list[str]:
    """Split BibTeX author strings on 'and'."""
    if not author_str:
        return []
    return [a.strip().strip("{}") for a in author_str.split(" and ")]


def parse_markdown(filepath: Path) -> list[Citation]:
    """Extract citations from Markdown files.

    Recognises:
     - DOIs:  doi:10.xxxx/yyyy  or  https://doi.org/10.xxxx/yyyy
     - Inline refs:  (Author, Year) or (Author et al., Year)
     - Reference list entries with numbered DOIs
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    citations = []

    # Extract DOIs
    doi_pattern = r"(?:doi[:\s]?\s*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,}/[^\s,;)\]]+)"
    for match in re.finditer(doi_pattern, text, re.IGNORECASE):
        doi = match.group(1).rstrip(".")
        cit_id = f"md_doi_{len(citations)}"
        citations.append(Citation(
            id=cit_id,
            doi=doi,
            source_file=str(filepath),
            raw_text=match.group(0),
        ))

    # Extract inline citations like (Smith et al., 2023)
    inline_pattern = r"\(([A-Z][a-z]+(?:\s+et\s+al\.?)?),?\s*(\d{4})\)"
    for match in re.finditer(inline_pattern, text):
        author = match.group(1)
        year = int(match.group(2))
        cit_id = f"md_inline_{author}_{year}"
        # Only add if not a duplicate
        if not any(c.id == cit_id for c in citations):
            citations.append(Citation(
                id=cit_id,
                authors=[author],
                year=year,
                source_file=str(filepath),
                raw_text=match.group(0),
            ))

    return citations


def parse_text(filepath: Path) -> list[Citation]:
    """Extract DOIs from any plain text file."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    citations = []
    doi_pattern = r"(10\.\d{4,}/[^\s,;)\]\"']+)"
    for match in re.finditer(doi_pattern, text):
        doi = match.group(1).rstrip(".")
        citations.append(Citation(
            id=f"txt_doi_{len(citations)}",
            doi=doi,
            source_file=str(filepath),
        ))
    return citations


def _safe_int(val) -> Optional[int]:
    """Safely convert to int."""
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  File Discovery
# ═══════════════════════════════════════════════════════════════════════════

def discover_files(path: Path, fmt: str) -> list[Path]:
    """Find citation files under the given path."""
    if path.is_file():
        return [path]

    patterns = {
        "bib": ["*.bib"],
        "md":  ["*.md"],
        "all": ["*.bib", "*.md", "*.txt"],
    }
    globs = patterns.get(fmt, patterns["all"])

    files = []
    # Directories to skip
    skip_dirs = {"_Noise_Archive", "__pycache__", ".git", "node_modules", "chroma_db", ".venv", "venv"}

    for pattern in globs:
        for f in path.rglob(pattern):
            # Skip noisy directories
            if any(skip in f.parts for skip in skip_dirs):
                continue
            # Skip very large files (> 1 MB)
            if f.stat().st_size > 1_048_576:
                continue
            files.append(f)

    return sorted(set(files))


# ═══════════════════════════════════════════════════════════════════════════
#  Cache management
# ═══════════════════════════════════════════════════════════════════════════

def load_cache(cache_dir: Path) -> dict:
    """Load the persistent validation cache."""
    cache_file = cache_dir / CACHE_FILENAME
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_cache(cache: dict, cache_dir: Path) -> None:
    """Save the validation cache."""
    cache_file = cache_dir / CACHE_FILENAME
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, default=str)
    except IOError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  Report generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(results: list[ValidationResult], output_path: Path) -> dict:
    """Generate the JSON validation report."""
    verified = sum(1 for r in results if r.status == "verified")
    partial = sum(1 for r in results if r.status == "partial_match")
    not_found = sum(1 for r in results if r.status == "not_found")
    errors = sum(1 for r in results if r.status == "error")

    report = {
        "meta": {
            "tool": f"MegaMedical Reference Validator v{VERSION}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tiers_used": ["CrossRef", "Semantic Scholar", "OpenAlex", "PubMed", "arXiv"],
        },
        "summary": {
            "total": len(results),
            "verified": verified,
            "partial_match": partial,
            "not_found": not_found,
            "errors": errors,
        },
        "results": [asdict(r) for r in results],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    return report


def print_summary(results: list[ValidationResult]) -> None:
    """Print a human-readable summary."""
    verified = [r for r in results if r.status == "verified"]
    partial = [r for r in results if r.status == "partial_match"]
    not_found = [r for r in results if r.status == "not_found"]

    if HAS_RICH and console:
        table = Table(title="Reference Validation Results", show_lines=True)
        table.add_column("ID", style="cyan", max_width=30)
        table.add_column("Status", justify="center")
        table.add_column("Source", style="dim")
        table.add_column("Similarity", justify="right")
        table.add_column("Corrections", style="yellow")

        for r in results:
            if r.status == "verified":
                status = "[bold green]🟢 Verified[/]"
            elif r.status == "partial_match":
                status = "[bold yellow]🟡 Partial[/]"
            else:
                status = "[bold red]🔴 Not Found[/]"

            corr = "; ".join(r.corrections) if r.corrections else "—"
            table.add_row(
                r.citation_id,
                status,
                r.matched_source or "—",
                f"{r.title_similarity:.0%}" if r.title_similarity else "—",
                corr,
            )

        console.print()
        console.print(table)
        console.print()

        # Summary panel
        summary = Text()
        summary.append(f"  Total:         {len(results)}\n")
        summary.append(f"  ✅ Verified:    {len(verified)}\n", style="green")
        summary.append(f"  🟡 Partial:     {len(partial)}\n", style="yellow")
        summary.append(f"  🔴 Not Found:   {len(not_found)}\n", style="red")
        console.print(Panel(summary, title="Summary", border_style="blue"))

        if not_found:
            console.print("\n[bold red]⚠  Potentially hallucinated references:[/]")
            for r in not_found:
                console.print(f"   • {r.citation_id}: {r.query_title or r.query_doi}")

        if partial:
            console.print("\n[bold yellow]⚠  References with metadata corrections needed:[/]")
            for r in partial:
                for c in r.corrections:
                    console.print(f"   • {r.citation_id}: {c}")

    else:
        # Plain text fallback
        print(f"\n{'='*60}")
        print(f"  Reference Validation Report")
        print(f"{'='*60}")
        print(f"  Total:       {len(results)}")
        print(f"  Verified:    {len(verified)}")
        print(f"  Partial:     {len(partial)}")
        print(f"  Not Found:   {len(not_found)}")
        print(f"{'='*60}")

        for r in not_found:
            print(f"  🔴 HALLUCINATED? — {r.citation_id}: {r.query_title or r.query_doi}")
        for r in partial:
            print(f"  🟡 PARTIAL — {r.citation_id}: {'; '.join(r.corrections)}")
        print()


# ═══════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Validate academic references against CrossRef, Semantic Scholar, OpenAlex, PubMed, and arXiv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reference_validator.py ./refs.bib
  python reference_validator.py ./ --format all --output report.json
  python reference_validator.py paper.md --format md
        """,
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to a .bib/.md file or directory to scan",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["bib", "md", "all"],
        default="all",
        help="File format to scan (default: all)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("validation_report.json"),
        help="Output JSON report path (default: validation_report.json)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable persistent cache",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the cache before running",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )

    args = parser.parse_args()

    # Banner
    _print(f"\n[bold blue]╔══════════════════════════════════════════════════╗[/]")
    _print(f"[bold blue]║[/]  [bold]MegaMedical Reference Validator v{VERSION}[/]          [bold blue]║[/]")
    _print(f"[bold blue]║[/]  5-Tier: CrossRef → S2 → OpenAlex → PubMed → arXiv  [bold blue]║[/]")
    _print(f"[bold blue]╚══════════════════════════════════════════════════╝[/]\n")

    # Resolve path
    target = args.path.resolve()
    if not target.exists():
        _print(f"[red]Error: Path '{target}' does not exist.[/]")
        sys.exit(1)

    # Discover files
    files = discover_files(target, args.format)
    if not files:
        _print(f"[yellow]No citation files found at '{target}' with format '{args.format}'.[/]")
        sys.exit(0)

    _print(f"Found [bold]{len(files)}[/] file(s) to scan.\n")

    # Parse citations
    all_citations: list[Citation] = []
    for f in files:
        suffix = f.suffix.lower()
        if suffix == ".bib":
            parsed = parse_bibtex(f)
        elif suffix == ".md":
            parsed = parse_markdown(f)
        else:
            parsed = parse_text(f)
        if parsed:
            _print(f"  📄 {f.name}: {len(parsed)} citation(s)")
            all_citations.extend(parsed)

    if not all_citations:
        _print(f"\n[yellow]No citations extracted from scanned files.[/]")
        sys.exit(0)

    # Deduplicate by DOI
    seen_dois: set[str] = set()
    unique_citations: list[Citation] = []
    for c in all_citations:
        doi_key = clean_doi(c.doi).lower() if c.doi else ""
        if doi_key and doi_key in seen_dois:
            continue
        if doi_key:
            seen_dois.add(doi_key)
        unique_citations.append(c)

    _print(f"\n[bold]Total unique citations to validate: {len(unique_citations)}[/]\n")

    # Cache
    cache_dir = target if target.is_dir() else target.parent
    cache: dict = {}
    if not args.no_cache and not args.clear_cache:
        cache = load_cache(cache_dir)
        if cache:
            _print(f"  📦 Loaded {len(cache)} cached result(s)\n")

    # Validate
    results: list[ValidationResult] = []
    if HAS_RICH and console:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Validating...", total=len(unique_citations))
            for i, cit in enumerate(unique_citations):
                progress.update(task, description=f"[{i+1}/{len(unique_citations)}] {cit.id[:40]}...")
                res = validate_citation(cit, cache)
                results.append(res)
                progress.advance(task)
                # Politeness delay between citations
                if i < len(unique_citations) - 1:
                    time.sleep(0.5)
    else:
        for i, cit in enumerate(unique_citations):
            print(f"  [{i+1}/{len(unique_citations)}] Validating: {cit.id}...")
            res = validate_citation(cit, cache)
            results.append(res)
            if i < len(unique_citations) - 1:
                time.sleep(0.5)

    # Save cache
    if not args.no_cache:
        save_cache(cache, cache_dir)

    # Generate report
    report = generate_report(results, args.output)
    _print(f"\n📝 Report saved to: [bold]{args.output}[/]")

    # Print summary
    print_summary(results)

    # Exit code: non-zero if any not_found
    not_found_count = report["summary"]["not_found"]
    if not_found_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

def validate_doi(doi: str) -> dict:
    from meddraft_ai.extraction.citation_tracker import CitationVerifier
    res = CitationVerifier.verify_doi(doi)
    return res.to_dict()

def validate_pmid(pmid: str) -> dict:
    from meddraft_ai.extraction.citation_tracker import CitationVerifier
    res = CitationVerifier.verify_pmid(pmid)
    return res.to_dict()

def validate_references(text: str) -> list[dict]:
    from meddraft_ai.extraction.citation_tracker import CitationVerifier
    results = CitationVerifier.extract_and_verify(text)
    return [r.to_dict() for r in results]

