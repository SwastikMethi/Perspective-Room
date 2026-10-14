# Execution prompt for Opus 5.5

You are implementing Perspective Room from the complete `handoff/` specification. Build the application, run meaningful checks, fix failures, and deliver a working local project in this coding run. A plan alone is not the deliverable.

Read `handoff/START_HERE.md`, all numbered specifications, configuration, contracts, fixtures, and the acceptance checklist before implementation. Open and inspect the four image references in `handoff/ui/` before building the interface, and read their asset guidance. Preserve the confirmed decisions. Work through document 11's checkpoints without waiting for approval between routine implementation steps.

## Required result

A mature local brainstorming app with eight distinct personalities; Jev coordination; OpenAI generation; on-demand sourced research; natural group and targeted conversation; saved ideas; evolving idea brief; session persistence/forks/exports; expandable chat navigation, searchable history and folders; matching light/dark cartoon themes; summaries that preserve disagreements; and a usable three-arm Experiment Lab. Build every P0 requirement. Use one FastAPI process serving the built React app plus PostgreSQL through Docker Compose. No login or public hosting is required.

Implement real provider adapters and a clearly labeled deterministic demo provider. Missing credentials must not prevent building and testing the full local app. They must prevent claims that live integration was verified. Do not substitute demo output for a live-provider error.

## Execution rules

1. Inspect the repository and preserve unrelated work. If empty, create the layout specified in the TRD. Install compatible dependencies and commit lockfiles to the deliverable; verify actual SDK methods before using them.
2. Convert the supplied schemas into validated backend models and generated frontend types. Keep one authoritative public API schema and check it against the supplied contract. Do not create conflicting duplicate types.
3. Implement the vertical slice early: create session, submit turn, execute provider adapter, validate contribution, persist result, and receive reconnectable SSE events.
4. Implement all personalities from configuration, not eight separate hardcoded agents. Give each its own profile while maintaining a shared, attributed public conversation.
5. Follow the Jev protocol exactly: independent typed questions, code-enforced eligibility and limits, validated answers, explicit fallback. Do not ask Jev to generate dialogue or invent free-form reasoning on its behalf.
6. Preserve research provenance through display and export. Never fabricate citations or translate provider citations into unsupported claims.
7. Reproduce the approved cartoon art direction in `ui/approved-room-dark.png` and `ui/approved-room-light.png`. Dark is default and Light/Dark is a working persistent switch. The eight-character selector is intentional. Use compact avatars, short first-view cards, and restrained background doodles; preserve full replies through expansion/transcript views. Build the 64px collapsed rail and 272px expandable sidebar with chat history, folders, search and complete management actions from documents 03 and 14. Do not revert to the superseded white three-column UI or leave the sidebar as a visual stub. The UI references are inspiration for real React components, never a full-screen background standing in for the app.
8. Exercise cancellation, refresh/reconnect, duplicate submission, provider failure, restart recovery, folder CRUD, chat search, per-chat drafts, theme persistence, and navigation during an active run. The app must never accidentally rerun a paid generation on refresh or replay.
9. Implement comparison modes and ratings without prefilled performance claims. Keep providers/model settings fixed for matched comparisons and report missing trials and fallbacks.
10. Run the tests and UI walkthrough in the test plan. Fix concrete failures before finishing. Use mock tests for routine checks and a small live smoke test only when credentials are already available. Do not run a large paid benchmark automatically.
11. Keep secrets server-side and out of logs, browser bundles, screenshots, and git. Use loopback port publishing. Do not deploy externally, publish, or push repository changes unless separately instructed.
12. If an optional cosmetic detail is unspecified, make a consistent choice and continue. Ask only for an actual blocker that cannot be resolved from the docs. Record reasonable choices in `IMPLEMENTATION_NOTES.md`.

## Finish criteria

Complete `handoff/ACCEPTANCE_CHECKLIST.md` with evidence. Supply `.env.example`, `docker-compose.yml`, migrations, seed loading, lockfiles, mock fixtures, meaningful tests, and a root README with exact commands. Add `IMPLEMENTATION_REPORT.md` describing delivered behavior, test results, verified live integrations, known limitations, and unverified items. Do not mark a mocked check as live success. Include actual-app screenshots for both themes, collapsed and expanded sidebar, all-eight panel replies, a long conversation, a folder view, search, and mobile navigation.

In your final response, state how to start the app, where to set keys, what was tested, and any real blocker. Continue through all internal milestones rather than stopping after scaffolding or one successful screen.
