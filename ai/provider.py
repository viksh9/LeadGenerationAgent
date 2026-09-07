"""AI provider abstraction (pluggable) + truthful status.

No provider is required: the deterministic reasoner is the always-available baseline.
When an OpenAI-compatible provider is configured (AI_API_KEY etc.), it produces the
narrative, which is then grounded-validated. CONNECTED is reported ONLY after a real
model request succeeds — never from configuration alone. Credentials come from the
environment and are never logged.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from ai.context import LeadIntelligenceContext
from ai.prompts import PROMPT_VERSION, build_system_prompt, build_user_prompt
from ai.schema import AIIntelligenceOutput
from config.settings import Settings, get_settings
from database.models import AIProviderStatus

logger = logging.getLogger("ai")
logging.getLogger("httpx").setLevel(logging.WARNING)


class AIProviderError(RuntimeError):
    """Base AI provider failure."""


class AIAuthError(AIProviderError):
    ...


class AIRateLimitError(AIProviderError):
    ...


class AIUnavailableError(AIProviderError):
    ...


class BaseAIProvider(ABC):
    name = "base"

    @abstractmethod
    def analyze(self, ctx: LeadIntelligenceContext) -> AIIntelligenceOutput: ...

    @abstractmethod
    def probe(self) -> AIProviderStatus:
        """Perform a minimal real request to verify connectivity."""


class OpenAICompatibleProvider(BaseAIProvider):
    """Any OpenAI-compatible /chat/completions endpoint (OpenAI, Azure, local, …)."""

    def __init__(self, settings: Settings, *, http: httpx.Client | None = None) -> None:
        self.settings = settings
        self.name = settings.ai_provider or "openai_compatible"
        self._http = http

    def _client(self) -> httpx.Client:
        return self._http or httpx.Client(timeout=self.settings.ai_timeout_seconds)

    def _post(self, messages: list[dict], *, max_tokens: int) -> dict:
        url = f"{self.settings.ai_api_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.ai_api_key}",
                   "Content-Type": "application/json"}
        body = {"model": self.settings.ai_model, "messages": messages,
                "temperature": self.settings.ai_temperature, "max_tokens": max_tokens,
                "response_format": {"type": "json_object"}}
        client = self._client()
        try:
            resp = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise AIUnavailableError(f"AI network error: {exc}") from exc
        finally:
            if self._http is None:
                client.close()
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (401, 403):
            raise AIAuthError(f"AI authentication failed (HTTP {resp.status_code}).")
        if resp.status_code == 429:
            raise AIRateLimitError("AI rate limit exceeded (HTTP 429).")
        raise AIUnavailableError(f"AI provider error (HTTP {resp.status_code}).")

    def analyze(self, ctx: LeadIntelligenceContext) -> AIIntelligenceOutput:
        messages = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(ctx)},
        ]
        data = self._post(messages, max_tokens=self.settings.ai_max_output_tokens)
        try:
            content = data["choices"][0]["message"]["content"]
            payload = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AIUnavailableError(f"AI returned malformed output: {exc}") from exc
        # Strict schema validation — reject anything that doesn't fit (§25).
        return AIIntelligenceOutput.model_validate(payload)

    def probe(self) -> AIProviderStatus:
        try:
            self._post([{"role": "user", "content": "Reply with {\"ok\":true} as JSON."}],
                       max_tokens=10)
        except AIAuthError:
            return AIProviderStatus.AUTHENTICATION_FAILED
        except AIRateLimitError:
            return AIProviderStatus.RATE_LIMITED
        except AIProviderError:
            return AIProviderStatus.ERROR
        return AIProviderStatus.CONNECTED


def build_provider(settings: Optional[Settings] = None) -> Optional[BaseAIProvider]:
    """Return a configured provider, or None when AI is not configured/disabled.

    None is the normal, honest state here — the caller falls back to the
    deterministic grounded baseline (never fabricates AI output)."""
    settings = settings or get_settings()
    if settings.ai_config_status != "CONFIGURED":
        return None
    return OpenAICompatibleProvider(settings)


def config_status(settings: Optional[Settings] = None) -> AIProviderStatus:
    """Config-level status (no network). CONNECTED requires a real probe()."""
    settings = settings or get_settings()
    return AIProviderStatus(settings.ai_config_status)
