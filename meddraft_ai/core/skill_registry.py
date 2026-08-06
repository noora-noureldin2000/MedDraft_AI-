import os
import re
from pathlib import Path
from typing import List, Dict, Any
from meddraft_ai.core.config import get_config

class SkillRegistry:
    """
    Discovers, indexes, and loads prompt/skill files dynamically from meddraft_ai/prompts.
    """
    def __init__(self):
        self.config = get_config()
        self.prompts_dir = self.config.PROMPTS_DIR
        self.skills: List[Dict[str, Any]] = []

    def load(self) -> 'SkillRegistry':
        self.skills = []
        if not self.prompts_dir.exists():
            return self

        for root, _, files in os.walk(self.prompts_dir):
            for file in files:
                if file.endswith(".md") or file.endswith(".txt"):
                    abs_path = Path(root) / file
                    try:
                        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        
                        keywords = set(re.findall(r"\b[a-zA-Z]{3,15}\b", content.lower()))
                        self.skills.append({
                            "name": file.replace(".md", "").replace(".txt", ""),
                            "abs_path": str(abs_path),
                            "rel_path": str(abs_path.relative_to(self.prompts_dir)),
                            "keywords": list(keywords)
                        })
                    except Exception:
                        pass
        return self

    def get_skill(self, name: str) -> str:
        for skill in self.skills:
            if skill["name"].lower() == name.lower():
                try:
                    with open(skill["abs_path"], "r", encoding="utf-8", errors="ignore") as f:
                        return f.read()
                except Exception:
                    return ""
        return ""
