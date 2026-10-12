"""Secondary / nested citation extractor (secondary-citation-extractor skill — code layer).

Implements the skill's 4-step workflow in executable form:

  Step 1 — Detect & distinguish the Container (PDF) author vs cited Root author.
  Step 2 — Trace an in-text key (``[28]``, ``(Miller, 2018)``) to the PDF bibliography.
  Step 3 — Verify / complete the Root metadata via Crossref → PubMed → Scholar guidance.
  Step 4 — Synthesize dual attribution (``as cited in`` + two bibliography records).

The module is intentionally dependency-light (stdlib + ``requests`` via the
existing verifier) so the pipeline, CLI, and tests can use it offline. Live
API calls are attempted best-effort and degrade to ``verified=False`` with an
explicit status flag instead of raising.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

logger = logging.getLogger(__name__)

SKILL_NAME = "secondary-citation-extractor"

# ---------------------------------------------------------------------------
# Auto-trigger signals — used by SkillRegistry.match_skill_for_task().
# ---------------------------------------------------------------------------

# Explicit narrative phrases that almost always mean a secondary citation task.
_NARRATIVE_PATTERNS = [
    r"\bas\s+cited\s+in\b",
    r"\bas\s+reported\s+by\b",
    r"\bas\s+described\s+by\b",
    r"\bas\s+reviewed\s+in\b",
    r"\bquoted\s+in\b",
    r"\bcited\s+by\b",
]

# Citation-marker shapes detected inside running prose.
_MARKER_PATTERNS = {
    # (Smith, 2020) / (Smith et al., 2020) / Smith (2020)
    "author-date": re.compile(
        r"\(?[A-Z][A-Za-z\-']+(?:\s+et\s+al\.?)?(?:\s*,\s*[A-Z][A-Za-z\-']+)*,?\s*\d{4}[a-z]?\)?"
    ),
    # [28] / [14-16]
    "bracket": re.compile(r"\[\d+(?:\s*[-,–]\s*\d+)*\]"),
    # Trailing superscript digits (conservative: digit run after a word char).
    "superscript": re.compile(r"(?<=[a-zA-Z.,;])\s*\^?\d{1,3}(?=[\s.,;])"),
}

# Keyword stems (lowercase) that raise the routing score.
_SECONDARY_KEYWORDS = [
    "secondary citation",
    "secondary source",
    "nested citation",
    "nested reference",
    "as cited in",
    "root author",
    "root study",
    "original author",
    "original study",
    "primary study",
    "container author",
    "container document",
    "container paper",
    "dual bibliography",
    "dual attribution",
    "trace citation",
    "trace the citation",
    "resolve reference",
    "resolve secondary",
    "truncated author",
    "et al",
    "unlisted in",
    "bibliography entry",
    "reference list",
]

# Reference-section heading detector.
_REFERENCES_HEADING = re.compile(
    r"^\s*(references|bibliography|literature\s+cited|works\s+cited)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Numbered bibliography entry: "28. Roden M, et al. ..." / "[28] Roden ..."
_ENTRY_START = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[\.\)])\s+(.*)$")

_DOI_RE = re.compile(r"10\.\d{4,}/[^\s,;\]\)\"']+")
_PMID_RE = re.compile(r"PMID[:\s]*(\d{7,8})", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ContainerSource:
    authors: list[str] = field(default_factory=list)
    title: str = ""
    venue: str = ""
    year: Optional[int] = None

    def label(self) -> str:
        if not self.authors:
            return f"Container ({self.year or 'n.d.'})"
        first = self.authors[0].split(",")[0].strip()
        suffix = " et al." if len(self.authors) > 1 else ""
        return f"{first}{suffix} ({self.year or 'n.d.'})" if self.year else f"{first}{suffix}"


@dataclass
class RootSource:
    authors: list[str] = field(default_factory=list)
    title: str = ""
    venue: str = ""
    year: Optional[int] = None
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    pmid: str = ""
    verified: bool = False
    verification_source: str = ""  # Crossref | PubMed | Google Scholar | unverified
    note: str = ""  # e.g. externally retrieved; unlisted in container bibliography

    def short_label(self) -> str:
        if not self.authors:
            return f"Unknown ({self.year or 'n.d.'})"
        first = self.authors[0].split(",")[0].strip()
        suffix = " et al." if len(self.authors) > 1 else ""
        return f"{first}{suffix} ({self.year or 'n.d.'})" if self.year else f"{first}{suffix}"


@dataclass
class SecondaryCitation:
    claim: str = ""
    in_text_key: str = ""
    key_kind: str = ""  # author-date | bracket | superscript | narrative
    page: Optional[int] = None
    paragraph: Optional[int] = None
    reference_index: str = ""
    root: RootSource = field(default_factory=RootSource)
    container: ContainerSource = field(default_factory=ContainerSource)
    citation_style: str = "Harvard"  # Harvard | Vancouver

    def in_text_attribution(self) -> str:
        root_label = self.root.short_label()
        container_label = self.container.label()
        if self.citation_style.lower().startswith("vanc"):
            ref = self.reference_index or self.in_text_key or "?"
            return f"{self.root.short_label()} [{ref}], as cited by {container_label}"
        return f"({root_label}, as cited in {container_label})"

    def to_markdown(self) -> str:
        lines = [
            "### Extracted Claim / Finding",
            f'> "{self.claim}"' if self.claim else "> [no claim text captured]",
            "",
            "### In-Text Attribution",
            self.in_text_attribution(),
            "",
            "### Full Bibliographic Entries",
            "",
            "1. **Original Source (Root Work):**",
            f"   - **Authors:** {', '.join(self.root.authors) or '[unresolved]'}",
            f"   - **Title:** {self.root.title or '[unresolved]'}",
            f"   - **Source:** {self.root.venue or '[unknown venue]'}, "
            f"{self.root.year or 'n.d.'}"
            + (f", {self.root.volume}({self.root.issue}):{self.root.pages}" if self.root.volume else ""),
            f"   - **Identifier:** "
            + (f"DOI {self.root.doi}" if self.root.doi else "")
            + (f" | PMID {self.root.pmid}" if self.root.pmid else "")
            + ("" if (self.root.doi or self.root.pmid) else "[none found]"),
            f"   - **Status:** {'Verified via ' + self.root.verification_source if self.root.verified else 'Unverified' + (f' — {self.root.note}' if self.root.note else '')}",
            "",
            "2. **Container Source (PDF Analyzed):**",
            f"   - **Authors:** {', '.join(self.container.authors) or '[unknown]'}",
            f"   - **Title:** {self.container.title or '[unknown]'}",
            f"   - **Source:** {self.container.venue or '[unknown venue]'}, {self.container.year or 'n.d.'}",
            f"   - **Location in PDF:** Page {self.page or '?'}"
            + (f", Paragraph {self.paragraph}" if self.paragraph else "")
            + (f", Reference #{self.reference_index}" if self.reference_index else ""),
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["in_text_attribution"] = self.in_text_attribution()
        return data


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class SecondaryCitationExtractor:
    """Stateless 4-step secondary-citation pipeline."""

    skill_name = SKILL_NAME

    # -- routing --------------------------------------------------------
    @classmethod
    def should_trigger(cls, task_text: str) -> bool:
        """Return True when *task_text* looks like a secondary-citation task."""
        if not task_text:
            return False
        lowered = task_text.lower()
        if SKILL_NAME in lowered or "secondary-citation" in lowered:
            return True
        for pat in _NARRATIVE_PATTERNS:
            if re.search(pat, task_text, re.IGNORECASE):
                return True
        hits = sum(1 for kw in _SECONDARY_KEYWORDS if kw in lowered)
        return hits >= 2

    @classmethod
    def match_score(cls, task_text: str) -> int:
        """Integer routing score — higher means stronger skill relevance."""
        if not task_text:
            return 0
        lowered = task_text.lower()
        score = 0
        if SKILL_NAME in lowered:
            score += 10
        for pat in _NARRATIVE_PATTERNS:
            if re.search(pat, task_text, re.IGNORECASE):
                score += 5
        for kw in _SECONDARY_KEYWORDS:
            if kw in lowered:
                score += 2 if len(kw.split()) > 1 else 1
        # A raw citation marker alone is weak evidence (+1 max).
        if score == 0:
            for kind, rx in _MARKER_PATTERNS.items():
                if rx.search(task_text):
                    score += 1
                    break
        return score

    # -- Step 1: container ----------------------------------------------
    @staticmethod
    def detect_container(pdf_text: str, metadata: Optional[dict] = None) -> ContainerSource:
        metadata = metadata or {}
        container = ContainerSource()
        if metadata.get("author"):
            raw = str(metadata["author"])
            container.authors = [a.strip() for a in re.split(r"[;]| and |,", raw) if a.strip()][:6]
        if metadata.get("title"):
            container.title = str(metadata["title"]).strip()
        head = pdf_text[:2500] if pdf_text else ""
        if not container.title and head:
            for line in head.splitlines()[:8]:
                line = line.strip()
                if len(line) > 25 and not line.lower().startswith(("page", "---")):
                    container.title = line[:250]
                    break
        years = _YEAR_RE.findall(head)
        if years and not container.year:
            try:
                container.year = int(years[-1] if isinstance(years[-1], str) else "".join(years[-1]))
            except (ValueError, TypeError):
                pass
        if isinstance(metadata.get("year"), int):
            container.year = metadata["year"]
        return container

    # -- Step 2: markers + bibliography ---------------------------------
    @classmethod
    def detect_in_text_keys(cls, text: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        # Narrative secondary phrases first (strongest signal).
        for pat in _NARRATIVE_PATTERNS:
            for m in re.finditer(pat, text, re.IGNORECASE):
                key = m.group(0)
                if key.lower() not in seen:
                    seen.add(key.lower())
                    found.append({"key": key, "kind": "narrative", "span": m.span()})
        for kind, rx in _MARKER_PATTERNS.items():
            if kind == "superscript":
                continue  # too noisy for auto-routing; still parsed per-sentence below
            for m in rx.finditer(text):
                key = m.group(0).strip()
                if key.lower() not in seen:
                    seen.add(key.lower())
                    found.append({"key": key, "kind": kind, "span": m.span()})
        return found

    @staticmethod
    def split_reference_section(pdf_text: str) -> str:
        match = _REFERENCES_HEADING.search(pdf_text or "")
        if not match:
            return ""
        return pdf_text[match.end():]

    @classmethod
    def parse_reference_list(cls, pdf_text: str) -> list[dict[str, Any]]:
        ref_text = cls.split_reference_section(pdf_text)
        if not ref_text:
            return []
        entries: list[dict[str, Any]] = []
        current: Optional[dict[str, Any]] = None
        for raw_line in ref_text.splitlines():
            m = _ENTRY_START.match(raw_line)
            if m:
                if current:
                    entries.append(current)
                idx = m.group(1) or m.group(2)
                body = (m.group(3) or "").strip()
                current = {"index": idx, "raw": body}
            elif current and raw_line.strip():
                current["raw"] += " " + raw_line.strip()
            # Stop at appendices/figures that sometimes follow references.
            if re.match(r"^\s*(appendix|supplementary|figure\s+\d+)\b", raw_line, re.IGNORECASE) and len(entries) > 3:
                break
        if current:
            entries.append(current)
        for entry in entries:
            entry.update(cls.parse_reference_entry(entry["raw"]))
        return entries

    @staticmethod
    def parse_reference_entry(raw: str) -> dict[str, Any]:
        doi_m = _DOI_RE.search(raw or "")
        pmid_m = _PMID_RE.search(raw or "")
        year_m = re.search(r"\b((?:19|20)\d{2})\b", raw or "")
        return {
            "doi": doi_m.group(0).rstrip(".,;)") if doi_m else "",
            "pmid": pmid_m.group(1) if pmid_m else "",
            "year": int(year_m.group(1)) if year_m else None,
            "authors": SecondaryCitationExtractor.guess_authors(raw or ""),
        }

    @staticmethod
    def guess_authors(raw: str) -> list[str]:
        """Best-effort author guess from an abbreviated bibliography line."""
        head = raw.split(".")[0].split(";")[0][:200]
        # "Roden M, Price TB, Perseghin G" style
        candidates = [c.strip() for c in re.split(r",\s*(?=[A-Z])", head) if c.strip()]
        if 1 < len(candidates) <= 8 and all(len(c) < 30 for c in candidates):
            return candidates
        # "Alvarez et al." style
        m = re.match(r"^([A-Z][A-Za-z\-']+(?:\s+et\s+al\.?)?)", raw.strip())
        return [m.group(1)] if m else []

    @classmethod
    def trace_to_reference(
        cls, key: str, ref_entries: list[dict[str, Any]], pdf_text: str = ""
    ) -> dict[str, Any]:
        # Bracketed numeric key → direct index lookup.
        num = re.search(r"\[(\d+)\]", key or "")
        if num:
            for entry in ref_entries:
                if entry.get("index") == num.group(1):
                    return entry
            return {"index": num.group(1), "raw": "", "doi": "", "pmid": "",
                    "year": None, "authors": [], "missing": True}
        # Author-date key → match surname (+year when available).
        surname = re.match(r"\(?([A-Z][A-Za-z\-']+)", (key or "").strip())
        year_m = re.search(r"((?:19|20)\d{2})", key or "")
        if surname:
            name = surname.group(1).lower()
            for entry in ref_entries:
                if name in (entry.get("raw") or "").lower():
                    if year_m and entry.get("year") and str(entry["year"]) != year_m.group(1):
                        continue
                    return entry
        return {"index": "", "raw": key, "doi": "", "pmid": "",
                "year": int(year_m.group(1)) if year_m else None,
                "authors": [surname.group(1)] if surname else [],
                "missing": True}

    # -- Step 3: verification queries ------------------------------------
    @staticmethod
    def build_crossref_query(entry: dict[str, Any]) -> str:
        if entry.get("doi"):
            return f"https://api.crossref.org/works/{entry['doi']}"
        title = entry.get("raw", "")[:200]
        return f"https://api.crossref.org/works?query.bibliographic={title}"

    @staticmethod
    def build_pubmed_query(entry: dict[str, Any]) -> str:
        parts = []
        authors = entry.get("authors") or []
        if authors:
            parts.append(authors[0])
        if entry.get("year"):
            parts.append(str(entry["year"]))
        raw = (entry.get("raw") or "").split(".")[1:2]
        if raw:
            parts.append(raw[0].strip()[:80])
        return " ".join(p for p in parts if p)

    @staticmethod
    def build_scholar_query(entry: dict[str, Any]) -> str:
        raw = (entry.get("raw") or "").strip()
        author = (entry.get("authors") or [""])[0]
        return f'"{raw[:120]}" {author}'.strip()

    @classmethod
    def resolve_root(cls, entry: dict[str, Any]) -> RootSource:
        root = RootSource(
            authors=list(entry.get("authors") or []),
            year=entry.get("year"),
            doi=entry.get("doi") or "",
            pmid=entry.get("pmid") or "",
        )
        raw = entry.get("raw") or ""
        if raw:
            # Naive title guess: second sentence-ish segment of the entry.
            segments = [s.strip() for s in raw.split(". ") if s.strip()]
            if len(segments) >= 2:
                root.title = segments[1][:300]
            root.venue = segments[2][:150] if len(segments) >= 3 else ""
        # Live verification — best effort, never raises.
        try:
            if root.doi:
                from meddraft_ai.extraction.citation_tracker import CitationVerifier
                verified = CitationVerifier.verify_doi(root.doi)
                if verified and verified.verified:
                    root.authors = verified.authors or root.authors
                    root.title = verified.title or root.title
                    root.venue = verified.journal or root.venue
                    root.year = verified.year or root.year
                    root.verified = True
                    root.verification_source = verified.source or "Crossref"
                    return root
            if root.title or root.doi:
                from meddraft_ai.validation.reference_validator import (
                    Citation, validate_citation, load_cache,
                )
                from pathlib import Path
                cit = Citation(
                    id="secondary_root",
                    title=root.title,
                    doi=root.doi,
                    authors=root.authors,
                    year=root.year,
                )
                result = validate_citation(cit, {})
                if result.status in ("verified", "partial_match"):
                    root.authors = result.verified_authors or root.authors
                    root.title = result.verified_title or root.title
                    root.venue = result.verified_journal or root.venue
                    root.year = result.verified_year or root.year
                    root.doi = result.verified_doi or root.doi
                    root.verified = result.status == "verified"
                    root.verification_source = result.matched_source or "CrossRef"
                    return root
        except Exception as exc:  # offline / API failure → explicit unverified
            logger.debug("Secondary root verification failed: %s", exc)
        if entry.get("missing"):
            root.note = "(Full details retrieved externally; unlisted in container bibliography)"
        elif not root.verified:
            root.note = "Unverified — bibliography entry abbreviated; run Crossref/PubMed/Scholar query"
        return root

    # -- Step 4: full pipeline -------------------------------------------
    @classmethod
    def extract(
        cls,
        pdf_text: str,
        container_meta: Optional[dict] = None,
        citation_style: str = "Harvard",
        max_claims: int = 20,
    ) -> list[SecondaryCitation]:
        container = cls.detect_container(pdf_text or "", container_meta)
        ref_entries = cls.parse_reference_list(pdf_text or "")
        sentences = re.split(r"(?<=[.!?])\s+", pdf_text or "")
        results: list[SecondaryCitation] = []
        page = 1
        for para_no, sent in enumerate(sentences, start=1):
            if len(results) >= max_claims:
                break
            keys = cls.detect_in_text_keys(sent)
            if not keys:
                continue
            # Skip sentences inside the bibliography itself.
            if _REFERENCES_HEADING.search(sent):
                break
            for item in keys[:2]:
                entry = cls.trace_to_reference(item["key"], ref_entries, pdf_text or "")
                root = cls.resolve_root(entry)
                ref_idx = entry.get("index") or re.sub(r"[^\d]", "", item["key"])[:6]
                results.append(SecondaryCitation(
                    claim=sent.strip()[:600],
                    in_text_key=item["key"],
                    key_kind=item["kind"],
                    page=page,
                    paragraph=para_no,
                    reference_index=ref_idx,
                    root=root,
                    container=container,
                    citation_style=citation_style,
                ))
            page_increment = sent.count("--- Page ")
            if page_increment:
                page += page_increment
        return results

    @classmethod
    def extract_to_markdown(
        cls,
        pdf_text: str,
        container_meta: Optional[dict] = None,
        citation_style: str = "Harvard",
        max_claims: int = 20,
    ) -> str:
        results = cls.extract(pdf_text, container_meta, citation_style, max_claims)
        if not results:
            return (
                "No secondary/nested citations detected. "
                "If the excerpt contains a claim with a reference marker "
                "([23], (Author, Year)), re-run with that sentence included."
            )
        return "\n\n---\n\n".join(r.to_markdown() for r in results)
