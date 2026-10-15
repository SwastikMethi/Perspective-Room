# Implementation acceptance checklist

This checklist is intentionally unmarked. It is for the implementation agent to complete with actual evidence. Documentation validation does not establish application correctness.

Completed 2026-10-15. Evidence references point to [IMPLEMENTATION_REPORT.md](../IMPLEMENTATION_REPORT.md) (§ numbers), test names in `tests/backend` and `frontend/src`, browser specs in `frontend/e2e`, and screenshots in `docs/screenshots`.

## Product

- [x] All eight configured personalities are selectable and behaviorally distinct in inspected examples. — `test_loads_exactly_eight_contract_personas_in_roster_order`; e2e "select all eight…"; live eight-person probe inspected (report §3).
- [x] Auto, direct-person, panel, reply, explore, challenge, combine, and summary flows work. — orchestrator integration tests; e2e journey (Ask more, panel, Combine, Summarize) at four sizes; live smoke covered auto, direct-person and summary (report §3).
- [x] Explicit user choices override automatic routing. — `test_explicit_target_speaks_even_if_jev_would_pick_another`, `test_explicit_target_and_move_override_jev`.
- [x] First panel views are generated from an identical input snapshot. — panel drafts share one run snapshot (plan G8); `test_fixed_panel_and_jev_snapshots_hold_the_same_conditions`; roster-order e2e.
- [x] Brief edits are versioned; user corrections override derived memory. — `test_brief_edit_creates_an_immutable_revision`, `test_next_run_uses_the_new_brief_and_flags_older_memory`.
- [x] Saved ideas, notes/status, forks, persistence, deletion, and exports work. — `test_saved_ideas_lifecycle`, fork tests, `test_deleting_a_chat_removes_everything_it_owns`, export tests; e2e journey (save two ideas, Combine, fork, export, reload).
- [x] Chat history, title/body search, pinning, archive/restore, rename, move and export work after refresh. — `tests/backend/integration/test_workspace.py`; e2e workspace spec and journey reload.
- [x] Folder create/rename/open/close/delete works; folder deletion retains every member chat. — `test_deleting_a_folder_keeps_and_unfiles_active_and_archived_chats`; e2e folders spec.
- [x] Copy/reply, edit-and-branch and regenerate-round actions preserve published source history. — `copy` unit tests; e2e edit-and-branch (original unchanged) and regenerate; `test_edit_inside_a_fork_and_source_deletion_keeps_copies`.
- [x] Per-chat drafts and ongoing generation survive switching among chats without duplicate work. — e2e drafts spec and "switching chats in-app…"; `drafts.test.ts`; `send.test.ts` (no duplicate resend).
- [x] Sources are visible, clickable, and attached to the relevant factual blocks. — `test_sources_come_from_citations_and_flow_into_cited_contributions`; numbered citation chips open the Sources drawer (`sources-drawer.png`); live: 7 real sources, every fact block cited.
- [x] Research failure and uncertainty are represented honestly. — `test_failed_search_is_disclosed_and_brainstorming_continues`, `test_empty_search_is_not_a_verification`; e2e "a failed search is disclosed…".

## Integration and reliability

- [x] Real OpenAI and Jev adapters are implemented, with documented configuration. — `backend/app/providers/{openai_adapter,jev_adapter}.py`; README; live-verified (report §3).
- [x] Demo mode is explicit and never substitutes for a live failure. — `APP_PROVIDER_MODE=demo` only; live without keys returns `provider_not_ready` (fresh-clone check); `test_run_queued_under_another_provider_mode_never_calls_a_provider`.
- [x] Jev request/response contracts, independent questions, and fallback behavior are tested. — `tests/backend/unit/test_jev.py`; fallback integration tests; live rounding issue found and fixed (report §3).
- [x] Duplicate submissions and concurrent turns cannot duplicate logical work. — idempotency tests; `test_two_concurrent_turns_accept_exactly_one`; e2e double Enter.
- [x] Stop prevents new work and late publication; published messages survive. — Stop tests (T09); e2e "Stop a delayed run".
- [x] SSE replay does not rerun generation or duplicate displayed messages. — SSE tests (T10); e2e reconnect specs.
- [x] Restart recovery preserves committed output and marks uncertain work interrupted. — `test_restart_recovery_interrupts_orphans_without_repeating_paid_work`.
- [x] Provider refusal, truncation, malformed output, timeout, and partial failure are handled. — adapter and call-policy tests (T12); `test_timeout_is_unknown_usage_and_never_resubmitted`; partial-failure retry tests.
- [x] Context, contribution, retry, research, deadline, and concurrency limits are enforced. — T06 tests; `test_required_context_over_the_ceiling_is_refused_at_submit`.
- [x] Credentials are absent from browser bundles, logs, exports, and git. — `test_built_frontend_contains_no_key_material` (also checks the real `.env` values), `test_exports_never_contain_keys_or_prompts`, adapter log tests; git history scanned for the configured key values (none).
- [x] The application is published on loopback only; database port is private. — `test_compose_publishes_only_loopback_and_never_the_database`; `docker compose ps` (report §2).

## UI

- [x] Start, Chats, Folder, Room, Personalities, Lab, and Settings screens are complete. — axe scan over each; screenshots; e2e specs.
- [x] Visual implementation follows the approved cartoon references, including all eight recognizable portraits. — `room-*-rail.png`, `room-*-sidebar-folder-open.png` vs `handoff/ui/*.png`; sprite math test.
- [x] Dark is default; dark/light switch persists and themes every screen/menu/dialog. — pre-paint theme script; `ui.test.ts`; e2e journey; axe in both themes including the drawer.
- [x] Sidebar expands/collapses; mobile drawer, search, chat menus and open folder children are keyboard accessible. — e2e journey (both states, Escape returns focus), `focus.test.tsx`, keyboard spec.
- [x] All-eight panel replies, long responses with sources and multi-turn history reflow without clipping; details stay closed by default. — overflow spec at four sizes; `eight-selected-eight-replies.png`, `long-cited-reply.png`, `long-multi-turn-chat.png`.
- [x] Desktop and mobile walkthroughs pass without overflow or unreachable controls. — 38 browser tests at 1440×900, 1920×1080, 1024×768, 390×844 (report §2).
- [x] Loading, empty, partial, error, cancellation, reconnect, and missing-key states are usable. — failures spec; empty states in workspace spec; missing-key screen checked on the fresh clone.
- [x] Keyboard navigation, focus, reduced motion, readable contrast, and zoom are checked. — `frontend/e2e/a11y.spec.ts` (axe WCAG 2.1 AA, keyboard-only room, reduced motion, 200 % zoom).
- [x] No fake benchmark metrics, decorative reasoning traces, or unfinished required controls appear. — Lab shows only measured values (`ResultsView.test.tsx`: missing means stay empty); no placeholder routes remain.

## Experiment

- [x] Standard, Fixed panel, and Jev-guided are implemented with recorded configuration. — batch snapshot (models, profile and template hashes, cases version/hash, limits, seed); `test_a_small_matched_batch_runs_through_the_normal_pipeline`.
- [x] Matched comparisons hold model/profile/evidence settings appropriately constant. — B/C snapshot equality in the batch test; A and B make zero Jev calls.
- [x] Blind labels and reveal tracking work; persona consistency is null for Standard. — `test_blinded_trials_hide_the_condition_until_revealed` (incl. `consistency_not_applicable`).
- [x] Incomplete/degraded trials remain in denominators and exports. — results warnings list planned/completed/incomplete and fallback/repair counts; CSV keeps one row per trial with `NA`.
- [x] Synthetic/demo data is labeled and excluded from live effectiveness claims. — demo batches flagged in results; fixture sources labeled; this release makes no effectiveness claim.
- [x] Ratings, paired comparisons, uncertainty display, and CSV/JSON export work. — `test_results_math.py`, export tests, e2e Lab spec.
- [x] No large live benchmark runs without an explicit Run action. — UI Run button with live confirmation; `eval-run` confirmation; no benchmark was run.

## Delivery

- [x] A fresh checkout starts using the documented Docker Compose command. — fresh-clone check (report §2).
- [x] Migrations, seed loading, dependency lockfiles, and environment template are supplied. — `backend/migrations`, catalog loaded from `handoff/` and validated at start, `backend/uv.lock`, `frontend/package-lock.json`, `.env.example`.
- [x] Required automated tests and actual browser checks were run; results are recorded. — report §2.
- [x] Actual-app screenshots include both themes, both sidebar states, a folder, search, all eight replies, long content and mobile navigation. — report §5.
- [x] Any live smoke tests are identified separately from mocks; missing access is disclosed. — report §3 (live vs mocked table; what was not live-verified).
- [x] Implementation notes, report, screenshots, and exact launch commands are delivered. — `IMPLEMENTATION_NOTES.md`, `IMPLEMENTATION_REPORT.md`, `docs/screenshots/`, `README.md`.

The experimental conclusion may be positive, negative, or inconclusive. Marking the application complete must never require inventing evidence that Jev improves it.
