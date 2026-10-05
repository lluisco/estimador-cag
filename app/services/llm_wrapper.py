from dataclasses import dataclass
from typing import Iterator
import time

import structlog
from litellm import Router
from pydantic import BaseModel

import instructor

log = structlog.get_logger()

def _strip_provider_prefix(model: str) -> str:
    return model.split("/", 1)[1] if "/" in model else model

def _provider_from_model(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    name = model.lower()
    if name.startswith("openai") or name.startswith("gpt"):
        return "openai"
    if name.startswith("anthropic") or name.startswith("claude"):
        return "anthropic"
    return "unknown"

@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    latency_ms: int

@dataclass
class LLMStructuredResponse:
    parsed: BaseModel
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    finish_reason: str
    latency_ms: int

class LLMWrapper:
    MODEL_GROUP = "estimator"

    def __init__(
        self,
        *,
        primary_model: str,
        fallback_model: str,
        open_api_key: str,
        anthropic_api_key: str,
        timeout: int,
        num_retries: int,
    ):
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.timeout = timeout
        self.num_retries = num_retries
        self.credentials = {
            "openai": open_api_key,
            "anthropic": anthropic_api_key,
        }

        self.router = Router(
            model_list=[
                self._deployment(primary_model),
                self._deployment(fallback_model),
            ],
            num_retries=num_retries,
        )

        self._instructor = instructor.from_litellm(self.router.completion)

    def _deployment(self, model: str) -> dict:
        provider = _provider_from_model(model)
        return {
            "model_name": self.MODEL_GROUP,
            "litellm_params": {
                "model": model,
                "api_key": self.credentials.get(provider),
                "timeout": self.timeout,
            }
        }

    def complete(self, *, system_prompt: str, user_message: str, max_tokens: int = 2000) -> LLMResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        log.info("llm_call_started", model=self.primary_model)
        t0 = time.perf_counter()
        try:
            response = self.router.completion(
                model=self.MODEL_GROUP,
                messages=messages,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log.error(
                "llm_call_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
                latency_ms=latency_ms,
            )
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)

        choice = response.choices[0]
        usage = response.usage
        raw_model = response.model
        provider = _provider_from_model(raw_model)
        model = _strip_provider_prefix(raw_model)

        log.info(
            "llm_call_completed",
            model=model,
            provider=provider,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            latency_ms=latency_ms,
            finish_reason=(choice.finish_reason or "stop").lower(),
        )

        return LLMResponse(
            text=choice.message.content or "",
            model=model,
            provider=provider,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            finish_reason=(choice.finish_reason or "stop").lower(),
            latency_ms=latency_ms,
        )

    def complete_structured(
        self, *, system_prompt: str, user_message: str, response_model: type[BaseModel],
        max_tokens: int = 2000, max_retries: int = 2,
    ) -> LLMStructuredResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        log.info("llm_call_started", model=self.primary_model, structured=True)
        t0 = time.perf_counter()
        try:
            parsed, raw = self._instructor.create_with_completion(
                model=self.MODEL_GROUP,
                messages=messages,
                max_tokens=max_tokens,
                response_model=response_model,
                max_retries=max_retries,
            )
        except Exception as exc:
            log.error("llm_call_failed", error_type=type(exc).__name__,
                error=str(exc)[:200], latency_ms=int((time.perf_counter() - t0) * 1000))
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)

        raw_model = raw.model
        finish_reason = (raw.choices[0].finish_reason or "stop").lower()
        # `raw.usage` es de la última llamada. Si hubo reintentos de validación, no suma los anteriores.
        log.info(
            "llm_call_completed",
            model=_strip_provider_prefix(raw_model),
            provider=_provider_from_model(raw_model),
            input_tokens=raw.usage.prompt_tokens,
            output_tokens=raw.usage.completion_tokens,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            structured=True,
        )
        return LLMStructuredResponse(
            parsed=parsed,
            model=_strip_provider_prefix(raw_model),
            provider=_provider_from_model(raw_model),
            input_tokens=raw.usage.prompt_tokens,
            output_tokens=raw.usage.completion_tokens,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
        )


    def complete_stream(
        self, *, system_prompt: str, messages: list[dict], max_tokens: int, metadata
    ) -> Iterator[str]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]

        log.info("llm_stream_started", model=self.primary_model)
        t0 = time.perf_counter()
        try:
            response = self.router.completion(
                model=self.MODEL_GROUP,
                messages=full_messages,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as exc:
            log.error(
                "llm_stream_failed_to_start",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            raise

        model = None
        finish_reason = None
        usage = None
        for chunk in response:
            if model is None:
                model = _strip_provider_prefix(chunk.model)
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason

        metadata.model = model or self.primary_model
        metadata.provider = _provider_from_model(metadata.model)
        metadata.truncated = finish_reason == "length"
        metadata.input_tokens = usage.prompt_tokens if usage else 0
        metadata.output_tokens = usage.completion_tokens if usage else 0

        log.info(
            "llm_stream_completed",
            model=metadata.model,
            provider=metadata.provider,
            input_tokens=metadata.input_tokens,
            output_tokens=metadata.output_tokens,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            truncated=metadata.truncated,
        )
