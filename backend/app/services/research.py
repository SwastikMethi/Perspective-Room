"""Research provenance (doc 07): sources come only from provider citation annotations, are
HTTP(S)-only, deduplicated by an exact normalized URL, and get server-assigned IDs."""

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from app.persistence.models import ResearchPack, Source
from app.providers.base import ResearchRaw
from app.services.common import utcnow
from app.workers.context import RunContext

EXCERPT_CHARS = 600
TRACKING_PARAMS = {"fbclid", "gclid"}


def normalize_url(url: str) -> str | None:
    """Lower-case scheme/host, drop the fragment and only known tracking parameters. Returns
    None for anything that is not an absolute HTTP(S) URL."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not (k.lower().startswith("utm_") or k.lower() in TRACKING_PARAMS)
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            urlencode(query, doseq=True),
            "",
        )
    )


def _excerpt(text: str, start: int, end: int) -> str:
    start, end = max(0, start), min(len(text), max(end, start))
    span = text[start:end].strip() or text[:EXCERPT_CHARS]
    return span[:EXCERPT_CHARS]


async def store_research(
    ctx: RunContext, query: str, raw: ResearchRaw, *, status: str | None = None
) -> tuple[UUID, list[Source]]:
    """Persist the citation-bearing answer and one source per distinct cited URL."""
    now = utcnow()
    by_url: dict[str, dict[str, Any]] = {}
    for c in raw.citations:
        url = normalize_url(c.url)
        if url is None:
            continue
        entry = by_url.setdefault(
            url,
            {
                "url": c.url.strip(),
                "title": c.title or url,
                "citations": [],
                "excerpt": _excerpt(raw.text, c.start, c.end),
            },
        )
        entry["citations"].append(
            {"start_index": c.start, "end_index": c.end, "title": c.title, "url": c.url}
        )
    async with ctx.sessionmaker() as s, s.begin():
        pack = ResearchPack(
            session_id=ctx.session_id,
            run_id=ctx.run_id,
            query=query,
            status=status or ("available" if by_url else "empty"),
            raw_answer={
                "text": raw.text,
                "action_sources": raw.action_sources,
                "tool_calls": raw.tool_calls,
                "model": raw.model,
            },
            provider_response_id=raw.response_id,
            is_fixture=raw.model == "demo",
            created_at=now,
        )
        s.add(pack)
        await s.flush()
        sources = []
        for url, e in by_url.items():
            src = Source(
                session_id=ctx.session_id,
                research_pack_id=pack.id,
                url=e["url"],
                title=e["title"][:300],
                domain=urlsplit(url).netloc,
                retrieved_at=now,
                published_at=None,
                provider_response_id=raw.response_id or "",
                provider_citation=e["citations"],
                research_excerpt=e["excerpt"],
                is_fixture=raw.model == "demo",
                created_at=now,
            )
            s.add(src)
            sources.append(src)
        await s.flush()
        return pack.id, sources


async def store_failed_research(ctx: RunContext, query: str, reason: str) -> UUID:
    async with ctx.sessionmaker() as s, s.begin():
        pack = ResearchPack(
            session_id=ctx.session_id,
            run_id=ctx.run_id,
            query=query,
            status="failed",
            raw_answer={"error": reason},
            created_at=utcnow(),
        )
        s.add(pack)
        await s.flush()
        return pack.id


async def save_normalized(
    ctx: RunContext, pack_id: UUID, normalized: dict[str, Any], status: str
) -> None:
    async with ctx.sessionmaker() as s, s.begin():
        pack = await s.get(ResearchPack, pack_id)
        assert pack is not None
        pack.normalized = normalized
        pack.unknowns = list(normalized.get("unknowns", []))
        pack.status = status
