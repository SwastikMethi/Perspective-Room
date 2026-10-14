"""OpenAI Responses adapter against a mock HTTP transport (T12, Review Focus 1)."""

import json
import logging

import httpx2 as httpx  # the openai SDK's HTTP stack
import pytest

from app.providers.base import Incomplete, ProviderFailure, Refused, Structured
from app.providers.openai_adapter import OpenAIGeneration

KEY = "sk-test-not-a-real-key-123"
SCHEMA = {
    "type": "object",
    "properties": {"headline": {"type": "string"}},
    "required": ["headline"],
    "additionalProperties": False,
}


def response(output, status="completed", incomplete=None, usage=True):
    body = {
        "id": "resp_123",
        "object": "response",
        "created_at": 0,
        "status": status,
        "model": "gpt-6.1-sol-2026-09-01",
        "output": output,
        "incomplete_details": incomplete,
    }
    if usage:
        body["usage"] = {
            "input_tokens": 120,
            "output_tokens": 40,
            "total_tokens": 160,
            "input_tokens_details": {"cached_tokens": 8},
            "output_tokens_details": {"reasoning_tokens": 25},
        }
    return body


def message(*parts):
    return {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "status": "completed",
        "content": list(parts),
    }


def text_part(text, annotations=()):
    return {"type": "output_text", "text": text, "annotations": list(annotations)}


class Recorder:
    def __init__(self, status=200, body=None, headers=None):
        self.status, self.body, self.headers = status, body, headers or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body, headers=self.headers)

    def json(self, i=0):
        return json.loads(self.requests[i].content)


def adapter(rec: Recorder) -> OpenAIGeneration:
    return OpenAIGeneration(KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(rec)))


async def structured(gen, effort=None):
    return await gen.structured(
        purpose="draft",
        instructions="You are one simulated perspective.",
        input_items=[
            {"role": "user", "content": [{"type": "input_text", "text": "SECRET PROMPT TEXT"}]}
        ],
        schema_name="contribution",
        schema=SCHEMA,
        max_output_tokens=4096,
        model="gpt-6.1-sol",
        reasoning_effort=effort,
    )


async def test_structured_output_is_parsed_and_request_is_strict_and_unstored():
    reasoning = {"type": "reasoning", "id": "rs_1", "summary": []}
    rec = Recorder(body=response([reasoning, message(text_part('{"headline": "Start small"}'))]))
    result = await structured(adapter(rec))
    assert isinstance(result, Structured) and result.data == {"headline": "Start small"}
    assert (result.model, result.response_id) == ("gpt-6.1-sol-2026-09-01", "resp_123")
    u = result.usage
    assert (u.input_tokens, u.output_tokens, u.reasoning_tokens, u.cached_tokens) == (
        120,
        40,
        25,
        8,
    )
    body = rec.json()
    assert body["store"] is False and body["model"] == "gpt-6.1-sol"
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "contribution",
        "schema": SCHEMA,
        "strict": True,
    }
    assert "temperature" not in body and "reasoning" not in body
    assert body["max_output_tokens"] == 4096
    assert rec.requests[0].url.path.endswith("/responses")


async def test_reasoning_effort_is_sent_only_when_configured():
    rec = Recorder(body=response([message(text_part('{"headline": "x"}'))]))
    await structured(adapter(rec), effort="low")
    assert rec.json()["reasoning"] == {"effort": "low"}


async def test_refusal_is_a_distinct_outcome():
    rec = Recorder(body=response([message({"type": "refusal", "refusal": "I can't help."})]))
    result = await structured(adapter(rec))
    assert isinstance(result, Refused) and result.message == "I can't help."


async def test_incomplete_max_output_tokens_is_a_distinct_outcome():
    rec = Recorder(
        body=response([], status="incomplete", incomplete={"reason": "max_output_tokens"})
    )
    result = await structured(adapter(rec))
    assert isinstance(result, Incomplete) and result.reason == "max_output_tokens"


async def test_invalid_json_text_is_incomplete_not_success():
    rec = Recorder(body=response([message(text_part('{"headline": "unterminated'))]))
    assert isinstance(await structured(adapter(rec)), Incomplete)


async def test_invalid_key_is_one_request_and_provider_not_ready():
    rec = Recorder(
        status=401,
        body={"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}},
    )
    with pytest.raises(ProviderFailure) as err:
        await structured(adapter(rec))
    assert err.value.code == "provider_not_ready" and not err.value.retryable
    assert len(rec.requests) == 1  # SDK retries are disabled: one policy only


async def test_unknown_model_is_model_unavailable():
    rec = Recorder(
        status=404,
        body={"error": {"code": "model_not_found", "message": "The model does not exist"}},
    )
    with pytest.raises(ProviderFailure) as err:
        await structured(adapter(rec))
    assert err.value.code == "model_unavailable"


async def test_rate_limit_is_retryable_with_the_provider_hint():
    rec = Recorder(
        status=429,
        body={"error": {"message": "slow down"}},
        headers={"retry-after": "2", "x-request-id": "req_9"},
    )
    with pytest.raises(ProviderFailure) as err:
        await structured(adapter(rec))
    assert err.value.retryable and err.value.retry_after == 2.0
    assert err.value.request_id == "req_9"


async def test_web_research_uses_hosted_search_and_keeps_citations():
    text = "Peer mock interviews improved confidence in a 2025 pilot."
    citation = {
        "type": "url_citation",
        "url": "https://example.edu/pilot",
        "title": "Pilot",
        "start_index": 0,
        "end_index": len(text),
    }
    search = {
        "type": "web_search_call",
        "id": "ws_1",
        "status": "completed",
        "action": {
            "type": "search",
            "query": "peer mock interviews",
            "sources": [
                {"type": "url", "url": "https://example.edu/pilot"},
                {"type": "url", "url": "https://other.example/x"},
            ],
        },
    }
    rec = Recorder(body=response([search, message(text_part(text, [citation]))]))
    raw = await adapter(rec).web_research(
        query="peer mock interview evidence",
        instructions="Research.",
        max_tool_calls=3,
        max_output_tokens=6144,
        model="gpt-6.1-sol",
        reasoning_effort=None,
    )
    body = rec.json()
    assert body["tools"] == [{"type": "web_search"}] and body["tool_choice"] == "required"
    assert body["max_tool_calls"] == 3 and body["store"] is False
    assert "web_search_call.action.sources" in body["include"]
    assert raw.text == text and raw.tool_calls == 1
    assert [(c.url, c.title, c.start, c.end) for c in raw.citations] == [
        ("https://example.edu/pilot", "Pilot", 0, len(text))
    ]
    assert raw.action_sources == ["https://example.edu/pilot", "https://other.example/x"]


async def test_logs_never_contain_the_key_or_prompt(caplog):
    caplog.set_level(logging.DEBUG)
    rec = Recorder(body=response([message(text_part('{"headline": "x"}'))]))
    await structured(adapter(rec))
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert KEY not in logged and "SECRET PROMPT TEXT" not in logged
    assert "Bearer" not in logged


async def test_connect_error_before_send_is_retryable_and_not_billed():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    gen = OpenAIGeneration(
        KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    )
    with pytest.raises(ProviderFailure) as err:
        await structured(gen)
    assert err.value.code == "transient" and err.value.retryable
    assert err.value.usage_unknown is False
