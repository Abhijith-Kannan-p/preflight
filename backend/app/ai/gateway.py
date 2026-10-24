"""Provider-agnostic LLM gateway.

Every call: mask -> provider (Gemini / Groq) with timeout -> one retry -> JSON parse ->
Pydantic validation -> unmask. Failures return None so callers fall back to deterministic
logic. Repeated failures open a circuit breaker that switches to deterministic-only mode
for a cool-down period. Every call is recorded for the "AI used in this review" panel.
"""

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.masking import Masker
from app.config import Settings, get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
BREAKER_THRESHOLD = 3
BREAKER_COOLDOWN_SECONDS = 60.0


class ProviderError(RuntimeError):
    pass


@dataclass
class Completion:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None


class Provider(Protocol):
    name: str
    model: str

    async def complete(self, prompt: str, timeout: float) -> Completion: ...


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, api_key: str) -> None:
        self.model, self._key = model, api_key

    async def complete(self, prompt: str, timeout: float) -> Completion:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                GEMINI_URL.format(model=self.model),
                headers={"x-goog-api-key": self._key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.2,
                    },
                },  # fmt: skip
            )
        if response.status_code != 200:
            raise ProviderError(f"gemini HTTP {response.status_code}")
        body = response.json()
        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise ProviderError("gemini returned no text") from exc
        usage = body.get("usageMetadata", {})
        return Completion(text, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))


class GroqProvider:
    name = "groq"

    def __init__(self, model: str, api_key: str) -> None:
        self.model, self._key = model, api_key

    async def complete(self, prompt: str, timeout: float) -> Completion:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
            )
        if response.status_code != 200:
            raise ProviderError(f"groq HTTP {response.status_code}")
        body = response.json()
        usage = body.get("usage", {})
        return Completion(
            body["choices"][0]["message"]["content"],
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )


class CircuitBreaker:
    def __init__(self, threshold: int = BREAKER_THRESHOLD,
                 cooldown: float = BREAKER_COOLDOWN_SECONDS) -> None:  # fmt: skip
        self.threshold, self.cooldown = threshold, cooldown
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at >= self.cooldown:
                self._opened_at, self._failures = None, 0  # half-open: try again
                return False
            return True

    def record(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self._failures = 0
                return
            self._failures += 1
            if self._failures >= self.threshold:
                self._opened_at = time.monotonic()


@dataclass
class AiCallRecord:
    purpose: str
    provider: str
    model: str
    latency_ms: int
    ok: bool
    masked: bool
    masked_count: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    error: str | None = None


@dataclass
class CallLog:
    """Collects the AI calls made during one review."""

    calls: list[AiCallRecord] = field(default_factory=list)

    def add(self, record: AiCallRecord) -> None:
        self.calls.append(record)


class Gateway:
    def __init__(self, provider: Provider | None, timeout: float,
                 breaker: CircuitBreaker | None = None) -> None:  # fmt: skip
        self.provider = provider
        self.timeout = timeout
        self.breaker = breaker or CircuitBreaker()

    @property
    def available(self) -> bool:
        return self.provider is not None and not self.breaker.open

    @property
    def mode(self) -> str:
        if self.provider is None:
            return "deterministic"
        return "degraded" if self.breaker.open else "llm"

    async def complete_json(
        self,
        prompt: str,
        schema: type[T],
        *,
        purpose: str,
        masker: Masker,
        log_to: CallLog | None = None,
    ) -> T | None:
        if self.provider is None or self.breaker.open:
            return None
        masked_prompt = masker.mask(prompt)
        started = time.perf_counter()
        error: str | None = None
        completion: Completion | None = None
        result: T | None = None
        for attempt in range(2):  # one retry
            try:
                completion = await asyncio.wait_for(
                    self.provider.complete(masked_prompt, self.timeout), self.timeout + 1
                )
                result = schema.model_validate(_unmask_json(json.loads(completion.text), masker))
                error = None
                break
            except (httpx.HTTPError, ProviderError, TimeoutError, json.JSONDecodeError,
                    ValidationError, KeyError) as exc:  # fmt: skip
                error = f"{type(exc).__name__}: {str(exc)[:120]}"
                log.warning("LLM %s attempt %d failed: %s", purpose, attempt + 1, error)
        self.breaker.record(result is not None)
        if log_to is not None:
            log_to.add(
                AiCallRecord(
                    purpose=purpose,
                    provider=self.provider.name,
                    model=self.provider.model,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    ok=result is not None,
                    masked=masker.enabled,
                    masked_count=masker.masked_count,
                    tokens_in=completion.tokens_in if completion else None,
                    tokens_out=completion.tokens_out if completion else None,
                    error=error,
                )
            )
        return result


def _unmask_json(value: Any, masker: Masker) -> Any:
    if isinstance(value, str):
        return masker.unmask(value)
    if isinstance(value, list):
        return [_unmask_json(v, masker) for v in value]
    if isinstance(value, dict):
        return {k: _unmask_json(v, masker) for k, v in value.items()}
    return value


def build_provider(settings: Settings) -> Provider | None:
    if settings.llm_provider == "none" or not settings.llm_api_key:
        return None
    if settings.llm_provider == "gemini":
        return GeminiProvider(settings.llm_model, settings.llm_api_key)
    return GroqProvider(settings.llm_model, settings.llm_api_key)


_gateway: Gateway | None = None


def get_gateway() -> Gateway:
    global _gateway
    if _gateway is None:
        settings = get_settings()
        _gateway = Gateway(build_provider(settings), settings.llm_timeout_seconds)
    return _gateway


def set_gateway(gateway: Gateway | None) -> None:
    """Override the shared gateway (used by tests)."""
    global _gateway
    _gateway = gateway
