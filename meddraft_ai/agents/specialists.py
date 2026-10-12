import sys
import re
import logging
from pathlib import Path

from meddraft_ai.core.config import get_config
from meddraft_ai.core.skill_registry import SkillRegistry
from meddraft_ai.core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class BaseSpecialist:
    def __init__(self, name: str, folder_keywords: list):
        self.name = name
        self.folder_keywords = folder_keywords
        self.config = get_config()
        self.registry = SkillRegistry().load()
        self.llm = LLMClient()

    def _read_prompt_file(self, file_path: str) -> str:
        try:
            return Path(file_path).read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            return Path(file_path).read_text(encoding="utf-8", errors="replace").strip()
        except FileNotFoundError:
            logger.warning("Prompt file not found: %s", file_path)
            return ""
        except OSError as err:
            logger.error("Cannot read prompt file %s: %s", file_path, err)
            return ""

    def get_preamble(self) -> str:
        preamble_path = self.config.PROMPTS_DIR / "agent_instructions.md"
        if preamble_path.exists():
            try:
                content = preamble_path.read_text(encoding="utf-8")
                rules_end = content.find("## Task 1:")
                if rules_end != -1:
                    return content[:rules_end].strip()
                return content[:5000].strip()
            except OSError as err:
                logger.error("Cannot read preamble file %s: %s", preamble_path, err)
        return "Core Persona: MedDraft_AI Medical Research Assistant (Zero-Hallucination Policy enabled)."

    def load_context(self, task_hint: str = None) -> str:
        MAX_CONTEXT_CHARS = 60000
        # Budget reserved for query-relevant Nature skills (phase 1 below).
        # Existing packs keep first claim on the remainder, so non-Nature
        # queries produce byte-identical context to before this integration.
        NATURE_FIRST_PASS_CHARS = 30000
        context_parts = []
        total_chars = 0
        loaded_paths = set()

        def _append(abs_path: str, name: str, content: str) -> bool:
            nonlocal total_chars
            entry = f"### SKILL: {name}\n{content}\n"
            if total_chars + len(entry) > MAX_CONTEXT_CHARS:
                return False
            context_parts.append(entry)
            total_chars += len(entry)
            loaded_paths.add(abs_path)
            return True

        # Phase 1: preload only the Nature skills this query actually needs
        # (and only those assigned to this specialist). Empty for queries
        # without Nature signals — existing behavior untouched.
        try:
            from meddraft_ai.core.nature_integration import (
                get_nature_chain,
                nature_keywords_for,
            )
            from meddraft_ai.core.skill_registry import AUTO_ROUTE_KEYWORDS
            own_frags = nature_keywords_for(self.name)
            if task_hint and own_frags:
                _, _, chain_skills = get_nature_chain(task_hint)
                # Chain skills first (priority order), then keyword-overlap
                # matches at the registry's >= 2-signal threshold.
                lowered = task_hint.lower()
                wanted = list(chain_skills)
                for skill_name, phrases in AUTO_ROUTE_KEYWORDS.items():
                    if skill_name in wanted:
                        continue
                    if sum(1 for kw in phrases if kw in lowered) >= 2:
                        wanted.append(skill_name)
                budgeted = 0
                for skill in wanted:
                    frag = next((f for f in own_frags if skill in f), None)
                    if frag is None:
                        continue
                    for reg_skill in self.registry.skills:
                        norm = reg_skill["abs_path"].replace("\\", "/")
                        if frag in norm and norm not in loaded_paths:
                            content = self._read_prompt_file(reg_skill["abs_path"])
                            if not content:
                                continue
                            entry_len = len(f"### SKILL: {reg_skill['name']}\n{content}\n")
                            if budgeted + entry_len > NATURE_FIRST_PASS_CHARS:
                                break
                            if _append(reg_skill["abs_path"], reg_skill["name"], content):
                                budgeted += entry_len
                            break
        except ImportError:
            pass

        # Phase 2: legacy walk-order loading of the remaining packs.
        for skill in self.registry.skills:
            path_str = skill["abs_path"].replace("\\", "/")
            if not any(kw in path_str for kw in self.folder_keywords):
                continue
            if skill["abs_path"] in loaded_paths:
                continue
            skill_path = Path(skill["abs_path"])
            folder = skill_path.parent
            if (folder / "SKILL.md").exists() and skill_path.name != "SKILL.md":
                continue
            content = self._read_prompt_file(skill["abs_path"])
            if not content:
                continue
            entry = f"### SKILL: {skill['name']}\n{content}\n"
            if total_chars + len(entry) > MAX_CONTEXT_CHARS:
                if total_chars == 0:
                    # A single oversized file (e.g. agent_instructions.md at
                    # ~100KB) must not abort loading entirely — skip it so
                    # smaller packs still load. Once anything has loaded, keep
                    # the original stop-at-budget behavior, so specialists
                    # that already load context are byte-for-byte unaffected.
                    logger.debug("Skipping oversized skill file %s (%d chars).",
                                 skill["abs_path"], len(entry))
                    continue
                break
            context_parts.append(entry)
            total_chars += len(entry)
        return "\n".join(context_parts)

    def format_prompt(self, user_query: str) -> dict:
        preamble = self.get_preamble()
        context = self.load_context(user_query)
        system_prompt = (
            f"ROLE AND CORE POLICIES:\n{preamble}\n\n"
            f"SPECIALIST CONTEXT & REFERENCE SKILLS:\n{context}\n\n"
            f"You are now acting as the {self.name} specialist. Adhere strictly to core policies and guidelines."
        )
        return {"system_prompt": system_prompt, "user_prompt": user_query}

    def execute(self, user_query: str) -> str:
        prompts = self.format_prompt(user_query)
        try:
            return self.llm.query(prompts["system_prompt"], prompts["user_prompt"])
        except ValueError as err:
            # Missing API key — surface clearly so the user can act on it
            logger.error("%s specialist failed — configuration error: %s", self.name, err)
            raise
        except Exception as err:
            logger.error("%s specialist LLM call failed: %s", self.name, err)
            raise RuntimeError(f"{self.name} specialist failed: {err}") from err


class CoreWriterSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("CORE_WRITER", [
            "agent_instructions",
            "sciwrite",
            "academic_research_skills",
            "medical_research_skills",
            "claude_scientific_writer",
            "citation-integrity",
            "surgical-word-reduction",
            # Nature layer: structural revision + figure logic + review articles.
            "manuscript-optimizer/SKILL.md",
            "results-section-revision/SKILL.md",
            "figure-planner/SKILL.md",
            "review-article-architecture/SKILL.md",
            "paper-bootstrap/SKILL.md",
            "draft-marker-discipline/SKILL.md",
        ])


class HumanizerSpecialist(BaseSpecialist):
    """
    Applied as an on-demand post-processing pass over full manuscript drafts.
    Incorporate Dr. Noora Noureldin's writing style markers and anti-AI clichés.
    Loads context from both humanizer_noora and humanizer-main prompt directories.
    """
    def __init__(self):
        super().__init__("HUMANIZER", ["humanizer_noora", "humanizer_general", "humanizer-main"])

    def humanize(self, full_manuscript_text: str) -> str:
        # Presentation (console output) belongs to the CLI layer; this method
        # only performs the LLM transformation and returns the result.
        user_prompt = (
            f"Please humanize the following completed academic manuscript draft while strictly preserving "
            f"all scientific facts, numbers, citations, and evidence integrity.\n\n"
            f"MANUSCRIPT DRAFT:\n\n{full_manuscript_text}"
        )
        return self.execute(user_prompt)


class VerifierAndStatsSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("VERIFIER_AND_STATS", [
            "doi_reference_validator",
            "apa_reporting",
            "academic_research_skills/academic-pipeline",
            # Nature layer: semantic claim checks, reporting audit, preflight.
            "claim-source-verification/SKILL.md",
            "stats-reporting-audit/SKILL.md",
            "submission-audit/SKILL.md",
            "citation-verifier/SKILL.md",
            "data-availability/SKILL.md",
        ])


class ProofReaderSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("PROOF_READER", [
            "proofreading",
            "sciwrite",
            "academic_research_skills/academic-paper-reviewer",
            "citation-integrity",
            "surgical-word-reduction",
            # Nature layer: sentence lint, de-auditing, clarity/logic diagnosis.
            "scientific-prose-style/SKILL.md",
            "anti-defensive-writing/SKILL.md",
            "write-scientific-manuscript/SKILL.md",
        ])


class ReferencesSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("REFERENCES", ["doi_reference_validator", "research_surfer", "medical-clinicaltrials"])


class TrialsSpecialist(BaseSpecialist):
    """Filtered ClinicalTrials.gov search + NCT-ID deep dives.

    Loaded automatically whenever the task text carries clinical-trial
    signals (see SkillRegistry auto-routing for medical-clinicaltrials).
    """
    def __init__(self):
        super().__init__("TRIALS", ["medical-clinicaltrials"])


class DeepResearchSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("DEEP_RESEARCH", [
            "academic_research_skills/deep-research",
            "research_surfer",
            "academic-search-agent",
            # Nature layer: single-paper deep notes.
            "paper-analyzer/SKILL.md",
        ])


class AcademicPaperSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("ACADEMIC_PAPER", [
            "academic_research_skills/academic-paper",
            "claude_scientific_writer",
            # Nature layer: venue fit, figure craft, findings bridge.
            "nature-portfolio-playbook/SKILL.md",
            "figure-style/SKILL.md",
            "figure-planner/SKILL.md",
            "results-analysis/SKILL.md",
        ])


class RebuttalSpecialist(BaseSpecialist):
    """Author-side reviewer-response workflow: inventory every ask, draft
    calibrated point-by-point replies, and grade coverage.

    Loaded automatically whenever the task text carries rebuttal signals
    (see SkillRegistry auto-routing for rebuttal-response / paper-reviewer).
    """
    def __init__(self):
        super().__init__("REBUTTAL", [
            "rebuttal-response/SKILL.md",
            "paper-reviewer/SKILL.md",
        ])


class MedPaperAssistantSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("MED_PAPER_ASSISTANT", ["med_paper_assistant", "medical_research_skills"])


class SecondaryCitationSpecialist(BaseSpecialist):
    """Traces nested/secondary citations to their root study and emits dual
    ``as cited in`` attribution. Loaded automatically whenever the task text
    matches the secondary-citation-extractor skill (see SkillRegistry).
    """
    def __init__(self):
        super().__init__("SECONDARY_CITATION", ["secondary-citation-extractor"])

    def trace(self, excerpt_or_pdf_text: str) -> str:
        from meddraft_ai.extraction.secondary_citation import (
            SecondaryCitationExtractor,
        )
        markdown = SecondaryCitationExtractor.extract_to_markdown(excerpt_or_pdf_text)
        return self.execute(
            "Apply the secondary-citation-extractor skill workflow to the text below. "
            "Distinguish the container author from the root author, trace each "
            "in-text key to the bibliography, and emit the dual-attribution output "
            "template (do not invent metadata).\n\n"
            f"PRE-EXTRACTED DUAL CITATIONS:\n{markdown}\n\n"
            f"SOURCE TEXT:\n{excerpt_or_pdf_text[:6000]}"
        )
