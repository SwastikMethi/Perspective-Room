"""Replaceable provider interfaces (OpenAI, Jev, deterministic demo) and their result types."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None


@dataclass
class Structured:
    data: dict[str, Any]
    model: str
    response_id: str | None
    usage: Usage = field(default_factory=Usage)
    request_id: str | None = None  # the provider's request ID, kept for local diagnosis


@dataclass
class Refused:
    message: str
    model: str
    response_id: str | None
    usage: Usage = field(default_factory=Usage)
    request_id: str | None = None  # the provider's request ID, kept for local diagnosis


@dataclass
class Incomplete:
    reason: str
    model: str
    response_id: str | None
    usage: Usage = field(default_factory=Usage)
    request_id: str | None = None  # the provider's request ID, kept for local diagnosis


GenerationResult = Structured | Refused | Incomplete


@dataclass
class Citation:
    url: str
    title: str
    start: int
    end: int


@dataclass
class ResearchRaw:
    text: str
    citations: list[Citation]
    action_sources: list[str]
    response_id: str | None
    model: str
    usage: Usage = field(default_factory=Usage)
    tool_calls: int | None = None
    request_id: str | None = None


class ProviderFailure(Exception):
    """A provider call failed. `code` is safe to show; `retryable` follows the G17 policy."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after: float | None = None,
        usage_unknown: bool = False,
        status: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message = code, message
        self.retryable, self.retry_after = retryable, retry_after
        self.usage_unknown, self.status, self.request_id = usage_unknown, status, request_id


class GenerationProvider(Protocol):
    name: str

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
    ) -> GenerationResult: ...

    async def web_research(
        self,
        *,
        query: str,
        instructions: str,
        max_tool_calls: int,
        max_output_tokens: int,
        model: str,
        reasoning_effort: str | None,
    ) -> ResearchRaw: ...


class Coordinator(Protocol):
    name: str

    async def ask(
        self, state: dict[str, Any], questions: dict[str, Any], model: str | None = None
    ) -> dict[str, Any]:
        """Raw Jev envelope: {"model": str, "answers": {qid: answer}, "usage": {...}}."""
        ...
