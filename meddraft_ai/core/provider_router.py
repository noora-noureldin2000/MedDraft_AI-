import logging
from typing import Dict, Any, Optional
from meddraft_ai.core.config import get_config

logger = logging.getLogger(__name__)

class ProviderRouter:
    """
    Router for dual-provider (DeepSeek text + Qwen 2.5 VL vision) and simple provider modes.
    """
    def __init__(self):
        self.config = get_config()

    def is_vision_task(self, image_path: Optional[str] = None) -> bool:
        """A task is visual only when an actual image accompanies it.

        Prompt keywords are not enough: a text request that merely mentions a
        figure has no pixels to inspect, and routing it to the local vision
        model would produce an image-less request.
        """
        return bool(image_path)

    def route(self, prompt: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        if self.config.LLM_PROVIDER.lower() == "dual" and self.config.VISION_ROUTING_ENABLED:
            if self.is_vision_task(image_path):
                return {
                    "provider": self.config.VISION_PROVIDER,
                    "model": self.config.VISION_MODEL,
                    "base_url": self.config.VISION_BASE_URL,
                    "is_vision": True
                }
            return {
                "provider": self.config.MAIN_PROVIDER,
                "model": self.config.MAIN_MODEL,
                "base_url": self.config.MAIN_BASE_URL,
                "is_vision": False
            }
        else:
            return {
                "provider": "openai_compatible",
                "api_key": self.config.SIMPLE_API_KEY,
                "model": self.config.SIMPLE_MODEL,
                "base_url": self.config.SIMPLE_BASE_URL,
                "is_vision": False
            }
