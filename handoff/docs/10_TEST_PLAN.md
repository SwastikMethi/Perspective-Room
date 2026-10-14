# Verification and acceptance tests

Use deterministic mocks for repeatable engineering checks and small live smoke tests for provider compatibility. Do not write assertions that a stochastic model must produce one exact creative sentence. The goal is to verify orchestration, state, provenance, and behavior contracts.

## Required automated checks

| ID | Scenario | Required result |
| --- | --- | --- |
| T01 | Load personality configuration | Exactly eight unique IDs; all mandatory profile fields present; default selection valid. |
| T02 | Route an explicit target | Only the requested selected persona speaks even if Jev proposes another. |
| T03 | Route automatic speakers | No unselected or already-heard persona is executed; fallback is deterministic. |
| T04 | Independent Jev questions | Move questions include the named persona; no question relies on another same-call answer. |
| T05 | Malformed or unavailable Jev | Reject invalid options/probabilities; disclose fallback; preserve a useful generation path. |
| T06 | Bounded work | Auto ≤3 contributions, panel ≤8, repair ≤1 per turn, research ≤1 job, total attempts and deadlines enforced. |
| T07 | Submit the same idempotency key twice | One run and one logical user message; changed body with same key returns 409. |
| T08 | Two concurrent turns in one session | One accepted; the other conflicts without duplicate generations. |
| T09 | Stop during generation or research | No later contribution or provider call is started/published; completed earlier messages remain. |
| T10 | Lost SSE connection | Reconnect and replay produces each visible message once; no new provider call. |
| T11 | Worker restart during a run | Orphan is interrupted, committed messages survive, uncertain paid call is not automatically repeated. |
| T12 | Provider refusal or incomplete JSON | Safe visible failure/partial state; no fabricated success; bounded repair policy. |
| T13 | Fake or foreign citation ID | Reject or repair; never render it as a valid citation. |
| T14 | Research normalization invents a URL | Source map rejects it; valid evidence provenance remains intact. |
| T15 | Retrieved content contains instructions | It remains data; cannot alter profiles, allowed actions, tools, or server configuration. |
| T16 | A user changes a constraint | Next run uses the new brief; prior version remains; old memory cannot override it. |
| T17 | Fork through an earlier message | Later messages/conclusions excluded; all copied ID references remapped correctly. |
| T18 | Panel partial failure | Successful contributions publish; only missing work is offered for retry. |
| T19 | Summary | Exactly five sections, valid message/source references, disagreements retained in fixture. |
| T20 | Three experiment modes | A/B make no Jev calls; B/C use identical profiles; model/settings/evidence snapshots match. |
| T21 | Blind trial display | Mode/metrics/fallback metadata hidden; reveal marks subsequent ratings unblinded. |
| T22 | Evaluation size and cancellation | Oversized batch rejected; cancelling stops new trials and preserves completed results. |
| T23 | CSV and Markdown export | References remain usable; formula-leading CSV values escaped; secrets absent. |
| T24 | Local API security | Cross-site mutation rejected; only loopback app port published; keys absent from browser bundle. |
| T25 | Source and message deletion | Session-owned records removed consistently; active/evaluation-linked session policy enforced. |
| T26 | Sidebar toggle and theme | Collapsed/expanded states and dark/light preference survive navigation/refresh; menus/drawers follow theme with no first-paint flash. |
| T27 | Folder CRUD and safe removal | Unique normalized names, stale-version conflicts, member counts; deleting folder retains and unfiles active/archived chats atomically. |
| T28 | Chat organization during generation | Rename/pin/move never modify run context or content version; archive/delete are blocked until idle. |
| T29 | History and search | Literal wildcard-safe title/body search, query-scoped pagination, one hit per chat, archive filtering and valid deep links; zero model calls. |
| T30 | Per-chat drafts and navigation | Two different drafts survive switching and refresh; active run continues once; restored SSE never duplicates results. |
| T31 | Pin/archive/restore/delete | Counts and all lists reconcile; archive retains content; delete clears only affected local draft; evaluation sessions excluded. |
| T32 | Edit-and-branch first/later turn | Correct exclusive prefix, no later brief/memory, remapped controls, source unchanged, separate idempotent fork and send. |
| T33 | Regenerate versus retry | Completed round regenerates in a new branch; partial round retries missing work only; no silent successful-output overwrite. |
| T34 | Full eight-speaker and long content UI | Eight selectable identities and eight panel results; stable ordering, reflow, expansion and citation access without clipping. |
| T35 | Folder races and lost responses | Delete/move/create race cannot orphan records; stable operation keys recover one created folder/chat/branch after lost response. |

Use real PostgreSQL in integration tests for row locks, partial unique indexes, and transactions. SQLite substitution does not verify those guarantees. Use mock HTTP transports for Jev/OpenAI fixture contracts. Validate frontend generated types against the public OpenAPI document. Test both valid and invalid JSON relationships beyond the schema.

## Browser walkthrough

Run at 1440×900 and 1920×1080 in both sidebar states, 1024×768, and 390×844, with both dark and light themes. Create an idea, browse all eight profiles, start with three, read distinct replies, ask one person, request a full panel, inspect a source, pin two ideas, combine them, change a brief after completion, summarize, fork, export, and reopen after refresh. Test keyboard-only navigation, 200% zoom, and reduced motion. Verify that old transcript reading is not interrupted by forced auto-scroll.

Create a folder, rename it, create a chat inside, move another chat into it, expand/collapse it, and search by a phrase in message content. Pin, archive, search archived, restore, and remove the folder while preserving its chats. Use distinct drafts in two chats while one generation continues. Run eight selected personalities, expand a long sourced reply, and inspect a multi-turn transcript. Test edit-and-branch, regenerate a completed round, and retry an incomplete round. Verify titles, overflow menus, folder controls and composer remain usable at every target size.

Trigger provider error, research error, fallback, disconnect, Stop, and retry fixtures. Capture screenshots of real rendered states. Check contrast, overflow, readable citation controls, focus restoration, empty states, and mobile composer behavior. Correct a concrete UI failure before final delivery.

## Personality behavior probes

Run shared prompts with each profile and a follow-up that changes a key assumption. Human inspection should distinguish the profile's priorities, see appropriate updating, and find no fabricated credentials. Include cases where empathy requires disagreement and skepticism should acknowledge good evidence. The supplied examples are probes, not text to memorize.

## Live smoke test

When keys are configured, run a small provider connection check, one Jev-guided turn, one direct-person follow-up, one explicit research turn with a verifiable source, and one summary. Inspect actual usage/model IDs, citations, refusal/incomplete handling, and latency. Keep this distinct from a full effectiveness benchmark. If keys or account access are missing, finish mock-backed implementation and report the exact unverified integration; never label it as live-verified.

## Completion evidence

The implementation report must include commands actually executed, pass/fail counts, relevant screenshots, which adapters were live or mocked, and remaining defects. Tests must not be marked passed merely because their files exist. A completed implementation can have an inconclusive Jev experiment; engineering correctness and scientific effectiveness are separate outcomes.
