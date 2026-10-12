import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any

from meddraft_ai.core.config import get_config

logger = logging.getLogger(__name__)

# Prompt sub-directories that are always scanned in addition to the root.
# New folders only need to be added here — no other code change required.
REGISTERED_PROMPT_SUBDIRS: List[str] = [
    "academic-writing",
    "academic_research_skills",
    "claude_scientific_writer",
    "doi_reference_validator",
    "humanizer-main",       # Phase 2: newly registered
    "humanizer_noora",
    "language-refinement",
    "med_paper_assistant",
    "medical_research_skills",
    "research_surfer",
    "sciwrite",
    "pdf",                  # Phase 2: newly registered
    "docx",                 # Phase 2: newly registered
    "thesis-discussion-writer",
    "secondary-citation-extractor",  # Nested/secondary citation tracing + dual attribution
]

# Skill name → trigger phrases used by match_skill_for_task() for automatic
# routing. The secondary-citation-extractor entry delegates scoring to its
# code layer (SecondaryCitationExtractor.match_score) via lazy import so the
# registry stays dependency-light and import-cycle free.
AUTO_ROUTE_KEYWORDS: Dict[str, List[str]] = {
    "secondary-citation-extractor": [
        "as cited in",
        "secondary citation",
        "secondary source",
        "nested citation",
        "dual bibliography",
        "trace citation",
        "root author",
        "container author",
        "resolve reference",
    ],
}


class SkillRegistry:
    """
    Discovers, indexes, and loads prompt/skill files dynamically from
    meddraft_ai/prompts and all registered sub-directories.
    """

    def __init__(self) -> None:
        self.config = get_config()
        self.prompts_dir = self.config.PROMPTS_DIR
        self.skills: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> "SkillRegistry":
        """Walk the prompts directory tree and index every .md / .txt file."""
        self.skills = []
        if not self.prompts_dir.exists():
            logger.warning("Prompts directory not found: %s", self.prompts_dir)
            return self

        for root, _, files in os.walk(self.prompts_dir):
            for file in files:
                if not (file.endswith(".md") or file.endswith(".txt")):
                    continue
                abs_path = Path(root) / file
                try:
                    # Strict UTF-8: no silent corruption of medical Unicode symbols.
                    content = abs_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    # Last-resort fallback with replacement — still log it.
                    logger.debug("UTF-8 decode failed for %s; retrying with replacement.", abs_path)
                    try:
                        content = abs_path.read_text(encoding="utf-8", errors="replace")
                    except OSError as io_err:
                        logger.error("Cannot read skill file %s: %s", abs_path, io_err)
                        continue
                except OSError as io_err:
                    logger.error("Cannot read skill file %s: %s", abs_path, io_err)
                    continue

                keywords = set(re.findall(r"\b[a-zA-Z]{3,15}\b", content.lower()))
                try:
                    rel_path = abs_path.relative_to(self.prompts_dir)
                except ValueError:
                    rel_path = abs_path

                self.skills.append({
                    "name": file.replace(".md", "").replace(".txt", ""),
                    "abs_path": str(abs_path),
                    "rel_path": str(rel_path),
                    "keywords": list(keywords),
                })

        logger.debug("SkillRegistry loaded %d skill files.", len(self.skills))
        return self

    def get_skill(self, name: str) -> str:
        """
        Return the content of the named skill file.

        Raises ValueError if the skill is not found so callers know the registry
        was not loaded or the name is wrong — rather than silently sending an
        empty prompt to the LLM.
        """
        for skill in self.skills:
            if skill["name"].lower() == name.lower():
                abs_path = skill["abs_path"]
                try:
                    return Path(abs_path).read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    return Path(abs_path).read_text(encoding="utf-8", errors="replace")
                except OSError as io_err:
                    raise ValueError(
                        f"Skill file found in index but cannot be read: {abs_path}"
                    ) from io_err

        raise ValueError(
            f"Skill '{name}' not found in registry. "
            f"Available: {[s['name'] for s in self.skills]}"
        )

    def match_skill_for_task(self, task_text: str) -> str | None:
        """Automatically route a task description to the most relevant skill.

        The secondary-citation-extractor skill is called out automatically
        when the task looks like nested/secondary citation work (``as cited
        in``, bracket/author-date markers plus bibliography language). Other
        skills fall back to simple keyword overlap so routing stays generic.

        Returns the skill/pack name (e.g. ``"secondary-citation-extractor"``)
        or ``None`` when nothing matches confidently.
        """
        if not task_text:
            return None
        # Dedicated scorer for the citation skill — lazy import, no cycle.
        try:
            from meddraft_ai.extraction.secondary_citation import (
                SecondaryCitationExtractor,
            )
            if SecondaryCitationExtractor.should_trigger(task_text):
                return SecondaryCitationExtractor.skill_name
        except ImportError:
            pass

        lowered = task_text.lower()
        best_name: str | None = None
        best_score = 0
        for skill_name, keywords in AUTO_ROUTE_KEYWORDS.items():
            if skill_name == "secondary-citation-extractor":
                continue  # already handled above
            score = sum(1 for kw in keywords if kw in lowered)
            if score > best_score:
                best_score = score
                best_name = skill_name
        if best_score >= 2:
            return best_name

        # Generic fallback: keyword overlap against indexed skill contents.
        if self.skills:
            scored: list[tuple[int, str]] = []
            task_words = set(re.findall(r"\b[a-z]{3,15}\b", lowered))
            for skill in self.skills:
                overlap = len(task_words & set(skill.get("keywords", [])))
                if overlap:
                    scored.append((overlap, skill["name"]))
            if scored:
                scored.sort(reverse=True)
                if scored[0][0] >= 3:
                    return scored[0][1]
        return None

    def get_skill_with_auto_routing(self, name_or_task: str) -> str:
        """Get a skill by exact name, falling back to automatic routing."""
        try:
            return self.get_skill(name_or_task)
        except ValueError:
            routed = self.match_skill_for_task(name_or_task)
            if routed:
                return self.get_skill(routed)
            raise
