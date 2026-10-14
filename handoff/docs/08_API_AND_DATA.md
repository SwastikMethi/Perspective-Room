# API, data, and event contracts

`contracts/openapi.yaml` is the public API source of truth. It defines request/response fields and schema constraints. The LLM schema files are the source for structured generation. `contracts/domain.schema.json` is a generated mirror for standalone validation; do not edit it independently. Application validation adds the relationships below.

## API conventions

Base path `/api/v1`. JSON uses snake_case and UUID identifiers. Timestamps are UTC ISO 8601, rendered in the browser's local timezone. Use cursor pagination; default 30, maximum 100. Chat history orders by last_activity_at/ID descending; folders by normalized name/ID ascending; transcripts use sequence/ID. Cursors encode direction and query/filter state and are opaque to the client. A null next cursor means no later page in that direction; transcripts also use previous_cursor for older history. Return structured `Error` objects for validation, conflicts, missing data, and provider readiness failures. Sanitize provider error details before returning them.

`expected_version` supports optimistic concurrency. Include it in context edits, turn submission, fork, and retry. A stale value is 409. Organization writes separately use `expected_organization_version`; folder writes use folder `expected_version`. A stale version returns 409 with the relevant current version in Error.details. Idempotency keys protect creating sessions, folders, turns, forks, saved ideas, evaluations, and ratings. The same key/body reuses the existing result; a changed body conflicts. No API call publishes externally or sends messages to other people.

## Endpoint groups

| Group | Operations |
| --- | --- |
| System | Health, personality catalog, settings/readiness, explicit provider connection check |
| Sessions | Lightweight filtered/searchable list, create, retrieve, edit context, edit organization, delete, fork, export |
| Folders | List, create, retrieve, rename, delete while retaining chats |
| Conversation | Submit turn, page messages, inspect run, stop run, retry missing work, subscribe to run events |
| Ideas | List/create saved ideas, edit notes/status/title, remove saved idea |
| Feedback | Replace the local user's feedback on a message |
| Sources | List session sources and inspect one source |
| Evaluation | Create/list batch, poll status, stop, read blind/revealed trials, save rating, export |

`GET /evaluation-cases` supplies the case catalog. `GET /evaluations/{id}/results` supplies ratings, condition summaries, and paired comparisons; values remain null until measurements exist. With fewer than five matched cases, leave confidence-interval fields null and show raw paired differences. Do not compute a Standard persona-consistency result. Implementation amendment (2026-10-15): `RatingCreate` and `Rating` also carry `labels` (the document 09 manual labels: `unsupported_claim`, `missed_constraint`, `false_credential`, `mishandled_disagreement`) and `distinct_directions` (count of distinct useful directions, or null), added to `openapi.yaml` and `domain.schema.json` together.

Trial reads default to blinded fields. A deliberate `reveal=true` read records reveal exposure, returns condition metadata, and sets `Cache-Control: no-store`; the UI must never prefetch a reveal URL. Aggregate results require prior reveal or an explicit `reveal=true`, otherwise return 409 `reveal_required`. Revealing aggregate results marks affected trials revealed. Remove mode-revealing warning codes from blinded message projections. This is presentation blinding, not protection from the local owner inspecting data.

Creating a session stores the idea as the first confirmed brief but does not call a model or create a transcript message. The frontend then submits the same opening text as the first turn. Keep the two idempotency keys distinct and stable across retries. Default mode is Jev-guided; default selected personas and settings come from configuration.

## Cross-field rules

- `audience=person` requires a selected `target_persona_id`; other audiences require null.
- `audience=summary` cannot have a persona target, move override, or force-research setting. Summaries use existing evidence. The frontend supplies a natural summary request as `message`.
- `move_override=combine` requires at least two valid referenced saved ideas, or a reply target plus another selected saved idea. All references must belong to the same session. The UI must show them before submission.
- `reply_to_message_id`, cited sources, and saved-idea references must resolve to the same session or copied fork records.
- Standard mode uses one neutral assistant; reject persona/panel audiences in this mode. Selected-profile metadata may be retained for a later fork/comparison, but is not passed into its generation prompt.
- A session's mode is immutable. An ordinary fork may choose another mode; edit/regenerate branches preserve the source turn's mode. Settings/brief/profile changes are blocked while a run is active. Feedback and idea-card notes remain editable without changing the active run snapshot.
- In Auto, `requested_count` is an upper bound and successful completion may publish fewer responses. In Panel, it is the exact number requested. The UI must distinguish these meanings.
- Retry applies only to the latest incomplete run with no later user turn. It creates a linked run, reuses the original user message and profile snapshot, and schedules only unpublished requested work. It does not create a second copy of the user message or regenerate successful replies. Otherwise return 409 and offer a new normal turn.
- Title length is 1–120 trimmed characters; folder name is 1–80; user message is 1–16,000 characters. Folder names are unique under normalized case-insensitive comparison. Reject all-whitespace strings in application validation. Deduplicate selected IDs and reject invalid values. Application policy can impose tighter input limits than provider schemas.
- A persona message has non-null persona ID and Contribution content. Standard-mode assistant messages use the moderator role with Contribution content and a null persona ID. A summary moderator message has Summary content. A clarification moderator message uses plain text. User messages have only text. Enforce one applicable content variant; the public schema intentionally keeps the envelope simple.
- LLM contribution blocks must be nonempty, with bounded text. `fact` blocks containing external claims require valid evidence IDs, or must be rewritten as an explicitly qualified assumption/limitation. Provenance validation alone is not truth validation.
- A Summary has exactly one of each of the five section kinds, in UI order. Empty sections are allowed and should say no item was established rather than invent one.
- Deleting an active session returns 409; the UI first offers Stop. Deletion removes its local messages, research, traces, feedback, saved ideas, and non-experiment runs transactionally. A session referenced by an evaluation cannot be deleted individually; delete the entire evaluation with its generated sessions through local data controls or retain it. Implement evaluation deletion as a CLI operation in this release and explain it in Settings.

## Persistence model

| Entity | Essential fields and constraints |
| --- | --- |
| `sessions` | ID, title, internal title_is_custom, nullable folder FK, is_pinned, is_archived, organization_version, last_activity_at, origin_session_id, immutable mode, selected persona IDs, settings, content version, current brief/revision, current memory, active run, timestamps |
| `folders` | ID, name, normalized unique name, version, timestamps; no parent folder in v1.1 |
| `idea_revisions` | Session, revision number, idea/goal/constraints, author type, source message IDs; immutable unique session/revision |
| `messages` | Session, run, increasing sequence, role, persona ID, content JSON, derived public search_text, warnings, source lineage; unique session/sequence and run/contribution index |
| `runs` | Session, opening user_message_id, status, stage, immutable input/profile/model snapshot, controls, worker/heartbeat, cancel flag, retry_of, desired/missing participants, usage, timestamps |
| `run_events` | Monotonic event ID, run ID, type, JSON payload, timestamp; index run/ID |
| `research_packs` | Run, query, raw citation-bearing answer, normalized findings, unknowns, status, provider response ID |
| `sources` | Pack/session, title, URL/domain, retrieved/published times, provider citation metadata, bounded excerpt, fixture flag |
| `idea_cards` | Session, source message, title, note, status, version, timestamps |
| `feedback` | Message, local-user labels/note, timestamp; unique message for this single-user app |
| `provider_calls` | Run, call purpose, attempt, provider/model, prompt/profile version hashes, request ID, timing, token categories, cost estimate, status, unknown-usage flag, sanitized diagnostics |
| `decision_events` | Run/step, Jev call reference, eligible options, selected answers, score/confidence, fallback/repair outcome |
| `idempotency_records` | Route/key, request hash, stored status/result reference, timestamp; unique route/key |
| `evaluation_batches` | Config, model/prompt/profile versions, planned/finished/failed counts, status, evidence policy, seed, timestamps |
| `evaluation_trials` | Batch, case, replicate, mode, session, blind label, evidence hash, status, elapsed/usage metrics, condition-revealed flag |
| `evaluation_ratings` | Trial, anchored ratings, notes, rater alias, unblinded flag, timestamp |

Use JSONB for immutable snapshots and flexible typed content; relational keys enforce ownership and ordering. Provide Alembic migrations and indexes for session history `(is_archived, last_activity_at, id)`, folder membership/history, pin filters, normalized folder names, active runs, events, and evaluation queries. Use PostgreSQL `pg_trgm` GIN indexes on normalized session titles and public message search_text for substring search; declare the extension explicitly in migrations and deployment requirements. Projection text is rebuilt when public content is committed, not by calling a model. Backfill folder_id=null, pin/archive=false, organization_version=1, and last_activity_at from the latest committed message or session creation for existing rows. Migrations must be idempotent at the deployment-command level (`alembic upgrade head`). The eight profiles load from versioned configuration; do not duplicate editable source definitions in database rows.

## Workspace endpoints and projection rules

`GET /sessions` returns `SessionList` containing lightweight `SessionSummary` objects, not full briefs/transcripts. Parameters: cursor, limit, optional q, folder_id, unfiled, pinned, and archive=`active|archived|all` (active default). folder_id and unfiled=true conflict. Always exclude evaluation-managed sessions. q is a trimmed 1–200-character literal substring; omit q when empty. Bind query parameters and escape LIKE wildcard syntax. Search title and normalized public message text; prefer a title hit, otherwise earliest matching message. `match` is null without q; with q it identifies the kind, plain-text snippet ≤240 characters, and matching message ID/sequence (both null for title hits). Return one result per chat. Do not return raw HTML or provider diagnostics.

`GET /sessions/{id}/messages` without cursor/anchor returns the most recent limit records in ascending sequence. `around_message_id` returns a bounded window containing a valid same-session message; it is mutually exclusive with cursor. Use the nearest earlier/later records up to limit, filling from the other side at an edge. Responses include `previous_cursor` and `next_cursor` for older/newer windows; either is null at its history boundary. Cursor requests still return ascending records. The frontend prepends/appends by message ID and preserves scroll. No pagination call executes a model.

`PATCH /sessions/{id}` is for selected profiles/settings/brief only and uses content expected_version. `PATCH /sessions/{id}/organization` accepts title/folder_id/is_pinned/is_archived and expected_organization_version. Require at least one mutation; omitted means unchanged, explicit folder_id=null unfiles. Context version never changes for organization edits. Title/pin/move are permitted during an active run; archive and delete require idle. While archived, allow title and restore only; users must restore before other mutations or sending. Reject mixed restore-plus-other-field requests and ask clients to restore then perform the second operation. Evaluation-managed sessions cannot be organized through this endpoint. Automatic title generation is compare-and-set and never overwrites a custom title.

`GET/POST /folders` lists paginated folders or idempotently creates one. `GET/PATCH/DELETE /folders/{id}` reads, renames or removes it. Rename accepts expected_version; DELETE requires the current expected_version query parameter. Delete atomically clears member sessions' folder_id, increments their organization_version, and removes the folder. It never cascades chat deletion. Folder counts distinguish active and archived member chats and exclude Lab records. New/moved chat membership checks the folder under a compatible transaction lock; concurrent deletion or stale versions cannot leave a dangling reference. Folder removal does not change last_activity_at.

UI-only theme, sidebar, open-folder and draft state remains in browser local storage rather than the provider settings endpoint. Version this shape and handle storage failure by retaining in-memory state with a concise unsaved-draft notice.

## SSE semantics

`GET /runs/{id}/events` emits persisted events using standard SSE `id`, `event`, and JSON `data` fields. `data` is a `RunEvent` envelope. Use monotonic server event IDs represented as strings. Support `Last-Event-ID` and an `after` query value; the header takes precedence. Heartbeat comments every configured interval keep an idle connection alive without creating stored events.

| Event | Required payload details |
| --- | --- |
| `run.queued`, `run.started` | Status, stage, session version |
| `run.stage` | Stage, optional persona ID, human-readable status key |
| `research.completed` | Pack ID, source IDs, availability status |
| `message.completed` | Complete public Message object and current session version |
| `run.warning` | Safe code, concise text, degraded flag |
| Terminal events | Final Run object: completed, partial, cancelled, failed, interrupted |

On connect, replay after the cursor, then tail new events. After terminal replay, close cleanly. If the supplied cursor is invalid/expired, return 409 before streaming so the client can fetch the run and message snapshots. A reconnect race cannot duplicate a displayed message because the client keys events and messages by ID. A dropped SSE connection does not cancel a run; only explicit Stop does.

## Fork and export semantics

Fork at a committed message copies the transcript prefix, selected profiles/settings, applicable brief, referenced sources, and selected saved ideas into a new session. Reassign local IDs and remap every source/message/card reference while retaining origin lineage. Expose nullable `origin_session_id` for the branch link and keep original message lineage internally; deleting a source chat clears the live source FK without deleting copied records. Rebuild derived memory from that prefix; never copy later conclusions. If neither cutoff is supplied, copy all committed messages. An ordinary prefix fork uses through_message_id (inclusive). before_message_id is exclusive; only one cutoff may be non-null. New forks are unpinned/unarchived and inherit the source folder unless folder_id is explicitly supplied (null means no folder). Source must be idle and non-archived; evaluation-managed source chats use Lab export and cannot be branched through the workspace UI. Do not copy running jobs or mutable provider state. A fork with a new mode keeps public history but uses the new mode for future turns; matched evaluation instead starts each condition from the same clean seed.

The fork endpoint now returns `ForkResult`: a Session and nullable turn_template. purpose=fork returns null. purpose=edit or regenerate requires before_message_id referencing a source user message and disallows mode overrides. Retrieve its immutable pre-turn context, selected-profile/settings snapshot and original controls on the server. Rebuild only earlier public memory and remap referenced earlier messages/ideas/sources. Reject a snapshot that cannot resolve its required references; do not silently drop a Combine target. If an original configured model is unavailable, surface that failure rather than silently substituting. For regenerate require the original round to be completed; partial/interrupted rounds use the retry flow. The returned TurnCreate template has the new session version and remapped controls; edit may replace its message text. No provider work starts until the client submits it with a separate stable idempotency key. Store fork result/template in the idempotency result so retries cannot create duplicate branches.

Markdown export includes the brief, attributed transcript, saved ideas, source list, summary, and mode/degradation labels. JSON export additionally includes schema/version metadata and public provenance, not secrets or hidden reasoning. CSV evaluation export includes one row per trial/rating with condition/evidence identifiers and missing-value markers; detailed conversations belong in JSON. Escape formula-leading cells in CSV exports.
