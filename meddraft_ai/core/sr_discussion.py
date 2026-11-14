"""Machine-enforceable layer for the ``systematic-review-discussion`` skill.

The prompt packs describe *how* to write a publication-grade systematic review
Discussion. This module supplies the parts an LLM cannot be trusted to police
by itself:

* task routing (``should_trigger``) so ``SkillRegistry`` loads the pack for
  systematic-review / meta-analysis Discussion requests;
* a read-only workspace inventory (``inventory_project``) so an agent can list
  protocol, included-RCT, meta-analysis, and prior-review files before writing;
* a draft auditor (``audit_discussion``) that enforces the guide's hard gates
  (zero em-dashes, banned AI vocabulary, no background-platitude opening,
  outcome coverage, GRADE calibration, two-tier limitations, specific future
  research) without touching or rewriting prose;
* a numeric-fidelity check (``check_numeric_fidelity``) that flags pooled
  effect sizes in the draft which do not appear in the supplied evidence files;
* a plug-and-play system-command builder (``build_system_command``) for a new
  study spec.

All checks are deterministic, offline, and side-effect free. Nothing here
writes a manuscript or alters a number; findings are advisory until a human
(or the drafting agent) resolves them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SKILL_NAME = "systematic-review-discussion"

# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

_SR_SIGNAL = re.compile(
    r"systematic\s+review|meta[-\s]?analys|evidence\s+synthesis|pooled\s+effect",
    re.IGNORECASE,
)
_DISCUSSION_SIGNAL = re.compile(
    r"discussion|interpret|contextuali[sz]|principal\s+findings|"
    r"clinical\s+implications|strengths?\s+and\s+limitations",
    re.IGNORECASE,
)
_METHODS_ONLY = re.compile(
    r"search\s+strategy|screening\s+process|data\s+extraction\s+form|"
    r"prisma\s+flow|risk[-\s]of[-\s]bias\s+assessment",
    re.IGNORECASE,
)


def should_trigger(task_text: str) -> bool:
    """True when the task is a systematic-review / meta-analysis Discussion.

    Requires both an evidence-synthesis signal and a discussion-writing signal,
    so protocol, screening, and extraction requests keep their existing routes.
    """
    if not task_text:
        return False
    if not (_SR_SIGNAL.search(task_text) and _DISCUSSION_SIGNAL.search(task_text)):
        return False
    # A protocol or methods task is not a Discussion task, even if it mentions
    # the review type. Only keep it when the Discussion itself is named.
    if re.search(r"\bprotocol\b|\bprospero\b", task_text, re.IGNORECASE) and not re.search(
        r"discussion", task_text, re.IGNORECASE
    ):
        return False
    # A methods-only request that happens to mention "discussion" as a section
    # of the protocol is not a Discussion-writing task.
    if _METHODS_ONLY.search(task_text) and not re.search(
        r"discussion", task_text, re.IGNORECASE
    ):
        return False
    return True


def match_score(task_text: str) -> int:
    """Confidence score used by tests/tooling (0 when no trigger)."""
    if not should_trigger(task_text or ""):
        return 0
    lowered = task_text.lower()
    score = 2
    score += 1 if "meta-analys" in lowered or "meta analys" in lowered else 0
    score += 1 if "discussion" in lowered else 0
    score += 1 if "draft" in lowered or "write" in lowered else 0
    return score


# ---------------------------------------------------------------------------
# Workspace inventory
# ---------------------------------------------------------------------------

_DOC_EXTENSIONS = {".md", ".txt", ".docx", ".pdf", ".html", ".htm", ".rtf"}
_DATA_EXTENSIONS = {".csv", ".tsv", ".json", ".xlsx", ".xls"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".tif", ".tiff"}

_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prior_reviews", ("old meta", "old_meta", "prior review", "previous review", "old systematic", "old review")),
    ("included_studies", ("included", "rct", "trial", "study")),
    ("meta_analysis", ("meta", "forest", "pooled", "revman")),
    ("protocol", ("protocol", "eligibility", "pico")),
)


def _categorize(path: Path) -> str:
    haystack = str(path).lower().replace("\\", "/")
    for category, needles in _CATEGORY_RULES:
        if any(needle in haystack for needle in needles):
            return category
    suffix = path.suffix.lower()
    if suffix in _DATA_EXTENSIONS:
        return "data"
    if suffix in _IMAGE_EXTENSIONS:
        return "figure"
    if suffix in _DOC_EXTENSIONS:
        return "document"
    return "other"


@dataclass
class EvidenceInventory:
    """Read-only manifest of a study workspace.

    ``files`` holds one dict per file: ``path``, ``name``, ``category``,
    ``size_bytes``. The manifest exists so the agent can prove it looked at the
    whole workspace before writing (the guide's Step 0 mandate).
    """

    roots: list[str]
    files: list[dict[str, Any]] = field(default_factory=list)

    @property
    def categories(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for entry in self.files:
            grouped.setdefault(entry["category"], []).append(entry["path"])
        return grouped

    def to_markdown(self) -> str:
        lines = ["# Evidence workspace inventory", ""]
        for root in self.roots:
            lines.append(f"- Root: `{root}`")
        lines.append("")
        for category in sorted(self.categories):
            lines.append(f"## {category} ({len(self.categories[category])})")
            for path in self.categories[category]:
                lines.append(f"- `{path}`")
            lines.append("")
        if not self.files:
            lines.append("_No readable files found._")
        return "\n".join(lines).strip() + "\n"

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": SKILL_NAME,
            "roots": list(self.roots),
            "count": len(self.files),
            "categories": self.categories,
            "files": list(self.files),
        }


def inventory_project(paths: Iterable[str | Path]) -> EvidenceInventory:
    """Walk each path (file or directory) and classify every readable file.

    Directory recursion is deliberate: the guide's Step 0 requires the complete
    workspace listing before the first sentence is written. Classification uses
    the path relative to each supplied root, so a root folder named "study" or
    "meta" does not contaminate the category of every file beneath it.
    """
    roots: list[str] = []
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in paths:
        path = Path(raw)
        roots.append(str(path))
        if not path.exists():
            continue
        if path.is_file():
            candidates = [(path, Path(path.name))]
        else:
            candidates = [
                (candidate, candidate.relative_to(path))
                for candidate in sorted(path.rglob("*"))
                if candidate.is_file()
            ]
        for candidate, relative in candidates:
            resolved = str(candidate.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                size = candidate.stat().st_size
            except OSError:
                size = 0
            entries.append(
                {
                    "path": str(candidate),
                    "name": candidate.name,
                    "category": _categorize(relative),
                    "size_bytes": size,
                }
            )
    return EvidenceInventory(roots=roots, files=entries)


# ---------------------------------------------------------------------------
# Draft audit
# ---------------------------------------------------------------------------

EM_DASH = "\u2014"

# Explicitly banned by the skill's prose guardrails. Matched on word
# boundaries, case-insensitively; inflections are listed where they occur.
BANNED_AI_VOCABULARY: tuple[str, ...] = (
    "delve",
    "delves",
    "delving",
    "underscore",
    "underscores",
    "underscoring",
    "testament",
    "tapestry",
    "beacon",
    "pivotal",
    "paramount",
    "multifaceted",
    "realm",
    "intricate",
    "notably",
    "importantly",
    "it is worth noting that",
    "in summary",
)

# Softer house-style tells: reported as warnings, not hard failures.
STYLE_WARNINGS: tuple[str, ...] = (
    "crucial",
    "nuanced",
    "groundbreaking",
    "a myriad of",
    "leverage",
    "foster",
    "harness",
    "commendable",
)

_BACKGROUND_OPENERS = re.compile(
    r"affects?\s+millions|million\s+(people|patients|adults)|"
    r"leading\s+cause\s+of|global\s+burden|public\s+health\s+(problem|burden|priority)|"
    r"worldwide|has\s+become\s+a\s+major|is\s+a\s+common",
    re.IGNORECASE,
)
_ANSWER_OPENER = re.compile(
    r"this\s+systematic\s+review|this\s+meta[-\s]?analysis|we\s+(found|show|demonstrate)|"
    r"our\s+(review|analysis|pooled)|pooled\s+(estimate|analysis)|"
    r"the\s+synthesi[sz]ed\s+evidence",
    re.IGNORECASE,
)
_OVERCLAIM = re.compile(
    r"\b(definitively|undeniably|unquestionably)\b", re.IGNORECASE
)
_PROVE = re.compile(r"\b(proves?|proven)\b", re.IGNORECASE)
_HIGH_CERTAINTY = re.compile(
    r"high[\s-]certainty|high\s+certainty\s+of\s+evidence", re.IGNORECASE
)
_GENERIC_RESEARCH_CALL = re.compile(
    r"\b(more|further|additional)\s+research\s+is\s+(needed|required|warranted)\b",
    re.IGNORECASE,
)
_APOLOGETIC = re.compile(
    r"\bunfortunately\b|\bsuffered\s+from\b|\bwe\s+regret\b|\bregrettably\b",
    re.IGNORECASE,
)
_GRADE_LANGUAGE = re.compile(
    r"\bGRADE\b|certainty\s+of\s+evidence|quality\s+of\s+evidence|"
    r"very\s+low\s+certainty|low\s+certainty|moderate\s+certainty|high\s+certainty",
    re.IGNORECASE,
)
_HETEROGENEITY = re.compile(r"\bI\s*[²2]\b|heterogeneity|tau\s*[²2]|Cochran", re.IGNORECASE)
_HETEROGENEITY_READ = re.compile(
    r"\b(low|moderate|substantial|considerable|minimal)\b|"
    r"\b(explain|explained|explaining|reflect|reflects|likely|subgroup)\b|"
    r"prediction\s+interval",
    re.IGNORECASE,
)
_STAT_SIGNAL = re.compile(r"statistically\s+significant", re.IGNORECASE)
_CLINICAL_SIGNAL = re.compile(
    r"clinically\s+(meaningful|important|relevant)|MCID|minimal\s+clinically\s+important",
    re.IGNORECASE,
)
_LIMITATION_HEADING = re.compile(r"limitation", re.IGNORECASE)
_REVIEW_LEVEL = re.compile(
    r"review[-\s]level|review\s+methodology|language\s+restriction|"
    r"database\s+scope|grey\s+literature|single[-\s]reviewer|"
    r"publication\s+bias\s+assessment",
    re.IGNORECASE,
)
_STUDY_LEVEL = re.compile(
    r"study[-\s]level|included\s+(studies|trials|evidence)|primary\s+stud"
    r"|risk\s+of\s+bias",
    re.IGNORECASE,
)
_IMPACT_LANGUAGE = re.compile(
    r"\b(limit|limits|limited|affect|affects|reduce|reduces|inflate|inflates|"
    r"compromise|compromises|restrict|restricts|bias|generaliz|precision|"
    r"confidence|validity)\b",
    re.IGNORECASE,
)
_MITIGATION_LANGUAGE = re.compile(
    r"\b(mitigated|mitigates|mitigating|mitigation)\b|"
    r"\b(we\s+(used|applied|conducted|verified|screened|extracted))\b|"
    r"dual\s+(independent\s+)?(screening|extraction)|"
    r"to\s+(reduce|limit|address)\s+this|"
    r"partially\s+(offset|addressed|address)|"
    r"registered\s+(protocol|in\s+PROSPERO)",
    re.IGNORECASE,
)
_FUTURE_SECTION = re.compile(
    r"future\s+(research|studies|trials)|research\s+agenda|recommendations?\s+for\s+research",
    re.IGNORECASE,
)
_SPECIFIC_DESIGN = re.compile(
    r"randomi[sz]ed|trial|cohort|registry|real[-\s]world|head[-\s]to[-\s]head|"
    r"follow[-\s]up|comparator|sample\s+size|ambulatory|ABPM|24[-\s]hour",
    re.IGNORECASE,
)
_CITATION_MARKER = re.compile(
    r"\[\d+(?:\s*[,–-]\s*\d+)*\]|\([A-Z][A-Za-z'’-]+(?:\s+et\s+al\.?)?,?\s+\d{4}\)"
)
_MARKDOWN_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")

_AUDIT_SECTIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("principal findings", re.compile(r"principal\s+finding|main\s+finding|summary\s+of\s+(main\s+)?finding", re.IGNORECASE)),
    ("interpretation", re.compile(r"interpret|contextuali[sz]|comparison\s+with\s+(prior|previous)", re.IGNORECASE)),
    ("certainty", re.compile(r"certainty|GRADE|strength\s+of\s+evidence", re.IGNORECASE)),
    ("limitations", re.compile(r"limitation", re.IGNORECASE)),
    ("implications", re.compile(r"implication|clinical\s+practice|practice\s+and\s+policy", re.IGNORECASE)),
    ("conclusion", re.compile(r"\bconclusion", re.IGNORECASE)),
)


@dataclass(frozen=True)
class AuditFinding:
    """One gate result. ``severity`` is ``error`` or ``warning``."""

    code: str
    severity: str
    message: str
    excerpt: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "excerpt": self.excerpt,
        }


def _excerpt(text: str, match: re.Match[str], width: int = 90) -> str:
    start = max(0, match.start() - width)
    end = min(len(text), match.end() + width)
    return " ".join(text[start:end].split())


def _banned_hits(text: str, words: Sequence[str]) -> list[tuple[str, re.Match[str]]]:
    hits: list[tuple[str, re.Match[str]]] = []
    for word in words:
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            hits.append((word, match))
    return hits


def _outcome_aliases(outcome: str | Mapping[str, Any]) -> tuple[str, list[str]]:
    if isinstance(outcome, str):
        return outcome, [outcome]
    label = str(outcome.get("label") or outcome.get("name") or "")
    aliases = outcome.get("aliases") or []
    return label, [label, *[str(alias) for alias in aliases]] if label else [str(a) for a in aliases]


@dataclass
class DiscussionAuditReport:
    findings: list[AuditFinding] = field(default_factory=list)
    word_count: int = 0
    paragraph_count: int = 0
    outcomes_found: list[str] = field(default_factory=list)
    outcomes_missing: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": SKILL_NAME,
            "passed": self.passed,
            "word_count": self.word_count,
            "paragraph_count": self.paragraph_count,
            "outcomes_found": list(self.outcomes_found),
            "outcomes_missing": list(self.outcomes_missing),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_markdown(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [
            f"# Systematic-review Discussion audit: {status}",
            "",
            f"- Words: {self.word_count}",
            f"- Paragraphs: {self.paragraph_count}",
            f"- Errors: {len(self.errors)}",
            f"- Warnings: {len(self.warnings)}",
        ]
        if self.outcomes_missing:
            lines.append(f"- Outcomes not discussed: {', '.join(self.outcomes_missing)}")
        lines.append("")
        for severity, label in (("error", "Errors"), ("warning", "Warnings")):
            items = [f for f in self.findings if f.severity == severity]
            if not items:
                continue
            lines.append(f"## {label}")
            for finding in items:
                line = f"- **{finding.code}** {finding.message}"
                if finding.excerpt:
                    line += f"  _...{finding.excerpt}..._"
                lines.append(line)
            lines.append("")
        return "\n".join(lines).strip() + "\n"


def audit_discussion(
    text: str,
    required_outcomes: Sequence[str | Mapping[str, Any]] | None = None,
    min_words: int = 1500,
    max_words: int = 3000,
) -> DiscussionAuditReport:
    """Run the guide's hard gates over a Discussion draft.

    The auditor never rewrites text. It returns errors (gate failures) and
    warnings (quality signals) so the drafting agent or a human can repair the
    draft without inventing evidence.
    """
    text = text or ""
    findings: list[AuditFinding] = []
    words = _WORD.findall(text)
    report = DiscussionAuditReport(
        findings=findings,
        word_count=len(words),
        paragraph_count=len([p for p in re.split(r"\n\s*\n", text) if p.strip()]),
    )

    # 1. Hard punctuation gate.
    for match in re.finditer(EM_DASH, text):
        findings.append(
            AuditFinding(
                "em_dash",
                "error",
                "Em dash found. Use a comma, colon, parentheses, or a period.",
                _excerpt(text, match),
            )
        )
    if len(re.findall(r";", text)) > 3:
        findings.append(
            AuditFinding(
                "semicolon_density",
                "warning",
                "More than three semicolons. Prefer periods or commas for readability.",
            )
        )

    # 2. Background-platitude opening.
    first_paragraph = re.split(r"\n\s*\n", text.strip())[0] if text.strip() else ""
    if _BACKGROUND_OPENERS.search(first_paragraph) and not _ANSWER_OPENER.search(
        first_paragraph
    ):
        findings.append(
            AuditFinding(
                "background_opening",
                "error",
                "Opening restates epidemiological background instead of answering the review question.",
                first_paragraph[:220],
            )
        )

    # 3. Banned vocabulary.
    for word, match in _banned_hits(text, BANNED_AI_VOCABULARY):
        findings.append(
            AuditFinding(
                "banned_vocabulary",
                "error",
                f"Banned AI filler term '{word}'.",
                _excerpt(text, match),
            )
        )
    for word, match in _banned_hits(text, STYLE_WARNINGS):
        findings.append(
            AuditFinding(
                "style_vocabulary",
                "warning",
                f"House-style tell '{word}'.",
                _excerpt(text, match),
            )
        )

    # 4. Overclaiming and generic research calls.
    for match in _OVERCLAIM.finditer(text):
        findings.append(
            AuditFinding(
                "grade_overclaim",
                "error",
                "Certainty overclaim. Match the verb to the GRADE rating (shows / likely / may / very uncertain).",
                _excerpt(text, match),
            )
        )
    if not _HIGH_CERTAINTY.search(text):
        for match in _PROVE.finditer(text):
            findings.append(
                AuditFinding(
                    "grade_overclaim",
                    "error",
                    "'Proves' or 'proven' is only admissible under high certainty. Use 'shows' or state the GRADE rating.",
                    _excerpt(text, match),
                )
            )
    for match in _GENERIC_RESEARCH_CALL.finditer(text):
        findings.append(
            AuditFinding(
                "generic_future_research",
                "error",
                "Generic 'more research is needed'. Name the design, population, comparator, and duration.",
                _excerpt(text, match),
            )
        )

    # 5. GRADE / clinical-significance calibration.
    if len(words) > 400 and not _GRADE_LANGUAGE.search(text):
        findings.append(
            AuditFinding(
                "grade_missing",
                "warning",
                "No certainty framework (GRADE) or certainty language detected.",
            )
        )
    if len(_STAT_SIGNAL.findall(text)) >= 3 and not _CLINICAL_SIGNAL.search(text):
        findings.append(
            AuditFinding(
                "clinical_significance_missing",
                "warning",
                "Statistical significance is emphasised without any MCID or clinical-meaningfulness calibration.",
            )
        )

    # 6. Heterogeneity interpretation.
    if len(words) > 500:
        if not _HETEROGENEITY.search(text):
            findings.append(
                AuditFinding(
                    "heterogeneity_missing",
                    "warning",
                    "Heterogeneity is not addressed. State I² and explain its clinical/methodological sources.",
                )
            )
        elif not _HETEROGENEITY_READ.search(text):
            findings.append(
                AuditFinding(
                    "heterogeneity_uninterpreted",
                    "warning",
                    "Heterogeneity is named but not interpreted (magnitude, sources, applicability).",
                )
            )

    # 7. Two-tier limitations, State -> Impact -> Mitigate.
    if _LIMITATION_HEADING.search(text):
        if not (_REVIEW_LEVEL.search(text) and _STUDY_LEVEL.search(text)):
            findings.append(
                AuditFinding(
                    "limitations_single_tier",
                    "warning",
                    "Separate study-level (included evidence) from review-level (review methodology) limitations.",
                )
            )
        if not _IMPACT_LANGUAGE.search(text):
            findings.append(
                AuditFinding(
                    "limitations_no_impact",
                    "warning",
                    "Limitations are listed without stating their impact on validity, precision, or generalisability.",
                )
            )
        if not _MITIGATION_LANGUAGE.search(text):
            findings.append(
                AuditFinding(
                    "limitations_no_mitigation",
                    "warning",
                    "No mitigation or residual-uncertainty statement follows the limitations.",
                )
            )
    else:
        findings.append(
            AuditFinding(
                "limitations_missing",
                "warning",
                "No limitations section detected.",
            )
        )
    for match in _APOLOGETIC.finditer(text):
        findings.append(
            AuditFinding(
                "apologetic_limitation",
                "warning",
                "Apologetic framing. Use objective 'This review has several limitations' phrasing.",
                _excerpt(text, match),
            )
        )

    # 8. Future-research specificity.
    if _FUTURE_SECTION.search(text) and not _SPECIFIC_DESIGN.search(text):
        findings.append(
            AuditFinding(
                "future_research_vague",
                "warning",
                "Future-research section lacks a concrete design, population, comparator, or follow-up.",
            )
        )

    # 9. Citation presence.
    if len(words) > 300 and not _CITATION_MARKER.search(text):
        findings.append(
            AuditFinding(
                "citations_missing",
                "warning",
                "No numbered or author-year citation markers detected.",
            )
        )

    # 10. Data dump.
    table_rows = len(_MARKDOWN_TABLE_ROW.findall(text))
    if table_rows > 5:
        findings.append(
            AuditFinding(
                "data_dump",
                "warning",
                f"{table_rows} Markdown table rows inside the Discussion. Move tables to the Results.",
            )
        )

    # 11. Length and section coverage.
    if len(words) < min_words:
        findings.append(
            AuditFinding(
                "length_low",
                "warning",
                f"{len(words)} words is below the {min_words}-word target for a comprehensive review Discussion.",
            )
        )
    if len(words) > max_words:
        findings.append(
            AuditFinding(
                "length_high",
                "warning",
                f"{len(words)} words exceeds the {max_words}-word ceiling; tighten without dropping outcomes.",
            )
        )
    for label, pattern in _AUDIT_SECTIONS:
        if not pattern.search(text):
            findings.append(
                AuditFinding(
                    "section_missing",
                    "warning",
                    f"No '{label}' block detected.",
                )
            )

    # 12. Zero-omission coverage.
    if required_outcomes:
        for outcome in required_outcomes:
            label, aliases = _outcome_aliases(outcome)
            if not label:
                continue
            if any(alias and alias.lower() in text.lower() for alias in aliases):
                report.outcomes_found.append(label)
            else:
                report.outcomes_missing.append(label)
                findings.append(
                    AuditFinding(
                        "outcome_omitted",
                        "error",
                        f"Required outcome not discussed: {label}.",
                    )
                )

    return report


# ---------------------------------------------------------------------------
# Numeric fidelity
# ---------------------------------------------------------------------------

_QUANTITY = re.compile(
    r"(?<![\w.])[-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s?%?(?![\w.])"
)
_YEAR = re.compile(r"^(19|20)\d{2}$")


def _normalise_number(token: str) -> str:
    cleaned = token.replace("\u2212", "-").replace(",", "").strip()
    cleaned = re.sub(r"\s?%$", "", cleaned)
    return cleaned


def _quantity_tokens(text: str) -> list[tuple[str, str, re.Match[str]]]:
    """Yield (normalised, raw, match) for quantitative tokens worth checking.

    Keeps decimals, percentages, and integers of 3+ digits; drops years and
    small integers (weeks, study counts, citation numbers). Handles thousands
    separators so ``4,200`` and ``4200`` compare equal.
    """
    found: list[tuple[str, str, re.Match[str]]] = []
    for match in _QUANTITY.finditer(text or ""):
        raw = match.group(0)
        # "95% CI" and "95% confidence interval" are structural labels, not
        # evidence values; flagging them would create a false mismatch.
        tail = (text or "")[match.end(): match.end() + 14]
        if re.match(r"\s*(CI\b|confidence\b)", tail, re.IGNORECASE):
            continue
        normalised = _normalise_number(raw)
        if not normalised or _YEAR.match(normalised):
            continue
        digits = normalised.lstrip("-")
        if "." in normalised or "%" in raw or len(digits) >= 3:
            found.append((normalised, raw, match))
    return found


def extract_quantitative_tokens(text: str) -> list[str]:
    """Return decimals, percentages, and integers of 3+ digits.

    Small integers (weeks, study counts, citation numbers) are excluded on
    purpose: they are too context-dependent to verify by string matching.
    """
    return [normalised for normalised, _raw, _match in _quantity_tokens(text)]


@dataclass
class NumericFidelityReport:
    draft_tokens: int = 0
    source_tokens: int = 0
    matched: list[str] = field(default_factory=list)
    unmatched: list[dict[str, str]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.unmatched

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": SKILL_NAME,
            "passed": self.passed,
            "draft_tokens": self.draft_tokens,
            "source_tokens": self.source_tokens,
            "matched": list(self.matched),
            "unmatched": list(self.unmatched),
        }

    def to_markdown(self) -> str:
        status = "PASS" if self.passed else "REVIEW"
        lines = [
            f"# Numeric fidelity check: {status}",
            "",
            f"- Draft quantitative tokens: {self.draft_tokens}",
            f"- Source quantitative tokens: {self.source_tokens}",
            f"- Unmatched in sources: {len(self.unmatched)}",
            "",
        ]
        if self.unmatched:
            lines.append("## Tokens not found in the evidence files")
            for item in self.unmatched:
                lines.append(f"- `{item['value']}`  _...{item['context']}..._")
        else:
            lines.append("Every quantitative token in the draft appears in the supplied evidence.")
        return "\n".join(lines).strip() + "\n"


def check_numeric_fidelity(
    draft_text: str,
    source_texts: Iterable[str],
) -> NumericFidelityReport:
    """Compare quantitative tokens in a draft against supplied evidence text.

    This is a string-presence check, not a statistical recomputation. It catches
    invented or mistyped pooled estimates. A token absent from the sources is
    flagged for review; it may still be legitimate (for example a guideline
    threshold supplied separately), so the author resolves it.
    """
    joined_sources = "\n".join(source_texts or [])
    source_values = {
        _normalise_number(t).lstrip("-") for t in extract_quantitative_tokens(joined_sources)
    }
    draft_tokens = _quantity_tokens(draft_text or "")

    report = NumericFidelityReport(source_tokens=len(source_values))
    seen: set[str] = set()
    for value, _raw, match in draft_tokens:
        if not value or _YEAR.match(value):
            continue
        report.draft_tokens += 1
        magnitude = value.lstrip("-")
        if magnitude in seen:
            continue
        seen.add(magnitude)
        if magnitude in source_values:
            report.matched.append(value)
        else:
            context = " ".join(
                draft_text[max(0, match.start() - 55): match.end() + 55].split()
            )
            report.unmatched.append({"value": value, "context": context})
    return report


def read_source_texts(
    paths: Iterable[str | Path],
    max_chars: int = 400_000,
    exclude: Iterable[str | Path] | None = None,
) -> list[str]:
    """Read text-like evidence files for the fidelity check.

    Binary formats (PDF/DOCX/XLSX) are skipped; run the repo's extraction
    modules first when those are the only sources. Returns however much text
    fits the budget, never raising on a single unreadable file. ``exclude``
    prevents the draft itself from being counted as evidence when it lives in
    the same project tree.
    """
    texts: list[str] = []
    budget = max_chars
    excluded = {str(Path(item).resolve()) for item in (exclude or [])}
    for raw in paths:
        path = Path(raw)
        candidates = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() not in {
                ".md", ".txt", ".csv", ".tsv", ".json", ".html", ".htm", ".rtf"
            }:
                continue
            if str(candidate.resolve()) in excluded:
                continue
            if budget <= 0:
                return texts
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            texts.append(content[:budget])
            budget -= len(content)
    return texts


# ---------------------------------------------------------------------------
# Plug-and-play system-command builder
# ---------------------------------------------------------------------------

_SYSTEM_COMMAND_TEMPLATE = """\
# System Command: Publication-Grade Systematic Review & Meta-Analysis Discussion Architect (MedDraft_AI)

<ROLE_AND_OBJECTIVE>
You are an elite medical writer, biostatistical synthesizer, and evidence-verification agent
operating inside the MedDraft_AI repository. Write the complete Discussion section for the study
below. Every pooled estimate, confidence interval, p value, I² statistic, and external claim must
be anchored to a verifiable project file or a live-verified reference. Never invent, round, or
transpose a number.
</ROLE_AND_OBJECTIVE>

<STUDY>
Title: {title}
Population: {population}
Intervention: {intervention}
Comparator: {comparator}
Outcomes: {outcomes}
Primary timepoint: {timepoint}
</STUDY>

<EVIDENCE_WORKSPACE>
{workspace}
</EVIDENCE_WORKSPACE>

<EXECUTION_MANDATE>
1. Inventory every file above before writing. Emit a Master Evidence Summary Table covering each
   included study and every pooled outcome (effect estimate, 95% CI, p value, I²), and list prior
   reviews with their scope and findings.
2. If a timepoint, subgroup, or safety outcome was not pooled, write NOT_POOLED / NOT_REPORTED.
   Never substitute a plausible value.
3. Follow the systematic-review-discussion architecture: principal findings, RCI interpretation,
   GRADE certainty, two-tier strengths and limitations, practice/policy implications, specific
   future research, conclusions.
4. Discuss every analysed outcome. Grouping by domain is allowed; omitting null or unfavourable
   outcomes is not.
5. Use the GRADE-calibrated verb for each finding (shows / likely / may / very uncertain).
6. No em dashes, no banned AI vocabulary, no generic "more research is needed".
7. Cite in {citation_style} style and verify every reference before delivery.
</EXECUTION_MANDATE>

<OUTPUT>
Save the draft to: {output}
Also save the audit report from `python -m meddraft_ai sr audit <draft.md>` and resolve every
error-severity finding before declaring the draft complete.
</OUTPUT>
"""


def build_system_command(spec: Mapping[str, Any]) -> str:
    """Render a plug-and-play system command from a study specification.

    Recognised keys: ``title``, ``population``, ``intervention``, ``comparator``,
    ``outcomes`` (string or list), ``timepoint``, ``workspace`` (string or list of
    paths), ``output``, ``citation_style``. Missing fields render as
    ``[INSERT ...]`` so the command is still usable as a template.
    """
    paths = spec.get("workspace") or []
    if isinstance(paths, (str, Path)):
        paths = [paths]
    inventory = inventory_project(paths) if paths else None
    workspace = (
        inventory.to_markdown()
        if inventory and inventory.files
        else "\n".join(f"- `{p}`" for p in paths) or "[INSERT EVIDENCE WORKSPACE PATHS]"
    )
    outcomes = spec.get("outcomes") or "[INSERT PRIMARY AND SECONDARY OUTCOMES]"
    if isinstance(outcomes, (list, tuple)):
        outcomes = "; ".join(str(item) for item in outcomes)
    return _SYSTEM_COMMAND_TEMPLATE.format(
        title=spec.get("title") or "[INSERT STUDY TITLE]",
        population=spec.get("population") or "[INSERT POPULATION]",
        intervention=spec.get("intervention") or "[INSERT INTERVENTION]",
        comparator=spec.get("comparator") or "[INSERT COMPARATOR]",
        outcomes=outcomes,
        timepoint=spec.get("timepoint") or "[INSERT PRIMARY TIMEPOINT]",
        workspace=workspace,
        citation_style=spec.get("citation_style") or "Vancouver",
        output=spec.get("output") or "[INSERT OUTPUT PATH]",
    )


def load_spec(path: str | Path) -> dict[str, Any]:
    """Load a JSON study spec for :func:`build_system_command`.

    ``utf-8-sig`` accepts both plain UTF-8 and the BOM that Windows editors and
    PowerShell's ``Set-Content -Encoding UTF8`` prepend.
    """
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))
