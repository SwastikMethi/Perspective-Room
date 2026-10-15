"""OpenAI Responses adapter (doc 06 §OpenAI integration, verified against openai 3.31).

Strict JSON-schema outputs, `store=False`, explicit context per call, no temperature, reasoning
effort only when configured. Output items are inspected by type; refusal and incomplete results
are distinct outcomes. SDK retries are off: `providers.calls` owns the single retry policy.
"""

import json
from typing import Any

import httpx2  # the openai SDK's HTTP stack (a fork of httpx with distinct classes)
import openai
from openai import AsyncOpenAI

from app.providers.base import (
    Citation,
    GenerationResult,
    Incomplete,
    ProviderFailure,
    Refused,
    ResearchRaw,
    Structured,
    Usage,
)
from app.providers.calls import classify_http


def _usage(resp: Any) -> Usage:
    u = getattr(resp, "usage", None)
    if u is None:
        return Usage()
    out_details = getattr(u, "output_tokens_details", None)
    in_details = getattr(u, "input_tokens_details", None)
    return Usage(
        input_tokens=u.input_tokens,
        output_tokens=u.output_tokens,
        reasoning_tokens=getattr(out_details, "reasoning_tokens", None),
        cached_tokens=getattr(in_details, "cached_tokens", None),
    )


def _retry_after(headers: httpx2.Headers) -> str | None:
    if ms := headers.get("retry-after-ms"):
        try:
            return str(float(ms) / 1000)
        except ValueError:
            return None
    return headers.get("retry-after")


DEFAULT_BASE_URL = "https://api.openai.com/v1"  # regional projects set OPENAI_BASE_URL instead


class OpenAIGeneration:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        http_client: httpx2.AsyncClient | None = None,
        base_url: str | None = None,
    ) -> None:
        self.client = AsyncOpenAI(
            api_key=api_key,
            # Explicit, so an empty OPENAI_BASE_URL in the environment can never reach the SDK.
            base_url=base_url or DEFAULT_BASE_URL,
            max_retries=0,
            timeout=httpx2.Timeout(300.0, connect=10.0),  # per-purpose deadlines are enforced above
            http_client=http_client,
        )

    async def _create(self, **kwargs: Any) -> Any:
        try:
            return await self.client.responses.create(**kwargs)
        except openai.APITimeoutError as e:
            raise ProviderFailure(
                "timeout", "OpenAI did not answer in time; outcome unknown.", usage_unknown=True
            ) from e
        except openai.APIConnectionError as e:
            before_send = isinstance(e.__cause__, httpx2.ConnectError)
            raise ProviderFailure(
                "transient" if before_send else "provider_error",
                "Could not reach OpenAI." if before_send else "Connection to OpenAI was lost.",
                retryable=before_send,
                usage_unknown=not before_send,
            ) from e
        except openai.APIStatusError as e:
            raise classify_http(
                e.status_code,
                e.response.text,
                retry_after=_retry_after(e.response.headers),
                request_id=e.response.headers.get("x-request-id"),
            ) from e

    async def structured(
        self,
        *,
        purpose: str,
        instructions: str,
        input_items: list[dict[str, Any]],
        schema_name: str,
        schema: dict[str, Any],
        max_output_tokens: int,
        model: str,
        reasoning_effort: str | None,
    ) -> GenerationResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input_items,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
            "store": False,
            "max_output_tokens": max_output_tokens,
        }
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}
        resp = await self._create(**kwargs)
        usage, rid, resp_model = _usage(resp), resp.id, resp.model
        req = getattr(resp, "_request_id", None)
        texts: list[str] = []
        for item in resp.output or []:
            if getattr(item, "type", None) != "message":
                continue  # reasoning and other items are not the answer
            for part in item.content or []:
                if part.type == "refusal":
                    return Refused(part.refusal, resp_model, rid, usage, req)
                if part.type == "output_text":
                    texts.append(part.text)
        if resp.status == "incomplete":
            reason = getattr(resp.incomplete_details, "reason", None) or "unknown"
            return Incomplete(reason, resp_model, rid, usage, req)
        if resp.status != "completed" or not texts:
            raise ProviderFailure("provider_error", f"OpenAI returned status {resp.status}.")
        try:
            data = json.loads("".join(texts))
        except ValueError:
            return Incomplete("invalid_json", resp_model, rid, usage, req)
        if not isinstance(data, dict):
            return Incomplete("invalid_json", resp_model, rid, usage, req)
        return Structured(data, resp_model, rid, usage, req)

    async def web_research(
        self,
        *,
        query: str,
        instructions: str,
        max_tool_calls: int,
        max_output_tokens: int,
        model: str,
        reasoning_effort: str | None,
    ) -> ResearchRaw:
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": query,
            "tools": [{"type": "web_search"}],
            "tool_choice": "required",
            "max_tool_calls": max_tool_calls,
            "include": ["web_search_call.action.sources"],
            "store": False,
            "max_output_tokens": max_output_tokens,
        }
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}
        resp = await self._create(**kwargs)
        text_parts: list[str] = []
        citations: list[Citation] = []
        sources: list[str] = []
        tool_calls = 0
        offset = 0
        for item in resp.output or []:
            kind = getattr(item, "type", None)
            if kind == "web_search_call":
                tool_calls += 1
                for src in getattr(getattr(item, "action", None), "sources", None) or []:
                    url = getattr(src, "url", None)
                    if url and url not in sources:
                        sources.append(url)
            elif kind == "message":
                for part in item.content or []:
                    if part.type != "output_text":
                        continue
                    for a in part.annotations or []:
                        if getattr(a, "type", None) == "url_citation":
                            citations.append(
                                Citation(
                                    a.url,
                                    a.title or a.url,
                                    offset + a.start_index,
                                    offset + a.end_index,
                                )
                            )
                    text_parts.append(part.text)
                    offset += len(part.text)
        return ResearchRaw(
            "".join(text_parts),
            citations,
            sources,
            resp.id,
            resp.model,
            _usage(resp),
            tool_calls,
            getattr(resp, "_request_id", None),
        )

    async def check(self, model: str) -> None:
        """Explicit connection check: verifies the key and model access without generation."""
        try:
            await self.client.models.retrieve(model)
        except openai.APIStatusError as e:
            raise classify_http(e.status_code, e.response.text or "model") from e
        except openai.APIConnectionError as e:
            raise ProviderFailure("transient", "Could not reach OpenAI.") from e
