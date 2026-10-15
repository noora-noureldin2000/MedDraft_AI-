import os
import json
import logging
from typing import Dict, Any, Optional, Type, TypeVar
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout

from meddraft_ai.core.config import get_config
from meddraft_ai.core.provider_router import ProviderRouter

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class LLMClient:
    """
    Unified LLM Client supporting both single OpenAI-compatible provider mode and dual-provider routing.
    """

    def __init__(self):
        self.config = get_config()
        self.router = ProviderRouter()
        # Compatibility shims for screening modules expecting these attributes
        self.api_type = self.config.LLM_PROVIDER or "openai_compatible"
        self.model_name = self.config.SIMPLE_MODEL or self.config.MAIN_MODEL or "gpt-4o-mini"

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

    def query_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        temperature: float = 0.0,
    ) -> T:
        """Queries LLM and returns validated Pydantic model with automatic fallback."""
        route_info = self.router.route(user_prompt)
        base_url = route_info.get("base_url") or self.config.SIMPLE_BASE_URL
        api_key = route_info.get("api_key") or self.config.SIMPLE_API_KEY or os.getenv("OPENAI_API_KEY", "")
        model = route_info.get("model") or self.config.SIMPLE_MODEL

        if not api_key:
            raise ValueError("No API key configured. Set SIMPLE_API_KEY (or OPENAI_API_KEY) in your .env file.")

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url if base_url else None)
            completion = client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_model,
                temperature=temperature,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is not None:
                return parsed
        except Exception as exc:
            logger.debug("Native structured parse failed (%s); trying JSON schema prompt fallback.", exc)

        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        augmented_prompt = (
            f"{user_prompt}\n\n"
            f"You MUST return ONLY valid JSON matching this schema exactly:\n"
            f"```json\n{schema_json}\n```"
        )
        raw_text = self._query_openai_compatible(system_prompt, augmented_prompt, route_info)
        cleaned = self._clean_json_markdown(raw_text)
        return response_model.model_validate_json(cleaned)

    @staticmethod
    def _clean_json_markdown(text: str) -> str:
        """Strip markdown fences from LLM responses."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.lstrip("`").strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
            cleaned = cleaned.rstrip("`").strip()
        return cleaned

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

    def run_parallel_screening(self, tasks: list[tuple[str, str, bool]], max_workers: int = 5) -> list[str]:
        """Parallel wrapper for screener modules. Executes query() concurrently."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[str | None] = [None] * len(tasks)

        def _call(idx: int, sys_p: str, usr_p: str) -> tuple[int, str]:
            try:
                out = self.query(sys_p, usr_p)
                return idx, out
            except Exception as e:
                logger.error(f"LLM screening task {idx} failed: {e}")
                return idx, f'{{\"verdict\": \"UNSURE\", \"reason\": \"LLM error: {e}\"}}'

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for idx, task in enumerate(tasks):
                # tasks are (system_prompt, user_prompt, bool) - bool is unused
                sys_p, usr_p = task[0], task[1]
                futures[executor.submit(_call, idx, sys_p, usr_p)] = idx

            for fut in as_completed(futures):
                idx, out = fut.result()
                results[idx] = out

        # Ensure no None remains
        return [r if r is not None else '{"verdict": "UNSURE", "reason": "No response"}' for r in results]
