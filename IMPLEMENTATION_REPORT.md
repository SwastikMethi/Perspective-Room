# Implementation report

Perspective Room v1.1, built from the [`handoff/`](handoff/START_HERE.md) specification on branch
`impl/perspective-room` (one local commit per checkpoint; nothing was pushed). This report says
what works, how it was checked, what ran live, and what was not verified. Design decisions are in
[IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md); launch commands are in [README.md](README.md).

**Status.** The full local application is implemented and verified with automated tests against a
real PostgreSQL database, real-browser walkthroughs at four viewport sizes in both themes, the
Docker Compose stack (including a fresh clone) and a small live smoke against OpenAI and Jev. No
benchmark was run, so this report makes **no claim about whether Jev coordination improves
brainstorming**; the Experiment Lab exists to measure that.

## 1. What was delivered

**Conversation.** Eight configurable personalities (default trio Mentor, Skeptic, Explorer) in
three modes — Jev-guided (Jev picks the next speaker and move and audits each reply), Fixed panel
(deterministic rotation, no Jev) and Standard (one assistant, no profiles). Audiences: automatic,
one persona, everyone selected, summary. Moves: explore, challenge, expand, combine, clarify.
Explicit user choices always override routing. Every turn freezes an immutable snapshot (profiles
and hashes, settings, brief revision, models, limits, templates, provider mode); panels draft from
one snapshot and publish in roster order. Deterministic validation rejects unknown or foreign
message and source IDs and unsourced facts; at most one repair per turn; labeled fallbacks
(`Fixed order used for this turn.`) when Jev is invalid or unavailable.

**Research.** One job per turn: OpenAI hosted web search, then a separate strict normalization
call. Sources come only from `url_citation` annotations, HTTP(S) only, deduplicated without losing
citations; the normalizer cannot add sources; failed or empty searches are disclosed and never
shown as verified. Citations stay attached to fact blocks, summaries and both exports.

**Durability.** Runs are persisted and executed by an in-process worker (two concurrent runs, two
concurrent generations, a 600 s turn deadline, 40 provider attempts per turn, one retry only for
429/503/529/pre-send connection errors). Idempotency keys on every create; one active run per chat;
Stop cancels in-flight calls and prevents later publication; restart marks orphans interrupted and
never repeats an uncertain paid call; SSE replays from a cursor and never re-runs anything.

**Workspace.** Sidebar (64 px rail / 272 px expanded; drawer below 900 px), folders, pinned,
recent and archived chats, rename/move/duplicate/export/archive/restore/delete, literal search with
snippets and deep links, per-chat drafts that survive switching and reloads (with an in-memory
fallback when storage is blocked), brief revisions, saved ideas with notes and status, Combine,
feedback, forks, edit-and-branch, regenerate round, retry missing replies, Markdown/JSON export.

**Interface.** The approved cartoon design in dark (default) and light, with all eight portraits,
compact cards that expand, numbered citations, a details drawer (Brief, Saved ideas, Sources,
Summary, Run details), honest loading/empty/error/partial/missing-key states, Personalities
catalog, Settings with an explicit connection check, and a persistent demo-mode label.

**Experiment Lab.** Matched batches of the 30 authored cases × up to three conditions × up to five
repetitions (≤ 90 trials, never truncated), run one trial at a time through the normal pipeline in
Lab-only chats; seeded neutral labels (Output 1/2/3); blind rating with the doc 09 rubric
(consistency not applicable to Standard); recorded reveal with server-forced `unblinded` ratings;
results with denominators, fallback/repair counts, paired case-level differences (intent-to-treat
and sensitivity), a 2,000-resample bootstrap only from five matched cases, and unknown cost;
formula-safe CSV and JSON exports; `eval-run`, `export-eval`, `delete-eval` commands.

**Operations.** Docker Compose (`app` + `db`, loopback-only, non-root multi-stage image,
migrations and config validation at start), trusted-host and cross-site/JSON request guards,
backup/restore scripts, `validate-config`, `export-session` and `smoke-live` commands.

## 2. Commands run and results (2026-10-15, after the final fix pass)

| Check | Command | Result |
| --- | --- | --- |
| Handoff package | `python3 handoff/validation/validate_handoff.py` | passed, 630 checks |
| Backend tests (real PostgreSQL 16, demo providers) | `cd backend && uv run pytest -W error` | **406 passed** |
| Backend lint / format / types | `uv run ruff check . ../tests`, `ruff format --check`, `mypy app` | clean (57 source files) |
| Frontend types | `npx tsc --noEmit` | clean |
| Frontend unit tests | `npx vitest run` | **52 passed** (18 files) |
| Contract types current | `npm run check:api` | no drift |
| Browser tests, 1440×900 / 1920×1080 / 1024×768 / 390×844 | `npx playwright test --project desktop --project wide --project laptop --project mobile` | **38 passed** |
| Screenshots | `npx playwright test --project screenshots` | 12 images written to `docs/screenshots/` |
| Accessibility | axe (WCAG 2.1 A/AA, serious + critical) on New chat, Room, Chats, Personalities, Settings, Lab and the open drawer, both themes; keyboard-only room; reduced motion; 200 % zoom | no violations; all pass |
| Compose stack | `docker compose up --build -d` | healthy; only `127.0.0.1:8000` published, database unpublished |
| Security on the running container | bad `Host` / cross-site `POST` | 400 / 403 |
| Backup / restore | `scripts/db_backup.sh`, then `scripts/db_restore.sh <dump>` | 46 KB dump; a marker created after the backup was gone after restore, earlier data intact; a wrong confirmation word refused |
| Fresh clone | `git clone`, `cp .env.example .env`, `APP_PORT=8091 docker compose -p pr-fresh up --build -d app` | starts, migrates, validates; missing-key screens shown (port 8001 was taken by another local process) |
| Live smoke | `docker compose exec app python -m app.cli smoke-live --probe` | see §3 |

Every backend test's JSON responses are validated against `handoff/contracts/openapi.yaml`, and a
test fails if any contract operation is unrouted.

## 3. Live versus mocked

| Component | Mock-tested | Live-verified |
| --- | --- | --- |
| OpenAI generation (Responses API, strict JSON schema, `store: false`) | yes — refusal, `max_output_tokens` incomplete, invalid JSON, 401/403/404/429/5xx, timeouts, no secrets in logs | **yes** — intake, drafts, research normalization, memory and summary; `gpt-6.1-sol` answered every call |
| OpenAI web research (hosted search + normalization) | yes | **yes** — 7 real sources (no fixtures) across repaircafe.org, openrepair.org, sciencedirect.com, journals.sagepub.com; every fact block cited a stored source |
| Jev coordination and audit (`jev-1.13.0`) | yes — malformed choices, NaN, out-of-range confidence, missing answers, 422/429/529/5xx, timeouts | **yes** — routing and assessment; see the fix below |
| Connection check | yes | **yes** — both providers `ok` after configuration |
| Demo provider | yes (deterministic, labeled) | not applicable |
| Experiment Lab | yes, demo mode end to end | **no** — no live batch was run (by design: no benchmark without an explicit Run) |

Live smoke results (`exports/smoke-live-20261015T045321Z.json`, after the fixes below): Jev-guided
turn 3/3 replies (Skeptic/challenge at confidence 0.68, Explorer/explore 0.41, Mentor/clarify);
direct-person follow-up 1/1; forced-research turn 3/3; summary 1/1 with the five sections. 30
provider calls, all `ok`; 0 refusals, 0 incomplete outputs, 0 unknown usage; median latency: draft
10.4 s, route 0.3 s, assessment 0.5 s, intake 4.8 s, web search 42 s, memory 17.9 s. Reasoning
tokens stayed ≤ 468 per turn, so `OPENAI_REASONING_EFFORT` was left unset.

**Found by the live smoke and fixed (each with a failing test first):**

1. The OpenAI key was refused with `401 incorrect_hostname` — the project is bound to the US
   regional host. Added the optional `OPENAI_BASE_URL` setting; with your approval it is set to
   `https://us.api.openai.com/v1` in your `.env`. No paid call was made before this was resolved.
2. Jev returns probabilities rounded to two decimals (for example 0.04 + 0.67 + 0.26 + 0.02 =
   0.99). The validator demanded a sum within 1e-6, rejected a valid route, fell back to the first
   persona and — because that persona's move was *clarify* — ended the round after one reply. The
   check now allows ±0.005 per option.
3. Provider request IDs were stored only for failed calls (0 of 30 successes). They are now kept
   for every call (OpenAI `x-request-id`, Jev `x-typesafe-request-id`). This was verified with
   mocks and by reading Jev's header name on its free `/v1/models` endpoint, **not** re-verified
   with a further paid call.

**Personality probe** (one eight-person panel on a community seed-library idea, then a follow-up
that resolves the hosting concern; 16 replies): each perspective took a distinct angle that matched
its priorities — Mentor on a welcoming first visit, Skeptic testing whether swapping must be
reciprocal, Explorer proposing a shared growing experiment, Strategist making the value concrete,
Engineer treating the seed handoff as the first dependency, Advocate walking through a real visit,
Civic thinker on open participation rules, Health thinker on visible uncertainty about donated
seeds. All eight updated after the follow-up (the Strategist kept "not yet self-sustaining"; the
Health thinker kept its earlier concern). No invented credentials appeared. Weakness: several
follow-ups opened with near-identical phrasing ("That makes me more confident about a small
pilot"). This is an inspection of one example, not a measurement.

## 4. Test plan coverage (doc 10)

| ID | Covered by |
| --- | --- |
| T01 | `test_loads_exactly_eight_contract_personas_in_roster_order`, `test_personas_endpoint_lists_eight_with_default_trio`, catalog duplicate/missing-field tests |
| T02 | `test_explicit_target_speaks_even_if_jev_would_pick_another`, `test_explicit_target_and_move_override_jev` |
| T03 | `test_auto_never_runs_unselected_or_already_heard_personas`, `test_eligible_excludes_heard_and_keeps_selection_order`, `test_fallback_speaker_is_least_recently_heard_then_selection_order` |
| T04 | `test_route_batch_has_independent_questions_naming_each_persona` |
| T05 | `test_malformed_answers_are_rejected` (7 cases), `test_nan_from_jev_falls_back_instead_of_crashing`, `test_no_jev_key_uses_the_fixed_order_fallback`, `test_probabilities_rounded_by_the_provider_are_accepted`, e2e "a Jev outage uses the labeled fixed order" |
| T06 | `test_at_most_one_repair_per_turn_even_with_concurrent_slots`, `test_research_runs_at_most_once_and_is_shared`, `test_attempt_ceiling_refuses_the_next_call`, `test_turn_deadline_ends_a_stuck_run_and_keeps_published_output`, `test_panel_and_person_and_standard_request_counts`, `test_at_most_two_runs_execute_concurrently` |
| T07 | `test_same_key_and_body_returns_the_same_session_once`, `test_same_key_with_a_different_body_conflicts`, turn duplicate-key tests |
| T08 | `test_two_concurrent_turns_accept_exactly_one` |
| T09 | `test_stop_a_delayed_demo_run`, `test_stop_during_research_prevents_any_later_reply`, `test_stop_mid_panel_publishes_nothing_further`, `test_stop_before_a_call_prevents_it` |
| T10 | `test_replay_streams_each_event_once_then_closes_after_terminal`, `test_cursor_resumes_after_the_last_seen_event_and_header_wins`, `test_replay_and_reconnect_never_create_provider_work`, e2e "a dropped event stream reconnects without resubmitting the turn", "reload mid-run reconnects…" |
| T11 | `test_restart_recovery_interrupts_orphans_without_repeating_paid_work`, `test_queued_ordinary_runs_survive_restart_but_lab_runs_are_cancelled` |
| T12 | `test_refusal_is_a_distinct_outcome`, `test_incomplete_max_output_tokens_is_a_distinct_outcome`, `test_invalid_json_text_is_incomplete_not_success`, `test_failed_summary_call_is_never_resent`, e2e provider-failure spec |
| T13 | `test_fake_or_foreign_citation_is_rejected`, `test_foreign_message_reference_is_rejected` |
| T14 | `test_normalizer_cannot_add_sources`, `test_research_normalizer_cannot_add_sources` |
| T15 | `test_injected_instructions_in_evidence_are_inert` |
| T16 | `test_brief_edit_creates_an_immutable_revision`, `test_next_run_uses_the_new_brief_and_flags_older_memory` |
| T17 | `test_prefix_fork_copies_only_the_chosen_history`, `test_full_fork_remaps_message_and_source_references`, `test_mid_round_fork_memory_never_covers_cut_replies`, `test_copied_research_packs_point_at_the_forks_own_sources` |
| T18 | `test_retry_fills_only_the_missing_replies`, `test_a_failing_persona_does_not_starve_the_others`, e2e "a partial round offers Retry missing replies…" |
| T19 | `test_summary_fixture_passes_and_keeps_its_disagreement`, `test_summary_section_order_and_count_are_enforced`, `test_summary_references_must_resolve` |
| T20 | `test_standard_and_fixed_panel_make_zero_jev_calls`, `test_fixed_panel_and_jev_snapshots_hold_the_same_conditions`, `test_a_small_matched_batch_runs_through_the_normal_pipeline` |
| T21 | `test_blinded_trials_hide_the_condition_until_revealed`, `test_results_disclose_ratings_made_after_reveal`, e2e Lab spec |
| T22 | `test_oversized_or_invalid_batches_are_refused_never_truncated`, `test_cancel_keeps_finished_trials_and_starts_nothing_new` |
| T23 | `test_exports_escape_formulas_mark_missing_values_and_reveal`, `test_formula_leading_cells_are_prefixed`, `test_json_export_keeps_the_source_chain_and_public_metadata`, `test_markdown_export_is_attributed_and_cites_by_number`, `test_exports_never_contain_keys_or_prompts` |
| T24 | `test_cross_site_mutations_are_rejected`, `test_mutation_bodies_must_be_json`, `test_untrusted_host_headers_are_refused`, `test_compose_publishes_only_loopback_and_never_the_database`, `test_built_frontend_contains_no_key_material` |
| T25 | `test_deleting_a_chat_removes_everything_it_owns`, `test_delete_refuses_active_session`, `test_lab_sessions_cannot_be_driven_from_the_workspace` |
| T26 | e2e journey (sidebar expand/collapse and light theme survive reload, at four sizes), `ui.test.ts` (persisted key, storage failure), pre-paint theme script in `index.html` |
| T27 | `test_folder_create_is_idempotent_and_names_are_unique_ignoring_case`, `test_folder_rename_checks_version_and_uniqueness`, `test_deleting_a_folder_keeps_and_unfiles_active_and_archived_chats`, e2e folders spec |
| T28 | `test_organization_edits_during_a_run_leave_content_and_snapshot_alone`, `test_context_edits_are_blocked_during_a_run_and_while_archived` |
| T29 | `test_search_prefers_titles_then_the_earliest_matching_message`, `test_search_treats_wildcards_literally_and_bounds_snippets`, `test_search_pages_are_stable_and_cursors_are_bound_to_the_query`, `SearchDialog.test.tsx`, e2e search + deep link |
| T30 | e2e drafts spec and "switching chats in-app starts each room fresh…", `drafts.test.ts`, `StorageNotice.test.tsx` |
| T31 | `test_archived_chats_allow_only_rename_and_restore`, `test_history_lists_filter_and_order_by_last_activity`, e2e archive and delete-clears-only-that-draft specs |
| T32 | `test_edit_first_message_branches_before_it_with_the_pre_turn_brief`, `test_edit_inside_a_fork_and_source_deletion_keeps_copies`, e2e edit-and-branch |
| T33 | `test_regenerate_a_completed_round`, `test_regenerate_needs_a_completed_round_and_mode_overrides_are_refused`, `test_retry_is_refused_for_completed_or_superseded_rounds`, e2e regenerate |
| T34 | e2e "select all eight and ask everyone…" (roster order, no overflow), overflow spec at four sizes (2,000-character unbroken lines, a 16,000-character message, eight long replies) |
| T35 | `test_concurrent_folder_delete_and_move_never_orphan_a_chat`, `test_move_into_own_folder_racing_its_deletion_never_deadlocks`, `actions.test.ts` (lost-response duplicate), `send.test.ts` (lost-response resend, pending conflicts) |

## 5. Screenshots (actual app, demo mode)

| State | File |
| --- | --- |
| Dark, collapsed rail | [room-dark-rail.png](docs/screenshots/room-dark-rail.png) |
| Light, collapsed rail | [room-light-rail.png](docs/screenshots/room-light-rail.png) |
| Dark, expanded sidebar with an open folder | [room-dark-sidebar-folder-open.png](docs/screenshots/room-dark-sidebar-folder-open.png) |
| Light, expanded sidebar with an open folder | [room-light-sidebar-folder-open.png](docs/screenshots/room-light-sidebar-folder-open.png) |
| Search with results | [search-results.png](docs/screenshots/search-results.png) |
| Folder view | [folder-view.png](docs/screenshots/folder-view.png) |
| Eight selected, eight replies | [eight-selected-eight-replies.png](docs/screenshots/eight-selected-eight-replies.png) |
| Long reply with citations | [long-cited-reply.png](docs/screenshots/long-cited-reply.png) and [sources-drawer.png](docs/screenshots/sources-drawer.png) |
| Long multi-turn chat | [long-multi-turn-chat.png](docs/screenshots/long-multi-turn-chat.png) |
| Mobile room and composer | [mobile-room-composer.png](docs/screenshots/mobile-room-composer.png) |
| Mobile navigation | [mobile-navigation.png](docs/screenshots/mobile-navigation.png) |

Each image was inspected against the approved mockups; the issues found (wrapped card actions,
a three-row mobile composer, a truncated mobile header) were fixed and the images re-captured.

## 6. Independent reviews

A fresh reviewer gated checkpoints 1–6. Checkpoint 7 (browser suite, security, live smoke, docs)
was gated by the whole-branch review of `c8ff1a3..830b6ac`, which found 1 critical, 4 important
and 9 minor issues. Every Critical and Important finding was reproduced as a failing test before
it was fixed (details in IMPLEMENTATION_NOTES.md §5). Fixed in the final pass:

- **An empty `OPENAI_BASE_URL` (as shipped in `.env.example`) broke every live OpenAI call** on
  standard projects. Empty now means the default host.
- **A rejected key or unavailable model was hidden in the room** behind a misleading intake note,
  and a Retry that could not work was offered. The room now shows the error with a link to
  Settings → Check connection, and offers no Retry when the error is not retryable or nothing is
  missing.
- **Long unbroken model-written text** (summary items, `new_angle`, `next_question`, Brief and
  Summary tabs) overflowed the page. It now wraps; the overflow spec covers it at four sizes.
- **Blocked browser storage blanked the Lab rating view** and broke *Clear local workspace
  state*. Both use the guarded storage wrapper.
- **Low-confidence Jev routing was neither shown nor counted.** It now adds a run note and is
  counted separately in Lab results and the CSV (`low_confidence_fallback`), hidden while blind.
- **New chat re-sent an unfinished first Send by itself on page load** (paid work on route mount).
  It now asks: *Send it now* or *Discard the earlier send*.
- **Only the first 30 saved ideas loaded**, giving a wrong bookmark state. All pages load.
- **A failed backup left a partial dump under a valid-looking name**, and a failed restore left
  the app stopped. The dump is renamed only on success; a failed restore restarts the app and says
  the database may be partly restored.
- From a separate plan audit: Stop during the memory stage leaves nothing to retry (tested);
  replies added by a retry are labeled "added by retry"; archiving or deleting a running chat
  offers to stop it first.

Five minor findings were deferred (§7).

## 7. Limitations and what is not verified

- **No benchmark was run** and the Lab was not exercised live; whether Jev improves breadth or
  usefulness is unknown. The seed set is a 30-case pilot, not a validated benchmark.
- Request-ID capture on successful calls is verified with mocks, not with a further live call.
- Live checks covered one Jev-guided turn, one direct question, one research turn, one summary and
  one eight-person probe — a smoke test, not a quality study. Live Fixed-panel, Standard,
  retry, fork, edit and regenerate paths were exercised only in demo mode (they reuse the same
  adapters).
- Cost is unknown everywhere (no price table, G21); a configured cost cap is shown as
  unenforceable.
- The worker, notifier and Lab scheduler assume a single backend process.
- Blinding is a presentation aid: a local owner can inspect conditions through the raw API, and a
  Jev-only clarification can hint at condition C.
- Portrait crops come from the 1.5 MB approved mockup images (preloaded after start).
- The browser tests ran on Chromium only.
- Deferred minor findings from the final review: a fast double-click on save can create two
  saved ideas; `model_unavailable` is recognized only on a 404; an invalid Jev key is retried on
  every step of a turn (shown only as "Fixed order used"); saved-idea notes have no token budget
  beyond the submit-time check; drafts are written on every keystroke (no 300 ms debounce).
