import sys
import re
from pathlib import Path
from rich.console import Console

from meddraft_ai.core.config import get_config
from meddraft_ai.core.skill_registry import SkillRegistry
from meddraft_ai.core.llm_client import LLMClient

console = Console()

class BaseSpecialist:
    def __init__(self, name: str, folder_keywords: list):
        self.name = name
        self.folder_keywords = folder_keywords
        self.config = get_config()
        self.registry = SkillRegistry().load()
        self.llm = LLMClient()

    def _read_prompt_file(self, file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except Exception:
            return ""

    def get_preamble(self) -> str:
        preamble_path = self.config.PROMPTS_DIR / "agent_instructions.md"
        if preamble_path.exists():
            try:
                with open(preamble_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                rules_end = content.find("## Task 1:")
                if rules_end != -1:
                    return content[:rules_end].strip()
                return content[:5000].strip()
            except Exception as e:
                return f"Preamble Error: {e}"
        return "Core Persona: MedDraft_AI Medical Research Assistant (Zero-Hallucination Policy enabled)."

    def load_context(self) -> str:
        context_parts = []
        for skill in self.registry.skills:
            path_str = skill["abs_path"].replace("\\", "/")
            if any(kw in path_str for kw in self.folder_keywords):
                content = self._read_prompt_file(skill["abs_path"])
                if content:
                    context_parts.append(f"### SKILL: {skill['name']}\n{content}\n")
        return "\n".join(context_parts)

    def format_prompt(self, user_query: str) -> dict:
        preamble = self.get_preamble()
        context = self.load_context()
        system_prompt = (
            f"ROLE AND CORE POLICIES:\n{preamble}\n\n"
            f"SPECIALIST CONTEXT & REFERENCE SKILLS:\n{context}\n\n"
            f"You are now acting as the {self.name} specialist. Adhere strictly to core policies and guidelines."
        )
        return {"system_prompt": system_prompt, "user_prompt": user_query}

    def execute(self, user_query: str) -> str:
        prompts = self.format_prompt(user_query)
        return self.llm.query(prompts["system_prompt"], prompts["user_prompt"])


class CoreWriterSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("CORE_WRITER", [
            "agent_instructions",
            "sciwrite",
            "academic_research_skills",
            "medical_research_skills",
            "claude_scientific_writer"
        ])


class HumanizerSpecialist(BaseSpecialist):
    """
    Applied as an on-demand post-processing pass over full manuscript drafts.
    Incorporate Dr. Noora Noureldin's writing style markers and anti-AI clichés.
    """
    def __init__(self):
        super().__init__("HUMANIZER", ["humanizer_noora", "humanizer_general"])

    def humanize(self, full_manuscript_text: str) -> str:
        console.print("[bold yellow]Executing on-demand humanization pass...[/bold yellow]")
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
            "academic_research_skills/academic-pipeline"
        ])


class ProofReaderSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("PROOF_READER", [
            "proofreading",
            "sciwrite",
            "academic_research_skills/academic-paper-reviewer"
        ])


class ReferencesSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("REFERENCES", ["doi_reference_validator", "research_surfer"])


class DeepResearchSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("DEEP_RESEARCH", ["academic_research_skills/deep-research", "research_surfer"])


class AcademicPaperSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("ACADEMIC_PAPER", ["academic_research_skills/academic-paper", "claude_scientific_writer"])


class MedPaperAssistantSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("MED_PAPER_ASSISTANT", ["med_paper_assistant", "medical_research_skills"])
