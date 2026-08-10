import os
import json
import logging
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout

from meddraft_ai.core.config import get_config
from meddraft_ai.core.provider_router import ProviderRouter

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Unified LLM Client supporting both single OpenAI-compatible provider mode and dual-provider routing.
    """

    def __init__(self):
        self.config = get_config()
        self.router = ProviderRouter()

    # Retry only on transient network failures: connection errors, timeouts, HTTP 429/5xx.
    # Auth errors (401/403) and bad requests (400) are NOT retried — they will always fail.
    @retry(
        retry=retry_if_exception_type((RequestsConnectionError, Timeout, requests.exceptions.HTTPError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def query(self, system_prompt: str, user_prompt: str, image_path: Optional[str] = None) -> str:
        route_info = self.router.route(user_prompt, image_path)
        
        # Dual-provider: Vision via Ollama
        if route_info.get("is_vision") and route_info.get("provider") == "ollama":
            return self._query_ollama_vision(system_prompt, user_prompt, image_path, route_info)
        
        # Simple or Dual Text via OpenAI-compatible endpoint
        return self._query_openai_compatible(system_prompt, user_prompt, route_info)

    def _query_openai_compatible(self, system_prompt: str, user_prompt: str, route_info: Dict[str, Any]) -> str:
        base_url = route_info.get("base_url") or self.config.SIMPLE_BASE_URL
        api_key = route_info.get("api_key") or self.config.SIMPLE_API_KEY or os.getenv("OPENAI_API_KEY", "")
        model = route_info.get("model") or self.config.SIMPLE_MODEL
        temperature = self.config.LLM_TEMPERATURE

        # Raise early rather than using a dummy key that produces confusing API errors
        if not api_key:
            raise ValueError(
                "No API key configured. Set SIMPLE_API_KEY (or OPENAI_API_KEY) in your .env file."
            )

        # Try using standard OpenAI Python SDK if installed
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url if base_url else None)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature
            )
            return response.choices[0].message.content or ""
        except (RequestsConnectionError, Timeout) as e:
            # Only fall back on transient network errors, not auth/payload errors
            logger.warning("OpenAI SDK call failed with transient error: %s. Falling back to direct HTTP.", e)

        # HTTP Fallback
        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }

        resp = requests.post(endpoint, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _query_ollama_vision(self, system_prompt: str, user_prompt: str, image_path: Optional[str], route_info: Dict[str, Any]) -> str:
        import base64
        base_url = route_info.get("base_url", "http://localhost:11434")
        model = route_info.get("model", "qwen2.5vl:3b")

        images = []
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                images.append(base64.b64encode(f.read()).decode("utf-8"))

        endpoint = f"{base_url.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "system": system_prompt,
            "prompt": user_prompt,
            "images": images,
            "stream": False
        }

        resp = requests.post(endpoint, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
