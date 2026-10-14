"""Deterministic demo provider: clearly labeled fixtures, zero external calls (doc 12).

Output is built from the persona profile, the move and a hash of the focus — never the canned
`example` text. Demo-only test directives in the user's message (ignored in live mode):
  [[demo:delay=MS]] [[demo:fail=<persona|all>]] [[demo:refuse]] [[demo:incomplete]] [[demo:long]]
  [[demo:jev=malformed|down]] [[demo:research=fail|empty]] [[demo:research]]
"""

import asyncio
import hashlib
import json
import re
from typing import Any

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

DIRECTIVE = re.compile(r"\[\[demo:([a-z_]+)(?:=([^\]]*))?\]\]")

LENS = {
    "mentor": (
        "Start with a safe first step",
        "Who might feel discouraged at the start, and what would make a first try feel safe?",
        "notice who could feel left out or anxious and lower the stakes of the first attempt",
    ),
    "skeptic": (
        "Test the riskiest assumption first",
        "What observable result would show this is not working?",
        "name the assumption everything depends on and design a small test that could fail",
    ),
    "explorer": (
        "Try a different framing",
        "What if this worked like a shared ritual instead of a solo task?",
        "borrow a pattern from an unrelated field and connect it back to the goal",
    ),
    "strategist": (
        "Check who benefits and who pays",
        "Who would choose this over what they already use, and why?",
        "look at incentives, adoption and how the idea could sustain itself",
    ),
    "engineer": (
        "Build the smallest runnable test",
        "What single dependency must work for a first version?",
        "turn the idea into one dependency and a test you could run this week",
    ),
    "customer": (
        "Find the moment of friction",
        "Where would a first-time user hesitate or give up?",
        "walk through one concrete use and find where trust or effort breaks down",
    ),
    "civic": (
        "Make access part of the design",
        "Who could be left out, and how would they still take part?",
        "weigh broad access against what it takes to deliver reliably",
    ),
    "health": (
        "Keep well-being in view",
        "What evidence would show this helps rather than adds pressure?",
        "check the evidence and the human consequences without giving clinical advice",
    ),
}
MOVE_LEAD = {
    "explore": "One possibility:",
    "challenge": "Assumption to test:",
    "expand": "Developing this further:",
    "combine": "Connecting the ideas:",
    "clarify": "Before going further:",
}
DEMO_USAGE = Usage()  # no external call, no tokens to report


def directives(text: str) -> dict[str, str]:
    return {k: v or "" for k, v in DIRECTIVE.findall(text or "")}


def clean(text: str) -> str:
    return DIRECTIVE.sub("", text or "").strip()


def _pick(seed: str, options: list[str]) -> str:
    return options[int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(options)]


def _short(text: str, n: int = 90) -> str:
    text = " ".join(clean(text).split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _payload(input_items: list[dict[str, Any]]) -> dict[str, Any]:
    for item in reversed(input_items):
        for part in item.get("content", []):
            try:
                data = json.loads(part.get("text", ""))
            except (TypeError, ValueError):
                continue
            if isinstance(data, dict):
                return data
    return {}


class DemoGeneration:
    name = "demo"

    def __init__(self, fixture_packs: dict[str, dict[str, Any]] | None = None) -> None:
        self.fixture_packs = fixture_packs or {}

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
        p = _payload(input_items)
        d = directives(p.get("latest_user_message", ""))
        persona = (p.get("profile") or {}).get("id")
        if "delay" in d:
            await asyncio.sleep(int(d["delay"] or 0) / 1000)
        if "fail" in d and d["fail"] in ("all", persona) and schema_name == "contribution":
            raise ProviderFailure("provider_error", "Demo failure requested for this reply.")
        if "refuse" in d and schema_name == "contribution":
            return Refused("Demo refusal requested.", "demo", None, DEMO_USAGE)
        if "incomplete" in d and schema_name == "contribution":
            return Incomplete("max_output_tokens", "demo", None, DEMO_USAGE)
        build = {
            "intake": self._intake,
            "contribution": self._contribution,
            "summary": self._summary,
            "memory": self._memory,
            "research": self._research,
        }[schema_name]
        return Structured(build(p, d), "demo", None, DEMO_USAGE)

    def _intake(self, p: dict[str, Any], d: dict[str, str]) -> dict[str, Any]:
        msg = clean(p.get("latest_user_message", "")) or clean(p.get("brief", {}).get("idea", ""))
        words = re.sub(r"[^\w\s-]", "", msg).split()
        title = " ".join(words[:6]).capitalize() or "Brainstorm"
        focus = re.split(r"(?<=[.?!])\s", msg, maxsplit=1)[0][:200] or "Explore the idea"
        wants = "research" in d or re.search(
            r"\b(current|existing|latest|evidence|study|studies|research)\b", msg, re.I
        )
        query = _short(msg, 120) if wants else None
        if query and d.get("research"):  # keep demo research directives on the query
            query += f" [[demo:research={d['research']}]]"
        return {
            "title_suggestion": title,
            "focus": focus,
            "intent": "summarize" if "summar" in msg.lower() else "brainstorm",
            "clarifying_question": "Who is the main person you want this to help?"
            if "clarify" in d
            else None,
            "research_query": query,
            "research_reason": "The question depends on current external facts." if wants else None,
            "open_questions": [f"What would make this worth returning to: {_short(focus, 60)}"],
        }

    def _contribution(self, p: dict[str, Any], d: dict[str, str]) -> dict[str, Any]:
        profile = p.get("profile") or {}
        pid = profile.get("id") or "assistant"
        move = p.get("move") or "explore"
        focus = _short(p.get("focus") or p.get("latest_user_message", ""), 80)
        if pid not in LENS:  # Standard mode: one neutral assistant
            blocks: list[dict[str, Any]] = [
                {
                    "kind": "suggestion",
                    "source_ids": [],
                    "text": f"For “{focus}”, start with the smallest version you can try with "
                    "a few people, then decide what to change based on what they actually do.",
                },
                {
                    "kind": "assumption",
                    "source_ids": [],
                    "text": "This assumes the people involved have time for a short first trial.",
                },
                {
                    "kind": "question",
                    "source_ids": [],
                    "text": "What would count as a clear sign that the first version helped?",
                },
            ]
            return {
                "headline": "A practical way to begin",
                "blocks": blocks,
                "referenced_message_ids": [],
                "new_angle": "A neutral starting plan.",
                "next_question": None,
            }
        headline, question, habit = LENS[pid]
        lead = MOVE_LEAD.get(move, MOVE_LEAD["explore"])
        seed = f"{pid}|{move}|{focus}"
        tail = _pick(seed, ["for the first week", "with five real people", "before building more"])
        blocks = [
            {
                "kind": "assumption" if move == "challenge" else "suggestion",
                "source_ids": [],
                "text": f"{lead} for “{focus}”, {habit} — {tail}.",
            },
        ]
        evidence = p.get("evidence") or []
        if evidence and pid in ("skeptic", "engineer", "strategist", "health"):
            ev = evidence[0]
            blocks.append(
                {
                    "kind": "fact",
                    "source_ids": [ev["source_id"]],
                    "text": f"The supplied evidence reports: {ev['statement']}",
                }
            )
        if "long" in d:
            for i in range(4):
                blocks.append(
                    {
                        "kind": "observation",
                        "source_ids": [],
                        "text": (
                            f"Point {i + 1}: {habit.capitalize()}. Keep notes on what "
                            "people actually do, not what they say they will do, and revisit "
                            "the plan once the first results arrive so the next step builds on "
                            "evidence rather than hope. "
                            "https://example.org/a-very-long-unbroken-reference-" + "x" * 120
                        ),
                    }
                )
        if move != "clarify":
            blocks.append({"kind": "question", "source_ids": [], "text": question})
        return {
            "headline": headline if move != "clarify" else "One question first",
            "blocks": blocks,
            "referenced_message_ids": [],
            "new_angle": f"{profile.get('display_name', pid)}: a {move} angle on "
            f"{(profile.get('priorities') or ['the idea'])[0]}.",
            "next_question": None,
        }

    def _summary(self, p: dict[str, Any], d: dict[str, str]) -> dict[str, Any]:
        msgs = [m for m in p.get("recent_messages", []) if m.get("role") != "user"]

        def item(text: str, ids: list[str], sources: list[str] | None = None) -> dict[str, Any]:
            return {"text": text, "source_message_ids": ids, "source_ids": sources or []}

        directions = [
            item(m.get("headline") or _short(m.get("text", "")), [m["id"]], m.get("source_ids"))
            for m in msgs[:3]
        ]
        skeptic = [m for m in msgs if m.get("persona_id") == "skeptic"]
        none = "No item was established in this conversation."
        return {
            "sections": [
                {"kind": "directions", "items": directions or [item(none, [])]},
                {
                    "kind": "disagreements",
                    "items": [
                        item(
                            f"The skeptic questioned: {skeptic[0].get('headline', '')}",
                            [skeptic[0]["id"]],
                        )
                    ]
                    if skeptic
                    else [item(none, [])],
                },
                {"kind": "assumptions", "items": [item(none, [])]},
                {
                    "kind": "questions",
                    "items": [
                        item(
                            "Which of these directions would people actually return to?",
                            [m["id"] for m in msgs[:1]],
                        )
                    ]
                    if msgs
                    else [item(none, [])],
                },
                {
                    "kind": "experiments",
                    "items": [
                        item(
                            "Run a one-week pilot with five people and record whether they "
                            "come back.",
                            [m["id"] for m in msgs[:2]],
                        )
                    ]
                    if msgs
                    else [item(none, [])],
                },
            ]
        }

    def _memory(self, p: dict[str, Any], d: dict[str, str]) -> dict[str, Any]:
        msgs = [m for m in p.get("recent_messages", []) if m.get("role") != "user"]
        return {
            "overview": f"The conversation explores: {_short(p.get('focus') or '', 120)}",
            "ideas": [
                {
                    "text": m.get("headline") or _short(m.get("text", "")),
                    "source_message_ids": [m["id"]],
                    "source_ids": [],
                }
                for m in msgs[:5]
            ],
            "open_questions": [],
            "assumptions": [],
        }

    def _research(self, p: dict[str, Any], d: dict[str, str]) -> dict[str, Any]:
        source_map = p.get("source_map") or {}
        text = p.get("research_text") or ""
        findings = (
            [
                {
                    "statement": _short(text, 200),
                    "source_ids": [sid],
                    "qualification": "Synthetic demo evidence; not a real study.",
                }
                for sid in list(source_map)[:1]
            ]
            if text
            else []
        )
        return {
            "query": p.get("query") or "",
            "findings": findings,
            "unknowns": ["Whether this generalizes beyond the demo fixture."],
        }

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
        d = directives(query)
        if d.get("research") == "fail":
            raise ProviderFailure("provider_error", "Demo research failure requested.")
        pack = next(iter(self.fixture_packs.values()), None)
        if d.get("research") == "empty" or pack is None:
            return ResearchRaw("No sources were found.", [], [], None, "demo", DEMO_USAGE, 0)
        text = " ".join(f["statement"] for f in pack["normalized"]["findings"])
        citations = [
            Citation(url=s["url"], title=s["title"], start=0, end=len(text))
            for s in pack["sources"]
        ]
        return ResearchRaw(
            text, citations, [c.url for c in citations], "demo-research", "demo", DEMO_USAGE, 1
        )


class DemoCoordinator:
    """Deterministic stand-in for Jev with valid typed answers."""

    name = "demo"

    async def ask(
        self, state: dict[str, Any], questions: dict[str, Any], model: str | None = None
    ) -> dict[str, Any]:
        d = directives(str(state.get("latest_user_message", "")))
        if d.get("jev") == "down":
            raise ProviderFailure(
                "transient", "Demo coordinator outage requested.", retryable=False
            )
        answers: dict[str, Any] = {}
        for qid, q in questions.items():
            if q["type"] == "choice":
                options = list(q["criteria"])
                pick = self._choose(qid, options, state)
                if d.get("jev") == "malformed":
                    pick = "persona_that_does_not_exist"
                n = len(options)
                probs = {o: (0.8 if o == pick else 0.2 / max(n - 1, 1)) for o in options}
                conf = (0.8 - 1 / n) / (1 - 1 / n) if n > 1 else 1.0
                answers[qid] = {
                    "type": "choice",
                    "choice": pick,
                    "probabilities": probs,
                    "confidence": conf,
                }
            else:
                answers[qid] = {
                    "type": "score",
                    "score": 1.9,
                    "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                    "probabilities": {"0": 0.0, "1": 0.1, "2": 0.9},
                    "confidence": 0.85,
                }
        return {"model": "demo", "answers": answers, "usage": {}}

    @staticmethod
    def _choose(qid: str, options: list[str], state: dict[str, Any]) -> str:
        heard = set(state.get("already_heard") or [])
        if qid == "next_speaker":
            fresh = [o for o in options if o != "return_user" and o not in heard]
            return fresh[0] if fresh else "return_user"
        if qid == "research_needed":
            return "needed" if state.get("research_query") else "not_needed"
        if qid.startswith("move_"):
            return "explore" if not heard else ("challenge" if len(heard) == 1 else "expand")
        return options[0]
