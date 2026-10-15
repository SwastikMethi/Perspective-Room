# Implementation notes

What was decided while building Perspective Room, beyond what the specification states. The
specification ([`handoff/`](handoff/START_HERE.md)) remains the authority; these notes record how
each gap was closed, every judgment call made during implementation (with what it would cost if it
were wrong), the fixes made after each independent checkpoint review, and the SDK adaptations.

Evidence for each claim (commands, counts, screenshots) is in
[IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md).

## 1. Specification gaps and how they were resolved (G1–G26)

| # | Gap | Resolution |
|---|---|---|
| G1 | Contract names only `reveal_required` | 400 `bad_request` (malformed/conflicting params, bad cursor); 404 `not_found`; 409 `version_conflict` (details `current_version` / `current_organization_version`), `idempotency_conflict`, `run_active` (details `active_run_id`), `session_archived`, `evaluation_managed`, `folder_name_taken`, `folder_missing`, `retry_not_allowed`, `regenerate_requires_completed`, `unresolvable_reference`, `model_unavailable`, `invalid_cursor`, `reveal_required`; 422 `validation_error`, `context_too_large`, `batch_too_large`, `target_not_selected`, `consistency_not_applicable`; 503 `provider_not_ready`, `database_unavailable`. Security-layer responses not declared in the contract: 403 `cross_site_rejected`, 415 `json_required`, 500 `internal_error` (sanitized). FastAPI `{"detail"}` bodies replaced by `Error` + `request_id` everywhere. |
| G2 | `Run.stage`, warnings, `RunEvent.data` untyped; SSE end | Stages `queued, preparing, intake, routing, researching, drafting, validating, assessing, repairing, publishing, memory, cancelling, finished`. Warnings `coordination_fallback`*, `coordination_unavailable`*, `audit_unavailable`*, `quality_warning`*, `repair_used`*, `research_unavailable`, `research_empty`, `research_findings_dropped`, `memory_unavailable`, `contribution_failed`, `deadline_exceeded`, `usage_unknown`, `demo_mode`, `budget_cap_unenforced` (* = mode-revealing, stripped from blinded projections). Event data: `run.queued/started {status, stage, session_version, audience, slots[]}`; `run.stage {stage, persona_id?, status_key}`; `research.completed {research_pack_id, source_ids, availability}`; `message.completed {message, session_version}`; `run.warning {code, text, degraded}`; terminal `{run, missing_persona_ids}`. Stream is always 200: replay, tail, close after a terminal event (live or replayed); client closes on terminal. |
| G3 | No API to choose demo mode | Global `APP_PROVIDER_MODE=demo` + restart; missing-key screens show setup guidance and that explicit option; never auto-substitute. |
| G4 | Health `degraded` vs 503 | `GET /health` always 200 with `status/database/worker`; writes return 503 `database_unavailable` when the DB is down. |
| G5 | Missing keys at Send | Live + no OpenAI key → `createSession`/`createTurn` 503 `provider_not_ready` (no empty chat). No Jev key → Jev-guided turns use labeled fixed-order fallback (`coordination_unavailable`); a live Lab batch including `jev_guided` is refused 503. |
| G6 | Fixed-panel move cycle; n < k | `k' = min(k, n)` (auto `requested_count` = `min(auto_contributions, n)` in B and C). B round `t`, contribution `j`: speaker `selected[(t·k' + j) mod n]`, move `[explore, challenge, expand][(t + j) mod 3]`. C fallback stays doc 05. |
| G7 | "needed above the routing threshold" | `choice == needed` AND `confidence ≥ 0.35` AND non-empty intake `research_query`. A/B and C-fallback: research when policy auto and intake gave a `research_query`; `force` always; `off` never. |
| G8 | Panel order vs publication | Concurrent drafts (2) from one snapshot; publication buffered to **roster order** (a failed slot doesn't block), so `sequence` order == roster order and the UI renders by sequence. |
| G9 | Rating labels / distinct directions absent from contract | Additive amendment applied first in Task 3: `labels` (unique enum `unsupported_claim, missed_constraint, false_credential, mishandled_disagreement`) and `distinct_directions` (int ≥ 0 or null) on `RatingCreate` + `Rating`, in `openapi.yaml` AND `domain.schema.json`; doc 08 note; validator must still pass. |
| G10 | Sort orders unspecified | Idea cards `created_at, id` asc; sources `retrieved_at, id` asc; evaluations `created_at, id` desc; trials `case_id, replicate, blind_label`. |
| G11 | Summary turns | `audience=summary` skips intake and routing; uses existing evidence. |
| G12 | Card/composer actions | Ask more = `person` + `expand` + `reply_to` (Standard mode: `auto` + `expand` + `reply_to`); Challenge = `auto` + `challenge` + `reply_to`; Summarize = header action + optional suggestion chip (never forced), sent as `audience=summary` with a natural message. Targeting an unselected persona asks "Add X to this room?" → PATCH selection → target; never silent. |
| G13 | Retryable states | Latest run with status `partial|failed|interrupted|cancelled` and no later user message; completed → 409 `retry_not_allowed`. |
| G14 | Fork memory without provider calls (doc 08 "rebuild from prefix") | Take memory from the turn snapshot of the first user message after the cutoff (edit/regenerate: that message's own snapshot; none after cutoff → current memory), remap IDs, drop items citing messages outside the prefix. |
| G15 | Applicable brief on fork | Edit/regenerate → that turn snapshot's revision; prefix fork → revision used by the next user turn after the prefix, else current; revisions copied with original numbers. |
| G16 | Edit/regenerate/retry inside forks | User messages store internal `turn_control`, `turn_snapshot`, `round_status` (copied + remapped on fork); lineage FKs (`origin_session_id`, `origin_message_id`, copied `research_packs.run_id`) are `ON DELETE SET NULL`. |
| G17 | Which failures retry | Retry once only on 429, 503, Jev 529 and connection errors before send (honoring `Retry-After`); 500/502/504 and timeouts → failure with `usage_unknown`, no retry. |
| G18 | Jev move options | `clarify` = persona asks one material question, then the round ends; `combine` offered only when ≥ 2 prior contributions or saved ideas exist. |
| G19 | Lab vs worker/restart/CLI | One batch at a time and at most one Lab run claimed at once; restart → queued Lab runs `cancelled`, non-terminal batches/trials `interrupted`; CLIs that create work (`eval-run`, `smoke-live`) call the running app's HTTP API. |
| G20 | Lab presentation | Blind labels "Output 1/2/3" (never A/B/C); `results?reveal=true` marks all trials revealed; median computed client-side from `case_differences`; sensitivity rows tagged by an `interpretation` prefix; reveal queries never prefetched or refetched on focus. |
| G21 | Cost / USD cap | Config has no rate fields → `estimated_cost_usd` null ("unknown"); a set `MAX_SESSION_USD` is reported unenforceable (`budget_cap_unenforced`) in Settings and run warnings — never a claimed guarantee. `# ponytail: add a versioned rate card when estimates are needed`. |
| G22 | Default titles, versions | Auto title = idea's first line ≤ 60 chars at a word boundary (`title_is_custom=false`), replaced once by intake via compare-and-set; fork title null → "<title> (fork)" / edit-regenerate "<title> (branch)"; Duplicate sends "Copy of <title>"; all ≤ 120. Idea-card and feedback writes never bump session `version`. |
| G23 | Context ceiling | Required material (message, brief, constraints, reply target, profiles, referenced ideas) + max output checked at submit → 422 `context_too_large`; no run created. `# ponytail: chars/4 estimate, tokenizer if limits bite`. |
| G24 | MANIFEST after edits | MANIFEST stays the record of the package as received (verified at import); checklist/contract edits tracked in git + notes. |
| G25 | Seed loading | Profiles, benchmark cases, fixture evidence load from `handoff/` at startup into a validated, hashed catalog (`python -m app.cli validate-config` prints counts + hashes). No DB copies of editable definitions; no fake chats seeded. |
| G26 | Two accent palettes | API `Persona.accent` from `personalities.json`; UI dots/rings use `persona-ui.json`. |

Additions to the G2 warning vocabulary made during implementation: `intake_unavailable`,
`attempts_exhausted`. The G1 error catalog gained `trial_not_finished` (409, rating an unfinished
Lab trial) and `provider_mode_changed` (a run queued under another provider mode never calls a
provider).

## 2. Architecture as built

- One FastAPI process with one Uvicorn worker serves `/api/v1`, server-sent events and the built
  React app on one origin. An in-process asyncio worker claims persisted runs from PostgreSQL 16
  (`FOR UPDATE SKIP LOCKED`, a partial unique index allows one active run per chat) and runs the
  stage pipeline through replaceable adapters (OpenAI, Jev, deterministic demo).
- `handoff/contracts/openapi.yaml` is the single public contract: backend Pydantic models
  (`backend/app/domain/api.py`) and frontend types (`frontend/src/api/schema.d.ts`) are generated
  from it, every response in the backend tests is validated against it, and a test fails if any
  contract operation is unrouted or if the generated files drift.
- Contract amendment G9 (rating `labels`, `distinct_directions`) was applied to `openapi.yaml` and
  `domain.schema.json` with a note in doc 08; the handoff validator still passes (630 checks).
  `MANIFEST` records the package as received (G24).
- Migrations: `0001` (initial schema), `0002` (`messages.round_info`, `runs.intake`).
- Request guards (`backend/app/api/security.py`): trusted Host, exact allowed origins plus the
  server's own origin, cross-site mutation rejection (403), JSON-only mutation bodies (415).
- The Experiment Lab scheduler (`backend/app/workers/lab.py`) starts after crash recovery and runs
  one batch and one trial at a time through the normal turn path.
- Cursor errors differ by kind. A bad **list** cursor (history, search, messages, sources, ideas,
  Lab trials) is 400 `bad_request`; a cursor from another query or filter set is also 400. A bad
  **event-stream** cursor (`Last-Event-ID` or `after` that is not an event of that run) is 409
  `invalid_cursor`, sent before streaming starts, so the client reloads the run and messages.
- Replies added by **Retry missing replies** publish after the replies that already exist, so a
  retried panel round is no longer in roster order. Each such card is labeled "added by retry"
  (`grouping.ts` `retriedIds`), and exports keep publication order.
- Archiving or deleting a chat that is still replying asks first ("Stop and archive" / "The
  running reply is stopped first"), cancels the run, waits until the chat is idle, then acts
  (doc 14). The server still refuses both while a run is active.

## 3. SDK and tooling adaptations

- **openai 3.31** runs on `httpx2` (a fork with distinct classes from `httpx`); the adapter,
  tests and connect-error detection use `httpx2`, declared as a direct dependency. The adapter sends
  the contract JSON schema with `strict: true`, `store: false`, never `temperature`, and reasoning
  effort only when `OPENAI_REASONING_EFFORT` is set; SDK retries are off (`max_retries=0`) so the
  app's single retry policy (G17) is the only one.
- **Regional OpenAI hosts**: `OPENAI_BASE_URL` (optional, empty by default) is passed to the SDK
  for projects bound to a data-residency host; the live smoke needed `https://us.api.openai.com/v1`.
- **Provider request IDs** are kept on every call: OpenAI's `x-request-id` (via the SDK) and Jev's
  `x-typesafe-request-id`. Jev probabilities arrive rounded to two decimals, so their sum is
  checked within ±0.005 per option.
- **Jev**: a small HTTPX adapter for `POST https://api.typesafe.ai/v1/systemone` (doc 13) rather
  than `typesafe-sdk`, which brings its own retries and unredacted body logging. The response body
  is parsed with NaN/Infinity rejected; usage is kept only as non-negative integers.
- **TypeScript** is pinned to 5.9.3: openapi-typescript 7.13 cannot run on TypeScript 7's native
  compiler. **Vitest** 4.1.11 is the current `latest` tag.
- **Docker**: `uv` is installed from PyPI in the image (pulls from ghcr.io hang behind this
  machine's Docker proxy) and the `# syntax=` directive is omitted for the same reason.
- Node 25 locally (images pin Node 24, `engines` and `.nvmrc` say 24); the unit-test setup restores
  jsdom's `localStorage` that Node ≥ 25's own global shadows.

## 4. Decisions made during implementation

Each line: the decision, why, and what it would cost if wrong. Grouped by plan task (Task N),
checkpoint review (CPn) and final review (Final).


**Pre-flight**

- T2 catalog consumes generated `Persona`/`EvaluationCase` (T3 step 2) — conflict: produced after consumed. Ruling: run T3's G9 amendment + model generation at the start of T2; T3 keeps the contract tests — cost if wrong: none, order only.
- T11 new-chat pending flow consumes `useDrafts().pending` (T22) — conflict: forward ref. Ruling: create stores/drafts.ts with T22's full interface in T11; T22 adds notice/UI — cost if wrong: none.

**Task 2**

- Ruling: G9 amendment + model generation done here (pre-flight ruling) — generator flags pinned incl. --collapse-root-models (enum RootModels → inline Literals; PERSONA_IDS/MODES derived from generated annotations) — cost if wrong: one regeneration.
- Ruling: no clarification template — doc 05 clarification republishes the intake's clarifying_question, no extra provider call — cost if wrong: one template file.
- Ruling: template version = sha256[:12] (content-addressed) — doc 06 asks for versioned templates with a hash on every call; a content hash is both — cost if wrong: none.
- Ruling: /health reports worker "failed" (status degraded) until Task 9 adds the worker; checkpoint-1 verify checks database "ok" instead of status "ok" — honest state — cost if wrong: none.
- Ruling: commits per checkpoint (user's choice) not per task; task ledger lines show the checkpoint base until the checkpoint commit — cost if wrong: coarser review ranges.
- Ruling: pytest runs as `cd backend && uv run pytest` (testpaths=../tests/backend in pyproject) — pytest only finds backend/pyproject.toml from cwd — cost if wrong: none.

**Task 3**

- Ruling: mirror checks (domain.schema.json, llm/*.json ≡ components) delegated to the handoff validator subprocess test rather than duplicated — it already asserts them — cost if wrong: none.

**Task 4**

- Ruling: migration 0001 autogenerated from models then hand-fixed (pg_trgm with clear error; runs<->messages cycle broken by use_alter + explicit create_foreign_key) — `alembic check` test proves models == migration — cost if wrong: none.
- Ruling: runs.user_message_id FK is DEFERRABLE INITIALLY DEFERRED so the user message and its run insert in one transaction — cost if wrong: none.

**Task 5**

- Ruling: TypeScript pinned to 5.9.3 — openapi-typescript 7.13 (peer ^5.x) crashes on TS 7's native compiler (no JS API) — cost if wrong: revisit when openapi-typescript supports TS 7.
- Ruling: Vitest 4.1.11 (npm latest tag; 5.0 not tagged latest) — cost if wrong: none.
- Ruling: test-setup restores jsdom localStorage when Node >= 25's own global shadows it (local Node 25; Docker uses 24) — cost if wrong: none.
- Ruling: header shows the brand; pages inject actions through HeaderActions portal (no per-page title slot — room title lives in the page body as in the mockup) — cost if wrong: small.

**Task 6**

- Ruling: uv installed from PyPI (pinned 0.12.0) in the image instead of COPY --from ghcr.io/astral-sh/uv — the Docker daemon's registry access through Docker Desktop's proxy hangs on ghcr; base images resolve from the local store; build containers reach PyPI/npm — cost if wrong: none (same uv version).
- Ruling: dropped `# syntax=docker/dockerfile:1.7` (needs a registry pull; Docker 29's built-in frontend supports cache mounts) — cost if wrong: none.
- Ruling: SPA fallback implemented as a 404 handler (not a catch-all route) so it can never shadow API routes registered later — cost if wrong: none.

**CP1**

- Ruling: sidebar /chats?filter active-state finding deferred to Task 22 (those links get real lists there) — cost if wrong: none.
- Ruling (reviewer declined-to-judge): per-run event ordering — append_event must hold the run row lock (Task 9, as planned); fork copies set run_id NULL and copy packs+sources (Task 19, as planned); updated_at maintained in services; enum CHECKs on runs.mode/audience/stage left to app validation — cost if wrong: small.

**Task 7**

- Ruling: idempotency scope = method + concrete path (keys per resource); only successful responses stored (errors roll back the record so retries re-execute) — cost if wrong: none.

**Task 8**

- Ruling: run row is flushed before its user message (messages.run_id FK is immediate; runs.user_message_id is deferred) instead of a new migration making both deferrable — cost if wrong: none.
- Ruling: G23 context check = sum of chars/4 over message, brief, reply target, selected profile JSON, referenced cards + reserved max output vs llm_input_tokens, at submit (422 context_too_large, no run) — cost if wrong: estimate too loose/tight; knob is the limit.
- Ruling: snapshot.idea_cards captures ALL session saved ideas at submission (context source); control.idea_card_ids are the explicit references — cost if wrong: none.

**Task 9**

- Ruling: publish_contribution (planned Task 11) built here — Stop/recovery tests need real transactional publication — cost if wrong: none.
- Ruling: JSONB columns use none_as_null=True — Python None was persisted as JSON null, violating the content CHECK (found by the worker test) — cost if wrong: none.
- Ruling: deadline = loop.call_later timer that behaves like Stop (expire → cancel in-flight provider call; checks raise DeadlineExceeded) instead of asyncio.timeout around the pipeline, so a DB transaction is never cancelled mid-flight — cost if wrong: a pipeline stuck in a non-provider await outlives its deadline.
- Ruling: Stop-after-completion race → finalize sees cancel_requested and records cancelled — cost if wrong: a fully published round labeled cancelled.
- Ruling: shutdown cancels running tasks → finalized as interrupted (same as crash recovery) — cost if wrong: none.

**Task 10**

- Ruling: notifier keys normalized to str(run_id) — the live-tail test exposed UUID vs str key mismatch — cost if wrong: none. Frontend: npx vitest run → 8 passed.

**Task 11**

- Ruling: browser specs live in frontend/e2e (not tests/e2e) — specs outside frontend/ cannot resolve @playwright/test; tests/ keeps backend + live checks — cost if wrong: layout differs from TRD table.
- Ruling: live mode uses a NotWired provider that raises provider_not_ready until Tasks 13-14 (never demo output) — cost if wrong: none.
- Ruling: slice pipeline runs slots sequentially and auto = first k selected (routing/intake/research/repair/panel concurrency arrive in Task 16) — cost if wrong: none (replaced in Task 16).

**CP2**

- Ruling (declined-to-judge): NotWired live runs end failed with null error until Tasks 13-14 — temporary; global TimeoutError→database_unavailable revisited when checkProviders lands (Task 24) — cost if wrong: small.

**Task 12**

- Ruling: HTTP classification (classify_http) lives in calls.py and is shared by both adapters; unexpected adapter exceptions become provider_error with unknown usage — cost if wrong: none.

**Task 13**

- Ruling: openai 3.31 runs on httpx2 (distinct classes from httpx) — adapter, tests and connect-error detection use httpx2; httpx2 declared as a direct dependency — found by mypy — cost if wrong: none.

**Task 14**

- Ruling: probability sums validated to 1e-6 (fixtures carry ~1e-16 float noise); confidence values validated for range, not recomputed (doc 13: thresholds are use-case tuned) — cost if wrong: a slightly off provider sum gets rejected → labeled fallback.

**Task 15**

- Ruling: invalid content (unknown/foreign IDs, unsourced fact, schema, bounds) is a violation → repair once or not published; no silent rewriting of block kinds — cost if wrong: a slot fails instead of a relabeled fact.

**Task 16**

- Ruling: research core (search → sources → normalization) built here because routing needs it; Task 17 covers URL normalization edges, failure paths, fixture provenance and export — cost if wrong: none.
- Ruling: only invalid/unavailable Jev output marks a run degraded (coordination_fallback); a valid low-confidence answer uses the doc-05 fallback speaker without the degraded label — cost if wrong: low-confidence turns look un-degraded.
- Ruling: a repaired draft is published after deterministic validation without a second Jev assessment (one repair, no loop) — cost if wrong: repaired text unaudited.
- Ruling: refusals are not repaired; provider_not_ready/model_unavailable stop the turn (no further slots) — cost if wrong: none.
- Ruling: Standard (A) single reply uses the per-turn output budget (12,288) as its ceiling; persona replies use 4,096 each — matches doc 09 matched allowance — cost if wrong: none.
- Ruling: memory updates do not bump session content version (derived context, not a user edit) — cost if wrong: none.
- Ruling: demo provider fail directive required an explicit check (None-in-tuple bug found by Standard-mode test) — fixed.

**CP3**

- Ruling: `force` research overrides a session research_policy=off (G7; explicit per-turn user control ranks above session default in doc 05's policy order) — cost if wrong: a forced search the user did not expect.
- Ruling: new warning codes intake_unavailable, attempts_exhausted, coordination_unavailable added to the G2 vocabulary (notes) — cost if wrong: none.

**Task 18**

- Ruling: saved ideas and feedback are refused on archived chats (doc 14: archived chats are read-only except title/restore/copy/export/delete) — cost if wrong: small.

**Task 19**

- Ruling: edit/regenerate refuse (409 model_unavailable) when the turn's snapshot models differ from the configured models; a prefix fork is allowed (it starts future turns with the current config) — cost if wrong: a stricter branch rule.
- Ruling: copied user messages keep turn_control/turn_snapshot with remapped IDs (G16); historical controls with unresolvable references keep text but drop the reference; a TEMPLATE with an unresolvable reference is 409 — cost if wrong: none.
- Ruling: retry is refused when the provider mode changed since the round ran — cost if wrong: none.

**Task 20**

- Ruling: exporting a Lab-managed chat → 409 evaluation_managed (Lab export owns those); archived chats export (doc 14) — cost if wrong: one guard.
- Ruling: summaries could not carry citations (message views omitted source_ids; demo summary hard-coded []); message views now include cited source_ids and summary validation accepts sources already cited by summarized replies — doc 11 checkpoint requires source → summary → export — cost if wrong: none (IDs are server-validated).
- Ruling: Markdown renders every summary inline where it occurred (not only the latest); CLI never overwrites an existing file — cost if wrong: formatting only.

**CP4**

- Ruling: a retry never starts a second research job, even when the round's search failed — doc 05/defaults cap research at 1 per turn — cost if wrong: a retried reply works without current facts (already disclosed).
- Ruling: no backfill of round_info for rounds created before migration 0002 (no released data; dev DBs only) — cost if wrong: Fixed-panel cycle restarts in pre-0002 chats.
- Ruling (declined-to-judge): retry after a selection PATCH runs the snapshot's personas (immutable snapshot); regenerate uses the current catalog profiles and records their hashes in the new run snapshot; a fully published but cancelled round is neither regenerable nor retryable (edit works); Markdown export writes text raw (local file, not rendered by the app) — cost if wrong: small.

**Task 21**

- Ruling: workspace routes (listSessions, organization PATCH, folders) live in app/api/workspace.py rather than api/sessions.py — same operations/contract, kept apart from the CP4 files under review — cost if wrong: none.
- Ruling: folders list sorts by case-folded name then ID (G10 silent on folders) — sidebar reads alphabetically — cost if wrong: order only.
- Ruling: listSessions with a folder_id that no longer exists → 404 (lets the UI show the missing-folder state); q is trimmed and an all-space q means a normal listing (doc 14 "empty means normal listing") — cost if wrong: none.
- Ruling: archive while archived and restore are organization-only; restore must be alone (422 otherwise); pin/move on an archived chat → 409 session_archived; rename allowed — doc 08/14 — cost if wrong: none.

**Task 22**

- Ruling: sidebar/rail render real lists directly (AppShell slot props removed); `/chats?filter=` links compute their own active state (CP1 deferral resolved) — cost if wrong: none.
- Ruling: history polling is a refetchInterval on history queries (5 s only while a listed chat has an active run) plus refetch on focus — doc 14 — cost if wrong: none.
- Ruling: e2e for Tasks 22 and 23 written and run together after the room UI (workspace.spec 4 tests, room.spec 5 tests) — cost if wrong: none.

**Task 23**

- Ruling: retry re-points the round's user message run_id at the newest run so the client always retries the latest attempt (getRun on that ID) — no contract change — cost if wrong: Message.run_id of a retried user message changes once.
- Ruling: "Regenerate round" is offered on every round (not just ones the client can prove completed); the server's 409 regenerate_requires_completed message is shown — the client has no public round status — cost if wrong: an extra click to learn it is unavailable.
- Ruling: brief "Suggested by the conversation" items come from the latest summary's assumptions/open questions with provenance; there is no revision-history API, so the drawer shows the current revision number only — cost if wrong: no browsing of old revisions in the UI (exports include them).
- Ruling: demo directive [[demo:fail_once=<persona>]] added so a demo/e2e retry can succeed (fail= fails every attempt) — cost if wrong: none (demo only).
- Ruling: column count is computed from the measured group width (ResizeObserver) rather than CSS container queries, so it is unit-testable — cost if wrong: none.

**Task 24**

- Ruling: Settings limits carry max_session_usd + cost_cap_enforced=false (G21) inside the free-form limits object; provider check is user-triggered only, maps missing keys by name and reports adapter (fixed, sanitized) messages — cost if wrong: none.
- Ruling: intake may retitle only on the opening turn (fixes a later turn retitling when the first suggestion equalled the auto title, G22) — test_the_automatic_title_is_replaced_at_most_once RED→GREEN.
- Ruling: catalog "Ask directly" opens a new chat with that perspective added and the first turn targeted to it (/?ask=) — cost if wrong: none.

**Task 25**

- Ruling: Lab trial sessions are created with the batch (one per case × replicate × mode), titled with case/replicate/blind label only and title_is_custom so intake never retitles them — cost if wrong: none.
- Ruling: the per-turn output budget needs no Lab override — Standard already uses turn_output_budget (12,288) and B/C use contribution_output_tokens (4,096 = 12,288/3) — cost if wrong: none.
- Ruling: fixture evidence = a labeled copy of the case's pack inserted into each condition's session before turn 1 (all seed cases have null packs → no evidence); live evidence = research_policy auto per condition — doc 09 — cost if wrong: none.
- Ruling: a trial stops at its first failed/cancelled turn (later turns depend on it); partial turns continue; trial status completed|partial|failed|cancelled; batch finished = completed trials, failed = the rest; batch status completed / partial / failed / cancelled — cost if wrong: denominators wording.
- Ruling: comparisons are C−B and C−A for every metric except consistency vs Standard, each in an intent-to-treat row and a "sensitivity (degraded trials excluded)" row; bootstrap seeded by the batch seed so results are reproducible — cost if wrong: none.
- Ruling: no ratings read endpoint before reveal exists in the contract, so the blind UI tracks ratings saved in this browser session; results (after reveal) list all ratings — cost if wrong: a rater cannot see earlier ratings before reveal.
- Ruling: Lab scheduler polls child run status every 100 ms (ponytail-marked) — cost if wrong: minor DB load during batches.

**Task 26**

- Ruling: main is the containing block (position: relative) so absolutely positioned sr-only controls can never extend the document scroll — found visually in the Lab — cost if wrong: none.

**CP5**

- Ruling: M8 (viewport/theme/mobile e2e projects and UI lost-response coverage) belongs to Task 27's planned walkthrough — cost if wrong: none (scheduled).
- Ruling: M10 q="" → 422 stays (the contract declares minLength 1); all-space q is a normal listing — cost if wrong: none.
- Ruling (declined-to-judge): New chat resumes an interrupted first Send on mount (doc 14 requires it; same keys, no new paid work); "Add to brief" appends a suggested item as a constraint only on an explicit click — cost if wrong: small.
- Ruling: the CP5 commit was split from interleaved CP6/CP7 work by staging CP5 files plus a CP5-only App.tsx; that exact tree was verified (backend 340 passed, vitest 38, tsc) before committing — cost if wrong: none.

**Task 26**

- Ruling: the blind trial list refetches on batch progress changes (polling alone stopped before the last trials settled — found as an e2e race) — cost if wrong: none.

**CP6**

- Ruling: the latest rating per rater still counts (doc 09: a new rating can supersede one for analysis); the unblinded count is disclosed rather than switching to blinded-only — cost if wrong: analysts must filter unblinded ratings themselves (the CSV has the flag).
- Ruling: blinded trial messages keep their real created_at (contract-required field; falsifying it is worse); the shuffled run order removes the timing pattern — cost if wrong: timing analysis of raw API data could still reveal a condition (doc 09: blinding is a presentation aid, not access control).
- Ruling: M10 (a Jev-only moderator clarification can hint the condition) is inherent to the treatment and left as is — cost if wrong: weaker blinding for that case.

**Task 27**

- Ruling: feature specs run at 1440×900; the doc 10 journey and the overflow spec run at all four sizes (1440×900, 1920×1080, 1024×768, 390×844 touch); a separate project writes the screenshots — cost if wrong: none.
- Ruling: 200 % zoom is checked as the equivalent 720×450 CSS viewport — cost if wrong: none.

**Task 28**

- Ruling: a mutation whose Origin equals this server's own origin is allowed even if not listed, so the app works on another APP_PORT (fresh-clone check on 8001); Host stays restricted to local names + APP_PUBLIC_HOST + allowed-origin hosts (DNS rebinding) — cost if wrong: none.
- Ruling: requests without Origin/Sec-Fetch-Site (CLI, scripts) are allowed; there is no CORS — doc 13 — cost if wrong: none.

**Task 29**

- live smoke 1 (2026-10-15T04:27Z): OpenAI connection check failed "rejected the configured API key" — diagnosis without printing the key: 401 incorrect_hostname, OpenAI asked for us.api.openai.com (regional/data-residency project). No paid calls were made. Ruling: added optional OPENAI_BASE_URL (adapter base_url; documented in .env.example/README); the user approved setting it to https://us.api.openai.com/v1 (host came from the API response, so asked first) — cost if wrong: none (unset = SDK default).
- Ruling: no reasoning-effort change needed (0 incomplete; reasoning tokens ≤ 468 per turn) — cost if wrong: none.

**Final**

- Ruling (declined-to-judge): Lab blinding beyond presentation (raw API, session IDs, created_at) stands — doc 09 calls blinding a presentation aid and notes §6 / report §7 disclose it — cost if wrong: a determined local owner can unblind through the raw API.
- Ruling (declined-to-judge): the single-process notifier and 100 ms Lab polling stand — one Uvicorn worker is a spec constraint and both are ponytail-marked — cost if wrong: move to LISTEN/NOTIFY if a second process is ever added.
- Ruling (declined-to-judge): results?reveal=true and export reveal on GET as the contract and G20 require; the UI never prefetches or refetches them and the batch ID is an unguessable UUID — cost if wrong: a stray GET reveals conditions (it is recorded as a reveal).
- Ruling (declined-to-judge): shutdown may wait in _finalize_reliably while the database is down; Compose kills after its stop timeout and start-up recovery marks the run interrupted — cost if wrong: a slower stop in that rare case, no lost output.
- Ruling (declined-to-judge → finding): db_backup.sh left a partial dump under a valid-looking name when pg_dump failed midway, and restoring such a file drops current data and left the app stopped — a person gets silent data loss, so it is Important by effect and fixed (see Final: fixed).
- Ruling (declined-to-judge): brief constraints are one per line in the editor — the spec is silent and each line is shown as one constraint — cost if wrong: a multi-line constraint becomes several.
- Ruling (declined-to-judge): WARNING_TEXT stays duplicated in backend and frontend; test_warning_texts_match_between_backend_and_frontend keeps them equal — cost if wrong: none.
- Ruling (declined-to-judge): a deep-link (?message=) window does not take live SSE upserts of new replies; reopening the chat or loading the latest page shows them — cost if wrong: someone reading an older window does not see new replies arrive.
- Ruling (declined-to-judge): doc 05's "uncertain → ask the user or offer Research this" is not implemented; an uncertain research answer continues on labeled assumptions and the composer's Research → Force is one click — deciding when an answer "depends on the missing fact" needs a judgment the plan never defined — cost if wrong: people miss a prompt to verify a fact their answer depends on.

## 5. Independent review findings and fixes

A fresh reviewer (a separate model context) gated checkpoints 1–6; the whole-branch review also gated checkpoint 7. Each Critical or Important finding was reproduced as a failing test before it was fixed. Minor findings from the whole-branch review that were not fixed are listed as deferred.

- Checkpoint 1 review (fresh reviewer, opus): 0 critical, 1 important, 7 minor.
- Checkpoint 2 review (fresh reviewer, opus): 0 critical, 2 important, 11 minor. Concurrency core confirmed (idempotency, one-active-run, lock order, Stop vs publish, claim).
- Checkpoint 3 review (fresh reviewer, opus): 2 critical, 6 important, 9 minor — all reproduced by reviewer probes.
- Checkpoint 4 review (fresh reviewer, opus): 1 critical, 4 important, 6 minor — 7 reproduced by reviewer probes (ported into the suite).
- Checkpoint 5 review (fresh reviewer, opus): 0 critical, 4 important, 10 minor — 3 important reproduced by browser probes, 1 by reading Radix.
- Checkpoint 6 review (fresh reviewer, opus): 0 critical, 4 important, 10 minor — 3 important reproduced by probes.
- Final review (fresh reviewer, opus, whole branch c8ff1a3..830b6ac): 1 critical, 4 important, 9 minor; Focus 3 and 4 verified end to end in the running app; verdict "ready once Critical and Important are fixed".

- CP1: fixed Important — backend/.env could be baked into the image (.dockerignore root-only) — test_dockerignore_excludes_env_files_at_any_depth + test_env_file_has_one_location_at_repo_root RED→GREEN; env_file now REPO_ROOT/.env.
- CP1: fixed minors — no-.env crash loop (DATABASE_URL falls back to AppEnv default; verified compose up without .env); banner names every missing key + unreachable-server state; README subshell commands; X-Request-ID on 500s (test asserts header); DB connect timeout 5s; enum drift guards (test_persistence_enums_match_contract) + generated-model staleness guard (test_generated_models_are_current — caught real formatting drift; gen script gained API_OUT/API_ONLY); duplicate default_selection rejected.
- CP2: fixed Important — finalize failure left a run active forever → _finalize_reliably retries with capped backoff — test_finalize_retries_until_the_database_answers RED→GREEN.
- CP2: fixed Important — snapshot provider_mode ignored → execute fails provider_mode_changed with zero provider calls — test_run_queued_under_another_provider_mode_never_calls_a_provider RED→GREEN.
- CP2: fixed minors — SSE reads status before events (terminal-frame race); missing slots computed at finalize (test_demo_runs_are_labeled_and_report_missing_slots_on_stop); demo_mode warning; malformed in-scope cursor → 400 (test); Lab-cancel error code; notifier prunes counters 60s after final notify; client: cancelQueries before SSE upsert, reconnect from start after a lost stream (no 409 loop), uncertain resend keeps edited text (send.test), TurnRejected moves the opening text into the created room; e2e mid-run reload test added (4/4).
- CP3: fixed C1 NaN/garbage from Jev crashed the run → Jev body parsed with parse_constant rejection, untrusted usage kept only as non-negative ints, decision payloads made JSON-safe — test_nan_from_jev_falls_back_instead_of_crashing + test_non_finite_numbers_in_the_jev_body_are_a_provider_failure RED→GREEN.
- CP3: fixed C2 summary resent after uncertain/fatal failure → repair only for Structured-invalid/Incomplete — test_failed_summary_call_is_never_resent RED→GREEN.
- CP3: fixed I1 failing persona starved the round → per-turn failed set excluded from eligibility — test_a_failing_persona_does_not_starve_the_others.
- CP3: fixed I2 invalid move/research/assessment answers undisclosed → any Invalid route answer flags coordination_fallback; all-invalid scores = audit_unavailable + degraded — two tests.
- CP3: fixed I3 concurrent panel traces overwrote each other → ask_jev returns an explicit Trace — test_each_panel_slot_keeps_its_own_assessment_trace.
- CP3: fixed I4 Stop mid-panel left call rows 'started' → call_provider records outer CancelledError as cancelled (shielded) — test_outer_cancellation_records_the_call_as_cancelled.
- CP3: fixed I5 reply target truncated to 800 chars → passed up to 4000 — test_reply_target_is_passed_in_full. I6 allowed message IDs = all same-session messages (not just recent).
- CP3: fixed minors — repair payload carries previous_draft (M1); cancellable generation-slot acquire (M2); fatal errors stop slots, repairs and memory (M3, test_fatal_provider_error_stops_the_rest_of_the_turn); forced research uses a short query (M4); bound_state clips long fields and trims assessment lists (M5, test); Jev model taken from the run snapshot (M6, test); Standard intake omits persona names (M7); blank clarifying question normalized to None (M8, test); 401 no longer marks usage incomplete and Retry-After > 10 s ends the attempt (M9, tests); move questions skipped under a move override.
- Task 17: fixed — provider coroutine created lazily inside the cancellable child (Stop just before a call left an unawaited coroutine; RuntimeWarning under -W error).
- Task 19: fixed orchestrator retry arithmetic (auto requested already = remainder; fixed-panel retries keep their round index).
- CP4: fixed C1 mid-round fork memory carried cut replies (overview/through_sequence) → memory past the cutoff falls back to the cut round's pre-round snapshot memory — test_mid_round_fork_memory_never_covers_cut_replies RED→GREEN.
- CP4: fixed I1 copied pack findings kept source-session IDs → normalized findings remapped — test_copied_research_packs_point_at_the_forks_own_sources RED→GREEN.
- CP4: fixed I2 fork exports lost demo/degraded/research disclosures → round public status (provider mode, warnings, missing, degraded, published) stored on the user message at terminal (messages.round_info, migration 0002), copied by forks, read by exports; packs of copied rounds (incl. failed/empty) copied — test_fork_exports_keep_demo_and_research_disclosures RED→GREEN; also fixes "missing after successful retry" (test_export_after_a_successful_retry_reports_nothing_missing).
- CP4: fixed I3 retry re-ran intake + research and could not see its round → runs.intake persisted and reused, retries never search again (research budget is per turn) and reuse the round's evidence, auto retries see the round's published replies — test_retry_reuses_the_rounds_intake_and_evidence_and_sees_its_replies RED→GREEN.
- CP4: fixed I4 fixed-panel cycle stalled after a retried failed round → round index counts earlier auto rounds with published replies from user-message round_info (forks keep it too) — test_fixed_panel_cycle_advances_after_a_failed_round_is_retried RED→GREEN.
- CP4: fixed minors — copied controls remap each reference independently with an internal unresolved marker (edit in fork still 409, test); Lab chats refuse cards/feedback and feedback refuses user messages (tests); copied cards/revisions keep dates, author and remapped source IDs; regenerate checks the research model too (test); prior evidence only from available packs.
- CP5: fixed I1 an uncertain earlier send was replayed in place of edited text → sends detect a different pending body (PendingConflict) and ask: resend the earlier request (same key, never duplicated) or discard it; Summarize uses its own key — send.test "never sends an uncertain earlier request…", "a summary uses its own key…", "a first send whose idea changed…" RED→GREEN.
- CP5: fixed I2 Duplicate / Fork here / New folder minted a new key per click → withOperationKey keeps one key per operation until the server answers — actions.test "a duplicate whose response was lost…" RED→GREEN.
- CP5: fixed I3 closing dialogs/drawers dropped focus on <body> → useReturnFocus (menu items resolve to their trigger) on the dialog host, search, details drawer and mobile nav — focus.test RED→GREEN (mutation-checked).
- CP5: fixed I4 room state leaked across chats → RoomRoute keys RoomPage by chat ID — e2e "switching chats in-app starts each room fresh…".
- CP5: fixed minors — M1 roster PATCHes serialized with the cached version, invalidate instead of stale rollback; M2 folder→chat lock order in organization edits (deadlock race test RED→GREEN); M3 Fork chat copies the whole conversation (through null); M4 Start without a folder merges drafts; M5 unselected target shown in select and chip asks to reselect; M6 per-code card warnings; M9 combobox + activedescendant for @ mentions; M10 confirm before removing a noted idea.
- CP6: fixed I1 unknown usage exported as 0 → trial token totals are null when any turn's usage is missing; CSV gains usage_incomplete and writes NA — test_unknown_usage_is_exported_as_missing_not_zero RED→GREEN.
- CP6: fixed I2 post-reveal ratings changed results silently → results state how many analysed ratings were unblinded — test_results_disclose_ratings_made_after_reveal RED→GREEN.
- CP6: fixed I3 a non-API exception left a trial "running" → the trial loop marks the trial failed and the batch continues — test_a_crash_inside_a_trial_fails_that_trial_and_the_batch_moves_on RED→GREEN.
- CP6: fixed I4 repairs/fallbacks unreported and "degraded" mislabeled → per-condition fallback, repair and quality-warning counts from run warnings in results and CSV columns — test_results_report_fallbacks_and_repairs RED→GREEN.
- CP6: fixed minors — M1 denominator wording; M2 a batch is failed only when no trial produced output; M3 condition run order shuffled per case with the batch seed; M4 rating an unfinished trial → 409 trial_not_finished (test); M5 live-run confirmation fails closed; M6 elapsed = run time, not queue wait; M7 failed-trial copy + keepPreviousData on reveal; M8 queued cancel counts trials as not finished (test); M9 export uses the case inputs captured in the batch snapshot (test).
- Task 27: fixed issues found by the walkthrough — composer combobox lacked aria-expanded (axe), a send right after a roster change self-409'd (mobile journey: send now awaits pending selection saves and uses the cached version), compact cards' hidden action row wrapped into blank space (icon buttons with names/tooltips; labels when expanded), mobile composer took three rows (one row), mobile header truncated to "Pe…" (logo; name stays for screen readers).
- Final: fixed C1 an empty OPENAI_BASE_URL (as shipped in .env.example) broke every live OpenAI call → empty means unset and the adapter passes the default host explicitly — test_an_empty_api_host_setting_means_the_default_host RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed I1 a rejected key/unavailable model was hidden behind intake_unavailable with a doomed Retry (+ M9 Retry on a fully published stopped round) → intake_unavailable suppressed when fatal; the room shows run.error with a Settings link; Retry only when retryable and something is missing — test_a_rejected_key_at_intake_is_one_call_and_no_misleading_intake_note, runStatus.test.ts RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed I2 long unbroken model-written text overflowed the page and drawer → overflow-wrap:anywhere on the turn section, summary sections and drawer; demo token=N directive seeds long tokens — overflow.spec "unbroken model-written text…" (4 sizes), test_token_directive_* RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed I3 blocked localStorage blanked the Lab rating view and broke Clear local workspace state → safeStorage — RatingView.test.tsx RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed I4 low-confidence Jev routing was neither shown nor counted → coordination_low_confidence run note (not degraded), low_confidence_fallback counted in results/CSV and hidden while blind — test_low_confidence_routing_is_disclosed_without_degrading_the_run, test_low_confidence_fallbacks_are_counted_and_hidden_while_blind RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed M3→Important New chat auto-resent an interrupted first Send on mount → banner with Send it now / Discard the earlier send — NewChatPage.test.tsx RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed M2→Important only 30 saved ideas loaded → useIdeas loads every page — queries.test.tsx RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed M8→Important doc claims → report §6 and notes §5 state CP1–6 reviews + whole-branch review gating CP7; README live commands corrected (RUN_LIVE only for the pytest wrapper); stale App.tsx comment replaced — docs only (no test).
- Final: fixed (declined-to-judge → finding) partial backup dump / app left stopped after a failed restore → dump renamed only on success; failed restore restarts the app and says so — test_a_backup_that_fails_midway_leaves_no_dump_behind, test_a_failed_restore_starts_the_app_again_and_says_so RED→GREEN (+ test_a_finished_backup_is_kept_under_its_final_name), suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed peer (a) Stop during memory after every reply published → nothing to retry — test_stop_during_memory_after_every_reply_leaves_nothing_to_retry RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed peer (b) retried panel replies publish after their siblings → labeled "added by retry" and documented (notes §2) — room.test retriedIds RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed peer (c) archive/delete of a running chat only showed a disabled item → offers Stop and archive / stops first on delete, then acts — workspace.spec "…offers Stop first (doc 14)" RED→GREEN, suite backend 406/406, vitest 52/52, Playwright 38/38.
- Final: fixed peer (d) cursor errors documented in notes §2 (list 400 bad_request, SSE 409 invalid_cursor) — docs only.

- Final: minor (deferred): M1 a fast double-click on Save creates two saved ideas (new idempotency key per click; no unique (session, message) constraint).
- Final: minor (deferred): M4 model_unavailable is detected only on a 404 mentioning "model"; a 400 model_not_found would be a non-fatal invalid_request, so each slot tries once (unverified that the API returns 400).
- Final: minor (deferred): M5 an invalid Jev key gives a 401 on every route/assessment step of a turn, labeled only "Fixed order used".
- Final: minor (deferred): M6 saved ideas (notes up to 4,000 chars) are appended to every payload with no token budget; only required context is checked against 24,000 at submit.
- Final: minor (deferred): M7 the 300 ms draft debounce is not implemented; each keystroke rewrites the drafts map to localStorage.

### Found by the live smoke (Task 29)

- live smoke 2 (04:42Z, with probe): all steps completed, but the Jev-guided turn fell back (coordination_fallback, 1/3 replies) — Jev returns 2-decimal probabilities (0.04+0.67+0.26+0.02 = 0.99) and the validator required a sum within 1e-6; the fallback speaker then got Jev's clarify move, ending the round. Fixed: tolerance 0.005 per option (rounding only) — test_probabilities_rounded_by_the_provider_are_accepted RED→GREEN.
- live smoke 3 (04:53Z, no probe) after the fix: jev_guided 3/3 (skeptic/challenge 0.68, explorer/explore 0.41, mentor/clarify), direct_person 1/1, forced_research 3/3 with 7 real sources (no fixtures; 5 fact blocks, all cited), summary 1/1 with the five sections; 30 calls all ok, 0 refused/incomplete, 0 unknown usage; models returned gpt-6.1-sol and jev-1.13.0; median latency draft 10.4 s, route 0.3 s, assess 0.5 s, research search 42 s.
- live smoke found request IDs missing on successful calls (0/30) → results carry request_id (OpenAI x-request-id via SDK; Jev x-typesafe-request-id, header name checked on the free /v1/models endpoint) and call_provider stores them — tests RED→GREEN (OpenAI, Jev, call log); not re-verified with a paid live call.
- personality probe (smoke 2): 8 + 8 panel replies on a seed-library idea; each perspective took a distinct angle matching its priorities and all updated after the follow-up; no fabricated credentials found by scan or reading; weakness: several follow-ups open with near-identical phrasing.
- complete (commits df44312..df44312, tests: uv run pytest -c pyproject.toml -p no:randomly ../tests/backend/unit/test_smoke_cli.py ../tests/backend/unit/test_jev.py ../tests/backend/unit/test_openai_adapter.py ../tests/backend/integration/test_calls.py → 66 passed in 9.22s)

## 6. Known limitations

- The seed set is a 30-case pilot, not a validated benchmark; scripted follow-ups are less natural
  than adaptive discussion (doc 09). No benchmark was run.
- Cost is reported as unknown: the configuration has no price table (G21). A configured
  `MAX_SESSION_USD` is shown as unenforceable rather than enforced.
- The in-process notifier assumes one backend process (`ponytail:` marked; switch to
  LISTEN/NOTIFY if more processes are ever needed). The Lab polls child runs every 100 ms.
- The context ceiling uses a characters ÷ 4 token estimate (G23).
- Portraits are cropped from the approved 1.5 MB mockup images (both preloaded after start);
  dedicated optimized portrait assets could replace them.
- Blinding is a presentation aid (doc 09): the raw API still lets a determined local owner work out
  conditions (for example from session IDs), and a Jev-only moderator clarification can hint at C.

