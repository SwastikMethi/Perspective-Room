# One-run implementation plan

The following are checkpoints within one continuous implementation, not separate releases or requests for approval. All P0 requirements remain in scope. The agent should advance through them, fix failures, and deliver the complete local project.

## 1. Read, settle, and scaffold

Read the full handoff and inspect the repository. Record the stack and confirmed scope. Create the backend/frontend structure, dependency lockfiles, Docker Compose, environment template, formatting/type-check commands, and root README. Load profiles/defaults and validate configuration. Implement migrations including folders and chat organization fields, and an initial health endpoint. Establish semantic theme tokens, the light/dark switch and sidebar shell immediately. Verify the database and built SPA can start together.

Checkpoint: a fresh checkout can build, migrate, and render the application shell without API keys. Missing credentials are represented honestly.

## 2. Build the durable conversation slice

Implement sessions, messages, run records, idempotency, one-active-run constraints, worker claiming, SSE replay, Stop, and startup recovery. Add a deterministic provider adapter with controlled delayed/error outputs. Build the start screen and room with real API data. A message must travel end-to-end through persistence and events.

Checkpoint: create a room, receive a mock contribution, refresh/reconnect, submit duplicate requests, and cancel a delayed run without duplicate or late messages.

## 3. Add the eight personalities and live providers

Load complete profile definitions and version snapshots. Implement explicit targeting, panel mode, auto eligibility, move overrides, intake, generation, deterministic validation, and memory. Add the OpenAI Responses adapter and Jev typed-decision adapter with contract fixtures. Follow document 05 for independent questions and fallback. Implement the repair ceiling and provider-attempt accounting.

Checkpoint: all eight profiles can speak through the same generation adapter; user targeting wins; malformed Jev answers cannot select arbitrary actions; A/B modes make no Jev calls.

## 4. Complete research and idea development

Implement the separate search/normalization pipeline, source records, citations, uncertainty, and failure handling. Add the working brief editor, saved ideas, Combine, summary, session fork, and Markdown/JSON exports. Resolve citation-ID and lineage mapping before styling the source drawer.

Checkpoint: a source survives retrieval → normalization → contribution → summary/export; an invalid source cannot be displayed as verified. A fork contains only its selected history.

## 5. Complete the interface and chat workspace

Match both approved cartoon references and the expanded-sidebar companion. Implement all eight portraits, compact turn cards with expansion, catalog, participant controls, message actions, and an on-demand source/idea/brief drawer. Build folders, chat search, rename/pin/move/archive/restore/delete/export, branch/edit/regenerate actions, separate drafts, theme/sidebar persistence, and active-run navigation using document 14. Use accessible menus/dialogs and keyboard flows. Check the sidebar at collapsed and expanded widths and at mobile breakpoints; reflow the main workspace rather than shrinking text. Ensure no orphan buttons, placeholder routes, fake metrics, or unfinished required screens.

Checkpoint: the complete journey works in both themes on desktop and mobile. Open a folder, move a chat, search its content, preserve drafts when switching, return to an active run, and restore an archived chat. All eight participants remain accessible; long replies and eight-response rounds remain usable.

## 6. Build the Experiment Lab

Load the 30 authored cases and exact condition definitions. Implement bounded trial scheduling, immutable model/profile/evidence snapshots, anonymized labels, rating persistence/reveal tracking, comparisons, uncertainty-aware reporting, and CSV/JSON export. Use mock trials to verify mechanics. No live benchmark starts without the explicit Run action.

Checkpoint: run a small mock matched set; conditions are correctly isolated; Standard has no persona-consistency score; missing/degraded trials remain visible; no results are fabricated.

## 7. Verify and finish

Run relevant unit, contract, PostgreSQL integration, browser, and security checks. Exercise the test plan's failure cases. If credentials are available, run only the small live smoke set. Fix actual failures. Produce screenshots, implementation notes, and the evidence-based implementation report. Complete the acceptance checklist and README commands.

Checkpoint: the user can start the local app, configure keys, brainstorm with any selected personalities, inspect sources, save/revisit ideas, and run a controlled comparison.

## Handling practical blockers

Missing provider credentials do not prevent implementation or mock tests. A real unavailable model requires a clearly recorded configuration decision; do not silently upgrade one experiment arm. If dependency/API behavior differs from the handoff, consult current official documentation, update the adapter and affected contract, and record the exact change. Ask the user only when a material product choice or unavailable external access genuinely prevents completion.

## Required final repository deliverables

- Working application code and locked dependencies.
- Docker Compose and repeatable migrations/seed loading.
- Backend-only `.env.example` and setup README.
- API and generated frontend contracts consistent with the supplied design.
- Versioned profiles/prompts, deterministic demo mode, benchmark fixtures.
- Meaningful automated tests and an actual UI walkthrough.
- `IMPLEMENTATION_NOTES.md`, `IMPLEMENTATION_REPORT.md`, and completed acceptance checklist.

Do not replace implementation with a plan, stop after scaffolding, or create empty stubs for P0 functionality.
