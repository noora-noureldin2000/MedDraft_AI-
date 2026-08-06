import os
from pathlib import Path
from dataclasses import dataclass, field
import json

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

@dataclass
class Config:
    WORKSPACE_ROOT: Path = Path(__file__).parent.parent.parent.resolve()
    
    # Provider Mode: "simple" (single OpenAI-compatible API) or "dual" (DeepSeek + Qwen VL)
    LLM_PROVIDER: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "simple"))
    
    # --- Simple Single Provider Configuration ---
    SIMPLE_API_KEY: str = field(default_factory=lambda: os.getenv("SIMPLE_API_KEY", os.getenv("OPENAI_API_KEY", "")))
    SIMPLE_BASE_URL: str = field(default_factory=lambda: os.getenv("SIMPLE_BASE_URL", "https://api.openai.com/v1"))
    SIMPLE_MODEL: str = field(default_factory=lambda: os.getenv("SIMPLE_MODEL", "gpt-4o"))
    
    # --- Dual Provider Configuration ---
    MAIN_PROVIDER: str = field(default_factory=lambda: os.getenv("MAIN_PROVIDER", "opencode"))
    MAIN_MODEL: str = field(default_factory=lambda: os.getenv("MAIN_MODEL", "deepseek-v4-flash-free"))
    MAIN_BASE_URL: str = field(default_factory=lambda: os.getenv("MAIN_BASE_URL", "http://localhost:3284/v1"))
    
    VISION_PROVIDER: str = field(default_factory=lambda: os.getenv("VISION_PROVIDER", "ollama"))
    VISION_MODEL: str = field(default_factory=lambda: os.getenv("VISION_MODEL", "qwen2.5vl:3b"))
    VISION_BASE_URL: str = field(default_factory=lambda: os.getenv("VISION_BASE_URL", "http://localhost:11434"))
    VISION_ROUTING_ENABLED: bool = field(default_factory=lambda: os.getenv("VISION_ROUTING_ENABLED", "true").lower() == "true")
    
    # Token & Context Limits
    MAX_CONTEXT_TOKENS: int = 100000
    
    # Academic Database Integrations
    NCBI_API_KEY: str = field(default_factory=lambda: os.getenv("NCBI_API_KEY", ""))
    SCIENCEDIRECT_API_KEY: str = field(default_factory=lambda: os.getenv("SCIENCEDIRECT_API_KEY", ""))
    APIFY_TOKEN: str = field(default_factory=lambda: os.getenv("APIFY_TOKEN", ""))
    FINDPAPERS_EMAIL: str = field(default_factory=lambda: os.getenv("FINDPAPERS_EMAIL", ""))
    
    # Browser Engine Automation
    BROWSER_HEADLESS: bool = field(default_factory=lambda: os.getenv("BROWSER_HEADLESS", "false").lower() == "true")
    BROWSER_PROXY_SERVER: str = field(default_factory=lambda: os.getenv("PROXY_SERVER", ""))
    BROWSER_PROXY_USERNAME: str = field(default_factory=lambda: os.getenv("PROXY_USERNAME", ""))
    BROWSER_PROXY_PASSWORD: str = field(default_factory=lambda: os.getenv("PROXY_PASSWORD", ""))
    
    # Output Settings
    OUTPUT_DIR: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent.resolve() / "outputs")
    DEFAULT_OUTPUT_FORMAT: str = "both"  # md, docx, or both
    
    # Prompts & Skills Directory
    PROMPTS_DIR: Path = field(default_factory=lambda: Path(__file__).parent.parent.resolve() / "prompts")
    TEMPLATES_DIR: Path = field(default_factory=lambda: Path(__file__).parent.parent.resolve() / "templates")

def load_config() -> Config:
    config_file = Path(__file__).parent.parent.parent / "config.json"
    default_config = Config()
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, val in data.items():
                if hasattr(default_config, key):
                    if key in ("WORKSPACE_ROOT", "OUTPUT_DIR", "PROMPTS_DIR", "TEMPLATES_DIR"):
                        setattr(default_config, key, Path(val))
                    elif isinstance(getattr(default_config, key), bool):
                        setattr(default_config, key, bool(val))
                    else:
                        setattr(default_config, key, val)
        except Exception as e:
            print(f"⚠️ Error reading config.json: {e}. Using default config.")
    return default_config

_config_instance = None

def get_config() -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = load_config()
    return _config_instance
