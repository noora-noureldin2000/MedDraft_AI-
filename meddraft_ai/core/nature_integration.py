"""Nature Paper Skills integration layer (additive, non-destructive).

Twenty skills vendored from Boom5426/Nature-Paper-Skills (see
meddraft_ai/prompts/nature-paper-skills/README.md for manifest, skipped-skill
rationale, and license attribution). Each skill is mirrored at
`.agents/skills/<name>/` (agent discovery, pinned in skills-lock.json) and
`meddraft_ai/prompts/<name>/` (pipeline registry).

This module is the single source of truth for how those skills plug into the
existing engine:

- NATURE_SKILL_TO_SPECIALIST: which specialist loads each skill
  (no existing skill was removed or renamed).
- NATURE_SPECIALIST_FILE_KEYWORDS: ``<name>/SKILL.md`` path fragments applied
  explicitly in each specialist's folder keywords (see specialists.py).
  File-scoped (not directory-scoped) on purpose: BaseSpecialist.load_context()
  caps context at 60,000 chars, so each specialist gains roughly one skill
  file without crowding out existing packs. The skills' ``references/``
  guides stay indexed for registry keyword fallback. nature_keywords_for()
  exposes the same mapping for tests and tooling.
- NATURE_TRIGGER_KEYWORDS: keyword sets mirrored into AUTO_ROUTE_KEYWORDS so
  SkillRegistry.match_skill_for_task() routes automatically.
- PIPELINE_CHAINS: ordered multi-skill chains for compound tasks.
- get_nature_chain(task_text): returns (chain_name, specialist, skills) or
  (None, None, []) when nothing matches, so normal routing is untouched.
"""

from __future__ import annotations

import re

# Skill folder name -> owning specialist. Must match specialist names in
# meddraft_ai/agents/specialists.py (REBUTTAL = RebuttalSpecialist, new).
NATURE_SKILL_TO_SPECIALIST: dict[str, str] = {
    # Integrity / verification family -> VERIFIER_AND_STATS
    "claim-source-verification": "VERIFIER_AND_STATS",
    "stats-reporting-audit": "VERIFIER_AND_STATS",
    "submission-audit": "VERIFIER_AND_STATS",
    "citation-verifier": "VERIFIER_AND_STATS",
    "data-availability": "VERIFIER_AND_STATS",
    # Structural writing family -> CORE_WRITER
    "manuscript-optimizer": "CORE_WRITER",
    "results-section-revision": "CORE_WRITER",
    "figure-planner": "CORE_WRITER",
    "review-article-architecture": "CORE_WRITER",
    "paper-bootstrap": "CORE_WRITER",
    "draft-marker-discipline": "CORE_WRITER",
    # Sentence / style family -> PROOF_READER
    "scientific-prose-style": "PROOF_READER",
    "anti-defensive-writing": "PROOF_READER",
    "write-scientific-manuscript": "PROOF_READER",
    # Review exchange family -> REBUTTAL (new RebuttalSpecialist)
    "rebuttal-response": "REBUTTAL",
    "paper-reviewer": "REBUTTAL",
    # Venue / figure craft + findings bridge -> ACADEMIC_PAPER
    "nature-portfolio-playbook": "ACADEMIC_PAPER",
    "figure-style": "ACADEMIC_PAPER",
    "figure-planner": "ACADEMIC_PAPER",
    "results-analysis": "ACADEMIC_PAPER",
    # Single-paper deep notes -> DEEP_RESEARCH
    "paper-analyzer": "DEEP_RESEARCH",
}

# Specialist -> extra file-scoped path fragments for load_context().
NATURE_SPECIALIST_FILE_KEYWORDS: dict[str, list[str]] = {
    "VERIFIER_AND_STATS": [
        "claim-source-verification/SKILL.md",
        "stats-reporting-audit/SKILL.md",
        "submission-audit/SKILL.md",
        "citation-verifier/SKILL.md",
        "data-availability/SKILL.md",
    ],
    "CORE_WRITER": [
        "manuscript-optimizer/SKILL.md",
        "results-section-revision/SKILL.md",
        "figure-planner/SKILL.md",
        "review-article-architecture/SKILL.md",
        "paper-bootstrap/SKILL.md",
        "draft-marker-discipline/SKILL.md",
    ],
    "PROOF_READER": [
        "scientific-prose-style/SKILL.md",
        "anti-defensive-writing/SKILL.md",
        "write-scientific-manuscript/SKILL.md",
    ],
    "REBUTTAL": [
        "rebuttal-response/SKILL.md",
        "paper-reviewer/SKILL.md",
    ],
    "ACADEMIC_PAPER": [
        "nature-portfolio-playbook/SKILL.md",
        "figure-style/SKILL.md",
        "figure-planner/SKILL.md",
        "results-analysis/SKILL.md",
    ],
    "DEEP_RESEARCH": [
        "paper-analyzer/SKILL.md",
    ],
}

# Skill name -> trigger phrases for AUTO_ROUTE_KEYWORDS. Each list is sized so
# a natural query scores >= 2 (the match_skill_for_task threshold) while
# staying clear of existing skills' signals (citation-integrity's
# "literature review", academic-search-agent's "background literature", etc.).
NATURE_TRIGGER_KEYWORDS: dict[str, list[str]] = {
    "claim-source-verification": [
        "claim to evidence",
        "claim-source",
        "does the source support",
        "does this paper support",
        "verify claims against",
        "citation support",
    ],
    "stats-reporting-audit": [
        "statistical reporting",
        "stats reporting audit",
        "independent-unit",
        "biological versus technical",
        "multiple-comparison correction",
        "figure legend statistics",
    ],
    "submission-audit": [
        "submission audit",
        "pre-submission",
        "preflight check",
        "ready for submission",
        "resubmission",
        "submission-ready",
    ],
    "citation-verifier": [
        "bibtex",
        "duplicate keys",
        "placeholder reference",
        "citation hygiene",
        "cited-vs-defined",
    ],
    "data-availability": [
        "data availability",
        "data-sharing statement",
        "source-data coverage",
        "accession number",
        "repository plan",
    ],
    "manuscript-optimizer": [
        "manuscript optimizer",
        "restructure my manuscript",
        "evidence chain",
        "claim hierarchy",
        "overclaiming",
    ],
    "results-section-revision": [
        "results section revision",
        "revise my results section",
        "stitched figure captions",
        "subsection titles",
        "paragraph openings",
    ],
    "figure-planner": [
        "figure planner",
        "one claim per figure",
        "panel role",
        "legend sync",
        "main versus supplement",
    ],
    "figure-style": [
        "figure style",
        "figure legibility",
        "apply_figure_style",
        "panel letter",
    ],
    "review-article-architecture": [
        "review article",
        "survey paper structure",
        "perspective article",
        "governing plan document",
        "display-item budget",
        "drift audit",
    ],
    "paper-bootstrap": [
        "paper bootstrap",
        "start a new manuscript",
        "new manuscript project",
        "source of truth",
    ],
    "draft-marker-discipline": [
        "draft marker",
        "todo marker",
        "open-question tracking",
    ],
    "scientific-prose-style": [
        "scientific prose style",
        "em-dash budget",
        "ai tells",
        "sounds ai-generated",
    ],
    "anti-defensive-writing": [
        "defensive writing",
        "de-audit",
        "audit tone",
        "self-critical writing",
    ],
    "write-scientific-manuscript": [
        "clarity and logic",
        "buried topic sentence",
        "observation separate from interpretation",
    ],
    "rebuttal-response": [
        "rebuttal",
        "response letter",
        "point-by-point",
        "reply to reviewer",
        "reviewer response",
        "revise and resubmit",
    ],
    "paper-reviewer": [
        "paper-reviewer",
        "referee report",
        "grade my reply",
        "did i miss a point",
        "reviewer checklist",
    ],
    "nature-portfolio-playbook": [
        "nature portfolio",
        "nature methods",
        "nature biotechnology",
        "venue fit",
    ],
    "paper-analyzer": [
        "paper analyzer",
        "single-paper analysis",
        "structured notes on",
        "claims, methods",
    ],
    "results-analysis": [
        "results analysis",
        "experiment outputs into",
        "paper-ready findings",
    ],
}

_CHAIN_PATTERNS: dict[str, re.Pattern] = {
    "pre_submission": re.compile(
        r"(submission.audit|pre.submission|preflight|ready (for|to) submi|"
        r"final (check|qa)|resubmission)",
        re.IGNORECASE,
    ),
    "rebuttal": re.compile(
        r"(rebuttal|response letter|point.by.point|reply to reviewer|"
        r"reviewer comment|revise and resubmit|answer each comment|"
        r"did i miss a point)",
        re.IGNORECASE,
    ),
    "results_repair": re.compile(
        r"(results section.*(revis|repair|flow|polish)|revise.*results section|"
        r"reads like.*figure caption|stitched.*caption)",
        re.IGNORECASE,
    ),
    "figure_plan": re.compile(
        r"(figure (plan|claim|design|logic|panel)|one claim per figure|"
        r"panel role|legend.*(sync|align)|apply_figure_style)",
        re.IGNORECASE,
    ),
    "review_article": re.compile(
        r"(review article|survey paper.*struct|perspective.*(article|struct)|"
        r"governing plan document|display.item budget)",
        re.IGNORECASE,
    ),
    "data_avail": re.compile(
        r"(data availability|data.sharing statement|source.data coverage|"
        r"accession.number|repository plan)",
        re.IGNORECASE,
    ),
    "claim_source": re.compile(
        r"(claim.source|claim.to.evidence|does (the|this) (source|paper|"
        r"reference|citation) (actually |really )?(support|say)|"
        r"verify (the |my |each )?claims? against|citation support)",
        re.IGNORECASE,
    ),
    "stats_audit": re.compile(
        r"(stats?.reporting.audit|statistical.reporting|independent.unit|"
        r"biological (vs|versus|and) technical replicat|"
        r"multiple.comparison.*correct|figure.legend.*statistic)",
        re.IGNORECASE,
    ),
}

# Ordered multi-skill chains for compound tasks. Each chain lists skill folder
# names in the order they should be applied, plus the owning specialist.
PIPELINE_CHAINS: dict[str, dict] = {
    "pre_submission": {
        "description": "Late-stage QA before (re)submission: audit claims, stats, figures, data package.",
        "specialist": "VERIFIER_AND_STATS",
        "skills": [
            "submission-audit",
            "claim-source-verification",
            "stats-reporting-audit",
            "citation-verifier",
            "data-availability",
        ],
    },
    "rebuttal": {
        "description": "Reviewer-response workflow: inventory asks, draft calibrated replies, grade coverage.",
        "specialist": "REBUTTAL",
        "skills": ["paper-reviewer", "rebuttal-response", "claim-source-verification"],
    },
    "results_repair": {
        "description": "Late-stage Results + figures repair: flow, claim-per-figure, legend sync, de-audit.",
        "specialist": "CORE_WRITER",
        "skills": [
            "results-section-revision",
            "figure-planner",
            "manuscript-optimizer",
            "anti-defensive-writing",
            "scientific-prose-style",
        ],
    },
    "new_paper": {
        "description": "Bootstrap then structure: project init, claim hierarchy, section contracts.",
        "specialist": "CORE_WRITER",
        "skills": ["paper-bootstrap", "manuscript-optimizer", "draft-marker-discipline", "figure-planner"],
    },
    "review_article": {
        "description": "Review/survey/Perspective architecture: governing plan, drift control, display budget.",
        "specialist": "CORE_WRITER",
        "skills": ["review-article-architecture", "figure-planner", "claim-source-verification"],
    },
}

_CHAIN_SPECIALIST_FALLBACK: dict[str, tuple[str, list[str]]] = {
    "figure_plan": ("CORE_WRITER", ["figure-planner", "figure-style"]),
    "data_avail": ("VERIFIER_AND_STATS", ["data-availability"]),
    "claim_source": ("VERIFIER_AND_STATS", ["claim-source-verification"]),
    "stats_audit": ("VERIFIER_AND_STATS", ["stats-reporting-audit"]),
}


def get_nature_chain(task_text: str) -> tuple[str | None, str | None, list[str]]:
    """Return (chain_name, specialist, skills) when a task needs a Nature chain.

    Additive hook: returns (None, None, []) when nothing matches so the normal
    routing flow is untouched. Called from SkillRegistry.match_skill_for_task()
    after the dedicated scorers (secondary-citation, clinicaltrials).
    """
    if not task_text:
        return None, None, []
    for chain_name, pattern in _CHAIN_PATTERNS.items():
        if pattern.search(task_text):
            if chain_name in PIPELINE_CHAINS:
                chain = PIPELINE_CHAINS[chain_name]
                return chain_name, chain["specialist"], list(chain["skills"])
            specialist, skills = _CHAIN_SPECIALIST_FALLBACK[chain_name]
            return chain_name, specialist, list(skills)
    return None, None, []


def nature_keywords_for(specialist_name: str) -> list[str]:
    """Extra file-scoped path fragments for a specialist (empty when none)."""
    return list(NATURE_SPECIALIST_FILE_KEYWORDS.get(specialist_name, []))
