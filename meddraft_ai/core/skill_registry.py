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
    "academic_research_skills",
    "claude_scientific_writer",
    "doi_reference_validator",
    "humanizer-main",       # Phase 2: newly registered
    "humanizer_noora",
    "med_paper_assistant",
    "medical_research_skills",
    "research_surfer",
    "sciwrite",
    "pdf",                  # Phase 2: newly registered
    "docx",                 # Phase 2: newly registered
]


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
