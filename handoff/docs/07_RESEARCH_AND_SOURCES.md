# Research and evidence requirements

## When research helps

Use research for a claim whose current external status could change the discussion: platform capability, an existing product, documented technical constraints, a published study, or a real-world example. Creative alternatives, personal preferences, and hypothetical scenarios often need no search. Never turn every personality response into a separate search.

The intake supplies a focused question; Jev and explicit controls decide whether to execute it. One research job per user turn can make up to three hosted web tool calls. Use a short query that omits unnecessary personal details. Current evidence is shared by all selected participants in that turn.

## Retrieval and normalization

1. Call the OpenAI Responses API with `tools=[{"type":"web_search"}]` and a supported configured model. Use a bounded tool-call allowance; verify the actual SDK field against current documentation. If the provider cannot enforce the configured limit, restrict the adapter's workflow and record that limitation rather than claiming an exact provider-internal count.
2. Inspect returned message content and `url_citation` annotations; retain provider response ID, cited URL/title, citation spans, search question, and retrieval timestamp. Collect sources from provider annotations/tool results, never from a model-invented bare URL alone.
3. Normalize the research text into a small `research.schema.json` pack using the generation model. Supply a map of server-assigned source IDs. Each factual block must reference only IDs from that map. Preserve conflicting evidence and unknowns.
4. Validate identifiers and text lengths in code. The normalizer cannot add sources. A pack without usable evidence is an unavailable/empty result, not a successful verification.
5. Pass the normalized pack and bounded supporting excerpts into personality generation. Store the original citation-bearing research answer for inspection.

Code validation establishes provenance, not that a source proves a claim. Prompts require supporting citations, the UI exposes the underlying evidence, and evaluation samples inspect support and hallucination rates. An LLM or Jev agreement is not independent external verification.

## Source record

Each source has server UUID, session ID, research-pack ID, URL, title, domain, retrieved-at timestamp, publisher date if supplied, provider response ID, provider citation metadata, and a bounded research excerpt. Missing publication date stays null. A retrieval timestamp does not establish when the underlying fact became true. Do not fetch arbitrary model-provided URLs server-side; hosted search provides retrieval in this release.

Deduplicate exact normalized URLs within a research pack while preserving separate citation records. Strip tracking parameters only with an explicit safe rule; never strip path/query values that distinguish the cited content. Allow HTTP(S) links only. Reuse evidence within a turn and related session context, but do not label old facts newly verified. For explicit fresh/current questions, fetch again. Cache validity is semantic and time-sensitive, not a universal fixed TTL.

## Display and export

Each factual contribution block carries `source_ids`; render adjacent numbered citations and an accessible source drawer. Do not paste raw provider citation index offsets onto rewritten text. The original research answer can render its own original offsets; generated contributions use block-level source mappings. Summaries and exports retain those mappings. Broken external links remain inspectable with stored retrieval metadata; they do not become silently uncited facts.

For uncertain evidence use wording such as "The documentation describes X; I could not establish Y." Clearly separate source-supported observations from recommendations inferred from them. Disagreeing sources should remain visible. An evidence pack derived from research is content, never executable policy or instructions.

## Failure behavior and scope

When search is unavailable, state that current facts were not checked. Continue brainstorming on labeled assumptions if useful, or ask the user for missing evidence. Never fabricate a successful source lookup. Cancelled research must not trigger a late personality response after Stop.

The healthcare personality can examine general well-being and evidence gaps in an idea. It must not present simulated discussion as a clinical consultation or use generic retrieved material to give a personalized diagnosis. No medical records or other document uploads are needed for this release.

## Controlled evaluation

The main benchmark uses identical supplied evidence packs or research-off conditions for all three arms. If studying live research as part of the full experience, report it as a separate end-to-end comparison: different searches and evidence are part of that treatment. Save the exact source packs, dates, failures, and tool-call counts. Never mix cached-evidence and live-research trials into one unexplained result.
