# Decisions and source notes

Specification date: 14 October 2026. The design choices below belong to this project. Provider facts were checked against official sources; availability in a particular account remains unverified until a live test.

## Architecture decisions

| Decision | Rationale and consequence |
| --- | --- |
| Eight curated profiles | Gives a useful variety without requiring a persona-authoring product. Profiles are configuration, not eight services. |
| One generation model initially | Makes persona differences attributable to instructions and coordination; model changes do not confound the primary experiment. |
| Jev remains the coordinator | It is the intervention being studied. Deterministic fallback is explicit and measured. |
| Local monolith with PostgreSQL | Supports durable jobs, transactional publication, and reproducible evaluation with two containers. |
| Explicit public context | Prevents accidental persona mixing through provider-managed sessions and keeps provenance under application control. |
| Buffered, validated publication | Avoids showing a draft that a later check retracts; progress is still visible. |
| On-demand shared research | Gives current evidence when useful while keeping brainstorming responsive and source attribution inspectable. |
| Independent initial panel views | Reduces immediate copying before participants begin building on public contributions. |
| No forced consensus | Disagreements and conditions can be more useful than one synthetic final verdict. |
| Three experiment arms | Separates the value of multiple perspectives from the added Jev supervision package. |
| No dollar cap by default | Reflects the user's updated budget instruction; operational ceilings remain. |
| Approved cartoon design | The user selected the eight-character interface, with matching dark and light themes. Dark is the initial default; visual density remains restrained. |
| Expandable chat sidebar | Multiple chats and openable single-level folders are core requirements. Collapsed rail preserves workspace area; expanded sidebar exposes history and management. |
| Separate organization version | Renaming, pinning or moving a chat can coexist with generation without invalidating its immutable input. |
| History-preserving edits | Editing a sent user message or regenerating a round creates a branch; published history and evidence remain intact. |

## Verified provider references

1. [TypeSafe introduction](https://docs.typesafe.ai/introduction): Jev returns typed decisions; independent questions share state. This supports atomic decision design rather than dialogue generation.
2. [TypeSafe API reference](https://docs.typesafe.ai/api): HTTP endpoint, bearer authentication, request/answer envelopes, typed question shapes, and errors. The application uses a small HTTPX adapter rather than depending on an unverified SDK wrapper.
3. [Choice](https://docs.typesafe.ai/primitives/choice): fixed options return a choice, probabilities, and confidence. Question IDs are not model-visible, so persona context belongs in instructions.
4. [Score](https://docs.typesafe.ai/primitives/score): ordered rubric levels produce a weighted score, which can be fractional. Do not cast it to an integer or confuse it with measured quality.
5. [Confidence](https://docs.typesafe.ai/confidence): confidence is computed from the distribution; thresholds require use-case testing. The supplied thresholds are experimental defaults.
6. [TypeSafe models](https://docs.typesafe.ai/models): the documented version is `jev-1.13.0`; inputs are text; request and per-question context limits apply. The package uses bounded text state and a pinned Jev version.
7. [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses): Responses supports strict schema-oriented output. Validate refusal/incomplete responses and semantic relationships in application code.
8. [OpenAI streaming](https://developers.openai.com/api/docs/guides/streaming-responses): response streaming uses typed events. The application independently persists its own run events for reconnection.
9. [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search): use the current `web_search` tool; citation annotations identify sources. Display citations clearly and clickably. This motivates a provenance-preserving source map.
10. [OpenAI Responses create reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create): verify exact current request fields and SDK types when implementing; do not assume examples from another API surface are interchangeable.
11. [GPT-6.1 Sol model](https://developers.openai.com/api/docs/models/gpt-6.1-sol): documents Responses, structured output, streaming, and web-search support for the configured default identifier. Account authorization and runtime availability are separate checks.
12. [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data): application storage controls and provider retention are different. `store=false` is not a blanket zero-retention guarantee.
13. [Node.js releases](https://nodejs.org/en/about/previous-releases): reference for selecting and checking the supported Node runtime during implementation.

## UI references and user decisions

The user approved the final cartoon dark/light designs on 14 October 2026 and then requested an expandable sidebar for chats and folders. The packaged approved PNGs govern the visual direction; the expanded-sidebar image is a supporting illustration of the new navigation requirement. The previous light-only room SVG/PNG is superseded and removed.

Earlier design research informed the direction: [Linear interface refresh](https://linear.app/now/behind-the-latest-design-refresh) for quieter navigation and hierarchy; [Cosmos](https://www.cosmos.so/) for visual curation; [Milanote brainstorming](https://milanote.com/product/brainstorming) for organizing thoughts. These are design inspirations, not UI libraries or additional runtime dependencies.

## Inferences and limitations

The claim that eight perspectives plus Jev will improve brainstorming is a hypothesis, not a sourced fact or measured result. The personality examples, workload limits, UI design, thresholds, and implementation architecture are project proposals. The synthetic fixtures are authored test data. No live Jev/OpenAI calls, user study, app benchmark, or implementation test has been performed by this documentation package.

The user's chosen execution agent is Opus 5.5. That name identifies the intended coding assistant, not an application API dependency or a verified model-access claim. The runtime application uses the independently configured OpenAI and TypeSafe endpoints.

## Decisions the implementer may make

Choose exact compatible dependency patches, icon primitives, internal module names, and minor visual details while preserving the contracts. Record a provider API adaptation if official behavior changes. Product expansion, account systems, public deployment, additional external vendors, and unbounded autonomous debate require a separate scope change. Do not silently replace required features with mock-only implementations.
