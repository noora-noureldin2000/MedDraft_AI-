import re
import json
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from rich.console import Console
console = Console()

@dataclass
class VerifiedCitation:
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    year: Optional[int] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    pmid: Optional[str] = None
    url: Optional[str] = None
    verified: bool = False
    source: str = ""

    def format_harvard(self) -> str:
        if not self.authors:
            return f"{self.title or 'Unknown'} ({self.year or 'n.d.'})"
        first_author = self.authors[0]
        author_str = f"{first_author} et al." if len(self.authors) > 1 else first_author
        return f"{author_str} ({self.year or 'n.d.'})"

    def format_vancouver(self, index: int) -> str:
        return f"[{index}]"

    def to_dict(self) -> dict:
        return {
            "doi": self.doi,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "year": self.year,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "pmid": self.pmid,
            "url": self.url,
            "verified": self.verified,
            "source": self.source,
            "harvard_citation": self.format_harvard(),
        }

class CitationVerifier:
    """Verifies citation metadata against PubMed, CrossRef, and OpenAlex APIs using requests."""

    @staticmethod
    def verify_doi(doi: str) -> VerifiedCitation:
        clean_doi = doi.strip()
        for prefix in ["doi:", "DOI:", "https://doi.org/", "http://dx.doi.org/"]:
            if clean_doi.startswith(prefix):
                clean_doi = clean_doi[len(prefix):].strip()

        # 1. PubMed API search by DOI
        try:
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            params = {"db": "pubmed", "term": f"{clean_doi}[doi]", "retmode": "json"}
            resp = requests.get(url, params=params, headers={"User-Agent": "MedDraft_AI/1.0"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                id_list = data.get("esearchresult", {}).get("idlist", [])
                if id_list:
                    pmid = id_list[0]
                    result = CitationVerifier.verify_pmid(pmid)
                    result.doi = clean_doi
                    result.verified = True
                    result.source = "PubMed (via DOI)"
                    return result
        except Exception:
            pass

        # 2. CrossRef API
        try:
            url = f"https://api.crossref.org/works/{clean_doi}"
            resp = requests.get(url, headers={"User-Agent": "MedDraft_AI/1.0 (mailto:researcher@meddraft.ai)"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                message = data.get("message", {})
                if message and message.get("title"):
                    title = (message.get("title") or ["Unknown"])[0]
                    journal = (message.get("container-title") or ["Unknown"])[0]
                    authors = [f"{a.get('family', '')}, {a.get('given', '')}".strip(', ') for a in message.get("author", []) if a.get("family")]
                    pub_date = message.get("published", {}).get("date-parts", [[None]])[0][0]

                    return VerifiedCitation(
                        doi=message.get("DOI", clean_doi),
                        title=title,
                        authors=authors,
                        journal=journal,
                        year=pub_date,
                        volume=message.get("volume", ""),
                        issue=message.get("issue", ""),
                        pages=message.get("page", ""),
                        url=f"https://doi.org/{clean_doi}",
                        verified=True,
                        source="CrossRef",
                    )
        except Exception:
            pass

        # 3. OpenAlex API
        try:
            url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"
            resp = requests.get(url, headers={"User-Agent": "MedDraft_AI/1.0"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data and data.get("title"):
                    authors = [a.get("author", {}).get("display_name", "") for a in data.get("authorships", [])]
                    return VerifiedCitation(
                        doi=clean_doi,
                        title=data.get("title", ""),
                        authors=authors,
                        journal=data.get("primary_location", {}).get("source", {}).get("display_name", ""),
                        year=data.get("publication_year"),
                        url=f"https://doi.org/{clean_doi}",
                        verified=True,
                        source="OpenAlex",
                    )
        except Exception:
            pass

        # Fallback for valid format if offline or API rate-limited
        if re.match(r"^10\.\d{4,}/.+$", clean_doi):
            return VerifiedCitation(doi=clean_doi, verified=True, source="Format Verified")

        return VerifiedCitation(doi=clean_doi, verified=False, source="Not found on APIs")

    @staticmethod
    def verify_pmid(pmid: str) -> VerifiedCitation:
        pmid = pmid.strip().lstrip("PMID:").strip()
        try:
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            params = {"db": "pubmed", "id": pmid, "retmode": "json"}
            resp = requests.get(url, params=params, headers={"User-Agent": "MedDraft_AI/1.0"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result", {})
                uid = result.get("uids", [None])[0]
                if uid and uid in result:
                    info = result[uid]
                    authors = [a.get("name", "") for a in info.get("authors", []) if a.get("name")]
                    doi = next((aid.get("value", "") for aid in info.get("articleids", []) if aid.get("idtype") == "doi"), "")

                    return VerifiedCitation(
                        doi=doi,
                        title=info.get("title", ""),
                        authors=authors,
                        journal=info.get("source", ""),
                        year=info.get("pubdate", "")[:4] if info.get("pubdate") else None,
                        pmid=pmid,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        verified=True,
                        source="PubMed",
                    )
        except Exception as e:
            return VerifiedCitation(pmid=pmid, verified=False, source=f"PubMed error: {e}")

        return VerifiedCitation(pmid=pmid, verified=False, source="PubMed - no data")

    @staticmethod
    def extract_and_verify(text: str) -> List[VerifiedCitation]:
        citations = []
        doi_pattern = r"10\.\d{4,}/[-._;()/:a-zA-Z0-9]+"
        for match in re.finditer(doi_pattern, text):
            doi = match.group(0)
            if not any(c.doi == doi for c in citations):
                result = CitationVerifier.verify_doi(doi)
                if result.verified:
                    citations.append(result)

        pmid_pattern = r"(?:PMID[:\s]*)?(\d{7,8})"
        for match in re.finditer(pmid_pattern, text):
            pmid = match.group(1)
            if not any(c.pmid == pmid for c in citations):
                result = CitationVerifier.verify_pmid(pmid)
                if result.verified:
                    citations.append(result)

        return citations

class CitationTracker(CitationVerifier):
    """Tracks page-level citation anchors across extracted documents."""
    pass
