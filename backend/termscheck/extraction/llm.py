"""LLM client boundary. The extraction service depends only on the ExtractionLLM protocol, so
tests use a recorded client and the Anthropic client can be swapped or configured freely."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from .schema import ExtractedTerms


class ExtractionLLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    terms: ExtractedTerms
    model: str                       # model that actually served the request
    meta: dict[str, Any] = field(default_factory=dict)  # stop_reason, usage, ids, fallback info
    raw_json: dict[str, Any] = field(default_factory=dict)


class ExtractionLLM(Protocol):
    def extract(self, *, system: str, user: str, model: str, max_tokens: int) -> LLMResponse: ...


class AnthropicExtractionClient:
    """Structured-output extraction via the Anthropic Messages API (messages.parse)."""

    def __init__(self, client: Any | None = None, *, server_fallback: bool = True):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client
        self.server_fallback = server_fallback

    def extract(self, *, system: str, user: str, model: str, max_tokens: int) -> LLMResponse:
        import anthropic
        kwargs: dict[str, Any] = dict(model=model, max_tokens=max_tokens, system=system,
                                      messages=[{"role": "user", "content": user}],
                                      output_format=ExtractedTerms)
        try:
            if self.server_fallback:
                # On a policy decline, the API re-runs the request on a fallback model.
                resp = self.client.beta.messages.parse(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
            else:
                resp = self.client.messages.parse(**kwargs)
        except anthropic.RateLimitError as e:
            raise ExtractionLLMError(f"rate limited: {e}") from e
        except anthropic.APIStatusError as e:
            raise ExtractionLLMError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionLLMError(f"connection error: {e}") from e
        except (ValidationError, ValueError) as e:
            # parse() validates eagerly; refusals and truncated output fail here.
            raise ExtractionLLMError(f"model output did not match the extraction schema: {e}") from e

        meta = {"id": resp.id, "stop_reason": resp.stop_reason,
                "usage": resp.usage.model_dump() if resp.usage else None}
        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            raise ExtractionLLMError(f"model declined the request: {details}")
        if resp.stop_reason == "max_tokens":
            raise ExtractionLLMError("response truncated at max_tokens")
        parsed = resp.parsed_output
        if parsed is None:
            raise ExtractionLLMError("no structured output returned")
        return LLMResponse(parsed, resp.model, meta, json.loads(parsed.model_dump_json()))


class RecordedExtractionClient:
    """Returns a recorded model response (tests, demos without an API key)."""

    def __init__(self, recorded: dict[str, Any], model: str = "recorded"):
        self.recorded = recorded
        self.model = model
        self.calls: list[dict[str, Any]] = []

    def extract(self, *, system: str, user: str, model: str, max_tokens: int) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "model": model})
        terms = ExtractedTerms.model_validate(self.recorded)
        return LLMResponse(terms, self.model, {"stop_reason": "end_turn", "recorded": True},
                           json.loads(terms.model_dump_json()))
